"""Real-footage MEME VIDEO clips for the editor (not just sounds).

The 100 clips in `meme-videos/` are REAL footage: short cuts from free
stock videos on Coverr (Coverr licence: free for personal and commercial
use, no attribution required). No text cards, no rendered backgrounds,
no AI-generated video, no copyrighted viral clip or movie scene.

`meme-videos/manifest.json` is the source of truth: one entry per clip
with its filename, category, source URL, source page, licence and trim
start time. Run this script to (re)build the `meme-videos/` folder from
the manifest:

    python make_meme_videos.py

Each clip: MP4 (H.264), 1280x720, 30 fps, 2.5 s. If the matching free
sound exists in `sounds/` it is mixed in with FFmpeg; if the sound (or
FFmpeg) is missing the clip is built SILENT — the video never fails
because of audio. Sources download once into `meme-sources/` (not in
the repo) and are reused on later runs.

The editor's custom-card box still renders a user-typed text card on
demand through `render_meme_card` (below): that is the user's own words
on a card, not part of the 100-clip library.

    from make_meme_videos import render_meme_card
    render_meme_card("MY OWN CARD", "timecard", "out.mp4",
                     sound_path="sounds/whoosh.wav")

Importing this module has no side effects: nothing is built unless
`main()` runs under `if __name__ == "__main__":`.
"""
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "meme-videos"
SOUNDS = HERE / "sounds"
MANIFEST = OUT / "manifest.json"
SRC_DIR = HERE / "meme-sources"

W, H = 1280, 720
FPS = 30
DUR = 2.5
N_FRAMES = int(FPS * DUR)
FONT = cv2.FONT_HERSHEY_DUPLEX
MAX_TEXT_W = 1120

# style name -> (background BGR, text BGR, draw effect, shadow BGR or None)
# Used ONLY by render_meme_card (the editor's custom-card box).
# Effects: "shadow" (drop shadow), "outline" (thick pale edge),
# "pill" (yellow pill behind the text), "arrow" (arrow underneath),
# "underline" (red bar underneath), "glow" (darker halo behind),
# "plain" (just the text).
STYLES = {
    "timecard": ((0, 200, 255), (25, 25, 25), "shadow", (0, 120, 180)),
    "neon":     ((15, 15, 15), (0, 215, 255), "plain", None),
    "arrow":    ((15, 15, 15), (0, 215, 255), "arrow", None),
    "pill":     ((45, 45, 45), (10, 10, 10), "pill", None),
    "red":      ((18, 18, 28), (50, 50, 255), "outline", None),
    "white":    ((25, 25, 25), (255, 255, 255), "underline", None),
    "gold":     ((20, 20, 25), (0, 205, 255), "glow", None),
    "grey":     ((95, 95, 95), (235, 235, 235), "plain", None),
    "green":    ((18, 55, 18), (80, 255, 140), "plain", None),
    "blue":     ((70, 40, 15), (180, 220, 255), "plain", None),
}


def _darker(color, factor=0.72):
    return tuple(int(c * factor) for c in color)


def _fit_scale(text, start=4.5):
    """Largest font scale whose text fits inside MAX_TEXT_W.

    Short texts (e.g. "GG") start big so they fill the card like the
    long ones do; long texts shrink back down until they fit.
    """
    scale = start
    while scale > 0.5:
        (tw, _), _ = cv2.getTextSize(text, FONT, scale, 7)
        if tw <= MAX_TEXT_W:
            return scale
        scale -= 0.1
    return scale


