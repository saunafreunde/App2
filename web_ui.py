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
from flask import (Flask, render_template_string, redirect, url_for,
                   request, flash, jsonify, session)

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


LOGIN_HTML = """<!DOCTYPE html><html lang="de"><head>
<meta charset="UTF-8"><title>Login – Levando Email Agent</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
*{box-sizing:border-box}
body{background:linear-gradient(135deg,#1a2035 0%,#2d3a5c 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif;margin:0;padding:16px;-webkit-text-size-adjust:100%}
.box{background:#fff;border-radius:14px;box-shadow:0 10px 40px rgba(0,0,0,.3);padding:38px 32px;width:100%;max-width:360px}
.logo{text-align:center;margin-bottom:22px}.logo h1{font-size:1.3rem;font-weight:700;color:#1a2035;margin:0}
.logo p{color:#6c757d;font-size:.85rem;margin:4px 0 0}
.form-control{padding:13px 14px;font-size:16px}
.btn-primary{background:#1a2035;border-color:#1a2035;padding:12px;font-weight:600;font-size:15px}
.btn-primary:hover{background:#2d3a5c;border-color:#2d3a5c}
@media(max-width:480px){.box{padding:30px 22px;border-radius:12px}}
</style></head>
<body><div class="box">
<div class="logo"><h1>Levando Email Agent</h1><p>Bitte einloggen</p></div>
{% with msgs = get_flashed_messages() %}{% if msgs %}<div class="alert alert-danger">{{ msgs[0] }}</div>{% endif %}{% endwith %}
<form method="post"><input class="form-control mb-3" name="user" placeholder="Benutzer" autocomplete="username" autofocus required>
<input class="form-control mb-3" type="password" name="pw" placeholder="Passwort" autocomplete="current-password" required>
<button class="btn btn-primary w-100">Einloggen</button></form></div></body></html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("user", "").strip()
        pw   = request.form.get("pw", "")
        if user == WEBUI_USER and pw == WEBUI_PASSWORD:
            session.permanent = True
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("Falsche Zugangsdaten")
    return render_template_string(LOGIN_HTML)


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


# ── HTML-Templates ────────────────────────────────────────────────────────────

BASE = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}E-Mail Agent{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
  <style>
    body { background: #f0f2f5; font-size: 0.92rem; -webkit-text-size-adjust:100%; }
    /* Layout */
    .layout { display: flex; min-height: 100vh; }
    .sidebar { width: 230px; min-width: 230px; background: #1a2035; padding-top: 1rem; }
    .main-content { flex: 1; padding: 24px 32px; min-width: 0; }
    /* Sidebar Items */
    .sidebar .nav-link { color: #adb5bd; border-radius: 8px; margin: 2px 8px; padding: 9px 14px; font-size: .92rem; }
    .sidebar .nav-link:hover, .sidebar .nav-link.active { background: #2d3a5c; color: #fff; }
    .sidebar .nav-link i { width: 22px; }
    .sidebar .brand { color: #fff; font-size: 1.1rem; font-weight: 700; padding: 12px 22px 20px; }
    .sidebar .badge-nav { float: right; margin-top: 2px; }
    .sidebar .nav-section { color: #6c7a99; font-size: .72rem; text-transform: uppercase;
                            letter-spacing: 1px; padding: 14px 22px 6px; }
    /* Mobile Top-Bar */
    .topbar-mobile { display: none; background: #1a2035; color: #fff; padding: 12px 16px;
                     position: sticky; top: 0; z-index: 1030; box-shadow: 0 2px 8px rgba(0,0,0,.15); }
    .topbar-mobile .toggle-btn { background: transparent; border: 0; color: #fff; padding: 4px 8px;
                                 font-size: 1.5rem; line-height: 1; }
    .topbar-mobile .brand-mobile { font-weight: 700; font-size: 1rem; }
    /* Cards & Stats */
    .stat-card { border: none; border-radius: 14px; box-shadow: 0 2px 12px rgba(0,0,0,.07); }
    .stat-card .card-body { padding: 16px 18px; }
    .stat-icon { width: 42px; height: 42px; border-radius: 11px; display: flex;
                 align-items: center; justify-content: center; font-size: 1.25rem; }
    .email-row:hover { background: #f8f9ff !important; cursor: pointer; }
    .email-row td { word-break: break-word; }
    .badge-cat { font-size: .72rem; font-weight: 600; letter-spacing: .3px; }
    .conf-bar  { height: 6px; border-radius: 3px; background: #e9ecef; }
    .conf-fill { height: 6px; border-radius: 3px; }
    .body-box  { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
                 padding: 14px 16px; font-size: .88rem; white-space: pre-wrap; max-height: 320px;
                 overflow-y: auto; font-family: inherit; word-break: break-word; }
    .page-header { font-size: 1.35rem; font-weight: 700; color: #1a2035; margin-bottom: 6px; }
    .text-muted-sm { font-size: .82rem; color: #6c757d; }
    .log-row td { font-size: .82rem; vertical-align: middle; }
    .empty-state { text-align: center; padding: 60px 20px; color: #6c757d; }
    .empty-state i { font-size: 3rem; display: block; margin-bottom: 12px; color: #adb5bd; }
    .email-card { transition: outline .15s; }
    kbd { background: #f1f3f5; color: #495057; border: 1px solid #ced4da;
          border-radius: 4px; padding: 2px 6px; font-size: .78rem; }
    .filter-pills .btn { font-size: .82rem; padding: 4px 12px; }
    .filter-pills .btn.active { background: #0d6efd; color: #fff; border-color: #0d6efd; }
    .health-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
                  margin-right: 6px; vertical-align: middle; }
    .health-ok { background: #198754; box-shadow: 0 0 6px #19875466; }
    .health-fail { background: #dc3545; }
    .health-unknown { background: #adb5bd; }

    /* Sidebar als Off-Canvas auf Mobile/Tablet */
    @media (max-width: 991.98px) {
      .layout { display: block; }
      .topbar-mobile { display: flex; align-items: center; justify-content: space-between; }
      .sidebar { position: fixed; top: 0; left: 0; bottom: 0; z-index: 1050;
                 transform: translateX(-100%); transition: transform .25s ease;
                 box-shadow: 4px 0 16px rgba(0,0,0,.2); overflow-y: auto; }
      .sidebar.open { transform: translateX(0); }
      .sidebar-backdrop { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.4);
                          z-index: 1040; }
      .sidebar-backdrop.active { display: block; }
      .main-content { padding: 16px 14px; }
      .page-header { font-size: 1.15rem; }
      .stat-card .card-body { padding: 12px 14px; }
      .stat-icon { width: 36px; height: 36px; font-size: 1rem; }
      /* Tabellen scrollbar machen */
      .table-responsive-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
      .table-responsive-wrap table { min-width: 540px; }
      /* Form-Filter stacken */
      .filter-pills { gap: 6px !important; }
      .modal-dialog { margin: 8px; }
      .body-box { font-size: .85rem; padding: 12px; }
      h5 { font-size: 1rem; }
      .btn { font-size: .88rem; }
    }
    @media (max-width: 480px) {
      .main-content { padding: 12px 10px; }
      .sidebar .nav-link { font-size: .95rem; padding: 11px 14px; }
      table.table th, table.table td { padding: 8px 6px; font-size: .82rem; }
    }
  </style>
</head>
<body>
<!-- Mobile Top-Bar -->
<div class="topbar-mobile">
  <button class="toggle-btn" id="sidebarToggle" aria-label="Menü öffnen">
    <i class="bi bi-list"></i>
  </button>
  <div class="brand-mobile"><i class="bi bi-envelope-check me-1"></i> Mail Agent</div>
  <a href="/logout" class="text-white text-decoration-none small"><i class="bi bi-box-arrow-right"></i></a>
</div>

<!-- Backdrop für mobile Sidebar -->
<div class="sidebar-backdrop" id="sidebarBackdrop"></div>

<div class="layout">
    <!-- Sidebar -->
    <nav class="sidebar" id="sidebar">
      <div class="brand"><i class="bi bi-envelope-check me-2"></i>Mail Agent</div>
      <ul class="nav flex-column">
        <li class="nav-item">
          <a class="nav-link {% if active=='dashboard' %}active{% endif %}" href="/">
            <i class="bi bi-speedometer2 me-2"></i>Dashboard
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link {% if active=='pending' %}active{% endif %}" href="/pending">
            <i class="bi bi-hourglass-split me-2"></i>Zur Prüfung
            {% if pending_count > 0 %}<span class="badge bg-danger badge-nav">{{ pending_count }}</span>{% endif %}
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link {% if active=='aufgaben' %}active{% endif %}" href="/aufgaben">
            <i class="bi bi-bookmark-star me-2"></i>Aufgaben
            {% if aufgaben_count > 0 %}<span class="badge bg-warning text-dark badge-nav">{{ aufgaben_count }}</span>{% endif %}
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link {% if active=='scheduled' %}active{% endif %}" href="/scheduled">
            <i class="bi bi-clock-history me-2"></i>Geplant
            {% if scheduled_count > 0 %}<span class="badge bg-info badge-nav">{{ scheduled_count }}</span>{% endif %}
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link {% if active=='snoozed' %}active{% endif %}" href="/snoozed">
            <i class="bi bi-moon me-2"></i>Snooze
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link {% if active=='sent' %}active{% endif %}" href="/sent">
            <i class="bi bi-send-check me-2"></i>Gesendet
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link {% if active=='manual' %}active{% endif %}" href="/manual">
            <i class="bi bi-person-lines-fill me-2"></i>Manuell
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link {% if active=='filtered' %}active{% endif %}" href="/filtered">
            <i class="bi bi-funnel me-2"></i>Gefiltert
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link {% if active=='rejected' %}active{% endif %}" href="/rejected">
            <i class="bi bi-x-octagon me-2"></i>Abgelehnt
          </a>
        </li>

        <div class="nav-section">Verwalten</div>
        <li class="nav-item">
          <a class="nav-link {% if active=='templates' %}active{% endif %}" href="/templates">
            <i class="bi bi-file-text me-2"></i>Vorlagen
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link {% if active=='log' %}active{% endif %}" href="/log">
            <i class="bi bi-journal-text me-2"></i>Aktivitäten
          </a>
        </li>

        <div class="nav-section">Aktionen</div>
        <li class="nav-item">
          <a class="nav-link" href="/run" onclick="return confirm('Jetzt E-Mails abrufen und verarbeiten?')">
            <i class="bi bi-arrow-repeat me-2"></i>Jetzt prüfen
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link" href="/telegram/report" onclick="return confirm('Report jetzt per Telegram senden?')">
            <i class="bi bi-telegram me-2"></i>Report senden
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link" href="/telegram/test">
            <i class="bi bi-send me-2"></i>Telegram testen
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link" href="/todo/generate" onclick="return confirm('Tages-ToDo-Liste jetzt erzeugen und versenden?')">
            <i class="bi bi-list-check me-2"></i>ToDo-Liste jetzt
          </a>
        </li>
      </ul>
    </nav>

    <!-- Main -->
    <main class="main-content">
      <form action="/search" method="get" class="mb-3">
        <div class="input-group input-group-sm" style="max-width:420px;">
          <span class="input-group-text bg-white border-end-0"><i class="bi bi-search text-muted"></i></span>
          <input type="text" name="q" class="form-control border-start-0 ps-0"
                 placeholder="E-Mails suchen (Betreff, Absender, Inhalt …)"
                 value="{{ request.args.get('q','') }}" autocomplete="off">
          <button class="btn btn-outline-secondary" type="submit">Suchen</button>
        </div>
      </form>

      {% with messages = get_flashed_messages(with_categories=true) %}
        {% for cat, msg in messages %}
          <div class="alert alert-{{ cat }} alert-dismissible fade show" role="alert">
            {{ msg }}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
          </div>
        {% endfor %}
      {% endwith %}

      {% block content %}{% endblock %}
    </main>
</div>

<!-- Globales Ablehnen-Modal -->
<div class="modal fade" id="rejectModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-sm modal-dialog-centered">
    <div class="modal-content">
      <form method="post" id="rejectForm">
        <div class="modal-header border-0 pb-0">
          <h6 class="modal-title"><i class="bi bi-x-circle text-danger me-2"></i>E-Mail ablehnen</h6>
          <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body pt-2">
          <p class="text-muted-sm mb-2" id="rejectSubject"></p>
          <label class="form-label text-muted-sm mb-1">Begründung (optional, hilft beim Lernen):</label>
          <textarea name="reason" id="rejectReason" class="form-control form-control-sm"
                    rows="3" placeholder="z.B. Ton zu förmlich, falsche Produktinfo …"></textarea>
        </div>
        <div class="modal-footer border-0 pt-0">
          <button type="button" class="btn btn-sm btn-light" data-bs-dismiss="modal">Abbrechen</button>
          <button type="submit" class="btn btn-sm btn-danger">
            <i class="bi bi-x-lg me-1"></i>Ablehnen
          </button>
        </div>
      </form>
    </div>
  </div>
</div>

<!-- Globales Snooze-Modal -->
<div class="modal fade" id="snoozeModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-sm modal-dialog-centered">
    <div class="modal-content">
      <form method="post" id="snoozeForm">
        <div class="modal-header border-0 pb-0">
          <h6 class="modal-title"><i class="bi bi-moon text-info me-2"></i>Erinnerung später</h6>
          <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body pt-2">
          <p class="text-muted-sm mb-3" id="snoozeSubject"></p>
          <div class="d-grid gap-2">
            <button type="submit" name="when" value="1h"       class="btn btn-outline-primary btn-sm">In 1 Stunde</button>
            <button type="submit" name="when" value="3h"       class="btn btn-outline-primary btn-sm">In 3 Stunden</button>
            <button type="submit" name="when" value="tomorrow" class="btn btn-outline-primary btn-sm">Morgen 8:00</button>
            <button type="submit" name="when" value="monday"   class="btn btn-outline-primary btn-sm">Nächsten Montag 8:00</button>
          </div>
        </div>
      </form>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
// Mobile Sidebar Toggle
(function(){
  const sidebar = document.getElementById('sidebar');
  const toggle  = document.getElementById('sidebarToggle');
  const backdrop = document.getElementById('sidebarBackdrop');
  if (!sidebar || !toggle || !backdrop) return;
  function open()  { sidebar.classList.add('open');  backdrop.classList.add('active'); document.body.style.overflow = 'hidden'; }
  function close() { sidebar.classList.remove('open'); backdrop.classList.remove('active'); document.body.style.overflow = ''; }
  toggle.addEventListener('click', open);
  backdrop.addEventListener('click', close);
  // Beim Klick auf Link in Sidebar → schließen
  sidebar.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
    if (window.innerWidth < 992) setTimeout(close, 100);
  }));
})();

// Tabellen automatisch in scroll-wrapper packen (für Mobile)
(function(){
  document.querySelectorAll('main.main-content table.table').forEach(tbl => {
    if (tbl.parentElement.classList.contains('table-responsive-wrap') ||
        tbl.parentElement.classList.contains('card-body')) {
      // Bei Cards: das card-body bekommt den scroll-wrapper
      const parent = tbl.closest('.card-body');
      if (parent && !parent.classList.contains('table-responsive-wrap')) {
        parent.classList.add('table-responsive-wrap');
      }
      return;
    }
    const wrap = document.createElement('div');
    wrap.className = 'table-responsive-wrap';
    tbl.parentElement.insertBefore(wrap, tbl);
    wrap.appendChild(tbl);
  });
})();

// Globaler Reject-Handler
(function(){
  const modal = document.getElementById('rejectModal');
  if (!modal) return;
  const form = document.getElementById('rejectForm');
  const subjEl = document.getElementById('rejectSubject');
  const reasonEl = document.getElementById('rejectReason');
  const bsModal = new bootstrap.Modal(modal);
  document.body.addEventListener('click', function(ev){
    const btn = ev.target.closest('[data-reject-id]');
    if (!btn) return;
    ev.preventDefault(); ev.stopPropagation();
    form.action = '/reject/' + btn.getAttribute('data-reject-id');
    subjEl.textContent = btn.getAttribute('data-reject-subject') || '';
    reasonEl.value = '';
    bsModal.show();
    setTimeout(()=>reasonEl.focus(), 300);
  });
})();
// Globaler Snooze-Handler
(function(){
  const modal = document.getElementById('snoozeModal');
  if (!modal) return;
  const form = document.getElementById('snoozeForm');
  const subjEl = document.getElementById('snoozeSubject');
  const bsModal = new bootstrap.Modal(modal);
  document.body.addEventListener('click', function(ev){
    const btn = ev.target.closest('[data-snooze-id]');
    if (!btn) return;
    ev.preventDefault(); ev.stopPropagation();
    form.action = '/snooze/' + btn.getAttribute('data-snooze-id');
    subjEl.textContent = btn.getAttribute('data-snooze-subject') || '';
    bsModal.show();
  });
})();
</script>

</body>
</html>"""


