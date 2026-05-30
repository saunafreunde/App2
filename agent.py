"""
Claude Email-Agent – Kernlogik.

Neu (v2):
  • Pre-Filter: Newsletter/Werbung/Portal → kein Claude-Aufruf
  • Dringlichkeitserkennung → sofortige Telegram-Warnung
  • Business-Hours-Filter → Antworten nur Mo–Fr 8–18 Uhr
  • Absender-Gedächtnis → Claude kennt Vorgeschichte
  • Lernkurve → Konfidenz-Boost bei hoher Genehmigungsrate
  • Watchdog → IMAP-Retry mit Telegram-Alert bei Ausfall
"""

import re
import json
import time
import random
from datetime import datetime, time as dtime, timedelta

import anthropic
from anthropic import beta_tool

import database as db
from email_client import EmailClient

# ── Globaler Zustand ──────────────────────────────────────────────────────────
_client: anthropic.Anthropic           = None
_email_client: EmailClient             = None
_email_clients: dict[str, EmailClient] = {}
_config: dict                          = None


def setup(cfg: dict):
    global _client, _email_client, _email_clients, _config
    _config = cfg
    _client = anthropic.Anthropic(api_key=cfg["claude"]["api_key"])
    accounts = cfg.get("accounts") or [cfg.get("email", {})]
    for acc in accounts:
        _email_clients[acc["email"]] = EmailClient(acc)
    _email_client = _email_clients[accounts[0]["email"]]


# ── Pre-Filter-Muster ─────────────────────────────────────────────────────────

_NOREPLY_PATTERNS = [
    "noreply", "no-reply", "do-not-reply", "donotreply",
    "newsletter", "news@", "mailing", "mailer", "automated@",
    "bounce@", "mailer-daemon", "autorespond", "notifications@",
    "notification@", "updates@", "deals@", "offers@",
]

_ADS_SENDER_DOMAINS = [
    "amazon.com", "business.amazon", "amazon.de",
    "ebay.com", "ebay.de",
    "bing.com", "microsoft.com",
    "facebook.com", "facebookmail.com", "meta.com",
    "linkedin.com", "xing.com",
    "google.com", "googlemail.com",
    "haendlerbund.de", "onlinehaendlernews",
    "dhl.de", "dhlgeschaeftskundenportal",
    "paypal.com", "paypal.de",
]

_ADS_SUBJECT_KEYWORDS = [
    "newsletter", "unsubscribe", "abbestellen", "abmelden",
    "deal days", "sale", "% rabatt", "% off",
    "black friday", "cyber monday", "prime day",
    "jetzt kaufen", "nur heute", "limited time", "last chance",
    "sonderangebot", "exklusiv für sie", "geschäftsangebot",
    "jetzt sparen", "gratis", "kostenlos testen",
    "business deal", "neue angebote", "upgrade your", "try for free",
]

_PORTAL_SENDERS = {
    "kleinanzeigen.de":      "Kleinanzeigen",
    "ebay-kleinanzeigen.de": "Kleinanzeigen",
    "ebay.de":               "eBay",
    "ebay.com":              "eBay",
    "messages.ebay":         "eBay",
    "amazon.de":             "Amazon Seller Central",
    "amazon.com":            "Amazon Seller Central",
    "seller.amazon":         "Amazon Seller Central",
    "sellercentral":         "Amazon Seller Central",
    "marketplace.amazon":    "Amazon Seller Central",
    "bgs":                   "BGS",
}

# ── Dringlichkeits-Muster ─────────────────────────────────────────────────────

_URGENCY_KEYWORDS = [
    "mahnung", "mahnbescheid", "inkasso", "zwangsvollstreckung",
    "abmahnung", "rechtsanwalt", "anwalt", "klage", "gericht",
    "deadline", "dringend",
    "letzte mahnung", "zahlungsrückstand", "forderung",
    "kündigung", "beschwerde",
    "betrug", "strafanzeige",
]


def _extract_email_addr(from_field: str) -> str:
    m = re.search(r"<([^>]+)>", from_field)
    return (m.group(1) if m else from_field).lower().strip()


