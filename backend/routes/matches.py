from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from extensions import db
from models import MatchResult, SoleImage, UploadedImage

matches_bp = Blueprint("matches", __name__)


@matches_bp.route("", methods=["GET"])
@jwt_required()
def list_matches():
    """List user's match history with pagination"""
    user_id = get_jwt_identity()

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = (
        MatchResult.query.filter_by(user_id=user_id)
        .order_by(MatchResult.matched_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    matches = []
    for match in pagination.items:
        primary_brand = None
        if match.primary_match_id:
            primary = SoleImage.query.get(match.primary_match_id)
            if primary:
                primary_brand = primary.brand

        matches.append(
            {
                "id": match.id,
                "uploaded_image_id": match.uploaded_image_id,
                "primary_match_brand": primary_brand,
                "primary_confidence": float(match.primary_confidence),
                "user_confirmed": match.user_confirmed_match is not None,
                "confirmed_at": match.confirmed_at.isoformat()
                if match.confirmed_at
                else None,
                "matched_at": match.matched_at.isoformat()
                if match.matched_at
                else None,
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


@matches_bp.route("/<match_id>", methods=["GET"])
@jwt_required()
def get_match(match_id):
    """Get detailed match result"""
    user_id = get_jwt_identity()

    match = MatchResult.query.filter_by(id=match_id, user_id=user_id).first()

    if not match:
        return jsonify({"error": "Match not found"}), 404

    # Build detailed match information
    matches = []

    for rank, (match_id_attr, confidence_attr) in enumerate(
        [
            ("primary_match_id", "primary_confidence"),
            ("secondary_match_id", "secondary_confidence"),
            ("tertiary_match_id", "tertiary_confidence"),
            ("quaternary_match_id", "quaternary_confidence"),
        ],
        1,
    ):
        sole_id = getattr(match, match_id_attr)
        confidence = getattr(match, confidence_attr)

        if sole_id:
            sole = SoleImage.query.get(sole_id)
            if sole:
                matches.append(
                    {
                        "rank": rank,
                        "brand": sole.brand,
                        "product_type": sole.product_type,
                        "product_name": sole.product_name,
                        "source_url": sole.source_url,
                        "confidence": float(confidence),
                        "quality_score": sole.quality_score,
                        "is_confirmed": match.user_confirmed_match == sole_id,
                    }
                )
        else:
            matches.append(None)

    return jsonify(
        {
            "id": match.id,
            "uploaded_image_id": match.uploaded_image_id,
            "matches": matches,
            "user_confirmed_match_id": match.user_confirmed_match,
            "custom_brand": match.custom_brand,
            "custom_type": match.custom_type,
            "matching_time_ms": match.matching_time_ms,
            "matched_at": match.matched_at.isoformat() if match.matched_at else None,
            "confirmed_at": match.confirmed_at.isoformat()
            if match.confirmed_at
            else None,
        }
    ), 200


@matches_bp.route("/<match_id>/confirm", methods=["POST"])
@jwt_required()
def confirm_match_result(match_id):
    """Confirm match result (user selects which match is correct)"""
    user_id = get_jwt_identity()

    match = MatchResult.query.filter_by(id=match_id, user_id=user_id).first()

    if not match:
        return jsonify({"error": "Match not found"}), 404

    data = request.get_json()

    try:
        if "confirmed_rank" in data:
            rank = int(data["confirmed_rank"])

            if rank < 1 or rank > 4:
                return jsonify({"error": "Invalid rank (must be 1-4)"}), 400

            match_id_attrs = [
                "primary_match_id",
                "secondary_match_id",
                "tertiary_match_id",
                "quaternary_match_id",
            ]

            confirmed_id = getattr(match, match_id_attrs[rank - 1])

            if not confirmed_id:
                return jsonify({"error": f"No match at rank {rank}"}), 400

            match.user_confirmed_match = confirmed_id

        if "custom_brand" in data:
            match.custom_brand = (
                data["custom_brand"][:100] if data["custom_brand"] else None
            )

        if "custom_type" in data:
            match.custom_type = (
                data["custom_type"][:100] if data["custom_type"] else None
            )

        match.confirmed_at = datetime.utcnow()

        # Update uploaded image's last matched timestamp
        uploaded = UploadedImage.query.get(match.uploaded_image_id)
        if uploaded:
            uploaded.last_matched_at = datetime.utcnow()

        db.session.commit()

        current_app.logger.info(f"Match confirmed by user {user_id}: {match.id}")

        return jsonify({"message": "Match confirmed"}), 200

    except ValueError:
        return jsonify({"error": "Invalid data format"}), 400
    except Exception as e:
        current_app.logger.error(f"Error confirming match: {str(e)}")
        return jsonify({"error": "Failed to confirm match"}), 500


@matches_bp.route("/<match_id>/re-match", methods=["POST"])
@jwt_required()
def re_match(match_id):
    """Re-run matching for an uploaded image"""
    user_id = get_jwt_identity()

    match = MatchResult.query.filter_by(id=match_id, user_id=user_id).first()

    if not match:
        return jsonify({"error": "Match not found"}), 404

    uploaded_image = UploadedImage.query.get(match.uploaded_image_id)

    if not uploaded_image:
        return jsonify({"error": "Uploaded image not found"}), 404

    try:
        from services.image_processor import ImageProcessor

        processor = ImageProcessor()

        # Deserialize features
        uploaded_features = processor.deserialize_features(
            uploaded_image.feature_vector
        )

        # Get all sole images
        sole_images = SoleImage.query.all()

        matches = []
        for sole in sole_images:
            sole_features = processor.deserialize_features(sole.feature_vector)
            similarity = processor.calculate_similarity(
                uploaded_features, sole_features
            )

            matches.append(
                {
                    "sole_id": sole.id,
                    "brand": sole.brand,
                    "product_type": sole.product_type,
                    "product_name": sole.product_name,
                    "confidence": similarity,
                }
            )

        # Sort and get top 4
        matches.sort(key=lambda x: x["confidence"], reverse=True)
        top_matches = matches[:4]

        # Update match result
        match.primary_match_id = (
            top_matches[0]["sole_id"] if len(top_matches) > 0 else None
        )
        match.primary_confidence = (
            top_matches[0]["confidence"] if len(top_matches) > 0 else 0
        )

        match.secondary_match_id = (
            top_matches[1]["sole_id"] if len(top_matches) > 1 else None
        )
        match.secondary_confidence = (
            top_matches[1]["confidence"] if len(top_matches) > 1 else 0
        )

        match.tertiary_match_id = (
            top_matches[2]["sole_id"] if len(top_matches) > 2 else None
        )
        match.tertiary_confidence = (
            top_matches[2]["confidence"] if len(top_matches) > 2 else 0
        )

        match.quaternary_match_id = (
            top_matches[3]["sole_id"] if len(top_matches) > 3 else None
        )
        match.quaternary_confidence = (
            top_matches[3]["confidence"] if len(top_matches) > 3 else 0
        )

        match.matched_at = datetime.utcnow()

        db.session.commit()

        current_app.logger.info(f"Match re-run for user {user_id}: {match.id}")

        # Return updated matches
        result_matches = []
        for i, m in enumerate(top_matches[:4]):
            sole = SoleImage.query.get(m["sole_id"])
            if sole:
                result_matches.append(
                    {
                        "rank": i + 1,
                        "brand": sole.brand,
                        "product_type": sole.product_type,
                        "product_name": sole.product_name,
                        "source_url": sole.source_url,
                        "confidence": float(m["confidence"]),
                    }
                )

        while len(result_matches) < 4:
            result_matches.append(None)

        return jsonify(
            {"message": "Match re-run complete", "matches": result_matches}
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error re-matching: {str(e)}")
        return jsonify({"error": "Failed to re-match image"}), 500


@matches_bp.route("/statistics", methods=["GET"])
@jwt_required()
def get_user_match_statistics():
    """Get user's matching statistics"""
    user_id = get_jwt_identity()

    total_matches = MatchResult.query.filter_by(user_id=user_id).count()
    confirmed_matches = (
        MatchResult.query.filter_by(user_id=user_id)
        .filter(MatchResult.user_confirmed_match.isnot(None))
        .count()
    )

    # Calculate average confidences
    from sqlalchemy import func

    avg_primary = (
        db.session.query(func.avg(MatchResult.primary_confidence))
        .filter_by(user_id=user_id)
        .scalar()
        or 0
    )

    avg_secondary = (
        db.session.query(func.avg(MatchResult.secondary_confidence))
        .filter_by(user_id=user_id)
        .scalar()
        or 0
    )

    custom_match_count = (
        MatchResult.query.filter_by(user_id=user_id)
        .filter(MatchResult.custom_brand.isnot(None))
        .count()
    )

    return jsonify(
        {
            "total_matches": total_matches,
            "confirmed_matches": confirmed_matches,
            "custom_match_count": custom_match_count,
            "average_primary_confidence": float(avg_primary),
            "average_secondary_confidence": float(avg_secondary),
        }
    ), 200
