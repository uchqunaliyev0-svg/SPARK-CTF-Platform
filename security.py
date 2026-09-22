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
    fwd = request.headers.get('X-Forwarded-For', '')
    return (fwd.split(',')[0].strip() if fwd else request.remote_addr or '')[:64]


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
