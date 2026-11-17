# A Confidence-Weighted, Adaptive Multimodal Framework for Offline Voice-Gesture Assistive HCI

This project is an offline, assistive human-computer interaction (HCI) framework designed to help users control a computer using hand gestures and voice commands without a physical keyboard or mouse. It is intended for accessibility-focused use cases where users may have limited mobility or prefer hands-free interaction.

The system combines:

- **Gesture recognition** from a webcam using MediaPipe
- **Speech recognition** from the microphone using faster-whisper
- **Action execution** via PyAutoGUI and system commands
- **Confidence-weighted modality fusion** with adaptive thresholding when gesture and voice inputs co-occur
- **Browser-based control panel** for real-time monitoring, gesture training, and configuration

---

## Project Overview

The project is split into two primary components:

- `backend/` contains the Flask + Socket.IO server, recognition logic, multimodal fusion engine, and action execution modules.
- `frontend/` contains the browser UI, styling, client-side scripts, and MediaPipe model assets.

The application runs locally on the host machine, ensuring low latency, privacy, and full offline operation without requiring cloud API calls.

---

## Key Features

- **Offline Gesture Control**: Real-time hand landmark tracking and gesture recognition via MediaPipe.
- **Offline Voice Recognition**: Local speech-to-command decoding powered by faster-whisper.
- **Confidence-Weighted Multimodal Fusion**: Proposes actions from both channels within a sliding time window and resolves conflicts using confidence scoring.
- **Adaptive Custom Gesture Learning**: Train custom hand gestures on the fly; landmark templates and dynamic thresholds adapt to individual user consistency.
- **Comprehensive Action Mapping**: Controls mouse movement, clicks, scrolling, keyboard shortcuts, window management, media volume, screen brightness, and application launchers.
- **Modern Interactive Dashboard**: Web-based interface for live camera preview, audio visualizer, real-time event logs, and settings configuration.

---

## Architecture

```
Webcam Input ───► MediaPipe Gesture Recognizer ───┐
                                                  ▼
                                         Modality Fusion Engine ──► Action Executor ──► OS / Desktop
                                                  ▲
Microphone   ───► faster-whisper Voice Engine  ───┘
```

1. **Camera Stream**: Processed in real time by the gesture recognizer to identify standard and custom gestures.
2. **Audio Stream**: Segmented and transcribed locally by faster-whisper to detect mapped command phrases.
3. **Multimodal Fusion**: Compares gesture and voice proposals within a configurable time window (`fusion_window`), computing confidence scores to arbitrate or trigger complementary actions.
4. **Action Executor**: Simulates mouse clicks, keystrokes, window operations, and system utilities.

---

## Technology Stack

- **Backend Framework**: Python 3.10+, Flask, Flask-SocketIO, Flask-CORS, Eventlet
- **Computer Vision**: OpenCV, MediaPipe, NumPy
- **Speech Recognition**: faster-whisper, SoundDevice
- **Automation & OS Control**: PyAutoGUI, pyttsx3, screen-brightness-control
- **Frontend**: HTML5, CSS3, JavaScript (WebSocket client)

---

## Project Structure

```text
├── backend/
│   ├── app.py                     # Main server and coordination hub
│   ├── action_executor.py         # OS automation & action execution
│   ├── config.json                # Mappings, thresholds & gesture templates
│   ├── fusion.py                  # Confidence-weighted multimodal fusion
│   ├── gesture_recognition.py     # MediaPipe hand tracking & custom gesture matcher
│   ├── voice_recognition.py       # faster-whisper audio processor
│   └── logs/                      # Session activity & fusion logs (runtime)
├── frontend/
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css          # UI styles and dashboard themes
│   │   ├── js/
│   │   │   └── main.js            # Frontend WebSocket logic & UI controls
│   │   └── models/
│   │       └── gesture_recognizer.task # MediaPipe gesture model
│   └── templates/
│       └── index.html             # Dashboard interface
├── requirements.txt               # Top-level dependencies
├── requirements-lock.txt          # Pinned dependency versions
├── .gitignore                     # Git ignore rules for venv, cache & logs
└── README.md                      # Project documentation
```

---

## Setup & Installation

### Prerequisites

- Python 3.10, 3.11, or 3.12
- Working webcam and microphone
- Windows, macOS, or Linux (Windows recommended for full OS automation support)

### 1. Clone the Repository

```bash
git clone https://github.com/Dhanu1110/Dhanu1110-A-CONFIDENCE-WEIGHTED-ADAPTIVE-FRAMEWORK-FOR-OFFLINE-VOICE-GESTURE-ASSISTIVE-HCI.git
cd Dhanu1110-A-CONFIDENCE-WEIGHTED-ADAPTIVE-FRAMEWORK-FOR-OFFLINE-VOICE-GESTURE-ASSISTIVE-HCI
```

### 2. Create and Activate a Virtual Environment

```bash
python -m venv .venv

# Windows (Command Prompt / PowerShell)
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Running the Application

From the project root directory, run:

```bash
python backend/app.py
```

Then open your browser and navigate to:

```text
http://127.0.0.1:5000
```

---

## Supported Actions

- **Mouse Control**: Cursor movement, left click, double click, right click, scroll up/down
- **Keyboard Shortcuts**: Copy, paste, cut, undo, redo, save, Enter, Escape, Space
- **Window Management**: Minimize window, maximize window, next tab, previous tab, new tab, close tab, switch window
- **App Launching**: Browser, File Explorer, Notepad, Settings, Mail
- **System Utilities**: Volume up/down/mute, brightness up/down, lock screen, screenshot, tell time/date, read screen

---

## Configuration

Configuration parameters are stored in `backend/config.json`. Key configuration sections include:

- **`settings`**: Camera index/resolution, cooldown timers, fusion window duration, modality weights, Whisper model size (`base.en`), energy thresholds.
- **`gestures`**: Gesture-to-action bindings.
- **`voice_commands`**: Spoken phrase-to-action bindings.
- **`custom_gesture_data`**: Stored landmark coordinate templates for trained custom gestures.

---

## Notes & Troubleshooting

- **Offline Execution**: Once the Whisper model is downloaded on initial launch, speech recognition runs completely offline from local cache.
- **Logs**: Detailed fusion and session telemetry are stored in `backend/logs/` in JSONL format for diagnostic and research evaluation.
- **Permissions**: Ensure your terminal/Python process has accessibility and screen capture permissions on your operating system.

---


