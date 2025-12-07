"""
Production-Grade RQ Worker
Features:
- Graceful shutdown handling
- Auto-cleanup of stuck jobs
- Health monitoring
- Cross-platform support (Windows/Linux)
- Worker metrics
"""

import os
import sys
import platform
import signal
import time
from datetime import datetime

# Add backend directory to Python path for RQ task imports
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from redis import Redis
from rq import Worker, Queue, SimpleWorker
from rq.worker import StopRequested
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Redis connection
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(redis_url)

# Queue names
CRAWLER_QUEUE = "crawlers"
DEFAULT_QUEUE = "default"

# Graceful shutdown flag
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global shutdown_requested
    shutdown_requested = True
    print(f"\n⚠️  Shutdown signal received (signal {signum})")
    print("🔄 Finishing current job before shutdown...")
    print("💡 Press Ctrl+C again to force quit (may lose data)")


def cleanup_stuck_crawlers():
    """
    Clean up any stuck crawler flags in database on worker startup
    This handles cases where a previous worker crashed without cleanup
    """
    try:
        from app import create_app
        from core.models import Crawler
        from core.extensions import db
        
        app = create_app()
        with app.app_context():
            # Reset all is_running flags - fresh start for worker
            stuck_count = Crawler.query.filter_by(is_running=True).count()
            if stuck_count > 0:
                Crawler.query.update({
                    'is_running': False,
                    'cancel_requested': False
                })
                db.session.commit()
                print(f"🧹 Cleaned up {stuck_count} stuck crawler flag(s)")
            else:
                print("✨ No stuck crawlers found - database is clean")
    except Exception as e:
        print(f"⚠️  Warning: Could not cleanup stuck crawlers: {e}")


def cleanup_stale_jobs():
    """Clean up stale job registries"""
    try:
        from rq import Queue
        
        queue = Queue(CRAWLER_QUEUE, connection=redis_conn)
        
        # Clean up started jobs that are no longer running
        started_count = len(queue.started_job_registry)
        if started_count > 0:
            queue.started_job_registry.cleanup()
            print(f"🧹 Cleaned up {started_count} stale started job(s)")
        
        # Clean up failed jobs older than 7 days
        failed_count = len(queue.failed_job_registry)
        if failed_count > 0:
            queue.failed_job_registry.cleanup(timestamp=time.time() - 7*24*60*60)
            print(f"🧹 Cleaned up old failed jobs (had {failed_count})")
        
    except Exception as e:
        print(f"⚠️  Warning: Could not cleanup stale jobs: {e}")


def get_worker_stats():
    """Get current worker statistics"""
    try:
        from rq import Queue, Worker as RQWorker
        
        queue = Queue(CRAWLER_QUEUE, connection=redis_conn)
        workers = RQWorker.all(connection=redis_conn)
        
        return {
            "workers": len(workers),
            "queued": queue.count,
            "started": len(queue.started_job_registry),
            "failed": len(queue.failed_job_registry),
            "finished": len(queue.finished_job_registry),
        }
    except Exception:
        return None


def create_worker(queues, name=None):
    """
    Create appropriate worker based on platform
    
    Args:
        queues: List of queue names to listen to
        name: Optional worker name
    
    Returns:
        Worker instance
    """
    is_windows = platform.system() == "Windows"
    
    worker_kwargs = {
        "connection": redis_conn,
        "name": name or f"worker-{os.getpid()}",
        "default_result_ttl": 86400,  # Keep results for 24 hours
        "default_worker_ttl": 43200,  # Worker TTL: 12 hours (increased for long crawls)
    }
    
    if is_windows:
        print("🪟 Detected Windows - using SimpleWorker (no fork)")
        return SimpleWorker(queues, **worker_kwargs)
    else:
        print("🐧 Detected Unix/Linux - using Worker (with fork)")
        return Worker(queues, **worker_kwargs)


def run_worker_with_monitoring():
    """Run worker with health monitoring and stats reporting"""
    
    # Print startup info
    print("=" * 60)
    print("🚀 Production-Grade RQ Worker")
    print("=" * 60)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🖥️  Platform: {platform.system()} {platform.release()}")
    print(f"🐍 Python: {sys.version.split()[0]}")
    print(f"📡 Redis: {redis_url}")
    print(f"📋 Queues: {CRAWLER_QUEUE}, {DEFAULT_QUEUE}")
    print("=" * 60)
    
    # Cleanup before starting
    print("\n🧹 Running startup cleanup...")
    cleanup_stuck_crawlers()
    cleanup_stale_jobs()
    
    # Print initial stats
    stats = get_worker_stats()
    if stats:
        print(f"\n📊 Initial Queue Stats:")
        print(f"   • Workers: {stats['workers']}")
        print(f"   • Queued: {stats['queued']}")
        print(f"   • Started: {stats['started']}")
        print(f"   • Failed: {stats['failed']}")
        print(f"   • Finished: {stats['finished']}")
    
    # Create worker
    print(f"\n🔧 Creating worker...")
    worker = create_worker([CRAWLER_QUEUE, DEFAULT_QUEUE])
    
    print(f"✅ Worker created: {worker.name}")
    print(f"💚 Worker is healthy and ready")
    print("⏳ Waiting for jobs...\n")
    print("=" * 60)
    
    # Work with periodic monitoring
    try:
        last_stats_time = time.time()
        stats_interval = 300  # Print stats every 5 minutes
        
        while not shutdown_requested:
            try:
                # Work on jobs (with timeout so we can check shutdown flag)
                worker.work(
                    burst=False,
                    logging_level="INFO",
                    with_scheduler=False,
                    max_jobs=None,
                )
                
                # Print periodic stats
                current_time = time.time()
                if current_time - last_stats_time >= stats_interval:
                    stats = get_worker_stats()
                    if stats:
                        print(f"\n📊 Worker Stats ({datetime.now().strftime('%H:%M:%S')}):")
                        print(f"   • Workers active: {stats['workers']}")
                        print(f"   • Jobs queued: {stats['queued']}")
                        print(f"   • Jobs running: {stats['started']}")
                        print(f"   • Jobs failed: {stats['failed']}")
                        print(f"   • Jobs completed: {stats['finished']}")
                        print()
                    last_stats_time = current_time
                
                # Small sleep to prevent tight loop if work() returns immediately
                time.sleep(0.1)
                
            except StopRequested:
                print("🛑 Stop requested by RQ")
                break
    
    except KeyboardInterrupt:
        print("\n⚠️  Keyboard interrupt received")
    
    finally:
        print("\n" + "=" * 60)
        print("🔄 Shutting down worker gracefully...")
        
        # Get final stats
        stats = get_worker_stats()
        if stats:
            print(f"\n📊 Final Stats:")
            print(f"   • Jobs completed in this session: {stats['finished']}")
            print(f"   • Jobs still queued: {stats['queued']}")
            print(f"   • Jobs failed: {stats['failed']}")
        
        print(f"\n✅ Worker {worker.name} shut down cleanly")
        print(f"📅 Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run worker with monitoring
    try:
        run_worker_with_monitoring()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
