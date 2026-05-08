@echo off
cd /d "%~dp0"
title Levando Email-Agent

echo.
echo ============================================================
echo   Levando Email-Agent ^| Daemon-Modus
echo ============================================================
echo.

:: Python suchen
set PYTHON=
for %%P in (python python3 py) do (
    if not defined PYTHON (
        %%P --version >nul 2>&1 && set PYTHON=%%P
    )
)

if not defined PYTHON (
    echo  FEHLER: Python nicht gefunden.
    echo  Bitte 1_SETUP.ps1 als Administrator ausfuehren.
    echo.
    pause
    exit /b 1
)

:: API-Key pruefen
%PYTHON% -c "import json; cfg=json.load(open('config.json',encoding='utf-8')); key=cfg['claude']['api_key']; exit(0 if key.startswith('sk-ant-') else 1)" >nul 2>&1
if errorlevel 1 (
    echo  FEHLER: Claude API-Key nicht gesetzt.
    echo  Bitte config.json oeffnen und den API-Key eintragen.
    echo  ^(claude.api_key muss mit sk-ant- beginnen^)
    echo.
    start notepad config.json
    pause
    exit /b 1
)

echo  Agent laeuft. Beenden mit STRG+C
echo.
%PYTHON% run.py daemon

echo.
echo  Agent beendet.
pause
