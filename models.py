# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False) # Parolning hash versiyasi saqlanadi
    score = db.Column(db.Integer, default=0) # CTF platformasi uchun ballar tizimi

    def __repr__(self):
        return f"<User {self.username}>"
