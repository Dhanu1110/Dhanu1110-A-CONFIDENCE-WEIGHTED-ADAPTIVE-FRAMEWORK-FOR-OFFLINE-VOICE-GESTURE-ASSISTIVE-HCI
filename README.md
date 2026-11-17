# A Confidence-Weighted, Adaptive Multimodal Framework for Offline Voice-Gesture Assistive HCI

This project is an offline, assistive human-computer interaction system designed to help users control a computer using hand gestures and voice commands without a keyboard or mouse. It is intended for accessibility-focused use cases where users may have limited mobility or prefer hands-free interaction.

The system combines:

- gesture recognition from a webcam using MediaPipe
- speech recognition from the microphone using Whisper
- action execution via PyAutoGUI and system commands
- confidence-based arbitration when gesture and voice inputs occur together
- a browser-based control panel for configuration and training

## Project overview

The project is split into two main parts:

- `backend/` contains the Flask server, recognition logic, fusion logic, and action execution modules
- `frontend/` contains the browser UI, CSS, JavaScript, and model assets

Recognition and command execution run locally. On first startup, faster-whisper may need an internet connection to download its selected speech model; later runs can use the cached model offline.

## Key features

- Offline gesture control using webcam input
- Offline voice command recognition using Whisper
- Real-time control through a Flask + SocketIO backend
- Custom gesture training and saved gesture templates
- Adaptive custom gesture thresholds that improve over time
- Confidence-weighted fusion between gesture and voice modalities
- Action mapping for browsing, window control, media control, system access, and app launching
- Browser-based UI for managing actions and configuration

## Architecture

The application is organized as a local multimodal control system:

1. Camera input is processed by the gesture recognizer.
2. Microphone input is processed by the voice recognizer.
3. The backend coordinates both inputs and maps them to actions.
4. The action executor performs the actual system operation.
5. When gesture and voice commands happen close together, the fusion module decides which one should run.

## Technology stack

- Backend: Flask, Flask-SocketIO, Flask-CORS, Eventlet
- Gesture recognition: OpenCV, MediaPipe, NumPy
- Voice recognition: faster-whisper, SoundDevice
- System control: PyAutoGUI, pyttsx3, subprocess, os
- Frontend: HTML, CSS, JavaScript
- Model assets: MediaPipe gesture model; faster-whisper downloads and caches its speech model when needed

## Project structure

```text
mini project (final code)/
├── backend/
│   ├── app.py
│   ├── action_executor.py
│   ├── fusion.py
│   ├── gesture_recognition.py
│   ├── voice_recognition.py
│   └── (config.json and logs/ are created at runtime)
├── frontend/
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── models/
│   └── templates/
│       └── index.html
├── requirements.txt
├── requirements-lock.txt
├── .gitignore
└── README.md
```

## Setup

### Prerequisites

- Python 3.10 or newer
- A webcam and microphone connected to the machine
- Windows/macOS/Linux environment compatible with the dependencies

### Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

## Run the application

From the project root, start the backend server:

```bash
python backend/app.py
```

Then open the browser at:

```text
http://127.0.0.1:5000
```

If you prefer, you can also navigate into the backend folder and run:

```bash
cd backend
python app.py
```

## What the system can do

The project supports actions such as:

- mouse actions like click, double click, right click, scroll, and cursor movement
- keyboard actions like copy, paste, cut, undo, redo, save, and text input
- window actions like minimize, maximize, switch window, and open/close tabs
- application control like opening browser, Notepad, file explorer, settings, and mail
- system actions like volume adjustments, brightness control, locking the screen, shutdown, and reading time/date

## Gesture and voice behavior

### Gesture recognition

The system uses MediaPipe to detect hand landmarks and classify gestures. It can recognize built-in gestures from the MediaPipe model and also learn custom gestures by averaging several saved landmark samples.

Custom gestures are compared against stored templates using a normalized distance metric. The project also adapts the threshold per gesture based on recent successful matches, so a user’s consistent gesture performance can be recognized more precisely over time.

### Voice recognition

The voice module uses faster-whisper with a local microphone stream and audio segmentation. It listens for short spoken commands and normalizes them before matching them to configured actions. Commands are stored in the app configuration and can be mapped to actions from the web interface.

### Modality fusion

When both gesture and voice recognition are active at the same time, the project uses a confidence-weighted fusion mechanism. The fusion layer compares active proposals from both modalities within a short time window and chooses the higher-scoring action. This helps avoid duplicate or conflicting actions when a user gives multiple inputs at the same time.

## Configuration

The app's runtime settings are stored in `backend/config.json`. If the file does not exist, the application creates it with default settings when it starts.

This file contains:

- camera settings
- gesture and voice cooldown values
- fusion parameters
- mapping between recognized gestures/voice phrases and actions
- stored custom gesture templates

## Notes

- After the faster-whisper model has been downloaded or otherwise cached, recognition runs locally and can be used without an internet connection.
- The project includes logging under `backend/logs/` for session activity and fusion decisions.
- Runtime configuration and logs are excluded from version control because they may contain personal gesture data or local activity.
- Some dependencies may require Windows-specific packages or environment settings depending on the machine.

## Intended use

This project is best understood as an accessibility and assistive-technology prototype for hands-free computer interaction. It is especially relevant for situations where a user needs to operate a computer without relying on traditional mouse and keyboard input.

## Summary

This repository contains a complete local assistive HCI system that blends gesture and voice recognition with adaptive behavior, custom training, and action execution. It is a practical prototype for offline multimodal control in assistive computing scenarios.
