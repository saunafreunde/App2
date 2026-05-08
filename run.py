"""
E-Mail Agent – Einstiegspunkt.

Verwendung:
  python run.py                    E-Mails einmal verarbeiten
  python run.py daemon             Kontinuierlich laufen (Scheduler)
  python run.py report             Tages-Report anzeigen
  python run.py report --send      Report anzeigen und per E-Mail senden
  python run.py pending            Ausstehende Überprüfungen auflisten
  python run.py approve <id>       Entwurf genehmigen und senden
  python run.py reject  <id> [Gr.] Entwurf ablehnen
  python run.py stats              Statistiken anzeigen
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Windows-Terminal: UTF-8 erzwingen
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = Path(__file__).parent / "config.json"
TEMPLATE_PATH = Path(__file__).parent / "config_template.json"


def load_config() -> dict:
    try:
        from config_loader import load_config as _load
        return _load()
    except ImportError:
        pass
    if not CONFIG_PATH.exists():
        print("\nFEHLER: config.json nicht gefunden!")
        print(f"Bitte '{TEMPLATE_PATH.name}' als 'config.json' kopieren und ausfüllen.")
        print(f"\n  copy {TEMPLATE_PATH} {CONFIG_PATH}\n")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def check_config(cfg: dict):
    """Prüft ob Pflichtfelder ausgefüllt sind."""
    errors = []
    api_key = cfg.get("claude", {}).get("api_key", "")
    if not api_key.startswith("sk-ant-"):
        errors.append("claude.api_key ist noch nicht gesetzt (muss mit sk-ant- beginnen)")
    accounts = cfg.get("accounts") or [cfg.get("email", {})]
    for acc in accounts:
        if "IHR_PASSWORT" in acc.get("password", ""):
            errors.append(f"Passwort für {acc.get('email', '?')} ist noch nicht gesetzt")
        if "ihre-domain" in acc.get("email", ""):
            errors.append("E-Mail-Adresse ist noch nicht gesetzt")
    if errors:
        print("\nKONFIGURATION UNVOLLSTÄNDIG:")
        for e in errors:
            print(f"  ✗ {e}")
        print(f"\nBitte config.json bearbeiten: {CONFIG_PATH}\n")
        sys.exit(1)


def main():
    import database as db
    import agent

    cfg = load_config()
    check_config(cfg)
    db.init_db()
    agent.setup(cfg)

    args = sys.argv[1:]
    cmd  = args[0] if args else "run"

    # ── Einmaliger Lauf ────────────────────────────────────────────────────────
    if cmd == "run":
        agent.process_all_emails()

    # ── Daemon-Modus ───────────────────────────────────────────────────────────
    elif cmd == "daemon":
        try:
            import schedule
            import time
        except ImportError:
            print("Fehlendes Paket: pip install schedule")
            sys.exit(1)

        interval    = cfg.get("agent", {}).get("check_interval_minutes", 15)
        report_time = cfg.get("agent", {}).get("report_time", "18:00")
        report_mail = cfg.get("agent", {}).get("report_email", "")

        def run_and_catch():
            try:
                agent.process_all_emails()
            except Exception as e:
                print(f"Fehler beim Verarbeiten: {e}")

        def send_report():
            report = agent.generate_daily_report()
            stats  = db.get_daily_stats()
            print(report)

            # ── E-Mail-Versand ────────────────────────────────────────────
            if report_mail:
                try:
                    from email_client import EmailClient
                    accounts = cfg.get("accounts") or [cfg.get("email", {})]
                    ec = EmailClient(accounts[0])
                    ec.send_reply(
                        report_mail,
                        f"E-Mail Report {datetime.now().strftime('%d.%m.%Y')}",
                        report,
                    )
                    print(f"Report per E-Mail gesendet an {report_mail}")
                except Exception as e:
                    print(f"Report E-Mail-Versand fehlgeschlagen: {e}")

            # ── Telegram-Versand ──────────────────────────────────────────
            try:
                import telegram_notify as tg
                ok = tg.send_report(report, stats)
                if ok:
                    print("Report per Telegram gesendet.")
            except Exception as e:
                print(f"Report Telegram-Versand fehlgeschlagen: {e}")

        # Tages-ToDo-Liste um 11:00 (oder aus config: agent.todo_time)
        todo_time = cfg.get("agent", {}).get("todo_time", "11:00")

        def send_todo_list():
            try:
                import todo_report as tr
                tr.send_todo_pdf()
                print(f"ToDo-Liste {datetime.now().strftime('%H:%M')} versendet.")
            except Exception as e:
                print(f"Fehler ToDo-Liste: {e}")

        # Verzögerter Versand: alle 5 Min fällige geplante Mails verschicken
        def send_scheduled():
            try:
                n = agent.send_due_emails()
                if n:
                    print(f"  → {n} verzögerte E-Mail(s) versendet")
            except Exception as e:
                print(f"Fehler beim verzögerten Versand: {e}")

        def auto_backup():
            try:
                bid = db.create_backup(label="Auto-Backup")
                print(f"  → Auto-Backup #{bid} erstellt")
            except Exception as e:
                print(f"Fehler Auto-Backup: {e}")

        schedule.every(interval).minutes.do(run_and_catch)
        schedule.every(5).minutes.do(send_scheduled)
        schedule.every().day.at(report_time).do(send_report)
        schedule.every().day.at(todo_time).do(send_todo_list)
        schedule.every().day.at("02:00").do(auto_backup)

        # Telegram-Bot-Thread starten
        try:
            import telegram_bot as tg_bot
            tg_bot.start_bot_thread()
            print("  Telegram-Bot:   aktiv (Direktantwort per /ok{id})")
        except Exception as e:
            print(f"  Telegram-Bot:   nicht gestartet ({e})")

        print(f"\nAgent läuft im Daemon-Modus")
        print(f"  E-Mails prüfen: alle {interval} Minuten")
        print(f"  Tages-Report:   {report_time} Uhr")
        print(f"  ToDo-Liste:     {todo_time} Uhr")
        print("  Beenden mit: STRG+C\n")

        run_and_catch()  # Sofort beim Start
        while True:
            schedule.run_pending()
            time.sleep(30)

    # ── Report ─────────────────────────────────────────────────────────────────
    elif cmd == "report":
        report = agent.generate_daily_report()
        stats  = db.get_daily_stats()
        print(report)
        if "--send" in args:
            report_mail = cfg.get("agent", {}).get("report_email", "")

            # E-Mail
            if report_mail:
                try:
                    from email_client import EmailClient
                    accounts = cfg.get("accounts") or [cfg.get("email", {})]
                    ec = EmailClient(accounts[0])
                    ec.send_reply(
                        report_mail,
                        f"E-Mail Report {datetime.now().strftime('%d.%m.%Y')}",
                        report,
                    )
                    print(f"Report per E-Mail gesendet an {report_mail}")
                except Exception as e:
                    print(f"E-Mail-Versand fehlgeschlagen: {e}")

            # Telegram
            try:
                import telegram_notify as tg
                ok = tg.send_report(report, stats)
                if ok:
                    print("Report per Telegram gesendet.")
            except Exception as e:
                print(f"Telegram-Versand fehlgeschlagen: {e}")

    # ── Pending anzeigen ───────────────────────────────────────────────────────
    elif cmd == "pending":
        pending = db.get_pending_review_emails()
        if not pending:
            print("\nKeine E-Mails zur Überprüfung. ✓\n")
            return
        print(f"\n{'='*52}")
        print(f"  Zur Überprüfung: {len(pending)} E-Mail(s)")
        print("=" * 52)
        for e in pending:
            conf  = e.get("confidence") or 0
            draft = (e.get("draft_reply") or "")[:200]
            print(f"\nID {e['id']}:  {e.get('subject', '')[:50]}")
            print(f"  Von:       {e.get('from_address', '')[:45]}")
            print(f"  Empfangen: {e.get('received_at', '')[:16]}")
            print(f"  Konfidenz: {conf:.0%}  |  Kategorie: {e.get('category') or '–'}")
            print(f"  Entwurf:\n{draft}")
            print(f"\n  ▶  python run.py approve {e['id']}")
            print(f"  ✗  python run.py reject  {e['id']}")
        print()

    # ── Genehmigen ─────────────────────────────────────────────────────────────
    elif cmd == "approve":
        if len(args) < 2:
            print("Verwendung: python run.py approve <id>")
            sys.exit(1)
        agent.approve_email(int(args[1]))

    # ── Ablehnen ───────────────────────────────────────────────────────────────
    elif cmd == "reject":
        if len(args) < 2:
            print("Verwendung: python run.py reject <id> [Grund]")
            sys.exit(1)
        reason = " ".join(args[2:]) if len(args) > 2 else ""
        agent.reject_email(int(args[1]), reason)

    # ── ToDo-Liste manuell erzeugen ────────────────────────────────────────────
    elif cmd == "todo":
        import todo_report as tr
        if "--send" in args:
            tr.send_todo_pdf()
        else:
            path, todos = tr.generate_todo_pdf()
            print(f"\n  PDF erstellt: {path}")
            print(f"  Aufgaben: {len(todos)}\n")

    # ── Statistiken ────────────────────────────────────────────────────────────
    elif cmd == "stats":
        stats = db.get_daily_stats()
        print(f"\nStatistiken für heute ({datetime.now().strftime('%d.%m.%Y')}):")
        print(f"  Gesamt:                {stats.get('total', 0)}")
        print(f"  Automatisch gesendet:  {stats.get('auto_sent', 0)}")
        print(f"  Wartet auf Prüfung:    {stats.get('pending_review', 0)}")
        print(f"  Manuell:               {stats.get('manual', 0)}")
        print(f"  Fehler:                {stats.get('errors', 0)}\n")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
