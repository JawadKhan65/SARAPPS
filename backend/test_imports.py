"""
Test script to verify all imports work correctly after reorganization
"""

print("Testing imports...")

try:
    print("\n1. Testing core imports...")
    from core.config.config import config
    from core.extensions import db, jwt, mail
    from core.models import User, AdminUser, SoleImage, Crawler

    print("   ✅ Core imports successful")
except Exception as e:
    print(f"   ❌ Core imports failed: {e}")

try:
    print("\n2. Testing routes imports...")
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.user import user_bp
    from routes.crawlers import crawlers_bp

    print("   ✅ Routes imports successful")
except Exception as e:
    print(f"   ❌ Routes imports failed: {e}")

try:
    print("\n3. Testing services imports...")
    from services.scraper_service import ScraperService
    from services.scraper_manager import ScraperManager, get_scraper_manager

    print("   ✅ Services imports successful")
except Exception as e:
    print(f"   ❌ Services imports failed: {e}")

try:
    print("\n4. Testing jobs imports...")
    from jobs.tasks import run_crawler_job, get_crawler_job_status
    from jobs.worker import Worker

    print("   ✅ Jobs imports successful")
except Exception as e:
    print(f"   ❌ Jobs imports failed: {e}")

try:
    print("\n5. Testing app creation...")
    from app import create_app

    app = create_app()
    print("   ✅ App creation successful")
except Exception as e:
    print(f"   ❌ App creation failed: {e}")

print("\n" + "=" * 50)
print("✅ All import tests completed!")
print("=" * 50)
