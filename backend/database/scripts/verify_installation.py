#!/usr/bin/env python3
"""
STIP Backend - Installation and Verification Script
Checks dependencies and sets up the Flask application
"""

import sys
import os
import subprocess
from pathlib import Path


def check_python_version():
    """Check if Python version is 3.8 or higher"""
    print("=" * 60)
    print("Checking Python Version...")
    print("=" * 60)

    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"❌ Python 3.8+ required (you have {version.major}.{version.minor})")
        return False

    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_virtual_env():
    """Check if running in virtual environment"""
    print("\n" + "=" * 60)
    print("Checking Virtual Environment...")
    print("=" * 60)

    in_venv = hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )

    if in_venv:
        print(f"✅ Virtual environment detected: {sys.prefix}")
    else:
        print("⚠️  Not in virtual environment. Recommended to use venv.")

    return in_venv


def check_postgres():
    """Check if PostgreSQL is accessible"""
    print("\n" + "=" * 60)
    print("Checking PostgreSQL...")
    print("=" * 60)

    try:
        import psycopg2

        print("✅ psycopg2 installed (PostgreSQL driver)")
        return True
    except ImportError:
        print("❌ psycopg2 not found. Install with: pip install psycopg2-binary")
        return False


def install_requirements():
    """Install dependencies from requirements.txt"""
    print("\n" + "=" * 60)
    print("Installing Requirements...")
    print("=" * 60)

    requirements_file = Path(__file__).parent / "requirements.txt"

    if not requirements_file.exists():
        print(f"❌ requirements.txt not found at {requirements_file}")
        return False

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)]
        )
        print("✅ All requirements installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install requirements: {e}")
        return False


def check_imports():
    """Verify critical imports"""
    print("\n" + "=" * 60)
    print("Verifying Imports...")
    print("=" * 60)

    critical_modules = [
        ("flask", "Flask"),
        ("flask_sqlalchemy", "SQLAlchemy"),
        ("flask_jwt_extended", "JWT"),
        ("flask_cors", "CORS"),
        ("flask_mail", "Mail"),
        ("PIL", "Pillow"),
        ("cv2", "OpenCV"),
        ("numpy", "NumPy"),
        ("torch", "PyTorch"),
        ("transformers", "Transformers"),
    ]

    all_ok = True
    for module, name in critical_modules:
        try:
            __import__(module)
            print(f"✅ {name}")
        except ImportError:
            print(f"❌ {name} (import '{module}')")
            all_ok = False

    return all_ok


def check_environment_file():
    """Check if .env file exists"""
    print("\n" + "=" * 60)
    print("Checking Environment Configuration...")
    print("=" * 60)

    env_file = Path(__file__).parent / ".env"

    if env_file.exists():
        print(f"✅ .env file found at {env_file}")
        return True
    else:
        print(f"⚠️  .env file not found at {env_file}")
        print("   Create .env file with necessary variables (see QUICKSTART.md)")
        return False


def check_logs_directory():
    """Create logs directory if needed"""
    print("\n" + "=" * 60)
    print("Checking Log Directory...")
    print("=" * 60)

    logs_dir = Path(__file__).parent / "logs"

    try:
        logs_dir.mkdir(exist_ok=True)
        print(f"✅ Logs directory: {logs_dir}")
        return True
    except Exception as e:
        print(f"❌ Failed to create logs directory: {e}")
        return False


def check_app_structure():
    """Verify Flask app structure"""
    print("\n" + "=" * 60)
    print("Checking Application Structure...")
    print("=" * 60)

    required_files = [
        "app.py",
        "config.py",
        "extensions.py",
        "models.py",
        "requirements.txt",
    ]

    required_dirs = [
        "routes",
        "services",
    ]

    base_path = Path(__file__).parent
    all_ok = True

    for filename in required_files:
        path = base_path / filename
        if path.exists():
            print(f"✅ {filename}")
        else:
            print(f"❌ {filename}")
            all_ok = False

    for dirname in required_dirs:
        path = base_path / dirname
        if path.is_dir():
            print(f"✅ {dirname}/")
        else:
            print(f"❌ {dirname}/")
            all_ok = False

    return all_ok


def test_app_import():
    """Test if Flask app can be imported"""
    print("\n" + "=" * 60)
    print("Testing Application Import...")
    print("=" * 60)

    try:
        from app import create_app

        print("✅ Flask app can be imported")
        return True
    except ImportError as e:
        print(f"❌ Failed to import app: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Warning during import: {e}")
        return False


def print_summary(results):
    """Print summary of checks"""
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    checks = [
        ("Python Version", results[0]),
        ("Virtual Environment", results[1]),
        ("PostgreSQL Driver", results[2]),
        ("Requirements Installed", results[3]),
        ("Critical Imports", results[4]),
        ("Environment File", results[5]),
        ("Logs Directory", results[6]),
        ("App Structure", results[7]),
        ("App Import", results[8]),
    ]

    passed = sum(1 for _, result in checks if result)
    total = len(checks)

    for check_name, result in checks:
        status = "✅" if result else "❌"
        print(f"{status} {check_name}")

    print(f"\nResult: {passed}/{total} checks passed")

    if passed == total:
        print("\n🎉 All checks passed! Ready to run the application.")
        print("\nNext steps:")
        print("1. Configure .env file with database and SMTP settings")
        print("2. Create PostgreSQL database and run migrations")
        print("3. Run: flask run --host=0.0.0.0 --port=5000")
        return True
    else:
        print("\n⚠️  Some checks failed. Please fix the issues above.")
        return False


def main():
    """Run all checks"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  STIP Backend - Installation & Verification".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")

    results = [
        check_python_version(),
        check_virtual_env(),
        check_postgres(),
        install_requirements(),
        check_imports(),
        check_environment_file(),
        check_logs_directory(),
        check_app_structure(),
        test_app_import(),
    ]

    success = print_summary(results)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
