"""IMAP/SMTP-Client für All-Inkl und kompatible Hoster."""
import imaplib
import smtplib
import email
import html
import re
import ssl
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


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


def build_html_email(body: str, signature: str, from_email: str) -> str:
    """Modernes mobile-first responsives Email-Template mit Levando-Branding."""
    body_html = _linkify(_escape_html(body)).replace("\n", "<br>\n")

    # Signatur splitten am '--' Trenner
    sig = signature.strip()
    sig_top, sig_bottom = sig, ""
    if "--" in sig:
        parts = sig.split("--", 1)
        sig_top    = parts[0].strip()
        sig_bottom = parts[1].strip()

    sig_top_html    = _linkify(_escape_html(sig_top)).replace("\n", "<br>\n")
    sig_bottom_html = _linkify(_escape_html(sig_bottom)).replace("\n", "<br>\n")

    # Logos vom GitHub-Repo (immer aktuell, kein Caching-Problem)
    levando_logo = "https://raw.githubusercontent.com/saunafreunde/App2/main/levando-Logo.png"
    aromen_logo  = "https://raw.githubusercontent.com/saunafreunde/App2/main/aromen123-logo.png"

    # Markenfarben
    DARK   = "#2d3340"   # Anthrazit aus Levando-Logo
    ORANGE = "#f08020"   # Orange aus Levando-Logo
    GREEN  = "#2d5a3f"   # Grün aus Aromen-Logo
    LIGHT  = "#f5f6fa"

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "https://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="de">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="format-detection" content="telephone=no,address=no,email=no,date=no,url=no">
<title>Levando GmbH</title>
<!--[if mso]>
<style type="text/css">
table, td, div, h1, p {{font-family: Arial, sans-serif !important;}}
</style>
<![endif]-->
<style type="text/css">
  body, table, td {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
  img {{ -ms-interpolation-mode:bicubic; border:0; outline:none; text-decoration:none; }}
  a {{ text-decoration:none; }}

  /* Mobile-First Responsive */
  @media screen and (max-width: 600px) {{
    .container {{ width:100% !important; max-width:100% !important; }}
    .px {{ padding-left:22px !important; padding-right:22px !important; }}
    .py-hero {{ padding-top:28px !important; padding-bottom:28px !important; }}
    .hero-logo {{ width:80px !important; height:auto !important; }}
    .body-text {{ font-size:15px !important; line-height:1.65 !important; }}
    .shop-cell {{ display:block !important; width:100% !important; padding:8px 0 !important; }}
    .shop-btn {{ width:100% !important; padding:22px 18px !important; }}
    .shop-logo-aromen  {{ height:60px !important; width:auto !important; max-width:100px !important; }}
    .shop-logo-levando {{ height:60px !important; width:auto !important; max-width:100px !important; }}
    .footer-text {{ font-size:11px !important; }}
    .card {{ border-radius:12px !important; }}
    .body-padding {{ padding:30px 22px 4px !important; }}
    .sig-padding {{ padding:6px 22px 22px !important; }}
    .shop-padding {{ padding:0 22px 22px !important; }}
    .footer-padding {{ padding:20px 22px 24px !important; }}
    .shops-title {{ font-size:13px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{LIGHT};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{DARK};line-height:1.6;-webkit-font-smoothing:antialiased;">

<!-- Preheader -->
<div style="display:none;max-height:0;overflow:hidden;font-size:1px;line-height:1px;color:{LIGHT};opacity:0;">
Ihre persönliche Nachricht von Levando GmbH
</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{LIGHT};">
<tr><td align="center" style="padding:24px 12px;">

  <!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
  <table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e8eaf0;">

    <!-- Header mit zentriertem Levando-Hexagon-Logo -->
    <tr>
      <td class="py-hero" style="background:#ffffff;padding:36px 36px 28px;text-align:center;" align="center">
        <img src="{levando_logo}" alt="Levando GmbH" width="100" height="auto" class="hero-logo" style="display:inline-block;width:100px;max-width:100px;height:auto;border:0;">
        <div style="margin-top:14px;font-size:11px;letter-spacing:3px;text-transform:uppercase;font-weight:600;color:#8a8f9e;">
          Qualität aus Meisterhand
        </div>
      </td>
    </tr>

    <!-- Orange Akzent-Streifen -->
    <tr>
      <td style="height:3px;background:{ORANGE};font-size:0;line-height:0;mso-line-height-rule:exactly;">&nbsp;</td>
    </tr>

    <!-- Body -->
    <tr>
      <td class="body-padding px body-text" style="padding:30px 36px 4px;font-size:15.5px;color:{DARK};line-height:1.7;">
        {body_html}
      </td>
    </tr>

    <!-- Grußformel -->
    <tr>
      <td class="sig-padding px body-text" style="padding:6px 36px 24px;font-size:15.5px;color:{DARK};line-height:1.6;">
        {sig_top_html}
      </td>
    </tr>

    <!-- Shops-Sektion -->
    <tr>
      <td class="shop-padding px" style="padding:8px 36px 32px;">
        <div class="shops-title" style="font-size:11px;letter-spacing:2.5px;text-transform:uppercase;font-weight:700;color:#8a8f9e;text-align:center;margin-bottom:14px;">
          Unsere Shops
        </div>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <!-- radschrauben123.de – Anthrazit/Orange -->
            <td class="shop-cell" width="50%" valign="top" style="padding:0 6px 0 0;">
              <a href="https://www.radschrauben123.de" target="_blank" class="shop-btn"
                 style="display:block;background:{DARK};border-radius:14px;text-decoration:none;overflow:hidden;">
                <!-- Logo-Bereich mit hellem Streifen -->
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                  <tr>
                    <td align="center" style="background:#ffffff;padding:14px 12px 10px;border-radius:12px 12px 0 0;">
                      <img src="{levando_logo}" alt="Levando" height="68" class="shop-logo-levando"
                           style="display:inline-block;height:68px;width:auto;max-width:110px;border:0;outline:none;">
                    </td>
                  </tr>
                  <!-- Orange Trennlinie -->
                  <tr>
                    <td style="height:3px;background:{ORANGE};font-size:0;line-height:0;">&nbsp;</td>
                  </tr>
                  <!-- Text auf dunklem Hintergrund -->
                  <tr>
                    <td align="center" style="padding:12px 10px 14px;">
                      <div style="font-size:13.5px;font-weight:700;color:#ffffff;letter-spacing:.3px;">radschrauben123.de</div>
                      <div style="font-size:9.5px;color:{ORANGE};margin-top:4px;font-weight:600;text-transform:uppercase;letter-spacing:1.2px;">Radschrauben &amp; Werkzeug</div>
                    </td>
                  </tr>
                </table>
              </a>
            </td>
            <!-- aromen123.de – Grün/Natur -->
            <td class="shop-cell" width="50%" valign="top" style="padding:0 0 0 6px;">
              <a href="https://www.aromen123.de" target="_blank" class="shop-btn"
                 style="display:block;background:{GREEN};border-radius:14px;text-decoration:none;overflow:hidden;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                  <tr>
                    <td align="center" style="background:#ffffff;padding:14px 12px 10px;border-radius:12px 12px 0 0;">
                      <img src="{aromen_logo}" alt="Aromen123" height="68" class="shop-logo-aromen"
                           style="display:inline-block;height:68px;width:auto;max-width:110px;border:0;outline:none;">
                    </td>
                  </tr>
                  <!-- Grüne Trennlinie -->
                  <tr>
                    <td style="height:3px;background:#4a8c5c;font-size:0;line-height:0;">&nbsp;</td>
                  </tr>
                  <!-- Text auf grünem Hintergrund -->
                  <tr>
                    <td align="center" style="padding:12px 10px 14px;">
                      <div style="font-size:13.5px;font-weight:700;color:#ffffff;letter-spacing:.3px;">aromen123.de</div>
                      <div style="font-size:9.5px;color:#b8e0c5;margin-top:4px;font-weight:600;text-transform:uppercase;letter-spacing:1.2px;">Natürliche Aromen</div>
                    </td>
                  </tr>
                </table>
              </a>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Footer mit Firmenangaben -->
    {f'''<tr>
      <td class="footer-padding px footer-text" style="padding:22px 36px 28px;background:#fafbfd;border-top:1px solid #e8eaf0;font-size:12px;color:#5a6478;line-height:1.7;">
        {sig_bottom_html}
      </td>
    </tr>''' if sig_bottom_html else ''}

  </table>
  <!--[if mso]></td></tr></table><![endif]-->

  <!-- Mini-Footer unter Card -->
  <table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;margin-top:14px;">
    <tr><td align="center" class="footer-text" style="font-size:11px;color:#9aa0a6;line-height:1.7;padding:0 20px;">
      Gesendet von <a href="mailto:{_escape_html(from_email)}" style="color:#5a6478;text-decoration:none;">{_escape_html(from_email)}</a> · <a href="https://www.levando.gmbh" style="color:#5a6478;text-decoration:none;">levando.gmbh</a>
    </td></tr>
  </table>

</td></tr>
</table>
</body>
</html>"""


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
