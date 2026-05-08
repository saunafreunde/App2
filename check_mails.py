"""Zeigt die letzten 10 E-Mails (gelesen + ungelesen) von info@levando.gmbh"""
import sys, json, imaplib, email
from email.header import decode_header
from datetime import datetime

# UTF-8 fuer Windows-Terminal erzwingen
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, '.')

try:
    from config_loader import load_config
    cfg = load_config()
except ImportError:
    with open('config.json', encoding='utf-8') as f:
        cfg = json.load(f)

acc = next(a for a in cfg['accounts'] if a['email'] == 'info@levando.gmbh')

print(f"\nVerbinde mit {acc['imap_server']}:{acc['imap_port']} ...")
imap = imaplib.IMAP4_SSL(acc['imap_server'], acc['imap_port'])
imap.login(acc['email'], acc['password'])
imap.select('INBOX')

# Alle E-Mails (nicht nur ungelesene), neueste zuerst
status, data = imap.search(None, 'ALL')
ids = data[0].split()
last10 = ids[-10:] if len(ids) >= 10 else ids
last10 = list(reversed(last10))  # neueste zuerst

print(f"Posteingang gesamt: {len(ids)} E-Mails")
print(f"Zeige letzte {len(last10)}:\n")
print(f"{'#':<4} {'Datum':<18} {'Von':<38} {'Betreff'}")
print("-" * 100)

for i, uid in enumerate(last10, 1):
    status, msg_data = imap.fetch(uid, '(RFC822.HEADER FLAGS)')
    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)

    # Betreff dekodieren
    subj_raw = msg.get('Subject', '')
    parts = decode_header(subj_raw)
    subj = ''
    for part, enc in parts:
        if isinstance(part, bytes):
            subj += part.decode(enc or 'utf-8', errors='replace')
        else:
            subj += str(part)

    # Absender dekodieren
    from_raw = msg.get('From', '')
    from_parts = decode_header(from_raw)
    sender = ''
    for part, enc in from_parts:
        if isinstance(part, bytes):
            sender += part.decode(enc or 'utf-8', errors='replace')
        else:
            sender += str(part)

    # Datum
    date_str = msg.get('Date', '')[:25]

    # Gelesen/Ungelesen Flag
    flags_data = msg_data[0][1] if len(msg_data[0]) > 1 else b''
    status2, flag_data = imap.fetch(uid, '(FLAGS)')
    flags_raw = flag_data[0].decode() if flag_data[0] else ''
    flag_str = '[NEU]' if '\\Seen' not in flags_raw else '     '

    print(f"{i:<4} {date_str[:17]:<18} {sender[:37]:<38} {flag_str} {subj[:55]}")

imap.logout()
print()
