@echo off
chcp 65001 > nul
echo.
echo ============================================================
echo   Email Agent – Upload zu GitHub (saunafreunde/App2)
echo ============================================================
echo.

cd /d "%~dp0"

REM Git initialisieren falls noch nicht vorhanden
git init

REM Altes Remote entfernen und neu setzen
git remote remove origin 2>nul
git remote add origin https://github.com/saunafreunde/App2.git

REM Branch auf main setzen
git branch -M main

REM Alle Dateien stagen (außer .gitignore-Ausnahmen)
git add .

REM Status anzeigen
echo.
echo Folgende Dateien werden hochgeladen:
git status --short

echo.
set /p CONFIRM=Jetzt zu GitHub hochladen? (j/n):
if /i "%CONFIRM%" neq "j" goto :end

REM Commit erstellen
git commit -m "Levando Email Agent – Deployment"

REM Hochladen (überschreibt bestehenden Inhalt)
git push -u origin main --force

echo.
echo ============================================================
echo   Fertig! Code ist auf GitHub:
echo   https://github.com/saunafreunde/App2
echo ============================================================
echo.
echo Jetzt deployen mit:
echo   python deploy.py
echo.

:end
pause
