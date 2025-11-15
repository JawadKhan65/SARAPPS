from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, mail
from models import User, AdminUser
from flask_mail import Message
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
import pyotp
import qrcode
from io import BytesIO
import base64

auth_bp = Blueprint("auth", __name__)


def send_email(recipient, subject, body, html=None):
    """Send email notification"""
    try:
        msg = Message(subject=subject, recipients=[recipient], body=body, html=html)
        mail.send(msg)
        current_app.logger.info(f"Email sent to {recipient}: {subject}")
    except Exception as e:
        current_app.logger.error(f"Failed to send email to {recipient}: {str(e)}")


def get_device_fingerprint():
    """Generate device fingerprint from request headers"""
    user_agent = request.headers.get("User-Agent", "")
    accept_language = request.headers.get("Accept-Language", "")
    fingerprint_str = f"{user_agent}:{accept_language}"
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new user"""
    data = request.get_json()

    if (
        not data
        or not data.get("email")
        or not data.get("username")
        or not data.get("password")
    ):
        return jsonify({"error": "Missing required fields"}), 400

    # Validate password length (minimum 15 characters for security)
    if len(data.get("password", "")) < 15:
        return jsonify({"error": "Password must be at least 15 characters"}), 400

    # Check if user exists
    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email already registered"}), 400

    if User.query.filter_by(username=data["username"]).first():
        return jsonify({"error": "Username already taken"}), 400

    # Create new user
    user = User(
        id=str(uuid.uuid4()),
        email=data["email"],
        username=data["username"],
        password_hash=generate_password_hash(data["password"]),
        is_active=True,
        dark_mode=data.get("dark_mode", False),
        language=data.get("language", "en"),
        created_at=datetime.utcnow(),
    )

    db.session.add(user)
    db.session.commit()

    # Send welcome email
    send_email(
        user.email,
        "Welcome to STIP - Shoe Type Identification Platform",
        f"Welcome {user.username}! Your account has been created successfully.",
    )

    current_app.logger.info(f"New user registered: {user.email}")

    # Create tokens for automatic login
    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    return jsonify(
        {
            "message": "User created successfully",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "dark_mode": user.dark_mode,
                "language": user.language,
            },
        }
    ), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """User login with device fingerprint and remember token"""
    data = request.get_json()

    if not data or not data.get("email") or not data.get("password"):
        return jsonify({"error": "Missing email or password"}), 400

    user = User.query.filter_by(email=data["email"]).first()

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    # Check if user is locked out due to failed attempts
    if user.failed_login_attempts >= 5:
        lockout_duration = timedelta(
            minutes=15 * (2 ** (user.failed_login_attempts - 5))
        )
        if user.last_failed_login:
            unlock_time = user.last_failed_login + lockout_duration
            if datetime.utcnow() < unlock_time:
                return jsonify({"error": "Account locked. Try again later"}), 429
        else:
            user.failed_login_attempts = 0

    if not check_password_hash(user.password_hash, data["password"]):
        user.failed_login_attempts += 1
        user.last_failed_login = datetime.utcnow()
        db.session.commit()

        # Send failed login notification
        send_email(
            user.email,
            "Failed Login Attempt",
            f"A failed login attempt was made on your account from {request.remote_addr}",
        )

        current_app.logger.warning(f"Failed login attempt for user: {user.email}")
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.is_active:
        return jsonify({"error": "Account is disabled"}), 403

    # Reset failed login attempts on successful login
    user.failed_login_attempts = 0
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = request.remote_addr

    # Handle device fingerprint and remember login
    device_fingerprint = get_device_fingerprint()
    remember_token = None

    if data.get("remember_login"):
        remember_token = secrets.token_urlsafe(32)
        user.remember_token = remember_token

        if user.trusted_devices is None:
            user.trusted_devices = {}

        user.trusted_devices[device_fingerprint] = {
            "fingerprint": device_fingerprint,
            "user_agent": request.headers.get("User-Agent", ""),
            "trusted_at": datetime.utcnow().isoformat(),
            "last_used": datetime.utcnow().isoformat(),
        }

    db.session.commit()

    # Send successful login notification
    send_email(
        user.email,
        "Successful Login",
        f"Your account was accessed successfully from {request.remote_addr}",
    )

    # Create tokens
    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    # Get profile image from group if user is in a group
    profile_image_url = None
    if user.group_id:
        from models import UserGroup

        group = UserGroup.query.get(user.group_id)
        if group and group.profile_image_data:
            profile_image_url = (
                f"http://localhost:5000/api/admin/groups/{group.id}/image"
            )

    response = {
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "dark_mode": user.dark_mode,
            "language": user.language,
            "group_id": str(user.group_id) if user.group_id else None,
            "profile_image_url": profile_image_url,
        },
    }

    if remember_token:
        response["remember_token"] = remember_token

    current_app.logger.info(f"User login: {user.email}")

    return jsonify(response), 200


@auth_bp.route("/login-with-device", methods=["POST"])
def login_with_device():
    """Login using device trust (fingerprint) - skip password"""
    data = request.get_json()

    if not data or not data.get("email") or not data.get("remember_token"):
        return jsonify({"error": "Missing email or remember token"}), 400

    user = User.query.filter_by(email=data["email"]).first()

    if not user or user.remember_token != data["remember_token"]:
        return jsonify({"error": "Invalid credentials"}), 401

    device_fingerprint = get_device_fingerprint()

    # Check if device is trusted
    if not user.trusted_devices or device_fingerprint not in user.trusted_devices:
        return jsonify({"error": "Device not trusted"}), 403

    user.last_login_at = datetime.utcnow()
    user.last_login_ip = request.remote_addr
    user.trusted_devices[device_fingerprint]["last_used"] = (
        datetime.utcnow().isoformat()
    )
    db.session.commit()

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    current_app.logger.info(f"Device-based login: {user.email}")

    return jsonify(
        {
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
            },
        }
    ), 200


@auth_bp.route("/biometric-auth", methods=["POST"])
def biometric_auth():
    """Handle biometric authentication (fingerprint/faceID)"""
    data = request.get_json()

    if not data or not data.get("user_id"):
        return jsonify({"error": "Missing user_id"}), 400

    user = User.query.get(data["user_id"])

    if not user or not user.is_active:
        return jsonify({"error": "User not found"}), 404

    # In production, verify biometric data with WebAuthn
    # For now, we'll trust the client's biometric verification
    # and issue tokens based on device trust

    device_fingerprint = get_device_fingerprint()

    if not user.trusted_devices or device_fingerprint not in user.trusted_devices:
        return jsonify({"error": "Device not trusted"}), 403

    user.last_login_at = datetime.utcnow()
    user.last_login_ip = request.remote_addr
    db.session.commit()

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    current_app.logger.info(f"Biometric login: {user.email}")

    return jsonify(
        {
            "message": "Biometric authentication successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
    ), 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token"""
    user_id = get_jwt_identity()
    access_token = create_access_token(identity=user_id)

    return jsonify({"access_token": access_token}), 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """User logout"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if user:
        send_email(
            user.email,
            "Logout Notification",
            f"Your account was logged out from {request.remote_addr}",
        )
        current_app.logger.info(f"User logout: {user.email}")

    return jsonify({"message": "Logout successful"}), 200


@auth_bp.route("/password-reset-request", methods=["POST"])
def password_reset_request():
    """Request password reset"""
    data = request.get_json()

    if not data or not data.get("email"):
        return jsonify({"error": "Email required"}), 400

    user = User.query.filter_by(email=data["email"]).first()

    if not user:
        # Don't reveal if email exists (security best practice)
        return jsonify({"message": "If email exists, reset link sent"}), 200

    reset_token = secrets.token_urlsafe(32)
    user.reset_token = reset_token
    user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
    db.session.commit()

    reset_url = f"{request.host_url}reset-password?token={reset_token}"
    send_email(
        user.email,
        "Password Reset Request",
        f"Click the link to reset your password: {reset_url}",
    )

    current_app.logger.info(f"Password reset requested for: {user.email}")

    return jsonify({"message": "Reset link sent to email"}), 200


@auth_bp.route("/password-reset", methods=["POST"])
def password_reset():
    """Reset password with token"""
    data = request.get_json()

    if not data or not data.get("token") or not data.get("new_password"):
        return jsonify({"error": "Missing token or password"}), 400

    if len(data["new_password"]) < 15:
        return jsonify({"error": "Password must be at least 15 characters"}), 400

    user = User.query.filter_by(reset_token=data["token"]).first()

    if (
        not user
        or not user.reset_token_expiry
        or datetime.utcnow() > user.reset_token_expiry
    ):
        return jsonify({"error": "Invalid or expired reset token"}), 401

    user.password_hash = generate_password_hash(data["new_password"])
    user.reset_token = None
    user.reset_token_expiry = None
    db.session.commit()

    send_email(
        user.email, "Password Changed", "Your password has been successfully changed"
    )

    current_app.logger.info(f"Password reset for: {user.email}")

    return jsonify({"message": "Password reset successfully"}), 200


@auth_bp.route("/admin/login", methods=["POST", "OPTIONS"])
def admin_login():
    """Admin login with MFA support"""
    # Handle CORS preflight
    if request.method == "OPTIONS":
        return "", 200

    try:
        data = request.get_json()

        if not data or not data.get("email") or not data.get("password"):
            return jsonify({"error": "Missing email or password"}), 400

        admin = AdminUser.query.filter_by(email=data["email"]).first()

        if not admin:
            current_app.logger.warning(
                f"Login attempt for non-existent admin: {data.get('email')}"
            )
            return jsonify({"error": "Invalid credentials"}), 401

        if not check_password_hash(admin.password_hash, data["password"]):
            admin.failed_login_attempts += 1
            admin.last_failed_login = datetime.utcnow()
            db.session.commit()
            current_app.logger.warning(f"Failed login attempt for {admin.email}")
            return jsonify({"error": "Invalid credentials"}), 401

        # If MFA is enabled, send code instead of token
        if admin.mfa_enabled:
            mfa_code = secrets.randbelow(1000000)
            admin.mfa_temp_code = str(mfa_code).zfill(6)
            admin.mfa_code_expiry = datetime.utcnow() + timedelta(minutes=5)
            db.session.commit()

            # Log MFA code for development purposes
            current_app.logger.info(
                f"🔐 MFA Code Generated for {admin.email}: {admin.mfa_temp_code}"
            )

            send_email(
                admin.email, "STIP Admin - MFA Code", f"Your MFA code is: {mfa_code}"
            )

            return jsonify({"message": "MFA code sent", "mfa_required": True}), 200

        # No MFA, issue tokens directly
        admin.failed_login_attempts = 0
        admin.last_login_at = datetime.utcnow()
        admin.session_token = secrets.token_urlsafe(32)
        admin.session_expires = datetime.utcnow() + timedelta(minutes=15)
        db.session.commit()

        access_token = create_access_token(identity=admin.id)
        refresh_token = create_refresh_token(identity=admin.id)

        current_app.logger.info(f"✅ Admin login: {admin.email}")

        return jsonify(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "session_token": admin.session_token,
                "admin": {
                    "id": admin.id,
                    "email": admin.email,
                    "username": admin.username
                    if hasattr(admin, "username")
                    else admin.email,
                },
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error in admin login: {str(e)}")
        return jsonify({"error": "Login failed"}), 500


@auth_bp.route("/admin/mfa-verify", methods=["POST", "OPTIONS"])
def admin_mfa_verify():
    """Verify admin MFA code"""
    # Handle CORS preflight
    if request.method == "OPTIONS":
        return "", 200

    try:
        data = request.get_json()

        if not data or not data.get("email") or not data.get("mfa_code"):
            return jsonify({"error": "Missing email or MFA code"}), 400

        admin = AdminUser.query.filter_by(email=data["email"]).first()

        if not admin:
            return jsonify({"error": "Admin not found"}), 404

        if not admin.mfa_temp_code or not admin.mfa_code_expiry:
            return jsonify({"error": "No active MFA code"}), 400

        if datetime.utcnow() > admin.mfa_code_expiry:
            admin.mfa_temp_code = None
            db.session.commit()
            return jsonify({"error": "MFA code expired"}), 401

        if admin.mfa_temp_code != data["mfa_code"]:
            current_app.logger.warning(f"Invalid MFA code attempt for {admin.email}")
            return jsonify({"error": "Invalid MFA code"}), 401

        # MFA verified
        admin.failed_login_attempts = 0
        admin.last_login_at = datetime.utcnow()
        admin.session_token = secrets.token_urlsafe(32)
        admin.session_expires = datetime.utcnow() + timedelta(minutes=15)
        admin.mfa_temp_code = None
        admin.mfa_code_expiry = None
        db.session.commit()

        access_token = create_access_token(identity=admin.id)

        current_app.logger.info(f"✅ Admin MFA verified: {admin.email}")

        return jsonify(
            {"access_token": access_token, "session_token": admin.session_token}
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error in MFA verification: {str(e)}")
        return jsonify({"error": "MFA verification failed"}), 500


@auth_bp.route("/admin/setup-mfa", methods=["POST"])
@jwt_required()
def setup_mfa():
    """Setup MFA for admin user - returns QR code"""
    admin_id = get_jwt_identity()
    admin = AdminUser.query.get(admin_id)

    if not admin:
        return jsonify({"error": "Admin not found"}), 404

    # Generate MFA secret
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp.provisioning_uri(name=admin.email, issuer_name="STIP Admin"))
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)
    qr_code_b64 = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")

    # Store secret temporarily for verification
    admin.mfa_secret_temp = secret
    db.session.commit()

    return jsonify(
        {
            "qr_code": qr_code_b64,
            "secret": secret,
            "message": "Scan QR code with authenticator app, then verify with code",
        }
    ), 200


@auth_bp.route("/admin/verify-mfa", methods=["POST"])
@jwt_required()
def verify_mfa():
    """Verify MFA setup"""
    admin_id = get_jwt_identity()
    admin = AdminUser.query.get(admin_id)

    if not admin:
        return jsonify({"error": "Admin not found"}), 404

    data = request.get_json()

    if not data or not data.get("code"):
        return jsonify({"error": "MFA code required"}), 400

    if not admin.mfa_secret_temp:
        return jsonify({"error": "No MFA setup in progress"}), 400

    totp = pyotp.TOTP(admin.mfa_secret_temp)

    if not totp.verify(data["code"]):
        return jsonify({"error": "Invalid MFA code"}), 401

    # Enable MFA
    admin.mfa_secret = admin.mfa_secret_temp
    admin.mfa_secret_temp = None
    admin.mfa_enabled = True
    db.session.commit()

    current_app.logger.info(f"MFA enabled for admin: {admin.email}")

    return jsonify({"message": "MFA enabled successfully"}), 200


@auth_bp.route("/admin/logout", methods=["POST"])
@jwt_required()
def admin_logout():
    """Admin logout"""
    admin_id = get_jwt_identity()
    admin = AdminUser.query.get(admin_id)

    if admin:
        admin.session_token = None
        admin.session_expires = None
        db.session.commit()
        current_app.logger.info(f"Admin logout: {admin.email}")

    return jsonify({"message": "Logout successful"}), 200
