@echo off
REM Build a single windowed .exe (no Python needed to run it afterwards,
REM and no terminal window when you run it).
REM Easiest way: double-click "Install Lite Game Recorder.bat" instead -
REM it builds this AND installs it with Desktop + Start Menu icons.
title Build Lite Game Recorder EXE
cd /d "%~dp0"
set PY=python
python --version >nul 2>&1
if errorlevel 1 set PY=py
%PY% -m pip install -r requirements.txt pyinstaller --quiet
%PY% -m PyInstaller --noconfirm --clean LiteGameRecorder.spec
echo.
echo Done! Your app is: dist\LiteGameRecorder.exe
echo Double-click it to run - no terminal window appears.
pause
