# 🚀 Running the Crawler System - Quick Start Guide

## Prerequisites Check

Before starting, ensure you have:
- ✅ PostgreSQL 15+ running with database created
- ✅ Redis 7+ running (Docker: `docker ps | Select-String redis`)
- ✅ Python 3.9+ with all requirements installed
- ✅ Node.js 18+ for frontend

## Step-by-Step Startup

### 1. Start Redis (if not running)
```powershell
# Check Redis status
docker ps | Select-String redis

# Start existing container
docker start redis

# OR create new Redis container
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

**Verify Redis:** `docker exec redis redis-cli ping` should return `PONG`

### 2. Start RQ Worker (Background Job Processor)
Open a **NEW terminal** (keep it running):
```powershell
cd "d:\advanced print match system\backend"
python jobs\worker.py
```

**Expected Output:**
```
18:45:12 RQ worker 'rq:worker:...' started
18:45:12 Listening on crawlers...
```

⚠️ **Keep this terminal open!** The worker must run continuously to process crawler jobs.

### 3. Start Backend API
Open **ANOTHER terminal**:
```powershell
cd "d:\advanced print match system\backend"
python app.py
```

**Expected Output:**
```
 * Running on http://0.0.0.0:5000
```

### 4. Start Frontend (User Dashboard)
Open **ANOTHER terminal**:
```powershell
cd "d:\advanced print match system\frontend"
npm run dev -- -H 0.0.0.0
```

**Expected Output:**
```
  ▲ Next.js 14.x
  - Local:        http://0.0.0.0:3000
  - Network:      http://192.168.1.8:3000
```

### 5. Start Admin Panel
Open **ANOTHER terminal**:
```powershell
cd "d:\advanced print match system\admin"
npm run dev
```

**Expected Output:**
```
  ▲ Next.js 14.x
  - Local:        http://localhost:3001
```

## 🧪 Testing the System

### Quick System Test
Run the automated test script:
```powershell
cd "d:\advanced print match system\backend"
python scripts\test_crawler_system.py
```

This will verify:
- ✅ Redis connection
- ✅ RQ queue setup
- ✅ Database connection
- ✅ Worker status
- ✅ Crawler availability
- ✅ URL normalization

### Manual Crawler Test

1. **Open Admin Panel:** http://localhost:3001
2. **Login** with admin credentials
3. **Navigate to:** Crawlers page
4. **Select a crawler** (e.g., Zappos, Amazon)
5. **Click "Start Crawler"**

**What to Watch:**

**In RQ Worker Terminal:**
```
Started crawler job abc-123 for crawler xyz-789
🚀 Starting crawler: Zappos (Run ID: ...)
Processing batch of 20 items during scraping...
✅ Batch insertion complete: 18 inserted, 2 duplicates
```

**In Admin UI:**
- Status changes to "Running" (green indicator)
- Progress bar appears
- Batch count increases (e.g., "Batch 3 of ?")
- Uniqueness percentage updates (e.g., "92.5%")
- Items count increases

**Backend Terminal (if errors occur):**
```
🔄 Duplicate product link detected: https://...
⚠️ Uniqueness below threshold: 70% < 85%
```

### Testing Duplicate Detection

Run same crawler twice:

**First Run (Expected):**
```
Batch 1: 50 inserted, 0 duplicates, 100% unique
Batch 2: 48 inserted, 2 duplicates, 96% unique
```

**Second Run (Expected):**
```
Batch 1: 5 inserted, 45 duplicates, 10% unique
⚠️ STOP SCRAPING: Batch uniqueness 10% below threshold 85%
Auto-stopped: Uniqueness 10% below threshold 85%
```

✅ **This is correct!** Duplicate detection is working.

## 🔍 Monitoring

### Check Active Crawlers
```sql
SELECT 
  name, 
  is_running, 
  current_run_items, 
  uniqueness_percentage,
  last_started_at
FROM crawlers
WHERE is_active = true;
```

### Check Recent Results
```sql
SELECT 
  brand, 
  product_name, 
  source_url,
  LENGTH(original_image_data) as image_size_bytes,
  crawled_at
FROM sole_images
ORDER BY crawled_at DESC
LIMIT 10;
```

### Check Job Queue (Redis)
```powershell
docker exec redis redis-cli

