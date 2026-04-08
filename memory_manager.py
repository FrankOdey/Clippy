import sqlite3
import datetime
from pathlib import Path
from config_manager import config

class MemoryManager:
    def __init__(self):
        self.max_context_turns = 6 # rolling context window
        self.history = [] # list of {"role": "user"/"assistant", "content": text}

    def add_user_turn(self, content: str):
        self.history.append({"role": "user", "content": [{"type": "text", "text": content}]})
        self._trim_history()

    def add_assistant_turn(self, content: str):
        self.history.append({"role": "assistant", "content": [{"type": "text", "text": content}]})
        self._trim_history()

    def _trim_history(self):
        while len(self.history) > self.max_context_turns * 2:
            self.history.pop(0)

    def get_context(self, num_turns=2):
        """Returns the last num_turns of conversation (each turn is a user and assistant message pair)."""
        num_messages = num_turns * 2
        return self.history[-num_messages:]

    def clear(self):
        self.history = []