# ── Dashboard ─────────────────────────────────────────────────────────────────

DASHBOARD_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<meta http-equiv="refresh" content="60">
<div class="d-flex justify-content-between align-items-center mb-4">
  <div>
    <div class="page-header">Dashboard</div>
    <div class="text-muted-sm">{{ date }}  &nbsp;|&nbsp;  {{ accounts_str }}</div>
  </div>
  <a href="/run" class="btn btn-primary btn-sm" onclick="return confirm('E-Mails jetzt abrufen?')">
    <i class="bi bi-arrow-repeat me-1"></i>Jetzt prüfen
  </a>
</div>

<!-- Stats -->
<div class="row g-3 mb-4">
  <div class="col-6 col-xl-2">
    <div class="card stat-card h-100"><div class="card-body d-flex align-items-center gap-3">
      <div class="stat-icon bg-primary bg-opacity-10 text-primary"><i class="bi bi-envelope"></i></div>
      <div><div class="fw-bold fs-4">{{ stats.total or 0 }}</div><div class="text-muted-sm">Heute gesamt</div></div>
    </div></div>
  </div>
  <div class="col-6 col-xl-2">
    <div class="card stat-card h-100"><div class="card-body d-flex align-items-center gap-3">
      <div class="stat-icon bg-success bg-opacity-10 text-success"><i class="bi bi-send-check"></i></div>
      <div><div class="fw-bold fs-4">{{ stats.auto_sent or 0 }}</div><div class="text-muted-sm">Auto gesendet</div></div>
    </div></div>
  </div>
  <div class="col-6 col-xl-2">
    <div class="card stat-card h-100"><div class="card-body d-flex align-items-center gap-3">
      <div class="stat-icon bg-warning bg-opacity-10 text-warning"><i class="bi bi-hourglass-split"></i></div>
      <div><div class="fw-bold fs-4">{{ stats.pending_review or 0 }}</div><div class="text-muted-sm">Zur Prüfung</div></div>
    </div></div>
  </div>
  <div class="col-6 col-xl-2">
    <div class="card stat-card h-100"><div class="card-body d-flex align-items-center gap-3">
      <div class="stat-icon bg-info bg-opacity-10 text-info"><i class="bi bi-person-lines-fill"></i></div>
      <div><div class="fw-bold fs-4">{{ stats.manual or 0 }}</div><div class="text-muted-sm">Manuell</div></div>
    </div></div>
  </div>
  <div class="col-6 col-xl-2">
    <div class="card stat-card h-100"><div class="card-body d-flex align-items-center gap-3">
      <div class="stat-icon bg-secondary bg-opacity-10 text-secondary"><i class="bi bi-funnel"></i></div>
      <div><div class="fw-bold fs-4">{{ stats.filtered or 0 }}</div><div class="text-muted-sm">Gefiltert</div></div>
    </div></div>
  </div>
  <div class="col-6 col-xl-2">
    <div class="card stat-card h-100"><div class="card-body d-flex align-items-center gap-3">
      <div class="stat-icon bg-danger bg-opacity-10 text-danger"><i class="bi bi-x-octagon"></i></div>
      <div><div class="fw-bold fs-4">{{ stats.rejected or 0 }}</div><div class="text-muted-sm">Abgelehnt</div></div>
    </div></div>
  </div>
