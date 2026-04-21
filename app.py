# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from models import db, User, Challenge, Submission
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
    challenges = Challenge.query.order_by(Challenge.created_at.desc()).all()
    # Foydalanuvchi yechgan masalalar ID lari
    solved_subs = Submission.query.filter_by(user_id=current_user.id).all()
    solved_ids = [sub.challenge_id for sub in solved_subs]
    
    return render_template('dashboard.html', challenges=challenges, solved_ids=solved_ids)

@app.route('/leaderboard')
@login_required
def leaderboard():
    # Eng yuqori ball to'plagan foydalanuvchilar (kuchli 50 talik)
    top_users = User.query.order_by(User.score.desc()).limit(50).all()
    return render_template('leaderboard.html', top_users=top_users)

@app.route('/api/submit', methods=['POST'])
@login_required
def submit_flag():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Ma'lumot yuborilmadi"}), 400
        
    challenge_id = data.get('challenge_id')
    flag = data.get('flag')
    
    challenge = Challenge.query.get(challenge_id)
    if not challenge:
        return jsonify({"status": "error", "message": "Masala topilmadi!"}), 404
        
    # Oldin yechilganligini tekshirish
    existing_sub = Submission.query.filter_by(user_id=current_user.id, challenge_id=challenge.id).first()
    if existing_sub:
        return jsonify({"status": "error", "message": "Siz bu masalani allaqachon yechgansiz!"}), 400
        
    if challenge.flag == flag:
        # To'g'ri javob
        new_sub = Submission(user_id=current_user.id, challenge_id=challenge.id)
        current_user.score += challenge.points
        db.session.add(new_sub)
        db.session.commit()
        return jsonify({
            "status": "success", 
            "message": f"Tabriklaymiz! To'g'ri javob. +{challenge.points} ball",
            "new_score": current_user.score
        })
    else:
        return jsonify({"status": "error", "message": "Noto'g'ri flag. Yana urinib ko'ring!"}), 400

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash("Sizda admin huquqlari yo'q!", "error")
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        difficulty = request.form.get('difficulty')
        flag = request.form.get('flag')
        points = request.form.get('points')
        
        new_challenge = Challenge(
            title=title,
            description=description,
            category=category,
            difficulty=difficulty,
            flag=flag,
            points=int(points)
        )
        db.session.add(new_challenge)
        db.session.commit()
        flash("Masala muvaffaqiyatli qo'shildi!", "success")
        return redirect(url_for('admin_panel'))
        
    challenges = Challenge.query.order_by(Challenge.created_at.desc()).all()
    return render_template('admin.html', challenges=challenges)
    
@app.route('/admin/delete/<int:id>')
@login_required
def delete_challenge(id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
        
    challenge = Challenge.query.get_or_404(id)
    # Delete related submissions first
    Submission.query.filter_by(challenge_id=id).delete()
    
    db.session.delete(challenge)
    db.session.commit()
    flash("Masala o'chirildi!", "success")
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    app.run(debug=True, port=8080)
