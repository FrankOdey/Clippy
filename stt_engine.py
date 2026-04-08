import numpy as np
import sounddevice as sd
import webrtcvad
import whisper
from PyQt6.QtCore import pyqtSignal, QThread

class STTEngine(QThread):
    finished_listening = pyqtSignal(str) # Emits the transcribed text
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.model = None
        self.sample_rate = 16000
        self.chunk_duration_ms = 30 # WebRTC VAD needs 10, 20, or 30ms frames
        self.chunk_size = int(self.sample_rate * self.chunk_duration_ms / 1000)
        self.vad = webrtcvad.Vad(2) # aggressiveness 2
        
    def _load_model(self):
        if self.model is None:
            self.model = whisper.load_model("tiny.en")
            
    def run(self):
        # Load model lazily
        try:
            self._load_model()
        except Exception as e:
            print(f"Whisper download/load error: {e}")
            self.error_occurred.emit(f"Could not load Whisper model. First run requires internet: {e}")
            return
        
        audio_data = []
        is_speaking = False
        silence_chunks = 0
        silence_limit = int(1.5 * 1000 / self.chunk_duration_ms) # 1.5 seconds of silence
        max_chunks = int(15.0 * 1000 / self.chunk_duration_ms) # max 15 seconds
        
        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16') as stream:
                for _ in range(max_chunks):
                    # read chunk
                    chunk, overflowed = stream.read(self.chunk_size)
                    
                    # chunk is numpy array, convert to bytes for VAD
                    # sounddevice returns 2D block (frames, channels), so we flatten and tobytes
                    raw_chunk = chunk.flatten().tobytes()
                    
                    is_speech = self.vad.is_speech(raw_chunk, self.sample_rate)
                    
                    if is_speech:
                        is_speaking = True
                        silence_chunks = 0
                    else:
                        if is_speaking:
                            silence_chunks += 1
                            
                    # Start appending if we detected speech or if we're leading up to it
                    # (Append some pre-speech padding)
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

        # convert to numpy float32 array expected by whisper
        full_audio = np.concatenate(audio_data, axis=0)
        full_audio = full_audio.astype(np.float32) / 32768.0 
        
        # transcribe
        try:
            result = self.model.transcribe(full_audio, fp16=False)
            text = result.get("text", "").strip()
            self.finished_listening.emit(text)
        except Exception as e:
            print(f"Whisper transcription error: {e}")
            self.finished_listening.emit("")
