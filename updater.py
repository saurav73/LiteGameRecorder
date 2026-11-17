"""Built-in auto-updater: install once, update in place.

Checks GitHub Releases for a newer version, downloads the zip for
this OS, verifies it, and swaps the app files in place with a small
helper script (a running exe cannot replace itself on Windows).
User data is never touched: config.json, the Recordings folder, and
anything the user added all survive, because the swap only ever
copies files that come in the release zip. Nothing is replaced until
the download is verified and unpacked.

In-place update only works for the installed (frozen) app. Running
from source, the check still works but the UI points at the
releases page instead of swapping files.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from app_version import __version__, get_app_dir

REPO = "saurav73/LiteGameRecorder"
LATEST_API = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASES_PAGE = "https://github.com/%s/releases" % REPO
USER_AGENT = "LiteTutorialMaker-updater"

_OS_ASSET_KEYS = {"win32": "Windows", "darwin": "macOS"}

# What the updater expects at the root of a valid release zip for
# each OS (checked before anything is replaced).
EXPECTED_APP = {
    "Windows": "LiteGameRecorder.exe",
    "macOS": "LiteGameRecorder.app/Contents/MacOS/LiteGameRecorder",
    "Linux": "LiteGameRecorder",
}

_EXE_NAME = {"Windows": "LiteGameRecorder.exe",
             "macOS": "LiteGameRecorder.app",
             "Linux": "LiteGameRecorder"}


class UpdateError(Exception):
    """An update step failed. Message is safe to show the user."""


class UpdateCancelled(UpdateError):
    """The user cancelled the update."""


def os_key(platform=None):
    """Which release asset this OS needs: Windows, macOS or Linux."""
    return _OS_ASSET_KEYS.get(platform or sys.platform, "Linux")


def parse_version(s):
    """Parse a version string for comparison. Prefers packaging when
    available, falls back to a plain numeric tuple."""
    s = str(s).strip().lstrip("vV")
    try:
        from packaging.version import parse as _parse
        return _parse(s)
    except Exception:
        parts = []
        for chunk in s.replace("-", ".").split("."):
            try:
                parts.append(int(chunk))
            except ValueError:
                parts.append(0)
        return tuple(parts)


def is_newer(latest, current):
    """True when the latest version is newer than the current one."""
    try:
        return parse_version(latest) > parse_version(current)
    except Exception:
        return False


def pick_asset(assets, key):
    """Pick the release asset for this OS: a .zip whose name contains
    the OS key (Windows, macOS or Linux). Returns None when the
    release has no build for this OS yet."""
    key = key.lower()
    for asset in assets or []:
        name = (asset.get("name") or "")
        if name.lower().endswith(".zip") and key in name.lower():
            return asset
    return None


def _short_error(exc):
    """Turn a network/API error into one short user-facing line."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (403, 429):
            return "GitHub refused the check for now (rate limit). Try again later."
        return "GitHub answered with an error (HTTP %d)." % exc.code
    if isinstance(exc, urllib.error.URLError):
        return "Could not reach GitHub. Check your internet connection."
    if isinstance(exc, TimeoutError):
        return "The check timed out. Check your internet connection."
    if isinstance(exc, json.JSONDecodeError):
        return "GitHub answered, but the reply was not readable."
    return "Could not check for updates (%s)." % exc


