# SPARK CTF

Doimiy mashq (practice) masalalari va vaqti-vaqti bilan o'tkaziladigan rasmiy musobaqalar platformasi.

- **Practice** — masalalar bo'limlarga (Web, Crypto, Pwn ...) ajratilgan, ball doimiy. Hint avval umumiy
  baldan, yetmasa shu masala balidan yechiladi.
- **Musobaqa** — alohida reyting va ballar (umumiy reytingga qo'shilmaydi), first blood, top-3 uchun
  tekshiriladigan sertifikat. Tugagach masalalar practice'ga ochiladi.

## Ishga tushirish

```bash
pip install -r requirements.txt
FLASK_APP=app.py flask run          # SQLite: /tmp/spark_ctf.db
python -m unittest discover -s tests
```

Asosiy o'zgaruvchilar: `SECRET_KEY`, `DATABASE_URL`, `ADMIN_EMAIL` (+ ixtiyoriy `ADMIN_USERNAME`),
email uchun `SMTP_USER` / `SMTP_PASSWORD`.

## Integratsiyalar

Har biri ixtiyoriy: o'zgaruvchilar qo'yilmasa, tegishli tugma yoki funksiya ko'rinmaydi.
Holatini admin panelning bosh sahifasidan ko'rish mumkin.

### Google orqali kirish
1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → *OAuth client ID* → *Web application*.
2. *Authorized redirect URI*: `https://<sayt>/auth/google/callback`
3. `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`

Google tasdiqlagan email mavjud hisobga to'g'ri kelsa, o'sha hisobga ulanadi.

### Telegram orqali kirish
1. [@BotFather](https://t.me/BotFather) → `/newbot`, keyin `/setdomain` → saytingiz domeni.
2. `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`

Telegram email bermaydi: bunday hisoblar `...@users.noreply.spark` ko'rinishidagi ichki manzil bilan
yaratiladi. Foydalanuvchi keyin *Sozlamalar*da Google'ni ham ulashi mumkin.

### Telegram kanalga e'lonlar
Yangi masala ko'rinadigan bo'lganda, musobaqa e'lon qilinganda va admin e'lon joylaganda (belgilansa)
kanalga xabar yuboriladi.
1. Botni kanalga **admin** qilib qo'shing.
2. `TELEGRAM_CHANNEL_ID` (`@kanal_nomi` yoki `-100...`), `SITE_URL` (`https://...`, havolalar uchun)

### VPN (WireGuard)
Sayt har bir ishtirokchiga shaxsiy `.conf` beradi (maxfiy kalit bazada saqlanmaydi) va server uchun
peer ro'yxatini chiqaradi.

```
VPN_ENDPOINT=vpn.example.uz:51820
VPN_SERVER_PUBLIC_KEY=<server public key>
VPN_SUBNET=10.13.0.0/16          # ixtiyoriy; server .1
VPN_ALLOWED_IPS=10.13.0.0/16     # ixtiyoriy
VPN_DNS=10.13.0.1                # ixtiyoriy
VPN_SYNC_TOKEN=<uzun tasodifiy qator>
```

Serverda (cron, masalan har daqiqada):

```bash
curl -fsS -H "Authorization: Bearer $VPN_SYNC_TOKEN" https://<sayt>/vpn/peers.conf -o /etc/wireguard/peers.conf \
  && cat /etc/wireguard/wg0-base.conf /etc/wireguard/peers.conf > /etc/wireguard/wg0.conf \
  && wg syncconf wg0 <(wg-quick strip wg0)
```

Bloklangan foydalanuvchilar ro'yxatga kirmaydi.

## Sertifikatlar
Musobaqa tugagach top-3 ga avtomatik beriladi: `/certificates/<kod>` — ochiq tekshirish sahifasi,
«PDF sifatida saqlash» brauzerning chop etish oynasini A4 formatda ochadi. Sertifikat bilimni emas,
aniq natijani (o'rin, ball, format, sana) tasdiqlaydi. Ishtirokchi bloklansa, sertifikati avtomatik
bekor qilinadi va o'rinlar qayta hisoblanadi.
