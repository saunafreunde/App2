@echo off
chcp 65001 > nul
title Levando Email Agent - Autostart Setup

echo.
echo ============================================================
echo   Levando Email Agent - Autostart einrichten
echo ============================================================
echo.
echo Der Agent wird beim naechsten Windows-Anmelden automatisch
echo gestartet (Autostart-Ordner, kein Admin erforderlich).
echo.
pause

set AGENT_DIR=C:\Users\Stephanie.Bischofber\OneDrive\Desktop\CLAUDE\email_agent\
set PYTHON_CMD=C:\Users\Stephanie.Bischofber\AppData\Local\Programs\Python\Python312\python.exe
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

echo Python:    %PYTHON_CMD%
echo Agent:     %AGENT_DIR%
echo Autostart: %STARTUP%
echo.

REM Alte VBS-Dateien entfernen
if exist "%STARTUP%\LevandoEmailAgent.vbs" del "%STARTUP%\LevandoEmailAgent.vbs"
if exist "%STARTUP%\LevandoEmailWebUI.vbs"  del "%STARTUP%\LevandoEmailWebUI.vbs"

REM VBScript fuer Daemon erstellen
(
echo Set WshShell = CreateObject("WScript.Shell"^)
echo WshShell.CurrentDirectory = "%AGENT_DIR%"
echo WshShell.Run Chr(34^) ^& "%PYTHON_CMD%" ^& Chr(34^) ^& " " ^& Chr(34^) ^& "%AGENT_DIR%run.py" ^& Chr(34^) ^& " daemon", 0, False
) > "%STARTUP%\LevandoEmailAgent.vbs"

REM VBScript fuer Web-UI erstellen
(
echo Set WshShell = CreateObject("WScript.Shell"^)
echo WshShell.CurrentDirectory = "%AGENT_DIR%"
echo WshShell.Run Chr(34^) ^& "%PYTHON_CMD%" ^& Chr(34^) ^& " " ^& Chr(34^) ^& "%AGENT_DIR%web_ui.py" ^& Chr(34^), 0, False
) > "%STARTUP%\LevandoEmailWebUI.vbs"

if exist "%STARTUP%\LevandoEmailAgent.vbs" (
    echo [OK] Email-Agent Autostart eingerichtet
) else (
    echo [FEHLER] Konnte Autostart-Datei nicht erstellen
    pause
    exit /b 1
)

if exist "%STARTUP%\LevandoEmailWebUI.vbs" (
    echo [OK] Web-UI Autostart eingerichtet
)

echo.
echo ============================================================
echo   Autostart eingerichtet!
echo   Beim naechsten Anmelden starten Agent und Web-UI
echo   automatisch im Hintergrund.
echo ============================================================
echo.
echo Web-UI: http://localhost:5000
echo Deaktivieren: 6_AUTOSTART_REMOVE.bat
echo.
pause