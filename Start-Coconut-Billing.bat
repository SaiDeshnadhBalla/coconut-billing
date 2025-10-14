@echo off
setlocal
cd /d "%~dp0"

rem Ensure venv exists
if not exist ".venv\Scripts\python.exe" (
  echo [Setup] Creating virtual environment...
  py -m venv .venv
)

rem Upgrade pip and ensure dependencies (quiet)
echo [Setup] Ensuring dependencies (requirements.txt if present)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet --upgrade pip 1>nul 2>nul
if exist "requirements.txt" (
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet -r requirements.txt 1>nul 2>nul
) else (
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet "Flask>=2.2,<3.1" waitress 1>nul 2>nul
)

set HOST=127.0.0.1
set PORT=8000
set BROWSER_URL=http://127.0.0.1:%PORT%/

rem Prefer pythonw for no console window
set PYEXE=".venv\Scripts\pythonw.exe"
if not exist %PYEXE% set PYEXE=".venv\Scripts\python.exe"

echo [Start] Launching Coconut Billing on %BROWSER_URL%
start "Coconut Billing" %PYEXE% wsgi.py

endlocal
