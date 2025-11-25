from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from core.extensions import db
from core.models import Crawler, CrawlerStatistics
import uuid

crawlers_bp = Blueprint("crawlers", __name__)


@crawlers_bp.route("", methods=["GET"])
@jwt_required()
def list_crawlers():
    """List all crawlers with status and statistics"""
    crawlers = Crawler.query.all()

    crawler_list = []
    for crawler in crawlers:
        crawler_list.append(
            {
                "id": crawler.id,
                "name": crawler.name,
                "website_url": crawler.website_url,
                "is_active": crawler.is_active,
                "is_running": crawler.is_running,
                "schedule": crawler.schedule,
                "total_images_crawled": crawler.total_images_crawled,
                "unique_images_added": crawler.unique_images_added,
                "unique_brands_count": crawler.unique_brands_count,
                "last_started_at": crawler.last_started_at.isoformat()
                if crawler.last_started_at
                else None,
                "last_completed_at": crawler.last_completed_at.isoformat()
                if crawler.last_completed_at
                else None,
                "last_run_duration": crawler.last_run_duration,
                "last_error": crawler.last_error,
                "last_error_at": crawler.last_error_at.isoformat()
                if crawler.last_error_at
                else None,
            }
        )

    return jsonify({"crawlers": crawler_list, "total": len(crawler_list)}), 200


@crawlers_bp.route("/<crawler_id>", methods=["GET"])
@jwt_required()
def get_crawler(crawler_id):
    """Get detailed crawler information"""
    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    return jsonify(
        {
            "id": crawler.id,
            "name": crawler.name,
            "website_url": crawler.website_url,
            "is_active": crawler.is_active,
            "is_running": crawler.is_running,
            "schedule": crawler.schedule,
            "total_images_crawled": crawler.total_images_crawled,
            "unique_images_added": crawler.unique_images_added,
            "unique_brands_count": crawler.unique_brands_count,
            "total_runs": crawler.total_runs,
            "last_started_at": crawler.last_started_at.isoformat()
            if crawler.last_started_at
            else None,
            "last_completed_at": crawler.last_completed_at.isoformat()
            if crawler.last_completed_at
            else None,
            "last_run_duration": crawler.last_run_duration,
            "last_error": crawler.last_error,
            "last_error_at": crawler.last_error_at.isoformat()
            if crawler.last_error_at
            else None,
            "created_at": crawler.created_at.isoformat()
            if crawler.created_at
            else None,
        }
    ), 200


@crawlers_bp.route("/<crawler_id>/start", methods=["POST"])
@jwt_required()
def start_crawler(crawler_id):
    """Start a crawler run"""
    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    if crawler.is_running:
        return jsonify({"error": "Crawler is already running"}), 409

    if not crawler.is_active:
        return jsonify({"error": "Crawler is disabled"}), 403

    try:
        crawler.is_running = True
        crawler.last_started_at = datetime.utcnow()
        crawler.total_runs += 1
        db.session.commit()

        current_app.logger.info(f"Crawler started: {crawler.name}")

        return jsonify({"message": "Crawler started", "crawler_id": crawler_id}), 200

    except Exception as e:
        current_app.logger.error(f"Error starting crawler: {str(e)}")
        return jsonify({"error": "Failed to start crawler"}), 500


@crawlers_bp.route("/<crawler_id>/stop", methods=["POST"])
@jwt_required()
def stop_crawler(crawler_id):
    """Stop a running crawler"""
    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    if not crawler.is_running:
        return jsonify({"error": "Crawler is not running"}), 409

    try:
        crawler.is_running = False
        crawler.last_completed_at = datetime.utcnow()

        if crawler.last_started_at:
            duration = (
                crawler.last_completed_at - crawler.last_started_at
            ).total_seconds()
            crawler.last_run_duration = duration

        db.session.commit()

        current_app.logger.info(f"Crawler stopped: {crawler.name}")

        return jsonify({"message": "Crawler stopped", "crawler_id": crawler_id}), 200

    except Exception as e:
        current_app.logger.error(f"Error stopping crawler: {str(e)}")
        return jsonify({"error": "Failed to stop crawler"}), 500


@crawlers_bp.route("/<crawler_id>/schedule", methods=["PUT"])
@jwt_required()
def update_crawler_schedule(crawler_id):
    """Update crawler schedule (cron format)"""
    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    data = request.get_json()

    if not data.get("schedule"):
        return jsonify({"error": "Schedule required"}), 400

    try:
        crawler.schedule = data["schedule"]
        db.session.commit()

        current_app.logger.info(
            f"Crawler schedule updated: {crawler.name} -> {data['schedule']}"
        )

        return jsonify({"message": "Schedule updated"}), 200

    except Exception as e:
        current_app.logger.error(f"Error updating schedule: {str(e)}")
        return jsonify({"error": "Failed to update schedule"}), 500


@crawlers_bp.route("/<crawler_id>/toggle", methods=["PUT"])
@jwt_required()
def toggle_crawler(crawler_id):
    """Enable/disable a crawler"""
    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    try:
        crawler.is_active = not crawler.is_active
        db.session.commit()

        status = "enabled" if crawler.is_active else "disabled"
        current_app.logger.info(f"Crawler {status}: {crawler.name}")

        return jsonify(
            {"message": f"Crawler {status}", "is_active": crawler.is_active}
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error toggling crawler: {str(e)}")
        return jsonify({"error": "Failed to toggle crawler"}), 500


@crawlers_bp.route("/statistics", methods=["GET"])
@jwt_required()
def get_statistics():
    """Get global crawler statistics"""
    stats = CrawlerStatistics.query.first()

    if not stats:
        # Return empty statistics
        return jsonify(
            {
                "unique_sole_images": 0,
                "unique_brands": 0,
                "total_crawlers": 0,
                "last_updated": None,
            }
        ), 200

    return jsonify(
        {
            "unique_sole_images": stats.unique_sole_images,
            "unique_brands": stats.unique_brands,
            "total_crawlers": stats.total_crawlers,
            "average_matching_time_ms": stats.average_matching_time_ms,
            "primary_match_avg_confidence": stats.primary_match_avg_confidence,
            "custom_match_percentage": stats.custom_match_percentage,
            "last_updated": stats.last_updated.isoformat()
            if stats.last_updated
            else None,
        }
    ), 200
