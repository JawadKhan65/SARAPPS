# Crawler Production Readiness Checklist

## ✅ Implementation Status

### Core Features
- [x] **Background Job Processing with Redis Queue (RQ)**
  - Jobs run in background worker process
  - 2-hour timeout per crawler job
  - Results stored for 24 hours in Redis
  
- [x] **Duplicate Detection (Product Link-Based)**
  - URL normalization (removes trailing slashes, sorts query params, removes tracking params)
  - Checks both normalized and original URLs
  - Database unique constraint on `source_url`
  - Improved logging for duplicate detection
  
- [x] **Image Storage**
  - Stores both original and processed images as binary data in PostgreSQL
  - Fallback to file paths for legacy compatibility
  - Image hash for additional deduplication
  - Supports in-memory processing (no temp files needed)
  
- [x] **Uniqueness Tracking**
  - Configurable uniqueness threshold per crawler
  - Auto-stop when uniqueness drops below threshold
  - Real-time progress tracking
  - Batch-level uniqueness calculation
  
- [x] **Cancellation Support**
  - Admin can cancel running crawlers via UI
  - Responsive cancellation (checked during scraping)
  - Proper cleanup on cancellation
  - Status tracking in database and Redis
  
- [x] **Error Handling**
  - Consecutive error tracking
  - Detailed error logging
  - Graceful failure handling
  - Error notifications (logging level)

## 🚀 Starting the System

### 1. Start Redis (Required for Background Jobs)
```powershell
# Check if Redis container exists
docker ps -a | Select-String redis

# Start Redis if stopped
docker start redis

# Or create new Redis container if needed
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### 2. Start RQ Worker (Background Job Processor)
```powershell
cd backend
python jobs/worker.py
```
**Expected Output:**
```
18:45:12 RQ worker 'rq:worker:...' started
18:45:12 Listening on crawlers...
```

### 3. Start Backend API
```powershell
cd backend
python app.py
```

### 4. Start Frontend
```powershell
cd frontend
npm run dev -- -H 0.0.0.0
```

## 🧪 Testing Checklist

### Test 1: Background Job Execution
1. Navigate to Admin Panel → Crawlers
2. Select a crawler (e.g., Zappos, Amazon)
3. Click "Start Crawler"
4. **Verify in RQ Worker Terminal:**
   ```
   Started crawler job <job-id> for crawler <crawler-id>
   🚀 Starting crawler: <name> (Run ID: <run-id>)
   ```
5. **Verify in Admin UI:**
   - Status changes to "Running"
   - Progress bar updates in real-time
   - Batch count increases
   - Uniqueness percentage displays

### Test 2: Duplicate Detection
1. Run a crawler that has existing data
2. **Check Backend Logs for:**
   ```
   🔄 Duplicate product link detected: https://...
   (Brand: ..., Name: ...)
   ```
3. **Verify in Database:**
   ```sql
   SELECT COUNT(*) FROM sole_images WHERE source_url = '<test-url>';
   -- Should return 1 (not duplicated)
   ```

### Test 3: Data Storage
1. After crawler completes, check database:
   ```sql
   SELECT 
     id, brand, product_name, source_url,
     LENGTH(original_image_data) as orig_size,
     LENGTH(processed_image_data) as proc_size,
     image_format, quality_score
   FROM sole_images 
   WHERE crawler_id = '<crawler-id>' 
   ORDER BY crawled_at DESC 
   LIMIT 10;
   ```
2. **Verify:**
   - Both `original_image_data` and `processed_image_data` have values
   - `source_url` is unique and normalized
   - `image_format`, `quality_score`, `image_width/height` populated

### Test 4: Cancellation
1. Start a long-running crawler
2. Click "Stop" button in Admin UI
3. **Verify in Worker Terminal:**
   ```
   🛑 Cancellation requested
   Scraper run cancelled: <name> after processing <N> items
   ```
4. **Verify in UI:**
   - Status changes to "Cancelled"
   - Reason shows "Manually cancelled by admin"
   - Partial statistics preserved

### Test 5: Uniqueness Threshold
1. Configure crawler with `min_uniqueness_threshold` = 85%
2. Run on data with many duplicates
3. **Verify Auto-Stop:**
   ```
   ⚠️ Uniqueness below threshold: 70.0% < 85.0%
   Auto-stopped: Uniqueness 70.0% below threshold 85.0%
   ```

## 📊 Monitoring

### Check Crawler Status
```sql
SELECT 
  c.name,
  c.is_running,
  c.current_batch,
  c.current_run_items,
  c.uniqueness_percentage,
  c.last_error,
  cr.status as run_status,
  cr.items_scraped,
  cr.unique_items,
  cr.duplicate_items
FROM crawlers c
LEFT JOIN crawler_runs cr ON cr.id = (
  SELECT id FROM crawler_runs 
  WHERE crawler_id = c.id 
  ORDER BY started_at DESC LIMIT 1
);
```

### Check Redis Job Queue
```powershell
# Connect to Redis
docker exec -it redis redis-cli

# Check queue length
LLEN rq:queue:crawlers

# Check job details
HGETALL crawler:<crawler-id>

