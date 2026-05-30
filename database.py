"""SQLite-Datenbank für den Email-Agenten."""
import sqlite3
import json
import re
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "email_agent.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    # timeout=30: bis zu 30s auf einen Lock warten statt sofort "database is locked".
    # Agent-Daemon + Web-UI teilen sich dieselbe DB-Datei (Docker-Volume).
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL: nebenläufige Leser blockieren den Schreiber nicht → deutlich weniger Locks.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    """Erstellt alle Tabellen falls noch nicht vorhanden."""
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            uid           TEXT    UNIQUE,
            from_address  TEXT,
            subject       TEXT,
            body          TEXT,
            received_at   TEXT,
            category      TEXT,
            status        TEXT    DEFAULT 'pending',
            confidence    REAL,
            draft_reply   TEXT,
            sent_reply    TEXT,
            processed_at  TEXT,
            notes         TEXT,
            account_email TEXT
        )
    """)
    # Migration für bestehende DBs ohne account_email-Spalte
    try:
        c.execute("ALTER TABLE emails ADD COLUMN account_email TEXT")
        conn.commit()
    except Exception:
        pass
    # Migration: snooze_until für Snooze-Funktion
    try:
        c.execute("ALTER TABLE emails ADD COLUMN snooze_until TEXT")
        conn.commit()
    except Exception:
        pass
    # Migration: send_at für verzögerten Versand (1-3h Random)
    try:
        c.execute("ALTER TABLE emails ADD COLUMN send_at TEXT")
        conn.commit()
    except Exception:
        pass

    # Versprechen / Verbindlichkeiten ("ich melde mich morgen", "Feedback bis Freitag")
    c.execute("""
        CREATE TABLE IF NOT EXISTS commitments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id      INTEGER,
            account_email TEXT,
            sender        TEXT,
            subject       TEXT,
            promise       TEXT,
            due_date      TEXT,
            completed     INTEGER DEFAULT 0,
            completed_at  TEXT,
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email_id) REFERENCES emails(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT,
            category         TEXT,
            keywords         TEXT,
            subject_template TEXT,
            body_template    TEXT,
            usage_count      INTEGER DEFAULT 0,
            created_at       TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS learned_responses (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            original_subject TEXT,
            original_body    TEXT,
            category         TEXT,
            keywords         TEXT,
            response_subject TEXT,
            response_body    TEXT,
            confidence_score REAL,
            approved_by      TEXT    DEFAULT 'auto',
            created_at       TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT    DEFAULT CURRENT_TIMESTAMP,
            action    TEXT,
            email_id  INTEGER,
            details   TEXT
        )
    """)

    # Telegram-Pending-Map: tg_message_id → email_id (für Direktantwort)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tg_pending_map (
            tg_message_id INTEGER PRIMARY KEY,
            email_id      INTEGER,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # DB-Backups (JSON-Snapshots aller Tabellen, für /backup im Web-UI)
    c.execute("""
        CREATE TABLE IF NOT EXISTS db_backups (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
            label      TEXT,
            data       TEXT
        )
    """)

    # Wissensbasis – Firmenfakten (Versand, Rückgabe, FAQ), fließt in Claudes System-Prompt
    c.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            topic      TEXT,
            content    TEXT,
            shop       TEXT    DEFAULT 'beide',
            active     INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # App-Einstellungen / Integrationen (JTL-Shop, JTL-WAWI, DHL, Feature-Schalter)
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            skey       TEXT PRIMARY KEY,
            svalue     TEXT,
            is_secret  INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)

    # Wissens-Vorschläge (selbstlernend – aus gesendeten Antworten extrahiert)
    c.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_suggestions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            topic      TEXT,
            content    TEXT,
            source     TEXT,
            status     TEXT    DEFAULT 'pending',
            created_at TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("  Datenbank initialisiert.")
    _seed_knowledge_if_empty()


# ── Emails ──────────────────────────────────────────────────────────────────

def save_email(uid: str, from_address: str, subject: str,
               body: str, received_at: str, account_email: str = "") -> int:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO emails (uid, from_address, subject, body, received_at, account_email) "
            "VALUES (?,?,?,?,?,?)",
            (uid, from_address, subject, body, received_at, account_email)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM emails WHERE uid=?", (uid,)).fetchone()
        return row["id"] if row else -1
    finally:
        conn.close()


def get_pending_emails(account_email: str = "") -> list[dict]:
    conn = get_conn()
    try:
        if account_email:
            rows = conn.execute(
                "SELECT id, uid, from_address, subject, body, received_at, account_email "
                "FROM emails WHERE status='pending' AND account_email=? ORDER BY received_at ASC",
                (account_email,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, uid, from_address, subject, body, received_at, account_email "
                "FROM emails WHERE status='pending' ORDER BY received_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_pending_review_emails() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, from_address, subject, received_at, "
            "draft_reply, confidence, notes, category "
            "FROM emails WHERE status='pending_review' ORDER BY received_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_email_by_id(email_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM emails WHERE id=?", (email_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_email(email_id: int, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    try:
        fields = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [email_id]
        conn.execute(f"UPDATE emails SET {fields} WHERE id=?", values)
        conn.commit()
    finally:
        conn.close()


# ── Vorlagen ─────────────────────────────────────────────────────────────────

def get_templates(category: str = None) -> list[dict]:
    conn = get_conn()
    try:
        if category:
            rows = conn.execute(
                "SELECT * FROM templates WHERE category=? ORDER BY usage_count DESC",
                (category,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM templates ORDER BY usage_count DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_template(name: str, category: str, keywords: list,
                  subject_template: str, body_template: str):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO templates (name, category, keywords, subject_template, body_template) "
            "VALUES (?,?,?,?,?)",
            (name, category, json.dumps(keywords, ensure_ascii=False),
             subject_template, body_template)
        )
        conn.commit()
    finally:
        conn.close()


# ── Lernen ────────────────────────────────────────────────────────────────────

def save_rejection_feedback(original_subject: str, original_body: str,
                             category: str, draft_reply: str, reason: str):
    """Speichert abgelehnten Entwurf + Begründung als Lernbeispiel (approved_by='rejected')."""
    keywords = [w for w in original_subject.split() if len(w) > 3][:6]
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO learned_responses "
            "(original_subject, original_body, category, keywords, "
            "response_subject, response_body, confidence_score, approved_by) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (original_subject, original_body, category or "ALLGEMEIN",
             json.dumps(keywords, ensure_ascii=False),
             draft_reply[:500] if draft_reply else "",
             reason or "Kein Grund angegeben",
             -1.0, "rejected")
        )
        conn.commit()
    finally:
        conn.close()


def get_rejection_feedback(category: str = None, limit: int = 5) -> list[dict]:
    """Gibt zuletzt abgelehnte Entwürfe mit Begründung zurück (für System-Prompt)."""
    conn = get_conn()
    try:
        if category:
            rows = conn.execute(
                "SELECT original_subject, response_subject AS draft_preview, "
                "response_body AS reason, category, created_at "
                "FROM learned_responses WHERE approved_by='rejected' AND category=? "
                "AND response_body NOT IN ('', 'Kein Grund angegeben') "
                "ORDER BY created_at DESC LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT original_subject, response_subject AS draft_preview, "
                "response_body AS reason, category, created_at "
                "FROM learned_responses WHERE approved_by='rejected' "
                "AND response_body NOT IN ('', 'Kein Grund angegeben') "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_learned_responses(category: str = None, limit: int = 8) -> list[dict]:
    conn = get_conn()
    try:
        if category:
            rows = conn.execute(
                "SELECT original_subject, original_body, response_subject, "
                "response_body, keywords, confidence_score, approved_by "
                "FROM learned_responses WHERE category=? "
                "ORDER BY confidence_score DESC, created_at DESC LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT original_subject, original_body, response_subject, "
                "response_body, keywords, confidence_score, approved_by "
                "FROM learned_responses "
                "ORDER BY confidence_score DESC, created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_learned_response(original_subject: str, original_body: str,
                           category: str, keywords: list,
                           response_subject: str, response_body: str,
                           confidence_score: float, approved_by: str = "auto"):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO learned_responses "
            "(original_subject, original_body, category, keywords, "
            "response_subject, response_body, confidence_score, approved_by) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (original_subject, original_body, category,
             json.dumps(keywords, ensure_ascii=False),
             response_subject, response_body, confidence_score, approved_by)
        )
        conn.commit()
    finally:
        conn.close()


# ── Log & Statistik ───────────────────────────────────────────────────────────

def log_activity(action: str, email_id: int = None, details: str = None):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO activity_log (action, email_id, details) VALUES (?,?,?)",
            (action, email_id, details)
        )
        conn.commit()
    finally:
        conn.close()


# ── Sender-Kontext (Gedächtnis) ───────────────────────────────────────────────

def get_sender_context(from_address: str, limit: int = 3) -> list[dict]:
    """Gibt die letzten N Interaktionen mit diesem Absender zurück."""
    m = re.search(r"<([^>]+)>", from_address)
    addr = (m.group(1) if m else from_address).lower().strip()
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT subject, status, category, received_at, sent_reply, notes "
            "FROM emails WHERE LOWER(from_address) LIKE ? "
            "AND status NOT IN ('pending','filtered') "
            "ORDER BY received_at DESC LIMIT ?",
            (f"%{addr}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Konfidenz-Boost (Lernkurve) ───────────────────────────────────────────────

def get_category_confidence_boost(category: str) -> float:
    """
    Berechnet Boost basierend auf bisheriger Genehmigungsrate dieser Kategorie.
    Gibt 0.0–0.10 zurück (wird auf den Konfidenz-Score addiert).
    """
    conn = get_conn()
    try:
        row = conn.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) AS approved
            FROM emails
            WHERE category = ? AND status IN ('sent', 'rejected')
        """, (category,)).fetchone()
        if not row or (row["total"] or 0) < 3:
            return 0.0
        rate = (row["approved"] or 0) / row["total"]
        if rate >= 0.90:
            return 0.10
        elif rate >= 0.75:
            return 0.05
        return 0.0
    finally:
        conn.close()


