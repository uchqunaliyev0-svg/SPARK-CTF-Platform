from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;'))
        db.session.commit()
        print("Muvaffaqiyatli: is_admin ustuni user jadvaliga qo'shildi!")
    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")
