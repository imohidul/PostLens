@echo off
setlocal
cd /d "%~dp0"
echo.
echo  Installing PostLens...
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo  Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH" during setup. Then run this file again.
  pause
  exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo  PostLens needs Python 3.10 or newer.
  python --version
  pause
  exit /b 1
)

if not exist .venv (
  echo  [1/3] Creating a private Python environment in .venv
  python -m venv .venv || goto :fail
)

echo  [2/3] Installing Python packages
.venv\Scripts\python -m pip install --upgrade pip >nul
.venv\Scripts\python -m pip install -r requirements.txt || goto :fail

echo  [3/3] Downloading the browser PostLens uses (about 150 MB, one time)
.venv\Scripts\python -m playwright install chromium || goto :fail

echo.
echo  Done. Double-click run.bat to start PostLens.
echo.
pause
exit /b 0

:fail
echo.
echo  Installation failed. Scroll up to see the error.
pause
exit /b 1
