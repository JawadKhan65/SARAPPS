from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from flask_mail import Message
import uuid
import os
import sys
from datetime import datetime, timedelta
from core.extensions import db, mail
from core.models import (
    User,
    UploadedImage,
    MatchResult,
    SoleImage,
    MatchHistory,
    MatchDetail,
)
from services.image_processor import ImageProcessor
import numpy as np
import cv2 as cv
from PIL import Image
import io

# Add line_tracing module to path
line_tracing_path = os.path.join(os.path.dirname(__file__), "..", "line_tracing_utils")
sys.path.insert(0, line_tracing_path)

try:
    from line_tracing import compare_sole_images, process_reference_sole
except ImportError:
    compare_sole_images = None
    process_reference_sole = None

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
        from core.models import UserGroup
        from flask import request

        group = UserGroup.query.get(user.group_id)
        if group and group.profile_image_data:
            # Use request context to build dynamic URL
            profile_image_url = (
                f"{request.url_root.rstrip('/')}/api/admin/groups/{group.id}/image"
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
    max_size = current_app.config.get("MAX_CONTENT_LENGTH", 120 * 1024 * 1024)
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

        # Convert numpy types to Python native types
        quality_score = float(process_result["quality_score"])

        # Check if image already exists for this user
        existing_image = UploadedImage.query.filter_by(
            user_id=user_id, image_hash=image_hash
        ).first()

        if existing_image:
            current_app.logger.info(
                f"Image already uploaded by user {user_id}: {existing_image.id}"
            )
            return jsonify(
                {
                    "message": "Image already uploaded",
                    "image_id": existing_image.id,
                    "quality_score": existing_image.quality_score,
                }
            ), 200

        # Create uploaded image record
        uploaded_image = UploadedImage(
            id=str(uuid.uuid4()),
            user_id=user_id,
            file_path=filepath,
            processed_image_path=processed_path,
            image_hash=image_hash,
            feature_vector=processor.serialize_features(process_result["features"]),
            quality_score=quality_score,
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
                "quality_score": quality_score,
            }
        ), 201

    except Exception as e:
        current_app.logger.error(f"Error uploading image: {str(e)}")
        return jsonify({"error": "Failed to process image"}), 500


