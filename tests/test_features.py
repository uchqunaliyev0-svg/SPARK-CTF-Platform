"""Leaderboard periods, achievements, certificates, event editing, channel posts and VPN."""

import base64
import os
import unittest
from datetime import timedelta
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

import app as app_module
from app import app, db
import achievements
import scoring
import vpn
from models import (Certificate, Challenge, Competition, CompetitionChallenge, CompetitionRegistration,
                    CompetitionSolve, Solve, User, VpnPeer, utcnow)


def user(name, **kw):
    return User(username=name, email=f'{name}@example.com', password_hash='x', is_verified=True, **kw)


class Base(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.ctx = app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.now = utcnow()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def login(self, u):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = u.get_id()
            sess['_fresh'] = True
            sess['_csrf'] = 't'


class LeaderboardTest(Base):
    def test_period_board_only_counts_recent_solves(self):
        old, new = user('oldtimer'), user('newbie')
        c1 = Challenge(title='a', description='a', category='Web', difficulty='Easy', flag='f', value=500)
        c2 = Challenge(title='b', description='b', category='Web', difficulty='Easy', flag='g', value=100)
        db.session.add_all([old, new, c1, c2])
        db.session.flush()
        db.session.add_all([
            Solve(user_id=old.id, challenge_id=c1.id, created_at=self.now - timedelta(days=40)),
            Solve(user_id=new.id, challenge_id=c2.id, created_at=self.now - timedelta(days=2)),
        ])
        db.session.commit()
        self.assertEqual([r['user'].username for r in scoring.standings()], ['oldtimer', 'newbie'])
        week = scoring.standings(self.now - timedelta(days=7))
        self.assertEqual([r['user'].username for r in week], ['newbie'])
        self.login(new)
        page = self.client.get('/scoreboard?period=week').data.decode()
        self.assertIn('newbie', page)
        self.assertNotIn('oldtimer', page)
        self.assertEqual(self.client.get('/scoreboard?period=bogus').status_code, 200)


class AchievementTest(Base):
    def test_badges_follow_solves(self):
        u = user('ach')
        chs = [Challenge(title=f'c{i}', description='d', category=cat, difficulty=diff, flag='f', value=10)
               for i, (cat, diff) in enumerate([('Web', 'Easy'), ('Crypto', 'Insane')])]
        db.session.add_all([u, *chs])
        db.session.flush()
        for i, c in enumerate(chs):
            db.session.add(Solve(user_id=u.id, challenge_id=c.id, created_at=self.now - timedelta(days=i)))
        db.session.commit()
        got = {b['key']: b['earned'] for b in achievements.badges(u, {'Web': 1, 'Crypto': 1, 'Pwn': 0})}
        self.assertTrue(got['first_flag'])
        self.assertTrue(got['all_rounder'])       # Pwn has no challenges, so it does not count
        self.assertTrue(got['category_master'])
        self.assertTrue(got['insane'])
        self.assertFalse(got['flags_10'])
        self.assertFalse(got['streak_7'])
        self.assertFalse(got['competitor'])


class CertificateAndEventTest(Base):
    def setUp(self):
        super().setUp()
        self.admin = user('root', is_admin=True)
        self.players = [user(n) for n in ('p1', 'p2', 'p3', 'p4')]
        self.ch = Challenge(title='E', description='e', category='Pwn', difficulty='Hard', flag='F', value=300,
                            visible=False)
        self.event = Competition(title='Cup', description='', published=True,
                                 starts_at=self.now - timedelta(hours=3), ends_at=self.now - timedelta(hours=1))
        db.session.add_all([self.admin, *self.players, self.ch, self.event])
        db.session.flush()
        db.session.add(CompetitionChallenge(competition_id=self.event.id, challenge_id=self.ch.id, points=300))
        for i, p in enumerate(self.players):
            db.session.add(CompetitionRegistration(competition_id=self.event.id, user_id=p.id, participated=True))
            db.session.add(CompetitionSolve(competition_id=self.event.id, user_id=p.id, challenge_id=self.ch.id,
                                            points=300, first_blood=i == 0,
                                            created_at=self.now - timedelta(hours=2, minutes=-i)))
        db.session.commit()

    def test_podium_certificates_and_revocation(self):
        scoring.finalize_placements(self.event)
        certs = {c.user.username: c for c in Certificate.query.all()}
        self.assertEqual(sorted(certs), ['p1', 'p2', 'p3'])
        self.assertEqual(certs['p1'].placement, 1)
        self.assertEqual(certs['p1'].players, 4)
        page = self.client.get(f"/certificates/{certs['p2'].code}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'p2', page.data)
        # disqualify the winner: everyone moves up, p1's certificate is revoked, p4 gets one
        self.players[0].is_banned = True
        db.session.commit()
        scoring.finalize_placements(self.event)
        certs = {c.user.username: c for c in Certificate.query.all()}
        self.assertTrue(certs['p1'].revoked)
        self.assertEqual(certs['p2'].placement, 1)
        self.assertEqual(certs['p4'].placement, 3)
        self.assertIn('bekor'.encode(), self.client.get(f"/certificates/{certs['p1'].code}").data)
        self.assertEqual(self.client.get('/certificates/NOPE').status_code, 404)

    def test_profile_links_certificate(self):
        self.login(self.players[1])
        page = self.client.get('/users/p2').data.decode()
        self.assertIn('/certificates/SPK-', page)

    def test_admin_edits_by_state(self):
        self.login(self.admin)
        # ended: title changes, times do not
        before = (self.event.starts_at, self.event.ends_at)
        r = self.client.post(f'/admin/competitions/{self.event.id}/edit',
                             data={'csrf_token': 't', 'title': 'Cup 2026', 'description': 'd', 'prize': '1M',
                                   'starts_at': '2030-01-01T00:00:00Z', 'ends_at': '2030-01-02T00:00:00Z'})
        self.assertEqual(r.status_code, 302)
        ev = db.session.get(Competition, self.event.id)
        self.assertEqual(ev.title, 'Cup 2026')
        self.assertEqual((ev.starts_at, ev.ends_at), before)
        # upcoming: new event with custom points, then edit points and challenge set
        spare = Challenge(title='S', description='s', category='Web', difficulty='Easy', flag='S', value=50,
                          visible=False)
        db.session.add(spare)
        db.session.commit()
        start = (self.now + timedelta(days=1)).isoformat() + 'Z'
        end = (self.now + timedelta(days=2)).isoformat() + 'Z'
        r = self.client.post('/admin/competitions/new', data={
            'csrf_token': 't', 'title': 'Next', 'starts_at': start, 'ends_at': end,
            'challenge_ids': [str(spare.id)], f'points_{spare.id}': '420'})
        self.assertEqual(r.status_code, 302)
        nxt = Competition.query.filter_by(title='Next').one()
        self.assertEqual(nxt.challenges[0].points, 420)
        self.assertFalse(nxt.published)
        r = self.client.post(f'/admin/competitions/{nxt.id}/edit', data={
            'csrf_token': 't', 'title': 'Next', 'starts_at': start, 'ends_at': end,
            'challenge_ids': [str(spare.id)], f'points_{spare.id}': '99999'})
        self.assertEqual(db.session.get(Competition, nxt.id).challenges[0].points, 420)  # rejected
        self.assertEqual(self.client.get(f'/admin/competitions/{nxt.id}/edit').status_code, 200)

    def test_publish_posts_to_channel(self):
        self.login(self.admin)
        ev = Competition(title='Soon', description='', published=False,
                         starts_at=self.now + timedelta(days=1), ends_at=self.now + timedelta(days=2))
        spare = Challenge(title='S2', description='s', category='Web', difficulty='Easy', flag='S', value=50,
                          visible=False)
        db.session.add_all([ev, spare])
        db.session.flush()
        db.session.add(CompetitionChallenge(competition_id=ev.id, challenge_id=spare.id, points=50))
        db.session.commit()
        with mock.patch.object(app_module.notify, 'post', return_value=True) as post:
            self.client.post(f'/admin/competitions/{ev.id}/publish', data={'csrf_token': 't'})
        self.assertTrue(db.session.get(Competition, ev.id).published)
        post.assert_called_once()
        self.assertIn('Soon', post.call_args[0][0])


class VpnTest(Base):
    env = {'VPN_ENDPOINT': 'vpn.example:51820', 'VPN_SERVER_PUBLIC_KEY': 'c2VydmVy', 'VPN_SYNC_TOKEN': 'sync'}

    def test_config_download_and_peer_sync(self):
        u, banned = user('vpnuser'), user('gone', is_banned=True)
        db.session.add_all([u, banned])
        db.session.commit()
        self.login(u)
        self.assertEqual(self.client.post('/vpn/config', data={'csrf_token': 't'}).status_code, 404)
        with mock.patch.dict(os.environ, self.env):
            r = self.client.post('/vpn/config', data={'csrf_token': 't'})
            self.assertEqual(r.status_code, 200)
            conf = r.data.decode()
            self.assertIn('Endpoint = vpn.example:51820', conf)
            self.assertIn('Address = 10.13.0.2/32', conf)
            private = conf.split('PrivateKey = ')[1].split('\n')[0]
            peer = VpnPeer.query.one()
            derived = base64.b64encode(vpn.x25519(base64.b64decode(private), (9).to_bytes(32, 'little'))).decode()
            self.assertEqual(peer.public_key, derived)   # server gets the matching public key only
            self.assertNotIn(private, peer.public_key)
            db.session.add(VpnPeer(user_id=banned.id, public_key='x'))
            db.session.commit()
            self.assertEqual(self.client.get('/vpn/peers.conf').status_code, 404)
            peers = self.client.get('/vpn/peers.conf', headers={'Authorization': 'Bearer sync'}).data.decode()
            self.assertIn(peer.public_key, peers)
            self.assertNotIn('# gone', peers)
            self.assertIn('10.13.0.2', self.client.get('/vpn').data.decode())


class PagesTest(Base):
    def test_main_pages_render(self):
        u = user('viewer')
        c = Challenge(title='Visible', description='d', category='Crypto', difficulty='Easy', flag='f', value=10)
        db.session.add_all([u, c])
        db.session.commit()
        self.login(u)
        for path in ('/dashboard', '/challenges', '/challenges?cat=Crypto', '/scoreboard', '/users/viewer',
                     '/vpn', '/settings', '/competitions'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        page = self.client.get('/challenges').data.decode()
        self.assertIn('data-open-cat="Crypto"', page)


if __name__ == '__main__':
    unittest.main()
