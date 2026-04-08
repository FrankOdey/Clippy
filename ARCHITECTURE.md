# Architecture

## Data Flow Diagram
1. Hotkey (`hotkey_listener.py`) -> Main Loop
2. STT Engine (`stt_engine.py`) -> Microphone -> VAD -> Whisper -> User Query Text
3. Capture System (`screen_capture.py`) -> DXcam -> JPEG Base64
4. LLM API (`llm_client.py`) -> Anthropic Client -> Stream Text Chunks
5. TTS Engine (`tts_engine.py`) -> Text Chunks -> ElevenLabs Voice Stream -> Sounddevice

## Threading Model
- Main Thread: PyQt6 Event Loop (UI, Animations, Config)
- Worker Thread 1: Hotkey Listener (blocking keyboard hooking)
- Worker Thread 2: LLM API Generator (blocking Anthropic streaming)
- Worker Thread 3: TTS Queue Processor (consumes ElevenLabs chunks)
- Worker Thread 4: STT VAD loop (Microphone loop & inference)

## Latency Budgets
- DXcam capture: < 16ms
- VAD trigger: ~200ms
- Whisper (tiny.en): ~250ms
- Claude 3.5 Sonnet First Token: ~500ms
- ElevenLabs First Byte: ~180ms
- Total Latency Target (Voice -> Response Start): < 1.2s
