"""Competition standings, placements, rank XP and net practice values."""

import os
import unittest
from datetime import timedelta

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app, db
import scoring
from models import (Challenge, Competition, CompetitionChallenge, CompetitionRegistration,
                    CompetitionSolve, Hint, HintDebit, HintUnlock, Solve, User, utcnow)


def make_user(name, **kw):
    return User(username=name, email=f'{name}@example.com', password_hash='x', is_verified=True, **kw)


class ScoringTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.ctx = app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.now = utcnow()
        self.alice, self.bob, self.carol = make_user('alice'), make_user('bob'), make_user('carol')
        self.admin = make_user('root', is_admin=True)
        self.ch1 = Challenge(title='A', description='a', category='Web', difficulty='Easy',
                             flag='SPARK{a}', value=100, visible=False)
        self.ch2 = Challenge(title='B', description='b', category='Crypto', difficulty='Hard',
                             flag='SPARK{b}', value=300, visible=False)
        self.event = Competition(title='Cup', description='', published=True,
                                 starts_at=self.now - timedelta(hours=3),
                                 ends_at=self.now - timedelta(hours=1))
        db.session.add_all([self.alice, self.bob, self.carol, self.admin, self.ch1, self.ch2, self.event])
        db.session.flush()
        db.session.add_all([
            CompetitionChallenge(competition_id=self.event.id, challenge_id=self.ch1.id, points=100),
            CompetitionChallenge(competition_id=self.event.id, challenge_id=self.ch2.id, points=300),
        ])
        for u in (self.alice, self.bob, self.carol, self.admin):
            db.session.add(CompetitionRegistration(competition_id=self.event.id, user_id=u.id,
                                                   participated=True))
        t = self.now - timedelta(hours=2)
        db.session.add_all([
            # bob and alice both reach 400; bob got there first, so bob is #1
            CompetitionSolve(competition_id=self.event.id, user_id=self.bob.id, challenge_id=self.ch1.id,
                             points=100, first_blood=True, created_at=t),
            CompetitionSolve(competition_id=self.event.id, user_id=self.bob.id, challenge_id=self.ch2.id,
                             points=300, first_blood=True, created_at=t + timedelta(minutes=10)),
            CompetitionSolve(competition_id=self.event.id, user_id=self.alice.id, challenge_id=self.ch1.id,
                             points=100, created_at=t + timedelta(minutes=5)),
            CompetitionSolve(competition_id=self.event.id, user_id=self.alice.id, challenge_id=self.ch2.id,
                             points=300, created_at=t + timedelta(minutes=20)),
            CompetitionSolve(competition_id=self.event.id, user_id=self.carol.id, challenge_id=self.ch1.id,
                             points=100, created_at=t + timedelta(minutes=30)),
            # admins play but never rank
            CompetitionSolve(competition_id=self.event.id, user_id=self.admin.id, challenge_id=self.ch1.id,
                             points=100, created_at=t + timedelta(minutes=1)),
        ])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_standings_rank_tiebreak_and_first_blood(self):
        rows = scoring.competition_standings(self.event)
        self.assertEqual([r['user'].username for r in rows], ['bob', 'alice', 'carol'])
        self.assertEqual([r['rank'] for r in rows], [1, 2, 3])
        self.assertEqual(rows[0]['first_bloods'], 2)
        self.assertEqual(rows[1]['first_bloods'], 0)
        self.assertEqual(rows[0]['solves'], 2)
        self.assertEqual(rows[2]['score'], 100)

    def test_finalize_placements_persists_once(self):
        self.assertTrue(scoring.finalize_placements(self.event))
        regs = {r.user_id: r.placement for r in CompetitionRegistration.query.all()}
        self.assertEqual(regs[self.bob.id], 1)
        self.assertEqual(regs[self.alice.id], 2)
        self.assertEqual(regs[self.carol.id], 3)
        self.assertIsNone(regs[self.admin.id])
        self.assertFalse(scoring.finalize_placements(self.event))

    def test_finalize_skips_live_events(self):
        self.event.ends_at = self.now + timedelta(hours=1)
        db.session.commit()
        self.assertFalse(scoring.finalize_placements(self.event))
        self.assertIsNone(CompetitionRegistration.query.filter_by(user_id=self.bob.id).first().placement)

    def test_competition_results_respects_profile_visibility(self):
        reg = CompetitionRegistration.query.filter_by(user_id=self.alice.id).first()
        reg.profile_visible = False
        db.session.commit()
        self.assertEqual(scoring.competition_results(self.alice), [])
        mine = scoring.competition_results(self.alice, include_hidden=True)
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]['placement'], 2)
        self.assertEqual(mine[0]['players'], 3)
        self.assertEqual(mine[0]['points'], 400)

    def test_activity_xp_bulk_matches_single_and_rewards_podium(self):
        db.session.add(Solve(user_id=self.carol.id, challenge_id=self.ch2.id))  # Hard = 100 XP
        db.session.commit()
        users = [self.alice, self.bob, self.carol]
        bulk = scoring.activity_xp_bulk(users)
        for u in users:
            self.assertEqual(bulk[u.id], scoring.activity_xp(u))
        self.assertEqual(bulk[self.bob.id], 100 + 150)      # played + 1st place
        self.assertEqual(bulk[self.alice.id], 100 + 100)    # played + 2nd place
        self.assertEqual(bulk[self.carol.id], 100 + 100 + 50)  # solve + played + 3rd

    def test_competition_points_never_reach_practice_score(self):
        self.assertEqual(scoring.user_score(self.bob), 0)
        self.assertEqual(scoring.standings()[0]['score'], 0)

    def test_earned_values_subtract_hint_paid_from_task_reward(self):
        ch = Challenge(title='P', description='p', category='Misc', difficulty='Easy',
                       flag='SPARK{p}', value=200, visible=True)
        db.session.add(ch)
        db.session.flush()
        hint = Hint(challenge_id=ch.id, content='psst', cost=50)
        db.session.add(hint)
        db.session.flush()
        db.session.add_all([
            HintUnlock(user_id=self.carol.id, hint_id=hint.id),
            HintDebit(user_id=self.carol.id, hint_id=hint.id, challenge_id=ch.id, amount=50,
                      source='challenge reward'),
            Solve(user_id=self.carol.id, challenge_id=ch.id),
        ])
        db.session.commit()
        self.assertEqual(scoring.earned_values(self.carol), {ch.id: 150})
        self.assertEqual(scoring.user_score(self.carol), 150)


if __name__ == '__main__':
    unittest.main()
