"""Smoke coverage for the practice and competition separation."""

import os
import unittest
from datetime import timedelta

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app, db
import scoring
from models import (Challenge, Competition, CompetitionChallenge, CompetitionRegistration,
                    CompetitionSolve, Solve, User, utcnow)


class CompetitionFlowTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.ctx = app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()

        user = User(username='tester', email='tester@example.com',
                    password_hash='test-hash', is_verified=True)
        future_ch = Challenge(title='UPCOMING_SECRET_TITLE', description='UPCOMING_SECRET_BODY',
                              category='Web', difficulty='Easy', flag='SPARK{future}',
                              value=100, visible=False)
        live_ch = Challenge(title='LIVE_SECRET_TITLE', description='LIVE_SECRET_BODY',
                            category='Crypto', difficulty='Medium', flag='SPARK{live}',
                            value=200, visible=False)
        now = utcnow()
        future = Competition(title='Upcoming', description='Public overview',
                             starts_at=now + timedelta(hours=1),
                             ends_at=now + timedelta(hours=2), published=True)
        live = Competition(title='Live', description='Public overview',
                           starts_at=now - timedelta(hours=1),
                           ends_at=now + timedelta(hours=1), published=True)
        db.session.add_all([user, future_ch, live_ch, future, live])
        db.session.flush()
        db.session.add_all([
            CompetitionChallenge(competition_id=future.id, challenge_id=future_ch.id, points=100),
            CompetitionChallenge(competition_id=live.id, challenge_id=live_ch.id, points=200),
        ])
        db.session.commit()
        self.user_id = user.id
        self.future_id, self.live_id = future.id, live.id
        self.future_ch_id, self.live_ch_id = future_ch.id, live_ch.id
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = user.get_id()
            sess['_fresh'] = True
            sess['_csrf'] = 'test-csrf'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_navigation_embargo_and_scoring(self):
        for path in ('/', '/dashboard', '/challenges', '/competitions', '/scoreboard'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        page = self.client.get('/competitions')
        self.assertIn(b'Musobaqalar', page.data)
        self.assertIn(b'/competitions', page.data)

        future_page = self.client.get(f'/competitions/{self.future_id}')
        self.assertEqual(future_page.status_code, 200)
        self.assertNotIn(b'UPCOMING_SECRET_TITLE', future_page.data)
        self.assertNotIn(b'UPCOMING_SECRET_BODY', future_page.data)
        self.assertNotIn(b'SPARK{future}', future_page.data)
        self.assertEqual(self.client.get(f'/api/challenges/{self.future_ch_id}').status_code, 404)
        self.assertEqual(self.client.post(
            f'/competitions/{self.future_id}/submit/{self.future_ch_id}',
            data={'csrf_token': 'test-csrf', 'flag': 'SPARK{future}'}).status_code, 302)
        self.assertEqual(CompetitionSolve.query.count(), 0)

        live_page = self.client.get(f'/competitions/{self.live_id}')
        self.assertEqual(live_page.status_code, 200)
        self.assertNotIn(b'LIVE_SECRET_BODY', live_page.data)
        self.assertNotIn(b'SPARK{live}', live_page.data)
        self.assertEqual(self.client.post(
            f'/competitions/{self.live_id}/submit/{self.live_ch_id}',
            data={'csrf_token': 'test-csrf', 'flag': 'SPARK{live}'}).status_code, 403)
        registered = self.client.post(f'/competitions/{self.live_id}/register',
                                      data={'csrf_token': 'test-csrf'})
        self.assertEqual(registered.status_code, 302)
        self.assertIn(b'LIVE_SECRET_BODY', self.client.get(f'/competitions/{self.live_id}').data)
        self.assertEqual(self.client.post(
            f'/competitions/{self.live_id}/submit/{self.live_ch_id}',
            data={'flag': 'SPARK{live}'}).status_code, 400)

        solved = self.client.post(f'/competitions/{self.live_id}/submit/{self.live_ch_id}',
                                  data={'csrf_token': 'test-csrf', 'flag': 'SPARK{live}'})
        self.assertEqual(solved.status_code, 302)
        self.assertEqual(CompetitionSolve.query.count(), 1)
        self.assertEqual(Solve.query.count(), 0)
        self.assertEqual(scoring.user_score(db.session.get(User, self.user_id)), 0)
        self.assertTrue(CompetitionRegistration.query.filter_by(
            competition_id=self.live_id, user_id=self.user_id).first().participated)
        self.assertEqual(self.client.get(f'/api/challenges/{self.live_ch_id}').status_code, 404)


if __name__ == '__main__':
    unittest.main()
