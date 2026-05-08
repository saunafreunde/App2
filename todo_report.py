"""
Tägliche ToDo-Liste als PDF.

Sammelt alle offenen Aufgaben aus pending_review, manual, snoozed-Mails
und lässt Claude konkrete Action-Items extrahieren ("Ersatz in Größe XX an
Kunden XY versenden"). Ergebnis als illustriertes PDF.

Verwendung:
  python todo_report.py        – PDF erzeugen + per Mail/Telegram senden
  python todo_report.py --show – nur erzeugen, Pfad ausgeben
"""

import sys
import json
from pathlib import Path
from datetime import datetime

import anthropic

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, white, black, grey
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak, KeepTogether)
from reportlab.platypus.flowables import HRFlowable

sys.path.insert(0, str(Path(__file__).parent))
import database as db

CONFIG_PATH = Path(__file__).parent / "config.json"
PDF_DIR = Path(__file__).parent / "reports"
PDF_DIR.mkdir(exist_ok=True)


def _load_cfg() -> dict:
    """Lädt Config: erst Umgebungsvariablen, dann config.json als Fallback."""
    try:
        from config_loader import load_config
        return load_config()
    except ImportError:
        pass
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Farben & Styles ──────────────────────────────────────────────────────────

PRIMARY = HexColor("#1a2035")
ACCENT  = HexColor("#0d6efd")
SUCCESS = HexColor("#198754")
WARNING = HexColor("#ffc107")
DANGER  = HexColor("#dc3545")
INFO    = HexColor("#0dcaf0")
LIGHT   = HexColor("#f8f9fa")
MUTED   = HexColor("#6c757d")


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="TitleBig", fontName="Helvetica-Bold",
                         fontSize=22, leading=26, textColor=PRIMARY,
                         spaceAfter=4))
    s.add(ParagraphStyle(name="SubTitle", fontName="Helvetica",
                         fontSize=11, leading=14, textColor=MUTED,
                         spaceAfter=14))
    s.add(ParagraphStyle(name="Section", fontName="Helvetica-Bold",
                         fontSize=13, leading=16, textColor=PRIMARY,
                         spaceBefore=14, spaceAfter=6))
    s.add(ParagraphStyle(name="TodoText", fontName="Helvetica",
                         fontSize=10, leading=14, textColor=black))
    s.add(ParagraphStyle(name="TodoMeta", fontName="Helvetica-Oblique",
                         fontSize=8.5, leading=11, textColor=MUTED))
    s.add(ParagraphStyle(name="Footer", fontName="Helvetica",
                         fontSize=8, leading=10, textColor=MUTED,
                         alignment=TA_CENTER))
    return s


# ── ToDo-Extraktion via Claude ────────────────────────────────────────────────

_PROMPT = """Du bist Assistent von Christoph Wolfert (Levando GmbH).

Aus folgenden offenen E-Mails sollst du KONKRETE Aufgaben für den heutigen Tag extrahieren.
Nur Aufgaben die Christoph PERSÖNLICH erledigen muss (nicht "Antwort schreiben"!).

Beispiele für gute Aufgaben:
  • Ersatzteil M14×1,5 SW17 an Kunde Müller versenden
  • Rückzahlung 89,90€ an Schmidt veranlassen
  • Lieferung mit Spedition klären (Bestellung 4711)
  • Reklamation Radmuttern: Ersatz oder Erstattung entscheiden
  • Steuerberater wegen USt-Voranmeldung kontaktieren

KEINE Aufgaben:
  • "E-Mail beantworten" (das macht der Agent)
  • "Newsletter lesen"
  • Allgemeine Werbung

Antworte als JSON-Array:
[
  {"prio": "hoch|mittel|niedrig",
   "kategorie": "Versand|Erstattung|Reklamation|Buchhaltung|Lieferung|Sonstiges",
   "aufgabe": "Konkreter Handlungsschritt",
   "kunde": "Name oder Mail-Adresse",
   "kontext": "Kurzer Hintergrund (max 80 Zeichen)",
   "email_id": 123,
   "frist": "heute|morgen|diese_woche|Datum"}
]

Wenn keine echten Aufgaben: leeres Array [].
KEINE Vorrede, NUR das JSON-Array.
"""


