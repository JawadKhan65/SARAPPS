from flask import Blueprint, request, jsonify, current_app, render_template
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)
from werkzeug.security import generate_password_hash, check_password_hash
from core.extensions import db, mail
from core.models import User, AdminUser
from flask_mail import Message
import os
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
import pyotp
import qrcode
from io import BytesIO
import base64
from core.config.firebase_config import (
    verify_firebase_token,
    create_firebase_user,
    delete_firebase_user,
)

auth_bp = Blueprint("auth", __name__)

# Password policy
MIN_PASSWORD_LENGTH = 9
MAX_PASSWORD_LENGTH = 64


@auth_bp.route("/health", methods=["GET"])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "ok", "message": "Backend is running"}), 200


def send_email(recipient, subject, body, html=None):
    """Send email notification"""
    try:
        msg = Message(subject=subject, recipients=[recipient])
        msg.body = body
        if html:
            msg.html = html
            # Attach inline logo if template references cid:stip_logo
            try:
                if "cid:stip_logo" in html:
                    static_dir = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)), "static"
                    )
                    logo_path_small = os.path.join(static_dir, "logo-small.png")
                    logo_path = os.path.join(static_dir, "logo.png")
                    chosen_path = (
                        logo_path_small
                        if os.path.isfile(logo_path_small)
                        else logo_path
                        if os.path.isfile(logo_path)
                        else None
                    )
                    if chosen_path:
                        with open(chosen_path, "rb") as f:
                            img_bytes = f.read()
                        # Attach as inline with Content-ID matching cid reference
                        msg.attach(
                            filename=os.path.basename(chosen_path),
                            content_type="image/png",
                            data=img_bytes,
                            disposition="inline",
                            headers={"Content-ID": "<stip_logo>"},
                        )
                        current_app.logger.info(
                            f"Attached inline logo for email (size: {len(img_bytes)} bytes)"
                        )
                    else:
                        current_app.logger.warning(
                            "Logo image not found in backend/static; skipping inline attachment"
                        )
            except Exception as attach_err:
                current_app.logger.error(
                    f"Failed to attach inline logo: {str(attach_err)}"
                )
            current_app.logger.info(
                f"Sending HTML email to {recipient}: {subject} (HTML length: {len(html)} chars)"
            )
        else:
            current_app.logger.info(
                f"Sending plain text email to {recipient}: {subject}"
            )
        mail.send(msg)
        current_app.logger.info(f"✅ Email sent successfully to {recipient}")
    except Exception as e:
        current_app.logger.error(f"❌ Failed to send email to {recipient}: {str(e)}")
        import traceback

        current_app.logger.error(f"Traceback: {traceback.format_exc()}")


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

    # Validate password length (minimum and maximum)
    password = data.get("password", "")
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify(
            {"error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}
        ), 400
    if len(password) > MAX_PASSWORD_LENGTH:
        return jsonify(
            {"error": f"Password must be at most {MAX_PASSWORD_LENGTH} characters"}
        ), 400

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


@auth_bp.route("/login", methods=["POST", "OPTIONS"])
def login():
    """User login with device fingerprint and remember token"""
    if request.method == "OPTIONS":
        # Preflight is handled by Flask-CORS
        return "", 204

    data = request.get_json()
    current_app.logger.info(
        f"Login attempt from {request.remote_addr} for email: {data.get('email') if data else 'N/A'}"
    )

    if not data or not data.get("email") or not data.get("password"):
        current_app.logger.warning(
            f"Missing credentials in login request from {request.remote_addr}"
        )
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

    # Generate and send OTP for login verification
    current_app.logger.info(f"🔐 Generating OTP for user: {user.email}")
    otp_code = secrets.randbelow(1000000)
    user.otp_code = str(otp_code).zfill(6)
    user.otp_code_expiry = datetime.utcnow() + timedelta(minutes=5)
    user.failed_login_attempts = 0
    db.session.commit()

    # Log OTP code for development
    current_app.logger.info(f"🔐 OTP Generated for {user.email}: {user.otp_code}")

    # Send OTP email
    try:
        html_content = render_template(
            "otp_email.html",
            username=user.username or user.email.split("@")[0],
            otp_code=user.otp_code,
            expiry_minutes=5,
        )
        send_email(
            user.email,
            "STIP - Your Login Verification Code",
            f"Your verification code is: {user.otp_code}\n\nThis code will expire in 5 minutes.",
            html=html_content,
        )
        current_app.logger.info(f"✅ OTP email sent to {user.email}")
    except Exception as e:
        current_app.logger.error(f"Failed to send OTP email: {str(e)}")

    return jsonify(
        {
            "message": "OTP sent to email",
            "otp_required": True,
            "email": user.email,
        }
    ), 200


@auth_bp.route("/verify-otp", methods=["POST", "OPTIONS"])
def verify_otp():
    """Verify OTP and complete user login"""
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.get_json()

    if not data or not data.get("email") or not data.get("otp_code"):
        return jsonify({"error": "Missing email or OTP code"}), 400

    user = User.query.filter_by(email=data["email"]).first()

    if not user:
        return jsonify({"error": "User not found"}), 404

    if not user.otp_code or not user.otp_code_expiry:
        return jsonify({"error": "No active OTP code"}), 400

    if datetime.utcnow() > user.otp_code_expiry:
        user.otp_code = None
        db.session.commit()
        return jsonify({"error": "OTP code expired"}), 401

    if user.otp_code != data["otp_code"]:
        current_app.logger.warning(f"Invalid OTP attempt for user: {user.email}")
        return jsonify({"error": "Invalid OTP code"}), 401

    # OTP verified - complete login
    user.last_login = datetime.utcnow()
    user.last_login_ip = request.remote_addr
    user.otp_code = None
    user.otp_code_expiry = None

    # Handle device fingerprint and remember login
    device_fingerprint = get_device_fingerprint()
    remember_token = None

    if data.get("remember_login"):
        remember_token = secrets.token_urlsafe(32)
        user.remember_token = remember_token

        if user.trusted_devices is None:
            user.trusted_devices = []

        # Add device to trusted devices list if not already present
        device_info = {
            "fingerprint": device_fingerprint,
            "user_agent": request.headers.get("User-Agent", ""),
            "trusted_at": datetime.utcnow().isoformat(),
            "last_used": datetime.utcnow().isoformat(),
        }

        # Remove existing entry for this device if present
        user.trusted_devices = [
            d
            for d in user.trusted_devices
            if d.get("fingerprint") != device_fingerprint
        ]
        # Add the new/updated device info
        user.trusted_devices.append(device_info)

    db.session.commit()

    # Send successful login notification (HTML template)
    try:
        html_content = render_template(
            "login_notification.html",
            username=user.username or user.email.split("@")[0],
            login_time=datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC"),
            ip_address=request.remote_addr or "Unknown",
            device=request.headers.get("User-Agent", "Unknown Device")[:50],
        )
        send_email(
            user.email,
            "STIP - New Login Detected",
            f"New login to your STIP account at {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}",
            html=html_content,
        )
    except Exception as e:
        current_app.logger.error(f"Failed to send login notification: {str(e)}")

    # Create tokens
    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    # Get profile image from group if user is in a group
    profile_image_url = None
    if user.group_id:
        from core.models import UserGroup

        group = UserGroup.query.get(user.group_id)
        if group and group.profile_image_data:
            profile_image_url = (
                f"{request.url_root.rstrip('/')}/api/admin/groups/{group.id}/image"
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

    current_app.logger.info(f"✅ User login completed: {user.email}")

    return jsonify(response), 200


@auth_bp.route("/login-original", methods=["POST"])
def login_original():
    """DEPRECATED: Original login without OTP (kept for backward compatibility)"""
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
    user.last_login = datetime.utcnow()
    user.last_login_ip = request.remote_addr

    # Handle device fingerprint and remember login
    device_fingerprint = get_device_fingerprint()
    remember_token = None

    if data.get("remember_login"):
        remember_token = secrets.token_urlsafe(32)
        user.remember_token = remember_token

        if user.trusted_devices is None:
            user.trusted_devices = []

        # Add device to trusted devices list if not already present
        device_info = {
            "fingerprint": device_fingerprint,
            "user_agent": request.headers.get("User-Agent", ""),
            "trusted_at": datetime.utcnow().isoformat(),
            "last_used": datetime.utcnow().isoformat(),
        }

        # Remove existing entry for this device if present
        user.trusted_devices = [
            d
            for d in user.trusted_devices
            if d.get("fingerprint") != device_fingerprint
        ]
        # Add the new/updated device info
        user.trusted_devices.append(device_info)

    db.session.commit()

    # Send successful login notification (HTML template)
    try:
        html_content = render_template(
            "login_notification.html",
            username=user.username or user.email.split("@")[0],
            login_time=datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC"),
            ip_address=request.remote_addr or "Unknown",
            device=request.headers.get("User-Agent", "Unknown Device")[:50],
        )
        send_email(
            user.email,
            "STIP - New Login Detected",
            f"New login to your STIP account at {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}",
            html=html_content,
        )
    except Exception as e:
        current_app.logger.error(f"Failed to send login notification: {str(e)}")

    # Create tokens
    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    # Get profile image from group if user is in a group
    profile_image_url = None
    if user.group_id:
        from core.models import UserGroup

        group = UserGroup.query.get(user.group_id)
        if group and group.profile_image_data:
            profile_image_url = (
                f"{request.url_root.rstrip('/')}/api/admin/groups/{group.id}/image"
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
    if not user.trusted_devices:
        return jsonify({"error": "Device not trusted"}), 403

    # Find device in trusted devices list
    device_found = False
    for device in user.trusted_devices:
        if device.get("fingerprint") == device_fingerprint:
            device_found = True
            device["last_used"] = datetime.utcnow().isoformat()
            break

    if not device_found:
        return jsonify({"error": "Device not trusted"}), 403

    user.last_login = datetime.utcnow()
    user.last_login_ip = request.remote_addr
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

    user.last_login = datetime.utcnow()
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
        try:
            html_content = render_template(
                "logout_notification.html",
                username=user.username or user.email.split("@")[0],
                logout_time=datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC"),
                ip_address=request.remote_addr or "Unknown",
            )
            send_email(
                user.email,
                "STIP - Logout Notification",
                f"Your account was logged out from {request.remote_addr}",
                html=html_content,
            )
        except Exception as e:
            current_app.logger.error(f"Failed to send logout notification: {str(e)}")
        current_app.logger.info(f"User logout: {user.email}")

    return jsonify({"message": "Logout successful"}), 200


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    """Request password reset with OTP"""
    data = request.get_json()

    if not data or not data.get("email"):
        return jsonify({"error": "Email required"}), 400

    user = User.query.filter_by(email=data["email"]).first()

    # Always return a generic success response to avoid disclosing account existence
    if user:
        # Generate 6-digit OTP
        otp_code = secrets.randbelow(1000000)
        user.otp_code = str(otp_code).zfill(6)
        user.otp_code_expiry = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()

        current_app.logger.info(
            f"🔐 Password reset OTP for {user.email}: {user.otp_code}"
        )

        # Send OTP email
        try:
            html_content = render_template(
                "password_reset_otp.html",
                username=user.username or user.email.split("@")[0],
                otp_code=user.otp_code,
                expiry_minutes=10,
            )
            send_email(
                user.email,
                "STIP - Password Reset Verification Code",
                f"Your password reset verification code is: {user.otp_code}\n\nThis code will expire in 10 minutes.",
                html=html_content,
            )
            current_app.logger.info(f"✅ Password reset OTP sent to {user.email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send password reset OTP: {str(e)}")

    return jsonify(
        {
            "message": "If an account exists for this email, a verification code has been sent."
        }
    ), 200


@auth_bp.route("/verify-reset-otp", methods=["POST"])
def verify_reset_otp():
    """Verify OTP for password reset"""
    data = request.get_json()

    if not data or not data.get("email") or not data.get("otp_code"):
        return jsonify({"error": "Email and OTP code required"}), 400

    user = User.query.filter_by(email=data["email"]).first()

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    # Check OTP
    if not user.otp_code or not user.otp_code_expiry:
        return jsonify({"error": "No OTP request found"}), 401

    if datetime.utcnow() > user.otp_code_expiry:
        return jsonify({"error": "OTP has expired"}), 401

    if user.otp_code != data["otp_code"]:
        return jsonify({"error": "Invalid OTP code"}), 401

    # Generate a temporary reset token (valid for 10 minutes)
    reset_token = secrets.token_urlsafe(32)
    user.reset_token = reset_token
    user.reset_token_expiry = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()

    current_app.logger.info(f"✅ OTP verified for password reset: {user.email}")

    return jsonify({"message": "OTP verified", "reset_token": reset_token}), 200


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    """Reset password with verified token"""
    data = request.get_json()

    if not data or not data.get("reset_token") or not data.get("new_password"):
        return jsonify({"error": "Reset token and new password required"}), 400

    if len(data["new_password"]) < MIN_PASSWORD_LENGTH:
        return jsonify(
            {"error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}
        ), 400
    if len(data["new_password"]) > MAX_PASSWORD_LENGTH:
        return jsonify(
            {"error": f"Password must be at most {MAX_PASSWORD_LENGTH} characters"}
        ), 400

    user = User.query.filter_by(reset_token=data["reset_token"]).first()

    if (
        not user
        or not user.reset_token_expiry
        or datetime.utcnow() > user.reset_token_expiry
    ):
        return jsonify({"error": "Invalid or expired reset token"}), 401

    # Update password
    user.password_hash = generate_password_hash(data["new_password"])
    user.reset_token = None
    user.reset_token_expiry = None
    user.otp_code = None
    user.otp_code_expiry = None
    db.session.commit()

    # Send confirmation email
    send_email(
        user.email,
        "STIP - Password Changed Successfully",
        "Your password has been successfully changed. If you did not make this change, please contact support immediately.",
    )

    current_app.logger.info(f"Password reset completed for: {user.email}")

    return jsonify({"message": "Password reset successfully"}), 200


@auth_bp.route("/admin/login", methods=["POST", "OPTIONS"])
def admin_login():
    """Admin login with Firebase Authentication"""
    # Handle CORS preflight
    if request.method == "OPTIONS":
        return "", 200

    try:
        data = request.get_json()
        current_app.logger.info(f"🔐 Admin login attempt received")
        current_app.logger.info(
            f"Request data keys: {list(data.keys()) if data else 'None'}"
        )

        # Check if Firebase ID token is provided (client-side auth)
        if data.get("firebase_token"):
            current_app.logger.info("🎫 Firebase token received, verifying...")
            current_app.logger.info(f"Token preview: {data['firebase_token'][:50]}...")
            # Verify Firebase token
            decoded_token = verify_firebase_token(data["firebase_token"])

            if not decoded_token:
                current_app.logger.error("❌ Firebase token verification failed")
                return jsonify({"error": "Invalid Firebase token"}), 401

            current_app.logger.info(f"✅ Firebase token verified successfully")
            current_app.logger.info(f"Decoded token UID: {decoded_token.get('uid')}")
            current_app.logger.info(
                f"Decoded token email: {decoded_token.get('email')}"
            )

            email = decoded_token.get("email")

            # Check if admin exists in database
            current_app.logger.info(f"🔍 Searching for admin in database: {email}")
            admin = AdminUser.query.filter_by(email=email).first()

            if not admin:
                current_app.logger.error(f"❌ Admin not found in database: {email}")
                return jsonify({"error": "Admin not found"}), 404

            current_app.logger.info(
                f"✅ Admin found: {admin.email} (ID: {admin.id})"
            )  # Update last login
            current_app.logger.info("💾 Updating admin session...")
            admin.failed_login_attempts = 0
            admin.last_login_at = datetime.utcnow()
            admin.session_token = secrets.token_urlsafe(32)
            admin.session_expires = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
            current_app.logger.info("✅ Admin session updated")

            current_app.logger.info("🎫 Creating JWT tokens...")
            access_token = create_access_token(identity=admin.id)
            refresh_token = create_refresh_token(identity=admin.id)
            current_app.logger.info("✅ JWT tokens created")

            current_app.logger.info(
                f"✅ Admin login via Firebase successful: {admin.email}"
            )

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

        # Fallback to email/password (for backward compatibility)
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

        # Check if MFA is enabled, send email code
        if admin.mfa_enabled:
            current_app.logger.info(
                f"🔐 MFA enabled for {admin.email}, generating code..."
            )
            mfa_code = secrets.randbelow(1000000)
            admin.mfa_temp_code = str(mfa_code).zfill(6)
            admin.mfa_code_expiry = datetime.utcnow() + timedelta(minutes=5)
            db.session.commit()

            # Log MFA code for development
            current_app.logger.info(
                f"🔐 MFA Code Generated for {admin.email}: {admin.mfa_temp_code}"
            )

            # Send email with code
            html_content = render_template(
                "otp_email.html",
                username=admin.email.split("@")[0],
                otp_code=admin.mfa_temp_code,
                expiry_minutes=5,
            )
            send_email(
                admin.email,
                "STIP - Your Verification Code",
                f"Your verification code is: {admin.mfa_temp_code}\n\nThis code will expire in 5 minutes.",
                html=html_content,
            )

            current_app.logger.info(f"✅ MFA code sent to {admin.email}")
            return jsonify(
                {"message": "MFA code sent to email", "mfa_required": True}
            ), 200

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
        current_app.logger.error(f"❌ Error in admin login: {str(e)}")
        import traceback

        current_app.logger.error(f"Full traceback:\n{traceback.format_exc()}")
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

        # Send login notification email
        try:
            html_content = render_template(
                "login_notification.html",
                username=admin.email.split("@")[0],
                login_time=datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC"),
                ip_address=request.remote_addr or "Unknown",
                device=request.headers.get("User-Agent", "Unknown Device")[:50],
            )
            send_email(
                admin.email,
                "STIP - New Login Detected",
                f"New login to your STIP account at {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}",
                html=html_content,
            )
        except Exception as e:
            current_app.logger.error(f"Failed to send login notification: {str(e)}")

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
