"""
Email Agent – Deployment via Hostinger API
==========================================
Verwendung:
  python deploy.py              Erstmalig deployen / aktualisieren
  python deploy.py status       Status der Container anzeigen
  python deploy.py logs         Logs anzeigen
  python deploy.py restart      Neustart
  python deploy.py stop         Stoppen
  python deploy.py delete       Projekt entfernen (Vorsicht!)
"""

import sys
import os
import json
import http.client
import urllib.parse
from pathlib import Path

# ── Konfiguration ─────────────────────────────────────────────────────────────
PROJECT_NAME   = "levando-email"
COMPOSE_FILE   = Path(__file__).parent / "docker-compose.server.yml"
ENV_FILE       = Path(__file__).parent / ".env"
API_BASE       = "developers.hostinger.com"
API_TOKEN_FILE = Path(__file__).parent / ".hostinger_token"

VM_ID          = 1387899   # srv1387899.hstgr.cloud – 187.77.85.206
GITHUB_REPO    = "https://github.com/saunafreunde/App2"


# ── API-Client ────────────────────────────────────────────────────────────────

class HostingerAPI:
    def __init__(self, token: str):
        self.token = token

    def _request(self, method: str, path: str, body: dict = None) -> dict:
        conn = http.client.HTTPSConnection(API_BASE)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        payload = json.dumps(body).encode() if body else None
        conn.request(method, path, payload, headers)
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()

        if not raw:
            return {"status": resp.status}
        try:
            data = json.loads(raw)
        except Exception:
            return {"raw": raw, "status": resp.status}

        if resp.status >= 400:
            error = data.get("error") or data.get("message") or raw
            raise RuntimeError(f"API Fehler {resp.status}: {error}")
        return data

    def get_vms(self) -> list:
        return self._request("GET", "/api/vps/v1/virtual-machines").get("data", [])

    def get_docker_projects(self, vm_id: int) -> list:
        return self._request("GET", f"/api/vps/v1/virtual-machines/{vm_id}/docker").get("data", [])

    def deploy_project(self, vm_id: int, name: str, content: str, env: str = "") -> dict:
        return self._request("POST", f"/api/vps/v1/virtual-machines/{vm_id}/docker", {
            "project_name": name,
            "content":      content,
            "environment":  env or None,
        })

    def get_containers(self, vm_id: int, project: str) -> list:
        return self._request("GET",
            f"/api/vps/v1/virtual-machines/{vm_id}/docker/{project}/containers"
        ).get("data", [])

    def get_logs(self, vm_id: int, project: str) -> dict:
        return self._request("GET",
            f"/api/vps/v1/virtual-machines/{vm_id}/docker/{project}/logs"
        )

    def restart_project(self, vm_id: int, project: str) -> dict:
        return self._request("POST",
            f"/api/vps/v1/virtual-machines/{vm_id}/docker/{project}/restart"
        )

    def stop_project(self, vm_id: int, project: str) -> dict:
        return self._request("POST",
            f"/api/vps/v1/virtual-machines/{vm_id}/docker/{project}/stop"
        )

    def start_project(self, vm_id: int, project: str) -> dict:
        return self._request("POST",
            f"/api/vps/v1/virtual-machines/{vm_id}/docker/{project}/start"
        )

    def delete_project(self, vm_id: int, project: str) -> dict:
        return self._request("DELETE",
            f"/api/vps/v1/virtual-machines/{vm_id}/docker/{project}/down"
        )


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def get_token() -> str:
    """API-Token laden oder abfragen."""
    # 1. Gespeicherter Token?
    if API_TOKEN_FILE.exists():
        token = API_TOKEN_FILE.read_text().strip()
        if token:
            return token

    # 2. Umgebungsvariable?
    token = os.environ.get("HOSTINGER_API_TOKEN", "")
    if token:
        return token

    # 3. Manuell eingeben
    print("\n" + "=" * 56)
    print("  Hostinger API-Token benötigt")
    print("=" * 56)
    print("  → Hostinger Panel öffnen:")
    print("    https://hpanel.hostinger.com/profile/api")
    print("  → 'Token erstellen' → Kopieren")
    print("=" * 56)
    token = input("\n  API-Token einfügen: ").strip()

    if not token:
        print("Abgebrochen.")
        sys.exit(1)

    save = input("  Token für künftige Aufrufe speichern? (j/n): ").strip().lower()
    if save == "j":
        API_TOKEN_FILE.write_text(token)
        print(f"  Gespeichert in: {API_TOKEN_FILE}")
    return token


def pick_vm(api: HostingerAPI) -> int:
    """VPS-ID – fix konfiguriert."""
    print(f"  VPS: srv1387899.hstgr.cloud  (187.77.85.206  |  ID: {VM_ID})")
    return VM_ID


