"""Posts platform news (new challenge, competition, announcement) to a Telegram channel.

Needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID (e.g. @spark_ctf or -100123...). The bot must be
an admin of that channel. Everything here is best-effort: a Telegram outage never breaks an
admin action, it only gets logged.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from html import escape


def channel_enabled():
    return bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHANNEL_ID'))


def _site_url(path=''):
    base = (os.getenv('SITE_URL') or '').rstrip('/')
    return f'{base}{path}' if base else ''


def post(html_text, link_path=None, link_label='Ochish'):
    """Sends one HTML-formatted message. Returns True on success."""
    if not channel_enabled():
        return False
    url = _site_url(link_path) if link_path else ''
    if url:
        html_text += f'\n\n<a href="{escape(url, quote=True)}">{escape(link_label)} →</a>'
    data = urllib.parse.urlencode({
        'chat_id': os.getenv('TELEGRAM_CHANNEL_ID'),
        'text': html_text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': 'true',
    }).encode()
    api = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage"
    try:
        with urllib.request.urlopen(urllib.request.Request(api, data=data), timeout=6) as resp:
            return bool(json.loads(resp.read().decode()).get('ok'))
    except Exception as e:
        print(f'[notify] telegram channel post failed: {e!r}', file=sys.stderr)
        return False


def new_challenge(ch):
    return post(f'🚩 <b>Yangi masala: {escape(ch.title)}</b>\n'
                f'{escape(ch.category)} · {escape(ch.difficulty)} · {ch.value} ball',
                f'/challenges#c-{ch.id}', 'Yechish')


def new_competition(event):
    prize = f'\n🎁 Sovrin: {escape(event.prize)}' if event.prize else ''
    return post(f'🏆 <b>{escape(event.title)}</b>\n'
                f'Boshlanish: {event.starts_at.strftime("%Y-%m-%d %H:%M")} UTC{prize}',
                f'/competitions/{event.id}', "Ro'yxatdan o'tish")


def announcement(title, content):
    return post(f'📣 <b>{escape(title)}</b>\n{escape(content)}', '/notifications', 'Batafsil')
