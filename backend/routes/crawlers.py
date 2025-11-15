from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
import asyncio
from extensions import db
from models import Crawler, CrawlerRun, CrawlerStatistics, AdminUser
from services.scraper_manager import get_scraper_manager, cleanup_scraper_manager
from services.crawler_scheduler import get_scheduler
import uuid

crawlers_bp = Blueprint("crawlers", __name__)


@crawlers_bp.route("", methods=["GET", "OPTIONS"])
@jwt_required()
def list_crawlers():
    """List all crawlers with status and statistics"""
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
                "progress_percentage": crawler.progress_percentage,
                "current_batch": crawler.current_batch,
                "total_batches": crawler.total_batches,
                "schedule_cron": crawler.schedule_cron,
                "next_run_at": crawler.next_run_at.isoformat()
                if crawler.next_run_at
                else None,
                "total_runs": crawler.total_runs,
                "items_scraped": crawler.items_scraped,
                "current_run_items": crawler.current_run_items,
                "total_images_crawled": crawler.total_images_crawled,
                "unique_images_added": crawler.unique_images_added,
                "duplicate_count": crawler.duplicate_count,
                "uniqueness_percentage": crawler.uniqueness_percentage,
                "min_uniqueness_threshold": crawler.min_uniqueness_threshold,
                "last_started_at": crawler.last_started_at.isoformat()
                if crawler.last_started_at
                else None,
                "last_completed_at": crawler.last_completed_at.isoformat()
                if crawler.last_completed_at
                else None,
                "last_run_duration_minutes": crawler.last_run_duration_minutes,
                "last_error": crawler.last_error,
                "consecutive_errors": crawler.consecutive_errors,
                "cancel_requested": crawler.cancel_requested,
                "latest_run": {
                    "id": latest_run.id,
                    "status": latest_run.status,
                    "run_type": latest_run.run_type,
                    "started_at": latest_run.started_at.isoformat(),
                    "uniqueness_percentage": latest_run.uniqueness_percentage,
                    "items_scraped": latest_run.items_scraped,
                }
                if latest_run
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

    # Get recent runs
    recent_runs = (
        CrawlerRun.query.filter_by(crawler_id=crawler_id)
        .order_by(CrawlerRun.started_at.desc())
        .limit(10)
        .all()
    )

    runs_data = [
        {
            "id": run.id,
            "status": run.status,
            "run_type": run.run_type,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "duration_seconds": run.duration_seconds,
            "items_scraped": run.items_scraped,
            "unique_items": run.unique_items,
            "duplicate_items": run.duplicate_items,
            "uniqueness_percentage": run.uniqueness_percentage,
            "auto_stopped_low_uniqueness": run.auto_stopped_low_uniqueness,
            "cancelled_reason": run.cancelled_reason,
        }
        for run in recent_runs
    ]

    return jsonify(
        {
            "id": crawler.id,
            "name": crawler.name,
            "website_url": crawler.website_url,
            "scraper_module": crawler.scraper_module,
            "is_active": crawler.is_active,
            "is_running": crawler.is_running,
            "run_type": crawler.run_type,
            "progress_percentage": crawler.progress_percentage,
            "schedule_cron": crawler.schedule_cron,
            "next_run_at": crawler.next_run_at.isoformat()
            if crawler.next_run_at
            else None,
            "total_runs": crawler.total_runs,
            "items_scraped": crawler.items_scraped,
            "uniqueness_percentage": crawler.uniqueness_percentage,
            "min_uniqueness_threshold": crawler.min_uniqueness_threshold,
            "recent_runs": runs_data,
            "created_at": crawler.created_at.isoformat()
            if crawler.created_at
            else None,
        }
    ), 200


