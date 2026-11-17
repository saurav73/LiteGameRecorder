"""Video Editor - CapCut-style editor inside Lite Tutorial Maker.

Not an exact copy of CapCut (CapCut is a huge app made by a big
team, with online templates and cloud effects) - but the same kind
of editor, built in, with the features that matter:

  Timeline:   add clips, remove, move up/down, split at the playhead,
              duplicate a clip
  Project:    💾 Save / 📂 Open the whole project (.json), so you
              can close the editor and carry on later
  Trim:       start / end per clip
  Speed:      0.5x / 1x / 1.5x / 2x per clip
  Filters:    the same character/style filters as the recorder
              (Cartoon, Anime, LING...) - on the whole clip here
  Text:       text overlay with position and colour per clip
  Stickers:   emoji stickers on the clip
  Transitions: None / Fade / Dissolve between clips
  Ratio:      16:9 landscape, 9:16 vertical (TikTok / Reels),
              1:1 square - with a blurred background fill
  Audio:      mute per clip, background music + volume
  Captions:   auto captions from the speech in the video
              (uses the Smart Record speech engine when installed)
  Export:     one MP4 with a progress bar, next to the first clip

The video is rendered with OpenCV; the audio is mixed with FFmpeg
when it is available (it is needed for Live already). If FFmpeg is
missing, the export is video-only and the app says so.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from app_version import get_app_dir

import wave

import cv2
import numpy as np

# Sound playback for the preview (and for listening to sounds):
# sounddevice is already a recorder dependency, so it is installed
# with the app. If it is missing, the editor just plays silently.
try:
    import sounddevice as sd
    _HAS_SD = True
except Exception:
    sd = None
    _HAS_SD = False


def _quiet_kwargs():
    # No black console window on Windows.
    if sys.platform == "win32":
        return {"creationflags": 0x08000000}
    return {}


_ffplay_proc = None  # the running ffplay player, if any


def _play_with_ffplay(path, offset=0.0):
    """Play a sound file with ffplay (it comes with the FFmpeg the
    installer downloads, so it works even when sounddevice / the
    PC's audio library has a problem). Returns True if ffplay
    started. The process is kept so it can be stopped."""
    global _ffplay_proc
    ffplay = _find_tool("ffplay")
    if not ffplay:
        return False
    _stop_ffplay()
    try:
        _ffplay_proc = subprocess.Popen(
            [ffplay, "-nodisp", "-autoexit", "-ss", "%.3f" % max(0.0, offset),
             "-v", "error", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **_quiet_kwargs())
        return True
    except Exception:
        _ffplay_proc = None
        return False


def _stop_ffplay():
    global _ffplay_proc
    if _ffplay_proc is not None:
        try:
            _ffplay_proc.terminate()
        except Exception:
            pass
        _ffplay_proc = None


def _play_wav_file(path, offset=0.0):
    """Play a WAV file, from `offset` seconds in. Tries sounddevice
    first, then ffplay (bundled with FFmpeg) — so sound works even
    when one of the two players is broken on this PC. Returns True
    if a player started, False if neither could."""
    if _HAS_SD:
        try:
            with wave.open(str(path), "rb") as wf:
                sr = wf.getframerate()
                ch = wf.getnchannels()
                raw = wf.readframes(wf.getnframes())
            data = np.frombuffer(raw, dtype=np.int16).reshape(-1, ch)
            start = min(len(data), int(max(0.0, offset) * sr))
            data = data[start:]
            if len(data) == 0:
                return False
            sd.play(data, sr)
            return True
        except Exception:
            pass
    return _play_with_ffplay(path, offset)


def _stop_wav():
    if _HAS_SD:
        try:
            sd.stop()
        except Exception:
            pass
    _stop_ffplay()


def sfx_library():
    """[(display name, path)] of the free sound effects shipped with
    the app (the `sounds/` folder next to the editor, or next to the
    frozen .exe). The first 15 were synthesized with numpy — free to
    use, no licence, no download. The 10 meme sounds are royalty-free
    re-creations from sfxreels.com (see sounds/SOURCES.txt) — not the
    original viral recordings, so they are cleared for commercial use.
    A further 303 free meme sounds were added 2026-11-15 from
    712tools.com (synthesized), sfxreels.com, memesoundboards.org
    and myinstants.com — see sounds/SOURCES.txt for each sound.
    A name with no file yet is simply skipped, so the tab only ever
    shows sounds that are really there."""
    names = ["whoosh", "pop", "ding", "coin", "boom", "riser", "airhorn",
             "applause", "drumroll", "click", "laser", "success", "scratch",
             "sad-trombone", "punch",
             # Meme sounds (their .wav files land separately; a name
             # with no file yet is simply skipped, so the tab only
             # ever shows sounds that are really there).
             "bruh", "emotional-damage", "dun-dun-dunnn",
             # Royalty-free meme re-creations from sfxreels.com.
             "a-few-moments-later", "bone-crack", "fahh", "fbi-open-up",
             "oh-no-laughing", "technologia", "what", "wow-anime",
             # 303 more free meme sounds (2026-11-15): 712tools
             # synthesized SFX, sfxreels re-creations, memesoundboards.org
             # + myinstants downloads — see sounds/SOURCES.txt. A few are
             # copyrighted samples offered as free downloads; SOURCES.txt
             # marks those "check before commercial use".
             "8-bit-blip", "8-bit-bonus", "8-bit-explosion", "8-bit-hurt", "achievement", "acoustic-guitar-strum", "adopt-me-cash", "air-horn", "alarm-clock", "alien-mystery-sting", "alien-mystery-theme", "among-us-kill", "anatoxic-garamararamararaman", "arcade-button", "arrow-whoosh", "arsenal-headshot", "arsenal-kill", "atm-beep", "aughhh", "autodarts-bonus-cricket", "aww", "balloon-pop", "baseball-catch", "bass-guitar", "beep-medical", "beep-morse", "bell-chime", "bell-prank", "blox-fruits-level-up", "bo-womp", "body-fall-thud", "boi", "boing", "boing-spring", "bongo-drum", "bonk", "bonk-meme", "boo-scary", "boo-womp-spongebob", "boxing-bell", "brainrot-cat", "brookhaven-doorbell", "bruh-meme-sound-effect", "buzzer-wrong", "camera-flash", "camera-shutter", "capuccino-assasino-italian-brainrot", "car-alarm", "car-crash", "car-horn", "cartoon-boing", "cartoon-metallic-stomp", "cartoon-slap", "cartoony-bash", "cash-register", "cash-register-cha-ching", "censor-beep", "checkpoint", "chicken-jockey-a-minecraft-movie-clean-audio", "cinematic-hit", "cinematic-whoosh", "classic-fart", "clock-ticking", "clown-horn-short", "coin-pickup", "conga-drum", "core-bass-hit", "cough", "count-up", "cowbell", "cricket", "cricket-bat-hitting-sound", "crickets-awkward-silence", "crow-caw", "crowd-boo", "crowd-chant", "digital-glitch", "discord-message-notification", "discord-notification", "discord-ping", "discordmute", "distant-scream", "dj-scratch", "door-knock", "doubt-music", "downlifter", "dramatic-sting", "duck-quack", "dun-dun-dun", "e2-error", "electric-zap", "email-notify", "emotional-damage-meme", "epic-choir", "epic-fail-flute", "epic-hit", "erichorn", "erm-what-the-sigma-full", "error-buzz", "error-tone", "explosion", "extra-life", "face-slap", "fake-laugh", "fart", "final-credit-music", "fire-alarm", "fire-crackle", "flatline", "footsteps", "fox-scream", "frog-croak", "game-over", "gary-meow", "gasp", "glitch", "glitch-transition", "goat-scream", "goofy-honk", "goofy-yeha-yeehaa-yeeha-yehaa-ohio-sigma-skibidi", "goose-honk", "gruneme-shrek", "hand-slap", "heartbeat", "hesitation", "hiccup", "hit-8bit", "hollow-metallic-head-konk-and-horn", "huh-cat-meme", "huh-roblox", "im-outta-here-sonic-cd", "jailbreak-siren", "jixaw-metal-pipe-falling-sound", "jump", "jump-8bit", "jump-landing", "jumpscare-scream", "kazoo", "keyboard-type", "keypad-beep", "kick-drum", "laser-blast", "laser-zap", "laugh-track", "lemmings-bonk", "level-up", "light-switch", "loud-dramatic-stinger", "loud-fart", "magic-wand", "mario-big-jump-sound-effect", "mario-meow", "mateooo-italian-brainrot", "menu-close", "menu-open", "meowl-steal-a-brainrot", "message-pop", "metal-pipe", "metal-pipe-vine-boom", "metallic-riser", "minecraft-oof-no-delay", "mission-complete", "mlg-air-horn-sound", "mlg-airhorn", "money-count", "murder-mystery-gun", "negative-beep", "nervous-giggle", "new-notification", "nintendo-switch-error", "noob-oof-sound", "notification-ding", "oh-my-god-bro-ah-hell-nah", "orchestra-hit", "ouch", "paper-flip", "pc-shutdown-chime", "penguin", "perfect-fart", "phone-ring", "piggy-chase-music", "piggy-jumpscare", "ping-pong", "portal-warp", "power-down", "power-up", "price-is-right-losing-trombone", "proper-clown-short-horn", "psst-roblox-doors", "quack", "quick-fart", "rain", "record-scratch", "retro-game-over", "retro-hero-horns", "retro-laser", "reverse-whoosh", "reward", "rewind-fail-fx", "rimshot", "rise-riser", "riser-quick", "rizzbot-laugh", "roblox-cash-register", "roblox-death-sound-oof", "roblox-drinking-potion", "roblox-error", "roblox-game-over", "roblox-hurt", "roblox-jumping", "roblox-level-up", "roblox-oof", "roblox-sword-swing", "roblox-victory-fanfare", "roblox-walking", "romance-music-meme", "rubber-chicken", "run-music", "sad-violin", "scared-scream", "scream", "select-menu", "shoot-blaster", "short-fart", "shrek-do-the-roar", "shrek-roar", "sigh", "siren", "siren-whistle", "skibidi-toilet-steal-a-brainrot", "slap", "slap-quandale-dingle", "slide-whistle", "slide-whistle-down", "slide-whistle-up", "slot-lever", "slow-clap", "slurp", "snare-drum", "sneeze", "snoring", "snort-laugh", "sonic-cd-jump", "sparkle-magic", "spongebob-fail", "spongebob-transition", "squeak", "startup-chime", "steal-a-brainrot-dragon-cannelloni", "steam-train-chuff", "stopwatch-beep", "submarine-ping", "success-chime", "sudden-suspense-boom", "surprise", "sus", "sus-violin", "suspense", "swipe", "swipe-transition", "swoosh", "tada", "tap", "tape-rewind", "text-message", "thunder", "ticking-clock", "toggle-off", "toggle-on", "toggle-switch", "toilet-ananas-nasdas", "tralalero-tralala-meme", "trollface-smile", "trullimero-trullicina", "typewriter", "vibraslap", "vine-boom", "vine-boom-bass-boosted-man", "vine-boom-meme", "vine-boom-spam", "warning-beep", "water-drop", "west-coast-groove", "wet-fart", "whistle-catcall", "whoosh-cinematic", "whoosh-snap", "whoosh-transition", "why-are-you-running", "wilhelm-scream", "wind", "windows-vista-chord-sound-effect", "windows-xp-critical-error-full-version", "windows-xp-error", "windows-xp-fail", "woman-scream", "wow", "yay", "yeet", "zelda-navi-hello", "zoom", "zoom-in", "zoom-out"]
    cands = []
    try:
        cands.append(get_app_dir() / "sounds")
    except Exception:
        pass
    try:
        cands.append(Path(sys.executable).parent / "sounds")
    except Exception:
        pass
    out = []
    for folder in cands:
        if folder.is_dir():
            for n in names:
                p = folder / (n + ".wav")
                if p.is_file():
                    out.append((n.replace("-", " ").title(), str(p)))
            if out:
                return out
    return out


SPEEDS = ["0.5x", "1x", "1.5x", "2x"]
TRANSITIONS = ["None", "Fade", "Dissolve", "Slide", "Zoom", "Glitch", "Flash", "Blur"]
# CapCut's curve speed editor: the average speed stays 1x, so the
# clip keeps its length — only the pacing changes.
RAMPS = ["None", "Slow → Fast", "Fast → Slow", "Slow-Fast-Slow", "Hero"]
TEXT_STYLES = ["Normal", "Pill", "Neon"]
FREEZES = ["0s", "0.5s", "1s", "2s"]
QUALITIES = ["720p", "1080p"]
# Animated subtitle styles, researched from the looks trending on
# Reels / TikTok / Shorts in 2026: Hormozi (green pill), Beast Mode
# (yellow + swell), Golden Karaoke, Neon, Typewriter, Gradient Pop,
# Minimal, Bouncing Ball, Word Punch, TikTok Box, Gamer.
CAPTION_STYLES = ["Normal", "Karaoke", "Hormozi", "Beast Mode",
                  "Golden Karaoke", "Neon", "Typewriter", "Gradient Pop",
                  "Minimal", "Bouncing Ball", "Word Punch", "TikTok Box",
                  "Gamer"]
# Text animations (CapCut: In / Loop) and clip animations, the same
# kinds the AI-edited videos use: kinetic type, shake, glitch, zoom.
TEXT_ANIMS = ["None", "Fade in", "Pop in", "Slide up", "Typewriter",
              "Bounce", "Wave", "Shake", "Glitch"]
CLIP_ANIMS = ["None", "Zoom in", "Zoom out", "Pan left", "Pan right",
              "Shake", "Glitch", "Zoom pulse", "Flash", "Jelly"]
RATIOS = {
    "16:9  Landscape": (1280, 720),
    "9:16  Vertical (TikTok / Reels)": (720, 1280),
    "9:16  Smart reframe (follow face)": (720, 1280),
    "1:1  Square": (720, 720),
}
TEXT_POSITIONS = ["Top", "Bottom"]
TEXT_COLORS = {"White": (255, 255, 255), "Yellow": (0, 255, 255),
               "Cyan": (255, 255, 0), "Pink": (180, 105, 255),
               "Green": (0, 255, 0), "Orange": (0, 165, 255)}
STICKERS = ["None", "🔥", "❤️", "😂", "⭐", "🎉", "👍", "💯", "😎", "🎮",
            "🎵", "💥", "🌟", "😍", "🤣", "👑", "💪", "🎯", "⚡", "💎", "😮", "👏"]
STICKER_POSITIONS = ["Top Left", "Top Right", "Bottom Left", "Bottom Right", "Centre"]

# One-click video templates (CapCut-style presets). Applying one
# sets the project (ratio, transition, captions) and the look of
# every clip (speed, filter, text colour) at once. Your clips,
# trims and text stay as they are.
TEMPLATES = {
    "🎮  Gaming Highlight": {
        "desc": "Big game moments, bold cartoon look",
        "ratio": "16:9  Landscape", "transition": "Dissolve",
        "speed": 1.0, "filter": "Cartoon", "text_color": "Yellow",
        "text_anim": "Pop in", "clip_anim": "Zoom pulse",
        "captions": False},
    "📱  TikTok / Reels": {
        "desc": "Vertical video, captions on, ready to post",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Fade",
        "speed": 1.0, "filter": "Anime", "text_color": "White",
        "text_anim": "Pop in", "clip_anim": "Zoom in",
        "captions": True},
    "🎬  Cinematic": {
        "desc": "Movie look — black & white, slow fade",
        "ratio": "16:9  Landscape", "transition": "Dissolve",
        "speed": 1.0, "filter": "B&W", "text_color": "White",
        "text_anim": "Fade in", "clip_anim": "Zoom in",
        "captions": False},
    "⚡  Fast Highlights": {
        "desc": "Everything 1.5x faster, neon look",
        "ratio": "16:9  Landscape", "transition": "Dissolve",
        "speed": 1.5, "filter": "Neon", "text_color": "Yellow",
        "text_anim": "Shake", "clip_anim": "Zoom pulse",
        "captions": False},
    "😂  Funny Moments": {
        "desc": "Square video, comic look",
        "ratio": "1:1  Square", "transition": "Fade",
        "speed": 1.0, "filter": "Comic", "text_color": "Pink",
        "text_anim": "Bounce", "clip_anim": "None",
        "captions": False},
    "✨  Clean & Simple": {
        "desc": "No filter, no tricks — just your video",
        "ratio": "16:9  Landscape", "transition": "None",
        "speed": 1.0, "filter": "None", "text_color": "White",
        "text_anim": "None", "clip_anim": "None",
        "captions": False},
    # ---- Popular Reels templates (researched Nov 2026) ----
    "📸  Photo Dump": {
        "desc": "Fast cuts of your best moments, set to music",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Fade",
        "speed": 1.0, "filter": "None", "text_color": "White",
        "text_anim": "Pop in", "clip_anim": "Zoom in",
        "captions": False},
    "🔄  Before / After": {
        "desc": "The change hits on the beat — glow-up, room, look",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Glitch",
        "speed": 1.0, "filter": "None", "text_color": "Yellow",
        "text_anim": "Pop in", "clip_anim": "Flash",
        "captions": False},
    "💄  GRWM Loading": {
        "desc": "0% to 100% — get ready with me",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Fade",
        "speed": 1.0, "filter": "Smooth", "text_color": "White",
        "text_anim": "Typewriter", "clip_anim": "None",
        "captions": False},
    "👗  Outfit Change": {
        "desc": "A new look every 1–2 seconds, on the beat",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Slide",
        "speed": 1.0, "filter": "Warm", "text_color": "White",
        "text_anim": "None", "clip_anim": "Zoom pulse",
        "captions": False},
    "🔋  Recharged 1%→100%": {
        "desc": "From 1% to 100% — energy, glow-up, mood switch",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Zoom",
        "speed": 1.0, "filter": "Neon", "text_color": "Yellow",
        "text_anim": "Bounce", "clip_anim": "Zoom in",
        "captions": False},
    "✈️  Travel Reel": {
        "desc": "Slow pans, warm colours, cinematic trip",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Dissolve",
        "speed": 1.0, "filter": "Warm", "text_color": "White",
        "text_anim": "Fade in", "clip_anim": "Pan left",
        "captions": False},
    "🕺  Dance Trend": {
        "desc": "The move, on the beat, then the reveal",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Dissolve",
        "speed": 1.0, "filter": "None", "text_color": "White",
        "text_anim": "None", "clip_anim": "Shake",
        "captions": False},
    # ---- New templates (researched from trending CapCut / Reels
    # formats, Nov 2026) ----
    "⚡  Velocity Edit 2.0": {
        "desc": "Fast, slow, fast — the hero moment in slow-mo",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Glitch",
        "speed": 1.0, "ramp": "Hero", "filter": "Vivid", "text_color": "Yellow",
        "text_anim": "Pop in", "clip_anim": "Zoom pulse",
        "captions": False},
    "🖼️  Photo Dump Minimal": {
        "desc": "Clean white frames, slow pan — no clutter",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Fade",
        "speed": 1.0, "filter": "None", "text_color": "White",
        "text_anim": "None", "clip_anim": "Pan left", "border": True,
        "captions": False},
    "🥁  Beat Sync Pro": {
        "desc": "Every cut lands on the music beat",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Flash",
        "speed": 1.0, "filter": "Vivid", "text_color": "White",
        "text_anim": "Pop in", "clip_anim": "Flash",
        "captions": False},
    "🐢  Slow Motion Cinematic": {
        "desc": "Half speed, warm film look, slow zoom",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Dissolve",
        "speed": 0.5, "filter": "TealOrange", "text_color": "White",
        "text_anim": "Fade in", "clip_anim": "Zoom in",
        "captions": False},
    "📷  3D Zoom Photo": {
        "desc": "Flat photo pushed at you — parallax depth",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Zoom",
        "speed": 1.0, "filter": "Warm", "text_color": "White",
        "text_anim": "Fade in", "clip_anim": "Zoom in",
        "captions": False},
    "🎞️  Cinematic Letterbox": {
        "desc": "Movie bars, slow pan, film colour",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Dissolve",
        "speed": 1.0, "filter": "TealOrange", "text_color": "White",
        "text_anim": "Fade in", "clip_anim": "Pan left", "letterbox": True,
        "captions": False},
    "📼  Vintage / Retro Film": {
        "desc": "Old film grain, faded warm tones",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Fade",
        "speed": 1.0, "filter": "Vintage", "text_color": "White",
        "text_anim": "Fade in", "clip_anim": "Pan right", "grain": True,
        "captions": False},
    "🪝  Text Reveal Hook": {
        "desc": "Big animated hook in the first seconds",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "None",
        "speed": 1.0, "filter": "None", "text_color": "Yellow",
        "text_anim": "Pop in", "clip_anim": "None",
        "captions": True, "caption_style": "Beast Mode"},
    "🎵  Lyrics Highlight": {
        "desc": "Words light up gold as they are sung",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Fade",
        "speed": 1.0, "filter": "Cool", "text_color": "Cyan",
        "text_anim": "Wave", "clip_anim": "None",
        "captions": True, "caption_style": "Golden Karaoke"},
    "📹  Vlog / Day in the Life": {
        "desc": "Easy daily vlog, warm and calm",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Slide",
        "speed": 1.0, "filter": "Warm", "text_color": "White",
        "text_anim": "Slide up", "clip_anim": "Pan left",
        "captions": False},
    "💀  Gaming Kill Montage": {
        "desc": "Kills in slow-mo, then fast — shake on the hit",
        "ratio": "9:16  Vertical (TikTok / Reels)", "transition": "Glitch",
        "speed": 1.0, "ramp": "Hero", "filter": "Vivid", "text_color": "Yellow",
        "text_anim": "Shake", "clip_anim": "Shake",
        "captions": False},
    # ---- Meme time cards (SpongeBob-style, recreated with the
    # editor's own text system — big bold centred text, the same
    # phrases, no copied artwork or font). A meme template also
    # carries the phrase itself ("text") so applying it writes
    # the words on the clip; other templates leave the text
    # alone. Pair the sound by hand from the Sounds tab: time
    # cards → whoosh, To Be Continued → riser, Bruh → bruh,
    # Emotional Damage → emotional-damage, Dramatic → dun-dun-dunnn. ----
    "🕐  A Few Moments Later": {
        "desc": "\"A FEW MOMENTS LATER\" — the classic time card",
        "ratio": "16:9  Landscape", "transition": "Fade",
        "speed": 1.0, "filter": "None", "text_color": "White",
        "text_anim": "Pop in", "clip_anim": "None",
        "captions": False, "text": "A FEW MOMENTS LATER",
        "text_pos": "Middle", "text_style": "Normal"},
    "♾️  One Eternity Later": {
        "desc": "\"ONE ETERNITY LATER\" — the long wait",
        "ratio": "16:9  Landscape", "transition": "Fade",
        "speed": 1.0, "filter": "None", "text_color": "White",
        "text_anim": "Pop in", "clip_anim": "None",
        "captions": False, "text": "ONE ETERNITY LATER",
        "text_pos": "Middle", "text_style": "Normal"},
    "⏳  2000 Years Later": {
        "desc": "\"2000 YEARS LATER\" — the really long wait",
        "ratio": "16:9  Landscape", "transition": "Fade",
        "speed": 1.0, "filter": "None", "text_color": "White",
        "text_anim": "Pop in", "clip_anim": "None",
        "captions": False, "text": "2000 YEARS LATER",
        "text_pos": "Middle", "text_style": "Normal"},
    "⏱️  Twelve Seconds Later": {
        "desc": "\"TWELVE SECONDS LATER\" — barely a wait at all",
        "ratio": "16:9  Landscape", "transition": "Fade",
        "speed": 1.0, "filter": "None", "text_color": "White",
        "text_anim": "Pop in", "clip_anim": "None",
        "captions": False, "text": "TWELVE SECONDS LATER",
        "text_pos": "Middle", "text_style": "Normal"},
    "🕑  A Few Minutes Later": {
        "desc": "\"A FEW MINUTES LATER\" — the short wait",
        "ratio": "16:9  Landscape", "transition": "Fade",
        "speed": 1.0, "filter": "None", "text_color": "White",
        "text_anim": "Pop in", "clip_anim": "None",
        "captions": False, "text": "A FEW MINUTES LATER",
        "text_pos": "Middle", "text_style": "Normal"},
    "🌅  Tomorrow": {
        "desc": "\"TOMORROW\" — the next day",
        "ratio": "16:9  Landscape", "transition": "Fade",
        "speed": 1.0, "filter": "None", "text_color": "White",
        "text_anim": "Pop in", "clip_anim": "None",
        "captions": False, "text": "TOMORROW",
        "text_pos": "Middle", "text_style": "Normal"},
    "➡️  To Be Continued": {
        "desc": "\"TO BE CONTINUED\" — the JoJo arrow moment",
        "ratio": "16:9  Landscape", "transition": "Glitch",
        "speed": 1.0, "filter": "None", "text_color": "Cyan",
        "text_anim": "Pop in", "clip_anim": "Zoom pulse",
        "captions": False, "text": "TO BE CONTINUED",
        "text_pos": "Middle", "text_style": "Neon"},
    "😐  Bruh Moment": {
        "desc": "\"BRUH.\" — the deadpan moment",
        "ratio": "16:9  Landscape", "transition": "Glitch",
        "speed": 1.0, "filter": "None", "text_color": "Yellow",
        "text_anim": "Pop in", "clip_anim": "Shake",
        "captions": False, "text": "BRUH.",
        "text_pos": "Middle", "text_style": "Pill"},
    "💥  Emotional Damage": {
        "desc": "\"EMOTIONAL DAMAGE!\" — it hurts",
        "ratio": "16:9  Landscape", "transition": "Flash",
        "speed": 1.0, "filter": "None", "text_color": "Orange",
        "text_anim": "Pop in", "clip_anim": "Shake",
        "captions": False, "text": "EMOTIONAL DAMAGE!",
        "text_pos": "Middle", "text_style": "Pill"},
    "🎭  Dramatic Moment": {
        "desc": "\"DUN DUN DUNNN…\" — the dramatic reveal",
        "ratio": "16:9  Landscape", "transition": "Fade",
        "speed": 1.0, "filter": "None", "text_color": "Yellow",
        "text_anim": "Pop in", "clip_anim": "Zoom in",
        "captions": False, "text": "DUN DUN DUNNN…",
        "text_pos": "Middle", "text_style": "Neon"},
}


# Short ready-made meme video clips (rendered by
# make_meme_videos.py into meme-videos/ next to the editor, or
# next to the frozen .exe): (label, file name). Each one is a
# normal 2.5 s clip with its own sound mixed in when one exists.
# The Templates tab lists them with a "＋ Add" button each; a
# missing folder or file shows "Not ready yet" instead of
# breaking the tab.
MEME_VIDEOS = [
    ("A Few Moments Later", "a-few-moments-later.mp4"),
    ("One Eternity Later", "one-eternity-later.mp4"),
    ("2000 Years Later", "2000-years-later.mp4"),
    ("Twelve Seconds Later", "twelve-seconds-later.mp4"),
    ("A Few Minutes Later", "a-few-minutes-later.mp4"),
    ("Tomorrow", "tomorrow.mp4"),
    ("To Be Continued", "to-be-continued.mp4"),
    ("Bruh Moment", "bruh-moment.mp4"),
    ("Emotional Damage", "emotional-damage.mp4"),
    ("Dramatic Moment", "dramatic-moment.mp4"),
]


def _meme_video_folders():
    """Folders a meme video can live in (next to the editor, or
    next to the frozen .exe)."""
    cands = []
    try:
        cands.append(get_app_dir() / "meme-videos")
    except Exception:
        pass
    try:
        cands.append(Path(sys.executable).parent / "meme-videos")
    except Exception:
        pass
    return cands


def meme_video_path(fname):
    """Full path of a meme video file, or None when it is not
    on this PC yet (the clips are rendered separately and may
    still be on their way)."""
    for folder in _meme_video_folders():
        p = folder / fname
        if p.is_file():
            return str(p)
    return None


def meme_video_files():
    """[(label, path)] of every meme video on this PC: the 10
    known ones first (in order), then any other .mp4 in
    meme-videos/ (the 100-clip library, custom cards) sorted by
    name. A label is the pretty file name when the clip is not
    one of the known ten."""
    out = []
    seen = set()
    for label, fname in MEME_VIDEOS:
        p = meme_video_path(fname)
        if p:
            out.append((label, p))
            seen.add(fname.lower())
    for folder in _meme_video_folders():
        if folder.is_dir():
            for p in sorted(folder.glob("*.mp4")):
                if p.name.lower() not in seen:
                    seen.add(p.name.lower())
                    out.append((p.stem.replace("-", " ").replace("_", " ").title(),
                                str(p)))
    return out


def meme_sounds_available():
    """{stem: path} of the sounds in the library right now
    (sfx_library() only lists files that really exist)."""
    out = {}
    try:
        for _name, path in sfx_library():
            out[Path(path).stem] = path
    except Exception:
        pass
    return out


# Auto-Edit meme sounds: moment type -> (preferred sound, fallback
# sound). Stems, not display names. Only sounds in the library
# right now are ever used — a preferred sound that has not landed
# yet falls back silently, and a moment with no usable sound is
# skipped. (The meme sounds bruh / vine-boom / emotional-damage
# are still being collected; until their .wav files land, the
# fallbacks below are what plays.)
MEME_SOUND_MAP = {
    "loud": ("vine-boom", "boom"),
    "laugh": ("applause", "success"),
    "bruh": ("bruh", "pop"),
    "win": ("success", "coin"),
    "sad": ("emotional-damage", "sad-trombone"),
    "absurd": ("fahh", "pop"),
}
# The meme video card that fits each moment type (file in
# meme-videos/). Only the single strongest moment gets a card.
MEME_CARD_MAP = {
    "loud": "dramatic-moment.mp4",
    "laugh": "bruh-moment.mp4",
    "bruh": "bruh-moment.mp4",
    "win": "dramatic-moment.mp4",
    "sad": "emotional-damage.mp4",
    "absurd": "bruh-moment.mp4",
}


def new_clip(path, info=None):
    info = info or probe(path) or {}
    dur = float(info.get("duration", 0) or 0)
    return {"path": str(path), "start": 0.0, "end": dur, "speed": 1.0,
            "filter": "None", "text": "", "text_pos": "Bottom",
            "text_color": "White", "text_anim": "None",
            "text_style": "Normal", "clip_anim": "None",
            "ramp": "None", "reverse": False, "freeze": 0.0,
            "volume": 1.0, "stabilize": False, "denoise": False,
            "border": False, "lut": None, "lut_name": "",
            "sticker": "None",
            "sticker_pos": "Top Right", "mute": False,
            "enhance": False, "fade_in": 0.0, "fade_out": 0.0}


def clip_duration(clip):
    # Freeze adds still time at the start of the clip. A speed
    # ramp keeps the average speed at 1x, so it changes pacing
    # only, not the length.
    base = max(0.0, (clip["end"] - clip["start"]) / max(clip["speed"], 0.1))
    return base + float(clip.get("freeze", 0.0) or 0.0)


def _parse_freeze(text):
    try:
        return float(str(text).replace("s", "").strip())
    except Exception:
        return 0.0


def project_duration(project):
    return sum(clip_duration(c) for c in project["clips"])


def project_to_dict(project):
    """A whole editor project as plain JSON data, so it can be
    saved to a .json file and opened again later. The parsed .cube
    LUT itself (a numpy array) is not saved — only its name, so
    the user can load that .cube file again if needed."""
    clips = []
    for c in project.get("clips", []):
        cc = dict(c)
        cc.pop("lut", None)
        clips.append(cc)
    return {
        "format": "LiteGameRecorder-project",
        "version": 1,
        "clips": clips,
        "transition": project.get("transition", "None"),
        "ratio": project.get("ratio", "16:9  Landscape"),
        "quality": project.get("quality", "720p"),
        "caption_style": project.get("caption_style", "Normal"),
        "caption_size": project.get("caption_size", "Normal"),
        "caption_pos": project.get("caption_pos", "Bottom"),
        "caption_anim": project.get("caption_anim", "Pop word-by-word"),
        "title_style": project.get("title_style", "Flame"),
        "caption_lang": project.get("caption_lang", "en"),
        "bg_blur": bool(project.get("bg_blur", True)),
        "ai_model": project.get("ai_model", AI_MODELS[0]),
        "ollama_model": project.get("ollama_model", OLLAMA_MODEL),
        # The OpenRouter key is NOT saved here on purpose: a project
        # .json can be shared, and the key must never leak with it.
        # It lives in openrouter_key.txt next to the app instead.
        "captions": bool(project.get("captions", False)),
        "caption_edits": copy.deepcopy(project.get("caption_edits", {}) or {}),
        "normalize": bool(project.get("normalize", False)),
        "auto_memes": bool(project.get("auto_memes", True)),
        "music": project.get("music", ""),
        "music_vol": float(project.get("music_vol", 0.5) or 0.5),
        "music_fade": bool(project.get("music_fade", True)),
        "ducking": bool(project.get("ducking", False)),
        "letterbox": bool(project.get("letterbox", False)),
        "grain": bool(project.get("grain", False)),
        "sfx": copy.deepcopy(project.get("sfx", [])),
        "chapters": copy.deepcopy(project.get("chapters", [])),
    }


def project_from_dict(data):
    """Rebuild a project from saved JSON. Returns (project,
    missing) — `missing` is the list of clip files that no
    longer exist on this PC. Those clips are left out (an export
    would fail on them), and the caller warns the user about them."""
    if not isinstance(data, dict) or not isinstance(data.get("clips"), list):
        raise ValueError("That file is not a Lite Tutorial Maker project.")
    project = {
        "clips": [], "transition": str(data.get("transition", "None")),
        "ratio": str(data.get("ratio", "16:9  Landscape")),
        "quality": str(data.get("quality", "720p")),
        "caption_style": str(data.get("caption_style", "Normal")),
        "caption_size": str(data.get("caption_size", "Normal")),
        "caption_pos": str(data.get("caption_pos", "Bottom")),
        "caption_anim": str(data.get("caption_anim", "Pop word-by-word")),
        "title_style": str(data.get("title_style", "Flame")),
        "caption_lang": str(data.get("caption_lang", "en") or "en"),
        "bg_blur": bool(data.get("bg_blur", True)),
        "ai_model": str(data.get("ai_model", AI_MODELS[0])),
        "ollama_model": str(data.get("ollama_model", OLLAMA_MODEL) or OLLAMA_MODEL),
        # The key is read from openrouter_key.txt on this PC, never
        # from the project file (see project_to_dict).
        "openrouter_key": load_openrouter_key(),
        "captions": bool(data.get("captions", False)),
        "caption_edits": copy.deepcopy(data.get("caption_edits", {}) or {}),
        "normalize": bool(data.get("normalize", False)),
        "auto_memes": bool(data.get("auto_memes", True)),
        "music": str(data.get("music", "") or ""),
        "music_vol": float(data.get("music_vol", 0.5) or 0.5),
        "music_fade": bool(data.get("music_fade", True)),
        "ducking": bool(data.get("ducking", False)),
        "letterbox": bool(data.get("letterbox", False)),
        "grain": bool(data.get("grain", False)),
        "sfx": copy.deepcopy(data.get("sfx", []) or []),
        "chapters": copy.deepcopy(data.get("chapters", []) or []),
    }
    missing = []
    for saved in data["clips"]:
        if not isinstance(saved, dict):
            continue
        path = str(saved.get("path", "") or "")
        if not path or not Path(path).is_file():
            missing.append(path or "(no file name)")
            continue
        clip = new_clip(path, probe(path))
        for key in ("start", "end", "speed", "filter", "text", "text_pos",
                    "text_color", "text_anim", "text_style", "clip_anim",
                    "ramp", "reverse", "freeze", "volume", "stabilize",
                    "denoise", "border", "lut_name", "sticker",
                    "sticker_pos", "mute", "enhance", "fade_in", "fade_out"):
            if key in saved:
                clip[key] = saved[key]
        project["clips"].append(clip)
    return project, missing


def _find_tool(name):
    """Find ffmpeg/ffprobe: the app's own folder first (the installer
    puts ffmpeg.exe + ffprobe.exe next to the app), then the PATH.
    If ffprobe is missing, probe() reports has_audio=False and the
    editor silently drops clip audio on export — that is how edited
    videos used to come out with no sound at all."""
    import sys
    cands = []
    try:
        cands.append(Path(sys.executable).parent / (name + (".exe" if sys.platform == "win32" else "")))
    except Exception:
        pass
    try:
        app_dir = get_app_dir()
        cands.append(app_dir / (name + (".exe" if sys.platform == "win32" else "")))
        cands.append(app_dir / name)
    except Exception:
        pass
    for c in cands:
        try:
            if c.is_file():
                return str(c)
        except Exception:
            pass
    return shutil.which(name)


def _ffmpeg():
    """The ffmpeg binary to run: the bundled one next to the app, or
    'ffmpeg' from the PATH."""
    return _find_tool("ffmpeg") or "ffmpeg"


def probe(path):
    """{duration, fps, width, height, has_audio} for a video file."""
    try:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        has_audio = False
        fp = _find_tool("ffprobe")
        if fp:
            try:
                out = subprocess.run(
                    [fp, "-v", "error", "-select_streams", "a",
                     "-show_entries", "stream=index", "-of", "csv=p=0",
                     str(path)], capture_output=True, text=True,
                    timeout=15).stdout.strip()
                has_audio = bool(out)
            except Exception:
                has_audio = False
        return {"duration": frames / fps if fps else 0.0, "fps": fps,
                "width": w, "height": h, "has_audio": has_audio}
    except Exception:
        return None


def ffmpeg_available():
    return _find_tool("ffmpeg") is not None


def _parse_speed(text):
    try:
        return float(str(text).replace("x", "").strip())
    except Exception:
        return 1.0


# ---------- drawing helpers ----------
def _draw_text_at(frame, text, x, y, scale, color, thick):
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, text, (x, y), font, scale, (0, 0, 0), thick + 3,
                cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), font, scale, color, thick, cv2.LINE_AA)


def _caption_outline(frame, text, x, y, font, scale, color, thick, outline):
    """One word with a black outline (outline px around the letters),
    so it stays readable over any footage."""
    cv2.putText(frame, text, (x, y), font, scale, (0, 0, 0),
                thick + outline, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), font, scale, color, thick, cv2.LINE_AA)


CAPTION_ANIMS = ["Pop word-by-word", "Karaoke", "Bounce", "Slide up",
                 "Typewriter"]
# Caption size menu -> word scale multiplier.
_CAPTION_SIZE_MULT = {"Small": 0.75, "Normal": 1.0, "Large": 1.35}


def draw_caption_words(frame, segment, t, style="Karaoke",
                       scale_mult=1.0, pos="Bottom",
                       anim="Pop word-by-word"):
    """Word-by-word animated captions. `segment` is
    {start, end, text, words:[{start, end, word}]} and `t` is the time
    in the clip. `scale_mult` scales the words (Small 0.75, Normal 1,
    Large 1.35); `pos` is Top / Middle / Bottom. Styles (researched
    from Reels/TikTok 2026):
    Karaoke = spoken word yellow; Hormozi = spoken word on a green
    pill; Beast Mode = ALL CAPS, spoken word yellow + 1.18x swell;
    Golden Karaoke = words stay gold once sung; Neon = cyan/pink
    glow; Typewriter = letters appear as spoken; Gradient Pop =
    words bounce in; Minimal = gentle fade; Bouncing Ball = a ball
    hops above the spoken word; Word Punch = each word slams in big;
    TikTok Box = white on a dark box; Gamer = neon green + glitch."""
    words = segment.get("words") or []
    if not words:
        return draw_text(frame, segment.get("text", ""), pos, "White",
                         scale=max(0.8, h / 480.0) * max(0.5, float(scale_mult or 1.0)))
    h, w = frame.shape[:2]
    scale = max(0.8, h / 480.0) * max(0.5, float(scale_mult or 1.0))
    font = cv2.FONT_HERSHEY_SIMPLEX
    thick = max(2, int(scale * 2))
    style = style or "Karaoke"
    caps = style in ("Hormozi", "Beast Mode", "Word Punch", "Gradient Pop", "Gamer")
    texts = [wd["word"].upper() if caps else wd["word"] for wd in words]
    # Layout at the base scale, so the line stays centred as words
    # light up; active words may draw slightly bigger in their slot.
    widths = []
    total = 0
    for txt in texts:
        (tw, _), _ = cv2.getTextSize(txt, font, scale, thick)
        widths.append(tw)
        total += tw
    space_w, _ = cv2.getTextSize(" ", font, scale, thick)[0]
    total += space_w * max(0, len(words) - 1)
    x0 = max(8, (w - total) // 2)
    (tw0, th0), _ = cv2.getTextSize(texts[0], font, scale, thick)
    if pos == "Top":
        y = 40 + th0
    elif pos == "Middle":
        y = h // 2
    else:
        y = h - 30
    # TikTok Box: dark rounded box behind the whole line first.
    if style == "TikTok Box":
        pad = 14
        box = np.zeros((th0 + pad * 2, total + pad * 2, 3), dtype=np.uint8)
        cv2.rectangle(box, (0, 0), (box.shape[1] - 1, box.shape[0] - 1),
                      (20, 20, 20), -1)
        bx, by = x0 - pad, y - th0 - pad
        by = max(0, min(h - box.shape[0], by))
        bx = max(0, min(w - box.shape[1], bx))
        roi = frame[by:by + box.shape[0], bx:bx + box.shape[1]]
        frame[by:by + box.shape[0], bx:bx + box.shape[1]] = cv2.addWeighted(
            roi, 0.4, box, 0.6, 0)
    # Typewriter: only the letters spoken so far are shown.
    if style == "Typewriter" or anim == "Typewriter":
        shown = []
        for wd in words:
            if t >= wd["end"]:
                shown.append(wd["word"])
            elif t >= wd["start"]:
                frac = (t - wd["start"]) / max(0.01, wd["end"] - wd["start"])
                shown.append(wd["word"][:max(1, int(len(wd["word"]) * frac))])
        if shown:
            line = " ".join(shown)
            (lw, _), _ = cv2.getTextSize(line, font, scale, thick)
            _caption_outline(frame, line, max(8, (w - lw) // 2), y,
                             font, scale, (255, 255, 255), thick, 3)
        return frame
    x = x0
    for i, wd in enumerate(words):
        txt = texts[i]
        active = wd["start"] <= t <= wd["end"]
        spoken = t > wd["end"]
        sc, th = scale, thick
        col = (255, 255, 255)
        outline = 3
        # Caption animation (Project panel): a word appears exactly
        # when it is spoken — unspoken words stay hidden for the
        # pop / bounce / slide animations.
        if anim in ("Pop word-by-word", "Bounce", "Slide up") and t < wd["start"]:
            x += widths[i] + space_w
            continue
        if style == "Karaoke":
            col = (0, 255, 255) if active else (255, 255, 255)
            if active:
                sc, th = scale * 1.15, max(2, int(scale * 1.15 * 2))
        elif style == "Hormozi":
            # Spoken word sits on a solid green pill.
            if active:
                sc, th = scale * 1.1, max(2, int(scale * 1.1 * 2))
                (aw, ah), _ = cv2.getTextSize(txt, font, sc, th)
                cv2.rectangle(frame, (x - 8, y - ah - 8), (x + aw + 8, y + 8),
                              (102, 255, 0), -1)
                cv2.putText(frame, txt, (x, y), font, sc, (255, 255, 255), th,
                            cv2.LINE_AA)
                x += widths[i] + space_w
                continue
        elif style == "Beast Mode":
            # Spoken word flashes yellow and swells 1.18x, hard outline.
            outline = max(3, int(scale * 14 / 10))
            if active:
                col = (0, 230, 255)
                sc, th = scale * 1.18, max(2, int(scale * 1.18 * 2))
        elif style == "Golden Karaoke":
            col = (0, 190, 255) if (active or spoken) else (255, 255, 255)
        elif style == "Neon":
            col = (255, 0, 255) if active else (255, 255, 0)
            if active:
                sc, th = scale * 1.1, max(2, int(scale * 1.1 * 2))
        elif style == "Gradient Pop":
            col = (180, 105, 255) if active else (255, 255, 255)
            if active:
                sc, th = scale * 1.15, max(2, int(scale * 1.15 * 2))
            elif t < wd["start"]:
                x += widths[i] + space_w
                continue
        elif style == "Minimal":
            # Words fade in gently as they are spoken.
            if t < wd["start"]:
                x += widths[i] + space_w
                continue
            if active:
                col = (255, 255, 255)
        elif style == "Word Punch":
            if t < wd["start"]:
                x += widths[i] + space_w
                continue
            age = t - wd["start"]
            punch = 1.0 + 0.3 * max(0.0, 1.0 - age / 0.15)
            sc, th = scale * punch, max(2, int(scale * punch * 2))
            col = (0, 230, 255) if active else (255, 255, 255)
        elif style == "Gamer":
            col = (0, 255, 0) if active else (255, 255, 255)
            if t < wd["start"]:
                x += widths[i] + space_w
                continue
            if active:
                rng = np.random.default_rng(int(t * 24) + i)
                dx = int(rng.integers(-3, 4))
                _caption_outline(frame, txt, x + dx, y, font, sc, col, th, 3)
                x += widths[i] + space_w
                continue
        elif style == "Bouncing Ball":
            col = (0, 230, 255) if (active or spoken) else (255, 255, 255)
        # Caption animation: the spoken word is emphasised (bigger /
        # coloured) while the other words of the line stay visible
        # but dimmer — the viral TikTok/Reels look.
        wy = y
        if anim == "Pop word-by-word":
            if active:
                sc, th = sc * 1.25, max(2, int(th * 1.25))
                col = (0, 255, 255)
            elif spoken:
                col = (190, 190, 190)
        elif anim == "Bounce":
            age = t - wd["start"]
            bounce = 1.0 + 0.35 * max(0.0, np.sin(age * 14.0)) * np.exp(-age * 4.0)
            sc, th = sc * bounce, max(2, int(th * bounce))
            if active:
                col = (0, 255, 255)
        elif anim == "Slide up":
            age = t - wd["start"]
            wy = y + int(16 * np.exp(-age * 4.0))
            if active:
                col = (0, 255, 255)
        elif anim == "Karaoke":
            if active:
                col = (0, 255, 255)
                sc, th = sc * 1.15, max(2, int(th * 1.15))
        _caption_outline(frame, txt, x, wy, font, sc, col, th, outline)
        if style == "Neon" and active:
            # Glow: a blurred copy of the word behind it.
            glow = np.zeros_like(frame)
            cv2.putText(glow, txt, (x, y), font, sc, col, th + 4, cv2.LINE_AA)
            glow = cv2.GaussianBlur(glow, (0, 0), 6)
            frame[:] = cv2.addWeighted(frame, 1.0, glow, 0.7, 0)
            _caption_outline(frame, txt, x, y, font, sc, col, th, outline)
        if style == "Bouncing Ball" and active:
            # A ball hops in an arc above the spoken word.
            frac = (t - wd["start"]) / max(0.01, wd["end"] - wd["start"])
            bx = x + widths[i] // 2
            by = y - th0 - 8 - int(14 * np.sin(np.pi * min(1.0, frac)))
            cv2.circle(frame, (bx, by), 7, (0, 230, 255), -1)
            cv2.circle(frame, (bx, by), 7, (0, 0, 0), 2)
        x += widths[i] + space_w
    return frame


def draw_text(frame, text, pos="Bottom", color_name="White", scale=None,
              anim="None", t=0.0, style="Normal"):
    """Big readable caption text with a black outline, plus a
    CapCut-style animation. `t` is seconds into the clip.
    In animations (first 0.6 s): Fade in, Pop in, Slide up,
    Typewriter. Loop animations (whole clip): Bounce, Wave, Shake,
    Glitch."""
    if not text:
        return frame
    h, w = frame.shape[:2]
    scale = scale or max(0.8, h / 480.0)
    color = TEXT_COLORS.get(color_name, (255, 255, 255))
    thick = max(2, int(scale * 2))
    anim = anim or "None"
    # --- in-animations: progress over the first 0.6 s ---
    p = min(1.0, max(0.0, t / 0.6))
    show = text
    dx, dy = 0, 0
    sc = scale
    if anim == "Typewriter":
        n = int(t / 0.08) + 1
        show = text[:max(1, min(len(text), n))]
    elif anim == "Pop in":
        sc = scale * (0.4 + 0.6 * (1.0 - (1.0 - p) ** 3))
    elif anim == "Slide up":
        dy = int((1.0 - p) * 50)
    elif anim == "Bounce":
        sc = scale * (1.0 + 0.25 * np.sin(t * 9.0) * np.exp(-t * 1.5))
    elif anim == "Wave":
        dy = int(6 * np.sin(t * 6.0))
    elif anim == "Shake":
        rng = np.random.default_rng(int(t * 24) + 7)
        dx, dy = int(rng.integers(-5, 6)), int(rng.integers(-5, 6))
    thick = max(2, int(sc * 2))
    (tw, th), _ = cv2.getTextSize(show, cv2.FONT_HERSHEY_SIMPLEX, sc, thick)
    x = max(8, (w - tw) // 2) + dx
    if pos == "Top":
        y = 40 + th
    elif pos == "Middle":
        y = h // 2
    else:
        y = h - 30
    y += dy
    if style == "Pill":
        # Dark rounded-ish background pill behind the text.
        pad = 16
        overlay = frame.copy()
        cv2.rectangle(overlay, (max(0, x - pad), y - th - pad),
                      (min(w, x + tw + pad), y + pad), (0, 0, 0), -1)
        frame = cv2.addWeighted(overlay, 0.65, frame, 0.35, 0)
    elif style == "Neon":
        # Glow: the same text, thick and blurred, behind the text.
        glow = frame.copy()
        _draw_text_at(glow, show, x, y, sc, color, thick + 6)
        glow = cv2.GaussianBlur(glow, (0, 0), 6)
        frame = cv2.addWeighted(glow, 0.8, frame, 0.2, 0)
    if anim == "Fade in" and p < 1.0:
        overlay = frame.copy()
        _draw_text_at(overlay, show, x, y, sc, color, thick)
        return cv2.addWeighted(overlay, p, frame, 1.0 - p, 0)
    if anim == "Glitch":
        # RGB-split ghost copies, like a broken TV signal.
        for (ox, col) in [(-6, (0, 0, 255)), (6, (255, 0, 0))]:
            cv2.putText(frame, show, (x + ox, y), cv2.FONT_HERSHEY_SIMPLEX,
                        sc, col, thick, cv2.LINE_AA)
    _draw_text_at(frame, show, x, y, sc, color, thick)
    return frame


def apply_clip_anim(frame, anim, t, dur, frame_index=0):
    """Motion for the whole clip, like CapCut effects:
    slow zoom in/out, pan, shake, glitch (RGB split), zoom pulse
    (beat), flash. `t` is seconds into the clip, `dur` its length."""
    if not anim or anim == "None":
        return frame
    h, w = frame.shape[:2]
    if anim in ("Zoom in", "Zoom out"):
        frac = min(1.0, max(0.0, t / max(dur, 0.1)))
        s = 1.0 + 0.15 * frac if anim == "Zoom in" else 1.15 - 0.15 * frac
        nw, nh = int(w * s), int(h * s)
        big = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x0, y0 = (nw - w) // 2, (nh - h) // 2
        return big[y0:y0 + h, x0:x0 + w]
    if anim in ("Pan left", "Pan right"):
        frac = min(1.0, max(0.0, t / max(dur, 0.1)))
        s = 1.12
        nw, nh = int(w * s), int(h * s)
        big = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        max_x = nw - w
        x0 = int(max_x * frac) if anim == "Pan left" else int(max_x * (1.0 - frac))
        y0 = (nh - h) // 2
        return big[y0:y0 + h, x0:x0 + w]
    if anim == "Shake":
        rng = np.random.default_rng(frame_index)
        dx, dy = int(rng.integers(-9, 10)), int(rng.integers(-9, 10))
        m = np.float32([[1, 0, dx], [0, 1, dy]])
        return cv2.warpAffine(frame, m, (w, h),
                              borderMode=cv2.BORDER_REFLECT)
    if anim == "Glitch":
        if frame_index % 6 < 2:
            out = frame.copy()
            b, g, r = cv2.split(frame)
            shift = 8 if frame_index % 6 == 0 else -8
            b = np.roll(b, shift, axis=1)
            r = np.roll(r, -shift, axis=1)
            out = cv2.merge([b, g, r])
            # A torn horizontal band.
            y0 = (frame_index * 37) % h
            out[y0:min(h, y0 + 14), :] = np.roll(
                out[y0:min(h, y0 + 14), :], 20, axis=1)
            return out
        return frame
    if anim == "Zoom pulse":
        s = 1.0 + 0.08 * abs(np.sin(t * 3.0))
        nw, nh = int(w * s), int(h * s)
        big = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x0, y0 = (nw - w) // 2, (nh - h) // 2
        return big[y0:y0 + h, x0:x0 + w]
    if anim == "Flash":
        # Quick white flash once a second.
        phase = (t % 1.0)
        if phase < 0.12:
            alpha = 0.55 * (1.0 - phase / 0.12)
            white = np.full_like(frame, 255)
            return cv2.addWeighted(white, alpha, frame, 1.0 - alpha, 0)
        return frame
    if anim == "Jelly":
        # Scale wobble on the beat (the popular "jelly" effect).
        s = 1.0 + 0.05 * np.sin(t * 2 * np.pi * 2.0)
        nw, nh = int(w * s), int(h * s)
        if s >= 1.0:
            big = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
            x0, y0 = (nw - w) // 2, (nh - h) // 2
            return big[y0:y0 + h, x0:x0 + w]
        small = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        out = np.zeros_like(frame)
        out[(h - nh) // 2:(h - nh) // 2 + nh,
            (w - nw) // 2:(w - nw) // 2 + nw] = small
        return out
    return frame


def draw_sticker(frame, emoji, pos="Top Right"):
    """Emoji sticker drawn as big text (no image files needed)."""
    if not emoji or emoji == "None":
        return frame
    h, w = frame.shape[:2]
    scale = max(1.2, h / 360.0)
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(emoji, font, scale, 3)
    margin = 24
    if "Left" in pos:
        x = margin
    elif "Right" in pos:
        x = w - tw - margin
    else:
        x = (w - tw) // 2
    if "Top" in pos:
        y = margin + th
    elif "Bottom" in pos:
        y = h - margin
    else:
        y = (h + th) // 2
    cv2.putText(frame, emoji, (x, y), font, scale, (0, 0, 0), 6, cv2.LINE_AA)
    cv2.putText(frame, emoji, (x, y), font, scale, (255, 255, 255), 3,
                cv2.LINE_AA)
    return frame


class SmartReframe:
    """Auto Reframe (Premiere / CapCut): for a 9:16 export, crop a
    vertical window that follows the detected face, smoothed so the
    pan stays calm. No face (or no face detector) = centre crop."""
    def __init__(self, out_w=720, out_h=1280):
        self.out_w, self.out_h = out_w, out_h
        self.cx = None
        self.face = None
        try:
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(path)
            if not cascade.empty():
                self.face = cascade
        except Exception:
            self.face = None

    def crop(self, frame):
        h, w = frame.shape[:2]
        cw = int(h * self.out_w / self.out_h)
        cw = min(w, max(8, cw))
        if self.face is not None:
            try:
                # 480 px wide (not 320): a small face in the corner of
                # a 720p frame is ~30 px at 320 and Haar misses it.
                small = cv2.resize(frame, (480, max(8, int(480 * h / w))))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                faces = self.face.detectMultiScale(gray, 1.2, 4,
                                                   minSize=(24, 24))
                if len(faces):
                    x, _y, fw, _fh = max(faces, key=lambda b: b[2] * b[3])
                    fx = (x + fw / 2) / small.shape[1]
                    self.cx = fx if self.cx is None else 0.75 * self.cx + 0.25 * fx
            except Exception:
                pass
        cx = self.cx if self.cx is not None else 0.5
        x0 = int(np.clip(cx * w - cw / 2, 0, w - cw))
        return frame[:, x0:x0 + cw]


def detect_silences(path, start, end, min_silence=0.7, noise_db=-35):
    """Find the parts of a clip that have sound. Returns
    ([(start, end), ...] in clip time, error_or_empty). Silences
    longer than min_silence are cut out."""
    import re
    if not ffmpeg_available():
        return None, "Remove silence needs FFmpeg."
    cmd = [_ffmpeg(), "-v", "info", "-ss", str(start), "-to", str(end),
           "-i", str(path), "-af",
           "silencedetect=noise=%ddB:d=%.2f" % (noise_db, min_silence),
           "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as exc:
        return None, "Could not read the clip audio: %s" % exc
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    dur = max(0.0, end - start)
    kept = []
    cur = 0.0
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else dur
        if s > cur:
            kept.append((cur, s))
        cur = max(cur, e)
    if cur < dur:
        kept.append((cur, dur))
    # Keep a breath of air at the edges so words are not clipped,
    # and drop slivers shorter than 0.4 s.
    out = []
    for (s, e) in kept:
        s2, e2 = max(0.0, s - 0.1), min(dur, e + 0.1)
        if e2 - s2 < 0.4:
            continue
        if out and s2 <= out[-1][1] + 0.05:
            out[-1] = (out[-1][0], e2)
        else:
            out.append((s2, e2))
    return [(start + s, start + e) for (s, e) in out], ""


def tidy_kept_segments(kept, max_gap=0.5, min_len=0.4):
    """Clean up the talking parts from detect_silences: join pieces
    separated by a short natural pause (under max_gap — a breath
    between words stays in the video), then drop slivers shorter
    than min_len. Returns a new list of (start, end)."""
    if not kept:
        return []
    merged = []
    for (s, e) in sorted(kept):
        if merged and s - merged[-1][1] < max_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((float(s), float(e)))
    return [(s, e) for (s, e) in merged if e - s >= min_len]


def clip_waveform(path, start, end, n=48):
    """RMS loudness per window (0..1) for a clip's audio, for the
    timeline waveform. Returns [] when there is no audio or FFmpeg
    is missing. The RMS math is the same as detect_beats uses."""
    if not ffmpeg_available() or n <= 0:
        return []
    dur = max(0.0, float(end) - float(start))
    if dur <= 0:
        return []
    import tempfile, wave as wavmod
    wav = os.path.join(tempfile.gettempdir(), "lgr_wave_%d.wav" % os.getpid())
    r = subprocess.run([_ffmpeg(), "-y", "-v", "error",
                        "-ss", "%.3f" % float(start), "-to", "%.3f" % float(end),
                        "-i", str(path), "-vn", "-ac", "1", "-ar", "22050", wav],
                       capture_output=True, timeout=120)
    if r.returncode != 0 or not os.path.exists(wav):
        return []
    try:
        with wavmod.open(wav, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    except Exception:
        return []
    if len(data) == 0:
        return []
    win = max(1, len(data) // n)
    m = max(1, len(data) // win)
    rms = np.sqrt(np.mean(data[:m * win].reshape(m, win) ** 2, axis=1))
    if m != n:
        idx = np.linspace(0, m - 1, n).astype(int)
        rms = rms[idx]
    peak = float(rms.max()) if len(rms) else 0.0
    if peak <= 1e-6:
        return [0.0] * n
    return [float(min(1.0, v / peak)) for v in rms]


def detect_beats(path, min_gap=0.3):
    """Beat times (seconds) in a music file: peaks of the sound
    energy. Returns ([times], error_or_empty)."""
    if not ffmpeg_available():
        return [], "Beat sync needs FFmpeg."
    import tempfile, wave as wavmod
    wav = os.path.join(tempfile.gettempdir(), "lgr_beats.wav")
    r = subprocess.run([_ffmpeg(), "-y", "-v", "error", "-i", str(path),
                        "-ac", "1", "-ar", "22050", wav],
                       capture_output=True, timeout=300)
    if r.returncode != 0 or not os.path.exists(wav):
        return [], "Could not read the music file."
    try:
        with wavmod.open(wav, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    except Exception as exc:
        return [], "Could not read the music: %s" % exc
    sr = 22050
    win = int(sr * 0.04)
    nwin = max(1, len(data) // win)
    if nwin < 8:
        return [], "The music is too short to find beats."
    rms = np.sqrt(np.mean(data[:nwin * win].reshape(nwin, win) ** 2, axis=1))
    sm = np.convolve(rms, np.ones(5) / 5.0, mode="same")
    thresh = float(np.max(sm)) * 0.45 if len(sm) else 0.0
    beats = []
    last = -10.0
    for i in range(1, len(sm) - 1):
        t = i * win / sr
        if sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1] and sm[i] > thresh:
            if t - last >= min_gap:
                beats.append(round(t, 2))
                last = t
    return beats, ""


# ---------- free AI (all on-device, no downloads, no API key) ----------
def detect_scenes(path, threshold=0.4):
    """Scene-change times (seconds) in a video, from FFmpeg's own
    scene detector. Returns ([times], error_or_empty)."""
    if not ffmpeg_available():
        return [], "Scene split needs FFmpeg."
    cmd = [_ffmpeg(), "-v", "info", "-i", str(path),
           "-vf", "select='gt(scene,%.2f)',showinfo" % threshold,
           "-f", "null", "-"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as exc:
        return [], str(exc)
    times = []
    for line in res.stderr.splitlines():
        if "pts_time:" not in line:
            continue
        try:
            t = float(line.split("pts_time:")[1].split()[0])
            if t > 0.3:
                times.append(round(t, 2))
        except Exception:
            pass
    return times, ""


# ---------- OpenClip ideas (free, offline) ----------
# OpenClip (github.com/linzzzzzz/openclip) is an open-source AI auto
# video editor: transcribe the video, rank the moments, cut the best
# parts into shorts with titles and covers. Its brain is a cloud LLM,
# but these five ideas work free and offline with the tools we
# already have (the faster-whisper transcript, word timestamps,
# audio energy, OpenCV frames). No API key, no GPU, no upload.
# NOT copied: speaker labels (needs a HuggingFace token, heavy and
# slow on a weak laptop), bilingual translation (needs a cloud LLM),
# downloading a video from a URL (yt-dlp fights bot-checks, and
# re-uploading someone else's video is a copyright problem).


def project_clip_offsets(project):
    """Project time where each clip's written frames start. The 0.5 s
    transition overlap is taken out (same maths as
    project_captions_srt), so the offsets match the exported video."""
    clips = project.get("clips", [])
    overlap = 0.5 if project.get("transition", "None") != "None" else 0.0
    offsets = []
    acc = 0.0
    for ci, clip in enumerate(clips):
        offsets.append(acc)
        acc += clip_duration(clip) - (overlap if ci < len(clips) - 1 else 0.0)
    return offsets


def project_export_duration(project):
    """Total length of the exported video (transition overlaps
    taken out, same maths as project_clip_offsets)."""
    offs = project_clip_offsets(project)
    clips = project.get("clips", [])
    if not clips:
        return 0.0
    return offs[-1] + clip_duration(clips[-1])


def export_to_cumulative(project, t):
    """An export-timeline time (transition overlaps subtracted, as
    the captions and the audio mix use) -> the plain cumulative
    time the timeline and _split_clip_at use. (Freeze cancels out:
    it sits at the clip start in both timelines.)"""
    clips = project.get("clips", [])
    if not clips:
        return float(t)
    offs = project_clip_offsets(project)
    cum = 0.0
    for ci, c in enumerate(clips):
        d = clip_duration(c)
        if offs[ci] <= t < offs[ci] + d:
            return cum + (t - offs[ci])
        cum += d
    return cum


def clip_local_to_project(project, ci, local_t):
    """A clip-local time (seconds into the trimmed clip, 0-based, as
    make_captions returns) -> project time in the exported video."""
    clips = project.get("clips", [])
    if ci < 0 or ci >= len(clips):
        return float(local_t)
    c = clips[ci]
    offs = project_clip_offsets(project)
    speed = max(0.1, float(c.get("speed", 1.0)))
    freeze = float(c.get("freeze", 0.0) or 0.0)
    return offs[ci] + freeze + float(local_t) / speed


def project_to_clip_local(project, ci, proj_t):
    """Project time -> clip-local time (0-based within the trim)."""
    clips = project.get("clips", [])
    if ci < 0 or ci >= len(clips):
        return float(proj_t)
    c = clips[ci]
    offs = project_clip_offsets(project)
    speed = max(0.1, float(c.get("speed", 1.0)))
    freeze = float(c.get("freeze", 0.0) or 0.0)
    return (float(proj_t) - offs[ci] - freeze) * speed


def audio_energy_series(wav_path, win=0.25):
    """RMS energy of a WAV in short windows: (times, rms) numpy
    arrays. Same reading as analyze_highlights, so the two agree."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            raw = wf.readframes(wf.getnframes())
    except Exception:
        return None, None
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    if len(data) == 0:
        return None, None
    step = max(1, int(win * sr))
    n = len(data) // step
    if n == 0:
        return None, None
    rms = np.sqrt(np.mean(data[:n * step].reshape(n, step) ** 2, axis=1))
    return np.arange(n) * win, rms


