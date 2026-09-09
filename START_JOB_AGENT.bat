@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo First run: creating the Python environment...
 py -3.12 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python -m agents.cli init-db
start "Tumelo Job Agent Scheduler" /min cmd /k "call .venv\Scripts\activate.bat && python -m agents.scheduler"
start "Tumelo Job Agent Dashboard" cmd /k "call .venv\Scripts\activate.bat && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
timeout /t 3 /nobreak >nul
start "" http://localhost:8000
endlocal