# ── Wochenstatistik ───────────────────────────────────────────────────────────

def get_weekly_stats() -> list[dict]:
    """Statistik der letzten 7 Tage für das Dashboard-Diagramm."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT
                DATE(received_at)                                           AS date,
                COUNT(*)                                                    AS total,
                SUM(CASE WHEN status='sent'           THEN 1 ELSE 0 END)   AS auto_sent,
                SUM(CASE WHEN status='pending_review' THEN 1 ELSE 0 END)   AS pending_review,
                SUM(CASE WHEN status='filtered'       THEN 1 ELSE 0 END)   AS filtered,
                SUM(CASE WHEN status='manual'         THEN 1 ELSE 0 END)   AS manual
            FROM emails
            WHERE DATE(received_at) >= DATE('now', '-6 days')
            GROUP BY DATE(received_at)
            ORDER BY date ASC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Volltext-Suche ────────────────────────────────────────────────────────────

def search_emails(query: str, limit: int = 50) -> list[dict]:
    """Sucht in Betreff, Absender, Body und Notizen."""
    q = f"%{query}%"
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, from_address, subject, received_at, status, category, account_email "
            "FROM emails "
            "WHERE subject LIKE ? OR from_address LIKE ? OR body LIKE ? OR notes LIKE ? "
            "ORDER BY received_at DESC LIMIT ?",
            (q, q, q, q, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Telegram Pending-Map ──────────────────────────────────────────────────────

def save_tg_map(tg_message_id: int, email_id: int):
    """Speichert Zuordnung Telegram-Nachricht → E-Mail-ID."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO tg_pending_map (tg_message_id, email_id) VALUES (?,?)",
            (tg_message_id, email_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_email_id_for_tg_msg(tg_message_id: int) -> int | None:
    """Gibt die E-Mail-ID zur Telegram-Nachricht zurück."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT email_id FROM tg_pending_map WHERE tg_message_id=?",
            (tg_message_id,)
        ).fetchone()
        return row["email_id"] if row else None
    finally:
        conn.close()


# ── Lern-Statistiken ──────────────────────────────────────────────────────────

def get_top_rejection_reasons(limit: int = 5) -> list[dict]:
    """Top-Begründungen aus abgelehnten Mails."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT response_body AS reason, COUNT(*) AS count
            FROM learned_responses
            WHERE approved_by='rejected'
              AND response_body NOT IN ('', 'Kein Grund angegeben')
            GROUP BY response_body
            ORDER BY count DESC, MAX(created_at) DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_top_senders(limit: int = 5) -> list[dict]:
    """Top-Absender mit Anzahl Mails (letzte 30 Tage)."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT from_address, COUNT(*) AS total,
                   SUM(CASE WHEN status='sent'           THEN 1 ELSE 0 END) AS sent,
                   SUM(CASE WHEN status='pending_review' THEN 1 ELSE 0 END) AS review,
                   SUM(CASE WHEN status='filtered'       THEN 1 ELSE 0 END) AS filtered
            FROM emails
            WHERE DATE(received_at) >= DATE('now','-30 days')
            GROUP BY from_address
            ORDER BY total DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_category_accuracy() -> list[dict]:
    """Genauigkeit pro Kategorie: Anzahl gesendet vs. abgelehnt."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT category,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status='sent'     THEN 1 ELSE 0 END) AS sent,
                   SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) AS rejected
            FROM emails
            WHERE category IS NOT NULL AND category != ''
              AND status IN ('sent','rejected')
            GROUP BY category
            HAVING total >= 2
            ORDER BY total DESC
        """).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["accuracy"] = (d["sent"] or 0) / d["total"] if d["total"] else 0
            result.append(d)
        return result
    finally:
        conn.close()


# ── Snooze ────────────────────────────────────────────────────────────────────

def set_snooze(email_id: int, snooze_until_iso: str):
    """Markiert eine E-Mail als geschnoozt (Status snoozed)."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE emails SET status='snoozed', snooze_until=? WHERE id=?",
            (snooze_until_iso, email_id)
        )
        conn.commit()
    finally:
        conn.close()


