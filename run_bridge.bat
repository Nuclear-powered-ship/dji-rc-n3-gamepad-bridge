@echo off
setlocal enabledelayedexpansion
title RC-N3 Bridge - Low Latency (Do Not Close)
cd /d "%~dp0"

rem ============================================================
rem  NOTE: This file is intentionally ASCII-only.
rem  cmd.exe parses a .bat line by line and decodes each line
rem  with the OEM code page (936 on zh-CN) BEFORE chcp takes
rem  effect on a later line. Any non-ASCII byte here corrupts
rem  parsing and produces errors like 'xit' or 'ss'.
rem  All Chinese output comes from the Python scripts instead.
rem ============================================================

echo ============================================================
echo   DJI RC-N3  to  Xbox 360 Gamepad  -  Low Latency Bridge
echo   Latency: 0.4 - 5 ms
echo ============================================================
echo.

if /i "%~1"=="--selftest" goto :selftest

rem ------------------------------------------------------------
rem  Kill stale bridge processes. wmic was removed in Win11 24H2,
rem  so use PowerShell Get-CimInstance instead.
rem ------------------------------------------------------------
echo Releasing COM6 / freeing serial port...
for /f "usebackq delims=" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*main_fast*' } | ForEach-Object { $_.ProcessId }" 2^>nul`) do (
    if not "%%p"=="" (
        echo   killing stale PID %%~p
        taskkill /F /PID %%~p > nul 2>&1
    )
)
echo.

rem ------------------------------------------------------------
rem  Locate Python. Hardcode absolute paths first because the
rem  python on PATH may be a different install without deps.
rem ------------------------------------------------------------
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
    echo Install it from https://www.python.org/downloads/
    echo IMPORTANT: tick "Add Python to PATH" during install.
    echo NOTE: vgamepad does not build on Python 3.13 or newer.
    echo.
    echo [ERROR] The bridge will not start until Python is installed.
    echo.
    pause
    exit /b 1
)

echo Using Python: %PY%
%PY% --version
echo.

rem ------------------------------------------------------------
rem  Dependencies
rem ------------------------------------------------------------
%PY% -c "import serial, vgamepad" > nul 2>&1
if errorlevel 1 (
    echo Installing dependencies, this may take a minute...
    %PY% -m pip install --upgrade pip
    %PY% -m pip install vgamepad pyserial
    if errorlevel 1 (
        echo.
        echo [ERROR] Dependency installation failed.
        echo Run this manually:
        echo    %PY% -m pip install vgamepad pyserial
        echo.
        pause
        exit /b 1
    )
    echo Dependencies installed.
    echo.
)

echo ------------------------------------------------------------
echo   Closing this window removes the virtual gamepad.
echo   If the game sees no controller, close this first.
echo ------------------------------------------------------------
echo.
echo Optional flags:
echo     --invert lv rh     invert the named axes
echo     --deadzone 300     remove centre drift
echo     --scale 0.8        lower sensitivity
echo.
echo Self-test:  run_bridge.bat --selftest
echo.

:retry
echo [start] %date% %time%
%PY% scripts\main_fast.py --rate 2
set "EXITCODE=%ERRORLEVEL%"

echo.
echo ============================================================
echo   Bridge stopped.  Exit code %EXITCODE%
echo ============================================================
echo.

if "%EXITCODE%"=="0" (
    echo Normal exit.
    pause
    exit /b 0
)

echo Retrying in 5 seconds...
echo.
echo If this keeps failing, check:
echo   1. Remote powered on, cable in the BOTTOM Type-C port
echo   2. DJI Assistant 2 not running in the background
echo   3. COM6 still present in Device Manager
echo   4. Or run:  run_bridge.bat --selftest
echo.
timeout /t 5 /nobreak > nul
goto retry


rem ===============================================================
rem  Self-test mode
rem ===============================================================
:selftest
set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PY where python > nul 2>&1 && set "PY=python"
if not defined PY (
    echo.
    echo [ERROR] Python 3.9 - 3.12 not found.
    echo Install from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

chcp 65001 > nul

echo ============================================================
echo   SELF-TEST
echo ============================================================
echo.

echo [1/4] Python version
%PY% --version
echo.

echo [2/4] Dependencies
%PY% -c "import serial; print('      pyserial', serial.__version__)" 2>&1
if errorlevel 1 echo       [FAIL] pyserial missing
%PY% -c "import vgamepad; print('      vgamepad OK')" 2>&1
if errorlevel 1 echo       [FAIL] vgamepad missing
echo.

echo [3/4] Virtual gamepad driver
if exist "C:\Windows\System32\drivers\ViGEmBus.sys" (
    echo       ViGEmBus.sys present
) else (
    echo       [FAIL] ViGEmBus missing
    echo       Download: https://github.com/nefarius/ViGEmBus/releases
)
echo.

echo [4/4] Serial ports
%PY% -c "import serial.tools.list_ports as lp; ps=list(lp.comports()); print('      no serial port found' if not ps else ''); [print('      ', p.device, '|', p.description) for p in ps]" 2>&1
echo.

echo ------------------------------------------------------------
echo   Running bridge for 8 seconds
echo   Latency should settle at 0.4 - 5 ms
echo   Latency should settle at 0.4 - 5 ms
echo ------------------------------------------------------------
echo.

%PY% scripts\main_fast.py --rate 2 --selftest --selftest-seconds 8
set "EXITCODE=%ERRORLEVEL%"

echo.
echo ============================================================
echo   VERDICT
echo ============================================================
echo.
if "%EXITCODE%"=="0" (
    echo   [PASS] Environment is ready.
    echo   [PASS] Environment is ready. Double-click run_bridge.bat to play.
) else (
    echo   [FAIL] Something is wrong, exit code %EXITCODE%
    echo   [FAIL] Something failed. Check each [FAIL] item above.
)
echo.
echo ============================================================
echo.
pause
exit /b %EXITCODE%