def score_keyword_highlights(all_segments, keywords, energy=None, total=0.0, top_n=5):
    """Rank transcript segments by what the user asked for.
    all_segments: [(proj_start, proj_end, text, words)] in project
    time. keywords: [str] (e.g. ["goal", "funny"]). energy:
    optional (times, rms) from audio_energy_series — a loud moment
    (a cheer, a laugh, applause) counts extra. Returns
    [(start, end, score, matched_text)] sorted by time, best first
    by score, top_n only. A segment is kept at least 1.5 s long so
    a short clip is still watchable."""
    kws = [str(k).strip().lower() for k in (keywords or []) if str(k).strip()]
    if not kws:
        return []
    times, rms = (None, None)
    if energy is not None:
        times, rms = energy
    max_rms = float(rms.max()) if rms is not None and len(rms) else 0.0
    scored = []
    for (s, e, text, words) in all_segments:
        txt = str(text or "")
        low = txt.lower()
        score = 0.0
        matched = []
        for kw in kws:
            n = low.count(kw)
            if n:
                matched.append(kw)
                score += 3.0 + 1.0 * (n - 1)
        if not matched:
            continue  # the keywords are the filter
        if "?" in txt:
            score += 2.0  # a question hooks the viewer
        if "!" in txt:
            score += 2.0  # excitement
        dur = max(0.1, float(e) - float(s))
        n_words = len(words) if words else len(txt.split())
        if n_words / dur > 2.5:
            score += 1.5  # fast talking = excited
        if max_rms > 0 and times is not None:
            m = (times >= float(s)) & (times <= float(e))
            if m.any():
                score += 4.0 * float(rms[m].mean()) / max_rms
        s2, e2 = float(s), float(e)
        if e2 - s2 < 1.5:  # keep it watchable: at least 1.5 s
            mid = (s2 + e2) / 2.0
            s2 = max(0.0, mid - 0.75)
            e2 = min(float(total) if total > 0 else e2, mid + 0.75)
        if e2 - s2 < 0.4:
            continue
        scored.append((s2, e2, score, txt.strip()))
    scored.sort(key=lambda x: -x[2])
    top = scored[:max(1, top_n)]
    top.sort(key=lambda x: x[0])
    return top


def snap_to_word_boundary(t, boundaries, tol=0.3):
    """Snap a cut time to the nearest caption word boundary (a word
    start or end) if one is within ±tol seconds — so a cut never
    lands in the middle of a spoken word. Returns t unchanged when
    there is no word boundary nearby."""
    if not boundaries:
        return float(t)
    best = min(boundaries, key=lambda b: abs(b - float(t)))
    return float(best) if abs(best - float(t)) <= tol else float(t)


def parse_srt(path):
    """Read a .srt subtitle file: [{start, end, text, words:[...]}]
    in seconds, in the file's own (absolute) time. Words are spread
    evenly across the line (a .srt has no word timings), so Karaoke
    still works. Returns (segments, error_message)."""
    import re
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except Exception as exc:
        return [], "Could not read the .srt file: %s" % exc
    pat = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*"
                     r"(\d+):(\d+):(\d+)[,.](\d+)")

    def _t(h, mi, s, ms):
        return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000.0

    segs = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        lines = [ln.strip() for ln in block.strip().split("\n") if ln.strip()]
        if not lines:
            continue
        ti, m = None, None
        for i, ln in enumerate(lines):
            m = pat.search(ln)
            if m:
                ti = i
                break
        if m is None:
            continue
        s = _t(*m.groups()[:4])
        e = _t(*m.groups()[4:])
        txt = " ".join(lines[ti + 1:]).strip()
        if not txt or e <= s:
            continue
        segs.append({"start": s, "end": e, "text": txt,
                     "words": _redistribute_words(txt, s, e)})
    if not segs:
        return [], "No captions found in that .srt file."
    return segs, ""


def shift_srt_segments(segs, start, end):
    """Shift .srt segments (absolute file time) to clip-local time
    (0-based within the trim [start, end]) and cut them to the trim.
    Words are re-spread across the kept part."""
    dur = max(0.0, float(end) - float(start))
    out = []
    for s in segs or []:
        a = float(s["start"]) - float(start)
        b = float(s["end"]) - float(start)
        if b <= 0 or a >= dur:
            continue
        a = max(0.0, a)
        b = min(dur, b)
        if b - a < 0.05:
            continue
        txt = str(s.get("text", "")).strip()
        out.append({"start": a, "end": b, "text": txt,
                    "words": _redistribute_words(txt, a, b)})
    return out


def srt_path_next_to(video_path):
    """The .srt file next to a video (same name, .srt ending), or
    None. A video downloaded with subtitles, or a YouTube caption
    file, often sits right there — use it instead of listening
    again."""
    p = Path(str(video_path))
    cand = p.with_suffix(".srt")
    return cand if cand.is_file() else None


def srt_segments_for_clip(video_path, start, end):
    """The .srt next to a video, shifted to clip-local time and cut
    to the trim. Returns (segments, error). ([], "") when there is
    no .srt next to the video."""
    srt = srt_path_next_to(video_path)
    if srt is None:
        return [], ""
    segs, err = parse_srt(srt)
    if err:
        return [], err
    return shift_srt_segments(segs, start, end), ""


def best_title_for_clip(segments):
    """The most striking sentence of a clip's transcript — the title
    for a short or a cover. A sentence with ! or ? wins, then a
    medium-length one (3-12 words). Returns "" when there is no
    transcript."""
    import re
    best, best_score = "", -1.0
    for s in segments or []:
        txt = str(s.get("text", "") or "").strip()
        if not txt:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", txt):
            sent = sent.strip().strip("\"'“”")
            if not sent:
                continue
            words = sent.split()
            sc = 0.0
            if "!" in sent:
                sc += 2.0
            if "?" in sent:
                sc += 1.5
            if 3 <= len(words) <= 12:
                sc += 1.0
            sc += min(len(sent), 40) / 40.0
            if sc > best_score:
                best, best_score = sent, sc
    return best


# Cover title styles: colour + outline combos, like the title
# banners on Reels / Shorts covers.
TITLE_STYLES = {"Flame": ("Orange", "Neon"),
                "Neon": ("Cyan", "Neon"),
                "Gold": ("Yellow", "Pill")}


def draw_title(frame, title, style_name="Flame"):
    """Draw a big title banner at the top of a frame (for a cover or
    a thumbnail). Reuses draw_text, so the look matches the text
    overlays. Returns the frame."""
    if frame is None or not str(title or "").strip():
        return frame
    color_name, style = TITLE_STYLES.get(str(style_name), TITLE_STYLES["Flame"])
    h = frame.shape[0]
    scale = max(1.6, h / 240.0)
    return draw_text(frame, str(title).strip(), pos="Top",
                     color_name=color_name, scale=scale, style=style)


def subproject_for_range(project, start, end):
    """A new project holding only the part of the timeline between
    start and end (project seconds) — one short for Repurpose mode.
    Clips are trimmed to the overlap; the transition is None (clean
    cuts), no music or sound effects (the short stands alone).
    Returns the new project dict."""
    clips = project.get("clips", [])
    offs = project_clip_offsets(project)
    out_clips = []
    for ci, c in enumerate(clips):
        d = clip_duration(c)
        cs, ce = offs[ci], offs[ci] + d
        if ce <= start or cs >= end:
            continue
        lo = max(start, cs)
        hi = min(end, ce)
        src_lo = float(c.get("start", 0.0)) + max(0.0, project_to_clip_local(project, ci, lo))
        src_hi = float(c.get("start", 0.0)) + max(0.0, project_to_clip_local(project, ci, hi))
        if src_hi - src_lo < 0.1:
            continue
        nc = dict(c)
        nc["start"] = src_lo
        nc["end"] = src_hi
        nc["freeze"] = 0.0
        out_clips.append(nc)
    return {"clips": out_clips, "transition": "None",
            "ratio": project.get("ratio", "16:9  Landscape"),
            "quality": project.get("quality", "720p"),
            "caption_style": project.get("caption_style", "Normal"),
            "caption_size": project.get("caption_size", "Normal"),
            "caption_pos": project.get("caption_pos", "Bottom"),
            "caption_anim": project.get("caption_anim", "Pop word-by-word"),
            "captions": False, "caption_edits": {},
            "normalize": bool(project.get("normalize", False)),
            "music": "", "music_vol": 0.5, "music_fade": False,
            "ducking": False,
            "letterbox": bool(project.get("letterbox", False)),
            "grain": bool(project.get("grain", False)), "sfx": []}


# ---------- Free AI (OpenRouter free models) ----------
# OpenCode is a coding agent, not a video editor — we do not use
# OpenCode the app. But the same FREE models it connects to work
# here: OpenRouter's free models (stepfun/step-3.5-flash:free is the
# free model OpenClip uses by default). OpenRouter's API is
# OpenAI-compatible: POST https://openrouter.ai/api/v1/chat/completions
# with `Authorization: Bearer <key>`. A free account, free models
# cost $0 — it needs internet and a free key from openrouter.ai.
# No key, no internet, or a bad reply: the offline tools above are
# used instead, so the feature never fails because of the network.
# Only the standard library (urllib/json) is used — no new
# dependency. A local model (Ollama) was NOT built: it downloads
# gigabytes and is too slow on a weak laptop.
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "stepfun/step-3.5-flash:free"
OPENROUTER_FALLBACK_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
# Local model (Ollama): free and private, no key and no account —
# but it needs Ollama installed and a model downloaded, and it is
# slow on a weak laptop. llama3.2:3b (~2 GB) is the smallest usable
# one; the user can type a different model name in the panel.
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.2:3b"
AI_MODELS = ["OpenRouter (free cloud key)", "Ollama (local, on this PC)"]

