@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe python -m venv .venv
call .venv\Scripts\activate
python -m pip install -r requirements.txt
echo.
echo Open http://localhost:8000  (officials page: http://localhost:8000/officials.html)
python -m uvicorn main:app --port 8000
pause
