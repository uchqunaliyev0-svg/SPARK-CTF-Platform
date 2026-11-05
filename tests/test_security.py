"""Security hardening tests — PortSwigger Academy guidelines compliance."""

import json
import os
import unittest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app, db
from models import User, utcnow
from security import password_problem, _json_depth, MAX_JSON_DEPTH, sanitize_filename


def user(name, **kw):
    return User(username=name, email=f'{name}@example.com', password_hash='x', is_verified=True, **kw)


class Base(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['RATE_LIMIT'] = False
        self.ctx = app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
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


class PasswordPolicyTest(Base):
    def test_rejects_short_password(self):
        self.assertIsNotNone(password_problem('Ab1!xyz'))

    def test_rejects_no_uppercase(self):
        self.assertIsNotNone(password_problem('abcd1234!'))

    def test_rejects_no_lowercase(self):
        self.assertIsNotNone(password_problem('ABCD1234!'))

    def test_rejects_no_digit(self):
        self.assertIsNotNone(password_problem('Abcdefgh!'))

    def test_rejects_no_special(self):
        self.assertIsNotNone(password_problem('Abcd1234'))

    def test_rejects_common_password(self):
        # 'p@ssw0rd' is in COMMON_PASSWORDS; adding caps/special to pass other checks
        # but the common-list check uses .lower() so 'P@ssw0rd' matches 'p@ssw0rd'
        self.assertIsNotNone(password_problem('P@ssw0rd'))

    def test_accepts_strong_password(self):
        self.assertIsNone(password_problem('Str0ng!Pass#99'))

    def test_rejects_too_long(self):
        self.assertIsNotNone(password_problem('A1!' + 'a' * 130))


class CookieSameSiteTest(Base):
    def test_session_cookie_is_strict(self):
        self.assertEqual(app.config['SESSION_COOKIE_SAMESITE'], 'Strict')

    def test_remember_cookie_is_strict(self):
        self.assertEqual(app.config['REMEMBER_COOKIE_SAMESITE'], 'Strict')


class JsonDepthTest(Base):
    def test_shallow_json_ok(self):
        self.assertLessEqual(_json_depth({'a': 1}), MAX_JSON_DEPTH)

    def test_deep_json_rejected(self):
        deep = {'a': {'b': {'c': {'d': {'e': 'too deep'}}}}}
        self.assertGreater(_json_depth(deep), MAX_JSON_DEPTH)

    def test_deep_json_request_blocked(self):
        deep = {'a': {'b': {'c': {'d': {'e': 'too deep'}}}}}
        with self.client as c:
            with c.session_transaction() as sess:
                sess['_csrf'] = 't'
            resp = c.post('/api/captcha', data=json.dumps(deep),
                         content_type='application/json',
                         headers={'X-CSRF-Token': 't'})
            self.assertIn(resp.status_code, [400, 405])


class SecurityHeadersTest(Base):
    def test_headers_present(self):
        resp = self.client.get('/')
        self.assertEqual(resp.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(resp.headers.get('X-Frame-Options'), 'DENY')
        self.assertIn('strict-origin', resp.headers.get('Referrer-Policy', ''))
        self.assertIn("default-src 'self'", resp.headers.get('Content-Security-Policy', ''))
        self.assertEqual(resp.headers.get('Cross-Origin-Opener-Policy'), 'same-origin')

    def test_cache_headers_for_authenticated(self):
        u = user('tester')
        db.session.add(u)
        db.session.commit()
        self.login(u)
        resp = self.client.get('/dashboard')
        self.assertIn('no-store', resp.headers.get('Cache-Control', ''))
        self.assertEqual(resp.headers.get('Pragma'), 'no-cache')


class CSRFTest(Base):
    def test_post_without_csrf_rejected(self):
        resp = self.client.post('/logout')
        self.assertEqual(resp.status_code, 400)

    def test_post_with_csrf_accepted(self):
        with self.client.session_transaction() as sess:
            sess['_csrf'] = 'test-token'
        resp = self.client.post('/logout', data={'csrf_token': 'test-token'})
        self.assertIn(resp.status_code, [302, 200])


class UsernameEnumerationTest(Base):
    def test_login_error_is_generic(self):
        with self.client.session_transaction() as sess:
            sess['_csrf'] = 't'
        resp = self.client.post('/login', data={
            'identity': 'nonexistent_user',
            'password': 'WrongPass1!',
            'csrf_token': 't',
            'captcha': 'fake',
        })
        self.assertNotIn(b'Bu username topilmadi', resp.data)
        self.assertNotIn(b'username mavjud emas', resp.data)


class FilenameSanitizeTest(Base):
    def test_path_traversal_stripped(self):
        result = sanitize_filename('../../../etc/passwd')
        self.assertNotIn('/', result)
        self.assertFalse(result.startswith('..'))
        self.assertNotIn('/../', result)

    def test_normal_name_preserved(self):
        self.assertEqual(sanitize_filename('user_123'), 'user_123')

    def test_empty_fallback(self):
        self.assertEqual(sanitize_filename(''), 'file')


if __name__ == '__main__':
    unittest.main()
