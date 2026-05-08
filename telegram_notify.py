"""
Telegram-Benachrichtigungen für den E-Mail-Agenten.

Funktionen:
  send_message()       – Beliebige Nachricht senden
  send_report()        – Tages-Report als formatierte Nachricht
  send_alert()         – Sofort-Alert (info/warning/error)
  send_pending_alert() – Neue pending_review E-Mail mit Approve/Reject-Befehlen
  test_connection()    – Verbindungstest

Zum Testen:  python telegram_notify.py
"""

import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

CONFIG_PATH = Path(__file__).parent / "config.json"


def _load_tg_cfg() -> tuple[str, str]:
    try:
        from config_loader import load_config
        cfg = load_config()
    except ImportError:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    tg = cfg.get("telegram", {})
    return tg.get("bot_token", ""), str(tg.get("chat_id", ""))


def send_message(text: str, parse_mode: str = "HTML",
                 reply_markup: dict | None = None) -> int | None:
    """
    Sendet eine Telegram-Nachricht (optional mit Inline-Buttons).

    Returns:
        message_id der gesendeten Nachricht (für Mapping), oder None bei Fehler.
    """
    token, chat_id = _load_tg_cfg()
    if not token or token == "DEIN_BOT_TOKEN":
        print("  [Telegram] Nicht konfiguriert.")
        return None

    if len(text) > 4096:
        text = text[:4090] + "\n…"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        body["reply_markup"] = reply_markup
    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                return result.get("result", {}).get("message_id")
            print(f"  [Telegram] API-Fehler: {result.get('description','?')}")
            return None
    except urllib.error.URLError as e:
        print(f"  [Telegram] Verbindungsfehler: {e}")
        return None
    except Exception as e:
        print(f"  [Telegram] Fehler: {e}")
        return None


def send_pending_alert(email_data: dict) -> int | None:
    """
    Benachrichtigt über eine neue E-Mail zur Prüfung.
    Gibt die Telegram-message_id zurück (für Direktantwort-Mapping).
    """
    eid    = email_data.get("id", "?")
    subj   = (email_data.get("subject") or "(kein Betreff)")[:60]
    sender = (email_data.get("from_address") or "")[:50]
    conf   = (email_data.get("confidence") or 0) * 100
    cat    = email_data.get("category") or "–"
    draft  = (email_data.get("draft_reply") or "")
    # Nur Body aus Entwurf (ohne BETREFF:-Zeile)
    if draft.startswith("BETREFF:"):
        parts = draft.split("\n\n", 1)
        draft_body = parts[1][:300] if len(parts) > 1 else ""
    else:
        draft_body = draft[:300]

    text = (
        f"⏳ <b>Neue E-Mail zur Prüfung – #{eid}</b>\n\n"
        f"📧 <b>Von:</b> {sender}\n"
        f"📋 <b>Betreff:</b> {subj}\n"
        f"🏷 <b>Kategorie:</b> {cat} | <b>Konfidenz:</b> {conf:.0f}%\n\n"
        f"💬 <b>Entwurf:</b>\n<i>{draft_body}</i>"
    )
    # Inline-Buttons für schnelles Tippen
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Senden",  "callback_data": f"approve:{eid}"},
                {"text": "✗ Ablehnen", "callback_data": f"reject:{eid}"},
            ],
            [
                {"text": "💤 1h",     "callback_data": f"snooze:{eid}:1"},
                {"text": "💤 3h",     "callback_data": f"snooze:{eid}:3"},
                {"text": "💤 Morgen", "callback_data": f"snooze:{eid}:tomorrow"},
            ],
        ]
    }
    return send_message(text, reply_markup=keyboard)


def send_report(report_text: str, stats: dict = None) -> bool:
    """Sendet den Tages-Report als Telegram-Nachricht."""
    today = datetime.now().strftime("%d.%m.%Y")

    if stats:
        pending = stats.get("pending_review") or 0
        sent    = stats.get("auto_sent") or 0
        manual  = stats.get("manual") or 0
        total   = stats.get("total") or 0
        filtered = stats.get("filtered") or 0
        errors  = stats.get("errors") or 0

        pending_hint = ""
        if pending > 0:
            pending_hint = (
                f"\n\n⚠️ <b>{pending} E-Mail(s) warten auf Prüfung!</b>\n"
                f"👉 Tippe /pending für Details"
            )

        msg = (
            f"📧 <b>E-Mail Report – {today}</b>\n"
            f"{'─'*28}\n"
            f"📥 Gesamt:        <b>{total}</b>\n"
            f"✅ Auto gesendet: <b>{sent}</b>\n"
            f"⏳ Zur Prüfung:   <b>{pending}</b>\n"
            f"👤 Manuell:       <b>{manual}</b>\n"
            f"⊘  Gefiltert:     <b>{filtered}</b>\n"
            f"❌ Fehler:        <b>{errors}</b>"
            f"{pending_hint}"
        )
    else:
        clean = report_text.strip().replace("<", "&lt;").replace(">", "&gt;")
        msg   = f"📧 <b>E-Mail Report – {today}</b>\n\n<pre>{clean[:3500]}</pre>"

    result = send_message(msg)
    return result is not None


def send_alert(subject: str, details: str = "", level: str = "info") -> bool:
    """Sofort-Benachrichtigung (info / warning / error)."""
    icons = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}
    icon  = icons.get(level, "ℹ️")
    msg   = f"{icon} <b>{subject}</b>"
    if details:
        safe = details.replace("<", "&lt;").replace(">", "&gt;")
        msg += f"\n\n{safe[:600]}"
    return send_message(msg) is not None


def test_connection() -> bool:
    """Testet Verbindung und sendet Testnachricht."""
    token, chat_id = _load_tg_cfg()
    if not token or token == "DEIN_BOT_TOKEN":
        print("\n  FEHLER: Kein Bot-Token konfiguriert.")
        return False
    if not chat_id or chat_id == "DEINE_CHAT_ID":
        print("\n  FEHLER: Keine Chat-ID konfiguriert.")
        return False

    print(f"  Token:   {token[:20]}…")
    print(f"  Chat-ID: {chat_id}")
    mid = send_message(
        "✅ <b>Levando E-Mail Agent</b> verbunden!\n\n"
        "Tippe /pending für ausstehende E-Mails.\n"
        "Tippe /stats für die heutige Statistik."
    )
    if mid:
        print(f"  → Nachricht gesendet (ID: {mid})")
    return mid is not None


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "=" * 40)
    print("  Telegram-Verbindungstest")
    print("=" * 40)
    ok = test_connection()
    print("=" * 40)
    sys.exit(0 if ok else 1)