</div>

<div class="row g-3 mb-4">
  <!-- Wochendiagramm -->
  <div class="col-lg-8">
    <div class="card border-0 shadow-sm h-100" style="border-radius:14px;">
      <div class="card-body px-4 py-3">
        <h6 class="mb-2 fw-bold"><i class="bi bi-bar-chart-line me-2 text-primary"></i>Letzte 7 Tage</h6>
        <canvas id="weekChart" height="100"></canvas>
      </div>
    </div>
  </div>

  <!-- System Health -->
  <div class="col-lg-4">
    <div class="card border-0 shadow-sm h-100" style="border-radius:14px;">
      <div class="card-body">
        <h6 class="mb-3 fw-bold"><i class="bi bi-heart-pulse me-2 text-danger"></i>System-Status</h6>
        <div id="healthBox">
          <div class="text-muted-sm"><span class="health-dot health-unknown"></span>IMAP wird geprüft...</div>
          <div class="text-muted-sm"><span class="health-dot health-unknown"></span>SMTP wird geprüft...</div>
          <div class="text-muted-sm"><span class="health-dot health-unknown"></span>Claude-API wird geprüft...</div>
          <div class="text-muted-sm"><span class="health-dot health-unknown"></span>Telegram wird geprüft...</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Lern-Statistik -->
<div class="row g-3 mb-4">
  <div class="col-lg-4">
    <div class="card border-0 shadow-sm h-100" style="border-radius:14px;">
      <div class="card-body">
        <h6 class="mb-3 fw-bold"><i class="bi bi-x-circle me-2 text-danger"></i>Top Ablehnungsgründe</h6>
        {% if top_rejections %}
          {% for r in top_rejections %}
          <div class="mb-2 small">
            <span class="badge bg-danger bg-opacity-10 text-danger me-2">{{ r.count }}×</span>
            {{ (r.reason or '')[:60] }}
          </div>
          {% endfor %}
        {% else %}
          <div class="text-muted-sm">Noch keine Ablehnungen mit Begründung.</div>
        {% endif %}
      </div>
    </div>
  </div>
  <div class="col-lg-4">
    <div class="card border-0 shadow-sm h-100" style="border-radius:14px;">
      <div class="card-body">
        <h6 class="mb-3 fw-bold"><i class="bi bi-people me-2 text-primary"></i>Top Absender (30 Tage)</h6>
        {% if top_senders %}
          {% for s in top_senders %}
          <div class="mb-2 small">
            <span class="badge bg-primary bg-opacity-10 text-primary me-2">{{ s.total }}</span>
            {{ (s.from_address or '')[:50] }}
          </div>
          {% endfor %}
        {% else %}
          <div class="text-muted-sm">Noch keine Daten.</div>
        {% endif %}
      </div>
    </div>
  </div>
  <div class="col-lg-4">
    <div class="card border-0 shadow-sm h-100" style="border-radius:14px;">
      <div class="card-body">
        <h6 class="mb-3 fw-bold"><i class="bi bi-graph-up me-2 text-success"></i>Genauigkeit pro Kategorie</h6>
        {% if accuracy %}
          {% for a in accuracy %}
          <div class="mb-2 small d-flex justify-content-between align-items-center">
            <span>{{ a.category }} <span class="text-muted-sm">({{ a.total }})</span></span>
            <span class="badge bg-{{ 'success' if a.accuracy >= 0.85 else ('warning' if a.accuracy >= 0.6 else 'danger') }}">
              {{ (a.accuracy*100)|int }}%
            </span>
          </div>
          {% endfor %}
        {% else %}
          <div class="text-muted-sm">Mindestens 2 Mails pro Kategorie nötig.</div>
        {% endif %}
      </div>
    </div>
  </div>
</div>

<!-- Pending Quick-Liste -->
{% if pending %}
<div class="card border-0 shadow-sm mb-4" style="border-radius:14px;">
  <div class="card-header bg-white border-bottom-0 pt-3 pb-0 px-4" style="border-radius:14px 14px 0 0;">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h6 class="mb-0 fw-bold"><i class="bi bi-hourglass-split text-warning me-2"></i>Warten auf Prüfung</h6>
      <a href="/pending" class="btn btn-sm btn-outline-primary">Alle bearbeiten</a>
    </div>
  </div>
  <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <thead class="table-light" style="font-size:.82rem;">
        <tr><th class="ps-4" style="width:40px;">#</th><th>Betreff</th><th>Von</th>
            <th style="width:110px;">Konfidenz</th><th style="width:100px;">Kategorie</th><th style="width:120px;"></th></tr>
      </thead>
      <tbody>
        {% for e in pending %}
        <tr class="email-row">
          <td class="ps-4 text-muted" onclick="location.href='/email/{{ e.id }}'">{{ e.id }}</td>
          <td class="fw-semibold" onclick="location.href='/email/{{ e.id }}'">{{ (e.subject or '–')[:55] }}</td>
          <td class="text-muted" onclick="location.href='/email/{{ e.id }}'">{{ (e.from_address or '')[:40] }}</td>
          <td onclick="location.href='/email/{{ e.id }}'">
            <div class="conf-bar"><div class="conf-fill bg-{{ 'success' if (e.confidence or 0) >= 0.75 else 'warning' }}" style="width:{{ ((e.confidence or 0)*100)|int }}%"></div></div>
            <div class="text-muted-sm mt-1">{{ ((e.confidence or 0)*100)|int }}%</div>
          </td>
          <td onclick="location.href='/email/{{ e.id }}'">
            {% set cat_colors = {'ANFRAGE':'primary','BESCHWERDE':'danger','BESTELLUNG':'success','SUPPORT':'info','ALLGEMEIN':'secondary'} %}
            <span class="badge badge-cat bg-{{ cat_colors.get(e.category or '', 'secondary') }} bg-opacity-75">{{ e.category or '–' }}</span>
          </td>
          <td class="pe-3 text-end">
            <a href="/email/{{ e.id }}" class="btn btn-sm btn-outline-primary py-0 px-2 me-1" title="Bearbeiten">
              <i class="bi bi-pencil"></i></a>
            <button type="button" class="btn btn-sm btn-outline-info py-0 px-2 me-1"
                    data-snooze-id="{{ e.id }}" data-snooze-subject="{{ e.subject or '' }}" title="Snooze">
              <i class="bi bi-moon"></i></button>
            <button type="button" class="btn btn-sm btn-outline-danger py-0 px-2"
                    data-reject-id="{{ e.id }}" data-reject-subject="{{ e.subject or '' }}" title="Ablehnen">
              <i class="bi bi-x-lg"></i></button>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
fetch('/api/weekly_stats').then(r=>r.json()).then(data=>{
  const labels = data.map(d=>d.date ? d.date.slice(5) : '');
  const ctx = document.getElementById('weekChart');
  if (!ctx) return;
  new Chart(ctx.getContext('2d'),{
    type:'bar',
    data:{labels, datasets:[
      {label:'Auto gesendet', data:data.map(d=>d.auto_sent||0), backgroundColor:'#198754cc'},
      {label:'Zur Prüfung',   data:data.map(d=>d.pending_review||0), backgroundColor:'#ffc107cc'},
      {label:'Gefiltert',     data:data.map(d=>d.filtered||0), backgroundColor:'#adb5bd99'},
    ]},
    options:{responsive:true, plugins:{legend:{position:'bottom'}},
             scales:{x:{stacked:true},y:{stacked:true,beginAtZero:true,ticks:{stepSize:1}}}}
  });
});

