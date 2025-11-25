# Quick Start: Background Jobs Implementation

## Summary of Changes

✅ Added **RQ (Redis Queue)** for background job processing  
✅ Crawlers now run as **non-blocking background jobs**  
✅ Added **RQ workers** to process jobs independently  
✅ Updated **Docker Compose** with 2 worker instances  
✅ Real-time **progress tracking via Redis**  

---

## Installation Steps

### 1. Install New Dependencies

```powershell
cd backend
pip install -r requirements.txt
```

This installs `rq` (Redis Queue) package.

### 2. Start Redis (if not running)

```powershell
# Using Docker
docker-compose up -d redis

# Or check if Redis is running
redis-cli ping
# Should return: PONG
```

### 3. Start RQ Worker(s)

**Option A: Development (Manual)**
```powershell
cd backend
python worker.py
```

**Option B: Production (Docker)**
```powershell
docker-compose up -d worker
```

**Option C: Multiple Workers (Better Performance)**
```powershell
# Terminal 1
python worker.py

# Terminal 2
python worker.py
```

### 4. Start Backend (As Before)

```powershell
cd backend
python app.py
```

---

## Usage

### Admin Starts Crawler

1. Admin clicks "Start Crawler" in dashboard
2. **Job is enqueued** → Returns immediately (no waiting!)
3. **Worker picks up job** → Runs in background
4. **Admin can close browser** → Job continues running
5. **Check progress anytime** → Real-time updates

### API Changes

**Start Crawler (Non-blocking now!)**
```http
POST /api/crawlers/{id}/start
Response:
{
  "message": "Crawler job started",
  "crawler_id": "...",
  "job_id": "rq-abc123",  ← New: Job tracking ID
  "run_type": "manual"
}
```

**Check Job Status (New endpoint)**
```http
GET /api/crawlers/{id}/job-status
Response:
{
  "status": {
    "job_id": "rq-abc123",
    "status": "running",
    "progress": "45.2%",
    "items_scraped": "1250"
  }
}
```

**Stop Crawler (Instant cancellation)**
```http
POST /api/crawlers/{id}/stop
Response:
{
  "message": "Crawler job cancelled",
  "crawler_id": "..."
}
```

---

## Testing

### 1. Check Worker is Running

```powershell
# Should see: "Waiting for jobs..."
```

### 2. Start a Crawler

```powershell
# In admin dashboard, click "Start Crawler"
# Check console: Should see job enqueued
```

### 3. Monitor Progress

```powershell
# Worker console should show:
# "Started crawler job rq-abc123..."
# "Processing batch 1/10..."
# etc.
```

---

## Verification Checklist

- [ ] `pip install rq` completed successfully
- [ ] Redis is running (`redis-cli ping` returns PONG)
- [ ] Worker started (`python worker.py` shows "Waiting for jobs...")
- [ ] Backend running (`python app.py`)
- [ ] Can start crawler from admin dashboard
- [ ] Crawler runs in background (doesn't block API)
- [ ] Can check job status
- [ ] Can cancel running crawler

---

## What Changed?

### Old System (Threading)
```
Admin clicks Start
  ↓
HTTP request stays open for hours
  ↓
Admin must keep browser open
  ↓
API worker blocked
  ↓
Can't run multiple crawlers
```

### New System (Background Jobs)
```
Admin clicks Start
  ↓
Job enqueued in Redis (instant response)
  ↓
Admin can close browser
  ↓
Dedicated worker processes job
  ↓
Can run 5+ crawlers simultaneously
  ↓
Real-time progress tracking
  ↓
Instant cancellation
```

---

## Troubleshooting

### "No module named 'rq'"
```powershell
pip install rq
```

### "Connection refused" (Redis)
```powershell
# Start Redis
docker-compose up -d redis
# Or install Redis locally
```

### Jobs not processing
```powershell
# Make sure worker is running
python worker.py
```

### Worker crashes
```powershell
# Check logs
# Make sure all environment variables are set
# DATABASE_URL, REDIS_URL, etc.
```

---

## Production Deployment

For production, add to your startup scripts:

```bash
# Start 2-3 workers
supervisorctl start rq-worker:*

# Or using systemd
systemctl start rq-worker@{1..2}
```

See `BACKGROUND_JOBS_SETUP.md` for detailed production configuration.

---

## Benefits You'll Notice

✅ **Faster admin dashboard** - No more waiting for crawlers  
✅ **Better user experience** - API stays responsive during crawls  
✅ **Run multiple crawlers** - No blocking, process 3-5 simultaneously  
✅ **Reliable** - Auto-retry on failure  
✅ **Easy monitoring** - Real-time progress in Redis  
✅ **Clean cancellation** - Stop jobs instantly  

---

## Next Steps

1. Test with a small crawler first
2. Monitor worker logs for any issues
3. Add more workers if processing 3+ crawlers simultaneously
4. Set up monitoring dashboard (optional: `pip install rq-dashboard`)

Need help? Check `BACKGROUND_JOBS_SETUP.md` for detailed documentation.
