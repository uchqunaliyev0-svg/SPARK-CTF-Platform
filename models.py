from datetime import datetime, timezone

import hashlib
import hmac

from flask import current_app
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    failed_logins = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def session_stamp(self):
        """Short HMAC of the password hash: changes whenever the password does."""
        key = (current_app.config.get('SECRET_KEY') or '').encode()
        return hmac.new(key, (self.password_hash or '').encode(), hashlib.sha256).hexdigest()[:16]

    def get_id(self):
        return f'{self.id}:{self.session_stamp()}'


class EmailCode(db.Model):
    __tablename__ = 'email_codes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    purpose = db.Column(db.String(16), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Challenge(db.Model):
    __tablename__ = 'challenges'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False)
    difficulty = db.Column(db.String(16), nullable=False)
    author = db.Column(db.String(60), nullable=True)
    flag = db.Column(db.String(255), nullable=False)
    case_insensitive = db.Column(db.Boolean, default=False, nullable=False)
    value = db.Column(db.Integer, nullable=False)
    dynamic = db.Column(db.Boolean, default=False, nullable=False)
    minimum = db.Column(db.Integer, nullable=True)
    decay = db.Column(db.Integer, nullable=True)
    files = db.Column(db.Text, nullable=True)
    visible = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    hints = db.relationship('Hint', backref='challenge', cascade='all, delete-orphan',
                            order_by='Hint.position')

    @property
    def file_list(self):
        return [f.strip() for f in (self.files or '').splitlines() if f.strip()]


class Hint(db.Model):
    __tablename__ = 'hints'
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id', ondelete='CASCADE'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Integer, default=0, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)

    unlocks = db.relationship('HintUnlock', backref='hint', cascade='all, delete-orphan')


class HintUnlock(db.Model):
    __tablename__ = 'hint_unlocks'
    __table_args__ = (db.UniqueConstraint('user_id', 'hint_id'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    hint_id = db.Column(db.Integer, db.ForeignKey('hints.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Solve(db.Model):
    __tablename__ = 'solves'
    __table_args__ = (db.UniqueConstraint('user_id', 'challenge_id'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship('User')
    challenge = db.relationship('Challenge')


class Attempt(db.Model):
    __tablename__ = 'attempts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id', ondelete='CASCADE'), nullable=False)
    submission = db.Column(db.String(255), nullable=False)
    correct = db.Column(db.Boolean, nullable=False)
    ip = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    user = db.relationship('User')
    challenge = db.relationship('Challenge')


class Announcement(db.Model):
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Setting(db.Model):
    __tablename__ = 'settings'
    key = db.Column(db.String(40), primary_key=True)
    value = db.Column(db.Text, nullable=True)


class Competition(db.Model):
    __tablename__ = 'competitions'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default='')
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    ends_at = db.Column(db.DateTime, nullable=False, index=True)
    prize = db.Column(db.String(240), nullable=True)
    published = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    challenges = db.relationship('CompetitionChallenge', backref='competition',
                                  cascade='all, delete-orphan', order_by='CompetitionChallenge.position')
    registrations = db.relationship('CompetitionRegistration', backref='competition',
                                    cascade='all, delete-orphan')

    @property
    def state(self):
        now = utcnow()
        if now < self.starts_at:
            return 'upcoming'
        if now < self.ends_at:
            return 'live'
        return 'ended'


class CompetitionChallenge(db.Model):
    __tablename__ = 'competition_challenges'
    __table_args__ = (db.UniqueConstraint('competition_id', 'challenge_id'),)
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competitions.id', ondelete='CASCADE'), nullable=False, index=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id', ondelete='CASCADE'), nullable=False, index=True)
    points = db.Column(db.Integer, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)
    challenge = db.relationship('Challenge')


class CompetitionRegistration(db.Model):
    __tablename__ = 'competition_registrations'
    __table_args__ = (db.UniqueConstraint('competition_id', 'user_id'),)
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competitions.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    participated = db.Column(db.Boolean, default=False, nullable=False)
    placement = db.Column(db.Integer, nullable=True)
    profile_visible = db.Column(db.Boolean, default=True, nullable=False)
    registered_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    user = db.relationship('User')


class CompetitionSolve(db.Model):
    __tablename__ = 'competition_solves'
    __table_args__ = (db.UniqueConstraint('competition_id', 'user_id', 'challenge_id'),)
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competitions.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id', ondelete='CASCADE'), nullable=False, index=True)
    points = db.Column(db.Integer, nullable=False)
    first_blood = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    user = db.relationship('User')
    challenge = db.relationship('Challenge')


class CompetitionAttempt(db.Model):
    __tablename__ = 'competition_attempts'
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competitions.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id', ondelete='CASCADE'), nullable=False)
    correct = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)


class HintDebit(db.Model):
    """Immutable snapshot of the source and amount used to unlock a paid hint."""
    __tablename__ = 'hint_debits'
    __table_args__ = (db.UniqueConstraint('user_id', 'hint_id'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    hint_id = db.Column(db.Integer, db.ForeignKey('hints.id', ondelete='CASCADE'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id', ondelete='CASCADE'), nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(16), nullable=False)  # balance or challenge reward
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class RateHit(db.Model):
    """One row per rate-limited event (failed login, signup, reset request...) keyed by bucket+IP."""
    __tablename__ = 'rate_hits'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(90), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)


class CaptchaUse(db.Model):
    __tablename__ = 'captcha_uses'
    sig = db.Column(db.String(64), primary_key=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
