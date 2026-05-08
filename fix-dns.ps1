# Hosts-Eintrag setzen (umgeht den Fritz!Box Cache)
# RECHTSKLICK -> "Mit PowerShell als Administrator ausfuehren"

$hostsPath = "C:\Windows\System32\drivers\etc\hosts"
$entry = "187.77.85.206 email.levando.gmbh"

# Alte Eintraege entfernen
$content = Get-Content $hostsPath | Where-Object { $_ -notmatch "email\.levando\.gmbh" }
$content | Set-Content -Path $hostsPath -Encoding ASCII

# Neuen Eintrag hinzufuegen
Add-Content -Path $hostsPath -Value $entry

# DNS-Cache leeren
ipconfig /flushdns | Out-Null

Write-Host "Fertig! Bitte Browser komplett schliessen und neu oeffnen."
Write-Host "Dann: https://email.levando.gmbh"
Pause
