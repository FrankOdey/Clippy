# Clippy

A lightweight, always-on Windows desktop companion. It floats near the cursor, activates on a global hotkey, listens to your voice query, captures the screen in real-time, and returns a spoken + visual response.

## Setup

1. **Install Requirements:**
   ```bash
   pip install -r requirements.txt
   ```

2. **API Keys:**
   On the first run, the app will use its `config_manager` to request API keys, or you can manually enter them.
   Run `python config_manager.py` to optionally test config setup, but `main.py` is the entry point.

3. **Run Clippy:**
   ```bash
   python main.py
   ```

## Hotkeys

- `Ctrl + Space`: Activate Clippy (starts listening / capturing)
- `Esc`: Cancel/Dismiss Clippy and stop TTS stream.

## Packaging

To build the executable:
```bash
python build.py
```
This produces a `dist/Clippy` directory.

To create an installer, ensure Inno Setup is installed, then compile `installer.iss`.
