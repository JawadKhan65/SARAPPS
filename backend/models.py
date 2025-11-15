from extensions import db
from datetime import datetime
from enum import Enum
import uuid


class User(db.Model):
    """User model for mobile app users"""

    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # Account status
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_deleted = db.Column(db.Boolean, default=False)

    # Preferences
    dark_mode = db.Column(db.Boolean, default=True)
    language = db.Column(db.String(10), default="en")

    # Security
    remember_token = db.Column(db.String(255), nullable=True)
    trusted_devices = db.Column(db.JSON, default=list)  # List of device fingerprints
    failed_login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    last_login = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(45), nullable=True)  # IPv6 support

    # Storage tracking
    storage_used_mb = db.Column(db.Float, default=0.0)

    # Group membership
    group_id = db.Column(
        db.String(36), db.ForeignKey("user_groups.id"), nullable=True, index=True
    )

    # Relationships
    uploaded_images = db.relationship(
        "UploadedImage", back_populates="user", cascade="all, delete-orphan"
    )
    match_results = db.relationship(
        "MatchResult", back_populates="user", cascade="all, delete-orphan"
    )
    group = db.relationship("UserGroup", back_populates="users")

    def __repr__(self):
        return f"<User {self.email}>"


class AdminUser(db.Model):
    """Admin user model"""

    __tablename__ = "admin_users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # MFA
    mfa_secret = db.Column(db.String(32), nullable=True)
    mfa_enabled = db.Column(db.Boolean, default=True)
    mfa_temp_code = db.Column(db.String(6), nullable=True)
    mfa_code_expiry = db.Column(db.DateTime, nullable=True)

    # Security
    is_active = db.Column(db.Boolean, default=True)
    failed_login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    last_logout = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Session
    last_activity = db.Column(db.DateTime, nullable=True)
    session_token = db.Column(db.String(255), nullable=True)
    session_expires = db.Column(db.DateTime, nullable=True)

    # Preferences
    dark_mode = db.Column(db.Boolean, default=True)
    language = db.Column(db.String(10), default="en")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AdminUser {self.username}>"


class SoleImage(db.Model):
    """Crawled sole image with vector representation"""

    __tablename__ = "sole_images"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Source
    crawler_id = db.Column(
        db.String(36), db.ForeignKey("crawlers.id"), nullable=False, index=True
    )
    source_url = db.Column(db.String(2048), nullable=False, unique=True, index=True)
    brand = db.Column(db.String(255), nullable=False, index=True)
    product_type = db.Column(db.String(255), nullable=False, index=True)
    product_name = db.Column(db.String(512), nullable=True)

    # Image storage - File paths (legacy/fallback)
    original_image_path = db.Column(
        db.String(1024), nullable=True
    )  # Made nullable for binary-only storage
    processed_image_path = db.Column(
        db.String(1024), nullable=True
    )  # Made nullable for binary-only storage
    image_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)

    # Image storage - Binary data (preferred for data integrity and similarity search)
    original_image_data = db.Column(
        db.LargeBinary, nullable=True
    )  # Original scraped image
    processed_image_data = db.Column(
        db.LargeBinary, nullable=True
    )  # Processed/cropped sole image
    image_format = db.Column(db.String(10), nullable=True)  # e.g., 'PNG', 'JPEG'

    # Vector representation for similarity matching
    feature_vector = db.Column(db.LargeBinary, nullable=True)  # Serialized numpy array
    lbp_histogram = db.Column(db.LargeBinary, nullable=True)  # LBP features

    # Metadata
    image_width = db.Column(db.Integer)
    image_height = db.Column(db.Integer)
    file_size_kb = db.Column(db.Float)

    # Quality and uniqueness
    quality_score = db.Column(db.Float, nullable=True)  # 0-1 scale
    uniqueness_score = db.Column(db.Float, nullable=True)  # Similarity to closest match

    # Timestamps
    crawled_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    processed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    crawler = db.relationship("Crawler", back_populates="sole_images")
    matches = db.relationship("MatchResult", back_populates="sole_image")

    def __repr__(self):
        return f"<SoleImage {self.brand} {self.product_type}>"


class UploadedImage(db.Model):
    """User-uploaded image for matching"""

    __tablename__ = "uploaded_images"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True
    )

    # Image storage
    file_path = db.Column(db.String(1024), nullable=False)
    processed_image_path = db.Column(db.String(1024), nullable=False)
    image_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)

    # Features
    feature_vector = db.Column(db.LargeBinary, nullable=True)
    lbp_histogram = db.Column(db.LargeBinary, nullable=True)

    # Metadata
    image_width = db.Column(db.Integer)
    image_height = db.Column(db.Integer)
    file_size_kb = db.Column(db.Float)
    quality_score = db.Column(db.Float, nullable=True)

    # Timestamps
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    last_matched_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship("User", back_populates="uploaded_images")
    match_results = db.relationship("MatchResult", back_populates="uploaded_image")

    def __repr__(self):
        return f"<UploadedImage {self.id}>"


