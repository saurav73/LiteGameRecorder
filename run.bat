@echo off
REM Run Lite Tutorial Maker from source (Windows).
REM Needs Python 3.11+ and internet on the first run (to install the
REM libraries into a .venv next to this file). After that, just run it.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 from https://www.python.org/downloads/
  echo IMPORTANT: tick "Add Python to PATH" during install, then run this again.
  pause
  exit /b 1
)
if not exist .venv (
  python -m venv .venv
  if errorlevel 1 (
    echo Could not create a virtual environment.
    pause
    exit /b 1
  )
)
.venv\Scripts\python -m pip install --upgrade pip --quiet
.venv\Scripts\python -m pip install -r requirements.txt --quiet
.venv\Scripts\python app.py
pause
