import math
from collections import defaultdict
from datetime import datetime

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
