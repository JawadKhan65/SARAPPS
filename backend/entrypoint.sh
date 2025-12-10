#!/bin/bash
set -e

echo "🚀 Starting backend container..."

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL..."
until python -c "import psycopg2; psycopg2.connect('$DATABASE_URL')" 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "✅ PostgreSQL is ready!"

# Initialize database
echo "🔧 Initializing database..."
python scripts/init_db.py init || echo "⚠️  Database already initialized"

# Start the application
echo "🚀 Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:5000 \
    --workers 4 \
    --worker-class sync \
    --timeout 1500 \
    --access-logfile - \
    --error-logfile - \
    app:app