def check_for_update(current_version=None, platform=None):
    """Ask GitHub Releases for the latest version. Never raises:
    network or API problems come back as an error string.

    Returns a dict: available (a newer version exists), latest (the
    version string), url (download URL of this OS's zip), asset (its
    file name), size (bytes, may be None), no_asset (a newer version
    exists but the release has no build for this OS yet), error.
    """
    current_version = current_version or __version__
    key = os_key(platform)
    result = {"available": False, "latest": None, "url": None,
              "asset": None, "size": None, "no_asset": False,
              "error": None}
    try:
        req = urllib.request.Request(LATEST_API,
                                     headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        result["error"] = _short_error(exc)
        return result
    tag = (data.get("tag_name") or "").strip()
    if not tag:
        result["error"] = "The release info had no version tag."
        return result
    latest = tag.lstrip("vV")
    result["latest"] = latest
    if not is_newer(latest, current_version):
        return result
    asset = pick_asset(data.get("assets") or [], key)
    if asset is None:
        result["available"] = True
        result["no_asset"] = True
        return result
    result["available"] = True
    result["url"] = asset.get("browser_download_url")
    result["asset"] = asset.get("name")
    result["size"] = asset.get("size")
    return result


def download(url, dest, progress=None, cancel=None):
    """Download url to dest (a Path). progress(downloaded, total) is
    called after each chunk; total may be 0 when unknown. When
    cancel() returns True the download aborts. Raises UpdateError
    (or UpdateCancelled) on failure; a partial file is removed."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
    except Exception as exc:
        raise UpdateError(_short_error(exc))
    total = 0
    try:
        total = int(resp.headers.get("Content-Length") or 0)
    except Exception:
        total = 0
    downloaded = 0
    try:
        with open(dest, "wb") as f:
            while True:
                if cancel is not None and cancel():
                    raise UpdateCancelled("Download cancelled.")
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress is not None:
                    progress(downloaded, total)
    except BaseException:
        try:
            os.remove(dest)
        except Exception:
            pass
        raise
    if total and downloaded != total:
        try:
            os.remove(dest)
        except Exception:
            pass
        raise UpdateError("Download incomplete (%d of %d bytes)."
                          % (downloaded, total))
    return downloaded


def validate_zip(path, key=None):
    """(ok, error). A valid release zip opens, passes testzip, and
    contains the expected app executable for this OS."""
    key = key or os_key()
    expected = EXPECTED_APP[key]
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                return False, ("The download is corrupt "
                               "(bad file inside: %s)." % bad)
            if expected not in set(zf.namelist()):
                return False, ("The download is not a Lite Tutorial "
                               "Maker release for %s." % key)
    except zipfile.BadZipFile:
        return False, "The download is not a valid zip file."
    except Exception as exc:
        return False, "Could not read the download: %s" % exc
    return True, ""


def extract_with_permissions(zip_path, dest):
    """Extract a zip, restoring Unix permission bits and symlinks.
    Plain zipfile extraction drops the +x bit (leaving the new binary
    unlaunchable on macOS/Linux) and turns symlinks into regular
    files (breaking the .app bundle's Frameworks). AppleDouble
    (__MACOSX) entries and .DS_Store files are skipped."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            if name.startswith("__MACOSX/") or name.endswith(".DS_Store"):
                continue
            target = dest / name
            mode = (info.external_attr >> 16) & 0o7777
            is_link = ((info.external_attr >> 16) & 0o170000) == 0o120000
            if is_link:
                link_to = zf.read(info).decode("utf-8", "replace")
                try:
                    if target.exists() or target.is_symlink():
                        target.unlink()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(link_to, target)
                except Exception:
                    pass
                continue
            zf.extract(info, dest)
            if mode:
                try:
                    os.chmod(target, mode)
                except Exception:
                    pass


def _staged_app_ok(stage, key):
    """The unpacked update really contains the app binary."""
    stage = Path(stage)
    if key == "macOS":
        return (stage / "LiteGameRecorder.app" / "Contents" / "MacOS"
                / "LiteGameRecorder").is_file()
    name = "LiteGameRecorder.exe" if key == "Windows" else "LiteGameRecorder"
    return (stage / name).is_file()


def helper_script_text(app_dir, stage_dir, pid, key):
    """The helper script that swaps the files once the app exits.
    Takes the app folder, the staged update folder, and the app's
    process id. Returns (file name, script text). The script waits
    for the app process to exit, copies the staged files over the
    app folder (never deleting anything, so config.json, Recordings/
    and user-added files survive), relaunches the app, deletes the
    staging folder and then itself."""
    if key == "Windows":
        text = (
            "@echo off\n"
            "setlocal EnableDelayedExpansion\n"
            "REM Lite Tutorial Maker updater: swap in the new version.\n"
            "set \"APP_DIR=%s\"\n"
            "set \"STAGE_DIR=%s\"\n"
            "set \"APP_PID=%d\"\n"
            ":waitloop\n"
            "tasklist /FI \"PID eq %%APP_PID%%\" 2>nul | find \"%%APP_PID%%\" >nul\n"
            "if not errorlevel 1 (\n"
            "  timeout /t 1 /nobreak >nul\n"
            "  goto waitloop\n"
            ")\n"
            "xcopy \"%%STAGE_DIR%%\\*\" \"%%APP_DIR%%\\\" /E /Y /Q >nul 2>&1\n"
            "REM The exe can briefly stay locked if another copy of the\n"
            "REM app is running, so retry it a few times.\n"
            "set TRIES=0\n"
            ":exeloop\n"
            "copy /Y \"%%STAGE_DIR%%\\LiteGameRecorder.exe\" \"%%APP_DIR%%\\LiteGameRecorder.exe\" >nul 2>&1\n"
            "if errorlevel 1 (\n"
            "  set /a TRIES+=1\n"
            "  if !TRIES! LSS 10 (\n"
            "    timeout /t 1 /nobreak >nul\n"
            "    goto exeloop\n"
            "  )\n"
            ")\n"
            "start \"\" \"%%APP_DIR%%\\LiteGameRecorder.exe\"\n"
            "rmdir /S /Q \"%%STAGE_DIR%%\" >nul 2>&1\n"
            "(goto) 2>nul & del \"%%~f0\"\n"
            % (app_dir, stage_dir, pid)
        )
        return "update_helper.bat", text
    app_q = shlex.quote(str(app_dir))
    stage_q = shlex.quote(str(stage_dir))
    text = (
        "#!/bin/sh\n"
        "# Lite Tutorial Maker updater: swap in the new version.\n"
        "APP_DIR=%s\n"
        "STAGE_DIR=%s\n"
        "APP_PID=%d\n"
        "while kill -0 \"$APP_PID\" 2>/dev/null; do sleep 1; done\n"
        "# macOS .app bundle: replace the whole bundle (it holds only\n"
        "# app files; config and recordings live next to it, never\n"
        "# inside it). ditto keeps the bundle's symlinks intact.\n"
        "if [ -d \"$STAGE_DIR/LiteGameRecorder.app\" ]; then\n"
        "  rm -rf \"$APP_DIR/LiteGameRecorder.app\"\n"
        "  ditto \"$STAGE_DIR/LiteGameRecorder.app\" \"$APP_DIR/LiteGameRecorder.app\" 2>/dev/null \\\n"
        "    || cp -R \"$STAGE_DIR/LiteGameRecorder.app\" \"$APP_DIR/LiteGameRecorder.app\"\n"
        "  chmod +x \"$APP_DIR/LiteGameRecorder.app/Contents/MacOS/LiteGameRecorder\" 2>/dev/null || true\n"
        "  rm -rf \"$STAGE_DIR/LiteGameRecorder.app\"\n"
        "fi\n"
        "cp -R \"$STAGE_DIR\"/. \"$APP_DIR\"/\n"
        "chmod +x \"$APP_DIR/LiteGameRecorder\" \"$APP_DIR/ffmpeg\" 2>/dev/null || true\n"
        "rm -rf \"$STAGE_DIR\"\n"
        "if [ -d \"$APP_DIR/LiteGameRecorder.app\" ]; then\n"
        "  open \"$APP_DIR/LiteGameRecorder.app\" 2>/dev/null || true\n"
        "else\n"
        "  \"$APP_DIR/LiteGameRecorder\" >/dev/null 2>&1 &\n"
        "fi\n"
        "( sleep 2; rm -f \"$0\" ) &\n"
        "exit 0\n"
        % (app_q, stage_q, pid)
    )
    return "update_helper.sh", text


def write_helper(app_dir, stage_dir, pid, key):
    """Write the helper script into the app folder. Returns its path."""
    name, text = helper_script_text(app_dir, stage_dir, pid, key)
    path = Path(app_dir) / name
    path.write_text(text, encoding="utf-8")
    if key != "Windows":
        try:
            os.chmod(path, 0o755)
        except Exception:
            pass
    return path


def launch_helper(path):
    """Start the helper script detached, so it outlives this process."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        subprocess.Popen(
            ["cmd", "/c", str(path)],
            startupinfo=si,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                           | subprocess.DETACHED_PROCESS),
            close_fds=True)
    else:
        subprocess.Popen(["/bin/sh", str(path)], start_new_session=True,
                         close_fds=True, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)


def apply_update(zip_path, key=None):
    """Verify, unpack and stage an update, then launch the helper
    that swaps the files once this process exits. Returns
    (ok, error). On success the caller MUST quit the app promptly so
    the helper can replace the files. Nothing is replaced until the
    download is verified and unpacked."""
    if not getattr(sys, "frozen", False):
        return False, ("In-place updates only work for the installed "
                       "app, not a source checkout.")
    key = key or os_key()
    app_dir = get_app_dir()
    ok, err = validate_zip(zip_path, key)
    if not ok:
        return False, err
    stage = Path(tempfile.mkdtemp(prefix="lgr-update-"))
    try:
        extract_with_permissions(zip_path, stage)
    except Exception as exc:
        shutil.rmtree(stage, ignore_errors=True)
        return False, "Could not unpack the update: %s" % exc
    if not _staged_app_ok(stage, key):
        shutil.rmtree(stage, ignore_errors=True)
        return False, "The unpacked update is missing the app itself."
    try:
        helper = write_helper(app_dir, stage, os.getpid(), key)
        launch_helper(helper)
    except Exception as exc:
        shutil.rmtree(stage, ignore_errors=True)
        return False, "Could not start the updater: %s" % exc
    return True, ""
