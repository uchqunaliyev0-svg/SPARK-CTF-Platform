from datetime import datetime, timezone

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
