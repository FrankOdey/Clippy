import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QComboBox, QPushButton, QColorDialog, QFormLayout, QDialogButtonBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from config_manager import config

DARK_CSS = """
QDialog {
    background-color: #1e1e1e;
    color: #ffffff;
    font-family: 'Segoe UI', -apple-system, sans-serif;
}
QLabel {
    color: #cccccc;
    font-size: 13px;
}
QLineEdit, QComboBox {
    background-color: #2d2d30;
    color: #ffffff;
    border: 1px solid #3e3e42;
    border-radius: 4px;
    padding: 6px;
    font-size: 13px;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #007acc;
}
QPushButton {
    background-color: #3f3f46;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #555555;
}
QPushButton:pressed {
    background-color: #007acc;
}
"""

class SettingsDialog(QDialog):
    # Signals for live preview and save events
    color_preview = pyqtSignal(str)     # "R,G,B"
    settings_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clippy Settings")
        self.setMinimumWidth(400)
        self.setStyleSheet(DARK_CSS)
        
        # Keep track of original color so we can revert if cancelled
        self.original_color_str = config.get("cursor_color", "66,133,244")
        
        self._setup_ui()
        self._populate_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 1. Hotkey
        self.hotkey_input = QLineEdit()
        self.hotkey_input.setPlaceholderText("e.g. ctrl+space")
        form_layout.addRow("Global Hotkey:", self.hotkey_input)
        
        # 2. LLM Provider
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["gemini", "anthropic", "openai", "ollama"])
        form_layout.addRow("LLM Provider:", self.provider_combo)
        
        # 3. LLM Model
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("e.g. gemini-2.5-flash or moondream")
        form_layout.addRow("LLM Model:", self.model_input)
        
        # 4. API Key
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Leave blank to keep existing")
        form_layout.addRow("API Key:", self.api_key_input)
        
        # 5. Ollama Host
        self.ollama_host_input = QLineEdit()
        self.ollama_host_input.setPlaceholderText("http://localhost:11434")
        form_layout.addRow("Ollama Host:", self.ollama_host_input)
        
        # 6. Cursor Color
        color_layout = QHBoxLayout()
        self.color_preview_label = QLabel()
        self.color_preview_label.setFixedSize(24, 24)
        self.color_preview_label.setStyleSheet(f"background-color: rgb({self.original_color_str}); border-radius: 12px;")
        
        self.color_btn = QPushButton("Pick Color...")
        self.color_btn.clicked.connect(self._pick_color)
        
        color_layout.addWidget(self.color_preview_label)
        color_layout.addWidget(self.color_btn)
        color_layout.addStretch()
        form_layout.addRow("Cursor Color:", color_layout)
        
        layout.addLayout(form_layout)
        
        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _populate_data(self):
        self.hotkey_input.setText(config.get("hotkey", "ctrl+space"))
        
        provider = config.get("llm_provider", "gemini")
        idx = self.provider_combo.findText(provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
            
        self.model_input.setText(config.get("llm_model", "gemini-2.5-flash"))
        self.ollama_host_input.setText(config.get("ollama_host", "http://localhost:11434"))

    def _pick_color(self):
        # Parse current
        current_str = self.color_preview_label.property("current_rgb") or self.original_color_str
        r, g, b = map(int, current_str.split(","))
        initial_color = QColor(r, g, b)
        
        color = QColorDialog.getColor(initial_color, self, "Pick Cursor Color")
        if color.isValid():
            new_rgb = f"{color.red()},{color.green()},{color.blue()}"
            self.color_preview_label.setProperty("current_rgb", new_rgb)
            self.color_preview_label.setStyleSheet(f"background-color: rgb({new_rgb}); border-radius: 12px;")
            # Emit live preview
            self.color_preview.emit(new_rgb)

    def accept(self):
        # Save sequence
        config.set("hotkey", self.hotkey_input.text())
        
        provider = self.provider_combo.currentText()
        config.set("llm_provider", provider)
        config.set("llm_model", self.model_input.text())
        config.set("ollama_host", self.ollama_host_input.text())
        
        # Save API key if typed (otherwise preserve existing keyring)
        new_key = self.api_key_input.text().strip()
        if new_key:
            config.set_api_key(provider, new_key)
            
        # Save Color
        current_rgb = self.color_preview_label.property("current_rgb")
        if current_rgb:
            config.set("cursor_color", current_rgb)
            
        self.settings_saved.emit()
        super().accept()

    def reject(self):
        # Revert live preview
        self.color_preview.emit(self.original_color_str)
        super().reject()