_KEY_FILE_OVERRIDE = None  # tests point this at a temp file


def _key_path():
    """Where the OpenRouter key lives on this PC: next to the app
    (or next to the .exe when frozen). It is NEVER written into a
    saved project .json, so sharing a project can never leak it."""
    if _KEY_FILE_OVERRIDE is not None:
        return Path(_KEY_FILE_OVERRIDE)
    try:
        app_dir = get_app_dir()
    except Exception:
        app_dir = Path.cwd()
    return app_dir / "openrouter_key.txt"


def load_openrouter_key():
    """The saved free OpenRouter key, or \"\" when none is saved."""
    try:
        return _key_path().read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def save_openrouter_key(key):
    """Save the key on this PC (or clear it with \"\"). Returns True
    when the file was written / removed."""
    key = str(key or "").strip()
    try:
        if not key:
            try:
                _key_path().unlink()
            except FileNotFoundError:
                pass
            return True
        _key_path().write_text(key + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def _openrouter_chat(key, prompt, timeout=20):
    """One chat call to a free OpenRouter model. Returns the model's
    reply text, or None when there is no key, no internet, or the
    reply is unusable. Tries the default free model first, then the
    fallback free model once."""
    key = str(key or "").strip()
    if not key:
        return None
    for model in (OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL):
        try:
            body = json.dumps({"model": model,
                               "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
            req = urllib.request.Request(
                OPENROUTER_URL, data=body,
                headers={"Authorization": "Bearer " + key,
                         "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            if content and str(content).strip():
                return str(content).strip()
        except Exception:
            continue
    return None


def _ollama_chat(model, prompt, timeout=60):
    """One chat call to a local Ollama model. Returns
    (reply_text_or_None, error_or_None). error is \"not_running\"
    (Ollama is not there), \"model_missing\" (the model is not
    downloaded yet), or \"bad_reply\"."""
    model = str(model or "").strip() or OLLAMA_MODEL
    try:
        body = json.dumps({"model": model,
                           "messages": [{"role": "user", "content": prompt}],
                           "stream": False}).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_URL, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        # 404 = the model is not downloaded yet.
        return None, "model_missing" if exc.code == 404 else "bad_reply"
    except Exception:
        # Connection refused, timeout, Ollama not installed…
        return None, "not_running"
    try:
        content = (data.get("message") or {}).get("content")
    except Exception:
        content = None
    if content and str(content).strip():
        return str(content).strip(), None
    err = str(data.get("error", "") or "")
    if "not found" in err.lower() or "model" in err.lower():
        return None, "model_missing"
    return None, "bad_reply"


def ai_chat(project, prompt, timeout=20):
    """Ask the configured AI model: OpenRouter (free cloud key) or
    local Ollama. Returns (reply_text_or_None, note_or_None). `note`
    is a plain-English message for the user when the local model
    could not be reached (so the UI can tell them how to fix it);
    it is None when the model simply was not configured or when the
    reply failed for another reason. The caller falls back to the
    offline tools whenever the reply is None."""
    mode = str(project.get("ai_model", AI_MODELS[0]))
    if mode.startswith("Ollama"):
        model = str(project.get("ollama_model", OLLAMA_MODEL) or OLLAMA_MODEL).strip()
        content, err = _ollama_chat(model, prompt, timeout=max(timeout, 60))
        if content:
            return content, None
        if err == "model_missing":
            return None, ("Ollama does not have the model '%s' yet.\n\nRun: ollama pull %s" % (model, model))
        if err == "not_running":
            return None, ("Ollama is not running.\n\nInstall it from ollama.com, then run:\nollama pull %s" % model)
        return None, ("Ollama did not answer. Check it is running, then try again.")
    key = str(project.get("openrouter_key") or "").strip()
    return _openrouter_chat(key, prompt, timeout=timeout), None


def llm_rank_highlights(project, segments, intent, total, top_n=5, timeout=20):
    """Ask the configured AI model to pick the best moments for
    `intent` from a transcript. segments: [(start, end, text)] in
    project seconds. Returns (highlights_or_None, note_or_None):
    highlights are [(start, end, score, reason)] sorted by time, or
    None when the model could not answer — the caller falls back to
    the offline ranking. `note` is a message for the user when the
    local model could not be reached. Times are clamped to the
    video, and pieces shorter than 0.4 s are dropped."""
    if not segments:
        return None, None
    # Keep the prompt small: at most 40 lines, each cut short.
    lines = []
    for (s, e, txt) in segments[:40]:
        lines.append("%.1fs-%.1fs: %s" % (float(s), float(e), str(txt).strip()[:120]))
    prompt = (
        "You are a video editor. The user wants the parts of this video about: %s\n\n"
        "Transcript (start-end times, then what is said):\n%s\n\n"
        "Return ONLY a JSON array of the %d best moments, like this:\n"
        "[{\"start\": 12.5, \"end\": 18.0, \"reason\": \"the goal is scored\"}]\n"
        "Times are in seconds. No other text." % (intent, "\n".join(lines), top_n))
    reply, note = ai_chat(project, prompt, timeout=timeout)
    if not reply:
        return None, note
    # The model may wrap the JSON in ```json fences — take the array.
    import re
    m = re.search(r"\[.*\]", reply, re.DOTALL)
    if not m:
        return None, None
    try:
        items = json.loads(m.group(0))
    except Exception:
        return None, None
    out = []
    for it in items if isinstance(items, list) else []:
        try:
            s = float(it.get("start"))
            e = float(it.get("end"))
        except Exception:
            continue
        s = max(0.0, min(float(total), s))
        e = max(0.0, min(float(total), e))
        if e - s < 0.4:
            continue
        out.append((s, e, 100.0 - len(out) * 5.0,
                    str(it.get("reason", "") or "").strip()))
    if not out:
        return None, None
    out.sort(key=lambda x: x[0])
    return out[:top_n], None


def llm_title(project, transcript_text, timeout=15):
    """Ask the configured AI model for a short punchy title (max 6
    words) for a clip, from its transcript. Returns the title, or
    None when the model could not answer — the caller falls back to
    the best-sentence title."""
    txt = str(transcript_text or "").strip()
    if not txt:
        return None
    prompt = (
        "Write a short punchy video title, max 6 words, for a clip where this is said:\n"
        "%s\n\nReply with ONLY the title. No quotes, no explanation." % txt[:500])
    reply, _note = ai_chat(project, prompt, timeout=timeout)
    if not reply:
        return None
    title = reply.split("\n")[0].strip().strip("\"'“”")
    if not title or len(title.split()) > 12:
        return None
    return title


def analyze_highlights(wav_path, total, top_n=5, win=0.25):
    """Find the loudest, most exciting moments in a WAV: RMS energy
    in short windows, peaks above the average, merged into
    highlight segments. Returns ([(start, end, score)] sorted by
    time, error_or_empty). Loud moments = the exciting parts
    (a goal, a kill, a laugh, a drop) — it cannot know which game
    moment it was, only that it was loud."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            raw = wf.readframes(wf.getnframes())
    except Exception as exc:
        return [], "Could not read the audio: %s" % exc
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    if len(data) == 0 or total <= 0:
        return [], "No audio to analyse."
    step = max(1, int(win * sr))
    n = len(data) // step
    if n < 8:
        return [], "The video is too short for highlights."
    rms = np.sqrt(np.mean(data[:n * step].reshape(n, step) ** 2, axis=1))
    base = float(rms.mean())
    sd = float(rms.std())
    if sd < 1e-4:
        return [], "The audio is flat — no loud moments stand out."
    thresh = base + 0.8 * sd
    hot = rms > thresh
    segs = []
    i = 0
    while i < n:
        if not hot[i]:
            i += 1
            continue
        j = i
        # Merge across a single quiet window (a breath between shouts).
        while j + 1 < n and (hot[j + 1] or (j + 2 < n and hot[j + 2])):
            j += 1
        segs.append((i * win, min(total, (j + 1) * win),
                     float(rms[i:j + 1].max())))
        i = j + 1
    segs = [s for s in segs if s[1] - s[0] >= 0.4]
    if not segs:
        return [], "No loud moments stand out in this video."
    segs.sort(key=lambda s: -s[2])
    return sorted(segs[:top_n]), ""


_face_cascade = None


def score_frame(frame):
    """How good a frame is as a thumbnail: sharp + well lit + has a
    face is best. Returns a score (higher = better)."""
    if frame is None or frame.size == 0:
        return -1.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    small = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA)
    sharp = float(cv2.Laplacian(small, cv2.CV_64F).var())
    bright = float(small.mean())
    light = 1.0 - abs(bright - 128.0) / 128.0
    score = sharp / 100.0 + light * 10.0
    global _face_cascade
    if _face_cascade is None:
        try:
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(path)
            _face_cascade = cascade if not cascade.empty() else False
        except Exception:
            _face_cascade = False
    if _face_cascade:
        try:
            faces = _face_cascade.detectMultiScale(small, 1.2, 4, minSize=(20, 20))
            if len(faces):
                score += 20.0  # a face makes a much better thumbnail
        except Exception:
            pass
    return score


def export_gif(video_path, out_path, width=480, fps=12):
    """Make a small shareable GIF from a finished video (FFmpeg
    palettegen, the good-looking way). Returns (ok, message)."""
    if not ffmpeg_available():
        return False, "GIF export needs FFmpeg."
    import tempfile
    pal = os.path.join(tempfile.gettempdir(), "lgr_palette.png")
    vf = "fps=%d,scale=%d:-1:flags=lanczos" % (fps, width)
    r1 = subprocess.run([_ffmpeg(), "-y", "-v", "error", "-i", str(video_path),
                         "-vf", vf + ",palettegen", pal],
                        capture_output=True, timeout=300)
    if r1.returncode != 0 or not os.path.exists(pal):
        return False, "Could not build the GIF colours."
    r2 = subprocess.run([_ffmpeg(), "-y", "-v", "error", "-i", str(video_path),
                         "-i", pal, "-lavfi",
                         vf + "[x];[x][1:v]paletteuse", str(out_path)],
                        capture_output=True, timeout=300)
    if r2.returncode != 0 or not os.path.exists(out_path):
        return False, "Could not write the GIF."
    return True, "Exported: %s" % Path(out_path).name


def fit_frame(frame, out_w, out_h, blur=True):
    """Scale the frame to fit inside out_w x out_h, filling the rest
    with a blurred copy of itself (the CapCut vertical-video look) —
    or plain black bars when blur is False (the Background pill)."""
    h, w = frame.shape[:2]
    if w == out_w and h == out_h:
        return frame
    scale = min(out_w / max(w, 1), out_h / max(h, 1))
    nw, nh = max(2, int(w * scale)), max(2, int(h * scale))
    small = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    if blur:
        bg = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        bg = cv2.GaussianBlur(bg, (51, 51), 0)
        bg = cv2.convertScaleAbs(bg, alpha=0.75, beta=0)
    else:
        bg = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    x = (out_w - nw) // 2
    y = (out_h - nh) // 2
    bg[y:y + nh, x:x + nw] = small
    return bg


# ---------- captions ----------
def make_captions(clip_path, start, end, language="en"):
    """Auto captions for one clip: [{start, end, text, words:[...]}]
    in clip-local seconds, or ([], error_message). Uses the Smart
    Record speech engine (faster-whisper offline) when it is
    installed. Words carry their own timestamps so Karaoke captions
    can highlight the word being spoken right now. language "en"
    forces English; "auto" (None) lets the engine detect it."""
    if not ffmpeg_available():
        return [], "Auto captions need FFmpeg (it is needed for Live too)."
    import tempfile
    wav = os.path.join(tempfile.gettempdir(), "lgr_caption.wav")
    try:
        subprocess.run(
            [_ffmpeg(), "-y", "-v", "error", "-ss", str(start), "-to",
             str(end), "-i", str(clip_path), "-vn", "-ac", "1", "-ar",
             "16000", wav], capture_output=True, timeout=120)
    except Exception as exc:
        return [], "Could not read the clip audio: %s" % exc
    # faster-whisper with word timestamps (for Karaoke captions).
    try:
        from app import get_whisper_model
        m = get_whisper_model()
        if m is not None:
            segs, _info = m.transcribe(
                wav, beam_size=1,
                language=(None if language in (None, "auto") else str(language)),
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                word_timestamps=True)
            out = []
            for s in segs:
                if not s.text.strip():
                    continue
                words = [{"start": float(wd.start), "end": float(wd.end),
                          "word": wd.word.strip()}
                         for wd in (s.words or []) if wd.word.strip()]
                out.append({"start": float(s.start), "end": float(s.end),
                            "text": s.text.strip(), "words": words})
            return out, ""
    except Exception as exc:
        pass
    try:
        from app import transcribe_wav
    except Exception as exc:
        return [], "Speech engine not available: %s" % exc
    segments, _engine, err = transcribe_wav(wav)
    if err:
        return [], err
    for s in segments:
        s.setdefault("words", [])
    return segments, ""


def _srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, (ms // 60000) % 60,
                                   (ms // 1000) % 60, ms % 1000)


def segments_to_srt(segments):
    """Caption segments [{start, end, text}] as .srt text."""
    lines = []
    for i, s in enumerate(segments, 1):
        lines.append(str(i))
        lines.append("%s --> %s" % (_srt_time(s["start"]), _srt_time(s["end"])))
        lines.append(str(s.get("text", "")).strip())
        lines.append("")
    return "\n".join(lines)


def _redistribute_words(text, start, end):
    """Split edited caption text into word timings spread evenly
    across the segment, so Karaoke highlighting still works after
    the user edits the words."""
    words = [w for w in str(text).split() if w]
    if not words:
        return []
    dur = max(0.05, float(end) - float(start))
    step = dur / len(words)
    return [{"start": float(start) + i * step,
             "end": float(start) + (i + 1) * step, "word": w}
            for i, w in enumerate(words)]


def project_captions_srt(project, clip_captions):
    """All clips' caption segments as one .srt, in project time.
    Clip-local segment times are mapped through speed + freeze,
    and the 0.5 s transition overlap is taken out, so the .srt
    matches the exported video. Reversed clips are skipped — their
    captions were made from forward speech and would be wrong."""
    clips = project.get("clips", [])
    overlap = 0.5 if project.get("transition", "None") != "None" else 0.0
    all_segs = []
    acc = 0.0  # project time where this clip's written frames start
    for ci, clip in enumerate(clips):
        d = clip_duration(clip)
        speed = max(0.1, float(clip.get("speed", 1.0)))
        freeze = float(clip.get("freeze", 0.0) or 0.0)
        if not clip.get("reverse"):
            for seg in (clip_captions[ci] if ci < len(clip_captions) else []):
                t0 = acc + freeze + float(seg["start"]) / speed
                t1 = acc + freeze + float(seg["end"]) / speed
                t0 = max(acc, min(acc + d, t0))
                t1 = max(t0 + 0.1, min(acc + d, t1))
                all_segs.append({"start": t0, "end": t1,
                                 "text": seg.get("text", "")})
        acc += d - (overlap if ci < len(clips) - 1 else 0.0)
    all_segs.sort(key=lambda s: s["start"])
    return segments_to_srt(all_segs)


# ---------- render / export ----------
# Stylization filters are slow on a weak laptop at full size
# (Anime is ~10x slower on a 1024x720 frame than on the small
# facecam). In the editor they run on the whole clip, so run them
# at half size and scale back up — the look is the same, the
# export is about 4x faster.
_HEAVY_FILTERS = {"Anime", "LING", "Cartoon", "Comic", "Sketch"}


def parse_cube(path):
    """Parse a free .cube 3D LUT file (FreeVisuals / FilterGrade /
    videoeditingluts.com). Returns (size, data) where data is a
    float32 array of shape (N, N, N, 3) in RGB, or (None, error)."""
    size = 0
    rows = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.upper().startswith("LUT_3D_SIZE"):
                    size = int(line.split()[-1])
                    continue
                if line.upper().startswith(("TITLE", "DOMAIN_", "LUT_1D_SIZE")):
                    continue
                parts = line.split()
                if len(parts) == 3:
                    try:
                        rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
                    except ValueError:
                        continue
    except Exception as exc:
        return None, "Could not read the .cube file: %s" % exc
    if not size or len(rows) < size ** 3:
        return None, "That .cube file has no 3D LUT in it (only %d rows)." % len(rows)
    data = np.array(rows[:size ** 3], dtype=np.float32).reshape(size, size, size, 3)
    return (size, data), ""


def apply_lut(frame, lut):
    """Apply a parsed .cube LUT (trilinear interpolation). Runs at
    half resolution like the other heavy filters, then scales back."""
    size, data = lut
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (max(2, w // 2), max(2, h // 2)),
                       interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x = rgb[..., 0] * (size - 1)
    y = rgb[..., 1] * (size - 1)
    z = rgb[..., 2] * (size - 1)
    x0 = np.clip(np.floor(x).astype(np.int32), 0, size - 2)
    y0 = np.clip(np.floor(y).astype(np.int32), 0, size - 2)
    z0 = np.clip(np.floor(z).astype(np.int32), 0, size - 2)
    fx, fy, fz = x - x0, y - y0, z - z0
    # .cube rows are R-fastest, so the reshaped array is [B][G][R].
    def _g(ix, iy, iz):
        return data[iz, iy, ix]
    c000 = _g(x0, y0, z0)
    c100 = _g(x0 + 1, y0, z0)
    c010 = _g(x0, y0 + 1, z0)
    c110 = _g(x0 + 1, y0 + 1, z0)
    c001 = _g(x0, y0, z0 + 1)
    c101 = _g(x0 + 1, y0, z0 + 1)
    c011 = _g(x0, y0 + 1, z0 + 1)
    c111 = _g(x0 + 1, y0 + 1, z0 + 1)
    fx = fx[..., None]; fy = fy[..., None]; fz = fz[..., None]
    out = (c000 * (1 - fx) * (1 - fy) * (1 - fz) +
           c100 * fx * (1 - fy) * (1 - fz) +
           c010 * (1 - fx) * fy * (1 - fz) +
           c110 * fx * fy * (1 - fz) +
           c001 * (1 - fx) * (1 - fy) * fz +
           c101 * fx * (1 - fy) * fz +
           c011 * (1 - fx) * fy * fz +
           c111 * fx * fy * fz)
    out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    out = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
    return cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR)


def _photo_border(frame):
    """White photo frame around the clip (Photo Dump Minimal)."""
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (10, 10), (w - 11, h - 11), (255, 255, 255), 5)
    return frame


def _letterbox(frame):
    """Cinematic black bars top and bottom (2.35:1 look)."""
    h, w = frame.shape[:2]
    bar = max(4, h // 10)
    frame[:bar, :] = 0
    frame[h - bar:, :] = 0
    return frame


def _add_grain(frame, seed=0):
    """Retro film grain: a little random noise over the frame."""
    rng = np.random.default_rng(seed)
    noise = rng.integers(-12, 13, frame.shape, dtype=np.int16)
    return np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def _apply_enhance(frame):
    """Auto-enhance a frame: lift a dull picture toward mid grey,
    a gentle contrast boost, and a little more colour. Pure
    OpenCV, so it runs in the same render path as the filters
    (preview and export) with no extra FFmpeg pass."""
    if frame is None or frame.size == 0:
        return frame
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    beta = max(-30.0, min(30.0, (112.0 - mean) * 0.35))
    out = cv2.convertScaleAbs(frame, alpha=1.12, beta=beta)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV)
    hsv[:, :, 1] = cv2.convertScaleAbs(hsv[:, :, 1], alpha=1.15, beta=0)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def _apply_clip_filter(frame, name, clip=None):
    out = frame
    if name and name != "None":
        # A loaded .cube LUT lives on the clip itself.
        if name == "LUT":
            lut = (clip or {}).get("lut")
            if lut is not None:
                try:
                    out = apply_lut(frame, lut)
                except Exception:
                    out = frame
        else:
            try:
                from app import apply_character_filter
                if name in _HEAVY_FILTERS:
                    h, w = frame.shape[:2]
                    small = cv2.resize(frame, (max(2, w // 2), max(2, h // 2)),
                                       interpolation=cv2.INTER_AREA)
                    f = apply_character_filter(small, name)
                    out = cv2.resize(f, (w, h), interpolation=cv2.INTER_LINEAR)
                else:
                    out = apply_character_filter(frame, name)
            except Exception:
                out = frame
    # Auto enhance runs on top of any filter (or on its own).
    if clip and clip.get("enhance"):
        try:
            out = _apply_enhance(out)
        except Exception:
            pass
    return out


def _ramp_frac(ramp, u):
    """Source fraction for a speed ramp at output fraction u (0..1).
    Average speed stays 1x, so the clip keeps its length."""
    if ramp == "Slow → Fast":
        return 0.5 * u + 0.5 * u * u
    if ramp == "Fast → Slow":
        return 1.5 * u - 0.5 * u * u
    if ramp == "Hero":
        # CapCut Hero curve: fast at the start and end, slow in the
        # middle for the hero moment (sports / stunts / kills).
        return u + np.sin(2 * np.pi * u) / (4 * np.pi)
    return u - np.sin(2 * np.pi * u) / (4 * np.pi)  # Slow-Fast-Slow


def _process_frame(frame, clip, captions, caption_style, t, src_t,
                   frame_index, clip_dur, caption_size="Normal",
                   caption_pos="Bottom", caption_anim="Pop word-by-word"):
    """One finished frame: clip animation, filter, text (+ style
    and animation), sticker, captions. `t` is exported time in
    the clip (for animations); `src_t` is time in the source clip
    (for captions, which are timed to the spoken words). Captions
    always go through draw_caption_words now, so the caption
    animation (Pop / Karaoke / Bounce / Slide up / Typewriter) is
    on by default — style "Normal" just means plain white words."""
    out = apply_clip_anim(frame, clip.get("clip_anim", "None"),
                          t, clip_dur, frame_index)
    out = _apply_clip_filter(out, clip.get("filter", "None"), clip)
    if clip.get("text"):
        out = draw_text(out, clip["text"], clip.get("text_pos", "Bottom"),
                        clip.get("text_color", "White"),
                        anim=clip.get("text_anim", "None"), t=t,
                        style=clip.get("text_style", "Normal"))
    if clip.get("sticker") and clip.get("sticker") != "None":
        out = draw_sticker(out, clip["sticker"],
                           clip.get("sticker_pos", "Top Right"))
    if clip.get("border"):
        out = _photo_border(out)
    if captions:
        for seg in captions:
            if seg["start"] <= src_t <= seg["end"]:
                out = draw_caption_words(
                    out, seg, src_t, caption_style or "Normal",
                    scale_mult=_CAPTION_SIZE_MULT.get(caption_size, 1.0),
                    pos=caption_pos, anim=caption_anim)
                break
    return out


def _ramp_frames(cap, clip, captions, caption_style, fps, start_f, end_f,
                 ramp, out_i, clip_dur, caption_size="Normal",
                 caption_pos="Bottom", caption_anim="Pop word-by-word"):
    """Speed ramp (CapCut curve): yield the clip's frames in ramped
    order. `out_i` is the output frame counter (freeze frames may
    already have been written before this)."""
    total = max(1, end_f - start_f)
    targets = [start_f + _ramp_frac(ramp, i / total) * total
               for i in range(total)]
    ti = 0
    last_frame = None
    while ti < total:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        cur = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        if cur < start_f:
            continue
        if cur >= end_f:
            break
        last_frame = frame
        while ti < total and targets[ti] <= cur:
            t = out_i / fps
            src_t = (targets[ti] - start_f) / fps
            yield _process_frame(frame, clip, captions, caption_style,
                                 t, src_t, out_i, clip_dur, caption_size,
                                 caption_pos, caption_anim), t
            out_i += 1
            ti += 1
    while ti < total and last_frame is not None:
        t = out_i / fps
        src_t = (targets[ti] - start_f) / fps
        yield _process_frame(last_frame, clip, captions, caption_style,
                             t, src_t, out_i, clip_dur, caption_size,
                             caption_pos, caption_anim), t
        out_i += 1
        ti += 1


def _clip_frames(clip, captions, caption_style="Normal",
                caption_size="Normal", caption_pos="Bottom",
                caption_anim="Pop word-by-word"):
    """Yield (frame, local_time) for one clip, speed applied.
    local_time is seconds into the clip's exported (sped) length."""
    cap = cv2.VideoCapture(str(clip["path"]))
    if not cap.isOpened():
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    speed = max(0.1, float(clip.get("speed", 1.0)))
    start_f = int(clip["start"] * fps)
    end_f = int(clip["end"] * fps)
    clip_dur = clip_duration(clip)
    out_i = 0
    # Freeze: hold the first frame still at the start of the clip.
    freeze = float(clip.get("freeze", 0.0) or 0.0)
    if freeze > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
        ok, first = cap.read()
        if ok and first is not None:
            for _ in range(int(freeze * fps)):
                t = out_i / fps
                yield _process_frame(first, clip, captions, caption_style,
                                     t, 0.0, out_i, clip_dur, caption_size,
                                     caption_pos, caption_anim), t
                out_i += 1
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    ramp = clip.get("ramp", "None") or "None"
    if ramp != "None":
        yield from _ramp_frames(cap, clip, captions, caption_style, fps,
                                start_f, end_f, ramp, out_i, clip_dur,
                                caption_size, caption_pos, caption_anim)
        cap.release()
        return
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    # Output frame k uses source frame start_f + k * speed.
    # speed >= 1: skip source frames; speed < 1: repeat each frame.
    next_needed = float(start_f)
    repeat = 1 if speed >= 1.0 else max(1, int(round(1.0 / speed)))
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        cur = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        if cur < start_f:
            continue
        if cur >= end_f:
            break
        if speed >= 1.0:
            if cur < next_needed:
                continue
            next_needed += speed
            times = 1
        else:
            times = repeat
        for _ in range(times):
            t = out_i / fps
            src_t = (cur - start_f) / fps
            yield _process_frame(frame, clip, captions, caption_style,
                                 t, src_t, out_i, clip_dur, caption_size,
                                 caption_pos, caption_anim), t
            out_i += 1
    cap.release()


def _blend(a, b, alpha):
    """Cross-dissolve blend of two frames (alpha 0..1 = weight of b)."""
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    return cv2.addWeighted(a, 1.0 - alpha, b, alpha, 0)


def export_project(project, out_path, progress_cb=None, status_cb=None):
    """Render the whole project to one MP4. Returns (ok, message).
    progress_cb(0..1), status_cb(text). Video is rendered with
    OpenCV; audio is mixed with FFmpeg when available."""
    clips = [c for c in project.get("clips", []) if c.get("path")]
    if not clips:
        return False, "Add a video clip first."
    out_w, out_h = RATIOS.get(project.get("ratio", "16:9  Landscape"), (1280, 720))
    # Export quality (CapCut export dialog): 1080p is 1.5x the 720p size.
    if project.get("quality", "720p") == "1080p":
        out_w, out_h = int(out_w * 1.5), int(out_h * 1.5)
    infos = [probe(c["path"]) for c in clips]
    fps = 30.0
    for info in infos:
        if info and info.get("fps"):
            fps = float(info["fps"])
            break
    total_dur = project_duration(project)
    if total_dur <= 0:
        return False, "The clips are empty - check the trim start/end."
    transition = project.get("transition", "None")
    trans_frames = int(fps * 0.5) if transition != "None" else 0

    # Auto captions (once per clip, before rendering). A clip with
    # no speech simply gets no captions - the export still goes
    # ahead, and the note below says why. Captions the user edited
    # in the editor are used as-is, without listening again.
    clip_captions = []
    caption_note = ""
    if project.get("captions"):
        edits = project.get("caption_edits") or {}
        need_listen = any(str(ci) not in edits for ci in range(len(clips)))
        if need_listen and status_cb:
            status_cb("Listening to the clips for auto captions… (first time may download the speech model, ~75 MB, once)")
        for ci, c in enumerate(clips):
            mine = edits.get(str(ci))
            if mine:
                clip_captions.append([dict(s) for s in mine])
                continue
            # A .srt next to the video wins over listening again:
            # it is the user's own captions (from YouTube, a
            # download, or an earlier export).
            segs, err = srt_segments_for_clip(c["path"], c["start"], c["end"])
            if not segs:
                segs, err = make_captions(c["path"], c["start"], c["end"],
                                        language=project.get("caption_lang", "en"))
            if err and not caption_note:
                caption_note = " (auto captions skipped: " + err + ")"
            clip_captions.append(segs)
    else:
        clip_captions = [[] for _ in clips]

    # Reverse clips (CapCut reverse): FFmpeg reverses the whole clip
    # once into a temp file; the trim range is mirrored, so the
    # video and the audio both play backwards. Done AFTER captions
    # (captions are made from the original, forward speech).
    import tempfile
    rev_files = []
    if ffmpeg_available():
        for ci, c in enumerate(clips):
            if not c.get("reverse"):
                continue
            info = infos[ci]
            dur = info.get("duration", 0) if info else 0
            if not dur or dur <= 0:
                continue
            rev = os.path.join(tempfile.gettempdir(),
                               "lgr_rev%d_%d.mp4" % (ci, os.getpid()))
            r = subprocess.run(
                [_ffmpeg(), "-y", "-v", "error", "-i", str(c["path"]),
                 "-vf", "reverse", "-af", "areverse", rev],
                capture_output=True, timeout=600)
            if r.returncode == 0 and os.path.exists(rev):
                clips[ci] = dict(c)
                clips[ci]["path"] = rev
                clips[ci]["start"] = max(0.0, dur - c["end"])
                clips[ci]["end"] = min(dur, dur - c["start"])
                rev_files.append(rev)
            else:
                caption_note += " (Reverse skipped for clip %d - FFmpeg failed)" % (ci + 1)
    caption_style = project.get("caption_style", "Normal")
    caption_size = project.get("caption_size", "Normal")
    caption_pos = project.get("caption_pos", "Bottom")
    caption_anim = project.get("caption_anim", "Pop word-by-word")

    # Stabilize (one-tap, like CapCut / Premiere Warp Stabilizer):
    # FFmpeg vidstab, two passes, on the clip (after Reverse, so a
    # reversed clip is stabilized in its reversed form too).
    if ffmpeg_available():
        for ci, c in enumerate(clips):
            if not c.get("stabilize"):
                continue
            trf = os.path.join(tempfile.gettempdir(),
                               "lgr_stab%d_%d.trf" % (ci, os.getpid()))
            stab = os.path.join(tempfile.gettempdir(),
                                "lgr_stab%d_%d.mp4" % (ci, os.getpid()))
            p1 = subprocess.run(
                [_ffmpeg(), "-y", "-v", "error", "-i", str(c["path"]),
                 "-vf", "vidstabdetect=shakiness=5:accuracy=15:result=%s" % trf,
                 "-f", "null", "-"], capture_output=True, timeout=600)
            p2 = None
            if p1.returncode == 0:
                p2 = subprocess.run(
                    [_ffmpeg(), "-y", "-v", "error", "-i", str(c["path"]),
                     "-vf", "vidstabtransform=input=%s:zoom=1:smoothing=10" % trf,
                     "-c:a", "copy", stab], capture_output=True, timeout=600)
            try:
                if os.path.exists(trf):
                    os.remove(trf)
            except OSError:
                pass
            if p2 is not None and p2.returncode == 0 and os.path.exists(stab):
                clips[ci] = dict(c)
                clips[ci]["path"] = stab
                rev_files.append(stab)
            else:
                caption_note += " (Stabilize skipped for clip %d - FFmpeg failed)" % (ci + 1)

    tmp_video = str(Path(out_path).with_suffix("")) + "_video_only.mp4"
    writer = None
    try:
        writer = cv2.VideoWriter(tmp_video, cv2.VideoWriter_fourcc(*"mp4v"),
                                 fps, (out_w, out_h))
        if not writer.isOpened():
            return False, "Could not open a video encoder. Try installing opencv-python again."
        written = 0
        total_frames = max(1, int(total_dur * fps))
        # Smart reframe: a 9:16 export that follows the face instead
        # of blurring the sides.
        reframer = (SmartReframe(out_w, out_h)
                    if project.get("ratio", "") == "9:16  Smart reframe (follow face)"
                    else None)

        letterbox = bool(project.get("letterbox", False))
        grain = bool(project.get("grain", False))

        def _finish(frame):
            if letterbox:
                frame = _letterbox(frame)
            if grain:
                frame = _add_grain(frame, written)
            return frame

        def _write(frame):
            nonlocal written
            if reframer is not None:
                frame = cv2.resize(reframer.crop(frame), (out_w, out_h),
                                   interpolation=cv2.INTER_AREA)
            else:
                frame = fit_frame(frame, out_w, out_h, blur=bool(project.get("bg_blur", True)))
            writer.write(_finish(frame))
            written += 1
            if progress_cb:
                progress_cb(min(1.0, written / total_frames))

        prev_tail = []  # last frames of the previous clip (for transitions)
        for ci, clip in enumerate(clips):
            frames = [f for (f, _t) in _clip_frames(clip, clip_captions[ci],
                                                   caption_style, caption_size,
                                                   caption_pos, caption_anim)]
            if not frames:
                continue
            if ci > 0 and trans_frames > 0 and prev_tail:
                # Blend the tail of the previous clip with the head
                # of this one. Dissolve cross-fades, Fade goes
                # through black, Slide wipes across, Zoom punches
                # in, Glitch tears the picture, Flash blinks white.
                n = min(trans_frames, len(prev_tail), len(frames))
                for k in range(n):
                    a = prev_tail[len(prev_tail) - n + k]
                    b = frames[k]
                    p = (k + 1) / (n + 1)
                    if transition == "Fade":
                        if k < n / 2:
                            blended = cv2.convertScaleAbs(
                                a, alpha=1.0 - (2.0 * k / n))
                        else:
                            blended = cv2.convertScaleAbs(
                                b, alpha=(2.0 * k / n) - 1.0)
                    elif transition == "Slide":
                        blended = a.copy()
                        cut = int(a.shape[1] * p)
                        blended[:, :cut] = b[:, :cut]
                    elif transition == "Zoom":
                        s = 1.0 + 0.25 * (1.0 - p)
                        h, w = b.shape[:2]
                        big = cv2.resize(b, (int(w * s), int(h * s)),
                                         interpolation=cv2.INTER_LINEAR)
                        x0, y0 = (big.shape[1] - w) // 2, (big.shape[0] - h) // 2
                        zoomed = big[y0:y0 + h, x0:x0 + w]
                        blended = _blend(a, zoomed, p)
                    elif transition == "Glitch":
                        blended = _blend(a, b, p)
                        blended = apply_clip_anim(blended, "Glitch",
                                                  k / fps, n / fps, k)
                    elif transition == "Flash":
                        blended = _blend(a, b, p)
                        if n / 3 <= k <= 2 * n / 3:
                            f = 0.7 * np.sin(np.pi * (k - n / 3) / (n / 3))
                            white = np.full_like(blended, 255)
                            blended = cv2.addWeighted(white, f, blended, 1.0 - f, 0)
                    elif transition == "Blur":
                        # Cross-blur: the picture blurs most in the
                        # middle of the transition, then clears.
                        blended = _blend(a, b, p)
                        sigma = 9.0 * (1.0 - abs(2.0 * p - 1.0))
                        if sigma > 0.5:
                            blended = cv2.GaussianBlur(blended, (0, 0), sigma)
                    else:  # Dissolve
                        blended = _blend(a, b, p)
                    _write(blended)
                frames = frames[n:]
                prev_tail = []
            for frame in frames:
                if ci < len(clips) - 1 and trans_frames > 0:
                    # Hold the tail back so the next clip can blend
                    # with it; write the oldest frame once the tail
                    # is full.
                    prev_tail.append(frame)
                    if len(prev_tail) > trans_frames:
                        _write(prev_tail.pop(0))
                else:
                    _write(frame)
        writer.release()
        writer = None
    except Exception as exc:
        if writer is not None:
            writer.release()
        return False, "Export failed while rendering video: %s" % exc

    # Subtitles file: the same captions as an .srt next to the
    # video, so the user can upload it to YouTube / TikTok too.
    if project.get("captions"):
        try:
            srt_text = project_captions_srt(project, clip_captions)
            if srt_text.strip():
                Path(str(out_path)).with_suffix(".srt").write_text(
                    srt_text, encoding="utf-8")
        except Exception:
            pass

    # Chapters file (v2.4): YouTube-style "MM:SS Title" lines next
    # to the video, ready to paste into the video description.
    # Chapter times are project times, which match the exported
    # video (transitions shift later chapters by at most 0.5 s).
    if project.get("chapters"):
        try:
            from app import chapters_to_text
            ch_path = Path(str(out_path)).with_name(
                Path(str(out_path)).stem + "_chapters.txt")
            ch_path.write_text(chapters_to_text(project["chapters"]),
                               encoding="utf-8")
        except Exception:
            pass

    # Audio: mix the clips' audio (+ music) with FFmpeg, then mux.
    # The real video length is the frames actually written - a
    # transition overlaps the clips, so it is shorter than the
    # plain sum of the clip lengths. The audio is cut to match it.
    if status_cb:
        status_cb("Mixing audio…")
    video_dur = written / fps if fps else total_dur
    # Tutorial export (v2.4): H.264 CRF 23 instead of the mp4v copy,
    # for a file that shares easily anywhere.
    tutorial = bool(project.get("tutorial_export"))
    final = export_audio(project, clips, tmp_video, str(out_path), video_dur,
                         reencode=tutorial)
    for rev in rev_files:
        try:
            if os.path.exists(rev):
                os.remove(rev)
        except OSError:
            pass
    if final is None:
        # No audio to mix (or FFmpeg missing) - the video-only file
        # is still a valid export, so move it to the final name.
        # A tutorial export re-encodes it to H.264 first when
        # FFmpeg is available.
        if tutorial and ffmpeg_available():
            if status_cb:
                status_cb("Encoding tutorial video (H.264)…")
            if _reencode_h264(tmp_video, str(out_path)):
                try:
                    os.remove(tmp_video)
                except OSError:
                    pass
                if progress_cb:
                    progress_cb(1.0)
                return True, "Exported: %s (tutorial: 1080p H.264, video only - no audio to mix)%s" % (Path(out_path).name, caption_note)
        try:
            shutil.move(tmp_video, str(out_path))
        except Exception as exc:
            return False, "Export failed while saving the video: %s" % exc
        note = "" if ffmpeg_available() else " (video only - FFmpeg is not installed, so there is no sound)"
        return True, "Exported: %s%s%s" % (Path(out_path).name, note, caption_note)
    try:
        if os.path.exists(tmp_video):
            os.remove(tmp_video)
    except OSError:
        pass
    if progress_cb:
        progress_cb(1.0)
    tut_note = " (tutorial: 1080p H.264)" if tutorial and final == "reencoded" else ""
    return True, "Exported: %s%s%s" % (Path(out_path).name, tut_note, caption_note)


def _audio_mix_parts(project, clips, total_dur, first_idx=1):
    """Build the FFmpeg audio mix for a project: clip audio + music +
    sound effects. Returns (inputs, filters, mixed_label) or
    (None, None, None) when there is nothing to mix. `first_idx` is
    the FFmpeg input number of the first audio file (1 when input 0
    is the video, 0 when rendering audio-only for the preview)."""
    inputs = []
    filters = []
    audio_maps = []
    idx = first_idx
    for c in clips:
        if c.get("mute"):
            continue
        info = probe(c["path"])
        if not info or not info.get("has_audio"):
            continue
        inputs.extend(["-i", str(c["path"])])
        # A speed ramp keeps the average speed at 1x, so the audio
        # stays at normal speed. Freeze holds the picture still, so
        # the sound is delayed by the same amount to stay in sync.
        ramp = c.get("ramp", "None") or "None"
        speed = 1.0 if ramp != "None" else max(0.1, float(c.get("speed", 1.0)))
        vol = max(0.0, min(2.0, float(c.get("volume", 1.0) or 1.0)))
        chain = ("[%d:a]atrim=%.3f:%.3f,asetpts=PTS-STARTPTS,atempo=%.3f,"
                 "volume=%.2f" % (idx, c["start"], c["end"],
                                  min(max(speed, 0.5), 2.0), vol))
        if c.get("denoise"):
            chain += ",afftdn"
        # Per-clip fade in / fade out (Video panel): the fade-out
        # starts at the end of this clip's audio, before the freeze
        # delay (the freeze holds the picture still, the sound
        # follows it).
        clip_dur = (c["end"] - c["start"]) / max(0.1, speed)
        fi = float(c.get("fade_in", 0.0) or 0.0)
        fo = float(c.get("fade_out", 0.0) or 0.0)
        if fi > 0:
            chain += ",afade=t=in:st=0:d=%.2f" % fi
        if fo > 0:
            chain += ",afade=t=out:st=%.3f:d=%.2f" % (max(0.0, clip_dur - fo), fo)
        freeze = float(c.get("freeze", 0.0) or 0.0)
        if freeze > 0:
            chain += ",adelay=%.0f:all=1" % (freeze * 1000)
        chain += "[a%d]" % idx
        filters.append(chain)
        audio_maps.append("[a%d]" % idx)
        idx += 1
    music = (project.get("music") or "").strip()
    if music and os.path.exists(music):
        inputs.extend(["-i", music])
        vol = float(project.get("music_vol", 0.5))
        mus = "[%d:a]volume=%.2f,apad" % (idx, vol)
        if project.get("music_fade", True):
            mus += (",afade=t=in:st=0:d=1,"
                    "afade=t=out:st=%.3f:d=1" % max(0.0, total_dur - 1.0))
        mus += "[mus]"
        filters.append(mus)
        music_idx = idx
        idx += 1
    # --- sound effects (added at the playhead, from the Sounds tab) ---
    sfx_maps = []
    for s in (project.get("sfx") or []):
        path = str(s.get("path") or "")
        if not path or not os.path.exists(path):
            continue
        inputs.extend(["-i", path])
        at = max(0.0, float(s.get("at", 0.0) or 0.0))
        vol = max(0.0, min(2.0, float(s.get("vol", 1.0) or 1.0)))
        chain = ("[%d:a]adelay=%.0f:all=1,volume=%.2f,apad[sfx%d]"
                 % (idx, at * 1000, vol, idx))
        filters.append(chain)
        sfx_maps.append("[sfx%d]" % idx)
        idx += 1
    if not audio_maps and not music and not sfx_maps:
        return None, None, None
    if audio_maps:
        if len(audio_maps) == 1:
            mixed = audio_maps[0]
        else:
            filters.append("".join(audio_maps) +
                           "concat=n=%d:v=0:a=1[ac]" % len(audio_maps))
            mixed = "[ac]"
    else:
        mixed = None
    if music and os.path.exists(music):
        if mixed:
            if project.get("ducking"):
                # Music ducking: the music goes quiet while the clip
                # audio (speech) plays, then comes back up. The
                # speech stream is split in two (asplit) because it
                # feeds both the sidechain and the final mix.
                filters.append("%saresample=48000,asplit=2[acs1][acs2]" % mixed)
                filters.append("[mus]aresample=48000[mus48]")
                filters.append("[mus48][acs1]sidechaincompress=threshold=0.02:ratio=8:attack=200:release=500[musd]")
                filters.append("[musd][acs2]amix=inputs=2:normalize=0[aout]")
                mixed = "[aout]"
            else:
                filters.append("%s[mus]amix=inputs=2:normalize=0[aout]" % mixed)
                mixed = "[aout]"
        else:
            mixed = "[mus]"
    if sfx_maps:
        if mixed:
            all_maps = [mixed] + sfx_maps
            filters.append("".join(all_maps) +
                           "amix=inputs=%d:normalize=0[final]" % len(all_maps))
            mixed = "[final]"
        else:
            if len(sfx_maps) == 1:
                mixed = sfx_maps[0]
            else:
                filters.append("".join(sfx_maps) +
                               "amix=inputs=%d:normalize=0[final]" % len(sfx_maps))
                mixed = "[final]"
    # Normalize loudness (Audio tab): one-pass loudnorm on the final
    # mix, so quiet and loud parts come out even. Runs for both the
    # export and the preview, since both use this mix.
    if mixed is not None and project.get("normalize"):
        filters.append("%sloudnorm=I=-16:TP=-1.5:LRA=11[norm]" % mixed)
        mixed = "[norm]"
    return inputs, filters, mixed


def _reencode_h264(src, dst, crf=23):
    """Re-encode a video to H.264 (CRF 23, veryfast) with FFmpeg.
    Returns True on success. Used by the tutorial export for the
    video-only path (no audio to mix)."""
    if not ffmpeg_available():
        return False
    cmd = [_ffmpeg(), "-y", "-v", "error", "-i", str(src),
           "-c:v", "libx264", "-crf", str(crf), "-preset", "veryfast",
           "-pix_fmt", "yuv420p", str(dst)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception:
        return False
    return res.returncode == 0 and os.path.exists(dst)


def export_audio(project, clips, video_path, out_path, total_dur, reencode=False):
    """Mix clip audio (+ optional music + sound effects) onto
    video_path with FFmpeg. Returns "reencoded" when the video was
    re-encoded with H.264, "copied" when the video stream was
    copied as-is, or None when there is nothing to mix or FFmpeg
    is missing (caller then ships the video-only file).
    reencode=True (tutorial export) re-encodes the video with
    H.264 CRF 23 instead of copying the mp4v stream; if the
    encoder is missing it falls back to a copy so the export
    still succeeds."""
    if not ffmpeg_available():
        return None
    inputs, filters, mixed = _audio_mix_parts(project, clips, total_dur, first_idx=1)
    if mixed is None:
        return None
    video_args = ["-c:v", "copy"]
    if reencode:
        video_args = ["-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
                      "-pix_fmt", "yuv420p"]
    cmd = [_ffmpeg(), "-y", "-v", "error", "-i", video_path] + inputs + [
        "-filter_complex", ";".join(filters),
        "-map", "0:v", "-map", mixed] + video_args + ["-c:a", "aac",
        "-t", "%.3f" % total_dur, str(out_path)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception:
        return None
    if res.returncode != 0 or not os.path.exists(out_path):
        if reencode:
            # libx264 missing or failed: fall back to a plain copy
            # so the export still succeeds.
            cmd2 = [_ffmpeg(), "-y", "-v", "error", "-i", video_path] + inputs + [
                "-filter_complex", ";".join(filters),
                "-map", "0:v", "-map", mixed, "-c:v", "copy", "-c:a", "aac",
                "-t", "%.3f" % total_dur, str(out_path)]
            try:
                res2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=600)
            except Exception:
                return None
            if res2.returncode != 0 or not os.path.exists(out_path):
                return None
            return "copied"
        return None
    return "reencoded" if reencode else "copied"


def render_project_audio(project, clips, out_wav):
    """Render the project's full audio mix (clip audio + music + SFX)
    to a WAV, for the editor preview. Returns the total duration, or
    None when there is nothing to hear or FFmpeg is missing."""
    if not ffmpeg_available():
        return None
    total = project_duration(project)
    if total <= 0:
        return None
    inputs, filters, mixed = _audio_mix_parts(project, clips, total, first_idx=0)
    if mixed is None:
        return None
    cmd = [_ffmpeg(), "-y", "-v", "error"] + inputs + [
        "-filter_complex", ";".join(filters),
        "-map", mixed, "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        "-t", "%.3f" % total, str(out_wav)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception:
        return None
    if res.returncode != 0 or not os.path.exists(out_wav):
        return None
    return total



# ---------- editor window: CapCut-style design ----------
# Layout copied from CapCut Desktop (from CapCut's own guides):
#   top bar: project title, Undo/Redo, Export (top right, teal)
#   media panel (top left): Media / Audio / Text / Stickers / Effects
#   preview player (top centre): the frame under the playhead
#   toolbar under the preview: Split, Speed, Volume, Delete, Text...
#   properties panel (right): settings for the selected clip
#   timeline (bottom): main video track, text track above it,
#   audio track below it, white playhead line
# Colours: deep charcoal backgrounds, CapCut's signature teal accent.
import copy
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk
from PIL import Image, ImageTk

# Shared design system with the recorder (app.py): dark shell, sky
# primary, teal for AI only, red for danger, green for audio.
CC_BG = "#0F1218"       # near-black canvas
CC_PANEL = "#181D27"    # panels
CC_CARD = "#1F2531"     # cards / inputs
CC_BORDER = "#2A3242"
CC_TEXT = "#E8EAF0"
CC_MUTED = "#9AA3B2"
CC_SKY = "#A9D6E8"      # primary action + selected states (dark text on it)
CC_SKY_HOVER = "#8FC6DC"
CC_TEAL = "#12B5D9"     # AI accent only
CC_TEAL_HOVER = "#0e9bb8"
CC_RED = "#E5484D"      # danger only
CC_GREEN = "#34D399"    # audio / success
CC_AMBER = "#FBBF24"    # SFX markers / warnings
CC_GOLD = "#FBBF24"     # AI highlight bars
CC_VIDEO = "#7C5CFF"    # video track (CapCut uses purple tracks)
CC_VIDEO_DIM = "#5A4BD6"
CC_AUDIO = "#34D399"    # audio track green
CC_TEXTTRK = "#8B7CFF"  # text track
CC_PINK = "#C86BA6"     # transcript clips (Dribbble subtitle track)
CC_BLUE = "#5E8FC4"
CC_MUSIC_BG = "#6E4E8A"  # music bar (Dribbble purple)
CC_LAVENDER = "#A78FD0"  # music waveform


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


class VideoEditor(ctk.CTkToplevel):
    """CapCut-style editor window."""

    def __init__(self, master, initial_path=None, on_exported=None):
        super().__init__(master)
        self.title("Video Editor - Lite Tutorial Maker")
        self.geometry("1400x860")
        self.minsize(1100, 700)
        self.configure(fg_color=CC_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.project = {"clips": [], "transition": "None",
                        "ratio": "16:9  Landscape", "music": "",
                        "music_vol": 0.5, "captions": False,
                        "caption_size": "Normal", "caption_pos": "Bottom",
                        "caption_anim": "Pop word-by-word",
                        "title_style": "Flame",
                        "ai_model": AI_MODELS[0],
                        "ollama_model": OLLAMA_MODEL,
                        "openrouter_key": load_openrouter_key(),
                        "normalize": False, "caption_edits": {},
                        "auto_memes": True,
                        "caption_lang": "en", "bg_blur": True,
                        "sfx": [],  # [{"path":..., "at":seconds, "vol":1.0}]
                        "chapters": []}  # v2.4: [{"time": project seconds, "title": str}]
        self.on_exported = on_exported
        self._project_path = None  # last .json project file saved / opened
        self._playing = False
        self._play_t = 0.0
        self._sound_var = tk.BooleanVar(value=True)  # play audio with the preview
        self._preview_audio_key = None
        self._preview_audio_path = None
        self._audio_rendering = False
        self._audio_render_gen = 0
        self._audio_render_after_id = None
        self._audio_render_result = None
        self._play_after_render = False
        self._highlights = []  # AI highlights: [(start, end, score)]
        self._highlight_notes = []  # matched words / model reasons, per highlight
        self._highlight_source = ""  # where the highlights came from
        self._highlight_transcript = []  # [(start, end, text, words)] in project time
        self._waveform_cache = {}   # (path, start, end) -> [rms 0..1]
        self._caption_cache = {}    # (path, start, end) -> [caption segments]
        self._caption_generating = set()  # keys with a background STT running
        self._sel = None
        self._preview_photo = None
        self._exporting = False
        self._captions_generating = False  # v2.4: Generate captions running
        self._thumbs = {}       # path -> PIL image (96x54)
        self._thumb_tk = {}     # path -> PhotoImage (timeline canvas)
        self._playhead_id = None
        self._history = []
        self._h_index = -1
        self._preview_key = None
        self._preview_frame = None
        self._settings_version = 0
        # Vars used by the media tabs AND the properties panel -
        # created first, before anything that references them.
        self._trim_start = tk.StringVar(value="0.0")
        self._trim_end = tk.StringVar(value="0.0")
        self._speed_var = tk.StringVar(value="1x")
        self._filter_var = tk.StringVar(value="None")
        self._text_var = tk.StringVar(value="")
        self._text_pos_var = tk.StringVar(value="Bottom")
        self._text_color_var = tk.StringVar(value="White")
        self._text_anim_var = tk.StringVar(value="None")
        self._clip_anim_var = tk.StringVar(value="None")
        self._sticker_var = tk.StringVar(value="None")
        self._sticker_pos_var = tk.StringVar(value="Top Right")
        self._mute_var = tk.BooleanVar(value=False)
        self._stabilize_var = tk.BooleanVar(value=False)
        self._denoise_var = tk.BooleanVar(value=False)
        self._ducking_var = tk.BooleanVar(value=False)
        self._border_var = tk.BooleanVar(value=False)
        self._letterbox_var = tk.BooleanVar(value=False)
        self._grain_var = tk.BooleanVar(value=False)
        self._ramp_var = tk.StringVar(value="None")
        self._reverse_var = tk.BooleanVar(value=False)
        self._freeze_var = tk.StringVar(value="0s")
        self._volume_var = tk.DoubleVar(value=1.0)
        self._text_style_var = tk.StringVar(value="Normal")
        self._trans_var = tk.StringVar(value="None")
        self._ratio_var = tk.StringVar(value="16:9  Landscape")
        self._quality_var = tk.StringVar(value="720p")
        self._caption_style_var = tk.StringVar(value="Normal")
        self._caption_size_var = tk.StringVar(value="Normal")
        self._caption_pos_var = tk.StringVar(value="Bottom")
        self._caption_anim_var = tk.StringVar(value="Pop word-by-word")
        self._title_style_var = tk.StringVar(value="Flame")
        self._ai_model_var = tk.StringVar(value=AI_MODELS[0])
        self._ollama_model_var = tk.StringVar(value=OLLAMA_MODEL)
        self._ai_key_var = tk.StringVar(value="")
        self._normalize_var = tk.BooleanVar(value=False)
        self._auto_memes_var = tk.BooleanVar(value=True)  # Auto-Edit meme step
        self._meme_text_var = tk.StringVar(value="")  # custom meme card words
        self._meme_style_var = tk.StringVar(value="Time Card")
        self._enhance_var = tk.BooleanVar(value=False)
        self._fade_in_var = tk.StringVar(value="0s")
        self._fade_out_var = tk.StringVar(value="0s")
        self._music_var = tk.StringVar(value="")
        self._music_vol_var = tk.DoubleVar(value=0.5)
        self._music_fade_var = tk.BooleanVar(value=True)
        self._intent_var = tk.StringVar(value="")  # AI card: what to look for
        self._media_search_var = tk.StringVar(value="")
        self._caption_lang_var = tk.StringVar(value="en")
        self._auto_highlight_var = tk.BooleanVar(value=False)
        self._captions_var = tk.BooleanVar(value=False)
        self._reframer = SmartReframe()
        try:
            from app import CHARACTER_FILTERS
            self._filters = list(CHARACTER_FILTERS)
        except Exception:
            self._filters = ["None", "Cartoon", "Anime", "Comic", "Sketch"]

        # ---------- top bar (52 px): logo + project, Undo/Redo centre, Save/Open/Help + Export right ----------
        top = ctk.CTkFrame(self, fg_color=CC_PANEL, corner_radius=0, height=52)
        top.pack(fill="x")
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="✂", font=("Segoe UI", 20),
                     text_color=CC_TEAL).pack(side="left", padx=(14, 2))
        ctk.CTkLabel(top, text="Video Editor",
                     font=("Segoe UI", 16, "bold"),
                     text_color=CC_TEXT).pack(side="left")
        self._project_name_var = tk.StringVar(value="Untitled project")
        ctk.CTkEntry(top, textvariable=self._project_name_var, width=170,
                     font=("Segoe UI", 12), text_color=CC_MUTED,
                     fg_color="transparent", border_width=0).pack(
                         side="left", padx=12)
        self._export_btn = ctk.CTkButton(
            top, text="Export", fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
            text_color="#0F1218", font=("Segoe UI", 13, "bold"),
            width=110, height=36, corner_radius=999, command=self._export)
        self._export_btn.pack(side="right", padx=14, pady=8)
        # v2.4: one-click tutorial export (1080p, H.264, captions
        # burned in when generated, chapters.txt alongside).
        self._export_tutorial_btn = ctk.CTkButton(
            top, text="🎓 Export tutorial", fg_color=CC_TEAL, hover_color=CC_TEAL_HOVER,
            text_color="#0F1218", font=("Segoe UI", 13, "bold"),
            width=150, height=36, corner_radius=999, command=self._export_tutorial)
        self._export_tutorial_btn.pack(side="right", padx=2, pady=8)
        ctk.CTkButton(top, text="?", width=36, height=36, fg_color=CC_CARD,
                      hover_color=CC_BORDER, text_color=CC_TEXT,
                      font=("Segoe UI", 14, "bold"), corner_radius=10,
                      command=self._show_help).pack(side="right", padx=2, pady=8)
        ctk.CTkButton(top, text="📂 Open", width=78, height=36, fg_color=CC_CARD,
                      hover_color=CC_BORDER, text_color=CC_TEXT,
                      font=("Segoe UI", 12), corner_radius=10,
                      command=self._load_project).pack(side="right", padx=2, pady=8)
        ctk.CTkButton(top, text="💾 Save", width=78, height=36, fg_color=CC_CARD,
                      hover_color=CC_BORDER, text_color=CC_TEXT,
                      font=("Segoe UI", 12), corner_radius=10,
                      command=self._save_project).pack(side="right", padx=2, pady=8)
        # Undo / Redo sit in the middle of the top bar.
        _mid = ctk.CTkFrame(top, fg_color="transparent")
        _mid.place(relx=0.5, rely=0.5, anchor="center")
        self._undo_btn = ctk.CTkButton(
            _mid, text="↩", width=36, height=36, fg_color=CC_CARD,
            hover_color=CC_BORDER, text_color=CC_TEXT,
            font=("Segoe UI", 14, "bold"), corner_radius=10, command=self._undo)
        self._undo_btn.pack(side="left", padx=2)
        self._redo_btn = ctk.CTkButton(
            _mid, text="↪", width=36, height=36, fg_color=CC_CARD,
            hover_color=CC_BORDER, text_color=CC_TEXT,
            font=("Segoe UI", 14, "bold"), corner_radius=10, command=self._redo)
        self._redo_btn.pack(side="left", padx=2)

        # ---------- middle: rail | panel | preview | properties ----------
        mid = ctk.CTkFrame(self, fg_color=CC_BG)
        mid.pack(fill="both", expand=True)

        # ---- left icon rail (64 px): one icon per panel section ----
        rail = ctk.CTkFrame(mid, fg_color=CC_BG, width=64, corner_radius=0)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self._rail_btns = {}
        self._section_name = "Templates"
        for icon, name in [("★", "Templates"), ("▦", "Media"), ("♪", "Audio"),
                           ("🔊", "Sounds"), ("🔤", "Text"), ("😀", "Stickers"),
                           ("✦", "Effects"), ("✨", "AI")]:
            b = ctk.CTkButton(rail, text=icon, width=48, height=48,
                              corner_radius=12, font=("Segoe UI", 20),
                              fg_color="transparent", hover_color=CC_CARD,
                              text_color=CC_MUTED,
                              command=lambda n=name: self._show_section(n))
            b.pack(pady=4)
            self._rail_btns[name] = b
        ctk.CTkButton(rail, text="?", width=48, height=48, corner_radius=12,
                      font=("Segoe UI", 20), fg_color="transparent",
                      hover_color=CC_CARD, text_color=CC_MUTED,
                      command=self._show_help).pack(side="bottom", pady=(4, 10))

        # ---- left panel (280 px): the selected rail section ----
        self._panel = ctk.CTkFrame(mid, fg_color=CC_PANEL, width=280,
                                   corner_radius=16)
        self._panel.pack(side="left", fill="y", padx=10, pady=10)
        self._panel.pack_propagate(False)
        self._tabs = self._panel  # old name: the panel that holds the sections
        self._panel_frames = {}
        for name in ["Templates", "Media", "Audio", "Sounds", "Text",
                     "Stickers", "Effects", "AI"]:
            self._panel_frames[name] = ctk.CTkFrame(self._panel,
                                                    fg_color="transparent")
        self._panel_title = ctk.CTkLabel(self._panel, text="Templates",
                                         font=("Segoe UI", 11, "bold"),
                                         text_color=CC_MUTED, anchor="w")
        self._panel_title.pack(anchor="w", padx=14, pady=(12, 2))
        self._load_user_templates()
        self._build_templates_tab()
        self._build_media_tab()
        self._build_audio_tab()
        self._build_sounds_tab()
        self._build_text_tab()
        self._build_stickers_tab()
        self._build_effects_tab()
        self._build_ai_tab()
        self._show_section("Templates")

        # ---- centre: preview + floating pill + toolbar + AI strip + transport ----
        centre = ctk.CTkFrame(mid, fg_color=CC_BG)
        centre.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        # The image is fit to its box by _show_frame (centre height
        # minus the fixed rows), and the <Configure> binding below
        # re-renders it when the box grows.  (An explicit height on
        # the label does not help: once an image is set, CTkLabel
        # sizes to the image.)
        self._preview = ctk.CTkLabel(centre, text="Import a video to preview it here",
                                     font=("Segoe UI", 12), text_color=CC_MUTED,
                                     fg_color="#000000", corner_radius=16)
        self._preview.pack(fill="both", expand=True)
        self._preview_size = None
        self._preview_resize_after = None
        self._preview.bind("<Configure>", self._on_preview_resize)
        # Floating pill under the preview (Dribbble): Magic Tools / Size / Background.
        self._pill = ctk.CTkFrame(centre, fg_color=CC_PANEL, corner_radius=999)
        self._pill.pack(pady=(6, 0))
        for text, cmd in [("✨  Magic Tools", self._toggle_ai_strip),
                          ("Size", self._cycle_ratio),
                          ("Background", self._toggle_bg_fill)]:
            ctk.CTkButton(self._pill, text=text, command=cmd, height=30,
                          fg_color="transparent", hover_color=CC_CARD,
                          text_color=CC_TEXT, corner_radius=999,
                          font=("Segoe UI", 11)).pack(side="left", padx=2, pady=3)
        # Toolbar under the preview (CapCut: Split, Speed, Volume, Delete, Text...)
        # Flow layout: the six buttons are gridded into as many
        # rows as fit, so on a narrow window they wrap to a second
        # row instead of overflowing the centre (grid can move a
        # widget between rows; pack cannot move it between parents).
        tools = ctk.CTkFrame(centre, fg_color="transparent")
        tools.pack(fill="x", pady=(6, 0))
        self._toolbar = tools
        self._toolbar_btns = []
        # Short text labels, auto-sized (width=0): the six emoji +
        # label buttons fit in one row at 1400 px and at 1024 px.
        # Sticker / Filter / Captions are not gone: Sticker lives
        # in the left rail's Stickers tab, Filter in the Effects tab
        # and the right-panel Video card, and Captions is the Auto
        # captions switch in the right-panel Project card.
        for text, cmd in [("Split", self._split_at_playhead),
                          ("Speed", lambda: self._focus_prop("speed")),
                          ("Volume", lambda: self._focus_prop("mute")),
                          ("Delete", self._remove_clip),
                          ("Duplicate", self._duplicate_clip),
                          ("Text", lambda: self._show_section("Text"))]:
            b = ctk.CTkButton(tools, text=text, command=cmd, height=30, width=0,
                              fg_color=CC_CARD, hover_color=CC_BORDER,
                              text_color=CC_TEXT, corner_radius=10,
                              font=("Segoe UI", 11))
            self._toolbar_btns.append(b)
        self._toolbar_w = 0
        self._toolbar_after = None
        tools.bind("<Configure>", self._on_toolbar_resize)
        # Grid the buttons in one row now, so the toolbar is never
        # empty; _reflow_toolbar wraps them when the centre is narrow.
        for c, b in enumerate(self._toolbar_btns):
            b.grid(row=0, column=c, padx=2, pady=2, sticky="w")
        self.after(100, self._reflow_toolbar)
        # One AI strip: a single CARD row with the 8 AI buttons in two rows of four.
        self._ai_strip = ctk.CTkFrame(centre, fg_color=CC_CARD, corner_radius=12)
        self._ai_strip.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(self._ai_strip, text="✨  AI", font=("Segoe UI", 11, "bold"),
                     text_color=CC_TEAL).pack(anchor="w", padx=12, pady=(6, 0))
        _ai_row1 = ctk.CTkFrame(self._ai_strip, fg_color="transparent")
        _ai_row1.pack(fill="x", padx=8, pady=2)
        for text, cmd in [("🔇  Remove silence", self._remove_silence),
                          ("🥁  Split on beats", self._split_on_beats),
                          ("🎞  GIF", self._export_gif),
                          ("🖼  Thumbnail", self._save_thumbnail)]:
            ctk.CTkButton(_ai_row1, text=text, command=cmd, height=30,
                          fg_color=CC_PANEL, hover_color=CC_BORDER,
                          text_color=CC_TEXT, corner_radius=10,
                          font=("Segoe UI", 11)).pack(side="left", padx=2, expand=True, fill="x")
        _ai_row2 = ctk.CTkFrame(self._ai_strip, fg_color="transparent")
        _ai_row2.pack(fill="x", padx=8, pady=(2, 6))
        for text, cmd in [("✨  Auto-Edit", self._ai_auto_edit),
                          ("🎯  Highlights", self._ai_highlights),
                          ("🎬  Scene Split", self._ai_scene_split),
                          ("🖼  Best Thumbnail", self._ai_best_thumbnail)]:
            ctk.CTkButton(_ai_row2, text=text, command=cmd, height=30,
                          fg_color=CC_PANEL, hover_color=CC_BORDER,
                          text_color=CC_TEXT, corner_radius=10,
                          font=("Segoe UI", 11)).pack(side="left", padx=2, expand=True, fill="x")
        # Transport: big round sky Play in the middle, skip buttons
        # beside it, seek slider + time below, Sound at the right.
        self._transport = ctk.CTkFrame(centre, fg_color="transparent")
        self._transport.pack(fill="x", pady=(6, 0))
        _t1 = ctk.CTkFrame(self._transport, fg_color="transparent")
        _t1.pack(fill="x")
        _t1.grid_columnconfigure(0, weight=1)
        _t1.grid_columnconfigure(2, weight=1)
        # An empty CTkFrame requests 200x200 by default - that made
        # the transport 232 px tall.  Pin the spacer to 1x1.
        ctk.CTkFrame(_t1, fg_color="transparent", width=1,
                     height=1).grid(row=0, column=0)
        _play_group = ctk.CTkFrame(_t1, fg_color="transparent")
        _play_group.grid(row=0, column=1)
        ctk.CTkButton(_play_group, text="⏮", width=40, height=40, corner_radius=10,
                      fg_color=CC_CARD, hover_color=CC_BORDER, text_color=CC_TEXT,
                      font=("Segoe UI", 14),
                      command=lambda: self._skip_clip(-1)).pack(side="left", padx=6)
        # A truly round Play: a labelled 72 px CTkButton renders as
        # a ~93x72 pill (minimum width = text + 2*corner_radius),
        # so the glyph lives in a label on top of a textless button
        # (see _round_button). The glyph is ``self._play_btn._glyph``.
        self._play_btn = _round_button(
            _play_group, "▶", CC_SKY, CC_SKY_HOVER, "#0F1218",
            ("Segoe UI", 26, "bold"), size=72, command=self._toggle_play)
        self._play_btn.pack(side="left", padx=4)
        ctk.CTkButton(_play_group, text="⏭", width=40, height=40, corner_radius=10,
                      fg_color=CC_CARD, hover_color=CC_BORDER, text_color=CC_TEXT,
                      font=("Segoe UI", 14),
                      command=lambda: self._skip_clip(1)).pack(side="left", padx=6)
        _t1r = ctk.CTkFrame(_t1, fg_color="transparent")
        _t1r.grid(row=0, column=2, sticky="e")
        ctk.CTkCheckBox(_t1r, text="🔊 Sound", variable=self._sound_var,
                        font=("Segoe UI", 11), text_color=CC_TEXT,
                        fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                        command=self._on_sound_toggle).pack(side="right", padx=(8, 0))
        _t2 = ctk.CTkFrame(self._transport, fg_color="transparent")
        _t2.pack(fill="x", pady=(2, 0))
        self._seek_var = tk.DoubleVar(value=0)
        self._seek = ctk.CTkSlider(_t2, variable=self._seek_var,
                                   from_=0, to=1000, progress_color=CC_SKY,
                                   button_color=CC_SKY, button_hover_color=CC_SKY_HOVER,
                                   command=lambda v: self._on_seek(float(v)))
        self._seek.pack(side="left", fill="x", expand=True)
        self._time_var = tk.StringVar(value="0:00 / 0:00")
        ctk.CTkLabel(_t2, textvariable=self._time_var,
                     font=("Segoe UI", 11), text_color=CC_TEXT).pack(side="left", padx=(10, 0))

        # ---- right: properties panel (300 px, scrollable) ----
        right = ctk.CTkScrollableFrame(mid, fg_color=CC_PANEL, width=268,
                                       corner_radius=16)
        self._right_panel = right
        right.pack(side="right", fill="y", padx=(0, 10), pady=10)
        # Pack order inside mid: the fixed panels take their space
        # first; the expanding centre (preview) gets what is left.
        # Packing the centre first squeezed the right panel off the
        # right edge of the window.
        centre.pack_forget()
        centre.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        def card(title):
            f = ctk.CTkFrame(right, fg_color=CC_CARD, corner_radius=12)
            f.pack(fill="x", pady=5)
            ctk.CTkLabel(f, text=title, font=("Segoe UI", 11, "bold"),
                         text_color=CC_MUTED).pack(anchor="w", padx=12, pady=(8, 2))
            return f

        b = card("Video — selected clip")
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(row, text="Start (s)", text_color=CC_TEXT).pack(side="left")
        self._trim_start_entry = ctk.CTkEntry(row, textvariable=self._trim_start, width=48,
                                              fg_color=CC_BG, border_color=CC_BORDER)
        self._trim_start_entry.pack(side="left", padx=4)
        ctk.CTkLabel(row, text="End (s)", text_color=CC_TEXT).pack(side="left")
        self._trim_end_entry = ctk.CTkEntry(row, textvariable=self._trim_end, width=48,
                                            fg_color=CC_BG, border_color=CC_BORDER)
        self._trim_end_entry.pack(side="left", padx=4)
        # Typing an exact time works: Enter or clicking away applies
        # it (clamped to the clip), and the box shows 2 decimals.
        for entry in (self._trim_start_entry, self._trim_end_entry):
            entry.bind("<Return>", self._on_trim_typed)
            entry.bind("<FocusOut>", self._on_trim_typed)
        row2 = ctk.CTkFrame(b, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(2, 6))
        ctk.CTkButton(row2, text="Set start here", width=0, fg_color=CC_BG,
                      hover_color=CC_BORDER,
                      command=lambda: self._set_trim("start")).pack(side="left", padx=2)
        ctk.CTkButton(row2, text="Set end here", width=0, fg_color=CC_BG,
                      hover_color=CC_BORDER,
                      command=lambda: self._set_trim("end")).pack(side="left", padx=2)
        # Trim to playhead (moved here from the centre toolbar, so
        # the preview has room to breathe): cut the selected clip
        # at the playhead and keep the part before or after it.
        row3 = ctk.CTkFrame(b, fg_color="transparent")
        row3.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkButton(row3, text="⏮ Keep before", width=0, fg_color=CC_BG,
                      hover_color=CC_BORDER,
                      command=lambda: self._trim_to_playhead("before")).pack(side="left", padx=2)
        ctk.CTkButton(row3, text="Keep after ⏭", width=0, fg_color=CC_BG,
                      hover_color=CC_BORDER,
                      command=lambda: self._trim_to_playhead("after")).pack(side="left", padx=2)
        ctk.CTkLabel(b, text="Speed", text_color=CC_TEXT).pack(anchor="w", padx=12)
        self._speed_menu = self._chips(b, self._speed_var,
                                       [(s, s) for s in SPEEDS],
                                       command=self._on_clip_setting_changed)
        ctk.CTkLabel(b, text="Filter", text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkOptionMenu(b, variable=self._filter_var, values=self._filters,
                          fg_color=CC_BG, button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER,
                          command=self._on_clip_setting_changed).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(b, text="Clip animation", text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkOptionMenu(b, variable=self._clip_anim_var, values=CLIP_ANIMS,
                          fg_color=CC_BG, button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER,
                          command=self._on_clip_setting_changed).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(b, text="Speed ramp (curve)", text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkOptionMenu(b, variable=self._ramp_var, values=RAMPS,
                          fg_color=CC_BG, button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER,
                          command=self._on_clip_setting_changed).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(b, text="Text style", text_color=CC_TEXT).pack(anchor="w", padx=12)
        self._chips(b, self._text_style_var, [(s, s) for s in TEXT_STYLES],
                    command=self._on_clip_setting_changed)
        ctk.CTkLabel(b, text="Freeze (hold first frame)", text_color=CC_TEXT).pack(anchor="w", padx=12)
        self._chips(b, self._freeze_var, [(s, s) for s in FREEZES],
                    command=self._on_clip_setting_changed)
        ctk.CTkLabel(b, text="Volume", text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkSlider(b, variable=self._volume_var, from_=0, to=1.5,
                      fg_color=CC_BG, button_color=CC_SKY,
                      button_hover_color=CC_SKY_HOVER,
                      command=self._on_clip_setting_changed).pack(
                          fill="x", padx=12, pady=2)
        ctk.CTkSwitch(b, text="Reverse this clip",
                      variable=self._reverse_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_clip_setting_changed).pack(anchor="w", padx=12, pady=(2, 0))
        ctk.CTkSwitch(b, text="Stabilize (fix shaky video)",
                      variable=self._stabilize_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_clip_setting_changed).pack(anchor="w", padx=12, pady=(2, 0))
        ctk.CTkSwitch(b, text="Reduce noise (clean audio)",
                      variable=self._denoise_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_clip_setting_changed).pack(anchor="w", padx=12, pady=(2, 0))
        ctk.CTkSwitch(b, text="White photo border",
                      variable=self._border_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_clip_setting_changed).pack(anchor="w", padx=12, pady=(2, 0))
        self._mute_switch = ctk.CTkSwitch(b, text="Mute this clip",
                                          variable=self._mute_var,
                                          progress_color=CC_SKY,
                                          text_color=CC_TEXT,
                                          command=self._on_clip_setting_changed)
        self._mute_switch.pack(anchor="w", padx=12, pady=(4, 0))
        # Short label: the "(brighter, richer)" detail made the
        # switch ~284 px wide and forced the whole card to 308 px,
        # clipping the trim row and the chip rows.
        ctk.CTkSwitch(b, text="Auto enhance picture",
                      variable=self._enhance_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_clip_setting_changed).pack(anchor="w", padx=12, pady=(2, 0))
        ctk.CTkLabel(b, text="Fade sound in", text_color=CC_TEXT).pack(anchor="w", padx=12)
        self._chips(b, self._fade_in_var,
                    [(s, s) for s in ["0s", "0.5s", "1s", "2s"]],
                    command=self._on_clip_setting_changed)
        ctk.CTkLabel(b, text="Fade sound out", text_color=CC_TEXT).pack(anchor="w", padx=12)
        self._chips(b, self._fade_out_var,
                    [(s, s) for s in ["0s", "0.5s", "1s", "2s"]],
                    command=self._on_clip_setting_changed)
        ctk.CTkFrame(b, fg_color="transparent", height=6).pack(fill="x")

        b = card("Project")
        ctk.CTkLabel(b, text="Transition between clips",
                     text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkOptionMenu(b, variable=self._trans_var, values=TRANSITIONS,
                          fg_color=CC_BG, button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER,
                          command=self._on_project_setting_changed).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(b, text="Video size (ratio)", text_color=CC_TEXT).pack(anchor="w", padx=12)
        self._chips(b, self._ratio_var,
                    [("16:9", "16:9  Landscape"),
                     ("9:16", "9:16  Vertical (TikTok / Reels)"),
                     ("9:16 Smart", "9:16  Smart reframe (follow face)"),
                     ("1:1", "1:1  Square")],
                    command=self._on_project_setting_changed, per_row=2)
        ctk.CTkLabel(b, text="Export quality", text_color=CC_TEXT).pack(anchor="w", padx=12)
        self._chips(b, self._quality_var, [(q, q) for q in QUALITIES],
                    command=self._on_project_setting_changed)
        ctk.CTkSwitch(b, text="Auto captions",
                      variable=self._captions_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_project_setting_changed).pack(anchor="w", padx=12, pady=(4, 0))
        ctk.CTkLabel(b, text="Captions style", text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkOptionMenu(b, variable=self._caption_style_var,
                          values=CAPTION_STYLES, fg_color=CC_BG,
                          button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER,
                          command=self._on_project_setting_changed).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(b, text="Caption size", text_color=CC_TEXT).pack(anchor="w", padx=12)
        self._chips(b, self._caption_size_var,
                    [(s, s) for s in ["Small", "Normal", "Large"]],
                    command=self._on_project_setting_changed)
        ctk.CTkLabel(b, text="Caption position", text_color=CC_TEXT).pack(anchor="w", padx=12)
        self._chips(b, self._caption_pos_var,
                    [(s, s) for s in ["Top", "Middle", "Bottom"]],
                    command=self._on_project_setting_changed)
        ctk.CTkLabel(b, text="Caption animation", text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkOptionMenu(b, variable=self._caption_anim_var,
                          values=CAPTION_ANIMS, fg_color=CC_BG,
                          button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER,
                          command=self._on_project_setting_changed).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(b, text="Cover title style", text_color=CC_TEXT).pack(anchor="w", padx=12)
        self._chips(b, self._title_style_var,
                    [(s, s) for s in list(TITLE_STYLES)],
                    command=self._on_project_setting_changed)
        # Subtitles, step by step (Dribbble wizard): pick the
        # language, tick automatic highlighting if you want the best
        # moments found too, then Create Subtitles. It just runs the
        # offline caption flow that is already in the app.
        ctk.CTkLabel(b, text="Subtitles — make them",
                     text_color=CC_TEXT,
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        ctk.CTkLabel(b, text="Language", text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkOptionMenu(b, variable=self._caption_lang_var,
                          values=["en", "auto"], fg_color=CC_BG,
                          button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER,
                          command=self._on_project_setting_changed).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(b, text="'en' = English. 'auto' = let the speech engine detect the language.",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     wraplength=260, justify="left").pack(anchor="w", padx=12, pady=(0, 4))
        ctk.CTkSwitch(b, text="Add automatic highlighting",
                      variable=self._auto_highlight_var, progress_color=CC_SKY,
                      text_color=CC_TEXT).pack(anchor="w", padx=12, pady=(2, 0))
        ctk.CTkButton(b, text="💬  Create Subtitles",
                      fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                      text_color="#0F1218", font=("Segoe UI", 12, "bold"),
                      command=self._create_subtitles).pack(fill="x", padx=12, pady=(6, 2))
        # v2.4: one tap writes a real .srt file next to each source
        # video (for YouTube / any player) and turns burn-in on.
        ctk.CTkButton(b, text="📝  Generate captions (.srt)",
                      fg_color=CC_CARD, hover_color=CC_BORDER,
                      command=self._generate_captions).pack(fill="x", padx=12, pady=(6, 2))
        ctk.CTkButton(b, text="✏️  Edit captions (fix the words)",
                      fg_color=CC_CARD, hover_color=CC_BORDER,
                      command=self._edit_captions).pack(fill="x", padx=12, pady=(6, 2))
        ctk.CTkButton(b, text="📥  Import .srt captions",
                      fg_color=CC_CARD, hover_color=CC_BORDER,
                      command=self._import_srt).pack(fill="x", padx=12, pady=(6, 2))
        ctk.CTkSwitch(b, text="Fade music in/out",
                      variable=self._music_fade_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_project_setting_changed).pack(anchor="w", padx=12, pady=(4, 0))
        ctk.CTkSwitch(b, text="Duck music under speech",
                      variable=self._ducking_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_project_setting_changed).pack(anchor="w", padx=12, pady=(2, 0))
        ctk.CTkSwitch(b, text="Letterbox bars (cinematic)",
                      variable=self._letterbox_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_project_setting_changed).pack(anchor="w", padx=12, pady=(2, 0))
        ctk.CTkSwitch(b, text="Film grain (retro)",
                      variable=self._grain_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_project_setting_changed).pack(anchor="w", padx=12, pady=(2, 0))
        ctk.CTkLabel(b, text="Speech in the video becomes text on screen. Karaoke lights up each word as it is spoken.",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     wraplength=260, justify="left").pack(
                         anchor="w", padx=12, pady=(0, 8))

        b = card("✨  AI — free models")
        ctk.CTkLabel(b, text="What should I look for?", text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkEntry(b, textvariable=self._intent_var,
                     placeholder_text="e.g. goal, funny, win",
                     fg_color=CC_BG, border_color=CC_BORDER).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(b, text="🎯  Highlights", fg_color=CC_TEAL, hover_color=CC_TEAL_HOVER,
                      text_color="white",
                      command=lambda: self._find_highlights(
                          self._intent_var.get().strip())).pack(fill="x", padx=12, pady=(4, 2))
        ctk.CTkButton(b, text="Export highlights as separate clips",
                      fg_color=CC_CARD, hover_color=CC_BORDER,
                      command=self._export_highlights_as_clips).pack(fill="x", padx=12, pady=2)
        ctk.CTkSwitch(b, text="🤣  Add memes automatically",
                      variable=self._auto_memes_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_project_setting_changed).pack(
                          anchor="w", padx=12, pady=(6, 0))
        ctk.CTkLabel(b, text="Auto-Edit drops meme sounds (and one meme card) on the best moments.",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     wraplength=230, justify="left").pack(anchor="w", padx=12, pady=(0, 2))
        ctk.CTkLabel(b, text="AI model", text_color=CC_TEXT).pack(anchor="w", padx=12, pady=(8, 0))
        ctk.CTkOptionMenu(b, variable=self._ai_model_var,
                          values=AI_MODELS, fg_color=CC_BG,
                          button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER,
                          command=self._on_project_setting_changed).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(b, text="Ollama model (local only)", text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkEntry(b, textvariable=self._ollama_model_var,
                     fg_color=CC_BG, border_color=CC_BORDER).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(b, text="Local (Ollama) — free and private, but needs Ollama installed and a model downloaded, and it is slow on a weak laptop.",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     wraplength=230, justify="left").pack(anchor="w", padx=12, pady=(0, 4))
        ctk.CTkLabel(b, text="Free AI key (optional, OpenRouter only)", text_color=CC_TEXT).pack(anchor="w", padx=12)
        ctk.CTkEntry(b, textvariable=self._ai_key_var, show="•",
                     fg_color=CC_BG, border_color=CC_BORDER).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(b, text="Stored only on this PC, never sent anywhere except to OpenRouter when you press an AI button. Get a free key at openrouter.ai — free models cost $0.",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     wraplength=230, justify="left").pack(anchor="w", padx=12, pady=(0, 4))
        key_btns = ctk.CTkFrame(b, fg_color="transparent")
        key_btns.pack(fill="x", padx=12, pady=(0, 4))
        # width=0: the 140 px default makes the two buttons ask for
        # 284 px together and forces the whole card to 308 px, which
        # clips the trim row and the chip rows.
        ctk.CTkButton(key_btns, text="💾 Save key", width=0, fg_color=CC_CARD, hover_color=CC_BORDER,
                      command=self._save_ai_key).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(key_btns, text="Clear", width=0, fg_color=CC_CARD, hover_color=CC_BORDER,
                      command=self._clear_ai_key).pack(side="left", expand=True, fill="x")
        ctk.CTkFrame(b, fg_color="transparent", height=6).pack(fill="x")

        # ---------- bottom: timeline (~200 px) ----------
        tl = ctk.CTkFrame(self, fg_color=CC_PANEL, corner_radius=16)
        self._tl_frame = tl
        tl.pack(fill="x", padx=10, pady=(0, 10))
        # Mini transport row: undo/redo/split left, delete/fullscreen right.
        tl_head = ctk.CTkFrame(tl, fg_color="transparent")
        tl_head.pack(fill="x", padx=10, pady=(8, 0))
        for text, cmd in [("↩ Undo", self._undo), ("↪ Redo", self._redo),
                          ("✂ Split", self._split_at_playhead)]:
            ctk.CTkButton(tl_head, text=text, command=cmd, height=28,
                          fg_color=CC_CARD, hover_color=CC_BORDER,
                          text_color=CC_TEXT, corner_radius=8,
                          font=("Segoe UI", 11)).pack(side="left", padx=2)
        ctk.CTkButton(tl_head, text="⛶ Fullscreen", command=self._toggle_fullscreen,
                      height=28, fg_color=CC_CARD, hover_color=CC_BORDER,
                      text_color=CC_TEXT, corner_radius=8,
                      font=("Segoe UI", 11)).pack(side="right", padx=2)
        ctk.CTkButton(tl_head, text="🗑 Delete", command=self._remove_clip,
                      height=28, fg_color=CC_CARD, hover_color=CC_BORDER,
                      text_color=CC_TEXT, corner_radius=8,
                      font=("Segoe UI", 11)).pack(side="right", padx=2)
        self._tl_info = ctk.CTkLabel(tl_head, text="No clips yet — Import a video",
                                     font=("Segoe UI", 11), text_color=CC_MUTED)
        self._tl_info.pack(side="left", padx=10)
        self._tl = tk.Canvas(tl, height=132, bg=CC_PANEL,
                             highlightthickness=0, borderwidth=0)
        self._tl.pack(fill="x", padx=10, pady=(2, 6))
        self._tl.bind("<Button-1>", self._on_timeline_click)
        self._tl.bind("<Configure>", lambda e: self._draw_timeline())
        # Bottom status strip (24 px): status left, progress right.
        status = ctk.CTkFrame(self, fg_color="transparent", height=24)
        status.pack(fill="x", padx=14, pady=(0, 10))
        # Pack order on the window: the timeline and status strip
        # take their space first; the middle (with the expanding
        # preview) gets what is left.  Packing mid first let it
        # swallow the timeline and push it below the fold.
        # (side="bottom": the first bottom-packed widget sits at the
        # very bottom, so the status strip is packed before the
        # timeline and the preview still ends up in the middle.)
        status.pack_forget()
        status.pack(fill="x", padx=14, pady=(0, 10), side="bottom")
        tl.pack_forget()
        tl.pack(fill="x", padx=10, pady=(0, 10), side="bottom")
        mid.pack_forget()
        mid.pack(fill="both", expand=True)
        self._status_var = tk.StringVar(value="Ready.")
        ctk.CTkLabel(status, textvariable=self._status_var,
                     font=("Segoe UI", 11), text_color=CC_MUTED).pack(side="left")
        self._bar = ctk.CTkProgressBar(status, width=220, progress_color=CC_SKY)
        self._bar.pack(side="right", padx=10)
        self._bar.set(0)

        # Shortcuts: Space = play/pause, Ctrl+Z = undo, Ctrl+Y = redo.
        self.bind("<space>", self._on_space)
        self.bind("<Control-z>", lambda e: self._undo())
        self.bind("<Control-y>", lambda e: self._redo())
        self.bind("<Control-Z>", lambda e: self._redo())

        # Responsiveness: when the window is resized, the panels
        # flex, the timeline grows, and wrapped labels re-wrap.
        self._resize_after = None
        self._panel_w = None
        self._tl_h = None
        self._wrap_orig = {}
        self._ai_manual = False
        self._ai_auto_hidden = False
        self.bind("<Configure>", self._on_window_resize)

        self._snapshot()
        if initial_path:
            self._add_clip(initial_path)

    def _show_help(self):
        messagebox.showinfo(
            "How to edit — 4 steps",
            "1.  Import — press ＋ Import and pick your videos.\n"
            "2.  Arrange — click a clip on the timeline to select it.\n"
            "     Split it at the white playhead with ✂ Split.\n"
            "3.  Style — pick a Template (Photo Dump, Before/After,\n"
            "     GRWM, Dance…), or set speed, speed ramp (curve),\n"
            "     filter, text, text style and animation, clip\n"
            "     animation, Reverse, Freeze, volume for the clip.\n"
            "4.  Export — top right. Pick the quality (720p / 1080p)\n"
            "     in the Project card. It saves a new *_edited.mp4\n"
            "     next to your video. Your original is never changed.\n\n"
            "Save your work: 💾 Save (top bar) saves the whole\n"
            "project to a .json file — clips, trims, text, music\n"
            "and sound effects. 📂 Open loads it back later.\n"
            "📄 Duplicate copies the selected clip, right after it.\n\n"
            "AI row (under the preview): Remove silence cuts dead\n"
            "air out of a clip, Split on beats cuts on the music,\n"
            "GIF makes a small shareable GIF, Thumbnail saves this\n"
            "frame as a YouTube thumbnail picture.\n\n"
            "Shortcuts:  Space = play / pause   •   Ctrl+Z = undo\n"
            "Ctrl+Y = redo   •   Click the timeline to jump there.")

    def _chips(self, parent, var, options, command=None, per_row=0):
        """Segmented pill chips bound to a variable. options =
        [(label, value), ...]. The selected chip is sky with dark
        text; the rest are card with light text. `command` runs when
        the user picks a chip (not when the value is set by code,
        e.g. loading a project). `per_row` wraps long lists."""
        items = list(options)
        groups = ([items[i:i + per_row] for i in range(0, len(items), per_row)]
                  if per_row and len(items) > per_row else [items])
        btns = []

        def refresh(*_a):
            cur = var.get()
            for value, b in btns:
                if value == cur:
                    b.configure(fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                                text_color="#0F1218")
                else:
                    b.configure(fg_color=CC_CARD, hover_color=CC_BORDER,
                                text_color=CC_TEXT)

        rows = []
        for group in groups:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            rows.append(row)
            for label, value in group:
                # width=0: auto-size to the text.  The 140 px
                # default makes two chips wider than the panel and
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

    def _show_section(self, name):
        """Switch the left panel to one rail section (replaces the
        old tab view's segmented-button row). All sections stay
        built, so the media list and the sounds list are always
        there for the code that refreshes them."""
        self._section_name = name
        for n, f in self._panel_frames.items():
            if n == name:
                f.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            else:
                f.pack_forget()
        self._panel_title.configure(text=name)
        if name == "Effects":
            self._build_effects_tab()
        if name == "Templates":
            # Rebuilt on every visit, so meme videos that finish
            # rendering while the editor is open show up here.
            self._build_templates_tab()
        for n, b in self._rail_btns.items():
            if n == name:
                b.configure(fg_color="#1E3A4A", text_color=CC_SKY)
            else:
                b.configure(fg_color="transparent", text_color=CC_MUTED)

    def _build_ai_tab(self):
        """The rail's AI section: the same one-tap AI tools as the
        strip under the preview, for when the strip is hidden."""
        tab = self._panel_frames["AI"]
        ctk.CTkLabel(tab, text="One-tap AI edits — free, on this PC",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     wraplength=250, justify="left").pack(anchor="w", pady=(4, 8))
        frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        for text, cmd in [("🔇  Remove silence", self._remove_silence),
                          ("🥁  Split on beats", self._split_on_beats),
                          ("🎞  GIF", self._export_gif),
                          ("🖼  Thumbnail", self._save_thumbnail),
                          ("✨  Auto-Edit", self._ai_auto_edit),
                          ("🎯  Highlights", self._ai_highlights),
                          ("🎬  Scene Split", self._ai_scene_split),
                          ("🖼  Best Thumbnail", self._ai_best_thumbnail)]:
            ctk.CTkButton(frame, text=text, anchor="w", height=34,
                          fg_color=CC_CARD, hover_color=CC_BORDER,
                          text_color=CC_TEXT, font=("Segoe UI", 11),
                          command=cmd).pack(fill="x", pady=2)
        ctk.CTkLabel(frame,
                     text="The free AI model (OpenRouter key or local Ollama) is chosen in the AI card on the right.",
                     text_color=CC_MUTED, font=("Segoe UI", 10),
                     wraplength=240, justify="left").pack(anchor="w", pady=(8, 0))

    def _toggle_ai_strip(self):
        """Floating pill: Magic Tools — show / hide the AI strip.
        A manual show is the user's choice: the auto-hide in
        _apply_window_size never hides a strip the user showed
        on purpose, and never restores one they hid."""
        if self._ai_strip.winfo_ismapped():
            self._ai_strip.pack_forget()
            self._ai_manual = False
            self._ai_auto_hidden = False
        else:
            self._ai_strip.pack(fill="x", pady=(6, 0), before=self._transport)
            self._ai_manual = True
            self._ai_auto_hidden = False

    def _cycle_ratio(self):
        """Floating pill: Size — step through the video sizes."""
        vals = list(RATIOS)
        try:
            i = vals.index(self._ratio_var.get())
        except ValueError:
            i = -1
        self._ratio_var.set(vals[(i + 1) % len(vals)])
        self._on_project_setting_changed()
        self._status_var.set("Video size: %s" % self._ratio_var.get())

    def _toggle_bg_fill(self):
        """Floating pill: Background — blurred fill on / off for
        vertical / square videos (plain black bars when off)."""
        cur = bool(self.project.get("bg_blur", True))
        self.project["bg_blur"] = not cur
        self._snapshot()
        self._show_frame(self._play_t)
        self._status_var.set("Background fill: %s"
                             % ("blurred" if not cur else "plain black"))

    def _toggle_fullscreen(self):
        """Timeline mini-row: make the editor fill the whole screen
        (press again, or Esc in the window, to come back)."""
        on = not getattr(self, "_fullscreen", False)
        self._fullscreen = on
        try:
            self.attributes("-fullscreen", on)
        except Exception:
            pass

    def _skip_clip(self, direction):
        """Transport ⏮ / ⏭: jump to the start of the previous /
        next clip (⏮ goes to the start of the current clip, unless
        already near it — then to the previous one)."""
        if not self.project["clips"]:
            return
        total = project_duration(self.project)
        if total <= 0:
            return
        starts = [self._clip_start_time(i)
                  for i in range(len(self.project["clips"]))]
        t = self._play_t
        if direction < 0:
            target = 0.0
            for s in starts:
                if s < t - 0.2:
                    target = s
            self._on_seek(target / total * 1000.0)
        else:
            target = total - 0.01
            for s in starts:
                if s > t + 0.05:
                    target = s
                    break
            self._on_seek(target / total * 1000.0)

    def _create_subtitles(self):
        """Guided subtitle step (Dribbble wizard): turn auto
        captions on, listen to every clip once, and — when the
        'automatic highlighting' box is ticked — find the best
        moments too. Uses the offline speech engine, as always."""
        if not self.project["clips"]:
            messagebox.showinfo("Create subtitles", "Add a video clip first.")
            return
        self._captions_var.set(True)
        self._read_project_settings()
        self._snapshot()
        for ci, c in enumerate(self.project["clips"]):
            self._captions_for_clip(ci, c)
        self._show_frame(self._play_t)
        self._status_var.set(
            "Creating subtitles from the speech in your video… they appear on the preview and on export.")
        if self._auto_highlight_var.get():
            self._find_highlights("")

    def _generate_captions(self):
        """Generate captions (.srt) for every clip: listen with the
        offline speech engine (the same one Smart Record uses),
        write an .srt next to each source video, and turn Auto
        captions on so the export burns them in too. Runs in the
        background; a missing speech engine shows a clear message
        instead of crashing."""
        if not self.project["clips"]:
            messagebox.showinfo("Generate captions", "Add a video clip first.")
            return
        if self._captions_generating:
            self._status_var.set("Captions are already being generated…")
            return
        self._captions_generating = True
        self._status_var.set("Generating captions… listening to the speech in your video (first time may download the speech model, ~75 MB, once)")
        threading.Thread(target=self._generate_captions_thread, daemon=True).start()

    def _generate_captions_thread(self):
        lang = self.project.get("caption_lang", "en")
        written, errors = [], []
        edits = dict(self.project.get("caption_edits") or {})
        for ci, c in enumerate(self.project["clips"]):
            # A .srt next to the video wins over listening again.
            segs, err = srt_segments_for_clip(c["path"], c["start"], c["end"])
            if not segs:
                segs, err = make_captions(c["path"], c["start"], c["end"],
                                          language=lang)
            if err:
                errors.append("clip %d: %s" % (ci + 1, err))
                continue
            if not segs:
                errors.append("clip %d: no speech found" % (ci + 1))
                continue
            # Burn-in uses clip-local times; the .srt next to the
            # source video uses file times (trim start + local).
            edits[str(ci)] = [dict(s) for s in segs]
            start = float(c.get("start", 0.0))
            file_segs = [{"start": start + float(s["start"]),
                          "end": start + float(s["end"]),
                          "text": s.get("text", "")} for s in segs]
            try:
                srt_path = Path(c["path"]).with_suffix(".srt")
                srt_path.write_text(segments_to_srt(file_segs), encoding="utf-8")
                written.append(srt_path.name)
            except Exception as exc:
                errors.append("clip %d: could not write .srt (%s)" % (ci + 1, exc))

        def _done():
            self._captions_generating = False
            if written:
                self.project["caption_edits"] = edits
                self._caption_cache = {}
                self._captions_var.set(True)
                self._read_project_settings()
                self._snapshot()
                self._preview_key = None
                self._refresh_all()
            if written and not errors:
                self._status_var.set("Captions saved: %s. Auto captions is ON, so the export burns them in." % ", ".join(written))
                messagebox.showinfo("Captions generated",
                                    "Saved:\n" + "\n".join("  " + w for w in written) +
                                    "\n\nAuto captions is ON, so the export burns them into the video too.")
            elif written:
                self._status_var.set("Captions saved for %d clip(s): %s. %s" % (len(written), ", ".join(written), "; ".join(errors)))
                messagebox.showinfo("Captions generated",
                                    "Saved:\n" + "\n".join("  " + w for w in written) +
                                    "\n\nSome clips had no captions:\n" + "\n".join("  " + e for e in errors))
            else:
                self._status_var.set("Could not generate captions: %s" % ("; ".join(errors) or "unknown error"))
                messagebox.showwarning("Could not generate captions",
                                       "No captions were made.\n\n" + "\n".join(errors) +
                                       "\n\nInstall the speech engine with: pip install -r requirements-smart.txt")

        self.after(0, _done)

    def _on_space(self, _event=None):
        # Space plays/pauses — unless you are typing in a text box.
        focus = self.focus_get()
        if focus is not None and isinstance(focus, (tk.Entry, ctk.CTkEntry)):
            return
        self._toggle_play()
        return "break"

    # ---------- media panel tabs ----------
    def _build_templates_tab(self):
        tab = self._panel_frames["Templates"]
        for child in tab.winfo_children():
            child.destroy()
        ctk.CTkLabel(tab, text="One tap — a whole look for your video",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     wraplength=250, justify="left").pack(anchor="w", pady=(4, 8))
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", pady=(0, 4))
        # width=0: the 140 px default makes the two buttons ask for
        # 286 px together and forces the panel wider than the window.
        ctk.CTkButton(row, text="📥  Import template", height=28, width=0,
                      fg_color=CC_CARD, hover_color=CC_BORDER,
                      text_color=CC_TEXT, font=("Segoe UI", 11),
                      command=self._import_template).pack(side="left", expand=True, fill="x", padx=(0, 3))
        ctk.CTkButton(row, text="💾  Save my look", height=28, width=0,
                      fg_color=CC_CARD, hover_color=CC_BORDER,
                      text_color=CC_TEXT, font=("Segoe UI", 11),
                      command=self._save_template).pack(side="left", expand=True, fill="x", padx=(3, 0))
        frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        _STRIP_COLORS = ["#7C5CFF", "#12B5D9", "#34D399", "#FBBF24",
                         "#E5484D", "#C86BA6", "#5E8FC4"]
        for _i, (name, t) in enumerate(TEMPLATES.items()):
            card = ctk.CTkFrame(frame, fg_color=CC_CARD, corner_radius=12)
            card.pack(fill="x", pady=4)
            # A coloured strip stands in for a thumbnail until real
            # template thumbnails exist.
            ctk.CTkFrame(card, fg_color=_STRIP_COLORS[_i % len(_STRIP_COLORS)],
                         corner_radius=8, height=36).pack(fill="x", padx=2, pady=(2, 0))
            ctk.CTkLabel(card, text=name, font=("Segoe UI", 12, "bold"),
                         text_color=CC_TEXT).pack(anchor="w", padx=10, pady=(6, 0))
            ctk.CTkLabel(card, text=t["desc"], font=("Segoe UI", 11),
                         text_color=CC_MUTED, wraplength=230,
                         justify="left").pack(anchor="w", padx=10)
            anims = "  •  ".join(x for x in (t.get("text_anim"), t.get("clip_anim"))
                                 if x and x != "None")
            info = "%s  •  %s  •  %s" % (
                t["ratio"].split("  ")[0], t["transition"],
                ("Captions ON" if t["captions"] else "Captions OFF"))
            if anims:
                info += "  •  " + anims
            ctk.CTkLabel(card, text=info,
                         font=("Segoe UI", 10), text_color=CC_SKY,
                         wraplength=240, justify="left").pack(
                    anchor="w", padx=10, pady=(2, 0))
            ctk.CTkButton(card, text="Apply template", height=30,
                          fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                          text_color="#0F1218",
                          font=("Segoe UI", 12, "bold"),
                          command=lambda n=name: self._apply_template(n)).pack(
                              fill="x", padx=10, pady=(6, 2))
            if name.startswith("📥"):
                # User / imported templates can be deleted (built-in
                # ones stay — they are part of the app).
                ctk.CTkButton(card, text="🗑  Delete this template", height=26,
                              fg_color="transparent", hover_color="#3a2020",
                              text_color="#ff8080", border_color="#5a2a2a",
                              border_width=1, font=("Segoe UI", 11),
                              command=lambda n=name: self._delete_template(n)).pack(
                                  fill="x", padx=10, pady=(0, 8))
        # ---- Meme videos: short ready-made clips to drop in ----
        # (The section is rebuilt every time the tab is shown, so
        # clips that finish rendering while the editor is open
        # appear without a restart. A missing folder or file never
        # breaks this tab — that row just says "Not ready yet".)
        ctk.CTkLabel(frame, text="🎬  Meme videos",
                     font=("Segoe UI", 12, "bold"),
                     text_color=CC_TEXT).pack(anchor="w", pady=(14, 2))
        ctk.CTkLabel(frame, text="Short meme clips — tap ＋ Add to drop one in at the playhead.",
                     font=("Segoe UI", 11), text_color=CC_MUTED,
                     wraplength=230, justify="left").pack(anchor="w", pady=(0, 4))
        any_ready = False
        shown = set()
        for label, fname in MEME_VIDEOS:
            path = meme_video_path(fname)
            if path:
                any_ready = True
                shown.add(fname.lower())
            row = ctk.CTkFrame(frame, fg_color=CC_CARD, corner_radius=12)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=label, font=("Segoe UI", 11, "bold"),
                         text_color=CC_TEXT, wraplength=140,
                         justify="left").pack(side="left", padx=10, pady=8)
            if path:
                ctk.CTkButton(row, text="＋ Add", width=60, height=28,
                              fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                              text_color="#0F1218",
                              font=("Segoe UI", 11, "bold"),
                              command=lambda p=path, l=label: self._add_meme_video(p, l)).pack(
                                  side="right", padx=8, pady=6)
            else:
                ctk.CTkLabel(row, text="Not ready yet", font=("Segoe UI", 11),
                             text_color=CC_MUTED).pack(side="right", padx=10, pady=8)
        # Any other .mp4 in the folder (the 100-clip library,
        # custom cards) shows up here too, so the list never goes
        # stale when new clips land.
        for label, path in meme_video_files():
            if Path(path).name.lower() in shown:
                continue
            shown.add(Path(path).name.lower())
            any_ready = True
            row = ctk.CTkFrame(frame, fg_color=CC_CARD, corner_radius=12)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=label, font=("Segoe UI", 11, "bold"),
                         text_color=CC_TEXT, wraplength=140,
                         justify="left").pack(side="left", padx=10, pady=8)
            ctk.CTkButton(row, text="＋ Add", width=60, height=28,
                          fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                          text_color="#0F1218",
                          font=("Segoe UI", 11, "bold"),
                          command=lambda p=path, l=label: self._add_meme_video(p, l)).pack(
                              side="right", padx=8, pady=6)
        if not any_ready:
            ctk.CTkLabel(frame, text="No meme videos on this PC yet — they appear here when they finish rendering.",
                         font=("Segoe UI", 11), text_color=CC_MUTED,
                         wraplength=230, justify="left").pack(anchor="w", pady=(2, 8))
        # ---- Make my own meme card: type any words, pick a style,
        # render a new 2.5 s card into meme-videos/ and drop it in
        # at the playhead. (So the library is effectively unlimited
        # — 100 shipped clips, plus any card the user makes.) ----
        ctk.CTkLabel(frame, text="🎨  Make my own meme card",
                     font=("Segoe UI", 12, "bold"),
                     text_color=CC_TEXT).pack(anchor="w", pady=(14, 2))
        ctk.CTkEntry(frame, textvariable=self._meme_text_var,
                     placeholder_text="Your meme words…",
                     fg_color=CC_BG, border_color=CC_BORDER).pack(fill="x", pady=2)
        ctk.CTkOptionMenu(frame, variable=self._meme_style_var,
                          values=["Time Card", "Neon", "Pill", "Red",
                                  "White", "Gold", "Green"],
                          fg_color=CC_BG, button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER).pack(fill="x", pady=2)
        ctk.CTkButton(frame, text="🎬  Make my meme card",
                      fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                      text_color="#0F1218", font=("Segoe UI", 12, "bold"),
                      command=self._make_meme_card).pack(fill="x", pady=(4, 8))
    def _apply_template(self, name):
        t = TEMPLATES.get(name)
        if not t:
            return
        self._read_clip_settings()
        self.project["transition"] = t["transition"]
        self.project["ratio"] = t["ratio"]
        self.project["captions"] = t["captions"]
        self.project["caption_style"] = t.get("caption_style", "Normal")
        self.project["letterbox"] = bool(t.get("letterbox", False))
        self.project["grain"] = bool(t.get("grain", False))
        self._trans_var.set(t["transition"])
        self._ratio_var.set(t["ratio"])
        self._captions_var.set(t["captions"])
        self._caption_style_var.set(t.get("caption_style", "Normal"))
        self._letterbox_var.set(bool(t.get("letterbox", False)))
        self._grain_var.set(bool(t.get("grain", False)))
        for c in self.project["clips"]:
            c["speed"] = t["speed"]
            c["filter"] = t["filter"]
            c["text_color"] = t["text_color"]
            c["text_anim"] = t.get("text_anim", "None")
            c["clip_anim"] = t.get("clip_anim", "None")
            c["ramp"] = t.get("ramp", "None")
            c["border"] = bool(t.get("border", False))
            # Meme templates carry their phrase: applying one
            # writes the words on the clip (big, centred). Other
            # templates have no "text" key and leave the clip's
            # own text exactly as it was.
            if t.get("text"):
                c["text"] = t["text"]
                c["text_pos"] = t.get("text_pos", "Middle")
                c["text_style"] = t.get("text_style", "Normal")
        self._settings_version += 1
        self._preview_key = None
        self._snapshot()
        self._refresh_all()
        self._load_clip_settings()
        self._show_frame(self._play_t)
        self._status_var.set("Template applied: %s — press Export when you are happy." % name)

    def _build_media_tab(self):
        tab = self._panel_frames["Media"]
        ctk.CTkEntry(tab, textvariable=self._media_search_var,
                     placeholder_text="🔍  Search media…",
                     fg_color=CC_BG, border_color=CC_BORDER).pack(fill="x", pady=(4, 4))
        ctk.CTkButton(tab, text="＋  Import", command=self._add_clips,
                      fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                      text_color="#0F1218",
                      font=("Segoe UI", 12, "bold")).pack(fill="x", pady=(4, 8))
        self._media_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._media_frame.pack(fill="both", expand=True)
        self._media_search_var.trace_add(
            "write", lambda *_a: self._refresh_media())
    def _build_audio_tab(self):
        tab = self._panel_frames["Audio"]
        ctk.CTkLabel(tab, text="Background music", text_color=CC_TEXT,
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(4, 2))
        ctk.CTkEntry(tab, textvariable=self._music_var,
                     placeholder_text="No music",
                     fg_color=CC_BG, border_color=CC_BORDER).pack(fill="x", pady=2)
        ctk.CTkButton(tab, text="Browse…", command=self._pick_music,
                      fg_color=CC_CARD, hover_color=CC_BORDER).pack(fill="x", pady=4)
        ctk.CTkLabel(tab, text="Music volume", text_color=CC_TEXT).pack(anchor="w")
        ctk.CTkSlider(tab, variable=self._music_vol_var, from_=0, to=1,
                      progress_color=CC_SKY, button_color=CC_SKY,
                      button_hover_color=CC_SKY_HOVER).pack(fill="x", pady=2)
        ctk.CTkSwitch(tab, text="Normalize loudness (even volume)",
                      variable=self._normalize_var, progress_color=CC_SKY,
                      text_color=CC_TEXT,
                      command=self._on_project_setting_changed).pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(tab, text="Makes quiet and loud parts the same\nlevel, in the export and the preview.",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     justify="left").pack(anchor="w", pady=2)
        ctk.CTkButton(tab, text="🔊  Test sound (do you hear the Ding?)",
                      fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                      text_color="#0F1218",
                      command=self._test_sound).pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(tab, text="If you hear nothing in the editor, press\nTest sound first — it tells you if the\nproblem is the sound player or the video.",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     justify="left").pack(anchor="w", pady=2)
        ctk.CTkLabel(tab, text="Tip: mute a single clip in the Video panel\non the right.",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     justify="left").pack(anchor="w", pady=8)

    def _build_sounds_tab(self):
        """Free sound-effects library. Every sound was synthesized
        (no samples copied from anywhere), so the library is free to
        use. ▶ listens to a sound, ＋ adds it at the playhead."""
        tab = self._panel_frames["Sounds"]
        ctk.CTkLabel(tab, text="Sound effects — free, built in",
                     text_color=CC_TEXT,
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(4, 2))
        ctk.CTkLabel(tab, text="▶ listen, then ＋ to add it at the\nplayhead. It is mixed into the export.",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     justify="left").pack(anchor="w", pady=(0, 6))
        frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        self._sfx_frame = frame
        self._refresh_sounds_tab()
        ctk.CTkButton(tab, text="📥  Import my own sound (.mp3 / .wav)",
                      fg_color=CC_CARD, hover_color=CC_BORDER,
                      command=self._import_sound).pack(fill="x", pady=(6, 2))
        ctk.CTkButton(tab, text="🗑  Remove added sounds",
                      fg_color="transparent", hover_color="#3a2020",
                      text_color="#ff8080", border_color="#5a2a2a", border_width=1,
                      command=self._clear_sfx).pack(fill="x", pady=2)

    def _refresh_sounds_tab(self):
        if not hasattr(self, "_sfx_frame"):
            return
        for w in self._sfx_frame.winfo_children():
            w.destroy()
        lib = sfx_library()
        if not lib:
            ctk.CTkLabel(self._sfx_frame,
                         text="No sounds found — the sounds/ folder\nis missing from the install.",
                         text_color=CC_MUTED, font=("Segoe UI", 11),
                         justify="left").pack(anchor="w", pady=8)
            return
        for name, path in lib:
            row = ctk.CTkFrame(self._sfx_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=name, text_color=CC_TEXT,
                         font=("Segoe UI", 11), width=110, anchor="w").pack(side="left")
            ctk.CTkButton(row, text="▶", width=36, height=28,
                          fg_color=CC_CARD, hover_color=CC_BORDER,
                          command=lambda p=path: self._listen_sfx(p)).pack(side="left", padx=2)
            ctk.CTkButton(row, text="＋ Add", width=64, height=28,
                          fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                          text_color="#0F1218",
                          command=lambda p=path, n=name: self._add_sfx(p, n)).pack(side="left", padx=2)

    def _listen_sfx(self, path):
        if not _play_wav_file(path):
            self._status_var.set("Could not play that sound (no sound device?).")

    def _add_sfx(self, path, name):
        self.project.setdefault("sfx", []).append(
            {"path": path, "at": float(self._play_t), "vol": 1.0})
        self._push_history()
        self._preview_audio_key = None  # the mix changed — re-render it
        self._draw_timeline()
        self._status_var.set("Added %s at %s — it plays on export and in the preview."
                             % (name, self._fmt(self._play_t)))

    def _import_sound(self):
        path = filedialog.askopenfilename(
            title="Import a sound",
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.ogg *.flac"), ("All files", "*.*")])
        if not path:
            return
        # Keep a copy with the app's sounds so it survives a move.
        try:
            dest_dir = None
            for cand in (get_app_dir() / "sounds",
                         Path(sys.executable).parent / "sounds"):
                try:
                    cand.mkdir(exist_ok=True)
                    dest_dir = cand
                    break
                except Exception:
                    continue
            if dest_dir is not None:
                dest = dest_dir / Path(path).name
                if os.path.abspath(str(dest)) != os.path.abspath(path):
                    shutil.copy2(path, dest)
                path = str(dest)
        except Exception:
            pass
        self._add_sfx(path, Path(path).stem)
        self._refresh_sounds_tab()

    def _clear_sfx(self):
        if not self.project.get("sfx"):
            return
        if not messagebox.askyesno("Remove sounds",
                                   "Remove all %d added sound effect(s) from this project?"
                                   % len(self.project["sfx"])):
            return
        self.project["sfx"] = []
        self._push_history()
        self._preview_audio_key = None
        self._draw_timeline()
        self._status_var.set("Removed all added sounds.")

    def _build_text_tab(self):
        tab = self._panel_frames["Text"]
        ctk.CTkLabel(tab, text="Text on the selected clip",
                     text_color=CC_TEXT,
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(4, 2))
        ctk.CTkEntry(tab, textvariable=self._text_var,
                     placeholder_text="Type your text…",
                     fg_color=CC_BG, border_color=CC_BORDER).pack(fill="x", pady=2)
        ctk.CTkLabel(tab, text="Position", text_color=CC_TEXT).pack(anchor="w")
        ctk.CTkOptionMenu(tab, variable=self._text_pos_var,
                          values=TEXT_POSITIONS, fg_color=CC_BG,
                          button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER).pack(fill="x", pady=2)
        ctk.CTkLabel(tab, text="Colour", text_color=CC_TEXT).pack(anchor="w")
        ctk.CTkOptionMenu(tab, variable=self._text_color_var,
                          values=list(TEXT_COLORS), fg_color=CC_BG,
                          button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER).pack(fill="x", pady=2)
        ctk.CTkLabel(tab, text="Text animation", text_color=CC_TEXT).pack(anchor="w")
        ctk.CTkOptionMenu(tab, variable=self._text_anim_var,
                          values=TEXT_ANIMS, fg_color=CC_BG,
                          button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER).pack(fill="x", pady=2)
        ctk.CTkLabel(tab, text="Fade in, Pop in, Typewriter, Bounce,\nWave, Shake, Glitch…",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     justify="left").pack(anchor="w", pady=4)

    def _build_stickers_tab(self):
        tab = self._panel_frames["Stickers"]
        ctk.CTkLabel(tab, text="Tap a sticker to put it on the\nselected clip",
                     text_color=CC_MUTED, font=("Segoe UI", 11),
                     justify="left").pack(anchor="w", pady=(4, 8))
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(fill="x")
        for i, s in enumerate(STICKERS):
            ctk.CTkButton(grid, text=s, width=56, height=44,
                          fg_color=CC_CARD, hover_color=CC_BORDER,
                          font=("Segoe UI", 18),
                          command=lambda v=s: self._set_sticker(v)).grid(
                              row=i // 4, column=i % 4, padx=3, pady=3)
        ctk.CTkLabel(tab, text="Position", text_color=CC_TEXT).pack(anchor="w", pady=(8, 0))
        ctk.CTkOptionMenu(tab, variable=self._sticker_pos_var,
                          values=STICKER_POSITIONS, fg_color=CC_BG,
                          button_color=CC_SKY,
                          button_hover_color=CC_SKY_HOVER).pack(fill="x", pady=2)

    def _build_effects_tab(self):
        tab = self._panel_frames["Effects"]
        for child in tab.winfo_children():
            child.destroy()
        ctk.CTkLabel(tab, text="Filter for the selected clip",
                     text_color=CC_TEXT,
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(4, 8))
        frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        # Filter swatches in a 2-column grid; the selected filter
        # gets a sky check so you can see it at a glance.
        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x")
        cur = self._filter_var.get()
        for i, name in enumerate(self._filters):
            sel = (name == cur)
            ctk.CTkButton(grid, text=("✓  " + name) if sel else name,
                          height=40, corner_radius=10,
                          fg_color=CC_SKY if sel else CC_CARD,
                          hover_color=CC_SKY_HOVER if sel else CC_BORDER,
                          text_color="#0F1218" if sel else CC_TEXT,
                          font=("Segoe UI", 11),
                          command=lambda v=name: self._set_filter(v)).grid(
                              row=i // 2, column=i % 2, padx=3, pady=3, sticky="ew")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(frame, text="📥  Load a .cube colour look (free LUT)",
                      anchor="w", height=32,
                      fg_color=CC_SKY, hover_color=CC_SKY_HOVER,
                      text_color="#0F1218",
                      command=self._load_lut).pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(frame,
                     text="Free .cube looks: FreeVisuals, FilterGrade, videoeditingluts.com — download one, load it here, and it colours the selected clip like a real film grade.",
                     text_color=CC_MUTED, font=("Segoe UI", 10),
                     wraplength=240, justify="left").pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(frame, text="Clip animation",
                     text_color=CC_TEXT,
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(10, 4))
        for name in CLIP_ANIMS:
            ctk.CTkButton(frame, text=name, anchor="w", height=32,
                          fg_color=CC_CARD, hover_color=CC_BORDER,
                          text_color=CC_TEXT,
                          command=lambda v=name: self._set_clip_anim(v)).pack(
                              fill="x", pady=2)
    def _set_clip_anim(self, value):
        self._clip_anim_var.set(value)
        self._read_clip_settings()
        self._show_frame(self._play_t)

    def _focus_prop(self, what):
        if what == "speed":
            self._speed_menu.focus_set()
        elif what == "mute":
            self._mute_var.set(not self._mute_var.get())
            self._read_clip_settings()
            self._show_frame(self._play_t)

    def _toggle_captions(self):
        self._captions_var.set(not self._captions_var.get())
        self._status_var.set("Auto captions %s — they will appear on export."
                             % ("ON" if self._captions_var.get() else "OFF"))

    def _set_sticker(self, value):
        self._sticker_var.set(value)
        self._read_clip_settings()
        self._show_frame(self._play_t)
        self._draw_timeline()

    def _set_filter(self, value):
        self._filter_var.set(value)
        self._read_clip_settings()
        self._show_frame(self._play_t)
        self._build_effects_tab()  # refresh the sky check on the grid

    def _load_lut(self):
        """Load a free .cube colour look and put it on the selected clip."""
        if self._sel is None:
            messagebox.showinfo("Colour look", "Add a video clip first, then select it.")
            return
        path = filedialog.askopenfilename(
            title="Load a .cube colour look",
            filetypes=[("3D LUT files", "*.cube"), ("All files", "*.*")])
        if not path:
            return
        lut, err = parse_cube(path)
        if lut is None:
            messagebox.showerror("Colour look", err)
            return
        c = self.project["clips"][self._sel]
        c["lut"] = lut
        c["lut_name"] = Path(path).stem
        self._filter_var.set("LUT")
        self._read_clip_settings()
        self._show_frame(self._play_t)
        self._status_var.set("Colour look loaded: %s — applied to the selected clip." % Path(path).name)

    # ---------- templates: import / save / auto-load ----------
    def _delete_template(self, name):
        """Delete a user / imported template (from the list and from
        its .json file in the templates folder, if it has one)."""
        if not messagebox.askyesno("Delete template",
                                   "Delete the template '%s'?" % name):
            return
        TEMPLATES.pop(name, None)
        plain = name[3:].strip() if name.startswith("📥") else name
        for folder in (get_app_dir() / "templates",
                       Path(sys.executable).parent / "templates"):
            if not folder.is_dir():
                continue
            for path in folder.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if str(data.get("name") or path.stem).strip() == plain:
                        path.unlink()
                except Exception:
                    pass
        self._build_templates_tab()
        self._status_var.set("Template deleted: %s" % name)

    def _import_template(self):
        """Import a template from a .json file (a look someone shared)."""
        path = filedialog.askopenfilename(
            title="Import a template",
            filetypes=[("Template files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror("Import template", "That file is not a template: %s" % exc)
            return
        name = str(data.get("name") or Path(path).stem)
        if not name.startswith(("🎮", "📱", "🎬", "⚡", "😂", "✨", "📸", "🔄", "💄", "👗", "🔋", "✈️", "🕺", "🖼️", "🥁", "🐢", "📷", "🎞️", "📼", "🪝", "🎵", "📹", "💀")):
            name = "📥  " + name
        TEMPLATES[name] = {
            "desc": str(data.get("desc", "Imported template")),
            "ratio": str(data.get("ratio", "9:16  Vertical (TikTok / Reels)")),
            "transition": str(data.get("transition", "Fade")),
            "speed": float(data.get("speed", 1.0)),
            "filter": str(data.get("filter", "None")),
            "text_color": str(data.get("text_color", "White")),
            "text_anim": str(data.get("text_anim", "None")),
            "clip_anim": str(data.get("clip_anim", "None")),
            "captions": bool(data.get("captions", False)),
            "caption_style": str(data.get("caption_style", "Normal")),
            "ramp": str(data.get("ramp", "None")),
            "letterbox": bool(data.get("letterbox", False)),
            "grain": bool(data.get("grain", False)),
            "border": bool(data.get("border", False)),
        }
        self._build_templates_tab()
        self._status_var.set("Template imported: %s" % name)

    def _save_template(self):
        """Save the current look (project + selected clip) as a .json
        template the user can share or import later."""
        self._read_project_settings()
        c = self.project["clips"][self._sel] if self._sel is not None else {}
        data = {
            "name": "My look",
            "desc": "Saved from the editor",
            "ratio": self.project.get("ratio", "9:16  Vertical (TikTok / Reels)"),
            "transition": self.project.get("transition", "Fade"),
            "speed": float(c.get("speed", 1.0)),
            "filter": str(c.get("filter", "None")),
            "text_color": str(c.get("text_color", "White")),
            "text_anim": str(c.get("text_anim", "None")),
            "clip_anim": str(c.get("clip_anim", "None")),
            "captions": bool(self.project.get("captions", False)),
            "caption_style": str(self.project.get("caption_style", "Normal")),
            "ramp": str(c.get("ramp", "None")),
            "letterbox": bool(self.project.get("letterbox", False)),
            "grain": bool(self.project.get("grain", False)),
            "border": bool(c.get("border", False)),
        }
        path = filedialog.asksaveasfilename(
            title="Save this look as a template",
            defaultextension=".json",
            filetypes=[("Template files", "*.json")],
            initialfile="my-look-template.json")
        if not path:
            return
        # The saved look joins the list right away (and saving over
        # an existing name updates that template).
        name = "📥  " + Path(path).stem.replace("-", " ").title()
        if name in TEMPLATES and not messagebox.askyesno(
                "Template saved",
                "A template called '%s' already exists.\nOverwrite it with this look?" % name):
            return
        try:
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
            TEMPLATES[name] = dict(data, desc="Saved from the editor")
            self._build_templates_tab()
            messagebox.showinfo("Template saved",
                "Saved to %s and added to your templates.\n\nShare this .json file with anyone — they can import it from the Templates tab." % Path(path).name)
        except Exception as exc:
            messagebox.showerror("Template saved", str(exc))

    def _load_user_templates(self):
        """Load *.json templates from a 'templates' folder next to the
        editor (or next to the installed exe), so free templates
        dropped there show up automatically."""
        folders = []
        try:
            folders.append(get_app_dir() / "templates")
        except Exception:
            pass
        try:
            folders.append(Path(sys.executable).parent / "templates")
        except Exception:
            pass
        for folder in folders:
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    name = str(data.get("name") or path.stem)
                    if name not in TEMPLATES:
                        TEMPLATES["📥  " + name] = {
                            "desc": str(data.get("desc", "From templates folder")),
                            "ratio": str(data.get("ratio", "9:16  Vertical (TikTok / Reels)")),
                            "transition": str(data.get("transition", "Fade")),
                            "speed": float(data.get("speed", 1.0)),
                            "filter": str(data.get("filter", "None")),
                            "text_color": str(data.get("text_color", "White")),
                            "text_anim": str(data.get("text_anim", "None")),
                            "clip_anim": str(data.get("clip_anim", "None")),
                            "captions": bool(data.get("captions", False)),
                            "caption_style": str(data.get("caption_style", "Normal")),
                            "ramp": str(data.get("ramp", "None")),
                            "letterbox": bool(data.get("letterbox", False)),
                            "grain": bool(data.get("grain", False)),
                            "border": bool(data.get("border", False)),
                        }
                except Exception:
                    continue

    # ---------- project save / load (CRUD for the timeline) ----------
    def _load_project_settings(self):
        """Put the loaded project's settings back into the panel."""
        self._trans_var.set(self.project.get("transition", "None"))
        self._ratio_var.set(self.project.get("ratio", "16:9  Landscape"))
        self._quality_var.set(self.project.get("quality", "720p"))
        self._caption_style_var.set(self.project.get("caption_style", "Normal"))
        self._caption_size_var.set(self.project.get("caption_size", "Normal"))
        self._caption_pos_var.set(self.project.get("caption_pos", "Bottom"))
        self._caption_anim_var.set(self.project.get("caption_anim", "Pop word-by-word"))
        self._title_style_var.set(self.project.get("title_style", "Flame"))
        self._caption_lang_var.set(self.project.get("caption_lang", "en"))
        self._ai_model_var.set(self.project.get("ai_model", AI_MODELS[0]))
        self._ollama_model_var.set(self.project.get("ollama_model", OLLAMA_MODEL))
        self._ai_key_var.set(self.project.get("openrouter_key", ""))
        self._normalize_var.set(bool(self.project.get("normalize", False)))
        self._auto_memes_var.set(bool(self.project.get("auto_memes", True)))
        self._music_var.set(self.project.get("music", ""))
        self._music_vol_var.set(float(self.project.get("music_vol", 0.5) or 0.5))
        self._music_fade_var.set(bool(self.project.get("music_fade", True)))
        self._ducking_var.set(bool(self.project.get("ducking", False)))
        self._letterbox_var.set(bool(self.project.get("letterbox", False)))
        self._grain_var.set(bool(self.project.get("grain", False)))
        self._captions_var.set(bool(self.project.get("captions", False)))

    def _save_project(self, path=None):
        """Save the whole timeline (clips, trims, settings, music,
        sound effects) to a .json file, so it can be opened again
        later. Returns the path, or None if the user cancelled."""
        self._read_project_settings()
        if not path:
            path = filedialog.asksaveasfilename(
                title="Save this project",
                defaultextension=".json",
                filetypes=[("Project files", "*.json")],
                initialfile="my-project.json")
            if not path:
                return None
        try:
            Path(path).write_text(
                json.dumps(project_to_dict(self.project), indent=2),
                encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Save project", str(exc))
            return None
        self._project_path = str(path)
        self._status_var.set("Project saved: %s" % Path(path).name)
        return str(path)

    def _load_project(self, path=None):
        """Open a saved .json project. Clips whose video file has
        moved or been deleted are left out, and the user is told
        which ones. Returns (project, missing) or (None, []) if
        the user cancelled / the file was not a project."""
        if not path:
            path = filedialog.askopenfilename(
                title="Open a project",
                filetypes=[("Project files", "*.json"), ("All files", "*.*")])
            if not path:
                return None, []
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            project, missing = project_from_dict(data)
        except Exception as exc:
            messagebox.showerror("Open project", str(exc))
            return None, []
        self._read_clip_settings()
        self.project = project
        self._project_path = str(path)
        self._sel = 0 if project["clips"] else None
        self._play_t = 0.0
        self._history = []
        self._h_index = -1
        self._snapshot()
        self._load_project_settings()
        self._refresh_all()
        if self._sel is not None:
            self._load_clip_settings()
        self._show_frame(0.0)
        if missing:
            messagebox.showwarning(
                "Open project",
                "This project was saved with %d clip(s) that are no "
                "longer on this PC, so they were left out:\n\n%s\n\n"
                "Move the videos back, or add them again with "
                "Import." % (len(missing), "\n".join(missing[:5])))
        self._status_var.set("Project opened: %s (%d clip%s)"
                             % (Path(path).name, len(project["clips"]),
                                "s" if len(project["clips"]) != 1 else ""))
        return project, missing

    # ---------- thumbnails ----------
    def _get_thumb(self, path):
        """Small 96x54 PIL thumbnail from the middle of the clip."""
        if path in self._thumbs:
            return self._thumbs[path]
        img = None
        try:
            cap = cv2.VideoCapture(str(path))
            if cap.isOpened():
                frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frames / 2)))
                ok, frame = cap.read()
                if ok and frame is not None:
                    small = cv2.resize(frame, (96, 54),
                                       interpolation=cv2.INTER_AREA)
                    img = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
            cap.release()
        except Exception:
            img = None
        if img is None:
            img = Image.new("RGB", (96, 54), (35, 39, 51))
        self._thumbs[path] = img
        return img

    # ---------- undo / redo (timeline edits) ----------
    def _state(self):
        return (copy.deepcopy(self.project["clips"]),
                self.project["transition"], self.project["ratio"],
                self.project["music"], self.project["music_vol"],
                self.project["captions"])

    def _snapshot(self):
        self._history = self._history[:self._h_index + 1]
        self._history.append(self._state())
        if len(self._history) > 30:
            self._history.pop(0)
        self._h_index = len(self._history) - 1
        self._update_undo_buttons()
        # The project changed — re-render the preview mix in the
        # background, so it is ready before the user presses Play.
        try:
            self._schedule_preview_audio_render()
        except Exception:
            pass

    def _push_history(self):
        """Push the current project onto the undo history. Same as
        _snapshot — the SFX code (Add / Remove / the Auto-Edit meme
        step) calls it by this name, and it was missing, so adding
        a sound raised AttributeError after the sound was already
        appended (the timeline never refreshed)."""
        self._snapshot()

    def _update_undo_buttons(self):
        self._undo_btn.configure(
            state="normal" if self._h_index > 0 else "disabled")
        self._redo_btn.configure(
            state="normal" if self._h_index < len(self._history) - 1 else "disabled")

    def _restore(self):
        clips, trans, ratio, music, vol, caps = self._history[self._h_index]
        self.project["clips"] = copy.deepcopy(clips)
        self.project["transition"] = trans
        self.project["ratio"] = ratio
        self.project["music"] = music
        self.project["music_vol"] = vol
        self.project["captions"] = caps
        self._trans_var.set(trans)
        self._ratio_var.set(ratio)
        self._music_var.set(music)
        self._music_vol_var.set(vol)
        self._captions_var.set(caps)
        self._sel = None
        self._refresh_all()
        self._update_undo_buttons()

    def _undo(self):
        if self._h_index > 0:
            self._read_clip_settings()
            self._h_index -= 1
            self._restore()

    def _redo(self):
        if self._h_index < len(self._history) - 1:
            self._h_index += 1
            self._restore()

    # ---------- clips ----------
    def _default_folder(self):
        try:
            return str(self.master.out_var.get())
        except Exception:
            return str(Path.home() / "Videos" / "GameRecorder")

    def _add_clips(self):
        paths = filedialog.askopenfilenames(
            title="Import video clips", initialdir=self._default_folder(),
            filetypes=[("Videos", "*.mp4 *.mov *.mkv *.avi"), ("All files", "*.*")])
        for p in paths:
            self._add_clip(p)

    def _add_clip(self, path):
        info = probe(path)
        if not info:
            messagebox.showerror("Could not open video", str(path))
            return
        self.project["clips"].append(new_clip(path, info))
        self._sel = len(self.project["clips"]) - 1
        self._load_chapters_for_clip(self._sel)
        self._snapshot()
        self._refresh_all()
        self._load_clip_settings()
        self._show_frame(self._clip_start_time(self._sel))

    def _load_chapters_for_clip(self, ci):
        """Chapters recorded with this clip (a .chapters.json next
        to the video) -> project time, merged into the project.
        Chapters outside the clip's trim are skipped. Splitting or
        reordering clips afterwards does not move chapter times:
        chapters are for the usual one-clip tutorial recording."""
        clips = self.project["clips"]
        if ci < 0 or ci >= len(clips):
            return
        c = clips[ci]
        try:
            from app import load_chapters_json
            raw = load_chapters_json(
                Path(c["path"]).with_suffix(".chapters.json"))
        except Exception:
            raw = []
        if not raw:
            return
        start = float(c.get("start", 0.0))
        end = float(c.get("end", 0.0))
        added = 0
        for ch in raw:
            t = float(ch.get("time", 0.0))
            if t < start or t > end:
                continue
            pt = clip_local_to_project(self.project, ci, t - start)
            self.project.setdefault("chapters", []).append(
                {"time": round(pt, 2),
                 "title": str(ch.get("title", "") or "Chapter")})
            added += 1
        if added:
            self.project["chapters"].sort(key=lambda x: x["time"])
            self._status_var.set(
                "Loaded %d chapter(s) from %s. Click a gold marker on the timeline to rename it."
                % (added, Path(c["path"]).name))

    def _add_meme_video(self, path, label, at_time=None, save_settings=True):
        """Drop a meme video into the project at the playhead (or
        at `at_time` when given, e.g. by Auto-Edit). It becomes a
        normal clip (its own sound comes with it): the clip under
        that time is split there so the meme lands exactly at that
        spot, or it goes at the end when the time is past the last
        clip. A file that cannot be opened shows a short note —
        never a crash, never a popup the user has to dismiss.
        `save_settings=False` (Auto-Edit only): skip reading the
        panel's trim entries first — after Auto-Edit's silence /
        beat cuts replaced the clips, those entries are stale and
        would stretch the selected clip back to its old trim."""
        if save_settings:
            self._read_clip_settings()
        info = probe(path)
        if not info:
            self._status_var.set(
                "That meme video is not ready yet — try again in a moment.")
            return
        clip = new_clip(path, info)
        t = float(at_time if at_time is not None
                  else getattr(self, "_play_t", 0.0) or 0.0)
        idx = len(self.project["clips"])
        acc = 0.0
        for i, c in enumerate(self.project["clips"]):
            d = clip_duration(c)
            if acc <= t < acc + d:
                # At the clip's start: before it, no split needed.
                # Inside it: split there so the meme lands exactly.
                # Too close to an edge to split: right after it.
                if abs(t - acc) < 0.05:
                    idx = i
                elif self._split_clip_at(i, t):
                    idx = i + 1
                else:
                    idx = i + 1
                break
            acc += d
        self.project["clips"].insert(idx, clip)
        self._sel = idx
        self._snapshot()
        self._refresh_all()
        self._load_clip_settings()
        self._show_frame(self._clip_start_time(idx))
        self._status_var.set("Added %s at %.1fs — press Export when you are happy."
                             % (label, self._clip_start_time(idx)))

    def _make_meme_card(self):
        """Render a custom meme card from the box in the Templates
        tab (type any words + pick a style) into meme-videos/ and
        drop it in at the playhead. A missing maker module or a
        failed render shows a short note — never a crash."""
        import re
        text = (self._meme_text_var.get() or "").strip()
        if not text:
            self._status_var.set("Type your meme words first.")
            return
        style = {"Time Card": "timecard", "Neon": "neon", "Pill": "pill",
                 "Red": "red", "White": "white", "Gold": "gold",
                 "Green": "green"}.get(self._meme_style_var.get(), "timecard")
        try:
            from make_meme_videos import render_meme_card
        except Exception:
            self._status_var.set("The meme card maker is not on this PC yet.")
            return
        # Safe filename: lowercase, dashes, no illegal chars; a
        # number when the name is taken.
        base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "meme-card"
        base = base[:40].strip("-") or "meme-card"
        folder = None
        for cand in _meme_video_folders():
            try:
                cand.mkdir(parents=True, exist_ok=True)
                folder = cand
                break
            except Exception:
                continue
        if folder is None:
            self._status_var.set("Could not make a folder for the meme card.")
            return
        out = folder / (base + ".mp4")
        n = 2
        while out.exists():
            out = folder / ("%s-%d.mp4" % (base, n))
            n += 1
        # Time cards get their whoosh when it is in the library;
        # other styles render silent (the video never fails for audio).
        sound = meme_sounds_available().get("whoosh") if style == "timecard" else None
        self._status_var.set("Making your meme card…")
        self.update()
        try:
            ok = render_meme_card(text, style, str(out), sound)
        except Exception:
            ok = False
        if not ok or not out.is_file():
            self._status_var.set("Could not make that meme card — try shorter words.")
            return
        self._build_templates_tab()  # the new card shows in the list
        self._add_meme_video(str(out), text)

    def _refresh_all(self):
        self._preview_key = None
        self._refresh_media()
        self._draw_timeline()
        n = len(self.project["clips"])
        total = project_duration(self.project)
        self._tl_info.configure(
            text="%d clip%s  •  %.1fs total" % (n, "s" if n != 1 else "", total)
            if n else "No clips yet — Import a video")

    def _refresh_media(self):
        for w in self._media_frame.winfo_children():
            w.destroy()
        q = ""
        try:
            q = self._media_search_var.get().strip().lower()
        except Exception:
            q = ""
        for i, c in enumerate(self.project["clips"]):
            name = Path(c["path"]).name
            if q and q not in name.lower():
                continue
            img = self._get_thumb(c["path"])
            photo = ctk.CTkImage(light_image=img, dark_image=img,
                                 size=(96, 54))
            btn = ctk.CTkButton(
                self._media_frame, text="%s  (%.1fs)  \u2713 Added" % (
                    name, clip_duration(c)),
                image=photo, compound="left", anchor="w", height=60,
                fg_color=CC_VIDEO_DIM if i == self._sel else CC_CARD,
                hover_color=CC_BORDER, text_color=CC_TEXT,
                font=("Segoe UI", 11),
                command=lambda idx=i: self._select_clip(idx))
            btn.pack(fill="x", pady=3)

    def _select_clip(self, idx):
        if self._sel is not None and self._sel != idx:
            self._read_clip_settings()
            self._snapshot()
        self._sel = idx
        self._load_clip_settings()
        self._refresh_media()
        self._draw_timeline()
        self._show_frame(self._clip_start_time(idx))

    def _clip_start_time(self, idx):
        return sum(clip_duration(c) for c in self.project["clips"][:idx])

    def _move_clip(self, delta):
        if self._sel is None:
            return
        j = self._sel + delta
        if 0 <= j < len(self.project["clips"]):
            clips = self.project["clips"]
            clips[self._sel], clips[j] = clips[j], clips[self._sel]
            self._sel = j
            self._snapshot()
            self._refresh_all()

    def _remove_clip(self):
        if self._sel is None:
            return
        self._read_clip_settings()
        del self.project["clips"][self._sel]
        self._sel = None
        self._snapshot()
        self._refresh_all()
        self._show_frame(0.0)

    def _duplicate_clip(self):
        """Copy the selected clip and put the copy right after it.
        Trim, speed, filter, text, volume and all other clip
        settings come with it. Sound effects are project-wide
        (their times are absolute), so they are not duplicated."""
        if self._sel is None:
            return
        self._read_clip_settings()
        dup = copy.deepcopy(self.project["clips"][self._sel])
        self.project["clips"].insert(self._sel + 1, dup)
        self._sel = self._sel + 1
        self._snapshot()
        self._refresh_all()
        self._load_clip_settings()
        self._show_frame(self._clip_start_time(self._sel))

    def _split_clip_at(self, i, t):
        """Split clip i at project time t. Returns True if it split
        (False when too close to an edge). Does not snapshot."""
        c = self.project["clips"][i]
        d = clip_duration(c)
        start = self._clip_start_time(i)
        if not (start < t < start + d):
            return False
        # Freeze holds the first frame, so the moving part starts
        # after the freeze; a ramp bends the time.
        base = max(0.1, (c["end"] - c["start"]) / c["speed"])
        u = (t - start - float(c.get("freeze", 0.0) or 0.0)) / base
        u = max(0.0, min(1.0, u))
        ramp = c.get("ramp", "None") or "None"
        frac = _ramp_frac(ramp, u) if ramp != "None" else u
        local = c["start"] + frac * (c["end"] - c["start"])
        if local <= c["start"] + 0.2 or local >= c["end"] - 0.2:
            return False
        second = dict(c)
        second["end"] = c["end"]
        second["start"] = local
        c["end"] = local
        self.project["clips"].insert(i + 1, second)
        return True

    def _split_at_playhead(self):
        total = project_duration(self.project)
        if total <= 0 or self._play_t <= 0 or self._play_t >= total:
            messagebox.showinfo("Split", "Move the playhead inside a clip first.")
            return
        t = self._play_t
        for i, c in enumerate(self.project["clips"]):
            d = clip_duration(c)
            start = self._clip_start_time(i)
            if start < t < start + d:
                if not self._split_clip_at(i, t):
                    messagebox.showinfo("Split", "Too close to the edge of the clip.")
                    return
                self._sel = i + 1
                self._snapshot()
                self._refresh_all()
                self._load_clip_settings()
                self._status_var.set("Split into two clips at %.1fs." % t)
                return

    # ---------- AI tools ----------
    def _remove_silence(self):
        """One tap: cut the dead air out of the selected clip."""
        if self._sel is None:
            messagebox.showinfo("Remove silence", "Select a clip on the timeline first.")
            return
        self._read_clip_settings()
        c = self.project["clips"][self._sel]
        self._status_var.set("Listening for silences…")
        self.update()
        kept, err = detect_silences(c["path"], c["start"], c["end"])
        if err:
            messagebox.showinfo("Remove silence", err)
            self._status_var.set("Ready.")
            return
        if not kept:
            messagebox.showinfo("Remove silence", "The whole clip is silent — nothing to keep.")
            self._status_var.set("Ready.")
            return
        if len(kept) == 1 and abs(kept[0][0] - c["start"]) < 0.05 and abs(kept[0][1] - c["end"]) < 0.05:
            messagebox.showinfo("Remove silence", "No long silences found — the clip is already tight.")
            self._status_var.set("Ready.")
            return
        new_clips = []
        for (s, e) in kept:
            nc = dict(c)
            nc["start"], nc["end"] = s, e
            new_clips.append(nc)
        self.project["clips"][self._sel:self._sel + 1] = new_clips
        self._snapshot()
        self._refresh_all()
        self._load_clip_settings()
        self._status_var.set("Removed silence: %d talking parts left." % len(kept))

    def _split_on_beats(self):
        """Cut the video on the music's beats, like CapCut Beat Sync.
        Uses the project music; if none is set, the selected clip's
        own sound."""
        if not self.project["clips"]:
            messagebox.showinfo("Split on beats", "Add a video clip first.")
            return
        self._read_project_settings()
        music = (self.project.get("music") or "").strip()
        source = music if music and os.path.exists(music) else None
        if source is None:
            if self._sel is None:
                messagebox.showinfo("Split on beats", "Pick background music (Audio tab) or select a clip.")
                return
            source = self.project["clips"][self._sel]["path"]
        self._status_var.set("Finding the beats…")
        self.update()
        beats, err = detect_beats(source)
        if err:
            messagebox.showinfo("Split on beats", err)
            self._status_var.set("Ready.")
            return
        if not beats:
            messagebox.showinfo("Split on beats", "No clear beats found in this music.")
            self._status_var.set("Ready.")
            return
        total = project_duration(self.project)
        made = 0
        # Beats are in the music's time, and the music starts at
        # project time 0 — so a beat is a project time.
        for t in sorted(beats):
            if t <= 0.3 or t >= total - 0.3:
                continue
            for i, c in enumerate(self.project["clips"]):
                d = clip_duration(c)
                start = self._clip_start_time(i)
                if start < t < start + d:
                    if self._split_clip_at(i, t):
                        made += 1
                    break
        if made:
            self._snapshot()
            self._refresh_all()
            self._status_var.set("Split on %d beats." % made)
        else:
            messagebox.showinfo("Split on beats", "The beats all fell too close to clip edges.")
            self._status_var.set("Ready.")

    def _export_gif(self):
        if self._exporting:
            return
        self._read_project_settings()
        if not self.project["clips"]:
            messagebox.showinfo("GIF", "Add a video clip first.")
            return
        first = Path(self.project["clips"][0]["path"])
        out_mp4 = first.with_name(first.stem + "_edited.mp4")
        out_gif = first.with_name(first.stem + "_edited.gif")
        self._exporting = True
        self._bar.set(0)
        self._status_var.set("Exporting video, then making the GIF…")
        threading.Thread(target=self._gif_thread,
                         args=(str(out_mp4), str(out_gif)), daemon=True).start()

    def _gif_thread(self, out_mp4, out_gif):
        def progress(v):
            self.after(0, lambda: self._bar.set(v))

        def status(text):
            self.after(0, lambda: self._status_var.set(text))

        ok, msg = export_project(self.project, out_mp4, progress, status)
        if ok:
            ok, msg = export_gif(out_mp4, out_gif)
        self.after(0, self._gif_done, ok, msg, out_gif)

    def _gif_done(self, ok, msg, out_gif):
        self._exporting = False
        self._bar.set(1.0 if ok else 0.0)
        self._status_var.set(msg)
        if ok:
            messagebox.showinfo("GIF exported", msg + "\n\nSaved next to the first clip.")
            if callable(self.on_exported):
                try:
                    self.on_exported()
                except Exception:
                    pass
        else:
            messagebox.showerror("GIF failed", msg)

    def _save_thumbnail(self):
        """Save the current preview frame as a YouTube thumbnail PNG."""
        if not self.project["clips"]:
            messagebox.showinfo("Thumbnail", "Add a video clip first.")
            return
        frame = self._frame_at(self._play_t)
        if frame is None:
            messagebox.showinfo("Thumbnail", "Move the playhead onto a clip first.")
            return
        first = Path(self.project["clips"][0]["path"])
        out = first.with_name(first.stem + "_thumbnail.png")
        cv2.imwrite(str(out), frame)
        self._status_var.set("Thumbnail saved: %s" % out.name)
        messagebox.showinfo("Thumbnail saved", "Saved as %s\n\nNext to the first clip — use it as your YouTube thumbnail." % out.name)

    # ---------- free AI: Auto-Edit, Highlights, Scene Split, Best Thumbnail ----------
    def _project_words(self):
        """[(project_time, text)] from captions already on hand:
        edited captions, the caption cache, or a .srt next to a
        clip. A word keeps its own time; a .srt line (no word
        timings) keeps its line time and full text. No listening —
        returns [] when nothing is ready yet, so this step costs
        nothing noticeable."""
        out = []
        edits = self.project.get("caption_edits") or {}
        for ci, c in enumerate(self.project["clips"]):
            segs = edits.get(str(ci))
            if not segs:
                key = (str(c["path"]), round(float(c["start"]), 2),
                       round(float(c["end"]), 2))
                segs = self._caption_cache.get(key) or []
            if not segs:
                try:
                    segs, _err = srt_segments_for_clip(c["path"], c["start"], c["end"])
                except Exception:
                    segs = []
            for s in segs:
                words = s.get("words") or []
                if words:
                    for w in words:
                        try:
                            out.append((clip_local_to_project(
                                self.project, ci, float(w["start"])),
                                str(w.get("word", "") or "")))
                        except Exception:
                            continue
                else:
                    try:
                        out.append((clip_local_to_project(
                            self.project, ci, float(s["start"])),
                            str(s.get("text", "") or "")))
                    except Exception:
                        continue
        return sorted(out)

    def _moment_fits(self, t):
        """True when a meme card can go at time t: either inside a
        clip with room on both sides (so the split lands on it),
        or within 0.2 s of a clip boundary (it drops between two
        clips, no split needed — at most 0.2 s off the moment,
        invisible on a 2.5 s card)."""
        acc = 0.0
        for c in self.project["clips"]:
            d = clip_duration(c)
            if abs(t - acc) < 0.2:
                return True
            if acc + 0.3 < t < acc + d - 0.3:
                return True
            acc += d
        return abs(t - acc) < 0.2

    def _auto_add_memes(self):
        """Auto-Edit's meme step: analyse the project (audio energy
        + any transcript already on hand) and drop meme sounds at
        the best moments, plus the matching meme video card at the
        single strongest moment. Returns a short report line ("" when
        nothing was added). Never raises — any failure just skips
        the memes and the rest of Auto-Edit still finishes."""
        try:
            return self._auto_add_memes_inner()
        except Exception:
            return ""

    def _auto_add_memes_inner(self):
        import re
        if not self.project["clips"]:
            return ""
        total = project_duration(self.project)
        if total <= 0:
            return ""
        lib = meme_sounds_available()
        if not lib:
            return ""
        # 1. The project's audio mix, for the energy read. (The
        # same render the preview does — a few seconds at most.)
        tmp = os.path.join(tempfile.gettempdir(), "lgr_meme_mix.wav")
        if render_project_audio(self.project, self.project["clips"], tmp) is None:
            return ""
        times, rms = audio_energy_series(tmp, win=0.25)
        if times is None or len(rms) == 0:
            return ""
        max_rms = float(rms.max()) or 0.0
        if max_rms <= 0:
            return ""
        base = float(rms.mean())
        sd = float(rms.std())
        # 2. Candidate moments: (time, score, kind).
        cands = []
        # 2a. Loud peaks (cheers, laughs, drops, kills).
        try:
            peaks, _err = analyze_highlights(tmp, total, top_n=5)
        except Exception:
            peaks = []
        for (s, _e, _sc) in peaks:
            i = min(len(rms) - 1, max(0, int(s / 0.25)))
            cands.append((float(s), float(rms[i]) / max_rms + 0.2, "loud"))
        # 2b. Silence right after a loud moment (the fail / let-down).
        if sd > 1e-4:
            thresh = base + 0.8 * sd
            for i in range(len(rms) - 2):
                if (rms[i] > thresh and rms[i + 1] < base * 0.5
                        and rms[i + 2] < base * 0.5):
                    cands.append((float(times[i + 1]),
                                  float(rms[i]) / max_rms + 0.1, "sad"))
                    break
        # 2c. Keyword moments from the transcript. ("absurd" is
        # checked first: its phrases are the multi-word surprises,
        # so they win over the single words in "bruh".)
        kw = {"absurd": ("what the", "no way", "oh my god", "oh my",
                         "insane", "crazy", "unbelievable", "bro"),
              "bruh": ("no", "oh no", "wait", "what", "bruh", "huh"),
              "win": ("win", "goal", "yes", "let's go", "lets go",
                      "got it", "easy"),
              "laugh": ("haha", "lol", "funny", "laugh")}
        for (t, text) in self._project_words():
            low = text.lower()
            for kind, phrases in kw.items():
                if any(re.search(r"\b" + re.escape(ph) + r"\b", low)
                       for ph in phrases):
                    i = min(len(rms) - 1, max(0, int(t / 0.25)))
                    cands.append((float(t), float(rms[i]) / max_rms + 0.3, kind))
                    break
        if not cands:
            return ""
        # 3. Best 5, at least 1 s apart (the sounds are short, so
        # moments 1 s apart still play cleanly), in time order.
        cands.sort(key=lambda m: -m[1])
        picked = []
        for m in cands:
            if all(abs(m[0] - p[0]) >= 1.0 for p in picked):
                picked.append(m)
            if len(picked) >= 5:
                break
        picked.sort()
        if not picked:
            return ""
        # 4. The card first, at the single strongest moment — only
        # when it fits cleanly and the card file exists. The moment
        # is snapped to a word boundary (like the beat cuts) so the
        # card never splits a word, then converted to the cumulative
        # time the timeline uses (the mix / transcript times are in
        # the export timeline, which is 0.5 s shorter per join).
        # Sounds after the card shift by exactly how much the
        # export grew when the card went in.
        best = max(picked, key=lambda m: m[1])
        card_added = None
        card_dur = 0.0
        card_file = MEME_CARD_MAP.get(best[2])
        if card_file:
            card_path = meme_video_path(card_file)
            if card_path:
                exp_total_before = project_export_duration(self.project)
                card_t = snap_to_word_boundary(
                    best[0], self._project_word_boundaries())
                card_t_cum = export_to_cumulative(self.project, card_t)
                if self._moment_fits(card_t_cum):
                    info = probe(card_path)
                    if info:
                        label = next((l for l, f in MEME_VIDEOS if f == card_file),
                                     best[2].title())
                        self._add_meme_video(card_path, label, at_time=card_t_cum,
                                             save_settings=False)
                        card_added = (label, card_t)
                        card_dur = (project_export_duration(self.project)
                                    - exp_total_before)
        # 5. The sounds (only ones in the library, with fallback).
        added = []
        entries = []
        for (t, _sc, kind) in picked:
            pref, fall = MEME_SOUND_MAP.get(kind, (None, None))
            stem = pref if pref in lib else fall
            if not stem or stem not in lib:
                continue
            at = t + (card_dur if card_added and t > card_added[1] else 0.0)
            entries.append({"path": lib[stem], "at": float(at), "vol": 1.0})
            added.append((stem.replace("-", " ").title(), at))
        if entries:
            self.project.setdefault("sfx", []).extend(entries)
            self._push_history()
            self._preview_audio_key = None
            self._draw_timeline()
        if not added and not card_added:
            return ""
        line = ""
        if added:
            line = "Auto-Edit added %d meme sound(s): %s." % (
                len(added), ", ".join(
                    "%s at %s" % (name, self._fmt(at)) for name, at in added))
        if card_added:
            line += " Meme card '%s' added at %s." % (
                card_added[0], self._fmt(card_added[1]))
        elif added:
            line += " No meme card fit this time — sounds only."
        return line

    def _ai_auto_edit(self):
        """One tap, the whole smart pass, v2: cut the dead air out of
        every clip (keeping natural pauses under 0.5 s), cut on the
        music's beats with a Fade between the cuts, auto-enhance
        every clip's picture, and turn auto captions on. Free and
        on-device — no account, no upload, no cost."""
        if not self.project["clips"]:
            messagebox.showinfo("AI Auto-Edit", "Add a video clip first.")
            return
        self._read_project_settings()
        # Auto-enhance first, so every piece cut later inherits it.
        for c in self.project["clips"]:
            c["enhance"] = True
        self._status_var.set("AI Auto-Edit: listening for silences…")
        self.update()
        cut = 0
        for i in range(len(self.project["clips"]) - 1, -1, -1):
            c = self.project["clips"][i]
            kept, err = detect_silences(c["path"], c["start"], c["end"],
                                        min_silence=0.5)
            if err or not kept:
                continue
            # Keep natural pauses under 0.5 s (a breath between
            # words stays in the video) and drop tiny fragments.
            kept = tidy_kept_segments(kept, max_gap=0.5, min_len=0.4)
            if not kept:
                continue
            if len(kept) == 1 and abs(kept[0][0] - c["start"]) < 0.05 and abs(kept[0][1] - c["end"]) < 0.05:
                continue
            self.project["clips"][i:i + 1] = [dict(c, start=s, end=e) for (s, e) in kept]
            cut += 1
        beats_made = 0
        music = (self.project.get("music") or "").strip()
        source = music if music and os.path.exists(music) else None
        if source is None and self.project["clips"]:
            source = self.project["clips"][0]["path"]
        if source:
            self._status_var.set("AI Auto-Edit: finding the beats…")
            self.update()
            beats, err = detect_beats(source)
            if not err and beats:
                total = project_duration(self.project)
                # Snap each beat cut to the nearest word boundary
                # (±0.3 s), so no cut lands in the middle of a word.
                bounds = self._project_word_boundaries()
                for t in sorted(beats):
                    if t <= 0.3 or t >= total - 0.3:
                        continue
                    t = snap_to_word_boundary(t, bounds)
                    for i, c in enumerate(self.project["clips"]):
                        d = clip_duration(c)
                        start = self._clip_start_time(i)
                        if start < t < start + d:
                            if self._split_clip_at(i, t):
                                beats_made += 1
                            break
        if beats_made:
            # Smooth cuts: a short Fade between the beat pieces.
            self.project["transition"] = "Fade"
            self._trans_var.set("Fade")
        self.project["captions"] = True
        self._captions_var.set(True)
        # Memes last: sounds (and one card) on the best moments.
        # The switch in the AI card turns this step off; any error
        # here never fails the rest of the edit.
        meme_line = ""
        if bool(self.project.get("auto_memes", True)):
            self._status_var.set("AI Auto-Edit: adding meme moments…")
            self.update()
            meme_line = self._auto_add_memes()
        self._preview_audio_key = None
        self._snapshot()
        self._refresh_all()
        self._load_clip_settings()
        n_enh = len(self.project["clips"])
        self._status_var.set(
            "AI Auto-Edit done: silence cut from %d clip(s), %d beat cuts (Fade), %d clip(s) enhanced, auto captions ON."
            % (cut, beats_made, n_enh)
            + (" " + meme_line if meme_line else ""))
        msg = ("Silence cut from %d clip(s) — natural pauses under 0.5 s kept.\n"
               "%d cuts on the music's beats, with a Fade between them.\n"
               "Auto enhance ON for %d clip(s).\n"
               "Auto captions turned ON.\n"
               % (cut, beats_made, n_enh))
        if meme_line:
            msg += meme_line + "\n"
        msg += "\nPress Export when you are happy."
        messagebox.showinfo("AI Auto-Edit done", msg)

    def _ai_highlights(self):
        """Find the best moments. A small box asks what to look for
        ("goal", "funny", "win") — the transcript is scored for those
        words, plus loud cheers/laughs and fast talking. Leave it
        empty for the loudest moments (the old way). The AI model is
        chosen in the Project panel: a free OpenRouter key, or local
        Ollama. Without either, the offline ranking is used."""
        if not self.project["clips"]:
            messagebox.showinfo("AI Highlights", "Add a video clip first.")
            return
        win = ctk.CTkToplevel(self)
        win.title("AI Highlights — find the best moments")
        win.geometry("460x320")
        win.configure(fg_color=CC_BG)
        ctk.CTkLabel(win, text="What should I look for?\n(e.g. goal, funny, win — leave empty for the loudest moments)",
                     font=("Segoe UI", 12), text_color=CC_TEXT, justify="left").pack(anchor="w", padx=14, pady=10)
        kw_var = tk.StringVar(value="")
        ent = ctk.CTkEntry(win, textvariable=kw_var, fg_color=CC_PANEL, border_color=CC_BORDER)
        ent.pack(fill="x", padx=14, pady=4)
        hint = ("The AI model is chosen in the Project panel (free OpenRouter key, or local Ollama).\n"
                "Without either, the offline ranking is used — no internet needed.")
        ctk.CTkLabel(win, text=hint, font=("Segoe UI", 11), text_color=CC_MUTED,
                     wraplength=420, justify="left").pack(anchor="w", padx=14, pady=6)
        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=10)

        def _go():
            kw = kw_var.get().strip()
            win.destroy()
            self._find_highlights(kw)

        ctk.CTkButton(btns, text="🔍  Find highlights", fg_color=CC_TEAL,
                      hover_color=CC_TEAL_HOVER, command=_go).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Close", fg_color=CC_CARD,
                      hover_color=CC_BORDER, command=win.destroy).pack(side="left")
        ent.focus()

    def _project_transcript(self):
        """The transcript of the whole project in project time:
        ([(proj_start, proj_end, text, words)], [word boundaries]).
        Edited captions first, then a .srt next to the clip, then the
        speech engine (slow — the caller says so in the status)."""
        edits = self.project.get("caption_edits") or {}
        all_segs = []
        bounds = []
        for ci, c in enumerate(self.project["clips"]):
            mine = edits.get(str(ci))
            if mine:
                segs = [dict(s) for s in mine]
            else:
                segs, _err = srt_segments_for_clip(c["path"], c["start"], c["end"])
                if not segs:
                    segs, _err = make_captions(c["path"], c["start"], c["end"],
                                         language=self.project.get("caption_lang", "en"))
            for s in segs:
                ps = clip_local_to_project(self.project, ci, float(s["start"]))
                pe = clip_local_to_project(self.project, ci, float(s["end"]))
                words = s.get("words") or []
                all_segs.append((ps, pe, str(s.get("text", "")), words))
                for w in words:
                    bounds.append(clip_local_to_project(self.project, ci, float(w["start"])))
                    bounds.append(clip_local_to_project(self.project, ci, float(w["end"])))
        all_segs.sort(key=lambda x: x[0])
        return all_segs, sorted(bounds)

    def _project_word_boundaries(self):
        """Word boundaries in project time from captions already
        available (edited, or already generated for the preview).
        No listening — returns [] when nothing is ready yet, and the
        cut simply stays where it is."""
        edits = self.project.get("caption_edits") or {}
        bounds = []
        for ci, c in enumerate(self.project["clips"]):
            segs = edits.get(str(ci))
            if not segs:
                key = (str(c["path"]), round(float(c["start"]), 2), round(float(c["end"]), 2))
                segs = self._caption_cache.get(key) or []
            for s in segs:
                for w in (s.get("words") or []):
                    bounds.append(clip_local_to_project(self.project, ci, float(w["start"])))
                    bounds.append(clip_local_to_project(self.project, ci, float(w["end"])))
        return sorted(bounds)

    def _find_highlights(self, keywords):
        """The real highlight search. keywords \"\" = loudest moments;
        otherwise the transcript is scored for those words. Cuts are
        snapped to the nearest word boundary (±0.3 s) so no cut lands
        mid-word."""
        total = project_duration(self.project)
        self._read_project_settings()
        self._status_var.set("AI Highlights: listening to the whole video…")
        self.update()
        tmp = os.path.join(tempfile.gettempdir(), "lgr_highlights.wav")
        total_audio = render_project_audio(self.project, self.project["clips"], tmp)
        if total_audio is None:
            messagebox.showinfo("AI Highlights",
                                "This video has no sound, so the AI cannot hear the exciting parts.\n"
                                "Add a clip with sound, or background music, and try again.")
            self._status_var.set("Ready.")
            return
        kws = [k.strip() for k in str(keywords or "").replace(",", " ").split() if k.strip()]
        source = "loudest moments"
        found = []  # (start, end, score, note)
        if kws:
            self._status_var.set("AI Highlights: reading the transcript for '%s'…" % ", ".join(kws))
            self.update()
            all_segs, bounds = self._project_transcript()
            if not all_segs:
                messagebox.showinfo("AI Highlights",
                                    "No speech found to search — try the loudest moments instead.\n"
                                    "(Auto captions need the speech engine; the run.bat version has it.)")
                self._status_var.set("Ready.")
                return
            self._highlight_transcript = all_segs
            mode = str(self.project.get("ai_model", AI_MODELS[0]))
            key = str(self.project.get("openrouter_key") or "").strip()
            use_llm = mode.startswith("Ollama") or bool(key)
            llm_found = None
            note = None
            if use_llm:
                self._status_var.set("AI Highlights: asking the %s…" % (
                    "local model — this can take a while on a weak laptop" if mode.startswith("Ollama")
                    else "free AI model"))
                self.update()
                llm_found, note = llm_rank_highlights(
                    self.project, [(s, e, t) for (s, e, t, _w) in all_segs],
                    ", ".join(kws), total)
                if llm_found:
                    source = "local AI model (Ollama)" if mode.startswith("Ollama") else "free AI model"
            if not llm_found:
                if note:
                    # The local model could not be reached: tell the
                    # user how to fix it, then fall back anyway.
                    messagebox.showinfo("Local AI model (Ollama)",
                                        note + "\n\nFalling back to the offline ranking — the highlights below still work.")
                energy = audio_energy_series(tmp)
                ranked = score_keyword_highlights(all_segs, kws, energy=energy, total=total)
                llm_found = [(s, e, sc, txt) for (s, e, sc, txt) in ranked]
                source = "offline ranking"
            # Snap each cut to the nearest word boundary.
            for (s, e, sc, txt) in llm_found:
                s2 = snap_to_word_boundary(s, bounds)
                e2 = snap_to_word_boundary(e, bounds)
                if e2 - s2 < 0.4:
                    s2, e2 = s, e
                found.append((s2, e2, sc, txt))
        else:
            found_raw, err = analyze_highlights(tmp, total)
            if err:
                messagebox.showinfo("AI Highlights", err)
                self._status_var.set("Ready.")
                return
            bounds = self._project_word_boundaries()
            for (s, e, sc) in found_raw:
                s2 = snap_to_word_boundary(s, bounds)
                e2 = snap_to_word_boundary(e, bounds)
                if e2 - s2 < 0.4:
                    s2, e2 = s, e
                found.append((s2, e2, sc, ""))
        if not found:
            messagebox.showinfo("AI Highlights", "No highlights found — try different words, or the loudest moments.")
            self._status_var.set("Ready.")
            return
        self._highlights = [(s, e, sc) for (s, e, sc, _t) in found]
        self._highlight_notes = [t for (_s, _e, _sc, t) in found]
        self._highlight_source = source
        self._draw_timeline()
        self._status_var.set("AI Highlights: %d best moments (%s) marked gold on the timeline." % (len(found), source))
        self._show_highlight_results(found, source)

    def _show_highlight_results(self, found, source):
        """The highlights, ranked best first, with three choices:
        keep only these moments, export each one as its own short
        (Repurpose mode), or close and keep the gold marks."""
        win = ctk.CTkToplevel(self)
        win.title("AI Highlights — %d best moments (%s)" % (len(found), source))
        win.geometry("520x420")
        win.configure(fg_color=CC_BG)
        ctk.CTkLabel(win, text="The best moments (%s):" % source,
                     font=("Segoe UI", 13, "bold"), text_color=CC_TEXT).pack(anchor="w", padx=14, pady=(10, 4))
        frame = ctk.CTkScrollableFrame(win, fg_color=CC_PANEL, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=14, pady=4)
        for i, (s, e, sc, txt) in enumerate(sorted(found, key=lambda x: -x[2])):
            line = "#%d   %s – %s   (score %.0f)" % (i + 1, self._fmt(s), self._fmt(e), sc)
            if txt:
                line += "\n      “%s”" % (txt[:80] + ("…" if len(txt) > 80 else ""))
            ctk.CTkLabel(frame, text=line, font=("Segoe UI", 11),
                         text_color=CC_TEXT, justify="left", anchor="w").pack(anchor="w", padx=8, pady=3)
        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=10)

        def _keep():
            win.destroy()
            self._keep_highlights()

        def _export():
            win.destroy()
            self._export_highlights_as_clips()

        ctk.CTkButton(btns, text="✂  Keep only highlights", fg_color=CC_TEAL,
                      hover_color=CC_TEAL_HOVER, command=_keep).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="📤  Export as separate clips", fg_color=CC_CARD,
                      hover_color=CC_BORDER, command=_export).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Close", fg_color=CC_CARD,
                      hover_color=CC_BORDER, command=win.destroy).pack(side="left")

    def _clip_title(self, ci, segments=None):
        """The auto title for a clip (or a highlight): the most
        striking sentence of its transcript. With an AI model set
        (free OpenRouter key, or local Ollama), the model writes a
        short punchy title instead; without one (or when it fails)
        the best sentence is used. segments: transcript segments
        for this clip, or None to read what is available (edited /
        .srt / preview cache). Returns \"\" when there is no
        transcript."""
        segs = segments
        if segs is None:
            edits = (self.project.get("caption_edits") or {}).get(str(ci))
            if edits:
                segs = [dict(s) for s in edits]
            else:
                c = self.project["clips"][ci]
                segs, _err = srt_segments_for_clip(c["path"], c["start"], c["end"])
                if not segs:
                    key = (str(c["path"]), round(float(c["start"]), 2), round(float(c["end"]), 2))
                    segs = self._caption_cache.get(key) or []
        if not segs:
            return ""
        text = " ".join(str(s.get("text", "")) for s in segs).strip()
        mode = str(self.project.get("ai_model", AI_MODELS[0]))
        key = str(self.project.get("openrouter_key") or "").strip()
        if text and (mode.startswith("Ollama") or key):
            title = llm_title(self.project, text)
            if title:
                return title
        return best_title_for_clip(segs)

    def _title_for_range(self, s, e):
        """Auto title for a highlight range: the transcript inside
        it (from the keyword search), otherwise the captions of the
        clips it overlaps."""
        segs_here = [sg for sg in (self._highlight_transcript or []) if sg[1] > s and sg[0] < e]
        if segs_here:
            return self._clip_title(0, segs_here)
        offs = project_clip_offsets(self.project)
        for ci, c in enumerate(self.project["clips"]):
            d = clip_duration(c)
            if offs[ci] + d <= s or offs[ci] >= e:
                continue
            title = self._clip_title(ci)
            if title:
                return title
        return ""

    def _export_highlights_as_clips(self):
        """Repurpose mode: one long video -> a batch of ranked
        shorts. Each highlight becomes its own MP4 (rank_01, rank_02,
        … — best first) plus a cover frame with an auto title. No new
        AI needed: it reuses the highlights and the export."""
        if not self._highlights:
            messagebox.showinfo("Export highlights", "Find the highlights first (AI Highlights button).")
            return
        if self._exporting:
            return
        self._read_project_settings()
        first = Path(self.project["clips"][0]["path"])
        ranked = sorted(self._highlights, key=lambda x: -x[2])
        self._exporting = True
        self._status_var.set("Exporting %d highlight clips…" % len(ranked))
        threading.Thread(target=self._export_highlights_thread,
                         args=(ranked, str(first.parent)), daemon=True).start()

    def _export_highlights_thread(self, ranked, out_dir):
        done = []
        for i, (s, e, sc) in enumerate(ranked, 1):
            sub = subproject_for_range(self.project, s, e)
            if not sub["clips"]:
                continue
            out = os.path.join(out_dir, "rank_%02d.mp4" % i)
            ok, _msg = export_project(sub, out)
            if ok:
                done.append(out)
        self.after(0, self._export_highlights_done, done)

    def _export_highlights_done(self, done):
        self._exporting = False
        if not done:
            self._status_var.set("Could not export the highlight clips.")
            messagebox.showerror("Export highlights", "The highlight clips could not be exported.")
            return
        # Cover frames, on the main thread (_frame_at reads video).
        out_dir = os.path.dirname(done[0])
        ranked = sorted(self._highlights, key=lambda x: -x[2])
        for i, (s, e, sc) in enumerate(ranked, 1):
            out = os.path.join(out_dir, "rank_%02d.mp4" % i)
            if out not in done:
                continue
            cover = os.path.join(out_dir, "rank_%02d_cover.png" % i)
            try:
                best_frame, best_sc = None, -1.0
                for k in range(6):
                    t = s + (e - s) * (k + 0.5) / 6.0
                    fr = self._frame_at(t)
                    if fr is None:
                        continue
                    fsc = score_frame(fr)
                    if fsc > best_sc:
                        best_sc, best_frame = fsc, fr
                if best_frame is not None:
                    title = self._title_for_range(s, e)
                    if title:
                        best_frame = draw_title(best_frame, title,
                                                self.project.get("title_style", "Flame"))
                    cv2.imwrite(cover, best_frame)
            except Exception:
                pass
        self._status_var.set("Exported %d highlight clip(s): %s"
                             % (len(done), ", ".join(Path(d).name for d in done)))
        messagebox.showinfo("Export highlights",
                            "Exported %d short(s) next to the first clip:\n%s\n\n"
                            "Each one has a cover frame (rank_0N_cover.png) with an auto title."
                            % (len(done), "\n".join(Path(d).name for d in done)))

    def _import_srt(self):
        """Load a .srt file as the captions for the selected clip
        (or the first clip), instead of listening again."""
        if not self.project["clips"]:
            messagebox.showinfo("Import .srt", "Add a video clip first.")
            return
        path = filedialog.askopenfilename(title="Pick a .srt subtitle file",
                                          filetypes=[("Subtitle files", "*.srt"), ("All files", "*.*")])
        if not path:
            return
        ci = self._sel if self._sel is not None else 0
        c = self.project["clips"][ci]
        segs, err = parse_srt(path)
        if err:
            messagebox.showerror("Import .srt", err)
            return
        out = shift_srt_segments(segs, c["start"], c["end"])
        if not out:
            messagebox.showinfo("Import .srt", "That .srt has no captions inside this clip's trim.")
            return
        edits = dict(self.project.get("caption_edits") or {})
        edits[str(ci)] = out
        self.project["caption_edits"] = edits
        self._caption_cache = {}
        self._preview_key = None
        self._snapshot()
        self._refresh_all()
        self._status_var.set("Loaded %d caption(s) from %s for clip %d."
                             % (len(out), Path(path).name, ci + 1))

    def _save_ai_key(self):
        """Save the free OpenRouter key on this PC (or clear it when
        the field is empty)."""
        key = self._ai_key_var.get().strip()
        if save_openrouter_key(key):
            self.project["openrouter_key"] = key
            self._status_var.set("Free AI key saved on this PC — only sent to OpenRouter when you press an AI button."
                                 if key else "Free AI key cleared.")
        else:
            messagebox.showerror("Free AI key", "Could not save the key on this PC.")

    def _clear_ai_key(self):
        self._ai_key_var.set("")
        self._save_ai_key()

    def _keep_highlights(self):
        if not self._highlights:
            return
        total = project_duration(self.project)
        bounds = sorted(set([round(s, 2) for s, _e, _sc in self._highlights] +
                            [round(e, 2) for _s, e, _sc in self._highlights]))
        for t in bounds:
            if t <= 0.3 or t >= total - 0.3:
                continue
            for i, c in enumerate(list(self.project["clips"])):
                d = clip_duration(c)
                start = self._clip_start_time(i)
                if start < t < start + d:
                    self._split_clip_at(i, t)
                    break
        kept = []
        acc = 0.0
        for c in self.project["clips"]:
            d = clip_duration(c)
            s, e = acc, acc + d
            if any(s < he and e > hs for hs, he, _sc in self._highlights):
                kept.append(c)
            acc += d
        n = len(self.project["clips"]) - len(kept)
        self.project["clips"] = kept
        self._highlights = []
        self._preview_audio_key = None
        self._snapshot()
        self._refresh_all()
        self._load_clip_settings()
        self._status_var.set("Kept only the highlights — %d clip piece(s) removed." % n)

    def _ai_scene_split(self):
        """Split the selected clip wherever the picture changes
        (a new scene, a cut, a new camera angle)."""
        if self._sel is None:
            messagebox.showinfo("AI Scene Split", "Select a clip on the timeline first.")
            return
        self._read_clip_settings()
        c = self.project["clips"][self._sel]
        self._status_var.set("AI Scene Split: watching for cuts…")
        self.update()
        times, err = detect_scenes(c["path"])
        if err:
            messagebox.showinfo("AI Scene Split", err)
            self._status_var.set("Ready.")
            return
        start = self._clip_start_time(self._sel)
        d = clip_duration(c)
        orig_start, orig_end = c["start"], c["end"]
        span = max(0.1, orig_end - orig_start)
        made = 0
        for s in times:
            if not (orig_start + 0.3 < s < orig_end - 0.3):
                continue
            t = start + (s - orig_start) / span * d
            if self._split_clip_at(self._sel, t):
                made += 1
                # The split inserts a clip after the selected one;
                # the next scene time belongs to the new clip.
                self._sel += 1
        if made:
            self._snapshot()
            self._refresh_all()
            self._load_clip_settings()
            self._status_var.set("AI Scene Split: %d scene cuts." % made)
        else:
            messagebox.showinfo("AI Scene Split", "No clear scene changes found in this clip.")
            self._status_var.set("Ready.")

    def _ai_best_thumbnail(self):
        """Look at 16 moments in the video and save the best frame
        as your thumbnail: sharp, well lit, and with a face if
        there is one."""
        if not self.project["clips"]:
            messagebox.showinfo("AI Best Thumbnail", "Add a video clip first.")
            return
        total = project_duration(self.project)
        self._status_var.set("AI Best Thumbnail: looking at the video…")
        self.update()
        best_t, best_score, best_frame = 0.0, -1.0, None
        for k in range(16):
            t = total * (k + 0.5) / 16.0
            frame = self._frame_at(t)
            if frame is None:
                continue
            sc = score_frame(frame)
            if sc > best_score:
                best_t, best_score, best_frame = t, sc, frame
        if best_frame is None:
            messagebox.showinfo("AI Best Thumbnail", "Could not read any frame from the video.")
            self._status_var.set("Ready.")
            return
        first = Path(self.project["clips"][0]["path"])
        out = first.with_name(first.stem + "_thumbnail.png")
        title = self._clip_title(0)
        if title:
            best_frame = draw_title(best_frame, title,
                                    self.project.get("title_style", "Flame"))
        cv2.imwrite(str(out), best_frame)
        self._play_t = best_t
        self._show_frame(best_t)
        self._status_var.set("AI Best Thumbnail saved: %s (at %s)." % (out.name, self._fmt(best_t)))
        messagebox.showinfo("AI Best Thumbnail",
                            "Saved as %s\n\nThe best frame is at %s — use it as your YouTube thumbnail."
                            % (out.name, self._fmt(best_t))
                            + ("\n\nTitle on the cover: “%s”" % title if title else ""))

    # ---------- clip settings ----------
    def _on_clip_setting_changed(self, _value=None):
        # A menu/slider/switch in the Video card was changed: apply
        # it to the selected clip right away, so the preview and the
        # timeline total update at once.
        self._read_clip_settings()
        self._refresh_all()

    def _on_project_setting_changed(self, _value=None):
        self._read_project_settings()
        self._refresh_all()

    def _read_clip_settings(self):
        if self._sel is None or self._sel >= len(self.project["clips"]):
            return
        c = self.project["clips"][self._sel]
        try:
            c["start"] = max(0.0, float(self._trim_start.get()))
        except Exception:
            pass
        try:
            c["end"] = max(c["start"] + 0.1, float(self._trim_end.get()))
        except Exception:
            pass
        c["speed"] = _parse_speed(self._speed_var.get())
        c["filter"] = self._filter_var.get()
        c["text"] = self._text_var.get()
        c["text_pos"] = self._text_pos_var.get()
        c["text_color"] = self._text_color_var.get()
        c["text_anim"] = self._text_anim_var.get()
        c["text_style"] = self._text_style_var.get()
        c["clip_anim"] = self._clip_anim_var.get()
        c["ramp"] = self._ramp_var.get()
        c["reverse"] = bool(self._reverse_var.get())
        c["stabilize"] = bool(self._stabilize_var.get())
        c["denoise"] = bool(self._denoise_var.get())
        c["border"] = bool(self._border_var.get())
        c["freeze"] = _parse_freeze(self._freeze_var.get())
        c["volume"] = max(0.0, min(1.5, float(self._volume_var.get())))
        c["sticker"] = self._sticker_var.get()
        c["sticker_pos"] = self._sticker_pos_var.get()
        c["mute"] = bool(self._mute_var.get())
        c["enhance"] = bool(self._enhance_var.get())
        c["fade_in"] = _parse_freeze(self._fade_in_var.get())
        c["fade_out"] = _parse_freeze(self._fade_out_var.get())
        self._settings_version += 1
        self._preview_key = None

    def _load_clip_settings(self):
        if self._sel is None or self._sel >= len(self.project["clips"]):
            return
        c = self.project["clips"][self._sel]
        self._trim_start.set("%.2f" % c["start"])
        self._trim_end.set("%.2f" % c["end"])
        self._speed_var.set("%.1fx" % c["speed"] if c["speed"] != 1.0 else "1x")
        self._filter_var.set(c.get("filter", "None"))
        self._text_var.set(c.get("text", ""))
        self._text_pos_var.set(c.get("text_pos", "Bottom"))
        self._text_color_var.set(c.get("text_color", "White"))
        self._text_anim_var.set(c.get("text_anim", "None"))
        self._text_style_var.set(c.get("text_style", "Normal"))
        self._clip_anim_var.set(c.get("clip_anim", "None"))
        self._ramp_var.set(c.get("ramp", "None"))
        self._reverse_var.set(bool(c.get("reverse", False)))
        self._stabilize_var.set(bool(c.get("stabilize", False)))
        self._denoise_var.set(bool(c.get("denoise", False)))
        self._border_var.set(bool(c.get("border", False)))
        self._freeze_var.set("%.1fs" % float(c.get("freeze", 0.0) or 0.0)
                             if float(c.get("freeze", 0.0) or 0.0) else "0s")
        self._volume_var.set(float(c.get("volume", 1.0) or 1.0))
        self._sticker_var.set(c.get("sticker", "None"))
        self._sticker_pos_var.set(c.get("sticker_pos", "Top Right"))
        self._mute_var.set(bool(c.get("mute", False)))
        self._enhance_var.set(bool(c.get("enhance", False)))
        self._fade_in_var.set("%.1fs" % float(c.get("fade_in", 0.0) or 0.0)
                              if float(c.get("fade_in", 0.0) or 0.0) else "0s")
        self._fade_out_var.set("%.1fs" % float(c.get("fade_out", 0.0) or 0.0)
                               if float(c.get("fade_out", 0.0) or 0.0) else "0s")

    def _set_trim(self, which):
        if self._sel is None:
            return
        start = self._clip_start_time(self._sel)
        c = self.project["clips"][self._sel]
        base = max(0.1, (c["end"] - c["start"]) / c["speed"])
        u = (self._play_t - start - float(c.get("freeze", 0.0) or 0.0)) / base
        u = max(0.0, min(1.0, u))
        ramp = c.get("ramp", "None") or "None"
        frac = _ramp_frac(ramp, u) if ramp != "None" else u
        local = c["start"] + frac * (c["end"] - c["start"])
        local = max(c["start"], min(c["end"], local))
        if which == "start":
            self._trim_start.set("%.2f" % local)
        else:
            self._trim_end.set("%.2f" % local)
        self._read_clip_settings()
        self._snapshot()
        self._refresh_all()

    def _on_trim_typed(self, _event=None):
        """The user typed an exact trim time: apply it (clamped to
        the clip and to the video's real length) and show it back
        with 2 decimals."""
        if self._sel is None:
            return
        self._read_clip_settings()
        c = self.project["clips"][self._sel]
        try:
            dur = float((probe(c["path"]) or {}).get("duration", 0) or 0)
        except Exception:
            dur = 0.0
        if dur > 0:
            c["start"] = max(0.0, min(c["start"], dur - 0.1))
            c["end"] = max(c["start"] + 0.1, min(c["end"], dur))
        self._snapshot()
        self._refresh_all()
        self._load_clip_settings()

    def _playhead_local_time(self, i, t):
        """Source time of the playhead inside clip i (same maths as
        _split_clip_at: freeze first, then the ramp bend)."""
        c = self.project["clips"][i]
        start = self._clip_start_time(i)
        base = max(0.1, (c["end"] - c["start"]) / c["speed"])
        u = (t - start - float(c.get("freeze", 0.0) or 0.0)) / base
        u = max(0.0, min(1.0, u))
        ramp = c.get("ramp", "None") or "None"
        frac = _ramp_frac(ramp, u) if ramp != "None" else u
        return c["start"] + frac * (c["end"] - c["start"])

    def _trim_to_playhead(self, keep):
        """Cut the selected clip at the playhead: keep the part
        before it (trim the end) or after it (trim the start)."""
        if self._sel is None:
            messagebox.showinfo("Trim to playhead", "Select a clip on the timeline first.")
            return
        total = project_duration(self.project)
        if total <= 0 or self._play_t <= 0 or self._play_t >= total:
            messagebox.showinfo("Trim to playhead", "Move the playhead inside a clip first.")
            return
        t = self._play_t
        for i, c in enumerate(self.project["clips"]):
            d = clip_duration(c)
            start = self._clip_start_time(i)
            if start < t < start + d:
                local = self._playhead_local_time(i, t)
                if keep == "before":
                    if local <= c["start"] + 0.2:
                        messagebox.showinfo("Trim to playhead", "Too close to the start of the clip.")
                        return
                    c["end"] = local
                    self._status_var.set("Trimmed: kept %.2fs – %.2fs." % (c["start"], c["end"]))
                else:
                    if local >= c["end"] - 0.2:
                        messagebox.showinfo("Trim to playhead", "Too close to the end of the clip.")
                        return
                    c["start"] = local
                    self._status_var.set("Trimmed: kept %.2fs – %.2fs." % (c["start"], c["end"]))
                self._sel = i
                self._preview_audio_key = None
                self._snapshot()
                self._refresh_all()
                self._load_clip_settings()
                return

    def _pick_music(self):
        p = filedialog.askopenfilename(
            title="Background music", initialdir=self._default_folder(),
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.ogg"), ("All files", "*.*")])
        if p:
            self._music_var.set(p)

    def _waveform_for(self, c):
        """Cached waveform for one clip (computed once, then reused
        every time the timeline redraws)."""
        key = (str(c["path"]), round(float(c["start"]), 2),
               round(float(c["end"]), 2))
        if key not in self._waveform_cache:
            self._waveform_cache[key] = clip_waveform(
                c["path"], c["start"], c["end"], n=48)
        return self._waveform_cache[key]

    def _captions_for_clip(self, ci, clip):
        """Caption segments for the preview: edited words first,
        otherwise the auto captions (generated once, in the
        background, so the preview never freezes). Returns [] when
        there are none (yet)."""
        edits = (self.project.get("caption_edits") or {}).get(str(ci))
        if edits:
            return [dict(s) for s in edits]
        key = (str(clip["path"]), round(float(clip["start"]), 2),
               round(float(clip["end"]), 2))
        if key in self._caption_cache:
            return self._caption_cache[key]
        if key not in self._caption_generating:
            self._caption_generating.add(key)

            def _gen():
                # A .srt next to the video wins over listening again.
                segs, _err = srt_segments_for_clip(clip["path"], clip["start"], clip["end"])
                if not segs:
                    segs, _err = make_captions(clip["path"], clip["start"],
                                               clip["end"],
                                               language=self.project.get("caption_lang", "en"))
                self._caption_cache[key] = segs
                self._caption_generating.discard(key)
                self._preview_key = None  # show the captions next frame

            threading.Thread(target=_gen, daemon=True).start()
        return []

    def _edit_captions(self):
        """Edit the auto captions' words: generate them (once per
        clip), show each line as an editable row, save the words
        back into the project so the export (and the preview) use
        them."""
        if not self.project["clips"]:
            messagebox.showinfo("Edit captions", "Add a video clip first.")
            return
        self._status_var.set("Listening for captions to edit…")
        self.update()
        edits = self.project.get("caption_edits") or {}
        all_segs = []  # (clip_index, seg_index, start, end, text)
        for ci, c in enumerate(self.project["clips"]):
            mine = edits.get(str(ci))
            if mine:
                segs = [dict(s) for s in mine]
            else:
                # A .srt next to the video wins over listening again.
                segs, err = srt_segments_for_clip(c["path"], c["start"], c["end"])
                if not segs:
                    segs, err = make_captions(c["path"], c["start"], c["end"],
                                            language=self.project.get("caption_lang", "en"))
                if err:
                    continue
            for si, s in enumerate(segs):
                all_segs.append((ci, si, float(s["start"]), float(s["end"]),
                                 str(s.get("text", ""))))
        if not all_segs:
            messagebox.showinfo("Edit captions",
                                "No speech found in these clips — nothing to edit.\n"
                                "Add a clip with talking and try again.")
            self._status_var.set("Ready.")
            return
        win = ctk.CTkToplevel(self)
        win.title("Edit captions")
        win.geometry("560x520")
        win.configure(fg_color=CC_BG)
        ctk.CTkLabel(win, text="Edit the words, then press Save.\nThe export (and the preview) will use your words.",
                     font=("Segoe UI", 12), text_color=CC_TEXT,
                     justify="left").pack(anchor="w", padx=14, pady=10)
        frame = ctk.CTkScrollableFrame(win, fg_color=CC_PANEL, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=14, pady=4)
        entries = []  # (clip_index, seg_index, start, end, entry)
        for (ci, si, s, e, text) in all_segs:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="Clip %d · %s – %s" % (ci + 1, self._fmt(s), self._fmt(e)),
                         font=("Segoe UI", 11), text_color=CC_MUTED, width=150,
                         anchor="w").pack(side="left")
            ent = ctk.CTkEntry(row, fg_color=CC_BG, border_color=CC_BORDER)
            ent.insert(0, text)
            ent.pack(side="left", fill="x", expand=True, padx=(6, 0))
            entries.append((ci, si, s, e, ent))
        self._caption_edit_win = win
        self._caption_edit_entries = entries
        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=10)

        def _save():
            new_edits = {}
            for (ci, si, s, e, ent) in entries:
                text = ent.get().strip()
                if not text:
                    continue  # empty line = delete this caption
                words = None
                mine = edits.get(str(ci))
                if mine and si < len(mine) and text == str(mine[si].get("text", "")).strip():
                    words = mine[si].get("words") or []  # unchanged: keep timings
                if words is None:
                    words = _redistribute_words(text, s, e)
                new_edits.setdefault(str(ci), []).append(
                    {"start": s, "end": e, "text": text, "words": words})
            self.project["caption_edits"] = new_edits
            self._caption_cache = {}
            self._preview_key = None
            self._snapshot()
            self._refresh_all()
            self._status_var.set("Captions saved — the export will use your words.")
            win.destroy()

        def _reset():
            self.project["caption_edits"] = {}
            self._caption_cache = {}
            self._preview_key = None
            self._snapshot()
            self._refresh_all()
            self._status_var.set("Caption edits cleared — auto captions will be used again.")
            win.destroy()

        ctk.CTkButton(btns, text="💾  Save captions", fg_color=CC_SKY,
                      hover_color=CC_SKY_HOVER, text_color="#0F1218",
                      command=_save).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(btns, text="↩  Reset to auto", fg_color=CC_CARD,
                      hover_color=CC_BORDER, command=_reset).pack(side="left", expand=True, fill="x", padx=(4, 0))
        self._status_var.set("Ready.")

    # ---------- preview ----------
    def _frame_at(self, t):
        """Render the preview frame at project time t (seconds)."""
        total = project_duration(self.project)
        if total <= 0 or not self.project["clips"]:
            return None
        t = max(0.0, min(t, total - 0.01))
        acc = 0.0
        for ci, c in enumerate(self.project["clips"]):
            d = clip_duration(c)
            if acc <= t < acc + d or (c is self.project["clips"][-1]):
                t_in_clip = t - acc
                freeze = float(c.get("freeze", 0.0) or 0.0)
                base = max(0.1, (c["end"] - c["start"]) / c["speed"])
                u = max(0.0, min(1.0, (t_in_clip - freeze) / base))
                ramp = c.get("ramp", "None") or "None"
                frac = _ramp_frac(ramp, u) if ramp != "None" else u
                local = c["start"] + frac * (c["end"] - c["start"])
                if c.get("reverse"):
                    local = c["end"] - (local - c["start"])
                cap = cv2.VideoCapture(str(c["path"]))
                cap.set(cv2.CAP_PROP_POS_MSEC, local * 1000.0)
                ok, frame = cap.read()
                cap.release()
                if not ok or frame is None:
                    return None
                frame = apply_clip_anim(frame, c.get("clip_anim", "None"),
                                        t_in_clip, d, int(t_in_clip * 30))
                frame = _apply_clip_filter(frame, c.get("filter", "None"), c)
                if c.get("text"):
                    frame = draw_text(frame, c["text"], c.get("text_pos", "Bottom"),
                                      c.get("text_color", "White"),
                                      anim=c.get("text_anim", "None"), t=t_in_clip,
                                      style=c.get("text_style", "Normal"))
                if c.get("sticker") and c.get("sticker") != "None":
                    frame = draw_sticker(frame, c["sticker"],
                                         c.get("sticker_pos", "Top Right"))
                if c.get("border"):
                    frame = _photo_border(frame)
                # Auto captions in the preview (same words, same
                # animation as the export). Reversed clips are
                # skipped — their captions were made from forward
                # speech and would be wrong.
                if self._captions_var.get() and not c.get("reverse"):
                    src_t = local - c["start"]
                    for seg in self._captions_for_clip(ci, c):
                        if seg["start"] <= src_t <= seg["end"]:
                            frame = draw_caption_words(
                                frame, seg, src_t,
                                self._caption_style_var.get() or "Normal",
                                scale_mult=_CAPTION_SIZE_MULT.get(
                                    self._caption_size_var.get(), 1.0),
                                pos=self._caption_pos_var.get(),
                                anim=self._caption_anim_var.get())
                            break
                out_w, out_h = RATIOS.get(self._ratio_var.get(), (1280, 720))
                if self._ratio_var.get() == "9:16  Smart reframe (follow face)":
                    frame = cv2.resize(self._reframer.crop(frame), (out_w, out_h),
                                       interpolation=cv2.INTER_AREA)
                else:
                    frame = fit_frame(frame, out_w, out_h, blur=bool(self.project.get("bg_blur", True)))
                if self._letterbox_var.get():
                    frame = _letterbox(frame)
                if self._grain_var.get():
                    frame = _add_grain(frame, int(t_in_clip * 30))
                return frame
            acc += d
        return None

    def _on_window_resize(self, event):
        """Responsiveness: the window itself was resized. Flex the
        panels, grow/shrink the timeline, and re-wrap labels.
        (Configure events from child widgets also reach this
        binding through the toplevel bindtag, so only the window's
        own resize counts.)"""
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
        # below ~240 px, so no button is ever cut off).
        if w < 1250:
            left_w, right_w = 240, 232
        elif w < 1600:
            left_w, right_w = 280, 268
        else:
            left_w, right_w = 300, 300
        if (left_w, right_w) != getattr(self, "_panel_w", None):
            self._panel_w = (left_w, right_w)
            self._panel.configure(width=left_w)
            self._right_panel.configure(width=right_w)
            # The panels only take their new width after the
            # geometry manager runs — measure the labels after
            # that, or the old (wider) widths are used and
            # nothing gets re-wrapped.
            self.update_idletasks()
        # Timeline height scales with the window (total ~160 px
        # at the minimum: head row + canvas + padding).
        canvas_h = max(100, min(200, int(h * 0.155)))
        if canvas_h != getattr(self, "_tl_h", None):
            self._tl_h = canvas_h
            self._tl.configure(height=canvas_h)
        # The AI strip is a secondary tool: on a short window it
        # must not squeeze the preview to a strip, so it hides
        # itself below 760 px and comes back when the window grows
        # again. The user can still show it with Magic Tools in
        # the pill — a strip they showed on purpose is never
        # auto-hidden, and one they hid is never auto-restored.
        if h < 760 and self._ai_strip.winfo_ismapped() and not self._ai_manual:
            self._ai_strip.pack_forget()
            self._ai_auto_hidden = True
        elif h >= 760 and self._ai_auto_hidden and not self._ai_manual:
            self._ai_strip.pack(fill="x", pady=(6, 0), before=self._transport)
            self._ai_auto_hidden = False
        # Wrapped labels: shrink their wraplength to the panel
        # they are in, restore it when the panel grows again.
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

    def _on_toolbar_resize(self, event):
        """The toolbar got wider/narrower: reflow its buttons
        into as many rows as fit. (CTkFrame.bind routes to the
        frame's inner canvas, so the event's widget is the canvas,
        not the frame — the width is what matters, and a
        Configure from a button inside the toolbar never reaches
        this binding anyway.)"""
        if event.width == self._toolbar_w or event.width < 50:
            return
        self._toolbar_w = event.width
        if self._toolbar_after:
            self.after_cancel(self._toolbar_after)
        self._toolbar_after = self.after(80, self._reflow_toolbar)

    def _reflow_toolbar(self):
        """Grid the toolbar buttons into as many rows as fit in
        the toolbar's width (grid can move a widget between rows;
        pack cannot move it between parents)."""
        self._toolbar_after = None
        if self._toolbar.winfo_width() < 50:
            return
        avail = max(120, self._toolbar.winfo_width())
        widths = [b.winfo_reqwidth() + 4 for b in self._toolbar_btns]
        rows, cur, cur_w = [], [], 0
        for b, w in zip(self._toolbar_btns, widths):
            if cur and cur_w + w > avail:
                rows.append(cur)
                cur, cur_w = [], 0
            cur.append(b)
            cur_w += w
        if cur:
            rows.append(cur)
        for b in self._toolbar_btns:
            b.grid_forget()
        for r, row in enumerate(rows):
            for c, b in enumerate(row):
                b.grid(row=r, column=c, padx=2, pady=2, sticky="w")

    def _on_preview_resize(self, event):
        """Re-render the preview when its box changes size (the image
        is fit to the box, so a resize needs a fresh render)."""
        if event.width < 50 or event.height < 50:
            return
        if (event.width, event.height) == getattr(self, "_preview_size", None):
            return
        self._preview_size = (event.width, event.height)
        if getattr(self, "_preview_resize_after", None):
            self.after_cancel(self._preview_resize_after)
        self._preview_resize_after = self.after(120, self._rerender_preview)

    def _rerender_preview(self):
        self._preview_resize_after = None
        if not getattr(self, "project", None) or not self.project.get("clips"):
            return
        # (No cache invalidation: _show_frame re-scales the cached
        # frame to the new box.)
        self._show_frame(getattr(self, "_play_t", 0.0))

    def _show_frame(self, t):
        self._play_t = t
        total = project_duration(self.project)
        self._time_var.set("%s / %s" % (self._fmt(t), self._fmt(total)))
        if total > 0:
            self._seek_var.set(1000.0 * t / total)
        self._move_playhead()
        # Preview cache: the same moment with the same settings is
        # the same picture — do not read the video file again.
        key = (round(t, 2), self._settings_version, self._ratio_var.get())
        if key == self._preview_key and self._preview_frame is not None:
            frame = self._preview_frame
        else:
            frame = self._frame_at(t)
            if frame is None:
                return
            self._preview_key = key
            self._preview_frame = frame
        h, w = frame.shape[:2]
        # Fit the image into the space the preview will actually get:
        # the centre's height minus the fixed rows (pill, toolbar,
        # trim, AI strip, transport).  Using the label's own height
        # feeds back - a tall image makes the label tall, which makes
        # the next image tall, and the transport gets pushed off the
        # bottom of the window.
        _centre = self._preview.master
        # Requested heights, not allocated ones: when the preview is
        # too tall the transport gets squeezed to 41 px, and using
        # that squeezed height here would keep the preview too tall
        # forever (a stable but wrong equilibrium).
        _fixed = sum(ch.winfo_reqheight() + 4 for ch in _centre.winfo_children()
                     if ch is not self._preview)
        pw = max(320, self._preview.winfo_width() - 20)
        ph = max(150, _centre.winfo_height() - _fixed - 16)
        scale = min(pw / w, ph / h)
        small = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))),
                           interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        self._preview_photo = ctk.CTkImage(light_image=img, dark_image=img,
                                           size=(img.width, img.height))
        self._preview.configure(image=self._preview_photo, text="")

    @staticmethod
    def _fmt(t):
        m, s = divmod(int(t), 60)
        return "%d:%02d" % (m, s)

    def _on_close(self):
        self._stop_preview_audio()
        self.destroy()

    def _on_sound_toggle(self):
        if not self._sound_var.get():
            self._stop_preview_audio()

    def _preview_audio_cache_key(self):
        clips = self.project["clips"]
        return (self._settings_version, len(clips),
                tuple((c["path"], c["start"], c["end"], c.get("speed", 1.0),
                       bool(c.get("mute")), float(c.get("volume", 1.0) or 1.0),
                       float(c.get("fade_in", 0.0) or 0.0),
                       float(c.get("fade_out", 0.0) or 0.0))
                      for c in clips),
                self.project.get("music"), self.project.get("music_vol"),
                bool(self.project.get("music_fade", True)),
                bool(self.project.get("ducking", False)),
                bool(self.project.get("normalize", False)),
                tuple((s.get("path"), round(float(s.get("at", 0)), 2))
                      for s in self.project.get("sfx") or []))

    def _play_preview_audio_now(self):
        """Play the cached mix from the playhead. Returns True if
        sound started."""
        if not self._sound_var.get() or not self._preview_audio_path:
            return False
        if _play_wav_file(self._preview_audio_path, offset=self._play_t):
            self._status_var.set("Playing with sound.")
            return True
        self._status_var.set("Sound did not play — press 'Test sound' in the Audio tab.")
        return False

    def _ensure_preview_audio_render(self, key):
        """Render the audio mix in the background (once at a time).
        The `gen` number drops stale renders when the project
        changes again before the render finishes. The worker only
        leaves a plain result behind — the main thread picks it up
        by polling, because Tk calls (after) from a worker thread
        fail with 'main thread is not in main loop'."""
        if self._audio_rendering:
            return
        self._audio_rendering = True
        self._audio_render_gen += 1
        gen = self._audio_render_gen
        self._audio_render_result = None

        def _render():
            tmp = os.path.join(tempfile.gettempdir(), "lgr_preview_audio.wav")
            total = render_project_audio(self.project, self.project["clips"], tmp)
            self._audio_render_result = (total, tmp, key, gen)

        threading.Thread(target=_render, daemon=True).start()
        try:
            self.after(100, self._check_preview_audio_ready)
        except Exception:
            pass

    def _check_preview_audio_ready(self):
        """Main-thread poll: has the background mix render finished?"""
        if not self._audio_rendering:
            return
        if self._audio_render_result is None:
            try:
                self.after(100, self._check_preview_audio_ready)
            except Exception:
                pass
            return
        total, tmp, key, gen = self._audio_render_result
        self._audio_render_result = None
        self._on_preview_audio_ready(total, tmp, key, gen)

    def _on_preview_audio_ready(self, total, tmp, key, gen):
        """The background mix render finished."""
        if gen != self._audio_render_gen:
            return  # a newer render replaced this one
        self._audio_rendering = False
        try:
            if total is None:
                self._preview_audio_path = None
                self._preview_audio_key = None
                self._status_var.set("No audio in this project to play.")
            else:
                self._preview_audio_path = tmp
                self._preview_audio_key = key
            if self._playing and self._play_after_render:
                # Play was pressed while the mix was rendering: start
                # the video AND the sound together, so the sound is
                # never left behind by a short clip.
                self._play_after_render = False
                if total is not None:
                    self._play_preview_audio_now()
                self.after(50, self._play_tick)
            elif self._playing:
                # The video is already playing — join the sound in
                # from the current playhead.
                if total is not None:
                    self._play_preview_audio_now()
            elif total is not None:
                self._status_var.set("Sound ready — press Play to hear it.")
        except Exception:
            pass

    def _schedule_preview_audio_render(self):
        """Re-render the mix in the background 0.6 s after the last
        edit, so it is usually ready before the user presses Play."""
        self._preview_audio_key = None
        if not self.project["clips"]:
            return
        try:
            self.after_cancel(self._audio_render_after_id)
        except Exception:
            pass
        try:
            self._audio_render_after_id = self.after(600, self._eager_render_audio)
        except Exception:
            pass

    def _eager_render_audio(self):
        if self._playing or self._audio_rendering:
            return
        try:
            key = self._preview_audio_cache_key()
            if key == self._preview_audio_key and self._preview_audio_path:
                return
            self._ensure_preview_audio_render(key)
        except Exception:
            pass

    def _begin_playback(self):
        """Start the preview. If the audio mix is ready, video and
        sound start together. If not, the mix renders first and the
        video waits for it — a short clip must not finish before
        its sound is ready."""
        try:
            key = self._preview_audio_cache_key()
        except Exception:
            key = None
        if key is not None and key == self._preview_audio_key and self._preview_audio_path:
            self._play_preview_audio_now()
            self.after(50, self._play_tick)
            return
        if not self._sound_var.get():
            self.after(50, self._play_tick)
            return
        self._status_var.set("Preparing sound…")
        self._play_after_render = True
        self._ensure_preview_audio_render(key)

    def _test_sound(self):
        """One-tap sound check: plays the Ding and says if it worked.
        Use this first if you hear nothing in the editor."""
        lib = dict(sfx_library())
        path = lib.get("Ding")
        if not path:
            self._status_var.set("Test sound: the sounds folder is missing — reinstall the update.")
            messagebox.showinfo("Test sound",
                                "The sounds folder is missing from the install.\n"
                                "Reinstall the update and try again.")
            return
        if _play_wav_file(path):
            self._status_var.set("Test sound: playing the Ding — you should hear it now.")
        else:
            self._status_var.set("Test sound FAILED — no sound player works on this PC.")
            messagebox.showerror(
                "Test sound",
                "The editor could not play any sound.\n\n"
                "It tried the built-in player and ffplay (bundled with FFmpeg).\n"
                "Check that your speakers or headphones are on and the volume\n"
                "is up, then open the setup window and press 'Get FFmpeg\n"
                "(sound)' and try again.")

    def _stop_preview_audio(self):
        _stop_wav()

    def _toggle_play(self):
        if not self.project["clips"]:
            return
        self._playing = not self._playing
        self._play_btn._glyph.configure(text="⏸" if self._playing else "▶")
        if self._playing:
            self._begin_playback()
        else:
            self._play_after_render = False
            self._stop_preview_audio()

    def _play_tick(self):
        if not self._playing:
            return
        total = project_duration(self.project)
        self._play_t += 0.05
        if self._play_t >= total:
            self._play_t = total
            self._playing = False
            self._play_btn._glyph.configure(text="▶")
            self._stop_preview_audio()
        self._show_frame(self._play_t)
        if self._playing:
            self.after(50, self._play_tick)

    def _on_seek(self, value):
        total = project_duration(self.project)
        if total <= 0:
            return
        self._playing = False
        self._play_after_render = False
        self._play_btn._glyph.configure(text="▶")
        self._stop_preview_audio()
        self._show_frame(float(value) / 1000.0 * total)

    # ---------- timeline (CapCut: video track, text track, audio track) ----------
    def _tl_geom(self):
        """(label_x, px_per_sec, width) for the timeline canvas."""
        w = max(200, self._tl.winfo_width())
        total = project_duration(self.project)
        pps = (w - 90) / total if total > 0 else 0
        return 70, pps, w

    def _draw_timeline(self):
        try:
            self._tl.delete("all")
        except Exception:
            return
        self._playhead_id = None
        label_x, pps, w = self._tl_geom()
        total = project_duration(self.project)
        if total <= 0 or pps <= 0:
            self._tl.create_text(90, 66, anchor="w", fill=CC_MUTED,
                                 font=("Segoe UI", 11),
                                 text="Import a video — it will appear here as a clip")
            return
        # Ruler
        step = 1 if total <= 30 else (5 if total <= 120 else 10)
        t = 0.0
        while t <= total:
            x = label_x + t * pps
            self._tl.create_line(x, 0, x, 8, fill=CC_BORDER)
            self._tl.create_text(x + 2, 14, anchor="w", fill=CC_MUTED,
                                 font=("Segoe UI", 8), text=self._fmt(t))
            t += step
        # Track labels (icon + name, at the left of each row)
        self._tl.create_text(8, 32, anchor="w", fill=CC_MUTED,
                             font=("Segoe UI", 9), text="🔤 Text")
        self._tl.create_text(8, 64, anchor="w", fill=CC_MUTED,
                             font=("Segoe UI", 9), text="🎬 Video")
        self._tl.create_text(8, 96, anchor="w", fill=CC_MUTED,
                             font=("Segoe UI", 9), text="🔊 Audio")
        self._tl.create_text(8, 116, anchor="w", fill=CC_MUTED,
                             font=("Segoe UI", 9), text="♪ Music")
        acc = 0.0
        for i, c in enumerate(self.project["clips"]):
            d = clip_duration(c)
            x0 = label_x + acc * pps
            x1 = label_x + (acc + d) * pps
            sel = (i == self._sel)
            fill = CC_VIDEO if sel else CC_VIDEO_DIM
            self._tl.create_rectangle(x0, 44, x1, 84, fill=fill, outline="#ffffff" if sel else "",
                                      width=2 if sel else 0)
            # Thumbnail at the left of the block
            if x1 - x0 > 60:
                tk_img = self._thumb_tk.get(c["path"])
                if tk_img is None:
                    tk_img = ImageTk.PhotoImage(self._get_thumb(c["path"]))
                    self._thumb_tk[c["path"]] = tk_img
                self._tl.create_image(x0 + 2, 64, anchor="w", image=tk_img)
            if x1 - x0 > 110:
                name = Path(c["path"]).name
                if len(name) > 18:
                    name = name[:17] + "…"
                self._tl.create_text(x0 + 100, 64, anchor="w", fill="#ffffff",
                                     font=("Segoe UI", 9), text=name)
            # Text overlay bar
            if c.get("text"):
                self._tl.create_rectangle(x0, 24, x1, 40, fill=CC_TEXTTRK, outline="")
                label = c["text"][:24]
                self._tl.create_text(x0 + 4, 32, anchor="w", fill="#ffffff",
                                     font=("Segoe UI", 9), text=label)
            # Waveform (light green) inside the video block — see where
            # the sound is loud or silent. Wide blocks only, so it
            # never draws over the thumbnail or the clip name.
            if not c.get("mute") and x1 - x0 > 140:
                wave = self._waveform_for(c)
                if wave:
                    wx0 = x0 + 100
                    n = len(wave)
                    for k, v in enumerate(wave):
                        wx = wx0 + (k + 0.5) * (x1 - wx0) / n
                        amp = max(1.0, v * 15.0)
                        self._tl.create_line(wx, 64 - amp, wx, 64 + amp,
                                             fill="#4ade80", width=1)
            # Audio bar (green) when the clip has sound and is not muted
            if not c.get("mute"):
                self._tl.create_rectangle(x0, 88, x1, 104, fill=CC_AUDIO, outline="")
            acc += d
        # Transcript segments as colour-coded chips on the Text track
        # (Dribbble subtitle track): pink / blue, with the words on
        # them. Only what is already known — edited words, captions
        # made for the preview, or the transcript from a highlight
        # search — never starts a new listen here.
        segs = []
        if getattr(self, "_highlight_transcript", None):
            segs = [(ps, pe, txt)
                    for (ps, pe, txt, _w) in self._highlight_transcript]
        else:
            for ci, c in enumerate(self.project["clips"]):
                key = (str(c["path"]), round(float(c["start"]), 2),
                       round(float(c["end"]), 2))
                for s in (self._caption_cache.get(key) or []):
                    ps = clip_local_to_project(self.project, ci, float(s["start"]))
                    pe = clip_local_to_project(self.project, ci, float(s["end"]))
                    segs.append((ps, pe, str(s.get("text", ""))))
        for k, (ps, pe, txt) in enumerate(segs):
            x0 = label_x + ps * pps
            x1 = label_x + pe * pps
            if x1 - x0 < 8 or not txt.strip():
                continue
            fill = CC_PINK if k % 2 == 0 else CC_BLUE
            self._tl.create_rectangle(x0, 24, x1, 40, fill=fill, outline="")
            label = txt.strip()
            if len(label) > 20:
                label = label[:19] + "…"
            self._tl.create_text(x0 + 4, 32, anchor="w", fill="#ffffff",
                                 font=("Segoe UI", 9), text=label)
        # Music bar (purple, Dribbble) with a lavender waveform.
        if (self._music_var.get() or "").strip():
            self._tl.create_rectangle(label_x, 108, label_x + total * pps, 124,
                                     fill=CC_MUSIC_BG, outline="")
            try:
                wave = self._waveform_for({"path": self._music_var.get(),
                                           "start": 0.0, "end": total})
            except Exception:
                wave = None
            if wave:
                n = len(wave)
                for k, v in enumerate(wave):
                    wx = label_x + (k + 0.5) * total * pps / n
                    amp = max(1.0, v * 6.0)
                    self._tl.create_line(wx, 116 - amp, wx, 116 + amp,
                                         fill=CC_LAVENDER, width=1)
            self._tl.create_text(label_x + 4, 116, anchor="w", fill="#ffffff",
                                 font=("Segoe UI", 9), text="♪ Music")
        # Sound-effect markers (amber diamonds) at their project time
        for s in (self.project.get("sfx") or []):
            at = float(s.get("at", 0.0) or 0.0)
            if at < 0 or at > total:
                continue
            x = label_x + at * pps
            self._tl.create_polygon(x, 88, x + 5, 96, x, 104, x - 5, 96,
                                    fill="#f59e0b", outline="")
            name = Path(str(s.get("path", ""))).stem
            if len(name) > 12:
                name = name[:11] + "…"
            self._tl.create_text(x + 7, 96, anchor="w", fill="#fbbf24",
                                 font=("Segoe UI", 8), text="♪ " + name)
        # Chapter markers (v2.4, Tutorial Maker): a gold line across
        # the tracks, a diamond in the ruler, and the title. Click
        # a marker (top strip) to rename the chapter.
        for ch in (self.project.get("chapters") or []):
            ct = float(ch.get("time", 0.0) or 0.0)
            if ct < 0 or ct > total:
                continue
            x = label_x + ct * pps
            self._tl.create_line(x, 22, x, 124, fill=CC_GOLD, width=1)
            self._tl.create_polygon(x, 14, x + 5, 19, x, 24, x - 5, 19,
                                    fill=CC_GOLD, outline="")
            title = str(ch.get("title", "") or "Chapter")
            if len(title) > 22:
                title = title[:21] + "…"
            self._tl.create_text(x + 7, 14, anchor="w", fill=CC_GOLD,
                                 font=("Segoe UI", 8, "bold"), text=title)
        # AI highlight ranges (gold bars over the video track)
        for (hs, he, _sc) in getattr(self, "_highlights", []):
            x0 = label_x + hs * pps
            x1 = label_x + he * pps
            self._tl.create_rectangle(x0, 44, x1, 84, fill="", outline="#fbbf24", width=2)
            self._tl.create_text(x0 + 4, 50, anchor="w", fill="#fbbf24",
                                 font=("Segoe UI", 9, "bold"), text="★ Highlight")
        # "+" at the right end of the Video and Audio rows.
        for y, tag, cmd in ((64, "tl_add_video", self._add_clips),
                            (96, "tl_add_audio", lambda: self._show_section("Sounds"))):
            self._tl.create_oval(w - 26, y - 9, w - 8, y + 9,
                                 fill=CC_CARD, outline=CC_BORDER, tags=(tag,))
            self._tl.create_text(w - 17, y, anchor="center", fill=CC_TEXT,
                                 font=("Segoe UI", 11, "bold"), text="+", tags=(tag,))
            self._tl.tag_bind(tag, "<Button-1>",
                              lambda e, c=cmd: self._on_tl_add(e, c))
        self._move_playhead()

    def _on_tl_add(self, event, cmd):
        """A "+" on the timeline: run its action, and stop the click
        turning into a seek on the timeline."""
        cmd()
        return "break"
    def _move_playhead(self):
        if not self._tl.winfo_exists():
            return
        label_x, pps, _w = self._tl_geom()
        x = label_x + self._play_t * pps
        if self._playhead_id is not None:
            try:
                self._tl.delete(self._playhead_id)
            except Exception:
                pass
        if project_duration(self.project) <= 0:
            return
        self._playhead_id = self._tl.create_line(x, 0, x, 132, fill="#ffffff", width=2)
        self._tl.create_polygon(x - 5, 0, x + 5, 0, x, 8, fill="#ffffff", outline="")

    def _on_timeline_click(self, event):
        total = project_duration(self.project)
        if total <= 0:
            return
        label_x, pps, _w = self._tl_geom()
        t = (event.x - label_x) / pps if pps else 0
        t = max(0.0, min(t, total - 0.01))
        # v2.4: a click on a chapter marker (top strip, near its
        # line) renames the chapter instead of seeking.
        if event.y < 30 and pps:
            for ch in (self.project.get("chapters") or []):
                cx = label_x + float(ch.get("time", 0.0) or 0.0) * pps
                if abs(event.x - cx) <= 6:
                    self._rename_chapter(ch)
                    return
        # Select the clip under the click, like CapCut does.
        acc = 0.0
        for i, c in enumerate(self.project["clips"]):
            d = clip_duration(c)
            if acc <= t < acc + d or (i == len(self.project["clips"]) - 1):
                if self._sel != i:
                    if self._sel is not None:
                        self._read_clip_settings()
                    self._sel = i
                    self._load_clip_settings()
                    self._refresh_media()
                    self._draw_timeline()
                break
            acc += d
        self._playing = False
        self._play_btn._glyph.configure(text="▶")
        self._show_frame(t)

    def _rename_chapter(self, chapter):
        """Rename one chapter (click its gold marker on the timeline).
        The new name is saved in the project and used in the
        chapters.txt written on export."""
        try:
            from app import format_chapter_time
            when = format_chapter_time(chapter.get("time", 0.0))
        except Exception:
            when = "%.1fs" % float(chapter.get("time", 0.0) or 0.0)
        new = simpledialog.askstring(
            "Rename chapter",
            "Chapter at %s. New name:" % when,
            initialvalue=str(chapter.get("title", "") or "Chapter"),
            parent=self)
        if new is None:
            return
        new = new.strip()
        if not new:
            self._status_var.set("Chapter name kept: an empty name is not allowed.")
            return
        chapter["title"] = new
        self._snapshot()
        self._draw_timeline()
        self._status_var.set("Chapter renamed to '%s'." % new)

    # ---------- export ----------
    def _read_project_settings(self):
        self._read_clip_settings()
        self.project["transition"] = self._trans_var.get()
        self.project["ratio"] = self._ratio_var.get()
        self.project["quality"] = self._quality_var.get()
        self.project["caption_style"] = self._caption_style_var.get()
        self.project["caption_size"] = self._caption_size_var.get()
        self.project["caption_pos"] = self._caption_pos_var.get()
        self.project["caption_anim"] = self._caption_anim_var.get()
        self.project["title_style"] = self._title_style_var.get()
        self.project["caption_lang"] = self._caption_lang_var.get()
        self.project["ai_model"] = self._ai_model_var.get()
        self.project["ollama_model"] = self._ollama_model_var.get().strip() or OLLAMA_MODEL
        self.project["normalize"] = bool(self._normalize_var.get())
        self.project["auto_memes"] = bool(self._auto_memes_var.get())
        self.project["music"] = self._music_var.get().strip()
        self.project["music_vol"] = float(self._music_vol_var.get())
        self.project["music_fade"] = bool(self._music_fade_var.get())
        self.project["ducking"] = bool(self._ducking_var.get())
        self.project["letterbox"] = bool(self._letterbox_var.get())
        self.project["grain"] = bool(self._grain_var.get())
        self.project["captions"] = bool(self._captions_var.get())

    def _captions_available(self):
        """True when captions were already generated for at least
        one clip (edited captions, or an .srt next to the video)."""
        edits = self.project.get("caption_edits") or {}
        if any(edits.get(str(ci)) for ci in range(len(self.project["clips"]))):
            return True
        for c in self.project["clips"]:
            try:
                if Path(c["path"]).with_suffix(".srt").is_file():
                    return True
            except Exception:
                pass
        return False

    def _export_tutorial(self):
        """One-click tutorial export: 1080p landscape, H.264 at
        CRF 23 for easy sharing, captions burned in when they were
        generated, chapters.txt written alongside. Uses the normal
        export flow with the tutorial preset applied."""
        if self._exporting:
            return
        if not self.project["clips"]:
            messagebox.showinfo("Export tutorial", "Add a video clip first.")
            return
        self._quality_var.set("1080p")
        self._ratio_var.set("16:9  Landscape")
        if self._captions_available():
            self._captions_var.set(True)
        self.project["tutorial_export"] = True
        self._status_var.set("Exporting tutorial (1080p, H.264)…")
        self._export()

    def _export(self):
        if self._exporting:
            return
        self._read_project_settings()
        if not self.project["clips"]:
            messagebox.showinfo("Export", "Add a video clip first.")
            return
        first = Path(self.project["clips"][0]["path"])
        out = first.with_name(first.stem + "_edited.mp4")
        self._exporting = True
        self._bar.set(0)
        self._status_var.set("Exporting… please wait.")
        threading.Thread(target=self._export_thread, args=(str(out),),
                         daemon=True).start()

    def _export_thread(self, out):
        def progress(v):
            self.after(0, lambda: self._bar.set(v))

        def status(text):
            self.after(0, lambda: self._status_var.set(text))

        ok, msg = export_project(self.project, out, progress, status)
        self.after(0, self._export_done, ok, msg, out)

    def _export_done(self, ok, msg, out):
        self._exporting = False
        # The tutorial preset is one-shot: a later normal Export
        # must not re-encode.
        self.project["tutorial_export"] = False
        self._bar.set(1.0 if ok else 0.0)
        self._status_var.set(msg)
        if ok:
            messagebox.showinfo("Exported", msg + "\n\nSaved next to the first clip.")
            if callable(self.on_exported):
                try:
                    self.on_exported()
                except Exception:
                    pass
        else:
            messagebox.showerror("Export failed", msg)


def _run_standalone(initial_path=None):
    """Run the editor as its own process (own window, own mainloop).

    Used when the recorder launches the editor separately, so closing
    the recorder never closes the editor (and vice versa). The hidden
    CTk root exists only to own the mainloop; the editor window is
    what the user sees. When the editor closes, the hidden root is
    destroyed too so the process exits cleanly.
    """
    root = ctk.CTk()
    root.withdraw()
    ed = VideoEditor(root, initial_path=initial_path)

    def _quit_when_editor_closes():
        try:
            alive = bool(ed.winfo_exists())
        except Exception:
            alive = False
        if not alive:
            try:
                root.destroy()
            except Exception:
                pass
        else:
            root.after(500, _quit_when_editor_closes)

    root.after(500, _quit_when_editor_closes)
    root.mainloop()


if __name__ == "__main__":
    _path = sys.argv[1] if len(sys.argv) > 1 else None
    _run_standalone(_path)
