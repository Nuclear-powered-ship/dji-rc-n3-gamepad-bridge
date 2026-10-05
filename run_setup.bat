@echo off
setlocal enabledelayedexpansion
title RC-N3 Gamepad Bridge - One-Shot Setup
cd /d "%~dp0"

rem ============================================================
rem  NOTE: ASCII-only on purpose. cmd.exe decodes each line of a
rem  .bat with the OEM code page (936 on zh-CN), so non-ASCII
rem  bytes corrupt parsing before any later chcp can take effect.
rem  All Chinese output comes from the Python scripts.
rem ============================================================

echo ============================================================
echo   DJI RC-N3  to  Xbox 360 Gamepad  -  One-Shot Setup
echo ============================================================
echo.

set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :gotpy
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :gotpy
)
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    goto :gotpy
)
if exist "%LOCALAPPDATA%\Programs\Python\Python39\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    goto :gotpy
)
where python > nul 2>&1 && set "PY=python"

:gotpy
if not defined PY (
    echo.
    echo [ERROR] Python 3.9 - 3.12 not found.
    echo.
    echo Install from https://www.python.org/downloads/
    echo IMPORTANT: tick "Add Python to PATH" during install.
    echo NOTE: vgamepad does not build on Python 3.13 or newer.
    echo.
    pause
    exit /b 1
)

echo [1/3] Using Python: %PY%
%PY% --version
echo.

echo [2/3] Checking dependencies
%PY% -c "import serial, vgamepad" > nul 2>&1
if errorlevel 1 (
    echo       installing, this may take a minute...
    %PY% -m pip install --upgrade pip
    %PY% -m pip install vgamepad pyserial
    if errorlevel 1 (
        echo.
        echo [ERROR] Installation failed. Run manually:
        echo    %PY% -m pip install vgamepad pyserial
        echo.
        pause
        exit /b 1
    )
    echo       done
) else (
    echo       already installed
)
echo.

echo [3/3] Environment check
echo.
%PY% scripts\check_env.py
echo.

echo ============================================================
echo   SETUP DONE
echo ============================================================
echo.
echo Next steps:
echo.
echo   1. Power on the remote, plug the BOTTOM Type-C port
echo      The bundled cable is for phones. You need a USB-A to Type-C data cable.
echo.
echo   2. Make sure DJI Assistant 2 is NOT running
echo      It holds the serial port and will block the bridge.
echo.
echo   3. Run the self-test
echo      Type "cmd" into this folder's address bar and press Enter,
echo      then type:  run_bridge.bat --selftest
echo.
echo   4. If the self-test passes, double-click run_bridge.bat
echo      and keep that window open while playing.
echo.
echo See README.md for details
echo.
pause