def wake_snoozed_emails() -> int:
    """Setzt alle E-Mails deren Snooze-Zeit abgelaufen ist zurück auf pending_review.
    Gibt die Anzahl der reaktivierten E-Mails zurück."""
    now_iso = datetime.now().isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE emails SET status='pending_review', snooze_until=NULL "
            "WHERE status='snoozed' AND snooze_until <= ?",
            (now_iso,)
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def get_snoozed_emails() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, from_address, subject, received_at, snooze_until, "
            "draft_reply, confidence, notes, category "
            "FROM emails WHERE status='snoozed' ORDER BY snooze_until ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Templates (CRUD) ──────────────────────────────────────────────────────────

def get_template_by_id(template_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_template(template_id: int, name: str, category: str, keywords: list,
                    subject_template: str, body_template: str):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE templates SET name=?, category=?, keywords=?, "
            "subject_template=?, body_template=? WHERE id=?",
            (name, category, json.dumps(keywords, ensure_ascii=False),
             subject_template, body_template, template_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_template(template_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
        conn.commit()
    finally:
        conn.close()


# ── Bulk-Operationen ──────────────────────────────────────────────────────────

def bulk_update_status(email_ids: list[int], status: str, notes: str = ""):
    """Massen-Update von E-Mail-Status."""
    if not email_ids:
        return
    conn = get_conn()
    try:
        placeholders = ",".join("?" * len(email_ids))
        params = [status, notes, datetime.now().isoformat(), *email_ids]
        conn.execute(
            f"UPDATE emails SET status=?, notes=?, processed_at=? WHERE id IN ({placeholders})",
            params
        )
        conn.commit()
    finally:
        conn.close()


# ── Verzögerter Versand (1-3h Random Delay) ──────────────────────────────────

def get_due_emails_to_send() -> list[dict]:
    """E-Mails die jetzt versendet werden sollen (status='scheduled' und send_at <= now)."""
    conn = get_conn()
    try:
        now = datetime.now().isoformat()
        rows = conn.execute(
            "SELECT * FROM emails WHERE status='scheduled' AND send_at IS NOT NULL "
            "AND send_at <= ? ORDER BY send_at ASC",
            (now,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_scheduled_emails(account_email: str = None) -> list[dict]:
    """Alle geplanten E-Mails (status='scheduled')."""
    conn = get_conn()
    try:
        if account_email:
            rows = conn.execute(
                "SELECT * FROM emails WHERE status='scheduled' AND account_email=? "
                "ORDER BY send_at ASC", (account_email,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM emails WHERE status='scheduled' ORDER BY send_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Versprechen / Verbindlichkeiten ──────────────────────────────────────────

def save_commitment(email_id: int, account_email: str, sender: str,
                    subject: str, promise: str, due_date: str):
    """Speichert ein Versprechen aus einer Antwort-E-Mail."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO commitments (email_id, account_email, sender, subject, "
            "promise, due_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (email_id, account_email, sender, subject, promise, due_date,
             datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def get_open_commitments(limit: int = 100) -> list[dict]:
    """Offene Versprechen, sortiert nach Fälligkeit."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM commitments WHERE completed=0 "
            "ORDER BY due_date ASC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_due_commitments(days_ahead: int = 2) -> list[dict]:
    """Versprechen die heute oder in den nächsten X Tagen fällig sind."""
    from datetime import timedelta
    conn = get_conn()
    try:
        cutoff = (datetime.now() + timedelta(days=days_ahead)).isoformat()
        rows = conn.execute(
            "SELECT * FROM commitments WHERE completed=0 AND due_date <= ? "
            "ORDER BY due_date ASC", (cutoff,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_commitment_done(commitment_id: int):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE commitments SET completed=1, completed_at=? WHERE id=?",
            (datetime.now().isoformat(), commitment_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_commitment(commitment_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM commitments WHERE id=?", (commitment_id,))
        conn.commit()
    finally:
        conn.close()


def get_commitments_count() -> dict:
    """Statistik: offen / heute fällig / überfällig."""
    from datetime import timedelta
    conn = get_conn()
    try:
        now    = datetime.now()
        today  = now.replace(hour=23, minute=59, second=59).isoformat()
        nowstr = now.isoformat()
        c = conn.cursor()
        open_   = c.execute("SELECT COUNT(*) FROM commitments WHERE completed=0").fetchone()[0]
        overdue = c.execute("SELECT COUNT(*) FROM commitments WHERE completed=0 AND due_date<?", (nowstr,)).fetchone()[0]
        today_  = c.execute("SELECT COUNT(*) FROM commitments WHERE completed=0 AND due_date<=? AND due_date>=?", (today, nowstr)).fetchone()[0]
        return {"open": open_, "overdue": overdue, "today": today_}
    finally:
        conn.close()


def get_daily_stats(date: str = None) -> dict:
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='sent'           THEN 1 ELSE 0 END) AS auto_sent,
                SUM(CASE WHEN status='pending_review' THEN 1 ELSE 0 END) AS pending_review,
                SUM(CASE WHEN status='manual'         THEN 1 ELSE 0 END) AS manual,
                SUM(CASE WHEN status='filtered'       THEN 1 ELSE 0 END) AS filtered,
                SUM(CASE WHEN status='rejected'       THEN 1 ELSE 0 END) AS rejected,
                SUM(CASE WHEN status='error'          THEN 1 ELSE 0 END) AS errors
            FROM emails
            WHERE DATE(received_at) = ?
        """, (date,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


# ── Listen nach Status / Aktivität (Web-UI) ───────────────────────────────────

def get_emails_by_status(status: str, limit: int = 500) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, from_address, subject, received_at, processed_at, "
            "category, account_email, confidence, notes, snooze_until "
            "FROM emails WHERE status=? ORDER BY received_at DESC LIMIT ?",
            (status, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_activity_log(limit: int = 100) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT timestamp, action, email_id, details "
            "FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_account_email_for_id(email_id: int) -> str:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT account_email FROM emails WHERE id=?", (email_id,)
        ).fetchone()
        return (row["account_email"] or "") if row else ""
    finally:
        conn.close()


# ── Backup / Restore (JSON-Snapshots aller Tabellen) ──────────────────────────

BACKUP_TABLES = ["emails", "commitments", "templates", "learned_responses",
                 "activity_log", "tg_pending_map"]


def dump_all_tables() -> dict:
    """Serialisiert alle Backup-Tabellen als JSON-fähiges dict {tabelle: [zeilen]}."""
    conn = get_conn()
    try:
        data = {}
        for table in BACKUP_TABLES:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            data[table] = [dict(r) for r in rows]
        return data
    finally:
        conn.close()


def create_backup(label: str = None) -> int:
    """Exportiert alle Tabellen als JSON-Snapshot in db_backups. Gibt Backup-ID zurück."""
    if not label:
        label = f"Backup {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    backup_json = json.dumps(dump_all_tables(), ensure_ascii=False)
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO db_backups (label, data, created_at) VALUES (?, ?, ?)",
            (label, backup_json, datetime.now().isoformat())
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_backups() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, created_at, label, LENGTH(data) AS size_bytes "
            "FROM db_backups ORDER BY id DESC"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            ca = d.get("created_at") or ""
            try:
                d["created_at_str"] = datetime.fromisoformat(ca).strftime("%d.%m.%Y %H:%M")
            except Exception:
                d["created_at_str"] = str(ca)
            d["size_kb"] = round((d.get("size_bytes") or 0) / 1024, 1)
            result.append(d)
        return result
    finally:
        conn.close()


def get_backup_data(backup_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT data, label FROM db_backups WHERE id=?", (backup_id,)
        ).fetchone()
        if not row:
            return None
        return {"label": row["label"], "data": json.loads(row["data"])}
    finally:
        conn.close()


def restore_backup(backup_id: int) -> dict:
    """Stellt ein Backup wieder her: leert die Tabellen und re-inserted aus JSON."""
    backup = get_backup_data(backup_id)
    if not backup:
        raise ValueError(f"Backup #{backup_id} nicht gefunden.")
    data = backup["data"]
    conn = get_conn()
    try:
        restored = {}
        # Reihenfolge wegen Foreign Keys: abhängige Tabellen zuerst leeren
        for table in reversed(BACKUP_TABLES):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        for table in BACKUP_TABLES:
            rows = data.get(table, [])
            if not rows:
                restored[table] = 0
                continue
            cols = list(rows[0].keys())
            placeholders = ",".join(["?"] * len(cols))
            col_str = ",".join(cols)
            for row in rows:
                vals = [row.get(col) for col in cols]
                conn.execute(
                    f"INSERT OR IGNORE INTO {table} ({col_str}) VALUES ({placeholders})",
                    vals
                )
            restored[table] = len(rows)
        conn.commit()
        return restored
    finally:
        conn.close()


def delete_backup(backup_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM db_backups WHERE id=?", (backup_id,))
        conn.commit()
    finally:
        conn.close()


# ── Wissensbasis (Firmenfakten für Claudes System-Prompt) ─────────────────────

def get_knowledge(active_only: bool = True) -> list[dict]:
    conn = get_conn()
    try:
        sql = ("SELECT id, topic, content, shop, active, sort_order "
               "FROM knowledge_base")
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY sort_order ASC, id ASC"
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def get_knowledge_by_id(kid: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM knowledge_base WHERE id=?", (kid,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_knowledge(topic: str, content: str, shop: str = "beide",
                   sort_order: int = 0) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO knowledge_base (topic, content, shop, sort_order, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (topic, content, shop or "beide", sort_order, datetime.now().isoformat())
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_knowledge(kid: int, topic: str, content: str, shop: str,
                     active: int, sort_order: int):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE knowledge_base SET topic=?, content=?, shop=?, active=?, "
            "sort_order=? WHERE id=?",
            (topic, content, shop or "beide", 1 if active else 0, sort_order, kid)
        )
        conn.commit()
    finally:
        conn.close()


def delete_knowledge(kid: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM knowledge_base WHERE id=?", (kid,))
        conn.commit()
    finally:
        conn.close()


def get_knowledge_for_prompt() -> str:
    """Formatiert die aktive Wissensbasis als Textblock für den System-Prompt."""
    rows = get_knowledge(active_only=True)
    if not rows:
        return ""
    lines = []
    for r in rows:
        shop = (r.get("shop") or "beide").strip()
        scope = "" if shop in ("", "beide") else f" ({shop})"
        lines.append(f"  • {r.get('topic','')}{scope}: {r.get('content','')}")
    return "\n".join(lines)


_KNOWLEDGE_SEEDS = [
    ("Versandzeit", "Die Lieferung dauert in der Regel 2–3 Werktage.", "beide", 10),
    ("Versandkosten", "Versandkosten betragen 4,90 €. Ab 30 € Bestellwert ist der "
     "Versand kostenlos.", "beide", 20),
    ("Rückgabe / Widerruf", "Im eigenen Shop (radschrauben123.de & aromen123.de) gilt "
     "ein 14-tägiges Widerrufsrecht. Bei Bestellungen über eBay oder Amazon beträgt "
     "das Rückgaberecht 30 Tage.", "beide", 30),
    ("\"Wo ist mein Paket?\"", "Wenn jemand fragt, wo sein Paket bleibt: zusichern, "
     "dass du den Sendungsverlauf prüfst und dich zeitnah mit dem aktuellen Stand "
     "meldest.", "beide", 40),
]


def _seed_knowledge_if_empty():
    """Befüllt die Wissensbasis beim ersten Start mit den Standardfakten.
    Atomar (BEGIN IMMEDIATE), damit die zwei Container nicht doppelt seeden."""
    conn = get_conn()
    try:
        conn.isolation_level = None  # Transaktion selbst steuern
        conn.execute("BEGIN IMMEDIATE")
        n = conn.execute("SELECT COUNT(*) AS n FROM knowledge_base").fetchone()["n"]
        if n == 0:
            conn.executemany(
                "INSERT INTO knowledge_base (topic, content, shop, sort_order, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [(t, c, s, o, datetime.now().isoformat()) for t, c, s, o in _KNOWLEDGE_SEEDS]
            )
            print(f"  Wissensbasis mit {len(_KNOWLEDGE_SEEDS)} Standardeinträgen befüllt.")
        conn.execute("COMMIT")
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        print(f"  Wissensbasis-Seed übersprungen ({e})")
    finally:
        conn.close()


# ── App-Einstellungen / Integrationen (JTL, DHL, Feature-Schalter) ─────────────

def get_setting(key: str, default: str = "") -> str:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT svalue FROM app_settings WHERE skey=?", (key,)
        ).fetchone()
        return row["svalue"] if row and row["svalue"] is not None else default
    finally:
        conn.close()


def set_setting(key: str, value: str, is_secret: int = 0):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO app_settings (skey, svalue, is_secret, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(skey) DO UPDATE SET svalue=excluded.svalue, "
            "is_secret=excluded.is_secret, updated_at=excluded.updated_at",
            (key, value, is_secret, datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def get_settings_dict() -> dict:
    """Alle Einstellungen als {key: value}-dict (fürs Formular)."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT skey, svalue FROM app_settings").fetchall()
        return {r["skey"]: (r["svalue"] or "") for r in rows}
    finally:
        conn.close()


# ── Selbstlernende Wissensbasis (Vorschläge) ──────────────────────────────────

def get_sent_for_learning(limit: int = 30) -> list[dict]:
    """Kürzlich gesendete (menschlich freigegebene) Antworten als Lernquelle."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT subject, body, sent_reply FROM emails "
            "WHERE status='sent' AND sent_reply IS NOT NULL AND sent_reply != '' "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_suggestions(status: str = "pending") -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, topic, content, source, status, created_at "
            "FROM knowledge_suggestions WHERE status=? ORDER BY id DESC",
            (status,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_suggestion(topic: str, content: str, source: str = "auto") -> int:
    """Speichert einen Vorschlag – aber nur, wenn das Thema nicht schon in der
    Wissensbasis oder als offener Vorschlag existiert (Dedup)."""
    t_low = (topic or "").strip().lower()
    if not t_low or not (content or "").strip():
        return 0
    conn = get_conn()
    try:
        exists = conn.execute(
            "SELECT 1 FROM knowledge_base WHERE lower(topic)=? "
            "UNION SELECT 1 FROM knowledge_suggestions "
            "WHERE lower(topic)=? AND status='pending'",
            (t_low, t_low)
        ).fetchone()
        if exists:
            return 0
        cur = conn.execute(
            "INSERT INTO knowledge_suggestions (topic, content, source, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (topic.strip(), content.strip(), source, datetime.now().isoformat())
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def accept_suggestion(sid: int):
    """Übernimmt einen Vorschlag in die Wissensbasis und markiert ihn als angenommen."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT topic, content FROM knowledge_suggestions WHERE id=?", (sid,)
        ).fetchone()
        if not row:
            return
        conn.execute(
            "INSERT INTO knowledge_base (topic, content, shop, sort_order, created_at) "
            "VALUES (?, ?, 'beide', 100, ?)",
            (row["topic"], row["content"], datetime.now().isoformat())
        )
        conn.execute("UPDATE knowledge_suggestions SET status='accepted' WHERE id=?", (sid,))
        conn.commit()
    finally:
        conn.close()


def reject_suggestion(sid: int):
    conn = get_conn()
    try:
        conn.execute("UPDATE knowledge_suggestions SET status='rejected' WHERE id=?", (sid,))
        conn.commit()
    finally:
        conn.close()
