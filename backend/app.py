"""
Main Flask Application for Real Gesture and Voice HCI System
Handles web server, WebSocket connections, and coordinates all modules
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import cv2
import base64
import json
import threading
import time

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'frontend'))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')

# Session Event Logging Setup for analyze_session_log.py
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)
SESSION_LOG_PATH = os.path.join(LOGS_DIR, f'session_{time.strftime("%Y%m%d_%H%M%S")}.jsonl')

def log_event(event_data):
    try:
        with open(SESSION_LOG_PATH, 'a') as f:
            f.write(json.dumps(event_data) + '\n')
    except Exception as e:
        print(f"Logging error: {e}")

log_event({'event_type': 'session_start', 'timestamp': time.time()})

import pyautogui
from gesture_recognition import GestureRecognizer 
from voice_recognition import VoiceRecognizer
from action_executor import ActionExecutor
from fusion import ModalityFusion

# Initialize Flask app with frontend template and static paths
app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, 'templates'),
    static_folder=os.path.join(FRONTEND_DIR, 'static')
)
app.config['SECRET_KEY'] = 'gesture-voice-hci-secret-key'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize modules
action_executor = ActionExecutor()
fusion = ModalityFusion(
    fusion_window=1.0,
    gesture_weight=1.0,
    voice_weight=1.0,
    logger=None
)
gesture_recognizer = None
voice_recognizer = None

SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# Global state
app_state = {
    'gesture_enabled': False,
    'voice_enabled': False,
    'camera_active': False,
    'cursor_enabled': False,
    'last_gesture': None,
    'last_command': None,
    'statistics': {
        'gestures_recognized': 0,
        'commands_recognized': 0,
        'actions_executed': 0
    }
}

# --- MODIFIED: State for Learning Gestures ---
config_lock = threading.Lock()
learning_mode = False
new_gesture_name = None
learning_status = {"status": "idle", "message": ""}
learning_samples = []
TARGET_SAMPLES = 30 # Set to 30 for speed, you can change this to 50
action_execution_lock = threading.Lock()
APP_LAUNCH_ACTIONS = {
    'open_browser',
    'open_file_explorer',
    'open_notepad',
    'open_settings',
    'open_mail'
}
REPEATABLE_NAVIGATION_ACTIONS = {
    'new_tab',
    'next_tab',
    'previous_tab',
    'close_tab',
    'switch_window',
    'right_click'
}
NAVIGATION_REPEAT_INTERVAL = 2.0
# --- END MODIFIED ---


# --- Configuration Management (Unchanged) ---
def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"{CONFIG_PATH} not found, creating a default one.")
        default_config = get_default_config()
        save_config(default_config)
        return default_config
    except json.JSONDecodeError:
        print(f"Error reading {CONFIG_PATH}, it might be corrupted. Using default.")
        return get_default_config()

def save_config(new_config):
    global config
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(new_config, f, indent=2)
        config = new_config 
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

def get_default_config():
    return {
        "settings": {
            "camera_index": 0,
            "camera_width": 640,
            "camera_height": 480,
            "gesture_cooldown": 0.5,
            "voice_cooldown": 0.5,
            "fusion_window": 1.0,
            "gesture_weight": 1.0,
            "voice_weight": 1.0,
            "voice_sample_rate": 16000,
            "background_color": "#667eea"
        },
        "gestures": { "Thumb_Up": { "name": "Thumbs Up", "action": "click" } },
        "voice_commands": { "click": { "command": "click", "action": "click" } },
        "custom_gesture_data": {}
    }

config = load_config()


def sync_fusion_settings(settings):
    fusion.update_settings(
        fusion_window=settings.get('fusion_window', 1.0),
        gesture_weight=settings.get('gesture_weight', 1.0),
        voice_weight=settings.get('voice_weight', 1.0)
    )


sync_fusion_settings(config['settings'])


def log_fusion_decision(modality, action, confidence, raw_label, decision):
    weight = fusion.weights.get(modality, 1.0)
    score = confidence * weight
    fusion_data = {
        'modality': modality,
        'label': raw_label,
        'action': action,
        'confidence': confidence,
        'weight': weight,
        'score': score,
        'winner': decision['winner'],
        'execute': decision['execute'],
        'reason': decision['reason']
    }
    socketio.emit('fusion_decision', fusion_data)
    log_event({'event_type': 'fusion_decision', **fusion_data})

# --- HTTP Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'static'), path)

@app.route('/api/config', methods=['GET'])
def get_config_api():
    return jsonify(config)

@app.route('/api/config/settings', methods=['POST'])
def update_settings():
    global config
    try:
        new_settings = request.json.get('settings')
        if new_settings:
            with config_lock:
                config['settings'].update(new_settings)
                save_config(config)
                sync_fusion_settings(config['settings'])
            
            if app_state['gesture_enabled']:
                handle_stop_gesture()
                socketio.sleep(0.5) 
                handle_start_gesture()
            
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'No settings found in request'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/actions', methods=['GET'])
def get_actions():
    action_list = list(action_executor.action_map.keys())
    return jsonify(action_list)

@app.route('/api/gestures', methods=['POST'])
def update_gestures():
    global config
    try:
        new_gestures = request.json
        with config_lock:
            for gesture_name, action_name in new_gestures.items():
                if gesture_name in config['gestures']:
                    config['gestures'][gesture_name]['action'] = action_name if action_name != "null" else None
                else:
                    config['gestures'][gesture_name] = {"name": gesture_name, "action": action_name if action_name != "null" else None}
            
            if save_config(config):
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'Failed to save config'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/voice', methods=['POST'])
def update_voice_commands():
    global config
    try:
        new_commands = request.json
        with config_lock:
            for command_key, action_name in new_commands.items():
                if command_key in config['voice_commands']:
                    config['voice_commands'][command_key]['action'] = action_name if action_name != "null" else None
            
            if save_config(config):
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'Failed to save config'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --- MODIFIED: Routes for Learning Gestures ---
@app.route('/api/learn_gesture', methods=['POST'])
def learn_gesture_route():
    global learning_mode, new_gesture_name, learning_status, config, learning_samples
    
    data = request.json
    gesture_name = data.get('name')
    
    if not gesture_name:
        return jsonify({"status": "error", "message": "Gesture name is required."}), 400
    
    with config_lock:
        if gesture_name in config['gestures'] or gesture_name in config['custom_gesture_data']:
            return jsonify({"status": "error", "message": "This name is already used. Please choose another."}), 400

    learning_mode = True
    new_gesture_name = gesture_name
    learning_samples = [] # Reset sample list
    learning_status = {"status": "learning", "message": f"Learning '{gesture_name}'. Go to Dashboard and hold pose..."}
    
    print(f"Starting to learn gesture: {gesture_name}")
    return jsonify(learning_status)

@app.route('/api/get_learning_status', methods=['GET'])
def get_learning_status():
    global learning_status
    return jsonify(learning_status)

# --- NEW: Route for Deleting Gestures ---
@app.route('/api/gesture/delete', methods=['POST'])
def delete_gesture():
    global config
    data = request.json
    gesture_name = data.get('name')
    
    if not gesture_name:
        return jsonify({'success': False, 'error': 'No gesture name provided.'}), 400
    
    with config_lock:
        config = load_config() # Load fresh config
        
        # Remove the mapping; built-in gestures remain available to the model
        # but will no longer trigger an action.
        deleted_from_gestures = config['gestures'].pop(gesture_name, None)
        deleted_from_data = config['custom_gesture_data'].pop(gesture_name, None)
        
        if deleted_from_gestures is None and deleted_from_data is None:
            return jsonify({'success': False, 'error': 'Gesture not found.'}), 404

        if save_config(config):
            print(f"Deleted gesture mapping: {gesture_name}")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save config after deletion.'}), 500
# --- END NEW ---


# --- Socket.IO Events (handle_start_gesture is modified) ---
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {
        'gesture_enabled': app_state['gesture_enabled'],
        'voice_enabled': app_state['voice_enabled']
    })

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('start_gesture')
def handle_start_gesture():
    global gesture_recognizer, app_state
    try:
        if not app_state['gesture_enabled']:
            with config_lock:
                current_config = load_config() # Load fresh config for recognizer
                camera_index = current_config['settings']['camera_index']
                width = current_config['settings']['camera_width']
                height = current_config['settings']['camera_height']
            
            gesture_recognizer = GestureRecognizer(
                camera_index=camera_index,
                width=width,
                height=height,
                config=current_config,
                on_threshold_change=lambda name, old, new, mean, std: log_event({
                    'event_type': 'threshold_adaptation',
                    'gesture': name,
                    'old_threshold': float(old),
                    'new_threshold': float(new),
                    'mean': float(mean),
                    'std': float(std)
                })
            )
            app_state['gesture_enabled'] = True
            app_state['camera_active'] = True
            socketio.start_background_task(target=gesture_loop)
            emit('gesture_status', {'message': 'Gesture recognition started'})
    except Exception as e:
        print(f"Error starting gesture recognition: {e}")
        emit('error', {'message': f'Failed to start gesture recognition: {str(e)}'})

@socketio.on('stop_gesture')
def handle_stop_gesture():
    global gesture_recognizer, app_state, learning_mode, learning_samples
    app_state['gesture_enabled'] = False
    app_state['cursor_enabled'] = False
    learning_mode = False # Stop learning
    learning_samples = [] # Clear samples
    if gesture_recognizer:
        gesture_recognizer.stop()
        gesture_recognizer = None
    emit('gesture_status', {'message': 'Gesture recognition stopped'})

@socketio.on('start_voice')
def handle_start_voice():
    global voice_recognizer, app_state
    try:
        if not app_state['voice_enabled']:
            with config_lock:
                current_config = load_config()
                model_size = current_config.get('settings', {}).get('whisper_model', 'base.en')
                sample_rate = current_config.get('settings', {}).get('voice_sample_rate', 16000)
            
            voice_recognizer = VoiceRecognizer(
                model_size=model_size, sample_rate=sample_rate, config=current_config
            )
            app_state['voice_enabled'] = True
            socketio.start_background_task(target=voice_loop)
            emit('voice_status', {'message': f'Voice recognition started (Whisper {model_size})'})
    except Exception as e:
        print(f"Error starting voice recognition: {e}")
        emit('error', {'message': f'Failed to start voice recognition: {str(e)}'})

@socketio.on('stop_voice')
def handle_stop_voice():
    # (Unchanged)
    global voice_recognizer, app_state
    app_state['voice_enabled'] = False
    if voice_recognizer:
        voice_recognizer.stop()
        voice_recognizer = None
    emit('voice_status', {'message': 'Voice recognition stopped'})


# --- HEAVILY MODIFIED: Background Loops ---

def gesture_loop():
    """
    Main loop for gesture recognition.
    MODIFIED to support sample-based learning, smooth continuous input, and glitch filtering.
    """
    global gesture_recognizer, app_state, config
    global learning_mode, new_gesture_name, learning_status, learning_samples
    
    last_gesture_time = 0
    last_gesture_name = None
    pending_gesture = None
    pending_count = 0
    launch_gesture_latched = set()
    MIN_CONFIDENCE = 0.65
    empty_frame_count = 0
    
    with config_lock:
        cooldown = config['settings']['gesture_cooldown']
    prev_x, prev_y = 0, 0
    smoothing = 0.7 

    def execute_action_async(action, gesture_name, confidence, elapsed, decision=None):
        if not action_execution_lock.acquire(blocking=False):
            print(f"Skipping action '{action}' while a previous action is still running.")
            return

        def run_action():
            try:
                success = (
                    decision is None or decision['execute']
                ) and action_executor.execute(action)
                if success:
                    app_state['statistics']['actions_executed'] += 1
                socketio.emit('gesture_recognized', {
                    'gesture': gesture_name, 'confidence': confidence, 'action': action
                })
                log_event({
                    'event_type': 'recognition',
                    'modality': 'gesture',
                    'label': gesture_name,
                    'action': action,
                    'success': success,
                    'latency_ms': round(elapsed * 1000, 2) if elapsed else 15.0,
                    'confidence': confidence
                })
                if decision is not None:
                    log_fusion_decision(
                        'gesture', action, confidence, gesture_name, decision
                    )
            finally:
                action_execution_lock.release()

        threading.Thread(target=run_action, daemon=True).start()

    while app_state['gesture_enabled']:
        try:
            if gesture_recognizer is None: break
            
            frame, gesture_result, landmarks_result = gesture_recognizer.process_frame()
            
            if frame is None:
                empty_frame_count += 1
                if empty_frame_count >= 30:
                    app_state['gesture_enabled'] = False
                    app_state['camera_active'] = False
                    socketio.emit('gesture_status', {
                        'message': 'Gesture recognition stopped: camera unavailable'
                    })
                    break
                socketio.sleep(0.1)
                continue

            empty_frame_count = 0
            
            # --- LEARNING MODE LOGIC ---
            if learning_mode:
                status_msg = ""
                if landmarks_result:
                    # 1. Check for conflict with BUILT-IN gestures
                    if gesture_result and gesture_result['gesture'] != 'None':
                        status_msg = f"Conflict: Too similar to '{gesture_result['gesture']}'. Try a different pose."
                        learning_status = {"status": "error", "message": status_msg}
                        learning_samples = [] # Reset samples on conflict
                        cv2.putText(frame, status_msg, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    
                    # 2. No conflict, collect sample
                    else:
                        normalized_landmarks = gesture_recognizer.normalize_landmarks(landmarks_result[0])
                        learning_samples.append(normalized_landmarks)
                        
                        sample_count = len(learning_samples)
                        status_msg = f"Hold still... ({sample_count}/{TARGET_SAMPLES})"
                        learning_status["message"] = status_msg # Update polling status
                        cv2.putText(frame, status_msg, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                        # 3. Check if we are done collecting
                        if sample_count >= TARGET_SAMPLES:
                            print(f"Collected {sample_count} samples. Averaging and saving...")
                            result = gesture_recognizer.save_averaged_template(learning_samples, new_gesture_name)
                            
                            if result["status"] == "success":
                                with config_lock:
                                    config.setdefault('custom_gesture_data', {})[
                                        new_gesture_name
                                    ] = gesture_recognizer.custom_gestures[new_gesture_name]
                                    config['gestures'][new_gesture_name] = {"name": new_gesture_name, "action": None}
                                    save_config(config)
                                learning_status = {"status": "success", "message": result["message"]}
                                print(f"Successfully learned: {new_gesture_name}")
                            
                            else:
                                # Failed (e.g., too similar to custom gesture)
                                learning_status = {"status": "error", "message": result["message"]}
                                print(f"Failed to learn: {result['message']}")

                            # Reset learning mode
                            learning_mode = False
                            new_gesture_name = None
                            learning_samples = []
                
                else:
                    # No hand detected
                    status_msg = learning_status["message"]
                    cv2.putText(frame, status_msg, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (50, 150, 255), 2)

            # --- NORMAL OPERATION LOGIC (NOW IN 'ELSE') ---
            else:
                if app_state['cursor_enabled'] and landmarks_result:
                    try:
                        index_finger_tip = landmarks_result[0][8] 
                        x = int(index_finger_tip.x * SCREEN_WIDTH)
                        y = int(index_finger_tip.y * SCREEN_HEIGHT)
                        smooth_x = int(prev_x + (x - prev_x) * (1 - smoothing))
                        smooth_y = int(prev_y + (y - prev_y) * (1 - smoothing))
                        pyautogui.moveTo(smooth_x, smooth_y)
                        prev_x, prev_y = smooth_x, smooth_y
                    except Exception as e:
                        pass 
                
                if gesture_result and gesture_result['gesture']:
                    current_time = time.time()
                    gesture_name = gesture_result['gesture']
                    confidence = gesture_result.get('confidence', 0.0)
                    
                    # Require minimum confidence threshold to filter out low-confidence noise
                    if gesture_name != 'None' and confidence >= MIN_CONFIDENCE:
                        if gesture_name != last_gesture_name:
                            launch_gesture_latched.clear()

                        # Debounce / stability filter to prevent single-frame glitches
                        if gesture_name != last_gesture_name:
                            if pending_gesture == gesture_name:
                                pending_count += 1
                            else:
                                pending_gesture = gesture_name
                                pending_count = 1
                            
                            # Accept new gesture only after 2 stable consecutive frames or high confidence
                            if pending_count >= 2 or confidence >= 0.85:
                                confirmed_gesture = gesture_name
                                pending_gesture = None
                                pending_count = 0
                            else:
                                confirmed_gesture = None
                        else:
                            confirmed_gesture = gesture_name
                            pending_gesture = None
                            pending_count = 0
                        
                        if confirmed_gesture:
                            is_new_gesture = (confirmed_gesture != last_gesture_name)
                            time_elapsed = current_time - last_gesture_time
                            
                            action_cooldown = cooldown
                            if action := get_gesture_action(confirmed_gesture):
                                if action in REPEATABLE_NAVIGATION_ACTIONS:
                                    action_cooldown = NAVIGATION_REPEAT_INTERVAL

                            if is_new_gesture or (time_elapsed >= action_cooldown):
                                action = get_gesture_action(confirmed_gesture)
                                
                                if action == 'toggle_cursor':
                                    app_state['cursor_enabled'] = not app_state['cursor_enabled']
                                    cursor_status = "ON" if app_state['cursor_enabled'] else "OFF"
                                    print(f"Cursor Mode Toggled: {cursor_status}")
                                    socketio.emit('gesture_recognized', {
                                        'gesture': confirmed_gesture, 'confidence': confidence, 'action': f'Cursor Mode {cursor_status}'
                                    })
                                    app_state['statistics']['gestures_recognized'] += 1
                                    log_event({
                                        'event_type': 'recognition',
                                        'modality': 'gesture',
                                        'label': confirmed_gesture,
                                        'action': f'Cursor Mode {cursor_status}',
                                        'success': True,
                                        'latency_ms': round(time_elapsed * 1000, 2) if time_elapsed else 15.0,
                                        'confidence': confidence
                                    })
                                    last_gesture_time = current_time
                                    last_gesture_name = confirmed_gesture
                                
                                elif action:
                                    should_execute = not (
                                        action in APP_LAUNCH_ACTIONS
                                        and confirmed_gesture in launch_gesture_latched
                                    )

                                    if should_execute and action in APP_LAUNCH_ACTIONS:
                                        launch_gesture_latched.add(confirmed_gesture)

                                    if should_execute:
                                        decision = None
                                        if app_state['gesture_enabled'] and app_state['voice_enabled']:
                                            decision = fusion.propose(
                                                'gesture', action, confidence,
                                                confirmed_gesture, socketio.sleep
                                            )
                                        execute_action_async(
                                            action, confirmed_gesture, confidence,
                                            time_elapsed, decision
                                        )
                                    app_state['statistics']['gestures_recognized'] += 1
                                    last_gesture_time = current_time
                                    last_gesture_name = confirmed_gesture
                    else:
                        # Reset pending tracker if gesture lost or low confidence
                        pending_gesture = None
                        pending_count = 0
                        launch_gesture_latched.clear()

            # --- ENDIF learning_mode ---
            
            _, buffer = cv2.imencode('.jpg', frame)
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            socketio.emit('video_frame', {'frame': jpg_as_text})
            
            socketio.sleep(0.01)
            
        except Exception as e:
            print(f"Error in gesture loop: {e}", flush=True)
            import traceback
            traceback.print_exc()
            app_state['gesture_enabled'] = False 
            app_state['camera_active'] = False
            socketio.emit('gesture_status', {
                'message': 'Gesture recognition stopped because of an internal error'
            })

    print("Gesture loop stopped.")


def voice_loop():
    # (Unchanged)
    global voice_recognizer, app_state
    
    with config_lock:
        cooldown = load_config()['settings']['voice_cooldown']
        
    last_command_time = 0
    
    while app_state['voice_enabled']:
        try:
            if voice_recognizer is None: break
            result = voice_recognizer.recognize()
            
            if result and result.get('text') and result.get('final', True):
                current_time = time.time()
                
                if current_time - last_command_time >= cooldown:
                    command_text = result['text']
                    app_state['statistics']['commands_recognized'] += 1
                    action = get_voice_action_robust(command_text)
                    success = False
                    decision = None
                    
                    if action:
                        if app_state['gesture_enabled'] and app_state['voice_enabled']:
                            decision = fusion.propose(
                                'voice', action, result.get('confidence', 1.0),
                                command_text, socketio.sleep
                            )
                        success = (
                            decision is None or decision['execute']
                        ) and action_executor.execute(action)
                        if success:
                            app_state['statistics']['actions_executed'] += 1
                    
                    socketio.emit('voice_recognized', {
                        'text': command_text,
                        'confidence': result.get('confidence', 1.0),
                        'action': action or 'None'
                    })
                    log_event({
                        'event_type': 'recognition',
                        'modality': 'voice',
                        'label': command_text,
                        'action': action or 'None',
                        'success': success,
                        'latency_ms': result.get('latency_ms', 25.0),
                        'confidence': result.get('confidence', 1.0)
                    })
                    if decision is not None:
                        log_fusion_decision(
                            'voice', action, result.get('confidence', 1.0),
                            command_text, decision
                        )
                    last_command_time = current_time
            
            socketio.sleep(0.05)
        except Exception as e:
            print(f"Error in voice loop: {e}")

    print("Voice loop stopped.")


# --- Action Mapping ---
import difflib
import re

VOICE_SYNONYMS = {
    'right_click': ['right click', 'rightclick', 'write click', 'context menu'],
    'double_click': ['double click', 'doubleclick'],
    'left_click': ['click', 'left click', 'single click', 'select'],
    'open_browser': ['open browser', 'browser', 'launch browser', 'chrome', 'open chrome'],
    'close_browser': ['close browser', 'exit browser', 'close chrome'],
    'new_tab': ['new tab', 'open tab', 'open new tab', 'create tab'],
    'close_tab': ['close tab', 'exit tab'],
    'next_tab': ['next tab', 'switch tab', 'forward tab'],
    'previous_tab': ['previous tab', 'prev tab', 'back tab'],
    'scroll_up': ['scroll up', 'scrolling up', 'page up'],
    'scroll_down': ['scroll down', 'scrolling down', 'page down'],
    'zoom_in': ['zoom in', 'zooming in', 'enlarge', 'magnify'],
    'zoom_out': ['zoom out', 'zooming out', 'shrink'],
    'open_notepad': ['open notepad', 'notepad', 'notes', 'text editor'],
    'open_file_explorer': ['open files', 'open file explorer', 'file explorer', 'explorer', 'files'],
    'open_settings': ['open settings', 'settings', 'control panel'],
    'open_mail': ['open mail', 'mail', 'email'],
    'minimize_window': ['minimize', 'minimize window'],
    'maximize_window': ['maximize', 'maximize window', 'fullscreen'],
    'lock_screen': ['lock screen', 'lock'],
    'volume_up': ['volume up', 'louder', 'increase volume'],
    'volume_down': ['volume down', 'quieter', 'decrease volume'],
    'volume_mute': ['mute', 'unmute', 'silence'],
    'brightness_up': [
        'brightness up', 'increase brightness', 'raise brightness',
        'higher brightness', 'more brightness', 'make brighter',
        'make it brighter', 'brighten screen', 'screen brighter', 'brighter'
    ],
    'brightness_down': [
        'brightness down', 'decrease brightness', 'lower brightness',
        'reduce brightness', 'less brightness', 'dim screen',
        'dimmer', 'dim', 'make dimmer', 'make it dimmer', 'screen darker', 'darker'
    ],
    'copy': ['copy'],
    'paste': ['paste'],
    'cut': ['cut'],
    'undo': ['undo'],
    'redo': ['redo'],
    'save': ['save'],
    'screenshot': ['screenshot', 'take screenshot'],
    'press_enter': ['enter', 'press enter'],
    'press_escape': ['escape', 'cancel'],
    'press_space': ['space'],
    'read_screen': ['read screen'],
    'tell_date_time': [
        'what date and time is it',
        'what date time is it',
        'what date or time is it',
        'what time and date is it',
        'what is the date and time',
        'what is the time and date',
        'whats the date and time',
        'whats the time and date',
        'tell date and time',
        'tell time and date',
        'date and time',
        'time and date',
        'date time',
        'time date',
        'current date and time',
        'current time and date'
    ],
    'tell_time': [
        'what time is it',
        'what is the time',
        'whats the time',
        'what time is it now',
        'what time is it please',
        'tell time',
        'tell me the time',
        'current time',
        'time now',
        'the time',
        'time'
    ],
    'tell_date': [
        'what date is it',
        'what is the date',
        'whats the date',
        'what is todays date',
        'whats todays date',
        'what day is it',
        'what day is today',
        'what date is today',
        'tell date',
        'tell me the date',
        'current date',
        'today date',
        'todays date',
        'the date',
        'date'
    ],
    'shutdown': ['shutdown system', 'shut down system', 'shutdown', 'shut down', 'turn off computer'],
    'restart': ['restart system', 'restart', 'reboot'],
    'refresh': ['refresh', 'reload']
}

def normalize_voice_text(text):
    text = (text or '').lower().strip()
    text = re.sub(r'[-_/\\]', ' ', text)
    text = re.sub(r'[^\w\s]', '', text)
    return ' '.join(text.split())

def get_gesture_action(gesture_name):
    with config_lock:
        if gesture_name in config.get('gestures', {}):
            return config['gestures'][gesture_name].get('action')
    return None

def get_voice_action_robust(spoken_text):
    clean = normalize_voice_text(spoken_text)
    if not clean:
        return None

    all_phrases = []
    for action, phrases in VOICE_SYNONYMS.items():
        for p in phrases:
            all_phrases.append((p, action, len(p.split())))
    all_phrases.sort(key=lambda x: (x[2], len(x[0])), reverse=True)

    # 1. Exact full match
    for phrase, action, _ in all_phrases:
        if clean == phrase:
            return action

    # 2. Multi-word phrase boundary match (multi-word commands take precedence)
    for phrase, action, word_count in all_phrases:
        if word_count > 1:
            pattern = r'\b' + re.escape(phrase) + r'\b'
            if re.search(pattern, clean):
                return action

    # 3. User configured voice commands check
    with config_lock:
        configured_cmds = list(config.get('voice_commands', {}).values())
    
    cfg_list = []
    for c_data in configured_cmds:
        c = normalize_voice_text(c_data.get('command', ''))
        act = c_data.get('action')
        if c and act:
            cfg_list.append((c, act, len(c.split())))
    cfg_list.sort(key=lambda x: (x[2], len(x[0])), reverse=True)

    for c, act, word_count in cfg_list:
        if word_count > 1:
            if clean == c or re.search(r'\b' + re.escape(c) + r'\b', clean):
                return act

    # 4. Fuzzy match for multi-word phrases (similarity >= 0.80)
    best_fuzzy_action = None
    best_ratio = 0.80
    for phrase, action, word_count in all_phrases:
        if word_count > 1:
            ratio = difflib.SequenceMatcher(None, clean, phrase).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_fuzzy_action = action
    if best_fuzzy_action:
        return best_fuzzy_action

    # 5. Single-word phrase boundary match
    for phrase, action, word_count in all_phrases:
        if word_count == 1:
            pattern = r'\b' + re.escape(phrase) + r'\b'
            if re.search(pattern, clean):
                return action

    # 6. Single-word configured commands match
    for c, act, word_count in cfg_list:
        if word_count == 1:
            if clean == c or re.search(r'\b' + re.escape(c) + r'\b', clean):
                return act

    # 7. Fuzzy match for single words (similarity >= 0.84)
    for phrase, action, word_count in all_phrases:
        if word_count == 1:
            ratio = difflib.SequenceMatcher(None, clean, phrase).ratio()
            if ratio >= 0.84:
                return action

    return None

if __name__ == '__main__':
    print("="*60)
    print("Gesture and Voice HCI System - Starting...")
    print("="*60)
    print(f"Server will run on: http://127.0.0.1:5000")
    print("Open this URL in your browser.")
    print("Press Ctrl+C to stop")
    print("="*60)
    
    socketio.run(app, host='127.0.0.1', port=5000, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)