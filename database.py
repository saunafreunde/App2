"""MySQL-Datenbank für den Email-Agenten (All-Inkl MariaDB)."""
import pymysql
import pymysql.cursors
import json
import re
import os
from datetime import datetime


def get_conn() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", ""),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )


def init_db():
    """Erstellt alle Tabellen falls noch nicht vorhanden."""
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    uid           TEXT,
                    from_address  TEXT,
                    subject       TEXT,
                    body          LONGTEXT,
                    received_at   VARCHAR(40),
                    category      VARCHAR(100),
                    status        VARCHAR(40)  DEFAULT 'pending',
                    confidence    DOUBLE,
                    draft_reply   LONGTEXT,
                    sent_reply    LONGTEXT,
                    processed_at  VARCHAR(40),
                    notes         TEXT,
                    account_email VARCHAR(200),
                    snooze_until  VARCHAR(40),
                    send_at       VARCHAR(40),
                    UNIQUE KEY uq_uid (uid(255))
                ) CHARACTER SET utf8mb4
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS commitments (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    email_id      INT,
                    account_email VARCHAR(200),
                    sender        TEXT,
                    subject       TEXT,
                    promise       TEXT,
                    due_date      VARCHAR(40),
                    completed     TINYINT DEFAULT 0,
                    completed_at  VARCHAR(40),
                    created_at    VARCHAR(40) DEFAULT (DATE_FORMAT(NOW(),'%Y-%m-%dT%H:%i:%s')),
                    FOREIGN KEY (email_id) REFERENCES emails(id)
                ) CHARACTER SET utf8mb4
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id               INT AUTO_INCREMENT PRIMARY KEY,
                    name             TEXT,
                    category         VARCHAR(100),
                    keywords         TEXT,
                    subject_template TEXT,
                    body_template    LONGTEXT,
                    usage_count      INT DEFAULT 0,
                    created_at       VARCHAR(40) DEFAULT (DATE_FORMAT(NOW(),'%Y-%m-%dT%H:%i:%s'))
                ) CHARACTER SET utf8mb4
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS learned_responses (
                    id               INT AUTO_INCREMENT PRIMARY KEY,
                    original_subject TEXT,
                    original_body    LONGTEXT,
                    category         VARCHAR(100),
                    keywords         TEXT,
                    response_subject TEXT,
                    response_body    LONGTEXT,
                    confidence_score DOUBLE,
                    approved_by      VARCHAR(40) DEFAULT 'auto',
                    created_at       VARCHAR(40) DEFAULT (DATE_FORMAT(NOW(),'%Y-%m-%dT%H:%i:%s'))
                ) CHARACTER SET utf8mb4
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id        INT AUTO_INCREMENT PRIMARY KEY,
                    timestamp VARCHAR(40) DEFAULT (DATE_FORMAT(NOW(),'%Y-%m-%dT%H:%i:%s')),
                    action    VARCHAR(100),
                    email_id  INT,
                    details   TEXT
                ) CHARACTER SET utf8mb4
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS tg_pending_map (
                    tg_message_id INT PRIMARY KEY,
                    email_id      INT,
                    created_at    VARCHAR(40) DEFAULT (DATE_FORMAT(NOW(),'%Y-%m-%dT%H:%i:%s'))
                ) CHARACTER SET utf8mb4
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS db_backups (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    label      VARCHAR(200),
                    data       LONGTEXT
                ) CHARACTER SET utf8mb4
            """)

        conn.commit()
        print("  Datenbank initialisiert.")
    finally:
        conn.close()


# ── Emails ──────────────────────────────────────────────────────────────────

def save_email(uid: str, from_address: str, subject: str,
               body: str, received_at: str, account_email: str = "") -> int:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "INSERT IGNORE INTO emails "
                "(uid, from_address, subject, body, received_at, account_email) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (uid, from_address, subject, body, received_at, account_email)
            )
            conn.commit()
            c.execute("SELECT id FROM emails WHERE uid=%s", (uid,))
            row = c.fetchone()
            return row["id"] if row else -1
    finally:
        conn.close()


def get_pending_emails(account_email: str = "") -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            if account_email:
                c.execute(
                    "SELECT id, uid, from_address, subject, body, received_at, account_email "
                    "FROM emails WHERE status='pending' AND account_email=%s "
                    "ORDER BY received_at ASC",
                    (account_email,)
                )
            else:
                c.execute(
                    "SELECT id, uid, from_address, subject, body, received_at, account_email "
                    "FROM emails WHERE status='pending' ORDER BY received_at ASC"
                )
            return c.fetchall()
    finally:
        conn.close()


def get_pending_review_emails() -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, from_address, subject, received_at, "
                "draft_reply, confidence, notes, category "
                "FROM emails WHERE status='pending_review' ORDER BY received_at ASC"
            )
            return c.fetchall()
    finally:
        conn.close()


def get_email_by_id(email_id: int) -> dict | None:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT * FROM emails WHERE id=%s", (email_id,))
            return c.fetchone()
    finally:
        conn.close()


def update_email(email_id: int, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    try:
        fields = ", ".join(f"{k}=%s" for k in kwargs)
        values = list(kwargs.values()) + [email_id]
        with conn.cursor() as c:
            c.execute(f"UPDATE emails SET {fields} WHERE id=%s", values)
        conn.commit()
    finally:
        conn.close()


# ── Vorlagen ─────────────────────────────────────────────────────────────────

def get_templates(category: str = None) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            if category:
                c.execute(
                    "SELECT * FROM templates WHERE category=%s ORDER BY usage_count DESC",
                    (category,)
                )
            else:
                c.execute("SELECT * FROM templates ORDER BY usage_count DESC")
            return c.fetchall()
    finally:
        conn.close()


def save_template(name: str, category: str, keywords: list,
                  subject_template: str, body_template: str):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO templates (name, category, keywords, subject_template, body_template) "
                "VALUES (%s,%s,%s,%s,%s)",
                (name, category, json.dumps(keywords, ensure_ascii=False),
                 subject_template, body_template)
            )
        conn.commit()
    finally:
        conn.close()


# ── Lernen ────────────────────────────────────────────────────────────────────

def save_rejection_feedback(original_subject: str, original_body: str,
                             category: str, draft_reply: str, reason: str):
    keywords = [w for w in original_subject.split() if len(w) > 3][:6]
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO learned_responses "
                "(original_subject, original_body, category, keywords, "
                "response_subject, response_body, confidence_score, approved_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
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
    conn = get_conn()
    try:
        with conn.cursor() as c:
            if category:
                c.execute(
                    "SELECT original_subject, response_subject AS draft_preview, "
                    "response_body AS reason, category, created_at "
                    "FROM learned_responses WHERE approved_by='rejected' AND category=%s "
                    "AND response_body NOT IN ('', 'Kein Grund angegeben') "
                    "ORDER BY created_at DESC LIMIT %s",
                    (category, limit)
                )
            else:
                c.execute(
                    "SELECT original_subject, response_subject AS draft_preview, "
                    "response_body AS reason, category, created_at "
                    "FROM learned_responses WHERE approved_by='rejected' "
                    "AND response_body NOT IN ('', 'Kein Grund angegeben') "
                    "ORDER BY created_at DESC LIMIT %s",
                    (limit,)
                )
            return c.fetchall()
    finally:
        conn.close()


def get_learned_responses(category: str = None, limit: int = 8) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            if category:
                c.execute(
                    "SELECT original_subject, original_body, response_subject, "
                    "response_body, keywords, confidence_score, approved_by "
                    "FROM learned_responses WHERE category=%s "
                    "ORDER BY confidence_score DESC, created_at DESC LIMIT %s",
                    (category, limit)
                )
            else:
                c.execute(
                    "SELECT original_subject, original_body, response_subject, "
                    "response_body, keywords, confidence_score, approved_by "
                    "FROM learned_responses "
                    "ORDER BY confidence_score DESC, created_at DESC LIMIT %s",
                    (limit,)
                )
            return c.fetchall()
    finally:
        conn.close()


def save_learned_response(original_subject: str, original_body: str,
                           category: str, keywords: list,
                           response_subject: str, response_body: str,
                           confidence_score: float, approved_by: str = "auto"):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO learned_responses "
                "(original_subject, original_body, category, keywords, "
                "response_subject, response_body, confidence_score, approved_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
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
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO activity_log (action, email_id, details, timestamp) "
                "VALUES (%s,%s,%s,%s)",
                (action, email_id, details, datetime.now().isoformat())
            )
        conn.commit()
    finally:
        conn.close()


# ── Sender-Kontext (Gedächtnis) ───────────────────────────────────────────────

def get_sender_context(from_address: str, limit: int = 3) -> list[dict]:
    m = re.search(r"<([^>]+)>", from_address)
    addr = (m.group(1) if m else from_address).lower().strip()
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT subject, status, category, received_at, sent_reply, notes "
                "FROM emails WHERE LOWER(from_address) LIKE %s "
                "AND status NOT IN ('pending','filtered') "
                "ORDER BY received_at DESC LIMIT %s",
                (f"%{addr}%", limit)
            )
            return c.fetchall()
    finally:
        conn.close()


# ── Konfidenz-Boost (Lernkurve) ───────────────────────────────────────────────

def get_category_confidence_boost(category: str) -> float:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) AS approved
                FROM emails
                WHERE category = %s AND status IN ('sent', 'rejected')
            """, (category,))
            row = c.fetchone()
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
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT
                    DATE(received_at)                                           AS date,
                    COUNT(*)                                                    AS total,
                    SUM(CASE WHEN status='sent'           THEN 1 ELSE 0 END)   AS auto_sent,
                    SUM(CASE WHEN status='pending_review' THEN 1 ELSE 0 END)   AS pending_review,
                    SUM(CASE WHEN status='filtered'       THEN 1 ELSE 0 END)   AS filtered,
                    SUM(CASE WHEN status='manual'         THEN 1 ELSE 0 END)   AS manual
                FROM emails
                WHERE DATE(received_at) >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
                GROUP BY DATE(received_at)
                ORDER BY date ASC
            """)
            rows = c.fetchall()
        # date-Objekte zu String konvertieren für JSON-Serialisierbarkeit
        for r in rows:
            if hasattr(r.get("date"), "isoformat"):
                r["date"] = r["date"].isoformat()
        return rows
    finally:
        conn.close()


# ── Volltext-Suche ────────────────────────────────────────────────────────────

def search_emails(query: str, limit: int = 50) -> list[dict]:
    q = f"%{query}%"
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, from_address, subject, received_at, status, category, account_email "
                "FROM emails "
                "WHERE subject LIKE %s OR from_address LIKE %s "
                "OR body LIKE %s OR notes LIKE %s "
                "ORDER BY received_at DESC LIMIT %s",
                (q, q, q, q, limit)
            )
            return c.fetchall()
    finally:
        conn.close()


# ── Telegram Pending-Map ──────────────────────────────────────────────────────

def save_tg_map(tg_message_id: int, email_id: int):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "REPLACE INTO tg_pending_map (tg_message_id, email_id) VALUES (%s,%s)",
                (tg_message_id, email_id)
            )
        conn.commit()
    finally:
        conn.close()


def get_email_id_for_tg_msg(tg_message_id: int) -> int | None:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT email_id FROM tg_pending_map WHERE tg_message_id=%s",
                (tg_message_id,)
            )
            row = c.fetchone()
        return row["email_id"] if row else None
    finally:
        conn.close()


# ── Lern-Statistiken ──────────────────────────────────────────────────────────

def get_top_rejection_reasons(limit: int = 5) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT response_body AS reason, COUNT(*) AS count
                FROM learned_responses
                WHERE approved_by='rejected'
                  AND response_body NOT IN ('', 'Kein Grund angegeben')
                GROUP BY response_body
                ORDER BY count DESC, MAX(created_at) DESC
                LIMIT %s
            """, (limit,))
            return c.fetchall()
    finally:
        conn.close()


