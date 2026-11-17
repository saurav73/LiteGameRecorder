# 🎓 Lite Tutorial Maker v2.4 - Turn a screen recording into a polished tutorial

Teachers, trainers, and developers need clear tutorial videos, but OBS is too complex and Camtasia/Loom cost money. Lite Tutorial Maker is the free, simple tool that turns a screen recording into a polished tutorial in one click. Game recording, live streaming, and memes are still in there, as features, not the whole app.

## 🎓 Tutorial Maker: the workflow

**1. Record with chapters.** Press Record (F9) and explain as you go. Whenever you move to a new topic, press **M** (or the 🔖 button) to drop a chapter marker. Need to point at something? Press the ✏️ button and draw a yellow highlight right on the screen, Esc stops drawing. Chapters are saved next to the video as a `.chapters.json` file.

**2. Generate captions.** Open the video in the editor (Edit video button). The chapters show as gold markers on the timeline, click one to rename it. Press **Generate captions (.srt)** in the Project panel: the app listens to your speech and writes an `.srt` file next to the video, and turns caption burn-in on. Captions need the free offline speech engine (`pip install -r requirements-smart.txt`); without it the app says so plainly and keeps working.

**3. Export tutorial.** Press **🎓 Export tutorial** in the editor top bar. You get a 1080p H.264 video (CRF 23, easy to share anywhere), captions burned in when generated, an `.srt` next to it, and a `chapters.txt` file with YouTube style `MM:SS Title` lines, ready to paste into your video description.

## 🪟 Windows: install it as a real app (like v1.5)

You do **not** need to use `run.bat` any more. v2.3.2 brings back the v1.5 one-click installer:

1. Extract the zip, open the folder.
2. Double-click **Install Lite Game Recorder.bat** — just once.
3. It installs Python for you if it is missing, then builds **LiteGameRecorder.exe**, installs it, and puts a **Lite Game Recorder** icon on your Desktop and in the Start Menu.
4. After that, just double-click the Desktop icon. It opens like a normal app — no Python, no black window.

> Note: the .exe has the new design, Live, game sound and character filters. **Smart Record** (speech check) is not inside the .exe — it needs the speech engine, which is too big to pack into the exe. If you want Smart Record, use `run.bat` instead (it uses the same folder). I can pack Smart Record into the exe later if you want it.

## ⚠️ Windows: if run.bat does nothing / flashes and closes

This usually means **Python is not installed**, or the app crashed and the old launcher hid the error. v2.3.1 fixes the launcher so you can see the error.

