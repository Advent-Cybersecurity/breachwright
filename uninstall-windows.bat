@echo off
REM ================================================================
REM  BREACHWRIGHT WINDOWS UNINSTALLER
REM  An Advent Cybersecurity Product
REM ================================================================

echo.
echo  ========================================
echo   BREACHWRIGHT UNINSTALLER
echo  ========================================
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\Breachwright"
set "DATA_DIR=%APPDATA%\Breachwright"
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

echo This will remove Breachwright from your system.
echo.
echo   Install directory: %INSTALL_DIR%
echo   Data directory:    %DATA_DIR%
echo.

if /i "%BREACHWRIGHT_CONFIRM_UNINSTALL%"=="1" goto uninstall_confirmed
set /p CONFIRM="Remove Breachwright? (y/n): "
if /i not "%CONFIRM%"=="y" (
    echo Cancelled.
    if /i not "%BREACHWRIGHT_NONINTERACTIVE%"=="1" pause
    exit /b 0
)

:uninstall_confirmed

REM Remove Start Menu shortcut
if /i not "%BREACHWRIGHT_SKIP_SHORTCUTS%"=="1" if exist "%START_MENU%\Breachwright.lnk" (
    del "%START_MENU%\Breachwright.lnk"
    echo [+] Start Menu shortcut removed
)

REM Remove Desktop shortcut
if /i not "%BREACHWRIGHT_SKIP_SHORTCUTS%"=="1" powershell -NoProfile -Command "$desktop = [Environment]::GetFolderPath('Desktop'); $lnk = Join-Path $desktop 'Breachwright.lnk'; if (Test-Path $lnk) { Remove-Item $lnk; Write-Host '[+] Desktop shortcut removed' }"

REM Remove install directory
if exist "%INSTALL_DIR%" (
    rmdir /s /q "%INSTALL_DIR%"
    echo [+] Application files removed
)

echo.
if /i "%BREACHWRIGHT_REMOVE_DATA%"=="1" goto remove_data
if /i "%BREACHWRIGHT_REMOVE_DATA%"=="0" goto preserve_data
set /p REMOVEDATA="Also remove your data (database, settings, reports)? (y/n): "
if /i "%REMOVEDATA%"=="y" goto remove_data

:preserve_data
echo [*] Data preserved at %DATA_DIR%
goto data_choice_done

:remove_data
if exist "%DATA_DIR%" (
    rmdir /s /q "%DATA_DIR%"
    echo [+] Data directory removed
)

:data_choice_done

echo.
echo  ========================================
echo   UNINSTALL COMPLETE
echo  ========================================
echo.

if /i not "%BREACHWRIGHT_NONINTERACTIVE%"=="1" pause
