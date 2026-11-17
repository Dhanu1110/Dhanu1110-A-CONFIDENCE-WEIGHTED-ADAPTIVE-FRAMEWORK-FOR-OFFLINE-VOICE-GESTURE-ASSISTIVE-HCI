"""
Voice Recognition Module using Whisper (faster-whisper)
Transformer-based speech-to-text with Voice Activity Detection (VAD),
pre-speech buffering, dynamic noise adaptation, and domain vocabulary conditioning.
"""

import os
import re
import time
import queue
import threading
from collections import deque
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel


class VoiceRecognizer:
    def __init__(self, model_size='base.en', sample_rate=16000, config=None, device='cpu', compute_type='int8'):
        """
        Initialize Whisper voice recognizer.
        
        Args:
            model_size (str): Whisper model ('tiny.en', 'base.en', 'small.en'). Default 'base.en'.
            sample_rate (int): Audio sample rate in Hz (16000).
            config (dict): Application configuration dict.
            device (str): Device to run inference on ('cpu').
            compute_type (str): Quantization type ('int8' for fast, low-RAM CPU execution).
        """
        self.sample_rate = sample_rate
        self.config = config or {}
        
        settings = self.config.get('settings', {})
        self.model_size = settings.get('whisper_model', model_size)
        self.device = settings.get('whisper_device', device)
        self.compute_type = settings.get('whisper_compute_type', compute_type)
        
        # Audio energy threshold & timing parameters
        self.base_energy_threshold = float(settings.get('whisper_energy_threshold', 0.008))
        self.ambient_energy = 0.003
        self.pause_threshold = float(settings.get('whisper_pause_threshold', 0.45))       # Sec of silence to finalize utterance
        self.min_phrase_duration = float(settings.get('whisper_min_phrase', 0.20))      # Ignore noise/pops shorter than this
        self.max_phrase_duration = float(settings.get('whisper_max_phrase', 3.50))      # Max duration before forcing transcription
        
        # Build initial prompt to bias Whisper's decoder towards application vocabulary
        self.initial_prompt = self._build_prompt()
        
        try:
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=4
            )
        except Exception as e:
            self.model_size = 'tiny.en'
            self.model = WhisperModel(
                'tiny.en',
                device='cpu',
                compute_type='int8',
                cpu_threads=4
            )

        self.audio_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.running = True
        
        # Pre-speech buffer: keeps the last ~400ms of audio (8 blocks of 50ms)
        # Prevents initial unvoiced consonants ('c', 's', 'p', 'th') from being clipped
        self.pre_buffer = deque(maxlen=8)
        
        # Process audio in 50ms chunks (800 frames @ 16kHz)
        self.block_size = int(self.sample_rate * 0.05)
        
        # Background worker for VAD speech segmentation and Whisper inference
        self.worker_thread = threading.Thread(target=self._transcription_worker, daemon=True)
        self.worker_thread.start()
        
        # Start sounddevice microphone stream
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                dtype='float32',
                channels=1,
                callback=self._audio_callback
            )
            self.stream.start()
        except Exception as e:
            self.running = False
            raise RuntimeError(f"Failed to start microphone stream: {e}")

    def _build_prompt(self):
        """Construct domain vocabulary prompt for Whisper decoder priming."""
        commands = [
            "click", "double click", "right click", "open browser", "close browser",
            "new tab", "close tab", "next tab", "previous tab", "scroll up", "scroll down",
            "zoom in", "zoom out", "copy", "paste", "enter", "space", "backspace",
            "maximize window", "minimize window", "volume up", "volume down", "mute",
            "brightness up", "brightness down", "increase brightness", "decrease brightness",
            "open notepad", "open settings", "open mail", "open file explorer",
            "what time is it", "what date is it", "what date and time is it", "what date time is it",
            "tell time", "tell date", "date and time",
            "shut down", "restart", "refresh", "screenshot"
        ]
        if self.config and 'voice_commands' in self.config:
            custom = [
                v.get('command') for v in self.config['voice_commands'].values()
                if v.get('command') and v.get('command') != '.'
            ]
            if custom:
                commands = list(set(commands + custom))
        return ", ".join(commands)

    def _audio_callback(self, indata, frames, time_info, status):
        """Sounddevice streaming callback."""
        if self.running:
            self.audio_queue.put(indata.copy())

    def _transcription_worker(self):
        """
        Background worker that continuously consumes audio chunks,
        tracks ambient noise, detects speech onset with pre-buffer prepend,
        detects phrase completion via silence, and executes Whisper inference.
        """
        phrase_buffer = []
        is_speaking = False
        silence_start_time = None
        phrase_start_time = None
        
        while self.running:
            try:
                block = self.audio_queue.get(timeout=0.1)
                audio_chunk = block.flatten()
                
                # Compute RMS energy of audio frame
                energy = float(np.sqrt(np.mean(audio_chunk**2)))
                now = time.time()
                
                # Dynamic threshold based on rolling ambient noise
                dynamic_threshold = max(self.base_energy_threshold, self.ambient_energy * 2.2)
                
                if energy >= dynamic_threshold:
                    if not is_speaking:
                        is_speaking = True
                        phrase_start_time = now
                        # Include pre-speech buffer so leading consonants are intact
                        phrase_buffer = list(self.pre_buffer)
                    silence_start_time = None
                    phrase_buffer.append(audio_chunk)
                else:
                    if not is_speaking:
                        # Update rolling ambient noise floor when quiet
                        self.ambient_energy = 0.95 * self.ambient_energy + 0.05 * energy
                        self.pre_buffer.append(audio_chunk)
                    else:
                        phrase_buffer.append(audio_chunk)
                        if silence_start_time is None:
                            silence_start_time = now
                        
                        silence_duration = now - silence_start_time
                        phrase_duration = now - phrase_start_time
                        
                        # Check phrase termination criteria
                        if silence_duration >= self.pause_threshold or phrase_duration >= self.max_phrase_duration:
                            is_speaking = False
                            silence_start_time = None
                            
                            if phrase_buffer:
                                full_audio = np.concatenate(phrase_buffer)
                                phrase_buffer = []
                                
                                if phrase_duration >= self.min_phrase_duration and len(full_audio) > 0:
                                    self._transcribe_audio(full_audio)
            except queue.Empty:
                continue
            except Exception:
                pass

    def _transcribe_audio(self, audio_data):
        """Perform Whisper inference on audio array."""
        try:
            t0 = time.time()
            segments, info = self.model.transcribe(
                audio_data,
                language="en",
                task="transcribe",
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
                initial_prompt=self.initial_prompt,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=180, speech_pad_ms=200)
            )
            
            raw_text = " ".join([seg.text for seg in segments]).strip()
            
            # Normalize text: convert hyphens/slashes to spaces before stripping punctuation
            cleaned_text = re.sub(r'[-_/\\]', ' ', raw_text)
            cleaned_text = re.sub(r'[^\w\s]', '', cleaned_text)
            cleaned_text = " ".join(cleaned_text.split()).strip().lower()
            
            latency_ms = (time.time() - t0) * 1000.0
            
            # Filter out hallucinations / non-commands
            hallucinations = {'you', 'thank you', 'thanks for watching', 'subtitles', 'subtitles by'}
            if cleaned_text and cleaned_text not in hallucinations and len(cleaned_text) >= 2:
                avg_logprob = getattr(info, 'avg_logprob', -0.2)
                confidence = float(np.clip(np.exp(avg_logprob) if avg_logprob is not None else 0.95, 0.1, 1.0))
                
                result = {
                    'text': cleaned_text,
                    'raw_text': raw_text,
                    'confidence': round(confidence, 2),
                    'final': True,
                    'latency_ms': round(latency_ms, 1)
                }
                self.result_queue.put(result)
        except Exception:
            pass

    def recognize(self):
        """
        Poll for recognition results (non-blocking).
        Returns a dict with 'text', 'confidence', 'final', or None if no result.
        """
        if not self.running:
            return None
        try:
            if not self.result_queue.empty():
                return self.result_queue.get_nowait()
        except queue.Empty:
            pass
        return None

    def stop(self):
        """Stop recognizer and release microphone stream and worker thread."""
        self.running = False
        try:
            if hasattr(self, 'stream') and self.stream:
                self.stream.stop()
                self.stream.close()
        except Exception:
            pass
