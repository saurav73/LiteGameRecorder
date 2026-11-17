"""Single source of truth for the app name and version.

Every module that shows the name or version imports from here, so a
release bump is one line in this file plus a matching git tag.
Never hardcode the version anywhere else.

This module also owns get_app_dir(): the one place that answers
"which folder does the app live in?" In a PyInstaller onefile build
__file__ points inside a temp extraction dir that is deleted when
the app exits, so frozen builds must use the exe's real folder
instead. That is what makes the portable zip work: config.json,
sounds/, meme-videos/, templates/ and FFmpeg all live next to the
exe (or next to the .app on macOS), never in a temp dir.
"""

import sys
from pathlib import Path

__version__ = "2.5.1"
APP_NAME = "Lite Tutorial Maker"
APP_DISPLAY_NAME = f"{APP_NAME} v{__version__}"


def get_app_dir():
    """The folder the app lives in: where config.json, sounds/,
    meme-videos/, templates/ and FFmpeg are found, and where
    config.json is written.

    Frozen (PyInstaller onefile): the folder holding the exe the
    user launched. On macOS the exe sits inside the .app bundle
    (LiteGameRecorder.app/Contents/MacOS/LiteGameRecorder), so the
    app folder is the folder holding the .app itself, keeping the
    data next to the app the user sees.
    From source: the folder holding this file (the project root).
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent.parent
        return exe.parent
    return Path(__file__).resolve().parent
