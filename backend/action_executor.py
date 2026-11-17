"""
Action Executor Module using PyAutoGUI
Executes system-level actions: mouse, keyboard, voice, and accessibility features
for Multimodal Gesture and Voice HCI System
"""

import pyautogui
import time
import platform
import subprocess
import webbrowser
import os
import datetime
import threading
import queue

# Try to import screen_brightness_control if available
try:
    import screen_brightness_control as sbc
except ImportError:
    sbc = None


class _TTSManager:
    """Thread-safe Text-to-Speech manager using a dedicated worker thread."""
    def __init__(self, os_type):
        self.os_type = os_type
        self.queue = queue.Queue()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def speak(self, text):
        if text:
            self.queue.put(text)

    def _run(self):
        # Dedicated thread loop for speech
        speaker = None
        engine = None

        if self.os_type == 'Windows':
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
            except Exception as e:
                print(f"[TTS] Native Windows SAPI init failed ({e}), falling back to pyttsx3.")

        if speaker is None:
            try:
                import pyttsx3
                engine = pyttsx3.init()
            except Exception as e:
                print(f"[TTS] pyttsx3 init failed: {e}")

        while True:
            text = self.queue.get()
            if text is None:
                break
            try:
                if speaker is not None:
                    # Windows native SAPI
                    speaker.Speak(text)
                elif engine is not None:
                    # pyttsx3 single-thread execution
                    engine.say(text)
                    engine.runAndWait()
                elif self.os_type == 'Darwin':
                    subprocess.run(['say', text], check=False)
                elif self.os_type == 'Linux':
                    subprocess.run(['spd-say', text], check=False)
                elif self.os_type == 'Windows':
                    # Fallback via PowerShell SAPI
                    escaped = text.replace('"', '`"')
                    cmd = f'powershell -NoProfile -Command "(New-Object -ComObject SAPI.SpVoice).Speak(\\"{escaped}\\")"'
                    subprocess.run(cmd, shell=True, check=False)
                else:
                    print(f"[TTS Audio]: {text}")
            except Exception as e:
                print(f"[TTS] Speak error: {e}")
            finally:
                self.queue.task_done()


