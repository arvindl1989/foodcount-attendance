#!/usr/bin/env sh
# One-command start: creates a virtualenv, installs dependencies, runs the app.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
pip install -q -r requirements.txt
exec python run.py
