# PyInstaller spec for Lite Tutorial Maker
# Builds a single windowed app on Windows (.exe), macOS (.app) and Linux:
#   python build.py
# or: python -m PyInstaller --noconfirm --clean LiteGameRecorder.spec
# Data files (sounds/, meme-videos/, templates/) and FFmpeg are NOT
# bundled into the binary: the release workflow puts them next to it,
# and get_app_dir() (app_version.py) finds them there. That is what
# makes the release zip portable.
# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

# Platform icon: .ico on Windows, .icns on macOS (built in CI from
# icon.png; if it is missing the build just ships without an icon
# instead of failing), none on Linux.
if sys.platform == "win32":
    ICON = "icon.ico"
elif sys.platform == "darwin" and os.path.exists("icon.icns"):
    ICON = "icon.icns"
else:
    ICON = None

# UPX breaks macOS binaries (code signing), so it stays off there.
USE_UPX = sys.platform != "darwin"

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'cv2', 'numpy', 'mss', 'PIL', 'PIL.Image', 'PIL.ImageTk',
        'sounddevice', 'pynput', 'pynput.mouse', 'pynput.keyboard',
        'customtkinter', 'editor', 'installer', 'app_version',
        'updater', 'make_meme_videos',
        'packaging', 'packaging.version',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LiteGameRecorder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=USE_UPX,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # <-- no terminal window, ever
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

# macOS: a proper .app bundle, so the app double-clicks like a real
# Mac app instead of opening a Terminal window. The data folders and
# ffmpeg live NEXT TO the .app in the release zip; get_app_dir()
# resolves the folder holding the .app, so the app finds them there.
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="LiteGameRecorder.app",
        icon=ICON,
        bundle_identifier="com.saurav73.litegamerecorder",
        info_plist={
            "NSHighResolutionCapable": "True",
            "NSCameraUsageDescription": "Lite Tutorial Maker uses your camera for the facecam overlay while recording.",
            "NSMicrophoneUsageDescription": "Lite Tutorial Maker records your microphone with your screen recording.",
        },
    )