def get_top_senders(limit: int = 5) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT from_address, COUNT(*) AS total,
                       SUM(CASE WHEN status='sent'           THEN 1 ELSE 0 END) AS sent,
                       SUM(CASE WHEN status='pending_review' THEN 1 ELSE 0 END) AS review,
                       SUM(CASE WHEN status='filtered'       THEN 1 ELSE 0 END) AS filtered
                FROM emails
                WHERE DATE(received_at) >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                GROUP BY from_address
                ORDER BY total DESC
                LIMIT %s
            """, (limit,))
            return c.fetchall()
    finally:
        conn.close()


def get_category_accuracy() -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("""
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
            """)
            rows = c.fetchall()
        result = []
        for r in rows:
            r["accuracy"] = (r["sent"] or 0) / r["total"] if r["total"] else 0
            result.append(r)
        return result
    finally:
        conn.close()


# ── Snooze ────────────────────────────────────────────────────────────────────

def set_snooze(email_id: int, snooze_until_iso: str):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "UPDATE emails SET status='snoozed', snooze_until=%s WHERE id=%s",
                (snooze_until_iso, email_id)
            )
        conn.commit()
    finally:
        conn.close()


def wake_snoozed_emails() -> int:
    now_iso = datetime.now().isoformat()
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "UPDATE emails SET status='pending_review', snooze_until=NULL "
                "WHERE status='snoozed' AND snooze_until <= %s",
                (now_iso,)
            )
            conn.commit()
            return c.rowcount
    finally:
        conn.close()


def get_snoozed_emails() -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, from_address, subject, received_at, snooze_until, "
                "draft_reply, confidence, notes, category "
                "FROM emails WHERE status='snoozed' ORDER BY snooze_until ASC"
            )
            return c.fetchall()
    finally:
        conn.close()


# ── Templates (CRUD) ──────────────────────────────────────────────────────────

def get_template_by_id(template_id: int) -> dict | None:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT * FROM templates WHERE id=%s", (template_id,))
            return c.fetchone()
    finally:
        conn.close()


def update_template(template_id: int, name: str, category: str, keywords: list,
                    subject_template: str, body_template: str):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "UPDATE templates SET name=%s, category=%s, keywords=%s, "
                "subject_template=%s, body_template=%s WHERE id=%s",
                (name, category, json.dumps(keywords, ensure_ascii=False),
                 subject_template, body_template, template_id)
            )
        conn.commit()
    finally:
        conn.close()


def delete_template(template_id: int):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("DELETE FROM templates WHERE id=%s", (template_id,))
        conn.commit()
    finally:
        conn.close()


# ── Bulk-Operationen ──────────────────────────────────────────────────────────

def bulk_update_status(email_ids: list[int], status: str, notes: str = ""):
    if not email_ids:
        return
    conn = get_conn()
    try:
        placeholders = ",".join(["%s"] * len(email_ids))
        params = [status, notes, datetime.now().isoformat(), *email_ids]
        with conn.cursor() as c:
            c.execute(
                f"UPDATE emails SET status=%s, notes=%s, processed_at=%s "
                f"WHERE id IN ({placeholders})",
                params
            )
        conn.commit()
    finally:
        conn.close()


# ── Verzögerter Versand ───────────────────────────────────────────────────────

def get_due_emails_to_send() -> list[dict]:
    conn = get_conn()
    try:
        now = datetime.now().isoformat()
        with conn.cursor() as c:
            c.execute(
                "SELECT * FROM emails WHERE status='scheduled' AND send_at IS NOT NULL "
                "AND send_at <= %s ORDER BY send_at ASC",
                (now,)
            )
            return c.fetchall()
    finally:
        conn.close()


def get_scheduled_emails(account_email: str = None) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            if account_email:
                c.execute(
                    "SELECT * FROM emails WHERE status='scheduled' AND account_email=%s "
                    "ORDER BY send_at ASC", (account_email,)
                )
            else:
                c.execute(
                    "SELECT * FROM emails WHERE status='scheduled' ORDER BY send_at ASC"
                )
            return c.fetchall()
    finally:
        conn.close()


# ── Versprechen / Verbindlichkeiten ──────────────────────────────────────────

def save_commitment(email_id: int, account_email: str, sender: str,
                    subject: str, promise: str, due_date: str):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO commitments (email_id, account_email, sender, subject, "
                "promise, due_date, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (email_id, account_email, sender, subject, promise, due_date,
                 datetime.now().isoformat())
            )
        conn.commit()
    finally:
        conn.close()


def get_open_commitments(limit: int = 100) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT * FROM commitments WHERE completed=0 "
                "ORDER BY due_date ASC LIMIT %s", (limit,)
            )
            return c.fetchall()
    finally:
        conn.close()


def get_due_commitments(days_ahead: int = 2) -> list[dict]:
    from datetime import timedelta
    conn = get_conn()
    try:
        cutoff = (datetime.now() + timedelta(days=days_ahead)).isoformat()
        with conn.cursor() as c:
            c.execute(
                "SELECT * FROM commitments WHERE completed=0 AND due_date <= %s "
                "ORDER BY due_date ASC", (cutoff,)
            )
            return c.fetchall()
    finally:
        conn.close()


def mark_commitment_done(commitment_id: int):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "UPDATE commitments SET completed=1, completed_at=%s WHERE id=%s",
                (datetime.now().isoformat(), commitment_id)
            )
        conn.commit()
    finally:
        conn.close()


def delete_commitment(commitment_id: int):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("DELETE FROM commitments WHERE id=%s", (commitment_id,))
        conn.commit()
    finally:
        conn.close()


def get_commitments_count() -> dict:
    from datetime import timedelta
    conn = get_conn()
    try:
        now    = datetime.now()
        today  = now.replace(hour=23, minute=59, second=59).isoformat()
        nowstr = now.isoformat()
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) AS n FROM commitments WHERE completed=0")
            open_ = c.fetchone()["n"]
            c.execute("SELECT COUNT(*) AS n FROM commitments WHERE completed=0 AND due_date<%s", (nowstr,))
            overdue = c.fetchone()["n"]
            c.execute("SELECT COUNT(*) AS n FROM commitments WHERE completed=0 AND due_date<=%s AND due_date>=%s", (today, nowstr))
            today_ = c.fetchone()["n"]
        return {"open": open_, "overdue": overdue, "today": today_}
    finally:
        conn.close()


def get_daily_stats(date: str = None) -> dict:
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status='sent'           THEN 1 ELSE 0 END) AS auto_sent,
                    SUM(CASE WHEN status='pending_review' THEN 1 ELSE 0 END) AS pending_review,
                    SUM(CASE WHEN status='manual'         THEN 1 ELSE 0 END) AS manual,
                    SUM(CASE WHEN status='filtered'       THEN 1 ELSE 0 END) AS filtered,
                    SUM(CASE WHEN status='rejected'       THEN 1 ELSE 0 END) AS rejected,
                    SUM(CASE WHEN status='error'          THEN 1 ELSE 0 END) AS errors
                FROM emails
                WHERE DATE(received_at) = %s
            """, (date,))
            row = c.fetchone()
        return row if row else {}
    finally:
        conn.close()


