"""
Database Initialization Script
Drops and recreates all tables with the new user groups feature
"""

import os
import sys
from sqlalchemy import text
from extensions import db
from app import create_app


def init_database():
    """Initialize database with all tables including user groups"""

    print("🔄 Starting database initialization...")
    print("⚠️  WARNING: This will DROP ALL EXISTING TABLES!")

    confirmation = input("Are you sure you want to continue? (yes/no): ")
    if confirmation.lower() != "yes":
        print("❌ Operation cancelled.")
        return

    app = create_app()

    with app.app_context():
        print("\n📋 Step 1: Dropping all existing tables...")
        try:
            db.drop_all()
            print("✅ All tables dropped")
        except Exception as e:
            print(f"⚠️  Error dropping tables: {e}")

        print("\n📋 Step 2: Creating all tables from models...")
        try:
            db.create_all()
            print("✅ All tables created")
        except Exception as e:
            print(f"❌ Error creating tables: {e}")
            return

        print("\n📋 Step 3: Creating default admin user...")
        try:
            # Import here to avoid circular imports
            from werkzeug.security import generate_password_hash
            from models import AdminUser

            # Check if admin exists
            admin = AdminUser.query.filter_by(email="jawadkhan8464@gmail.com").first()
            if not admin:
                admin = AdminUser(
                    username="admin",
                    email="jawadkhan8464@gmail.com",
                    password_hash=generate_password_hash("admin123"),
                    is_active=True,
                )
                db.session.add(admin)
                db.session.commit()
                print("✅ Default admin user created")
                print("   Username: admin")
                print("   Email: jawadkhan8464@gmail.com")
                print("   Password: admin123")
            else:
                print("✅ Admin user already exists")
        except Exception as e:
            print(f"⚠️  Error creating admin user: {e}")
            db.session.rollback()

        print("\n📋 Step 4: Verifying tables...")
        try:
            result = db.session.execute(
                text("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public' 
                ORDER BY tablename
            """)
            )
            tables = [row[0] for row in result]

            print("✅ Created tables:")
            for table in tables:
                print(f"   - {table}")

            # Check for user_groups table
            if "user_groups" in tables:
                print("\n✅ user_groups table created successfully")
            else:
                print("\n⚠️  user_groups table not found!")

            # Check for group_id column in users
            result = db.session.execute(
                text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'group_id'
            """)
            )
            group_id_col = result.first()

            if group_id_col:
                print(f"✅ users.group_id column exists ({group_id_col[1]})")
            else:
                print("⚠️  users.group_id column not found!")

            # Check for OTP columns in users
            otp_columns = db.session.execute(
                text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name IN ('otp_code', 'otp_code_expiry')
            """)
            ).fetchall()

            if len(otp_columns) == 2:
                print(f"✅ users OTP columns exist (otp_code, otp_code_expiry)")
            else:
                print("⚠️  users OTP columns not found!")

        except Exception as e:
            print(f"⚠️  Error verifying tables: {e}")

        print("\n📋 Step 5: Creating uploads directory...")
        try:
            uploads_dir = os.path.join("uploads", "group_images")
            os.makedirs(uploads_dir, exist_ok=True)
            print(f"✅ Created {uploads_dir} directory")
        except Exception as e:
            print(f"⚠️  Error creating uploads directory: {e}")

        print("\n📋 Step 6: Seeding crawlers...")
        try:
            from models import Crawler
            import uuid

            # Define all available crawlers
            crawlers_config = [
                {
                    "name": "Amazon",
                    "website_url": "https://www.amazon.com",
                    "scraper_module": "amazon",
                },
                {
                    "name": "Zappos",
                    "website_url": "https://www.zappos.com",
                    "scraper_module": "zappos",
                },
                {
                    "name": "Zalando",
                    "website_url": "https://www.zalando.com",
                    "scraper_module": "zalando_playwright",
                },
                {
                    "name": "Decathlon",
                    "website_url": "https://www.decathlon.com",
                    "scraper_module": "decathlon",
                },
                {
                    "name": "Clarks",
                    "website_url": "https://www.clarks.com",
                    "scraper_module": "clarks",
                },
                {
                    "name": "Bergfreunde",
                    "website_url": "https://www.bergfreunde.com",
                    "scraper_module": "bergfreunde",
                },
                {
                    "name": "Canterbury",
                    "website_url": "https://www.canterbury.com",
                    "scraper_module": "canterbury",
                },
                {
                    "name": "Crockett & Jones (Men)",
                    "website_url": "https://www.crockettandjones.com/collections/mens-shoes",
                    "scraper_module": "crocket_jones_men",
                },
                {
                    "name": "Crockett & Jones (Women)",
                    "website_url": "https://www.crockettandjones.com/collections/womens-shoes",
                    "scraper_module": "crocket_jones_women",
                },
                {
                    "name": "Givenchy",
                    "website_url": "https://www.givenchy.com",
                    "scraper_module": "givenchy",
                },
                {
                    "name": "John Lobb (UK)",
                    "website_url": "https://www.johnlobb.com/gb/en",
                    "scraper_module": "johnloob_playwright_en_gb",
                },
                {
                    "name": "John Lobb (EU)",
                    "website_url": "https://www.johnlobb.com/eu/en",
                    "scraper_module": "johnloob_playwright_en_eu",
                },
                {
                    "name": "Military 1st",
                    "website_url": "https://www.military1st.com",
                    "scraper_module": "military1st",
                },
                {
                    "name": "GearPoint",
                    "website_url": "https://www.gearpoint.nl/en/search/shoes",
                    "scraper_module": "gearpoint",
                },
            ]

            added_count = 0
            for config in crawlers_config:
                crawler = Crawler(
                    id=str(uuid.uuid4()),
                    name=config["name"],
                    website_url=config["website_url"],
                    scraper_module=config["scraper_module"],
                    is_active=True,
                    min_uniqueness_threshold=30.0,
                    is_running=False,
                    total_runs=0,
                    items_scraped=0,
                    unique_images_added=0,
                    duplicate_count=0,
                    consecutive_errors=0,
                )
                db.session.add(crawler)
                added_count += 1

            db.session.commit()
            print(f"✅ Seeded {added_count} crawlers")

        except Exception as e:
            print(f"⚠️  Error seeding crawlers: {e}")
            db.session.rollback()

        print("\n" + "=" * 60)
        print("🎉 Database initialization completed successfully!")
        print("=" * 60)
        print("\nDefault Credentials:")
        print("  Username: admin")
        print("  Email: jawadkhan8464@gmail.com")
        print("  Password: admin123")
        print("\nCrawlers seeded: 14")
        print("\nYou can now start the Flask application:")
        print("  python app.py")
        print()


if __name__ == "__main__":
    init_database()
