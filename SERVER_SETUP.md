# Email Agent – Server Setup (Hostinger KVM 2)

## Schritt 1: Server vorbereiten (einmalig)

Per SSH einloggen (Hostinger gibt dir IP + root-Passwort):

```bash
ssh root@DEINE-SERVER-IP
```

System aktualisieren + Docker installieren:

```bash
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin git
```

Coolify installieren (Web-Panel für alle Docker-Apps):

```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

Danach: Browser öffnen → http://DEINE-SERVER-IP:8000
Account anlegen → fertig.

---

## Schritt 2: App auf den Server laden

Auf deinem PC – Projektordner hochladen:

```bash
scp -r "C:\Users\Stephanie.Bischofber\OneDrive\Desktop\CLAUDE\email_agent" root@DEINE-SERVER-IP:/opt/email-agent
```

Oder per Git (empfohlen):
```bash
# Einmalig auf dem Server:
git clone DEIN-REPO /opt/email-agent
```

---

## Schritt 3: .env-Datei erstellen (WICHTIG – niemals in Git!)

```bash
cd /opt/email-agent
cp .env.example .env
nano .env
```

Alle Werte eintragen (Passwörter, API-Keys etc.), dann speichern: STRG+X → Y → Enter

---

## Schritt 4: Container starten

```bash
cd /opt/email-agent
docker compose up -d --build
```

Logs prüfen:
```bash
docker compose logs -f
```

---

## Schritt 5: Web-UI erreichbar machen (Domain + SSL)

In Coolify:
1. "New Resource" → "Service" → "Custom Docker Compose"
2. Oder: Nginx Proxy Manager installieren → Port 5000 auf deine Domain zeigen lassen
3. SSL wird automatisch per Let's Encrypt aktiviert

Danach erreichbar unter: https://email.levando.gmbh (oder deine Domain)

---

## Nützliche Befehle

```bash
# Status prüfen
docker compose ps

# Logs anschauen
docker compose logs -f email-agent

# Neustart
docker compose restart

# Update (nach Code-Änderungen)
docker compose up -d --build

# Stoppen
docker compose down
```

---

## Ressourcen-Verbrauch (KVM 2: 8GB RAM)

| Container     | RAM   | CPU  |
|---------------|-------|------|
| email-agent   | ~150MB | ~2%  |
| web-ui        | ~100MB | ~1%  |
| Coolify       | ~300MB | ~2%  |
| **Gesamt**    | ~550MB | ~5%  |

→ Noch 7+ GB RAM frei für weitere Apps!