# ── Emails nach Status (für Web-UI Listen) ────────────────────────────────────

def get_emails_by_status(status: str, limit: int = 500) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, from_address, subject, received_at, processed_at, "
                "category, account_email, confidence, notes, snooze_until "
                "FROM emails WHERE status=%s ORDER BY received_at DESC LIMIT %s",
                (status, limit)
            )
            return c.fetchall()
    finally:
        conn.close()


def get_activity_log(limit: int = 100) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT timestamp, action, email_id, details "
                "FROM activity_log ORDER BY id DESC LIMIT %s",
                (limit,)
            )
            return c.fetchall()
    finally:
        conn.close()


def get_account_email_for_id(email_id: int) -> str:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT account_email FROM emails WHERE id=%s", (email_id,))
            row = c.fetchone()
        return (row["account_email"] or "") if row else ""
    finally:
        conn.close()


# ── Backup / Restore ──────────────────────────────────────────────────────────

BACKUP_TABLES = ["emails", "commitments", "templates", "learned_responses",
                 "activity_log", "tg_pending_map"]


def create_backup(label: str = None) -> int:
    """Exportiert alle Tabellen als JSON und speichert in db_backups. Gibt backup-ID zurück."""
    if not label:
        label = f"Backup {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    conn = get_conn()
    try:
        data = {}
        with conn.cursor() as c:
            for table in BACKUP_TABLES:
                c.execute(f"SELECT * FROM `{table}`")
                rows = c.fetchall()
                # datetime-Objekte zu String
                serialized = []
                for row in rows:
                    r = {}
                    for k, v in row.items():
                        if hasattr(v, "isoformat"):
                            r[k] = v.isoformat()
                        else:
                            r[k] = v
                    serialized.append(r)
                data[table] = serialized

            backup_json = json.dumps(data, ensure_ascii=False)
            c.execute(
                "INSERT INTO db_backups (label, data) VALUES (%s, %s)",
                (label, backup_json)
            )
            backup_id = c.lastrowid
        conn.commit()
        return backup_id
    finally:
        conn.close()


