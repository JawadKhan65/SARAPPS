"""
Add OTP columns to users table
"""

from main import app
from extensions import db

with app.app_context():
    try:
        # Add OTP code column
        db.session.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_code VARCHAR(6);"
        )

        # Add OTP expiry column
        db.session.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_code_expiry TIMESTAMP;"
        )

        db.session.commit()
        print("✅ OTP columns added to users table successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.session.rollback()