fetch('/api/health').then(r=>r.json()).then(h=>{
  const box = document.getElementById('healthBox');
  if (!box) return;
  const items = [
    {key:'imap',     label:'IMAP-Server'},
    {key:'smtp',     label:'SMTP-Server'},
    {key:'claude',   label:'Claude-API'},
    {key:'telegram', label:'Telegram-Bot'},
  ];
  box.innerHTML = items.map(it => {
    const s = h[it.key] || {};
    const cls = s.ok ? 'health-ok' : (s.ok===false ? 'health-fail' : 'health-unknown');
    const txt = s.ok ? 'OK' : (s.detail || 'n/a');
    return `<div class="text-muted-sm mb-1"><span class="health-dot ${cls}"></span>${it.label}: <b>${txt}</b></div>`;
  }).join('');
  if (h.last_check) {
    box.innerHTML += `<div class="text-muted-sm mt-2 small">Letzte Prüfung: ${h.last_check}</div>`;
  }
});
</script>
{% endblock %}""")


# ── Pending Liste mit Bulk-Aktionen + Filter ─────────────────────────────────

PENDING_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="d-flex justify-content-between align-items-end mb-3">
  <div>
    <div class="page-header mb-1">Zur Prüfung</div>
    <div class="text-muted-sm">{{ pending|length }} E-Mail(s) — Konto: {{ filter_account or 'alle' }}</div>
  </div>
</div>

<!-- Filter-Pills -->
<div class="filter-pills mb-3 d-flex flex-wrap gap-2">
  <a href="?account=" class="btn btn-sm btn-outline-secondary {% if not filter_account %}active{% endif %}">Alle Konten</a>
  {% for acc in accounts %}
    <a href="?account={{ acc }}" class="btn btn-sm btn-outline-secondary {% if filter_account == acc %}active{% endif %}">{{ acc }}</a>
  {% endfor %}
</div>

{% if not pending %}
<div class="card border-0 shadow-sm" style="border-radius:14px;">
  <div class="card-body empty-state">
    <i class="bi bi-check2-circle text-success"></i>
    <div class="fw-semibold">Alles erledigt!</div>
    <div class="text-muted-sm mt-1">Keine E-Mails zur Prüfung.</div>
    <a href="/" class="btn btn-sm btn-outline-primary mt-3">Zum Dashboard</a>
  </div>
</div>
{% else %}

<!-- Bulk-Aktionen -->
<form method="post" action="/bulk" id="bulkForm">
  <div class="card border-0 shadow-sm mb-3" style="border-radius:14px; background:#eef2ff;">
    <div class="card-body py-2 px-4 d-flex align-items-center gap-3 flex-wrap">
      <input type="checkbox" class="form-check-input" id="checkAll">
      <label for="checkAll" class="text-muted-sm mb-0 me-2">Alle wählen</label>
      <span class="text-muted-sm">| Mit Auswahl:</span>
      <button type="submit" name="action" value="approve" formnovalidate
              class="btn btn-sm btn-success" onclick="return confirm('Alle ausgewählten genehmigen und senden?')">
        <i class="bi bi-check-lg me-1"></i>Genehmigen
      </button>
      <button type="submit" name="action" value="reject"
              class="btn btn-sm btn-danger" onclick="return confirm('Alle ausgewählten ablehnen?')">
        <i class="bi bi-x-lg me-1"></i>Ablehnen
      </button>
      <button type="submit" name="action" value="filtered"
              class="btn btn-sm btn-secondary" onclick="return confirm('Als Werbung markieren?')">
        <i class="bi bi-funnel me-1"></i>Als Werbung
      </button>
      <span class="ms-auto text-muted-sm" id="selCount">0 ausgewählt</span>
    </div>
  </div>

  {% for e in pending %}
  <div class="card border-0 shadow-sm mb-3 email-card" data-email-id="{{ e.id }}" style="border-radius:14px;">
    <div class="card-body p-4">
      <div class="d-flex justify-content-between align-items-start mb-3">
        <div class="d-flex gap-3">
          <input type="checkbox" name="ids" value="{{ e.id }}" class="form-check-input bulk-cb mt-1">
          <div>
            <div class="fw-bold fs-6 mb-1">{{ e.subject or '(kein Betreff)' }}</div>
            <div class="text-muted-sm">
              <i class="bi bi-person me-1"></i>{{ e.from_address }}
              &nbsp;·&nbsp; <i class="bi bi-clock me-1"></i>{{ (e.received_at or '')[:16] }}
              &nbsp;·&nbsp; ID: {{ e.id }}
            </div>
          </div>
        </div>
        <div class="d-flex gap-2 flex-shrink-0">
          {% set cat_colors = {'ANFRAGE':'primary','BESCHWERDE':'danger','BESTELLUNG':'success','SUPPORT':'info','ALLGEMEIN':'secondary'} %}
          <span class="badge bg-{{ cat_colors.get(e.category or '', 'secondary') }}">{{ e.category or '–' }}</span>
          <span class="badge bg-light text-dark border">{{ ((e.confidence or 0)*100)|int }}%</span>
        </div>
      </div>

      {% if e.notes %}
      <div class="alert alert-light py-2 px-3 mb-3 text-muted-sm">
        <i class="bi bi-info-circle me-1"></i>{{ e.notes }}
      </div>
      {% endif %}
    </div>
  </div>
  {% endfor %}
</form>

<!-- Einzelaktion-Karten (außerhalb der Bulk-Form) -->
{% for e in pending %}
<div class="card border-0 shadow-sm mb-3" style="border-radius:14px; margin-top:-1.05rem;">
  <div class="card-body p-4 pt-0">
    <form method="post" action="/approve/{{ e.id }}" class="approve-form">
      <textarea name="edited_draft" class="form-control mb-3"
                style="font-size:.88rem; font-family:inherit; min-height:160px; border-left:4px solid #0d6efd; border-radius:0 8px 8px 0; background:#f8f9fa; resize:vertical;"
                >{{ e.draft_reply or '' }}</textarea>
      <div class="d-flex gap-2 flex-wrap">
        <button type="submit" name="send_now" value="0" class="btn btn-success btn-sm px-3">
          <i class="bi bi-clock-history me-1"></i>Genehmigen (verzögert 1-3h)
        </button>
        <a href="/email/{{ e.id }}" class="btn btn-outline-primary btn-sm px-3">
          <i class="bi bi-eye me-1"></i>Vorschau / Detail
        </a>
        <a href="/reprocess/{{ e.id }}" class="btn btn-outline-warning btn-sm px-3"
           onclick="return confirm('E-Mail erneut von Claude verarbeiten lassen?')">
          <i class="bi bi-arrow-clockwise me-1"></i>Neu verarbeiten
        </a>
        <button type="button" class="btn btn-outline-info btn-sm px-3"
                data-snooze-id="{{ e.id }}" data-snooze-subject="{{ e.subject or '' }}">
          <i class="bi bi-moon me-1"></i>Snooze
        </button>
        <button type="button" class="btn btn-outline-danger btn-sm px-3"
                data-reject-id="{{ e.id }}" data-reject-subject="{{ e.subject or '' }}">
          <i class="bi bi-x-lg me-1"></i>Ablehnen
        </button>
      </div>
    </form>
  </div>
</div>
{% endfor %}

<div class="text-muted-sm mt-3 text-center">
  <kbd>↑</kbd> <kbd>↓</kbd> Karte wählen &nbsp;&nbsp;
  <kbd>A</kbd> Genehmigen &nbsp;&nbsp; <kbd>R</kbd> Ablehnen &nbsp;&nbsp; <kbd>S</kbd> Snooze
</div>
{% endif %}

<script>
// Bulk-Checkbox-Handling
(function(){
  const all = document.getElementById('checkAll');
  if (!all) return;
  const cbs = document.querySelectorAll('.bulk-cb');
  const counter = document.getElementById('selCount');
  function update(){
    const n = [...cbs].filter(c=>c.checked).length;
    if (counter) counter.textContent = n + ' ausgewählt';
  }
  all.addEventListener('change', () => {
    cbs.forEach(c => c.checked = all.checked);
    update();
  });
  cbs.forEach(c => c.addEventListener('change', update));
})();

// Keyboard-Shortcuts
(function(){
  const cards = document.querySelectorAll('.email-card');
  if (!cards.length) return;
  let idx = 0;
  function highlight(i){
    cards.forEach((c,j)=>c.style.outline = j===i ? '2px solid #0d6efd' : '');
    if(cards[i]) cards[i].scrollIntoView({behavior:'smooth',block:'center'});
  }
  highlight(0);
  document.addEventListener('keydown', e => {
    const t = document.activeElement.tagName;
    if(t==='TEXTAREA'||t==='INPUT'||t==='SELECT') return;
    if(e.key==='ArrowDown'||e.key==='ArrowRight'){ idx=Math.min(idx+1,cards.length-1); highlight(idx); e.preventDefault(); }
    else if(e.key==='ArrowUp'||e.key==='ArrowLeft'){ idx=Math.max(idx-1,0); highlight(idx); e.preventDefault(); }
  });
})();
</script>
{% endblock %}""")


# ── E-Mail Detail ─────────────────────────────────────────────────────────────

EMAIL_DETAIL_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="d-flex align-items-center gap-3 mb-4">
  <a href="javascript:history.back()" class="btn btn-sm btn-light"><i class="bi bi-arrow-left"></i></a>
  <div>
    <div class="page-header mb-0">{{ email.subject or '(kein Betreff)' }}</div>
    <div class="text-muted-sm">ID {{ email.id }}  ·  {{ (email.received_at or '')[:16] }}</div>
  </div>
</div>

