@echo off
REM Fuegt Hosts-Eintrag hinzu und oeffnet die Web-UI

REM Admin-Rechte pruefen
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo Bitte als Administrator starten - Rechtsklick auf Datei -^> "Als Administrator ausfuehren"
    pause
    exit /b 1
)

echo Setze Hosts-Eintrag fuer email.levando.gmbh ...

REM Alte Eintraege fuer email.levando.gmbh entfernen
findstr /v /c:"email.levando.gmbh" "%WINDIR%\System32\drivers\etc\hosts" > "%TEMP%\hosts.new"
copy /y "%TEMP%\hosts.new" "%WINDIR%\System32\drivers\etc\hosts" >nul

REM Neuen Eintrag anhaengen
echo. >> "%WINDIR%\System32\drivers\etc\hosts"
echo 187.77.85.206 email.levando.gmbh >> "%WINDIR%\System32\drivers\etc\hosts"

echo DNS-Cache leeren ...
ipconfig /flushdns >nul

echo.
echo ============================================================
echo   FERTIG! Oeffne Browser ...
echo ============================================================
echo.

start "" "https://email.levando.gmbh"

timeout /t 3 >nul
exit