def _gather_open_emails() -> list[dict]:
    """Sammelt alle offenen E-Mails der letzten 14 Tage."""
    conn = db.get_conn()
    try:
        rows = conn.execute("""
            SELECT id, from_address, subject, body, received_at, status,
                   category, notes, draft_reply
            FROM emails
            WHERE status IN ('pending_review','manual','snoozed','sent')
              AND DATE(received_at) >= DATE('now','-14 days')
            ORDER BY
              CASE status
                WHEN 'pending_review' THEN 1
                WHEN 'manual'         THEN 2
                WHEN 'snoozed'        THEN 3
                WHEN 'sent'           THEN 4
              END,
              received_at DESC
            LIMIT 60
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _extract_todos(emails: list[dict], cfg: dict) -> list[dict]:
    """Lässt Claude konkrete Aufgaben aus E-Mails extrahieren."""
    if not emails:
        return []

    client = anthropic.Anthropic(api_key=cfg["claude"]["api_key"])
    model  = cfg["claude"].get("model", "claude-haiku-4-5-20251001")

    # E-Mails kompakt für Claude formatieren
    lines = []
    for em in emails:
        body_short = (em.get("body") or "")[:600]
        lines.append(
            f"--- E-Mail #{em['id']} [{em['status']}] ---\n"
            f"Von: {em.get('from_address','')}\n"
            f"Betreff: {em.get('subject','')}\n"
            f"Kategorie: {em.get('category') or '–'}\n"
            f"Notiz: {em.get('notes') or '–'}\n"
            f"Inhalt:\n{body_short}\n"
        )
    user_msg = "\n".join(lines)

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            system=_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = resp.content[0].text.strip()
        # JSON-Block extrahieren (falls Claude doch was drumherum schreibt)
        if "[" in text and "]" in text:
            start = text.index("[")
            end   = text.rindex("]") + 1
            text = text[start:end]
        return json.loads(text)
    except Exception as e:
        print(f"  [Claude-Fehler] {e}")
        return []


# ── PDF-Erzeugung ─────────────────────────────────────────────────────────────

PRIO_STYLES = {
    "hoch":    {"color": DANGER,  "icon": "▲", "label": "HOCH"},
    "mittel":  {"color": WARNING, "icon": "■", "label": "MITTEL"},
    "niedrig": {"color": SUCCESS, "icon": "●", "label": "NIEDRIG"},
}

KAT_COLORS = {
    "Versand":      HexColor("#0d6efd"),
    "Erstattung":   HexColor("#dc3545"),
    "Reklamation":  HexColor("#fd7e14"),
    "Buchhaltung":  HexColor("#6f42c1"),
    "Lieferung":    HexColor("#198754"),
    "Sonstiges":    HexColor("#6c757d"),
}


def _draw_header(canvas_obj, doc):
    """Header und Footer auf jeder Seite zeichnen."""
    canvas_obj.saveState()
    w, h = A4
    # Top-Bar
    canvas_obj.setFillColor(PRIMARY)
    canvas_obj.rect(0, h - 12*mm, w, 12*mm, fill=1, stroke=0)
    canvas_obj.setFillColor(white)
    canvas_obj.setFont("Helvetica-Bold", 11)
    canvas_obj.drawString(20*mm, h - 8*mm, "Levando GmbH – Tagesaufgaben")
    canvas_obj.setFont("Helvetica", 9)
    canvas_obj.drawRightString(w - 20*mm, h - 8*mm, datetime.now().strftime("%A, %d.%m.%Y  %H:%M Uhr"))
    # Footer
    canvas_obj.setFillColor(MUTED)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawCentredString(w/2, 10*mm, f"Seite {doc.page}  ·  Generiert vom Levando E-Mail Agent")
    canvas_obj.restoreState()


def _build_pdf(todos: list[dict], output_path: Path) -> Path:
    s = _styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=22*mm, bottomMargin=18*mm,
        title="Levando Tagesaufgaben",
        author="Levando E-Mail Agent",
    )

    story = []
    today = datetime.now().strftime("%d.%m.%Y")
    weekday = datetime.now().strftime("%A")

    # Titel
    story.append(Paragraph(f"To-Do für {weekday}", s["TitleBig"]))
    story.append(Paragraph(f"{today} · {len(todos)} Aufgaben", s["SubTitle"]))

    # Übersichts-Box
    counts = {"hoch": 0, "mittel": 0, "niedrig": 0}
    for t in todos:
        p = (t.get("prio") or "mittel").lower()
        if p in counts: counts[p] += 1

    summary_data = [[
        Paragraph(f"<b>{counts['hoch']}</b><br/><font size=8>HOCH</font>",
                  ParagraphStyle("c", alignment=TA_CENTER, textColor=white,
                                 fontSize=18, fontName="Helvetica-Bold")),
        Paragraph(f"<b>{counts['mittel']}</b><br/><font size=8>MITTEL</font>",
                  ParagraphStyle("c", alignment=TA_CENTER, textColor=white,
                                 fontSize=18, fontName="Helvetica-Bold")),
        Paragraph(f"<b>{counts['niedrig']}</b><br/><font size=8>NIEDRIG</font>",
                  ParagraphStyle("c", alignment=TA_CENTER, textColor=white,
                                 fontSize=18, fontName="Helvetica-Bold")),
    ]]
    sum_table = Table(summary_data, colWidths=[58*mm]*3, rowHeights=[22*mm])
    sum_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,0), DANGER),
        ("BACKGROUND", (1,0), (1,0), WARNING),
        ("BACKGROUND", (2,0), (2,0), SUCCESS),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",  (0,0), (-1,-1), "CENTER"),
        ("ROUNDEDCORNERS", [6,6,6,6]),
    ]))
    story.append(sum_table)
    story.append(Spacer(1, 14))

    if not todos:
        story.append(Paragraph(
            "<para alignment='center'><font color='#198754' size=14>"
            "✓ Keine offenen Aufgaben für heute!</font></para>",
            s["TodoText"]
        ))
    else:
        # Nach Priorität sortieren
        prio_order = {"hoch": 0, "mittel": 1, "niedrig": 2}
        todos_sorted = sorted(todos, key=lambda t: prio_order.get((t.get("prio") or "mittel").lower(), 1))

        # Gruppierung nach Priorität
        last_prio = None
        for idx, todo in enumerate(todos_sorted, 1):
            prio = (todo.get("prio") or "mittel").lower()
            ps   = PRIO_STYLES.get(prio, PRIO_STYLES["mittel"])
            if prio != last_prio:
                if last_prio is not None:
                    story.append(Spacer(1, 8))
                story.append(Paragraph(
                    f"<font color='{ps['color'].hexval()}'>{ps['icon']}</font>  "
                    f"<font color='{PRIMARY.hexval()}'>Priorität: {ps['label']}</font>",
                    s["Section"]
                ))
                last_prio = prio

            kat       = todo.get("kategorie") or "Sonstiges"
            kat_color = KAT_COLORS.get(kat, MUTED)
            aufgabe   = todo.get("aufgabe") or ""
            kunde     = todo.get("kunde") or ""
            kontext   = todo.get("kontext") or ""
            frist     = todo.get("frist") or ""
            email_id  = todo.get("email_id") or ""

            # Card-Tabelle: links Checkbox + Nummer, rechts Text
            checkbox_cell = Paragraph(
                f"<font size=14 color='{kat_color.hexval()}'>☐</font><br/>"
                f"<font size=8 color='{MUTED.hexval()}'>#{idx}</font>",
                ParagraphStyle("cb", alignment=TA_CENTER, fontSize=10)
            )

            kat_badge = (
                f"<font color='white' backColor='{kat_color.hexval()}'> {kat} </font>"
            )
            frist_badge = ""
            if frist:
                frist_color = DANGER if frist.lower() == "heute" else (
                    WARNING if frist.lower() == "morgen" else MUTED
                )
                frist_badge = (
                    f" &nbsp; <font color='white' backColor='{frist_color.hexval()}'> "
                    f"⏰ {frist} </font>"
                )

            text_cell = Paragraph(
                f"<font size=11><b>{aufgabe}</b></font><br/>"
                + (f"<font size=9 color='{MUTED.hexval()}'>{kontext}</font><br/>" if kontext else "")
                + (f"<font size=9 color='{ACCENT.hexval()}'><b>👤 {kunde}</b></font>" if kunde else "")
                + f"<br/><br/>{kat_badge}{frist_badge}"
                + (f"  <font size=8 color='{MUTED.hexval()}'>E-Mail #{email_id}</font>" if email_id else ""),
                ParagraphStyle("td", fontSize=10, leading=14, textColor=black)
            )

            row = Table(
                [[checkbox_cell, text_cell]],
                colWidths=[15*mm, 159*mm]
            )
            row.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,-1), LIGHT),
                ("VALIGN",     (0,0), (-1,-1), "TOP"),
                ("LEFTPADDING",   (0,0), (-1,-1), 8),
                ("RIGHTPADDING",  (0,0), (-1,-1), 8),
                ("TOPPADDING",    (0,0), (-1,-1), 10),
                ("BOTTOMPADDING", (0,0), (-1,-1), 10),
                ("LINEBEFORE",    (0,0), (0,0), 4, ps["color"]),
                ("ROUNDEDCORNERS", [4,4,4,4]),
            ]))
            story.append(KeepTogether(row))
            story.append(Spacer(1, 6))

    # ── Versprechen-Sektion ──────────────────────────────────────────────────
    commits = db.get_open_commitments(50)
    if commits:
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=0.7, color=PRIMARY))
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "<para><font color='#1a2035' size=14><b>Versprechen &amp; Zusagen</b></font></para>",
            s["TodoText"]
        ))
        story.append(Paragraph(
            f"<para><font color='#6c757d' size=9>{len(commits)} offene Versprechen aus E-Mail-Antworten</font></para>",
            s["TodoText"]
        ))
        story.append(Spacer(1, 8))

        now = datetime.now()
        for c in commits[:25]:
            try:
                due = datetime.fromisoformat(c["due_date"])
            except Exception:
                continue
            if due < now:
                color_hex = "#dc3545"
                label = f"ÜBERFÄLLIG seit {due.strftime('%d.%m.')}"
            elif due.date() == now.date():
                color_hex = "#ffc107"
                label = f"HEUTE bis {due.strftime('%H:%M')}"
            else:
                color_hex = "#198754"
                label = due.strftime("Bis %a, %d.%m.")

            text = (
                f"<para><font color='{color_hex}' size=8><b>{label}</b></font> &nbsp; "
                f"<font color='#6c757d' size=9>an {(c.get('sender') or '')[:40]}</font><br/>"
                f"<font size=10>\"{(c.get('promise') or '')[:200]}\"</font><br/>"
                f"<font color='#999' size=8>Betreff: {(c.get('subject') or '')[:60]}</font></para>"
            )
            row = Table([[Paragraph(text, s["TodoText"])]],
                        colWidths=[170*mm], rowHeights=None)
            row.setStyle(TableStyle([
                ("BACKGROUND",     (0,0), (0,0), HexColor("#f8f9fa")),
                ("LINEBEFORE",     (0,0), (0,0), 3, HexColor(color_hex)),
                ("LEFTPADDING",    (0,0), (-1,-1), 12),
                ("RIGHTPADDING",   (0,0), (-1,-1), 8),
                ("TOPPADDING",     (0,0), (-1,-1), 8),
                ("BOTTOMPADDING",  (0,0), (-1,-1), 8),
                ("ROUNDEDCORNERS", [4,4,4,4]),
            ]))
            story.append(row)
            story.append(Spacer(1, 5))

    # Footer-Hinweis
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=0.5, color=grey))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Diese Liste wurde automatisch aus {len(_gather_open_emails())} offenen E-Mails "
        "der letzten 14 Tage generiert. Erledigte Aufgaben werden nicht automatisch entfernt – "
        "sie verschwinden, sobald die zugehörige E-Mail beantwortet/geschlossen ist.",
        s["Footer"]
    ))

    doc.build(story, onFirstPage=_draw_header, onLaterPages=_draw_header)
    return output_path


# ── Hauptfunktion ─────────────────────────────────────────────────────────────

def generate_todo_pdf() -> tuple[Path, list[dict]]:
    """Erzeugt das Tages-ToDo-PDF und gibt Pfad + ToDo-Liste zurück."""
    cfg = _load_cfg()

    print("  Sammle offene E-Mails …")
    emails = _gather_open_emails()
    print(f"  → {len(emails)} E-Mails")

    print("  Lasse Claude Aufgaben extrahieren …")
    todos = _extract_todos(emails, cfg)
    print(f"  → {len(todos)} Aufgaben gefunden")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    pdf_path  = PDF_DIR / f"todo_{timestamp}.pdf"
    print(f"  Erzeuge PDF: {pdf_path.name}")
    _build_pdf(todos, pdf_path)
    return pdf_path, todos


def send_todo_pdf():
    """Erzeugt PDF und sendet per E-Mail + Telegram."""
    cfg = _load_cfg()

    pdf_path, todos = generate_todo_pdf()

    # E-Mail an report_email senden
    report_email = cfg.get("agent", {}).get("report_email", "")
    if report_email:
        try:
            from email_client import EmailClient
            import smtplib, ssl
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.application import MIMEApplication

            acc = (cfg.get("accounts") or [cfg.get("email", {})])[0]
            today = datetime.now().strftime("%d.%m.%Y")
            counts = {"hoch": 0, "mittel": 0, "niedrig": 0}
            for t in todos:
                p = (t.get("prio") or "mittel").lower()
                if p in counts: counts[p] += 1

            body = (
                f"Guten Morgen,\n\n"
                f"hier ist Ihre Tagesliste fuer {today}:\n\n"
                f"  Hoch:    {counts['hoch']}\n"
                f"  Mittel:  {counts['mittel']}\n"
                f"  Niedrig: {counts['niedrig']}\n"
                f"  Gesamt:  {len(todos)} Aufgaben\n\n"
                f"Details siehe PDF im Anhang.\n\n"
                f"Viel Erfolg!\n--\nLevando E-Mail Agent"
            )

            msg = MIMEMultipart()
            msg["From"]    = acc["email"]
            msg["To"]      = report_email
            msg["Subject"] = f"📋 Tagesaufgaben {today} – {len(todos)} ToDos"
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with open(pdf_path, "rb") as f:
                pdf_attach = MIMEApplication(f.read(), _subtype="pdf")
                pdf_attach.add_header("Content-Disposition", "attachment",
                                       filename=pdf_path.name)
                msg.attach(pdf_attach)

            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(acc["smtp_server"], acc["smtp_port"], context=ctx) as smtp:
                smtp.login(acc["email"], acc["password"])
                smtp.sendmail(acc["email"], report_email, msg.as_string())
            print(f"  ✓ Per E-Mail gesendet an {report_email}")
        except Exception as e:
            print(f"  ✗ E-Mail-Versand fehlgeschlagen: {e}")

    # Telegram-Dokument senden
    try:
        import urllib.request
        import urllib.parse
        token = cfg.get("telegram", {}).get("bot_token", "")
        chat_id = str(cfg.get("telegram", {}).get("chat_id", ""))
        if token and chat_id:
            url = f"https://api.telegram.org/bot{token}/sendDocument"
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            # multipart/form-data manuell zusammenbauen
            boundary = "----LevandoBoundary7MA4YWxkTrZu0gW"
            body = []
            body.append(f"--{boundary}".encode())
            body.append(b'Content-Disposition: form-data; name="chat_id"\r\n')
            body.append(chat_id.encode())
            body.append(f"--{boundary}".encode())
            body.append(b'Content-Disposition: form-data; name="caption"\r\n')
            today = datetime.now().strftime("%d.%m.%Y")
            cap = f"📋 Tagesaufgaben {today} – {len(todos)} ToDos"
            body.append(cap.encode("utf-8"))
            body.append(f"--{boundary}".encode())
            body.append(
                f'Content-Disposition: form-data; name="document"; filename="{pdf_path.name}"\r\n'
                f'Content-Type: application/pdf\r\n'.encode()
            )
            body.append(pdf_bytes)
            body.append(f"--{boundary}--".encode())

            payload = b"\r\n".join(body)
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            if result.get("ok"):
                print("  ✓ Per Telegram gesendet")
            else:
                print(f"  ✗ Telegram: {result.get('description','?')}")
    except Exception as e:
        print(f"  ✗ Telegram-Versand fehlgeschlagen: {e}")

    return pdf_path, todos


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "=" * 52)
    print(f"  Levando ToDo-Generator  |  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 52)
    if "--show" in sys.argv:
        path, todos = generate_todo_pdf()
        print(f"\nPDF: {path}")
        print(f"Aufgaben: {len(todos)}")
    else:
        send_todo_pdf()