<div class="row g-3">
  <div class="col-lg-6">
    <div class="card border-0 shadow-sm mb-3" style="border-radius:14px;">
      <div class="card-body">
        <table class="table table-sm table-borderless mb-0" style="font-size:.87rem;">
          <tr><td class="text-muted fw-semibold" style="width:100px;">Von</td><td>{{ email.from_address }}</td></tr>
          <tr><td class="text-muted fw-semibold">Konto</td><td>{{ email.account_email or '–' }}</td></tr>
          <tr><td class="text-muted fw-semibold">Status</td>
              <td>
                {% set s_colors = {'sent':'success','pending_review':'warning','pending':'secondary','manual':'info','filtered':'secondary','rejected':'danger','snoozed':'info','error':'danger'} %}
                <span class="badge bg-{{ s_colors.get(email.status, 'secondary') }}">{{ email.status }}</span>
              </td></tr>
          <tr><td class="text-muted fw-semibold">Kategorie</td><td>{{ email.category or '–' }}</td></tr>
          <tr><td class="text-muted fw-semibold">Konfidenz</td>
              <td>{% if email.confidence is not none %}
                <div class="d-flex align-items-center gap-2">
                  <div class="conf-bar flex-grow-1"><div class="conf-fill bg-{{ 'success' if email.confidence >= 0.75 else 'warning' }}" style="width:{{ (email.confidence*100)|int }}%"></div></div>
                  {{ (email.confidence*100)|int }}%
                </div>{% else %}–{% endif %}</td></tr>
          {% if email.notes %}
          <tr><td class="text-muted fw-semibold">Notizen</td><td class="text-muted">{{ email.notes }}</td></tr>
          {% endif %}
          {% if email.snooze_until %}
          <tr><td class="text-muted fw-semibold">Erinnerung</td><td>{{ email.snooze_until[:16] }}</td></tr>
          {% endif %}
        </table>
      </div>
    </div>

    <div class="card border-0 shadow-sm" style="border-radius:14px;">
      <div class="card-header bg-white border-0 pb-0 pt-3 px-4">
        <span class="fw-semibold text-muted-sm">ORIGINAL E-MAIL</span>
      </div>
      <div class="card-body pt-2 px-4 pb-4">
        <div class="body-box">{{ email.body or '(kein Inhalt)' }}</div>
      </div>
    </div>
  </div>

  <div class="col-lg-6">
    {% if email.status == 'pending_review' %}
    <div class="card border-0 shadow-sm mb-3" style="border-radius:14px; border-left: 4px solid #0d6efd !important;">
      <div class="card-header bg-white border-0 pb-0 pt-3 px-4">
        <span class="fw-semibold text-muted-sm">CLAUDE-ENTWURF</span>
      </div>
      <div class="card-body pt-2 px-4 pb-4">
        <div class="text-muted-sm mb-2"><i class="bi bi-pencil me-1"></i>Text direkt bearbeitbar</div>
        <form method="post" action="/approve/{{ email.id }}" id="approveForm">
          <textarea name="edited_draft" id="draftEdit" class="form-control mb-3"
                    style="font-size:.88rem; font-family:inherit; min-height:220px; border-left:4px solid #0d6efd; border-radius:0 8px 8px 0; background:#f8f9fa; resize:vertical;"
                    >{{ email.draft_reply or '' }}</textarea>
          <div class="d-flex gap-2 align-items-center">
            <button type="button" class="btn btn-outline-secondary" data-bs-toggle="modal" data-bs-target="#previewModal">
              <i class="bi bi-eye me-2"></i>Vorschau
            </button>
            <button type="submit" name="send_now" value="0" class="btn btn-success px-4">
              <i class="bi bi-clock-history me-2"></i>Genehmigen (verzögert 1-3h)
            </button>
            <button type="submit" name="send_now" value="1" class="btn btn-warning px-4"
                    onclick="return confirm('Sofort senden ohne Verzögerung? Nur in Notfällen empfohlen.')">
              <i class="bi bi-send-fill me-2"></i>Sofort senden
            </button>
          </div>
        </form>

        <!-- Vorschau-Modal -->
        <div class="modal fade" id="previewModal" tabindex="-1" aria-hidden="true">
          <div class="modal-dialog modal-lg modal-dialog-scrollable">
            <div class="modal-content">
              <div class="modal-header">
                <h5 class="modal-title"><i class="bi bi-eye me-2"></i>Vorschau – So sieht der Empfänger die Mail</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
              </div>
              <div class="modal-body p-0" style="background:#f5f6f8;">
                <div style="padding:14px 20px; background:#fff; border-bottom:1px solid #e9ecef; font-size:.85rem; color:#666;">
                  <div><strong>An:</strong> {{ email.from_address }}</div>
                  <div><strong>Von:</strong> {{ email.account_email or '' }}</div>
                  <div><strong>Betreff:</strong> <span id="previewSubject" style="color:#1a2035;font-weight:600;"></span></div>
                </div>
                <iframe id="previewFrame" style="width:100%; min-height:520px; border:0; background:#f5f6f8;"></iframe>
              </div>
              <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Weiter bearbeiten</button>
                <button type="button" class="btn btn-success"
                        onclick="document.querySelector('#approveForm button[name=send_now][value=\"0\"]').click();">
                  <i class="bi bi-clock-history me-2"></i>Genehmigen (verzögert)
                </button>
              </div>
            </div>
          </div>
        </div>

        <script>
        document.getElementById('previewModal').addEventListener('show.bs.modal', function() {
            const draft = document.getElementById('draftEdit').value;
            let subject = '', body = draft;
            if (draft.startsWith('BETREFF:')) {
                const idx = draft.indexOf('\\n\\n');
                if (idx > 0) {
                    subject = draft.substring(0, idx).replace('BETREFF:', '').trim();
                    body    = draft.substring(idx + 2).trim();
                } else {
                    subject = draft.replace('BETREFF:', '').trim();
                    body    = '';
                }
            } else {
                subject = "Re: {{ (email.subject or '')|e }}";
            }
            document.getElementById('previewSubject').textContent = subject || '(kein Betreff)';

            // HTML-Vorschau via Backend rendern (zeigt exakt was versendet wird)
            fetch('/preview_html', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email_id: {{ email.id }}, body: body})
            }).then(r => r.text()).then(html => {
                const iframe = document.getElementById('previewFrame');
                iframe.srcdoc = html;
            });
        });
        </script>
        <div class="mt-3 pt-3 border-top d-flex flex-wrap gap-2">
          <a href="/reprocess/{{ email.id }}" class="btn btn-outline-warning btn-sm"
             onclick="return confirm('Erneut von Claude verarbeiten?')">
            <i class="bi bi-arrow-clockwise me-1"></i>Neu verarbeiten
          </a>
          <button type="button" class="btn btn-outline-info btn-sm"
                  data-snooze-id="{{ email.id }}" data-snooze-subject="{{ email.subject or '' }}">
            <i class="bi bi-moon me-1"></i>Snooze
          </button>
          <button type="button" class="btn btn-outline-danger btn-sm"
                  data-reject-id="{{ email.id }}" data-reject-subject="{{ email.subject or '' }}">
            <i class="bi bi-x-lg me-1"></i>Ablehnen
          </button>
        </div>
      </div>
    </div>
    {% elif email.status == 'sent' %}
    <div class="card border-0 shadow-sm mb-3" style="border-radius:14px;">
      <div class="card-header bg-white border-0 pb-0 pt-3 px-4">
        <span class="fw-semibold text-muted-sm text-success"><i class="bi bi-check-circle me-1"></i>GESENDETE ANTWORT</span>
      </div>
      <div class="card-body pt-2 px-4 pb-4">
        <div class="body-box">{{ email.sent_reply or email.draft_reply or '–' }}</div>
      </div>
    </div>
    {% elif email.status == 'manual' %}
    <div class="alert alert-info" style="border-radius:14px;">
      <i class="bi bi-person-lines-fill me-2"></i>Manuelle Bearbeitung.<br>
      <span class="text-muted-sm">{{ email.notes or '' }}</span>
    </div>
    <a href="/reprocess/{{ email.id }}" class="btn btn-outline-warning btn-sm"
       onclick="return confirm('Erneut von Claude verarbeiten?')">
      <i class="bi bi-arrow-clockwise me-1"></i>Erneut von Claude verarbeiten
    </a>
    {% elif email.status == 'rejected' %}
    <div class="alert alert-danger" style="border-radius:14px;">
      <i class="bi bi-x-octagon me-2"></i>Abgelehnt.<br>
      <span class="text-muted-sm">{{ email.notes or '' }}</span>
    </div>
    {% if email.draft_reply %}
    <div class="card border-0 shadow-sm mt-3" style="border-radius:14px;">
      <div class="card-header bg-white border-0 pb-0 pt-3 px-4">
        <span class="fw-semibold text-muted-sm">ABGELEHNTER ENTWURF</span>
      </div>
      <div class="card-body pt-2 px-4 pb-4">
        <div class="body-box" style="opacity:.65;">{{ email.draft_reply }}</div>
      </div>
    </div>
    {% endif %}
    <a href="/reprocess/{{ email.id }}" class="btn btn-outline-warning btn-sm mt-3"
       onclick="return confirm('Erneut von Claude verarbeiten?')">
      <i class="bi bi-arrow-clockwise me-1"></i>Erneut versuchen
    </a>
    {% elif email.status == 'snoozed' %}
    <div class="alert alert-info" style="border-radius:14px;">
      <i class="bi bi-moon me-2"></i>Erinnerung um {{ (email.snooze_until or '')[:16] }}
    </div>
    <a href="/unsnooze/{{ email.id }}" class="btn btn-outline-secondary btn-sm">
      <i class="bi bi-bell me-1"></i>Jetzt aufwecken
    </a>
    {% elif email.status == 'filtered' %}
    <div class="alert alert-secondary" style="border-radius:14px;">
      <i class="bi bi-funnel me-2"></i>Als Newsletter/Werbung gefiltert.
    </div>
    {% endif %}
  </div>