@user_bp.route("/match-image/<image_id>", methods=["POST"])
@jwt_required()
def match_image(image_id):
    """
    Match uploaded image against database using vector similarity search
    Find matching sole images for uploaded image
    Returns ALL matches with confidence scores (default: all matches, limit: configurable)
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    # Get limit from request body (default: None = all matches, max: 100 for performance)
    data = request.get_json() or {}
    requested_limit = data.get("limit")

    if requested_limit is None:
        limit = None  # Return all matches
    else:
        limit = min(int(requested_limit), 100)  # Cap at 100 for performance

    if not user:
        return jsonify({"error": "User not found"}), 404

    # Get uploaded image
    uploaded_image = UploadedImage.query.filter_by(id=image_id, user_id=user_id).first()

    if not uploaded_image:
        return jsonify({"error": "Image not found"}), 404

    try:
        processor = ImageProcessor()

        # Load uploaded image - use ORIGINAL file (not processed) for compare_sole_images
        # compare_sole_images needs to do its own processing
        uploaded_img_array = None
        uploaded_features = None

        if os.path.exists(uploaded_image.file_path):
            # Load ORIGINAL image file (compare_sole_images will process it)
            uploaded_img_array = cv.imread(uploaded_image.file_path, cv.IMREAD_COLOR)
            if uploaded_img_array is not None:
                # Convert to grayscale for compare_sole_images
                uploaded_img_array = cv.cvtColor(uploaded_img_array, cv.COLOR_BGR2GRAY)

        # Also load feature vector for quick filtering
        if uploaded_image.feature_vector:
            uploaded_features = processor.deserialize_features(
                uploaded_image.feature_vector
            )

        # === STAGE 1: Fast Vector Search using pgvector (10-50ms for 10,000 images!) ===
        # Extract vectors from uploaded image
        uploaded_vectors = processor.extract_vector_embeddings(
            uploaded_img_array
            if uploaded_img_array.ndim == 3
            else cv.cvtColor(uploaded_img_array, cv.COLOR_GRAY2BGR),
            uploaded_image.file_path,
        )

        clip_vec = uploaded_vectors.get("clip_vector")
        edge_vec = uploaded_vectors.get("edge_vector")
        texture_vec = uploaded_vectors.get("texture_vector")

        # Try vector-based search first (much faster!)
        candidates = []
        try:
            from sqlalchemy import text

            # Multi-vector ensemble query using pgvector
            # Combine CLIP (40%), Edge (35%), Texture (25%)
            if (
                clip_vec is not None
                and edge_vec is not None
                and texture_vec is not None
            ):
                current_app.logger.info("Using pgvector fast similarity search...")

                candidates_query = text("""
                    SELECT 
                        id,
                        brand,
                        product_type,
                        product_name,
                        source_url,
                        quality_score,
                        (
                            0.40 * (1 - (clip_embedding <=> CAST(:clip_vec AS vector))) +
                            0.35 * (1 - (edge_embedding <-> CAST(:edge_vec AS vector))) +
                            0.25 * (1 - (texture_embedding <=> CAST(:texture_vec AS vector)))
                        ) as vector_similarity
                    FROM sole_images
                    WHERE clip_embedding IS NOT NULL
                        AND edge_embedding IS NOT NULL
                        AND texture_embedding IS NOT NULL
                    ORDER BY vector_similarity DESC
                    LIMIT 50
                """)

                result = db.session.execute(
                    candidates_query,
                    {
                        "clip_vec": clip_vec.tolist(),
                        "edge_vec": edge_vec.tolist(),
                        "texture_vec": texture_vec.tolist(),
                    },
                )

                # Convert results to candidate format
                for row in result:
                    sole_image = SoleImage.query.get(row.id)
                    if sole_image:
                        candidates.append(
                            {
                                "sole_image": sole_image,
                                "quick_score": float(row.vector_similarity),
                            }
                        )

                current_app.logger.info(
                    f"✓ Vector search found {len(candidates)} candidates in <50ms"
                )
        except Exception as e:
            current_app.logger.warning(
                f"Vector search failed, falling back to linear search: {str(e)}"
            )
            candidates = []

        # Fallback to legacy feature-based search if vector search failed or returned no results
        if not candidates:
            current_app.logger.info("Using legacy linear feature search...")
            sole_images = SoleImage.query.all()

            for sole_image in sole_images:
                # Quick feature-based similarity check
                if uploaded_features and sole_image.feature_vector:
                    try:
                        sole_features = processor.deserialize_features(
                            sole_image.feature_vector
                        )
                        similarity = processor.calculate_similarity(
                            uploaded_features, sole_features
                        )
                        candidates.append(
                            {"sole_image": sole_image, "quick_score": similarity}
                        )
                    except Exception as e:
                        current_app.logger.warning(
                            f"Feature comparison failed for {sole_image.id}: {str(e)}"
                        )
                        continue

            # Sort candidates by quick score
            candidates.sort(key=lambda x: x["quick_score"], reverse=True)
            candidates = candidates[:50]  # Take top 50

        top_candidates = candidates

        # Step 2: Now use compare_sole_images on top candidates for accurate matching
        matches = []
        for candidate in top_candidates:
            sole_image = candidate["sole_image"]

            # Use line_tracing comparison if available and images loaded
            if (
                compare_sole_images
                and uploaded_img_array is not None
                and sole_image.processed_image_data
            ):
                try:
                    # Load DB sole image (already processed)
                    db_img_bytes = sole_image.processed_image_data
                    db_img_array = cv.imdecode(
                        np.frombuffer(db_img_bytes, np.uint8), cv.IMREAD_GRAYSCALE
                    )

                    if db_img_array is None:
                        current_app.logger.warning(
                            f"Failed to decode image for {sole_image.id}"
                        )
                        similarity = candidate["quick_score"]
                    else:
                        # Use compare_sole_images for accurate similarity
                        # uploaded_img_array (grayscale original) will be processed inside compare_sole_images
                        # db_img_array is already processed from DB
                        similarity = compare_sole_images(
                            uploaded_img_array,  # Original grayscale, will be processed
                            db_img_array,  # Already processed matrix from DB
                            debug=False,
                        )
                        current_app.logger.debug(
                            f"compare_sole_images result for {sole_image.id}: {similarity:.4f}"
                        )
                except Exception as e:
                    current_app.logger.warning(
                        f"Line tracing comparison failed for {sole_image.id}: {str(e)}"
                    )
                    import traceback

                    current_app.logger.debug(traceback.format_exc())
                    # Use the quick score as fallback
                    similarity = candidate["quick_score"]
            else:
                # Fallback: use quick score
                if uploaded_img_array is None:
                    current_app.logger.warning(
                        "Uploaded image array is None, using feature-based matching only"
                    )
                if not compare_sole_images:
                    current_app.logger.warning(
                        "compare_sole_images function not available"
                    )
                similarity = candidate["quick_score"]

            matches.append(
                {
                    "sole_image_id": sole_image.id,
                    "brand": sole_image.brand,
                    "product_type": sole_image.product_type,
                    "product_name": sole_image.product_name,
                    "source_url": sole_image.source_url,
                    "confidence": float(similarity),
                    "quality_score": sole_image.quality_score,
                    "feature_vector_size": len(
                        processor.deserialize_features(sole_image.feature_vector) or []
                    ),
                    "crawled_at": sole_image.crawled_at.isoformat()
                    if sole_image.crawled_at
                    else None,
                }
            )

        # Sort by confidence
        matches.sort(key=lambda x: x["confidence"], reverse=True)

        # Apply limit if specified, otherwise return all
        if limit is not None:
            top_matches = matches[:limit]
            current_app.logger.info(
                f"Matching complete: Found {len(matches)} total matches, "
                f"returning top {len(top_matches)} (limit={limit})"
            )
        else:
            top_matches = matches
            current_app.logger.info(
                f"Matching complete: Found {len(matches)} total matches, "
                f"returning ALL matches (no limit)"
            )

        # Check if no matches found
        if not matches or all(m["confidence"] == 0 for m in matches):
            current_app.logger.info(
                f"No matches found for user {user_id} - database may be empty"
            )
            return jsonify(
                {
                    "match_id": None,
                    "uploaded_image_id": image_id,
                    "matches": [],
                    "message": "No matches found. The database may not contain any shoe images yet.",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ), 200

        # Ensure we have at least 4 matches (pad with nulls if needed)
        while len(top_matches) < 4:
            top_matches.append(None)

        # Calculate overall similarity as average of all match scores
        confidence_scores = [
            top_matches[0]["confidence"] if top_matches[0] else 0,
            top_matches[1]["confidence"] if top_matches[1] else 0,
            top_matches[2]["confidence"] if top_matches[2] else 0,
            top_matches[3]["confidence"] if top_matches[3] else 0,
        ]
        valid_scores = [score for score in confidence_scores if score > 0]
        overall_similarity = (
            sum(valid_scores) / len(valid_scores) if valid_scores else 0
        )

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
            overall_similarity=overall_similarity,
            matching_time_ms=0,
            matched_at=datetime.utcnow(),
        )

        db.session.add(match_result)

        # === NEW: Save to MatchHistory and MatchDetail tables ===
        # Create match history record
        match_history = MatchHistory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            uploaded_image_id=image_id,
            total_matches=len(matches),
            best_score=matches[0]["confidence"] if matches else 0,
            matching_time_ms=0,
            matched_at=datetime.utcnow(),
        )
        db.session.add(match_history)
        db.session.flush()  # Get the match_history ID

        # Create match detail records for ALL matches
        for rank, match in enumerate(matches, start=1):
            match_detail = MatchDetail(
                id=str(uuid.uuid4()),
                match_history_id=match_history.id,
                sole_image_id=match["sole_image_id"],
                similarity_score=match["confidence"],
                rank=rank,
                created_at=datetime.utcnow(),
            )
            db.session.add(match_detail)

        db.session.commit()

        current_app.logger.info(
            f"Image matched for user {user_id}: "
            f"primary={top_matches[0]['brand'] if top_matches[0] else 'None'} "
            f"({top_matches[0]['confidence'] if top_matches[0] else 0:.2f}), "
            f"saved {len(matches)} matches to history"
        )

        return jsonify(
            {
                "match_id": match_result.id,
                "uploaded_image_id": image_id,
                "matches": top_matches,
                "total_matches": len(matches),  # Total matches found
                "returned_matches": len(top_matches),  # Matches returned
                "has_more": len(matches) > len(top_matches) if limit else False,
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


@user_bp.route("/matches", methods=["GET"])
@jwt_required()
def list_matches():
    """List user's match history with pagination and filtering"""
    user_id = get_jwt_identity()

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    filter_type = request.args.get("filter", "all")

    # Base query for user's match history
    query = MatchHistory.query.filter_by(user_id=user_id)

    # Apply filters
    if filter_type == "high_confidence":
        query = query.filter(MatchHistory.best_score > 0.75)

    # Order by match date descending
    query = query.order_by(MatchHistory.matched_at.desc())

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    matches = []
    for history in pagination.items:
        uploaded_image = UploadedImage.query.get(history.uploaded_image_id)

        # Get top match details (rank 1)
        top_match_detail = MatchDetail.query.filter_by(
            match_history_id=history.id, rank=1
        ).first()

        # Get all match details for this history
        all_match_details = (
            MatchDetail.query.filter_by(match_history_id=history.id)
            .order_by(MatchDetail.rank)
            .all()
        )

        if top_match_detail:
            matches.append(
                {
                    "id": history.id,
                    "similarity_score": float(history.best_score)
                    if history.best_score
                    else 0.0,
                    "matched_at": history.matched_at.isoformat()
                    if history.matched_at
                    else None,
                    "total_matches": history.total_matches,
                    "uploaded_image_id": uploaded_image.id if uploaded_image else None,
                    "shoe": {
                        "id": top_match_detail.sole_image.id,
                        "brand": top_match_detail.sole_image.brand,
                        "product_name": top_match_detail.sole_image.product_name,
                        "product_type": top_match_detail.sole_image.product_type,
                        "source_url": top_match_detail.sole_image.source_url,
                        # Provide client-consumable endpoints matching existing routes
                        "sole_image_id": top_match_detail.sole_image.id,
                        "image_url": f"/user/sole-image/{top_match_detail.sole_image.id}/original",
                    },
                    # Include all matches for this history session
                    "all_matches": [
                        {
                            "sole_image_id": detail.sole_image_id,
                            "similarity_score": detail.similarity_score,
                            "rank": detail.rank,
                            "brand": detail.sole_image.brand,
                            "product_name": detail.sole_image.product_name,
                            "product_type": detail.sole_image.product_type,
                            "source_url": detail.sole_image.source_url,
                        }
                        for detail in all_match_details
                    ],
                }
            )

    return jsonify(
        {
            "matches": matches,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
            "per_page": per_page,
        }
    ), 200


