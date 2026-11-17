"""
Lite Game Recorder v2.1 - Screen + Facecam for light / low-end laptops
  * Modern CustomTkinter UI, cross-platform (Windows / macOS / Linux)
  * Live streaming to any RTMP platform: YouTube, Twitch, Facebook, Kick, Custom
-----------------------------------------------------------------
Why it's light:
  * Screen capture with `mss` (fast, low CPU, no full-frame copies via FFmpeg pipe)
  * Webcam read in its own thread, only the LATEST frame is kept (no queue build-up)
  * A timeline writer writes frames on a wall-clock schedule (v1.2), so the video
    duration always matches the real recording time - never fast-forward playback
  * Default is 720p / 30 FPS (the sweet spot for weak laptops). 1080p / 60 FPS are optional.
  * No Electron, no heavy UI - just Tkinter (built into Python)

Controls:
  F9  = Start / Stop recording
  F10 = Pause / Resume

Output: MP4 video (+ mic audio muxed in automatically if FFmpeg is installed,
        otherwise a separate .wav mic file is saved next to the video - see README)
"""

import os
import sys
import json
import math
import time
import queue
import wave
import threading
import datetime
import traceback
import shutil
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import customtkinter as ctk
    HAS_CTK = True
except Exception as e:
    # Do NOT hide the real error: an earlier version set ctk=None here
    # and crashed later with a confusing "'NoneType' has no attribute
    # 'CTk'". Show the real reason instead, and write it to error.log
    # next to app.py so the user can send it to us.
    import traceback as _tb
    _err = f"Could not load the design library (customtkinter): {type(e).__name__}: {e}\n{_tb.format_exc()}"
    print(_err, file=sys.stderr)
    try:
        with open(Path(__file__).resolve().parent / "error.log", "w", encoding="utf-8") as _f:
            _f.write(_err)
    except Exception:
        pass
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Lite Game Recorder cannot start",
            "The design library (customtkinter) could not be loaded.\n\n"
            f"{type(e).__name__}: {e}\n\n"
            "The full error was saved to error.log next to app.py.\n"
            "Please send error.log (or run.log) to Muse so it can be fixed.",
        )
        root.destroy()
    except Exception:
        pass
    sys.exit(1)

try:
    import cv2
    import numpy as np
    import mss
    from PIL import Image, ImageTk
except ImportError as e:
    # Friendly first-run error instead of a traceback
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Missing libraries",
        f"Some libraries are missing ({e}).\n\n"
        "Please run:\n  pip install -r requirements.txt\n\n"
        "Or double-click run.bat (Windows) which does it for you.",
    )
    sys.exit(1)

# Optional mic support - app works fine without it
try:
    import sounddevice as sd
    HAS_MIC = True
except Exception:
    HAS_MIC = False

APP_NAME = "Lite Game Recorder v2.3"

# RTMP ingest URLs. The stream key is yours - never share it.
# YouTube / Twitch / Facebook / Kick all speak RTMP, so "any platform"
# just means: pick the preset, paste your key, go live.
LIVE_PLATFORMS = {
    "YouTube":  "rtmp://a.rtmp.youtube.com/live2",
    "Twitch":   "rtmp://live.twitch.tv/app",
    "Facebook": "rtmps://live-api-s.facebook.com:443/rtmp/",
    "Kick":     "rtmp://live.kick.com/app",
    "Custom":   "",
}
LIVE_HELP = {
    "YouTube":  "YouTube Studio > Create > Go live > Stream > copy Stream key",
    "Twitch":   "Twitch Creator Dashboard > Settings > Stream > copy Primary Stream Key",
    "Facebook": "Meta Live Producer / facebook.com/live/producer > copy Stream Key",
    "Kick":     "Kick Dashboard > Settings > Stream Key > copy it",
    "Custom":   "Paste the full RTMP URL your platform gave you, plus its stream key",
}
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_OUTPUT = Path.home() / "Videos" / "GameRecorder"



def _quiet_subprocess_kwargs():
    """Run a helper program (FFmpeg) without flashing a black console window.

    On Windows, subprocess calls can briefly pop a console even from a
    windowed app. Hiding it here is what makes v1.5 feel like a real
    installed app instead of a script run from a terminal.
    """
    if sys.platform == "win32":
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
        except Exception:
            return {}
    return {}


# --------------------------------------------------------------------------- config
def load_config():
    defaults = {
        "output_dir": str(DEFAULT_OUTPUT),
        "resolution": "720p (Light - Recommended)",
        "fps": 30,
        "light_mode": True,  # weak-laptop mode: 720p max, lighter preview/filter
        "facecam": True,
        "mirror_facecam": True,  # flip the facecam left-right, like a selfie - off = as a viewer sees you
        "facecam_pos": "Bottom Right",
        "facecam_size": 22,          # % of video width
        "facecam_shape": "Rounded",
        "mic": True,
        "system_audio": False,
        "game_sound_only": False,
        "system_audio_source": "",
        "camera_index": 0,
        "speed": 1.0,
        "voice": "Off",
        "video_filter": "None",
        "filter_whole_video": False,
        # v2.3 - smart script record
        "script_enabled": False,
        "script_text": "Hi, welcome back to my channel!",
        "script_autocorrect": True,
        "script_live_check": True,
        "screen_only": False,
        "click_zoom": True,
        "zoom_level": 1.8,
        "mouse_fx": True,
        "countdown": True,
        "keystrokes": False,
        "record_limit": 0,
        "area": "Full Screen",
        "region": None,
        "gif": False,
        "noise_reduction": False,
        # v2.0 - live streaming (RTMP, any platform)
        # Instant Replay (ShadowPlay-style): record in the background
        # and save the last moments on F11.
        "replay_enabled": False,
        "replay_seconds": 60,
        "live_enabled": False,
        "live_platform": "YouTube",
        "live_rtmp_url": LIVE_PLATFORMS["YouTube"],
        "live_stream_key": "",
        "live_remember_key": False,
        "live_bitrate": "4500k",
        "live_audio": True,
    }
    if CONFIG_PATH.exists():
        try:
            defaults.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return defaults


def save_config(cfg):
    try:
        to_save = dict(cfg)
        if not to_save.get("live_remember_key"):
            to_save["live_stream_key"] = ""
        CONFIG_PATH.write_text(json.dumps(to_save, indent=2), encoding="utf-8")
    except Exception:
        pass


def _dir_is_usable(d):
    """Create folder (step by step) and prove we can actually write into it."""
    # Create one level at a time - more reliable on Windows when a library
    # folder (e.g. Videos) is missing / redirected / blocked.
    cur = Path(d.anchor) if d.is_absolute() else Path(".")
    for part in d.parts[1:] if d.is_absolute() else d.parts:
        cur = cur / part
        try:
            cur.mkdir(exist_ok=True)
        except FileExistsError:
            pass
        if not cur.is_dir():
            return False
    test = Path(d) / ".write_test_tmp"
    with open(test, "wb") as f:
        f.write(b"ok")
    test.unlink()
    return True


def ensure_output_dir(preferred):
    """Return the first folder we can create + write to.

    Fix for v1 bug: on some Windows PCs the Videos library folder can't be
    created (missing/redirected/blocked), and recording failed instantly with
    [WinError 2] 'system cannot find the file specified: ...\\Videos\\GameRecorder'.
    Now we automatically fall back instead of failing.
    """
    candidates = []
    if preferred:
        candidates.append(Path(preferred))
    home = Path.home()
    candidates += [
        home / "Documents" / "GameRecorder",
        home / "Desktop" / "GameRecorder",
        home / "GameRecorder",
        APP_DIR / "Recordings",
    ]
    errors = []
    seen = set()
    for cand in candidates:
        key = str(cand).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if _dir_is_usable(cand):
                return cand
            errors.append(f"{cand}: not usable")
        except Exception as e:
            errors.append(f"{cand}: {e}")
    raise RuntimeError(
        "I couldn't create a folder to save videos in. Tried:\n" + "\n".join(errors) +
        "\n\nPlease click Browse and pick a folder you created yourself, e.g. on your Desktop."
    )


def log_error(context):
    try:
        (APP_DIR / "error.log").write_text(
            f"{datetime.datetime.now().isoformat()}  {context}\n{traceback.format_exc()}",
            encoding="utf-8",
        )
    except Exception:
        pass



# --------------------------------------------------------------------------- character filters (v2.2)
# When you are on camera (facecam), these make you look like another
# character - cartoon, anime, robot, alien and so on. They are STYLE
# filters (colour + edges + posterising, all in OpenCV, light enough to
# run live). They are NOT a face-swap to a real person or a specific
# licensed character - that needs a heavy AI model and a download.
CHARACTER_FILTERS = [
    "None", "Smooth (Natural)", "B&W", "Sepia", "Warm", "Cool",
    "Cartoon", "Anime", "LING", "Comic", "Sketch", "Pixel",
    "Robot", "Alien", "Vampire", "Neon", "Hero",
    "Vintage", "Vivid", "Noir", "TealOrange",
    "LUT",  # a .cube colour look loaded in the editor (see editor.py)
]

def _posterize(img, levels=4):
    step = 256 // levels
    return ((img // step) * step + step // 2).astype(np.uint8)

def _edges_bgr(img, block=9, c=9):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY, block, c)
    return cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

def _boost_saturation(img, factor):
    try:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * factor, 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    except Exception:
        return img

_FACE_CASCADE = None

def _detect_face_box(img):
    """Largest face box (x, y, w, h) in a BGR image, or None.
    Uses the Haar cascade bundled with OpenCV when available;
    returns None when it is missing or finds nothing (caller
    falls back to the centre of the frame - the facecam is a
    close-up, so the face is normally in the middle)."""
    global _FACE_CASCADE
    try:
        if _FACE_CASCADE is None:
            import os
            path = os.path.join(cv2.data.haarcascades,
                                "haarcascade_frontalface_default.xml")
            _FACE_CASCADE = cv2.CascadeClassifier(path)
            if _FACE_CASCADE.empty():
                _FACE_CASCADE = False
        if not _FACE_CASCADE:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = _FACE_CASCADE.detectMultiScale(gray, 1.2, 5,
                                               minSize=(60, 60))
        if len(faces) == 0:
            return None
        return tuple(int(v) for v in max(faces, key=lambda b: b[2] * b[3]))
    except Exception:
        return None

def _ling_filter(img):
    """LING - the anime guy from the user's picture: black swept hair
    with a side part, round thin glasses, pale smooth anime skin.
    Drawn over the face (tracked by face detection when available,
    centred on the facecam otherwise). This is a drawn character
    look, not a face-swap - the face underneath is still yours."""
    out = apply_character_filter(img, "Anime")
    h, w = out.shape[:2]
    box = _detect_face_box(img)
    if box is None:
        # No face found (e.g. head tilted or turned away): do NOT
        # guess where the hair and glasses go - a guessed overlay
        # lands on the wrong place and looks like a black block.
        # Just return the anime style; sit straight and face the
        # camera and the hair + glasses appear.
        return out
    fx, fy, fw, fh = box
    # Pale, smooth anime skin on the face area
    try:
        face = out[fy:fy + fh, fx:fx + fw]
        smooth = cv2.bilateralFilter(face, 9, 60, 60)
        out[fy:fy + fh, fx:fx + fw] = cv2.convertScaleAbs(
            smooth, alpha=1.05, beta=10)
    except Exception:
        pass
    hair = (18, 18, 22)      # near-black, like his hair
    hi = (70, 70, 80)        # hair highlight
    # Black swept fringe: top of the head down to just above the
    # eyebrows, with a jagged strand edge and a side part.
    top = max(0, fy - int(fh * 0.18))
    pts = np.array([
        (fx - int(fw * 0.04), fy + int(fh * 0.26)),
        (fx - int(fw * 0.03), top + int(fh * 0.08)),
        (fx + int(fw * 0.25), top),
        (fx + int(fw * 0.60), top),
        (fx + int(fw * 0.95), top + int(fh * 0.05)),
        (fx + fw + int(fw * 0.03), fy + int(fh * 0.24)),
        (fx + fw, fy + int(fh * 0.36)),
        (fx + int(fw * 0.82), fy + int(fh * 0.24)),
        (fx + int(fw * 0.74), fy + int(fh * 0.36)),
        (fx + int(fw * 0.58), fy + int(fh * 0.22)),
        (fx + int(fw * 0.46), fy + int(fh * 0.38)),
        (fx + int(fw * 0.30), fy + int(fh * 0.24)),
        (fx + int(fw * 0.16), fy + int(fh * 0.36)),
    ], dtype=np.int32)
    cv2.fillPoly(out, [pts], hair)
    # A few loose strands falling over the forehead
    for sx, sl in [(0.30, 0.42), (0.52, 0.45), (0.72, 0.40)]:
        x0 = fx + int(fw * sx)
        cv2.line(out, (x0, fy + int(fh * 0.22)),
                 (x0 + int(fw * 0.03), fy + int(fh * sl)), hair, 4)
    cv2.line(out, (fx + int(fw * 0.25), top + int(fh * 0.05)),
             (fx + int(fw * 0.45), top + int(fh * 0.02)), hi, 3)
    # His round thin glasses
    ey = fy + int(fh * 0.46)
    lx, rx = fx + int(fw * 0.30), fx + int(fw * 0.70)
    r = int(fw * 0.11)
    frame_col = (45, 45, 45)
    for cx in (lx, rx):
        cv2.circle(out, (cx, ey), r, frame_col, 3)
    cv2.line(out, (lx + r, ey - int(r * 0.25)),
             (rx - r, ey - int(r * 0.25)), frame_col, 3)
    cv2.line(out, (lx - r, ey), (fx - int(fw * 0.02), ey), frame_col, 2)
    cv2.line(out, (rx + r, ey), (fx + fw + int(fw * 0.02), ey),
             frame_col, 2)
    return out

def apply_character_filter(img, name):
    """Apply one character/style filter to a BGR image. Returns the
    same shape/dtype, or the original image on any failure."""
    if img is None or not name or name == "None":
        return img
    if name == "LING":
        try:
            return _ling_filter(img)
        except Exception:
            return img
    try:
        if name == "B&W":
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
        if name == "Sepia":
            m = np.array([[0.272, 0.534, 0.131],
                          [0.349, 0.686, 0.168],
                          [0.393, 0.769, 0.189]], dtype=np.float32)
            return np.clip(cv2.transform(img, m), 0, 255).astype(np.uint8)
        if name == "Warm":
            b, g, r = cv2.split(img.astype(np.float32))
            return cv2.merge([np.clip(b * 0.88, 0, 255), g, np.clip(r * 1.12, 0, 255)]).astype(np.uint8)
        if name == "Cool":
            b, g, r = cv2.split(img.astype(np.float32))
            return cv2.merge([np.clip(b * 1.12, 0, 255), g, np.clip(r * 0.88, 0, 255)]).astype(np.uint8)
        if name.startswith("Smooth"):
            return cv2.bilateralFilter(img, 5, 40, 40)
        if name == "Cartoon":
            smooth = cv2.bilateralFilter(img, 9, 75, 75)
            return cv2.bitwise_and(smooth, _edges_bgr(img))
        if name == "Anime":
            # Cleaner anime look: OpenCV stylization (painterly, flat
            # colours) + soft dark outlines. Falls back to the old
            # posterize method if stylization is not available.
            try:
                out = cv2.stylization(img, sigma_s=60, sigma_r=0.45)
                out = cv2.bilateralFilter(out, 5, 50, 50)
                return cv2.bitwise_and(out, _edges_bgr(img, block=9, c=9))
            except Exception:
                smooth = cv2.bilateralFilter(_posterize(img, 4), 9, 75, 75)
                smooth = _boost_saturation(smooth, 1.4)
                return cv2.bitwise_and(smooth, _edges_bgr(img, block=9, c=5))
        if name == "Comic":
            smooth = _boost_saturation(_posterize(img, 5), 1.6)
            return cv2.bitwise_and(smooth, _edges_bgr(img))
        if name == "Sketch":
            try:
                gray_sketch, _color_sketch = cv2.pencilSketch(img)
                return cv2.cvtColor(gray_sketch, cv2.COLOR_GRAY2BGR)
            except Exception:
                g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                inv = 255 - g
                blur = cv2.GaussianBlur(inv, (21, 21), 0)
                sketch = cv2.divide(g, 255 - blur, scale=256)
                return cv2.cvtColor(sketch, cv2.COLOR_GRAY2BGR)
        if name == "Vintage":
            # Warm old-photo look: sepia + darkened corners.
            m = np.array([[0.272, 0.534, 0.131],
                          [0.349, 0.686, 0.168],
                          [0.393, 0.769, 0.189]], dtype=np.float32)
            out = np.clip(cv2.transform(img, m), 0, 255).astype(np.uint8)
            h, w = out.shape[:2]
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            dist = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 +
                           ((yy - h / 2) / (h / 2)) ** 2)
            vig = np.clip(1.0 - 0.45 * np.clip(dist - 0.55, 0, 1) ** 2, 0, 1)
            return (out.astype(np.float32) * vig[..., None]).astype(np.uint8)
        if name == "Vivid":
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[..., 1] = np.clip(hsv[..., 1] * 1.5, 0, 255)
            out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
            return cv2.convertScaleAbs(out, alpha=1.12, beta=0)
        if name == "Noir":
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            g = cv2.convertScaleAbs(g, alpha=1.35, beta=-12)
            return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
        if name == "TealOrange":
            # Cinematic teal & orange: shadows go teal, skin and
            # highlights go warm orange. (The editor can also load a
            # real .cube LUT for this look.)
            f = img.astype(np.float32) / 255.0
            lum = f.mean(axis=2, keepdims=True)
            shadow = np.clip(1.0 - lum * 2.0, 0, 1)
            high = np.clip(lum * 2.0 - 1.0, 0, 1)
            out = f.copy()
            out[..., 0] = np.clip(f[..., 0] + 0.10 * shadow + 0.02 * high, 0, 1)
            out[..., 1] = np.clip(f[..., 1] - 0.03 * shadow + 0.02 * high, 0, 1)
            out[..., 2] = np.clip(f[..., 2] - 0.06 * shadow + 0.12 * high, 0, 1)
            return (out * 255).astype(np.uint8)
        if name == "LUT":
            # A .cube look is applied by the editor (it holds the LUT
            # data); here it is a no-op so the facecam never breaks.
            return img
        if name == "Pixel":
            h, w = img.shape[:2]
            sw, sh = max(8, w // 14), max(8, h // 14)
            small = cv2.resize(img, (sw, sh), interpolation=cv2.INTER_LINEAR)
            return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
        if name == "Robot":
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
            out = cv2.merge([np.clip(g * 0.6, 0, 255), np.clip(g * 1.0, 0, 255), np.clip(g * 0.6, 0, 255)]).astype(np.uint8)
            out[::4, :, :] = (out[::4, :, :].astype(np.float32) * 0.65).astype(np.uint8)
            return out
        if name == "Alien":
            f = img.astype(np.float32)
            out = cv2.merge([np.clip(f[:, :, 0] * 0.75, 0, 255),
                             np.clip(f[:, :, 1] * 1.25, 0, 255),
                             np.clip(f[:, :, 2] * 0.75, 0, 255)]).astype(np.uint8)
            return _boost_saturation(out, 1.3)
        if name == "Vampire":
            f = img.astype(np.float32)
            out = cv2.merge([np.clip(f[:, :, 0] * 0.95, 0, 255),
                             np.clip(f[:, :, 1] * 0.82, 0, 255),
                             np.clip(f[:, :, 2] * 1.12, 0, 255)]).astype(np.uint8)
            out = cv2.convertScaleAbs(out, alpha=1.15, beta=12)
            return _boost_saturation(out, 0.55)
        if name == "Neon":
            out = _boost_saturation(img, 1.9)
            out = cv2.convertScaleAbs(out, alpha=1.1, beta=8)
            try:
                edges = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 80, 180)
                out[edges > 0] = (255, 255, 0)
            except Exception:
                pass
            return out
        if name == "Hero":
            out = cv2.convertScaleAbs(img, alpha=1.25, beta=6)
            out = _boost_saturation(out, 1.5)
            b, g, r = cv2.split(out.astype(np.float32))
            return cv2.merge([np.clip(b * 0.9, 0, 255), g, np.clip(r * 1.12, 0, 255)]).astype(np.uint8)
    except Exception:
        return img
    return img



# --------------------------------------------------------------------------- smart script record (v2.3)
# You paste your script. While you speak, the app listens to your mic,
# turns your speech into text, and checks it against the script.
# If you say a word wrong - e.g. script says "welcome" and you say
# "elcom" - it is flagged as a mistake, live and in a report after.
# It does NOT change your recorded voice (that is impossible to fix
# cleanly). What it DOES auto-correct is the captions / subtitles:
# with "Auto-correct captions" on, the .srt shows the correct script
# word instead of the misspoken one.
import difflib
import re as _re

def _norm_words(text):
    return _re.findall(r"[a-z0-9']+", (text or "").lower())

def _fmt_srt_time(sec):
    sec = max(0.0, float(sec))
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

def compare_script(script_text, heard_text):
    """Compare what you said to the script. Returns a dict with
    accuracy, mistakes, corrected text, and per-line retakes."""
    expected = _norm_words(script_text)
    heard = _norm_words(heard_text)
    if not expected:
        return {"accuracy": 0.0, "mistakes": [], "corrected_text": heard_text or "",
                "heard_text": heard_text or "", "expected_words": [], "heard_words": heard,
                "retake_lines": [], "total": 0, "correct": 0}
    sm = difflib.SequenceMatcher(a=expected, b=heard, autojunk=False)
    mistakes = []
    corrected = []
    correct = 0
    heard_idx = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            correct += (i2 - i1)
            corrected.extend(expected[i1:i2])
        elif tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                exp_w = expected[i1 + k] if i1 + k < i2 else None
                heard_w = heard[j1 + k] if j1 + k < j2 else None
                if exp_w:
                    mistakes.append({"expected": exp_w, "heard": heard_w or "(missed)",
                                     "position": i1 + k + 1})
                    corrected.append(exp_w)
                elif heard_w:
                    corrected.append(heard_w)
        elif tag == "delete":
            for k in range(i1, i2):
                mistakes.append({"expected": expected[k], "heard": "(missed)", "position": k + 1})
                corrected.append(expected[k])
        elif tag == "insert":
            corrected.extend(heard[j1:j2])
    accuracy = (correct / len(expected) * 100.0) if expected else 0.0
    # retake lines: script lines where that line's words were mostly wrong
    retake_lines = []
    lines = [ln.strip() for ln in (script_text or "").splitlines() if ln.strip()]
    if len(lines) > 1:
        heard_set = set(heard)
        for ln in lines:
            lw = _norm_words(ln)
            if lw:
                hit = sum(1 for w in lw if w in heard_set)
                if hit / len(lw) < 0.6:
                    retake_lines.append(ln)
    return {"accuracy": accuracy, "mistakes": mistakes, "corrected_text": " ".join(corrected),
            "heard_text": heard_text or "", "expected_words": expected, "heard_words": heard,
            "retake_lines": retake_lines, "total": len(expected), "correct": correct}

