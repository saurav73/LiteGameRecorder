# Changelog

All notable changes to Lite Tutorial Maker are documented here.
Version numbers follow Semantic Versioning (MAJOR.MINOR.PATCH):
a patch bumps for fixes, a minor bumps for new features, a major
bumps for breaking changes. Every version below has a matching
git tag (vX.Y.Z) and a Windows release built from that tag.

## Unreleased

- Meme videos and sounds: replacing the synthetic OpenCV text cards
  and numpy-synthesized sounds with real footage and real recordings
  from legal free sources (Pexels, Pixabay, public domain, free sound
  libraries).

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
