@echo off
REM ================================================================
REM  Breachwright Windows Build Script
REM  An Advent Cybersecurity Product
REM
REM  Prerequisites:
REM    1. Python 3.11+ installed and on PATH
REM    2. Node.js 18+ installed and on PATH
REM    3. Run from project root: build-windows.bat
REM ================================================================

echo.
echo  ========================================
echo   BREACHWRIGHT WINDOWS BUILD
echo   An Advent Cybersecurity Product
echo  ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ and add to PATH.
    exit /b 1
)

REM Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install Node.js 18+ and add to PATH.
    exit /b 1
)

REM Create venv if it doesn't exist
if not exist ".venv" (
    echo [*] Creating virtual environment...
    python -m venv .venv
)

REM Activate venv
call .venv\Scripts\activate.bat

REM Install dependencies
echo [*] Installing Python dependencies...
pip install -r backend\requirements.txt pyinstaller pywebview[cef] pythonnet >nul 2>&1

REM Build frontend
echo [*] Building frontend...
cd frontend
if not exist "node_modules" (
    call npm install
)
call npm run build
cd ..

if not exist "frontend\dist\index.html" (
    echo [ERROR] Frontend build failed - frontend\dist\index.html not found
    exit /b 1
)

REM Run PyInstaller
echo [*] Running PyInstaller...
pyinstaller breachwright-windows.spec --noconfirm

if not exist "dist\Breachwright\Breachwright.exe" (
    echo [ERROR] PyInstaller build failed
    exit /b 1
)

REM Copy install script and uninstall script
copy /Y install-windows.bat dist\Breachwright\ >nul 2>&1
copy /Y uninstall-windows.bat dist\Breachwright\ >nul 2>&1
copy /Y icon.ico dist\Breachwright\ >nul 2>&1
copy /Y icon.png dist\Breachwright\ >nul 2>&1

echo.
echo  ========================================
echo   BUILD COMPLETE
echo  ========================================
echo   Output: dist\Breachwright\
echo   Run:    dist\Breachwright\Breachwright.exe
echo  ========================================
echo.

REM Deactivate venv
deactivate
