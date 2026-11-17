@echo off
REM ============================================================
REM  Uninstall Lite Game Recorder v2.3 (Windows)
REM  Double-click this file. It closes the app if it is running,
REM  then removes the installed app folder and the Desktop +
REM  Start Menu icons. Your recordings are NEVER deleted.
REM  (A small window pops up when it is done.)
REM ============================================================
taskkill /F /IM LiteGameRecorder.exe >nul 2>nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found, so the automatic uninstall cannot run.
  echo Manual uninstall: delete these two things:
  echo   %LOCALAPPDATA%\Programs\LiteGameRecorder
  echo   Desktop icon "Lite Game Recorder" + Start Menu icon
  pause
  exit /b 1
)
start "" pythonw installer.py --uninstall
