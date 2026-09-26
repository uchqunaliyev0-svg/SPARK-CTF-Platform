from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import case, func

import secrets

from models import (Certificate, Challenge, Competition, CompetitionRegistration, CompetitionSolve,
                    Hint, HintDebit, HintUnlock, Solve, User, db)

CERTIFIED_PLACES = 3


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


def standings(since=None):
    """Ranked list of dicts for all visible (non-admin, non-banned) users.

    With `since`, only points earned from that moment count (weekly / monthly boards) and
    players with nothing in the window are left out."""
    users = User.query.filter_by(is_banned=False, is_admin=False, is_verified=True).all()
    events = _events([u.id for u in users])
    rows = []
    for u in users:
        evs = events.get(u.id, [])
        if since is not None:
            evs = [e for e in evs if e[0] >= since]
            if not any(e[2] == 'solve' for e in evs):
                continue
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


def earned_values(user):
    """{challenge_id: points actually credited} for one user's practice solves.

    A hint paid out of the task's own reward is already subtracted, so this is what the
    scoreboard counts (the raw challenge value can be higher)."""
    return {cid: delta for _at, delta, kind, cid in _events([user.id]).get(user.id, [])
            if kind == 'solve'}


# ---------------------------------------------------------------- competitions

def competition_standings(event):
    """Ranked rows for one event, highest points first; on a tie whoever got there first wins.

    Admins and banned users never appear. Each row: user, score, solves, first_bloods,
    last_solve, rank. This is the single source of truth for event ranks, placements and XP."""
    rows = (db.session.query(CompetitionSolve.user_id,
                             func.sum(CompetitionSolve.points).label('score'),
                             func.count(CompetitionSolve.id).label('solves'),
                             func.sum(case((CompetitionSolve.first_blood.is_(True), 1), else_=0))
                             .label('first_bloods'),
                             func.max(CompetitionSolve.created_at).label('last_solve'))
            .filter(CompetitionSolve.competition_id == event.id)
            .group_by(CompetitionSolve.user_id).all())
    if not rows:
        return []
    users = {u.id: u for u in User.query.filter(User.id.in_([r.user_id for r in rows])).all()}
    ranked = []
    for r in sorted(rows, key=lambda r: (-r.score, r.last_solve)):
        u = users.get(r.user_id)
        if not u or u.is_banned or u.is_admin:
            continue
        ranked.append({'user': u, 'score': int(r.score), 'solves': int(r.solves),
                       'first_bloods': int(r.first_bloods or 0), 'last_solve': r.last_solve,
                       'rank': len(ranked) + 1})
    return ranked


def _new_certificate_code():
    while True:
        raw = secrets.token_hex(5).upper()
        code = f'SPK-{raw[:5]}-{raw[5:]}'
        if not Certificate.query.filter_by(code=code).first():
            return code


def _sync_certificates(event, standings):
    """Podium certificates follow the final standings; anyone who drops off is revoked."""
    podium = {row['user'].id: row for row in standings if row['rank'] <= CERTIFIED_PLACES}
    changed = False
    existing = {c.user_id: c for c in Certificate.query.filter_by(competition_id=event.id).all()}
    for uid, cert in existing.items():
        row = podium.get(uid)
        if row is None:
            if not cert.revoked:
                cert.revoked, changed = True, True
            continue
        fresh = (row['rank'], row['score'], row['solves'], len(standings), False)
        if (cert.placement, cert.points, cert.solves, cert.players, cert.revoked) != fresh:
            cert.placement, cert.points, cert.solves, cert.players, cert.revoked = fresh
            changed = True
    for uid, row in podium.items():
        if uid not in existing:
            db.session.add(Certificate(code=_new_certificate_code(), competition_id=event.id, user_id=uid,
                                       placement=row['rank'], points=row['score'], solves=row['solves'],
                                       players=len(standings)))
            changed = True
    return changed


def finalize_placements(event, standings=None):
    """Persist final ranks and podium certificates once an event has ended.
    Returns True when anything changed."""
    if event.state != 'ended':
        return False
    standings = competition_standings(event) if standings is None else standings
    rank_of = {row['user'].id: row['rank'] for row in standings}
    changed = False
    for reg in event.registrations:
        placement = rank_of.get(reg.user_id) if reg.participated else None
        if reg.placement != placement:
            reg.placement = placement
            changed = True
    changed = _sync_certificates(event, standings) or changed
    if changed:
        db.session.commit()
    return changed


