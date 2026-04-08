import platform
import psutil
import pywin32_system32 # ensure it is imported
import win32process
import win32gui
import time
from datetime import datetime
from anthropic import Anthropic, APIStatusError, RateLimitError
import re
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

from config_manager import config

SYSTEM_PROMPT_TEMPLATE = """You are Clippy, a brilliant AI companion living on the user's Windows desktop.
You can see their screen. The red crosshair in the screenshot marks their cursor.
Active app: {active_app_name} | Window: {window_title} | Time: {current_time}

Behavior rules:
- Be concise. Lead with the answer. Elaborate only if asked.
- If you see code on screen, you can reference it directly.
- If you see an error message, diagnose it immediately.
- Speak like a knowledgeable friend — warm, direct, no corporate hedging.
- For multi-step tasks, number your steps clearly.
- Never say "As an AI..." or "I cannot...". Just help.
- If the screenshot is unclear, say so and ask a targeted question.
- Max response length: 120 words unless the user asks for detail.
{custom_append}"""

def get_active_window_info():
    try:
        hwnd = win32gui.GetForegroundWindow()
        window_title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        active_app_name = process.name()
        return active_app_name, window_title
    except Exception:
        return "Unknown", "Unknown"

class LLMClient:
    def __init__(self):
        import os
        self.provider = config.get("llm_provider", "gemini")
        self.api_key = config.get_api_key(self.provider) or os.environ.get(f"{self.provider.upper()}_API_KEY")
        self.anthropic_client = None
        self.gemini_client = None
        
        if self.provider == "anthropic" and self.api_key:
            self.anthropic_client = Anthropic(api_key=self.api_key)
        elif self.provider == "gemini" and self.api_key and genai is not None:
            self.gemini_client = genai.Client(api_key=self.api_key)

    def build_system_prompt(self):
        active_app, window_title = get_active_window_info()
        current_time = datetime.now().strftime("%I:%M %p")
        custom_append = config.get("custom_system_prompt_append", "")
        return SYSTEM_PROMPT_TEMPLATE.format(
            active_app_name=active_app,
            window_title=window_title,
            current_time=current_time,
            custom_append=custom_append
        )

    def generate_streaming(self, user_query: str, image_b64: str, context_messages: list, token_callback, sentence_callback, error_callback):
        if self.provider == "anthropic" and not self.anthropic_client:
            error_callback("Anthropic API Key missing. Please set it in Settings.")
            return
        elif self.provider == "gemini" and not self.gemini_client:
            error_callback("Gemini API Key missing or google-genai not installed.")
            return
        elif self.provider not in ["anthropic", "gemini"]:
            error_callback(f"Provider {self.provider} not fully implemented yet.")
            return

        system_prompt = self.build_system_prompt()
        
        sentence_buffer = ""
        split_pattern = re.compile(r'([.?!])\s+')
        
        def process_buffer(chunk_text):
            nonlocal sentence_buffer
            token_callback(chunk_text)
            sentence_buffer += chunk_text
            
            match = split_pattern.search(sentence_buffer)
            if match:
                split_idx = match.end()
                sentence = sentence_buffer[:split_idx].strip()
                sentence_buffer = sentence_buffer[split_idx:]
                if sentence:
                    sentence_callback(sentence)
                    
        try:
            if self.provider == "anthropic":
                content = []
                if image_b64:
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64
                        }
                    })
                content.append({
                    "type": "text",
                    "text": user_query
                })
                
                messages = context_messages + [{"role": "user", "content": content}]
        
                with self.anthropic_client.messages.stream(
                    max_tokens=256,
                    system=system_prompt,
                    messages=messages,
                    model="claude-3-5-sonnet-latest",
                ) as stream:
                    for chunk in stream.text_stream:
                        process_buffer(chunk)

            elif self.provider == "gemini":
                gemini_messages = []
                for msg in context_messages:
                    role = "user" if msg["role"] == "user" else "model"
                    text_content = msg["content"][0]["text"]
                    gemini_messages.append(types.Content(role=role, parts=[types.Part.from_text(text=text_content)]))
                
                parts = []
                if image_b64:
                    import base64
                    image_bytes = base64.b64decode(image_b64)
                    parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
                parts.append(types.Part.from_text(text=user_query))
                gemini_messages.append(types.Content(role="user", parts=parts))
                
                response = self.gemini_client.models.generate_content_stream(
                    model="gemini-2.5-flash",
                    contents=gemini_messages,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        max_output_tokens=256,
                    )
                )
                for chunk in response:
                    if chunk.text:
                        process_buffer(chunk.text)
                        
            if sentence_buffer.strip():
                sentence_callback(sentence_buffer.strip())
                
        except APIStatusError as e:
            error_callback(f"API Error: {e.message}")
        except RateLimitError:
            error_callback("Rate Limit Exceeded. Backing off.")
        except Exception as e:
            error_callback(f"Unknown LLM Error: {str(e)}")
