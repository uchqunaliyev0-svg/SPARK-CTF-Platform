# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False) # Parolning hash versiyasi saqlanadi
    score = db.Column(db.Integer, default=0) # CTF platformasi uchun ballar tizimi
    is_admin = db.Column(db.Boolean, default=False) # Adminlarni aniqlash uchun

    def __repr__(self):
        return f"<User {self.username}>"

class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=False) # Web, Crypto, RE, etc.
    difficulty = db.Column(db.String(50), nullable=False) # Easy, Medium, Hard
    flag = db.Column(db.String(200), nullable=False) # Javob kaliti
    points = db.Column(db.Integer, nullable=False) # Beriladigan ball
    file_url = db.Column(db.String(500), nullable=True) # Fayl yuklab olish kerak bo'lsa
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Challenge {self.title}>"

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenge.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('submissions', lazy=True))
    challenge = db.relationship('Challenge', backref=db.backref('submissions', lazy=True))

    def __repr__(self):
        return f"<Submission User:{self.user_id} Challenge:{self.challenge_id}>"
