"""
Migration script to add reset_token fields to users table
Run this after updating the User model
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Database connection
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stip"
)


def migrate():
    """Add reset_token fields to users table"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        print("Adding reset_token columns to users table...")

        # Add reset_token column
        cur.execute("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS reset_token VARCHAR(255);
        """)

        # Add reset_token_expiry column
        cur.execute("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS reset_token_expiry TIMESTAMP;
        """)

        conn.commit()
        print("✅ Migration completed successfully!")

        # Verify columns exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name IN ('reset_token', 'reset_token_expiry');
        """)

        columns = cur.fetchall()
        print(f"Verified columns: {[col[0] for col in columns]}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        raise


if __name__ == "__main__":
    migrate()
