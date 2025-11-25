"""
Production-Grade Background Tasks for Crawlers
Features:
- Retry logic with exponential backoff
- Heartbeat monitoring
- Graceful shutdown
- Dead letter queue
- Progress tracking
- Error categorization
- Resource cleanup
- Job timeout handling
"""

import os
import sys
import asyncio
import signal
import traceback
from datetime import datetime, timedelta
from typing import Dict, Optional
from core.extensions import db
from services.scraper_manager import get_scraper_manager, cleanup_scraper_manager
import redis
from rq import get_current_job
from rq.job import JobStatus

# Global flag for graceful shutdown
_shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global _shutdown_requested
    _shutdown_requested = True
    print(f"\n⚠️  Shutdown signal received ({signum}). Finishing current job...")


# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def get_redis_connection():
    """Get Redis connection for RQ"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(redis_url)


class CrawlerJobError(Exception):
    """Base exception for crawler job errors"""
    def __init__(self, message: str, retryable: bool = True, category: str = "unknown"):
        self.message = message
        self.retryable = retryable
        self.category = category
        super().__init__(self.message)


class NetworkError(CrawlerJobError):
    """Network-related errors (retryable)"""
    def __init__(self, message: str):
        super().__init__(message, retryable=True, category="network")


class ValidationError(CrawlerJobError):
    """Data validation errors (not retryable)"""
    def __init__(self, message: str):
        super().__init__(message, retryable=False, category="validation")


class ResourceError(CrawlerJobError):
    """Resource exhaustion errors (retryable)"""
    def __init__(self, message: str):
        super().__init__(message, retryable=True, category="resource")


def send_heartbeat(redis_conn, crawler_id: str, job_id: str):
    """Send heartbeat to indicate job is alive"""
    try:
        redis_conn.hset(
            f"crawler:{crawler_id}:heartbeat",
            "last_beat",
            datetime.utcnow().isoformat()
        )
        redis_conn.hset(
            f"crawler:{crawler_id}:heartbeat",
            "job_id",
            job_id
        )
        redis_conn.expire(f"crawler:{crawler_id}:heartbeat", 300)  # 5 min TTL
    except Exception:
        pass  # Don't fail job if heartbeat fails


def update_job_progress(redis_conn, crawler_id: str, progress_data: Dict):
    """
    Update job progress in Redis
    
    Args:
        redis_conn: Redis connection
        crawler_id: Crawler ID
        progress_data: Dict with keys: current, total, percentage, message
    """
    try:
        pipeline = redis_conn.pipeline()
        pipeline.hset(f"crawler:{crawler_id}:progress", "current", progress_data.get("current", 0))
        pipeline.hset(f"crawler:{crawler_id}:progress", "total", progress_data.get("total", 0))
        pipeline.hset(f"crawler:{crawler_id}:progress", "percentage", progress_data.get("percentage", 0))
        pipeline.hset(f"crawler:{crawler_id}:progress", "message", progress_data.get("message", ""))
        pipeline.hset(f"crawler:{crawler_id}:progress", "updated_at", datetime.utcnow().isoformat())
        pipeline.expire(f"crawler:{crawler_id}:progress", 86400)  # 24 hour TTL
        pipeline.execute()
    except Exception as e:
        print(f"⚠️  Failed to update progress: {e}")


def categorize_error(error: Exception) -> CrawlerJobError:
    """Categorize exceptions into retryable/non-retryable errors"""
    error_str = str(error).lower()
    
    # Network errors (retryable)
    if any(keyword in error_str for keyword in [
        'connection', 'timeout', 'network', 'dns', 'unreachable', 'refused'
    ]):
        return NetworkError(str(error))
    
    # Resource errors (retryable)
    if any(keyword in error_str for keyword in [
        'memory', 'disk', 'space', 'resource', 'quota'
    ]):
        return ResourceError(str(error))
    
    # Validation errors (not retryable)
    if any(keyword in error_str for keyword in [
        'validation', 'invalid', 'malformed', 'corrupt'
    ]):
        return ValidationError(str(error))
    
    # Default: treat as retryable with unknown category
    return CrawlerJobError(str(error), retryable=True, category="unknown")


def run_crawler_job(crawler_id: str, admin_id: str, run_type: str = "manual"):
    """
    Production-grade background job to run a crawler
    
    Features:
    - Automatic retry with exponential backoff
    - Heartbeat monitoring
    - Graceful shutdown handling
    - Progress tracking
    - Error categorization
    - Resource cleanup
    
    Args:
        crawler_id: ID of the crawler to run
        admin_id: ID of the admin who started the job
        run_type: 'manual' or 'scheduled'
    """
    from app import create_app
    from core.models import Crawler, CrawlerRun
    
    # Create Flask app context
    app = create_app()
    
    with app.app_context():
        job = get_current_job()
        redis_conn = get_redis_connection()
        lock = None
        scraper_manager = None
        start_time = datetime.utcnow()
        
        # Job metadata
        job_id = job.id if job else "unknown"
        attempt = job.meta.get('attempt', 1) if job else 1
        max_attempts = 3
        
        app.logger.info(
            f"🚀 Starting crawler job {job_id} "
            f"(attempt {attempt}/{max_attempts}, crawler: {crawler_id})"
        )
        
        try:
            # === STEP 1: Acquire Global Lock ===
            lock_key = "crawler:global:lock"
            lock_timeout = 7200  # 2 hours
            lock = redis_conn.lock(lock_key, timeout=lock_timeout, blocking_timeout=0)
            
            if not lock.acquire(blocking=False):
                app.logger.warning(f"Another crawler is running. Job {job_id} queued.")
                raise CrawlerJobError(
                    "Another crawler is already running. Only one crawler can run at a time.",
                    retryable=False,
                    category="concurrency"
                )
            
            app.logger.info(f"✅ Acquired global crawler lock (timeout: {lock_timeout}s)")
            
            # === STEP 2: Initialize Job Tracking ===
            job_data = {
                "job_id": job_id,
                "status": "running",
                "started_at": start_time.isoformat(),
                "attempt": attempt,
                "max_attempts": max_attempts,
                "admin_id": admin_id,
                "run_type": run_type,
            }
            
            # Store in Redis with TTL
            pipeline = redis_conn.pipeline()
            for key, value in job_data.items():
                pipeline.hset(f"crawler:{crawler_id}:job", key, str(value))
            pipeline.expire(f"crawler:{crawler_id}:job", 86400)  # 24 hours
            pipeline.execute()
            
            # === STEP 3: Send Initial Heartbeat ===
            send_heartbeat(redis_conn, crawler_id, job_id)
            
            # === STEP 4: Initialize Progress Tracking ===
            update_job_progress(redis_conn, crawler_id, {
                "current": 0,
                "total": 0,
                "percentage": 0,
                "message": "Initializing crawler..."
            })
            
            # === STEP 5: Check Shutdown Signal ===
            if _shutdown_requested:
                raise CrawlerJobError(
                    "Worker shutdown requested before job start",
                    retryable=True,
                    category="shutdown"
                )
            
            # === STEP 6: Load Crawler from Database ===
            crawler = Crawler.query.get(crawler_id)
            if not crawler:
                raise ValidationError(f"Crawler {crawler_id} not found in database")
            
            if not crawler.is_active:
                raise ValidationError(f"Crawler {crawler.name} is disabled")
            
            app.logger.info(f"📊 Crawler loaded: {crawler.name}")
            
            # === STEP 7: Create Scraper Manager ===
            scraper_manager = get_scraper_manager(crawler_id, admin_id)
            
            # === STEP 8: Run Crawler with Progress Updates ===
            update_job_progress(redis_conn, crawler_id, {
                "current": 0,
                "total": 0,
                "percentage": 5,
                "message": f"Starting {crawler.name} scraper..."
            })
            
            # Periodic heartbeat during execution
            async def run_with_heartbeat():
                """Run scraper with periodic heartbeats"""
                import asyncio
                
                async def heartbeat_loop():
                    """Send heartbeat every 30 seconds"""
                    while True:
                        await asyncio.sleep(30)
                        send_heartbeat(redis_conn, crawler_id, job_id)
                        
                        # Check for shutdown
                        if _shutdown_requested:
                            app.logger.warning("Shutdown requested, stopping crawler...")
                            if scraper_manager:
                                scraper_manager.stop_requested = True
                            break
                
                # Run scraper and heartbeat concurrently
                heartbeat_task = asyncio.create_task(heartbeat_loop())
                
                try:
                    result = await scraper_manager.start_scraper(run_type)
                    return result
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
            
            # Execute with heartbeat
            result = asyncio.run(run_with_heartbeat())
            
            # === STEP 9: Process Result ===
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            if result.get("success"):
                app.logger.info(
                    f"✅ Crawler job {job_id} completed successfully "
                    f"({duration:.1f}s, {result.get('total_unique', 0)} unique items)"
                )
                
                # Update Redis
                pipeline = redis_conn.pipeline()
                pipeline.hset(f"crawler:{crawler_id}:job", "status", "completed")
                pipeline.hset(f"crawler:{crawler_id}:job", "completed_at", datetime.utcnow().isoformat())
                pipeline.hset(f"crawler:{crawler_id}:job", "duration_seconds", int(duration))
                pipeline.hset(f"crawler:{crawler_id}:job", "items_scraped", result.get("total_scraped", 0))
                pipeline.hset(f"crawler:{crawler_id}:job", "items_unique", result.get("total_unique", 0))
                pipeline.hset(f"crawler:{crawler_id}:job", "items_duplicate", result.get("total_duplicates", 0))
                pipeline.expire(f"crawler:{crawler_id}:job", 86400)
                pipeline.execute()
                
                update_job_progress(redis_conn, crawler_id, {
                    "current": result.get("total_scraped", 0),
                    "total": result.get("total_scraped", 0),
                    "percentage": 100,
                    "message": f"Completed: {result.get('total_unique', 0)} unique items"
                })
                
                return result
            else:
                error_msg = result.get("error", "Unknown error")
                app.logger.error(f"❌ Crawler job {job_id} failed: {error_msg}")
                
                # Categorize error for retry decision
                categorized_error = CrawlerJobError(
                    error_msg,
                    retryable=True,  # Assume retryable for scraper errors
                    category="scraper"
                )
                raise categorized_error
        
        except Exception as e:
            # === ERROR HANDLING ===
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            # Categorize error
            if isinstance(e, CrawlerJobError):
                categorized_error = e
            else:
                categorized_error = categorize_error(e)
            
            error_info = {
                "message": categorized_error.message,
                "category": categorized_error.category,
                "retryable": categorized_error.retryable,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "traceback": traceback.format_exc()
            }
            
            app.logger.error(
                f"❌ Crawler job {job_id} failed "
                f"(attempt {attempt}/{max_attempts}, "
                f"category: {categorized_error.category}, "
                f"retryable: {categorized_error.retryable}): "
                f"{categorized_error.message}"
            )
            
            # Store error details in Redis
            pipeline = redis_conn.pipeline()
            pipeline.hset(f"crawler:{crawler_id}:job", "status", "failed")
            pipeline.hset(f"crawler:{crawler_id}:job", "error_message", categorized_error.message)
            pipeline.hset(f"crawler:{crawler_id}:job", "error_category", categorized_error.category)
            pipeline.hset(f"crawler:{crawler_id}:job", "error_retryable", str(categorized_error.retryable))
            pipeline.hset(f"crawler:{crawler_id}:job", "failed_at", datetime.utcnow().isoformat())
            pipeline.hset(f"crawler:{crawler_id}:job", "duration_seconds", int(duration))
            pipeline.expire(f"crawler:{crawler_id}:job", 86400)
            
            # Store full traceback for debugging
            pipeline.hset(f"crawler:{crawler_id}:error", "traceback", traceback.format_exc())
            pipeline.hset(f"crawler:{crawler_id}:error", "timestamp", datetime.utcnow().isoformat())
            pipeline.expire(f"crawler:{crawler_id}:error", 86400)
            pipeline.execute()
            
            update_job_progress(redis_conn, crawler_id, {
                "current": 0,
                "total": 0,
                "percentage": 0,
                "message": f"Failed: {categorized_error.message[:100]}"
            })
            
            # === RETRY LOGIC ===
            if categorized_error.retryable and attempt < max_attempts:
                # Calculate exponential backoff
                backoff_seconds = min(2 ** attempt * 60, 900)  # Max 15 minutes
                
                app.logger.info(
                    f"🔄 Will retry job {job_id} in {backoff_seconds}s "
                    f"(attempt {attempt + 1}/{max_attempts})"
                )
                
                # Store retry info
                if job:
                    job.meta['attempt'] = attempt + 1
                    job.meta['last_error'] = categorized_error.message
                    job.meta['retry_at'] = (datetime.utcnow() + timedelta(seconds=backoff_seconds)).isoformat()
                    job.save_meta()
                
                # Re-queue with delay
                from rq import Queue
                queue = Queue("crawlers", connection=redis_conn)
                queue.enqueue_in(
                    timedelta(seconds=backoff_seconds),
                    run_crawler_job,
                    crawler_id,
                    admin_id,
                    run_type,
                    job_timeout=7200,
                    result_ttl=86400,
                    failure_ttl=86400,
                    meta={'attempt': attempt + 1}
                )
            else:
                # Max attempts reached or non-retryable error
                reason = "non-retryable error" if not categorized_error.retryable else "max attempts reached"
                app.logger.error(
                    f"💀 Job {job_id} moved to dead letter queue ({reason})"
                )
                
                # Move to dead letter queue
                redis_conn.lpush(
                    "crawler:dead_letter_queue",
                    f"{crawler_id}:{job_id}:{datetime.utcnow().isoformat()}"
                )
                redis_conn.ltrim("crawler:dead_letter_queue", 0, 99)  # Keep last 100
            
            # Re-raise to mark job as failed in RQ
            raise
        
        finally:
            # === CLEANUP (ALWAYS RUNS) ===
            cleanup_duration = datetime.utcnow() - start_time
            
            app.logger.info(f"🧹 Cleaning up job {job_id}...")
            
            # Cleanup scraper manager
            if scraper_manager:
                try:
                    cleanup_scraper_manager(crawler_id)
                    app.logger.info("✅ Scraper manager cleaned up")
                except Exception as e:
                    app.logger.warning(f"⚠️  Failed to cleanup scraper manager: {e}")
            
            # Release global lock
            if lock:
                try:
                    lock.release()
                    app.logger.info("✅ Released global crawler lock")
                except Exception as e:
                    app.logger.warning(f"⚠️  Failed to release lock: {e}")
            
            # Clear database is_running flag
            try:
                from core.models import Crawler
                crawler = Crawler.query.get(crawler_id)
                if crawler and crawler.is_running:
                    crawler.is_running = False
                    db.session.commit()
                    app.logger.info("✅ Cleared crawler is_running flag")
            except Exception as e:
                app.logger.warning(f"⚠️  Failed to clear is_running flag: {e}")
            
            # Remove heartbeat
            try:
                redis_conn.delete(f"crawler:{crawler_id}:heartbeat")
            except Exception:
                pass
            
            app.logger.info(
                f"🏁 Job {job_id} cleanup complete "
                f"(total duration: {cleanup_duration.total_seconds():.1f}s)"
            )


def cancel_crawler_job(crawler_id: str):
    """
    Cancel a running crawler job
    
    Args:
        crawler_id: ID of the crawler to cancel
    
    Returns:
        dict: Success status and message
    """
    from app import create_app
    from rq.job import Job
    from core.models import Crawler
    
    app = create_app()
    
    with app.app_context():
        redis_conn = get_redis_connection()
        
        # Get job ID from Redis
        job_id_bytes = redis_conn.hget(f"crawler:{crawler_id}:job", "job_id")
        
        if not job_id_bytes:
            raise ValueError(f"No running job found for crawler {crawler_id}")
        
        job_id = job_id_bytes.decode() if isinstance(job_id_bytes, bytes) else job_id_bytes
        
        try:
            # Fetch and cancel RQ job
            job = Job.fetch(job_id, connection=redis_conn)
            
            if job.get_status() in [JobStatus.QUEUED, JobStatus.STARTED]:
                job.cancel()
                app.logger.info(f"🛑 Cancelled RQ job {job_id}")
            
            # Update database
            crawler = Crawler.query.get(crawler_id)
            if crawler:
                crawler.is_running = False
                crawler.cancel_requested = False
                db.session.commit()
            
            # Update Redis
            pipeline = redis_conn.pipeline()
            pipeline.hset(f"crawler:{crawler_id}:job", "status", "cancelled")
            pipeline.hset(f"crawler:{crawler_id}:job", "cancelled_at", datetime.utcnow().isoformat())
            pipeline.delete(f"crawler:{crawler_id}:heartbeat")
            pipeline.execute()
            
            update_job_progress(redis_conn, crawler_id, {
                "current": 0,
                "total": 0,
                "percentage": 0,
                "message": "Cancelled by user"
            })
            
            app.logger.info(f"✅ Cancelled crawler job {job_id} for crawler {crawler_id}")
            
            return {"success": True, "message": "Crawler job cancelled successfully"}
        
        except Exception as e:
            app.logger.error(f"❌ Failed to cancel job {job_id}: {str(e)}")
            raise


def get_crawler_job_status(crawler_id: str) -> Optional[Dict]:
    """
    Get comprehensive job status from Redis
    
    Args:
        crawler_id: ID of the crawler
    
    Returns:
        dict: Job status with progress, heartbeat, and error info
    """
    redis_conn = get_redis_connection()
    
    # Get job data
    job_data = redis_conn.hgetall(f"crawler:{crawler_id}:job")
    if not job_data:
        return None
    
    # Decode bytes to strings
    status = {
        k.decode() if isinstance(k, bytes) else k: 
        v.decode() if isinstance(v, bytes) else v
        for k, v in job_data.items()
    }
    
    # Add progress data
    progress_data = redis_conn.hgetall(f"crawler:{crawler_id}:progress")
    if progress_data:
        status['progress'] = {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in progress_data.items()
        }
    
    # Add heartbeat data
    heartbeat_data = redis_conn.hgetall(f"crawler:{crawler_id}:heartbeat")
    if heartbeat_data:
        status['heartbeat'] = {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in heartbeat_data.items()
        }
        
        # Check if heartbeat is stale (> 5 minutes old)
        try:
            last_beat = status['heartbeat'].get('last_beat')
            if last_beat:
                last_beat_time = datetime.fromisoformat(last_beat)
                if datetime.utcnow() - last_beat_time > timedelta(minutes=5):
                    status['heartbeat_stale'] = True
                    status['status'] = 'stalled'
        except Exception:
            pass
    
    # Add error details if available
    error_data = redis_conn.hgetall(f"crawler:{crawler_id}:error")
    if error_data:
        status['error_details'] = {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in error_data.items()
        }
    
    return status


def get_worker_health() -> Dict:
    """
    Get worker health metrics
    
    Returns:
        dict: Worker health status and metrics
    """
    redis_conn = get_redis_connection()
    
    try:
        from rq import Queue, Worker
        
        queue = Queue("crawlers", connection=redis_conn)
        workers = Worker.all(connection=redis_conn)
        
        return {
            "healthy": True,
            "workers": len(workers),
            "queued_jobs": queue.count,
            "started_jobs": len(queue.started_job_registry),
            "failed_jobs": len(queue.failed_job_registry),
            "finished_jobs": len(queue.finished_job_registry),
            "dead_letter_queue_size": redis_conn.llen("crawler:dead_letter_queue"),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