@crawlers_bp.route("/<crawler_id>/start", methods=["POST", "OPTIONS"])
@jwt_required()
def start_crawler(crawler_id):
    """Start a crawler run instantly"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    if crawler.is_running:
        return jsonify({"error": "Crawler is already running"}), 409

    if not crawler.is_active:
        return jsonify({"error": "Crawler is disabled"}), 403

    try:
        # Get scraper manager and start
        scraper_manager = get_scraper_manager(crawler_id, admin_id)

        # Run in background thread
        def run_scraper():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(scraper_manager.start_scraper("manual"))
            loop.close()
            cleanup_scraper_manager(crawler_id)

        import threading

        thread = threading.Thread(target=run_scraper, daemon=True)
        thread.start()

        current_app.logger.info(f"🚀 Crawler started: {crawler.name}")

        return (
            jsonify(
                {
                    "message": "Crawler started",
                    "crawler_id": crawler_id,
                    "run_type": "manual",
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Error starting crawler: {str(e)}")
        return jsonify({"error": f"Failed to start crawler: {str(e)}"}), 500


@crawlers_bp.route("/<crawler_id>/stop", methods=["POST", "OPTIONS"])
@jwt_required()
def stop_crawler(crawler_id):
    """Stop/cancel a running crawler"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    if not crawler.is_running:
        return jsonify({"error": "Crawler is not running"}), 409

    try:
        # Request cancellation via scraper manager
        scraper_manager = get_scraper_manager(crawler_id, admin_id)
        success = scraper_manager.cancel_run("Manual cancellation by admin")

        if success:
            current_app.logger.info(f"🛑 Crawler stop requested: {crawler.name}")
            return (
                jsonify(
                    {
                        "message": "Crawler stop requested",
                        "crawler_id": crawler_id,
                        "note": "Crawler will stop after current batch completes",
                    }
                ),
                200,
            )
        else:
            return jsonify({"error": "Failed to request stop"}), 500

    except Exception as e:
        current_app.logger.error(f"Error stopping crawler: {str(e)}")
        return jsonify({"error": "Failed to stop crawler"}), 500


@crawlers_bp.route("/<crawler_id>/schedule", methods=["PUT", "OPTIONS"])
@jwt_required()
def update_crawler_schedule(crawler_id):
    """Update crawler schedule (cron format)"""
    if request.method == "OPTIONS":
        return "", 204

    admin_id = get_jwt_identity()
    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    data = request.get_json()
    cron_expression = data.get("schedule")

    if not cron_expression:
        return jsonify({"error": "Schedule required (cron format)"}), 400

    try:
        # Update crawler schedule in database
        crawler.schedule_cron = cron_expression
        crawler.scheduled_by = admin_id
        db.session.commit()

        # Update scheduler
        scheduler = get_scheduler()
        success = scheduler.add_crawler_job(crawler_id, cron_expression)

        if success:
            current_app.logger.info(
                f"📅 Crawler schedule updated: {crawler.name} -> {cron_expression}"
            )
            return jsonify(
                {"message": "Schedule updated", "schedule": cron_expression}
            ), 200
        else:
            return jsonify({"error": "Invalid cron expression"}), 400

    except Exception as e:
        current_app.logger.error(f"Error updating schedule: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Failed to update schedule"}), 500


@crawlers_bp.route("/<crawler_id>/schedule", methods=["DELETE"])
@jwt_required()
def remove_crawler_schedule(crawler_id):
    """Remove crawler schedule"""
    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    try:
        crawler.schedule_cron = None
        crawler.next_run_at = None
        db.session.commit()

        # Remove from scheduler
        scheduler = get_scheduler()
        scheduler.remove_crawler_job(crawler_id)

        current_app.logger.info(f"📅 Crawler schedule removed: {crawler.name}")
        return jsonify({"message": "Schedule removed"}), 200

    except Exception as e:
        current_app.logger.error(f"Error removing schedule: {str(e)}")
        return jsonify({"error": "Failed to remove schedule"}), 500


