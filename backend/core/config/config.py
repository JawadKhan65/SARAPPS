import os
from datetime import timedelta


class Config:
    """Base configuration"""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql://postgres:12345678@localhost:5432/stip_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 20,  # Increased from 10 for better concurrency
        "max_overflow": 10,  # Allow 10 extra connections when pool is full
        "pool_recycle": 3600,  # Recycle connections after 1 hour
        "pool_pre_ping": True,  # Verify connections before use
        "pool_timeout": 30,  # Wait up to 30s for connection from pool
        "connect_args": {
            "connect_timeout": 10,  # Initial connection timeout
            "options": "-c statement_timeout=30000",  # 30s query timeout
        },
    }

    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret-key-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # Mail
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "False").lower() in ("true", "1", "yes")
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "False").lower() in ("true", "1", "yes")
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "noreply@stip.local")

    # File uploads
    MAX_CONTENT_LENGTH = 120 * 1024 * 1024  # 120 MB max file size
    UPLOAD_FOLDER = "/app/uploads"
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

    # Pagination
    ITEMS_PER_PAGE = 20

    # Image processing
    SIMILARITY_THRESHOLD = 0.85  # Stop scraping if uniqueness < 85%
    BATCH_SIZE = 50  # Process images in batches of 50

    # Zalando Scraper Anti-Detection Configuration
    ZALANDO_MIN_PRODUCT_DELAY = int(
        os.getenv("ZALANDO_MIN_PRODUCT_DELAY", 8)
    )  # Min seconds between products
    ZALANDO_MAX_PRODUCT_DELAY = int(
        os.getenv("ZALANDO_MAX_PRODUCT_DELAY", 15)
    )  # Max seconds between products
    ZALANDO_MIN_PAGE_DELAY = int(
        os.getenv("ZALANDO_MIN_PAGE_DELAY", 30)
    )  # Min seconds between pages
    ZALANDO_MAX_PAGE_DELAY = int(
        os.getenv("ZALANDO_MAX_PAGE_DELAY", 60)
    )  # Max seconds between pages
    ZALANDO_PROXY_ROTATION_INTERVAL = int(
        os.getenv("ZALANDO_PROXY_ROTATION_INTERVAL", 15)
    )  # Rotate proxy every N products
    ZALANDO_SESSION_RESTART_INTERVAL = int(
        os.getenv("ZALANDO_SESSION_RESTART_INTERVAL", 30)
    )  # Restart browser every N products (reduced from 50 to prevent memory buildup)
    ZALANDO_MAX_RETRIES_PER_PRODUCT = int(
        os.getenv("ZALANDO_MAX_RETRIES_PER_PRODUCT", 3)
    )  # Max retries per product
    ZALANDO_ENABLE_PROXIES = (
        os.getenv("ZALANDO_ENABLE_PROXIES", "true").lower() == "true"
    )  # Enable/disable proxy rotation

    # Scraper Configuration
    # Minimum items to scrape before considering stopping based on uniqueness
    # Large e-commerce sites should scrape more before stopping
    CRAWLER_MIN_ITEMS_THRESHOLDS = {
        "Zalando": 1000,  # Large catalog, expect ~10k+ items
        "Amazon": 1000,  # Large catalog
        "Nike": 500,  # Mid-size catalog
        "Adidas": 500,  # Mid-size catalog
        "Default": 200,  # Default for other crawlers
    }

    # Uniqueness thresholds per crawler (percentage)
    CRAWLER_UNIQUENESS_THRESHOLDS = {
        "Zalando": 15.0,  # Can be lower due to large catalog
        "Amazon": 15.0,  # Can be lower due to large catalog
        "Default": 30.0,  # Default threshold
    }

    # Fuzzy name matching threshold (0-1)
    FUZZY_NAME_MATCH_THRESHOLD = 0.90  # 90% similarity for duplicate names

    # CORS
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3001,http://192.168.1.8:3000,http://192.168.1.8:3001,https://localhost:443",
    ).split(",")


class DevelopmentConfig(Config):
    """Development configuration"""

    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""

    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