class ActionExecutor:
    def __init__(self):
        """Initialize action executor"""
        pyautogui.PAUSE = 0.01
        pyautogui.FAILSAFE = True
        self.os_type = platform.system()

        # Thread-safe Text-to-Speech manager
        self._tts = _TTSManager(self.os_type)

        # --- Action map (gesture + voice) ---
        self.action_map = {
            # Mouse Actions
            'click': self.left_click,
            'left_click': self.left_click,
            'right_click': self.right_click,
            'double_click': self.double_click,
            'middle_click': self.middle_click,
            'scroll_up': self.scroll_up,
            'scroll_down': self.scroll_down,
            'move_cursor': self.move_cursor,

            # Keyboard Actions
            'press_enter': lambda: self.press_key('enter'),
            'press_space': lambda: self.press_key('space'),
            'press_tab': lambda: self.press_key('tab'),
            'press_escape': lambda: self.press_key('escape'),
            'press_delete': lambda: self.press_key('delete'),
            'press_backspace': lambda: self.press_key('backspace'),

            'copy': lambda: self.hotkey('ctrl', 'c'),
            'paste': lambda: self.hotkey('ctrl', 'v'),
            'cut': lambda: self.hotkey('ctrl', 'x'),
            'undo': lambda: self.hotkey('ctrl', 'z'),
            'redo': lambda: self.hotkey('ctrl', 'y'),
            'select_all': lambda: self.hotkey('ctrl', 'a'),
            'save': lambda: self.hotkey('ctrl', 's'),

            # Window Management
            'minimize_window': self.minimize_window,
            'maximize_window': self.maximize_window,
            'close_window': self.close_window,
            'switch_window': self.switch_window,
            'new_window': lambda: self.hotkey('ctrl', 'n'),
            'refresh': lambda: self.press_key('f5'),

            # Tabs & Browser Navigation
            'new_tab': lambda: self.hotkey('ctrl', 't'),
            'close_tab': lambda: self.hotkey('ctrl', 'w'),
            'next_tab': lambda: self.hotkey('ctrl', 'tab'),
            'previous_tab': lambda: self.hotkey('ctrl', 'shift', 'tab'),

            # Applications
            'open_browser': self.open_browser,
            'close_browser': self.close_browser,
            'open_file_explorer': self.open_file_explorer,
            'open_notepad': self.open_notepad,
            'open_settings': self.open_settings,
            'open_mail': self.open_mail,

            # System Actions
            'screenshot': self.take_screenshot,
            'lock_screen': self.lock_screen,
            'shutdown': self.shutdown,
            'restart': self.restart,

            # Volume & Brightness
            'volume_up': self.volume_up,
            'volume_down': self.volume_down,
            'volume_mute': self.volume_mute,
            'brightness_up': self.brightness_up,
            'brightness_down': self.brightness_down,

            # Zoom & Accessibility
            'zoom_in': self.zoom_in,
            'zoom_out': self.zoom_out,
            'read_screen': self.read_screen,
            'tell_time': self.tell_time,
            'tell_date': self.tell_date,
            'tell_date_time': self.tell_date_time,
            'tell_datetime': self.tell_date_time,

            # Special Actions
            'toggle_cursor': self.toggle_cursor
        }

    # ============================================================
    # ----------------------- Core Executor ----------------------
    # ============================================================
    def execute(self, action_name, params=None):
        """Execute an action by name"""
        if not action_name:
            return False

        action_name = action_name.lower().replace(' ', '_')
        action_func = self.action_map.get(action_name)

        if action_func:
            try:
                # Toggle cursor handled elsewhere
                if action_name == 'toggle_cursor':
                    return True

                # Handle dynamic params (like move_cursor)
                if params:
                    action_func(**params)
                else:
                    action_func()

                print(f"✅ Executed action: {action_name}")
                return True
            except Exception as e:
                print(f"❌ Error executing action '{action_name}': {e}")
                return False
        else:
            print(f"⚠️ Unknown action: {action_name}")
            return False

    # ============================================================
    # ------------------------- Mouse ----------------------------
    # ============================================================
    def left_click(self): pyautogui.click()
    def right_click(self): pyautogui.rightClick()
    def double_click(self): pyautogui.doubleClick()
    def middle_click(self): pyautogui.middleClick()
    def scroll_up(self, amount=3): pyautogui.scroll(amount * 100)
    def scroll_down(self, amount=3): pyautogui.scroll(-amount * 100)

    def move_cursor(self, x=None, y=None):
        """Move cursor — controlled externally via gesture coordinates"""
        if x is not None and y is not None:
            pyautogui.moveTo(x, y)

    # ============================================================
    # ----------------------- Keyboard ---------------------------
    # ============================================================
    def press_key(self, key): pyautogui.press(key)
    def hotkey(self, *keys): pyautogui.hotkey(*keys)
    def type_text(self, text): pyautogui.write(text, interval=0.05)

    # ============================================================
    # ------------------ Window / System Mgmt --------------------
    # ============================================================
    def minimize_window(self):
        if self.os_type == 'Windows':
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        elif self.os_type == 'Darwin': self.hotkey('command', 'm')
        else: self.hotkey('super', 'h')

    def maximize_window(self):
        if self.os_type == 'Windows':
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
        elif self.os_type == 'Darwin': self.hotkey('f')
        else: self.hotkey('super', 'up')

    def close_window(self):
        if self.os_type == 'Windows': self.hotkey('alt', 'f4')
        elif self.os_type == 'Darwin': self.hotkey('command', 'w')
        else: self.hotkey('alt', 'f4')

    def switch_window(self):
        if self.os_type in ['Windows', 'Linux']: self.hotkey('alt', 'tab')
        elif self.os_type == 'Darwin': self.hotkey('command', 'tab')

    # ============================================================
    # ---------------------- Applications ------------------------
    # ============================================================
    def open_browser(self): webbrowser.open("https://google.com")

    def close_browser(self):
        """Close browser (supports Chrome/Edge)"""
        try:
            if self.os_type == 'Windows':
                os.system("taskkill /IM chrome.exe /F")
                os.system("taskkill /IM msedge.exe /F")
            elif self.os_type == 'Linux':
                os.system("pkill chrome")
            else:
                os.system("osascript -e 'quit app \"Google Chrome\"'")
        except Exception as e:
            print(f"Browser close failed: {e}")

    def open_file_explorer(self):
        if self.os_type == 'Windows': self.hotkey('win', 'e')
        elif self.os_type == 'Darwin': subprocess.Popen(['open', '/'])
        else: subprocess.Popen(['xdg-open', '/home'])

    def open_notepad(self):
        if self.os_type == 'Windows': subprocess.Popen(['notepad.exe'])
        elif self.os_type == 'Darwin': subprocess.Popen(['open', '-a', 'TextEdit'])
        else: subprocess.Popen(['gedit'])

    def open_settings(self):
        if self.os_type == 'Windows': subprocess.Popen('start ms-settings:', shell=True)
        elif self.os_type == 'Darwin': subprocess.Popen(['open', '-a', 'System Settings'])
        else: subprocess.Popen(['gnome-control-center'])

    def open_mail(self):
        """Open Gmail in browser"""
        webbrowser.open("https://mail.google.com")

    def speak(self, text):
        """Thread-safe, non-blocking text-to-speech invocation"""
        self._tts.speak(text)

    # ============================================================
    # ------------------- System-Level Actions -------------------
    # ============================================================
    def take_screenshot(self):
        filename = f"screenshot_{time.strftime('%Y%m%d-%H%M%S')}.png"
        pyautogui.screenshot(filename)
        self.speak("Screenshot taken")
        print(f"📸 Saved {filename}")

    def lock_screen(self):
        if self.os_type == 'Windows':
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        elif self.os_type == 'Darwin': self.hotkey('command', 'control', 'q')
        else: self.hotkey('super', 'l')

    def shutdown(self):
        if self.os_type == 'Windows': os.system("shutdown /s /t 1")
        elif self.os_type == 'Linux': os.system("shutdown now")
        else: os.system("osascript -e 'tell app \"System Events\" to shut down'")

    def restart(self):
        if self.os_type == 'Windows': os.system("shutdown /r /t 1")
        elif self.os_type == 'Linux': os.system("reboot")
        else: os.system("osascript -e 'tell app \"System Events\" to restart'")

    # ============================================================
    # ---------------- Volume & Brightness -----------------------
    # ============================================================
    def volume_up(self): pyautogui.press('volumeup')
    def volume_down(self): pyautogui.press('volumedown')
    def volume_mute(self): pyautogui.press('volumemute')

    def get_brightness(self):
        """Get current screen brightness as integer 0-100."""
        # 1. Try screen_brightness_control
        if sbc is not None:
            try:
                val = sbc.get_brightness()
                if isinstance(val, list) and len(val) > 0:
                    return int(val[0])
                elif isinstance(val, (int, float)):
                    return int(val)
            except Exception as e:
                print(f"[Brightness] SBC get error: {e}")

        # 2. Windows WMI fallback
        if self.os_type == 'Windows':
            try:
                cmd = 'powershell -NoProfile -Command "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness).CurrentBrightness"'
                output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
                if output.isdigit():
                    return int(output)
            except Exception as e:
                print(f"[Brightness] WMI get error: {e}")

        return 50

    def set_brightness(self, value):
        """Set screen brightness as integer 0-100."""
        value = max(0, min(100, int(round(value))))
        success = False

        # 1. Try screen_brightness_control
        if sbc is not None:
            try:
                sbc.set_brightness(value)
                success = True
            except Exception as e:
                print(f"[Brightness] SBC set error: {e}")

        # 2. Windows WMI fallback
        if not success and self.os_type == 'Windows':
            try:
                cmd = f'powershell -NoProfile -Command "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {value})"'
                subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                success = True
            except Exception as e:
                print(f"[Brightness] WMI set error: {e}")

        # 3. Linux brightnessctl / xbacklight fallback
        if not success and self.os_type == 'Linux':
            try:
                subprocess.run(['brightnessctl', 'set', f'{value}%'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                success = True
            except Exception:
                try:
                    subprocess.run(['xbacklight', '-set', str(value)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    success = True
                except Exception:
                    pass

        # 4. macOS brightness fallback
        if not success and self.os_type == 'Darwin':
            try:
                subprocess.run(['brightness', str(value / 100.0)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                success = True
            except Exception:
                pass

        return success, value

    def brightness_up(self, step=10):
        """Increase screen brightness by step percentage (default +10%)."""
        curr = self.get_brightness()
        new_val = min(100, curr + step)
        success, final_val = self.set_brightness(new_val)
        if success:
            print(f"🔆 Brightness increased to {final_val}%")
        else:
            print("⚠️ Brightness control not supported on this display.")
        return success

    def brightness_down(self, step=10):
        """Decrease screen brightness by step percentage (default -10%)."""
        curr = self.get_brightness()
        new_val = max(0, curr - step)
        success, final_val = self.set_brightness(new_val)
        if success:
            print(f"🔅 Brightness decreased to {final_val}%")
        else:
            print("⚠️ Brightness control not supported on this display.")
        return success

    # ============================================================
    # -------------------- Accessibility -------------------------
    # ============================================================
    def zoom_in(self): pyautogui.hotkey('ctrl', '+')
    def zoom_out(self): pyautogui.hotkey('ctrl', '-')

    def read_screen(self):
        """Placeholder for text-to-speech screen reading"""
        self.speak("Screen reading feature not fully implemented yet.")

    def tell_time(self):
        """Speak the current time aloud."""
        now = datetime.datetime.now()
        hour = now.strftime("%I").lstrip("0") or "12"
        minute = now.strftime("%M")
        ampm = now.strftime("%p")
        msg = f"The time is {hour}:{minute} {ampm}"
        print(f"🕒 {msg}")
        self.speak(msg)

    def tell_date(self):
        """Speak the current date aloud."""
        today = datetime.datetime.now().strftime("%A, %B %d, %Y")
        msg = f"Today is {today}"
        print(f"📅 {msg}")
        self.speak(msg)

    def tell_date_time(self):
        """Speak both the current date and time aloud."""
        now = datetime.datetime.now()
        hour = now.strftime("%I").lstrip("0") or "12"
        minute = now.strftime("%M")
        ampm = now.strftime("%p")
        today = now.strftime("%A, %B %d, %Y")
        msg = f"Today is {today}, and the time is {hour}:{minute} {ampm}"
        print(f"🗓️ {msg}")
        self.speak(msg)

    # ============================================================
    # --------------------- Special ------------------------------
    # ============================================================
    def toggle_cursor(self):
        """Handled externally in app.py"""
        pass
