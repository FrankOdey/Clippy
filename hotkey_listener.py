import keyboard
import time
from PyQt6.QtCore import QThread, pyqtSignal
from config_manager import config

class HotkeyListener(QThread):
    hotkey_pressed = pyqtSignal()
    cancel_pressed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.running = True
        self.trigger_hotkey = config.get("hotkey", "ctrl+space")

    def run(self):
        try:
            keyboard.add_hotkey(self.trigger_hotkey, self._emit_hotkey, suppress=True)
            keyboard.add_hotkey('esc', self._emit_cancel, suppress=False)
            while self.running:
                time.sleep(0.1)
        except ImportError:
            print("Keyboard library needs to run as Administrator on Windows to hook keys.")
        except Exception as e:
            print(f"Hotkey exception: {e}")

    def _emit_hotkey(self):
        self.hotkey_pressed.emit()

    def _emit_cancel(self):
        self.cancel_pressed.emit()

    def stop(self):
        self.running = False
        try:
            keyboard.unhook_all()
        except:
            pass