def load_env() -> str:
    """Lädt .env-Datei als String für die API."""
    if not ENV_FILE.exists():
        print(f"\n  FEHLER: .env nicht gefunden ({ENV_FILE})")
        print(f"  Bitte .env.example kopieren und ausfüllen:")
        print(f"  copy .env.example .env")
        sys.exit(1)

    content = ENV_FILE.read_text(encoding="utf-8")

    # Prüfen ob Platzhalter noch drin sind
    if "DEIN_PASSWORT" in content or "DEIN_BOT_TOKEN" in content:
        print("\n  WARNUNG: .env enthält noch Platzhalter!")
        print("  Bitte alle Werte in .env ausfüllen bevor du deployst.")
        ok = input("  Trotzdem fortfahren? (j/n): ").strip().lower()
        if ok != "j":
            sys.exit(0)

    return content


def load_compose() -> str:
    """Lädt docker-compose.server.yml."""
    if not COMPOSE_FILE.exists():
        print(f"\n  FEHLER: {COMPOSE_FILE} nicht gefunden!")
        sys.exit(1)
    return COMPOSE_FILE.read_text(encoding="utf-8")


def print_action(action: dict):
    """Zeigt API-Action-Status."""
    state = action.get("state") or action.get("status") or "gestartet"
    aid   = action.get("id", "")
    print(f"  → Action {aid}: {state}")


# ── Befehle ───────────────────────────────────────────────────────────────────

def cmd_deploy(api: HostingerAPI, vm_id: int):
    print("\n  Lade Compose-Datei und .env …")
    compose = load_compose()
    env     = load_env()

    print(f"  Deploye Projekt '{PROJECT_NAME}' …")
    result = api.deploy_project(vm_id, PROJECT_NAME, compose, env)
    print_action(result.get("data", result))
    print("\n  Deployment gestartet!")
    print("  Status prüfen mit:  python deploy.py status")
    print("  Logs anzeigen mit:  python deploy.py logs")


def cmd_status(api: HostingerAPI, vm_id: int):
    print(f"\n  Container-Status für '{PROJECT_NAME}':\n")
    try:
        containers = api.get_containers(vm_id, PROJECT_NAME)
    except RuntimeError as e:
        print(f"  {e}")
        return

    if not containers:
        print("  Keine Container gefunden (noch nicht deployed?).")
        return

    for c in containers:
        name   = c.get("name", "?")
        status = c.get("status", "?")
        health = c.get("health", "")
        ports  = c.get("ports", [])
        port_s = ", ".join(f"{p.get('host_port')}→{p.get('container_port')}"
                           for p in ports) if ports else "–"
        icon   = "✓" if "running" in status.lower() else "✗"
        print(f"  {icon} {name:<25} {status:<15} Ports: {port_s}")
        if health:
            print(f"    Health: {health}")


def cmd_logs(api: HostingerAPI, vm_id: int):
    print(f"\n  Logs für '{PROJECT_NAME}':\n")
    try:
        logs = api.get_logs(vm_id, PROJECT_NAME)
    except RuntimeError as e:
        print(f"  {e}")
        return
    print(logs.get("data") or logs.get("logs") or str(logs))


def cmd_restart(api: HostingerAPI, vm_id: int):
    print(f"\n  Starte '{PROJECT_NAME}' neu …")
    result = api.restart_project(vm_id, PROJECT_NAME)
    print_action(result.get("data", result))


def cmd_stop(api: HostingerAPI, vm_id: int):
    print(f"\n  Stoppe '{PROJECT_NAME}' …")
    result = api.stop_project(vm_id, PROJECT_NAME)
    print_action(result.get("data", result))


def cmd_delete(api: HostingerAPI, vm_id: int):
    print(f"\n  ⚠  ACHTUNG: Projekt '{PROJECT_NAME}' wird gelöscht!")
    print("  Alle Container und Netzwerke werden entfernt.")
    print("  Daten in Volumes bleiben erhalten.")
    ok = input("  Sicher? Tippe 'ja' zum Bestätigen: ").strip().lower()
    if ok != "ja":
        print("  Abgebrochen.")
        return
    result = api.delete_project(vm_id, PROJECT_NAME)
    print_action(result.get("data", result))
    print("  Projekt entfernt.")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 56)
    print("  Email Agent – Hostinger Deployment")
    print("=" * 56)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "deploy"

    token = get_token()
    api   = HostingerAPI(token)

    print("\n  Verbinde mit Hostinger API …")
    try:
        vm_id = pick_vm(api)
    except RuntimeError as e:
        print(f"\n  API-Fehler: {e}")
        print("  Bitte API-Token prüfen.")
        sys.exit(1)

    if cmd == "deploy":
        cmd_deploy(api, vm_id)
    elif cmd == "status":
        cmd_status(api, vm_id)
    elif cmd == "logs":
        cmd_logs(api, vm_id)
    elif cmd == "restart":
        cmd_restart(api, vm_id)
    elif cmd == "stop":
        cmd_stop(api, vm_id)
    elif cmd == "delete":
        cmd_delete(api, vm_id)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
