@echo off
cd /d "%~dp0"
title Levando - Ausstehende E-Mails

echo.
echo ============================================================
echo   Levando Email-Agent ^| Ausstehende E-Mails
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
    pause
    exit /b 1
)

%PYTHON% run.py pending

echo.
echo ============================================================
echo  Befehle zum Genehmigen / Ablehnen:
echo.
echo    Genehmigen:  %PYTHON% run.py approve ^<ID^>
echo    Ablehnen:    %PYTHON% run.py reject  ^<ID^> [Grund]
echo ============================================================
echo.
pause
