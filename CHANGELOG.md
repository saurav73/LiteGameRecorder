# Changelog

All notable changes to Lite Tutorial Maker are documented here.
Version numbers follow Semantic Versioning (MAJOR.MINOR.PATCH):
a patch bumps for fixes, a minor bumps for new features, a major
bumps for breaking changes. Every version below has a matching
git tag (vX.Y.Z) and portable releases (Windows, macOS, Linux)
built from that tag.

## Unreleased

(nothing yet)

## 2.5.0 - 2026-11-17

- Multi-OS portable builds: one GitHub Actions matrix build now
  produces a portable zip for Windows, macOS, and Linux. Each zip
  extracts anywhere and runs with no install (app + FFmpeg +
  sounds + meme videos + templates). macOS gets a real .app bundle;
  Linux gets a single binary. The app folder is fully portable:
  config.json, sounds, meme videos, templates, and FFmpeg are all
  found next to the exe (or next to the .app on macOS) instead of
  a temp dir, so the whole folder works from a USB stick.
- Built-in auto-updater: install once, then update in place. The
  app checks GitHub Releases (at most once a day, silently when
  there is nothing new), downloads the zip for your OS, verifies
  it, and swaps the app files, keeping config.json, Recordings/,
  and anything you added. Help menu, Check for updates, checks on
  demand. Source checkouts get a link to the releases page.
- Source launchers: run.sh (macOS/Linux), run.bat (Windows), and
  run.command (macOS double-click) now exist; the error messages
  and README already told users to run them.

## 2.4.1 - 2026-11-17

- Fixed: the video editor now runs in its own process. Opening the
  editor from the recorder and then closing the recorder used to
  kill both tools, because the editor was a child window of the
  recorder. Now the editor is launched separately (a new process,
  or a re-run of the exe with --editor in the Windows build), so
  either tool can be closed without affecting the other.
- Real meme content: the 100 meme video clips are now real footage
  from free stock videos on Coverr (no AI-generated video, no
  copyrighted viral clip), cut to 2.5 s with the same filenames and
  sounds as before. `meme-videos/manifest.json` lists every clip's
  source URL and licence, and `make_meme_videos.py` rebuilds all 100
  from the manifest. The 16 original sounds (whoosh, pop, ding, coin,
  boom, riser, airhorn, applause, drumroll, click, laser, success,
  scratch, sad-trombone, punch, dun-dun-dunnn) are now real recordings
  from Freesound instead of numpy-synthesized tones; sources are
  listed in `sounds/SOURCES.txt`. The editor, Templates tab, and
  Auto-Edit work exactly as before.

## 2.4.0 - 2026-11-17

Reframed from Lite Game Recorder into Lite Tutorial Maker: a free,
simple tool for making tutorial and explainer videos.

- Chapter markers: press M (or the bookmark button) while recording
  to drop a timestamped chapter. Chapters show on the editor
  timeline, can be renamed, and export writes a YouTube-style
  chapters.txt file.
- Auto-captions: Generate captions in the editor transcribes the
  recording with Whisper and writes an .srt file; the tutorial
  export burns the captions into the video.
- Tutorial export preset: one-click 1080p H.264 export (CRF 23)
  with captions burned in and chapters.txt alongside.
- Screen annotation: draw a yellow highlight on screen while
  recording (Windows only).
- Reframe: the app presents itself as a tutorial maker first.
  Game recording, facecam, live streaming, replay buffer, editor,
  memes, and sounds all still work.
- Windows release build: GitHub Actions builds LiteGameRecorder.exe
  on windows-latest, bundles FFmpeg plus sounds, meme videos, and
  templates, and publishes a Release on every tag push.

## 2.3.0 - 2026-11-15

Last release as Lite Game Recorder (imported from the original zip).

- Responsive design: windows fit any size, toolbar wraps, editor
  centre simplified to one button row.
- Memes: 10 meme templates, 100 meme video clips, 329 sounds,
  Auto-Edit that adds memes by itself.
- Full new design plus a better editor, 127 checks passing.
