from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from core.extensions import db
from core.models import AdminUser, SoleImage

database_bp = Blueprint("database", __name__)


@database_bp.route("/health", methods=["GET"])
def health_check():
    """
    Comprehensive health check endpoint for production monitoring
    Returns: 200 if healthy, 207 if degraded, 503 if unhealthy
    """
    import os
    import shutil
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    
    overall_healthy = True
    degraded = False
    
    # 1. Database connectivity check
    try:
        db.session.execute(db.text("SELECT 1"))
        health_status["checks"]["database"] = {
            "status": "ok",
            "message": "Connected"
        }
    except Exception as e:
        overall_healthy = False
        health_status["checks"]["database"] = {
            "status": "error",
            "message": str(e)
        }
    
    # 2. Database query performance check
    try:
        import time
        start = time.time()
        result = db.session.execute(db.text("SELECT COUNT(*) FROM sole_images"))
        query_time_ms = (time.time() - start) * 1000
        sole_count = result.scalar()
        
        health_status["checks"]["database_performance"] = {
            "status": "ok" if query_time_ms < 1000 else "warning",
            "query_time_ms": round(query_time_ms, 2),
            "sole_images_count": sole_count
        }
        
        if query_time_ms >= 1000:
            degraded = True
    except Exception as e:
        health_status["checks"]["database_performance"] = {
            "status": "error",
            "message": str(e)
        }
    
    # 3. Redis connectivity check
    try:
        from redis import Redis
        redis_url = current_app.config.get("REDIS_URL", "redis://localhost:6379/0")
        redis_client = Redis.from_url(redis_url, socket_connect_timeout=5)
        redis_client.ping()
        health_status["checks"]["redis"] = {
            "status": "ok",
            "message": "Connected"
        }
    except Exception as e:
        degraded = True
        health_status["checks"]["redis"] = {
            "status": "warning",
            "message": f"Unavailable (rate limiting may not work)"
        }
    
    # 4. Disk space check
    try:
        upload_dir = current_app.config.get("UPLOAD_FOLDER", "/data/uploads")
        
        if os.path.exists(upload_dir):
            total, used, free = shutil.disk_usage(upload_dir)
            free_percent = (free / total) * 100
            used_gb = used / (1024**3)
            free_gb = free / (1024**3)
            
            if free_percent < 10:
                overall_healthy = False
                status = "critical"
            elif free_percent < 20:
                degraded = True
                status = "warning"
            else:
                status = "ok"
            
            health_status["checks"]["disk_space"] = {
                "status": status,
                "free_percent": round(free_percent, 1),
                "free_gb": round(free_gb, 2),
                "used_gb": round(used_gb, 2)
            }
        else:
            health_status["checks"]["disk_space"] = {
                "status": "warning",
                "message": f"Upload directory not found: {upload_dir}"
            }
            degraded = True
    except Exception as e:
        health_status["checks"]["disk_space"] = {
            "status": "error",
            "message": str(e)
        }
    
    # 5. Database size and vector statistics
    try:
        result = db.session.execute(db.text("""
            SELECT 
                pg_size_pretty(pg_database_size(current_database())) as db_size,
                (SELECT COUNT(*) FROM sole_images WHERE clip_embedding IS NOT NULL) as vector_count,
                (SELECT COUNT(*) FROM sole_images) as total_images
        """))
        row = result.fetchone()
        
        vector_coverage = (row.vector_count / row.total_images * 100) if row.total_images > 0 else 0
        
        health_status["checks"]["database_stats"] = {
            "status": "ok",
            "database_size": row.db_size,
            "total_images": row.total_images,
            "images_with_vectors": row.vector_count,
            "vector_coverage_percent": round(vector_coverage, 1)
        }
        
        # Warn if vector coverage is low
        if vector_coverage < 80 and row.total_images > 100:
            health_status["checks"]["database_stats"]["status"] = "warning"
            health_status["checks"]["database_stats"]["message"] = "Low vector coverage - run backfill script"
            degraded = True
            
    except Exception as e:
        health_status["checks"]["database_stats"] = {
            "status": "error",
            "message": str(e)
        }
    
    # 6. pgvector extension check
    try:
        result = db.session.execute(db.text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            ) as has_pgvector
        """))
        has_pgvector = result.scalar()
        
        health_status["checks"]["pgvector"] = {
            "status": "ok" if has_pgvector else "warning",
            "installed": has_pgvector,
            "message": "Extension active" if has_pgvector else "Not installed - search performance degraded"
        }
        
        if not has_pgvector:
            degraded = True
    except Exception as e:
        health_status["checks"]["pgvector"] = {
            "status": "warning",
            "message": "Could not verify pgvector status"
        }
    
    # Determine overall status
    if not overall_healthy:
        health_status["status"] = "unhealthy"
        status_code = 503
    elif degraded:
        health_status["status"] = "degraded"
        status_code = 207  # Multi-status
    else:
        health_status["status"] = "healthy"
        status_code = 200
    
    return jsonify(health_status), status_code


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
        from core.models import MatchResult, UploadedImage, User

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
