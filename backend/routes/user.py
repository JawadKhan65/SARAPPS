from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from flask_mail import Message
import uuid
import os
from datetime import datetime, timedelta
from extensions import db, mail
from models import User, UploadedImage, MatchResult, SoleImage
from services.image_processor import ImageProcessor

user_bp = Blueprint("user", __name__)


def allowed_file(filename):
    """Check if file extension is allowed"""
    allowed_extensions = current_app.config.get(
        "ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "gif", "webp"}
    )
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


@user_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    """Get user profile"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    # Get profile image from group if user is in a group
    profile_image_url = None
    if user.group_id:
        from models import UserGroup

        group = UserGroup.query.get(user.group_id)
        if group and group.profile_image_data:
            profile_image_url = (
                f"http://localhost:5000/api/admin/groups/{group.id}/image"
            )

    return jsonify(
        {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "dark_mode": user.dark_mode,
            "language": user.language,
            "group_id": str(user.group_id) if user.group_id else None,
            "profile_image_url": profile_image_url,
            "storage_used_mb": user.storage_used_mb,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
    ), 200


@user_bp.route("/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    """Update user profile"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()

    if "dark_mode" in data:
        user.dark_mode = bool(data["dark_mode"])

    if "language" in data:
        user.language = data["language"][:10]

    db.session.commit()

    return jsonify({"message": "Profile updated successfully"}), 200


