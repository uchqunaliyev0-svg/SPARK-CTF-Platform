import os
import smtplib
import ssl
from email.message import EmailMessage
from html import escape

SUBJECTS = {
    'verify': 'SPARK CTF — emailni tasdiqlash kodi',
    'reset': 'SPARK CTF — parolni tiklash kodi',
}
INTROS = {
    'verify': "Ro'yxatdan o'tishni yakunlash uchun quyidagi kodni kiriting:",
    'reset': 'Parolni tiklash uchun quyidagi kodni kiriting:',
}


def mail_enabled():
    return bool(os.getenv('SMTP_USER') and os.getenv('SMTP_PASSWORD'))


def _html(username, intro, code):
    return f"""<!doctype html><html><body style="margin:0;background:#060913;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 16px;"><tr><td align="center">
<table width="440" cellpadding="0" cellspacing="0" style="max-width:440px;background:#0c1222;border:1px solid #1e2a44;border-radius:16px;padding:36px;">
<tr><td style="font-size:22px;font-weight:bold;letter-spacing:1px;">
<span style="color:#22d3ee;">SPARK</span> <span style="color:#ff3b5c;">CTF</span></td></tr>
<tr><td style="color:#c7d2e6;font-size:15px;padding-top:20px;line-height:1.6;">Salom, <b style="color:#fff;">{escape(username)}</b>!<br>{intro}</td></tr>
<tr><td align="center" style="padding:28px 0;">
<div style="font-family:'Courier New',monospace;font-size:34px;font-weight:bold;letter-spacing:10px;color:#fff;background:#111a30;border:1px solid #22d3ee55;border-radius:12px;padding:16px 24px;display:inline-block;">{code}</div></td></tr>
<tr><td style="color:#7d8aa5;font-size:13px;line-height:1.6;">Kod 10 daqiqa amal qiladi. Agar bu so'rovni siz yubormagan bo'lsangiz, xatni e'tiborsiz qoldiring — hech kimga kodni bermang.</td></tr>
</table></td></tr></table></body></html>"""


def send_code(to_email, username, purpose, code):
    """Returns True if the email was handed to the SMTP server."""
    if not mail_enabled():
        print(f'[mail disabled] {purpose} code for {to_email}: {code}')
        return False
    msg = EmailMessage()
    msg['Subject'] = SUBJECTS[purpose]
    msg['From'] = os.getenv('MAIL_FROM') or f"SPARK CTF <{os.getenv('SMTP_USER')}>"
    msg['To'] = to_email
    msg.set_content(f'Salom, {username}!\n{INTROS[purpose]}\n\n{code}\n\nKod 10 daqiqa amal qiladi.')
    msg.add_alternative(_html(username, INTROS[purpose], code), subtype='html')
    host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    port = int(os.getenv('SMTP_PORT', '587'))
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=10) as s:
                s.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
                s.send_message(msg)
        return True
    except Exception as e:
        print(f'[mail error] {e}')
        return False
