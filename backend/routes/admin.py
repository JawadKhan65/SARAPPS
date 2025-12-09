from flask import Blueprint, request, jsonify, current_app, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from core.extensions import db, mail
from flask_mail import Message
from core.models import (
    AdminUser,
    User,
    CrawlerStatistics,
    SystemConfig,
    Crawler,
    UserGroup,
)
from services.scraper_manager import get_scraper_manager, cleanup_scraper_manager
from utils.schedule_helper import (
    cron_to_human,
    human_to_cron,
    get_schedule_display_text,
    SCHEDULE_PRESETS,
)
import asyncio
import uuid
import os
from jobs.tasks import get_crawler_job_status, get_worker_health

admin_bp = Blueprint("admin", __name__)


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
            except Exception as attach_err:
                current_app.logger.error(
                    f"Failed to attach inline logo: {str(attach_err)}"
                )
        mail.send(msg)
        current_app.logger.info(f"✅ Email sent successfully to {recipient}")
    except Exception as e:
        current_app.logger.error(f"❌ Failed to send email to {recipient}: {str(e)}")


def get_group_image_url(group):
    """Helper function to get group image URL"""
    if group and group.profile_image_data:
        return f"/api/admin/groups/{group.id}/image"
    return None


def verify_admin_session(admin_id):
    """Verify admin exists (JWT already validates token)"""
    admin = AdminUser.query.get(admin_id)
    if not admin:
        return None

    # Update last activity (optional session extension)
    if hasattr(admin, "session_expires") and admin.session_expires:
        from datetime import timedelta

        admin.session_expires = datetime.utcnow() + timedelta(minutes=15)
        db.session.commit()

    return admin


@admin_bp.route("/users", methods=["GET"])
@jwt_required()
def list_users():
    """List all users with statistics"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = User.query.filter_by(is_deleted=False).paginate(
        page=page, per_page=per_page, error_out=False
    )

    users = []
    for user in pagination.items:
        # Get group info if user is in a group
        group_info = None
        if user.group_id:
            group = UserGroup.query.get(user.group_id)
            if group:
                group_info = {
                    "id": group.id,
                    "name": group.name,
                    "profile_image_url": get_group_image_url(group),
                }

        users.append(
            {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "is_active": user.is_active,
                "is_deleted": user.is_deleted,
                "storage_used_mb": user.storage_used_mb,
                "group": group_info,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            }
        )

    return jsonify(
        {
            "users": users,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
            "per_page": per_page,
        }
    ), 200


@admin_bp.route("/users/<user_id>/block", methods=["POST"])
@jwt_required()
def block_user(user_id):
    """Block a user account"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.is_deleted:
        return jsonify({"error": "Cannot block a deleted user"}), 400

    try:
        user.is_active = False
        db.session.commit()

        current_app.logger.info(f"User blocked by admin: {user.email}")

        return jsonify({"message": "User blocked", "is_active": False}), 200

    except Exception as e:
        current_app.logger.error(f"Error blocking user: {str(e)}")
        return jsonify({"error": "Failed to block user"}), 500


@admin_bp.route("/users/<user_id>/unblock", methods=["POST"])
@jwt_required()
def unblock_user(user_id):
    """Unblock a user account"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.is_deleted:
        return jsonify({"error": "Cannot unblock a deleted user"}), 400

    try:
        user.is_active = True
        db.session.commit()

        current_app.logger.info(f"User unblocked by admin: {user.email}")

        return jsonify({"message": "User unblocked", "is_active": True}), 200

    except Exception as e:
        current_app.logger.error(f"Error unblocking user: {str(e)}")
        return jsonify({"error": "Failed to unblock user"}), 500


@admin_bp.route("/users/<user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    """Permanently delete a user account"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        import os
        from core.models import UploadedImage, MatchResult

        user_email = user.email

        # Delete user's uploaded images from filesystem
        uploaded_images = UploadedImage.query.filter_by(user_id=user_id).all()

        for img in uploaded_images:
            if os.path.exists(img.file_path):
                os.remove(img.file_path)
            if img.processed_image_path and os.path.exists(img.processed_image_path):
                os.remove(img.processed_image_path)

        # Delete match results and uploaded images from database
        MatchResult.query.filter_by(user_id=user_id).delete()
        UploadedImage.query.filter_by(user_id=user_id).delete()

        # Permanently delete user from database
        db.session.delete(user)

        db.session.commit()

        current_app.logger.info(f"User permanently deleted by admin: {user_email}")

        return jsonify({"message": "User permanently deleted"}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting user: {str(e)}")
        return jsonify({"error": "Failed to delete user"}), 500


@admin_bp.route("/users/<user_id>/password", methods=["PUT"])
@jwt_required()
def change_user_password(user_id):
    """Change a user's password (admin only)"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.is_deleted:
        return jsonify({"error": "Cannot change password for deleted user"}), 400

    data = request.get_json()
    new_password = data.get("new_password")

    if not new_password:
        return jsonify({"error": "New password is required"}), 400

    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    try:
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()

        current_app.logger.info(
            f"Admin {admin.email} changed password for user {user.email}"
        )

        return jsonify({"message": "Password changed successfully"}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error changing user password: {str(e)}")
        return jsonify({"error": "Failed to change password"}), 500


@admin_bp.route("/users/<user_id>", methods=["PUT", "PATCH"])
@jwt_required()
def update_user(user_id):
    """Update user information (admin only)"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.is_deleted:
        return jsonify({"error": "Cannot update deleted user"}), 400

    data = request.get_json()

    try:
        # Update group if provided
        if "group_id" in data:
            group_id = data.get("group_id")
            if group_id:
                # Verify group exists
                group = UserGroup.query.get(group_id)
                if not group:
                    return jsonify({"error": "Group not found"}), 404
                user.group_id = group_id
            else:
                # Allow removing group by setting to None
                user.group_id = None

        db.session.commit()

        current_app.logger.info(f"Admin {admin.email} updated user {user.email}")

        return jsonify(
            {
                "message": "User updated successfully",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "group_id": user.group_id,
                },
            }
        ), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating user: {str(e)}")
        return jsonify({"error": "Failed to update user"}), 500