</div>
{% endblock %}""")


# ── Generische Liste mit Filter-Pills ────────────────────────────────────────

LIST_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="page-header mb-1">{{ title }}</div>
<div class="text-muted-sm mb-3">{{ subtitle }} — {{ emails|length }} Einträge</div>

<!-- Such- und Filter-Form -->
<form method="get" class="row g-2 mb-3 align-items-end">
  <div class="col-md-4">
    <label class="text-muted-sm mb-1">Suche</label>
    <input type="text" name="q" value="{{ filter_search or '' }}" class="form-control form-control-sm"
           placeholder="Betreff, Absender oder Inhalt …">
  </div>
  <div class="col-md-3">
    <label class="text-muted-sm mb-1">Kategorie</label>
    <select name="category" class="form-select form-select-sm">
      <option value="">Alle</option>
      {% for c in ['ANFRAGE','BESCHWERDE','BESTELLUNG','SUPPORT','ALLGEMEIN','PORTAL','WERBUNG'] %}
        <option value="{{ c }}" {% if filter_category == c %}selected{% endif %}>{{ c }}</option>
      {% endfor %}
    </select>
  </div>
  {% if accounts %}
  <div class="col-md-3">
    <label class="text-muted-sm mb-1">Konto</label>
    <select name="account" class="form-select form-select-sm">
      <option value="">Alle</option>
      {% for acc in accounts %}
        <option value="{{ acc }}" {% if filter_account == acc %}selected{% endif %}>{{ acc }}</option>
      {% endfor %}
    </select>
  </div>
  {% endif %}
  <div class="col-md-2">
    <label class="text-muted-sm mb-1">Zeitraum</label>
    <select name="period" class="form-select form-select-sm">
      <option value="" {% if not filter_period %}selected{% endif %}>Alle</option>
      <option value="today" {% if filter_period == 'today' %}selected{% endif %}>Heute</option>
      <option value="week" {% if filter_period == 'week' %}selected{% endif %}>7 Tage</option>
      <option value="month" {% if filter_period == 'month' %}selected{% endif %}>30 Tage</option>
    </select>
  </div>
  <div class="col-12 d-flex gap-2 mt-2">
    <button type="submit" class="btn btn-sm btn-primary"><i class="bi bi-funnel"></i> Filtern</button>
    <a href="?" class="btn btn-sm btn-outline-secondary">Zurücksetzen</a>
  </div>
</form>

{% if not emails %}
<div class="card border-0 shadow-sm" style="border-radius:14px;">
  <div class="card-body empty-state">
    <i class="bi bi-{{ icon }} text-muted"></i>
    <div class="fw-semibold">{{ empty_text }}</div>
  </div>
</div>
{% else %}
<div class="card border-0 shadow-sm" style="border-radius:14px;">
  <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <thead class="table-light" style="font-size:.82rem;">
        <tr>
          <th class="ps-4" style="width:50px;">#</th>
          <th>Betreff</th>
          <th>Von</th>
          <th style="width:140px;">Datum</th>
          {% if show_notes %}<th>Grund/Notiz</th>{% endif %}
          {% if show_category %}<th style="width:110px;">Kategorie</th>{% endif %}
        </tr>
      </thead>
      <tbody>
        {% for e in emails %}
        <tr class="email-row" onclick="location.href='/email/{{ e.id }}'">
          <td class="ps-4 text-muted">{{ e.id }}</td>
          <td class="fw-semibold">{{ (e.subject or '–')[:55] }}</td>
          <td class="text-muted">{{ (e.from_address or '')[:35] }}</td>
          <td class="text-muted-sm">{{ (e.received_at or e.processed_at or '')[:16] }}</td>
          {% if show_notes %}<td class="text-muted-sm">{{ (e.notes or '')[:80] }}</td>{% endif %}
          {% if show_category %}
          <td>
            {% set cat_colors = {'ANFRAGE':'primary','BESCHWERDE':'danger','BESTELLUNG':'success','SUPPORT':'info','ALLGEMEIN':'secondary','PORTAL':'warning','WERBUNG':'light'} %}
            <span class="badge badge-cat bg-{{ cat_colors.get(e.category or '', 'secondary') }} bg-opacity-75">{{ e.category or '–' }}</span>
          </td>
          {% endif %}
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}
{% endblock %}""")


# ── Snoozed View ─────────────────────────────────────────────────────────────

SNOOZED_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="page-header mb-1">Snooze – Erinnerungen</div>
<div class="text-muted-sm mb-4">{{ emails|length }} E-Mail(s) warten auf Reaktivierung</div>

{% if not emails %}
<div class="card border-0 shadow-sm" style="border-radius:14px;">
  <div class="card-body empty-state">
    <i class="bi bi-moon text-muted"></i>
    <div class="fw-semibold">Keine geschnoozten E-Mails</div>
  </div>
</div>
{% else %}
<div class="card border-0 shadow-sm" style="border-radius:14px;">
  <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <thead class="table-light" style="font-size:.82rem;">
        <tr>
          <th class="ps-4">#</th><th>Betreff</th><th>Von</th>
          <th>Erinnerung</th><th></th>
        </tr>
      </thead>
      <tbody>
        {% for e in emails %}
        <tr>
          <td class="ps-4 text-muted">{{ e.id }}</td>
          <td class="fw-semibold"><a href="/email/{{ e.id }}" class="text-decoration-none">{{ (e.subject or '–')[:55] }}</a></td>
          <td class="text-muted">{{ (e.from_address or '')[:35] }}</td>
          <td class="text-muted-sm">
            <i class="bi bi-bell me-1"></i>{{ (e.snooze_until or '')[:16] }}
          </td>
          <td class="pe-3 text-end">
            <a href="/unsnooze/{{ e.id }}" class="btn btn-sm btn-outline-primary">
              <i class="bi bi-bell me-1"></i>Jetzt aufwecken
            </a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}
{% endblock %}""")


# ── Vorlagen-Seite ────────────────────────────────────────────────────────────

TEMPLATES_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
  <div>
    <div class="page-header">Antwort-Vorlagen</div>
    <div class="text-muted-sm">{{ templates|length }} Vorlage(n) — Claude nutzt sie automatisch</div>
  </div>
  <a href="/templates/new" class="btn btn-primary btn-sm">
    <i class="bi bi-plus-lg me-1"></i>Neue Vorlage
  </a>
</div>

{% if not templates %}
<div class="card border-0 shadow-sm" style="border-radius:14px;">
  <div class="card-body empty-state">
    <i class="bi bi-file-text text-muted"></i>
    <div class="fw-semibold">Noch keine Vorlagen</div>
    <div class="text-muted-sm mt-1">Lege Standardantworten an, die Claude bei passenden E-Mails verwendet.</div>
    <a href="/templates/new" class="btn btn-sm btn-outline-primary mt-3">Erste Vorlage anlegen</a>
  </div>
</div>
{% else %}
<div class="row g-3">
  {% for t in templates %}
  <div class="col-md-6">
    <div class="card border-0 shadow-sm h-100" style="border-radius:14px;">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-start mb-2">
          <div>
            <h6 class="mb-1 fw-bold">{{ t.name }}</h6>
            {% set cat_colors = {'ANFRAGE':'primary','BESCHWERDE':'danger','BESTELLUNG':'success','SUPPORT':'info','ALLGEMEIN':'secondary'} %}
            <span class="badge bg-{{ cat_colors.get(t.category, 'secondary') }} bg-opacity-75">{{ t.category }}</span>
            <span class="text-muted-sm ms-2">verwendet: {{ t.usage_count or 0 }}×</span>
          </div>
          <div>
            <a href="/templates/{{ t.id }}/edit" class="btn btn-sm btn-outline-primary py-0 px-2"><i class="bi bi-pencil"></i></a>
            <form method="post" action="/templates/{{ t.id }}/delete" style="display:inline" onsubmit="return confirm('Vorlage wirklich löschen?')">
              <button class="btn btn-sm btn-outline-danger py-0 px-2"><i class="bi bi-trash"></i></button>
            </form>
          </div>
        </div>
        <div class="text-muted-sm mb-2"><i class="bi bi-tags me-1"></i>{{ t.keywords or '–' }}</div>
        <div class="fw-semibold small mb-1">{{ t.subject_template }}</div>
        <div class="body-box" style="font-size:.82rem; max-height:120px;">{{ (t.body_template or '')[:300] }}</div>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}
{% endblock %}""")


TEMPLATE_FORM_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="d-flex align-items-center gap-3 mb-4">
  <a href="/templates" class="btn btn-sm btn-light"><i class="bi bi-arrow-left"></i></a>
  <div class="page-header mb-0">{{ 'Vorlage bearbeiten' if t else 'Neue Vorlage' }}</div>
</div>