def segments_to_srt(segments, corrected_text_by_segment=None):
    """segments: [{start, end, text}] -> SRT string. If corrected text
    is given per segment, use that (auto-correct captions)."""
    out = []
    for i, seg in enumerate(segments, 1):
        text = seg.get("text", "").strip()
        if corrected_text_by_segment is not None and i - 1 < len(corrected_text_by_segment):
            text = corrected_text_by_segment[i - 1] or text
        if not text:
            continue
        out.append(f"{i}\n{_fmt_srt_time(seg.get('start', 0))} --> {_fmt_srt_time(seg.get('end', 0))}\n{text}\n")
    return "\n".join(out)

_WHISPER_MODEL = None
_WHISPER_TRIED = False

def get_whisper_model():
    """Load faster-whisper tiny.en once (offline, CPU). Returns None
    if faster-whisper is not installed - caller falls back to Google."""
    global _WHISPER_MODEL, _WHISPER_TRIED
    if _WHISPER_MODEL is not None:
        return _WHISPER_MODEL
    if _WHISPER_TRIED:
        return None
    _WHISPER_TRIED = True
    try:
        from faster_whisper import WhisperModel
        _WHISPER_MODEL = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        return _WHISPER_MODEL
    except Exception as e:
        log_error(f"whisper load: {e}")
        return None

def transcribe_wav(wav_path, model=None):
    """Turn a mic WAV into [{start, end, text}]. Returns
    (segments, engine_name, error_or_None). Tries faster-whisper
    (offline) first, then Google Web Speech (online, no key)."""
    if not wav_path or not os.path.exists(str(wav_path)):
        return ([], "", "No mic audio file to check.")
    # 1) faster-whisper (offline, with timestamps)
    try:
        m = model if model is not None else get_whisper_model()
        if m is not None:
            segs, _info = m.transcribe(str(wav_path), beam_size=1, language="en",
                                       vad_filter=True, vad_parameters={"min_silence_duration_ms": 500})
            out = [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
                   for s in segs if s.text.strip()]
            return (out, "faster-whisper (offline)", None)
    except Exception as e:
        log_error(f"whisper transcribe: {e}")
    # 2) Google Web Speech via SpeechRecognition (online, no timestamps)
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes(); rate = wf.getframerate()
            dur = frames / rate if rate else 0
        segments = []
        chunk = 25.0
        t = 0.0
        while t < dur:
            with sr.AudioFile(str(wav_path)) as src:
                audio = r.record(src, offset=t, duration=min(chunk, dur - t))
            try:
                text = r.recognize_google(audio)
            except Exception:
                text = ""
            if text:
                segments.append({"start": t, "end": min(dur, t + chunk), "text": text})
            t += chunk
        if segments:
            return (segments, "Google Web Speech (online)", None)
        return ([], "Google Web Speech (online)", "Speech was not understood - too quiet, or no speech in the mic audio.")
    except ImportError:
        return ([], "", "No speech engine installed. Install it with: pip install -r requirements-smart.txt  (faster-whisper, offline)  -  video still saved.")
    except Exception as e:
        return ([], "", f"Speech check failed: {e}")


# ---------- chapters (Tutorial Maker, v2.4) ----------
# A chapter is {"time": seconds into the VIDEO, "title": str}.
# The recorder saves them as <video>.chapters.json next to the
# recording; the editor loads them, shows them on the timeline,
# and writes a YouTube-style chapters.txt on export.

def format_chapter_time(t):
    """Seconds -> "MM:SS" (or "H:MM:SS" past one hour), the format
    YouTube chapters use."""
    t = max(0, int(round(float(t))))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def chapters_to_text(chapters, ensure_start=True):
    """Chapter list -> YouTube description lines, "MM:SS Title".
    With ensure_start, a missing 00:00 chapter is added as
    "Intro": YouTube only shows chapters when the first one is
    at 00:00."""
    items = sorted(({"time": float(c.get("time", 0.0)),
                     "title": str(c.get("title", "")).strip() or "Chapter"}
                    for c in (chapters or [])),
                   key=lambda c: c["time"])
    if ensure_start and (not items or items[0]["time"] > 0.5):
        items.insert(0, {"time": 0.0, "title": "Intro"})
    return "\n".join(f"{format_chapter_time(c['time'])} {c['title']}"
                     for c in items)