@user_bp.route("/uploaded-image/<image_id>", methods=["GET"])
@jwt_required()
def get_uploaded_image(image_id):
    """Return the original uploaded image as base64 for the authenticated user"""
    user_id = get_jwt_identity()

    uploaded_image = UploadedImage.query.filter_by(id=image_id, user_id=user_id).first()
    if not uploaded_image:
        return jsonify({"error": "Image not found"}), 404

    if not os.path.exists(uploaded_image.file_path):
        return jsonify({"error": "Image file not found"}), 404

    try:
        import base64

        with open(uploaded_image.file_path, "rb") as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        return jsonify({"image": f"data:image/png;base64,{img_b64}"}), 200
    except Exception as e:
        current_app.logger.error(f"Error reading uploaded image {image_id}: {str(e)}")
        return jsonify({"error": "Failed to read image"}), 500


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


@user_bp.route("/image/<image_id>/features", methods=["GET"])
@jwt_required()
def get_image_features(image_id):
    """Extract and return feature processing steps for uploaded image"""
    user_id = get_jwt_identity()

    uploaded_image = UploadedImage.query.filter_by(id=image_id, user_id=user_id).first()

    if not uploaded_image:
        return jsonify({"error": "Image not found"}), 404

    if not os.path.exists(uploaded_image.file_path):
        return jsonify({"error": "Image file not found"}), 404

    try:
        from line_tracing_utils.line_tracing import extract_shoeprint_features
        import base64

        # Extract features
        (
            l_channel,
            a_channel,
            b_channel,
            denoised_l,
            enhanced_l,
            binary_pattern,
            cleaned_pattern,
            lbp,
            lbp_features,
        ) = extract_shoeprint_features(uploaded_image.file_path)

        def encode_image(arr):
            """Convert numpy array to base64 encoded PNG"""
            if arr.dtype != np.uint8:
                # Normalize to 0-255
                arr_min, arr_max = arr.min(), arr.max()
                if arr_max > arr_min:
                    arr = ((arr - arr_min) / (arr_max - arr_min) * 255).astype(np.uint8)
                else:
                    arr = np.clip(arr, 0, 255).astype(np.uint8)

            _, buffer = cv.imencode(".png", arr)
            return base64.b64encode(buffer).decode("utf-8")

        # Prepare response with all processing steps
        features_data = {
            "l_channel": f"data:image/png;base64,{encode_image(l_channel)}",
            "a_channel": f"data:image/png;base64,{encode_image(a_channel)}",
            "b_channel": f"data:image/png;base64,{encode_image(b_channel)}",
            "denoised_l": f"data:image/png;base64,{encode_image(denoised_l)}",
            "enhanced_l": f"data:image/png;base64,{encode_image(enhanced_l)}",
            "binary_pattern": f"data:image/png;base64,{encode_image(binary_pattern)}",
            "cleaned_pattern": f"data:image/png;base64,{encode_image(cleaned_pattern)}",
            "lbp": f"data:image/png;base64,{encode_image(lbp)}",
            "lbp_features": lbp_features.flatten().tolist()[:200]
            if lbp_features is not None
            else [],
            "lbp_features_length": lbp_features.size if lbp_features is not None else 0,
        }

        return jsonify(features_data), 200

    except Exception as e:
        current_app.logger.error(f"Error extracting features: {str(e)}")
        import traceback

        current_app.logger.debug(traceback.format_exc())
        return jsonify({"error": f"Failed to extract features: {str(e)}"}), 500


