import os
import subprocess

def run_build():
    print("Building Clippy executable...")
    # PyInstaller with --onedir for startup speed
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "Clippy",
        "main.py"
    ]
    subprocess.run(cmd, check=True)
    print("Build complete. Artifacts in dist/Clippy")

if __name__ == "__main__":
    run_build()
