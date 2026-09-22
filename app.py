import hmac
import os
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request,
                   session, url_for)
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

import scoring
from i18n import LANGS, _, get_lang, js_strings
from mailer import mail_enabled, send_code
from models import (Announcement, Attempt, Challenge, EmailCode, Hint, HintUnlock, Setting, Solve,
                    User, db, utcnow)
from security import (EMAIL_RE, USERNAME_RE, check_csrf, client_ip, consume_code, csrf_token,
                      issue_code, new_captcha, password_problem, resend_wait_seconds, verify_captcha)

CATEGORIES = ['Web', 'Crypto', 'Reverse', 'Forensics', 'Pwn', 'OSINT', 'Misc']
CATEGORY_META = {
    'Web': ('#22d3ee', "Veb-ilovalardagi zaifliklar: SQLi, XSS, SSRF, autentifikatsiya xatolari."),
    'Crypto': ('#a78bfa', "Klassik va zamonaviy shifrlar, xesh va kalit almashinuvi xatolarini buzish."),
    'Reverse': ('#fbbf24', "Binar fayllar va dasturlarni teskari muhandislik orqali tahlil qilish."),
    'Forensics': ('#34d399', "Tarmoq trafigi, xotira dampi va fayllardan raqamli izlarni topish."),
    'Pwn': ('#ff3b5c', "Xotira zaifliklari: buffer overflow, format string, ROP zanjirlari."),
    'OSINT': ('#60a5fa', "Ochiq manbalardan ma'lumot yig'ish va razvedka qilish."),
    'Misc': ('#f472b6', "Mantiqiy jumboqlar, steganografiya va nostandart masalalar."),
}
DIFFICULTIES = ['Easy', 'Medium', 'Hard', 'Insane']
MAX_LOGIN_FAILS = 5
LOCK_TIME = timedelta(minutes=15)
FLAG_WINDOW = timedelta(seconds=60)
FLAG_MAX_WRONG = 10

IS_PROD = bool(os.getenv('VERCEL') or os.getenv('FORCE_HTTPS'))


def _db_url():
    url = os.getenv('DATABASE_URL', 'sqlite:////tmp/spark_ctf.db')
    return url.replace('postgres://', 'postgresql://', 1)


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv('SECRET_KEY', 'spark-ctf-dev-key-change-in-prod'),
    SQLALCHEMY_DATABASE_URI=_db_url(),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True, 'pool_recycle': 280},
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=IS_PROD,
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SAMESITE='Lax',
    REMEMBER_COOKIE_SECURE=IS_PROD,
    REMEMBER_COOKIE_DURATION=timedelta(days=14),
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    MAX_CONTENT_LENGTH=1024 * 1024,
    CAPTCHA_BITS=int(os.getenv('CAPTCHA_BITS', '16')),
)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', '').strip().lower()
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', '').strip().lower()

db.init_app(app)
bcrypt = Bcrypt(app)
DUMMY_HASH = bcrypt.generate_password_hash('timing-equalizer').decode()
login_manager = LoginManager(app)
login_manager.login_view = 'login'

with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f'[startup] DB init failed: {e}')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith('/api/'):
        return jsonify({'status': 'error', 'message': _('Avval tizimga kiring.')}), 401
    flash(_('Davom etish uchun tizimga kiring.'), 'info')
    return redirect(url_for('login', next=request.full_path.rstrip('?')))


app.jinja_env.globals['_'] = _


@app.template_filter('zip')
def zip_filter(a, *others):
    return zip(a, *others)


@app.template_global()
def hue(name):
    h = 0
    for c in name:
        h = (h * 31 + ord(c)) % 360
    return h


# ---------------------------------------------------------------- helpers

def get_setting(key):
    s = db.session.get(Setting, key)
    return s.value if s else None


def set_setting(key, value):
    s = db.session.get(Setting, key) or Setting(key=key)
    s.value = value
    db.session.add(s)