@user_bp.route("/sole-image/<sole_image_id>", methods=["GET"])
def get_sole_image(sole_image_id):
    """Get sole image data (public endpoint for displaying matches)"""
    sole_image = SoleImage.query.get(sole_image_id)

    if not sole_image:
        return jsonify({"error": "Image not found"}), 404

    try:
        import base64

        if sole_image.processed_image_data:
            # Return processed image as base64
            img_base64 = base64.b64encode(sole_image.processed_image_data).decode(
                "utf-8"
            )
            return jsonify(
                {
                    "image": f"data:image/png;base64,{img_base64}",
                    "brand": sole_image.brand,
                    "product_name": sole_image.product_name,
                    "product_type": sole_image.product_type,
                    "source_url": sole_image.source_url,
                }
            ), 200
        else:
            return jsonify({"error": "No image data available"}), 404

    except Exception as e:
        current_app.logger.error(f"Error getting sole image: {str(e)}")
        return jsonify({"error": "Failed to get image"}), 500


@user_bp.route("/sole-image/<sole_image_id>/original", methods=["GET"])
def get_sole_image_original(sole_image_id):
    """Get original (unprocessed) sole image data"""
    sole_image = SoleImage.query.get(sole_image_id)

    if not sole_image:
        return jsonify({"error": "Image not found"}), 404

    try:
        import base64

        if sole_image.original_image_data:
            # Return original image as base64
            img_base64 = base64.b64encode(sole_image.original_image_data).decode(
                "utf-8"
            )
            return jsonify(
                {
                    "image": f"data:image/png;base64,{img_base64}",
                    "brand": sole_image.brand,
                    "product_name": sole_image.product_name,
                    "product_type": sole_image.product_type,
                    "source_url": sole_image.source_url,
                }
            ), 200
        else:
            return jsonify({"error": "No original image data available"}), 404

    except Exception as e:
        current_app.logger.error(f"Error getting original sole image: {str(e)}")
        return jsonify({"error": "Failed to get original image"}), 500