def get_backups() -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, created_at, label, "
                "LENGTH(data) AS size_bytes "
                "FROM db_backups ORDER BY created_at DESC"
            )
            rows = c.fetchall()
        for r in rows:
            if hasattr(r.get("created_at"), "isoformat"):
                r["created_at_str"] = r["created_at"].strftime("%d.%m.%Y %H:%M")
                r["created_at"] = r["created_at"].isoformat()
            else:
                r["created_at_str"] = str(r.get("created_at", ""))
            r["size_kb"] = round((r.get("size_bytes") or 0) / 1024, 1)
        return rows
    finally:
        conn.close()


def get_backup_data(backup_id: int) -> dict | None:
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT data, label FROM db_backups WHERE id=%s", (backup_id,))
            row = c.fetchone()
        if not row:
            return None
        return {"label": row["label"], "data": json.loads(row["data"])}
    finally:
        conn.close()


def restore_backup(backup_id: int) -> dict:
    """Stellt ein Backup wieder her. Gibt {'restored': {table: count}} zurück."""
    backup = get_backup_data(backup_id)
    if not backup:
        raise ValueError(f"Backup #{backup_id} nicht gefunden.")

    data = backup["data"]
    conn = get_conn()
    try:
        restored = {}
        with conn.cursor() as c:
            # Reihenfolge wegen Foreign Keys: erst abhängige Tabellen leeren
            for table in reversed(BACKUP_TABLES):
                c.execute(f"DELETE FROM `{table}`")
            conn.commit()

            for table in BACKUP_TABLES:
                rows = data.get(table, [])
                if not rows:
                    restored[table] = 0
                    continue
                cols = list(rows[0].keys())
                placeholders = ",".join(["%s"] * len(cols))
                col_str = ",".join(f"`{col}`" for col in cols)
                for row in rows:
                    vals = [row.get(col) for col in cols]
                    c.execute(
                        f"INSERT IGNORE INTO `{table}` ({col_str}) VALUES ({placeholders})",
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
        with conn.cursor() as c:
            c.execute("DELETE FROM db_backups WHERE id=%s", (backup_id,))
        conn.commit()
    finally:
        conn.close()
