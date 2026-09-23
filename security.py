import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from flask import abort, current_app, request, session

from i18n import _
from models import CaptchaUse, EmailCode, db, utcnow

USERNAME_RE = re.compile(r'^[A-Za-z0-9_]{3,20}$')
EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$')

_DOMAIN_TYPOS = {
    'gmail.com': ['gmai', 'gmail', 'gmial', 'gmal', 'gmaill', 'gamil', 'gnail', 'gmsil', 'gmali', 'gmai.com',
                  'gmial.com', 'gmal.com', 'gmaill.com', 'gamil.com', 'gnail.com', 'gmsil.com', 'gmali.com',
                  'gmail.co', 'gmail.con', 'gmail.cm', 'gmail.om', 'gmail.comm', 'gmail.cim', 'gmail.ru'],
    'mail.ru': ['mail.r', 'mail.rh', 'mali.ru', 'mial.ru'],
    'yahoo.com': ['yahoo', 'yaho.com', 'yahoo.co', 'yahoo.con', 'yhoo.com'],
    'outlook.com': ['outlook', 'outlok.com', 'outlook.co', 'outlook.con', 'otlook.com'],
    'icloud.com': ['icloud', 'iclod.com', 'icloud.co', 'icloud.con', 'icoud.com'],
}
_TYPO_TO_DOMAIN = {t: d for d, ts in _DOMAIN_TYPOS.items() for t in ts}


def email_suggestion(email):
    """Returns a corrected address for common domain typos (e.g. 'x@gmai' -> 'x@gmail.com'), else None."""
    name, at, domain = (email or '').strip().lower().rpartition('@')
    if not at or not name:
        return None
    fixed = _TYPO_TO_DOMAIN.get(domain)
    return f'{name}@{fixed}' if fixed else None

CODE_TTL = timedelta(minutes=10)
CODE_MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=60)


def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_urlsafe(32)
    return session['_csrf']


def check_csrf():
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    sent = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token', '')
    expected = session.get('_csrf', '')
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, description=_("Xavfsizlik tokeni yaroqsiz. Sahifani yangilab qayta urinib ko'ring."))


def password_problem(pw):
    if len(pw) < 8:
        return _("Parol kamida 8 ta belgidan iborat bo'lishi kerak.")
    if len(pw) > 128:
        return _('Parol juda uzun.')
    if not re.search(r'[A-Za-z]', pw) or not re.search(r'\d', pw):
        return _("Parolda kamida bitta harf va bitta raqam bo'lishi kerak.")
    return None


def _hash_code(code):
    key = current_app.config['SECRET_KEY'].encode()
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def resend_wait_seconds(user, purpose):
    last = (EmailCode.query.filter_by(user_id=user.id, purpose=purpose)
            .order_by(EmailCode.created_at.desc()).first())
    if not last:
        return 0
    left = (last.created_at + RESEND_COOLDOWN) - utcnow()
    return max(int(left.total_seconds()), 0)


def issue_code(user, purpose):
    EmailCode.query.filter_by(user_id=user.id, purpose=purpose, used=False).update({'used': True})
    code = f'{secrets.randbelow(10 ** 6):06d}'
    db.session.add(EmailCode(user_id=user.id, purpose=purpose, code_hash=_hash_code(code),
                             expires_at=utcnow() + CODE_TTL))
    db.session.commit()
    return code


def consume_code(user, purpose, code):
    """Returns None on success, otherwise an error message."""
    rec = (EmailCode.query.filter_by(user_id=user.id, purpose=purpose, used=False)
           .order_by(EmailCode.created_at.desc()).first())
    if not rec or rec.expires_at < utcnow():
        return _("Kod muddati o'tgan. Yangi kod so'rang.")
    if rec.attempts >= CODE_MAX_ATTEMPTS:
        rec.used = True
        db.session.commit()
        return _("Urinishlar soni tugadi. Yangi kod so'rang.")
    code = (code or '').strip()
    if not code.isdigit() or not hmac.compare_digest(_hash_code(code), rec.code_hash):
        rec.attempts += 1
        left = CODE_MAX_ATTEMPTS - rec.attempts
        if left <= 0:
            rec.used = True
        db.session.commit()
        return _("Kod noto'g'ri. Qolgan urinishlar: {left}.", left=max(left, 0))
    rec.used = True
    db.session.commit()
    return None


def client_ip():
    # Vercel sets these itself; a client-supplied X-Forwarded-For is never trusted.
    ip = (request.headers.get('X-Vercel-Forwarded-For') or request.headers.get('X-Real-IP')
          or request.remote_addr or '')
    return ip.split(',')[0].strip()[:64]


CAPTCHA_TTL = timedelta(minutes=5)


def _captcha_sig(salt, exp, bits):
    key = current_app.config['SECRET_KEY'].encode()
    return hmac.new(key, f'captcha|{salt}|{exp}|{bits}'.encode(), hashlib.sha256).hexdigest()


def new_captcha():
    bits = current_app.config.get('CAPTCHA_BITS', 16)
    salt = secrets.token_hex(12)
    exp = int((utcnow() + CAPTCHA_TTL).timestamp())
    return {'salt': salt, 'exp': exp, 'bits': bits, 'sig': _captcha_sig(salt, exp, bits)}


def _leading_zero_bits(digest):
    n = 0
    for byte in digest:
        if byte == 0:
            n += 8
            continue
        n += 8 - byte.bit_length()
        break
    return n


def verify_captcha(token):
    """Token is 'salt:exp:bits:sig:nonce' from the browser's proof-of-work."""
    try:
        salt, exp, bits, sig, nonce = (token or '').split(':')
        exp_i, bits_i = int(exp), int(bits)
    except ValueError:
        return False
    if bits_i < current_app.config.get('CAPTCHA_BITS', 16) or len(nonce) > 20:
        return False
    if not hmac.compare_digest(sig, _captcha_sig(salt, exp_i, bits_i)):
        return False
    now = utcnow()
    if exp_i < int(now.timestamp()):
        return False
    if _leading_zero_bits(hashlib.sha256(f'{salt}{nonce}'.encode()).digest()) < bits_i:
        return False
    if db.session.get(CaptchaUse, sig):
        return False
    CaptchaUse.query.filter(CaptchaUse.expires_at < now).delete()
    db.session.add(CaptchaUse(sig=sig, expires_at=now + CAPTCHA_TTL))
    db.session.commit()
    return True


def code_fingerprint(code):
    """Keyed fingerprint of a code, safe to put in a link (does not reveal the code)."""
    return _hash_code(code)[:24]


def consume_code_link(user, purpose, fingerprint):
    """Like consume_code, but for a signed link that carries only the code fingerprint."""
    rec = (EmailCode.query.filter_by(user_id=user.id, purpose=purpose, used=False)
           .order_by(EmailCode.created_at.desc()).first())
    if not rec or rec.expires_at < utcnow() or rec.attempts >= CODE_MAX_ATTEMPTS:
        return _("Kod muddati o'tgan. Yangi kod so'rang.")
    if not hmac.compare_digest(rec.code_hash[:24], str(fingerprint or '')):
        return _("Kod muddati o'tgan. Yangi kod so'rang.")
    rec.used = True
    db.session.commit()
    return None