1. **Extract first** — right-click the zip → **Extract All** → open the extracted folder. Do NOT run it from inside the zip.
2. **Install Python 3.11** from [python.org/downloads](https://www.python.org/downloads/) — during install, **tick "Add Python to PATH"**. This is the most common fix.
3. Double-click **run.bat** again. The first run takes 1–2 minutes and needs internet.
4. If it still does not open, double-click **Diagnose.bat** — it writes `diagnose.txt` in the same folder. Send me that file and I will tell you the exact fix.
5. If Windows says "Windows protected your PC", click **More info** → **Run anyway**.

## What's new - Tutorial Maker v2.4 (Nov 2026)

**🔖 Chapters while recording** - press M (or the 🔖 button) during a recording to drop a timestamped chapter marker. Chapters save as `.chapters.json` next to the video, show as gold markers on the editor timeline (click one to rename it), and export as a YouTube style `chapters.txt`.

**📝 Generate captions (.srt)** - one button in the editor transcribes your speech with the offline Whisper engine, writes an `.srt` next to the video, and turns caption burn-in on for the export. No speech engine installed? The app tells you how to install it and carries on.

**🎓 Export tutorial** - one click in the editor top bar: 1080p, H.264 at CRF 23, captions burned in when generated, `chapters.txt` alongside. The normal Export is unchanged.

**✏️ Draw on the screen** - while recording, press the ✏️ button and draw a yellow highlight freehand on the screen. The recording captures it. Esc stops drawing, 🗑 clears it. Windows only (it uses a transparent overlay).

**New name** - the app is now Lite Tutorial Maker. Game recording, live, replay buffer, memes, and sounds all still work exactly as before.

## What's new - Real meme content v2.4.1 (Nov 2026)

**🎬 Real footage meme clips** - the 100 meme video clips are now real footage, not rendered text cards. Each one is a 2.5 second cut from a free stock video on Coverr (Coverr licence: free for personal and commercial use, no attribution required): real people reacting, laughing, celebrating, falling over, real clocks and sunsets for the time cards, real gamers and board games for the gaming clips. No AI-generated video, no copyrighted viral clip or movie scene. `meme-videos/manifest.json` lists every clip with its source URL and licence, and `make_meme_videos.py` rebuilds all 100 from it.

**🔊 Real recorded sounds** - the 16 original sounds (Whoosh, Pop, Ding, Coin, Boom, Riser, Airhorn, Applause, Drumroll, Click, Laser, Success, Scratch, Sad Trombone, Punch, Dun Dun Dunnn) are now real recordings from Freesound instead of numpy-synthesized tones. Same filenames, same 44.1 kHz mono WAV format, so the editor, Templates tab, and Auto-Edit keep working exactly as before. Sources are listed in `sounds/SOURCES.txt`.

## What's new — Responsive design + memes (Nov 2026)

**📐 Responsive — the windows now fit any size**
- The preview grows and shrinks with the window, the side panels flex instead of cutting buttons off, the toolbar wraps to a second row when the window is narrow, the timeline gets taller with the window, and there is a minimum window size (editor 1100×700, recorder 1000×650) so nothing is ever squeezed off-screen. The Record and Play buttons are truly round now. Record, timer and status are biggest and closest to the preview; trim, speed and filter are visible without scrolling. Tested at 1024×640, 1400×860 / 1280×820 and 1920×1080 with screenshots — no clipped buttons, no panel pushed off-screen.
- **Editor centre made simpler (your feedback):** only one row of buttons under the preview now — Split, Speed, Volume, Delete, Duplicate, Text — so the preview is bigger. Sticker, Filter and Captions moved out of the toolbar (they are still one click away: Stickers and Effects in the left icon bar, Captions switch in the right panel). The "Keep before / after playhead" buttons moved to the right panel, next to the trim boxes.

**🤣 Memes — templates, video clips, sounds, and Auto-Edit that adds them by itself**
- **10 meme templates** in the Templates tab: A Few Moments Later, One Eternity Later, 2000 Years Later, Twelve Seconds Later, A Few Minutes Later, Tomorrow, To Be Continued, Bruh Moment, Emotional Damage, Dramatic Moment. (The exact SpongeBob card picture belongs to Nickelodeon, so the editor recreates the same look with its own text.)
- **100 meme video clips** (Templates tab → "Meme videos") to drop into any video with one tap: 20 time cards, 20 reactions, 15 fails, 15 wins, 15 dramatic moments, 15 gaming moments (Headshot!, Killstreak, 1V5, 360 No Scope, GG EZ...). Each one is real footage from free stock videos on Coverr, and each one has its sound in it already. `meme-videos/manifest.json` lists every clip's source, and `make_meme_videos.py` rebuilds all 100 from it.
- **Make your own meme card:** type any words, pick a style, press "Make my meme card" — a new video card in seconds.
- **Auto-Edit adds memes by itself:** it listens to your video, finds the best moments (a loud funny part, a fail, a win, a shock) and drops the right meme sound there, plus the matching meme card at the best moment. It tells you what it added. Turn it off with the "Add memes automatically" switch.
- **329 free sounds** in the Sounds tab now (was 15): Fahh, Bruh, Emotional Damage, Dun Dun Dunnn, Vine Boom, Roblox Oof, Windows XP Error, MLG Airhorn, Metal Pipe, Wilhelm Scream, Slide Whistle, Goat Scream, Sad Violin, and 300 more from free sources (Freesound, 712tools, sfxreels, memesoundboards.org, myinstants — see `sounds/SOURCES.txt`). The 16 original sounds are real Freesound recordings now, not synthesized tones. Some are copyrighted samples offered as free downloads, marked "check before commercial use". Pixabay could not be used — it blocks all automatic downloads with a bot check.

**🧪 Tested — 127 checks, all passing:** the full test suite still passes 127/127 on the final code.

## What's new — Full new design + better editor (Nov 2026)

**🎨 BOTH windows redesigned like the modern editors you showed me (Dribbble)**
- **Recorder:** thin icon bar on the left (Record, Library, Facecam, Audio, Live, Script, Settings), big preview in the middle, timer on top, and a **BIG ROUND RED Record button at the bottom**, like a camera app. No more long wall of settings — one section at a time. The right side shows your session: Now recording, Smart Record live, Sound, Instant Replay.
- **Video editor:** thin icon bar on the left (Templates, Media, Audio, Sounds, Text, Stickers, Effects, AI), big preview in the middle with a floating **Magic Tools / Size / Background** pill under it, a light-blue **Export** button on top, a big round Play button, and the timeline at the bottom with video, audio waveform, text and music tracks. Subtitles appear as coloured clips on the timeline, pink and blue, with the words on them.
- One shared look: very dark, very round, one light-blue colour for the main buttons. Only the look changed — every button does the same thing.
- **🖱️ Left-click zoom — fixed:** the app used to stop listening for mouse clicks almost as soon as a recording started, so no click ever reached the zoom. Now the click listener stays alive for the whole recording — a left click zooms in 1.8x right where you clicked, then eases back out. The same bug was also cutting Live streams off at the start, so that is fixed too.

**✂️ Better editor — the four things you asked for, plus the OpenClip ideas and animated subtitles**
- **AI Edit v2:** also fixes the picture by itself (brightness and colour), keeps natural short pauses instead of cutting everything into tiny pieces, and uses smooth fades between beat cuts.
- **Cut:** "Keep before playhead" / "Keep after playhead" buttons, and type the exact trim time (2 decimals).
- **Sound:** loudness normalizer (quiet and loud parts come out even), fade in / fade out on each clip, and a waveform on the timeline so you can SEE where the sound is loud or silent.
- **Subtitles:** edit the caption words yourself after they are made, change the size and position, and the export also saves an .srt file. If you already have an .srt file next to the video, it uses that — no need to transcribe again.
- **Animated subtitles (on by default):** the words pop in one by one as they are spoken, Hormozi style (spoken word big and yellow, the rest dimmer). Change it to Karaoke, Bounce, Slide up, or Typewriter. Works in preview and in export.
- **Find the parts about X:** type what to look for ("goal", "funny", "win") and it finds those moments from the words spoken. Cuts snap to sentence ends — never in the middle of a word. One long video becomes many short clips at once (repurpose mode), each with its own auto title and cover.
- **Free AI models (optional):** in the editor's AI panel, pick OpenRouter (free cloud key from openrouter.ai, no payment) or Ollama (local, on your PC, default model llama3.2:3b). The AI then READS what was said and picks the best moments and writes the titles. The key stays only on your PC and is never saved in a project file. No key, no internet, or Ollama not running? The editor just uses the free offline version — it still works, and tells you how to start Ollama if you want the local one.

**🧪 Tested — 127 checks, all passing:** the redesign changed only the look — no button, setting or feature was renamed or moved, and the full test suite still passes 127/127.

## What's new — voice delay fixed, editor sound, free sound effects, voice switching, CRUD (Nov 2026)

**🎙️ Voice delay — fixed for real**
- The bug from the user's video: the mic started up to 1 second *before* the video (opening the webcam + starting game sound takes time), so the voice came ~1 s **after** the mouth moved. The app now stamps when the mic, the game sound and the first video frame actually start, and shifts the audio back onto the lips in the final mix. Pausing is fixed too: the mic used to keep recording while the video was paused, so the sound drifted after every pause — paused parts are now cut out of the audio.
- Tested: tone onset at **0.00 s** (was 1.00 s), pause cut exactly, voice switch verified by pitch (440 Hz → 704 Hz Deep).

**🎤 Voice changer while recording**
- Change the voice (Off / Deep / High (Chipmunk) / Echo / Robot) in the Audio card **in the middle of a recording** — the new voice starts from that moment, so one video can go Deep and then Chipmunk. The recorder stamps each change and applies each voice to its own part of the mic audio when the video is saved.

**🔊 The editor can play sound now — and the sound bug is fixed**
- Press Play in the editor and you hear the clip sound + music + sound effects in sync with the preview (before it was video only). A "🔊 Sound" tick box next to Play turns it off. The mix is rendered once with FFmpeg and cached until the project changes.
- **The bug:** the video used to start at once while the sound was still being prepared, so on a short clip the video finished *before* the sound was ready — you heard nothing, and the status just said "Preparing sound…" forever. Now the video waits for the sound, and the mix is prepared in the background while you edit, so it is usually ready before you press Play.
- **Two players, not one:** if the built-in player (sounddevice) cannot play on your PC, the editor falls back to **ffplay**, which comes with the FFmpeg the installer downloads. The installer now downloads ffplay.exe too. If both fail, the editor says so instead of staying silent.
- **"🔊 Test sound" button** (Audio tab): plays the Ding in one tap, so you can check in 2 seconds whether sound works on your PC at all — no need to guess.

**🤖 Free AI in the editor (new AI row — all on your PC, no account, no upload, no cost)**
- **✨ Auto-Edit** — one tap: cuts the dead air out of every clip, cuts on the music's beats, and turns auto captions ON.
- **🎯 Highlights** — listens to the whole video, finds the loudest moments (a goal, a kill, a laugh, a drop) and marks them gold on the timeline; you can keep only those moments (everything else is cut out). It hears loudness, not the game — it cannot tell which kill it was.
- **🎬 Scene Split** — splits the selected clip wherever the picture changes (a new scene, a cut, a new camera angle).
- **🖼️ Best Thumbnail** — looks at 16 moments in the video and saves the best frame as your thumbnail: sharp, well lit, and with a face if there is one.

**🎵 Free sound effects (Sounds tab)**
- 16 core sounds, all real recordings from Freesound (CC-licensed, see `sounds/SOURCES.txt` for each sound's creator and page): Whoosh, Pop, Ding, Coin, Boom, Riser, Airhorn, Applause, Drumroll, Click, Laser, Success, Scratch, Sad Trombone, Punch, Dun Dun Dunnn. ▶ listens, **＋ Add** puts the sound at the playhead (orange markers on the timeline), and they are mixed into the export. Import your own sounds too (mp3 / wav) — they are copied into the `sounds/` folder.

**✏️ Proper edit / delete (CRUD)**
- Recent recordings: **Rename** (pencil), **Duplicate** (page icon — makes a "<name> copy.mp4") and **Delete** (trash) buttons per video — renaming/deleting/duplicating also handles the `_script.txt` / `_captions.srt` sidecars. Templates: user / imported templates have a **Delete this template** button (removes the `.json` too), and **Save my look** adds the look to the list right away (saving over the same name updates it).
- Editor: **📄 Duplicate** in the toolbar copies the selected clip right after it, with its trim, speed, filter, text and volume. **💾 Save** (top bar) saves the whole project — clips, trims, settings, music and sound effects — to a `.json` file, and **📂 Open** loads it back later. If a clip's video file has moved since you saved, that clip is left out and you are told which one.

**🧪 Tested — 127 checks, all passing** (was 88): everything from before, plus the editor sound fallback (sounddevice fails → ffplay plays; no sounddevice at all → ffplay still plays), the video waiting for its sound (short clip, sound plays in sync), scene detection, highlights (loud moment found, kept alone), best-frame scoring, AI Scene Split / Best Thumbnail / Highlights / Auto-Edit in the editor, rename + delete recordings, template delete, duplicate a recording, duplicate a clip, and project save → load (including a missing clip file being left out and reported), and the left-click zoom (listener alive 1 s into a recording, a real click zooms 1.8x on the click point, zooms back to 1.0, video still saves) — plus the new editor v2 checks: AI Edit v2 (natural pauses kept, enhance brightens), trim to playhead, typed trim, per-clip fades, loudness normalize, timeline waveform, editable captions, SRT on export, animated captions (spoken word pops yellow), keyword highlights, snap to sentence ends, repurpose to separate clips, auto titles + covers, .srt import, and the free AI models (OpenRouter mocked, Ollama mocked, no key = offline, bad reply = offline).

## What's new — sound fixed, facecam fixed, better templates (Nov 2026)

**🔊 Sound — fixed for real**
- The installer now **downloads FFmpeg automatically** (one time, ~40 MB) and puts it next to the app. FFmpeg is what puts your mic and game sound into the video — without it every recording was silent. If you already installed, the setup window has a new **"Get FFmpeg (sound)"** button.
- **Before you record, the app now warns you** if your video would have no sound at all (mic off + no game-sound source on the PC, or FFmpeg missing) — instead of letting you record a silent video.
- **"Test game sound — record 3 sec"** (Audio card): it really records 3 seconds of game sound and tells you how loud it was, so you know BEFORE recording whether it works. If it captures silence, it tells you to play something and check Stereo Mix / VB-Cable.
- The editor also finds FFmpeg/ffprobe next to the app now, so edited videos keep their sound too.

**🪞 Facecam — no more flipped face**
- The facecam is now **mirrored like a selfie** (the way TikTok / phone cameras show you), so your hair and hands no longer look "opposite" in the video. Turn it off in the Facecam card ("Mirror facecam") if you want to look like a viewer sees you.

**🎬 Editor — 26 templates + 13 animated subtitle styles (researched from trending Reels / CapCut, Nov 2026)**
- New templates: **Velocity Edit 2.0** (fast-slow-fast Hero speed ramp), **Beat Sync Pro**, **Slow Motion Cinematic**, **3D Zoom Photo**, **Cinematic Letterbox** (black movie bars), **Vintage / Retro Film** (film grain), **Text Reveal Hook**, **Lyrics Highlight**, **Vlog / Day in the Life**, **Gaming Kill Montage**, **Photo Dump Minimal** (white photo frames).
- New **Hero** speed ramp (fast → slow in the middle → fast, like CapCut's Hero curve), **Jelly** clip animation, **TealOrange** film colour filter, **Letterbox bars** and **Film grain** switches (Project card), **White photo border** (Video card).
- **13 animated subtitle styles** (Captions style, Project card): Hormozi (green pill on the spoken word), Beast Mode (yellow + swell), Golden Karaoke, Karaoke, Neon, Typewriter, Gradient Pop, Minimal, Bouncing Ball, Word Punch, TikTok Box, Gamer.
- **Import your own templates**: Templates tab → "Import template" (a `.json` file) or "Save my look" (saves your current look as a `.json` you can share). Drop any `.json` template into the `templates` folder next to the app and it shows up by itself. Two free example templates are included.
- **Load a free .cube colour look** (Effects tab): download a free `.cube` LUT from FreeVisuals / FilterGrade / videoeditingluts.com, load it here, and it colours your clip like a real film grade — that is the one template format that really imports.
- **Smart reframe** now finds small faces too (it looks at a bigger picture before cropping).

**✅ Tested this time — all 49 checks passed**: recording, mic + game sound mixing, system-audio detection, facecam mirror, every filter, LING, Smart Record, live failing safely, all 26 templates, all 13 caption styles, all 10 clip animations, Hero ramp, all transitions, letterbox/grain/border, .cube LUTs, remove silence, beat split, reverse, freeze, stabilize, denoise, ducking, GIF, thumbnail, smart reframe, installer FFmpeg download, uninstall, and instant replay.

## What's new — Instant Replay + AI editor tools (Nov 2026 research)

Researched what the best clipping and editing apps do in 2026 (ShadowPlay, OBS Replay Buffer, Medal, CapCut, Filmora, VN, Premiere) and added the best of it, free and offline:

**⏪ Instant Replay (Capture card, or Record menu)**
- Turn it on and the app records your screen in the background all the time. Do something amazing? Press **F11** (or the "Save replay" button) and it saves the **last 30 / 60 / 120 seconds** as `Replay_YYYY-MM-DD_HH-MM-SS.mp4` — with your mic + game sound, if those are on.
- Like ShadowPlay: you never miss a moment you didn't think to record. The buffer is small (5-second clips, old ones deleted automatically — about 90 MB for 60 s) and it stops by itself when you start a normal recording. While it is on, the preview shows your screen live.

**✂️ Editor — AI row (under the preview toolbar)**
- **Remove silence** — one tap cuts the dead air out of the selected clip, like Descript / VN. It keeps only the parts where someone is talking.
- **Split on beats** — cuts the video exactly on the music's beats, like CapCut Beat Sync. Set your music in the Audio tab first, then one tap.
- **GIF** — exports a small shareable GIF of your edit (`*_edited.gif`, 480 px, 12 fps).
- **Thumbnail** — saves the current preview frame as `*_thumbnail.png`, ready for YouTube.
- **Stabilize** (Video card) — one-tap fix for shaky video, like Premiere Warp Stabilizer (FFmpeg vidstab).
- **Reduce noise** (Video card) — cleans up a clip's audio (FFmpeg afftdn).
- **Duck music under speech** (Project card) — the music goes quiet while someone talks, then comes back up.
- **9:16 Smart reframe** (Video size) — turns a wide video vertical and follows your face, like Premiere Auto Reframe. No face in frame = centre crop.

Still not possible (honest): auto-detecting kills/wins in a specific game (Medal/Outplayed do this with game hooks — needs a big team and per-game work), cloud AI background removal, and 4K/60fps hardware encoding.

## What's new in v2.3 — Smart Record (script check, auto-correct)

You paste your script, and the app checks what you actually say against it.

In the **📜 Script — Smart Record** card:

1. Turn on **Smart Record — check my speech against the script**.
2. Paste your script, e.g. `Hi, welcome back to my channel!` (or **Load .txt…** to load a script file).
3. Press **Record** and speak. While you record it shows live: **Now say: …**, **Accuracy …%**, **mistakes**, and **Last heard: …**
4. After you stop, you get two new files next to the video:
   - `Game_…_script.txt` — accuracy, what you said, the auto-corrected version, every mistake (`script says 'welcome', you said 'elcom'`), and lines to re-record.
   - `Game_…_captions.srt` — subtitles for the video. With **Auto-correct captions to the script** on, a misspoken word in the captions is replaced with the correct script word.

**Your example, tested:** script `Hi, welcome back to my channel!`, you say `hi elcom eback to my chnnel` → **50% accurate, 3 mistakes** (welcome→elcom, back→eback, channel→chnnel), auto-corrected captions say `Hi welcome back to my channel`. Press **▶ Test with example** in the app to try this yourself, no mic needed.

> **Honest note:** your recorded **voice is NOT changed** — no app can cleanly fix a misspoken word in the audio itself. What is auto-corrected is the **captions / report**, so viewers reading subtitles see the right words, and you know exactly which lines to re-record.
>
> **Speech engine:** Smart Record needs a speech-to-text engine. Install it once with `pip install -r requirements-smart.txt` (faster-whisper, offline, tiny model ~75 MB downloaded once) — or it tries Google Web Speech (online). If no engine is installed, the app tells you so and the video still saves. Tested with faster-whisper on a real speech sample (JFK: 100% accurate, with timestamps, in ~6 seconds).

## What's new in v2.2 — Character filters (you on camera, as another character)

In the **🎥 Facecam** card, **Character filter — you on camera**:

- **Cartoon, Anime, Comic, Sketch, Pixel, Robot, Alien, Vampire, Neon, Hero** — plus the old ones (None, Smooth, B&W, Sepia, Warm, Cool).
- Pick one, and your facecam in the video looks like that character/style. You can see it in the preview **before** you press Record.
- **Apply same filter to whole video too** — turn this on and the whole video (game + you) gets the same filter. This is heavier, so use **720p or 480p** for it.

> Honest note: these are **style filters** (colour + edges + posterising, all in OpenCV, light enough to run live). They make you *look like* a cartoon / anime / robot character. They are **not** a face-swap to a real person or a specific licensed character (like Spider-Man or a VTuber avatar) — that needs a heavy AI model and a download. If you tell me which exact character you want, I can add a mask/overlay version for that one next.

Tested: all 16 filters run on a test face image (shape/dtype unchanged, each one visibly changes the image), and a 3-second recording with Cartoon + whole-video saved correctly (87 frames, 2.90 s). Whole-video Cartoon is slower — on the test PC capture dropped to ~15 fps while the writer still filled the timeline to 2.90 s — so expect a choppier video with whole-video filters on a weak laptop; facecam-only filters are much lighter.

Records your **game (full screen)** with your **facecam in the corner** and your **microphone and/or game sound**, in one MP4 — and now it can also **go live to YouTube, Twitch, Facebook, Kick, or any RTMP platform** while it records.

Everything from v1.5 still works: click auto-zoom, click ripple + cursor ring, region select, countdown, shortcut display, auto-stop timer, GIF copy, mic noise reduction, voice changer, face filters, speed controller, and the 1x rule (record 50 sec → video is 50 sec).

## What's new in v2.1 — Game sound (system audio)

In the **🎙️ Audio** card you now have separate switches:

- **Microphone on** — your voice, as before.
- **🎮 System audio — game sound** — ON or OFF, your choice. This records what the game / PC itself is playing.
- **Game sound ONLY (no mic)** — turn this on and the video has **game sound only, no mic**. Perfect for what you asked: while playing a game, only the game voice/sound is recorded.

The app shows what will be recorded, e.g. `Audio: 🎙️ Mic + 🎮 Game sound` or `Audio: 🎮 Game sound only`.

**How it works:** game sound is captured with FFmpeg from your system's loopback/monitor source, in the background while you play, then mixed into the MP4 when you stop. The voice changer and noise reduction apply to the **mic only** — game sound is left untouched (except speed, so it stays in sync). If you turn both mic and game sound on, they are mixed together.

**🔍 Check system audio on this PC** — press this button in the Audio card first. It tells you if game sound will work, or exactly what to set up:

| Your PC | What you need |
|---|---|
| **Windows** | Enable **Stereo Mix**: right-click speaker icon → Sound settings → More sound settings → Recording → right-click Stereo Mix → Enable. No Stereo Mix? Install free **VB-Cable** (vb-audio.com) and set it as your playback device. |
| **Mac** | Install free **BlackHole** (existential.audio/blackhole) and set it as your output in System Settings → Sound. macOS can't capture system sound without a virtual device like this. |
| **Linux** | Usually works automatically (PulseAudio/PipeWire monitor source). If it fails, install `pulseaudio-utils` and check `pactl info`. |

> **Needs FFmpeg** for game sound (free, [ffmpeg.org](https://ffmpeg.org)). If game sound can't start on your PC, the app tells you why in the status bar — and **recording still works**, just without game sound. It never fails the whole recording because of audio.
> Game sound also goes into the **Live** stream when it's on (mic + game mixed, or game only if you picked that). If that audio input fails, Live falls back to mic-only, then video-only.

## What's new in v2.0

### 🎨 New design
- Modern dark UI (CustomTkinter): big 16:9 preview, one big red **● Start Recording** button, LIVE badge + big timer in the header.
- Settings grouped into cards in a sidebar — **Capture, Facecam, Audio, Effects, 🔴 Go Live, Save to** — instead of one long grey grid.
- **Recent recordings** list under the preview: click any video to open it.
- Your v1.5 settings carry over — `config.json` is compatible.

### 🔴 Live to any platform (RTMP)
In the **🔴 Go Live** card:
1. Turn on **Go Live when recording starts**.
2. Pick a platform — **YouTube, Twitch, Facebook, Kick, or Custom**. The RTMP URL fills in automatically.
3. Paste your **stream key** (Show button to check it). Where to find it:
   - **YouTube:** YouTube Studio → Create → Go live → Stream → copy Stream key
   - **Twitch:** Creator Dashboard → Settings → Stream → copy Primary Stream Key
   - **Facebook:** Meta Live Producer → copy Stream Key
   - **Kick:** Dashboard → Settings → Stream Key
   - **Custom:** paste the full RTMP URL your platform gave you, plus its key.
4. Pick a bitrate (4500k is a good default for 720p) and press **Record**. The LIVE badge turns red. Recording and streaming happen at the same time — if the stream drops, **recording keeps going** and the app tells you.

> **Needs FFmpeg** for Live (free, [ffmpeg.org](https://ffmpeg.org)). The app warns you if it's missing.
> **Never share your stream key.** It is stored only on your PC, and only if you tick *Remember stream key on this PC*. Anyone with it can stream as you.
> Live mic audio is best-effort (it uses your system's default mic via FFmpeg). If your mic input can't be opened, the stream goes live video-only instead of failing.

### 💻 Works on any platform (Windows / macOS / Linux)
- The old Windows-only `keyboard` library is gone — hotkeys (F9 / F10) now use `pynput`, which works on all three OSes without admin.
- Launchers use a local virtualenv, so they work on modern Mac/Linux where system-wide `pip install` is blocked:
  - **Windows:** double-click `run.bat`
  - **Mac:** double-click `run.command` (or `./run.sh` in Terminal)
  - **Linux:** `./run.sh`
- Build a standalone app for your OS with `python build.py` (PyInstaller, no terminal window). For all three OSes at once, push a `v*` tag and GitHub Actions builds them — see `.github/workflows/build.yml`.

## Quick start

1. Unzip this folder anywhere.
2. Install **FFmpeg** (optional but recommended — it merges your mic, makes GIFs, and powers Live): [ffmpeg.org/download](https://ffmpeg.org/download) — on Mac `brew install ffmpeg`, on Linux `sudo apt install ffmpeg`, on Windows `choco install ffmpeg`.
3. Double-click the launcher for your OS above (first run installs the libraries, ~1 minute, needs internet once).
4. Click **● Start Recording (F9)**, switch to your game, play.
5. Press **F9** again to stop. Video is saved to `Videos/GameRecorder` (or the folder you pick).

## Controls

- **F9** — Start / Stop recording (and Live, if it's on)
- **F10** — Pause / Resume

## Best settings for a light laptop

| Setting | Use this | Why |
|---|---|---|
| Quality | **720p (Light)** | Biggest FPS saver. Looks great on YouTube, especially with facecam. |
| FPS | **30** | Half the work of 60 FPS. |
| Face size | 20–24% | Bigger facecam = slightly more work + covers more game. |
| Live bitrate | **4500k** | Good for 720p30 on YouTube/Twitch. Use 2500k on slow upload. |

## Honest notes

- **Game / system sound:** v2.1 **does** capture it — see above. It needs FFmpeg plus a loopback/monitor source (Stereo Mix on Windows, BlackHole on Mac, Pulse/PipeWire monitor on Linux). Tested on Linux: with no PulseAudio present it fails gracefully (recording continues, 3 s / 91 frames / 3.03 s), and mic+game mixing was tested with real FFmpeg files (both tracks merged into one AAC track, 2.00 s). A real game-sound test needs a real PC with sound playing, so try it with a game open and check the saved video has sound.
- **Live:** tested on Linux with FFmpeg against a dead RTMP server (stream fails gracefully, recording continues) and a 3-second screen recording (91 frames, 3.03 s — timing correct). A real live test needs your own stream key, so try it with an unlisted / test stream first.
- **No facecam preview?** Close Zoom/Teams/Discord video (they lock the camera), check camera privacy settings, try unplugging/replugging the webcam.
- **Black screen recording?** Play in Borderless/Windowed Fullscreen, and on dual-GPU laptops run the app on the same GPU as the game.

## Files

- `app.py` — the whole app (one file, readable)
- `requirements.txt` — OpenCV, mss, Pillow, sounddevice, pynput, CustomTkinter
- `run.bat` / `run.sh` / `run.command` — one-click launchers (Windows / Linux / Mac)
- `build.py` / `LiteGameRecorder.spec` — build a standalone app for your OS
- `.github/workflows/build.yml` — builds Windows + macOS + Linux automatically
- `icon.ico` / `icon.png` — the app icon
- `config.json` — your settings, saved automatically (stream key only if you tick Remember)

Everything runs **100% on your laptop** — nothing is uploaded anywhere, except the live stream you deliberately send to the platform you chose.
