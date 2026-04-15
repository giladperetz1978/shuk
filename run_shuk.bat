@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Local Python environment was not found in .venv
    echo Recreate it before launching the app.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" gui.py
set "exit_code=%errorlevel%"

if not "%exit_code%"=="0" (
    echo.
    echo Application exited with code %exit_code%.
    pause
)

exit /b %exit_code%