def pre_filter(email_data: dict) -> str | None:
    """
    Gibt zurück:
      None           → normal mit Claude verarbeiten
      "filtered"     → Newsletter/Werbung, ignorieren
      "portal:XYZ"   → nur im Portal XYZ antwortbar
      "urgent"       → dringend, sofort Telegram-Alert

    WICHTIG: Noreply/Werbung wird VOR der Dringlichkeitsprüfung gefiltert,
    damit automatische Mails (z.B. DHL-Lieferschein mit "Datenschutz" im Text)
    keinen falschen Urgent-Alert auslösen.
    """
    from_raw  = (email_data.get("from_address") or "").lower()
    from_addr = _extract_email_addr(from_raw)
    subject   = (email_data.get("subject") or "").lower()
    body      = (email_data.get("body") or "").lower()

    # 1. Noreply / Newsletter – zuerst! (kann keine echte Dringlichkeit sein)
    for pat in _NOREPLY_PATTERNS:
        if pat in from_addr:
            return "filtered"

    # 2. Werbe-Domains (aber nicht Seller Central)
    for dom in _ADS_SENDER_DOMAINS:
        if dom in from_addr:
            if "seller" in from_addr or "sellercentral" in from_addr:
                break
            return "filtered"

    # 3. Betreff = Werbung
    for kw in _ADS_SUBJECT_KEYWORDS:
        if kw in subject:
            return "filtered"

    # 4. Portal-Absender
    for pattern, portal_name in _PORTAL_SENDERS.items():
        if pattern in from_addr:
            return f"portal:{portal_name}"

    # 5. Dringlichkeit – nur für echte Absender (kein noreply, keine Werbung)
    full_text = subject + " " + body
    for kw in _URGENCY_KEYWORDS:
        if kw in full_text:
            return "urgent"

    return None


# ── Business-Hours ────────────────────────────────────────────────────────────

def _is_business_hours() -> bool:
    """Prüft ob aktuell Geschäftszeiten sind (config: business_hours)."""
    bh = _config.get("business_hours", {})
    start_h = bh.get("start", 8)
    end_h   = bh.get("end",   18)
    days    = bh.get("days",  [0, 1, 2, 3, 4])  # Mo–Fr

    now = datetime.now()
    if now.weekday() not in days:
        return False
    return dtime(start_h, 0) <= now.time() < dtime(end_h, 0)


# ── System-Prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt(sender_context: list[dict] = None,
                          category_hint: str = None) -> str:
    company   = _config.get("agent", {}).get("company_name", "Levando GmbH")
    threshold = _config.get("agent", {}).get("auto_reply_threshold", 0.8)

    # ── Absender-Vorgeschichte ────────────────────────────────────────────────
    context_block = ""
    if sender_context:
        lines = ["ABSENDER-VORGESCHICHTE (letzte Kontakte):"]
        for s in sender_context:
            status_label = s.get("status", "?")
            note = ""
            if status_label == "rejected" and s.get("notes"):
                note = f" → Abgelehnt wegen: {s['notes'].replace('Abgelehnt: ','')[:100]}"
            lines.append(
                f"  • {(s.get('received_at') or '')[:10]}  "
                f"[{status_label}]  {s.get('subject','')[:50]}{note}"
            )
        if sender_context[0].get("sent_reply"):
            lines.append(f"  Letzte Antwort: {sender_context[0]['sent_reply'][:200]}")
        context_block = "\n".join(lines) + "\n\n"

    # ── Lernfeedback aus Ablehnungen ─────────────────────────────────────────
    feedback_block = ""
    feedback = db.get_rejection_feedback(category=category_hint, limit=5)
    if feedback:
        lines = ["ABGELEHNTE ENTWÜRFE – DIESE FEHLER VERMEIDEN:"]
        for f in feedback:
            lines.append(
                f"  • [{f.get('category','?')}] Betreff: {(f.get('original_subject',''))[:50]}"
                f"\n    Grund der Ablehnung: {f.get('reason','')[:200]}"
            )
        feedback_block = "\n".join(lines) + "\n\n"

    return f"""{context_block}{feedback_block}Du bist der persönliche E-Mail-Assistent von {company} – schreibst aber wie ein echter Mensch, NICHT wie ein Bot.

DEINE AUFGABE:
1. Kategorisiere: ANFRAGE | BESCHWERDE | BESTELLUNG | SUPPORT | ALLGEMEIN
2. Suche passende Vorlagen (search_knowledge)
3. Verfasse eine menschliche, empathische Antwort auf Deutsch
4. Vergib Vertrauensscore (0.0–1.0):
   - >= {threshold}: senden  → send_email_reply()
   - 0.5–{threshold-0.01:.2f}: Entwurf  → mark_for_review()
   - < 0.5: manuell  → mark_as_manual()

KONVERSATIONS-STIL (sehr wichtig!):
- Antworte WIE EIN MENSCH – kurze, persönliche Sätze, kein Formular-Deutsch
- Bei Problemen/Beschwerden: zeige ECHTE Empathie ("Das tut mir leid", "Ich verstehe Ihren Ärger")
- Mache VERBINDLICHE ZUSAGEN mit Zeitrahmen, statt Generic-Floskeln:
  ✓ GUT:  "Ich kümmere mich gleich darum und melde mich morgen mit einer konkreten Antwort."
  ✓ GUT:  "Ich prüfe das mit DHL und gebe Ihnen bis morgen Mittag Bescheid."
  ✗ SCHLECHT: "Wir werden Ihre Anfrage bearbeiten."
  ✗ SCHLECHT: "Vielen Dank für Ihre Nachricht."
- Versprich nur REALISTISCHES (kein "in 5 Minuten gelöst"). Lieber "morgen Feedback" als unrealistisch.
- Wenn du keine sofortige Lösung hast: zusichern dass du dich KÜMMERST und WANN du dich meldest.

BEISPIELE ANTWORTSTIL:

Beispiel "Paket nicht angekommen":
"Hallo Frau Müller, das tut mir leid – ich verstehe den Ärger. Ich prüfe gleich mit DHL was los ist und melde mich morgen im Lauf des Vormittags bei Ihnen mit einer konkreten Information. Falls es bis dahin doch noch ankommt, freue ich mich über eine kurze Mitteilung."

Beispiel "Frage zur Lieferzeit":
"Hallo Herr Schmidt, danke für Ihre Nachricht. Bei normaler Bestellung versenden wir innerhalb von 1–2 Werktagen, danach sind es typisch 2–3 Tage Versandzeit. Bei Fragen zu einer konkreten Bestellnummer schauen Sie mir gerne kurz, ich check das dann persönlich."

SIGNATUR: Schreibe KEINE Grußformel oder Signatur – wird automatisch ergänzt.

QUALITÄT:
- Bei Beschwerden: max. Konfidenz 0.75 (immer Überprüfung)
- Bei Vorgeschichte: Bezug nehmen auf frühere Kontakte
- Lernfeedback oben IMMER beachten
- KEINE Formaltexte wie "Mit Bezug auf Ihre Anfrage"
"""


