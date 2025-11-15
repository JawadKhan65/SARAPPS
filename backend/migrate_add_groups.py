"""
Database Migration: Add User Groups Feature
This script adds user groups without dropping existing data
"""

from sqlalchemy import text
from extensions import db
from app import create_app


def migrate_user_groups():
    """Add user groups feature to existing database"""

    print("🔄 Starting User Groups migration...")
    print("✅ This will ADD user groups without deleting existing data")
    print()

    confirmation = input("Continue with migration? (yes/no): ")
    if confirmation.lower() != "yes":
        print("❌ Operation cancelled.")
        return

    app = create_app()

    with app.app_context():
        try:
            print("\n📋 Step 1: Creating user_groups table...")

            # Create user_groups table
            db.session.execute(
                text("""
                CREATE TABLE IF NOT EXISTS user_groups (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    name VARCHAR(100) UNIQUE NOT NULL,
                    description TEXT,
                    profile_image_url VARCHAR(500),
                    profile_image_path VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by UUID REFERENCES admin_users(id) ON DELETE SET NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )

            print("✅ user_groups table created")

            print("\n📋 Step 2: Creating indexes...")

            # Create indexes
            db.session.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_user_groups_name 
                ON user_groups(name)
            """)
            )

            db.session.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_user_groups_created_by 
                ON user_groups(created_by)
            """)
            )

            print("✅ Indexes created")

            print("\n📋 Step 3: Adding group_id column to users table...")

            # Check if column exists
            result = db.session.execute(
                text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'group_id'
            """)
            )

            if result.first():
                print("✅ group_id column already exists")
            else:
                # Add column
                db.session.execute(
                    text("""
                    ALTER TABLE users 
                    ADD COLUMN group_id UUID 
                    REFERENCES user_groups(id) ON DELETE SET NULL
                """)
                )

                # Create index
                db.session.execute(
                    text("""
                    CREATE INDEX idx_users_group_id ON users(group_id)
                """)
                )

                print("✅ group_id column added to users table")

            # Commit all changes
            db.session.commit()

            print("\n📋 Step 4: Verifying migration...")

            # Verify user_groups table
            result = db.session.execute(
                text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'user_groups' 
                ORDER BY ordinal_position
            """)
            )

            columns = result.fetchall()
            print("✅ user_groups table columns:")
            for col_name, col_type in columns:
                print(f"   - {col_name} ({col_type})")

            # Verify users.group_id
            result = db.session.execute(
                text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'group_id'
            """)
            )

            col = result.first()
            if col:
                print(f"\n✅ users.group_id column: {col[1]}")

            # Create uploads directory
            print("\n📋 Step 5: Creating uploads directory...")
            import os

            uploads_dir = os.path.join("uploads", "group_images")
            os.makedirs(uploads_dir, exist_ok=True)
            print(f"✅ Created {uploads_dir} directory")

            print("\n" + "=" * 60)
            print("🎉 User Groups migration completed successfully!")
            print("=" * 60)
            print("\nYou can now:")
            print("  1. Restart your Flask backend")
            print("  2. Go to Admin Panel → Groups")
            print("  3. Create groups and upload images")
            print()

        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            db.session.rollback()
            import traceback

            traceback.print_exc()
            return


if __name__ == "__main__":
    migrate_user_groups()
