from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_mail import Mail
import logging
from logging.handlers import RotatingFileHandler
import os

db = SQLAlchemy()
jwt = JWTManager()
mail = Mail()


def setup_logging(app):
    """Setup logging with rotation"""
    if not app.debug:
        os.makedirs("logs", exist_ok=True)

        # File handler with rotation (max 10MB, keep 10 files)
        file_handler = RotatingFileHandler(
            "logs/stip.log",
            maxBytes=10485760,  # 10 MB
            backupCount=10,
        )

        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info("STIP application startup")
