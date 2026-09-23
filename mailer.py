import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from html import escape

from i18n import _

SUBJECTS = {
    'verify': 'SPARK CTF — emailni tasdiqlash kodi',
    'reset': 'SPARK CTF — parolni tiklash kodi',
}
HEADINGS = {
    'verify': 'Emailingizni tasdiqlang',
    'reset': 'Parolni tiklash',
}
INTROS = {
    'verify': "SPARK CTF ga xush kelibsiz! Hisobingizni faollashtirish uchun quyidagi tugmani bosing yoki saytdagi maydonga kodni kiriting:",
    'reset': 'Parolni tiklash uchun quyidagi kodni kiriting:',
}
BUTTONS = {
    'verify': 'Emailni tasdiqlash',
    'reset': 'Parolni tiklash',
}
TAGLINE = 'Capture The Flag platformasi'
NOTE = "Kod 10 daqiqa amal qiladi. Agar bu so'rovni siz yubormagan bo'lsangiz, xatni e'tiborsiz qoldiring — hech kimga kodni bermang."
FALLBACK = "Tugma ishlamasa, quyidagi havolani brauzerga nusxalang:"
last_error = ''
FOOTER = "Bu xat SPARK CTF platformasida ro'yxatdan o'tganingiz sababli yuborildi."


def mail_enabled():
    return bool(os.getenv('SMTP_USER') and os.getenv('SMTP_PASSWORD'))


def _html(username, purpose, code, link):
    intro = _(INTROS[purpose])
    heading = _(HEADINGS[purpose])
    button = ''
    if link:
        safe = escape(link, quote=True)
        button = f"""
<tr><td align="center" style="padding:6px 0 26px;">
<a href="{safe}" style="display:inline-block;background:#22d3ee;color:#04111a;font-size:16px;font-weight:bold;text-decoration:none;padding:15px 40px;border-radius:12px;letter-spacing:.3px;">{_(BUTTONS[purpose])} &rarr;</a>
</td></tr>
<tr><td style="color:#7d8aa5;font-size:12px;line-height:1.6;padding-bottom:22px;">{_(FALLBACK)}<br>
<a href="{safe}" style="color:#22d3ee;word-break:break-all;">{safe}</a></td></tr>"""
    return f"""<!doctype html><html><body style="margin:0;padding:0;background:#060913;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#060913;padding:40px 16px;"><tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;">
<tr><td align="center" style="padding-bottom:22px;">
<table cellpadding="0" cellspacing="0"><tr>
<td style="width:44px;height:44px;background:#22d3ee;border-radius:12px;text-align:center;vertical-align:middle;font-size:24px;font-weight:bold;color:#04111a;">S</td>
<td style="padding-left:12px;text-align:left;">
<div style="font-size:20px;font-weight:bold;letter-spacing:1px;line-height:1.1;"><span style="color:#22d3ee;">SPARK</span> <span style="color:#ff3b5c;">CTF</span></div>
<div style="color:#7d8aa5;font-size:12px;letter-spacing:.5px;">{_(TAGLINE)}</div></td>
</tr></table></td></tr>
<tr><td style="background:#0c1222;border:1px solid #1e2a44;border-radius:18px;padding:36px 32px;">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td style="color:#fff;font-size:24px;font-weight:bold;line-height:1.25;">{heading}</td></tr>
<tr><td style="color:#c7d2e6;font-size:15px;padding-top:16px;line-height:1.65;">{_('Salom')}, <b style="color:#fff;">{escape(username)}</b>!<br>{intro}</td></tr>
<tr><td align="center" style="padding:26px 0;">
<div style="font-family:'Courier New',monospace;font-size:36px;font-weight:bold;letter-spacing:10px;color:#fff;background:#111a30;border:1px solid #22d3ee55;border-radius:12px;padding:16px 24px;display:inline-block;">{code}</div></td></tr>
{button}
<tr><td style="border-top:1px solid #1e2a44;padding-top:18px;color:#7d8aa5;font-size:13px;line-height:1.6;">{_(NOTE)}</td></tr>
</table></td></tr>
<tr><td align="center" style="color:#4b5673;font-size:11px;padding-top:20px;line-height:1.6;">{_(FOOTER)}<br>&copy; SPARK CTF</td></tr>
</table></td></tr></table></body></html>"""


def _smtp_settings():
    host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    port = int(os.getenv('SMTP_PORT', '587'))
    user = (os.getenv('SMTP_USER') or '').strip()
    password = (os.getenv('SMTP_PASSWORD') or '').replace(' ', '').strip()
    return host, port, user, password


def _deliver(msg):
    """Hands the message to the SMTP server; raises on any failure."""
    host, port, user, password = _smtp_settings()
    msg['From'] = os.getenv('MAIL_FROM') or f"SPARK CTF <{user}>"
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            s.login(user, password)
            s.send_message(msg)


def describe_error(e):
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return ("Gmail loginni rad etdi (535). App Password aynan SMTP_USER dagi Gmail hisobida yaratilgan "
                "bo'lishi kerak va 2-bosqichli tekshiruv yoqilgan bo'lishi shart.")
    if isinstance(e, (smtplib.SMTPConnectError, TimeoutError, OSError)) and not isinstance(e, smtplib.SMTPException):
        return f'SMTP serverga ulanib bo\'lmadi ({type(e).__name__}: {e}).'
    return f'{type(e).__name__}: {e}'


def send_test(to_email):
    """Sends a plain test email. Returns None on success, otherwise an error string."""
    if not mail_enabled():
        return 'SMTP_USER yoki SMTP_PASSWORD o\'rnatilmagan.'
    msg = EmailMessage()
    msg['Subject'] = 'SPARK CTF — test xat'
    msg['To'] = to_email
    msg.set_content('SPARK CTF email sozlamalari to\'g\'ri ishlayapti.')
    try:
        _deliver(msg)
        return None
    except Exception as e:
        print(f'[mail error] test -> {to_email}: {e!r}', file=sys.stderr)
        return describe_error(e)


def send_code(to_email, username, purpose, code, link=None):
    """Returns True if the email was handed to the SMTP server."""
    if not mail_enabled():
        print(f'[mail disabled] {purpose} code for {to_email}: {code}' + (f' link: {link}' if link else ''))
        return False
    msg = EmailMessage()
    intro = _(INTROS[purpose])
    msg['Subject'] = _(SUBJECTS[purpose])
    msg['To'] = to_email
    text = f"{_(HEADINGS[purpose])}\n\n{_('Salom')}, {username}!\n{intro}\n\n{code}\n"
    if link:
        text += f"\n{_(BUTTONS[purpose])}: {link}\n"
    text += f"\n{_(NOTE)}"
    msg.set_content(text)
    msg.add_alternative(_html(username, purpose, code, link), subtype='html')
    global last_error
    try:
        _deliver(msg)
        last_error = ''
        return True
    except Exception as e:
        last_error = describe_error(e)
        print(f'[mail error] {purpose} -> {to_email}: {e!r}', file=sys.stderr)
        return False
