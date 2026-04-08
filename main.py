import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, pyqtSignal, QTimer

from buddy_window import BuddyWindow
from hotkey_listener import HotkeyListener
from screen_capture import ScreenCapturer
from llm_client import LLMClient
from memory_manager import MemoryManager
from stt_engine import STTEngine
from tts_engine import TTSEngine

class LLMWorker(QThread):
    chunk_received = pyqtSignal(str)
    sentence_completed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished_run = pyqtSignal()

    def __init__(self, llm_client, user_query, image_b64, context):
        super().__init__()
        self.llm_client = llm_client
        self.user_query = user_query
        self.image_b64 = image_b64
        self.context = context

    def run(self):
        def _token(t):
            self.chunk_received.emit(t)
        
        def _sentence(s):
            self.sentence_completed.emit(s)
            
        def _error(e):
            self.error_occurred.emit(e)

        self.llm_client.generate_streaming(
            self.user_query, 
            self.image_b64, 
            self.context, 
            _token, 
            _sentence, 
            _error
        )
        self.finished_run.emit()

class ClippyApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = BuddyWindow()
        self.hotkey_listener = HotkeyListener()
        self.capturer = ScreenCapturer()
        self.llm_client = LLMClient()
        self.memory = MemoryManager()
        self.tts_engine = TTSEngine()
        self.stt_engine = STTEngine()
        
        self.hotkey_listener.hotkey_pressed.connect(self.on_trigger)
        self.hotkey_listener.cancel_pressed.connect(self.on_cancel)
        self.hotkey_listener.start()
        
        self.stt_engine.finished_listening.connect(self.on_speech_recognized)
        self.stt_engine.error_occurred.connect(self.on_error)
        self.worker = None

    def on_trigger(self):
        if self.worker and self.worker.isRunning():
            return # already working
        if self.stt_engine.isRunning():
             return # already listening

        self.window.set_state_listening()
        self.stt_engine.start()
        
    def on_speech_recognized(self, text):
        if not text:
            # Silence or error
            self.window.set_state_idle()
            return
            
        user_query = text
        self.memory.add_user_turn(user_query)
        
        image_b64 = self.capturer.capture_base64()
        self.window.set_state_thinking()
        
        # Fetch prior context
        context = self.memory.get_context()
        
        self.worker = LLMWorker(self.llm_client, user_query, image_b64, context)
        self.worker.chunk_received.connect(self.window.append_response_text)
        self.worker.sentence_completed.connect(self.tts_engine.speak)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.finished_run.connect(self.on_finished)
        
        self.window.set_state_responding()
        self.window.central_widget.set_text("")
        self.full_response = ""
        self.worker.chunk_received.connect(self._accumulate)
        self.worker.start()

        # None needed here as memory is added at trigger since we now have `stt_engine`
        pass

    def _accumulate(self, t):
        self.full_response += t

    def on_error(self, err):
        self.window.central_widget.set_text(f"Error: {err}")
        QTimer.singleShot(3000, self.window.set_state_idle)

    def on_finished(self):
        self.memory.add_assistant_turn(self.full_response)
        # Collapse after a while or on cancel
        QTimer.singleShot(10000, self.window.set_state_idle)

    def on_cancel(self):
        self.window.set_state_idle()
        self.tts_engine.stop()
        if self.stt_engine and self.stt_engine.isRunning():
            self.stt_engine.terminate()
            self.stt_engine.wait()
        if self.worker and self.worker.isRunning():
            self.worker.terminate() 
            self.worker.wait()

    def run(self):
        self.window.set_state_idle()
        sys.exit(self.app.exec())

if __name__ == "__main__":
    app = ClippyApp()
    app.run()
