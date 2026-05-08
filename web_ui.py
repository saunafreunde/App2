"""
E-Mail Agent – Web-UI für Approval-Workflow.

Starten:  python web_ui.py
Browser:  http://localhost:5000
"""

import sys
import os
import json
import socket
from functools import wraps
from pathlib import Path
from datetime import datetime, timedelta
from flask import (Flask, render_template, redirect, url_for,
                   request, flash, jsonify, session, Response)

# Windows UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
import database as db
import agent

CONFIG_PATH = Path(__file__).parent / "config.json"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "levando-email-agent-2026")
app.permanent_session_lifetime = timedelta(days=14)

# ── Login ─────────────────────────────────────────────────────────────────────
WEBUI_USER     = os.environ.get("WEBUI_USER", "")
WEBUI_PASSWORD = os.environ.get("WEBUI_PASSWORD", "")


@app.before_request
def _require_login():
    if not WEBUI_USER or not WEBUI_PASSWORD:
        return None  # kein Login konfiguriert (Entwicklung)
    if request.endpoint in ("login", "static"):
        return None
    if session.get("logged_in"):
        return None
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("user", "").strip()
        pw   = request.form.get("pw", "")
        if user == WEBUI_USER and pw == WEBUI_PASSWORD:
            session.permanent = True
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("Falsche Zugangsdaten", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    try:
        from config_loader import load_config as _load
        return _load()
    except ImportError:
        pass
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _pending_count() -> int:
    return len(db.get_pending_review_emails())


@app.context_processor
def _inject_counts():
    """Globale Sidebar-Counts in jedem Template verfügbar."""
    try:
        return {
            "aufgaben_count":  db.get_commitments_count().get("open", 0),
            "scheduled_count": len(db.get_scheduled_emails()),
        }
    except Exception:
        return {"aufgaben_count": 0, "scheduled_count": 0}


def _all_account_emails() -> list:
    cfg = load_config()
    accs = cfg.get("accounts") or [cfg.get("email", {})]
    return [a["email"] for a in accs if a.get("email")]


def _filter_emails(rows: list, account: str = "", period: str = "",
                   category: str = "", search: str = "") -> list:
    """Filter nach Konto, Zeitraum, Kategorie und Volltext-Suche."""
    if account:
        rows = [r for r in rows if (r.get("account_email") or "") == account]
    if category:
        rows = [r for r in rows if (r.get("category") or "").upper() == category.upper()]
    if search:
        s = search.lower()
        rows = [r for r in rows if
                s in (r.get("subject") or "").lower() or
                s in (r.get("from_address") or "").lower() or
                s in (r.get("body") or "").lower()]
    if period:
        now = datetime.now()
        if period == "today":
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            cutoff = now - timedelta(days=7)
        elif period == "month":
            cutoff = now - timedelta(days=30)
        else:
            cutoff = None
        if cutoff:
            iso = cutoff.isoformat()
            rows = [r for r in rows if (r.get("received_at") or r.get("processed_at") or "") >= iso]
    return rows


def _get_emails_by_status(status: str, limit: int = 500) -> list:
    return db.get_emails_by_status(status, limit)


def _get_activity_log(limit: int = 100) -> list:
    return db.get_activity_log(limit)


# ── Routen: Dashboard ─────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    cfg = load_config()
    accounts = cfg.get("accounts") or [cfg.get("email", {})]
    accounts_str = "  ·  ".join(a["email"] for a in accounts)
    pending = db.get_pending_review_emails()
    return render_template(
        "dashboard.html",
        active="dashboard",
        pending_count=len(pending),
        pending=pending,
        stats=db.get_daily_stats(),
        date=datetime.now().strftime("%d.%m.%Y"),
        accounts_str=accounts_str,
        top_rejections=db.get_top_rejection_reasons(5),
        top_senders=db.get_top_senders(5),
        accuracy=db.get_category_accuracy(),
    )


# ── Routen: Pending ──────────────────────────────────────────────────────────

@app.route("/pending")
def pending_view():
    filter_account = request.args.get("account", "").strip()
    pending = db.get_pending_review_emails()
    for p in pending:
        p["account_email"] = db.get_account_email_for_id(p["id"]) or p.get("account_email", "")
    if filter_account:
        pending = [p for p in pending if (p.get("account_email") or "") == filter_account]

    return render_template(
        "pending.html",
        active="pending",
        pending_count=len(db.get_pending_review_emails()),
        pending=pending,
        accounts=_all_account_emails(),
        filter_account=filter_account,
    )


@app.route("/email/<int:email_id>")
def email_detail(email_id: int):
    email = db.get_email_by_id(email_id)
    if not email:
        flash("E-Mail nicht gefunden.", "danger")
        return redirect(url_for("dashboard"))

    cfg = load_config()
    accs = cfg.get("accounts") or []
    sig = ""
    for a in accs:
        if a.get("email") == email.get("account_email"):
            sig = a.get("signature", "")
            break
    if not sig and accs:
        sig = accs[0].get("signature", "")

    return render_template(
        "email_detail.html",
        active="",
        pending_count=_pending_count(),
        email=email,
        signature_json=json.dumps(sig),
    )


# ── Test-Mail ──────────────────────────────────────────────────────────────────

@app.route("/send_test", methods=["GET", "POST"])
def send_test():
    to_addr = request.values.get("to", "").strip()
    if not to_addr:
        return ("Usage: /send_test?to=test@example.com", 400)
    cfg = load_config()
    accs = cfg.get("accounts") or []
    if not accs:
        return "Keine Konten konfiguriert.", 500
    from email_client import EmailClient
    ec = EmailClient(accs[0])
    body = (
        "Hallo Christoph,\n\n"
        "das ist eine Testmail vom Levando E-Mail Agent.\n\n"
        "Der Bot ist bereit für den produktiven Betrieb."
    )
    ts = datetime.now().strftime("%H:%M")
    try:
        ec.send_reply(to_addr, f"Testmail Levando v4 – Modern UI ({ts})", body)
        return f"Testmail gesendet an {to_addr}", 200
    except Exception as e:
        return f"Fehler: {e}", 500


# ── Vorschau-API ──────────────────────────────────────────────────────────────

@app.route("/preview_html", methods=["POST"])
def preview_html():
    data     = request.get_json(silent=True) or {}
    email_id = data.get("email_id")
    body     = data.get("body", "")
    cfg = load_config()
    accs = cfg.get("accounts") or []
    sig = ""
    from_addr = ""
    if email_id:
        em = db.get_email_by_id(int(email_id))
        if em:
            for a in accs:
                if a.get("email") == em.get("account_email"):
                    sig = a.get("signature", "")
                    from_addr = a.get("email", "")
                    break
    if not sig and accs:
        sig = accs[0].get("signature", "")
        from_addr = accs[0].get("email", "")
    from email_client import build_html_email
    html_out = build_html_email(body, sig, from_addr)
    return html_out


# ── Routen: Approve / Reject / Reprocess ─────────────────────────────────────

@app.route("/approve/<int:email_id>", methods=["POST"])
def approve(email_id: int):
    cfg = load_config()
    agent.setup(cfg)
    edited   = request.form.get("edited_draft", "").strip() or None
    send_now = request.form.get("send_now", "0") == "1"
    try:
        agent.approve_email(email_id, edited_body=edited, send_now=send_now)
        if send_now:
            flash(f"✓ E-Mail #{email_id} wurde sofort gesendet.", "success")
        else:
            flash(f"✓ E-Mail #{email_id} wurde genehmigt und für verzögerten Versand geplant.", "success")
    except Exception as e:
        flash(f"Fehler beim Senden: {e}", "danger")
    return redirect(request.referrer or url_for("pending_view"))


@app.route("/reject/<int:email_id>", methods=["POST"])
def reject(email_id: int):
    reason = request.form.get("reason", "").strip()
    cfg = load_config()
    agent.setup(cfg)
    try:
        agent.reject_email(email_id, reason)
        flash(f"✗ E-Mail #{email_id} abgelehnt" + (" – Lernfeedback gespeichert." if reason else "."), "warning")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    ref = request.referrer or ""
    if f"/email/{email_id}" in ref:
        return redirect(url_for("pending_view"))
    return redirect(ref or url_for("pending_view"))


@app.route("/reprocess/<int:email_id>")
def reprocess(email_id: int):
    cfg = load_config()
    agent.setup(cfg)
    try:
        ok = agent.reprocess_email(email_id)
        if ok:
            flash(f"✓ E-Mail #{email_id} wurde erneut verarbeitet.", "success")
        else:
            flash("E-Mail nicht gefunden.", "danger")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    return redirect(url_for("email_detail", email_id=email_id))


# ── Routen: Bulk-Aktionen ────────────────────────────────────────────────────

@app.route("/bulk", methods=["POST"])
def bulk():
    action = request.form.get("action", "")
    ids = request.form.getlist("ids")
    if not ids:
        flash("Keine E-Mails ausgewählt.", "warning")
        return redirect(url_for("pending_view"))
    cfg = load_config()
    agent.setup(cfg)
    success = fail = 0
    if action == "approve":
        for sid in ids:
            try:
                agent.approve_email(int(sid))
                success += 1
            except Exception:
                fail += 1
        flash(f"✓ {success} genehmigt" + (f", {fail} Fehler" if fail else "") + ".", "success")
    elif action == "reject":
        for sid in ids:
            try:
                agent.reject_email(int(sid), "Bulk-Ablehnung")
                success += 1
            except Exception:
                fail += 1
        flash(f"✗ {success} abgelehnt.", "warning")
    elif action == "filtered":
        try:
            db.bulk_update_status([int(i) for i in ids], "filtered", "Bulk: als Werbung markiert")
            for sid in ids:
                db.log_activity("filtered", int(sid), "Bulk")
            flash(f"⊘ {len(ids)} als Werbung markiert.", "secondary")
        except Exception as e:
            flash(f"Fehler: {e}", "danger")
    return redirect(url_for("pending_view"))


# ── Routen: Snooze ───────────────────────────────────────────────────────────

@app.route("/snooze/<int:email_id>", methods=["POST"])
def snooze(email_id: int):
    when = request.form.get("when", "1h")
    now = datetime.now()
    if when == "1h":
        target = now + timedelta(hours=1); label = "1 Stunde"
    elif when == "3h":
        target = now + timedelta(hours=3); label = "3 Stunden"
    elif when == "tomorrow":
        target = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        label = "morgen 8:00"
    elif when == "monday":
        days_ahead = (7 - now.weekday()) % 7 or 7
        target = (now + timedelta(days=days_ahead)).replace(hour=8, minute=0, second=0, microsecond=0)
        label = f"Montag {target.strftime('%d.%m. %H:%M')}"
    else:
        target = now + timedelta(hours=1); label = "1 Stunde"
    try:
        db.set_snooze(email_id, target.isoformat())
        db.log_activity("snooze", email_id, label)
        flash(f"💤 E-Mail #{email_id} – Erinnerung in {label}.", "info")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    return redirect(request.referrer or url_for("pending_view"))


@app.route("/unsnooze/<int:email_id>")
def unsnooze(email_id: int):
    try:
        db.update_email(email_id, status="pending_review", snooze_until=None)
        db.log_activity("unsnooze", email_id, "Manuell aufgeweckt")
        flash(f"⏰ E-Mail #{email_id} wieder aktiv.", "info")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    return redirect(url_for("pending_view"))


@app.route("/snoozed")
def snoozed_view():
    return render_template(
        "snoozed.html",
        active="snoozed",
        pending_count=_pending_count(),
        emails=db.get_snoozed_emails(),
    )


# ── Routen: Listen ───────────────────────────────────────────────────────────

def _list_view(status: str, **kwargs):
    filter_account  = request.args.get("account", "").strip()
    filter_period   = request.args.get("period", "").strip()
    filter_category = request.args.get("category", "").strip()
    filter_search   = request.args.get("q", "").strip()
    emails = _get_emails_by_status(status)
    emails = _filter_emails(emails, filter_account, filter_period,
                            filter_category, filter_search)
    return render_template(
        "list.html",
        pending_count=_pending_count(),
        emails=emails,
        accounts=_all_account_emails(),
        filter_account=filter_account,
        filter_period=filter_period,
        filter_category=filter_category,
        filter_search=filter_search,
        **kwargs
    )


@app.route("/sent")
def sent_view():
    return _list_view("sent",
        active="sent",
        title="Gesendete E-Mails",
        subtitle="Automatisch und manuell genehmigte Antworten",
        empty_text="Noch keine gesendeten E-Mails",
        icon="send",
        show_category=True, show_notes=False)


@app.route("/manual")
def manual_view():
    return _list_view("manual",
        active="manual",
        title="Manuelle Bearbeitung",
        subtitle="Portale & E-Mails mit niedriger Konfidenz",
        empty_text="Keine E-Mails zur manuellen Bearbeitung",
        icon="person-lines-fill",
        show_category=True, show_notes=True)


@app.route("/filtered")
def filtered_view():
    return _list_view("filtered",
        active="filtered",
        title="Gefilterte E-Mails",
        subtitle="Newsletter, Werbung und automatische Mails",
        empty_text="Noch keine gefilterten E-Mails",
        icon="funnel",
        show_category=False, show_notes=True)


@app.route("/rejected")
def rejected_view():
    return _list_view("rejected",
        active="rejected",
        title="Abgelehnte E-Mails",
        subtitle="Entwürfe die du abgelehnt hast – mit Begründungen",
        empty_text="Noch keine abgelehnten E-Mails",
        icon="x-octagon",
        show_category=True, show_notes=True)


# ── Routen: Vorlagen ─────────────────────────────────────────────────────────

@app.route("/templates")
def templates_list():
    tpls = db.get_templates()
    for t in tpls:
        try:
            kws = json.loads(t.get("keywords") or "[]")
            t["keywords"] = ", ".join(kws) if isinstance(kws, list) else (t.get("keywords") or "")
        except Exception:
            pass
    return render_template(
        "templates.html",
        active="templates",
        pending_count=_pending_count(),
        templates=tpls,
    )


@app.route("/templates/new", methods=["GET", "POST"])
def template_new():
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        category = request.form.get("category", "ALLGEMEIN")
        keywords = [k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()]
        subject  = request.form.get("subject_template", "").strip()
        body     = request.form.get("body_template", "").strip()
        if name and subject and body:
            db.save_template(name, category, keywords, subject, body)
            flash(f"✓ Vorlage '{name}' angelegt.", "success")
            return redirect(url_for("templates_list"))
        flash("Bitte alle Pflichtfelder ausfüllen.", "warning")
    return render_template(
        "template_form.html",
        active="templates",
        pending_count=_pending_count(),
        t=None,
        kw_str="",
    )


@app.route("/templates/<int:template_id>/edit", methods=["GET", "POST"])
def template_edit(template_id: int):
    t = db.get_template_by_id(template_id)
    if not t:
        flash("Vorlage nicht gefunden.", "danger")
        return redirect(url_for("templates_list"))
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        category = request.form.get("category", "ALLGEMEIN")
        keywords = [k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()]
        subject  = request.form.get("subject_template", "").strip()
        body     = request.form.get("body_template", "").strip()
        db.update_template(template_id, name, category, keywords, subject, body)
        flash(f"✓ Vorlage '{name}' gespeichert.", "success")
        return redirect(url_for("templates_list"))
    try:
        kws = json.loads(t.get("keywords") or "[]")
        kw_str = ", ".join(kws) if isinstance(kws, list) else (t.get("keywords") or "")
    except Exception:
        kw_str = t.get("keywords") or ""
    return render_template(
        "template_form.html",
        active="templates",
        pending_count=_pending_count(),
        t=t,
        kw_str=kw_str,
    )


@app.route("/templates/<int:template_id>/delete", methods=["POST"])
def template_delete(template_id: int):
    db.delete_template(template_id)
    flash("Vorlage gelöscht.", "warning")
    return redirect(url_for("templates_list"))


# ── Aufgaben / Versprechen ───────────────────────────────────────────────────

@app.route("/aufgaben")
def aufgaben_view():
    commits = db.get_open_commitments(200)
    now = datetime.now()
    today_end = now.replace(hour=23, minute=59, second=59)

    def fmt(c):
        d = datetime.fromisoformat(c["due_date"])
        c["due_dt"]  = d
        c["due_str"] = d.strftime("%d.%m.%Y %H:%M")
        return c

    commits = [fmt(c) for c in commits]
    overdue = [c for c in commits if c["due_dt"] < now]
    today_  = [c for c in commits if now <= c["due_dt"] <= today_end]
    future  = [c for c in commits if c["due_dt"] > today_end]

    return render_template(
        "aufgaben.html",
        active="aufgaben",
        pending_count=_pending_count(),
        groups={"overdue": overdue, "today": today_, "future": future},
    )


@app.route("/aufgaben/<int:cid>/done", methods=["POST"])
def aufgaben_done(cid: int):
    db.mark_commitment_done(cid)
    flash("Versprechen als erledigt markiert.", "success")
    return redirect(url_for("aufgaben_view"))


# ── Geplante E-Mails (Versand-Queue) ─────────────────────────────────────────

@app.route("/scheduled")
def scheduled_view():
    rows = db.get_scheduled_emails()
    now = datetime.now()
    for r in rows:
        if r.get("send_at"):
            d = datetime.fromisoformat(r["send_at"])
            r["send_str"] = d.strftime("%d.%m. %H:%M")
            delta = d - now
            mins  = int(delta.total_seconds() / 60)
            if mins < 60:
                r["in_str"] = f"in {mins} Min"
            else:
                r["in_str"] = f"in {mins // 60}h {mins % 60}m"
        else:
            r["send_str"] = "—"
            r["in_str"]   = "—"
    return render_template(
        "scheduled.html",
        active="scheduled",
        pending_count=_pending_count(),
        emails=rows,
    )


@app.route("/scheduled/<int:email_id>/now", methods=["POST"])
def scheduled_send_now(email_id: int):
    cfg = load_config()
    agent.setup(cfg)
    try:
        agent.approve_email(email_id, send_now=True)
        flash("Sofort gesendet.", "success")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    return redirect(url_for("scheduled_view"))


# ── Routen: Log / Search / Run ───────────────────────────────────────────────

@app.route("/log")
def log_view():
    return render_template(
        "log.html",
        active="log",
        pending_count=_pending_count(),
        log=_get_activity_log(),
    )


@app.route("/run")
def run_now():
    cfg = load_config()
    db.init_db()
    agent.setup(cfg)
    try:
        agent.process_all_emails()
        flash("E-Mails wurden abgerufen und verarbeitet.", "success")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    results = db.search_emails(query) if query else []
    return render_template(
        "search.html",
        active="",
        pending_count=_pending_count(),
        query=query,
        results=results,
    )


# ── APIs ─────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    stats = db.get_daily_stats()
    return jsonify({**dict(stats), "pending_review": _pending_count()})


@app.route("/api/weekly_stats")
def api_weekly_stats():
    return jsonify(db.get_weekly_stats())


@app.route("/api/health")
def api_health():
    """System-Health-Check: IMAP/SMTP/Claude/Telegram."""
    cfg = load_config()
    health = {}
    try:
        accs = cfg.get("accounts") or [cfg.get("email", {})]
        acc  = accs[0] if accs else {}
        srv  = acc.get("imap_server", "")
        port = int(acc.get("imap_port", 993))
        s = socket.create_connection((srv, port), timeout=4); s.close()
        health["imap"] = {"ok": True, "detail": f"{srv}:{port}"}
    except Exception as e:
        health["imap"] = {"ok": False, "detail": str(e)[:60]}
    try:
        srv  = acc.get("smtp_server", "")
        port = int(acc.get("smtp_port", 465))
        s = socket.create_connection((srv, port), timeout=4); s.close()
        health["smtp"] = {"ok": True, "detail": f"{srv}:{port}"}
    except Exception as e:
        health["smtp"] = {"ok": False, "detail": str(e)[:60]}

    api_key = cfg.get("claude", {}).get("api_key", "")
    health["claude"] = {"ok": api_key.startswith("sk-ant-"),
                        "detail": "Schlüssel gesetzt" if api_key.startswith("sk-ant-") else "kein gültiger Key"}

    try:
        import urllib.request
        token = cfg.get("telegram", {}).get("bot_token", "")
        if token and token != "DEIN_BOT_TOKEN":
            url = f"https://api.telegram.org/bot{token}/getMe"
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.loads(r.read())
            if data.get("ok"):
                health["telegram"] = {"ok": True, "detail": "@" + data["result"].get("username", "?")}
            else:
                health["telegram"] = {"ok": False, "detail": "Token ungültig"}
        else:
            health["telegram"] = {"ok": False, "detail": "Nicht konfiguriert"}
    except Exception as e:
        health["telegram"] = {"ok": False, "detail": str(e)[:60]}

    health["last_check"] = datetime.now().strftime("%H:%M:%S")
    return jsonify(health)


# ── Routen: Telegram ─────────────────────────────────────────────────────────

@app.route("/telegram/test")
def telegram_test():
    try:
        import telegram_notify as tg
        ok = tg.send_message("✅ <b>Levando E-Mail Agent – Web-UI</b>\n\nTelegram funktioniert!")
        flash("✓ Telegram-Testnachricht gesendet." if ok else "Telegram nicht erreichbar.",
              "success" if ok else "warning")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/todo/generate")
def todo_generate():
    try:
        import todo_report as tr
        path, todos = tr.send_todo_pdf()
        flash(f"✓ ToDo-Liste mit {len(todos)} Aufgaben gesendet ({path.name}).", "success")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/telegram/report")
def telegram_report():
    cfg = load_config()
    db.init_db()
    agent.setup(cfg)
    try:
        import telegram_notify as tg
        report = agent.generate_daily_report()
        ok = tg.send_report(report, db.get_daily_stats())
        flash("✓ Report per Telegram gesendet." if ok else "Telegram-Versand fehlgeschlagen.",
              "success" if ok else "warning")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    return redirect(url_for("dashboard"))


# ── Backup / Restore ─────────────────────────────────────────────────────────

@app.route("/backup")
def backup_view():
    backups = db.get_backups()
    return render_template(
        "backup.html",
        active="backup",
        pending_count=_pending_count(),
        backups=backups,
    )


@app.route("/backup/create", methods=["POST"])
def backup_create():
    label = request.form.get("label", "").strip() or None
    try:
        backup_id = db.create_backup(label)
        # Backup-Daten für Download laden
        bk = db.get_backup_data(backup_id)
        backups_list = db.get_backups()
        size_kb = next((b["size_kb"] for b in backups_list if b["id"] == backup_id), "?")
        flash(f"✓ Backup #{backup_id} erstellt ({size_kb} KB) – wird heruntergeladen.", "success")
        import json as _json
        json_bytes = _json.dumps(bk["data"], ensure_ascii=False, indent=2).encode("utf-8")
        filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return Response(
            json_bytes,
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        flash(f"Backup-Fehler: {e}", "danger")
        return redirect(url_for("backup_view"))


@app.route("/backup/restore/<int:backup_id>", methods=["POST"])
def backup_restore(backup_id: int):
    try:
        restored = db.restore_backup(backup_id)
        total = sum(restored.values())
        flash(f"✓ Backup #{backup_id} eingespielt – {total} Datensätze wiederhergestellt.", "success")
    except Exception as e:
        flash(f"Restore-Fehler: {e}", "danger")
    return redirect(url_for("backup_view"))


@app.route("/backup/delete/<int:backup_id>", methods=["POST"])
def backup_delete(backup_id: int):
    try:
        db.delete_backup(backup_id)
        flash(f"Backup #{backup_id} gelöscht.", "warning")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    return redirect(url_for("backup_view"))


# ── Start ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db.init_db()
    print("\n" + "=" * 52)
    print("  E-Mail Agent – Web-UI  (Modern Dark UI)")
    print("=" * 52)
    print("  Browser:  http://localhost:5000")
    print("  Beenden:  STRG+C")
    print("=" * 52 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