def _placement(reg, standings_cache):
    """Stored placement, or the live rank for an ended event that was never finalized."""
    event = reg.competition
    if reg.placement is not None or event.state != 'ended':
        return reg.placement
    if event.id not in standings_cache:
        standings_cache[event.id] = {row['user'].id: row['rank']
                                     for row in competition_standings(event)}
    return standings_cache[event.id].get(reg.user_id)


def _played_registrations(user_ids):
    return (CompetitionRegistration.query.join(Competition)
            .filter(CompetitionRegistration.user_id.in_(user_ids),
                    CompetitionRegistration.participated.is_(True),
                    Competition.published.is_(True)).all())


def competition_results(user, include_hidden=False):
    """Profile rows, newest event first: one per published event the user actually played.

    Rows the user hid from their profile are only returned with include_hidden (their own page)."""
    q = (CompetitionRegistration.query.join(Competition)
         .filter(CompetitionRegistration.user_id == user.id,
                 CompetitionRegistration.participated.is_(True),
                 Competition.published.is_(True)))
    if not include_hidden:
        q = q.filter(CompetitionRegistration.profile_visible.is_(True))
    out = []
    for reg in q.order_by(Competition.starts_at.desc()).all():
        event = reg.competition
        standings = competition_standings(event)
        finalize_placements(event, standings)
        mine = next((r for r in standings if r['user'].id == user.id), None)
        cert = Certificate.query.filter_by(competition_id=event.id, user_id=user.id, revoked=False).first()
        placement = reg.placement
        if placement is None and event.state == 'ended' and mine:
            placement = mine['rank']
        out.append({'registration': reg, 'event': event,
                    'solves': mine['solves'] if mine else 0,
                    'points': mine['score'] if mine else 0,
                    'first_bloods': mine['first_bloods'] if mine else 0,
                    'placement': placement if event.state == 'ended' else None,
                    'players': len(standings), 'certificate': cert})
    return out


TIERS = [  # (minimum activity XP, display name, colour)
    (0, 'Boshlovchi', '#94a3b8'),
    (200, 'Tadqiqotchi', '#34d399'),
    (600, 'Xaker', '#22d3ee'),
    (1500, 'Mutaxassis', '#a78bfa'),
    (3000, 'Usta', '#fbbf24'),
    (6000, 'Afsona', '#ff3b5c'),
]
LEVEL_XP = 100


XP_BY_DIFFICULTY = {'Easy': 25, 'Medium': 50, 'Hard': 100, 'Insane': 150}
XP_PER_EVENT = 100
XP_BY_PLACEMENT = {1: 150, 2: 100, 3: 50}


def activity_xp_bulk(users):
    """{user_id: XP} for many users in a handful of queries (the scoreboard needs everyone).

    Rank progress is based on solved challenge difficulty and played events, not score, so
    competition points never leak into the practice ladder."""
    ids = [u.id for u in users]
    xp = {uid: 0 for uid in ids}
    if not ids:
        return xp
    for uid, difficulty in (db.session.query(Solve.user_id, Challenge.difficulty)
                            .join(Challenge, Challenge.id == Solve.challenge_id)
                            .filter(Solve.user_id.in_(ids)).all()):
        xp[uid] += XP_BY_DIFFICULTY.get(difficulty, 25)
    standings_cache = {}
    for reg in _played_registrations(ids):
        xp[reg.user_id] += XP_PER_EVENT + XP_BY_PLACEMENT.get(_placement(reg, standings_cache), 0)
    return xp


def activity_xp(user):
    return activity_xp_bulk([user])[user.id]


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
    event_count = len(_played_registrations([user.id]))
    return {'score': score, 'solves': len(solves), 'xp': xp, 'events': event_count, 'this_month': this_m,
            'last_month': last_m, 'activity': activity, 'streak': streak, 'best_streak': best,
            'tier': tier_info(xp), 'level': level_info(xp), 'series': series,
            'hints': sum(1 for e in events if e[2] == 'hint')}
