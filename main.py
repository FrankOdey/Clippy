import sys
import threading
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PyQt6.QtCore import QThread, pyqtSignal, QTimer

from buddy_window import BuddyWindow
from settings_dialog import SettingsDialog
from hotkey_listener import HotkeyListener
from screen_capture import ScreenCapturer
from llm_client import LLMClient
from memory_manager import MemoryManager
from stt_engine import STTEngine
from tts_engine import TTSEngine
from config_manager import config


class LLMWorker(QThread):
    """Background thread for streaming LLM responses."""
    chunk_received = pyqtSignal(str)
    sentence_completed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished_run = pyqtSignal()

    def __init__(self, llm_client, user_query, image_b64, context, cancel_event):
        super().__init__()
        self.llm_client = llm_client
        self.user_query = user_query
        self.image_b64 = image_b64
        self.context = context
        self.cancel_event = cancel_event

    def run(self):
        self.llm_client.generate_streaming(
            self.user_query,
            self.image_b64,
            self.context,
            lambda t: self.chunk_received.emit(t),
            lambda s: self.sentence_completed.emit(s),
            lambda e: self.error_occurred.emit(e),
            cancel_event=self.cancel_event,
        )
        self.finished_run.emit()


def _create_tray_icon_pixmap():
    """Create a simple blue triangle icon for the system tray."""
    pm = QPixmap(32, 32)
    pm.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(66, 133, 244))
    painter.setPen(QColor(66, 133, 244))
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPolygonF
    triangle = QPolygonF([QPointF(6, 4), QPointF(6, 28), QPointF(28, 16)])
    painter.drawPolygon(triangle)
    painter.end()
    return pm


class ClippyApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # Core components
        self.window = BuddyWindow()
        self.hotkey_listener = HotkeyListener()
        self.capturer = ScreenCapturer()
        self.llm_client = LLMClient()
        self.memory = MemoryManager()
        self.tts_engine = TTSEngine()

        # Cancellation
        self._cancel_event = threading.Event()
        self.stt_engine = None
        self.worker = None
        self.full_response = ""

        # Connect hotkeys
        self.hotkey_listener.hotkey_pressed.connect(self.on_trigger)
        self.hotkey_listener.cancel_pressed.connect(self.on_cancel)
        self.hotkey_listener.start()

        # Pre-load Whisper in background
        threading.Thread(target=STTEngine.preload_model, daemon=True).start()

        # System tray
        self._setup_tray()
        
        # Check LLM error state on startup
        if self.llm_client.error_state:
            self.tray.showMessage("Clippy Error", self.llm_client.error_state, QSystemTrayIcon.MessageIcon.Error, 5000)
        elif self.llm_client.provider == "ollama":
            self.tray.showMessage("Clippy Offline Mode", f"Found Ollama! Using local {self.llm_client.model_name}", QSystemTrayIcon.MessageIcon.Information, 5000)
        else:
            self.tray.showMessage("Clippy Online", f"Connected securely to {self.llm_client.provider}", QSystemTrayIcon.MessageIcon.Information, 3000)

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(QIcon(_create_tray_icon_pixmap()), self.app)
        menu = QMenu()

        self.provider_label = menu.addAction(f"Provider: {self.llm_client.provider}")
        self.provider_label.setEnabled(False)

        self.model_label = menu.addAction(f"Model: {self.llm_client.model_name}")
        self.model_label.setEnabled(False)

        menu.addSeparator()

        settings_action = QAction("Settings...", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)
        
        clear_action = QAction("Clear History", menu)
        clear_action.triggered.connect(lambda: self.memory.clear())
        menu.addAction(clear_action)

        menu.addSeparator()

        quit_action = QAction("Quit Clippy", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.setToolTip(f"Clippy — {self.llm_client.provider}/{self.llm_client.model_name}")
        self.tray.show()

    def _open_settings(self):
        dialog = SettingsDialog(self.window)
        dialog.color_preview.connect(self.window.set_color)
        dialog.settings_saved.connect(self._apply_settings)
        dialog.exec()

    def _apply_settings(self):
        # Full subsystem reset
        self.llm_client = LLMClient()
        self.provider_label.setText(f"Provider: {self.llm_client.provider}")
        self.model_label.setText(f"Model: {self.llm_client.model_name}")
        self.tray.setToolTip(f"Clippy — {self.llm_client.provider}/{self.llm_client.model_name}")
        
        # Hotkey listener reset
        self.hotkey_listener.stop()
        self.hotkey_listener.wait()
        
        self.hotkey_listener = HotkeyListener()
        self.hotkey_listener.hotkey_pressed.connect(self.on_trigger)
        self.hotkey_listener.cancel_pressed.connect(self.on_cancel)
        self.hotkey_listener.start()
        
        if self.llm_client.error_state:
            self.tray.showMessage("Clippy Error", self.llm_client.error_state, QSystemTrayIcon.MessageIcon.Error, 5000)

    def _quit(self):
        self.hotkey_listener.stop()
        self.tts_engine.stop()
        self.on_cancel()
        self.app.quit()

    # ------------------------------------------------------------------
    # Activation flow
    # ------------------------------------------------------------------
    def on_trigger(self):
        # Don't interrupt an active session
        if self.worker and self.worker.isRunning():
            return
        if self.stt_engine and self.stt_engine.isRunning():
            return

        self._cancel_event.clear()
        self.window.set_state_listening()

        # Create fresh STT engine each cycle (QThread can't be re-started)
        self.stt_engine = STTEngine(cancel_event=self._cancel_event)
        self.stt_engine.finished_listening.connect(self.on_speech_recognized)
        self.stt_engine.error_occurred.connect(self.on_error)
        self.stt_engine.start()

    def on_speech_recognized(self, text):
        if not text:
            self.window.set_state_idle()
            return

        self.memory.add_user_turn(text)
        image_b64 = self.capturer.capture_base64()
        self.window.set_state_thinking()

        context = self.memory.get_context()

        self.worker = LLMWorker(self.llm_client, text, image_b64, context, self._cancel_event)
        self.worker.chunk_received.connect(self.window.append_response_text)
        self.worker.sentence_completed.connect(self.tts_engine.speak)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.finished_run.connect(self.on_finished)

        self.window.set_state_responding()
        self.window.set_text("")
        self.full_response = ""
        self.worker.chunk_received.connect(self._accumulate)
        self.worker.start()

    def _accumulate(self, t):
        self.full_response += t

    def on_error(self, err):
        self.window.set_text(f"Error: {err}")
        QTimer.singleShot(4000, self.window.set_state_idle)

    def on_finished(self):
        self.memory.add_assistant_turn(self.full_response)
        QTimer.singleShot(10000, self.window.set_state_idle)

    # ------------------------------------------------------------------
    # Cancellation (cooperative, no terminate())
    # ------------------------------------------------------------------
    def on_cancel(self):
        self._cancel_event.set()
        self.tts_engine.stop()
        self.window.set_state_idle()

        # Wait for threads to finish cleanly (with timeout)
        if self.stt_engine and self.stt_engine.isRunning():
            self.stt_engine.wait(2000)
        if self.worker and self.worker.isRunning():
            self.worker.wait(2000)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(self):
        self.window.set_state_idle()
        sys.exit(self.app.exec())


if __name__ == "__main__":
    app = ClippyApp()
    app.run()
