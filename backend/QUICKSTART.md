# Quick Start Guide - Backend

## Prerequisites
- Python 3.11+
- PostgreSQL 15
- Redis 7 (Docker)
- Virtual environment activated

## Setup

### 1. Install Dependencies
```powershell
cd "d:\advanced print match system\backend"
pip install -r requirements.txt
```

### 2. Configure Environment
Create `.env` file with:
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/stip
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-secret-key
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
```

### 3. Initialize Database
```powershell
python database/scripts/init_db.py
```

### 4. Run Migrations (if needed)
```powershell
python database/migrations/add_reset_token_fields.py
```

## Running the Application

### Option 1: Flask App Only (No Background Jobs)
```powershell
python app.py
```
Server runs on: http://localhost:5000

### Option 2: Flask App + Background Worker (Recommended)

**Terminal 1 - Flask App:**
```powershell
cd "d:\advanced print match system\backend"
python app.py
```

**Terminal 2 - RQ Worker:**
```powershell
cd "d:\advanced print match system\backend"
python jobs/worker.py
```

### Option 3: Using Docker Compose
```powershell
docker-compose up
```

## Testing Imports
```powershell
python test_imports.py
```

## Common Commands

### Database Operations
```powershell
# Initialize database
python database/scripts/init_db.py

# Reset database
python database/scripts/reset_database.ps1

# Verify installation
python database/scripts/verify_installation.py
```

### Worker Operations
```powershell
# Start worker (single)
python jobs/worker.py

# Start multiple workers
python jobs/worker.py --workers 2

# Monitor jobs (Redis CLI)
docker exec -it stip_redis redis-cli
> LLEN rq:queue:crawlers
> KEYS rq:*
```

### Crawler Operations
```powershell
# Check running crawlers
curl http://localhost:5000/api/admin/crawlers

# Start a crawler (via API)
curl -X POST http://localhost:5000/api/admin/crawlers/{id}/start \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Project Structure

```
backend/
├── app.py                 # Main entry point - START HERE
├── test_imports.py        # Test all imports work
│
├── core/                  # Core modules
│   ├── models.py         # Database models
│   ├── extensions.py     # Flask extensions
│   └── config/
│       ├── config.py     # Configuration
│       └── firebase_config.py
│
├── routes/               # API endpoints
├── services/             # Business logic
├── jobs/                 # Background tasks
│   ├── tasks.py         # Job definitions
│   └── worker.py        # Worker process - RUN IN SEPARATE TERMINAL
│
├── database/            # Database management
│   ├── migrations/      # Schema migrations
│   └── scripts/         # DB scripts
│
└── [other folders...]
```

## Troubleshooting

### Import Errors
If you see `ModuleNotFoundError`:
1. Make sure you're in the backend directory
2. Virtual environment is activated
3. Run: `python test_imports.py` to diagnose

### Database Connection Issues
```powershell
# Check PostgreSQL is running
Get-Service postgresql*

# Test connection
psql -U postgres -d stip
```

### Redis Connection Issues
```powershell
# Check Redis container
docker ps | findstr redis

# Test Redis connection
docker exec stip_redis redis-cli ping
# Should return: PONG
```

### Worker Not Processing Jobs
1. Check Redis is running
2. Check worker is running: `python jobs/worker.py`
3. Check queue: `docker exec stip_redis redis-cli LLEN rq:queue:crawlers`

## API Endpoints

### Health Check
```
GET /api/health
```

### Authentication
```
POST /api/auth/register
POST /api/auth/login
POST /api/auth/verify-otp
POST /api/auth/forgot-password
POST /api/auth/verify-reset-otp
POST /api/auth/reset-password
```

### Admin
```
POST /api/admin/login
GET /api/admin/statistics
GET /api/admin/crawlers
POST /api/admin/crawlers/{id}/start
```

### User
```
GET /api/user/profile
POST /api/user/upload-image
POST /api/user/match-image/{id}
GET /api/user/matches
```

## Development Tips

1. **Keep both terminals open** when developing with background jobs
2. **Check logs** in `logs/` directory for errors
3. **Use Redis CLI** to monitor job queues
4. **Run migrations** after database schema changes
5. **Test imports** after moving files: `python test_imports.py`

## Production Deployment

See `docs/BACKGROUND_JOBS_SETUP.md` for production setup with:
- Supervisor (worker management)
- Nginx (reverse proxy)
- Gunicorn (WSGI server)
- Systemd (service management)
