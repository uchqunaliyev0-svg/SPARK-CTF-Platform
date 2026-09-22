import math
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func

from models import Challenge, Hint, HintUnlock, Solve, User, db


def challenge_value(ch, solve_count):
    """CTFd-style quadratic decay; the first solver always gets the full value."""
    if not ch.dynamic or not ch.decay or ch.minimum is None:
        return ch.value
    n = max(solve_count - 1, 0)
    v = ((ch.minimum - ch.value) / (ch.decay ** 2)) * (n ** 2) + ch.value
    return max(int(math.ceil(v)), ch.minimum)


def solve_counts(include_hidden_users=False):
    q = db.session.query(Solve.challenge_id, func.count(Solve.id)).join(User, User.id == Solve.user_id)
    if not include_hidden_users:
        q = q.filter(User.is_banned.is_(False), User.is_admin.is_(False))
    return dict(q.group_by(Solve.challenge_id).all())


def current_values(challenges=None, counts=None):
    challenges = challenges if challenges is not None else Challenge.query.all()
    counts = counts if counts is not None else solve_counts()
    return {c.id: challenge_value(c, counts.get(c.id, 0)) for c in challenges}


def _events(user_ids=None):
    """Per-user timeline of (time, delta, kind, challenge_id) for solves and hint costs."""
    values = current_values()
    events = defaultdict(list)
    sq = Solve.query
    if user_ids is not None:
        sq = sq.filter(Solve.user_id.in_(user_ids))
    for s in sq.all():
        events[s.user_id].append((s.created_at, values.get(s.challenge_id, 0), 'solve', s.challenge_id))
    hq = db.session.query(HintUnlock.user_id, HintUnlock.created_at, Hint.cost, Hint.challenge_id).join(Hint)
    if user_ids is not None:
        hq = hq.filter(HintUnlock.user_id.in_(user_ids))
    for uid, at, cost, cid in hq.all():
        if cost:
            events[uid].append((at, -cost, 'hint', cid))
    for evs in events.values():
        evs.sort(key=lambda e: e[0])
    return events


def standings():
    """Ranked list of dicts for all visible (non-admin, non-banned) users."""
    users = User.query.filter_by(is_banned=False, is_admin=False, is_verified=True).all()
    events = _events([u.id for u in users])
    rows = []
    for u in users:
        evs = events.get(u.id, [])
        score = sum(e[1] for e in evs)
        solves = sum(1 for e in evs if e[2] == 'solve')
        last = max((e[0] for e in evs if e[2] == 'solve'), default=None)
        rows.append({'user': u, 'score': score, 'solves': solves, 'last': last})
    rows.sort(key=lambda r: (-r['score'], r['last'] or datetime.max, r['user'].id))
    rank = 0
    for r in rows:
        rank += 1
        r['rank'] = rank
    return rows


def user_score(user):
    evs = _events([user.id]).get(user.id, [])
    return sum(e[1] for e in evs)


def graph_series(rows, limit=10):
    top = [r for r in rows if r['solves'] > 0][:limit]
    events = _events([r['user'].id for r in top])
    series = []
    for r in top:
        total = 0
        points = []
        for at, delta, _, _ in events.get(r['user'].id, []):
            total += delta
            points.append({'t': at.isoformat() + 'Z', 'y': total})
        series.append({'name': r['user'].username, 'points': points})
    return series


TIERS = [  # (min score, name, colour)
    (0, 'Rookie', '#94a3b8'),
    (200, 'Explorer', '#34d399'),
    (600, 'Hacker', '#22d3ee'),
    (1500, 'Elite', '#a78bfa'),
    (3000, 'Master', '#fbbf24'),
    (6000, 'Legend', '#ff3b5c'),
]
LEVEL_XP = 100


def tier_info(score):
    idx = max(i for i, t in enumerate(TIERS) if score >= t[0])
    lo, name, color = TIERS[idx]
    nxt = TIERS[idx + 1] if idx + 1 < len(TIERS) else None
    progress = 100 if not nxt else int((score - lo) / (nxt[0] - lo) * 100)
    return {'index': idx + 1, 'name': name, 'color': color, 'next': nxt[1] if nxt else None,
            'next_at': nxt[0] if nxt else None, 'progress': max(min(progress, 100), 0)}


def level_info(score):
    s = max(score, 0)
    return {'level': s // LEVEL_XP + 1, 'xp': s % LEVEL_XP, 'need': LEVEL_XP}


def first_blood_ids(user_id):
    """Challenge ids where this user was the first non-admin solver."""
    first = {}
    rows = (db.session.query(Solve.challenge_id, Solve.user_id, Solve.created_at)
            .join(User, User.id == Solve.user_id)
            .filter(User.is_admin.is_(False), User.is_banned.is_(False))
            .order_by(Solve.created_at).all())
    for cid, uid, _at in rows:
        first.setdefault(cid, uid)
    return {cid for cid, uid in first.items() if uid == user_id}


def profile_stats(user, now):
    """Everything the dashboard and profile pages show about one user."""
    events = _events([user.id]).get(user.id, [])
    score = sum(e[1] for e in events)
    solves = [e for e in events if e[2] == 'solve']
    bloods = first_blood_ids(user.id)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_start = (month_start - timedelta(days=1)).replace(day=1)

    def window(a, b):
        evs = [e for e in events if a <= e[0] < b]
        return {'points': sum(e[1] for e in evs),
                'solves': sum(1 for e in evs if e[2] == 'solve'),
                'bloods': sum(1 for e in evs if e[2] == 'solve' and e[3] in bloods),
                'hints': sum(1 for e in evs if e[2] == 'hint')}
    this_m, last_m = window(month_start, now + timedelta(days=1)), window(prev_start, month_start)

    today = now.date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    per_day = {}
    for e in solves:
        per_day[e[0].date()] = per_day.get(e[0].date(), 0) + 1
    activity = [{'date': d.isoformat(), 'count': per_day.get(d, 0)} for d in days]
    streak, d = 0, today if per_day.get(today) else today - timedelta(days=1)
    while per_day.get(d):
        streak += 1
        d -= timedelta(days=1)
    best, run, prev = 0, 0, None
    for day in sorted(per_day):
        run = run + 1 if prev and (day - prev).days == 1 else 1
        best, prev = max(best, run), day
    total = 0
    series = []
    for at, delta, _k, _c in events:
        total += delta
        series.append({'t': at.isoformat() + 'Z', 'y': total})
    return {'score': score, 'solves': len(solves), 'bloods': len(bloods), 'this_month': this_m,
            'last_month': last_m, 'activity': activity, 'streak': streak, 'best_streak': best,
            'tier': tier_info(score), 'level': level_info(score), 'series': series,
            'hints': sum(1 for e in events if e[2] == 'hint')}
