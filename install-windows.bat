@echo off
REM ================================================================
REM  BREACHWRIGHT WINDOWS INSTALLER
REM  An Advent Cybersecurity Product
REM
REM  Installs to %LOCALAPPDATA%\Breachwright
REM  Creates Start Menu shortcut
REM ================================================================

echo.
echo  ========================================
echo   BREACHWRIGHT INSTALLER
echo   An Advent Cybersecurity Product
echo  ========================================
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\Breachwright"
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

REM Create install directory
echo [*] Installing to %INSTALL_DIR%
if exist "%INSTALL_DIR%" (
    echo [*] Removing previous installation...
    rmdir /s /q "%INSTALL_DIR%"
)
mkdir "%INSTALL_DIR%"

REM Copy all files
echo [*] Copying files...
xcopy /s /e /q /y "%~dp0*" "%INSTALL_DIR%\" >nul

REM Create data directory
set "DATA_DIR=%APPDATA%\Breachwright"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
if not exist "%DATA_DIR%\uploads" mkdir "%DATA_DIR%\uploads"
if not exist "%DATA_DIR%\reports" mkdir "%DATA_DIR%\reports"
if not exist "%DATA_DIR%\logs" mkdir "%DATA_DIR%\logs"
if not exist "%DATA_DIR%\backups" mkdir "%DATA_DIR%\backups"

if /i "%BREACHWRIGHT_SKIP_SHORTCUTS%"=="1" goto shortcuts_done

REM Create Start Menu shortcut using PowerShell
echo [*] Creating Start Menu shortcut...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%START_MENU%\Breachwright.lnk'); $s.TargetPath = '%INSTALL_DIR%\Breachwright.exe'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Breachwright - AI Pentest Management'; $s.IconLocation = '%INSTALL_DIR%\icon.ico'; $s.Save()"

REM Create Desktop shortcut
echo [*] Creating Desktop shortcut...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Breachwright.lnk'); $s.TargetPath = '%INSTALL_DIR%\Breachwright.exe'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Breachwright - AI Pentest Management'; $s.IconLocation = '%INSTALL_DIR%\icon.ico'; $s.Save()"

:shortcuts_done

REM Copy uninstaller
copy /Y "%~dp0uninstall-windows.bat" "%INSTALL_DIR%\" >nul 2>&1

echo.
echo  ========================================
echo   INSTALLATION COMPLETE
echo  ========================================
echo.
echo   Installed to: %INSTALL_DIR%
echo   Data stored in: %DATA_DIR%
echo.
echo   1. First time setup:
echo      Open Breachwright from Start Menu or Desktop
echo      Or run: "%INSTALL_DIR%\Breachwright.exe" --setup
echo.
echo   2. Launch:
echo      Double-click the Breachwright shortcut
echo      Or run: "%INSTALL_DIR%\Breachwright.exe"
echo.
echo  ========================================
echo.

if /i not "%BREACHWRIGHT_NONINTERACTIVE%"=="1" pause