@admin_bp.route("/users", methods=["POST", "OPTIONS"])
@jwt_required()
def create_user():
    """Create a new user"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        data = request.get_json()

        # Validate required fields
        if (
            not data.get("email")
            or not data.get("username")
            or not data.get("password")
        ):
            return jsonify({"error": "Email, username, and password are required"}), 400

        # Check if email already exists
        if User.query.filter_by(email=data["email"]).first():
            return jsonify({"error": "Email already exists"}), 409

        # Check if username already exists
        if User.query.filter_by(username=data["username"]).first():
            return jsonify({"error": "Username already exists"}), 409

        # Create new user
        new_user = User(
            id=str(uuid.uuid4()),
            email=data["email"],
            username=data["username"],
            password_hash=generate_password_hash(data["password"]),
            is_active=data.get("is_active", True),
            group_id=data.get("group_id"),
        )

        db.session.add(new_user)
        db.session.commit()

        current_app.logger.info(f"User created by admin: {new_user.email}")

        # Send welcome email with credentials
        try:
            html_content = render_template(
                "welcome_user_email.html",
                username=new_user.username,
                email=new_user.email,
                password=data["password"],  # Send plain password in welcome email
            )
            send_email(
                new_user.email,
                "STIP - Welcome! Your Account Credentials",
                f"Welcome to STIP! Your account has been created.\n\nEmail: {new_user.email}\nPassword: {data['password']}\n\nPlease change your password after first login.",
                html=html_content,
            )
            current_app.logger.info(f"✅ Welcome email sent to {new_user.email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send welcome email: {str(e)}")

        # Get profile image from group if assigned
        profile_image_url = None
        if new_user.group_id:
            group = UserGroup.query.get(new_user.group_id)
            if group:
                profile_image_url = get_group_image_url(group)

        return jsonify(
            {
                "message": "User created successfully",
                "user": {
                    "id": new_user.id,
                    "email": new_user.email,
                    "username": new_user.username,
                    "is_active": new_user.is_active,
                    "group_id": new_user.group_id,
                    "profile_image_url": profile_image_url,
                    "created_at": new_user.created_at.isoformat(),
                },
            }
        ), 201

    except Exception as e:
        current_app.logger.error(f"Error creating user: {e}")
        db.session.rollback()
        return jsonify({"error": f"Failed to create user: {str(e)}"}), 500


@admin_bp.route("/groups", methods=["GET", "OPTIONS"])
@jwt_required()
def list_groups():
    """List all user groups"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        groups = UserGroup.query.all()

        groups_data = []
        for group in groups:
            groups_data.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "description": group.description,
                    "profile_image_url": get_group_image_url(group),
                    "user_count": group.users.count(),
                    "created_at": group.created_at.isoformat()
                    if group.created_at
                    else None,
                }
            )

        return jsonify({"groups": groups_data}), 200

    except Exception as e:
        current_app.logger.error(f"Error listing groups: {e}")
        return jsonify({"error": "Failed to list groups"}), 500


