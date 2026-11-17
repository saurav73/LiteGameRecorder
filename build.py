"""Build a standalone Lite Game Recorder v2 for the current OS.

Usage (any platform, after installing requirements):
    python build.py
Output: dist/LiteGameRecorder  (or .exe on Windows, .app on macOS with --app)

This replaces the old Windows-only build_exe.bat. PyInstaller runs on
Windows, macOS and Linux and produces a native binary for that OS.
For all three at once, see .github/workflows/build.yml (GitHub Actions).
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "pyinstaller", "--quiet"], check=True, cwd=HERE)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "LiteGameRecorder.spec"]
    if "--app" in sys.argv and sys.platform == "darwin":
        cmd.append("--windowed")
    subprocess.run(cmd, check=True, cwd=HERE)
    print("\nDone! Your app is in dist/ — double-click it to run, no terminal window.")


if __name__ == "__main__":
    main()
