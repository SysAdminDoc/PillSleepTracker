@echo off
setlocal EnableDelayedExpansion
title PillSleepTracker Pro - Launcher
color 0B
mode con cols=62 lines=20

echo.
echo   ====================================================
echo    PillSleepTracker Pro - Desktop Health Widget v2.0
echo   ====================================================
echo.

:: ── Locate Python ────────────────────────────────────────
set "PY="
where pythonw >nul 2>&1 && set "PY=pythonw" && goto :found
where python  >nul 2>&1 && set "PY=python"  && goto :found
where python3 >nul 2>&1 && set "PY=python3" && goto :found

:: Check common install paths
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe"
    "C:\Python313\pythonw.exe"
    "C:\Python312\pythonw.exe"
    "C:\Python311\pythonw.exe"
) do (
    if exist %%P ( set "PY=%%~P" & goto :found )
)

echo   [ERROR] Python not found.
echo.
echo   Install Python 3.8+ from https://python.org
echo   Make sure to check "Add to PATH" during install.
echo.
pause
exit /b 1

:found
echo   [OK] Python: %PY%

:: ── Verify Python version ────────────────────────────────
for /f "tokens=2 delims= " %%V in ('%PY% --version 2^>^&1') do set "PYVER=%%V"
echo   [OK] Version: %PYVER%

:: ── Install / update dependencies ────────────────────────
echo.
echo   Checking dependencies...

%PY% -m pip install --upgrade customtkinter matplotlib Pillow pystray -q 2>nul
if %errorlevel% neq 0 (
    %PY% -m pip install --user customtkinter matplotlib Pillow pystray -q 2>nul
)
if %errorlevel% neq 0 (
    %PY% -m pip install customtkinter matplotlib Pillow pystray -q --break-system-packages 2>nul
)

echo   [OK] Dependencies ready.
echo.
echo   Launching PillSleepTracker Pro...
echo.

:: ── Launch (prefer pythonw for no console) ───────────────
set "SCRIPT=%~dp0PillSleepTracker.py"
if not exist "%SCRIPT%" (
    echo   [ERROR] PillSleepTracker.py not found in:
    echo   %~dp0
    pause
    exit /b 1
)

:: Try pythonw first (no console window)
where pythonw >nul 2>&1 && (
    start "" pythonw "%SCRIPT%"
    exit /b 0
)

:: Fall back to python (console stays open briefly)
start "" %PY% "%SCRIPT%"
exit /b 0
