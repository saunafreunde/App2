@echo off
chcp 65001 > nul
title Email Agent Web-UI
echo.
echo ============================================================
echo   E-Mail Agent - Web-UI
echo ============================================================
echo.
cd /d "%~dp0"
python --version > nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden!
    pause
    exit /b 1
)
python -c "import flask" > nul 2>&1
if errorlevel 1 (
    echo Flask wird installiert...
    python -m pip install flask --quiet
)
echo   Browser:  http://localhost:5000
echo   Beenden:  STRG+C
echo.
start "" /b cmd /c "timeout /t 2 > nul && start http://localhost:5000"
python web_ui.py
pause
