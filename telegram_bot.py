"""
Telegram-Bot: Direktantwort auf E-Mails aus Telegram heraus.

Läuft als Hintergrund-Thread neben dem Daemon.

Befehle:
  /ok42           → E-Mail #42 mit Claude-Entwurf genehmigen & senden
  /ok42 Mein Text → E-Mail #42 mit eigenem Text senden
  /nein42         → E-Mail #42 ablehnen
  /nein42 Grund   → E-Mail #42 mit Begründung ablehnen
  /pending        → Alle ausstehenden E-Mails anzeigen
  /stats          → Heutige Statistik
"""

import json
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

_stop_event = threading.Event()
_last_update_id = 0


def _load_cfg() -> dict:
    try:
        from config_loader import load_config
        return load_config()
    except ImportError:
        pass
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _api(method: str, data: dict = None) -> dict | None:
    cfg   = _load_cfg()
    token = cfg.get("telegram", {}).get("bot_token", "")
    if not token or token == "DEIN_BOT_TOKEN":
        return None

    url     = f"https://api.telegram.org/bot{token}/{method}"
    payload = json.dumps(data or {}).encode("utf-8")
    req     = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _send(chat_id: str, text: str):
    if len(text) > 4096:
        text = text[:4090] + "\n…"
    _api("sendMessage", {
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })


