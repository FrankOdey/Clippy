import os
import json
import keyring
from pathlib import Path

APP_NAME = "Clippy"

DEFAULT_CONFIG = {
    "hotkey": "ctrl+space",
    "tts_provider": "elevenlabs",  # or pyttsx3
    "voice_id": "rachel",
    "llm_provider": "anthropic", # 'anthropic', 'gemini', or 'local'
    "whisper_model": "tiny.en",
    "multi_monitor": False,
    "theme": "auto",
    "custom_system_prompt_append": "",
    "history_enabled": False
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
                # merge with defaults for missing keys
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
        return keyring.get_password(APP_NAME, f"{service_name}_api_key")

    def set_api_key(self, service_name, api_key):
        if api_key:
            keyring.set_password(APP_NAME, f"{service_name}_api_key", api_key)
        else:
            try:
                keyring.delete_password(APP_NAME, f"{service_name}_api_key")
            except keyring.errors.PasswordDeleteError:
                pass

config = ConfigManager()