class MatchResult(db.Model):
    """Match result between user image and database soles"""

    __tablename__ = "match_results"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True
    )
    uploaded_image_id = db.Column(
        db.String(36), db.ForeignKey("uploaded_images.id"), nullable=False, index=True
    )

    # Match rankings
    primary_match_id = db.Column(
        db.String(36), db.ForeignKey("sole_images.id"), nullable=True
    )
    secondary_match_id = db.Column(db.String(36), nullable=True)
    tertiary_match_id = db.Column(db.String(36), nullable=True)
    quaternary_match_id = db.Column(db.String(36), nullable=True)

    # Scores
    primary_confidence = db.Column(db.Float, nullable=True)
    secondary_confidence = db.Column(db.Float, nullable=True)
    tertiary_confidence = db.Column(db.Float, nullable=True)
    quaternary_confidence = db.Column(db.Float, nullable=True)
    overall_similarity = db.Column(db.Float, nullable=True)  # Highest similarity score

    # User confirmation
    confirmed_match = db.Column(
        db.String(36), nullable=True
    )  # Which match user confirmed
    confirmation_type = db.Column(
        db.String(50), nullable=True
    )  # primary/secondary/tertiary/quaternary/custom
    custom_brand = db.Column(db.String(255), nullable=True)
    custom_product_type = db.Column(db.String(255), nullable=True)

    # Performance metrics
    matching_time_ms = db.Column(db.Integer, nullable=True)

    # Timestamps
    matched_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship("User", back_populates="match_results")
    uploaded_image = db.relationship("UploadedImage", back_populates="match_results")
    sole_image = db.relationship("SoleImage", back_populates="matches")

    def __repr__(self):
        return f"<MatchResult {self.id}>"


class Crawler(db.Model):
    """Crawler configuration and status"""

    __tablename__ = "crawlers"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    website_url = db.Column(db.String(2048), nullable=False, unique=True)
    scraper_module = db.Column(db.String(255), nullable=True)  # Python module name

    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_running = db.Column(db.Boolean, default=False, index=True)
    run_type = db.Column(db.String(50), nullable=True)  # 'scheduled' or 'manual'
    current_batch = db.Column(db.Integer, default=0)
    total_batches = db.Column(db.Integer, default=0)
    progress_percentage = db.Column(db.Float, default=0.0)

    # Cancellation
    cancel_requested = db.Column(db.Boolean, default=False)
    cancelled_by = db.Column(db.String(36), nullable=True)  # Admin ID
    cancelled_at = db.Column(db.DateTime, nullable=True)

    # Schedule
    schedule_cron = db.Column(
        db.String(255), nullable=True
    )  # e.g., "0 2 * * *" for 2 AM daily
    next_run_at = db.Column(db.DateTime, nullable=True)
    scheduled_by = db.Column(db.String(36), nullable=True)  # Admin ID

    # Performance metrics
    total_runs = db.Column(db.Integer, default=0)
    items_scraped = db.Column(db.Integer, default=0)  # Total items scraped
    current_run_items = db.Column(db.Integer, default=0)  # Items in current run
    last_started_at = db.Column(db.DateTime, nullable=True)
    last_completed_at = db.Column(db.DateTime, nullable=True)
    last_run_at = db.Column(db.DateTime, nullable=True)  # Last time crawler ran
    last_run_duration_minutes = db.Column(db.Float, nullable=True)
    started_by = db.Column(db.String(36), nullable=True)  # Admin ID who started

    # Data statistics
    total_images_crawled = db.Column(db.Integer, default=0)
    unique_images_added = db.Column(db.Integer, default=0)
    unique_brands = db.Column(db.Integer, default=0)
    duplicate_count = db.Column(db.Integer, default=0)
    uniqueness_percentage = db.Column(db.Float, default=100.0)

    # Uniqueness threshold
    min_uniqueness_threshold = db.Column(db.Float, default=30.0)  # Stop if below this %
    notify_admin_on_low_uniqueness = db.Column(db.Boolean, default=True)

    # Error tracking
    last_error = db.Column(db.Text, nullable=True)
    last_error_at = db.Column(db.DateTime, nullable=True)
    consecutive_errors = db.Column(db.Integer, default=0)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    sole_images = db.relationship(
        "SoleImage", back_populates="crawler", cascade="all, delete-orphan"
    )
    crawler_runs = db.relationship(
        "CrawlerRun", back_populates="crawler", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Crawler {self.name}>"


class CrawlerRun(db.Model):
    """Individual crawler run history"""

    __tablename__ = "crawler_runs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    crawler_id = db.Column(db.String(36), db.ForeignKey("crawlers.id"), nullable=False)

    # Run details
    run_type = db.Column(db.String(50), nullable=False)  # 'scheduled' or 'manual'
    started_by = db.Column(db.String(36), nullable=True)  # Admin ID
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)

    # Status
    status = db.Column(
        db.String(50), default="running"
    )  # running, completed, failed, cancelled

    # Statistics
    items_scraped = db.Column(db.Integer, default=0)
    unique_items = db.Column(db.Integer, default=0)
    duplicate_items = db.Column(db.Integer, default=0)
    uniqueness_percentage = db.Column(db.Float, default=0.0)
    batches_processed = db.Column(db.Integer, default=0)

    # Cancellation
    cancelled_reason = db.Column(db.String(500), nullable=True)
    auto_stopped_low_uniqueness = db.Column(db.Boolean, default=False)

    # Error tracking
    error_message = db.Column(db.Text, nullable=True)
    error_count = db.Column(db.Integer, default=0)

    # Relationships
    crawler = db.relationship("Crawler", back_populates="crawler_runs")

    def __repr__(self):
        return f"<CrawlerRun {self.id}>"