<div class="card border-0 shadow-sm" style="border-radius:14px; max-width:780px;">
  <div class="card-body p-4">
    <form method="post">
      <div class="mb-3">
        <label class="form-label fw-semibold">Name</label>
        <input type="text" name="name" class="form-control" required
               value="{{ t.name if t else '' }}"
               placeholder="z.B. Versandbestätigung">
      </div>
      <div class="row g-3 mb-3">
        <div class="col-md-6">
          <label class="form-label fw-semibold">Kategorie</label>
          <select name="category" class="form-select">
            {% for c in ['ANFRAGE','BESCHWERDE','BESTELLUNG','SUPPORT','ALLGEMEIN'] %}
              <option value="{{ c }}" {% if t and t.category==c %}selected{% endif %}>{{ c }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-6">
          <label class="form-label fw-semibold">Schlüsselwörter (kommagetrennt)</label>
          <input type="text" name="keywords" class="form-control"
                 value="{{ kw_str }}"
                 placeholder="versand, lieferung, paket">
        </div>
      </div>
      <div class="mb-3">
        <label class="form-label fw-semibold">Betreff-Vorlage</label>
        <input type="text" name="subject_template" class="form-control" required
               value="{{ t.subject_template if t else '' }}"
               placeholder="Re: Ihre Bestellung">
      </div>
      <div class="mb-3">
        <label class="form-label fw-semibold">Antworttext (OHNE Signatur)</label>
        <textarea name="body_template" class="form-control" rows="10" required
                  style="font-family:inherit;">{{ t.body_template if t else '' }}</textarea>
        <div class="text-muted-sm mt-1">Die Signatur wird automatisch ergänzt.</div>
      </div>
      <div class="d-flex gap-2">
        <button type="submit" class="btn btn-success">
          <i class="bi bi-check-lg me-1"></i>Speichern
        </button>
        <a href="/templates" class="btn btn-outline-secondary">Abbrechen</a>
      </div>
    </form>
  </div>
</div>
{% endblock %}""")


# ── Aktivitäten-Log ───────────────────────────────────────────────────────────

LOG_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="page-header mb-1">Aktivitäten</div>
<div class="text-muted-sm mb-4">Letzte 100 Aktionen des Agenten</div>

<div class="card border-0 shadow-sm" style="border-radius:14px;">
  <div class="card-body p-0">
    {% if not log %}
    <div class="empty-state"><i class="bi bi-journal text-muted"></i><div>Noch keine Aktivitäten.</div></div>
    {% else %}
    <table class="table mb-0">
      <thead class="table-light" style="font-size:.82rem;">
        <tr><th class="ps-4" style="width:145px;">Zeitpunkt</th>
            <th style="width:120px;">Aktion</th>
            <th style="width:70px;">E-Mail</th>
            <th>Details</th></tr>
      </thead>
      <tbody>
        {% for row in log %}
        <tr class="log-row">
          <td class="ps-4 text-muted">{{ (row.timestamp or '')[:16] }}</td>
          <td>
            {% set a_colors = {'sent':'success','approved':'success','flagged':'warning','manual':'info','rejected':'danger','send_error':'danger','filtered':'secondary','portal':'warning','reprocess':'primary','snooze':'info','unsnooze':'info'} %}
            <span class="badge bg-{{ a_colors.get(row.action, 'secondary') }} bg-opacity-75 badge-cat">{{ row.action }}</span>
          </td>
          <td class="text-muted">
            {% if row.email_id %}<a href="/email/{{ row.email_id }}" class="text-decoration-none">{{ row.email_id }}</a>{% else %}–{% endif %}
          </td>
          <td class="text-muted">{{ (row.details or '')[:100] }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% endif %}
  </div>
</div>
{% endblock %}""")


# ── Suche ─────────────────────────────────────────────────────────────────────

SEARCH_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="page-header mb-1">Suchergebnisse</div>
<div class="text-muted-sm mb-4">
  {% if query %}{{ results|length }} Treffer für „<b>{{ query }}</b>"{% else %}Bitte Suchbegriff eingeben.{% endif %}
</div>

{% if query %}
  {% if not results %}
  <div class="card border-0 shadow-sm" style="border-radius:14px;">
    <div class="card-body empty-state">
      <i class="bi bi-search text-muted"></i>
      <div class="fw-semibold">Keine Ergebnisse</div>
    </div>
  </div>
  {% else %}
  <div class="card border-0 shadow-sm" style="border-radius:14px;">
    <div class="card-body p-0">
      <table class="table table-hover mb-0">
        <thead class="table-light" style="font-size:.82rem;">
          <tr><th class="ps-4">#</th><th>Betreff</th><th>Von</th><th>Datum</th><th>Status</th><th>Konto</th></tr>
        </thead>
        <tbody>
        {% for e in results %}
        <tr class="email-row" onclick="location.href='/email/{{ e.id }}'">
          <td class="ps-4 text-muted">{{ e.id }}</td>
          <td class="fw-semibold">{{ (e.subject or '–')[:55] }}</td>
          <td class="text-muted">{{ (e.from_address or '')[:35] }}</td>
          <td class="text-muted-sm">{{ (e.received_at or '')[:10] }}</td>
          <td>
            {% set s_colors = {'sent':'success','pending_review':'warning','manual':'info','filtered':'secondary','rejected':'danger','snoozed':'info','error':'danger'} %}
            <span class="badge bg-{{ s_colors.get(e.status,'secondary') }} bg-opacity-75" style="font-size:.75rem;">{{ e.status }}</span>
          </td>
          <td class="text-muted-sm">{{ (e.account_email or '')[:25] }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% endif %}
{% endif %}
{% endblock %}""")


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


def _all_account_emails() -> list[str]:
    cfg = load_config()
    accs = cfg.get("accounts") or [cfg.get("email", {})]
    return [a["email"] for a in accs if a.get("email")]


def _filter_emails(rows: list[dict], account: str = "", period: str = "",
                   category: str = "", search: str = "") -> list[dict]:
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


def _get_emails_by_status(status: str, limit: int = 500) -> list[dict]:
    conn = db.get_conn()
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


def _get_activity_log(limit: int = 100) -> list[dict]:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT timestamp, action, email_id, details "
            "FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Routen: Dashboard ─────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    cfg = load_config()
    accounts = cfg.get("accounts") or [cfg.get("email", {})]
    accounts_str = "  ·  ".join(a["email"] for a in accounts)
    pending = db.get_pending_review_emails()
    return render_template_string(
        DASHBOARD_TMPL,
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
    if filter_account:
        pending = [p for p in pending if (p.get("account_email") or "") == filter_account]
    # account_email nachladen für Filter (get_pending_review_emails liefert es nicht)
    conn = db.get_conn()
    try:
        for p in pending:
            row = conn.execute("SELECT account_email FROM emails WHERE id=?", (p["id"],)).fetchone()
            if row: p["account_email"] = row["account_email"]
    finally:
        conn.close()
    if filter_account:
        pending = [p for p in pending if (p.get("account_email") or "") == filter_account]

    return render_template_string(
        PENDING_TMPL,
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

    # Signatur des passenden Kontos für Vorschau ermitteln
    cfg = load_config()
    accs = cfg.get("accounts") or []
    sig = ""
    for a in accs:
        if a.get("email") == email.get("account_email"):
            sig = a.get("signature", "")
            break
    if not sig and accs:
        sig = accs[0].get("signature", "")

    return render_template_string(
        EMAIL_DETAIL_TMPL,
        active="",
        pending_count=_pending_count(),
        email=email,
        signature_json=json.dumps(sig),
    )


# ── Test-Mail (einmalig, geschützt durch Login) ──────────────────────────────

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
        "das ist eine Testmail vom Levando E-Mail Agent — frisch deployed auf dem Hostinger-Server.\n\n"
        "Was du in dieser Mail siehst:\n"
        "- Modernes HTML-Layout mit Levando-Branding\n"
        "- Farbiger Header-Streifen oben\n"
        "- Klickbare Links: info@levando.gmbh, https://www.levando.gmbh\n"
        "- Saubere Trennung zwischen Grußformel und Firmen-Footer\n"
        "- Mobile-responsive Design\n\n"
        "Falls dein Mailclient HTML nicht unterstützt, siehst du automatisch eine Plaintext-Version.\n\n"
        "Der Bot ist bereit für den produktiven Betrieb."
    )
    ts = datetime.now().strftime("%H:%M")
    try:
        ec.send_reply(to_addr, f"Testmail Levando v3 – Mobile responsive ({ts})", body)
        return f"Testmail gesendet an {to_addr}", 200
    except Exception as e:
        return f"Fehler: {e}", 500


# ── Vorschau-API: rendert exakt das HTML das versendet wird ──────────────────

@app.route("/preview_html", methods=["POST"])
def preview_html():
    data    = request.get_json(silent=True) or {}
    email_id = data.get("email_id")
    body    = data.get("body", "")

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

    # Genau dieselbe Funktion nutzen wie beim Versand
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
        flash(f"✓ {success} genehmigt und gesendet" + (f", {fail} Fehler" if fail else "") + ".", "success")
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
    return render_template_string(
        SNOOZED_TMPL,
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
    return render_template_string(
        LIST_TMPL,
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
    # keywords-JSON in lesbaren String umwandeln
    for t in tpls:
        try:
            kws = json.loads(t.get("keywords") or "[]")
            t["keywords"] = ", ".join(kws) if isinstance(kws, list) else (t.get("keywords") or "")
        except Exception:
            pass
    return render_template_string(
        TEMPLATES_TMPL,
        active="templates",
        pending_count=_pending_count(),
        templates=tpls,
    )


@app.route("/templates/new", methods=["GET", "POST"])
def template_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "ALLGEMEIN")
        keywords = [k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()]
        subject = request.form.get("subject_template", "").strip()
        body = request.form.get("body_template", "").strip()
        if name and subject and body:
            db.save_template(name, category, keywords, subject, body)
            flash(f"✓ Vorlage '{name}' angelegt.", "success")
            return redirect(url_for("templates_list"))
        flash("Bitte alle Pflichtfelder ausfüllen.", "warning")
    return render_template_string(
        TEMPLATE_FORM_TMPL,
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
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "ALLGEMEIN")
        keywords = [k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()]
        subject = request.form.get("subject_template", "").strip()
        body = request.form.get("body_template", "").strip()
        db.update_template(template_id, name, category, keywords, subject, body)
        flash(f"✓ Vorlage '{name}' gespeichert.", "success")
        return redirect(url_for("templates_list"))
    try:
        kws = json.loads(t.get("keywords") or "[]")
        kw_str = ", ".join(kws) if isinstance(kws, list) else (t.get("keywords") or "")
    except Exception:
        kw_str = t.get("keywords") or ""
    return render_template_string(
        TEMPLATE_FORM_TMPL,
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

AUFGABEN_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="page-header mb-1">Aufgaben & Versprechen</div>
<div class="text-muted-sm mb-4">{{ groups.overdue|length + groups.today|length + groups.future|length }} offen — was du per E-Mail zugesagt hast</div>

{% if groups.overdue %}
<div class="card border-0 shadow-sm mb-3" style="border-radius:14px;border-left:4px solid #dc3545;">
  <div class="card-body">
    <h5 class="text-danger fw-bold mb-3"><i class="bi bi-exclamation-triangle"></i> Überfällig ({{ groups.overdue|length }})</h5>
    {% for c in groups.overdue %}
    <div class="border-bottom py-3">
      <div class="d-flex justify-content-between align-items-start">
        <div class="flex-grow-1">
          <div class="text-muted-sm mb-1"><strong class="text-danger">{{ c.due_str }}</strong> — an <a href="/email/{{ c.email_id }}" class="text-decoration-none">{{ c.sender }}</a></div>
          <div class="fw-semibold mb-1">{{ c.subject }}</div>
          <div style="color:#444;">"{{ c.promise }}"</div>
        </div>
        <form method="post" action="/aufgaben/{{ c.id }}/done" class="ms-3">
          <button class="btn btn-sm btn-outline-success">Erledigt</button>
        </form>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}

{% if groups.today %}
<div class="card border-0 shadow-sm mb-3" style="border-radius:14px;border-left:4px solid #ffc107;">
  <div class="card-body">
    <h5 class="text-warning fw-bold mb-3"><i class="bi bi-clock"></i> Heute fällig ({{ groups.today|length }})</h5>
    {% for c in groups.today %}
    <div class="border-bottom py-3">
      <div class="d-flex justify-content-between align-items-start">
        <div class="flex-grow-1">
          <div class="text-muted-sm mb-1"><strong>{{ c.due_str }}</strong> — an <a href="/email/{{ c.email_id }}" class="text-decoration-none">{{ c.sender }}</a></div>
          <div class="fw-semibold mb-1">{{ c.subject }}</div>
          <div style="color:#444;">"{{ c.promise }}"</div>
        </div>
        <form method="post" action="/aufgaben/{{ c.id }}/done" class="ms-3">
          <button class="btn btn-sm btn-outline-success">Erledigt</button>
        </form>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}

{% if groups.future %}
<div class="card border-0 shadow-sm mb-3" style="border-radius:14px;border-left:4px solid #198754;">
  <div class="card-body">
    <h5 class="text-success fw-bold mb-3"><i class="bi bi-calendar"></i> Nächste Tage ({{ groups.future|length }})</h5>
    {% for c in groups.future %}
    <div class="border-bottom py-3">
      <div class="d-flex justify-content-between align-items-start">
        <div class="flex-grow-1">
          <div class="text-muted-sm mb-1"><strong>{{ c.due_str }}</strong> — an <a href="/email/{{ c.email_id }}" class="text-decoration-none">{{ c.sender }}</a></div>
          <div class="fw-semibold mb-1">{{ c.subject }}</div>
          <div style="color:#444;">"{{ c.promise }}"</div>
        </div>
        <form method="post" action="/aufgaben/{{ c.id }}/done" class="ms-3">
          <button class="btn btn-sm btn-outline-success">Erledigt</button>
        </form>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}

{% if not groups.overdue and not groups.today and not groups.future %}
<div class="card border-0 shadow-sm" style="border-radius:14px;">
  <div class="card-body empty-state">
    <i class="bi bi-bookmark-star text-muted"></i>
    <div class="fw-semibold">Keine offenen Versprechen</div>
    <div class="text-muted-sm">Alle Zusagen erledigt — gut gemacht!</div>
  </div>
</div>
{% endif %}
{% endblock %}""")


