"""Achievement badges, derived from existing data on every read (nothing is stored).

Adding a badge = one entry in BADGES plus, if needed, one more fact in _facts()."""

from collections import defaultdict
from datetime import timedelta

from models import Challenge, CompetitionSolve, Solve, db
import scoring

# key, name, description, icon, colour, test(facts) -> bool
BADGES = [
    ('first_flag', 'Birinchi flag', 'Birinchi topshiriqni yeching', 'flag', '#22d3ee',
     lambda f: f['solves'] >= 1),
    ('flags_10', 'Faol xaker', '10 ta topshiriq yeching', 'target', '#34d399',
     lambda f: f['solves'] >= 10),
    ('flags_50', 'Tajribali xaker', '50 ta topshiriq yeching', 'trophy', '#a78bfa',
     lambda f: f['solves'] >= 50),
    ('all_rounder', 'Har tomonlama', 'Har bir kategoriyadan kamida bitta topshiriq yeching', 'grid', '#60a5fa',
     lambda f: f['categories_total'] > 0 and f['categories_touched'] >= f['categories_total']),
    ('category_master', 'Kategoriya ustasi', 'Bitta kategoriyadagi barcha topshiriqlarni yeching', 'award', '#fbbf24',
     lambda f: f['categories_completed'] >= 1),
    ('hard_10', 'Qo‘rqmas', '10 ta Hard yoki Insane topshiriq yeching', 'fire', '#ff3b5c',
     lambda f: f['hard'] >= 10),
    ('insane', 'Insane', 'Insane topshiriq yeching', 'zap', '#f472b6',
     lambda f: f['insane'] >= 1),
    ('streak_7', '7 kunlik seriya', '7 kun ketma-ket topshiriq yeching', 'fire', '#fb923c',
     lambda f: f['best_streak'] >= 7),
    ('competitor', 'Musobaqa ishtirokchisi', 'Rasmiy musobaqada qatnashing', 'trophy', '#94a3b8',
     lambda f: f['events'] >= 1),
    ('first_blood', 'First blood', 'Musobaqada topshiriqni birinchi bo‘lib yeching', 'drop', '#ef4444',
     lambda f: f['first_bloods'] >= 1),
    ('podium', 'Sovrindor', 'Musobaqada top-3 ga kiring', 'award', '#cbd5e1',
     lambda f: f['best_place'] is not None and f['best_place'] <= 3),
    ('champion', 'Chempion', 'Musobaqada 1-o‘rinni oling', 'crown', '#fcd34d',
     lambda f: f['best_place'] == 1),
]


def _best_streak(days):
    best = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best, prev = max(best, run), d
    return best


def _facts(user_ids, category_totals):
    """Per-user numbers every badge test reads. category_totals: {category: practice task count}."""
    facts = {uid: {'solves': 0, 'hard': 0, 'insane': 0, 'categories_touched': 0,
                   'categories_completed': 0, 'best_streak': 0, 'events': 0,
                   'first_bloods': 0, 'best_place': None,
                   'categories_total': sum(1 for n in category_totals.values() if n)}
             for uid in user_ids}
    if not user_ids:
        return facts
    per_cat = defaultdict(lambda: defaultdict(int))
    days = defaultdict(set)
    for uid, cat, diff, at in (db.session.query(Solve.user_id, Challenge.category, Challenge.difficulty,
                                                Solve.created_at)
                               .join(Challenge, Challenge.id == Solve.challenge_id)
                               .filter(Solve.user_id.in_(user_ids)).all()):
        f = facts[uid]
        f['solves'] += 1
        f['hard'] += diff in ('Hard', 'Insane')
        f['insane'] += diff == 'Insane'
        per_cat[uid][cat] += 1
        days[uid].add(at.date())
    for uid, cats in per_cat.items():
        facts[uid]['categories_touched'] = sum(1 for c, n in category_totals.items() if n and cats.get(c))
        facts[uid]['categories_completed'] = sum(1 for c, n in category_totals.items()
                                                 if n and cats.get(c, 0) >= n)
    for uid, ds in days.items():
        facts[uid]['best_streak'] = _best_streak(ds)
    cache = {}
    for reg in scoring._played_registrations(user_ids):
        f = facts[reg.user_id]
        f['events'] += 1
        place = scoring._placement(reg, cache)
        if place is not None and (f['best_place'] is None or place < f['best_place']):
            f['best_place'] = place
    for uid, n in (db.session.query(CompetitionSolve.user_id, db.func.count(CompetitionSolve.id))
                   .filter(CompetitionSolve.user_id.in_(user_ids), CompetitionSolve.first_blood.is_(True))
                   .group_by(CompetitionSolve.user_id).all()):
        facts[uid]['first_bloods'] = n
    return facts


def badges_bulk(users, category_totals):
    """{user_id: [badge dict, ...]} with every badge and an `earned` flag."""
    facts = _facts([u.id for u in users], category_totals)
    out = {}
    for uid, f in facts.items():
        out[uid] = [{'key': k, 'name': name, 'desc': desc, 'icon': ic, 'color': col, 'earned': bool(test(f))}
                    for k, name, desc, ic, col, test in BADGES]
    return out


def badges(user, category_totals):
    return badges_bulk([user], category_totals)[user.id]
