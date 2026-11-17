"""Render short MEME VIDEO clips for the editor (not just sounds).

The user asked for meme videos they can drop into a video, e.g. the
SpongeBob-style "a few moments later" time cards. These clips are
rendered from scratch with OpenCV — big bold centred text on a solid
bright background, with a pop-in at the start and a fade-out at the
end. They are OUR OWN look (our colours, our layout): no
Nickelodeon card image, no copied font, no sampled audio.

Run it to (re)build the `meme-videos/` folder:

    python make_meme_videos.py

Each clip: MP4, 1280x720, 30 fps, 2.5 s. If the matching free sound
exists in `sounds/` it is mixed in with FFmpeg; if the sound (or
FFmpeg) is missing the clip is rendered SILENT — the video never
fails because of audio.

The core function is importable so the editor can render a custom
card on demand (the editor's custom-card box calls it later):

    from make_meme_videos import render_meme_card
    render_meme_card("MY OWN CARD", "timecard", "out.mp4",
                     sound_path="sounds/whoosh.wav")

Importing this module has no side effects: nothing is rendered
unless `main()` runs under `if __name__ == "__main__":`.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "meme-videos"
SOUNDS = HERE / "sounds"

W, H = 1280, 720
FPS = 30
DUR = 2.5
N_FRAMES = int(FPS * DUR)
FONT = cv2.FONT_HERSHEY_DUPLEX
MAX_TEXT_W = 1120

# style name -> (background BGR, text BGR, draw effect, shadow BGR or None)
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

# The library: (filename, on-screen text, style, sound file in sounds/)
# 100 clips in 6 categories. No duplicate texts; every line is short
# enough to fit on screen (the auto-fit shrinks long lines).
CLIPS = [
    # ---- Time cards (20) ----
    ("a-few-moments-later", "A FEW MOMENTS LATER", "timecard", "whoosh.wav"),
    ("one-eternity-later", "ONE ETERNITY LATER", "timecard", "whoosh.wav"),
    ("2000-years-later", "2000 YEARS LATER", "timecard", "whoosh.wav"),
    ("twelve-seconds-later", "TWELVE SECONDS LATER", "timecard", "whoosh.wav"),
    ("a-few-minutes-later", "A FEW MINUTES LATER", "timecard", "whoosh.wav"),
    ("tomorrow", "TOMORROW", "timecard", "whoosh.wav"),
    ("10-seconds-later", "10 SECONDS LATER", "timecard", "whoosh.wav"),
    ("a-few-inches-later", "A FEW INCHES LATER", "timecard", "whoosh.wav"),
    ("day-two", "DAY TWO", "timecard", "whoosh.wav"),
    ("day-three", "DAY THREE", "timecard", "whoosh.wav"),
    ("three-days-later", "THREE DAYS LATER", "timecard", "whoosh.wav"),
    ("many-months-later", "MANY MONTHS LATER", "timecard", "whoosh.wav"),
    ("eventually", "EVENTUALLY", "timecard", "whoosh.wav"),
    ("six-and-a-half-hours-later", "6 1/2 HOURS LATER", "timecard", "whoosh.wav"),
    ("the-next-day", "THE NEXT DAY", "timecard", "whoosh.wav"),
    ("later-that-night", "LATER THAT NIGHT", "timecard", "whoosh.wav"),
    ("meanwhile", "MEANWHILE", "timecard", "whoosh.wav"),
    ("2-hours-later", "2 HOURS LATER", "timecard", "whoosh.wav"),
    ("1-week-later", "1 WEEK LATER", "timecard", "whoosh.wav"),
    ("back-at-the-ranch", "BACK AT THE RANCH", "timecard", "whoosh.wav"),
    # ---- Reactions (20) ----
    ("bruh-moment", "BRUH.", "pill", "pop.wav"),
    ("what-meme", "WHAT?!", "neon", "pop.wav"),
    ("oh-no", "OH NO", "red", "sad-trombone.wav"),
    ("wait-a-minute", "WAIT A MINUTE", "neon", "whoosh.wav"),
    ("no-way", "NO WAY", "red", "pop.wav"),
    ("seriously", "SERIOUSLY?", "blue", "pop.wav"),
    ("are-you-kidding-me", "ARE YOU KIDDING ME", "blue", "pop.wav"),
    ("i-cant-believe-this", "I CAN'T BELIEVE THIS", "neon", "pop.wav"),
    ("wow", "WOW", "gold", "airhorn.wav"),
    ("noooo", "NOOOO", "red", "sad-trombone.wav"),
    ("yesss", "YESSS", "gold", "applause.wav"),
    ("lets-gooo", "LET'S GOOO", "gold", "airhorn.wav"),
    ("nah-bro", "NAH BRO", "pill", "pop.wav"),
    ("thats-crazy", "THAT'S CRAZY", "neon", "pop.wav"),
    ("im-dead", "I'M DEAD", "white", "pop.wav"),
    ("lol", "LOL", "pill", "pop.wav"),
    ("hahaha", "HAHAHA", "pill", "pop.wav"),
    ("what-did-i-just-watch", "WHAT DID I JUST WATCH", "neon", "pop.wav"),
    ("excuse-me", "EXCUSE ME?", "white", "pop.wav"),
    ("my-god", "MY GOD", "gold", "airhorn.wav"),
    # ---- Fails (15) ----
    ("emotional-damage", "EMOTIONAL DAMAGE!", "red", "sad-trombone.wav"),
    ("fail", "FAIL", "red", "sad-trombone.wav"),
    ("epic-fail", "EPIC FAIL", "red", "sad-trombone.wav"),
    ("task-failed", "TASK FAILED", "grey", "sad-trombone.wav"),
    ("sad-trombone", "SAD TROMBONE", "grey", "sad-trombone.wav"),
    ("that-did-not-work", "THAT DID NOT WORK", "grey", "sad-trombone.wav"),
    ("oof", "OOF", "red", "punch.wav"),
    ("rip", "RIP", "grey", "sad-trombone.wav"),
    ("game-over", "GAME OVER", "red", "boom.wav"),
    ("disaster", "DISASTER", "red", "boom.wav"),
    ("welp", "WELP", "grey", "pop.wav"),
    ("mission-failed", "MISSION FAILED", "grey", "sad-trombone.wav"),
    ("f-in-the-chat", "F IN THE CHAT", "white", "pop.wav"),
    ("so-close", "SO CLOSE", "grey", "sad-trombone.wav"),
    ("thats-a-no", "THAT'S A NO", "red", "pop.wav"),
    # ---- Wins (15) ----
    ("victory", "VICTORY!", "gold", "applause.wav"),
    ("winner-winner", "WINNER WINNER", "gold", "applause.wav"),
    ("clutch", "CLUTCH!", "gold", "success.wav"),
    ("insane", "INSANE!", "gold", "airhorn.wav"),
    ("that-was-clean", "THAT WAS CLEAN", "gold", "success.wav"),
    ("easy", "EASY", "gold", "pop.wav"),
    ("gg", "GG", "gold", "success.wav"),
    ("unstoppable", "UNSTOPPABLE", "gold", "applause.wav"),
    ("legendary", "LEGENDARY", "gold", "coin.wav"),
    ("perfect", "PERFECT!", "gold", "success.wav"),
    ("nailed-it", "NAILED IT", "gold", "applause.wav"),
    ("champion", "CHAMPION", "gold", "applause.wav"),
    ("too-easy", "TOO EASY", "gold", "success.wav"),
    ("world-record", "WORLD RECORD", "gold", "coin.wav"),
    ("we-did-it", "WE DID IT", "gold", "applause.wav"),
    # ---- Dramatic (15) ----
    ("dramatic-moment", "DUN DUN DUNNN...", "white", "boom.wav"),
    ("to-be-continued", "TO BE CONTINUED", "arrow", "riser.wav"),
    ("plot-twist", "PLOT TWIST", "neon", "riser.wav"),
    ("wait-for-it", "WAIT FOR IT", "neon", "whoosh.wav"),
    ("dramatic-zoom", "DRAMATIC ZOOM", "white", "boom.wav"),
    ("the-truth-is", "THE TRUTH IS", "neon", "riser.wav"),
    ("but-wait", "BUT WAIT", "neon", "whoosh.wav"),
    ("and-then", "AND THEN...", "neon", "riser.wav"),
    ("suddenly", "SUDDENLY", "white", "boom.wav"),
    ("the-end", "THE END?", "neon", "riser.wav"),
    ("cliffhanger", "CLIFFHANGER", "neon", "riser.wav"),
    ("reveal", "REVEAL", "gold", "drumroll.wav"),
    ("shocking", "SHOCKING", "red", "boom.wav"),
    ("back-at-home", "BACK AT HOME", "neon", "whoosh.wav"),
    ("the-moment-of-truth", "THE MOMENT OF TRUTH", "gold", "drumroll.wav"),
    # ---- Gaming (15) ----
    ("headshot", "HEADSHOT!", "green", "laser.wav"),
    ("killstreak", "KILLSTREAK", "green", "laser.wav"),
    ("double-kill", "DOUBLE KILL", "green", "laser.wav"),
    ("triple-kill", "TRIPLE KILL", "green", "laser.wav"),
    ("rampage", "RAMPAGE", "green", "laser.wav"),
    ("first-blood", "FIRST BLOOD", "red", "laser.wav"),
    ("ace", "ACE!", "gold", "success.wav"),
    ("clutch-or-kick", "CLUTCH OR KICK", "green", "laser.wav"),
    ("1v5", "1V5", "green", "boom.wav"),
    ("no-scope", "NO SCOPE", "green", "punch.wav"),
    ("360-no-scope", "360 NO SCOPE", "green", "punch.wav"),
    ("lag", "LAG!", "grey", "scratch.wav"),
    ("my-team", "MY TEAM...", "grey", "sad-trombone.wav"),
    ("gg-ez", "GG EZ", "green", "ding.wav"),
    ("camping", "CAMPING?", "grey", "pop.wav"),
]


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
    """Render the 2.5 s video-only MP4 with OpenCV."""
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
    """Render one meme card video.

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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    have_ffmpeg = shutil.which("ffmpeg") is not None
    print("ffmpeg: %s" % ("found" if have_ffmpeg else "NOT FOUND "
                          "(clips will be video-only)"))
    # drop stale clips from earlier runs so the folder is exactly CLIPS
    keep = {name + ".mp4" for name, _, _, _ in CLIPS}
    for old in OUT.glob("*.mp4"):
        if old.name not in keep:
            old.unlink()
            print("  removed stale clip %s" % old.name)
    results = []
    for name, text, style, sound in CLIPS:
        out_path = OUT / (name + ".mp4")
        sound_path = SOUNDS / sound if sound else None
        ok = render_meme_card(text, style, out_path, sound_path)
        if not ok:
            print("  %-28s FAILED" % out_path.name)
            results.append((name, False, "failed"))
            continue
        with_audio = bool(sound_path and sound_path.is_file()
                          and have_ffmpeg)
        # confirm the file really has an audio stream
        if with_audio:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=codec_name",
                 "-of", "csv=p=0", str(out_path)],
                capture_output=True, text=True)
            with_audio = bool(probe.stdout.strip())
        reason = sound if with_audio else (
            "no ffmpeg" if not have_ffmpeg
            else "sound %s missing" % sound
            if sound_path and not sound_path.is_file()
            else "ffmpeg mux failed")
        print("  %-28s %s (%s)" % (out_path.name,
                                   "with audio" if with_audio else "SILENT",
                                   reason))
        results.append((name, with_audio, reason))
    n_audio = sum(1 for _, a, _ in results if a)
    print("done: %d clips in %s (%d with audio, %d silent)"
          % (len(results), OUT, n_audio, len(results) - n_audio))
    return 0 if len(results) == len(CLIPS) else 1


if __name__ == "__main__":
    sys.exit(main())
