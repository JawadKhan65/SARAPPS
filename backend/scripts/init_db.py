"""
Database Initialization Script

This script initializes the PostgreSQL database for the Advanced Print Match System.
It creates all tables, indexes, and loads default data.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --reset  # Reset database
    python scripts/init_db.py --seed   # Seed with sample data
"""

import sys
import click
import logging
from pathlib import Path
from werkzeug.security import generate_password_hash

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from extensions import db
from models import User, UploadedImage, SoleImage, MatchResult, Crawler, AdminUser
from app import create_app
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using werkzeug."""
    return generate_password_hash(password)


def init_database():
    """Initialize database with all tables and indexes."""
    logger.info("Initializing database...")

    try:
        # Create all tables
        with db.engine.begin() as connection:
            db.create_all()

        logger.info("✓ All tables created successfully")

        # Create indexes
        create_indexes()

        # Enable extensions (optional)
        with db.engine.begin() as connection:
            try:
                connection.execute(db.text("CREATE EXTENSION IF NOT EXISTS pgvector"))
                logger.info("✓ PostgreSQL pgvector extension enabled")
            except Exception:
                logger.info(
                    "ℹ pgvector extension not available (optional for vector search)"
                )

            try:
                connection.execute(
                    db.text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
                )
                logger.info("✓ PostgreSQL uuid-ossp extension enabled")
            except Exception:
                logger.info("ℹ uuid-ossp extension not available (using Python uuid)")

        logger.info("✓ Database initialization complete")

    except Exception as e:
        logger.error(f"✗ Error initializing database: {e}")
        raise


def create_indexes():
    """Create database indexes for optimization."""
    logger.info("Creating indexes...")

    try:
        with db.engine.begin() as connection:
            # User indexes
            connection.execute(
                db.text("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            )
            connection.execute(
                db.text(
                    "CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)"
                )
            )
            connection.execute(
                db.text(
                    "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)"
                )
            )

            # Image indexes
            connection.execute(
                db.text(
                    "CREATE INDEX IF NOT EXISTS idx_uploaded_images_user_id ON uploaded_images(user_id)"
                )
            )
            connection.execute(
                db.text(
                    "CREATE INDEX IF NOT EXISTS idx_uploaded_images_uploaded_at ON uploaded_images(uploaded_at)"
                )
            )

            # Match indexes
            connection.execute(
                db.text(
                    "CREATE INDEX IF NOT EXISTS idx_match_results_user_id ON match_results(user_id)"
                )
            )
            connection.execute(
                db.text(
                    "CREATE INDEX IF NOT EXISTS idx_match_results_similarity ON match_results(overall_similarity DESC)"
                )
            )

            # Crawler indexes
            connection.execute(
                db.text(
                    "CREATE INDEX IF NOT EXISTS idx_crawler_is_active ON crawlers(is_active)"
                )
            )
            connection.execute(
                db.text(
                    "CREATE INDEX IF NOT EXISTS idx_crawler_is_running ON crawlers(is_running)"
                )
            )

            logger.info("✓ All indexes created successfully")

    except Exception as e:
        logger.warning(f"Some indexes could not be created: {e}")


def create_default_admin():
    """Create default admin user."""
    logger.info("Creating default admin user...")

    try:
        # Check if admin already exists
        admin = AdminUser.query.filter_by(email="admin@shoeidentifier.local").first()
        if admin:
            logger.info("✓ Admin user already exists")
            return

        # Create new admin
        admin = AdminUser(
            id=str(uuid.uuid4()),
            email="admin@shoeidentifier.local",
            username="admin",
            password_hash=hash_password("admin123"),
            is_active=True,
            mfa_enabled=True,
        )

        db.session.add(admin)
        db.session.commit()

        logger.info("✓ Default admin user created")
        logger.info("  Email: admin@shoeidentifier.local")
        logger.info("  Password: admin123 (please change on first login)")

    except Exception as e:
        logger.error(f"✗ Error creating admin user: {e}")
        db.session.rollback()
        raise


def create_sample_crawlers():
    """Create sample crawler configurations."""
    logger.info("Creating sample crawlers...")

    try:
        crawlers = [
            {
                "name": "Zappos",
                "url": "https://www.zappos.com/men-shoes/.zso?t=men%20shoes",
                "module": "zappos",
            },
            {
                "name": "Amazon Shoes",
                "url": "https://www.amazon.com",
                "module": "amazon",
            },
            {
                "name": "Zalando",
                "url": "https://www.zalando.com",
                "module": "zalando_playwright",
            },
            {
                "name": "Bergfreunde",
                "url": "https://www.bergfreunde.nl/bergschoenen/voor--heren",
                "module": "bergfreunde",
            },
            {
                "name": "Canterbury",
                "url": "https://canterbury.nl/nl/rugbyschoenen/alles-bekijken",
                "module": "canterbury",
            },
            {
                "name": "Clarks",
                "url": "https://www.clarks.com/en-gb/mens/mens-boots/m_boots_uk-c",
                "module": "clarks",
            },
            {
                "name": "Crockett & Jones Men",
                "url": "https://eu.crockettandjones.com/collections/all-mens-styles",
                "module": "crocket_jones_men",
            },
            {
                "name": "Crockett & Jones Women",
                "url": "https://eu.crockettandjones.com/collections/all-womens-styles",
                "module": "crocket_jones_women",
            },
            {
                "name": "Decathlon",
                "url": "https://www.decathlon.com/collections/footwear",
                "module": "decathlon",
            },
            {
                "name": "Givenchy",
                "url": "https://www.givenchy.com/nl/en/men/shoes",
                "module": "givenchy",
            },
            {
                "name": "John Lobb EU",
                "url": "https://www.johnlobb.com/en_eu/shoes/shoes-all",
                "module": "johnloob_playwright_en_eu",
            },
            {
                "name": "John Lobb GB",
                "url": "https://www.johnlobb.com/en_gb/shoes/shoes-all",
                "module": "johnloob_playwright_en_gb",
            },
            {
                "name": "Military 1st",
                "url": "https://www.military1st.eu/footwear/boots",
                "module": "military1st",
            },
        ]

        for crawler_data in crawlers:
            crawler = Crawler.query.filter_by(name=crawler_data["name"]).first()
            if not crawler:
                crawler = Crawler(
                    name=crawler_data["name"],
                    website_url=crawler_data["url"],
                    scraper_module=crawler_data.get("module"),
                    is_active=True,
                )
                db.session.add(crawler)

        db.session.commit()
        logger.info("✓ Sample crawlers created successfully")

    except Exception as e:
        logger.error(f"✗ Error creating crawlers: {e}")
        db.session.rollback()
        raise


def create_sample_users(count: int = 5):
    """Create sample users for testing."""
    logger.info(f"Creating {count} sample users...")

    try:
        for i in range(count):
            email = f"user{i + 1}@example.com"

            # Check if user exists
            user = User.query.filter_by(email=email).first()
            if user:
                continue

            user = User(
                id=str(uuid.uuid4()),
                email=email,
                username=f"user{i + 1}",
                password_hash=hash_password("password123"),
                is_active=True,
                dark_mode=True,
                language="en",
            )

            db.session.add(user)

        db.session.commit()
        logger.info(f"✓ Created {count} sample users")

    except Exception as e:
        logger.error(f"✗ Error creating sample users: {e}")
        db.session.rollback()
        raise


def seed_database():
    """Seed database with sample data."""
    logger.info("Seeding database with sample data...")

    try:
        create_sample_users(10)
        create_sample_crawlers()
        logger.info("✓ Database seeding complete")

    except Exception as e:
        logger.error(f"✗ Error seeding database: {e}")
        raise


def reset_database():
    """Reset database by dropping all tables and recreating them."""
    logger.warning("Resetting database... This will delete all data!")

    response = input("Are you sure? Type 'yes' to confirm: ")
    if response.lower() != "yes":
        logger.info("Reset cancelled")
        return

    try:
        db.drop_all()
        logger.info("✓ All tables dropped")

        init_database()
        create_default_admin()
        create_sample_crawlers()

        logger.info("✓ Database reset complete")

    except Exception as e:
        logger.error(f"✗ Error resetting database: {e}")
        raise


def verify_database():
    """Verify database connectivity and structure."""
    logger.info("Verifying database...")

    try:
        # Check database connection
        with db.engine.connect() as connection:
            result = connection.execute("SELECT 1")
            result.fetchone()

        logger.info("✓ Database connection successful")

        # Check tables exist
        tables = [
            "users",
            "uploaded_images",
            "shoes",
            "match_results",
            "crawler_history",
            "system_logs",
            "audit_logs",
            "crawler_status",
            "sessions",
            "admin_users",
        ]

        inspector = db.inspect(db.engine)
        existing_tables = inspector.get_table_names()

        for table in tables:
            if table in existing_tables:
                logger.info(f"✓ Table '{table}' exists")
            else:
                logger.warning(f"✗ Table '{table}' missing")

        logger.info("✓ Database verification complete")

    except Exception as e:
        logger.error(f"✗ Error verifying database: {e}")
        raise


@click.group()
def cli():
    """Database initialization and management tool."""
    pass


@cli.command()
def init():
    """Initialize the database."""
    app = create_app()
    with app.app_context():
        init_database()
        create_default_admin()
        create_sample_crawlers()
        logger.info("\n✓ Database initialization complete!")


@cli.command()
def reset():
    """Reset the database (dangerous!)."""
    app = create_app()
    with app.app_context():
        reset_database()


@cli.command()
def seed():
    """Seed database with sample data."""
    app = create_app()
    with app.app_context():
        seed_database()


@cli.command()
def verify():
    """Verify database connectivity and structure."""
    app = create_app()
    with app.app_context():
        verify_database()


@cli.command()
@click.option("--email", prompt="Admin email", default="admin@shoeidentifier.local")
@click.option(
    "--password", prompt="Admin password", hide_input=True, confirmation_prompt=True
)
def create_admin(email, password):
    """Create a new admin user."""
    app = create_app()
    with app.app_context():
        try:
            # Check if admin exists
            admin = AdminUser.query.filter_by(email=email).first()
            if admin:
                logger.error(f"Admin user with email '{email}' already exists")
                return

            # Create admin
            admin = AdminUser(
                id=str(uuid.uuid4()),
                email=email,
                password_hash=hash_password(password),
                admin_level="super",
                is_active=True,
            )

            db.session.add(admin)
            db.session.commit()

            logger.info(f"✓ Admin user '{email}' created successfully")

        except Exception as e:
            logger.error(f"✗ Error creating admin: {e}")
            db.session.rollback()


@cli.command()
def stats():
    """Display database statistics."""
    app = create_app()
    with app.app_context():
        try:
            user_count = User.query.count()
            image_count = UploadedImage.query.count()
            sole_image_count = SoleImage.query.count()
            match_count = MatchResult.query.count()

            logger.info("\n=== Database Statistics ===")
            logger.info(f"Total users: {user_count}")
            logger.info(f"Total images: {image_count}")
            logger.info(f"Total sole images: {sole_image_count}")
            logger.info(f"Total matches: {match_count}")

        except Exception as e:
            logger.error(f"✗ Error retrieving statistics: {e}")


if __name__ == "__main__":
    cli()