@crawlers_bp.route("/<crawler_id>/toggle", methods=["PUT", "OPTIONS"])
@jwt_required()
def toggle_crawler(crawler_id):
    """Enable/disable a crawler"""
    if request.method == "OPTIONS":
        return "", 204

    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    try:
        crawler.is_active = not crawler.is_active
        db.session.commit()

        status = "enabled" if crawler.is_active else "disabled"
        current_app.logger.info(f"Crawler {status}: {crawler.name}")

        # Pause/resume schedule
        scheduler = get_scheduler()
        if crawler.is_active and crawler.schedule_cron:
            scheduler.add_crawler_job(crawler_id, crawler.schedule_cron)
        else:
            scheduler.remove_crawler_job(crawler_id)

        return jsonify(
            {"message": f"Crawler {status}", "is_active": crawler.is_active}
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error toggling crawler: {str(e)}")
        return jsonify({"error": "Failed to toggle crawler"}), 500


@crawlers_bp.route("/<crawler_id>/config", methods=["PUT"])
@jwt_required()
def update_crawler_config(crawler_id):
    """Update crawler configuration"""
    crawler = Crawler.query.get(crawler_id)

    if not crawler:
        return jsonify({"error": "Crawler not found"}), 404

    data = request.get_json()

    try:
        if "name" in data:
            crawler.name = data["name"]
        if "website_url" in data:
            crawler.website_url = data["website_url"]
        if "scraper_module" in data:
            crawler.scraper_module = data["scraper_module"]
        if "min_uniqueness_threshold" in data:
            crawler.min_uniqueness_threshold = float(data["min_uniqueness_threshold"])
        if "notify_admin_on_low_uniqueness" in data:
            crawler.notify_admin_on_low_uniqueness = data[
                "notify_admin_on_low_uniqueness"
            ]

        db.session.commit()

        current_app.logger.info(f"⚙️  Crawler config updated: {crawler.name}")
        return jsonify({"message": "Configuration updated"}), 200

    except Exception as e:
        current_app.logger.error(f"Error updating config: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Failed to update configuration"}), 500


@crawlers_bp.route("/<crawler_id>/runs", methods=["GET"])
@jwt_required()
def get_crawler_runs(crawler_id):
    """Get crawler run history"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    runs = (
        CrawlerRun.query.filter_by(crawler_id=crawler_id)
        .order_by(CrawlerRun.started_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify(
        {
            "runs": [
                {
                    "id": run.id,
                    "status": run.status,
                    "run_type": run.run_type,
                    "started_at": run.started_at.isoformat(),
                    "completed_at": run.completed_at.isoformat()
                    if run.completed_at
                    else None,
                    "duration_seconds": run.duration_seconds,
                    "items_scraped": run.items_scraped,
                    "unique_items": run.unique_items,
                    "uniqueness_percentage": run.uniqueness_percentage,
                }
                for run in runs.items
            ],
            "total": runs.total,
            "page": page,
            "pages": runs.pages,
        }
    ), 200


@crawlers_bp.route("/statistics", methods=["GET"])
@jwt_required()
def get_statistics():
    """Get global crawler statistics"""
    stats = CrawlerStatistics.query.first()

    # Calculate real-time statistics
    total_crawlers = Crawler.query.count()
    active_crawlers = Crawler.query.filter_by(is_active=True).count()
    running_crawlers = Crawler.query.filter_by(is_running=True).count()

    if not stats:
        return jsonify(
            {
                "unique_sole_images": 0,
                "unique_brands": 0,
                "total_crawlers": total_crawlers,
                "active_crawlers": active_crawlers,
                "running_crawlers": running_crawlers,
                "last_updated": None,
            }
        ), 200

    return jsonify(
        {
            "unique_sole_images": stats.unique_sole_images,
            "unique_brands": stats.unique_brands,
            "total_crawlers": total_crawlers,
            "active_crawlers": active_crawlers,
            "running_crawlers": running_crawlers,
            "average_matching_time_ms": stats.average_matching_time_ms,
            "primary_match_avg_confidence": stats.primary_match_avg_confidence,
            "custom_match_percentage": stats.custom_match_percentage,
            "last_updated": stats.last_updated.isoformat()
            if stats.last_updated
            else None,
        }
    ), 200


@crawlers_bp.route("/create", methods=["POST"])
@jwt_required()
def create_crawler():
    """Create a new crawler"""
    data = request.get_json()

    if not data.get("name") or not data.get("website_url"):
        return jsonify({"error": "Name and website_url required"}), 400

    try:
        crawler = Crawler(
            id=str(uuid.uuid4()),
            name=data["name"],
            website_url=data["website_url"],
            scraper_module=data.get("scraper_module"),
            schedule_cron=data.get("schedule_cron"),
            min_uniqueness_threshold=data.get("min_uniqueness_threshold", 30.0),
        )

        db.session.add(crawler)
        db.session.commit()

        # Add to scheduler if has cron
        if crawler.schedule_cron:
            scheduler = get_scheduler()
            scheduler.add_crawler_job(crawler.id, crawler.schedule_cron)

        current_app.logger.info(f"✨ New crawler created: {crawler.name}")
        return jsonify({"message": "Crawler created", "id": crawler.id}), 201

    except Exception as e:
        current_app.logger.error(f"Error creating crawler: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Failed to create crawler"}), 500
