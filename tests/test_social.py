"""Google / Telegram sign-in: signature checks, account creation, linking and bans."""

import hashlib
import hmac
import os
import time
import unittest
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ['GOOGLE_CLIENT_ID'] = 'gid'
os.environ['GOOGLE_CLIENT_SECRET'] = 'gsecret'
os.environ['TELEGRAM_BOT_TOKEN'] = '123456:ABCDEF'
os.environ['TELEGRAM_BOT_USERNAME'] = 'spark_test_bot'

import app as app_module
from app import app, db
import social
from models import SocialAccount, User

BOT_TOKEN = '123456:ABCDEF'


def signed_telegram(**fields):
    data = {'id': '777', 'first_name': 'Ali', 'username': 'ali_tg', 'auth_date': str(int(time.time()))}
    data.update(fields)
    check = '\n'.join(f'{k}={data[k]}' for k in sorted(data))
    secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
    data['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return data


class SocialTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['RATE_LIMIT'] = False
        self.ctx = app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess['_csrf'] = 't'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def logged_in_user(self):
        with self.client.session_transaction() as sess:
            uid = sess.get('_user_id')
        return db.session.get(User, int(uid.split(':')[0])) if uid else None

    def test_telegram_signature_verification(self):
        self.assertEqual(social.telegram_profile(signed_telegram())['id'], '777')
        bad = signed_telegram()
        bad['username'] = 'someone_else'
        with self.assertRaises(social.SocialError):
            social.telegram_profile(bad)
        old = signed_telegram(auth_date=str(int(time.time()) - 3600))
        with self.assertRaises(social.SocialError):
            social.telegram_profile(old)

    def test_telegram_login_creates_then_reuses_account(self):
        r = self.client.post('/auth/telegram', data={'csrf_token': 't', **signed_telegram()})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers['Location'].endswith('/dashboard'))
        user = User.query.one()
        self.assertEqual(user.username, 'ali_tg')
        self.assertTrue(user.is_verified)
        self.assertEqual(SocialAccount.query.one().provider_id, '777')
        self.client.post('/logout', data={'csrf_token': self.client.get_cookie('session') and 't'})
        with self.client.session_transaction() as sess:
            sess.clear()
            sess['_csrf'] = 't'
        self.client.post('/auth/telegram', data={'csrf_token': 't', **signed_telegram()})
        self.assertEqual(User.query.count(), 1)
        self.assertEqual(self.logged_in_user().id, user.id)

    def test_telegram_requires_csrf_and_valid_hash(self):
        self.assertEqual(self.client.post('/auth/telegram', data=signed_telegram()).status_code, 400)
        forged = signed_telegram()
        forged['id'] = '1'
        r = self.client.post('/auth/telegram', data={'csrf_token': 't', **forged})
        self.assertTrue(r.headers['Location'].endswith('/login'))
        self.assertEqual(User.query.count(), 0)

    def test_google_state_and_email_match_links_existing_user(self):
        existing = User(username='alice', email='alice@gmail.com', password_hash='x', is_verified=False)
        db.session.add(existing)
        db.session.commit()
        r = self.client.get('/auth/google')
        self.assertIn('accounts.google.com', r.headers['Location'])
        with self.client.session_transaction() as sess:
            state = sess['oauth_state']
        # wrong state is refused before any network call
        r = self.client.get('/auth/google/callback?state=nope&code=c')
        self.assertTrue(r.headers['Location'].endswith('/login'))
        self.client.get('/auth/google')
        with self.client.session_transaction() as sess:
            state = sess['oauth_state']
        profile = {'id': 'g-1', 'email': 'alice@gmail.com', 'name': 'Alice'}
        with mock.patch.object(app_module, 'google_profile', return_value=profile):
            r = self.client.get(f'/auth/google/callback?state={state}&code=c')
        self.assertTrue(r.headers['Location'].endswith('/dashboard'))
        self.assertEqual(User.query.count(), 1)
        self.assertEqual(self.logged_in_user().id, existing.id)
        self.assertTrue(db.session.get(User, existing.id).is_verified)
        self.assertEqual(SocialAccount.query.one().user_id, existing.id)

    def test_banned_user_cannot_social_login(self):
        banned = User(username='bad', email='bad@gmail.com', password_hash='x', is_verified=True, is_banned=True)
        db.session.add(banned)
        db.session.commit()
        self.client.get('/auth/google')
        with self.client.session_transaction() as sess:
            state = sess['oauth_state']
        with mock.patch.object(app_module, 'google_profile',
                               return_value={'id': 'g-2', 'email': 'bad@gmail.com', 'name': ''}):
            r = self.client.get(f'/auth/google/callback?state={state}&code=c')
        self.assertTrue(r.headers['Location'].endswith('/login'))
        self.assertIsNone(self.logged_in_user())
        self.assertEqual(SocialAccount.query.count(), 0)

    def test_username_collision_gets_suffix(self):
        db.session.add(User(username='ali_tg', email='x@x.com', password_hash='x', is_verified=True))
        db.session.commit()
        self.client.post('/auth/telegram', data={'csrf_token': 't', **signed_telegram()})
        self.assertEqual(self.logged_in_user().username, 'ali_tg2')

    def test_login_page_shows_buttons(self):
        page = self.client.get('/login').data
        self.assertIn(b'/auth/google', page)
        self.assertIn(b'data-telegram-login="123456"', page)


if __name__ == '__main__':
    unittest.main()