# ── Tools ─────────────────────────────────────────────────────────────────────

@beta_tool
def get_email_details(email_id: int) -> str:
    """Hole vollständige Details einer E-Mail aus der Datenbank.

    Args:
        email_id: Die Datenbank-ID der E-Mail.
    """
    row = db.get_email_by_id(email_id)
    return json.dumps(row, ensure_ascii=False, default=str) if row else "Nicht gefunden."


@beta_tool
def search_knowledge(keywords: str, category: str = "") -> str:
    """Suche in Vorlagen und gelernten Antworten.

    Args:
        keywords: Schlüsselwörter, kommagetrennt.
        category: Optionale Kategorie.
    """
    cat       = category.strip() or None
    templates = db.get_templates(cat)
    learned   = db.get_learned_responses(cat, limit=6)
    return json.dumps({"vorlagen": templates, "gelernte_antworten": learned},
                      ensure_ascii=False, default=str)


def _compute_send_at() -> str:
    """Plant einen zufälligen Sendezeitpunkt 1-3h in der Zukunft.
    Außerhalb der Geschäftszeiten wird auf den nächsten Werktagsmorgen verschoben."""
    bh    = _config.get("business_hours", {})
    start = bh.get("start", 8)
    end   = bh.get("end",   18)
    days  = bh.get("days",  [0, 1, 2, 3, 4])

    # Zufällige Verzögerung 1-3 Stunden (in Minuten für mehr Variation)
    delay_minutes = random.randint(60, 180)
    target = datetime.now() + timedelta(minutes=delay_minutes)

    # Außerhalb Geschäftszeiten? → Auf nächsten Werktag morgen verschieben
    while target.weekday() not in days or target.hour < start or target.hour >= end:
        if target.hour >= end or target.weekday() not in days:
            # Nächster Tag um Geschäftsbeginn + Random-Offset (0-90 Min)
            target = target.replace(hour=start, minute=0, second=0, microsecond=0)
            target += timedelta(days=1)
            if target.weekday() not in days:
                continue  # nochmal weiter
            target += timedelta(minutes=random.randint(0, 90))
        elif target.hour < start:
            target = target.replace(hour=start, minute=random.randint(0, 90),
                                    second=0, microsecond=0)
    return target.isoformat()


@beta_tool
def send_email_reply(email_id: int, to_address: str, subject: str,
                     body: str, confidence: float, category: str) -> str:
    """Plant eine Antwort-E-Mail mit zufälliger Verzögerung (1-3h) für menschliches Verhalten.

    Args:
        email_id:   Datenbank-ID der Original-E-Mail.
        to_address: Empfänger.
        subject:    Betreff mit 'Re: ' Prefix.
        body:       Antworttext OHNE Signatur.
        confidence: 0.0–1.0.
        category:   Kategorie.
    """
    threshold = _config.get("agent", {}).get("auto_reply_threshold", 0.8)

    # Konfidenz-Boost aus Lernkurve anwenden
    boost = db.get_category_confidence_boost(category)
    effective_conf = min(confidence + boost, 1.0)

    if effective_conf < threshold:
        return (f"Konfidenz {effective_conf:.2f} unter Schwelle {threshold:.2f}. "
                f"Bitte mark_for_review() verwenden.")

    # Verzögerten Sendezeitpunkt berechnen (1-3h, ggf. nächster Werktag)
    send_at = _compute_send_at()
    full_draft = f"BETREFF: {subject}\n\n{body}"

    db.update_email(email_id,
                    status="scheduled",
                    category=category,
                    confidence=effective_conf,
                    draft_reply=full_draft,
                    sent_reply=body,
                    send_at=send_at,
                    processed_at=datetime.now().isoformat())

    db.log_activity("scheduled", email_id, f"auto ({effective_conf:.0%}, send_at={send_at[:16]})")
    when = datetime.fromisoformat(send_at).strftime("%d.%m. %H:%M")
    return f"Geplant für {when} an {to_address} (verzögert für menschlicheres Verhalten)."


