#!/usr/bin/env bash
# One-step setup and run: creates a virtual environment, installs everything including the OCR engine, starts the server.
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
echo "Open http://localhost:8000  (officials page: http://localhost:8000/officials.html)"
python -m uvicorn main:app --port 8000
