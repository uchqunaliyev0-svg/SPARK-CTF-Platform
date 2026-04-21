from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE challenge ADD COLUMN IF NOT EXISTS hint TEXT;'))
        db.session.execute(text('ALTER TABLE challenge ADD COLUMN IF NOT EXISTS hint_cost INTEGER DEFAULT 0;'))
        db.session.commit()
        db.create_all() # This will create unlocked_hint table
        print("Muvaffaqiyatli: hint ustunlari va yangi jadval qo'shildi!")
    except Exception as e:
        print(f"Xatolik: {e}")
