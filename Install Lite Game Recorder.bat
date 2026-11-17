@echo off
REM ============================================================
REM  Lite Game Recorder v2.3 - Setup (Windows)
REM  Double-click this file. A setup WINDOW opens (no black
REM  terminal) with Install and Uninstall buttons, a progress
REM  bar and a log that shows what is happening.
REM  Install: libraries + build the app + Desktop icon.
REM  Uninstall: removes the app + icons, keeps your recordings.
REM ============================================================
title Lite Game Recorder v2.3 - Setup
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found.
  echo Please install Python 3.12 from https://www.python.org/downloads/
  echo IMPORTANT: tick "Add Python to PATH" during install, then run this again.
  pause
  exit /b 1
)
REM pythonw = no terminal window at all. If it fails, fall back to
REM python so the error stays visible instead of vanishing.
start "" pythonw installer.py
if errorlevel 1 python installer.py
