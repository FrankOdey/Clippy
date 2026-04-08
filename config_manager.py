import os
import json
import keyring
from pathlib import Path

APP_NAME = "Clippy"

DEFAULT_CONFIG = {
    "hotkey": "ctrl+space",
    # --- LLM ---
    "llm_provider": "gemini",           # gemini | anthropic | ollama | openai
    "llm_model": "gemini-2.5-flash",    # model name (provider-specific)
    "ollama_host": "http://localhost:11434",
    "openai_base_url": "https://api.openai.com/v1",
    # --- Voice ---
    "tts_provider": "pyttsx3",          # elevenlabs | pyttsx3
    "voice_id": "rachel",
    "whisper_model": "tiny.en",
    # --- Capture ---
    "capture_max_width": 1280,
    "capture_jpeg_quality": 80,
    # --- UI ---
    "cursor_color": "66,133,244",
    "theme": "auto",
    # --- Misc ---
    "multi_monitor": False,
    "custom_system_prompt_append": "",
    "history_enabled": False,
}


class ConfigManager:
    def __init__(self):
        self.appdata_dir = Path(os.environ.get("APPDATA", "~")).expanduser() / APP_NAME
        self.config_path = self.appdata_dir / "config.json"
        self._ensure_config()
        self.config = self._load_config()

    def _ensure_config(self):
        if not self.appdata_dir.exists():
            self.appdata_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)

    def _load_config(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Merge with defaults for any missing keys
                for k, v in DEFAULT_CONFIG.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            return DEFAULT_CONFIG.copy()

    def save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()

    def get_api_key(self, service_name):
        try:
            return keyring.get_password(APP_NAME, f"{service_name}_api_key")
        except Exception:
            return None

    def set_api_key(self, service_name, api_key):
        if api_key:
            keyring.set_password(APP_NAME, f"{service_name}_api_key", api_key)
        else:
            try:
                keyring.delete_password(APP_NAME, f"{service_name}_api_key")
            except Exception:
                pass


config = ConfigManager()
