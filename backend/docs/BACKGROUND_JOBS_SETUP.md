# Background Jobs Setup with Redis and RQ

This document explains how to run crawlers as background jobs using Redis Queue (RQ).

## Benefits

✅ **Non-blocking operations** - Admin can start crawlers and close browser  
✅ **Better resource management** - Crawlers don't block API workers  
✅ **Reliability** - Auto-retry on failure, graceful shutdown  
✅ **Progress tracking** - Real-time updates via Redis  
✅ **Easy cancellation** - Instant job cancellation  
✅ **Concurrent crawlers** - Run multiple crawlers simultaneously  

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure Redis is running:
```bash
# Using Docker
docker-compose up redis

# Or local Redis
redis-server
```

## Running Workers

### Development (Single Worker)

```bash
cd backend
python worker.py
```

### Production (Multiple Workers)

```bash
# Terminal 1: Worker for crawlers
python worker.py

# Terminal 2: Another worker for crawlers
python worker.py

# Or use supervisord/systemd
```

### Using Supervisor (Recommended for Production)

Create `/etc/supervisor/conf.d/rq-worker.conf`:

```ini
[program:rq-worker]
command=/path/to/venv/bin/python /path/to/backend/worker.py
directory=/path/to/backend
user=www-data
numprocs=2
process_name=%(program_name)s_%(process_num)02d
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
redirect_stderr=true
stdout_logfile=/var/log/rq-worker.log
```

Then:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start rq-worker:*
```

## How It Works

### 1. Admin Starts Crawler
```
POST /api/crawlers/{id}/start
→ Job enqueued in Redis
→ Immediate response to admin
→ Worker picks up job
```

### 2. Worker Processes Job
```
Worker → Fetch job from Redis queue
       → Run scraper (scrape images, process, store)
       → Update progress in Redis
       → Update database on completion
```

### 3. Admin Monitors Progress
```
GET /api/crawlers/{id}/job-status
→ Read from Redis (fast, no DB load)
→ Get real-time progress
```

### 4. Admin Cancels Job
```
POST /api/crawlers/{id}/stop
→ Job cancelled in Redis
→ Worker stops gracefully
```

## Monitoring

### Check Queue Status

```python
from redis import Redis
from rq import Queue

redis_conn = Redis.from_url('redis://localhost:6379/0')
queue = Queue('crawlers', connection=redis_conn)

print(f"Jobs in queue: {len(queue)}")
print(f"Failed jobs: {len(queue.failed_job_registry)}")
```

### View Worker Status

```bash
# In Python console
from redis import Redis
from rq import Worker

redis_conn = Redis.from_url('redis://localhost:6379/0')
workers = Worker.all(redis_conn)

for worker in workers:
    print(f"Worker: {worker.name}")
    print(f"State: {worker.state}")
    print(f"Current job: {worker.get_current_job()}")
```

### RQ Dashboard (Optional)

Install RQ Dashboard for web UI:
```bash
pip install rq-dashboard
rq-dashboard --redis-url redis://localhost:6379/0
```

Access at: http://localhost:9181

## Production Deployment

### Server Architecture (2-Server Setup)

**Server 1: API + Frontend**
- Flask API (Gunicorn with 4 workers)
- Next.js Frontend
- Nginx reverse proxy

**Server 2: Database + Workers**
- PostgreSQL
- Redis
- RQ Workers (2-3 workers for crawlers)

### Environment Variables

```bash
REDIS_URL=redis://localhost:6379/0
```

### Systemd Service (Alternative to Supervisor)

Create `/etc/systemd/system/rq-worker@.service`:

```ini
[Unit]
Description=RQ Worker %i
After=network.target redis.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/backend
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python /path/to/backend/worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable rq-worker@{1..2}.service
sudo systemctl start rq-worker@{1..2}.service
```

## Troubleshooting

### Jobs Not Processing

1. Check if workers are running:
```bash
ps aux | grep worker.py
```

2. Check Redis connection:
```bash
redis-cli ping
```

3. Check worker logs:
```bash
tail -f /var/log/rq-worker.log
```

### Job Failures

```python
# View failed jobs
from rq import Queue
from redis import Redis

redis_conn = Redis.from_url('redis://localhost:6379/0')
queue = Queue('crawlers', connection=redis_conn)
failed = queue.failed_job_registry

for job_id in failed.get_job_ids():
    job = queue.fetch_job(job_id)
    print(f"Job {job_id}: {job.exc_info}")
```

### High Memory Usage

- Limit concurrent jobs: Use fewer workers
- Set job timeout: `job_timeout='2h'`
- Monitor with: `htop` or `free -h`

## API Changes

### New Endpoints

- `GET /api/crawlers/{id}/job-status` - Get real-time job status from Redis
- Job ID returned in start response for tracking

### Response Changes

Start crawler now returns:
```json
{
  "message": "Crawler job started",
  "crawler_id": "uuid",
  "job_id": "rq-job-id",
  "run_type": "manual"
}
```

## Migration from Old System

The old threading-based system is replaced. No migration needed for data, just:

1. Install `rq` package
2. Start workers
3. Use updated endpoints

Old crawlers will still show in database, but new runs use RQ.

## Performance

| Metric | Before (Threading) | After (RQ) |
|--------|-------------------|------------|
| API blocking | Yes (entire duration) | No (instant response) |
| Concurrent crawlers | 1-2 (blocks workers) | 5+ (dedicated workers) |
| Recovery on crash | None | Auto-retry |
| Cancellation | Delayed | Instant |
| Monitoring | Database polling | Redis (fast) |

## Next Steps

Future enhancements:
- Scheduled crawlers (cron-like)
- Priority queue for urgent crawlers
- Email notifications on completion
- Retry failed batches automatically