def parse_iso(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return None


def ctf_window():
    return parse_iso(get_setting('ctf_start')), parse_iso(get_setting('ctf_end'))


def ctf_state():
    start, end = ctf_window()
    now = utcnow()
    if start and now < start:
        return 'before'
    if end and now >= end:
        return 'ended'
    return 'running'


def maybe_grant_admin(user):
    if not user.is_verified:
        return
    if (ADMIN_USERNAME and user.username.lower() == ADMIN_USERNAME) or \
       (ADMIN_EMAIL and user.email == ADMIN_EMAIL):
        user.is_admin = True


def safe_next(target):
    if target and target.startswith('/') and not target.startswith('//') and '\\' not in target:
        return target
    return None


def mask_email(email):
    name, _, domain = email.partition('@')
    return (name[:2] + '•' * max(len(name) - 2, 1)) + '@' + domain


def verified_required(view):
    @wraps(view)
    @login_required
    def wrapper(*a, **kw):
        if not current_user.is_verified:
            session['pending_uid'] = current_user.id
            logout_user()
            return redirect(url_for('verify'))
        return view(*a, **kw)
    return wrapper


def admin_required(view):
    @wraps(view)
    @verified_required
    def wrapper(*a, **kw):
        if not current_user.is_admin:
            abort(404)
        return view(*a, **kw)
    return wrapper


def wants_json():
    return request.path.startswith('/api/')


def api_error(msg, code=400):
    return jsonify({'status': 'error', 'message': msg}), code


def start_login(user, remember=False):
    token = session.get('_csrf')
    session.clear()
    if token:
        session['_csrf'] = token
    user.failed_logins = 0
    user.locked_until = None
    maybe_grant_admin(user)
    db.session.commit()
    login_user(user, remember=remember)


def captcha_ok():
    if verify_captcha(request.form.get('captcha')):
        return True
    flash(_("Iltimos, robot emasligingizni tasdiqlang."), 'error')
    return False


def send_verification(user):
    wait = resend_wait_seconds(user, 'verify')
    if wait:
        return wait
    code = issue_code(user, 'verify')
    if not send_code(user.email, user.username, 'verify', code):
        flash(_("Emailga kod yuborib bo'lmadi. Birozdan so'ng qayta yuborib ko'ring."), 'error')
    return 0


# ---------------------------------------------------------------- request hooks

@app.before_request
def before():
    check_csrf()
    if current_user.is_authenticated and current_user.is_banned:
        logout_user()
        flash(_('Hisobingiz bloklangan.'), 'error')
        return redirect(url_for('login'))


@app.after_request
def security_headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    resp.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if IS_PROD:
        resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    if request.path.startswith('/api/') or current_user.is_authenticated:
        resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.context_processor
def inject():
    ctx = {'csrf_token': csrf_token, 'CATEGORIES': CATEGORIES, 'DIFFICULTIES': DIFFICULTIES,
           'CATEGORY_META': CATEGORY_META, 'ctf_state': ctf_state, 'mail_enabled': mail_enabled(),
           'lang': get_lang(), 'js_i18n': js_strings(), 'year': utcnow().year}
    if current_user.is_authenticated and current_user.is_verified:
        if 'my_score' not in g:
            g.my_score = scoring.user_score(current_user)
            g.bell = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
        ctx['my_score'] = g.my_score
        ctx['bell'] = g.bell
    return ctx


@app.errorhandler(HTTPException)
def http_error(e):
    if wants_json():
        return api_error(e.description or e.name, e.code)
    return render_template('error.html', code=e.code, message=e.description), e.code


@app.errorhandler(Exception)
def server_error(e):
    print(f'[error] {e!r}')
    db.session.rollback()
    if wants_json():
        return api_error(_('Serverda xatolik yuz berdi.'), 500)
    return render_template('error.html', code=500,
                           message="Serverda kutilmagan xatolik. Birozdan so'ng qayta urinib ko'ring."), 500


# ---------------------------------------------------------------- public pages

@app.route('/')
def index():
    rows = scoring.standings()
    stats = {
        'users': len(rows),
        'challenges': Challenge.query.filter_by(visible=True).count(),
        'solves': Solve.query.count(),
    }
    start, end = ctf_window()
    return render_template('index.html', top=rows[:5], stats=stats, start=start, end=end)


@app.route('/api/captcha')
def api_captcha():
    return jsonify(new_captcha())


def _category_progress(user_id):
    chs = Challenge.query.filter_by(visible=True).all()
    solved = {s.challenge_id for s in Solve.query.filter_by(user_id=user_id).all()}
    names = CATEGORIES + sorted({c.category for c in chs} - set(CATEGORIES))
    out = []
    for n in names:
        items = [c for c in chs if c.category == n]
        out.append({'name': n, 'total': len(items), 'solved': sum(1 for c in items if c.id in solved),
                    'color': CATEGORY_META.get(n, ('#22d3ee', ''))[0]})
    diffs = []
    for d in DIFFICULTIES:
        items = [c for c in chs if c.difficulty == d]
        diffs.append({'name': d, 'total': len(items), 'solved': sum(1 for c in items if c.id in solved)})
    return out, diffs


@app.route('/dashboard')
@verified_required
def dashboard():
    rows = scoring.standings()
    me = next((r for r in rows if r['user'].id == current_user.id), None)
    stats = scoring.profile_stats(current_user, utcnow())
    cats, diffs = _category_progress(current_user.id)
    recent = (Solve.query.filter_by(user_id=current_user.id).join(Challenge)
              .filter(Challenge.visible.is_(True)).order_by(Solve.created_at.desc()).limit(6).all())
    anns = Announcement.query.order_by(Announcement.created_at.desc()).limit(3).all()
    values = scoring.current_values()
    counts = scoring.solve_counts()
    solved = {s.challenge_id for s in Solve.query.filter_by(user_id=current_user.id).all()}
    suggestions = []
    if ctf_state() == 'running' or current_user.is_admin:
        pool = sorted((c for c in Challenge.query.filter_by(visible=True).all() if c.id not in solved),
                      key=lambda c: (DIFFICULTIES.index(c.difficulty) if c.difficulty in DIFFICULTIES else 9,
                                     -counts.get(c.id, 0), values.get(c.id, 0)))
        seen = set()
        for c in pool:
            if c.category not in seen:
                suggestions.append(c)
                seen.add(c.category)
            if len(suggestions) == 4:
                break
    total = sum(c['total'] for c in cats)
    return render_template('dashboard.html', row=me, players=len(rows), stats=stats, recent=recent,
                           announcements=anns, values=values, counts=counts, suggestions=suggestions,
                           total=total)


@app.route('/notifications')
@verified_required
def notifications():
    anns = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template('notifications.html', announcements=anns)


@app.route('/vpn')
@verified_required
def vpn():
    return render_template('vpn.html')


@app.route('/lang/<code>')
def set_lang(code):
    resp = redirect(safe_next(request.args.get('next')) or url_for('index'))
    if code in LANGS:
        resp.set_cookie('lang', code, max_age=365 * 86400, samesite='Lax', secure=IS_PROD)
    return resp


@app.route('/rules')
def rules():
    return render_template('rules.html')


@app.route('/scoreboard')
@verified_required
def scoreboard():
    rows = scoring.standings()
    return render_template('scoreboard.html', rows=rows, series=scoring.graph_series(rows))


@app.route('/users/<username>')
@verified_required
def user_page(username):
    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if not user or user.is_banned or not user.is_verified:
        abort(404)
    rows = scoring.standings()
    me = next((r for r in rows if r['user'].id == user.id), None)
    stats = scoring.profile_stats(user, utcnow())
    cats, diffs = _category_progress(user.id)
    solves = (Solve.query.filter_by(user_id=user.id).join(Challenge)
              .filter(Challenge.visible.is_(True)).order_by(Solve.created_at.desc()).all())
    return render_template('user.html', user=user, row=me, players=len(rows), stats=stats,
                           cats=cats, diffs=diffs, solves=solves, values=scoring.current_values(),
                           bloods=scoring.first_blood_ids(user.id))


# ---------------------------------------------------------------- auth

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = {}
    if request.method == 'POST':
        form = {k: (request.form.get(k) or '').strip() for k in ('username', 'email')}
        pw, pw2 = request.form.get('password') or '', request.form.get('password2') or ''
        email = form['email'].lower()
        error = None
        if not USERNAME_RE.match(form['username']):
            error = _("Username 3–20 belgi: faqat lotin harflari, raqamlar va _ bo'lishi mumkin.")
        elif len(email) > 120 or not EMAIL_RE.match(email):
            error = _("Email manzil noto'g'ri.")
        elif password_problem(pw):
            error = password_problem(pw)
        elif pw != pw2:
            error = _('Parollar mos kelmadi.')
        elif User.query.filter(func.lower(User.username) == form['username'].lower()).first():
            error = _('Bu username band.')
        elif User.query.filter_by(email=email).first():
            error = _("Bu email bilan allaqachon ro'yxatdan o'tilgan.")
        if not error and not verify_captcha(request.form.get('captcha')):
            error = _("Iltimos, robot emasligingizni tasdiqlang.")
        if error:
            flash(error, 'error')
            return render_template('auth/register.html', form=form), 400
        user = User(username=form['username'], email=email,
                    password_hash=bcrypt.generate_password_hash(pw).decode(),
                    is_verified=not mail_enabled())
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(_('Bu username yoki email band.'), 'error')
            return render_template('auth/register.html', form=form), 400
        if user.is_verified:
            start_login(user)
            flash(_("Xush kelibsiz! Hisobingiz yaratildi."), 'success')
            return redirect(url_for('dashboard'))
        session['pending_uid'] = user.id
        send_verification(user)
        return redirect(url_for('verify'))
    return render_template('auth/register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    ident = ''
    if request.method == 'POST':
        ident = (request.form.get('identity') or '').strip()
        pw = request.form.get('password') or ''
        if not captcha_ok():
            return render_template('auth/login.html', ident=ident), 400
        user = User.query.filter(or_(func.lower(User.username) == ident.lower(),
                                     User.email == ident.lower())).first()
        now = utcnow()
        if user and user.locked_until and user.locked_until > now:
            mins = int((user.locked_until - now).total_seconds() // 60) + 1
            flash(_("Ko'p noto'g'ri urinish. Hisob {mins} daqiqaga vaqtincha bloklandi.", mins=mins), 'error')
            return render_template('auth/login.html', ident=ident), 429
        valid = bcrypt.check_password_hash(user.password_hash if user else DUMMY_HASH, pw)
        if not user or not valid:
            if user:
                user.failed_logins += 1
                if user.failed_logins >= MAX_LOGIN_FAILS:
                    user.failed_logins = 0
                    user.locked_until = now + LOCK_TIME
                db.session.commit()
            flash(_("Login yoki parol noto'g'ri."), 'error')
            return render_template('auth/login.html', ident=ident), 401
        if user.is_banned:
            flash(_('Hisobingiz bloklangan.'), 'error')
            return render_template('auth/login.html', ident=ident), 403
        if not user.is_verified:
            if not mail_enabled():
                user.is_verified = True
            else:
                session['pending_uid'] = user.id
                send_verification(user)
                flash(_('Avval emailingizni tasdiqlang.'), 'info')
                return redirect(url_for('verify'))
        nxt = safe_next(request.args.get('next'))
        start_login(user, remember=bool(request.form.get('remember')))
        return redirect(nxt or url_for('dashboard'))
    return render_template('auth/login.html', ident=ident)


@app.route('/verify', methods=['GET', 'POST'])
def verify():
    uid = session.get('pending_uid')
    user = db.session.get(User, uid) if uid else None
    if not user or user.is_verified:
        session.pop('pending_uid', None)
        return redirect(url_for('login'))
    if request.method == 'POST':
        err = consume_code(user, 'verify', request.form.get('code'))
        if err:
            flash(err, 'error')
        else:
            user.is_verified = True
            db.session.commit()
            start_login(user)
            flash(_('Email tasdiqlandi. Omad, xaker!'), 'success')
            return redirect(url_for('dashboard'))
    return render_template('auth/verify.html', email=mask_email(user.email),
                           wait=resend_wait_seconds(user, 'verify'))


@app.route('/verify/resend', methods=['POST'])
def verify_resend():
    uid = session.get('pending_uid')
    user = db.session.get(User, uid) if uid else None
    if not user or user.is_verified:
        return redirect(url_for('login'))
    wait = send_verification(user)
    if wait:
        flash(_("Yangi kodni {wait} soniyadan so'ng so'rashingiz mumkin.", wait=wait), 'error')
    else:
        flash(_('Yangi kod emailingizga yuborildi.'), 'success')
    return redirect(url_for('verify'))


@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        if not mail_enabled():
            flash(_("Email xizmati hozircha sozlanmagan. Admin bilan bog'laning."), 'error')
            return render_template('auth/forgot.html'), 503
        email = (request.form.get('email') or '').strip().lower()
        if not captcha_ok():
            return render_template('auth/forgot.html'), 400
        user = User.query.filter_by(email=email).first()
        if user and not user.is_banned and not resend_wait_seconds(user, 'reset'):
            send_code(user.email, user.username, 'reset', issue_code(user, 'reset'))
        session['reset_email'] = email
        flash(_("Agar bu email ro'yxatdan o'tgan bo'lsa, unga tiklash kodi yuborildi."), 'info')
        return redirect(url_for('reset'))
    return render_template('auth/forgot.html')


@app.route('/reset', methods=['GET', 'POST'])
def reset():
    email = session.get('reset_email')
    if not email:
        return redirect(url_for('forgot'))
    if request.method == 'POST':
        pw, pw2 = request.form.get('password') or '', request.form.get('password2') or ''
        user = User.query.filter_by(email=email).first()
        if password_problem(pw):
            flash(password_problem(pw), 'error')
        elif pw != pw2:
            flash(_('Parollar mos kelmadi.'), 'error')
        elif not user:
            flash(_("Kod noto'g'ri."), 'error')
        else:
            err = consume_code(user, 'reset', request.form.get('code'))
            if err:
                flash(err, 'error')
            else:
                user.password_hash = bcrypt.generate_password_hash(pw).decode()
                user.is_verified = True
                user.failed_logins = 0
                user.locked_until = None
                db.session.commit()
                session.pop('reset_email', None)
                flash(_("Parol yangilandi. Endi yangi parol bilan kiring."), 'success')
                return redirect(url_for('login'))
    return render_template('auth/reset.html', email=mask_email(email))


@app.route('/logout', methods=['POST'])
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('index'))


@app.route('/settings', methods=['GET', 'POST'])
@verified_required
def settings():
    if request.method == 'POST':
        cur = request.form.get('current_password') or ''
        pw, pw2 = request.form.get('password') or '', request.form.get('password2') or ''
        if not bcrypt.check_password_hash(current_user.password_hash, cur):
            flash(_("Joriy parol noto'g'ri."), 'error')
        elif password_problem(pw):
            flash(password_problem(pw), 'error')
        elif pw != pw2:
            flash(_('Yangi parollar mos kelmadi.'), 'error')
        else:
            current_user.password_hash = bcrypt.generate_password_hash(pw).decode()
            db.session.commit()
            flash(_('Parol muvaffaqiyatli yangilandi.'), 'success')
            return redirect(url_for('settings'))
    return render_template('settings.html')


# ---------------------------------------------------------------- challenges

@app.route('/challenges')
@verified_required
def challenges():
    state = ctf_state()
    start, end = ctf_window()
    if state == 'before' and not current_user.is_admin:
        return render_template('challenges.html', state=state, start=start, end=end, groups=[],
                               announcements=[], solved=set(), values={}, counts={}, overview=[],
                               me=None, players=0)
    q = Challenge.query
    if not current_user.is_admin:
        q = q.filter_by(visible=True)
    chs = q.order_by(Challenge.value, Challenge.id).all()
    counts = scoring.solve_counts()
    values = scoring.current_values(chs, counts)
    solved = {s.challenge_id for s in Solve.query.filter_by(user_id=current_user.id).all()}
    order = {c: i for i, c in enumerate(CATEGORIES)}
    groups = {}
    for c in chs:
        groups.setdefault(c.category, []).append(c)
    groups = sorted(groups.items(), key=lambda kv: (order.get(kv[0], 99), kv[0]))
    anns = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    names = CATEGORIES + sorted(k for k, _v in groups if k not in CATEGORIES)
    by_cat = dict(groups)
    overview = [{'name': n, 'total': len(by_cat.get(n, [])),
                 'solved': sum(1 for c in by_cat.get(n, []) if c.id in solved)} for n in names]
    rows = scoring.standings()
    me = next((r for r in rows if r['user'].id == current_user.id), None)
    return render_template('challenges.html', state=state, start=start, end=end, groups=groups,
                           counts=counts, values=values, solved=solved, announcements=anns,
                           overview=overview, me=me, players=len(rows))


def _challenge_or_404(cid):
    ch = db.session.get(Challenge, cid)
    if not ch or (not ch.visible and not current_user.is_admin):
        abort(404, description=_('Masala topilmadi.'))
    if ctf_state() == 'before' and not current_user.is_admin:
        abort(403, description=_('Musobaqa hali boshlanmagan.'))
    return ch


@app.route('/api/challenges/<int:cid>')
@verified_required
def api_challenge(cid):
    ch = _challenge_or_404(cid)
    counts = scoring.solve_counts()
    unlocked = {u.hint_id for u in HintUnlock.query.filter_by(user_id=current_user.id).all()}
    solved = Solve.query.filter_by(user_id=current_user.id, challenge_id=ch.id).first() is not None
    return jsonify({
        'id': ch.id, 'title': ch.title, 'category': ch.category, 'difficulty': ch.difficulty,
        'author': ch.author or '', 'description': ch.description,
        'value': scoring.challenge_value(ch, counts.get(ch.id, 0)),
        'solves': counts.get(ch.id, 0), 'files': ch.file_list, 'solved': solved,
        'hints': [{'id': h.id, 'cost': h.cost, 'unlocked': h.id in unlocked,
                   'content': h.content if h.id in unlocked else None} for h in ch.hints],
        'can_submit': ctf_state() == 'running' or current_user.is_admin,
    })


@app.route('/api/challenges/<int:cid>/solves')
@verified_required
def api_challenge_solves(cid):
    ch = _challenge_or_404(cid)
    rows = (db.session.query(User.username, Solve.created_at).join(User, User.id == Solve.user_id)
            .filter(Solve.challenge_id == ch.id, User.is_admin.is_(False), User.is_banned.is_(False))
            .order_by(Solve.created_at).all())
    return jsonify([{'username': u, 'time': t.isoformat() + 'Z'} for u, t in rows])


@app.route('/api/challenges/<int:cid>/submit', methods=['POST'])
@verified_required
def api_submit(cid):
    ch = _challenge_or_404(cid)
    state = ctf_state()
    if state != 'running' and not current_user.is_admin:
        return api_error(_('Musobaqa yakunlangan — flag qabul qilinmaydi.'), 403)
    if Solve.query.filter_by(user_id=current_user.id, challenge_id=ch.id).first():
        return api_error(_('Bu masalani allaqachon yechgansiz.'), 400)
    since = utcnow() - FLAG_WINDOW
    wrong = Attempt.query.filter(Attempt.user_id == current_user.id, Attempt.correct.is_(False),
                                 Attempt.created_at >= since).count()
    if wrong >= FLAG_MAX_WRONG:
        return api_error(_("Juda ko'p urinish. 1 daqiqa kuting."), 429)
    data = request.get_json(silent=True) or {}
    submitted = str(data.get('flag') or '').strip()
    if not submitted:
        return api_error(_('Flagni kiriting.'), 400)
    if len(submitted) > 255:
        return api_error(_('Flag juda uzun.'), 400)
    a, b = submitted, ch.flag.strip()
    if ch.case_insensitive:
        a, b = a.lower(), b.lower()
    correct = hmac.compare_digest(a.encode(), b.encode())
    db.session.add(Attempt(user_id=current_user.id, challenge_id=ch.id, submission=submitted,
                           correct=correct, ip=client_ip()))
    if not correct:
        db.session.commit()
        return jsonify({'status': 'wrong', 'message': _("Noto'g'ri flag. Yana urinib ko'ring.")})
    db.session.add(Solve(user_id=current_user.id, challenge_id=ch.id))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return api_error(_('Bu masalani allaqachon yechgansiz.'), 400)
    counts = scoring.solve_counts()
    first = counts.get(ch.id, 0) == 1 and not current_user.is_admin
    return jsonify({'status': 'correct', 'first_blood': first,
                    'value': scoring.challenge_value(ch, counts.get(ch.id, 0)),
                    'score': scoring.user_score(current_user),
                    'message': _("First blood! 🩸 Siz birinchi bo'ldingiz!") if first else _("To'g'ri flag! Tabriklaymiz.")})


@app.route('/api/hints/<int:hid>/unlock', methods=['POST'])
@verified_required
def api_unlock_hint(hid):
    hint = db.session.get(Hint, hid)
    if not hint:
        abort(404)
    _challenge_or_404(hint.challenge_id)
    if HintUnlock.query.filter_by(user_id=current_user.id, hint_id=hint.id).first():
        return jsonify({'status': 'ok', 'content': hint.content})
    if ctf_state() != 'running' and not current_user.is_admin:
        return api_error(_('Musobaqa yakunlangan.'), 403)
    if hint.cost and scoring.user_score(current_user) < hint.cost:
        return api_error(_("Bu hint uchun kamida {cost} ball kerak.", cost=hint.cost), 400)
    db.session.add(HintUnlock(user_id=current_user.id, hint_id=hint.id))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return jsonify({'status': 'ok', 'content': hint.content, 'score': scoring.user_score(current_user)})


# ---------------------------------------------------------------- admin

@app.route('/admin')
@admin_required
def admin_index():
    day = utcnow() - timedelta(days=1)
    stats = {
        'users': User.query.count(),
        'verified': User.query.filter_by(is_verified=True).count(),
        'challenges': Challenge.query.count(),
        'hidden': Challenge.query.filter_by(visible=False).count(),
        'solves': Solve.query.count(),
        'attempts_24h': Attempt.query.filter(Attempt.created_at >= day).count(),
        'correct_24h': Attempt.query.filter(Attempt.created_at >= day, Attempt.correct.is_(True)).count(),
    }
    recent = Solve.query.order_by(Solve.created_at.desc()).limit(10).all()
    weak_secret = app.config['SECRET_KEY'] == 'spark-ctf-dev-key-change-in-prod'
    return render_template('admin/index.html', stats=stats, recent=recent, weak_secret=weak_secret)


def _challenge_from_form(ch):
    f = request.form
    errors = []
    title = (f.get('title') or '').strip()
    category = (f.get('category') or '').strip()
    difficulty = f.get('difficulty')
    flag = (f.get('flag') or '').strip()
    desc = (f.get('description') or '').strip()
    try:
        value = int(f.get('value') or 0)
    except ValueError:
        value = 0
    if not title or len(title) > 120:
        errors.append(_("Nom 1–120 belgi bo'lishi kerak."))
    if not category or len(category) > 40:
        errors.append(_('Kategoriya tanlang.'))
    if difficulty not in DIFFICULTIES:
        errors.append(_('Qiyinlik darajasini tanlang.'))
    if not desc:
        errors.append(_("Tavsif bo'sh bo'lmasin."))
    if not flag or len(flag) > 255:
        errors.append(_("Flag 1–255 belgi bo'lishi kerak."))
    if not 1 <= value <= 10000:
        errors.append(_("Ball 1–10000 oralig'ida bo'lsin."))
    dynamic = bool(f.get('dynamic'))
    minimum = decay = None
    if dynamic:
        try:
            minimum, decay = int(f.get('minimum') or 0), int(f.get('decay') or 0)
        except ValueError:
            minimum = decay = -1
        if not 0 <= minimum <= value or decay < 1:
            errors.append(_("Dinamik ball: minimum 0..boshlang'ich ball, decay ≥ 1 bo'lsin."))
    files = [l.strip() for l in (f.get('files') or '').splitlines() if l.strip()]
    if any(not (u.startswith('https://') or u.startswith('http://')) for u in files):
        errors.append(_('Fayl havolalari http(s):// bilan boshlanishi kerak.'))
    hints = []
    for hid, content, cost in zip(f.getlist('hint_id'), f.getlist('hint_content'), f.getlist('hint_cost')):
        content = content.strip()
        if not content:
            continue
        try:
            cost = max(int(cost or 0), 0)
        except ValueError:
            cost = 0
        hints.append((hid, content, cost))
    if errors:
        return errors
    ch.title, ch.category, ch.difficulty, ch.description = title, category, difficulty, desc
    ch.author = (f.get('author') or '').strip()[:60] or None
    ch.flag, ch.case_insensitive, ch.value = flag, bool(f.get('case_insensitive')), value
    ch.dynamic, ch.minimum, ch.decay = dynamic, minimum, decay
    ch.files = '\n'.join(files) or None
    ch.visible = bool(f.get('visible'))
    existing = {str(h.id): h for h in ch.hints}
    keep = []
    for pos, (hid, content, cost) in enumerate(hints):
        h = existing.get(hid) or Hint()
        h.content, h.cost, h.position = content, cost, pos
        keep.append(h)
    ch.hints = keep
    return []


@app.route('/admin/challenges')
@admin_required
def admin_challenges():
    chs = Challenge.query.order_by(Challenge.category, Challenge.value).all()
    counts = scoring.solve_counts()
    return render_template('admin/challenges.html', challenges=chs, counts=counts,
                           values=scoring.current_values(chs, counts))


@app.route('/admin/challenges/new', methods=['GET', 'POST'])
@app.route('/admin/challenges/<int:cid>/edit', methods=['GET', 'POST'])
@admin_required
def admin_challenge_form(cid=None):
    ch = db.session.get(Challenge, cid) if cid else Challenge(visible=True)
    if cid and not ch:
        abort(404)
    if request.method == 'POST':
        errors = _challenge_from_form(ch)
        if errors:
            for e in errors:
                flash(e, 'error')
        else:
            db.session.add(ch)
            db.session.commit()
            flash(_('Masala saqlandi.'), 'success')
            return redirect(url_for('admin_challenges'))
    return render_template('admin/challenge_form.html', ch=ch, is_new=cid is None)


@app.route('/admin/challenges/<int:cid>/<action>', methods=['POST'])
@admin_required
def admin_challenge_action(cid, action):
    ch = db.session.get(Challenge, cid) or abort(404)
    if action == 'toggle':
        ch.visible = not ch.visible
        flash(_("«{title}» ko'rinadigan qilindi.", title=ch.title) if ch.visible else _("«{title}» yashirildi.", title=ch.title), 'success')
    elif action == 'delete':
        Attempt.query.filter_by(challenge_id=ch.id).delete()
        Solve.query.filter_by(challenge_id=ch.id).delete()
        for h in ch.hints:
            HintUnlock.query.filter_by(hint_id=h.id).delete()
        db.session.delete(ch)
        flash(_("Masala o'chirildi."), 'success')
    else:
        abort(404)
    db.session.commit()
    return redirect(url_for('admin_challenges'))


@app.route('/admin/users')
@admin_required
def admin_users():
    q = (request.args.get('q') or '').strip()
    query = User.query
    if q:
        like = f'%{q.lower()}%'
        query = query.filter(or_(func.lower(User.username).like(like), User.email.like(like)))
    users = query.order_by(User.created_at.desc()).limit(300).all()
    scores = {r['user'].id: r for r in scoring.standings()}
    return render_template('admin/users.html', users=users, scores=scores, q=q)


@app.route('/admin/users/<int:uid>/<action>', methods=['POST'])
@admin_required
def admin_user_action(uid, action):
    user = db.session.get(User, uid) or abort(404)
    if user.id == current_user.id and action in ('ban', 'unadmin', 'delete'):
        flash(_("O'zingizga bu amalni qo'llab bo'lmaydi."), 'error')
        return redirect(url_for('admin_users'))
    if action == 'ban':
        user.is_banned = True
    elif action == 'unban':
        user.is_banned = False
    elif action == 'verify':
        user.is_verified = True
    elif action == 'admin':
        user.is_admin = True
    elif action == 'unadmin':
        user.is_admin = False
    elif action == 'delete':
        for model in (Attempt, Solve, HintUnlock, EmailCode):
            model.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
    else:
        abort(404)
    db.session.commit()
    flash(_('Bajarildi.'), 'success')
    return redirect(url_for('admin_users', q=request.args.get('q', '')))


@app.route('/admin/submissions')
@admin_required
def admin_submissions():
    kind = request.args.get('type', 'all')
    page = max(request.args.get('page', 1, type=int), 1)
    q = Attempt.query
    if kind == 'correct':
        q = q.filter(Attempt.correct.is_(True))
    elif kind == 'wrong':
        q = q.filter(Attempt.correct.is_(False))
    items = q.order_by(Attempt.created_at.desc()).offset((page - 1) * 50).limit(51).all()
    return render_template('admin/submissions.html', items=items[:50], kind=kind, page=page,
                           has_next=len(items) > 50)


@app.route('/admin/announcements', methods=['GET', 'POST'])
@admin_required
def admin_announcements():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:120]
        content = (request.form.get('content') or '').strip()
        if not title or not content:
            flash(_("Sarlavha va matnni to'ldiring."), 'error')
        else:
            db.session.add(Announcement(title=title, content=content))
            db.session.commit()
            flash(_("E'lon joylandi."), 'success')
            return redirect(url_for('admin_announcements'))
    anns = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template('admin/announcements.html', announcements=anns)


@app.route('/admin/announcements/<int:aid>/delete', methods=['POST'])
@admin_required
def admin_announcement_delete(aid):
    a = db.session.get(Announcement, aid) or abort(404)
    db.session.delete(a)
    db.session.commit()
    flash(_("E'lon o'chirildi."), 'success')
    return redirect(url_for('admin_announcements'))


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        start = parse_iso(request.form.get('ctf_start'))
        end = parse_iso(request.form.get('ctf_end'))
        if start and end and end <= start:
            flash(_("Tugash vaqti boshlanishdan keyin bo'lishi kerak."), 'error')
        else:
            set_setting('ctf_start', start.isoformat() if start else None)
            set_setting('ctf_end', end.isoformat() if end else None)
            db.session.commit()
            flash(_('Sozlamalar saqlandi.'), 'success')
            return redirect(url_for('admin_settings'))
    start, end = ctf_window()
    return render_template('admin/settings.html', start=start, end=end)


if __name__ == '__main__':
    app.run(debug=True, port=8080)