@app.route("/aufgaben")
def aufgaben_view():
    commits = db.get_open_commitments(200)
    now = datetime.now()
    today_end = now.replace(hour=23, minute=59, second=59)

    def fmt(c):
        d = datetime.fromisoformat(c["due_date"])
        c["due_dt"]   = d
        c["due_str"]  = d.strftime("%d.%m.%Y %H:%M")
        return c

    commits = [fmt(c) for c in commits]
    overdue = [c for c in commits if c["due_dt"] < now]
    today_  = [c for c in commits if now <= c["due_dt"] <= today_end]
    future  = [c for c in commits if c["due_dt"] > today_end]

    return render_template_string(
        AUFGABEN_TMPL,
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

SCHEDULED_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="page-header mb-1">Versand-Queue</div>
<div class="text-muted-sm mb-4">{{ emails|length }} E-Mail(s) warten — wegen 1-3h Verzögerung für menschliches Verhalten</div>

{% if not emails %}
<div class="card border-0 shadow-sm" style="border-radius:14px;">
  <div class="card-body empty-state">
    <i class="bi bi-clock-history text-muted"></i>
    <div class="fw-semibold">Keine geplanten Versendungen</div>
  </div>
</div>
{% else %}
<div class="card border-0 shadow-sm" style="border-radius:14px;">
  <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <thead class="table-light" style="font-size:.82rem;">
        <tr>
          <th class="ps-4" style="width:50px;">#</th>
          <th>Betreff</th>
          <th>An</th>
          <th style="width:140px;">Sendet um</th>
          <th style="width:140px;">In</th>
          <th style="width:120px;text-align:right;padding-right:1rem;">Aktion</th>
        </tr>
      </thead>
      <tbody>
        {% for e in emails %}
        <tr class="email-row">
          <td class="ps-4 text-muted">{{ e.id }}</td>
          <td class="fw-semibold" onclick="location.href='/email/{{ e.id }}'" style="cursor:pointer;">{{ (e.subject or '–')[:55] }}</td>
          <td class="text-muted">{{ (e.from_address or '')[:35] }}</td>
          <td class="text-muted-sm">{{ e.send_str }}</td>
          <td class="text-muted-sm"><span class="badge bg-info bg-opacity-25 text-dark">{{ e.in_str }}</span></td>
          <td class="text-end pe-3">
            <form method="post" action="/scheduled/{{ e.id }}/now" class="d-inline">
              <button class="btn btn-sm btn-outline-primary" title="Sofort senden"><i class="bi bi-send-fill"></i></button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}
{% endblock %}""")


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
    return render_template_string(
        SCHEDULED_TMPL,
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
    return render_template_string(
        LOG_TMPL,
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
    return render_template_string(
        SEARCH_TMPL,
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

    # IMAP & SMTP per TCP-Connect prüfen (schnell, kein Login)
    try:
        accs = cfg.get("accounts") or [cfg.get("email", {})]
        acc = accs[0] if accs else {}
        srv = acc.get("imap_server", "")
        port = int(acc.get("imap_port", 993))
        s = socket.create_connection((srv, port), timeout=4); s.close()
        health["imap"] = {"ok": True, "detail": f"{srv}:{port}"}
    except Exception as e:
        health["imap"] = {"ok": False, "detail": str(e)[:60]}
    try:
        srv = acc.get("smtp_server", "")
        port = int(acc.get("smtp_port", 465))
        s = socket.create_connection((srv, port), timeout=4); s.close()
        health["smtp"] = {"ok": True, "detail": f"{srv}:{port}"}
    except Exception as e:
        health["smtp"] = {"ok": False, "detail": str(e)[:60]}

    # Claude-API: einfacher API-Key-Format-Check
    api_key = cfg.get("claude", {}).get("api_key", "")
    health["claude"] = {"ok": api_key.startswith("sk-ant-"),
                        "detail": "Schlüssel gesetzt" if api_key.startswith("sk-ant-") else "kein gültiger Key"}

    # Telegram: getMe-Aufruf
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
        flash("✓ Telegram-Testnachricht gesendet." if ok else "Telegram nicht erreichbar.", "success" if ok else "warning")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/todo/generate")
def todo_generate():
    """Erzeugt ToDo-PDF und versendet es per Mail + Telegram."""
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


# ── Start ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db.init_db()
    print("\n" + "=" * 52)
    print("  E-Mail Agent – Web-UI")
    print("=" * 52)
    print("  Browser:  http://localhost:5000")
    print("  Beenden:  STRG+C")
    print("=" * 52 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
