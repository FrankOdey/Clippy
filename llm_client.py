import os
import sys
import re
import time
import threading
import httpx
from datetime import datetime

import psutil
import win32process
import win32gui

from config_manager import config

# --- Optional provider imports (none should crash the app) ---
try:
    from anthropic import Anthropic, APIStatusError, RateLimitError
except ImportError:
    Anthropic = None
    APIStatusError = None
    RateLimitError = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """You are Clippy, a brilliant AI companion living on the user's Windows desktop.
You can see their screen. The cursor arrow in the screenshot marks their pointer.
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
    """Return (app_name, window_title) for the foreground window."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        window_title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        return process.name(), window_title
    except Exception:
        return "Unknown", "Unknown"


class LLMClient:
    """Thin orchestrator that delegates to the configured LLM provider."""

    def __init__(self):
        # Load .env file if present (for developer convenience)
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass  # dotenv not installed — that's fine, not required

        self.provider = config.get("llm_provider", "gemini")
        self.model_name = config.get("llm_model", "gemini-2.5-flash")

        # Resolve API key: keyring first, then environment variable
        self.api_key = config.get_api_key(self.provider)
        if not self.api_key:
            self.api_key = os.environ.get(f"{self.provider.upper()}_API_KEY")
            if self.api_key:
                print(f"Using environment variable for {self.provider} API key")

        self.anthropic_client = None
        self.gemini_client = None
        self.error_state = None

        # Auto-detect fallback logic
        provider_ready = False
        if self.provider == "anthropic" and self.api_key and Anthropic is not None:
            self.anthropic_client = Anthropic(api_key=self.api_key)
            provider_ready = True
        elif self.provider == "gemini" and self.api_key and genai is not None:
            self.gemini_client = genai.Client(api_key=self.api_key)
            provider_ready = True
        elif self.provider == "openai" and self.api_key:
            provider_ready = True
        elif self.provider == "ollama":
            pass # verified actively below

        # If provider isn't ready (missing key/packages) OR provider is explicitly ollama:
        if not provider_ready or self.provider == "ollama":
            # Attempt Ollama local detection
            host = config.get("ollama_host", "http://localhost:11434")
            try:
                r = httpx.get(f"{host}/api/tags", timeout=1.0)
                if r.status_code == 200:
                    tags = r.json().get("models", [])
                    models = [m.get("name") for m in tags]
                    
                    self.provider = "ollama"
                    
                    # Auto-select a vision model if available
                    preferred = ["moondream:latest", "llava:latest"]
                    found_model = None
                    for p in preferred:
                        if p in models:
                            found_model = p
                            break
                            
                    if found_model:
                        self.model_name = found_model
                    elif models:
                        self.model_name = models[0] # Fallback to first available
                    else:
                        self.error_state = "Ollama is running but has no models pulled."
                        
                    provider_ready = True
                    print(f"✅ Active Provider: Ollama -> {self.model_name}")
            except Exception as e:
                if self.provider == "ollama":
                    self.error_state = f"Ollama connection failed: {e}"
                
        if not provider_ready and not self.error_state:
            self.error_state = f"Provider '{self.provider}' failed to initialize (missing API key or package)."


    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------
    def build_system_prompt(self) -> str:
        active_app, window_title = get_active_window_info()
        current_time = datetime.now().strftime("%I:%M %p")
        custom_append = config.get("custom_system_prompt_append", "")
        # Guard against excessively long custom prompts
        if len(custom_append) > 500:
            custom_append = custom_append[:500]
        return SYSTEM_PROMPT_TEMPLATE.format(
            active_app_name=active_app,
            window_title=window_title,
            current_time=current_time,
            custom_append=custom_append,
        )

    # ------------------------------------------------------------------
    # Streaming entry point
    # ------------------------------------------------------------------
    def generate_streaming(
        self,
        user_query: str,
        image_b64: str,
        context_messages: list,
        token_callback,
        sentence_callback,
        error_callback,
        cancel_event: threading.Event = None,
    ):
        if cancel_event is None:
            cancel_event = threading.Event()

        if self.error_state:
            error_callback(self.error_state); return
            
        # Validate provider readiness (safety check)
        if self.provider == "anthropic":
            if Anthropic is None:
                error_callback("anthropic package is not installed."); return
            if not self.anthropic_client:
                error_callback("Anthropic API key missing."); return

        elif self.provider == "gemini":
            if genai is None:
                error_callback("google-genai package is not installed."); return
            if not self.gemini_client:
                error_callback("Gemini API key missing."); return

        elif self.provider == "ollama":
            pass  # no key needed

        elif self.provider == "openai":
            if not self.api_key:
                error_callback("OpenAI API key missing."); return

        else:
            error_callback(f"Unknown provider: {self.provider}"); return

        system_prompt = self.build_system_prompt()

        # Sentence chunking
        sentence_buffer = ""
        split_pattern = re.compile(r"([.?!])\s+")

        def process_token(chunk_text):
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
                self._stream_anthropic(system_prompt, user_query, image_b64, context_messages, process_token, cancel_event)
            elif self.provider == "gemini":
                self._stream_gemini(system_prompt, user_query, image_b64, context_messages, process_token, cancel_event)
            elif self.provider == "ollama":
                self._stream_ollama(system_prompt, user_query, image_b64, context_messages, process_token, cancel_event)
            elif self.provider == "openai":
                self._stream_openai(system_prompt, user_query, image_b64, context_messages, process_token, cancel_event)

            # Flush remaining buffer
            if sentence_buffer.strip():
                sentence_callback(sentence_buffer.strip())

        except Exception as e:
            # Catch-all for provider-specific exceptions that leaked
            error_callback(f"LLM Error ({self.provider}): {e}")

    # ------------------------------------------------------------------
    # Anthropic
    # ------------------------------------------------------------------
    def _stream_anthropic(self, system_prompt, user_query, image_b64, context_messages, process_token, cancel_event):
        content = []
        if image_b64:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
            })
        content.append({"type": "text", "text": user_query})
        messages = context_messages + [{"role": "user", "content": content}]

        with self.anthropic_client.messages.stream(
            max_tokens=256,
            system=system_prompt,
            messages=messages,
            model=self.model_name or "claude-3-5-sonnet-latest",
        ) as stream:
            for chunk in stream.text_stream:
                if cancel_event.is_set():
                    break
                process_token(chunk)

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------
    def _stream_gemini(self, system_prompt, user_query, image_b64, context_messages, process_token, cancel_event):
        import base64 as b64mod

        gemini_messages = []
        for msg in context_messages:
            role = "user" if msg["role"] == "user" else "model"
            text_content = msg["content"][0]["text"]
            gemini_messages.append(
                types.Content(role=role, parts=[types.Part.from_text(text=text_content)])
            )

        parts = []
        if image_b64:
            image_bytes = b64mod.b64decode(image_b64)
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
        parts.append(types.Part.from_text(text=user_query))
        gemini_messages.append(types.Content(role="user", parts=parts))

        response = self.gemini_client.models.generate_content_stream(
            model=self.model_name or "gemini-2.5-flash",
            contents=gemini_messages,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=256,
            ),
        )
        for chunk in response:
            if cancel_event.is_set():
                break
            if chunk.text:
                process_token(chunk.text)

    # ------------------------------------------------------------------
    # Ollama (fully local, no API key)
    # ------------------------------------------------------------------
    def _stream_ollama(self, system_prompt, user_query, image_b64, context_messages, process_token, cancel_event):
        import json
        import httpx

        host = config.get("ollama_host", "http://localhost:11434")
        model = self.model_name or "moondream"

        messages = [{"role": "system", "content": system_prompt}]
        for msg in context_messages:
            messages.append({
                "role": msg["role"],
                "content": msg["content"][0]["text"],
            })

        user_msg = {"role": "user", "content": user_query}
        if image_b64:
            user_msg["images"] = [image_b64]
        messages.append(user_msg)

        with httpx.stream(
            "POST",
            f"{host}/api/chat",
            json={"model": model, "messages": messages, "stream": True},
            timeout=60.0,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if cancel_event.is_set():
                    break
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                if token:
                    process_token(token)

    # ------------------------------------------------------------------
    # OpenAI-compatible (OpenAI, Azure, LM Studio, vLLM, etc.)
    # ------------------------------------------------------------------
    def _stream_openai(self, system_prompt, user_query, image_b64, context_messages, process_token, cancel_event):
        import json
        import httpx

        base_url = config.get("openai_base_url", "https://api.openai.com/v1")
        model = self.model_name or "gpt-4o"

        messages = [{"role": "system", "content": system_prompt}]
        for msg in context_messages:
            messages.append({
                "role": msg["role"],
                "content": msg["content"][0]["text"],
            })

        # Build user message with optional vision
        if image_b64:
            user_content = [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": user_query},
            ]
        else:
            user_content = user_query
        messages.append({"role": "user", "content": user_content})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.stream(
            "POST",
            f"{base_url}/chat/completions",
            json={"model": model, "messages": messages, "stream": True, "max_tokens": 256},
            headers=headers,
            timeout=30.0,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if cancel_event.is_set():
                    break
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                data = json.loads(payload)
                delta = data.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    process_token(token)
