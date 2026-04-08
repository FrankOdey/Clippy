import os
from screen_capture import ScreenCapturer
from llm_client import LLMClient
from config_manager import config

def test_loop():
    print("Testing capture...")
    capturer = ScreenCapturer()
    img_b64 = capturer.capture_base64()
    print("Capture size:", len(img_b64))

    print("Configuring LLM...")
    api_key = os.environ.get("TEST_GEMINI_KEY")
    config.set("llm_provider", "gemini")
    
    # We patch the client since we don't want to store the key in keyring
    client = LLMClient()
    client.provider = "gemini"
    client.api_key = api_key
    from google import genai
    client.gemini_client = genai.Client(api_key=api_key)
    
    print("Generating streaming response...")
    def token_cb(t): print(t, end="", flush=True)
    def sentence_cb(s): pass
    def err_cb(e): print("ERROR:", e)
    
    client.generate_streaming(
        "What shape is my cursor pointer overlaid as? (e.g. triangle, crosshair, dot). Please be brief.", 
        img_b64, 
        [], 
        token_cb, 
        sentence_cb, 
        err_cb
    )
    print("\nTest complete.")

if __name__ == "__main__":
    test_loop()
