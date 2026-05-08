@echo off
chcp 65001 > nul
echo.
echo Entferne Levando Autostart ...

REM Task Scheduler Tasks entfernen
schtasks /delete /tn "LevandoEmailAgent" /f > nul 2>&1
schtasks /delete /tn "LevandoEmailWebUI" /f > nul 2>&1

REM Startup-Ordner VBScripts entfernen (Fallback)
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
if exist "%STARTUP%\LevandoEmailAgent.vbs" del "%STARTUP%\LevandoEmailAgent.vbs"
if exist "%STARTUP%\LevandoEmailWebUI.vbs" del "%STARTUP%\LevandoEmailWebUI.vbs"

echo [OK] Autostart deaktiviert.
echo.
pause