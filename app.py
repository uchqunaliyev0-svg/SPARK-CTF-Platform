# app.py
from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, User
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

app = Flask(__name__)

# Xavfsizlik kaliti (Sessiyalar uchun)
app.config['SECRET_KEY'] = 'super-secret-ctf-key-2026' 
# Ma'lumotlar bazasi sifatida Supabase (PostgreSQL) ishlatamiz
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.bwiusxkzvrhybnllfhnb:%23qunbek6141@aws-1-ap-south-1.pooler.supabase.com:5432/postgres'

# Kutubxonalarni ilova bilan bog'lash
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Dastur ishga tushganda ma'lumotlar bazasini (jadvallarni) yaratish
with app.app_context():
    db.create_all()

@app.route('/', methods=['GET', 'POST'])
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard')) # Tizimga kirgan bo'lsa to'g'ridan-to'g'ri o'yin/dashboard qismiga
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    # Parolni tekshirish
    if user and bcrypt.check_password_hash(user.password, password):
        login_user(user)
        return redirect(url_for('dashboard'))
    else:
        # Xato bo'lsa xabar berish
        flash("Login yoki parol noto'g'ri. Qaytadan urinib ko'ring.", "error")
        return redirect(url_for('home'))

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    
    # Bandligini tekshirish
    if User.query.filter_by(username=username).first():
        flash("Bu login (username) band, boshqasini tanlang.", "error")
        return redirect(url_for('home'))
        
    if User.query.filter_by(email=email).first():
        flash("Bu email ro'yxatdan o'tgan.", "error")
        return redirect(url_for('home'))
        
    # Parolni heshlab saqlash
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user = User(username=username, email=email, password=hashed_pw)
    
    db.session.add(new_user)
    db.session.commit()
    
    flash("Muvaffaqiyatli ro'yxatdan o'tdingiz! Endi tizimga kiring.", "success")
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True, port=8080)