@admin_bp.route("/groups", methods=["POST"])
@jwt_required()
def create_group():
    """Create a new user group"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        data = request.get_json()

        if not data.get("name"):
            return jsonify({"error": "Group name is required"}), 400

        # Check if group name already exists
        if UserGroup.query.filter_by(name=data["name"]).first():
            return jsonify({"error": "Group name already exists"}), 409

        new_group = UserGroup(
            id=str(uuid.uuid4()),
            name=data["name"],
            description=data.get("description"),
            created_by=admin_id,
        )

        db.session.add(new_group)
        db.session.commit()

        current_app.logger.info(f"Group created by admin: {new_group.name}")

        return jsonify(
            {
                "message": "Group created successfully",
                "group": {
                    "id": new_group.id,
                    "name": new_group.name,
                    "description": new_group.description,
                    "profile_image_url": get_group_image_url(new_group),
                    "created_at": new_group.created_at.isoformat(),
                },
            }
        ), 201

    except Exception as e:
        current_app.logger.error(f"Error creating group: {e}")
        db.session.rollback()
        return jsonify({"error": f"Failed to create group: {str(e)}"}), 500


@admin_bp.route("/groups/<group_id>", methods=["PUT", "OPTIONS"])
@jwt_required()
def update_group(group_id):
    """Update a group"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        group = UserGroup.query.get(group_id)

        if not group:
            return jsonify({"error": "Group not found"}), 404

        data = request.get_json()

        if "name" in data:
            # Check if new name already exists
            existing = UserGroup.query.filter_by(name=data["name"]).first()
            if existing and existing.id != group_id:
                return jsonify({"error": "Group name already exists"}), 409
            group.name = data["name"]

        if "description" in data:
            group.description = data["description"]

        group.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify(
            {
                "message": "Group updated successfully",
                "group": {
                    "id": group.id,
                    "name": group.name,
                    "description": group.description,
                    "profile_image_url": get_group_image_url(group),
                },
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error updating group: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to update group"}), 500


@admin_bp.route("/groups/<group_id>", methods=["DELETE"])
@jwt_required()
def delete_group(group_id):
    """Delete a group"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        group = UserGroup.query.get(group_id)

        if not group:
            return jsonify({"error": "Group not found"}), 404

        # Unlink users from this group
        User.query.filter_by(group_id=group_id).update({"group_id": None})

        # Delete the group (image data is stored in database, will be deleted automatically)
        db.session.delete(group)
        db.session.commit()

        current_app.logger.info(f"Group deleted by admin: {group.name}")

        return jsonify({"message": "Group deleted successfully"}), 200

    except Exception as e:
        current_app.logger.error(f"Error deleting group: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to delete group"}), 500


@admin_bp.route("/groups/<group_id>/upload-image", methods=["POST", "OPTIONS"])
@jwt_required()
def upload_group_image(group_id):
    """Upload profile image for a group (stored as binary data in database)"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        group = UserGroup.query.get(group_id)

        if not group:
            return jsonify({"error": "Group not found"}), 404

        if "image" not in request.files:
            return jsonify({"error": "No image file provided"}), 400

        image_file = request.files["image"]

        if image_file.filename == "":
            return jsonify({"error": "No image selected"}), 400

        # Validate file type
        allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}
        if not (
            "." in image_file.filename
            and image_file.filename.rsplit(".", 1)[1].lower() in allowed_extensions
        ):
            return jsonify({"error": "Invalid image format"}), 400

        # Validate file size (max 5MB)
        image_file.seek(0, 2)  # Seek to end
        file_size = image_file.tell()
        image_file.seek(0)  # Reset to start

        if file_size > 5 * 1024 * 1024:  # 5MB
            return jsonify({"error": "Image size must be less than 5MB"}), 400

        # Read image binary data
        image_data = image_file.read()

        # Determine mimetype
        mimetype = image_file.content_type or "image/jpeg"

        # Update group with binary data
        group.profile_image_data = image_data
        group.profile_image_mimetype = mimetype
        group.profile_image_filename = image_file.filename
        group.updated_at = datetime.utcnow()

        db.session.commit()

        current_app.logger.info(f"Group image uploaded to database: {group.name}")

        return jsonify(
            {
                "message": "Image uploaded successfully",
                "profile_image_url": f"/api/admin/groups/{group_id}/image",
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error uploading group image: {e}")
        db.session.rollback()
        return jsonify({"error": f"Failed to upload image: {str(e)}"}), 500


@admin_bp.route("/groups/<group_id>/image", methods=["GET"])
def get_group_image(group_id):
    """Serve group profile image from database"""
    try:
        group = UserGroup.query.get(group_id)

        if not group or not group.profile_image_data:
            return jsonify({"error": "Image not found"}), 404

        from flask import send_file
        import io

        # Create file-like object from binary data
        image_io = io.BytesIO(group.profile_image_data)
        image_io.seek(0)

        return send_file(
            image_io,
            mimetype=group.profile_image_mimetype or "image/jpeg",
            as_attachment=False,
            download_name=group.profile_image_filename or f"{group.name}.jpg",
        )

    except Exception as e:
        current_app.logger.error(f"Error serving group image: {e}")
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/statistics", methods=["GET"])
@jwt_required()
def get_admin_statistics():
    """Get comprehensive system statistics"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    stats = CrawlerStatistics.query.first()

    if not stats:
        stats = CrawlerStatistics()

    total_users = User.query.filter_by(is_deleted=False).count()
    active_users = User.query.filter_by(is_deleted=False, is_active=True).count()
    total_uploads = (
        db.session.query(db.func.count())
        .select_from(__import__("models", fromlist=["UploadedImage"]).UploadedImage)
        .scalar()
        or 0
    )

    return jsonify(
        {
            "total_users": total_users,
            "active_users": active_users,
            "total_uploads": total_uploads,
            "unique_sole_images": stats.unique_sole_images,
            "unique_brands": stats.unique_brands,
            "total_crawlers": stats.total_crawlers,
            "average_matching_time_ms": stats.average_matching_time_ms,
            "last_updated": stats.last_updated.isoformat()
            if stats.last_updated
            else None,
        }
    ), 200


@admin_bp.route("/system-config", methods=["GET"])
@jwt_required()
def get_system_config():
    """Get system configuration"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    config = SystemConfig.query.first()

    if not config:
        return jsonify({"error": "System config not found"}), 404

    return jsonify(
        {
            "smtp_server": config.smtp_server,
            "smtp_port": config.smtp_port,
            "smtp_username": config.smtp_username,
            "smtp_security": config.smtp_security,
            "similarity_threshold": config.similarity_threshold,
            "batch_size": config.batch_size,
            "max_image_size_mb": config.max_image_size_mb,
            "session_timeout_minutes": config.session_timeout_minutes,
            "max_login_attempts": config.max_login_attempts,
            "lockout_duration_minutes": config.lockout_duration_minutes,
            "min_password_length": config.min_password_length,
            "last_updated": config.last_updated.isoformat()
            if config.last_updated
            else None,
        }
    ), 200


@admin_bp.route("/system-config", methods=["PUT"])
@jwt_required()
def update_system_config():
    """Update system configuration"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    config = SystemConfig.query.first()

    if not config:
        return jsonify({"error": "System config not found"}), 404

    data = request.get_json()

    try:
        if "smtp_server" in data:
            config.smtp_server = data["smtp_server"]

        if "smtp_port" in data:
            config.smtp_port = int(data["smtp_port"])

        if "smtp_username" in data:
            config.smtp_username = data["smtp_username"]

        if "smtp_password" in data:
            config.smtp_password = data["smtp_password"]

        if "smtp_security" in data:
            config.smtp_security = data["smtp_security"]

        if "similarity_threshold" in data:
            config.similarity_threshold = float(data["similarity_threshold"])

        if "batch_size" in data:
            config.batch_size = int(data["batch_size"])

        if "max_image_size_mb" in data:
            config.max_image_size_mb = int(data["max_image_size_mb"])

        if "session_timeout_minutes" in data:
            config.session_timeout_minutes = int(data["session_timeout_minutes"])

        if "min_password_length" in data:
            config.min_password_length = int(data["min_password_length"])

        config.last_updated = datetime.utcnow()
        config.updated_by = admin.email

        db.session.commit()

        current_app.logger.info(f"System config updated by admin: {admin.email}")

        return jsonify({"message": "Configuration updated"}), 200

    except Exception as e:
        current_app.logger.error(f"Error updating config: {str(e)}")
        return jsonify({"error": "Failed to update configuration"}), 500


@admin_bp.route("/email-template/<template_type>", methods=["GET"])
@jwt_required()
def get_email_template(template_type):
    """Get email template"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    config = SystemConfig.query.first()

    if not config:
        return jsonify({"error": "System config not found"}), 404

    valid_types = [
        "welcome",
        "failed_login",
        "successful_login",
        "logout",
        "delete_account",
    ]

    if template_type not in valid_types:
        return jsonify({"error": "Invalid template type"}), 400

    template_attr = f"{template_type}_template"
    subject_attr = f"{template_type}_subject"

    template = getattr(config, template_attr, None)
    subject = getattr(config, subject_attr, None)

    return jsonify({"type": template_type, "subject": subject, "body": template}), 200


@admin_bp.route("/email-template/<template_type>", methods=["PUT"])
@jwt_required()
def update_email_template(template_type):
    """Update email template"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    config = SystemConfig.query.first()

    if not config:
        return jsonify({"error": "System config not found"}), 404

    valid_types = [
        "welcome",
        "failed_login",
        "successful_login",
        "logout",
        "delete_account",
    ]

    if template_type not in valid_types:
        return jsonify({"error": "Invalid template type"}), 400

    data = request.get_json()

    try:
        if "subject" in data:
            setattr(config, f"{template_type}_subject", data["subject"])

        if "body" in data:
            setattr(config, f"{template_type}_template", data["body"])

        config.last_updated = datetime.utcnow()
        db.session.commit()

        current_app.logger.info(f"Email template updated by admin: {admin.email}")

        return jsonify({"message": "Template updated"}), 200

    except Exception as e:
        current_app.logger.error(f"Error updating template: {str(e)}")
        return jsonify({"error": "Failed to update template"}), 500


@admin_bp.route("/activity-log", methods=["GET"])
@jwt_required()
def get_activity_log():
    """Get system activity log (crawler runs, user actions, etc.)"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    # Get recent crawler activity
    crawlers = Crawler.query.order_by(Crawler.last_completed_at.desc()).limit(10).all()

    activity = []
    for crawler in crawlers:
        if crawler.last_completed_at:
            activity.append(
                {
                    "type": "crawler_run",
                    "description": f'Crawler "{crawler.name}" completed',
                    "timestamp": crawler.last_completed_at.isoformat(),
                    "duration_seconds": crawler.last_run_duration,
                }
            )

    return jsonify({"activity": activity, "total": len(activity)}), 200


# Dashboard Stats Endpoints
@admin_bp.route("/stats", methods=["GET", "OPTIONS"])
@jwt_required()
def get_dashboard_stats():
    """Get dashboard statistics"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()

        from core.models import MatchResult

        total_matches = MatchResult.query.count()

        crawlers_running = Crawler.query.filter_by(is_running=True).count()

        # Calculate actual database size
        try:
            from sqlalchemy import text

            result = db.session.execute(
                text("SELECT pg_database_size(current_database())")
            )
            db_size_bytes = result.scalar()
            db_size_mb = db_size_bytes / (1024 * 1024) if db_size_bytes else 0.0
        except Exception as e:
            current_app.logger.warning(f"Could not get DB size: {e}")
            db_size_mb = 0.0

        # Get actual cache hit rate from Redis if available
        cache_hit_rate = 0.0
        try:
            import redis

            redis_client = redis.from_url(
                current_app.config.get("REDIS_URL", "redis://localhost:6379/0")
            )
            info = redis_client.info("stats")

            keyspace_hits = info.get("keyspace_hits", 0)
            keyspace_misses = info.get("keyspace_misses", 0)

            total_requests = keyspace_hits + keyspace_misses
            if total_requests > 0:
                cache_hit_rate = keyspace_hits / total_requests
        except Exception as e:
            current_app.logger.debug(f"Could not get Redis cache stats: {e}")
            cache_hit_rate = 0.0

        return jsonify(
            {
                "total_users": total_users,
                "active_users": active_users,
                "total_matches": total_matches,
                "crawlers_running": crawlers_running,
                "db_size_mb": round(db_size_mb, 2),
                "cache_hit_rate": cache_hit_rate,
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error getting dashboard stats: {e}")
        return jsonify({"error": "Failed to load statistics"}), 500


@admin_bp.route("/stats/users", methods=["GET", "OPTIONS"])
@jwt_required()
def get_user_stats():
    """Get detailed user statistics"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        from datetime import timedelta

        now = datetime.utcnow()
        month_ago = now - timedelta(days=30)

        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        new_users = User.query.filter(User.created_at >= month_ago).count()
        blocked_users = User.query.filter_by(is_active=False).count()

        return jsonify(
            {
                "total_users": total_users,
                "active_users": active_users,
                "new_users": new_users,
                "blocked_users": blocked_users,
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error getting user stats: {e}")
        return jsonify({"error": "Failed to load user statistics"}), 500


@admin_bp.route("/stats/matches", methods=["GET", "OPTIONS"])
@jwt_required()
def get_match_stats():
    """Get detailed match statistics"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        from core.models import MatchResult

        total_matches = MatchResult.query.count()

        # Calculate average confidence dynamically from all confidence scores
        if total_matches > 0:
            all_matches = MatchResult.query.all()
            total_confidence = 0
            total_scores = 0
            perfect_count = 0

            for match in all_matches:
                scores = []
                if match.primary_confidence and match.primary_confidence > 0:
                    scores.append(match.primary_confidence)
                if match.secondary_confidence and match.secondary_confidence > 0:
                    scores.append(match.secondary_confidence)
                if match.tertiary_confidence and match.tertiary_confidence > 0:
                    scores.append(match.tertiary_confidence)
                if match.quaternary_confidence and match.quaternary_confidence > 0:
                    scores.append(match.quaternary_confidence)

                if scores:
                    match_avg = sum(scores) / len(scores)
                    total_confidence += match_avg
                    total_scores += 1

                    # Count as perfect if average is >= 0.95
                    if match_avg >= 0.95:
                        perfect_count += 1

            avg_confidence = total_confidence / total_scores if total_scores > 0 else 0
            perfect_matches = perfect_count
        else:
            avg_confidence = 0
            perfect_matches = 0

        return jsonify(
            {
                "total_matches": total_matches,
                "avg_confidence": float(avg_confidence),
                "perfect_matches": perfect_matches,
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error getting match stats: {e}")
        return jsonify({"error": "Failed to load match statistics"}), 500


@admin_bp.route("/stats/crawlers", methods=["GET", "OPTIONS"])
@jwt_required()
def get_crawler_stats():
    """Get detailed crawler statistics"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        from core.models import SoleImage, CrawlerRun

        total_items = SoleImage.query.count()
        active_crawlers = Crawler.query.filter_by(is_active=True).count()
        running_crawlers = Crawler.query.filter_by(is_running=True).count()

        # Calculate success rate based on crawler runs
        total_runs = CrawlerRun.query.count()
        successful_runs = CrawlerRun.query.filter_by(status="completed").count()

        if total_runs > 0:
            success_rate = successful_runs / total_runs
        else:
            # Fallback: count crawlers that have scraped items
            total_crawlers = Crawler.query.count()
            successful = Crawler.query.filter(Crawler.items_scraped > 0).count()
            success_rate = (successful / total_crawlers) if total_crawlers > 0 else 0

        # Get total unique images added
        unique_images = (
            db.session.query(db.func.sum(Crawler.unique_images_added)).scalar() or 0
        )

        # Calculate average uniqueness percentage
        crawlers_with_data = Crawler.query.filter(Crawler.items_scraped > 0).all()
        if crawlers_with_data:
            avg_uniqueness = sum(
                (c.unique_images_added / c.items_scraped * 100)
                for c in crawlers_with_data
                if c.items_scraped > 0
            ) / len(crawlers_with_data)
        else:
            avg_uniqueness = 0

        return jsonify(
            {
                "total_items": total_items,
                "active_crawlers": active_crawlers,
                "running_crawlers": running_crawlers,
                "success_rate": success_rate,
                "total_runs": total_runs,
                "successful_runs": successful_runs,
                "unique_images": int(unique_images),
                "avg_uniqueness": round(avg_uniqueness, 2),
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error getting crawler stats: {e}")
        return jsonify({"error": "Failed to load crawler statistics"}), 500


@admin_bp.route("/crawlers", methods=["GET", "OPTIONS"])
@jwt_required(optional=True)
def list_crawlers():
    """List all crawlers with their status"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        from core.models import CrawlerRun

        crawlers = Crawler.query.all()

        crawler_list = []
        for crawler in crawlers:
            # Get latest run
            latest_run = (
                CrawlerRun.query.filter_by(crawler_id=crawler.id)
                .order_by(CrawlerRun.started_at.desc())
                .first()
            )

            crawler_list.append(
                {
                    "id": crawler.id,
                    "name": crawler.name,
                    "website_url": crawler.website_url,
                    "scraper_module": crawler.scraper_module,
                    "is_active": crawler.is_active,
                    "is_running": crawler.is_running,
                    "run_type": crawler.run_type,
                    "progress_percentage": crawler.progress_percentage or 0,
                    "current_batch": crawler.current_batch or 0,
                    "total_batches": crawler.total_batches or 0,
                    "items_scraped": crawler.items_scraped or 0,
                    "current_run_items": crawler.current_run_items or 0,
                    "unique_images_added": crawler.unique_images_added or 0,
                    "duplicate_count": crawler.duplicate_count or 0,
                    "uniqueness_percentage": crawler.uniqueness_percentage or 0,
                    "min_uniqueness_threshold": crawler.min_uniqueness_threshold or 30,
                    "total_runs": crawler.total_runs or 0,
                    "last_run_at": crawler.last_run_at.isoformat()
                    if crawler.last_run_at
                    else None,
                    "last_started_at": crawler.last_started_at.isoformat()
                    if crawler.last_started_at
                    else None,
                    "last_completed_at": crawler.last_completed_at.isoformat()
                    if crawler.last_completed_at
                    else None,
                    "last_run_duration_minutes": crawler.last_run_duration_minutes,
                    "schedule_cron": crawler.schedule_cron,
                    "schedule_display": get_schedule_display_text(
                        crawler.schedule_cron
                    ),
                    "schedule_human": cron_to_human(crawler.schedule_cron or ""),
                    "next_run_at": crawler.next_run_at.isoformat()
                    if crawler.next_run_at
                    else None,
                    "cancel_requested": crawler.cancel_requested or False,
                    "last_error": crawler.last_error,
                    "consecutive_errors": crawler.consecutive_errors or 0,
                    "latest_run": {
                        "id": latest_run.id,
                        "status": latest_run.status,
                        "run_type": latest_run.run_type,
                        "started_at": latest_run.started_at.isoformat(),
                        "uniqueness_percentage": latest_run.uniqueness_percentage or 0,
                        "items_scraped": latest_run.items_scraped or 0,
                    }
                    if latest_run
                    else None,
                }
            )

        return jsonify({"crawlers": crawler_list, "total": len(crawler_list)}), 200

    except Exception as e:
        current_app.logger.error(f"Error listing crawlers: {e}")
        return jsonify({"error": "Failed to load crawlers"}), 500


@admin_bp.route("/crawlers/<crawler_id>/start", methods=["POST", "OPTIONS"])
@jwt_required(optional=True)
def start_crawler(crawler_id):
    """Start a crawler run instantly"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    if crawler.is_running:
        return jsonify({"error": "Crawler is already running"}), 409

    if not crawler.is_active:
        return jsonify({"error": "Crawler is disabled"}), 403

    try:
        # Enqueue job to Redis/RQ instead of using threads
        from redis import Redis
        from rq import Queue
        from jobs.tasks import run_crawler_job

        # Connect to Redis
        redis_conn = Redis.from_url(current_app.config["REDIS_URL"])

        # Check if another crawler is already queued or running
        # This is an additional safety check beyond the database lock in tasks.py
        queue = Queue("crawlers", connection=redis_conn)

        # Check if any crawler job is currently running or queued
        running_jobs = queue.started_job_registry.get_job_ids()
        queued_jobs = queue.get_job_ids()

        if running_jobs or queued_jobs:
            return jsonify(
                {
                    "error": "Another crawler is already running or queued. Only one crawler can run at a time."
                }
            ), 409

        # Enqueue the crawler job
        job = queue.enqueue(
            run_crawler_job,
            crawler_id,
            admin_id,
            "manual",
            job_timeout=604800,  # 7 days max for job execution (for large catalogs)
        )

        # NOTE: Don't set is_running=True here - let the job set it
        # This prevents race condition where job checks and finds it already True
        crawler.started_by = admin_id
        crawler.last_started_at = datetime.utcnow()
        db.session.commit()

        current_app.logger.info(
            f"🚀 Crawler job enqueued: {crawler.name} (Job ID: {job.id})"
        )

        return jsonify(
            {
                "message": "Crawler job enqueued successfully",
                "crawler_id": crawler_id,
                "job_id": job.id,
                "run_type": "manual",
                "status": "queued",
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error starting crawler: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"Failed to start crawler: {str(e)}"}), 500


@admin_bp.route("/crawlers/<crawler_id>/stop", methods=["POST", "OPTIONS"])
@jwt_required(optional=True)
def stop_crawler(crawler_id):
    """Stop/cancel a running crawler"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    if not crawler.is_running:
        return jsonify({"error": "Crawler is not running"}), 409

    try:
        # Try to cancel via scraper manager if it exists
        scraper_manager = get_scraper_manager(crawler_id, admin_id)
        if scraper_manager:
            scraper_manager.cancel_run(reason="Manual stop by admin")

        # Update database status
        crawler.is_running = False
        crawler.cancel_requested = True
        crawler.cancelled_by = admin_id
        crawler.cancelled_at = datetime.utcnow()

        if crawler.last_started_at:
            duration = (
                datetime.utcnow() - crawler.last_started_at
            ).total_seconds() / 60
            crawler.last_run_duration_minutes = duration

        crawler.last_completed_at = datetime.utcnow()
        db.session.commit()

        current_app.logger.info(f"🛑 Crawler stopped: {crawler.name}")

        return jsonify(
            {
                "message": "Crawler stopped",
                "crawler_id": crawler_id,
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error stopping crawler: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Failed to stop crawler"}), 500


@admin_bp.route("/schedule/presets", methods=["GET", "OPTIONS"])
@jwt_required(optional=True)
def get_schedule_presets():
    """Get available schedule presets for user-friendly scheduling"""
    if request.method == "OPTIONS":
        return "", 204

    return jsonify({"presets": SCHEDULE_PRESETS}), 200


@admin_bp.route("/crawlers/<crawler_id>/schedule", methods=["PUT", "OPTIONS"])
@jwt_required(optional=True)
def update_crawler_schedule(crawler_id):
    """Update crawler schedule using human-readable format"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    crawler = Crawler.query.get(crawler_id)
    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    try:
        data = request.get_json()

        # Convert human-readable schedule to cron
        interval_type = data.get("interval_type", "quarterly")
        interval_value = data.get("interval_value", 3)
        time_hour = data.get("time_hour", 2)
        time_minute = data.get("time_minute", 0)
        day_of_month = data.get("day_of_month", 1)
        day_of_week = data.get("day_of_week")

        cron_expression = human_to_cron(
            interval_type=interval_type,
            interval_value=interval_value,
            time_hour=time_hour,
            time_minute=time_minute,
            day_of_month=day_of_month,
            day_of_week=day_of_week,
        )

        crawler.schedule_cron = cron_expression
        crawler.scheduled_by = admin_id
        db.session.commit()

        current_app.logger.info(
            f"Schedule updated for {crawler.name}: {get_schedule_display_text(cron_expression)}"
        )

        return jsonify(
            {
                "message": "Schedule updated successfully",
                "schedule_cron": cron_expression,
                "schedule_display": get_schedule_display_text(cron_expression),
                "schedule_human": cron_to_human(cron_expression),
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error updating schedule: {e}")
        db.session.rollback()
        return jsonify({"error": f"Failed to update schedule: {str(e)}"}), 500


@admin_bp.route("/crawlers/<crawler_id>/config", methods=["PUT", "OPTIONS"])
@jwt_required(optional=True)
def update_crawler_config(crawler_id):
    """Update crawler configuration (active status, uniqueness threshold, schedule)"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    crawler = Crawler.query.get(crawler_id)
    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    try:
        data = request.get_json()

        # Update fields if provided
        if "is_active" in data:
            crawler.is_active = data["is_active"]

        if "min_uniqueness_threshold" in data:
            threshold = float(data["min_uniqueness_threshold"])
            if 0 <= threshold <= 100:
                crawler.min_uniqueness_threshold = threshold
            else:
                return jsonify({"error": "Threshold must be between 0 and 100"}), 400

        if "schedule_cron" in data:
            crawler.schedule_cron = data["schedule_cron"]
            crawler.scheduled_by = admin_id

        db.session.commit()

        current_app.logger.info(f"Config updated for crawler: {crawler.name}")

        return jsonify(
            {
                "message": "Configuration updated successfully",
                "crawler": {
                    "id": crawler.id,
                    "name": crawler.name,
                    "is_active": crawler.is_active,
                    "min_uniqueness_threshold": crawler.min_uniqueness_threshold,
                    "schedule_cron": crawler.schedule_cron,
                    "schedule_display": get_schedule_display_text(
                        crawler.schedule_cron
                    ),
                },
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error updating crawler config: {e}")
        db.session.rollback()
        return jsonify({"error": f"Failed to update configuration: {str(e)}"}), 500


@admin_bp.route("/settings", methods=["GET"])
@jwt_required()
def get_settings():
    """Get system settings (alias for system-config)"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        config = SystemConfig.query.first()

        if not config:
            config = SystemConfig()
            db.session.add(config)
            db.session.commit()

        return jsonify(
            {
                "site_name": config.site_name,
                "site_description": config.site_description,
                "similarity_threshold": config.similarity_threshold,
                "batch_size": config.batch_size,
                "max_image_size_mb": config.max_image_size_mb,
                "session_timeout_minutes": config.session_timeout_minutes,
                "max_login_attempts": config.max_login_attempts,
                "login_lockout_minutes": config.login_lockout_minutes,
                "password_min_length": config.password_min_length,
                "smtp_server": config.smtp_server,
                "smtp_port": config.smtp_port,
                "smtp_username": config.smtp_username,
                "smtp_sender_email": config.smtp_sender_email,
                "smtp_security": config.smtp_security,
                "db_pool_size": config.db_pool_size,
                "db_pool_recycle": config.db_pool_recycle,
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error getting settings: {e}")
        return jsonify({"error": "Failed to load settings"}), 500


@admin_bp.route("/settings", methods=["PUT"])
@jwt_required()
def update_settings():
    """Update system settings (alias for system-config)"""
    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        data = request.get_json()
        config = SystemConfig.query.first()

        if not config:
            config = SystemConfig()
            db.session.add(config)

        # Update config with fields that actually exist in the model
        if "site_name" in data:
            config.site_name = data["site_name"]
        if "site_description" in data:
            config.site_description = data["site_description"]
        if "similarity_threshold" in data:
            config.similarity_threshold = data["similarity_threshold"]
        if "batch_size" in data:
            config.batch_size = data["batch_size"]
        if "max_image_size_mb" in data:
            config.max_image_size_mb = data["max_image_size_mb"]
        if "session_timeout_minutes" in data:
            config.session_timeout_minutes = data["session_timeout_minutes"]
        if "max_login_attempts" in data:
            config.max_login_attempts = data["max_login_attempts"]
        if "login_lockout_minutes" in data:
            config.login_lockout_minutes = data["login_lockout_minutes"]
        if "password_min_length" in data:
            config.password_min_length = data["password_min_length"]
        if "smtp_server" in data:
            config.smtp_server = data["smtp_server"]
        if "smtp_port" in data:
            config.smtp_port = data["smtp_port"]
        if "smtp_username" in data:
            config.smtp_username = data["smtp_username"]
        if "smtp_password" in data:
            config.smtp_password = data["smtp_password"]
        if "smtp_sender_email" in data:
            config.smtp_sender_email = data["smtp_sender_email"]
        if "smtp_security" in data:
            config.smtp_security = data["smtp_security"]
        if "db_pool_size" in data:
            config.db_pool_size = data["db_pool_size"]
        if "db_pool_recycle" in data:
            config.db_pool_recycle = data["db_pool_recycle"]

        config.updated_by = admin_id

        db.session.commit()

        return jsonify({"message": "Settings updated successfully"}), 200

    except Exception as e:
        current_app.logger.error(f"Error updating settings: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to update settings"}), 500


@admin_bp.route("/change-password", methods=["POST", "OPTIONS"])
@jwt_required()
def change_admin_password():
    """Change admin password"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        data = request.get_json()
        current_password = data.get("current_password")
        new_password = data.get("new_password")

        if not current_password or not new_password:
            return jsonify(
                {"error": "Current password and new password are required"}
            ), 400

        # Verify current password
        if not check_password_hash(admin.password_hash, current_password):
            return jsonify({"error": "Current password is incorrect"}), 401

        # Validate new password length
        config = SystemConfig.query.first()
        min_length = config.password_min_length if config else 9

        if len(new_password) < min_length:
            return jsonify(
                {"error": f"Password must be at least {min_length} characters"}
            ), 400

        # Update password
        admin.password_hash = generate_password_hash(new_password)
        admin.updated_at = datetime.utcnow()
        db.session.commit()

        current_app.logger.info(f"Admin password changed: {admin.username}")

        return jsonify({"message": "Password changed successfully"}), 200

    except Exception as e:
        current_app.logger.error(f"Error changing password: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to change password"}), 500


@admin_bp.route("/database/backup/status", methods=["GET", "OPTIONS"])
@jwt_required()
def get_backup_status():
    """Get backup status (placeholder)"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    # Placeholder implementation
    return jsonify(
        {
            "last_backup": None,
            "backup_count": 0,
            "total_size_mb": 0,
            "status": "No backups available",
        }
    ), 200


@admin_bp.route("/database/backup/create", methods=["POST", "OPTIONS"])
@jwt_required()
def create_backup():
    """Create database backup"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        import subprocess
        from datetime import datetime
        import os

        # Get database connection info from environment or config
        db_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI")

        if not db_uri:
            return jsonify({"error": "Database URI not configured"}), 500

        # Parse database URI (postgresql://user:password@host:port/database)
        from urllib.parse import urlparse

        parsed = urlparse(db_uri)

        # Create backup directory if it doesn't exist
        backup_dir = os.path.join(os.getcwd(), "backups")
        os.makedirs(backup_dir, exist_ok=True)

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"backup_{timestamp}.sql")

        # Create pg_dump command
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password

        cmd = [
            "pg_dump",
            "-h",
            parsed.hostname or "localhost",
            "-p",
            str(parsed.port or 5432),
            "-U",
            parsed.username or "postgres",
            "-d",
            parsed.path.lstrip("/"),
            "-f",
            backup_file,
            "--format=plain",
            "--no-owner",
            "--no-acl",
        ]

        # Execute backup
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if result.returncode == 0:
            # Get file size
            file_size = os.path.getsize(backup_file)
            size_mb = file_size / (1024 * 1024)

            current_app.logger.info(
                f"Database backup created: {backup_file} ({size_mb:.2f} MB)"
            )

            return jsonify(
                {
                    "message": "Backup created successfully",
                    "filename": os.path.basename(backup_file),
                    "size_mb": round(size_mb, 2),
                    "timestamp": timestamp,
                }
            ), 200
        else:
            error_msg = result.stderr or "Unknown error"
            current_app.logger.error(f"Backup failed: {error_msg}")
            return jsonify({"error": f"Backup failed: {error_msg}"}), 500

    except Exception as e:
        current_app.logger.error(f"Error creating backup: {e}")
        return jsonify({"error": f"Failed to create backup: {str(e)}"}), 500


@admin_bp.route("/database/init", methods=["POST", "OPTIONS"])
@jwt_required()
def init_database():
    """Initialize database (placeholder)"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    return jsonify({"message": "Database initialization not implemented"}), 501


@admin_bp.route("/database/clear", methods=["POST", "OPTIONS"])
@jwt_required()
def clear_database():
    """Clear database (placeholder - dangerous operation)"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    return jsonify(
        {"error": "Database clear operation not implemented for safety"}
    ), 501


# ========================================================================
# PRODUCTION-GRADE MONITORING ENDPOINTS
# ========================================================================


@admin_bp.route("/workers/health", methods=["GET", "OPTIONS"])
@jwt_required()
def get_workers_health():
    """
    Get worker health status and metrics
    Production-grade monitoring endpoint
    """
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        health = get_worker_health()
        return jsonify(health), 200
    except Exception as e:
        current_app.logger.error(f"Error getting worker health: {str(e)}")
        return jsonify({"healthy": False, "error": str(e)}), 500


@admin_bp.route("/crawlers/<crawler_id>/job/status", methods=["GET", "OPTIONS"])
@jwt_required()
def get_crawler_job_status_endpoint(crawler_id):
    """
    Get detailed status of crawler job
    Includes: progress, heartbeat, errors, retry info
    """
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        status = get_crawler_job_status(crawler_id)

        if not status:
            return jsonify(
                {
                    "crawler_id": crawler_id,
                    "status": "idle",
                    "message": "No job running or completed recently",
                }
            ), 200

        return jsonify(status), 200
    except Exception as e:
        current_app.logger.error(f"Error getting crawler job status: {str(e)}")
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/system/monitoring", methods=["GET", "OPTIONS"])
@jwt_required()
def get_system_monitoring():
    """
    Comprehensive system monitoring endpoint
    Returns: worker health, queue stats, crawler statuses, system metrics
    """
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        # Worker health
        worker_health = get_worker_health()

        # Active crawlers
        running_crawlers = Crawler.query.filter_by(is_running=True).all()
        crawler_statuses = []

        for crawler in running_crawlers:
            job_status = get_crawler_job_status(str(crawler.id))
            crawler_statuses.append(
                {
                    "crawler_id": str(crawler.id),
                    "crawler_name": crawler.name,
                    "status": job_status if job_status else {"status": "unknown"},
                }
            )

        # Database stats
        from core.models import SoleImage, UploadedImage, MatchResult

        db_stats = {
            "sole_images": SoleImage.query.count(),
            "uploaded_images": UploadedImage.query.count(),
            "match_results": MatchResult.query.count(),
            "total_crawlers": Crawler.query.count(),
            "active_crawlers": Crawler.query.filter_by(is_active=True).count(),
        }

        return jsonify(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "worker_health": worker_health,
                "running_crawlers": crawler_statuses,
                "database_stats": db_stats,
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error getting system monitoring: {str(e)}")
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/jobs/dead-letter-queue", methods=["GET", "OPTIONS"])
@jwt_required()
def get_dead_letter_queue():
    """
    Get jobs from dead letter queue (permanently failed jobs)
    """
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    admin = verify_admin_session(admin_id)

    if not admin:
        return jsonify({"error": "Session expired"}), 401

    try:
        from redis import Redis

        redis_conn = Redis.from_url(
            current_app.config.get("REDIS_URL", "redis://localhost:6379/0")
        )

        # Get dead letter queue entries
        entries = redis_conn.lrange("crawler:dead_letter_queue", 0, -1)

        dead_jobs = []
        for entry in entries:
            entry_str = entry.decode() if isinstance(entry, bytes) else entry
            parts = entry_str.split(":")
            if len(parts) >= 3:
                dead_jobs.append(
                    {"crawler_id": parts[0], "job_id": parts[1], "failed_at": parts[2]}
                )

        return jsonify({"total": len(dead_jobs), "jobs": dead_jobs}), 200

    except Exception as e:
        current_app.logger.error(f"Error getting dead letter queue: {str(e)}")
        return jsonify({"error": str(e)}), 500
