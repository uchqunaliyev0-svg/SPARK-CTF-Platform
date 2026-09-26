"""Google OAuth 2.0 and Telegram Login, without extra dependencies.

Both providers are optional: a provider is offered on the login page only when its
environment variables are set (see google_enabled / telegram_enabled).

Google:   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET  (redirect URI: <site>/auth/google/callback)
Telegram: TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME (set the site domain with /setdomain in BotFather)
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.parse
import urllib.request

GOOGLE_AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO = 'https://openidconnect.googleapis.com/v1/userinfo'
TELEGRAM_AUTH_TTL = 300  # seconds a Telegram login payload stays valid


class SocialError(Exception):
    pass


def google_enabled():
    return bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET'))


def telegram_enabled():
    return bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_BOT_USERNAME'))


def telegram_bot_id():
    """The numeric bot id is the public part of the token (before the colon)."""
    return (os.getenv('TELEGRAM_BOT_TOKEN') or '').split(':')[0]


def telegram_bot_username():
    return (os.getenv('TELEGRAM_BOT_USERNAME') or '').lstrip('@')


def google_auth_url(redirect_uri, state):
    params = {
        'client_id': os.getenv('GOOGLE_CLIENT_ID'),
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    }
    return f'{GOOGLE_AUTH}?{urllib.parse.urlencode(params)}'


def _post_json(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _get_json(url, token):
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def google_profile(code, redirect_uri):
    """Exchanges the OAuth code and returns {'id', 'email', 'name'} for a verified Google email."""
    try:
        tokens = _post_json(GOOGLE_TOKEN, {
            'code': code,
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        })
        info = _get_json(GOOGLE_USERINFO, tokens['access_token'])
    except Exception as e:  # network / provider errors are all "try again"
        raise SocialError(f'google: {e!r}')
    if not info.get('sub') or not info.get('email') or not info.get('email_verified'):
        raise SocialError('google: email not verified')
    return {'id': str(info['sub']), 'email': info['email'].lower(),
            'name': info.get('given_name') or info.get('name') or ''}


def telegram_profile(args):
    """Verifies the Telegram Login Widget payload (HMAC over the sorted fields) and returns
    {'id', 'username', 'name'}."""
    data = {k: v for k, v in args.items() if k != 'hash' and v is not None}
    received = args.get('hash') or ''
    check = '\n'.join(f'{k}={data[k]}' for k in sorted(data))
    secret = hashlib.sha256(os.getenv('TELEGRAM_BOT_TOKEN', '').encode()).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not received or not hmac.compare_digest(received, expected):
        raise SocialError('telegram: bad signature')
    try:
        if time.time() - int(data.get('auth_date', 0)) > TELEGRAM_AUTH_TTL:
            raise SocialError('telegram: payload expired')
    except ValueError:
        raise SocialError('telegram: bad auth_date')
    if not data.get('id'):
        raise SocialError('telegram: no id')
    return {'id': str(data['id']), 'username': data.get('username') or '',
            'name': data.get('first_name') or ''}


_CLEAN = re.compile(r'[^A-Za-z0-9_]')


def suggest_username(*candidates):
    """First candidate that can be turned into a valid username, else a random one."""
    for c in candidates:
        base = _CLEAN.sub('', (c or '').split('@')[0])[:20]
        if len(base) >= 3:
            return base
    return f'user_{secrets.token_hex(3)}'
