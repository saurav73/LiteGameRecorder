#!/bin/sh
# Run Lite Tutorial Maker from source (macOS / Linux).
# Needs Python 3.11+ and internet on the first run (to install the
# libraries into a .venv next to this file). After that, just run it.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Get it from https://www.python.org/downloads/ and run this again."
  exit 1
fi
if [ ! -d .venv ]; then
  python3 -m venv .venv || { echo "Could not create a virtual environment. Install python3-venv and try again."; exit 1; }
fi
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt --quiet
.venv/bin/python app.py