class CrawlerStatistics(db.Model):
    """Aggregated statistics from all crawlers"""

    __tablename__ = "crawler_statistics"

    id = db.Column(db.Integer, primary_key=True)

    # Global stats
    total_unique_brands = db.Column(db.Integer, default=0)
    total_unique_soles = db.Column(db.Integer, default=0)
    total_crawlers = db.Column(db.Integer, default=0)
    total_active_crawlers = db.Column(db.Integer, default=0)

    # Matching stats
    avg_matching_time_ms = db.Column(db.Float, default=0.0)
    avg_primary_confidence = db.Column(db.Float, default=0.0)
    avg_secondary_confidence = db.Column(db.Float, default=0.0)
    avg_tertiary_confidence = db.Column(db.Float, default=0.0)
    avg_quaternary_confidence = db.Column(db.Float, default=0.0)
    avg_custom_match_percentage = db.Column(db.Float, default=0.0)

    # User stats
    total_active_users = db.Column(db.Integer, default=0)
    total_uploads = db.Column(db.Integer, default=0)
    avg_storage_per_user_mb = db.Column(db.Float, default=0.0)

    last_updated = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return "<CrawlerStatistics>"


class SystemConfig(db.Model):
    """System configuration and settings"""

    __tablename__ = "system_config"

    id = db.Column(db.Integer, primary_key=True)

    # General settings
    site_name = db.Column(db.String(255), default="Shoe Identifier")
    site_description = db.Column(
        db.Text, default="Advanced shoe identification platform"
    )

    # SMTP Settings
    smtp_server = db.Column(db.String(255), nullable=False, default="smtp.gmail.com")
    smtp_port = db.Column(db.Integer, default=587)
    smtp_username = db.Column(db.String(255), nullable=True, default="")
    smtp_password = db.Column(db.String(255), nullable=True, default="")
    smtp_sender_email = db.Column(
        db.String(255), nullable=True, default="noreply@stip.local"
    )
    smtp_security = db.Column(db.String(20), default="STARTTLS")  # STARTTLS, TLS, NONE

    # Email Templates
    welcome_email_subject = db.Column(db.String(255), default="Welcome to STIP")
    welcome_email_body = db.Column(
        db.Text, default="Welcome to Shoe Type Identification System"
    )

    failed_login_email_subject = db.Column(
        db.String(255), default="Failed Login Attempt"
    )
    failed_login_email_body = db.Column(
        db.Text, default="A failed login attempt was made on your account."
    )

    successful_login_email_subject = db.Column(
        db.String(255), default="Login Successful"
    )
    successful_login_email_body = db.Column(
        db.Text, default="You have successfully logged in."
    )

    logout_email_subject = db.Column(db.String(255), default="Logout Notification")
    logout_email_body = db.Column(db.Text, default="You have been logged out.")

    # Database settings
    db_pool_size = db.Column(db.Integer, default=10)
    db_pool_recycle = db.Column(db.Integer, default=3600)

    # Crawler settings
    similarity_threshold = db.Column(db.Float, default=0.85)
    batch_size = db.Column(db.Integer, default=50)
    max_image_size_mb = db.Column(db.Integer, default=50)

    # Security settings
    session_timeout_minutes = db.Column(db.Integer, default=15)
    max_login_attempts = db.Column(db.Integer, default=5)
    login_lockout_minutes = db.Column(db.Integer, default=15)
    password_min_length = db.Column(db.Integer, default=15)

    last_updated = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    updated_by = db.Column(db.String(36), nullable=True)

    def __repr__(self):
        return "<SystemConfig>"


class UserGroup(db.Model):
    """User groups for organizing users and assigning profile images"""

    __tablename__ = "user_groups"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)

    # Group profile image stored as binary data
    profile_image_data = db.Column(db.LargeBinary, nullable=True)  # Binary image data
    profile_image_mimetype = db.Column(
        db.String(50), nullable=True
    )  # e.g., 'image/png'
    profile_image_filename = db.Column(
        db.String(255), nullable=True
    )  # Original filename

    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(36), nullable=True)  # Admin ID
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    users = db.relationship("User", back_populates="group", lazy="dynamic")

    def __repr__(self):
        return f"<UserGroup {self.name}>"