def _draw_text(overlay, text, scale, thick, y_off=0, effect="shadow",
               fg=(25, 25, 25), shadow=None):
    """Draw the centred meme text on `overlay`; returns text width."""
    (tw, th), base = cv2.getTextSize(text, FONT, scale, thick)
    x = (W - tw) // 2
    y = (H + th) // 2 + y_off
    if effect == "shadow":
        sc = shadow if shadow is not None else (0, 0, 0)
        cv2.putText(overlay, text, (x + 5, y + 5), FONT, scale,
                    sc, thick, cv2.LINE_AA)
        cv2.putText(overlay, text, (x, y), FONT, scale, fg, thick,
                    cv2.LINE_AA)
    elif effect == "outline":
        # thick white edge, coloured text inside
        cv2.putText(overlay, text, (x, y), FONT, scale,
                    (255, 255, 255), thick + 8, cv2.LINE_AA)
        cv2.putText(overlay, text, (x, y), FONT, scale, fg, thick,
                    cv2.LINE_AA)
    elif effect == "pill":
        # yellow pill behind the text
        pad_x, pad_y = 60, 46
        x0, y0 = x - pad_x, y - th - pad_y
        x1, y1 = x + tw + pad_x, y + base + pad_y
        r = (y1 - y0) // 2
        cv2.rectangle(overlay, (x0 + r, y0), (x1 - r, y1),
                      (0, 210, 255), -1, cv2.LINE_AA)
        cv2.circle(overlay, (x0 + r, (y0 + y1) // 2), r,
                   (0, 210, 255), -1, cv2.LINE_AA)
        cv2.circle(overlay, (x1 - r, (y0 + y1) // 2), r,
                   (0, 210, 255), -1, cv2.LINE_AA)
        cv2.putText(overlay, text, (x, y), FONT, scale, fg, thick,
                    cv2.LINE_AA)
    elif effect == "arrow":
        cv2.putText(overlay, text, (x, y), FONT, scale, fg, thick,
                    cv2.LINE_AA)
        ay = y + 70
        cv2.arrowedLine(overlay, (W // 2 - 190, ay), (W // 2 + 190, ay),
                        fg, 10, cv2.LINE_AA, tipLength=0.25)
    elif effect == "underline":
        cv2.putText(overlay, text, (x, y), FONT, scale, fg, thick,
                    cv2.LINE_AA)
        cv2.rectangle(overlay, (x, y + 34), (x + tw, y + 48),
                      (0, 0, 220), -1, cv2.LINE_AA)
    elif effect == "glow":
        # darker halo behind, bright text on top
        halo = _darker(fg, 0.45)
        cv2.putText(overlay, text, (x, y), FONT, scale,
                    halo, thick + 8, cv2.LINE_AA)
        cv2.putText(overlay, text, (x, y), FONT, scale, fg, thick,
                    cv2.LINE_AA)
    else:  # "plain"
        cv2.putText(overlay, text, (x, y), FONT, scale, fg, thick,
                    cv2.LINE_AA)
    return tw


def _render_video_only(text, bg, fg, effect, shadow, tmp_path):
    """Render the 2.5 s video-only MP4 with OpenCV (custom cards only)."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(tmp_path), fourcc, FPS, (W, H))
    if not vw.isOpened():
        raise RuntimeError("VideoWriter could not open %s" % tmp_path)
    base = np.full((H, W, 3), bg, dtype=np.uint8)
    # thin darker card border so the clip reads as a card, not a flat fill
    cv2.rectangle(base, (14, 14), (W - 15, H - 15), _darker(bg, 0.62), 10)
    scale = _fit_scale(text)
    thick = max(5, int(round(scale * 2.7)))
    y_off = -30 if effect in ("arrow", "underline") else 0
    for i in range(N_FRAMES):
        t = i / FPS
        # pop-in: first 0.3 s scales up 0.55 -> 1.0 with an ease-out
        p = min(1.0, t / 0.3)
        ease = 1.0 - (1.0 - p) ** 2
        alpha = ease
        # fade-out: last 0.3 s
        if t > DUR - 0.3:
            alpha *= max(0.0, (DUR - t) / 0.3)
        overlay = base.copy()
        _draw_text(overlay, text, scale * (0.55 + 0.45 * ease), thick,
                   y_off=y_off, effect=effect, fg=fg, shadow=shadow)
        frame = cv2.addWeighted(base, 1.0 - alpha, overlay, alpha, 0)
        vw.write(frame)
    vw.release()


def _mux_audio(video_path, sound_path, out_path):
    """Mux the (short) sound into the video; returns True on success."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not sound_path.is_file():
        return False
    cmd = [ffmpeg, "-y", "-v", "error",
           "-i", str(video_path), "-i", str(sound_path),
           "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
           "-af", "apad", "-t", str(DUR), str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and out_path.is_file()


def render_meme_card(text, style, out_path, sound_path=None):
    """Render one CUSTOM meme card video (user-typed text).

    This is for the editor's custom-card box only: the user types
    their own words and gets a text card. The 100-clip library is
    real footage built from the manifest, not this function.

    `text` is the big centred text, `style` is a key of STYLES
    (unknown styles fall back to "timecard"), `out_path` is the MP4
    to write, `sound_path` is an optional sound file (path or None)
    mixed in with FFmpeg. If the sound is missing (or FFmpeg is),
    the clip is written SILENT — the video never fails for audio.

    Returns True if the clip file was written, False on failure.
    Safe to call from the editor's custom-card box.
    """
    if style not in STYLES:
        print("make_meme_videos: unknown style %r, using 'timecard'"
              % (style,))
        style = "timecard"
    bg, fg, effect, shadow = STYLES[style]
    out_path = Path(out_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_name(".tmp_" + out_path.name)
        _render_video_only(text, bg, fg, effect, shadow, tmp_path)
        with_audio = False
        if sound_path is not None:
            sound_path = Path(sound_path)
            if sound_path.is_file() and _mux_audio(tmp_path, sound_path,
                                                   out_path):
                with_audio = True
                tmp_path.unlink(missing_ok=True)
        if not with_audio:
            if tmp_path.is_file():
                shutil.move(str(tmp_path), str(out_path))
        return out_path.is_file()
    except Exception as exc:  # video must never crash the caller
        print("make_meme_videos: failed to render %r: %s" % (text, exc))
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False


# ------------------------------------------------------------------
# Manifest-driven library build (real footage)
# ------------------------------------------------------------------

def _probe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _download_source(entry):
    """Download the source video once into meme-sources/; reuse it."""
    slug = entry["source_url"].split("/videos/")[1].split("/")[0]
    dest = SRC_DIR / (slug + ".mp4")
    if dest.is_file() and dest.stat().st_size > 100_000:
        return dest
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        entry["source_url"],
        headers={"User-Agent": "Mozilla/5.0 (LiteGameRecorder meme build)"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, \
                open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
    except Exception as exc:
        print("  download failed for %s: %s" % (entry["clip"], exc))
        if dest.is_file():
            dest.unlink()
        return None
    if dest.stat().st_size < 100_000:
        dest.unlink()
        return None
    return dest


def _build_clip_from_footage(entry):
    """Cut one 2.5 s clip from real footage; returns (ok, reason)."""
    name = entry["clip"]
    src = _download_source(entry)
    if src is None:
        return False, "download failed"
    dur = _probe_duration(src)
    if dur <= 0:
        return False, "unreadable source"
    start = float(entry.get("start", 0.0))
    if start + DUR > dur:
        start = max(0.0, dur - DUR)
    out_path = OUT / (name + ".mp4")
    vf = ("scale=1280:720:force_original_aspect_ratio=increase,"
          "crop=1280:720,fps=30")
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if dur < DUR + start:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-ss", str(start), "-i", str(src)]
    sound_path = SOUNDS / entry["sound"] if entry.get("sound") else None
    have_sound = sound_path is not None and sound_path.is_file()
    if have_sound:
        cmd += ["-i", str(sound_path), "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-vf", vf,
                "-c:a", "aac", "-b:a", "128k", "-af", "apad",
                "-t", str(DUR), "-movflags", "+faststart", str(out_path)]
    else:
        cmd += ["-map", "0:v:0", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "23", "-pix_fmt", "yuv420p", "-vf", vf,
                "-t", str(DUR), "-movflags", "+faststart", str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out_path.is_file():
        return False, "ffmpeg failed: " + (r.stderr or "")[:200]
    return True, entry["sound"] if have_sound else "silent"


def main():
    if not MANIFEST.is_file():
        print("make_meme_videos: manifest not found: %s" % MANIFEST)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    have_ffmpeg = shutil.which("ffmpeg") is not None
    if not have_ffmpeg:
        print("make_meme_videos: ffmpeg is required to build the clips")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    # drop stale clips from earlier runs so the folder is exactly the manifest
    keep = {entry["clip"] + ".mp4" for entry in manifest}
    keep.add("manifest.json")
    for old in OUT.glob("*.mp4"):
        if old.name not in keep:
            old.unlink()
            print("  removed stale clip %s" % old.name)
    results = []
    for entry in manifest:
        ok, reason = _build_clip_from_footage(entry)
        print("  %-28s %s (%s)" % (entry["clip"] + ".mp4",
                                   "OK" if ok else "FAILED", reason))
        results.append((entry["clip"], ok, reason))
    n_ok = sum(1 for _, ok, _ in results if ok)
    print("done: %d/%d clips in %s" % (n_ok, len(results), OUT))
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
