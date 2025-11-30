import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables FIRST before importing config
load_dotenv()

from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from core.config.config import config
from core.extensions import db, jwt, mail, setup_logging
from core.models import (
    User,
    AdminUser,
    SoleImage,
    UploadedImage,
    MatchResult,
    Crawler,
    CrawlerStatistics,
    SystemConfig,
)
import core.config.firebase_config  # Initialize Firebase Admin SDK


def create_app(config_name=None):
    """Application factory"""
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)

    # CORS setup with proper preflight handling
    # Use environment-based origins for security
    allowed_origins = app.config.get("CORS_ORIGINS", [])
    if isinstance(allowed_origins, str):
        allowed_origins = [origin.strip() for origin in allowed_origins.split(",")]
    
    # Log CORS origins for debugging
    app.logger.info(f"🌐 CORS allowed origins: {allowed_origins}")
    
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": allowed_origins,
                "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"],
                "expose_headers": ["Content-Type", "Authorization"],
                "supports_credentials": True,
                "max_age": 3600,
            }
        },
        supports_credentials=True,
    )

    # Logging setup
    setup_logging(app)

    # Rate limiting setup
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["1000 per day", "200 per hour"],  # Increased for admin dashboard polling
        storage_uri=app.config.get("REDIS_URL", "redis://localhost:6379/0"),
        storage_options={"socket_connect_timeout": 30},
        strategy="fixed-window",
    )
    
    # Store limiter in app for use in routes
    app.limiter = limiter

    # Create upload directories
    try:
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "originals"), exist_ok=True)
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "processed"), exist_ok=True)
    except PermissionError as e:
        app.logger.warning(f"Could not create upload directories: {e}")
        app.logger.warning("Upload directories will be created by Docker volume mounts")

    # Database context
    with app.app_context():
        try:
            db.create_all()

            # Initialize system config if not exists
            if SystemConfig.query.first() is None:
                default_config = SystemConfig()
                db.session.add(default_config)
                db.session.commit()
        except Exception as e:
            app.logger.warning(f"Database initialization failed: {e}")
            app.logger.warning(
                "Continuing without database. Run 'python scripts/init_db.py' to initialize."
            )

    # Register blueprints
    from routes.auth import auth_bp
    from routes.user import user_bp
    from routes.matches import matches_bp
    from routes.admin import admin_bp
    from routes.crawlers import crawlers_bp
    from routes.database import database_bp
    from routes.images import images_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(user_bp, url_prefix="/api/user")
    app.register_blueprint(matches_bp, url_prefix="/api/matches")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(crawlers_bp, url_prefix="/api/crawlers")
    app.register_blueprint(database_bp, url_prefix="/api/database")
    app.register_blueprint(
        images_bp
    )  # Uses /api/images prefix from blueprint definition
    
    # Exempt admin endpoints from rate limiting (they have JWT auth already)
    limiter.exempt(admin_bp)

    # Serve static files (logo for emails)
    @app.route("/static/<path:filename>")
    def serve_static(filename):
        from flask import send_from_directory

        return send_from_directory("static", filename)

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Not found"}, 404

    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error(f"Internal server error: {e}")
        return {"error": "Internal server error"}, 500

    @app.shell_context_processor
    def make_shell_context():
        return {
            "db": db,
            "User": User,
            "AdminUser": AdminUser,
            "SoleImage": SoleImage,
            "UploadedImage": UploadedImage,
            "MatchResult": MatchResult,
            "Crawler": Crawler,
        }

    return app


# Create application instance for Gunicorn
app = create_app()


if __name__ == "__main__":
    import os

    app = create_app()

    # Use Waitress production server instead of Flask development server
    if os.getenv("FLASK_ENV") == "development":
        # Development mode - use Flask's built-in server with debug
        app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
    else:
        # Production mode - use Waitress
        from waitress import serve

        print("Starting production server with Waitress...")
        print(" * Running on http://0.0.0.0:5000")
        serve(app, host="0.0.0.0", port=5000, threads=6)
