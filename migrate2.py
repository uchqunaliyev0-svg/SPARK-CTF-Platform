from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE "challenge" ADD COLUMN IF NOT EXISTS hint TEXT;'))
        db.session.commit()
        print("Muvaffaqiyatli: hint ustuni challenge jadvaliga qo'shildi!")
    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")