@user_bp.route("/upload-image", methods=["POST"])
@jwt_required()
def upload_image():
    """Upload image for identification"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    # Check if image in request
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files["image"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    # Check file size
    max_size = current_app.config.get("MAX_CONTENT_LENGTH", 50 * 1024 * 1024)
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Seek back to start

    if file_size > max_size:
        return jsonify(
            {"error": f"File too large (max {max_size / (1024 * 1024):.0f}MB)"}
        ), 400

    try:
        # Create upload directory structure
        user_upload_dir = os.path.join(
            current_app.config.get("UPLOAD_FOLDER", "uploads"), "user_uploads", user_id
        )
        os.makedirs(user_upload_dir, exist_ok=True)

        # Save original image
        filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        filepath = os.path.join(user_upload_dir, filename)
        file.save(filepath)

        # Process image
        processor = ImageProcessor()

        processed_path = os.path.join(user_upload_dir, f"processed_{uuid.uuid4()}.png")
        process_result = processor.process_image(
            filepath, save_processed_path=processed_path
        )

        # Calculate image hash
        import hashlib

        image_bytes = process_result["image_array"].tobytes()
        image_hash = hashlib.sha256(image_bytes).hexdigest()

        # Create uploaded image record
        uploaded_image = UploadedImage(
            id=str(uuid.uuid4()),
            user_id=user_id,
            file_path=filepath,
            processed_image_path=processed_path,
            image_hash=image_hash,
            feature_vector=processor.serialize_features(process_result["features"]),
            quality_score=process_result["quality_score"],
            uploaded_at=datetime.utcnow(),
        )

        # Update user storage
        user.storage_used_mb += file_size / (1024 * 1024)

        db.session.add(uploaded_image)
        db.session.commit()

        current_app.logger.info(
            f"Image uploaded by user {user_id}: {uploaded_image.id}"
        )

        return jsonify(
            {
                "message": "Image uploaded successfully",
                "image_id": uploaded_image.id,
                "quality_score": process_result["quality_score"],
            }
        ), 201

    except Exception as e:
        current_app.logger.error(f"Error uploading image: {str(e)}")
        return jsonify({"error": "Failed to process image"}), 500


@user_bp.route("/match-image/<image_id>", methods=["POST"])
@jwt_required()
def match_image(image_id):
    """
    Find matching sole images for uploaded image
    Returns top 4 matches with confidence scores
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    # Get uploaded image
    uploaded_image = UploadedImage.query.filter_by(id=image_id, user_id=user_id).first()

    if not uploaded_image:
        return jsonify({"error": "Image not found"}), 404

    try:
        processor = ImageProcessor()

        # Deserialize uploaded image features
        uploaded_features = processor.deserialize_features(
            uploaded_image.feature_vector
        )

        # Get all sole images for comparison
        sole_images = SoleImage.query.all()

        matches = []
        for sole_image in sole_images:
            sole_features = processor.deserialize_features(sole_image.feature_vector)
            similarity = processor.calculate_similarity(
                uploaded_features, sole_features
            )

            matches.append(
                {
                    "sole_image_id": sole_image.id,
                    "brand": sole_image.brand,
                    "product_type": sole_image.product_type,
                    "product_name": sole_image.product_name,
                    "source_url": sole_image.source_url,
                    "confidence": float(similarity),
                    "quality_score": sole_image.quality_score,
                    "crawled_at": sole_image.crawled_at.isoformat()
                    if sole_image.crawled_at
                    else None,
                }
            )

        # Sort by confidence and get top 4
        matches.sort(key=lambda x: x["confidence"], reverse=True)
        top_matches = matches[:4]

        # Ensure we have 4 matches (pad with nulls if needed)
        while len(top_matches) < 4:
            top_matches.append(None)

        # Create match result record
        match_result = MatchResult(
            id=str(uuid.uuid4()),
            user_id=user_id,
            uploaded_image_id=image_id,
            primary_match_id=top_matches[0]["sole_image_id"]
            if top_matches[0]
            else None,
            primary_confidence=top_matches[0]["confidence"] if top_matches[0] else 0,
            secondary_match_id=top_matches[1]["sole_image_id"]
            if top_matches[1]
            else None,
            secondary_confidence=top_matches[1]["confidence"] if top_matches[1] else 0,
            tertiary_match_id=top_matches[2]["sole_image_id"]
            if top_matches[2]
            else None,
            tertiary_confidence=top_matches[2]["confidence"] if top_matches[2] else 0,
            quaternary_match_id=top_matches[3]["sole_image_id"]
            if top_matches[3]
            else None,
            quaternary_confidence=top_matches[3]["confidence"] if top_matches[3] else 0,
            matching_time_ms=0,
            matched_at=datetime.utcnow(),
        )

        db.session.add(match_result)
        db.session.commit()

        current_app.logger.info(
            f"Image matched for user {user_id}: "
            f"primary={top_matches[0]['brand'] if top_matches[0] else 'None'} "
            f"({top_matches[0]['confidence']:.2f})"
        )

        return jsonify(
            {
                "match_id": match_result.id,
                "uploaded_image_id": image_id,
                "matches": top_matches,
                "timestamp": datetime.utcnow().isoformat(),
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error matching image: {str(e)}")
        return jsonify({"error": "Failed to match image"}), 500


@user_bp.route("/match-result/<match_id>", methods=["GET"])
@jwt_required()
def get_match_result(match_id):
    """Get previous match result"""
    user_id = get_jwt_identity()

    match_result = MatchResult.query.filter_by(id=match_id, user_id=user_id).first()

    if not match_result:
        return jsonify({"error": "Match not found"}), 404

    # Build response with match details
    matches = []

    for i, (match_id_attr, confidence_attr) in enumerate(
        [
            ("primary_match_id", "primary_confidence"),
            ("secondary_match_id", "secondary_confidence"),
            ("tertiary_match_id", "tertiary_confidence"),
            ("quaternary_match_id", "quaternary_confidence"),
        ]
    ):
        sole_image_id = getattr(match_result, match_id_attr)
        confidence = getattr(match_result, confidence_attr)

        if sole_image_id:
            sole_image = SoleImage.query.get(sole_image_id)
            if sole_image:
                matches.append(
                    {
                        "rank": i + 1,
                        "sole_image_id": sole_image.id,
                        "brand": sole_image.brand,
                        "product_type": sole_image.product_type,
                        "product_name": sole_image.product_name,
                        "source_url": sole_image.source_url,
                        "confidence": float(confidence),
                        "quality_score": sole_image.quality_score,
                    }
                )
        else:
            matches.append(None)

    return jsonify(
        {
            "match_id": match_result.id,
            "uploaded_image_id": match_result.uploaded_image_id,
            "matches": matches,
            "user_confirmed_match": match_result.user_confirmed_match,
            "custom_brand": match_result.custom_brand,
            "custom_type": match_result.custom_type,
            "matched_at": match_result.matched_at.isoformat()
            if match_result.matched_at
            else None,
            "confirmed_at": match_result.confirmed_at.isoformat()
            if match_result.confirmed_at
            else None,
        }
    ), 200


@user_bp.route("/match-result/<match_id>/confirm", methods=["POST"])
@jwt_required()
def confirm_match(match_id):
    """Confirm a match result"""
    user_id = get_jwt_identity()

    match_result = MatchResult.query.filter_by(id=match_id, user_id=user_id).first()

    if not match_result:
        return jsonify({"error": "Match not found"}), 404

    data = request.get_json()

    # User can confirm one of the matches or provide custom info
    if "confirmed_rank" in data:
        rank = data["confirmed_rank"]  # 1-4
        if rank < 1 or rank > 4:
            return jsonify({"error": "Invalid rank"}), 400

        match_id_attrs = [
            "primary_match_id",
            "secondary_match_id",
            "tertiary_match_id",
            "quaternary_match_id",
        ]
        confirmed_sole_id = getattr(match_result, match_id_attrs[rank - 1])

        if not confirmed_sole_id:
            return jsonify({"error": "No match at this rank"}), 400

        match_result.user_confirmed_match = confirmed_sole_id

    # Optional custom brand/type if user provided different info
    if "custom_brand" in data:
        match_result.custom_brand = data["custom_brand"]

    if "custom_type" in data:
        match_result.custom_type = data["custom_type"]

    match_result.confirmed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Match confirmed"}), 200


@user_bp.route("/uploads", methods=["GET"])
@jwt_required()
def list_uploads():
    """List user's uploaded images with pagination"""
    user_id = get_jwt_identity()

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = (
        UploadedImage.query.filter_by(user_id=user_id)
        .order_by(UploadedImage.uploaded_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    uploads = []
    for image in pagination.items:
        uploads.append(
            {
                "id": image.id,
                "uploaded_at": image.uploaded_at.isoformat()
                if image.uploaded_at
                else None,
                "quality_score": image.quality_score,
                "last_matched_at": image.last_matched_at.isoformat()
                if image.last_matched_at
                else None,
                "matches_count": MatchResult.query.filter_by(
                    uploaded_image_id=image.id
                ).count(),
            }
        )

    return jsonify(
        {
            "uploads": uploads,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
            "per_page": per_page,
        }
    ), 200


@user_bp.route("/delete-image/<image_id>", methods=["DELETE"])
@jwt_required()
def delete_image(image_id):
    """Delete uploaded image"""
    user_id = get_jwt_identity()

    uploaded_image = UploadedImage.query.filter_by(id=image_id, user_id=user_id).first()

    if not uploaded_image:
        return jsonify({"error": "Image not found"}), 404

    try:
        # Delete files
        if os.path.exists(uploaded_image.file_path):
            os.remove(uploaded_image.file_path)

        if uploaded_image.processed_image_path and os.path.exists(
            uploaded_image.processed_image_path
        ):
            os.remove(uploaded_image.processed_image_path)

        # Delete related match results
        MatchResult.query.filter_by(uploaded_image_id=image_id).delete()

        # Delete the uploaded image record
        db.session.delete(uploaded_image)
        db.session.commit()

        current_app.logger.info(f"Image deleted: {image_id} by user {user_id}")

        return jsonify({"message": "Image deleted successfully"}), 200

    except Exception as e:
        current_app.logger.error(f"Error deleting image: {str(e)}")
        return jsonify({"error": "Failed to delete image"}), 500


@user_bp.route("/delete-account", methods=["POST"])
@jwt_required()
def delete_account():
    """Delete user account (requires MFA confirmation)"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()

    if not data.get("password"):
        return jsonify({"error": "Password required to delete account"}), 400

    # Verify password
    if not check_password_hash(user.password_hash, data["password"]):
        return jsonify({"error": "Invalid password"}), 401

    try:
        # Send confirmation email
        confirmation_token = str(uuid.uuid4())
        user.delete_token = confirmation_token
        user.delete_token_expiry = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()

        confirmation_url = (
            f"{request.host_url}confirm-delete?token={confirmation_token}"
        )
        msg = Message(
            subject="STIP - Delete Account Confirmation",
            recipients=[user.email],
            body=f"Click the link to confirm account deletion: {confirmation_url}",
        )
        mail.send(msg)

        current_app.logger.info(f"Delete account confirmation sent to: {user.email}")

        return jsonify(
            {"message": "Confirmation email sent", "token": confirmation_token}
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error processing delete account: {str(e)}")
        return jsonify({"error": "Failed to process deletion"}), 500


@user_bp.route("/confirm-delete", methods=["POST"])
def confirm_delete_account():
    """Confirm account deletion"""
    data = request.get_json()

    if not data.get("token"):
        return jsonify({"error": "Token required"}), 400

    user = User.query.filter_by(delete_token=data["token"]).first()

    if (
        not user
        or not user.delete_token_expiry
        or datetime.utcnow() > user.delete_token_expiry
    ):
        return jsonify({"error": "Invalid or expired token"}), 401

    try:
        # Delete user's images and related data
        uploaded_images = UploadedImage.query.filter_by(user_id=user.id).all()

        for img in uploaded_images:
            if os.path.exists(img.file_path):
                os.remove(img.file_path)
            if img.processed_image_path and os.path.exists(img.processed_image_path):
                os.remove(img.processed_image_path)

        # Delete match results
        MatchResult.query.filter_by(user_id=user.id).delete()

        # Delete uploaded images
        UploadedImage.query.filter_by(user_id=user.id).delete()

        # Mark user as deleted
        user.is_deleted = True
        user.is_active = False

        db.session.commit()

        current_app.logger.info(f"User account deleted: {user.email}")

        return jsonify({"message": "Account deleted successfully"}), 200

    except Exception as e:
        current_app.logger.error(f"Error deleting account: {str(e)}")
        return jsonify({"error": "Failed to delete account"}), 500
