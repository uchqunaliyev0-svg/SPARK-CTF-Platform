from flask import g, has_request_context, request

from translations import EN

LANGS = ('uz', 'en')

# Strings the browser scripts need; they are sent to the page in the current language.
JS_KEYS = [
    "Parollar mos kelmadi.", "6 xonali kodni to'liq kiriting.", "Juda zaif", "Zaif", "O'rtacha", "Kuchli",
    "Kamida 8 belgi, harf va raqam.", "Server javobi noto'g'ri.", "Xatolik yuz berdi.", "bepul",
    "Bu hint {cost} ball turadi. Ochishni xohlaysizmi?", "ball", "ta yechim", "muallif:",
    "Hali hech kim yechmagan. Birinchi bo'ling!", "Siz bu masalani yechgansiz!", "Yuklab bo'lmadi.",
    "{solved} / {total} ta masala yechilgan", "Musobaqa yakunlangan — flag qabul qilinmaydi.",
    "Tekshirilmoqda...", "Tasdiqlandi", "Xatolik. Qayta bosing.",
]


def get_lang():
    if not has_request_context():
        return 'uz'
    if 'lang' not in g:
        lang = request.cookies.get('lang')
        g.lang = lang if lang in LANGS else 'uz'
    return g.lang


def _(text, **kw):
    if get_lang() == 'en':
        text = EN.get(text, text)
    return text.format(**kw) if kw else text


def js_strings():
    return {k: _(k) for k in JS_KEYS}
