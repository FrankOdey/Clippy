import threading
import numpy as np
import sounddevice as sd
import webrtcvad

try:
    import whisper
except ImportError:
    whisper = None

from PyQt6.QtCore import pyqtSignal, QThread
from config_manager import config


class STTEngine(QThread):
    """Speech-to-text engine using local Whisper with WebRTC VAD.
    
    Designed to be re-created for each activation cycle since QThread
    cannot reliably be re-started after finishing.
    """
    finished_listening = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    # Class-level model cache — survives instance re-creation
    _shared_model = None
    _model_lock = threading.Lock()

    def __init__(self, cancel_event: threading.Event = None):
        super().__init__()
        self.cancel_event = cancel_event or threading.Event()
        self.sample_rate = 16000
        self.chunk_duration_ms = 30
        self.chunk_size = int(self.sample_rate * self.chunk_duration_ms / 1000)
        self.vad = webrtcvad.Vad(2)

    @classmethod
    def preload_model(cls):
        """Pre-load the Whisper model in a background thread at app startup."""
        if whisper is None:
            return
        with cls._model_lock:
            if cls._shared_model is None:
                model_name = config.get("whisper_model", "tiny.en")
                try:
                    cls._shared_model = whisper.load_model(model_name)
                except Exception as e:
                    print(f"Whisper preload failed (will retry on first use): {e}")

    def _get_model(self):
        """Get the shared model, loading it if necessary."""
        if whisper is None:
            raise RuntimeError("openai-whisper is not installed. Run: pip install openai-whisper")
        with self._model_lock:
            if self._shared_model is None:
                model_name = config.get("whisper_model", "tiny.en")
                self._shared_model = whisper.load_model(model_name)
            return self._shared_model

    def run(self):
        # Load model
        try:
            model = self._get_model()
        except Exception as e:
            print(f"Whisper load error: {e}")
            self.error_occurred.emit(f"Could not load Whisper model: {e}")
            return

        audio_data = []
        is_speaking = False
        silence_chunks = 0
        silence_limit = int(1.5 * 1000 / self.chunk_duration_ms)
        max_chunks = int(15.0 * 1000 / self.chunk_duration_ms)

        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16') as stream:
                for _ in range(max_chunks):
                    # Cooperative cancellation check
                    if self.cancel_event.is_set():
                        self.finished_listening.emit("")
                        return

                    chunk, overflowed = stream.read(self.chunk_size)
                    raw_chunk = chunk.flatten().tobytes()

                    is_speech = self.vad.is_speech(raw_chunk, self.sample_rate)

                    if is_speech:
                        is_speaking = True
                        silence_chunks = 0
                    else:
                        if is_speaking:
                            silence_chunks += 1

                    if is_speaking or len(audio_data) < 10:
                        audio_data.append(chunk.flatten())

                    if is_speaking and silence_chunks >= silence_limit:
                        break
        except Exception as e:
            print(f"Audio input error: {e}")
            self.finished_listening.emit("")
            return

        if not is_speaking or not audio_data:
            self.finished_listening.emit("")
            return

        # Check cancellation before transcription
        if self.cancel_event.is_set():
            self.finished_listening.emit("")
            return

        # Transcribe
        full_audio = np.concatenate(audio_data, axis=0)
        full_audio = full_audio.astype(np.float32) / 32768.0

        try:
            result = model.transcribe(full_audio, fp16=False)
            text = result.get("text", "").strip()
            self.finished_listening.emit(text)
        except Exception as e:
            print(f"Whisper transcription error: {e}")
            self.finished_listening.emit("")