# Check active jobs
SMEMBERS rq:workers
```

### Backend Logs
- Look for these markers:
  - `🚀 Starting crawler:` - Job started
  - `🔄 Duplicate product link detected:` - Duplicate found
  - `✅ Batch insertion complete:` - Batch processed successfully
  - `⚠️ STOP SCRAPING:` - Threshold not met
  - `🛑 Cancel requested:` - User cancelled
  - `✅ Crawler completed:` - Success
  - `❌ Crawler failed:` - Error occurred

## 🔧 Configuration

### Per-Crawler Settings (database: `crawlers` table)
- `min_uniqueness_threshold`: Stop if uniqueness drops below this % (default: 85)
- `notify_admin_on_low_uniqueness`: Send notification when threshold not met
- `scraper_module`: Python module name (e.g., `zappos`, `amazon`)
- `is_active`: Enable/disable crawler

### Global Settings (`backend/core/config/config.py`)
- `BATCH_SIZE`: Products per batch (default: 50)
- `SIMILARITY_THRESHOLD`: Image similarity threshold (default: 0.85)
- `REDIS_URL`: Redis connection string

### RQ Worker Settings (`backend/jobs/worker.py`)
- Queue names: `crawlers`
- Job timeout: 2 hours
- Result TTL: 24 hours

## 🐛 Troubleshooting

### Worker Not Processing Jobs
**Symptom:** Jobs stuck in "running" but nothing happens
**Solution:**
```powershell
# Check if worker is running
Get-Process python | Where-Object {$_.CommandLine -like "*worker.py*"}

# Restart worker
cd backend
python jobs/worker.py
```

### Redis Connection Failed
**Symptom:** `redis.exceptions.ConnectionError`
**Solution:**
```powershell
# Check Redis status
docker ps | Select-String redis

# Restart Redis
docker restart redis

# Check connectivity
docker exec -it redis redis-cli ping
# Should return: PONG
```

### Duplicate URLs Still Being Inserted
**Symptom:** Same product URL appears multiple times
**Check:**
1. Database unique constraint: `SELECT * FROM pg_indexes WHERE tablename='sole_images' AND indexname LIKE '%source_url%';`
2. URL normalization working: Check logs for "Duplicate product link detected"
3. Migration applied: `SELECT * FROM sole_images WHERE source_url LIKE '%?utm_%' LIMIT 5;` (should be empty)

### Images Not Stored
**Symptom:** `original_image_data` or `processed_image_data` is NULL
**Check:**
1. Image download successful: Check logs for "Downloaded image"
2. Processing successful: Check logs for "Storing image in database"
3. Database column size sufficient: PostgreSQL `bytea` has no practical limit

## 📈 Performance Optimization

### Database Indexes (Already Applied)
- `source_url` - UNIQUE index for duplicate detection
- `image_hash` - UNIQUE index for image deduplication
- `crawler_id` - Index for crawler-specific queries
- `crawled_at` - Index for time-based queries

### Batch Size Tuning
- **Small batches (10-20)**: More frequent uniqueness checks, slower overall
- **Medium batches (50)**: Balanced performance and responsiveness ✅ **Recommended**
- **Large batches (100+)**: Faster but may waste work if threshold not met

### Redis Optimization
- Use persistent Redis for production: `docker run -d -v redis-data:/data redis:7-alpine redis-server --appendonly yes`
- Monitor memory: `docker exec redis redis-cli INFO memory`

## 🚢 Production Deployment Checklist

### Pre-Deployment
- [ ] All tests passing
- [ ] Redis persistent storage configured
- [ ] Database backups enabled
- [ ] Environment variables set (`.env` file)
- [ ] Logging configured (log level, rotation)
- [ ] RQ worker set as systemd service (Linux) or Windows Service

### Deployment
- [ ] Deploy backend with Gunicorn/Waitress
- [ ] Start RQ worker processes (recommend 2-4 workers)
- [ ] Configure Nginx reverse proxy
- [ ] Enable HTTPS (Let's Encrypt)
- [ ] Set up monitoring (Prometheus/Grafana)

### Post-Deployment
- [ ] Run test crawler with small dataset
- [ ] Verify duplicate detection working
- [ ] Monitor worker logs for errors
- [ ] Set up alerting (email/Slack for failures)
- [ ] Document runbook for operations team

## 📝 Notes

### URL Normalization Details
The `normalize_url()` function:
1. Converts scheme and domain to lowercase
2. Removes trailing slashes from path
3. Sorts query parameters alphabetically
4. Removes tracking parameters: `utm_source`, `utm_medium`, `utm_campaign`, `ref`, `source`
5. Removes URL fragments (#anchor)

**Examples:**
- `https://Example.com/Product/` → `https://example.com/Product`
- `https://site.com/item?ref=123&id=ABC` → `https://site.com/item?id=ABC`
- `https://site.com/item?b=2&a=1` → `https://site.com/item?a=1&b=2`

### Image Processing Pipeline
1. **Download**: Image downloaded to memory (no temp files)
2. **Process**: Rotation-robust sole detection with `process_reference_sole()`
3. **Extract Features**: LBP histogram, SIFT/ORB features
4. **Store**: Both original and processed saved as binary in database
5. **Deduplicate**: Check URL, image hash, and visual similarity

### Background Job Flow
```
Admin UI → API Endpoint → RQ Queue → Worker → ScraperManager → Scraper Class
                                         ↓
                                    Batch Callback
                                         ↓
                                  ScraperService
                                         ↓
                                    Database
```

## 🎯 Success Metrics

A production-ready crawler should achieve:
- **Uniqueness Rate**: > 85% for first run, 20-50% for subsequent runs
- **Error Rate**: < 5% per batch
- **Processing Speed**: 50-200 products per minute (depends on image size)
- **Memory Usage**: < 500MB per worker
- **Duplicate Detection**: 99.9% accuracy (URL-based)

---

**Last Updated:** Production deployment preparation phase
**Status:** ✅ Ready for production deployment
