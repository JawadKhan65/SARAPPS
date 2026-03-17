# Fix: Worker Memory Crash at ~184 Products

## 🔍 Problem Summary

**Your logs show:**
```
01:54:06 Worker worker-1: killed horse pid 112
01:54:06 Work-horse terminated unexpectedly
```

**Root Cause**: Memory exhaustion - Playwright browser accumulating memory, worker killed by OOM (Out of Memory) killer.

---

## ✅ Fixes Applied

### 1. **Added Garbage Collection**
- Imported Python `gc` module
- Added `gc.collect()` after every browser restart
- Added `gc.collect()` after proxy rotation
- Forces immediate memory cleanup

### 2. **Reduced Session Restart Interval**
- **Before**: Browser restarted every 50 products
- **After**: Browser restarted every **30 products**
- More frequent restarts = less memory accumulation

### 3. **Enhanced Logging**
- Now logs: `"🧹 Memory cleanup: garbage collection completed"`
- Helps monitor when cleanup happens

---

## 🚀 Deploy the Fix

### On Your Local Machine:
```bash
git add .
git commit -m "Fix memory crash: add GC, reduce session interval to 30"
git push origin main
```

### On Backend Server:
```bash
ssh keyadmin@10.110.0.6
cd /opt/sarapps

# Pull changes
git pull origin main

# Rebuild and restart
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production stop worker
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production build --no-cache worker
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production up -d worker

# Monitor
sudo docker logs -f stip_worker | grep -E "Product #|Memory cleanup|Session restart"
```

---

## 📊 What You'll See Now

### Good Signs ✅
```
✅ Scraped Product #30
🔄 Periodic session restart after 30 products (anti-fingerprinting + memory cleanup)
🧹 Memory cleanup: garbage collection completed
✅ Session restarted with proxy gate.smartproxy.com:7000

✅ Scraped Product #60
🔄 Periodic session restart after 60 products
🧹 Memory cleanup: garbage collection completed

✅ Scraped Product #90
... continues past 184 without crash! ✅
```

### Expected Performance
- **Before**: Crashed at ~184 products
- **After**: Should scrape 300+, 500+, 1000+ products continuously

---

## 🔍 Monitor Memory Usage

### Check Memory in Real-Time
```bash
# Watch memory usage every 2 seconds
watch -n 2 'sudo docker stats stip_worker --no-stream'
```

**What to look for:**
- **MEM USAGE** should stay below 1.5-2GB
- Memory should **drop** after each "Session restart" log
- If it keeps growing > 2.5GB, we need more aggressive cleanup

### Check Worker Logs for Crashes
```bash
# Watch for crashes
sudo docker logs -f stip_worker | grep -E "killed|terminated|OOM"
```

**If you see:**
- `killed horse` = Memory crash again (need more fixes)
- `OOM` = Out of memory
- Nothing = Good! ✅

---

## 🛠️ Additional Fixes (if still crashing)

### Option A: Increase Docker Memory Limit

```bash
# Edit docker-compose
nano docker-compose.backend.yml
```

Add to worker service:
```yaml
worker:
  # ... existing config ...
  deploy:
    resources:
      limits:
        memory: 4G         # Allow up to 4GB
      reservations:
        memory: 2G         # Reserve 2GB minimum
```

Restart:
```bash
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production up -d worker
```

### Option B: Further Reduce Session Interval

If still crashing at ~180-200 products, restart even more frequently:

```bash
# Edit .env.production
nano .env.production
```

Change:
```bash
ZALANDO_SESSION_RESTART_INTERVAL=20  # Restart every 20 products instead of 30
```

Restart:
```bash
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production restart worker
```

### Option C: Add Memory Monitoring to Code

I can add automatic memory monitoring that logs RAM usage and triggers cleanup when it gets high. Let me know if needed.

---

## 📈 Test Scrape

### Start a New Crawler
1. Go to admin panel: `https://stip.sarapps.com/admin`
2. Start Zalando crawler
3. Watch logs:

```bash
sudo docker logs -f stip_worker | grep -E "Product #|Memory|Session|killed"
```

### Checkpoints to Monitor

| Products | What Should Happen |
|----------|-------------------|
| **30** | 🔄 Session restart + memory cleanup |
| **60** | 🔄 Session restart + memory cleanup |
| **90** | 🔄 Session restart + memory cleanup |
| **120** | 🔄 Session restart + memory cleanup |
| **150** | 🔄 Session restart + memory cleanup |
| **180** | 🔄 Session restart + memory cleanup |
| **184** | ❌ Previously crashed here - should now continue! ✅ |
| **200+** | ✅ Should keep going! |
| **500+** | ✅ Target reached! |
| **1000+** | 🎯 Success! |

---

## 🎯 Success Criteria

- [ ] Worker doesn't crash at ~184 products
- [ ] Memory usage stays below 2GB
- [ ] Logs show "Memory cleanup" every 30 products
- [ ] Scraper continues past 200, 500, 1000+ products
- [ ] No "killed horse" or "OOM" errors in logs

---

## 📞 Quick Commands

```bash
# Deploy fix
cd /opt/sarapps && git pull && \
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production build --no-cache worker && \
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production up -d worker

# Monitor memory
watch -n 2 'sudo docker stats stip_worker --no-stream'

# Monitor scraping
sudo docker logs -f stip_worker | grep "Product #"

# Check for crashes
sudo docker logs stip_worker | grep -E "killed|terminated" | tail -20

# Restart if needed
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production restart worker
```

---

## 🎉 Expected Outcome

**Before Fix:**
- ❌ Crashed at 184 products
- ❌ "Work-horse terminated unexpectedly"
- ❌ Had to manually restart

**After Fix:**
- ✅ Scrapes 500+ products continuously
- ✅ Memory cleaned up every 30 products
- ✅ No crashes
- ✅ Can reach 10,000+ products

---

**Deploy now and let's monitor the results! 🚀**