# ── Versprechen-Extraktion ────────────────────────────────────────────────────

_PROMISE_PATTERNS = [
    # "morgen", "übermorgen", "in X Tagen", "bis Mittwoch", "bis Freitag" etc.
    (r"(morgen|übermorgen|heute Abend|heute|morgen früh|morgen Vormittag|morgen Nachmittag|morgen Mittag)", None),
    (r"in\s+(\d+)\s+(Tagen?|Werktagen?|Stunden?)", None),
    (r"bis\s+(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag)", None),
    (r"bis\s+(spätestens\s+)?(\d{1,2}\.\d{1,2}\.|\d{1,2}\.\s+\w+)", None),
    (r"nächste\s+Woche", None),
    (r"diese\s+Woche", None),
]

_PROMISE_VERBS = [
    "melde mich", "melden uns", "kümmere mich", "kümmern uns",
    "prüfe", "prüfen", "schaue", "schauen", "schicke", "schicken",
    "sende", "senden", "klär", "informiere", "informieren",
    "Feedback", "Bescheid", "Antwort", "Rückmeldung",
]


def _parse_due_from_text(text: str) -> str:
    """Versucht ein Fälligkeitsdatum aus Versprechen-Text zu extrahieren."""
    now = datetime.now()
    text_lower = text.lower()

    if "heute abend" in text_lower or "heute" in text_lower:
        return now.replace(hour=18, minute=0).isoformat()
    if "morgen früh" in text_lower or "morgen vormittag" in text_lower:
        return (now + timedelta(days=1)).replace(hour=10, minute=0).isoformat()
    if "morgen nachmittag" in text_lower or "morgen mittag" in text_lower:
        return (now + timedelta(days=1)).replace(hour=14, minute=0).isoformat()
    if "übermorgen" in text_lower:
        return (now + timedelta(days=2)).replace(hour=12, minute=0).isoformat()
    if "morgen" in text_lower:
        return (now + timedelta(days=1)).replace(hour=12, minute=0).isoformat()

    m = re.search(r"in\s+(\d+)\s+(Tagen?|Werktagen?|Stunden?)", text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if "stund" in unit:
            return (now + timedelta(hours=n)).isoformat()
        return (now + timedelta(days=n)).replace(hour=12, minute=0).isoformat()

    weekdays = {"montag":0,"dienstag":1,"mittwoch":2,"donnerstag":3,
                "freitag":4,"samstag":5,"sonntag":6}
    for name, idx in weekdays.items():
        if f"bis {name}" in text_lower:
            days_ahead = (idx - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (now + timedelta(days=days_ahead)).replace(hour=12, minute=0).isoformat()

    if "nächste woche" in text_lower:
        return (now + timedelta(days=7)).replace(hour=12, minute=0).isoformat()

    # Fallback: 1 Tag
    return (now + timedelta(days=1)).replace(hour=12, minute=0).isoformat()


def _extract_promises_from_reply(reply_body: str) -> list[str]:
    """Findet Versprechens-Sätze in einer eigenen Antwort."""
    sentences = re.split(r"(?<=[.!?])\s+", reply_body)
    found = []
    for s in sentences:
        if len(s) < 15 or len(s) > 300:
            continue
        s_lower = s.lower()
        # Hat Verb + Zeit-Marker?
        has_verb = any(v.lower() in s_lower for v in _PROMISE_VERBS)
        has_time = any(re.search(p, s_lower, re.IGNORECASE) for p, _ in _PROMISE_PATTERNS)
        if has_verb and has_time:
            found.append(s.strip())
    return found[:3]  # max 3 Versprechen pro Mail


def _extract_and_save_commitments(email_id: int, to_address: str,
                                   subject: str, reply_body: str,
                                   account_email: str):
    """Extrahiert Versprechen aus einer gerade gesendeten Antwort und speichert sie."""
    promises = _extract_promises_from_reply(reply_body)
    for p in promises:
        due = _parse_due_from_text(p)
        try:
            db.save_commitment(email_id=email_id, account_email=account_email,
                               sender=to_address, subject=subject,
                               promise=p, due_date=due)
        except Exception as e:
            print(f"    Versprechen konnte nicht gespeichert werden: {e}")


# ── Versendet alle fälligen geplanten E-Mails ─────────────────────────────────

def send_due_emails():
    """Verarbeitet alle E-Mails mit status='scheduled' deren send_at jetzt erreicht ist."""
    due = db.get_due_emails_to_send()
    if not due:
        return 0

    print(f"\n  📤 {len(due)} geplante E-Mail(s) jetzt fällig zum Versand:")
    sent = 0
    for mail in due:
        acc_email = mail.get("account_email") or ""
        ec = _email_clients.get(acc_email) or _email_client
        if not ec:
            continue

        body = mail.get("sent_reply") or ""
        draft = mail.get("draft_reply") or ""
        subject = ""
        if draft.startswith("BETREFF:"):
            parts = draft.split("\n\n", 1)
            subject = parts[0].replace("BETREFF:", "").strip()
        if not subject:
            orig_subj = mail.get("subject") or ""
            subject = orig_subj if orig_subj.startswith("Re:") else f"Re: {orig_subj}"

        try:
            ec.send_reply(mail["from_address"], subject, body)
            db.update_email(mail["id"], status="sent")

            # Versprechen extrahieren & speichern
            _extract_and_save_commitments(
                email_id=mail["id"],
                to_address=mail["from_address"],
                subject=subject,
                reply_body=body,
                account_email=acc_email,
            )

            # Lernen
            kw = [w for w in (mail.get("subject") or "").split() if len(w) > 3][:6]
            db.save_learned_response(mail.get("subject", ""), mail.get("body", ""),
                                     mail.get("category") or "ALLGEMEIN", kw,
                                     subject, body, mail.get("confidence") or 0.8, "auto")
            try:
                ec.mark_as_read(mail["uid"])
            except Exception:
                pass

            db.log_activity("sent_delayed", mail["id"], f"verzögert versendet")
            print(f"    ✓ #{mail['id']} an {mail['from_address']}")
            sent += 1
        except Exception as e:
            print(f"    ✗ #{mail['id']}: {e}")
            db.log_activity("send_error", mail["id"], str(e))
    return sent


@beta_tool
def mark_for_review(email_id: int, draft_reply: str, subject: str,
                    confidence: float, category: str, notes: str = "") -> str:
    """Entwurf zur menschlichen Überprüfung speichern.

    Args:
        email_id:    Datenbank-ID.
        draft_reply: Antworttext OHNE Signatur.
        subject:     Vorgeschlagener Betreff.
        confidence:  0.0–1.0.
        category:    Kategorie.
        notes:       Begründung.
    """
    full_draft = f"BETREFF: {subject}\n\n{draft_reply}"
    db.update_email(email_id,
                    status="pending_review",
                    category=category,
                    confidence=confidence,
                    draft_reply=full_draft,
                    notes=notes,
                    processed_at=datetime.now().isoformat())
    db.log_activity("flagged", email_id, notes)
    return f"Entwurf gespeichert ({confidence:.0%}). Warte auf Genehmigung."


@beta_tool
def mark_as_manual(email_id: int, category: str, reason: str) -> str:
    """Manuelle Bearbeitung markieren (Konfidenz < 0.5).

    Args:
        email_id: ID.
        category: Erkannte Kategorie.
        reason:   Begründung.
    """
    db.update_email(email_id, status="manual", category=category,
                    confidence=0.0, notes=reason,
                    processed_at=datetime.now().isoformat())
    db.log_activity("manual", email_id, reason)
    return f"E-Mail {email_id} zur manuellen Bearbeitung markiert."


@beta_tool
def save_template(name: str, category: str, keywords: str,
                  subject_template: str, body_template: str) -> str:
    """Neue Vorlage speichern.

    Args:
        name:             Name.
        category:         Kategorie.
        keywords:         Kommagetrennt.
        subject_template: Betreff-Vorlage.
        body_template:    Text-Vorlage OHNE Signatur.
    """
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    db.save_template(name, category, kw_list, subject_template, body_template)
    return f"Vorlage '{name}' gespeichert."


# ── E-Mail verarbeiten ────────────────────────────────────────────────────────

def process_email(email_data: dict):
    sender_ctx = db.get_sender_context(email_data.get("from_address", ""))

    tools = [get_email_details, search_knowledge, send_email_reply,
             mark_for_review, mark_as_manual, save_template]

    user_msg = (
        f"Bitte verarbeite diese E-Mail:\n\n"
        f"ID: {email_data['id']}\n"
        f"Von: {email_data['from_address']}\n"
        f"Betreff: {email_data['subject']}\n"
        f"Empfangen: {email_data['received_at']}\n\n"
        f"Inhalt:\n{email_data['body']}\n\n"
        f"Vorgehen:\n"
        f"1. search_knowledge() aufrufen\n"
        f"2. Professionelle Antwort verfassen (OHNE Signatur)\n"
        f"3. Senden oder markieren je nach Konfidenz"
    )

    runner = _client.beta.messages.tool_runner(
        model=_config["claude"].get("model", "claude-haiku-4-5-20251001"),
        max_tokens=1024,
        system=[{
            "type": "text",
            "text": _build_system_prompt(sender_ctx, category_hint=None),
            "cache_control": {"type": "ephemeral"},
        }],
        tools=tools,
        messages=[{"role": "user", "content": user_msg}],
        betas=["prompt-caching-2024-07-31"],
    )
    for _ in runner:
        pass


# ── Alle E-Mails verarbeiten (mit Watchdog) ───────────────────────────────────

def _fetch_with_retry(ec: EmailClient, max_retries: int = 3) -> list[dict]:
    """IMAP-Abruf mit automatischem Retry bei Verbindungsproblemen."""
    for attempt in range(1, max_retries + 1):
        try:
            return ec.fetch_new_emails()
        except Exception as e:
            if attempt == max_retries:
                raise
            wait = 60 * attempt
            print(f"    Verbindungsfehler (Versuch {attempt}/{max_retries}): {e}")
            print(f"    Warte {wait}s …")
            time.sleep(wait)
    return []


def process_all_emails():
    global _email_client
    sep = "=" * 52
    print(f"\n{sep}")
    print(f"  E-Mail-Agent  |  {datetime.now().strftime('%d.%m.%Y  %H:%M')}")
    print(sep)

    # ── 0. Geplante E-Mails (verzögerter Versand) verarbeiten ────────────────
    sent_delayed = send_due_emails()
    if sent_delayed:
        print(f"  → {sent_delayed} verzögerte E-Mail(s) versendet")

    # Snooze-Wakeup: aufgewachte E-Mails wieder als pending_review markieren
    woken = db.wake_snoozed_emails()
    if woken:
        print(f"\n  💤 → ⏳ {woken} geschnoozte E-Mail(s) reaktiviert.")
        # Telegram-Alert für reaktivierte
        try:
            import telegram_notify as tg
            for em in db.get_pending_review_emails():
                # Nur falls in den letzten 30s reaktiviert
                pass
            tg.send_alert(f"⏰ {woken} geschnoozte E-Mail(s) reaktiviert", level="info")
        except Exception:
            pass

    accounts = _config.get("accounts") or [_config.get("email", {})]

    for acc in accounts:
        acc_email = acc["email"]
        ec = _email_clients[acc_email]
        print(f"\n{'─'*52}\n  Konto: {acc_email}\n{'─'*52}")

        print("\n[1] Hole neue E-Mails …")
        try:
            new_mails = _fetch_with_retry(ec)
            print(f"    {len(new_mails)} neue E-Mail(s)")
        except Exception as e:
            print(f"    FEHLER nach 3 Versuchen: {e}")
            try:
                import telegram_notify as tg
                tg.send_alert(f"IMAP-Fehler: {acc_email}", str(e), level="error")
            except Exception:
                pass
            continue

        saved = 0
        for m in new_mails:
            eid = db.save_email(m["uid"], m["from"], m["subject"],
                                m["body"], m["received_at"], acc_email)
            if eid > 0:
                saved += 1
        if saved:
            print(f"    {saved} gespeichert")

        pending = db.get_pending_emails(acc_email)
        print(f"\n[2] Verarbeite {len(pending)} ausstehende E-Mail(s) …")
        _email_client = ec

        filtered_count = portal_count = urgent_count = 0

        for mail in pending:
            subj_short = (mail["subject"] or "")[:55]
            from_short = (mail["from_address"] or "")[:35]
            print(f"\n    → [{mail['id']}] {subj_short}")
            print(f"         von: {from_short}")

            filter_result = pre_filter(mail)

            if filter_result == "urgent":
                print("         🚨 DRINGEND – Telegram-Alert")
                urgent_count += 1
                try:
                    import telegram_notify as tg
                    tg.send_alert(
                        f"🚨 DRINGENDE E-Mail #{mail['id']}",
                        f"Von: {mail['from_address']}\nBetreff: {mail['subject']}\n\n{(mail['body'] or '')[:300]}",
                        level="error"
                    )
                except Exception:
                    pass
                # Mit Claude verarbeiten, aber max. Konfidenz 0.6
                try:
                    process_email(mail)
                    updated = db.get_email_by_id(mail["id"])
                    if updated and (updated.get("confidence") or 0) > 0.6:
                        db.update_email(mail["id"],
                                        confidence=0.6,
                                        status="pending_review",
                                        notes="Dringend – manuelle Prüfung erforderlich")
                    updated2 = db.get_email_by_id(mail["id"])
                    # Pending-Alert mit Mapping für /ok{id}-Befehl
                    if updated2 and updated2.get("status") == "pending_review":
                        try:
                            import telegram_notify as tg
                            msg_id = tg.send_pending_alert(updated2)
                            if msg_id:
                                db.save_tg_map(msg_id, mail["id"])
                        except Exception:
                            pass
                    print(f"         ✓ {updated2.get('status','?')} (dringend, max. 60%)")
                except Exception as e:
                    db.update_email(mail["id"], status="error", notes=str(e))
                    print(f"         ✗ FEHLER: {e}")
                continue

            if filter_result == "filtered":
                db.update_email(mail["id"], status="filtered", category="WERBUNG",
                                confidence=0.0, notes="Newsletter/Werbung",
                                processed_at=datetime.now().isoformat())
                db.log_activity("filtered", mail["id"], "Newsletter/Werbung")
                print("         ⊘ gefiltert")
                filtered_count += 1
                continue

            if filter_result and filter_result.startswith("portal:"):
                portal_name = filter_result.split(":", 1)[1]
                db.update_email(mail["id"], status="manual", category="PORTAL",
                                confidence=0.0,
                                notes=f"Antwort nur im {portal_name}-Portal möglich",
                                processed_at=datetime.now().isoformat())
                db.log_activity("portal", mail["id"], portal_name)
                print(f"         ⚑ Portal: {portal_name}")
                portal_count += 1
                continue

            try:
                process_email(mail)
                updated = db.get_email_by_id(mail["id"])
                status  = updated.get("status", "?") if updated else "?"
                conf    = updated.get("confidence") if updated else None
                conf_s  = f"  ({conf:.0%})" if conf is not None else ""

                # Telegram-Benachrichtigung bei pending_review
                if status == "pending_review":
                    try:
                        import telegram_notify as tg
                        msg_id = tg.send_pending_alert(updated)
                        if msg_id:
                            db.save_tg_map(msg_id, mail["id"])
                    except Exception:
                        pass

                print(f"         ✓ {status}{conf_s}")
            except Exception as e:
                print(f"         ✗ FEHLER: {e}")
                db.update_email(mail["id"], status="error", notes=str(e))

        summary = []
        if filtered_count: summary.append(f"{filtered_count} gefiltert")
        if portal_count:   summary.append(f"{portal_count} Portal")
        if urgent_count:   summary.append(f"{urgent_count} dringend")
        if summary:
            print(f"\n    → {' | '.join(summary)}")

    print(f"\n{sep}")


# ── Tages-Report ──────────────────────────────────────────────────────────────

def generate_daily_report() -> str:
    today  = datetime.now().strftime("%d.%m.%Y")
    stats  = db.get_daily_stats()
    review = db.get_pending_review_emails()

    lines = [
        "", "=" * 52,
        f"  E-MAIL TAGES-REPORT  |  {today}",
        "=" * 52, "",
        "ÜBERSICHT", "-" * 30,
        f"  Gesamt empfangen:          {stats.get('total', 0) or 0:>4}",
        f"  Automatisch beantwortet:   {stats.get('auto_sent', 0) or 0:>4}",
        f"  Warten auf Überprüfung:    {stats.get('pending_review', 0) or 0:>4}",
        f"  Manuelle Bearbeitung:      {stats.get('manual', 0) or 0:>4}",
        f"  Gefiltert (Werbung):       {stats.get('filtered', 0) or 0:>4}",
        f"  Abgelehnt:                 {stats.get('rejected', 0) or 0:>4}",
        f"  Fehler:                    {stats.get('errors', 0) or 0:>4}",
        "",
    ]

    if review:
        lines += [f"BITTE ÜBERPRÜFEN ({len(review)} E-Mail(s))", "-" * 52]
        for e in review:
            conf  = e.get("confidence") or 0
            draft = (e.get("draft_reply") or "")[:150].replace("\n", " ")
            lines += [
                "",
                f"  ID {e['id']}: {(e['subject'] or '')[:50]}",
                f"  Von:       {(e['from_address'] or '')[:45]}",
                f"  Konfidenz: {conf:.0%}",
                f"  Entwurf:   {draft} …",
                f"  ▶ /ok{e['id']}  ✗ /nein{e['id']}",
            ]
        lines.append("")

    lines += ["=" * 52, ""]
    return "\n".join(lines)


# ── Genehmigung / Ablehnung ───────────────────────────────────────────────────

def approve_email(email_id: int, edited_body: str = None, send_now: bool = False):
    """Genehmigt Entwurf. Standardmäßig mit Verzögerung (1-3h).
    send_now=True für sofortigen Versand (z.B. urgent)."""
    row = db.get_email_by_id(email_id)
    if not row or row.get("status") not in ("pending_review", "scheduled"):
        print(f"E-Mail {email_id} nicht zur Genehmigung verfügbar.")
        return

    draft   = edited_body or row.get("draft_reply") or ""
    subject = ""
    body    = draft
    if draft.startswith("BETREFF:"):
        parts   = draft.split("\n\n", 1)
        subject = parts[0].replace("BETREFF:", "").strip()
        body    = parts[1].strip() if len(parts) > 1 else ""
    if not subject:
        orig_subj = row.get("subject") or ""
        subject = orig_subj if orig_subj.startswith("Re:") else f"Re: {orig_subj}"

    acc_addr = row.get("account_email") or ""

    # Mit Verzögerung planen (Default) oder sofort senden
    if not send_now:
        send_at = _compute_send_at()
        full_draft = f"BETREFF: {subject}\n\n{body}"
        db.update_email(email_id,
                        status="scheduled",
                        draft_reply=full_draft,
                        sent_reply=body,
                        send_at=send_at)
        db.log_activity("approved_scheduled", email_id, f"send_at={send_at[:16]}")
        when = datetime.fromisoformat(send_at).strftime("%d.%m. %H:%M")
        print(f"✓ E-Mail {email_id} geplant für {when} an {row['from_address']}")
        return

    # Sofort senden
    ec = _email_clients.get(acc_addr) or _email_client
    try:
        ec.send_reply(row["from_address"], subject, body)
        db.update_email(email_id, status="sent", sent_reply=body)

        # Versprechen extrahieren
        _extract_and_save_commitments(email_id, row["from_address"], subject,
                                       body, acc_addr)

        kw = [w for w in (row.get("subject") or "").split() if len(w) > 3][:6]
        db.save_learned_response(row.get("subject", ""), row.get("body", ""),
                                 row.get("category") or "ALLGEMEIN", kw,
                                 subject, body, 1.0, "human")
        try:
            ec.mark_as_read(row["uid"])
        except Exception:
            pass

        db.log_activity("approved", email_id, "human approval (sofort)")
        print(f"✓ E-Mail {email_id} sofort gesendet an {row['from_address']}")
    except Exception as e:
        print(f"✗ Fehler: {e}")
        raise


def reprocess_email(email_id: int):
    """Setzt eine E-Mail zurück und lässt Claude sie erneut verarbeiten."""
    row = db.get_email_by_id(email_id)
    if not row:
        return False
    db.update_email(email_id,
                    status="pending",
                    confidence=None,
                    draft_reply=None,
                    notes=None,
                    processed_at=None)
    db.log_activity("reprocess", email_id, "Manuell ausgelöst")
    # Direkt verarbeiten
    process_email(row)
    # Telegram-Alert für neuen Entwurf
    updated = db.get_email_by_id(email_id)
    if updated and updated.get("status") == "pending_review":
        try:
            import telegram_notify as tg
            msg_id = tg.send_pending_alert(updated)
            if msg_id:
                db.save_tg_map(msg_id, email_id)
        except Exception:
            pass
    return True


def rewrite_draft(email_id: int, hint: str) -> bool:
    """Schreibt den Entwurf mit einem Benutzer-Hinweis neu (ohne Tool-Calls, direkter Claude-Aufruf)."""
    row = db.get_email_by_id(email_id)
    if not row:
        return False

    company  = _config.get("agent", {}).get("company_name", "Levando GmbH")
    original = row.get("body", "")[:2000]
    subject  = row.get("subject", "")
    sender   = row.get("from_address", "")
    old_draft = row.get("draft_reply", "") or ""

    prompt = f"""Du schreibst eine Antwort-E-Mail für {company}.

URSPRÜNGLICHE E-MAIL:
Von: {sender}
Betreff: {subject}
Inhalt: {original}

BISHERIGER ENTWURF:
{old_draft[:1000]}

WICHTIGER HINWEIS VOM BENUTZER:
{hint}

Schreibe eine neue, verbesserte Antwort unter Berücksichtigung des Hinweises.
Antworte auf Deutsch, schreibe wie ein echter Mensch (kein Formular-Deutsch).
Keine Grußformel/Signatur am Ende – wird automatisch ergänzt.
Gib NUR den Antworttext zurück, ohne Einleitung oder Erklärung."""

    response = _client.messages.create(
        model=_config.get("claude", {}).get("model", "claude-haiku-4-5-20251001"),
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    new_draft = response.content[0].text.strip()

    db.update_email(email_id,
                    draft_reply=new_draft,
                    status="pending_review",
                    notes=f"Neu geschrieben mit Hinweis: {hint[:100]}")
    db.log_activity("rewrite", email_id, f"Hinweis: {hint[:100]}")
    return True


def reject_email(email_id: int, reason: str = ""):
    row = db.get_email_by_id(email_id)
    db.update_email(email_id, status="rejected",
                    notes=f"Abgelehnt: {reason}" if reason else "Abgelehnt")
    db.log_activity("rejected", email_id, reason)

    # Lernfeedback speichern – nur wenn Begründung angegeben
    if row and reason and reason.strip():
        db.save_rejection_feedback(
            original_subject=row.get("subject", ""),
            original_body=row.get("body", ""),
            category=row.get("category") or "ALLGEMEIN",
            draft_reply=row.get("draft_reply", ""),
            reason=reason.strip()
        )
        print(f"  → Lernfeedback gespeichert: \"{reason.strip()[:80]}\"")

    print(f"✓ E-Mail {email_id} abgelehnt.")
