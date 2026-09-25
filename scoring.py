from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func

from models import (Challenge, CompetitionRegistration, CompetitionSolve, Hint, HintDebit,
                    HintUnlock, Solve, User, db, utcnow)


def challenge_value(ch, solve_count):
    """Practice challenge rewards are fixed and never decay with solve count."""
    return ch.value


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
    challenge_debits = defaultdict(int)
    for debit in HintDebit.query.filter_by(source='challenge reward').all():
        challenge_debits[(debit.user_id, debit.challenge_id)] += debit.amount
    if user_ids is not None:
        challenge_debits = defaultdict(int, {k: v for k, v in challenge_debits.items() if k[0] in user_ids})
    for s in sq.all():
        value = max(values.get(s.challenge_id, 0) - challenge_debits[(s.user_id, s.challenge_id)], 0)
        events[s.user_id].append((s.created_at, value, 'solve', s.challenge_id))
    hq = db.session.query(HintUnlock.user_id, HintUnlock.created_at, Hint.cost, Hint.challenge_id,
                          HintDebit.amount, HintDebit.source).select_from(HintUnlock).join(
                              Hint, Hint.id == HintUnlock.hint_id).outerjoin(
                              HintDebit, db.and_(HintDebit.user_id == HintUnlock.user_id,
                                                 HintDebit.hint_id == HintUnlock.hint_id))
    if user_ids is not None:
        hq = hq.filter(HintUnlock.user_id.in_(user_ids))
    for uid, at, cost, cid, amount, source in hq.all():
        debit = amount if amount is not None else cost
        if debit and source != 'challenge reward':
            events[uid].append((at, -debit, 'hint', cid))
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


TIERS = [  # (minimum activity XP, display name, colour)
    (0, 'Yangi boshlovchi', '#94a3b8'),
    (200, 'Tadqiqotchi', '#34d399'),
    (600, 'Hacker', '#22d3ee'),
    (1500, 'Mutaxassis', '#a78bfa'),
    (3000, 'Usta', '#fbbf24'),
    (6000, 'Afsona', '#ff3b5c'),
]
LEVEL_XP = 100


def activity_xp(user):
    """Rank progress is based on solved challenge difficulty and verified events, not score."""
    xp_by_difficulty = {'Easy': 25, 'Medium': 50, 'Hard': 100, 'Insane': 150}
    xp = sum(xp_by_difficulty.get(d, 25) for (d,) in
             db.session.query(Challenge.difficulty).join(Solve, Solve.challenge_id == Challenge.id)
             .filter(Solve.user_id == user.id).all())
    registrations = CompetitionRegistration.query.filter_by(user_id=user.id, participated=True).all()
    for registration in registrations:
        xp += 100
        placement = registration.placement
        if placement is None and registration.competition.ends_at <= utcnow():
            results = (db.session.query(CompetitionSolve.user_id,
                                        func.sum(CompetitionSolve.points).label('points'),
                                        func.min(CompetitionSolve.created_at).label('first_solve'))
                       .filter(CompetitionSolve.competition_id == registration.competition_id)
                       .group_by(CompetitionSolve.user_id)
                       .order_by(func.sum(CompetitionSolve.points).desc(),
                                 func.min(CompetitionSolve.created_at)).all())
            eligible = []
            for row in results:
                player = db.session.get(User, row.user_id)
                if player and not player.is_banned and not player.is_admin:
                    eligible.append(row.user_id)
            placement = next((rank for rank, uid in enumerate(eligible, 1) if uid == user.id), None)
        if placement == 1:
            xp += 150
        elif placement == 2:
            xp += 100
        elif placement == 3:
            xp += 50
    return xp


def tier_info(xp):
    idx = max(i for i, t in enumerate(TIERS) if xp >= t[0])
    lo, name, color = TIERS[idx]
    nxt = TIERS[idx + 1] if idx + 1 < len(TIERS) else None
    progress = 100 if not nxt else int((xp - lo) / (nxt[0] - lo) * 100)
    return {'index': idx + 1, 'name': name, 'color': color, 'next': nxt[1] if nxt else None,
            'next_at': nxt[0] if nxt else None, 'progress': max(min(progress, 100), 0)}


def level_info(xp):
    s = max(xp, 0)
    return {'level': s // LEVEL_XP + 1, 'xp': s % LEVEL_XP, 'need': LEVEL_XP}


def profile_stats(user, now):
    """Everything the dashboard and profile pages show about one user."""
    events = _events([user.id]).get(user.id, [])
    score = sum(e[1] for e in events)
    solves = [e for e in events if e[2] == 'solve']
    xp = activity_xp(user)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_start = (month_start - timedelta(days=1)).replace(day=1)

    def window(a, b):
        evs = [e for e in events if a <= e[0] < b]
        return {'points': sum(e[1] for e in evs),
                'solves': sum(1 for e in evs if e[2] == 'solve'),
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
    event_count = CompetitionRegistration.query.filter_by(user_id=user.id, participated=True).count()
    return {'score': score, 'solves': len(solves), 'xp': xp, 'events': event_count, 'this_month': this_m,
            'last_month': last_m, 'activity': activity, 'streak': streak, 'best_streak': best,
            'tier': tier_info(xp), 'level': level_info(xp), 'series': series,
            'hints': sum(1 for e in events if e[2] == 'hint')}
