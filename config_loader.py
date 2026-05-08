"""
Lädt Konfiguration aus Umgebungsvariablen (.env) oder config.json als Fallback.
Auf dem Server: .env-Datei verwenden (sicher)
Lokal: config.json wie bisher
"""

import os
import json
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_config() -> dict:
    # Umgebungsvariablen vorhanden? → Server-Modus
    if os.getenv("CLAUDE_API_KEY"):
        return _from_env()

    # Sonst config.json (lokaler Modus)
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    raise FileNotFoundError(
        "Keine Konfiguration gefunden. "
        "Bitte .env-Datei erstellen (Server) oder config.json (lokal)."
    )


def _from_env() -> dict:
    accounts = []
    for i in range(1, 6):
        email = os.getenv(f"ACCOUNT{i}_EMAIL")
        if not email:
            break
        accounts.append({
            "email":       email,
            "password":    os.getenv(f"ACCOUNT{i}_PASSWORD", ""),
            "imap_server": os.getenv(f"ACCOUNT{i}_IMAP_SERVER", ""),
            "imap_port":   int(os.getenv(f"ACCOUNT{i}_IMAP_PORT", "993")),
            "smtp_server": os.getenv(f"ACCOUNT{i}_SMTP_SERVER", ""),
            "smtp_port":   int(os.getenv(f"ACCOUNT{i}_SMTP_PORT", "465")),
            "smtp_ssl":    True,
            "signature": (
                "\n\nMit freundlichen Grüßen\nChristoph Rene Wolfert\n\n--\n"
                "Levando GmbH | Vorderer Aischbach 27 | 72275 Alpirsbach\n"
                f"E-Mail: {email} | Web: www.levando.gmbh\n"
                "Geschäftsführer: Christoph Rene Wolfert\n"
                "HRB 762226 | Amtsgericht Stuttgart | USt-IdNr.: DE313901596"
            ),
        })

    return {
        "accounts": accounts,
        "claude": {
            "api_key": os.getenv("CLAUDE_API_KEY", ""),
            "model":   os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
        },
        "agent": {
            "auto_reply_threshold":    float(os.getenv("AGENT_AUTO_REPLY_THRESHOLD", "0.80")),
            "report_email":            os.getenv("AGENT_REPORT_EMAIL", ""),
            "report_time":             os.getenv("AGENT_REPORT_TIME", "18:00"),
            "todo_time":               os.getenv("AGENT_TODO_TIME", "11:00"),
            "check_interval_minutes":  int(os.getenv("AGENT_CHECK_INTERVAL_MINUTES", "15")),
            "company_name":            os.getenv("AGENT_COMPANY_NAME", "Levando GmbH"),
            "language":                os.getenv("AGENT_LANGUAGE", "de"),
        },
        "business_hours": {
            "start": int(os.getenv("BUSINESS_HOURS_START", "8")),
            "end":   int(os.getenv("BUSINESS_HOURS_END", "18")),
            "days":  [0, 1, 2, 3, 4],
        },
        "telegram": {
            "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "chat_id":   os.getenv("TELEGRAM_CHAT_ID", ""),
        },
        "flask_secret_key": os.getenv("FLASK_SECRET_KEY", "bitte-aendern"),
    }
