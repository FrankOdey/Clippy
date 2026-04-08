import threading
import queue
from config_manager import config
import pyttsx3
try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import stream
except ImportError:
    ElevenLabs = None

class TTSEngine:
    def __init__(self):
        self.provider = config.get("tts_provider", "elevenlabs")
        api_key = config.get_api_key(self.provider)
        
        self.eleven_client = None
        if self.provider == "elevenlabs" and api_key and ElevenLabs is not None:
            self.eleven_client = ElevenLabs(api_key=api_key)
            
        self.offline_engine = pyttsx3.init()
        # Ensure offline voice rate is reasonable
        self.offline_engine.setProperty('rate', 170)
        
        self.text_queue = queue.Queue()
        self.worker = threading.Thread(target=self._process_queue, daemon=True)
        self.worker.start()

    def speak(self, text: str):
        """Adds a complete sentence or chunk to the speaking queue."""
        if text.strip():
            self.text_queue.put(text)

    def stop(self):
        # Empty queue
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except queue.Empty:
                break
        
        # We can't immediately stop blocking ElevenLabs stream easily without killing process here,
        # but offline engine can be stopped
        if not self.eleven_client:
             self.offline_engine.stop()

    def _process_queue(self):
        while True:
            text = self.text_queue.get()
            if text is None:
                break
                
            if self.eleven_client:
                try:
                    audio_stream = self.eleven_client.generate(
                        text=text,
                        voice="Rachel", 
                        model="eleven_turbo_v2", # Turbo model is much lower latency
                        stream=True
                    )
                    # Play the chunk
                    stream(audio_stream)
                except Exception as e:
                    print(f"ElevenLabs TTS error: {e}, falling back to pyttsx3.")
                    self.offline_engine.say(text)
                    self.offline_engine.runAndWait()
            else:
                # Offline fallback
                self.offline_engine.say(text)
                self.offline_engine.runAndWait()
                
            self.text_queue.task_done()