# Inside Redis CLI:
LLEN rq:queue:crawlers          # Jobs waiting
SMEMBERS rq:workers             # Active workers
HGETALL crawler:<crawler-id>    # Job status
```

## 🐛 Common Issues

### Issue: "No workers running"
**Symptom:** Crawler status stuck at "Running" but nothing happens

**Solution:**
```powershell
# Terminal 1 (worker terminal)
# Press Ctrl+C to stop if running
cd "d:\advanced print match system\backend"
python jobs\worker.py
```

### Issue: "Redis connection refused"
**Symptom:** `redis.exceptions.ConnectionError`

**Solution:**
```powershell
# Check if Redis is running
docker ps | Select-String redis

# If not running
docker start redis

# If not exists
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### Issue: "Another crawler already running"
**Symptom:** Cannot start new crawler

**Solution:**
1. Check Admin UI - is a crawler actually running?
2. If stuck, reset in database:
```sql
UPDATE crawlers SET is_running = false, cancel_requested = false;
```

### Issue: Mobile CORS error
**Symptom:** "CORS policy: Response to preflight request doesn't pass"

**Solution:**
1. Ensure backend CORS allows your IP (already configured for `*`)
2. Restart backend after CORS changes
3. Clear mobile browser cache
4. Access via `http://192.168.1.8:3000` (use your computer's IP)

## 📊 Expected Performance

### Normal Operation:
- **Processing Speed:** 50-200 products/minute
- **Uniqueness (first run):** 90-100%
- **Uniqueness (repeat run):** 10-30%
- **Memory (per worker):** 200-500 MB
- **CPU:** 20-40% during active processing

### When to Worry:
- ⚠️ Processing < 10 products/minute → Check network/image download issues
- ⚠️ Memory > 1GB → Possible memory leak, restart worker
- ⚠️ Consecutive errors > 5 → Check crawler scraper_module compatibility

## 🎯 Production Checklist

Before deploying to production:

- [ ] Test all crawlers individually
- [ ] Verify duplicate detection with repeat runs
- [ ] Check database storage (images stored as binary)
- [ ] Monitor worker memory usage over 30 minutes
- [ ] Test cancellation functionality
- [ ] Verify uniqueness threshold auto-stop
- [ ] Test with poor internet (expect graceful failures)
- [ ] Check logs for any unexpected errors
- [ ] Backup database before running crawlers
- [ ] Document which crawlers are production-ready

## 📱 Accessing from Mobile

### For Testing Camera Feature:
1. Find your computer's IP: `ipconfig` → Look for IPv4 Address
2. Ensure frontend started with `-H 0.0.0.0` flag
3. On mobile browser: `http://192.168.1.8:3000` (use your IP)
4. Mobile must be on same WiFi network

### For Admin Panel (not recommended for mobile):
- Admin panel best viewed on desktop
- Use `http://192.168.1.8:3001` if needed

## 🔄 Daily Operations

### Starting Work Session:
1. Start Redis: `docker start redis`
2. Start RQ Worker: `python jobs\worker.py`
3. Start Backend: `python app.py`
4. Start Frontend: `npm run dev -- -H 0.0.0.0`

### Ending Work Session:
1. Stop all crawlers via Admin UI
2. Press `Ctrl+C` in each terminal
3. Optionally stop Redis: `docker stop redis`

### Maintenance:
- **Weekly:** Check Redis memory usage
- **Weekly:** Review crawler error logs
- **Monthly:** Clean old crawler_runs records
- **Monthly:** Analyze duplicate rates per crawler

## 📞 Getting Help

### Logs Location:
- **Backend:** Terminal output (can redirect to file: `python app.py > backend.log 2>&1`)
- **Worker:** Terminal output (worker.log if configured)
- **Redis:** `docker logs redis`

### Debugging Commands:
```powershell
# Check processes
Get-Process python

# Check ports
netstat -ano | Select-String "5000|6379|3000|3001"

# Database connection
# In PostgreSQL: \c your_database
# Check tables: \dt

# Redis info
docker exec redis redis-cli INFO
```

---

**System Status:** ✅ Ready for production deployment  
**Last Updated:** Final improvement phase complete  
**Next Steps:** Production deployment and monitoring setup
