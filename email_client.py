"""IMAP/SMTP-Client für All-Inkl und kompatible Hoster."""
import imaplib
import smtplib
import email
import html
import re
import ssl
import os
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from jinja2 import Environment, FileSystemLoader


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def decode_str(value) -> str:
    """Decodiert E-Mail-Header-Strings (MIME-encoded, UTF-8, latin-1 …)."""
    if not value:
        return ""
    parts = decode_header(str(value))
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def html_to_text(html_content: str) -> str:
    """Einfache HTML → Text-Konvertierung."""
    html_content = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.I)
    html_content = re.sub(r"<style[^>]*>.*?</style>",  "", html_content, flags=re.DOTALL | re.I)
    html_content = re.sub(r"<br\s*/?>",  "\n",  html_content, flags=re.I)
    html_content = re.sub(r"<p[^>]*>",   "\n",  html_content, flags=re.I)
    html_content = re.sub(r"<li[^>]*>",  "\n- ", html_content, flags=re.I)
    html_content = re.sub(r"<[^>]+>",    " ",   html_content)
    html_content = html.unescape(html_content)
    html_content = re.sub(r"\n{3,}", "\n\n", html_content)
    return html_content.strip()


def _escape_html(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _linkify(text: str) -> str:
    """E-Mails und URLs in <a>-Tags umwandeln."""
    # E-Mails
    text = re.sub(
        r"([\w\.\-_+]+@[\w\.\-_]+\.[a-zA-Z]{2,})",
        r'<a href="mailto:\1" style="color:#0d6efd;text-decoration:none;">\1</a>',
        text
    )
    # Webseiten (http/https/www.)
    text = re.sub(
        r"(?<![\">])(https?://[^\s<]+|www\.[\w\.\-/\?=#&]+)",
        lambda m: f'<a href="{m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)}" style="color:#0d6efd;text-decoration:none;">{m.group(0)}</a>',
        text
    )
    return text


_jinja_env = Environment(
    loader=FileSystemLoader(os.path.dirname(os.path.abspath(__file__))),
    autoescape=False,
)


def build_html_email(body: str, signature: str, from_email: str) -> str:
    """Modernes mobile-first responsives Email-Template mit Levando-Branding."""
    body_html = _linkify(_escape_html(body)).replace("\n", "<br>\n")

    sig = signature.strip()
    sig_top, sig_bottom = sig, ""
    if "--" in sig:
        parts = sig.split("--", 1)
        sig_top    = parts[0].strip()
        sig_bottom = parts[1].strip()

    sig_top_html    = _linkify(_escape_html(sig_top)).replace("\n", "<br>\n")
    sig_bottom_html = _linkify(_escape_html(sig_bottom)).replace("\n", "<br>\n")

    template = _jinja_env.get_template("email_template.html")
    return template.render(
        body_html=body_html,
        sig_top_html=sig_top_html,
        sig_bottom_html=sig_bottom_html,
        from_email=_escape_html(from_email),
    )


def get_email_body(msg: email.message.Message, max_chars: int = 2000) -> str:
    """Extrahiert den Text-Body aus einer E-Mail (bevorzugt plain text)."""
    plain = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct  = part.get_content_type()
            cd  = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            text = payload.decode(charset, errors="replace")
            if ct == "text/plain" and not plain:
                plain = text
            elif ct == "text/html" and not html_body:
                html_body = text
    else:
        ct      = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            text = payload.decode(charset, errors="replace")
            if ct == "text/html":
                html_body = text
            else:
                plain = text

    body = plain or html_to_text(html_body)
    return body[:max_chars]


# ── EmailClient ───────────────────────────────────────────────────────────────

class EmailClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    # ── IMAP ──────────────────────────────────────────────────────────────────

    def fetch_new_emails(self, folder: str = "INBOX", max_emails: int = 50) -> list[dict]:
        """Holt ungelesene E-Mails vom IMAP-Server."""
        result = []
        ctx = ssl.create_default_context()

        with imaplib.IMAP4_SSL(
            self.cfg["imap_server"], self.cfg["imap_port"], ssl_context=ctx
        ) as imap:
            imap.login(self.cfg["email"], self.cfg["password"])
            imap.select(folder)

            _, data = imap.search(None, "UNSEEN")
            if not data or not data[0]:
                return result

            uids = data[0].split()
            # Nur die letzten N, älteste zuerst
            for uid in uids[-max_emails:]:
                try:
                    _, raw = imap.fetch(uid, "(RFC822)")
                    msg = email.message_from_bytes(raw[0][1])

                    from_addr  = decode_str(msg.get("From", ""))
                    subject    = decode_str(msg.get("Subject", "(Kein Betreff)"))
                    date_str   = msg.get("Date", "")
                    message_id = msg.get("Message-ID", "")
                    body       = get_email_body(msg)

                    try:
                        received_at = email.utils.parsedate_to_datetime(date_str).isoformat()
                    except Exception:
                        received_at = datetime.now().isoformat()

                    result.append({
                        "uid":         uid.decode(),
                        "from":        from_addr,
                        "subject":     subject,
                        "body":        body,
                        "received_at": received_at,
                        "message_id":  message_id,
                    })
                except Exception as e:
                    print(f"    Warnung: E-Mail {uid} übersprungen ({e})")

        return result

    def mark_as_read(self, uid: str, folder: str = "INBOX"):
        """Markiert eine E-Mail als gelesen."""
        ctx = ssl.create_default_context()
        with imaplib.IMAP4_SSL(
            self.cfg["imap_server"], self.cfg["imap_port"], ssl_context=ctx
        ) as imap:
            imap.login(self.cfg["email"], self.cfg["password"])
            imap.select(folder)
            imap.store(uid.encode(), "+FLAGS", "\\Seen")

    # ── SMTP ──────────────────────────────────────────────────────────────────

    def send_reply(self, to_address: str, subject: str, body: str,
                   in_reply_to: str = None) -> bool:
        """Sendet eine E-Mail per SMTP – multipart HTML + Plaintext."""
        signature = self.cfg.get("signature", "")
        full_text = body + (("\n" + signature) if signature else "")
        full_html = build_html_email(body, signature, self.cfg.get("email", ""))

        msg = MIMEMultipart("alternative")
        msg["From"]    = self.cfg["email"]
        msg["To"]      = to_address
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"]  = in_reply_to

        # Plaintext zuerst, HTML danach (Mail-Clients zeigen das letzte das sie können)
        msg.attach(MIMEText(full_text, "plain", "utf-8"))
        msg.attach(MIMEText(full_html, "html",  "utf-8"))

        use_ssl = self.cfg.get("smtp_ssl", True)
        server  = self.cfg["smtp_server"]
        port    = self.cfg["smtp_port"]
        user    = self.cfg["email"]
        pw      = self.cfg["password"]

        if use_ssl:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(server, port, context=ctx) as smtp:
                smtp.login(user, pw)
                smtp.sendmail(user, to_address, msg.as_string())
        else:
            with smtplib.SMTP(server, port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(user, pw)
                smtp.sendmail(user, to_address, msg.as_string())

        return True