def _handle_message(msg: dict):
    """Verarbeitet eine eingehende Telegram-Nachricht."""
    global _last_update_id

    chat_id = str(msg.get("chat", {}).get("id", ""))
    text    = (msg.get("text") or "").strip()
    if not text or not chat_id:
        return

    # Erlaubte Chat-IDs prüfen
    cfg          = _load_cfg()
    allowed_chat = str(cfg.get("telegram", {}).get("chat_id", ""))
    if chat_id != allowed_chat:
        _send(chat_id, "⛔ Nicht autorisiert.")
        return

    import database as db
    import agent as ag

    text_lower = text.lower()

    # ── /ok{id} [optionaler Text] ─────────────────────────────────────────────
    if text_lower.startswith("/ok"):
        parts   = text[3:].strip().split(" ", 1)
        id_str  = parts[0].lstrip("/").strip()
        custom  = parts[1].strip() if len(parts) > 1 else None
        try:
            email_id = int(id_str)
        except ValueError:
            _send(chat_id, "❌ Ungültige ID. Beispiel: /ok42")
            return

        row = db.get_email_by_id(email_id)
        if not row:
            _send(chat_id, f"❌ E-Mail #{email_id} nicht gefunden.")
            return
        if row.get("status") != "pending_review":
            _send(chat_id, f"⚠️ E-Mail #{email_id} ist nicht mehr in Prüfung (Status: {row.get('status')}).")
            return

        # Agent initialisieren falls nötig
        if ag._config is None:
            ag.setup(cfg)

        try:
            # Wenn custom-Text: Entwurf überschreiben
            edited = None
            if custom:
                draft = row.get("draft_reply") or ""
                if draft.startswith("BETREFF:"):
                    subj_line = draft.split("\n\n", 1)[0]
                    edited = f"{subj_line}\n\n{custom}"
                else:
                    edited = custom

            ag.approve_email(email_id, edited_body=edited)
            addr = (row.get("from_address") or "")[:40]
            _send(chat_id,
                  f"✅ E-Mail <b>#{email_id}</b> genehmigt und gesendet.\n"
                  f"📧 An: {addr}")
        except Exception as e:
            _send(chat_id, f"❌ Fehler: {e}")
        return

    # ── /nein{id} [Grund] ─────────────────────────────────────────────────────
    if text_lower.startswith("/nein"):
        parts  = text[5:].strip().split(" ", 1)
        id_str = parts[0].lstrip("/").strip()
        reason = parts[1].strip() if len(parts) > 1 else ""
        try:
            email_id = int(id_str)
        except ValueError:
            _send(chat_id, "❌ Ungültige ID. Beispiel: /nein42")
            return

        if ag._config is None:
            ag.setup(cfg)

        ag.reject_email(email_id, reason)
        _send(chat_id, f"❌ E-Mail <b>#{email_id}</b> abgelehnt.")
        return

    # ── /pending ──────────────────────────────────────────────────────────────
    if text_lower.startswith("/pending") or text_lower.startswith("/start"):
        pending = db.get_pending_review_emails()
        if not pending:
            _send(chat_id, "✅ Keine E-Mails zur Prüfung.")
            return
        lines = [f"⏳ <b>{len(pending)} E-Mail(s) zur Prüfung:</b>\n"]
        for e in pending[:10]:
            conf = (e.get("confidence") or 0) * 100
            lines.append(
                f"<b>#{e['id']}</b> – {(e['subject'] or '')[:45]}\n"
                f"  Von: {(e['from_address'] or '')[:35]}\n"
                f"  Konfidenz: {conf:.0f}%\n"
                f"  ✅ /ok{e['id']}   ❌ /nein{e['id']}\n"
            )
        _send(chat_id, "\n".join(lines))
        return

    # ── /aufgaben ─ Versprechen die du eingegangen bist ───────────────────────
    if text_lower.startswith("/aufgaben") or text_lower.startswith("/todo"):
        commits = db.get_due_commitments(days_ahead=7)
        if not commits:
            _send(chat_id, "✅ Keine offenen Versprechen — alles erledigt!")
            return

        from datetime import datetime as dt
        now = dt.now()
        overdue = [c for c in commits if dt.fromisoformat(c["due_date"]) < now]
        today   = [c for c in commits if c not in overdue and
                   dt.fromisoformat(c["due_date"]).date() == now.date()]
        future  = [c for c in commits if c not in overdue and c not in today]

        lines = ["🎯 <b>Deine offenen Versprechen</b>\n"]
        if overdue:
            lines.append(f"\n🔴 <b>ÜBERFÄLLIG ({len(overdue)})</b>")
            for c in overdue[:5]:
                d = dt.fromisoformat(c["due_date"]).strftime("%d.%m.")
                lines.append(f"  • <i>{d}</i> – an {(c['sender'] or '')[:30]}")
                lines.append(f"    {(c['promise'] or '')[:120]}")
                lines.append(f"    /erledigt{c['id']}")
        if today:
            lines.append(f"\n🟡 <b>HEUTE FÄLLIG ({len(today)})</b>")
            for c in today[:5]:
                d = dt.fromisoformat(c["due_date"]).strftime("%H:%M")
                lines.append(f"  • <i>{d}</i> – an {(c['sender'] or '')[:30]}")
                lines.append(f"    {(c['promise'] or '')[:120]}")
                lines.append(f"    /erledigt{c['id']}")
        if future:
            lines.append(f"\n🟢 <b>NÄCHSTE TAGE ({len(future)})</b>")
            for c in future[:5]:
                d = dt.fromisoformat(c["due_date"]).strftime("%d.%m.")
                lines.append(f"  • <i>{d}</i> – an {(c['sender'] or '')[:30]}")
                lines.append(f"    {(c['promise'] or '')[:120]}")
                lines.append(f"    /erledigt{c['id']}")
        _send(chat_id, "\n".join(lines))
        return

    # ── /erledigt{id} – Versprechen abhaken ───────────────────────────────────
    if text_lower.startswith("/erledigt"):
        try:
            cid = int(text[9:].strip().lstrip("/"))
            db.mark_commitment_done(cid)
            _send(chat_id, f"✅ Versprechen #{cid} als erledigt markiert.")
        except Exception as e:
            _send(chat_id, f"❌ Fehler: {e}")
        return

    # ── /geplant – Welche Mails sind im Versand-Queue? ────────────────────────
    if text_lower.startswith("/geplant") or text_lower.startswith("/queue"):
        scheduled = db.get_scheduled_emails()
        if not scheduled:
            _send(chat_id, "✅ Keine Mails im Versand-Queue.")
            return
        from datetime import datetime as dt
        lines = [f"📤 <b>{len(scheduled)} Mails geplant</b>\n"]
        for e in scheduled[:10]:
            when = dt.fromisoformat(e["send_at"]).strftime("%d.%m. %H:%M") if e.get("send_at") else "?"
            lines.append(
                f"<b>#{e['id']}</b> → {when}\n"
                f"  An: {(e['from_address'] or '')[:35]}\n"
                f"  Betreff: {(e['subject'] or '')[:45]}\n"
            )
        _send(chat_id, "\n".join(lines))
        return

    # ── /stats ────────────────────────────────────────────────────────────────
    if text_lower.startswith("/stats"):
        stats   = db.get_daily_stats()
        pending = len(db.get_pending_review_emails())
        from datetime import datetime
        _send(chat_id,
              f"📊 <b>Statistik heute ({datetime.now().strftime('%d.%m.%Y')})</b>\n"
              f"{'─'*24}\n"
              f"📥 Gesamt:        <b>{stats.get('total') or 0}</b>\n"
              f"✅ Gesendet:      <b>{stats.get('auto_sent') or 0}</b>\n"
              f"⏳ Zur Prüfung:   <b>{pending}</b>\n"
              f"👤 Manuell:       <b>{stats.get('manual') or 0}</b>\n"
              f"⊘  Gefiltert:     <b>{stats.get('filtered') or 0}</b>\n"
              f"❌ Fehler:        <b>{stats.get('errors') or 0}</b>")
        return

    # ── Hilfe ─────────────────────────────────────────────────────────────────
    _send(chat_id,
          "📧 <b>Levando E-Mail Agent</b>\n\n"
          "/pending – Ausstehende E-Mails\n"
          "/aufgaben – Offene Versprechen\n"
          "/geplant – Versand-Queue\n"
          "/stats – Heutige Statistik\n\n"
          "/ok<i>42</i> – E-Mail #42 genehmigen (verzögert 1-3h)\n"
          "/ok<i>42</i> <i>Eigener Text</i> – Mit eigenem Text\n"
          "/nein<i>42</i> – E-Mail #42 ablehnen\n"
          "/erledigt<i>5</i> – Versprechen #5 abhaken")


