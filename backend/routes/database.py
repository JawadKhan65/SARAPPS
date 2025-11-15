from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from extensions import db
from models import AdminUser, SoleImage

database_bp = Blueprint("database", __name__)


@database_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    try:
        db.session.execute("SELECT 1")
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        current_app.logger.error(f"Database health check failed: {str(e)}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@database_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_database_stats():
    """Get database statistics (admin only)"""
    user_id = get_jwt_identity()
    admin = AdminUser.query.get(user_id)

    if not admin:
        return jsonify({"error": "Admin access required"}), 403

    try:
        sole_images_count = SoleImage.query.count()
        unique_brands = db.session.query(SoleImage.brand).distinct().count()

        return jsonify(
            {
                "total_sole_images": sole_images_count,
                "unique_brands": unique_brands,
                "last_crawl": SoleImage.query.order_by(SoleImage.crawled_at.desc())
                .first()
                .crawled_at.isoformat()
                if sole_images_count > 0
                else None,
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error getting database stats: {str(e)}")
        return jsonify({"error": "Failed to get statistics"}), 500


@database_bp.route("/export/sole-images", methods=["GET"])
@jwt_required()
def export_sole_images():
    """Export sole images data (admin only)"""
    user_id = get_jwt_identity()
    admin = AdminUser.query.get(user_id)

    if not admin:
        return jsonify({"error": "Admin access required"}), 403

    brand_filter = request.args.get("brand")

    try:
        query = SoleImage.query

        if brand_filter:
            query = query.filter_by(brand=brand_filter)

        images = query.limit(1000).all()

        data = []
        for img in images:
            data.append(
                {
                    "id": img.id,
                    "brand": img.brand,
                    "product_type": img.product_type,
                    "product_name": img.product_name,
                    "source_url": img.source_url,
                    "quality_score": img.quality_score,
                    "uniqueness_score": img.uniqueness_score,
                    "crawled_at": img.crawled_at.isoformat()
                    if img.crawled_at
                    else None,
                }
            )

        return jsonify({"total": len(data), "images": data}), 200

    except Exception as e:
        current_app.logger.error(f"Error exporting data: {str(e)}")
        return jsonify({"error": "Failed to export data"}), 500


@database_bp.route("/cleanup", methods=["POST"])
@jwt_required()
def database_cleanup():
    """Clean up orphaned records (admin only)"""
    user_id = get_jwt_identity()
    admin = AdminUser.query.get(user_id)

    if not admin:
        return jsonify({"error": "Admin access required"}), 403

    try:
        from models import MatchResult, UploadedImage, User

        # Delete match results for deleted uploaded images
        orphaned_matches = (
            db.session.query(MatchResult)
            .filter(
                ~MatchResult.uploaded_image_id.in_(db.session.query(UploadedImage.id))
            )
            .count()
        )

        db.session.query(MatchResult).filter(
            ~MatchResult.uploaded_image_id.in_(db.session.query(UploadedImage.id))
        ).delete(synchronize_session=False)

        # Delete uploaded images for deleted users
        orphaned_uploads = (
            db.session.query(UploadedImage)
            .filter(~UploadedImage.user_id.in_(db.session.query(User.id)))
            .count()
        )

        db.session.query(UploadedImage).filter(
            ~UploadedImage.user_id.in_(db.session.query(User.id))
        ).delete(synchronize_session=False)

        db.session.commit()

        current_app.logger.info(
            f"Database cleanup: deleted {orphaned_matches} orphaned matches, "
            f"{orphaned_uploads} orphaned uploads"
        )

        return jsonify(
            {
                "message": "Cleanup complete",
                "orphaned_matches_deleted": orphaned_matches,
                "orphaned_uploads_deleted": orphaned_uploads,
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error during cleanup: {str(e)}")
        return jsonify({"error": "Failed to cleanup database"}), 500


@database_bp.route("/vacuum", methods=["POST"])
@jwt_required()
def database_vacuum():
    """Optimize database (admin only)"""
    user_id = get_jwt_identity()
    admin = AdminUser.query.get(user_id)

    if not admin:
        return jsonify({"error": "Admin access required"}), 403

    try:
        # For PostgreSQL, run VACUUM
        db.session.execute("VACUUM")
        db.session.commit()

        current_app.logger.info("Database optimized with VACUUM")

        return jsonify({"message": "Database optimized"}), 200

    except Exception as e:
        current_app.logger.error(f"Error during vacuum: {str(e)}")
        return jsonify({"error": "Failed to optimize database"}), 500
