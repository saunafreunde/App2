# ============================================================
#  Levando Email-Agent - Einmalige Einrichtung
#  Dieses Skript als Administrator in PowerShell ausführen
# ============================================================

$ErrorActionPreference = "Stop"
$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Levando Email-Agent - Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Schritt 1: Python prüfen / installieren ─────────────────
Write-Host "[1/4] Prüfe Python..." -ForegroundColor Yellow

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3") {
            $pythonCmd = $cmd
            Write-Host "      Python gefunden: $ver" -ForegroundColor Green
            break
        }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Host "      Python nicht gefunden. Installiere via winget..." -ForegroundColor Yellow
    try {
        winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("PATH", "User")
        $pythonCmd = "python"
        Write-Host "      Python installiert." -ForegroundColor Green
    } catch {
        Write-Host ""
        Write-Host "  FEHLER: Python konnte nicht automatisch installiert werden." -ForegroundColor Red
        Write-Host "  Bitte manuell installieren: https://www.python.org/downloads/" -ForegroundColor Red
        Write-Host "  Dann dieses Skript erneut ausführen." -ForegroundColor Red
        pause
        exit 1
    }
}

# ── Schritt 2: pip-Pakete installieren ──────────────────────
Write-Host ""
Write-Host "[2/4] Installiere Python-Pakete..." -ForegroundColor Yellow
& $pythonCmd -m pip install --upgrade pip --quiet
& $pythonCmd -m pip install anthropic schedule --quiet
Write-Host "      Pakete installiert." -ForegroundColor Green

# ── Schritt 3: API-Key eintragen ────────────────────────────
Write-Host ""
Write-Host "[3/4] Claude API-Key einrichten..." -ForegroundColor Yellow

$configPath = Join-Path $AgentDir "config.json"
$config = Get-Content $configPath -Raw | ConvertFrom-Json
$currentKey = $config.claude.api_key

if ($currentKey -eq "HIER_API_KEY_EINTRAGEN") {
    Write-Host ""
    Write-Host "  Du benötigst einen Claude API-Key." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  So bekommst du einen (kostenlos mit Startguthaben):" -ForegroundColor White
    Write-Host "  1. Öffne: https://console.anthropic.com" -ForegroundColor White
    Write-Host "  2. Registrieren / Anmelden (Google-Account reicht)" -ForegroundColor White
    Write-Host "  3. Links auf 'API Keys' klicken" -ForegroundColor White
    Write-Host "  4. 'Create Key' - Name z.B. 'Levando-Email-Agent'" -ForegroundColor White
    Write-Host "  5. Den Key (sk-ant-...) kopieren" -ForegroundColor White
    Write-Host ""

    # Browser öffnen
    try {
        Start-Process "https://console.anthropic.com/settings/keys"
        Write-Host "  Browser wurde geöffnet." -ForegroundColor Green
    } catch { }

    Write-Host ""
    $apiKey = Read-Host "  API-Key hier einfügen (sk-ant-...)"

    if ($apiKey -match "^sk-ant-") {
        # In config.json speichern
        $config.claude.api_key = $apiKey
        $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8
        Write-Host "      API-Key gespeichert." -ForegroundColor Green
    } else {
        Write-Host "  WARNUNG: Key sieht ungewöhnlich aus. Bitte später in config.json eintragen." -ForegroundColor Yellow
    }
} else {
    Write-Host "      API-Key bereits eingetragen." -ForegroundColor Green
}

# ── Schritt 4: Verbindung testen ────────────────────────────
Write-Host ""
Write-Host "[4/4] Teste E-Mail-Verbindung..." -ForegroundColor Yellow

$testScript = @"
import sys
sys.path.insert(0, r'$AgentDir')
import json, imaplib, ssl

with open(r'$configPath', encoding='utf-8') as f:
    cfg = json.load(f)['email']

try:
    ctx = ssl.create_default_context()
    with imaplib.IMAP4_SSL(cfg['imap_server'], cfg['imap_port'], ssl_context=ctx) as imap:
        imap.login(cfg['email'], cfg['password'])
        imap.select('INBOX')
        _, data = imap.search(None, 'ALL')
        count = len(data[0].split()) if data[0] else 0
        print(f'OK: IMAP-Login erfolgreich. {count} E-Mail(s) im Postfach.')
except Exception as e:
    print(f'FEHLER: {e}')
    sys.exit(1)
"@

$result = & $pythonCmd -c $testScript 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "      $result" -ForegroundColor Green
} else {
    Write-Host "      $result" -ForegroundColor Red
}

# ── Windows Task Scheduler einrichten ───────────────────────
Write-Host ""
$setupTask = Read-Host "Windows-Aufgabe einrichten (Agent startet automatisch beim Login)? [j/n]"
if ($setupTask -eq "j" -or $setupTask -eq "J") {
    $pythonPath = (& $pythonCmd -c "import sys; print(sys.executable)").Trim()
    $action  = New-ScheduledTaskAction -Execute $pythonPath -Argument "run.py daemon" -WorkingDirectory $AgentDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)

    Register-ScheduledTask -TaskName "Levando-Email-Agent" `
        -Action $action -Trigger $trigger -Settings $settings `
        -RunLevel Highest -Force | Out-Null

    Write-Host "      Aufgabe 'Levando-Email-Agent' eingerichtet." -ForegroundColor Green
    Write-Host "      Der Agent startet automatisch bei jedem Windows-Login." -ForegroundColor Green
}

# ── Fertig ───────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setup abgeschlossen!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Nächste Schritte:" -ForegroundColor White
Write-Host ""
Write-Host "  Agent einmal starten (Test):" -ForegroundColor White
Write-Host "    cd '$AgentDir'" -ForegroundColor Gray
Write-Host "    python run.py" -ForegroundColor Gray
Write-Host ""
Write-Host "  Als Daemon starten:" -ForegroundColor White
Write-Host "    Doppelklick auf: 2_START_AGENT.bat" -ForegroundColor Gray
Write-Host ""
Write-Host "  Ausstehende E-Mails prüfen:" -ForegroundColor White
Write-Host "    Doppelklick auf: 3_PENDING.bat" -ForegroundColor Gray
Write-Host ""
pause