def _answer_callback(callback_id: str, text: str = ""):
    """Bestätigt eine Inline-Button-Aktion (Loading-Spinner stoppt)."""
    _api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


def _edit_message(chat_id: str, message_id: int, text: str):
    """Ändert Text einer Nachricht (entfernt Buttons)."""
    _api("editMessageText", {
        "chat_id":    chat_id,
        "message_id": message_id,
        "text":       text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })


def _handle_callback(cb: dict):
    """Verarbeitet Inline-Button-Klicks (approve/reject/snooze)."""
    cb_id   = cb.get("id")
    chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
    msg_id  = cb.get("message", {}).get("message_id")
    data    = cb.get("data", "")

    cfg          = _load_cfg()
    allowed_chat = str(cfg.get("telegram", {}).get("chat_id", ""))
    if chat_id != allowed_chat:
        _answer_callback(cb_id, "Nicht autorisiert.")
        return

    import database as db
    import agent as ag
    if ag._config is None:
        ag.setup(cfg)

    parts = data.split(":")
    action = parts[0] if parts else ""

    try:
        if action == "approve" and len(parts) >= 2:
            email_id = int(parts[1])
            row = db.get_email_by_id(email_id)
            if not row or row.get("status") != "pending_review":
                _answer_callback(cb_id, "Nicht mehr in Prüfung.")
                _edit_message(chat_id, msg_id, f"⚠️ E-Mail #{email_id} – nicht mehr in Prüfung.")
                return
            ag.approve_email(email_id)
            _answer_callback(cb_id, "Gesendet ✓")
            _edit_message(chat_id, msg_id,
                          f"✅ E-Mail <b>#{email_id}</b> gesendet an {(row.get('from_address') or '')[:40]}")

        elif action == "reject" and len(parts) >= 2:
            email_id = int(parts[1])
            ag.reject_email(email_id, "Per Telegram abgelehnt")
            _answer_callback(cb_id, "Abgelehnt ✗")
            _edit_message(chat_id, msg_id, f"❌ E-Mail <b>#{email_id}</b> abgelehnt.")

        elif action == "snooze" and len(parts) >= 3:
            email_id = int(parts[1])
            mode     = parts[2]
            from datetime import datetime, timedelta
            now = datetime.now()
            if mode == "tomorrow":
                target = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
                label  = "morgen 8:00"
            else:
                hours = int(mode)
                target = now + timedelta(hours=hours)
                label  = f"{hours}h"
            db.set_snooze(email_id, target.isoformat())
            _answer_callback(cb_id, f"Erinnerung in {label}")
            _edit_message(chat_id, msg_id,
                          f"💤 E-Mail <b>#{email_id}</b> – Erinnerung in {label} "
                          f"({target.strftime('%d.%m. %H:%M')})")
        else:
            _answer_callback(cb_id, "Unbekannte Aktion.")
    except Exception as e:
        _answer_callback(cb_id, f"Fehler: {str(e)[:50]}")


def _polling_loop():
    """Holt neue Telegram-Nachrichten per Long-Polling."""
    global _last_update_id
    print("  [Telegram-Bot] Polling gestartet …")

    while not _stop_event.is_set():
        try:
            result = _api("getUpdates", {
                "offset":  _last_update_id + 1,
                "timeout": 20,
                "allowed_updates": ["message", "callback_query"],
            })
            if not result or not result.get("ok"):
                time.sleep(5)
                continue

            for update in result.get("result", []):
                uid = update.get("update_id", 0)
                if uid > _last_update_id:
                    _last_update_id = uid
                msg = update.get("message")
                if msg:
                    try:
                        _handle_message(msg)
                    except Exception as e:
                        print(f"  [Telegram-Bot] Fehler bei Nachricht: {e}")
                cb = update.get("callback_query")
                if cb:
                    try:
                        _handle_callback(cb)
                    except Exception as e:
                        print(f"  [Telegram-Bot] Fehler bei Callback: {e}")

        except Exception as e:
            print(f"  [Telegram-Bot] Polling-Fehler: {e}")
            time.sleep(10)


def start_bot_thread() -> threading.Thread:
    """Startet den Bot als Hintergrund-Thread."""
    t = threading.Thread(target=_polling_loop, daemon=True, name="TelegramBot")
    t.start()
    return t


def stop_bot():
    """Stoppt den Polling-Loop."""
    _stop_event.set()


if __name__ == "__main__":
    import sys
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Telegram-Bot direkt starten (STRG+C zum Beenden) …")
    _polling_loop()
