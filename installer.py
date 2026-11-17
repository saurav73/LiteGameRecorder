"""Lite Game Recorder v2.3 - Setup (installer + uninstaller) for Windows.

A small window, no black terminal. Double-click "Install Lite Game
Recorder.bat" and this window opens. It shows what is happening,
with a progress bar and a log.

    Install:   pip-installs the libraries, builds LiteGameRecorder.exe
               with PyInstaller, installs it to
               %LOCALAPPDATA%\\Programs\\LiteGameRecorder, puts an icon
               on the Desktop and in the Start Menu, and copies this
               setup file + the Uninstall bat next to the exe so the
               app can uninstall itself later.
    Uninstall: closes the app, deletes the installed folder and both
               shortcuts. Your recordings are NEVER deleted.

Run it with --uninstall to uninstall without opening the window
(used by "Uninstall Lite Game Recorder.bat").

Paths can be overridden for testing with the LGR_INSTALL_DIR,
LGR_DESKTOP_DIR and LGR_STARTMENU_DIR environment variables.
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

VERSION = "2.3"
APP_NAME = "Lite Game Recorder"
EXE_NAME = "LiteGameRecorder.exe"

# Modern dark theme — the same palette as the main app, so the
# setup window no longer looks like a grey box from the 90s.
# Pure tkinter (no customtkinter): this window runs before any
# libraries are installed.
INS_BG = "#0F1218"
INS_PANEL = "#181D27"
INS_PANEL2 = "#1F2531"
INS_BORDER = "#2A3242"
INS_TEXT = "#E8EAF0"
INS_MUTED = "#9AA3B2"
INS_GREEN = "#2FBF71"
INS_GREEN_HOVER = "#28A861"
INS_LOG_BG = "#0B0E13"
INS_LOG_FG = "#C9D1D9"
INS_BANNER = "#0B5E43"      # deep green banner band at the top
INS_BANNER_SUB = "#B7EFD2"  # pale green text on the banner

# The 5 install steps, in the same order do_install() runs them.
# The stepper ticks them off as do_install() logs "Step N of 5".
_INSTALL_STEPS = [
    "Install libraries",
    "Build the app",
    "Copy files to install folder",
    "Get FFmpeg (for sound)",
    "Create Desktop + Start Menu shortcuts",
]


def _shorten(text, limit=72):
    """Long Windows paths wrap badly in the log — keep the start
    and the end, cut the middle out. 72 fits on one line of the
    log box even with a wide fallback monospace font."""
    if len(text) <= limit:
        return text
    keep = (limit - 3) // 2
    return text[:keep] + " … " + text[-keep:]


class _RoundedBar(tk.Canvas):
    """Progress bar with rounded ends, drawn on a canvas (ttk's
    clam bar is always a sharp rectangle). It behaves like a ttk
    Progressbar for the bits the installer uses: bar["value"] and
    bar["maximum"]. The percentage label is updated through the
    on_change callback whenever the value moves."""

    def __init__(self, master, maximum=100, on_change=None, **kw):
        super().__init__(master, height=26, bg=INS_BG,
                         highlightthickness=0, bd=0, **kw)
        self._maximum = float(maximum)
        self._value = 0.0
        self._on_change = on_change
        self.bind("<Configure>", lambda e: self._draw())

    def __setitem__(self, key, value):
        if key == "value":
            self._value = max(0.0, min(self._maximum, float(value)))
            self._draw()
            if self._on_change is not None:
                self._on_change(self._value)
        elif key == "maximum":
            self._maximum = float(value)
            self._draw()
        else:
            raise KeyError(key)

    def __getitem__(self, key):
        if key == "value":
            return self._value
        if key == "maximum":
            return self._maximum
        raise KeyError(key)

    def _round_rect(self, x0, y0, x1, y1, r, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r,
               x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r,
               x0, y0 + r, x0, y0]
        return self.create_polygon(pts, smooth=True, **kw)

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return
        self._round_rect(2, 2, w - 2, h - 2, 11,
                         fill=INS_PANEL2, outline=INS_BORDER)
        frac = self._value / self._maximum if self._maximum else 0.0
        fw = (w - 4) * frac
        if fw > 0:
            self._round_rect(2, 2, 2 + max(fw, 20), h - 2, 11,
                             fill=INS_GREEN, outline="")


def base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def install_dir():
    return os.environ.get(
        "LGR_INSTALL_DIR",
        os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                     "Programs", "LiteGameRecorder"))


def desktop_dir():
    return os.environ.get(
        "LGR_DESKTOP_DIR",
        os.path.join(os.path.expanduser("~"), "Desktop"))


def startmenu_dir():
    return os.environ.get(
        "LGR_STARTMENU_DIR",
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming",
                     "Microsoft", "Windows", "Start Menu", "Programs"))


def _run(cmd, log):
    """Run a command hidden (no console window on Windows), streaming
    its output into log(). Returns True when it exits with code 0."""
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                cwd=base_dir(), **kw)
    except Exception as exc:
        log("Could not start: %s" % exc)
        return False
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log(line)
    proc.wait()
    return proc.returncode == 0


def _make_shortcut(target, link_path):
    """Create a .lnk shortcut with PowerShell (no extra libraries)."""
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
        " $s.TargetPath='%s'; $s.WorkingDirectory='%s';"
        " $s.IconLocation='%s,0'; $s.Save()"
        % (link_path, target, os.path.dirname(target), target))
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-Command", ps], capture_output=True, **kw)


FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def download_ffmpeg(log, target_dir, progress=None):
    """Download FFmpeg (needed for ALL sound: mic, game sound, live,
    editor audio) and put ffmpeg.exe + ffprobe.exe + ffplay.exe in
    target_dir. ffplay is the editor's backup sound player, used
    when the built-in player cannot play. Only called when no
    FFmpeg is found. Returns True on success."""
    import urllib.request
    import zipfile
    import tempfile
    ff = os.path.join(target_dir, "ffmpeg.exe")
    if os.path.exists(ff) or shutil.which("ffmpeg"):
        log("FFmpeg is already there — skipping the download.")
        return True
    log("Getting FFmpeg (for sound — mic, game sound, live, editor)...")
    log("This is a one-time download (~40 MB).")
    tmp = os.path.join(tempfile.gettempdir(), "lgr_ffmpeg.zip")
    try:
        with urllib.request.urlopen(FFMPEG_URL, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total and progress is not None:
                        progress(got / total)
                    if got % (10 * 1024 * 1024) < 256 * 1024:
                        log("  ...downloaded %.0f MB of %.0f MB" % (got / 1048576, total / 1048576))
        log("Downloaded. Unpacking ffmpeg.exe + ffprobe.exe + ffplay.exe...")
        with zipfile.ZipFile(tmp, "r") as z:
            for member in z.namelist():
                base = os.path.basename(member)
                if base in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                    data = z.read(member)
                    with open(os.path.join(target_dir, base), "wb") as f:
                        f.write(data)
        if os.path.exists(ff):
            log("FFmpeg ready — sound will work.")
            return True
        log("FFmpeg download worked but ffmpeg.exe was not in the zip.")
        return False
    except Exception as exc:
        log("FFmpeg download failed (%s)." % exc)
        log("The app still works, but sound needs FFmpeg — get it from ffmpeg.org and put ffmpeg.exe next to the app.")
        return False
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def do_uninstall(log=print):
    """Remove the installed app + shortcuts. Never touches recordings."""
    log("Uninstalling %s v%s..." % (APP_NAME, VERSION))
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/IM", EXE_NAME],
                       capture_output=True)
    target = install_dir()
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)
        log("Removed: %s" % target)
    else:
        log("Install folder was already gone.")
    for folder in (desktop_dir(), startmenu_dir()):
        link = os.path.join(folder, APP_NAME + ".lnk")
        if os.path.exists(link):
            try:
                os.remove(link)
                log("Removed shortcut: %s" % link)
            except OSError as exc:
                log("Could not remove %s (%s)" % (link, exc))
    log("Done. Your recordings were NOT deleted.")
    return True


def do_install(log, progress):
    """Full install. log(text) writes to the log, progress(0-100)
    moves the bar. Returns True on success."""
    if shutil.which("python") is None and shutil.which("py") is None:
        log("Python was not found. Install Python 3.12 from python.org")
        log("(tick 'Add Python to PATH' during install), then run this again.")
        return False
    py = sys.executable or "python"
    log("Using Python: %s" % py)
    progress(10)
    log("Step 1 of 5: installing libraries (first run only, needs internet once)...")
    if not _run([py, "-m", "pip", "install", "-r", "requirements.txt",
                 "pyinstaller", "--quiet"], log):
        log("Library install failed. Check your internet and try again.")
        return False
    progress(35)
    log("Step 2 of 5: building the app (this takes a minute or two)...")
    if not _run([py, "-m", "PyInstaller", "--noconfirm", "--clean",
                 "LiteGameRecorder.spec"], log):
        log("Build failed. The log above says why - send it to Muse.")
        return False
    exe = os.path.join(base_dir(), "dist", EXE_NAME)
    if not os.path.exists(exe):
        log("Build finished but %s was not found in dist\\" % EXE_NAME)
        return False
    progress(70)
    log("Step 3 of 5: installing to %s ..." % install_dir())
    os.makedirs(install_dir(), exist_ok=True)
    shutil.copy2(exe, os.path.join(install_dir(), EXE_NAME))
    # So the installed app can uninstall itself later.
    for name in ("installer.py", "Uninstall Lite Game Recorder.bat"):
        src = os.path.join(base_dir(), name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(install_dir(), name))
    # Ship the free example templates with the install, so the
    # editor's Templates tab can load them.
    tpl_src = os.path.join(base_dir(), "templates")
    if os.path.isdir(tpl_src):
        try:
            shutil.copytree(tpl_src, os.path.join(install_dir(), "templates"),
                            dirs_exist_ok=True)
        except Exception:
            pass
    # Ship the free sound-effects library too (the editor's Sounds
    # tab reads it from next to the installed exe).
    sfx_src = os.path.join(base_dir(), "sounds")
    if os.path.isdir(sfx_src):
        try:
            shutil.copytree(sfx_src, os.path.join(install_dir(), "sounds"),
                            dirs_exist_ok=True)
        except Exception:
            pass
    # Ship the 100 meme video clips too (the editor's Templates tab
    # "Meme videos" section reads them from next to the installed
    # exe), plus the script that renders them, so the editor's
    # "Make my meme card" box can make new ones.
    meme_src = os.path.join(base_dir(), "meme-videos")
    if os.path.isdir(meme_src):
        try:
            shutil.copytree(meme_src, os.path.join(install_dir(), "meme-videos"),
                            dirs_exist_ok=True)
        except Exception:
            pass
    for name in ("make_meme_videos.py",):
        src = os.path.join(base_dir(), name)
        if os.path.exists(src):
            try:
                shutil.copy2(src, os.path.join(install_dir(), name))
            except Exception:
                pass
    progress(78)
    log("Step 4 of 5: getting FFmpeg (for sound)...")
    download_ffmpeg(log, install_dir())
    progress(88)
    log("Step 5 of 5: creating Desktop and Start Menu shortcuts...")
    try:
        _make_shortcut(os.path.join(install_dir(), EXE_NAME),
                       os.path.join(desktop_dir(), APP_NAME + ".lnk"))
        _make_shortcut(os.path.join(install_dir(), EXE_NAME),
                       os.path.join(startmenu_dir(), APP_NAME + ".lnk"))
    except Exception as exc:
        log("Shortcut failed (%s) - the app itself is still installed." % exc)
    progress(100)
    log("")
    log("Done! %s v%s is installed." % (APP_NAME, VERSION))
    log("Double-click the '%s' icon on your Desktop to open it." % APP_NAME)
    return True


class SetupWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("%s v%s - Setup" % (APP_NAME, VERSION))
        self.geometry("660x800")
        self.resizable(False, False)
        self.configure(bg=INS_BG)
        self._busy = False

        # ---- coloured banner band ----
        banner = tk.Frame(self, bg=INS_BANNER, height=88)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        tk.Label(banner, text="🎮  %s" % APP_NAME, font=("Segoe UI", 24, "bold"),
                 bg=INS_BANNER, fg="white").pack(pady=(10, 0))
        tk.Label(banner, text="Version %s  •  Screen + Facecam + Live + Smart Record + Video Editor" % VERSION,
                 font=("Segoe UI", 11), bg=INS_BANNER, fg=INS_BANNER_SUB).pack(pady=(2, 0))
        tk.Frame(self, bg=INS_GREEN, height=3).pack(fill="x")

        # ---- subtitle + divider ----
        tk.Label(self, text="1 click Install  →  wait 2–3 minutes  →  double-click the Desktop icon.",
                 font=("Segoe UI", 11, "bold"), bg=INS_BG, fg=INS_GREEN).pack(pady=(14, 0))
        tk.Label(self, text="That's it — no black window, no typing. Your recordings are never deleted.",
                 font=("Segoe UI", 10), bg=INS_BG, fg=INS_MUTED).pack(pady=(2, 0))
        tk.Frame(self, bg=INS_BORDER, height=1).pack(fill="x", padx=28, pady=(14, 0))

        # ---- install steps stepper: numbered circles joined by a line ----
        steps_box = tk.Frame(self, bg=INS_PANEL, highlightbackground=INS_BORDER,
                             highlightthickness=1, bd=0)
        steps_box.pack(fill="x", padx=28, pady=(14, 0))
        tk.Label(steps_box, text="WHAT HAPPENS NEXT", font=("Segoe UI", 9, "bold"),
                 bg=INS_PANEL, fg=INS_MUTED).pack(anchor="w", padx=16, pady=(12, 6))
        self._steps_canvas = tk.Canvas(steps_box, bg=INS_PANEL,
                                       highlightthickness=0, bd=0,
                                       height=len(_INSTALL_STEPS) * 32)
        self._steps_canvas.pack(fill="x", pady=(0, 10))
        self._step_markers = []   # [(circle item, glyph item)] per step
        self._step_texts = []     # [label text item] per step
        self._step_lines = []     # [line item] below each step but the last
        for i, name in enumerate(_INSTALL_STEPS):
            y = 16 + i * 32
            if i < len(_INSTALL_STEPS) - 1:
                line = self._steps_canvas.create_line(
                    17, y + 12, 17, y + 32 - 12, fill=INS_BORDER, width=2)
                self._step_lines.append(line)
            circle = self._steps_canvas.create_oval(
                6, y - 11, 28, y + 11, fill=INS_PANEL, outline=INS_MUTED, width=2)
            glyph = self._steps_canvas.create_text(
                17, y, text=str(i + 1), font=("Segoe UI", 10, "bold"), fill=INS_MUTED)
            label = self._steps_canvas.create_text(
                40, y, text=name, font=("Segoe UI", 11), fill=INS_MUTED, anchor="w")
            self._step_markers.append((circle, glyph))
            self._step_texts.append(label)

        # ---- status + thick rounded progress bar with % ----
        self.status = tk.StringVar(value="Ready — press Install to start.")
        tk.Label(self, textvariable=self.status, font=("Segoe UI", 11, "bold"),
                 bg=INS_BG, fg=INS_TEXT).pack(pady=(12, 0))
        self.pct_var = tk.StringVar(value="0%")
        bar_row = tk.Frame(self, bg=INS_BG)
        bar_row.pack(fill="x", padx=28, pady=(6, 12))
        self.bar = _RoundedBar(bar_row, maximum=100,
                               on_change=lambda v: self.pct_var.set("%d%%" % round(v)))
        self.bar.pack(side="left", fill="x", expand=True)
        tk.Label(bar_row, textvariable=self.pct_var, font=("Segoe UI", 11, "bold"),
                 bg=INS_BG, fg=INS_GREEN, width=5, anchor="e").pack(side="left", padx=(10, 0))

        # ---- dark log box ----
        self.log = scrolledtext.ScrolledText(self, height=8, width=64,
                                             font=("Consolas", 9),
                                             bg=INS_LOG_BG, fg=INS_LOG_FG,
                                             insertbackground=INS_TEXT,
                                             relief="flat", bd=0,
                                             highlightthickness=1,
                                             highlightbackground=INS_BORDER,
                                             spacing1=2, spacing3=2,
                                             state="disabled")
        self.log.pack(fill="x", padx=28, pady=(0, 12))
        try:
            self.log.vbar.configure(bg=INS_PANEL2, troughcolor=INS_BG,
                                    activebackground=INS_BORDER,
                                    relief="flat", bd=0)
        except Exception:
            pass

        # ---- big Install button, then outline-style secondary buttons ----
        self.install_btn = tk.Button(self, text="⬇  Install", font=("Segoe UI", 14, "bold"),
                                     bg=INS_GREEN, fg="white",
                                     activebackground=INS_GREEN_HOVER,
                                     activeforeground="white",
                                     relief="flat", bd=0, height=2,
                                     command=self._on_install)
        self.install_btn.pack(fill="x", padx=28, pady=(0, 8))
        row = tk.Frame(self, bg=INS_BG)
        row.pack(fill="x", padx=28, pady=(0, 10))
        self.uninstall_btn = tk.Button(row, text="🗑  Uninstall", font=("Segoe UI", 11),
                                       bg=INS_PANEL2, fg=INS_TEXT,
                                       activebackground=INS_BORDER,
                                       activeforeground=INS_TEXT,
                                       relief="flat", bd=0,
                                       highlightthickness=1,
                                       highlightbackground=INS_BORDER,
                                       height=2, command=self._on_uninstall)
        self.uninstall_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.launch_btn = tk.Button(row, text="▶  Launch app", font=("Segoe UI", 11),
                                    bg=INS_PANEL2, fg=INS_TEXT,
                                    disabledforeground=INS_MUTED,
                                    activebackground=INS_BORDER,
                                    activeforeground=INS_TEXT,
                                    relief="flat", bd=0,
                                    highlightthickness=1,
                                    highlightbackground=INS_BORDER,
                                    height=2, state="disabled",
                                    command=self._on_launch)
        self.launch_btn.pack(side="left", fill="x", expand=True, padx=3)
        self.ffmpeg_btn = tk.Button(row, text="⬇  Get FFmpeg (sound)", font=("Segoe UI", 11),
                                    bg=INS_PANEL2, fg=INS_TEXT,
                                    activebackground=INS_BORDER,
                                    activeforeground=INS_TEXT,
                                    relief="flat", bd=0,
                                    highlightthickness=1,
                                    highlightbackground=INS_BORDER,
                                    height=2, command=self._on_ffmpeg)
        self.ffmpeg_btn.pack(side="left", fill="x", expand=True, padx=3)
        self.close_btn = tk.Button(row, text="Close", font=("Segoe UI", 11),
                                   bg=INS_PANEL2, fg=INS_TEXT,
                                   activebackground=INS_BORDER,
                                   activeforeground=INS_TEXT,
                                   relief="flat", bd=0,
                                   highlightthickness=1,
                                   highlightbackground=INS_BORDER,
                                   height=2, command=self.destroy)
        self.close_btn.pack(side="left", fill="x", expand=True, padx=(3, 0))

        # ---- footer ----
        tk.Label(self, text="Lite Game Recorder v%s  •  Free  •  Your recordings are never deleted" % VERSION,
                 font=("Segoe UI", 9), bg=INS_BG, fg=INS_MUTED).pack(pady=(0, 14))

        # Size the window to its content: font metrics differ between
        # Windows (real Segoe UI) and Linux (fallback font), so a
        # hardcoded height can clip the bottom buttons on one of
        # them. The window is fixed-size, so this runs once here.
        self.update_idletasks()
        need = self.winfo_reqheight()
        if need > 400:
            self.geometry("660x%d" % (need + 4))

    def _set_step(self, i, state):
        """Stepper state: 'todo' (numbered circle, muted),
        'active' (green circle, bold label), 'done' (green check)."""
        c = self._steps_canvas
        circle, glyph = self._step_markers[i]
        label = self._step_texts[i]
        if state == "done":
            c.itemconfig(circle, fill=INS_GREEN, outline=INS_GREEN)
            c.itemconfig(glyph, text="✓", fill="white")
            c.itemconfig(label, fill=INS_MUTED, font=("Segoe UI", 11))
            if i < len(self._step_lines):
                c.itemconfig(self._step_lines[i], fill=INS_GREEN)
        elif state == "active":
            c.itemconfig(circle, fill=INS_GREEN, outline=INS_GREEN)
            c.itemconfig(glyph, text=str(i + 1), fill="white")
            c.itemconfig(label, fill=INS_TEXT, font=("Segoe UI", 11, "bold"))
        else:
            c.itemconfig(circle, fill=INS_PANEL, outline=INS_MUTED)
            c.itemconfig(glyph, text=str(i + 1), fill=INS_MUTED)
            c.itemconfig(label, fill=INS_MUTED, font=("Segoe UI", 11))
            if i < len(self._step_lines):
                c.itemconfig(self._step_lines[i], fill=INS_BORDER)

    def _reset_steps(self):
        for i in range(len(_INSTALL_STEPS)):
            self._set_step(i, "todo")

    def _write(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", _shorten(text) + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        # do_install() logs "Step N of 5: ..." — tick the checklist off it.
        m = re.search(r"Step (\d) of 5", text)
        if m:
            n = int(m.group(1))
            for i in range(len(_INSTALL_STEPS)):
                self._set_step(i, "done" if i < n - 1 else
                               ("active" if i == n - 1 else "todo"))
        elif text.startswith("Done!"):
            for i in range(len(_INSTALL_STEPS)):
                self._set_step(i, "done")
        self.update_idletasks()

    def _set_progress(self, value):
        self.bar["value"] = value
        self.update_idletasks()

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.install_btn.configure(state=state)
        self.uninstall_btn.configure(state=state)

    def _on_ffmpeg(self):
        """Download FFmpeg into the install folder (for an existing
        install that has no sound). Runs in a thread so the window
        stays alive."""
        if self._busy:
            return
        self._set_busy(True)
        self.status.set("Getting FFmpeg (for sound)...")
        threading.Thread(target=self._ffmpeg_thread, daemon=True).start()

    def _ffmpeg_thread(self):
        ok = download_ffmpeg(self._write, install_dir())
        self.after(0, self._ffmpeg_done, ok)

    def _ffmpeg_done(self, ok):
        self._set_busy(False)
        if ok:
            self._set_step(3, "done")
        self.status.set("FFmpeg ready — sound will work now." if ok
                        else "FFmpeg download failed — see the log.")

    def _on_install(self):
        self._set_busy(True)
        self.bar["value"] = 0
        self._reset_steps()
        self.status.set("Installing...")
        threading.Thread(target=self._install_thread, daemon=True).start()

    def _install_thread(self):
        ok = do_install(self._write, self._set_progress)
        self.after(0, self._install_done, ok)

    def _install_done(self, ok):
        self._set_busy(False)
        if ok:
            for i in range(len(_INSTALL_STEPS)):
                self._set_step(i, "done")
            self.status.set("Installed! Double-click the Desktop icon.")
            self.launch_btn.configure(state="normal")
        else:
            self.status.set("Install failed - see the log above.")

    def _on_uninstall(self):
        if not messagebox.askyesno("Uninstall",
                                   "Remove %s and its Desktop + Start Menu icons?\n\n"
                                   "Your recordings will NOT be deleted." % APP_NAME):
            return
        self._set_busy(True)
        self._reset_steps()
        self.status.set("Uninstalling...")
        threading.Thread(target=self._uninstall_thread, daemon=True).start()

    def _uninstall_thread(self):
        do_uninstall(self._write)
        self.after(0, self._uninstall_done)

    def _uninstall_done(self):
        self._set_busy(False)
        self.bar["value"] = 100
        self.status.set("Uninstalled. Your recordings were not deleted.")

    def _on_launch(self):
        exe = os.path.join(install_dir(), EXE_NAME)
        if os.path.exists(exe):
            if sys.platform == "win32":
                os.startfile(exe)
            else:
                subprocess.Popen([exe])
        self.destroy()


def main():
    if "--uninstall" in sys.argv:
        do_uninstall()
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(APP_NAME, "Uninstalled.\n\nYour recordings were NOT deleted.")
            root.destroy()
        except Exception:
            pass
        return
    SetupWindow().mainloop()


if __name__ == "__main__":
    main()
