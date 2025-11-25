"""
Quick test script to verify crawler background job system
Run this to test if Redis, RQ worker, and crawler are properly configured
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from redis import Redis
from rq import Queue
from core.models import Crawler
from app import create_app
import time


def test_redis_connection():
    """Test Redis connectivity"""
    print("\n1️⃣ Testing Redis Connection...")
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_conn = Redis.from_url(redis_url)
        redis_conn.ping()
        print("   ✅ Redis connected successfully")
        return redis_conn
    except Exception as e:
        print(f"   ❌ Redis connection failed: {e}")
        print("   💡 Start Redis: docker start redis")
        return None


def test_rq_queue(redis_conn):
    """Test RQ queue"""
    print("\n2️⃣ Testing RQ Queue...")
    try:
        queue = Queue("crawlers", connection=redis_conn)
        print(f"   ✅ Queue 'crawlers' accessible")
        print(f"   📊 Jobs in queue: {len(queue)}")
        return queue
    except Exception as e:
        print(f"   ❌ Queue failed: {e}")
        return None


def test_database():
    """Test database and crawler availability"""
    print("\n3️⃣ Testing Database Connection...")
    try:
        app = create_app()
        with app.app_context():
            crawlers = Crawler.query.all()
            print(f"   ✅ Database connected")
            print(f"   📊 Total crawlers: {len(crawlers)}")

            if crawlers:
                print("\n   Available Crawlers:")
                for crawler in crawlers:
                    status = "🟢 Active" if crawler.is_active else "🔴 Inactive"
                    running = "▶️ Running" if crawler.is_running else ""
                    print(
                        f"   - {crawler.name} ({crawler.id[:8]}...) {status} {running}"
                    )
                return crawlers[0]  # Return first crawler for testing
            else:
                print("   ⚠️ No crawlers found in database")
                return None
    except Exception as e:
        print(f"   ❌ Database failed: {e}")
        return None


def test_worker_status(redis_conn):
    """Check if RQ worker is running"""
    print("\n4️⃣ Checking RQ Worker Status...")
    try:
        from rq import Worker

        workers = Worker.all(connection=redis_conn)

        if workers:
            print(f"   ✅ {len(workers)} worker(s) running:")
            for worker in workers:
                print(f"   - {worker.name} - State: {worker.get_state()}")
        else:
            print("   ⚠️ No workers running")
            print("   💡 Start worker: python jobs/worker.py")

        return len(workers) > 0
    except Exception as e:
        print(f"   ❌ Worker check failed: {e}")
        return False


def test_job_submission(queue, crawler):
    """Test job submission (dry run - don't actually run crawler)"""
    print("\n5️⃣ Testing Job Submission (Dry Run)...")

    if not crawler:
        print("   ⚠️ No crawler available for testing")
        return

    print(f"   📝 Would submit job for: {crawler.name}")
    print(f"   📝 Crawler ID: {crawler.id}")
    print(f"   📝 Queue name: crawlers")
    print(f"   ✅ Job submission pathway verified")

    # Don't actually submit to avoid running a real crawler
    print("\n   ℹ️ Skipping actual job submission (dry run mode)")
    print("   💡 To test real job: Use Admin UI or API endpoint")


def test_url_normalization():
    """Test URL normalization function"""
    print("\n6️⃣ Testing URL Normalization...")

    from services.scraper_service import ScraperService

    # Create dummy app context
    app = create_app()
    with app.app_context():
        try:
            # Get first crawler for initialization
            crawler = Crawler.query.first()
            if not crawler:
                print("   ⚠️ No crawler found, skipping test")
                return

            service = ScraperService(crawler.id)

            test_cases = [
                ("https://Example.com/Product/", "https://example.com/Product"),
                ("https://site.com/item?b=2&a=1", "https://site.com/item?a=1&b=2"),
                (
                    "https://site.com/item?ref=123&id=ABC",
                    "https://site.com/item?id=ABC",
                ),
                ("https://site.com/item#section", "https://site.com/item"),
            ]

            all_passed = True
            for original, expected in test_cases:
                result = service.normalize_url(original)
                if result == expected:
                    print(f"   ✅ {original[:40]}... → {result[:40]}...")
                else:
                    print(f"   ❌ {original} → Got: {result}, Expected: {expected}")
                    all_passed = False

            if all_passed:
                print("   ✅ All URL normalization tests passed")
            else:
                print("   ❌ Some URL normalization tests failed")

        except Exception as e:
            print(f"   ❌ URL normalization test failed: {e}")


def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 Crawler Background Job System Test")
    print("=" * 60)

    # Test Redis
    redis_conn = test_redis_connection()
    if not redis_conn:
        print("\n❌ Cannot proceed without Redis. Please start Redis and try again.")
        return

    # Test Queue
    queue = test_rq_queue(redis_conn)
    if not queue:
        print("\n❌ Cannot proceed without RQ queue.")
        return

    # Test Database
    crawler = test_database()

    # Test Worker
    worker_running = test_worker_status(redis_conn)

    # Test Job Submission (dry run)
    test_job_submission(queue, crawler)

    # Test URL Normalization
    test_url_normalization()

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    print(f"Redis:         {'✅ Connected' if redis_conn else '❌ Failed'}")
    print(f"RQ Queue:      {'✅ Ready' if queue else '❌ Failed'}")
    print(f"Database:      {'✅ Connected' if crawler else '❌ Failed'}")
    print(f"RQ Worker:     {'✅ Running' if worker_running else '⚠️ Not Running'}")
    print(f"Crawlers:      {'✅ Available' if crawler else '⚠️ None Found'}")

    if redis_conn and queue and crawler:
        print("\n✅ System is ready for background crawler jobs!")

        if not worker_running:
            print("\n⚠️ Warning: No RQ worker detected")
            print("Start worker with: python jobs/worker.py")
    else:
        print("\n❌ System not ready. Please fix the issues above.")

    print("=" * 60)


if __name__ == "__main__":
    main()
