# STIP - Sole Track & Identification Platform

**Professional shoe sole image matching system with web scraping, vector similarity search, and admin management.**

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Repository Structure](#repository-structure)
4. [Prerequisites](#prerequisites)
5. [Installation & Setup](#installation--setup)
6. [Docker Operations Reference](#docker-operations-reference)
7. [Database Operations](#database-operations)
8. [Deployment Guide](#deployment-guide)
9. [User Guides](#user-guides)
10. [Development Guide](#development-guide)
11. [Troubleshooting](#troubleshooting)
12. [API Reference](#api-reference)

---

## 🎯 Project Overview

STIP is an advanced shoe sole matching system that:
- **Scrapes** shoe sole images from major retailers (Zalando, Amazon, Clarks, etc.)
- **Processes** images using computer vision (Edge detection, LBP textures, CLIP embeddings)
- **Matches** uploaded images against 1000+ database images using pgvector similarity search
- **Manages** crawlers, users, and statistics via admin dashboard

### Key Features

✅ **Multi-Retailer Scraping** - 15+ scrapers with anti-bot protection  
✅ **Fast Vector Search** - Sub-second matching using PostgreSQL pgvector  
✅ **Professional Matching** - Edge (60%) + Texture (40%) + Optional CLIP (512-dim)  
✅ **Admin Dashboard** - User management, crawler control, statistics  
✅ **Production Ready** - Two-server deployment with HTTPS/SSL  
✅ **Background Jobs** - RQ (Redis Queue) worker for long-running tasks  

---

## 🏗️ System Architecture

### Two-Server Production Setup

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend Server (stip-frontend01 / 95.142.102.147)        │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌────────┐  ┌────────────────────┐          │
│  │  Nginx   │◄─┤  SSL   │  │  Node.js Services  │          │
│  │  :80/443 │  │  Cert  │  │  ┌──────────────┐  │          │
│  └────┬─────┘  └────────┘  │  │  Frontend    │  │          │
│       │                     │  │  (Next.js)   │  │          │
│       ├─────────────────────►  │  :3000       │  │          │
│       │                     │  └──────────────┘  │          │
│       │                     │  ┌──────────────┐  │          │
│       └─────────────────────►  │  Admin       │  │          │
│                             │  │  (Next.js)   │  │          │
│                             │  │  :3001       │  │          │
│                             │  └──────────────┘  │          │
│                             └────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/HTTPS
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend Server (stip-backend01 / 95.142.102.138)          │
├─────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  PostgreSQL    │  │  Redis       │  │  Flask API     │  │
│  │  +pgvector     │  │  (Cache+RQ)  │  │  (Gunicorn)    │  │
│  │  :5432         │  │  :6379       │  │  :5000         │  │
│  └────────────────┘  └──────────────┘  └────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  RQ Worker (Background Jobs)                           │ │
│  │  - Crawlers (Playwright)                               │ │
│  │  - Image processing                                    │ │
│  │  - Vector embedding generation                         │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

#### Backend
- **Framework**: Flask (Python 3.11)
- **Database**: PostgreSQL 17 + pgvector 0.8.1
- **Cache/Queue**: Redis 7
- **Web Server**: Gunicorn (4 workers, 300s timeout)
- **Background Jobs**: RQ (Redis Queue)
- **Scraping**: Playwright (headless browser)
- **ML/Vision**: OpenCV, scikit-image, PyTorch, CLIP

#### Frontend
- **Framework**: Next.js 14 (React)
- **Styling**: Tailwind CSS
- **State**: Context API
- **Auth**: Firebase Auth + JWT

#### Infrastructure
- **Reverse Proxy**: Nginx
- **SSL**: Let's Encrypt / Custom Certificate
- **Containerization**: Docker + Docker Compose
- **OS**: Ubuntu 24.04 LTS

---

## 📁 Repository Structure

```
stip/
├── backend/                      # Flask API backend
│   ├── app.py                   # Main Flask application
│   ├── requirements.txt         # Python dependencies
│   ├── Dockerfile               # Backend container
│   ├── entrypoint.sh            # Container startup script
│   │
│   ├── core/                    # Core application modules
│   │   ├── models.py            # SQLAlchemy ORM models
│   │   ├── extensions.py        # Flask extensions (DB, JWT, etc.)
│   │   └── config/              # Configuration files
│   │       ├── config.py        # Main config (DB, Redis, thresholds)
│   │       ├── scraper_config.py  # Scraper-specific settings
│   │       └── __init__.py
│   │
│   ├── routes/                  # API endpoints
│   │   ├── auth.py              # Authentication (login, register, MFA)
│   │   ├── user.py              # User operations (upload, match)
│   │   ├── admin.py             # Admin operations (users, groups)
│   │   ├── crawlers.py          # Crawler management
│   │   ├── database.py          # Database health checks
│   │   ├── images.py            # Image operations
│   │   └── matches.py           # Re-matching operations
│   │
│   ├── services/                # Business logic
│   │   ├── image_processor.py   # Image feature extraction (CLIP, Edge, LBP)
│   │   ├── scraper_service.py   # Scraper operations & duplicate detection
│   │   ├── scraper_manager.py   # Batch processing & uniqueness checks
│   │   └── crawler_scheduler.py # Scheduled crawler runs
│   │
│   ├── scrapers/                # Website-specific scrapers
│   │   ├── zalando_playwright.py  # Zalando.nl scraper
│   │   ├── amazon.py            # Amazon scraper
│   │   ├── clarks.py            # Clarks scraper
│   │   ├── bergfreunde.py       # Bergfreunde scraper
│   │   ├── decathlon.py         # Decathlon scraper
│   │   └── [15+ more scrapers]
│   │
│   ├── jobs/                    # Background job system
│   │   ├── worker.py            # RQ worker configuration
│   │   └── tasks.py             # Job definitions (run_crawler_job)
│   │
│   ├── scripts/                 # Utility scripts
│   │   ├── init_db.py           # Database initialization
│   │   ├── backfill_vectors.py  # Populate vector embeddings
│   │   └── test_crawler_system.py  # Test crawlers
│   │
│   ├── ml_models/               # Machine learning models
│   │   ├── clip_model.py        # CLIP sole detector
│   │   └── shoe_sole_classifier_full.pth
│   │
│   ├── line_tracing_utils/      # Line tracing algorithms
│   │   └── line_tracing.py      # Shoeprint comparison
│   │
│   └── templates/               # Email templates
│
├── frontend/                    # User-facing Next.js app
│   ├── app/                     # Next.js 14 App Router
│   │   ├── page.jsx             # Home/landing page
│   │   ├── login/               # User login
│   │   ├── register/            # User registration
│   │   ├── dashboard/           # Main user dashboard (upload & match)
│   │   └── layout.jsx           # Root layout
│   │
│   ├── components/              # React components
│   │   ├── Header.jsx           # User header
│   │   ├── MatchResults.jsx     # Match display
│   │   └── ui/                  # Reusable UI components
│   │
│   ├── lib/                     # Utility libraries
│   │   ├── api.js               # API client
│   │   ├── firebase.js          # Firebase config
│   │   └── store.js             # State management
│   │
│   ├── Dockerfile               # Frontend container
│   ├── package.json             # Node.js dependencies
│   └── next.config.ts           # Next.js configuration
│
├── admin/                       # Admin dashboard (Next.js)
│   ├── app/                     # Next.js 14 App Router
│   │   ├── page.jsx             # Admin home
│   │   ├── login/               # Admin login
│   │   ├── users/               # User management
│   │   ├── groups/              # Group management
│   │   ├── crawlers/            # Crawler control
│   │   └── statistics/          # System statistics
│   │
│   ├── components/              # Admin components
│   │   ├── AdminHeader.jsx      # Admin navigation
│   │   └── ui/                  # Reusable UI components
│   │
│   ├── lib/                     # Admin utilities
│   │   └── api.js               # Admin API client
│   │
│   ├── Dockerfile               # Admin container
│   └── package.json             # Node.js dependencies
│
├── docker-compose.yml           # All-in-one Docker Compose
├── nginx.conf                   # Nginx configuration
│
├── deploy-backend.sh            # Backend deployment script
├── deploy-frontend.sh           # Frontend deployment script
├── deploy-single-server.sh      # Single server deployment
│
├── PRODUCTION_DEPLOYMENT_GUIDE.md  # Detailed deployment guide
├── QUICK_START_GUIDE.md         # Quick start instructions
├── FIX_MEMORY_CRASH.md          # Memory troubleshooting
├── ZALANDO_SCRAPER_PROFESSIONAL_GUIDE.md  # Zalando-specific guide
│
└── README.md                    # This file
```

---

## 🔧 Prerequisites

### Required Software

- **Docker**: 20.10+ (with Docker Compose)
- **Git**: 2.30+
- **Linux**: Ubuntu 24.04 LTS (or similar Debian-based distro)
- **SSH Access**: To production servers

### Required Credentials

1. **PostgreSQL Password** (`DB_PASSWORD`)
2. **JWT Secret Keys** (`SECRET_KEY`, `JWT_SECRET_KEY`)
3. **Firebase Admin SDK** (optional, for push notifications)
4. **Proxy Credentials** (optional, for Decodo/residential proxies)
5. **SSL Certificate** (for HTTPS)

### System Requirements

#### Backend Server
- **CPU**: 4+ cores
- **RAM**: 8GB+ (16GB recommended for large crawls)
- **Disk**: 100GB+ SSD
- **Network**: 100Mbps+ (for fast scraping)

#### Frontend Server
- **CPU**: 2+ cores
- **RAM**: 4GB+
- **Disk**: 50GB+ SSD
- **Network**: 100Mbps+

---

## 🚀 Installation & Setup

### Option 1: Single Server (Development/Testing)

```bash
# 1. Clone repository
cd /opt
sudo mkdir -p sarapps
sudo chown $USER:$USER sarapps
cd sarapps
git clone <your-repo-url> .

# 2. Create environment file
cp env.production.template .env.production

# 3. Edit environment variables
nano .env.production
# Set DB_PASSWORD, SECRET_KEY, JWT_SECRET_KEY

# 4. Start all services
docker-compose up -d

# 5. Initialize database
docker exec -it stip_backend python scripts/init_db.py init

# 6. Access application
# Frontend: http://localhost:3000
# Admin: http://localhost:3001
# API: http://localhost:5000
```

### Option 2: Two-Server Production (Recommended)

See [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md) for detailed instructions.

**Quick Summary:**

#### Backend Server (95.142.102.138)
```bash
ssh root@95.142.102.138
cd /opt/sarapps
git clone <repo> .
cp env.production.template .env.production
nano .env.production  # Set passwords/secrets
docker-compose up -d postgres redis backend worker
docker exec -it stip_backend python scripts/init_db.py init
```

#### Frontend Server (95.142.102.147)
```bash
ssh root@95.142.102.147
cd /opt/sarapps
git clone <repo> .
# Copy SSL certificates to /etc/nginx/ssl/
docker-compose up -d frontend admin nginx
```

---

## 🐳 Docker Operations Reference

### PostgreSQL Operations

#### Basic Commands
```bash
# Start PostgreSQL container
docker-compose up -d postgres

# Stop PostgreSQL
docker-compose stop postgres

# View logs
docker logs stip_postgres
docker logs stip_postgres --tail 100 -f  # Follow last 100 lines

# Restart PostgreSQL
docker-compose restart postgres

# Check health
docker inspect stip_postgres | grep -A 10 Health
```

#### Database Access
```bash
# Access PostgreSQL CLI
docker exec -it stip_postgres psql -U stip_user -d stip_production

# Execute SQL from command line
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "SELECT COUNT(*) FROM sole_images;"

# Dump database (backup)
docker exec -it stip_postgres pg_dump -U stip_user stip_production > backup_$(date +%Y%m%d).sql

# Restore database
docker exec -i stip_postgres psql -U stip_user stip_production < backup_20250101.sql

# Check database size
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "SELECT pg_size_pretty(pg_database_size('stip_production'));"
```

#### Performance Monitoring
```bash
# Active connections
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "SELECT count(*) FROM pg_stat_activity;"

# Long-running queries
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC;"

# Database statistics
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "SELECT schemaname, tablename, n_live_tup, n_dead_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"
```

### Redis Operations

#### Basic Commands
```bash
# Start Redis
docker-compose up -d redis

# Stop Redis
docker-compose stop redis

# View logs
docker logs stip_redis --tail 100 -f

# Restart Redis
docker-compose restart redis
```

#### Redis CLI Access
```bash
# Access Redis CLI
docker exec -it stip_redis redis-cli

# Check Redis status
docker exec -it stip_redis redis-cli INFO

# Monitor Redis commands in real-time
docker exec -it stip_redis redis-cli MONITOR

# Get all keys
docker exec -it stip_redis redis-cli KEYS '*'

# Check RQ queues
docker exec -it stip_redis redis-cli LLEN rq:queue:default

# Flush all data (WARNING: Deletes everything!)
docker exec -it stip_redis redis-cli FLUSHALL
```

#### RQ Job Management
```bash
# List failed jobs
docker exec -it stip_redis redis-cli LRANGE rq:queue:failed 0 -1

# Clear failed jobs
docker exec -it stip_redis redis-cli DEL rq:queue:failed

# Check worker status
docker exec -it stip_worker python -c "from jobs.worker import get_worker_stats; print(get_worker_stats())"
```

### Backend Operations

#### Basic Commands
```bash
# Start backend
docker-compose up -d backend

# Stop backend
docker-compose stop backend

# Restart backend
docker-compose restart backend

# View logs
docker logs stip_backend --tail 200 -f

# Rebuild backend after code changes
docker-compose build --no-cache backend
docker-compose up -d backend
```

#### Execute Python Scripts
```bash
# Initialize database
docker exec -it stip_backend python scripts/init_db.py init

# Backfill vector embeddings
docker exec -it stip_backend python scripts/backfill_vectors.py --batch-size 50

# Test crawler system
docker exec -it stip_backend python scripts/test_crawler_system.py

# Create admin user
docker exec -it stip_backend python scripts/init_db.py create-admin \
  --email admin@example.com \
  --password SecurePassword123! \
  --username admin
```

#### Backend Shell Access
```bash
# Enter container shell
docker exec -it stip_backend /bin/bash

# Python interactive shell with app context
docker exec -it stip_backend python
>>> from app import create_app, db
>>> from core.models import User, SoleImage
>>> app = create_app()
>>> with app.app_context():
...     users = User.query.all()
...     print(f"Total users: {len(users)}")
```

#### Update Backend Code
```bash
# On production server
cd /opt/sarapps
git stash  # Save local changes
git pull origin main
docker-compose build --no-cache backend
docker-compose up -d backend
docker logs stip_backend --tail 50 -f  # Verify startup
```

### Worker Operations

#### Basic Commands
```bash
# Start worker
docker-compose up -d worker

# Stop worker
docker-compose stop worker

# Restart worker
docker-compose restart worker

# View worker logs (shows crawler progress)
docker logs stip_worker --tail 500 -f

# Rebuild worker
docker-compose build --no-cache worker
docker-compose up -d worker
```

#### Monitor Worker Jobs
```bash
# Check current jobs
docker exec -it stip_redis redis-cli KEYS 'rq:job:*' | wc -l

# View job details
docker exec -it stip_redis redis-cli HGETALL rq:job:<job_id>

# Check worker TTL
docker exec -it stip_worker python -c "from jobs.worker import get_worker_stats; print(get_worker_stats())"
```

### Frontend Operations

#### Basic Commands
```bash
# Start frontend
docker-compose up -d frontend

# Stop frontend
docker-compose stop frontend

# Restart frontend
docker-compose restart frontend

# View logs
docker logs stip_frontend --tail 100 -f

# Rebuild frontend
docker-compose build --no-cache --pull frontend
docker-compose up -d frontend
```

#### Update Frontend Code
```bash
# On frontend server
cd /opt/sarapps
git stash
git pull origin main
docker-compose -f docker-compose.frontend.yml build --no-cache --pull frontend
docker-compose -f docker-compose.frontend.yml up -d frontend
docker logs stip_frontend --tail 50 -f
```

#### Check for Malware/Compromised Container
```bash
# Monitor container behavior
docker logs stip_frontend --tail 100 -f | grep -iE 'download|wget|curl|http|malware|virus'

# Check network connections
docker exec -it stip_frontend netstat -tulnp

# Stop and remove compromised container
docker-compose stop frontend
docker-compose rm -f frontend
docker rmi -f $(docker images -q node:20-alpine)  # Remove base image
docker-compose build --no-cache --pull frontend  # Rebuild with clean image
docker-compose up -d frontend
```

### Admin Dashboard Operations

#### Basic Commands
```bash
# Start admin
docker-compose up -d admin

# Stop admin
docker-compose stop admin

# Restart admin
docker-compose restart admin

# View logs
docker logs stip_admin --tail 100 -f

# Rebuild admin
docker-compose build --no-cache admin
docker-compose up -d admin
```

### Nginx Operations

#### Basic Commands
```bash
# Start Nginx (if using Docker)
docker-compose up -d nginx

# Restart Nginx (system service)
sudo systemctl restart nginx

# View logs
docker logs stip_nginx --tail 100 -f
# OR (system service)
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

#### Configuration Management
```bash
# Test Nginx configuration
sudo nginx -t
# OR (Docker)
docker exec stip_nginx nginx -t

# Reload configuration (no downtime)
sudo systemctl reload nginx
# OR (Docker)
docker exec stip_nginx nginx -s reload

# Edit configuration
sudo nano /etc/nginx/sites-available/stip-frontend
# OR (Docker)
nano /opt/sarapps/nginx.conf
```

#### SSL Certificate Management
```bash
# Generate Let's Encrypt certificate
sudo certbot --nginx -d stip.sarapps.com -d www.stip.sarapps.com

# Renew certificate
sudo certbot renew --dry-run  # Test renewal
sudo certbot renew  # Actual renewal

# Check certificate expiry
echo | openssl s_client -servername stip.sarapps.com -connect stip.sarapps.com:443 2>/dev/null | openssl x509 -noout -dates

# Install custom certificate
sudo mkdir -p /etc/nginx/ssl
sudo cp cert.pem /etc/nginx/ssl/cert.pem
sudo cp key.pem /etc/nginx/ssl/key.pem
sudo chmod 600 /etc/nginx/ssl/*.pem
sudo nginx -t && sudo systemctl reload nginx
```

### Multi-Container Operations

#### Start/Stop All Services
```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Stop all (with volume removal - WARNING!)
docker-compose down -v

# Restart all services
docker-compose restart
```

#### View All Container Status
```bash
# List all containers
docker-compose ps

# OR
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# View resource usage
docker stats
```

#### Rebuild Everything
```bash
# Full rebuild (after major changes)
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Check logs for all services
docker-compose logs -f
```

#### Clean Up Docker Resources
```bash
# Remove stopped containers
docker container prune -f

# Remove unused images
docker image prune -a -f

# Remove unused volumes
docker volume prune -f

# Remove unused networks
docker network prune -f

# Full cleanup (WARNING: Removes everything not in use!)
docker system prune -a --volumes -f
```

---

## 🗄️ Database Operations

### Database Schema Overview

#### Main Tables

**`users`** - Frontend users
- `id` (UUID, PK)
- `email`, `firebase_uid`
- `created_at`, `is_active`

**`admin_users`** - Admin dashboard users
- `id` (UUID, PK)
- `username`, `email`, `password_hash`
- `mfa_enabled`, `mfa_secret`
- `is_active`, `created_at`

**`sole_images`** - Scraped shoe images
- `id` (UUID, PK)
- `crawler_id` (FK → crawlers)
- `source_url`, `brand`, `product_type`, `product_name`
- `original_image_data`, `processed_image_data` (BYTEA)
- `image_hash` (for deduplication)
- `feature_vector`, `lbp_histogram` (legacy features)
- **`clip_embedding`** (vector(512)) - CLIP embeddings
- **`edge_embedding`** (vector(256)) - Edge features
- **`texture_embedding`** (vector(128)) - Texture features
- `quality_score`, `image_width`, `image_height`

**`crawlers`** - Crawler configuration
- `id` (UUID, PK)
- `name`, `url`, `scraper_module`
- `is_active`, `schedule`
- `items_scraped`, `last_run_at`

**`crawler_runs`** - Crawler execution history
- `id` (UUID, PK)
- `crawler_id` (FK → crawlers)
- `status` ('running', 'completed', 'failed', 'cancelled')
- `items_scraped`, `started_at`, `completed_at`

**`uploaded_images`** - User-uploaded images
- `id` (UUID, PK)
- `user_id` (FK → users)
- `filename`, `file_path`, `file_size_bytes`
- `features_vector` (vector(512))
- `is_processed`, `processing_status`

### Common Database Queries

#### User Management
```sql
-- List all users
SELECT id, email, created_at, is_active FROM users ORDER BY created_at DESC;

-- Count users
SELECT COUNT(*) FROM users;

-- Activate/deactivate user
UPDATE users SET is_active = true WHERE email = 'user@example.com';
UPDATE users SET is_active = false WHERE id = '<user_id>';

-- Delete user (and their uploads)
DELETE FROM users WHERE id = '<user_id>';
```

#### Admin Management
```sql
-- List all admins
SELECT id, username, email, is_active, mfa_enabled, created_at 
FROM admin_users ORDER BY created_at DESC;

-- Enable MFA for admin
UPDATE admin_users SET mfa_enabled = true WHERE email = 'admin@example.com';

-- Disable admin account
UPDATE admin_users SET is_active = false WHERE username = 'admin';
```

#### Crawler & Images
```sql
-- List all crawlers with stats
SELECT 
    id, name, url, is_active, items_scraped, 
    last_run_at, created_at 
FROM crawlers ORDER BY name;

-- Count scraped images per crawler
SELECT 
    c.name, 
    COUNT(si.id) as image_count 
FROM crawlers c
LEFT JOIN sole_images si ON c.id = si.crawler_id
GROUP BY c.name ORDER BY image_count DESC;

-- Check vector embedding coverage
SELECT 
    COUNT(*) as total_images,
    COUNT(clip_embedding) as images_with_clip,
    COUNT(edge_embedding) as images_with_edge,
    COUNT(texture_embedding) as images_with_texture,
    ROUND(100.0 * COUNT(clip_embedding) / COUNT(*), 2) as clip_coverage_pct,
    ROUND(100.0 * COUNT(edge_embedding) / COUNT(*), 2) as edge_coverage_pct
FROM sole_images;

-- Find images without vectors
SELECT id, brand, product_type, created_at 
FROM sole_images 
WHERE edge_embedding IS NULL OR texture_embedding IS NULL
LIMIT 20;

-- Delete all images from a specific crawler
DELETE FROM sole_images WHERE crawler_id = '<crawler_id>';

-- Reset crawler statistics
UPDATE crawlers 
SET items_scraped = 0, 
    current_run_items = 0,
    last_run_at = NULL
WHERE id = '<crawler_id>';
```

#### Performance & Indexes
```sql
-- Check pgvector extension
SELECT extname, extversion FROM pg_extension WHERE extname='vector';

-- Install pgvector (if missing)
CREATE EXTENSION IF NOT EXISTS vector;

-- List all indexes on sole_images
SELECT indexname, indexdef FROM pg_indexes 
WHERE tablename = 'sole_images';

-- Rebuild vector indexes
REINDEX INDEX idx_sole_images_clip_embedding;
REINDEX INDEX idx_sole_images_edge_embedding;
REINDEX INDEX idx_sole_images_texture_embedding;

-- Analyze tables (update statistics)
ANALYZE sole_images;
ANALYZE uploaded_images;

-- Vacuum tables (reclaim space)
VACUUM FULL sole_images;
```

#### Database Maintenance
```sql
-- Check database size
SELECT pg_size_pretty(pg_database_size('stip_production'));

-- Check table sizes
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check connections
SELECT 
    datname, 
    usename, 
    application_name, 
    state, 
    query_start
FROM pg_stat_activity
WHERE datname = 'stip_production';

-- Kill specific connection
SELECT pg_terminate_backend(<pid>);
```

### Vector Embeddings Management

#### Backfill Missing Vectors
```bash
# Backfill all images with missing vectors
docker exec -it stip_backend python scripts/backfill_vectors.py --batch-size 50

# Backfill with limit (for testing)
docker exec -it stip_backend python scripts/backfill_vectors.py --batch-size 10 --limit 100

# Resume from offset (if interrupted)
docker exec -it stip_backend python scripts/backfill_vectors.py --start-offset 500
```

#### Verify Vector Quality
```sql
-- Check vector dimensions
SELECT 
    id,
    array_length(clip_embedding::float[], 1) as clip_dim,
    array_length(edge_embedding::float[], 1) as edge_dim,
    array_length(texture_embedding::float[], 1) as texture_dim
FROM sole_images 
WHERE clip_embedding IS NOT NULL
LIMIT 5;

-- Expected: clip_dim=512, edge_dim=256, texture_dim=128
```

#### Test Vector Search
```sql
-- Find similar images using edge+texture (example)
WITH target AS (
    SELECT edge_embedding, texture_embedding 
    FROM sole_images 
    WHERE id = '<some_image_id>'
)
SELECT 
    si.id,
    si.brand,
    si.product_type,
    (
        0.60 * (1 - (si.edge_embedding <-> target.edge_embedding)) +
        0.40 * (1 - (si.texture_embedding <=> target.texture_embedding))
    ) as similarity_score
FROM sole_images si, target
WHERE si.edge_embedding IS NOT NULL
  AND si.texture_embedding IS NOT NULL
  AND si.id != '<some_image_id>'
ORDER BY similarity_score DESC
LIMIT 10;
```

---

## 🚢 Deployment Guide

### Pre-Deployment Checklist

- [ ] Servers are accessible via SSH
- [ ] Docker & Docker Compose installed
- [ ] Firewall configured (ports 22, 80, 443)
- [ ] Environment variables set in `.env.production`
- [ ] SSL certificates obtained and placed in `/etc/nginx/ssl/`
- [ ] Code pulled from Git repository
- [ ] Database backup taken (if updating existing deployment)

### Backend Deployment

```bash
# SSH to backend server
ssh root@95.142.102.138

# Navigate to app directory
cd /opt/sarapps

# Pull latest code
git stash  # Save local changes
git pull origin main

# Stop services
docker-compose stop backend worker

# Rebuild containers
docker-compose build --no-cache backend worker

# Start services
docker-compose up -d backend worker

# Verify startup
docker logs stip_backend --tail 50 -f
docker logs stip_worker --tail 50 -f

# Test API health
curl http://localhost:5000/api/database/health
```

### Frontend Deployment

```bash
# SSH to frontend server
ssh root@95.142.102.147

# Navigate to app directory
cd /opt/sarapps

# Pull latest code
git stash
git pull origin main

# Stop services
docker-compose -f docker-compose.frontend.yml stop frontend admin

# Rebuild containers (with fresh base images)
docker-compose -f docker-compose.frontend.yml build --no-cache --pull frontend admin

# Start services
docker-compose -f docker-compose.frontend.yml up -d frontend admin

# Verify startup
docker logs stip_frontend --tail 50 -f
docker logs stip_admin --tail 50 -f

# Test Nginx
sudo nginx -t
sudo systemctl reload nginx
```

### Nginx Configuration Update

```bash
# Edit Nginx config
sudo nano /etc/nginx/sites-available/stip-frontend

# Key settings for performance:
location /api/ {
    proxy_pass http://95.142.102.138:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Increase timeouts for slow image matching
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
}

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### Post-Deployment Verification

```bash
# 1. Check all containers are running
docker ps

# Expected output:
# stip_postgres    (healthy)
# stip_redis       (up)
# stip_backend     (up)
# stip_worker      (up)
# stip_frontend    (up)
# stip_admin       (up)

# 2. Test API endpoints
curl -k https://stip.sarapps.com/api/database/health
# Should return: {"status": "healthy"}

# 3. Test frontend
curl -I https://stip.sarapps.com
# Should return: 200 OK

# 4. Test admin dashboard
curl -I https://stip.sarapps.com/admin
# Should return: 200 OK

# 5. Check database connectivity
docker exec -it stip_backend python -c "from app import create_app, db; app = create_app(); with app.app_context(): db.engine.execute('SELECT 1')"

# 6. Check Redis connectivity
docker exec -it stip_redis redis-cli PING
# Should return: PONG

# 7. Check vector embeddings
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "SELECT COUNT(*) FROM sole_images WHERE edge_embedding IS NOT NULL;"
```

### Rollback Procedure

If deployment fails:

```bash
# 1. Stop new containers
docker-compose stop backend worker frontend admin

# 2. Revert code
git log  # Find previous commit hash
git reset --hard <previous_commit_hash>

# 3. Rebuild with old code
docker-compose build --no-cache backend worker frontend admin

# 4. Restore database (if schema changed)
docker exec -i stip_postgres psql -U stip_user stip_production < backup_before_deployment.sql

# 5. Start services
docker-compose up -d

# 6. Verify
docker ps
curl https://stip.sarapps.com/api/database/health
```

---

## 📖 User Guides

### Frontend User Guide

#### 1. Registration & Login

**Registration:**
1. Navigate to `https://stip.sarapps.com/register`
2. Enter your email address
3. Create a strong password (min 8 characters)
4. Click "Register"
5. Verify email (if email verification is enabled)

**Login:**
1. Navigate to `https://stip.sarapps.com/login`
2. Enter email and password
3. Click "Login"
4. You'll be redirected to the dashboard

#### 2. Uploading Shoe Images

1. Go to **Dashboard** (automatically shown after login)
2. Click **"Upload Image"** or drag-and-drop an image
3. Supported formats: JPG, PNG, WEBP (max 120MB)
4. Wait for upload confirmation

**Best Practices:**
- Use clear, high-resolution images
- Ensure the shoe sole is visible
- Avoid heavily shadowed or blurred images
- Crop image to focus on the sole (optional but improves accuracy)

#### 3. Matching Images

After uploading:

1. Image processing begins automatically
2. System extracts:
   - **Edge features** (tread patterns, grooves)
   - **Texture features** (rubber texture, wear patterns)
   - Optional: **CLIP embeddings** (deep learning visual features)

3. **Match Results** appear in seconds:
   - **Similarity Score**: 0-100% match confidence
   - **Product Info**: Brand, type, name, source URL
   - **Image Preview**: Matched sole image
   - **Source Link**: Click to view original product

#### 4. Viewing Match Results

**Result Filters:**
- **Top 5**: Show only top 5 matches (fastest)
- **Top 200**: Show top 200 matches
- **Top 500**: Show top 500 matches
- **Custom Range (All)**: Show all matches (slowest)

**Understanding Scores:**
- **90-100%**: Extremely high match (likely the same shoe)
- **80-89%**: Very high match (similar shoe or variant)
- **70-79%**: High match (same brand/type, different model)
- **60-69%**: Moderate match (similar tread pattern)
- **Below 60%**: Low match (not recommended)

#### 5. Re-Matching

If match quality is poor:
1. Click **"Re-match"** button
2. System re-processes image with updated algorithms
3. New results appear

**Note**: Re-matching uses the latest vector embeddings and may yield better results if the database has been updated.

---

### Admin User Guide

#### 1. Admin Login

1. Navigate to `https://stip.sarapps.com/admin/login`
2. Enter admin **username** and **password**
3. If MFA is enabled:
   - Enter 6-digit code from authenticator app (Google Authenticator, Authy)
4. Click "Login"

**Default Admin Credentials** (change immediately!):
- Username: `admin`
- Password: (set during deployment)

#### 2. User Management

**View Users:**
1. Go to **Users** tab
2. See list of all registered users
3. Columns: Email, Firebase UID, Created Date, Status

**Actions:**
- **Activate/Deactivate**: Toggle user access
- **Delete User**: Permanently remove user and their uploads
- **View Details**: See user's upload history

**Add User Manually:**
```sql
-- Use database query (no UI for this yet)
INSERT INTO users (id, email, firebase_uid, is_active, created_at)
VALUES (gen_random_uuid(), 'user@example.com', 'firebase_uid_here', true, NOW());
```

#### 3. Group Management

**Create Group:**
1. Go to **Groups** tab
2. Click "Add Group"
3. Enter:
   - **Name**: Group identifier (e.g., "Police Department A")
   - **Description**: Purpose of group
4. Click "Save"

**Assign Users to Groups:**
1. Select group
2. Click "Add Members"
3. Select users from list
4. Click "Add"

**Group Permissions** (future feature):
- Limit crawlers accessible by group
- Set upload/match quotas per group

#### 4. Crawler Management

**View Crawlers:**
1. Go to **Crawlers** tab
2. See list of all scrapers:
   - Name, URL, Status, Items Scraped, Last Run

**Start Crawler:**
1. Click **"Start"** button next to crawler
2. Crawler begins scraping in background
3. Progress updates in real-time

**Stop Crawler:**
1. Click **"Stop"** button
2. Current batch completes, then crawler stops
3. Progress is saved

**Activate/Deactivate Crawler:**
- Toggle **"Active"** switch
- Inactive crawlers cannot be started

**Configure Crawler:**
1. Click **"Edit"** button
2. Modify:
   - **Name**: Display name
   - **URL**: Base URL to scrape
   - **Scraper Module**: Python module name (e.g., `zalando_playwright`)
   - **Schedule**: Cron expression for auto-runs (future feature)
   - **Max Pages**: Limit number of pages to scrape
3. Click "Save"

**Monitor Crawler Progress:**
- View logs in real-time:
  ```bash
  docker logs stip_worker --tail 500 -f
  ```
- Check database for scraped count:
  ```sql
  SELECT name, items_scraped FROM crawlers;
  ```

#### 5. Statistics Dashboard

**View System Stats:**
1. Go to **Statistics** tab
2. See metrics:
   - **Total Users**: Registered users
   - **Total Images**: Scraped sole images
   - **Total Uploads**: User-uploaded images
   - **Active Crawlers**: Currently running
   - **Database Size**: Disk usage
   - **Vector Coverage**: % of images with embeddings

**Crawler Performance:**
- **Items/Hour**: Scraping speed
- **Unique %**: Percentage of unique (non-duplicate) images
- **Success Rate**: % of successful scrapes

**Export Statistics:**
```bash
# Database query for detailed stats
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "
SELECT 
    c.name,
    c.items_scraped,
    c.last_run_at,
    COUNT(si.id) as db_images
FROM crawlers c
LEFT JOIN sole_images si ON c.id = si.crawler_id
GROUP BY c.id
ORDER BY c.items_scraped DESC;
" > crawler_stats_$(date +%Y%m%d).csv
```

#### 6. Admin Settings

**Change Password:**
1. Go to **Settings**
2. Enter current password
3. Enter new password (min 8 characters)
4. Click "Update Password"

**Enable MFA (Multi-Factor Authentication):**
1. Go to **Settings** → **Security**
2. Click "Enable MFA"
3. Scan QR code with authenticator app
4. Enter 6-digit code to verify
5. Save backup codes (use if you lose your phone!)

**Disable MFA:**
```sql
-- Use database if locked out
UPDATE admin_users SET mfa_enabled = false WHERE username = 'admin';
```

#### 7. Database Management (Advanced)

**Backup Database:**
```bash
# On backend server
docker exec -it stip_postgres pg_dump -U stip_user stip_production > backup_$(date +%Y%m%d_%H%M%S).sql

# Compress backup
gzip backup_*.sql

# Download backup (from local machine)
scp root@95.142.102.138:/opt/sarapps/backup_*.sql.gz ./
```

**Restore Database:**
```bash
# Stop backend/worker to prevent writes
docker-compose stop backend worker

# Restore
docker exec -i stip_postgres psql -U stip_user stip_production < backup_20250101.sql

# Restart services
docker-compose up -d backend worker
```

**Delete All Scraped Images:**
```sql
-- WARNING: This deletes ALL scraped data!
TRUNCATE sole_images CASCADE;
UPDATE crawlers SET items_scraped = 0, last_run_at = NULL;
```

---

## 💻 Development Guide

### Local Development Setup

```bash
# 1. Clone repository
git clone <repo-url>
cd stip

# 2. Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Create local .env file
cp .env.example .env
nano .env
# Set DATABASE_URL, REDIS_URL, SECRET_KEY, JWT_SECRET_KEY

# 4. Start PostgreSQL and Redis locally (or use Docker)
docker-compose up -d postgres redis

# 5. Initialize database
python scripts/init_db.py init

# 6. Run backend
python app.py
# Backend runs on http://localhost:5000

# 7. Frontend setup (in new terminal)
cd ../frontend
npm install
npm run dev
# Frontend runs on http://localhost:3000

# 8. Admin setup (in new terminal)
cd ../admin
npm install
npm run dev
# Admin runs on http://localhost:3001
```

### Code Style & Standards

#### Python (Backend)
- **Formatter**: Black (`black .`)
- **Linter**: Flake8 (`flake8 .`)
- **Type Hints**: Use where appropriate
- **Docstrings**: Google-style

```python
def extract_vector_embeddings(self, image_array, image_path=None):
    """
    Extract vector embeddings for pgvector similarity search.
    
    Args:
        image_array: NumPy array of the image (RGB)
        image_path: Optional path to image file
        
    Returns:
        dict: {
            'clip_vector': np.array (512-dim) or None,
            'edge_vector': np.array (256-dim) or None,
            'texture_vector': np.array (128-dim) or None
        }
    """
    pass
```

#### JavaScript/React (Frontend/Admin)
- **Formatter**: Prettier (`npx prettier --write .`)
- **Linter**: ESLint (`npx eslint .`)
- **Style**: Functional components, hooks

```jsx
/**
 * MatchResults component displays shoe sole match results
 * @param {Array} matches - Array of match objects with similarity scores
 * @param {number} limit - Maximum number of results to display
 */
export default function MatchResults({ matches, limit }) {
  // Component logic
}
```

### Adding a New Scraper

1. **Create scraper file**: `backend/scrapers/mynewscraper.py`

```python
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class MyNewScraperScraper:
    def __init__(self, max_pages=None):
        self.max_pages = max_pages
        
    async def scrape(self):
        """Main scraping method - must be async generator"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Navigate and scrape
            await page.goto("https://example.com/shoes")
            
            # Extract products
            products = []
            # ... scraping logic ...
            
            # Yield batch of products
            yield products
            
            await browser.close()

# Required: Export scraper instance
async def scrape(max_pages=None):
    scraper = MyNewScraperScraper(max_pages=max_pages)
    async for batch in scraper.scrape():
        yield batch
```

2. **Add crawler to database**:

```sql
INSERT INTO crawlers (id, name, url, scraper_module, is_active)
VALUES (
    gen_random_uuid(),
    'MyNewScraper',
    'https://example.com',
    'mynewscraper',
    true
);
```

3. **Test scraper**:

```bash
docker exec -it stip_backend python -c "
import asyncio
from scrapers.mynewscraper import scrape

async def test():
    async for batch in scrape(max_pages=1):
        print(f'Scraped {len(batch)} products')
        
asyncio.run(test())
"
```

### Testing

#### Backend Tests
```bash
cd backend
pytest tests/  # (if tests exist)

# Manual API testing
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPass123!"}'
```

#### Frontend Tests
```bash
cd frontend
npm run test  # (if tests configured)

# Manual browser testing
npm run dev
# Open http://localhost:3000 and test flows
```

### Debugging

#### Backend Debugging
```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use print debugging
print(f"DEBUG: variable = {variable}")

# Check logs
docker logs stip_backend --tail 200 -f
```

#### Frontend Debugging
- Use browser DevTools (F12)
- Check Console for errors
- Check Network tab for API calls
- Use React DevTools extension

#### Database Debugging
```sql
-- Check slow queries
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 seconds';

-- Explain query performance
EXPLAIN ANALYZE
SELECT * FROM sole_images WHERE edge_embedding IS NOT NULL LIMIT 100;
```

---

## 🔧 Troubleshooting

### Common Issues & Solutions

#### 1. **Frontend shows "Cannot connect to API"**

**Cause**: Backend not accessible or CORS issue

**Solution**:
```bash
# Check backend is running
docker ps | grep stip_backend

# Test backend directly
curl http://95.142.102.138:5000/api/database/health

# Check Nginx proxy configuration
sudo nano /etc/nginx/sites-available/stip-frontend
# Ensure proxy_pass points to correct backend IP

# Reload Nginx
sudo systemctl reload nginx

# Check CORS settings in backend
docker exec -it stip_backend grep -r "CORS_ORIGINS" core/config/
```

#### 2. **504 Gateway Timeout when uploading images**

**Cause**: Nginx timeout too short, backend Gunicorn timeout too short

**Solution**:
```bash
# Increase Nginx timeouts
sudo nano /etc/nginx/sites-available/stip-frontend
# Add to location /api/ block:
proxy_connect_timeout 300s;
proxy_send_timeout 300s;
proxy_read_timeout 300s;

sudo nginx -t && sudo systemctl reload nginx

# Increase Gunicorn timeout (already done in entrypoint.sh)
# --timeout 300

# Restart backend
docker-compose restart backend
```

#### 3. **Vector search not working (falls back to legacy search)**

**Cause**: Images missing vector embeddings

**Solution**:
```bash
# Check vector coverage
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "
SELECT 
    COUNT(*) as total,
    COUNT(edge_embedding) as with_edge,
    COUNT(texture_embedding) as with_texture
FROM sole_images;
"

# Backfill missing vectors
docker exec -it stip_backend python scripts/backfill_vectors.py --batch-size 50

# Verify after backfill
# edge and texture counts should match total
```

#### 4. **Crawler crashes at ~365 products**

**Cause**: RQ job timeout (default 180 seconds)

**Solution**:
```bash
# Job timeout already increased to 24 hours in backend/routes/crawlers.py
# Verify:
docker exec -it stip_backend grep -A 5 "enqueue.*run_crawler_job" routes/crawlers.py
# Should show: job_timeout=86400 (24 hours)

# If not, rebuild backend
docker-compose build --no-cache backend
docker-compose up -d backend
```

#### 5. **Scraper "total_items" and "unique_items" not updating**

**Cause**: Key mismatch in `scraper_manager.py` or `tasks.py`

**Solution**:
```bash
# Check if fixed in code
docker exec -it stip_backend grep "total_unique" services/scraper_manager.py
docker exec -it stip_backend grep "total_unique" jobs/tasks.py

# Should return consistent keys
# If not, update code and rebuild

# Restart worker
docker-compose restart worker
```

#### 6. **Container compromised with malware**

**Cause**: Compromised base Docker image or malicious package

**Solution**:
```bash
# Stop and remove compromised container
docker-compose stop frontend
docker-compose rm -f frontend

# Remove ALL instances of potentially compromised image
docker rmi -f $(docker images -q node:20-alpine)

# Rebuild with clean, verified image
docker-compose build --no-cache --pull frontend

# Start container
docker-compose up -d frontend

# Monitor for suspicious activity
docker logs stip_frontend --tail 100 -f | grep -iE 'wget|curl|http://[0-9]'

# Block malicious IPs at firewall level
sudo ufw deny from 172.237.55.180
sudo ufw deny from 176.117.107.158
```

#### 7. **PostgreSQL unhealthy on startup**

**Cause**: Timing issue - PostgreSQL slow to initialize

**Solution**:
```bash
# Check PostgreSQL logs
docker logs stip_postgres --tail 50

# If "database system is ready to accept connections" appears, just wait 10 seconds

# If persistent issue, restart PostgreSQL
docker-compose restart postgres

# Check health manually
docker exec -it stip_postgres pg_isready -U stip_user
```

#### 8. **Out of disk space**

**Cause**: Large database, uploaded images, Docker volumes

**Solution**:
```bash
# Check disk usage
df -h

# Check Docker disk usage
docker system df

# Clean up unused Docker resources
docker system prune -a --volumes -f  # WARNING: Removes unused volumes!

# Clean old backups
cd /opt/sarapps
rm -f backup_*.sql.gz

# Vacuum database to reclaim space
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "VACUUM FULL;"

# Consider moving uploads to separate storage
# Or implement image size limits
```

#### 9. **"Permission denied" errors in containers**

**Cause**: File ownership mismatch

**Solution**:
```bash
# Fix ownership of app directory
sudo chown -R $USER:$USER /opt/sarapps

# Fix ownership of uploads directory
sudo chown -R 1000:1000 /opt/sarapps/backend/uploads

# Rebuild containers with correct UID
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

#### 10. **Admin cannot login (MFA locked out)**

**Cause**: Lost authenticator app or incorrect MFA code

**Solution**:
```bash
# Disable MFA via database
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "
UPDATE admin_users SET mfa_enabled = false WHERE username = 'admin';
"

# Admin can now login without MFA code
# Re-enable MFA in Settings after login
```

### Performance Optimization

#### Slow Image Matching

**Optimize pgvector indexes:**
```bash
# Rebuild indexes with optimal parameters
docker exec -it stip_backend python scripts/init_db.py init

# Or manually:
docker exec -it stip_postgres psql -U stip_user -d stip_production -c "
REINDEX INDEX idx_sole_images_edge_embedding;
REINDEX INDEX idx_sole_images_texture_embedding;
ANALYZE sole_images;
"
```

**Reduce image processing time:**
- Use smaller images (resize before upload)
- Reduce `top_k_candidates` in `backend/routes/user.py`
- Increase backend workers in `entrypoint.sh` (`--workers 8`)

#### Slow Scraping

**Optimize crawler:**
- Reduce `batch_size` in `scraper_manager.py` (less memory)
- Increase `SESSION_RESTART_INTERVAL` (fewer browser restarts)
- Use faster proxies (residential vs datacenter)
- Disable image downloads if only metadata needed

---

## 📚 API Reference

### Authentication

#### Register User
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "firebase_uid": "optional_firebase_uid"
}

Response: 201 Created
{
  "message": "User registered successfully",
  "user_id": "uuid-here"
}
```

#### Login User
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!"
}

Response: 200 OK
{
  "access_token": "jwt-token-here",
  "refresh_token": "refresh-token-here",
  "user": {
    "id": "uuid",
    "email": "user@example.com"
  }
}
```

#### Admin Login
```http
POST /api/admin/login
Content-Type: application/json

{
  "username": "admin",
  "password": "AdminPass123!",
  "mfa_code": "123456"  // Optional, if MFA enabled
}

Response: 200 OK
{
  "access_token": "jwt-token-here",
  "admin": {
    "id": "uuid",
    "username": "admin",
    "email": "admin@example.com"
  }
}
```

### User Operations

#### Upload Image
```http
POST /api/user/upload-image
Authorization: Bearer <jwt-token>
Content-Type: multipart/form-data

file: <image-file>

Response: 201 Created
{
  "message": "Image uploaded successfully",
  "image_id": "uuid-here",
  "filename": "shoe_sole.jpg"
}
```

#### Match Image
```http
POST /api/user/match-image/<image_id>
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "limit": 200  // Optional: 5, 200, 500, or null (all)
}

Response: 200 OK
{
  "matches": [
    {
      "id": "uuid",
      "brand": "Zalando",
      "product_type": "Sneakers",
      "product_name": "Nike Air Max",
      "source_url": "https://...",
      "similarity_score": 0.95,
      "image_url": "https://..."
    },
    // ... more matches
  ],
  "total_matches": 200,
  "processing_time_ms": 450
}
```

### Admin Operations

#### List Users
```http
GET /api/admin/users?page=1&limit=20&search=email@example.com
Authorization: Bearer <admin-jwt-token>

Response: 200 OK
{
  "users": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "created_at": "2025-01-01T00:00:00Z",
      "is_active": true
    }
  ],
  "total": 150,
  "page": 1,
  "limit": 20
}
```

#### Start Crawler
```http
POST /api/admin/crawlers/<crawler_id>/start
Authorization: Bearer <admin-jwt-token>

Response: 200 OK
{
  "message": "Crawler started successfully",
  "run_id": "uuid-here",
  "job_id": "rq-job-id"
}
```

#### Stop Crawler
```http
POST /api/admin/crawlers/<crawler_id>/stop
Authorization: Bearer <admin-jwt-token>

Response: 200 OK
{
  "message": "Crawler stop requested",
  "run_id": "uuid-here"
}
```

#### Get Crawler Statistics
```http
GET /api/admin/crawlers/<crawler_id>/statistics
Authorization: Bearer <admin-jwt-token>

Response: 200 OK
{
  "crawler_id": "uuid",
  "name": "Zalando",
  "total_items_scraped": 1233,
  "last_run_at": "2025-01-01T12:00:00Z",
  "average_items_per_hour": 450,
  "success_rate": 0.95
}
```

### Database Health Check

```http
GET /api/database/health

Response: 207 Multi-Status
{
  "postgres": {
    "status": "healthy",
    "response_time_ms": 5
  },
  "redis": {
    "status": "healthy",
    "response_time_ms": 2
  },
  "overall": "healthy"
}
```

---

## 📞 Support & Contact

### Getting Help

1. **Documentation**: Start with this README and the guides in the repo
2. **Logs**: Check Docker logs for detailed error messages
3. **Database**: Query PostgreSQL for data insights
4. **GitHub Issues**: Report bugs or request features (if repo is public)

### Useful Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [Docker Documentation](https://docs.docker.com/)
- [Playwright Documentation](https://playwright.dev/)

---

## 📄 License

*[Add license information here]*

---

## 🙏 Acknowledgments

- **OpenAI CLIP** for visual embeddings
- **pgvector** for fast similarity search
- **Playwright** for robust web scraping
- **Flask & Next.js** communities

---

**Last Updated**: December 2025  
**Version**: 1.0.0  
**Maintained By**: SAR Apps Development Team