def save_chapters_json(path, chapters, video_name=""):
    """Write the chapters file next to a recording."""
    data = {"version": 1, "video": video_name,
            "chapters": [{"time": round(float(c.get("time", 0.0)), 2),
                          "title": str(c.get("title", ""))}
                         for c in (chapters or [])]}
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_chapters_json(path):
    """Read a .chapters.json file. Returns the chapter list, or []
    when the file is missing or unreadable (never raises)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        raw = data.get("chapters", []) if isinstance(data, dict) else []
        out = []
        for c in raw:
            if isinstance(c, dict) and "time" in c:
                out.append({"time": float(c["time"]),
                            "title": str(c.get("title", "") or "Chapter")})
        return sorted(out, key=lambda c: c["time"])
    except Exception:
        return []

class SmartChecker:
    """Keeps score while you speak: expected script words, what was
    heard so far, mistakes, accuracy, and what to say next."""

    def __init__(self, script_text):
        self.script_text = script_text or ""
        self.expected = _norm_words(self.script_text)
        self.heard_words = []
        self.last_heard = ""
        self.mistakes = []
        self.accuracy = 0.0
        # RLock: summary() calls next_phrase(), which also locks.
        self._lock = threading.RLock()

    def update(self, heard_text):
        if not heard_text:
            return
        with self._lock:
            self.last_heard = heard_text
            self.heard_words.extend(_norm_words(heard_text))
            res = compare_script(self.script_text, " ".join(self.heard_words))
            # Live score is about what you have said SO FAR, not the whole
            # script - words you have not reached yet are not mistakes yet.
            n = len(self.heard_words)
            self.mistakes = [m for m in res["mistakes"] if m["position"] <= n]
            self.accuracy = (res["correct"] / n * 100.0) if n else 0.0

    def next_phrase(self, n=8):
        # first expected word not yet matched = next thing to say
        with self._lock:
            heard = list(self.heard_words)
        if len(heard) >= len(self.expected) and self.expected:
            return "(script finished)"
        # walk expected vs heard in order, find first unmatched expected word
        sm = difflib.SequenceMatcher(a=self.expected, b=heard, autojunk=False)
        matched = set()
        for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
            if tag == "equal":
                matched.update(range(i1, i2))
        for i, w in enumerate(self.expected):
            if i not in matched:
                return " ".join(self.expected[i:i + n])
        return "(script finished)"

    def summary(self):
        with self._lock:
            return (f"Accuracy {self.accuracy:.0f}%  •  {len(self.mistakes)} mistake(s)  •  "
                    f"Next: {self.next_phrase()}")

class SmartListener(threading.Thread):
    """Background thread: takes 5-second mic chunks, transcribes them,
    and feeds the text to the SmartChecker. Best-effort - if a chunk
    takes too long, it is skipped, never blocking the recording."""

    def __init__(self, chunk_queue, checker, stop_evt):
        super().__init__(daemon=True)
        self.chunk_queue = chunk_queue
        self.checker = checker
        self.stop_evt = stop_evt
        self.model = None
        self.engine = ""
        self.failures = 0

    def _transcribe_chunk(self, wav_bytes):
        tmp = None
        try:
            import tempfile
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            with wave.open(tmp, "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(44100)
                wf.writeframes(wav_bytes)
            # faster-whisper if available, else Google per chunk
            if self.model is None and self.engine != "google-tried":
                self.model = get_whisper_model()
            if self.model is not None:
                segs, _ = self.model.transcribe(tmp, beam_size=1, language="en", vad_filter=True)
                return " ".join(s.text.strip() for s in segs if s.text.strip())
            import speech_recognition as sr
            self.engine = "google-tried"
            r = sr.Recognizer()
            with sr.AudioFile(tmp) as src:
                audio = r.record(src)
            try:
                return r.recognize_google(audio) or ""
            except Exception:
                return ""
        except Exception:
            return ""
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    def run(self):
        while not self.stop_evt.is_set():
            try:
                chunk = self.chunk_queue.get(timeout=0.5)
            except Exception:
                continue
            if not chunk:
                continue
            # skip silence (all near-zero) - no point transcribing it
            try:
                import audioop
                if audioop.rms(chunk, 2) < 80:
                    continue
            except Exception:
                pass
            text = self._transcribe_chunk(chunk)
            if text:
                self.failures = 0
                self.checker.update(text)
            else:
                self.failures += 1
                if self.failures >= 5:
                    return  # STT keeps failing - stop quietly, recording goes on


# --------------------------------------------------------------------------- mic recorder
class MicRecorder:
    """Records microphone to a WAV file in a background callback. Very low overhead."""

    def __init__(self, wav_path, samplerate=44100, chunk_queue=None, chunk_seconds=5,
                 stream_to_disk=False, raw=False):
        self.wav_path = str(wav_path)
        self.samplerate = samplerate
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self.chunk_queue = chunk_queue
        self._chunk_buf = bytearray()
        self._chunk_bytes = int(samplerate * 2 * chunk_seconds)
        # Instant Replay: write the sound to disk as it arrives, so the
        # file can be trimmed while the mic is still recording. raw=True
        # writes plain int16 samples (no WAV header) - a WAV header is
        # only finalised when the file is closed, so a live WAV cannot
        # be seeked from the end while recording.
        self.stream_to_disk = stream_to_disk
        self.raw = raw
        self._wf = None
        self._disk_bytes = 0
        # Lip-sync: when the mic stream actually starts, in the same
        # clock the video writer uses. The recorder compares this with
        # the video's first frame time and shifts the audio to match,
        # so the voice no longer lags the mouth by a second.
        self.start_perf = None

    def _callback(self, indata, frames, time_info, status):
        data = bytes(indata)
        with self._lock:
            if self.stream_to_disk and self._wf is not None:
                try:
                    self._wf.writeframes(data) if not self.raw else self._wf.write(data)
                    self._disk_bytes += len(data)
                except Exception:
                    pass
            else:
                self._frames.append(data)
            if self.chunk_queue is not None:
                self._chunk_buf.extend(data)
                if len(self._chunk_buf) >= self._chunk_bytes:
                    try:
                        self.chunk_queue.put_nowait(bytes(self._chunk_buf))
                    except Exception:
                        pass  # queue full - drop this chunk, never block the mic
                    self._chunk_buf = bytearray()

    def start(self):
        if not HAS_MIC:
            return False
        if self.stream_to_disk:
            try:
                if self.raw:
                    self._wf = open(self.wav_path, "wb")
                else:
                    self._wf = wave.open(self.wav_path, "wb")
                    self._wf.setnchannels(1)
                    self._wf.setsampwidth(2)
                    self._wf.setframerate(self.samplerate)
            except Exception:
                self._wf = None
                return False
        try:
            self._stream = sd.RawInputStream(
                samplerate=self.samplerate, channels=1, dtype="int16",
                callback=self._callback,
            )
            self._stream.start()
            self.start_perf = time.perf_counter()
            return True
        except Exception:
            self._stream = None
            return False

    def stop(self):
        if self._stream:
            try:
                self._stream.stop(); self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self.stream_to_disk:
            if self._wf is not None:
                try:
                    self._wf.close()
                except Exception:
                    pass
                self._wf = None
            return self._disk_bytes > 1024
        if self._frames:
            try:
                with wave.open(self.wav_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # int16
                    wf.setframerate(self.samplerate)
                    with self._lock:
                        wf.writeframes(b"".join(self._frames))
                return True
            except Exception:
                return False
        return False




# --------------------------------------------------------------------------- system audio (v2.1)
# Game / system sound is NOT the mic. It is what the PC itself is playing.
# There is no single cross-platform way to grab it, so we use FFmpeg with
# each OS's own loopback / monitor source, and fail gracefully if that
# source does not exist on this PC (recording still works, mic still works).
def find_ffmpeg():
    """Find FFmpeg. Checks the app's own folder FIRST (the installer
    puts ffmpeg.exe next to the app, so sound works even when the user
    never installed FFmpeg), then the system PATH.

    Without FFmpeg the mic audio is never merged into the video and
    game sound cannot be captured at all — so a missing FFmpeg used to
    mean a silent video with no clear warning. This is why the
    installer now downloads it."""
    cands = []
    try:
        exe_dir = Path(sys.executable).parent
        cands += [exe_dir / "ffmpeg.exe", exe_dir / "ffmpeg"]
    except Exception:
        pass
    try:
        app_dir = Path(__file__).resolve().parent
        cands += [app_dir / "ffmpeg.exe", app_dir / "ffmpeg",
                  app_dir / "ffmpeg" / "ffmpeg.exe", app_dir / "ffmpeg" / "ffmpeg"]
    except Exception:
        pass
    for c in cands:
        try:
            if c.is_file() and os.access(str(c), os.X_OK):
                return str(c)
        except Exception:
            pass
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if found:
        return found
    for cand in ("ffmpeg", "ffmpeg.exe"):
        try:
            subprocess.run([cand, "-version"], capture_output=True, timeout=3,
                           **_quiet_subprocess_kwargs())
            return cand
        except Exception:
            continue
    return None


def system_audio_setup_hint():
    if sys.platform == "win32":
        return ("Windows: enable Stereo Mix — right-click the speaker icon > "
                "Sound settings > More sound settings > Recording > "
                "right-click Stereo Mix > Enable. If there is no Stereo Mix, "
                "install the free VB-Cable (vb-audio.com) and set it as your "
                "playback device, then try again.")
    if sys.platform == "darwin":
        return ("Mac: install the free BlackHole audio driver "
                "(existential.audio/blackhole), set it as your output in "
                "System Settings > Sound, then try again. macOS cannot "
                "capture system sound without a virtual device like this.")
    return ("Linux: needs PulseAudio or PipeWire running. On most desktops "
            "it works automatically from the default sink's monitor source. "
            "If it fails, install pulseaudio-utils and check `pactl info`.")

def detect_system_audio(cfg=None):
    """Return (ffmpeg_input_args, source_name, hint_or_None).

    ffmpeg_input_args is e.g. ['-f', 'pulse', '-i', 'alsa_output...monitor'].
    Returns (None, None, hint) when no system-audio source can be found.
    A custom source in cfg['system_audio_source'] is used verbatim.
    """
    cfg = cfg or {}
    custom = str(cfg.get("system_audio_source") or "").strip()
    if custom:
        if sys.platform == "win32":
            return (["-f", "dshow", "-i", f'audio="{custom}"'], custom, None)
        if sys.platform == "darwin":
            return (["-f", "avfoundation", "-i", f":{custom}"], custom, None)
        return (["-f", "pulse", "-i", custom], custom, None)
    ff = find_ffmpeg()
    if not ff:
        return (None, None, "FFmpeg is missing - game sound needs it. Run the installer again (it downloads FFmpeg for you), or install FFmpeg from ffmpeg.org and restart the app.")
    if sys.platform == "win32":
        try:
            r = subprocess.run([ff, "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                               capture_output=True, timeout=5, text=True, errors="ignore",
                               **_quiet_subprocess_kwargs())
            import re as _re
            names = _re.findall(r'"([^"]+)"\s*\(audio\)', r.stderr or "")
            want = ("stereo mix", "what u hear", "loopback", "virtual", "vb-audio", "cable", "voicemeeter", "blackhole")
            for n in names:
                if any(k in n.lower() for k in want):
                    return (["-f", "dshow", "-i", f'audio="{n}"'], n, None)
            if names:
                return (None, None, system_audio_setup_hint() + f" Found audio devices: {', '.join(names[:4])} - none of them is a loopback/mix device.")
        except Exception:
            pass
        return (None, None, system_audio_setup_hint())
    if sys.platform == "darwin":
        try:
            r = subprocess.run([ff, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                               capture_output=True, timeout=5, text=True, errors="ignore",
                               **_quiet_subprocess_kwargs())
            out = (r.stderr or "") + (r.stdout or "")
            lines = [ln.strip() for ln in out.splitlines() if "audio" in ln.lower() or "BlackHole" in ln or "Soundflower" in ln]
            for i, ln in enumerate(lines):
                if any(k in ln for k in ("BlackHole", "Soundflower", "VB-Cable", "Loopback")):
                    import re as _re
                    m = _re.search(r"\[(\d+)\]", ln)
                    idx = m.group(1) if m else str(i)
                    return (["-f", "avfoundation", "-i", f":{idx}"], ln, None)
        except Exception:
            pass
        return (None, None, system_audio_setup_hint())
    # Linux: PulseAudio / PipeWire monitor of the default sink
    try:
        if shutil.which("pactl"):
            r = subprocess.run(["pactl", "get-default-sink"], capture_output=True, timeout=5, text=True)
            sink = (r.stdout or "").strip()
            if sink:
                return (["-f", "pulse", "-i", f"{sink}.monitor"], f"{sink}.monitor", None)
            r2 = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, timeout=5, text=True)
            for ln in (r2.stdout or "").splitlines():
                parts = ln.split()
                if len(parts) >= 2 and parts[1].endswith(".monitor"):
                    return (["-f", "pulse", "-i", parts[1]], parts[1], None)
        if shutil.which("wpctl"):
            return (["-f", "pulse", "-i", "default.monitor"], "default.monitor", None)
    except Exception:
        pass
    return (None, None, system_audio_setup_hint())


class SystemAudioRecorder:
    """Captures system/game sound to a WAV via FFmpeg, in the background.

    Same pattern as the mic: record to a file while you play (zero extra
    work for the game), merge it into the MP4 when you stop. If no
    loopback/monitor source exists on this PC, start() returns False and
    sets .error - recording continues without game sound.
    """

    def __init__(self, wav_path, cfg=None):
        self.wav_path = str(wav_path)
        self.cfg = cfg or {}
        self.proc = None
        self.error = ""
        self.source = ""
        self.start_perf = None

    def start(self):
        args, name, hint = detect_system_audio(self.cfg)
        if not args:
            self.error = hint or "No system-audio source found on this PC."
            return False
        ff = find_ffmpeg()
        if not ff:
            self.error = "FFmpeg is missing - game sound needs it (run the installer again, it downloads FFmpeg)."
            return False
        self.source = name or ""
        cmd = [ff, "-y", "-vn"] + args + ["-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", self.wav_path]
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         **_quiet_subprocess_kwargs())
            # Lip-sync: same clock as the video writer (see MicRecorder).
            self.start_perf = time.perf_counter()
        except Exception as e:
            self.error = str(e)
            return False
        time.sleep(0.5)
        if self.proc.poll() is not None:
            self.error = (f"Could not open system audio ({self.source}). " + system_audio_setup_hint())
            self.proc = None
            return False
        return True

    def stop(self):
        if not self.proc:
            return False
        try:
            try:
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
            except Exception:
                pass
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        try:
            return os.path.exists(self.wav_path) and os.path.getsize(self.wav_path) > 1024
        except Exception:
            return False


# --------------------------------------------------------------------------- live streaming (v2.0)
class LiveStreamer:
    """Streams the composited frames to any RTMP platform via FFmpeg.

    Video only is fed through the pipe (raw BGR frames, already composited
    with facecam / zoom / cursor FX, so viewers see exactly what is recorded).
    Audio is FFmpeg's own platform mic input when live_audio is on, otherwise
    a silent track so platforms that require audio still accept the stream.
    If the audio input fails, we retry video-only instead of failing the stream.
    """

    def __init__(self, cfg, out_w, out_h, fps, on_error=None):
        self.cfg = cfg
        self.out_w = out_w
        self.out_h = out_h
        self.fps = int(fps)
        self.on_error = on_error or (lambda msg: None)
        self.proc = None
        self.failed = False
        self._lock = threading.Lock()

    def _ffmpeg(self):
        return find_ffmpeg()

    def _mic_audio_args(self):
        if sys.platform == "win32":
            # Default Windows mic via DirectShow; device name varies, so this
            # is best-effort - start() retries without it if it fails.
            return ["-f", "dshow", "-i", "audio=@device_pnp_@{0.0.1.00000000}.{00000000-0000-0000-0000-000000000000}"]
        if sys.platform == "darwin":
            return ["-f", "avfoundation", "-i", ":0"]
        return ["-f", "pulse", "-i", "default"]

    def _audio_inputs(self, mode):
        """List of FFmpeg input-arg lists for the live audio, for mode:
        'full' = mic (+ system audio if on), 'mic' = mic only, 'silent' = none.
        Returns [] for silent."""
        if mode == "silent":
            return []
        inputs = []
        mic_on = bool(self.cfg.get("mic", True)) and bool(self.cfg.get("live_audio", True))
        if mode in ("full", "mic") and mic_on:
            inputs.append(self._mic_audio_args())
        if mode == "full" and self.cfg.get("system_audio"):
            args, _name, _hint = detect_system_audio(self.cfg)
            if args:
                inputs.append(args)
        return inputs

    def _start_proc(self, mode="full"):
        ff = self._ffmpeg()
        if not ff:
            raise RuntimeError("FFmpeg is not installed - live streaming needs it (ffmpeg.org).")
        url = (self.cfg.get("live_rtmp_url") or "").strip()
        key = (self.cfg.get("live_stream_key") or "").strip()
        if not url or not key:
            raise RuntimeError("Live is on but the RTMP URL or stream key is missing.")
        dest = url.rstrip("/") + "/" + key
        bitrate = str(self.cfg.get("live_bitrate", "4500k"))
        cmd = [ff, "-y",
               "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{self.out_w}x{self.out_h}", "-r", str(self.fps), "-i", "-"]
        inputs = self._audio_inputs(mode)
        if not inputs:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            audio_map = "1:a"
            filt = None
        elif len(inputs) == 1:
            cmd += inputs[0]
            audio_map = "1:a"
            filt = None
        else:
            for inp in inputs:
                cmd += inp
            filt = "[1:a][2:a]amix=inputs=2:duration=longest:normalize=0[aout]"
            audio_map = "[aout]"
        if filt:
            cmd += ["-filter_complex", filt]
        cmd += ["-map", "0:v", "-map", audio_map,
                "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
                "-pix_fmt", "yuv420p", "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", bitrate,
                "-g", str(self.fps * 2),
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                "-f", "flv", dest]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     **_quiet_subprocess_kwargs())
        return self.proc

    def start(self):
        # Try full audio (mic + game sound if on), then mic only, then
        # silent - instead of refusing to go live because one audio
        # device failed. A bad RTMP URL/key fails every attempt, so we
        # only raise after the last one.
        last_err = None
        for mode in ("full", "mic", "silent"):
            try:
                self._start_proc(mode=mode)
            except Exception as e:
                last_err = e
                continue
            time.sleep(0.4)
            if self.proc and self.proc.poll() is None:
                return True
            try:
                if self.proc:
                    self.proc.kill()
            except Exception:
                pass
            self.proc = None
        raise RuntimeError("FFmpeg could not connect - check the RTMP URL and stream key, then try again.")

    def write_frame(self, frame):
        if self.failed or not self.proc or not self.proc.stdin:
            return
        try:
            with self._lock:
                self.proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError):
            self.failed = True
            try:
                self.on_error("Live stream disconnected (FFmpeg pipe broke). Recording continued.")
            except Exception:
                pass
        except Exception:
            pass

    def stop(self):
        if not self.proc:
            return
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None


# --------------------------------------------------------------------------- core recorder
def _trim_audio_tail(src, dur, out, samplerate=44100, channels=1, raw=False):
    """Cut the last `dur` seconds off an audio file that may still be
    being written (mic / game sound during Instant Replay). Reads the
    tail bytes directly and writes a fresh WAV with a correct header,
    so nothing has to seek inside a half-written file.
    Returns out, or None when there is too little sound."""
    try:
        with open(src, "rb") as f:
            data = f.read()
    except Exception:
        return None
    header = 0
    if not raw and data[:4] == b"RIFF":
        header = 44
    frame_bytes = 2 * channels
    body = data[header:]
    want = int(dur * samplerate * frame_bytes)
    tail = body[-want:] if want > 0 else b""
    tail = tail[:len(tail) - (len(tail) % frame_bytes)]
    if len(tail) < samplerate * frame_bytes // 4:  # under 0.25 s - not worth it
        return None
    try:
        with wave.open(out, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes(tail)
        return out
    except Exception:
        return None


class ReplayBuffer:
    """Instant Replay (ShadowPlay / OBS Replay Buffer): records the
    screen into short segment files in the background and keeps only
    the last N seconds. Save on demand - you never miss a moment you
    didn't think to record.

    Video: 5 s segments (mp4v, same size/fps as a recording).
    Audio: the mic and game-sound files are written continuously and
    trimmed to the same last N seconds on save.
    This is a separate mode from normal recording - it never touches
    a recording in progress."""

    SEG_SECONDS = 5

    def __init__(self, cfg, get_frame, out_dir, seconds=60):
        self.cfg = cfg
        self._get_frame = get_frame
        self.out_dir = Path(out_dir)
        self.seconds = max(10, int(seconds))
        self.keep = max(2, int(math.ceil(self.seconds / self.SEG_SECONDS)))
        self.buf_dir = self.out_dir / "replay_buffer"
        self._stop_evt = threading.Event()
        self._thread = None
        self._writer = None
        self._wlock = threading.Lock()
        self._seg_start = 0.0
        self._seg_idx = 0
        self._seg_files = []
        self._lock = threading.Lock()
        self._fps = int(cfg.get("fps", 30))
        self._size = (0, 0)
        self._mic = None
        self._mic_wav = None
        self._sys = None
        self._sys_wav = None
        self.started_at = 0.0

    def start(self, size):
        self._size = size
        try:
            self.buf_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return False
        self.started_at = time.time()
        if self.cfg.get("mic") and HAS_MIC:
            self._mic_wav = str(self.buf_dir / "replay.mic.pcm")
            self._mic = MicRecorder(self._mic_wav, stream_to_disk=True, raw=True)
            self._mic.start()
        if self.cfg.get("system_audio"):
            self._sys_wav = str(self.buf_dir / "replay.sys.wav")
            self._sys = SystemAudioRecorder(self._sys_wav, self.cfg)
            self._sys.start()
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def _open_segment(self):
        with self._wlock:
            self._close_segment_locked()
            path = str(self.buf_dir / ("seg_%05d.mp4" % self._seg_idx))
            self._seg_idx += 1
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            w = cv2.VideoWriter(path, fourcc, self._fps, self._size)
            if w.isOpened():
                self._writer = w
                self._seg_start = time.time()
                with self._lock:
                    self._seg_files.append(path)
                    while len(self._seg_files) > self.keep:
                        old = self._seg_files.pop(0)
                        try:
                            os.remove(old)
                        except OSError:
                            pass
            else:
                w.release()
                self._writer = None

    def _close_segment_locked(self):
        if self._writer is not None:
            try:
                self._writer.release()
            except Exception:
                pass
            self._writer = None

    def _close_segment(self):
        with self._wlock:
            self._close_segment_locked()

    def _loop(self):
        # Wall-clock writer, like the recording writer: one frame per
        # 1/fps of real time, so the replay plays at real speed.
        interval = 1.0 / self._fps
        next_t = time.perf_counter()
        last_id = -1
        self._open_segment()
        while not self._stop_evt.is_set():
            now = time.perf_counter()
            if now < next_t:
                time.sleep(min(next_t - now, 0.02))
                continue
            next_t = now + interval
            if time.time() - self._seg_start >= self.SEG_SECONDS:
                self._open_segment()
            frame, fid = self._get_frame()
            if frame is None or fid == last_id:
                continue
            last_id = fid
            with self._wlock:
                if self._writer is not None:
                    try:
                        self._writer.write(frame)
                    except Exception:
                        pass

    def buffered_seconds(self):
        with self._lock:
            n = len(self._seg_files)
        if n == 0:
            return 0.0
        # Completed segments (5 s each) + the one still being written.
        partial = max(0.0, time.time() - self._seg_start)
        return min(self.seconds, (n - 1) * self.SEG_SECONDS + partial)

    def stop(self):
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        self._close_segment()
        if self._mic is not None:
            try:
                self._mic.stop()
            except Exception:
                pass
            self._mic = None
        if self._sys is not None:
            try:
                self._sys.stop()
            except Exception:
                pass
            self._sys = None

    def save(self, out_path):
        """Save the buffered seconds to out_path. Returns (ok, note)."""
        self._close_segment()  # flush the current segment so it is complete
        with self._lock:
            segs = list(self._seg_files)
        segs = [s for s in segs if os.path.exists(s) and os.path.getsize(s) > 1024]
        if not segs:
            return False, "Replay buffer is empty - wait a few seconds after turning it on."
        ff = find_ffmpeg()
        if not ff:
            return False, "Replay save needs FFmpeg (it joins the clips)."
        list_path = str(self.buf_dir / "concat.txt")
        try:
            with open(list_path, "w") as f:
                for s in segs:
                    f.write("file '%s'\n" % s.replace("'", "'\\''"))
        except Exception as exc:
            return False, "Could not save the replay: %s" % exc
        tmp_video = str(Path(out_path).with_suffix("")) + "_replay_video.mp4"
        r = subprocess.run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0",
                            "-i", list_path, "-c", "copy", tmp_video],
                           capture_output=True, timeout=300)
        if r.returncode != 0 or not os.path.exists(tmp_video):
            return False, "Could not join the replay clips."
        dur = 0.0
        try:
            cap = cv2.VideoCapture(tmp_video)
            n = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            fps = cap.get(cv2.CAP_PROP_FPS) or self._fps
            cap.release()
            dur = n / fps if fps else 0.0
        except Exception:
            pass
        if dur <= 0:
            dur = len(segs) * self.SEG_SECONDS
        # Audio: the last `dur` seconds of each live file, mixed.
        mic_cut = None
        sys_cut = None
        if self._mic_wav:
            mic_cut = _trim_audio_tail(self._mic_wav, dur,
                                       str(self.buf_dir / "replay.mic.cut.wav"),
                                       44100, 1, raw=True)
        if self._sys_wav:
            sys_cut = _trim_audio_tail(self._sys_wav, dur,
                                       str(self.buf_dir / "replay.sys.cut.wav"),
                                       44100, 2, raw=False)
        inputs, filters, maps = [], [], []
        idx = 1
        for cut in (mic_cut, sys_cut):
            if cut:
                inputs += ["-i", cut]
                filters.append("[%d:a]anull[a%d]" % (idx, idx))
                maps.append("[a%d]" % idx)
                idx += 1
        if maps:
            if len(maps) == 1:
                mixed = maps[0]
            else:
                filters.append("".join(maps) + "amix=inputs=2:normalize=0[aout]")
                mixed = "[aout]"
            cmd = [ff, "-y", "-v", "error", "-i", tmp_video] + inputs + [
                "-filter_complex", ";".join(filters), "-map", "0:v", "-map", mixed,
                "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path)]
            r = subprocess.run(cmd, capture_output=True, timeout=300)
            if r.returncode == 0 and os.path.exists(out_path):
                try:
                    os.remove(tmp_video)
                except OSError:
                    pass
                self._open_segment()  # keep buffering after the save
                return True, "Saved the last %.0f s as %s" % (dur, Path(out_path).name)
        try:
            shutil.move(tmp_video, str(out_path))
        except Exception as exc:
            return False, "Could not save the replay: %s" % exc
        self._open_segment()
        return True, "Saved the last %.0f s as %s (no audio captured)" % (dur, Path(out_path).name)


class Recorder:
    def __init__(self, cfg, on_status=None):
        self.cfg = cfg
        self.on_status = on_status or (lambda **kw: None)
        self.recording = False
        self.paused = False
        self._stop_evt = threading.Event()
        self._capture_thread = None
        self._writer_thread = None
        self._cam_thread = None
        self._latest_cam = None
        self._cam_lock = threading.Lock()
        self.dropped = 0
        self.written = 0
        self.start_time = 0.0
        self.paused_total = 0.0
        self._pause_started = None
        # Lip-sync (v2.3 fix): the mic and game sound used to start
        # up to a second BEFORE the video's first frame (webcam open
        # + system-audio/live startup), so the voice landed ~1 s after
        # the mouth moved. These perf_counter stamps let _mux_audio
        # shift the audio back onto the video. Pauses are tracked too:
        # the mic keeps recording while paused, the video does not,
        # so paused parts are cut out of the audio.
        self._video_t0 = None
        self._mic_t0 = None
        self._sys_t0 = None
        self._stop_perf = None
        self._pause_intervals = []
        # Live voice switching: (perf_counter, voice) each time the
        # user changes the voice while recording.
        self._voice_changes = []
        self._voice_start = "Off"
        self.output_path = None
        self.preview_frame = None  # latest composited frame (for small UI preview)
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._frame_id = 0
        self.captured = 0
        self._behind_mode = False
        self._active_seconds = 0.0
        self._mask_cache = {}
        self._mic = None
        self._mic_wav = None
        self.mic_active = False
        self._sys = None
        self._sys_wav = None
        self.sys_active = False
        self.sys_error = ""
        self.sys_source = ""
        self.streamer = None
        self.live_error = ""
        self.replay = None  # Instant Replay buffer (None when off)
        self._replay_cap = None
        self.smart_checker = None
        self._smart_queue = None
        self._smart_listener = None
        self._smart_stop_evt = None
        self.smart_result = None
        self.smart_report_path = None
        self.smart_srt_path = None
        # v2.4 - tutorial chapters: [{"time": video seconds, "title": str}]
        self.chapters = []
        self._chapter_lock = threading.Lock()
        # v1.4: mouse/keyboard tracking + click-zoom state
        self._mouse_listener = None
        self._kb_listener = None
        self._mouse_ctrl = None
        self._pending_clicks = []
        self._track_lock = threading.Lock()
        self._mods_down = set()
        self._prev_btn = False
        self._keystroke = None
        self._ripple = None
        self._zoom_level = 1.0
        self._zoom_target = 1.0
        self._zoom_cx = 0.0
        self._zoom_cy = 0.0
        self._zoom_tx = 0.0
        self._zoom_ty = 0.0
        self._zoom_hold_until = 0.0
        self._monitor = None
        self._src_off = (0, 0)
        self._src_size = (0, 0)

    # ---- webcam thread: always keep only latest frame
    def _cam_loop(self, cap):
        while not self._stop_evt.is_set():
            ok, frame = cap.read()
            if ok:
                with self._cam_lock:
                    self._latest_cam = frame
            else:
                time.sleep(0.02)

    def _get_cam_frame(self):
        with self._cam_lock:
            return None if self._latest_cam is None else self._latest_cam.copy()

    # ---- facecam overlay with shape / border
    def _overlay(self, screen, cam, out_w, out_h):
        if cam is None:
            return screen
        size_pct = int(self.cfg["facecam_size"])
        cam_w = max(120, int(out_w * size_pct / 100))
        cam_h = int(cam_w * cam.shape[0] / cam.shape[1])
        cam_small = cv2.resize(cam, (cam_w, cam_h), interpolation=cv2.INTER_LINEAR)

        shape = self.cfg["facecam_shape"]
        if shape in ("Rounded", "Circle"):
            if shape == "Circle":
                s = min(cam_w, cam_h)
                cam_small = cv2.resize(cam, (s, s), interpolation=cv2.INTER_LINEAR)
                cam_w = cam_h = s
            # Mask/border are identical every frame for a given size - build once, cache it.
            # (Rebuilding them per frame was wasted CPU on a light laptop.)
            key = (cam_w, cam_h, shape)
            cached = self._mask_cache.get(key)
            if cached is None:
                mask = np.zeros((cam_h, cam_w), dtype=np.uint8)
                if shape == "Circle":
                    cv2.circle(mask, (cam_w // 2, cam_h // 2), cam_w // 2, 255, -1)
                else:
                    r = 18
                    cv2.rectangle(mask, (r, 0), (cam_w - r, cam_h), 255, -1)
                    cv2.rectangle(mask, (0, r), (cam_w, cam_h - r), 255, -1)
                    for cx, cy in [(r, r), (cam_w - r, r), (r, cam_h - r), (cam_w - r, cam_h - r)]:
                        cv2.circle(mask, (cx, cy), r, 255, -1)
                edge = cv2.dilate(mask, np.ones((7, 7), np.uint8))
                cached = (mask, edge)
                self._mask_cache = {key: cached}
            mask, edge = cached
            # composite cam, then white edge ring
            bg = screen  # placeholder, real composite below using positions
            # We'll composite in the caller section below by returning prepared pieces
            return (cam_small, mask, edge, cam_w, cam_h)
        return (cam_small, None, None, cam_w, cam_h)

    def _apply_filter(self, img):
        """Facecam character filter. Works on the small facecam image only,
        so it stays cheap and never changes your game colours. The filter
        is NEVER applied to the whole video / game.
        Anime / LING use stylization, which is heavy (~70 ms), so they
        are recomputed only every 3rd frame and reused in between -
        the face moves slowly, and the game keeps running at full speed."""
        name = self.cfg.get("video_filter", "None")
        if name in ("Anime", "LING"):
            # Light mode reuses the filtered face for 5 frames instead
            # of 3 - the face moves slowly, the CPU saving is real.
            stride = 5 if self.cfg.get("light_mode", True) else 3
            self._anime_n = getattr(self, "_anime_n", 0) + 1
            last = getattr(self, "_anime_last", None)
            if self._anime_n % stride != 1 and last is not None and last.shape == img.shape:
                return last
            out = apply_character_filter(img, name)
            self._anime_last = out
            return out
        return apply_character_filter(img, name)

    def _composite(self, screen, cam, out_w, out_h):
        result = self._overlay(screen, cam, out_w, out_h)
        if isinstance(result, np.ndarray):
            return result
        cam_small, mask, edge, cam_w, cam_h = result
        cam_small = self._apply_filter(cam_small)
        margin = 16
        pos = self.cfg["facecam_pos"]
        x = out_w - cam_w - margin if "Right" in pos else margin
        y = out_h - cam_h - margin if "Bottom" in pos else margin
        x = max(0, min(x, out_w - cam_w)); y = max(0, min(y, out_h - cam_h))
        roi = screen[y:y + cam_h, x:x + cam_w]
        if mask is None:
            # rectangle with simple border
            cv2.rectangle(screen, (x - 2, y - 2), (x + cam_w + 2, y + cam_h + 2), (255, 255, 255), 2)
            screen[y:y + cam_h, x:x + cam_w] = cam_small
        else:
            # white border ring
            roi[edge == 255] = (255, 255, 255)
            roi[mask == 255] = cam_small[mask == 255]
            screen[y:y + cam_h, x:x + cam_w] = roi
        return screen

    # ---- frame producer: capture as fast as this PC can, keep only the latest frame
    # ---- v1.4 mouse / keyboard tracking (near-zero CPU: OS listeners, no polling loop)
    def _init_trackers(self):
        need_mouse = bool(self.cfg.get("click_zoom") or self.cfg.get("mouse_fx"))
        if not (need_mouse or self.cfg.get("keystrokes")):
            return
        try:
            from pynput import mouse as _m, keyboard as _k
            if need_mouse:
                def on_click(x, y, button, pressed):
                    if pressed:
                        with self._track_lock:
                            self._pending_clicks.append((int(x), int(y)))
                self._mouse_listener = _m.Listener(on_click=on_click)
                self._mouse_listener.start()
                self._mouse_ctrl = _m.Controller()
            if self.cfg.get("keystrokes"):
                mods_map = {}
                for key, name in [(_k.Key.ctrl_l, "Ctrl"), (_k.Key.ctrl_r, "Ctrl"),
                                  (_k.Key.alt_l, "Alt"), (_k.Key.alt_r, "Alt"),
                                  (_k.Key.shift, "Shift"), (_k.Key.shift_l, "Shift"), (_k.Key.shift_r, "Shift"),
                                  (_k.Key.cmd, "Win"), (_k.Key.cmd_l, "Win"), (_k.Key.cmd_r, "Win")]:
                    mods_map[key] = name
                def on_press(key):
                    try:
                        name = mods_map.get(key)
                        if name:
                            self._mods_down.add(name)
                            return
                        # ONLY shortcut combos are ever shown - never plain typing (password safety)
                        if self._mods_down:
                            if isinstance(key, _k.KeyCode) and key.char:
                                kname = key.char.upper()
                            else:
                                kname = str(key).replace("Key.", "").replace("_", " ").title()
                            combo = " + ".join(sorted(self._mods_down) + [kname])
                            self._keystroke = (combo, time.time())
                    except Exception:
                        pass
                def on_release(key):
                    name = mods_map.get(key)
                    if name:
                        self._mods_down.discard(name)
                self._kb_listener = _k.Listener(on_press=on_press, on_release=on_release)
                self._kb_listener.start()
        except Exception:
            self._mouse_listener = None
            self._kb_listener = None

    def _mouse_snapshot(self):
        """(cursor_xy_or_None, [click_xy, ...]) in absolute screen coordinates."""
        clicks = []
        with self._track_lock:
            if self._pending_clicks:
                clicks = list(self._pending_clicks)
                self._pending_clicks = []
        pos = None
        if self._mouse_ctrl is not None:
            try:
                pos = self._mouse_ctrl.position
            except Exception:
                pos = None
        if pos is None and sys.platform == "win32":
            try:
                import ctypes
                class _PT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                pt = _PT()
                if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                    pos = (pt.x, pt.y)
                if self._mouse_listener is None:
                    down = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
                    if down and not self._prev_btn and pos is not None:
                        clicks.append((pos[0], pos[1]))
                    self._prev_btn = down
            except Exception:
                pass
        return pos, clicks

    def _capture_loop(self, cap, out_w, out_h, fps):
        min_interval = 1.0 / (fps * 2)  # never capture more than 2x the output FPS - saves CPU
        src_w, src_h = self._src_size
        off_x, off_y = self._src_off
        zoom_on = bool(self.cfg.get("click_zoom"))
        fx_on = bool(self.cfg.get("mouse_fx"))
        keys_on = bool(self.cfg.get("keystrokes"))
        zoom_factor = float(self.cfg.get("zoom_level", 1.8))
        last_t = time.perf_counter()
        with mss.mss() as sct:
            monitor = self._monitor or sct.monitors[1]
            while not self._stop_evt.is_set():
                if self.paused:
                    time.sleep(0.03)
                    last_t = time.perf_counter()
                    continue
                iter_start = time.perf_counter()
                dt = max(0.001, iter_start - last_t)
                last_t = iter_start
                now = time.time()

                pos, clicks = (None, [])
                if zoom_on or fx_on:
                    pos, clicks = self._mouse_snapshot()
                if clicks:
                    cx_abs, cy_abs = clicks[-1]
                    rel = (cx_abs - off_x, cy_abs - off_y)
                    if 0 <= rel[0] < src_w and 0 <= rel[1] < src_h:
                        self._zoom_tx, self._zoom_ty = float(rel[0]), float(rel[1])
                        self._zoom_hold_until = now + 1.4  # hold ~1.4 s so viewers see the click result
                        self._ripple = (rel, now)
                        if zoom_on:
                            self._zoom_target = zoom_factor
                if zoom_on:
                    if now > self._zoom_hold_until:
                        self._zoom_target = 1.0
                    k = min(1.0, dt * 5.5)  # ease in/out in roughly 0.4 s, no jump cuts
                    self._zoom_level += (self._zoom_target - self._zoom_level) * k
                    if self._zoom_level > 1.02 and pos is not None:
                        kf = min(1.0, dt * 2.5)  # gentle cursor follow while zoomed
                        self._zoom_tx += ((pos[0] - off_x) - self._zoom_tx) * kf
                        self._zoom_ty += ((pos[1] - off_y) - self._zoom_ty) * kf
                    kc = min(1.0, dt * 6.0)
                    self._zoom_cx += (self._zoom_tx - self._zoom_cx) * kc
                    self._zoom_cy += (self._zoom_ty - self._zoom_cy) * kc

                raw = sct.grab(monitor)
                frame4 = np.asarray(raw)
                # Click-zoom: crop around the (smoothed) click point in source
                # coordinates, then scale that crop up to the output size.
                ox = oy = 0
                cw, ch = src_w, src_h
                if zoom_on and self._zoom_level > 1.01:
                    cw = max(16, int(src_w / self._zoom_level))
                    ch = max(16, int(src_h / self._zoom_level))
                    ox = int(min(max(self._zoom_cx - cw / 2, 0), src_w - cw))
                    oy = int(min(max(self._zoom_cy - ch / 2, 0), src_h - ch))
                    frame4 = frame4[oy:oy + ch, ox:ox + cw]
                if frame4.shape[1] != out_w or frame4.shape[0] != out_h:
                    # INTER_AREA is faster and sharper when shrinking
                    # the screen down to the recording size.
                    shrink = frame4.shape[1] > out_w or frame4.shape[0] > out_h
                    frame4 = cv2.resize(frame4, (out_w, out_h),
                                        interpolation=cv2.INTER_AREA if shrink else cv2.INTER_LINEAR)
                frame = np.ascontiguousarray(frame4[:, :, :3])

                # Facecam-only filter: the character filter is applied
                # to the small facecam image in _composite() only.
                # It is NEVER applied to the whole video / game here -
                # the user asked for anime face on the cam only.
                if fx_on:
                    sx = out_w / cw
                    sy = out_h / ch
                    try:
                        if self._ripple is not None:
                            (rx, ry), rt = self._ripple
                            age = now - rt
                            if age < 0.45:
                                r = int(6 + (age / 0.45) * 24)
                                cv2.circle(frame, (int((rx - ox) * sx), int((ry - oy) * sy)), r, (0, 215, 255), 2)
                            else:
                                self._ripple = None
                        if pos is not None:
                            px = (pos[0] - off_x - ox) * sx
                            py = (pos[1] - off_y - oy) * sy
                            if 0 <= px < out_w and 0 <= py < out_h:
                                cv2.circle(frame, (int(px), int(py)), 11, (0, 215, 255), 2)
                                cv2.circle(frame, (int(px), int(py)), 2, (0, 215, 255), -1)
                    except Exception:
                        pass

                if cap is not None:
                    cam = self._get_cam_frame()
                    if cam is not None:
                        # Mirror facecam (like a selfie): without this,
                        # the camera shows you flipped left-right and
                        # your hair / hand look "opposite" in the video.
                        if self.cfg.get("mirror_facecam", True):
                            cam = cv2.flip(cam, 1)
                        frame = self._composite(frame, cam, out_w, out_h)

                if keys_on and self._keystroke is not None:
                    text, kt = self._keystroke
                    if now - kt < 1.6:
                        try:
                            cv2.putText(frame, text, (14, out_h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
                            cv2.putText(frame, text, (14, out_h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                        except Exception:
                            pass

                if self.streamer is not None:
                    self.streamer.write_frame(frame)
                with self._frame_lock:
                    self._latest_frame = frame
                    self._frame_id += 1
                self.captured += 1
                self.preview_frame = frame
                spent = time.perf_counter() - iter_start
                if spent < min_interval:
                    time.sleep(min_interval - spent)

    def _get_latest(self):
        with self._frame_lock:
            return self._latest_frame, self._frame_id

    # ---- timeline writer (v1.2 speed fix)
    # Writes frames on a WALL-CLOCK schedule: one frame per 1/fps of real time.
    # v1 wrote only as many frames as the PC managed to capture, but still
    # labelled the file 30 FPS - so a PC capturing 4 FPS produced a video
    # 7x too short and played at ~7x speed (50 s recording -> 7 s video).
    # Now: if capture is slow, the last frame is repeated to fill time;
    # if ENCODING is too slow to do even that, we switch to writing only new
    # frames and afterwards re-stamp the file with the real achieved FPS
    # (see _finish / _fix_fps) - either way the duration matches real time.
    def _writer_loop(self, writer, fps):
        # Speed controller: one output frame is written every (speed / fps)
        # real seconds. speed=1 -> real time (record 50 s, video is 50 s).
        # speed=2 -> timelapse (50 s -> 25 s). speed=0.5 -> slow motion (50 s -> 100 s).
        speed = float(self.cfg.get("speed", 1.0))
        interval = speed / fps
        t0 = time.perf_counter()
        written = 0
        last_id = -1
        behind = False
        behind_streak = 0
        pause_mark = None
        paused_perf = 0.0
        last_status = 0.0
        while not self._stop_evt.is_set():
            if self.paused:
                if pause_mark is None:
                    pause_mark = time.perf_counter()
                time.sleep(0.02)
                continue
            if pause_mark is not None:
                paused_perf += time.perf_counter() - pause_mark
                pause_mark = None

            target = t0 + paused_perf + written * interval
            wait = target - time.perf_counter()
            if wait > 0:
                time.sleep(min(wait, 0.02))
                continue

            frame, fid = self._get_latest()
            if frame is None:
                t0 = time.perf_counter()
                paused_perf = 0.0
                continue
            if behind and fid == last_id:
                time.sleep(0.004)  # wait for a NEW frame instead of wasting encodes on copies
                continue
            writer.write(frame)
            written += 1
            last_id = fid
            self.written = written
            if written == 1 and self._video_t0 is None:
                # Lip-sync: the video's time 0, in the same clock as
                # the mic / system-audio stamps.
                self._video_t0 = t0 + paused_perf

            lateness = time.perf_counter() - (t0 + paused_perf + written * interval)
            if lateness > interval:
                behind_streak += 1
                if behind_streak >= 5:
                    behind = True
            else:
                behind_streak = 0

            now = time.time()
            if now - last_status >= 0.25:  # throttle: flooding Tk from this thread also slowed v1 down
                last_status = now
                self._active_seconds = time.perf_counter() - t0 - paused_perf
                self.on_status(elapsed=self._active_seconds, dropped=0, written=written)
                limit_min = float(self.cfg.get("record_limit", 0) or 0)
                if limit_min > 0 and self._active_seconds >= limit_min * 60:
                    self._stop_evt.set()  # auto-stop timer reached

        if pause_mark is not None:
            paused_perf += time.perf_counter() - pause_mark
        self._active_seconds = max(0.0, time.perf_counter() - t0 - paused_perf)
        self._behind_mode = behind

    def _fix_fps(self, path, new_fps):
        """Re-write the video stamped with the FPS it was really captured at,
        so its duration matches the real recording time."""
        try:
            src = cv2.VideoCapture(str(path))
            if not src.isOpened():
                return False
            w = int(src.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(src.get(cv2.CAP_PROP_FRAME_HEIGHT))
            tmp = str(path).replace(".mp4", ".fixed.mp4")
            out = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), max(1.0, float(new_fps)), (w, h))
            if not out.isOpened():
                src.release()
                return False
            n = 0
            while True:
                ok, f = src.read()
                if not ok:
                    break
                out.write(f)
                n += 1
            src.release()
            out.release()
            if n > 10:
                os.replace(tmp, str(path))
                return True
            if os.path.exists(tmp):
                os.remove(tmp)
            return False
        except Exception:
            log_error("fix fps")
            return False

    def _finish(self, writer, cap, fps):
        """Runs after Stop: finalise the file, correct its speed if this PC
        couldn't encode in real time, then merge the mic audio."""
        # This thread is started when recording STARTS, and it waits
        # here for the capture thread to end (when Stop is pressed).
        # The teardown below must only run AFTER that wait: stopping
        # the mouse listener / live stream first killed click-zoom
        # (the listener was dead ~0.2 s into every recording, so no
        # click ever reached the zoom) and cut the live stream off
        # at the start too.
        if self._capture_thread:
            self._capture_thread.join()
        if getattr(self, "streamer", None):
            try:
                self.streamer.stop()
            except Exception:
                pass
            self.streamer = None
        for lst in (self._mouse_listener, self._kb_listener):
            try:
                if lst is not None:
                    lst.stop()
            except Exception:
                pass
        if self._writer_thread:
            self._writer_thread.join()
        try:
            writer.release()
        except Exception:
            pass
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        note = ""
        speed = float(self.cfg.get("speed", 1.0))
        if self._behind_mode and self._active_seconds > 3 and self.written > 10:
            # Frames written cover _active_seconds of real time; at the chosen
            # speed the output must last _active_seconds / speed.
            out_seconds = self._active_seconds / speed
            real_fps = self.written / out_seconds if out_seconds > 0 else fps
            if real_fps < fps * 0.92:
                self.on_status(elapsed=self._active_seconds, dropped=0, written=self.written, phase="fixing")
                if self._fix_fps(self.output_path, real_fps):
                    note = (f" Your PC could only manage ~{real_fps:.0f} FPS at this quality, "
                            f"so the video was stamped at that rate to keep the timing/speed correct. "
                            f"For smoother video, try 480p (Ultra Light).")
        had_mic = False
        had_sys = False
        if self._mic:
            had_mic = self._mic.stop()
            self._mic = None
        if self._sys:
            had_sys = self._sys.stop()
            self._sys = None
        if self._smart_stop_evt is not None:
            try:
                self._smart_stop_evt.set()
            except Exception:
                pass
        # v2.3 - smart script check, BEFORE mux (mux deletes the mic WAV)
        if bool(self.cfg.get("script_enabled")) and (self.cfg.get("script_text") or "").strip():
            if had_mic and self._mic_wav and os.path.exists(self._mic_wav):
                note += self._smart_post_check()
            elif not had_mic:
                note += " Smart check: no mic audio, so your speech could not be checked (turn the mic on for Smart Record)."
            else:
                note += " Smart check: mic audio was empty, so your speech could not be checked."
        if had_mic or had_sys:
            self._mux_audio()
            # If a WAV is still there, FFmpeg wasn't available to merge it.
            if had_mic and os.path.exists(self._mic_wav or "") and self.cfg.get("voice", "Off") != "Off":
                note += " (Voice changer needs FFmpeg installed to apply - your plain mic audio was saved as the .mic.wav file next to the video.)"
        if self.sys_error:
            note += f" System audio: {self.sys_error}"
        elif had_sys:
            note += f" Game sound included (from {self.sys_source})." if self.sys_source else " Game sound included."
        elif self.cfg.get("system_audio") and not had_sys:
            note += " (Game sound was on but nothing was captured - see the Audio card's Check button for setup.)"
        if self.cfg.get("gif"):
            note += self._make_gif(str(self.output_path.with_suffix(".gif")))
        # v2.4 - tutorial chapters: save them next to the video so
        # the editor can load them (and the user can rename them).
        if self.chapters:
            try:
                ch_path = self.output_path.with_suffix(".chapters.json")
                save_chapters_json(ch_path, self.chapters, self.output_path.name)
                note += f" {len(self.chapters)} chapter(s) saved ({ch_path.name})."
            except Exception:
                pass
        self.recording = False
        self.on_status(done=True, path=str(self.output_path), mic_active=self.mic_active, note=note)

    # ---- capture setup, shared by Record and Instant Replay ----
    def _capture_geometry(self):
        """Work out the capture area and output size from the settings.
        Returns (out_w, out_h, fps)."""
        cfg = self.cfg
        fps = int(cfg["fps"])
        res_label = cfg["resolution"]
        region = cfg.get("region") if cfg.get("area") == "Region (custom)" else None
        with mss.mss() as sct:
            if region and len(region) == 4 and int(region[2]) >= 50 and int(region[3]) >= 50:
                mon = {"left": int(region[0]), "top": int(region[1]),
                       "width": int(region[2]), "height": int(region[3])}
            else:
                mon = sct.monitors[1]  # primary monitor (fastest, best for gaming)
            src_w, src_h = mon["width"], mon["height"]
        self._monitor = mon
        self._src_off = (mon.get("left", 0), mon.get("top", 0))
        self._src_size = (src_w, src_h)
        if "480" in res_label:
            out_h = 480
        elif "720" in res_label:
            out_h = 720
        elif "1080" in res_label:
            out_h = 1080
        else:
            out_h = src_h
        # Light mode (weak laptop): never record above 720p, however
        # high the resolution setting is - 1080p costs a lot of CPU.
        if self.cfg.get("light_mode", True):
            out_h = min(out_h, 720)
        out_h = min(out_h, src_h)
        out_w = int(src_w * out_h / src_h)
        out_w -= out_w % 2
        out_h -= out_h % 2
        return out_w, out_h, fps

    def _start_capture_threads(self, out_w, out_h, fps):
        """Open the webcam and start the capture thread (screen grab +
        facecam composite). Returns the camera handle (or None).
        Used by both Record and Instant Replay."""
        cfg = self.cfg
        cap = None
        if cfg["facecam"]:
            cap = cv2.VideoCapture(int(cfg["camera_index"]), cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # low latency / low memory
            else:
                cap = None  # screen-only rather than failing
        self._stop_evt.clear()
        self.recording = False
        self.paused = False
        self.dropped = 0
        self.written = 0
        self.captured = 0
        self.paused_total = 0.0
        self.start_time = time.time()
        with self._frame_lock:
            self._latest_frame = None
            self._frame_id = 0
        self._behind_mode = False
        self._active_seconds = 0.0
        src_w = self._src_size[0] if self._src_size else out_w
        self._zoom_level = 1.0
        self._zoom_target = 1.0
        self._zoom_cx = src_w / 2
        self._zoom_cy = (self._src_size[1] if self._src_size else out_h) / 2
        self._zoom_tx = self._zoom_cx
        self._zoom_ty = self._zoom_cy
        self._zoom_hold_until = 0.0
        self._ripple = None
        self._keystroke = None
        self._init_trackers()
        if cap is not None:
            self._cam_thread = threading.Thread(target=self._cam_loop, args=(cap,), daemon=True)
            self._cam_thread.start()
        self._capture_thread = threading.Thread(target=self._capture_loop, args=(cap, out_w, out_h, fps), daemon=True)
        self._capture_thread.start()
        return cap

    def _end_capture_threads(self):
        """Stop the capture thread + camera + trackers (Replay teardown;
        a normal recording is torn down by _finish instead)."""
        self._stop_evt.set()
        if getattr(self, "_capture_thread", None):
            try:
                self._capture_thread.join(timeout=3)
            except Exception:
                pass
            self._capture_thread = None
        if getattr(self, "_replay_cap", None) is not None:
            try:
                self._replay_cap.release()
            except Exception:
                pass
            self._replay_cap = None
        for lst in (self._mouse_listener, self._kb_listener):
            try:
                if lst is not None:
                    lst.stop()
            except Exception:
                pass
        self._mouse_listener = None
        self._kb_listener = None
        self._cam_thread = None

    # ---- Instant Replay ----
    def start_replay(self, seconds=60):
        """Start Instant Replay: capture runs in the background (no
        recording file) and the buffer keeps the last `seconds`.
        Returns True, or False when a recording is already running."""
        if self.recording or self.replay is not None:
            return False
        try:
            out_dir = ensure_output_dir(self.cfg.get("output_dir"))
        except Exception:
            return False
        self.cfg["output_dir"] = str(out_dir)
        try:
            out_w, out_h, fps = self._capture_geometry()
            cap = self._start_capture_threads(out_w, out_h, fps)
        except Exception as e:
            log_error("replay start: %s" % e)
            return False
        self._replay_cap = cap
        self.replay = ReplayBuffer(self.cfg, self._get_latest, out_dir, seconds)
        if not self.replay.start((out_w, out_h)):
            self._end_capture_threads()
            self.replay = None
            return False
        return True

    def stop_replay(self):
        if self.replay is not None:
            try:
                self.replay.stop()
            except Exception:
                pass
            self.replay = None
        self._end_capture_threads()

    def save_replay(self):
        if self.replay is None:
            return False, "Instant Replay is off - turn it on first."
        out_dir = ensure_output_dir(self.cfg.get("output_dir"))
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out = out_dir / ("Replay_%s.mp4" % stamp)
        return self.replay.save(out)

    # ---- main capture loop
    def start(self):
        cfg = self.cfg
        # Pressing Record while Replay is on stops the replay first,
        # then starts a normal recording.
        if getattr(self, "replay", None) is not None:
            self.stop_replay()
        # v1.1: never fail just because the chosen/Videos folder can't be created.
        out_dir = ensure_output_dir(cfg.get("output_dir"))
        cfg["output_dir"] = str(out_dir)  # tell the UI where we really saved
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.output_path = out_dir / f"Game_{stamp}.mp4"

        out_w, out_h, fps = self._capture_geometry()

        # Video writer - mp4v first: it's the codec that reliably opens with
        # stock opencv-python on Windows (avc1 often silently fails there).
        writer = None
        for codec in ("mp4v", "avc1", "XVID"):
            fourcc = cv2.VideoWriter_fourcc(*codec)
            w = cv2.VideoWriter(str(self.output_path), fourcc, fps, (out_w, out_h))
            if w.isOpened():
                writer = w
                break
            w.release()
        if writer is None:
            raise RuntimeError("Could not open a video encoder. Try installing opencv-python again.")

        # Mic
        self.mic_active = False
        # v2.3 - smart script: checker exists even without a mic, so the
        # UI can show "Next: ..." - the listener only runs with a mic.
        self.smart_checker = None
        self._smart_queue = None
        self._smart_listener = None
        self._smart_stop_evt = None
        self.smart_result = None
        script_on = bool(cfg.get("script_enabled")) and bool((cfg.get("script_text") or "").strip())
        if script_on:
            self.smart_checker = SmartChecker(cfg.get("script_text") or "")
            if cfg.get("script_live_check", True):
                self._smart_queue = queue.Queue(maxsize=4)
                self._smart_stop_evt = threading.Event()
        self._video_t0 = None
        self._mic_t0 = None
        self._sys_t0 = None
        self._stop_perf = None
        self._pause_intervals = []
        self._pause_started = None
        self._voice_changes = []
        self.chapters = []  # v2.4: fresh chapter list per recording
        self._voice_start = cfg.get("voice", "Off")
        if cfg.get("mic") and HAS_MIC:
            self._mic_wav = str(self.output_path.with_suffix(".mic.wav"))
            self._mic = MicRecorder(self._mic_wav, chunk_queue=self._smart_queue)
            self.mic_active = self._mic.start()
            if self.mic_active:
                self._mic_t0 = getattr(self._mic, "start_perf", None)
            if self.mic_active and self._smart_queue is not None:
                self._smart_listener = SmartListener(self._smart_queue, self.smart_checker, self._smart_stop_evt)
                self._smart_listener.start()

        # v2.1 - system / game sound (separate from the mic, non-fatal)
        self.sys_active = False
        self.sys_error = ""
        self.sys_source = ""
        self._sys = None
        self._sys_wav = None
        if cfg.get("system_audio"):
            self._sys_wav = str(self.output_path.with_suffix(".sys.wav"))
            self._sys = SystemAudioRecorder(self._sys_wav, cfg)
            self.sys_active = self._sys.start()
            if self.sys_active:
                self.sys_source = self._sys.source
                self._sys_t0 = getattr(self._sys, "start_perf", None)
            else:
                self.sys_error = self._sys.error or "System audio could not be started."

        # v2.0 - live: start the RTMP stream (non-fatal if it fails)
        self.streamer = None
        self.live_error = ""
        if cfg.get("live_enabled"):
            try:
                self.streamer = LiveStreamer(cfg, out_w, out_h, fps,
                                             on_error=lambda m: setattr(self, "live_error", m))
                self.streamer.start()
            except Exception as e:
                self.live_error = str(e)
                self.streamer = None

        cap = self._start_capture_threads(out_w, out_h, fps)
        self.recording = True

        self._writer_thread = threading.Thread(target=self._writer_loop, args=(writer, fps), daemon=True)
        self._writer_thread.start()
        threading.Thread(target=self._finish, args=(writer, cap, fps), daemon=True).start()
        return self.output_path

    @staticmethod
    def _voice_chain(voice, sr=44100):
        """The voice-changer filter for one voice (mic only)."""
        if voice == "Deep":
            return f"asetrate={sr}*0.8,aresample={sr},atempo=1.25"
        if voice and voice.startswith("High"):
            return f"asetrate={sr}*1.35,aresample={sr},atempo=0.7407"
        if voice == "Echo":
            return "aecho=0.8:0.9:120:0.35"
        if voice == "Robot":
            return "tremolo=f=30:d=0.85"
        return ""

    def _audio_filter_chain(self):
        """FFmpeg audio filters for the voice changer + speed controller.
        Applied AFTER recording, so they cost zero CPU while you play."""
        sr = 44100
        if self._mic is not None:
            sr = int(getattr(self._mic, "samplerate", 44100) or 44100)
        parts = []
        if self.cfg.get("noise_reduction"):
            parts.append("highpass=f=80,afftdn=nf=-25")  # gentle mic noise cleanup, applied after recording
        vc = self._voice_chain(self.cfg.get("voice", "Off"), sr)
        if vc:
            parts.append(vc)
        speed = float(self.cfg.get("speed", 1.0))
        if speed != 1.0:
            parts.append(f"atempo={speed}")  # keep mic in sync with the video speed
        return ",".join(parts)

    def _wav_duration(self, path):
        try:
            with wave.open(str(path), "rb") as wf:
                return wf.getnframes() / float(wf.getframerate() or 44100)
        except Exception:
            return 0.0

    def _kept_intervals(self, src_t0, wav_dur):
        """(start, end) ranges of a WAV that belong in the video.

        The video starts at self._video_t0; the WAV started at src_t0.
        Sound recorded before the first video frame is cut, and paused
        parts are cut out (the mic keeps recording while paused, the
        video does not). Returns the whole WAV when the stamps are
        missing, exactly as before."""
        if self._video_t0 is None or src_t0 is None or wav_dur <= 0:
            return [(0.0, wav_dur)]
        end_perf = self._stop_perf or (src_t0 + wav_dur)
        kept = []
        cur = self._video_t0
        for (ps, pe) in sorted(self._pause_intervals):
            if pe <= cur:
                continue
            if ps > cur:
                kept.append((cur, min(ps, end_perf)))
            cur = max(cur, pe)
            if cur >= end_perf:
                break
        if cur < end_perf:
            kept.append((cur, end_perf))
        out = []
        for (a, b) in kept:
            s, e = a - src_t0, b - src_t0
            s, e = max(0.0, s), min(wav_dur, e)
            if e - s > 0.05:
                out.append((s, e))
        return out or [(0.0, wav_dur)]

    def _mic_segments(self, wav_dur):
        """[(start, end, voice)] in mic-wav seconds, lip-sync aligned:
        the start gap and paused parts are removed, and the list is
        split wherever the user changed the voice mid-recording."""
        segs = [[s, e] for (s, e) in self._kept_intervals(self._mic_t0, wav_dur)]
        for (perf, _voice) in sorted(self._voice_changes):
            if self._mic_t0 is None:
                break
            mt = perf - self._mic_t0
            for seg in segs:
                if seg[0] < mt < seg[1] - 0.05:
                    segs.append([mt, seg[1]])
                    seg[1] = mt
                    break
        out = []
        for (s, e) in sorted(segs):
            v = self._voice_start
            for (perf, voice) in sorted(self._voice_changes):
                if self._mic_t0 is not None and perf - self._mic_t0 <= s + 0.01:
                    v = voice
            if e - s > 0.05:
                out.append((s, e, v))
        return out

    def _find_ffmpeg(self):
        return find_ffmpeg()

    def _make_gif(self, gif_path):
        """Also save an animated GIF copy (FFmpeg, after recording - no cost while playing)."""
        try:
            dur = self._active_seconds / float(self.cfg.get("speed", 1.0))
            if dur > 90:
                return " (GIF copy skipped - recording over 90 seconds.)"
            ff = self._find_ffmpeg()
            if not ff:
                return " (GIF copy needs FFmpeg.)"
            pal = str(self.output_path.with_suffix(".palette.png"))
            vf = "fps=12,scale=640:-1:flags=lanczos"
            r1 = subprocess.run([ff, "-y", "-i", str(self.output_path), "-vf", vf + ",palettegen", pal],
                                capture_output=True, timeout=600, **_quiet_subprocess_kwargs())
            ok = False
            if r1.returncode == 0 and os.path.exists(pal):
                r2 = subprocess.run([ff, "-y", "-i", str(self.output_path), "-i", pal,
                                     "-lavfi", vf + " [x]; [x][1:v] paletteuse", gif_path],
                                    capture_output=True, timeout=600, **_quiet_subprocess_kwargs())
                ok = r2.returncode == 0 and os.path.exists(gif_path)
            if os.path.exists(pal):
                os.remove(pal)
            return " GIF copy saved next to the video." if ok else " (GIF copy failed.)"
        except Exception:
            log_error("make gif")
            return " (GIF copy failed.)"

    def _smart_post_check(self):
        """After Stop: transcribe the mic WAV, compare it to the script,
        write a report + auto-corrected captions (.srt). Returns a note
        string for the status bar. Never raises - a failed check must
        never lose the video."""
        try:
            self.on_status(phase="script")
            segments, engine, err = transcribe_wav(self._mic_wav)
            if err:
                return f" Smart check: {err}"
            heard = " ".join(seg["text"] for seg in segments)
            if not heard.strip():
                return " Smart check: no speech was heard in the mic audio."
            res = compare_script(self.cfg.get("script_text") or "", heard)
            self.smart_result = res
            base = str(self.output_path.with_suffix(""))
            # report
            report_path = base + "_script.txt"
            lines = [f"Smart Script Check - {self.output_path.name}",
                     f"Accuracy: {res['accuracy']:.0f}%  ({res['correct']}/{res['total']} script words correct)",
                     f"Speech engine: {engine}",
                     "",
                     "What you said:",
                     heard,
                     "",
                     "Auto-corrected (script) version:",
                     res["corrected_text"],
                     "",
                     "Mistakes:"]
            if res["mistakes"]:
                for m in res["mistakes"]:
                    lines.append(f"  - word {m['position']}: script says '{m['expected']}', you said '{m['heard']}'")
            else:
                lines.append("  (none - perfect!)")
            if res["retake_lines"]:
                lines.append("")
                lines.append("Lines to re-record:")
                for ln in res["retake_lines"]:
                    lines.append(f"  - {ln}")
            try:
                Path(report_path).write_text("\n".join(lines), encoding="utf-8")
                self.smart_report_path = report_path
            except Exception:
                pass
            # captions (.srt) - auto-corrected if that switch is on
            try:
                corr_map = {}
                for m in res["mistakes"]:
                    if m["heard"] not in ("(missed)",):
                        corr_map[m["heard"].lower()] = m["expected"]
                srt_segments = []
                for seg in segments:
                    text = seg["text"]
                    if self.cfg.get("script_autocorrect", True) and corr_map:
                        words = text.split()
                        fixed = []
                        for w in words:
                            key = _norm_words(w)
                            fixed.append(corr_map.get(key[0], w) if key else w)
                        text = " ".join(fixed)
                    srt_segments.append({"start": seg["start"], "end": seg["end"], "text": text})
                srt_path = base + "_captions.srt"
                Path(srt_path).write_text(segments_to_srt(srt_segments), encoding="utf-8")
                self.smart_srt_path = srt_path
            except Exception:
                pass
            n = len(res["mistakes"])
            return (f" Smart check: {res['accuracy']:.0f}% accurate, {n} mistake(s) - "
                    f"see {Path(report_path).name} and {Path(base + '_captions.srt').name}.")
        except Exception as e:
            log_error(f"smart post check: {e}")
            return " Smart check failed (video still saved)."

    def _mux_audio(self):
        """Merge mic and/or system-audio WAVs into the MP4 (FFmpeg, after recording).

        Voice changer / noise reduction apply to the MIC only - game sound
        is left untouched, apart from the speed (atempo) so it stays in
        sync with the video. Mic + game are mixed with amix.
        If FFmpeg is missing, the WAVs stay next to the video, nothing lost.
        """
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            return
        mic_path = self._mic_wav if (self._mic_wav and os.path.exists(self._mic_wav)) else None
        sys_path = self._sys_wav if (self._sys_wav and os.path.exists(self._sys_wav)) else None
        if not mic_path and not sys_path:
            return
        video = str(self.output_path)
        tmp = video.replace(".mp4", ".withaudio.mp4")
        speed = float(self.cfg.get("speed", 1.0))
        sys_chain = f"atempo={speed}" if speed != 1.0 else "anull"
        sr = 44100
        if self._mic is not None:
            sr = int(getattr(self._mic, "samplerate", 44100) or 44100)
        # Lip-sync: the audio started before the video (or a pause /
        # voice change happened) — use the aligned path. Otherwise
        # keep the old simple path.
        need_align = (self._video_t0 is not None and
                      (self._pause_intervals or self._voice_changes or
                       (self._mic_t0 is not None and abs(self._video_t0 - self._mic_t0) > 0.05) or
                       (self._sys_t0 is not None and abs(self._video_t0 - self._sys_t0) > 0.05)))
        try:
            if not need_align:
                if mic_path and sys_path:
                    mic_chain = self._audio_filter_chain() or "anull"
                    filt = f"[1:a]{mic_chain}[mic];[2:a]{sys_chain}[sys];[mic][sys]amix=inputs=2:duration=longest:normalize=0[aout]"
                    cmd = [ffmpeg, "-y", "-i", video, "-i", mic_path, "-i", sys_path,
                           "-filter_complex", filt, "-map", "0:v", "-map", "[aout]",
                           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", tmp]
                elif mic_path:
                    cmd = [ffmpeg, "-y", "-i", video, "-i", mic_path, "-c:v", "copy"]
                    chain = self._audio_filter_chain()
                    if chain:
                        cmd += ["-af", chain]
                    cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest", tmp]
                else:
                    cmd = [ffmpeg, "-y", "-i", video, "-i", sys_path, "-c:v", "copy"]
                    if sys_chain != "anull":
                        cmd += ["-af", sys_chain]
                    cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest", tmp]
                r = subprocess.run(cmd, capture_output=True, timeout=300, **_quiet_subprocess_kwargs())
                if r.returncode == 0 and os.path.exists(tmp):
                    os.replace(tmp, video)
                    for pth in (mic_path, sys_path):
                        if pth:
                            try:
                                os.remove(pth)
                            except Exception:
                                pass
                elif os.path.exists(tmp):
                    os.remove(tmp)
                return
            # ---- aligned path: cut each audio stream into segments ----
            # Input 0 is the video; mic is 1 if present, sys is next.
            mic_idx = 1 if mic_path else None
            sys_idx = (2 if mic_path else 1) if sys_path else None
            filters = []
            maps = []
            if mic_path:
                segs = self._mic_segments(self._wav_duration(mic_path))
                if segs:
                    parts = []
                    for i, (s, e, v) in enumerate(segs):
                        chain = f"[{mic_idx}:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS"
                        vc = self._voice_chain(v, sr)
                        if vc:
                            chain += "," + vc
                        chain += f"[ms{i}]"
                        filters.append(chain)
                        parts.append(f"[ms{i}]")
                    label = parts[0] if len(parts) == 1 else "[mic]"
                    if len(parts) > 1:
                        filters.append("".join(parts) +
                                       f"concat=n={len(parts)}:v=0:a=1[mic]")
                    tail = ""
                    if self.cfg.get("noise_reduction"):
                        tail += "highpass=f=80,afftdn=nf=-25"
                    if speed != 1.0:
                        tail += ("," if tail else "") + f"atempo={speed}"
                    if tail:
                        filters.append(f"{label}{tail}[micf]")
                        label = "[micf]"
                    if self._mic_t0 is not None and self._video_t0 is not None:
                        gap = self._mic_t0 - self._video_t0
                        if gap > 0.05:
                            filters.append(f"{label}adelay={int(gap * 1000)}:all=1[micd]")
                            label = "[micd]"
                    maps.append(label)
            if sys_path:
                kept = self._kept_intervals(self._sys_t0, self._wav_duration(sys_path))
                parts = []
                for i, (s, e) in enumerate(kept):
                    filters.append(f"[{sys_idx}:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[ss{i}]")
                    parts.append(f"[ss{i}]")
                if parts:
                    label = parts[0] if len(parts) == 1 else "[sys]"
                    if len(parts) > 1:
                        filters.append("".join(parts) +
                                       f"concat=n={len(parts)}:v=0:a=1[sys]")
                    if speed != 1.0:
                        filters.append(f"{label}atempo={speed}[sysf]")
                        label = "[sysf]"
                    if self._sys_t0 is not None and self._video_t0 is not None:
                        gap = self._sys_t0 - self._video_t0
                        if gap > 0.05:
                            filters.append(f"{label}adelay={int(gap * 1000)}:all=1[sysd]")
                            label = "[sysd]"
                    maps.append(label)
            if not maps:
                return
            inputs = ["-i", video]
            if mic_path:
                inputs += ["-i", mic_path]
            if sys_path:
                inputs += ["-i", sys_path]
            if len(maps) == 1:
                final = maps[0]
            else:
                filters.append("".join(maps) +
                               f"amix=inputs={len(maps)}:duration=longest:normalize=0[aout]")
                final = "[aout]"
            cmd = [ffmpeg, "-y"] + inputs + [
                "-filter_complex", ";".join(filters),
                "-map", "0:v", "-map", final, "-c:v", "copy", "-c:a", "aac",
                "-b:a", "192k", "-shortest", tmp]
            r = subprocess.run(cmd, capture_output=True, timeout=300, **_quiet_subprocess_kwargs())
            if r.returncode == 0 and os.path.exists(tmp):
                os.replace(tmp, video)
                for pth in (mic_path, sys_path):
                    if pth:
                        try:
                            os.remove(pth)
                        except Exception:
                            pass
            elif os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass  # WAVs stay next to video, nothing is lost

    def toggle_pause(self):
        if self.recording:
            self.paused = not self.paused
            now = time.perf_counter()
            if self.paused:
                self._pause_started = now
            elif self._pause_started is not None:
                self._pause_intervals.append((self._pause_started, now))
                self._pause_started = None
            return self.paused
        return False

    def add_chapter(self, title=None):
        """Drop a timestamped chapter marker at the current point
        in the recording. Returns the chapter dict, or None when
        not recording. The time is in VIDEO seconds (active
        recording time divided by the speed setting), so it
        matches the timeline in the editor."""
        if not self.recording:
            return None
        speed = max(0.1, float(self.cfg.get("speed", 1.0)))
        t = max(0.0, self._active_seconds / speed)
        with self._chapter_lock:
            n = len(self.chapters) + 1
            ch = {"time": round(t, 2), "title": title or f"Chapter {n}"}
            self.chapters.append(ch)
            return dict(ch)

    def set_voice(self, voice):
        """Change the voice changer live, while recording. The change
        is stamped in mic time; _mux_audio applies the new voice from
        that moment on, so one recording can go Deep -> Chipmunk."""
        self.cfg["voice"] = voice
        if self.recording and self.mic_active and self._mic_t0 is not None:
            self._voice_changes.append((time.perf_counter(), voice))

    def stop(self):
        self._stop_perf = time.perf_counter()
        if self._pause_started is not None:
            self._pause_intervals.append((self._pause_started, self._stop_perf))
            self._pause_started = None
        self._stop_evt.set()



# --------------------------------------------------------------------------- GUI v2.0
# Modern dark UI (CustomTkinter). Same recorder core as v1.5, new look:
#   header with LIVE + timer, big 16:9 preview, one big Record button,
#   settings grouped into cards in a scrollable sidebar, recent recordings.
BG = "#0F1218"
PANEL = "#181D27"
PANEL2 = "#1F2531"
BORDER = "#2A3242"
TEXT = "#E8EAF0"
MUTED = "#9AA3B2"
ACCENT = "#E5484D"
ACCENT_HOVER = "#C62F33"
GREEN = "#34D399"
AMBER = "#FBBF24"
SKY = "#A9D6E8"      # primary action (dark text on it)
SKY_HOVER = "#8FC6DC"
TEAL = "#12B5D9"     # AI accent (editor)
PURPLE = "#7C5CFF"   # video track (editor)
PURPLE = "#8B7CFF"


def _ffmpeg_available():
    return find_ffmpeg() is not None


class ToolTip:
    """Hover a button for half a second and a small plain-English
    explanation pops up. Makes the app friendly for first-time
    users without adding clutter to the screen."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        self._after = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")

    def _enter(self, _event=None):
        self._after = self.widget.after(500, self._show)

    def _leave(self, _event=None):
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        self._hide()

    def _show(self):
        if self.tip is not None:
            return
        try:
            x = self.widget.winfo_rootx() + 8
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry("+%d+%d" % (x, y))
            tk.Label(self.tip, text=self.text, bg=PANEL2, fg=TEXT,
                     font=("Segoe UI", 11), padx=10, pady=6, wraplength=320,
                     justify="left", relief="solid", borderwidth=1).pack()
        except Exception:
            self.tip = None

    def _hide(self):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


def _round_button(master, glyph, fg_color, hover_color, text_color, font,
                  size=72, command=None):
    """A truly round button. CTkButton's minimum width is
    text + 2*corner_radius, so a 72 px button with a glyph always
    renders as a ~93x72 stadium pill. With no text the button is
    exactly size x size, and the glyph is a label placed on top of
    it — the same trick CTkButton uses internally for its own text
    (its _text_label forwards Enter/Leave/ButtonRelease to the
    button). The label's background follows the button's hover
    colour by hand, and clicks on the glyph invoke the button.
    Returns the button; the glyph label is ``button._glyph``."""
    b = ctk.CTkButton(master, text="", width=size, height=size,
                      corner_radius=size // 2, fg_color=fg_color,
                      hover_color=hover_color, font=font, command=command)
    b._glyph_fg = fg_color
    b._glyph_hover = hover_color
    b._glyph_text_color = text_color
    g = tk.Label(b, text=glyph, font=font, fg=text_color, bg=fg_color,
                 borderwidth=0, padx=0, pady=0)
    g.place(relx=0.5, rely=0.5, anchor="center")
    b._glyph = g
    g.bind("<ButtonRelease-1>", lambda e: b.invoke())
    g.bind("<Enter>", lambda e: g.configure(bg=b._glyph_hover), add="+")
    g.bind("<Leave>", lambda e: g.configure(bg=b._glyph_fg), add="+")
    b.bind("<Enter>", lambda e: g.configure(bg=b._glyph_hover), add="+")
    b.bind("<Leave>", lambda e: g.configure(bg=b._glyph_fg), add="+")
    return b


def _round_button_set(b, glyph=None, fg_color=None, hover_color=None,
                      text_color=None, corner_radius=None, state=None):
    """Change a round button's look and keep its glyph in step:
    the glyph label's text and background follow the button's
    colours, and a disabled button gets a dimmed glyph."""
    kw = {}
    if corner_radius is not None:
        kw["corner_radius"] = corner_radius
    if fg_color is not None:
        kw["fg_color"] = fg_color
        b._glyph_fg = fg_color
    if hover_color is not None:
        kw["hover_color"] = hover_color
        b._glyph_hover = hover_color
    if kw:
        b.configure(**kw)
    if glyph is not None:
        b._glyph.configure(text=glyph)
    if text_color is not None:
        b._glyph_text_color = text_color
    if state is not None:
        b.configure(state=state)
        b._glyph.configure(fg="#8A919C" if state == "disabled"
                           else b._glyph_text_color)
    b._glyph.configure(bg=b._glyph_fg)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.cfg = load_config()
        self.title(APP_NAME)
        self.geometry("1280x820")
        self.minsize(1000, 650)
        self.configure(fg_color=BG)
        self.recorder = None
        self._preview_photo = None
        self._idle_cap = None
        self._hotkeys = None
        self._live_on = False

        self._build_ui()
        self._load_cfg_to_ui()
        self._refresh_recent()
        try:
            usable = ensure_output_dir(self.out_var.get())
            if str(usable) != self.out_var.get():
                self.out_var.set(str(usable))
                self.cfg["output_dir"] = str(usable)
                save_config(self.cfg)
                self.status_var.set(f"Save folder set to {usable} (the previous one wasn't available)")
        except Exception:
            log_error("startup folder check")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F9>", lambda e: self.toggle_record())
        self.bind("<F10>", lambda e: self.toggle_pause())
        self.bind("<F11>", lambda e: self._save_replay())
        # v2.4 - M drops a chapter marker while recording. Window-local
        # on purpose: a global M hotkey would fire while typing.
        self.bind("<m>", self._on_m_key)
        self.bind("<M>", self._on_m_key)
        self.after(120, self._preview_tick)
        self.after(600, self._smart_tick)
        # Responsiveness: when the window is resized, the panels
        # flex and wrapped labels re-wrap.
        self._resize_after = None
        self._panel_w = None
        self._wrap_orig = {}
        self.bind("<Configure>", self._on_window_resize)
        # Global hotkeys, cross-platform via pynput (replaces the old
        # Windows-only `keyboard` library, which needed admin on Linux).
        try:
            from pynput import keyboard as _pk
            self._hotkeys = _pk.GlobalHotKeys({
                "<f9>": lambda: self.after(0, self.toggle_record),
                "<f10>": lambda: self.after(0, self.toggle_pause),
                "<f11>": lambda: self.after(0, self._save_replay),
            })
            self._hotkeys.start()
        except Exception:
            self._hotkeys = None

    # ---------- UI construction ----------
    def _card(self, parent, title):
        frame = ctk.CTkFrame(parent, fg_color=PANEL2, corner_radius=14, border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(frame, text=title, font=("Segoe UI", 13, "bold"), text_color=TEXT, anchor="w").pack(fill="x", padx=14, pady=(8, 2))
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=(0, 10))
        return body

    def _chips(self, parent, var, options, command=None, per_row=0):
        """Segmented pill chips bound to a variable. options =
        [(label, value), ...]. The selected chip is sky with dark
        text; the rest are card with light text. `command` runs when
        the user picks a chip (not when the value is set by code,
        e.g. loading the config). `per_row` wraps long lists."""
        items = list(options)
        groups = ([items[i:i + per_row] for i in range(0, len(items), per_row)]
                  if per_row and len(items) > per_row else [items])
        btns = []

        def refresh(*_a):
            cur = var.get()
            for value, b in btns:
                if value == cur:
                    b.configure(fg_color=SKY, hover_color=SKY_HOVER,
                                text_color="#0F1218")
                else:
                    b.configure(fg_color=PANEL2, hover_color=BORDER,
                                text_color=TEXT)

        rows = []
        for group in groups:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=2)
            rows.append(row)
            for label, value in group:
                # width=0: auto-size to the text.  The 140 px
                # default makes two chips wider than the card and
                # the second one gets clipped.
                b = ctk.CTkButton(row, text=label, height=30, width=0, corner_radius=999,
                                  font=("Segoe UI", 11),
                                  command=lambda v=value: (
                                      var.set(v), command() if command else None))
                b.pack(side="left", padx=2, expand=True, fill="x")
                btns.append((value, b))
        var.trace_add("write", refresh)
        refresh()
        return rows[0] if len(rows) == 1 else rows

    def _show_app_section(self, name):
        """Switch the left panel to one rail section. All sections
        stay built, so the recent list and the script box are always
        there for the code that refreshes them."""
        self._section_name = name
        for n, f in self._panel_frames.items():
            if n == name:
                f.pack(fill="x", padx=6, pady=(4, 8))
            else:
                f.pack_forget()
        for n, b in self._rail_btns.items():
            if n == name:
                b.configure(fg_color="#3A2020", text_color=ACCENT)
            else:
                b.configure(fg_color="transparent", text_color=MUTED)

    def _on_window_resize(self, event):
        """Responsiveness: the window itself was resized. Flex the
        panels and re-wrap labels. (Configure events from child
        widgets also reach this binding through the toplevel
        bindtag, so only the window's own resize counts.)"""
        if event.widget is not self:
            return
        if getattr(self, "_resize_after", None):
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(150, self._apply_window_size)

    def _apply_window_size(self):
        self._resize_after = None
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 100 or h < 100:
            return
        self.update_idletasks()
        # Panels flex: the preview takes most of the extra width;
        # the panels shrink a little on narrow windows (never
        # below ~240 px, so no button is ever cut off — the
        # Quality chips need 181 px in their card).
        if w < 1150:
            left_w, right_w = 240, 240
        elif w < 1400:
            left_w, right_w = 247, 267
        else:
            left_w, right_w = 280, 300
        if (left_w, right_w) != getattr(self, "_panel_w", None):
            self._panel_w = (left_w, right_w)
            self._panel.configure(width=left_w)
            self._right_panel.configure(width=right_w)
            # The panels only take their new width after the
            # geometry manager runs — measure the labels after
            # that, or the old (wider) widths are used and
            # nothing gets re-wrapped.
            self.update_idletasks()
        # Wrapped labels: shrink their wraplength to the panel
        # they are in, restore it when the panel grows again.
        # (This is what kept the Sound card's hint text running
        # to the edge of its card.)
        self._fix_wraplengths(self._panel)
        self._fix_wraplengths(self._right_panel)

    def _fix_wraplengths(self, container):
        """Keep wrapped labels inside a panel that just got
        narrower: a label whose wraplength is wider than its card
        is clipped on the right. Only ever shrink (never grow
        past the wraplength the code asked for)."""
        for w in container.winfo_children():
            if isinstance(w, ctk.CTkLabel):
                orig = self._wrap_orig.get(id(w))
                if orig is None:
                    orig = w.cget("wraplength")
                    self._wrap_orig[id(w)] = orig
                if orig and orig > 0:
                    avail = max(120, w.master.winfo_width() - 24)
                    w.configure(wraplength=min(orig, avail))
            self._fix_wraplengths(w)

    def _update_session_card(self):
        """Keep the Session panel's 'Now recording' heading true:
        what is recording now, or where the next video will save."""
        try:
            if self.recorder and self.recorder.recording:
                name = self._session_file_var.get() or "…"
                self._session_head_var.set("●  Recording — %s" % name)
            else:
                folder = self.out_var.get() or ""
                if len(folder) > 34:
                    folder = "…" + folder[-33:]
                self._session_head_var.set(
                    "Not recording — your next video saves to %s" % folder)
        except Exception:
            pass

    # ---------- top menu bar ----------
    def _build_menu(self):
        """Menu bar at the top of the app (File / Record / Live /
        Facecam / Tools / Help). Every item calls the same action as
        the button or switch with the same name in the sidebar, so
        the menu and the sidebar always stay in sync."""
        menubar = tk.Menu(self, tearoff=0)
        self.menubar = menubar
        self.configure(menu=menubar)

        m = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=m)
        m.add_command(label="Open recordings folder", command=self._open_folder)
        m.add_command(label="Change save folder…", command=self._browse)
        m.add_separator()
        m.add_command(label="Edit a video…  (CapCut-style editor)",
                      command=lambda: self._open_editor())
        m.add_separator()
        m.add_command(label="Exit", command=self._on_close)

        m = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Record", menu=m)
        m.add_command(label="Start / Stop Recording  (F9)", command=self.toggle_record)
        m.add_command(label="Pause / Resume  (F10)", command=self.toggle_pause)
        m.add_separator()
        m.add_command(label="💾  Save replay  (F11)", command=self._save_replay)
        m.add_command(label="⏪  Instant Replay on / off", command=self._toggle_replay_menu)
        m.add_checkbutton(label="Screen record ONLY  (no facecam, no audio)",
                          variable=self.screen_only_var,
                          command=self._on_screen_only)

        m = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Live", menu=m)
        m.add_checkbutton(label="Go Live when recording starts",
                          variable=self.live_var,
                          command=self._on_live_toggle)
        plat = tk.Menu(m, tearoff=0)
        m.add_cascade(label="Platform", menu=plat)
        for name in ["YouTube", "Twitch", "Facebook", "Kick", "Custom"]:
            plat.add_radiobutton(label=name, variable=self.live_platform_var,
                                 value=name,
                                 command=lambda: self._on_platform_change(
                                     self.live_platform_var.get()))

        m = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Facecam", menu=m)
        m.add_checkbutton(label="Facecam on", variable=self.face_var)
        m.add_checkbutton(label="Mirror facecam (like a selfie)", variable=self.mirror_var)
        filt = tk.Menu(m, tearoff=0)
        m.add_cascade(label="Character filter", menu=filt)
        for name in CHARACTER_FILTERS:
            filt.add_radiobutton(label=name, variable=self.filter_var, value=name)
        pos = tk.Menu(m, tearoff=0)
        m.add_cascade(label="Position", menu=pos)
        for name in ["Bottom Right", "Bottom Left", "Top Right", "Top Left"]:
            pos.add_radiobutton(label=name, variable=self.pos_var, value=name)
        shape = tk.Menu(m, tearoff=0)
        m.add_cascade(label="Shape", menu=shape)
        for name in ["Rounded", "Circle", "Rectangle"]:
            shape.add_radiobutton(label=name, variable=self.shape_var, value=name)

        m = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=m)
        m.add_checkbutton(label="Light mode — weak laptop (720p max, less CPU)",
                          variable=self.light_mode_var)
        m.add_command(label="Check system audio on this PC",
                      command=self._check_system_audio)
        m.add_command(label="Load script from file…",
                      command=self._load_script_file)
        m.add_command(label="Test script with example",
                      command=self._test_script_check)
        m.add_separator()
        m.add_command(label="Video Editor…  (trim, split, text, music)",
                      command=lambda: self._open_editor())
        m.add_separator()
        m.add_command(label="Uninstall app…", command=self._uninstall_app)

        m = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=m)
        m.add_command(label="Keyboard shortcuts", command=self._show_shortcuts)
        m.add_command(label="About Lite Game Recorder", command=self._show_about)

    def _show_shortcuts(self):
        messagebox.showinfo(
            "Keyboard shortcuts",
            "F9   Start / Stop recording\n"
            "F10   Pause / Resume recording\n\n"
            "Everything in the menu bar also has a button or switch\n"
            "in the sidebar with the same name.")

    def _show_about(self):
        messagebox.showinfo(
            "About Lite Game Recorder",
            "Lite Game Recorder v2.3\n\n"
            "Screen + Facecam + Mic + Game sound\n"
            "Live to YouTube, Twitch, Facebook, Kick or any RTMP\n"
            "Character filters for your facecam (facecam only)\n"
            "Smart Record — checks your speech against your script\n"
            "Video Editor (File / Tools menu or the Edit button):\n"
            "trim, split, speed, filters, text, stickers, transitions,\n"
            "9:16 vertical, background music, auto captions\n\n"
            "Light mode keeps it fast on weak laptops.")

    def _build_ui(self):
        # Vars used by the header/status row AND the menu - created
        # first, before anything that references them.
        self.light_mode_var = tk.BooleanVar(value=True)
        self.fps_now_var = tk.StringVar(value="")
        self._fps_chip_var = tk.StringVar(value="30 fps")
        self._session_file_var = tk.StringVar(value="")
        self._session_head_var = tk.StringVar(value="Not recording")
        # ---- settings vars (used by the panels AND the menu) ----
        self.res_var = tk.StringVar(); self.fps_var = tk.IntVar()
        self.face_var = tk.BooleanVar(); self.mirror_var = tk.BooleanVar(value=True); self.pos_var = tk.StringVar(); self.shape_var = tk.StringVar()
        self.size_pct_var = tk.IntVar(); self.mic_var = tk.BooleanVar(); self.out_var = tk.StringVar()
        self.screen_only_var = tk.BooleanVar(); self.speed_var = tk.StringVar(); self.voice_var = tk.StringVar()
        self.filter_var = tk.StringVar(); self.speed_hint_var = tk.StringVar()
        self.click_zoom_var = tk.BooleanVar(); self.zoom_var = tk.StringVar(); self.mouse_fx_var = tk.BooleanVar()
        self.countdown_var = tk.BooleanVar(); self.keys_var = tk.BooleanVar(); self.limit_var = tk.StringVar()
        self.replay_var = tk.BooleanVar(); self.replay_len_var = tk.StringVar(value="60 s")
        self.replay_status_var = tk.StringVar(value="")
        self.area_var = tk.StringVar(); self.region_label_var = tk.StringVar()
        self.gif_var = tk.BooleanVar(); self.noise_var = tk.BooleanVar()
        # live
        self.live_var = tk.BooleanVar(); self.live_platform_var = tk.StringVar()
        self.live_rtmp_var = tk.StringVar(); self.live_key_var = tk.StringVar()
        self.live_remember_var = tk.BooleanVar(); self.live_bitrate_var = tk.StringVar()
        self.live_audio_var = tk.BooleanVar(); self.live_help_var = tk.StringVar()
        self.sys_var = tk.BooleanVar(); self.game_only_var = tk.BooleanVar()
        self.filter_whole_var = tk.BooleanVar()
        self.script_var = tk.BooleanVar(); self.script_autocorrect_var = tk.BooleanVar()
        self.script_live_var = tk.BooleanVar(); self.smart_status_var = tk.StringVar()
        self.smart_next_var = tk.StringVar()
        self.sys_hint_var = tk.StringVar(); self.audio_summary_var = tk.StringVar()
        self._key_visible = False
        self._build_menu()
        # The fps chip in the top bar follows the FPS setting.
        self.fps_var.trace_add(
            "write", lambda *_a: self._fps_chip_var.set("%s fps" % self.fps_var.get()))
        # ---- top bar (52 px): logo + version, timer centre, LIVE + fps + Help right ----
        top = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=52)
        top.pack(fill="x")
        top.pack_propagate(False)
        _tl = ctk.CTkFrame(top, fg_color="transparent")
        _tl.pack(side="left", padx=14, pady=8)
        ctk.CTkLabel(_tl, text="🎮", font=("Segoe UI", 22)).pack(side="left")
        ctk.CTkLabel(_tl, text="Lite Game Recorder", font=("Segoe UI", 16, "bold"), text_color=TEXT).pack(side="left", padx=8)
        ctk.CTkLabel(_tl, text="v2.3", font=("Segoe UI", 11, "bold"), text_color=MUTED,
                     fg_color=PANEL2, corner_radius=999, width=44, height=22).pack(side="left", padx=2)
        _tr = ctk.CTkFrame(top, fg_color="transparent")
        _tr.pack(side="right", padx=14, pady=8)
        self.live_badge = ctk.CTkLabel(_tr, text="○  OFFLINE", font=("Segoe UI", 12, "bold"), text_color=MUTED)
        self.live_badge.pack(side="left", padx=8)
        ctk.CTkLabel(_tr, textvariable=self._fps_chip_var, font=("Segoe UI", 11, "bold"),
                     text_color=GREEN, fg_color=PANEL2, corner_radius=999, width=64, height=24).pack(side="left", padx=4)
        ctk.CTkButton(_tr, text="?", width=36, height=36, fg_color=PANEL2,
                      hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 14, "bold"),
                      corner_radius=10, command=self._show_shortcuts).pack(side="left", padx=4)
        # Centre: the timer, with the red REC dot in front while recording.
        _tc = ctk.CTkFrame(top, fg_color="transparent")
        _tc.place(relx=0.5, rely=0.5, anchor="center")
        self.rec_dot = ctk.CTkLabel(_tc, text="●", font=("Segoe UI", 14), text_color=MUTED)
        self.rec_dot.pack(side="left", padx=(0, 6))
        self.timer_var = tk.StringVar(value="00:00")
        ctk.CTkLabel(_tc, textvariable=self.timer_var, font=("Segoe UI", 26, "bold"), text_color=TEXT).pack(side="left")

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # ---- left icon rail (64 px) ----
        rail = ctk.CTkFrame(main, fg_color=BG, width=64, corner_radius=0)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self._rail_btns = {}
        self._section_name = "Record"
        for icon, name in [("●", "Record"), ("▦", "Library"), ("📷", "Facecam"),
                           ("♪", "Audio"), ("🔴", "Live"), ("📝", "Script"),
                           ("⚙", "Settings")]:
            b = ctk.CTkButton(rail, text=icon, width=48, height=48, corner_radius=12,
                              font=("Segoe UI", 20), fg_color="transparent",
                              hover_color=PANEL2, text_color=MUTED,
                              command=lambda n=name: self._show_app_section(n))
            b.pack(pady=4)
            self._rail_btns[name] = b
        ctk.CTkButton(rail, text="?", width=48, height=48, corner_radius=12,
                      font=("Segoe UI", 20), fg_color="transparent",
                      hover_color=PANEL2, text_color=MUTED,
                      command=self._show_about).pack(side="bottom", pady=(4, 10))

        # ---- left panel (280 px, scrollable): one section at a time ----
        self._panel = ctk.CTkScrollableFrame(main, fg_color=PANEL, width=247,
                                             corner_radius=16)
        self._panel.pack(side="left", fill="y", padx=(8, 0))
        self._panel_frames = {}
        for name in ["Record", "Library", "Facecam", "Audio", "Live", "Script", "Settings"]:
            self._panel_frames[name] = ctk.CTkFrame(self._panel, fg_color="transparent")

        # ---- centre: preview + status line + transport bar ----
        centre_col = ctk.CTkFrame(main, fg_color="transparent")
        centre_col.pack(side="left", fill="both", expand=True, padx=(8, 0))
        preview_box = ctk.CTkFrame(centre_col, fg_color=PANEL, corner_radius=16, border_width=1, border_color=BORDER)
        preview_box.pack(fill="both", expand=True)
        self.preview = ctk.CTkLabel(preview_box, text="Camera preview will appear here\n\nStart recording to see your game + facecam",
                                    font=("Segoe UI", 12), text_color=MUTED, fg_color="#000000", corner_radius=12)
        self.preview.pack(fill="both", expand=True, padx=10, pady=10)

        self.status_var = tk.StringVar(value="Ready — pick your settings, then hit Record (F9)")
        self.size_var = tk.StringVar(value="")
        status_row = ctk.CTkFrame(centre_col, fg_color="transparent")
        status_row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(status_row, textvariable=self.status_var, font=("Segoe UI", 11), text_color=MUTED, wraplength=520, anchor="w").pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(status_row, textvariable=self.fps_now_var, font=("Segoe UI", 11, "bold"), text_color=GREEN).pack(side="right", padx=6)
        ctk.CTkLabel(status_row, textvariable=self.size_var, font=("Segoe UI", 11), text_color=MUTED).pack(side="right")

        # Bottom transport bar (its own dark panel): shortcuts hint
        # left, the big ROUND Record button in the middle (Pause left
        # of it, Save replay right of it), Recordings + Edit video
        # right. One red element (Record), one sky element (Edit).
        # Full-width bottom bar (not inside the centre column):
        # at a 1280 px window the centre is only ~590 px wide and
        # the transport needs ~640 px, so inside the centre the
        # "Edit video" button was clipped to 69 px and the shortcut
        # hint to 58 px.  Spanning the window keeps every button whole.
        transport = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=16, border_width=1, border_color=BORDER)
        transport.pack(fill="x", padx=10, pady=(10, 10), side="bottom")
        # uniform="a" keeps the two side columns the same width,
        # so the Record button sits exactly in the middle.
        transport.grid_columnconfigure(0, weight=1, uniform="a")
        transport.grid_columnconfigure(2, weight=1, uniform="a")
        _bl = ctk.CTkFrame(transport, fg_color="transparent")
        _bl.grid(row=0, column=0, sticky="w", padx=14, pady=12)
        ctk.CTkLabel(_bl, text="F9  Start / Stop\nF10  Pause / Resume\nF11  Save replay\nM  Add chapter",
                     font=("Segoe UI", 11), text_color=MUTED, justify="left").pack(anchor="w")
        _bc = ctk.CTkFrame(transport, fg_color="transparent")
        _bc.grid(row=0, column=1, pady=10)
        self.pause_btn = ctk.CTkButton(_bc, text="⏸", command=self.toggle_pause, state="disabled",
                                       fg_color=PANEL2, hover_color=BORDER, text_color=TEXT,
                                       font=("Segoe UI", 18), width=56, height=56, corner_radius=18)
        self.pause_btn.pack(side="left", padx=6)
        ToolTip(self.pause_btn, "Pause the recording (F10).\nPress it again to carry on — one video file.")
        # A truly round Record button: a labelled 72 px CTkButton
        # renders as a ~93x72 pill (minimum width = text +
        # 2*corner_radius), so the ● glyph lives in a label on top
        # of a textless button (see _round_button). The glyph is
        # ``self.record_btn._glyph``; its look is changed with
        # _round_button_set wherever the old code changed the text.
        self.record_btn = _round_button(
            _bc, "●", ACCENT, ACCENT_HOVER, "white",
            ("Segoe UI", 22, "bold"), size=72, command=self.toggle_record)
        self.record_btn.pack(side="left", padx=4)
        ToolTip(self.record_btn, "Start recording your screen + facecam.\nPress F9 to start, F9 again to stop.")
        ToolTip(self.record_btn._glyph, "Start recording your screen + facecam.\nPress F9 to start, F9 again to stop.")
        self._transport_replay_btn = ctk.CTkButton(_bc, text="💾", command=self._save_replay,
                                                   fg_color=PANEL2, hover_color=BORDER, text_color=TEXT,
                                                   font=("Segoe UI", 18), width=56, height=56, corner_radius=18)
        self._transport_replay_btn.pack(side="left", padx=6)
        ToolTip(self._transport_replay_btn, "Save the last moments as a replay video (F11).\nTurn Instant Replay on in the Session panel first.")
        # v2.4 - tutorial chapter marker: drops a timestamped
        # chapter at the current point in the recording (M key).
        self.chapter_btn = ctk.CTkButton(_bc, text="🔖", command=self._add_chapter, state="disabled",
                                         fg_color=PANEL2, hover_color=BORDER, text_color=TEXT,
                                         font=("Segoe UI", 18), width=56, height=56, corner_radius=18)
        self.chapter_btn.pack(side="left", padx=6)
        ToolTip(self.chapter_btn, "Mark a chapter here (M).\nChapters are saved next to the video and show on the editor timeline, where you can rename them.")
        _br = ctk.CTkFrame(transport, fg_color="transparent")
        _br.grid(row=0, column=2, sticky="e", padx=14, pady=12)
        rec_btn = ctk.CTkButton(_br, text="📂  Recordings", command=self._open_folder,
                                fg_color=PANEL2, hover_color=BORDER, text_color=TEXT,
                                font=("Segoe UI", 12), height=40, width=118, corner_radius=10)
        rec_btn.pack(side="left", padx=4)
        ToolTip(rec_btn, "Open the folder where your videos are saved.")
        edit_btn = ctk.CTkButton(_br, text="✂️  Edit video", command=lambda: self._open_editor(),
                                 fg_color=SKY, hover_color=SKY_HOVER, text_color="#0F1218",
                                 font=("Segoe UI", 12, "bold"), height=40, width=118, corner_radius=999)
        edit_btn.pack(side="left", padx=4)
        ToolTip(edit_btn, "Open the CapCut-style editor: trim, split,\ntext, stickers, templates — then Export.")

        # ---- right panel (300 px, scrollable): Session ----
        right = ctk.CTkScrollableFrame(main, fg_color=PANEL, width=267, corner_radius=16)
        self._right_panel = right
        right.pack(side="right", fill="y", padx=(8, 0))
        # Pack order inside main: the fixed panels take their space
        # first; the expanding centre (preview) gets what is left.
        centre_col.pack_forget()
        centre_col.pack(side="left", fill="both", expand=True, padx=(8, 0))
        b = self._card(right, "⏺  Now recording")
        ctk.CTkLabel(b, textvariable=self._session_head_var, font=("Segoe UI", 11, "bold"), text_color=TEXT, wraplength=260, justify="left").pack(anchor="w")
        ctk.CTkLabel(b, textvariable=self.timer_var, font=("Segoe UI", 22, "bold"), text_color=TEXT).pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(b, text="File", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(b, textvariable=self._session_file_var, font=("Segoe UI", 11), text_color=TEXT, wraplength=260, justify="left").pack(anchor="w")
        ctk.CTkLabel(b, text="Size  •  Speed", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(4, 0))
        _sz = ctk.CTkFrame(b, fg_color="transparent")
        _sz.pack(fill="x")
        ctk.CTkLabel(_sz, textvariable=self.size_var, font=("Segoe UI", 11, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(_sz, textvariable=self.fps_now_var, font=("Segoe UI", 11, "bold"), text_color=GREEN).pack(side="left", padx=10)
        ctk.CTkLabel(b, text="Saves to", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(b, textvariable=self.out_var, font=("Segoe UI", 11), text_color=TEXT, wraplength=260, justify="left").pack(anchor="w")
        b = self._card(right, "📜  Smart Record — live")
        ctk.CTkLabel(b, textvariable=self.smart_next_var, font=("Segoe UI", 11, "bold"), text_color=GREEN, wraplength=260, justify="left").pack(anchor="w")
        ctk.CTkLabel(b, textvariable=self.smart_status_var, font=("Segoe UI", 10), text_color=MUTED, wraplength=260, justify="left").pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(b, text="Set up your script in the Script panel on the left.", font=("Segoe UI", 10), text_color=MUTED, wraplength=260, justify="left").pack(anchor="w", pady=(4, 0))
        b = self._card(right, "🎙️  Sound")
        ctk.CTkLabel(b, textvariable=self.audio_summary_var, font=("Segoe UI", 11, "bold"), text_color=GREEN, wraplength=260, justify="left").pack(anchor="w")
        ctk.CTkLabel(b, textvariable=self.sys_hint_var, font=("Segoe UI", 10), text_color=MUTED, wraplength=260, justify="left").pack(anchor="w", pady=(2, 4))
        ctk.CTkButton(b, text="🔍  Test game sound — record 3 sec", command=self._check_system_audio, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), height=30).pack(fill="x", pady=(0, 6))
        b = self._card(right, "⏪  Instant Replay")
        ctk.CTkSwitch(b, text="⏪  Instant Replay — always recording", variable=self.replay_var, command=self._toggle_replay, font=("Segoe UI", 11, "bold"), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(b, text="Save the last…", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(4, 0))
        ctk.CTkOptionMenu(b, variable=self.replay_len_var, values=["30 s", "60 s", "120 s"], fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 4))
        ctk.CTkButton(b, text="💾  Save replay  (F11)", command=self._save_replay, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), height=30).pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(b, textvariable=self.replay_status_var, font=("Segoe UI", 10), text_color=MUTED, wraplength=260, justify="left").pack(anchor="w")

        # ---- left panel sections (one at a time) ----
        # Record section: capture settings + mouse.
        sec = self._panel_frames["Record"]
        b = self._card(sec, "📹  Capture")
        ctk.CTkLabel(b, text="Quality", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w")
        self._chips(b, self.res_var, [
            ("720p Light", "720p (Light - Recommended)"),
            ("480p Ultra", "480p (Ultra Light - smoothest on weak PCs)"),
            ("1080p", "1080p (Sharper, heavier)"),
            ("Original", "Original (Heaviest)")], per_row=2)
        ctk.CTkLabel(b, text="FPS", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(6, 0))
        self._chips(b, self.fps_var, [("24", 24), ("30", 30), ("60", 60)])
        ctk.CTkLabel(b, text="Record area", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(8, 0))
        ctk.CTkOptionMenu(b, variable=self.area_var, values=["Full Screen", "Region (custom)"], fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 6))
        # Button full-width, label underneath: side by side the
        # two need ~290 px and the card is ~200 px, so the label
        # was clipped to "ion selec...".
        ctk.CTkButton(b, text="Select Region…", command=self._select_region, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), height=30).pack(fill="x")
        ctk.CTkLabel(b, textvariable=self.region_label_var, font=("Segoe UI", 10), text_color=MUTED, wraplength=200, justify="left").pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(b, text="Auto-stop", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(8, 0))
        ctk.CTkOptionMenu(b, variable=self.limit_var, values=["No limit", "1 min", "5 min", "10 min", "30 min", "60 min"], fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 0))
        ctk.CTkSwitch(b, text="Countdown 3-2-1", variable=self.countdown_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=(8, 0))
        ctk.CTkSwitch(b, text="Show shortcuts (Ctrl+C…)", variable=self.keys_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=4)
        ctk.CTkLabel(b, text="Speed", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(8, 0))
        speed_menu = ctk.CTkOptionMenu(b, variable=self.speed_var, values=["0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x", "4x"], fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11), command=lambda v: self._update_speed_hint())
        speed_menu.pack(fill="x", pady=(2, 4))
        ctk.CTkLabel(b, textvariable=self.speed_hint_var, font=("Segoe UI", 10), text_color=MUTED, wraplength=240).pack(anchor="w")
        ctk.CTkSwitch(b, text="Screen record ONLY", variable=self.screen_only_var, command=self._on_screen_only, font=("Segoe UI", 11, "bold"), text_color=AMBER, fg_color=PANEL2, progress_color=AMBER).pack(anchor="w", pady=(8, 0))
        b = self._card(sec, "🖱️  Mouse")
        ctk.CTkSwitch(b, text="🖱️  Click Zoom (auto)", variable=self.click_zoom_var, font=("Segoe UI", 11, "bold"), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(b, text="Zoom level", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(6, 0))
        ctk.CTkOptionMenu(b, variable=self.zoom_var, values=["1.5x", "1.8x", "2x", "2.5x", "3x"], fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 4))
        ctk.CTkSwitch(b, text="Click ripple + cursor ring", variable=self.mouse_fx_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=2)
        ctk.CTkSwitch(b, text="Also save GIF copy", variable=self.gif_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=2)

        # Library section: recent recordings.
        sec = self._panel_frames["Library"]
        recent_head = ctk.CTkFrame(sec, fg_color="transparent")
        recent_head.pack(fill="x", pady=(12, 2))
        ctk.CTkLabel(recent_head, text="Recent recordings", font=("Segoe UI", 13, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkButton(recent_head, text="↻  Refresh", command=self._refresh_recent, fg_color="transparent",
                      hover_color=PANEL2, text_color=MUTED, font=("Segoe UI", 11), width=80, height=26).pack(side="right")
        self.recent_frame = ctk.CTkScrollableFrame(sec, fg_color=PANEL, corner_radius=12, height=260, border_width=1, border_color=BORDER)
        self.recent_frame.pack(fill="x")
        ctk.CTkButton(sec, text="📂  Open recordings folder", command=self._open_folder, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), height=30).pack(fill="x", pady=(10, 0))

        # Facecam section.
        sec = self._panel_frames["Facecam"]
        b = self._card(sec, "📷  Facecam")
        ctk.CTkSwitch(b, text="Facecam on", variable=self.face_var, font=("Segoe UI", 12, "bold"), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w")
        ctk.CTkSwitch(b, text="Mirror facecam (like a selfie)", variable=self.mirror_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(b, text="If your face looks flipped in the video, keep this on. Turn it off to show yourself as a viewer sees you.", font=("Segoe UI", 10), text_color=MUTED, wraplength=240).pack(anchor="w")
        ctk.CTkLabel(b, text="Position", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(8, 0))
        ctk.CTkOptionMenu(b, variable=self.pos_var, values=["Bottom Right", "Bottom Left", "Top Right", "Top Left"], fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(b, text="Shape", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w")
        ctk.CTkOptionMenu(b, variable=self.shape_var, values=["Rounded", "Circle", "Rectangle"], fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(b, text="Face size", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(6, 0))
        ctk.CTkSlider(b, variable=self.size_pct_var, from_=14, to=35, fg_color=PANEL2, progress_color=ACCENT, button_color=TEXT).pack(fill="x")
        ctk.CTkLabel(b, text="Character filter — you on camera", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(8, 0))
        ctk.CTkOptionMenu(b, variable=self.filter_var, values=CHARACTER_FILTERS, fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 4))
        ctk.CTkLabel(b, text="LING = the anime guy with black hair + glasses from your picture. It draws his hair and glasses on your face — a character look, not a face-swap.", font=("Segoe UI", 10), text_color=MUTED, wraplength=240).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(b, text="✅  Facecam only — your game stays normal, only your face in the corner gets the filter.", font=("Segoe UI", 11, "bold"), text_color=GREEN, wraplength=240).pack(anchor="w", pady=(2, 0))

        # Audio section.
        sec = self._panel_frames["Audio"]
        b = self._card(sec, "🎙️  Audio")
        self.mic_switch = ctk.CTkSwitch(b, text="Microphone on", variable=self.mic_var, command=self._update_audio_summary, font=("Segoe UI", 12, "bold"), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT)
        self.mic_switch.pack(anchor="w")
        ctk.CTkSwitch(b, text="🎮  System audio — game sound", variable=self.sys_var, command=self._update_audio_summary, font=("Segoe UI", 12, "bold"), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=(6, 0))
        ctk.CTkSwitch(b, text="Game sound ONLY  (no mic)", variable=self.game_only_var, command=self._on_game_only, font=("Segoe UI", 11, "bold"), text_color=AMBER, fg_color=PANEL2, progress_color=AMBER).pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(b, textvariable=self.audio_summary_var, font=("Segoe UI", 11, "bold"), text_color=GREEN, wraplength=240).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(b, textvariable=self.sys_hint_var, font=("Segoe UI", 10), text_color=MUTED, wraplength=240).pack(anchor="w", pady=(2, 6))
        ctk.CTkButton(b, text="🔍  Test game sound — record 3 sec", command=self._check_system_audio, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), height=30).pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(b, text="Voice changer (mic only, applied after recording)", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(8, 0))
        ctk.CTkOptionMenu(b, variable=self.voice_var, values=["Off", "Deep", "High (Chipmunk)", "Echo", "Robot"], fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11), command=self._on_voice_change).pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(b, text="Change it any time — even while recording. The new voice starts from that moment.", font=("Segoe UI", 10), text_color=MUTED, wraplength=240).pack(anchor="w")
        ctk.CTkSwitch(b, text="Mic noise reduction", variable=self.noise_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=2)

        # Script section (Smart Record).
        sec = self._panel_frames["Script"]
        b = self._card(sec, "📜  Script — Smart Record")
        ctk.CTkSwitch(b, text="Smart Record — check my speech against the script", variable=self.script_var, font=("Segoe UI", 12, "bold"), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(b, text="Paste your script below. While you speak, the app listens and flags words you say wrong.", font=("Segoe UI", 10), text_color=MUTED, wraplength=240).pack(anchor="w", pady=(4, 6))
        self.script_textbox = ctk.CTkTextbox(b, height=110, fg_color=PANEL2, border_color=BORDER, text_color=TEXT, font=("Segoe UI", 11))
        self.script_textbox.pack(fill="x")
        row = ctk.CTkFrame(b, fg_color="transparent"); row.pack(fill="x", pady=(6, 0))
        # width=0 + expand: the 140 px default makes the two
        # buttons ask for 286 px together and the second one was
        # clipped in the ~220 px card.
        ctk.CTkButton(row, text="📂 Load .txt…", command=self._load_script_file, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), height=28, width=0).pack(side="left", expand=True, fill="x")
        ctk.CTkButton(row, text="▶ Test with example", command=self._test_script_check, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), height=28, width=0).pack(side="left", padx=6, expand=True, fill="x")
        ctk.CTkSwitch(b, text="Auto-correct captions to the script", variable=self.script_autocorrect_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=(6, 2))
        ctk.CTkSwitch(b, text="Live check while recording", variable=self.script_live_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=2)
        ctk.CTkLabel(b, textvariable=self.smart_next_var, font=("Segoe UI", 11, "bold"), text_color=GREEN, wraplength=240).pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(b, textvariable=self.smart_status_var, font=("Segoe UI", 10), text_color=MUTED, wraplength=240).pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(b, text="Needs a speech engine: faster-whisper (offline, in requirements-smart.txt) or Google speech (online). Your voice is NOT changed — only the captions are auto-corrected.", font=("Segoe UI", 10), text_color=MUTED, wraplength=240).pack(anchor="w", pady=(6, 0))

        # Live section.
        sec = self._panel_frames["Live"]
        b = self._card(sec, "🔴  Go Live — any platform")
        ctk.CTkSwitch(b, text="Go Live when recording starts", variable=self.live_var, command=self._on_live_toggle, font=("Segoe UI", 12, "bold"), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(b, text="Platform", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(8, 0))
        ctk.CTkOptionMenu(b, variable=self.live_platform_var, values=list(LIVE_PLATFORMS.keys()), fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11), command=self._on_platform_change).pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(b, text="RTMP URL", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w")
        ctk.CTkEntry(b, textvariable=self.live_rtmp_var, fg_color=PANEL2, border_color=BORDER, text_color=TEXT, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(b, text="Stream key  (never share this)", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w")
        key_row = ctk.CTkFrame(b, fg_color="transparent"); key_row.pack(fill="x", pady=(2, 4))
        self.live_key_entry = ctk.CTkEntry(key_row, textvariable=self.live_key_var, show="•", fg_color=PANEL2, border_color=BORDER, text_color=TEXT, font=("Segoe UI", 11))
        self.live_key_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(key_row, text="Show", command=self._toggle_key_visible, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), width=52, height=28).pack(side="left", padx=6)
        ctk.CTkLabel(b, textvariable=self.live_help_var, font=("Segoe UI", 10), text_color=MUTED, wraplength=240).pack(anchor="w", pady=(2, 6))
        row = ctk.CTkFrame(b, fg_color="transparent"); row.pack(fill="x")
        ctk.CTkLabel(row, text="Bitrate", font=("Segoe UI", 11), text_color=MUTED).pack(side="left")
        ctk.CTkOptionMenu(row, variable=self.live_bitrate_var, values=["2500k", "4500k", "6000k", "8000k"], fg_color=PANEL2, button_color=PANEL2, text_color=TEXT, font=("Segoe UI", 11), width=110).pack(side="right")
        ctk.CTkSwitch(b, text="Include audio in the live stream (mic + game sound if on)", variable=self.live_audio_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=(6, 2))
        ctk.CTkSwitch(b, text="Remember stream key on this PC", variable=self.live_remember_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w", pady=2)
        ctk.CTkLabel(b, text="Needs FFmpeg. Your key is stored only on this PC, only if you tick Remember.", font=("Segoe UI", 10), text_color=MUTED, wraplength=240).pack(anchor="w", pady=(6, 0))

        # Settings section.
        sec = self._panel_frames["Settings"]
        b = self._card(sec, "⚙️  Settings")
        ctk.CTkSwitch(b, text="Light mode — weak laptop (720p max, less CPU)", variable=self.light_mode_var, font=("Segoe UI", 11), text_color=TEXT, fg_color=PANEL2, progress_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(b, text="Save to", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(8, 0))
        ctk.CTkEntry(b, textvariable=self.out_var, fg_color=PANEL2, border_color=BORDER, text_color=TEXT, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 6))
        ctk.CTkButton(b, text="Browse…", command=self._browse, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), height=30).pack(fill="x")
        ctk.CTkButton(b, text="⌨️  Keyboard shortcuts", command=self._show_shortcuts, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), height=30).pack(fill="x", pady=(8, 0))
        ctk.CTkButton(b, text="ℹ️  About Lite Game Recorder", command=self._show_about, fg_color=PANEL2, hover_color=BORDER, text_color=TEXT, font=("Segoe UI", 11), height=30).pack(fill="x", pady=(4, 0))
        ctk.CTkButton(b, text="🗑  Uninstall app…", command=self._uninstall_app, fg_color="transparent", hover_color="#3a2020", text_color="#ff8080", border_color="#5a2a2a", border_width=1, font=("Segoe UI", 11), height=30).pack(fill="x", pady=(8, 0))

        self._show_app_section("Record")
        self._update_session_card()
    # ---------- live helpers ----------
    def _on_platform_change(self, value):
        if value in LIVE_PLATFORMS and value != "Custom":
            self.live_rtmp_var.set(LIVE_PLATFORMS[value])
        self.live_help_var.set(LIVE_HELP.get(value, ""))

    def _toggle_key_visible(self):
        self._key_visible = not self._key_visible
        self.live_key_entry.configure(show="" if self._key_visible else "•")

    def _on_live_toggle(self):
        on = bool(self.live_var.get())
        if on and not _ffmpeg_available():
            self.live_var.set(False)
            messagebox.showwarning("FFmpeg needed for Live", "Live streaming needs FFmpeg installed (free, ffmpeg.org).\n\nRecording still works without it — install FFmpeg, then turn Live back on.")
            return
        if on and not (self.live_rtmp_var.get().strip() and self.live_key_var.get().strip()):
            self.status_var.set("Live is on — paste your RTMP URL and stream key in the Live card first")
        self._update_live_badge()

    # ---------- audio helpers (v2.1) ----------
    def _update_audio_summary(self):
        only = bool(self.screen_only_var.get())
        game_only = bool(self.game_only_var.get())
        mic = bool(self.mic_var.get()) and not only and not game_only
        sys_on = (bool(self.sys_var.get()) or game_only) and not only
        if only:
            txt = "Audio: none — video only"
        elif mic and sys_on:
            txt = "Audio: 🎙️ Mic + 🎮 Game sound"
        elif sys_on:
            txt = "Audio: 🎮 Game sound only"
        elif mic:
            txt = "Audio: 🎙️ Mic only"
        else:
            txt = "Audio: none — video only"
        self.audio_summary_var.set(txt)
        self.sys_hint_var.set(system_audio_setup_hint())

    def _on_game_only(self):
        if bool(self.game_only_var.get()):
            self.sys_var.set(True)
        self._update_audio_summary()

    def _on_voice_change(self, value=None):
        """Voice menu changed. While recording, the new voice starts
        from this moment (the recorder stamps the change); otherwise
        it is just the voice for the next recording."""
        voice = self.voice_var.get()
        if self.recorder and self.recorder.recording and self.recorder.mic_active:
            self.recorder.set_voice(voice)
            self.status_var.set(f"Voice: {voice} — applies from now on in this recording.")
        elif self.recorder and self.recorder.recording:
            self.status_var.set("Voice change saved — turn the mic on for it to apply.")

    def _check_system_audio(self):
        """Real test: record 3 seconds of game sound and measure how
        loud it is, so the user knows BEFORE recording whether it works."""
        import tempfile
        args, name, hint = detect_system_audio({"system_audio_source": ""})
        if not args:
            messagebox.showwarning("System audio — needs setup", hint or "No system-audio source found on this PC.")
            return
        ff = find_ffmpeg()
        if not ff:
            messagebox.showwarning("System audio — needs FFmpeg",
                "A game-sound source was found (%s), but FFmpeg is missing, so nothing can be captured.\n\n"
                "Run the installer again — it downloads FFmpeg for you — or install FFmpeg from ffmpeg.org and restart the app." % name)
            return
        tmp = str(Path(tempfile.gettempdir()) / "lgr_sys_test.wav")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        self.sys_hint_var.set("Testing game sound — play something loud for 3 seconds…")
        self.update()
        try:
            subprocess.run([ff, "-y", "-t", "3", "-vn"] + args +
                           ["-c:a", "pcm_s16le", "-ar", "44100", "-ac", "1", tmp],
                           capture_output=True, timeout=15, **_quiet_subprocess_kwargs())
        except Exception as e:
            messagebox.showerror("System audio test failed", str(e))
            return
        peak = 0.0
        try:
            with wave.open(tmp, "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            if raw:
                data = np.frombuffer(raw, dtype=np.int16).astype(float) / 32768.0
                peak = float(np.max(np.abs(data))) if len(data) else 0.0
        except Exception:
            peak = 0.0
        if peak > 0.02:
            self.sys_hint_var.set("Game sound works — last test: %.0f%% volume." % (peak * 100))
            messagebox.showinfo("System audio — works!",
                "Game sound WORKS on this PC.\n\nSource: %s\nCaptured 3 seconds, loudest sound: %.0f%% of full volume.\n\n"
                "Turn on 'System audio — game sound', then press Record and play." % (name, peak * 100))
        elif os.path.exists(tmp):
            self.sys_hint_var.set("Last test captured silence — play something and test again.")
            messagebox.showwarning("System audio — silence",
                "The source opened (%s) but captured SILENCE.\n\n"
                "Play some music or game sound and test again. If it is still silent, open Sound settings and make sure Stereo Mix (or VB-Cable) is enabled AND is the default playback device." % name)
        else:
            messagebox.showwarning("System audio — failed",
                "Could not capture from %s. %s" % (name, hint or ""))

    # ---------- smart script helpers (v2.3) ----------
    def _script_text(self):
        try:
            return self.script_textbox.get("1.0", "end").strip()
        except Exception:
            return ""

    def _load_script_file(self):
        d = filedialog.askopenfilename(title="Load script", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if d:
            try:
                text = Path(d).read_text(encoding="utf-8", errors="ignore")
                self.script_textbox.delete("1.0", "end")
                self.script_textbox.insert("1.0", text)
                self.smart_status_var.set(f"Loaded script from {Path(d).name} ({len(text.split())} words)")
            except Exception as e:
                messagebox.showerror("Could not load script", str(e))

    def _test_script_check(self):
        script = self._script_text() or "Hi, welcome back to my channel!"
        heard = "hi elcom eback to my chnnel"
        res = compare_script(script, heard)
        lines = [f"Script: {script}", f"You said (example): {heard}", "",
                 f"Accuracy: {res['accuracy']:.0f}%  ({res['correct']}/{res['total']} words correct)", "",
                 "Mistakes:"]
        if res["mistakes"]:
            for m in res["mistakes"]:
                lines.append(f"  - word {m['position']}: script says '{m['expected']}', you said '{m['heard']}'")
        else:
            lines.append("  (none)")
        lines += ["", f"Auto-corrected captions would say: {res['corrected_text']}"]
        messagebox.showinfo("Smart check — example", "\n".join(lines))

    def _smart_tick(self):
        try:
            if self.recorder and self.recorder.recording and getattr(self.recorder, "smart_checker", None):
                chk = self.recorder.smart_checker
                self.smart_next_var.set(f"Now say: {chk.next_phrase()}")
                self.smart_status_var.set(chk.summary() + (f"  •  Last heard: \"{chk.last_heard}\"" if chk.last_heard else "  •  Listening…"))
            elif bool(self.script_var.get()):
                txt = self._script_text()
                words = txt.split()
                self.smart_next_var.set(f"Ready — {len(words)} words in your script. Press Record and say the first line.")
                if not self.smart_status_var.get():
                    self.smart_status_var.set("Smart Record is on. Mistakes will be flagged live and in a report after.")
        except Exception:
            pass
        self.after(600, self._smart_tick)

    def _update_live_badge(self):
        # A dead stream (streamer.failed) must not show as LIVE.
        if (self.recorder and self.recorder.recording and self.recorder.streamer is not None
                and not getattr(self.recorder.streamer, "failed", False)):
            self.live_badge.configure(text="●  LIVE", text_color=ACCENT)
            self._live_on = True
        elif bool(self.live_var.get()):
            self.live_badge.configure(text="●  LIVE ARMED", text_color=AMBER)
            self._live_on = False
        else:
            self.live_badge.configure(text="○  OFFLINE", text_color=MUTED)
            self._live_on = False

    # ---------- recent recordings ----------
    def _refresh_recent(self):
        for w in self.recent_frame.winfo_children():
            w.destroy()
        try:
            folder = Path(self.out_var.get() or str(DEFAULT_OUTPUT))
            files = sorted(folder.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)[:6] if folder.is_dir() else []
        except Exception:
            files = []
        if not files:
            ctk.CTkLabel(self.recent_frame, text="No recordings yet — your videos will show up here", font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", padx=8, pady=8)
            return
        for f in files:
            try:
                mb = f.stat().st_size / (1024 * 1024)
                label = f"{f.name}   •   {mb:.1f} MB"
            except Exception:
                label = f.name
            row = ctk.CTkFrame(self.recent_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)
            btn = ctk.CTkButton(row, text=label, anchor="w", fg_color="transparent", hover_color=PANEL2,
                                text_color=TEXT, font=("Segoe UI", 11), height=30,
                                command=lambda p=f: self._open_file(p))
            btn.pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="✏️", width=34, height=30,
                          fg_color="transparent", hover_color=PANEL2,
                          font=("Segoe UI", 12),
                          command=lambda p=f: self._rename_recording(p)).pack(side="right", padx=(2, 0))
            ctk.CTkButton(row, text="📄", width=34, height=30,
                          fg_color="transparent", hover_color=PANEL2,
                          font=("Segoe UI", 12),
                          command=lambda p=f: self._duplicate_recording(p)).pack(side="right", padx=(2, 0))
            ctk.CTkButton(row, text="🗑", width=34, height=30,
                          fg_color="transparent", hover_color="#3a2020",
                          text_color="#ff8080", font=("Segoe UI", 12),
                          command=lambda p=f: self._delete_recording(p)).pack(side="right", padx=(2, 0))
            ctk.CTkButton(row, text="✂️ Edit", width=64, height=30,
                          fg_color=ACCENT, hover_color=ACCENT_HOVER,
                          font=("Segoe UI", 11, "bold"),
                          command=lambda p=f: self._open_editor(str(p))).pack(side="right", padx=(4, 0))

    def _rename_recording(self, path):
        """Rename a recording (and its script/captions sidecars)."""
        from tkinter import simpledialog
        new = simpledialog.askstring("Rename recording",
                                     "New name for this video (without .mp4):",
                                     initialvalue=Path(path).stem)
        if not new or not new.strip():
            return
        new = new.strip()
        if any(c in new for c in '<>:"/\\|?*'):
            messagebox.showerror("Rename recording",
                                 "That name has a character Windows does not allow in file names.")
            return
        dest = Path(path).with_name(new + ".mp4")
        if dest.exists() and dest != Path(path):
            messagebox.showerror("Rename recording", "A video with that name already exists.")
            return
        try:
            Path(path).rename(dest)
            for suffix in ("_script.txt", "_captions.srt"):
                side = Path(str(path).replace(".mp4", suffix))
                if side.exists():
                    side.rename(Path(str(dest).replace(".mp4", suffix)))
            self._refresh_recent()
            self.status_var.set(f"Renamed to {dest.name}")
        except Exception as e:
            messagebox.showerror("Rename recording", str(e))

    def _duplicate_recording(self, path):
        """Make a copy of a recording (and its script/captions
        sidecars) called "<name> copy.mp4" — or " copy 2", " copy 3"
        if that name is already taken. Returns the new path, or
        None if the copy failed."""
        src = Path(path)
        stem = src.stem
        dest = src.with_name(stem + " copy.mp4")
        n = 2
        while dest.exists():
            dest = src.with_name("%s copy %d.mp4" % (stem, n))
            n += 1
        try:
            shutil.copy2(src, dest)
            for suffix in ("_script.txt", "_captions.srt"):
                side = Path(str(src).replace(".mp4", suffix))
                if side.exists():
                    shutil.copy2(side, Path(str(dest).replace(".mp4", suffix)))
            self._refresh_recent()
            self.status_var.set(f"Copied to {dest.name}")
            return dest
        except Exception as e:
            messagebox.showerror("Duplicate recording", str(e))
            return None

    def _delete_recording(self, path):
        """Delete a recording (and its script/captions sidecars)."""
        if not messagebox.askyesno("Delete recording",
                                   f"Delete {Path(path).name}?\n\nThis cannot be undone."):
            return
        try:
            Path(path).unlink(missing_ok=True)
            for suffix in ("_script.txt", "_captions.srt"):
                side = Path(str(path).replace(".mp4", suffix))
                if side.exists():
                    side.unlink()
            self._refresh_recent()
            self.status_var.set("Recording deleted.")
        except Exception as e:
            messagebox.showerror("Delete recording", str(e))

    def _open_editor(self, path=None):
        """Open the CapCut-style video editor, optionally with one
        recording already loaded. Recordings are never touched by
        the editor - Export saves a new *_edited.mp4 next to it."""
        try:
            from editor import VideoEditor
        except Exception as exc:
            messagebox.showerror("Video Editor",
                                 "Could not open the editor: %s" % exc)
            return
        try:
            VideoEditor(self, initial_path=path,
                        on_exported=self._refresh_recent)
        except Exception as exc:
            messagebox.showerror("Video Editor",
                                 "Could not open the editor: %s" % exc)

    def _open_file(self, path):
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path)])
            else:
                subprocess.run(["xdg-open", str(path)])
        except Exception as e:
            messagebox.showerror("Could not open file", str(e))


    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get() or str(DEFAULT_OUTPUT))
        if d:
            self.out_var.set(d)
            self._refresh_recent()
            self._update_session_card()

    def _uninstall_app(self):
        """Remove the installed app + its Desktop/Start Menu icons.
        Recordings are never deleted. Runs the uninstaller next to
        this app (or next to the installed exe) and closes the app."""
        if self.recorder and self.recorder.recording:
            messagebox.showwarning("Recording in progress",
                                   "Stop the recording first, then uninstall.")
            return
        if not messagebox.askyesno(
                "Uninstall Lite Game Recorder",
                "Remove the installed app and its Desktop + Start Menu icons?\n\n"
                "Your recordings will NOT be deleted."):
            return
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))
        bat = os.path.join(base, "Uninstall Lite Game Recorder.bat")
        if os.path.exists(bat):
            try:
                if sys.platform == "win32":
                    os.startfile(bat)
                else:
                    subprocess.Popen(["bash", bat])
            except Exception as exc:
                messagebox.showerror("Could not start uninstaller", str(exc))
                return
            self.destroy()
            return
        messagebox.showinfo(
            "Uninstall",
            "The uninstaller was not found next to the app.\n\n"
            "To uninstall by hand, delete:\n"
            "  %LOCALAPPDATA%\\Programs\\LiteGameRecorder\n"
            "and the 'Lite Game Recorder' icons on your Desktop\n"
            "and in the Start Menu. Your recordings stay safe.")

    def _open_folder(self):
        try:
            p = ensure_output_dir(self.out_var.get() or str(DEFAULT_OUTPUT))
            self.out_var.set(str(p))
        except Exception as e:
            messagebox.showerror("Could not open recordings folder", str(e))
            return
        if sys.platform == "win32":
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)])
        else:
            subprocess.run(["xdg-open", str(p)])

    def _parse_speed(self):
        try:
            return float(str(self.speed_var.get()).replace("x", "").strip()) or 1.0
        except Exception:
            return 1.0

    def _parse_zoom(self):
        try:
            return float(str(self.zoom_var.get()).replace("x", "").strip()) or 1.8
        except Exception:
            return 1.8

    def _parse_limit(self):
        v = str(self.limit_var.get())
        if v == "No limit":
            return 0
        try:
            return int(v.split()[0])
        except Exception:
            return 0

    def _select_region(self):
        self.withdraw()
        ov = ctk.CTkToplevel(self)
        ov.attributes("-fullscreen", True)
        try:
            ov.attributes("-alpha", 0.35)
        except Exception:
            pass
        ov.attributes("-topmost", True)
        ov.configure(fg_color="black")
        canvas = tk.Canvas(ov, bg="black", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        canvas.create_text(40, 30, anchor="w", fill="white", font=("Segoe UI", 14, "bold"),
                           text="Drag to select the area to record — Esc to cancel")
        state = {"root": None, "widget": None, "rect": None}

        def down(e):
            state["root"] = (e.x_root, e.y_root); state["widget"] = (e.x, e.y)

        def drag(e):
            if state["root"] is None:
                return
            if state["rect"]:
                canvas.delete(state["rect"])
            x0, y0 = state["widget"]
            state["rect"] = canvas.create_rectangle(x0, y0, e.x, e.y, outline="#ffd166", width=2)

        def up(e):
            if state["root"] is None:
                ov.destroy(); self.deiconify(); return
            rx, ry = state["root"]
            x, y = min(rx, e.x_root), min(ry, e.y_root)
            w, h = abs(e.x_root - rx), abs(e.y_root - ry)
            ov.destroy(); self.deiconify()
            if w >= 50 and h >= 50:
                self.cfg["region"] = [int(x), int(y), int(w), int(h)]
                self.area_var.set("Region (custom)")
                self.region_label_var.set(f"{w}x{h} at {x},{y}")
                save_config(self.cfg)
                self.status_var.set(f"Region set: {w}x{h} — recordings will capture only that area")
            else:
                self.status_var.set("Region too small — cancelled")

        def cancel(e):
            ov.destroy(); self.deiconify()

        ov.bind("<ButtonPress-1>", down); ov.bind("<B1-Motion>", drag)
        ov.bind("<ButtonRelease-1>", up); ov.bind("<Escape>", cancel)
        ov.focus_force()

    def _update_speed_hint(self):
        s = self._parse_speed()
        out = 50 / s
        out_txt = f"{out:.0f}" if abs(out - round(out)) < 0.05 else f"{out:.1f}"
        if s == 1.0:
            self.speed_hint_var.set("1x = real time: record 50 sec → video is 50 sec")
        elif s > 1.0:
            self.speed_hint_var.set(f"Fast: record 50 sec → video is {out_txt} sec")
        else:
            self.speed_hint_var.set(f"Slow motion: record 50 sec → video is {out_txt} sec")

    def _on_screen_only(self):
        only = bool(self.screen_only_var.get())
        if only:
            self._release_idle_cap()
            self.preview.configure(image=None, text="Screen-only mode: facecam and all audio are OFF")
        self._update_audio_summary()

    def _load_cfg_to_ui(self):
        c = self.cfg
        _res = str(c.get("resolution", ""))
        if _res.startswith("480p"):
            _res = "480p (Ultra Light - smoothest on weak PCs)"
        elif _res.startswith("1080p"):
            _res = "1080p (Sharper, heavier)"
        elif _res.startswith("Original"):
            _res = "Original (Heaviest)"
        else:
            _res = "720p (Light - Recommended)"
        self.res_var.set(_res); self.fps_var.set(int(c["fps"]))
        self.light_mode_var.set(bool(c.get("light_mode", True)))
        self.face_var.set(bool(c["facecam"])); self.mirror_var.set(bool(c.get("mirror_facecam", True))); self.pos_var.set(c["facecam_pos"])
        self.shape_var.set(c["facecam_shape"]); self.size_pct_var.set(int(c["facecam_size"]))
        self.mic_var.set(bool(c["mic"]) and HAS_MIC)
        self.sys_var.set(bool(c.get("system_audio", False)))
        self.game_only_var.set(bool(c.get("game_sound_only", False)))
        self.out_var.set(c["output_dir"])
        self.speed_var.set(f"{float(c.get('speed', 1.0)):g}x")
        self.voice_var.set(c.get("voice", "Off"))
        self.filter_var.set(c.get("video_filter", "None"))
        # Facecam-only filter: always off, even if an old config had it on.
        self.filter_whole_var.set(False)
        self.script_var.set(bool(c.get("script_enabled", False)))
        self.script_autocorrect_var.set(bool(c.get("script_autocorrect", True)))
        self.script_live_var.set(bool(c.get("script_live_check", True)))
        try:
            self.script_textbox.delete("1.0", "end")
            self.script_textbox.insert("1.0", c.get("script_text", "Hi, welcome back to my channel!"))
        except Exception:
            pass
        self.screen_only_var.set(bool(c.get("screen_only", False)))
        self.click_zoom_var.set(bool(c.get("click_zoom", True)))
        self.zoom_var.set(f"{float(c.get('zoom_level', 1.8)):g}x")
        self.mouse_fx_var.set(bool(c.get("mouse_fx", True)))
        self.countdown_var.set(bool(c.get("countdown", True)))
        self.keys_var.set(bool(c.get("keystrokes", False)))
        self.replay_var.set(bool(c.get("replay_enabled", False)))
        self.replay_len_var.set(f"{int(c.get('replay_seconds', 60))} s")
        lim = int(c.get("record_limit", 0) or 0)
        self.limit_var.set("No limit" if lim == 0 else f"{lim} min")
        self.area_var.set(c.get("area", "Full Screen"))
        reg = c.get("region")
        self.region_label_var.set(f"{reg[2]}x{reg[3]} at {reg[0]},{reg[1]}" if reg else "No region selected yet")
        self.gif_var.set(bool(c.get("gif", False)))
        self.noise_var.set(bool(c.get("noise_reduction", False)))
        # live
        self.live_var.set(bool(c.get("live_enabled", False)))
        self.live_platform_var.set(c.get("live_platform", "YouTube"))
        self.live_rtmp_var.set(c.get("live_rtmp_url", LIVE_PLATFORMS["YouTube"]))
        self.live_key_var.set(c.get("live_stream_key", ""))
        self.live_remember_var.set(bool(c.get("live_remember_key", False)))
        self.live_bitrate_var.set(str(c.get("live_bitrate", "4500k")))
        self.live_audio_var.set(bool(c.get("live_audio", True)))
        self.live_help_var.set(LIVE_HELP.get(c.get("live_platform", "YouTube"), ""))
        self._update_speed_hint()
        self._on_screen_only()
        self._update_audio_summary()
        self._update_live_badge()
        self._update_session_card()

    def _read_ui_to_cfg(self):
        only = bool(self.screen_only_var.get())
        game_only = bool(self.game_only_var.get())
        sys_on = (bool(self.sys_var.get()) or game_only) and not only
        self.cfg.update({
            "output_dir": self.out_var.get().strip() or str(DEFAULT_OUTPUT),
            "resolution": self.res_var.get(),
            "fps": int(self.fps_var.get()),
            "light_mode": bool(self.light_mode_var.get()),
            "facecam": bool(self.face_var.get()) and not only,
            "mirror_facecam": bool(self.mirror_var.get()),
            "facecam_pos": self.pos_var.get(),
            "facecam_shape": self.shape_var.get(),
            "facecam_size": int(self.size_pct_var.get()),
            "mic": bool(self.mic_var.get()) and not only and not game_only,
            "system_audio": bool(sys_on),
            "game_sound_only": bool(game_only),
            "system_audio_source": self.cfg.get("system_audio_source", ""),
            "speed": self._parse_speed(),
            "voice": self.voice_var.get(),
            "video_filter": self.filter_var.get(),
            "filter_whole_video": False,  # facecam only, never whole video
            "script_enabled": bool(self.script_var.get()),
            "script_text": self._script_text(),
            "script_autocorrect": bool(self.script_autocorrect_var.get()),
            "script_live_check": bool(self.script_live_var.get()),
            "screen_only": only,
            "click_zoom": bool(self.click_zoom_var.get()),
            "zoom_level": self._parse_zoom(),
            "mouse_fx": bool(self.mouse_fx_var.get()),
            "countdown": bool(self.countdown_var.get()),
            "keystrokes": bool(self.keys_var.get()),
            "replay_enabled": bool(self.replay_var.get()),
            "replay_seconds": self._replay_seconds(),
            "record_limit": self._parse_limit(),
            "area": self.area_var.get(),
            "gif": bool(self.gif_var.get()),
            "noise_reduction": bool(self.noise_var.get()),
            "live_enabled": bool(self.live_var.get()),
            "live_platform": self.live_platform_var.get(),
            "live_rtmp_url": self.live_rtmp_var.get().strip(),
            "live_stream_key": self.live_key_var.get(),
            "live_remember_key": bool(self.live_remember_var.get()),
            "live_bitrate": self.live_bitrate_var.get(),
            "live_audio": bool(self.live_audio_var.get()),
        })
        save_config(self.cfg)
        return self.cfg

    def _release_idle_cap(self):
        if self._idle_cap is not None:
            try:
                self._idle_cap.release()
            except Exception:
                pass
            self._idle_cap = None

    # ---------- recording actions ----------
    # ---------- Instant Replay ----------
    def _replay_seconds(self):
        try:
            return int(str(self.replay_len_var.get()).split()[0])
        except Exception:
            return 60

    def _toggle_replay_menu(self):
        # Menu items can't flip a switch, so flip it here first.
        self.replay_var.set(not self.replay_var.get())
        self._toggle_replay()

    def _toggle_replay(self):
        if self.recorder and self.recorder.recording:
            messagebox.showinfo("Instant Replay", "Stop the recording first — Replay runs when you are not recording.")
            self.replay_var.set(False)
            return
        if not self.replay_var.get():
            if self.recorder is not None and getattr(self.recorder, "replay", None) is not None:
                self.recorder.stop_replay()
            self.replay_status_var.set("")
            self.status_var.set("Instant Replay off.")
            return
        if self.recorder is None:
            self.recorder = Recorder(self._read_ui_to_cfg(), on_status=self._on_status)
        self._release_idle_cap()
        ok = self.recorder.start_replay(self._replay_seconds())
        if not ok:
            self.replay_var.set(False)
            self.replay_status_var.set("")
            messagebox.showerror("Instant Replay", "Could not start Instant Replay (screen capture failed).")
            return
        self.status_var.set(f"⏪ Instant Replay on — playing as normal, press F11 to save the last {self._replay_seconds()} s.")
        self._update_replay_status()

    def _save_replay(self):
        if self.recorder is None or getattr(self.recorder, "replay", None) is None:
            messagebox.showinfo("Instant Replay", "Turn Instant Replay on first (Capture card) — then it records in the background and F11 saves the last moments.")
            return
        ok, note = self.recorder.save_replay()
        if ok:
            self.status_var.set("⏪ " + note)
            self._refresh_recent()
        else:
            messagebox.showinfo("Instant Replay", note)
        self._update_replay_status()

    def _update_replay_status(self):
        rec = self.recorder
        if rec is None or getattr(rec, "replay", None) is None:
            if not self.replay_var.get():
                self.replay_status_var.set("")
            return
        buf = rec.replay.buffered_seconds()
        total = rec.replay.seconds
        self.replay_status_var.set(
            f"Recording in the background — {buf:.0f} s of {total} s saved. "
            f"Press F11 to keep it. Uses ~{total * 1.5:.0f} MB of temp space.")

    def toggle_record(self):
        if self.recorder and self.recorder.recording:
            self.status_var.set("Stopping & saving… please wait")
            self.recorder.stop()
            _round_button_set(self.record_btn, state="disabled")
            return
        if self.countdown_var.get():
            _round_button_set(self.record_btn, state="disabled")
            self._countdown(3)
            return
        self._actually_start()

    def _countdown(self, n):
        if n <= 0:
            self._actually_start()
            return
        self.status_var.set(f"Recording starts in {n}… get ready")
        self.timer_var.set(str(n))
        self.after(900, lambda: self._countdown(n - 1))

    def _actually_start(self):
        cfg = self._read_ui_to_cfg()
        # A normal recording replaces Replay: stop the old buffer and
        # turn its switch off, so the UI never lies about it.
        if self.recorder is not None and getattr(self.recorder, "replay", None) is not None:
            self.recorder.stop_replay()
            self.replay_var.set(False)
            self.replay_status_var.set("")
        # SOUND GUARDRAIL: never let the user record a silent video
        # without warning. Two ways a video ends up with no sound:
        # (1) FFmpeg missing, so no audio can be merged at all,
        # (2) mic off + game sound with no source on this PC.
        if cfg.get("mic") or cfg.get("system_audio"):
            if find_ffmpeg() is None:
                if not messagebox.askokcancel(
                        "No sound will be recorded",
                        "FFmpeg is missing on this PC, so your mic and game sound CANNOT be put into the video.\n\n"
                        "Run the installer again — it downloads FFmpeg for you — or install FFmpeg from ffmpeg.org.\n\n"
                        "Press Cancel to stop, or OK to record video with no sound."):
                    _round_button_set(self.record_btn, state="normal")
                    return
            elif not cfg.get("mic") and cfg.get("system_audio"):
                _args, _name, hint = detect_system_audio(cfg)
                if not _args:
                    if not messagebox.askokcancel(
                            "No sound will be recorded",
                            "Game sound is on, but this PC has no game-sound source, and the mic is OFF.\n\n"
                            "Your video will have NO sound at all.\n\n"
                            + (hint or "") + "\n\n"
                            "Press Cancel, turn the MIC on, and record again — or OK to record silent anyway."):
                        _round_button_set(self.record_btn, state="normal")
                        return
        if cfg.get("live_enabled") and not (cfg.get("live_rtmp_url") and cfg.get("live_stream_key")):
            messagebox.showwarning("Live needs a stream key", "You turned Live on, but the RTMP URL or stream key is empty.\n\nFill them in the Live card — or turn Live off — then press Record.")
            _round_button_set(self.record_btn, state="normal")
            return
        self._release_idle_cap()
        time.sleep(0.3)
        self.recorder = Recorder(cfg, on_status=self._on_status)
        try:
            path = self.recorder.start()
        except Exception as e:
            log_error("start recording")
            _round_button_set(self.record_btn, state="normal")
            self.timer_var.set("00:00")
            messagebox.showerror("Could not start recording", f"{e}\n\nA technical detail file (error.log) was saved next to app.py.")
            return
        folder_note = ""
        if cfg.get("output_dir") and cfg["output_dir"] != self.out_var.get():
            self.out_var.set(cfg["output_dir"])
            save_config(self.cfg)
            folder_note = f"  •  Save folder changed to {cfg['output_dir']} (old one wasn't available)"
        live_note = ""
        if self.recorder.streamer is not None:
            live_note = f"  •  🔴 LIVE on {cfg.get('live_platform', 'Custom')}"
        elif self.recorder.live_error:
            live_note = f"  •  Live failed: {self.recorder.live_error} (recording continued)"
        audio_note = ""
        if cfg.get("system_audio") and self.recorder.sys_active:
            audio_note = f"  •  🎮 Game sound on ({self.recorder.sys_source})"
        elif cfg.get("system_audio") and self.recorder.sys_error:
            audio_note = "  •  Game sound failed — check the Audio card (recording continued)"
        elif cfg.get("game_sound_only"):
            audio_note = "  •  Game sound only"
        self.status_var.set(f"Recording → {path.name}" + ("" if cfg["facecam"] else "  (facecam off)") + folder_note + live_note + audio_note)
        self.rec_dot.configure(text_color=ACCENT)
        self._session_file_var.set(getattr(path, "name", ""))
        self._update_session_card()
        _round_button_set(self.record_btn, glyph="■", fg_color=PANEL2,
                          hover_color=BORDER, corner_radius=18, state="normal")
        self.pause_btn.configure(state="normal")
        self.chapter_btn.configure(state="normal")
        self._update_live_badge()

    def toggle_pause(self):
        if self.recorder and self.recorder.recording:
            paused = self.recorder.toggle_pause()
            self.pause_btn.configure(text="▶" if paused else "⏸")
            self.status_var.set("Paused" if paused else "Recording…")

    def _on_m_key(self, _event=None):
        # M drops a chapter marker, unless the user is typing in a
        # text box (then the letter belongs to the text).
        focus = self.focus_get()
        if focus is not None and isinstance(focus, (tk.Entry, ctk.CTkEntry)):
            return
        self._add_chapter()

    def _add_chapter(self):
        """Drop a chapter marker at the current point in the
        recording (button or M key)."""
        if not (self.recorder and self.recorder.recording):
            return
        ch = self.recorder.add_chapter()
        if ch:
            self.status_var.set(
                f"Chapter marked: {ch['title']} at {format_chapter_time(ch['time'])} "
                f"({len(self.recorder.chapters)} so far) — rename it in the editor")

    def _on_status(self, elapsed=None, dropped=None, written=None, done=False, path=None, mic_active=None, note="", phase=None):
        def ui():
            if phase == "fixing":
                self.status_var.set("Fixing video speed to match real time… please wait")
                return
            if phase == "script":
                self.status_var.set("Checking your script… turning your speech into text (first time may download the speech model, ~75 MB, once)")
                return
            if done:
                _round_button_set(self.record_btn, glyph="●", fg_color=ACCENT,
                                  hover_color=ACCENT_HOVER, corner_radius=36,
                                  state="normal")
                self.pause_btn.configure(state="disabled", text="⏸")
                self.chapter_btn.configure(state="disabled")
                self._session_file_var.set("")
                self._update_session_card()
                self.rec_dot.configure(text_color=MUTED)
                self.timer_var.set("00:00")
                msg = ""
                if path and os.path.exists(path):
                    mb = os.path.getsize(path) / (1024 * 1024)
                    msg = f"Saved: {Path(path).name}  ({mb:.1f} MB)"
                    if mic_active and not _ffmpeg_available():
                        msg += "  •  Mic saved as separate .mic.wav (install FFmpeg to auto-merge)"
                self.status_var.set((msg or "Ready") + note)
                if self.recorder and getattr(self.recorder, "live_error", ""):
                    self.status_var.set(self.status_var.get() + f"  •  Live: {self.recorder.live_error}")
                self.size_var.set("")
                self.fps_now_var.set("")
                self._update_live_badge()
                self._refresh_recent()
                return
            if elapsed is not None:
                m, s = divmod(int(elapsed), 60)
                h, m = divmod(m, 60)
                self.timer_var.set(f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}")
                if elapsed > 0 and written is not None:
                    self.fps_now_var.set(f"{written / elapsed:.0f} fps")
                if self.recorder and self.recorder.output_path and os.path.exists(self.recorder.output_path):
                    mb = os.path.getsize(self.recorder.output_path) / (1024 * 1024)
                    self.size_var.set(f"{mb:.1f} MB")
                # v2.1: if the live stream dies mid-recording, say so now,
                # instead of only at Stop (recording itself keeps going).
                if self.recorder and getattr(self.recorder, "live_error", "") and "Live:" not in self.status_var.get():
                    self.status_var.set(self.status_var.get() + f"  •  Live: {self.recorder.live_error}")
                self._update_live_badge()
        self.after(0, ui)

    # ---------- preview ----------
    def _preview_tick(self):
        try:
            frame = None
            if self.recorder and (self.recorder.recording or getattr(self.recorder, "replay", None) is not None):
                frame = self.recorder.preview_frame
                self._update_replay_status()
            elif self.face_var.get() and not self.screen_only_var.get():
                if self._idle_cap is None:
                    cap = cv2.VideoCapture(int(self.cfg.get("camera_index", 0)),
                                           cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        self._idle_cap = cap
                    else:
                        cap.release()
                if self._idle_cap is not None:
                    ok, f = self._idle_cap.read()
                    if ok:
                        if bool(self.cfg.get("mirror_facecam", True)):
                            f = cv2.flip(f, 1)
                        frame = apply_character_filter(f, self.filter_var.get())
            if frame is not None:
                disp_w = max(320, self.preview.winfo_width() - 20)
                disp_h = max(200, self.preview.winfo_height() - 20)
                fh, fw = frame.shape[:2]
                scale = min(disp_w / fw, disp_h / fh)
                small = cv2.resize(frame, (max(1, int(fw * scale)), max(1, int(fh * scale))), interpolation=cv2.INTER_LINEAR)
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                self._preview_photo = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
                self.preview.configure(image=self._preview_photo, text="")
        except Exception:
            pass
        # Light mode: the preview updates slower while recording, so
        # the CPU goes to the recording itself, not the preview.
        recording = bool(self.recorder and self.recorder.recording)
        light = bool(self.cfg.get("light_mode", True))
        interval = 500 if (recording and light) else 300 if recording else 90
        self.after(interval, self._preview_tick)

    def _on_close(self):
        if self.recorder and self.recorder.recording:
            if not messagebox.askokcancel("Recording in progress", "Stop recording and close? The video will be saved."):
                return
            self.recorder.stop()
            time.sleep(0.8)
        if self.recorder is not None and getattr(self.recorder, "replay", None) is not None:
            try:
                self.recorder.stop_replay()
            except Exception:
                pass
        if self._hotkeys is not None:
            try:
                self._hotkeys.stop()
            except Exception:
                pass
        if self._idle_cap is not None:
            try:
                self._idle_cap.release()
            except Exception:
                pass
        self._read_ui_to_cfg()
        self.destroy()


if __name__ == "__main__":
    if not HAS_CTK:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "CustomTkinter is missing",
            "Lite Game Recorder v2 needs CustomTkinter for its new design.\n\n"
            "Please run:\n  pip install -r requirements.txt\n\n"
            "Or double-click run.sh (Mac/Linux) / run.bat (Windows), which does it for you.",
        )
        sys.exit(1)
    App().mainloop()
