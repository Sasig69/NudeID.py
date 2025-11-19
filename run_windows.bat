@echo off
REM Run this to create a venv (if needed), install requirements, start the server, and open the browser.

setlocal

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
  echo Python not found in PATH. Please install Python 3.8+ and re-run this script.
  pause
  exit /b 1
)

REM Create venv if missing
if not exist ".venv\Scripts\activate.bat" (
  echo Creating virtual environment .venv...
  python -m venv .venv
)

REM Activate venv for pip install steps
echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip

if exist requirements.txt (
  echo Installing dependencies from requirements.txt...
  pip install -r requirements.txt
) else (
  echo requirements.txt not found; skipping pip install.
)

REM Start server in a new window so console output stays visible
echo Starting server in a new window...
start "Moderator Server" cmd /k ".venv\Scripts\python.exe NudeID.py"

REM Give server a moment and open browser
timeout /t 2 >nul
echo Opening browser to http://127.0.0.1:5000 ...
start http://127.0.0.1:5000

echo All done. Server is running in a separate window.
exit /b 0
