# Decodo Proxy Integration Guide

## ✅ Configuration Complete

Your Zalando scraper is now configured to use **10 Decodo proxy endpoints** through `gate.decodo.com` (ports 10001-10010).

## 🔄 **Automatic Proxy Rotation**

The scraper will **automatically enable proxy rotation** when:
1. ✅ `proxies.json` exists in `backend/scrapers/`
2. ✅ Scraper is triggered from the admin panel

**No manual configuration needed!** Just ensure `proxies.json` is in place.

## 🚀 Quick Start

### 1. Test Your Proxies

Before scraping, verify your Decodo proxies are working:

```bash
cd backend/scrapers
python test_decodo_proxies.py
```

This will test all 10 proxies and show you:
- ✅ Which proxies are working
- ⏱️ Response times
- ❌ Any connection errors

### 2. Run Detailed Test (Optional)

For troubleshooting a specific proxy with browser visible:

```bash
python test_decodo_proxies.py --detailed
```

### 3. Use from Admin Panel (Automatic)

When you start the scraper from the admin panel:
1. ✅ **Automatically detects** `proxies.json`
2. ✅ **Enables proxy rotation** without any configuration
3. ✅ **Rotates through all 10 Decodo proxies**
4. ✅ **Logs proxy statistics** at the end

**No code changes needed!** Just start the crawler from admin.

### 4. Use Programmatically (Manual)

If calling directly from code:

```python
from scrapers.zalando_playwright import ZalandoScraper

# Option 1: Auto-detect (recommended)
scraper = ZalandoScraper()  # Automatically uses proxies.json if it exists

# Option 2: Explicitly enable
scraper = ZalandoScraper(enable_proxy_rotation=True)

# Option 3: Explicitly disable (ignore proxies.json)
scraper = ZalandoScraper(enable_proxy_rotation=False)

# Scrape
results = await scraper.scrape(max_pages=10)
```

## 📋 Your Decodo Configuration

- **Proxy Host:** gate.decodo.com
- **Ports:** 10001-10010 (10 endpoints)
- **Username:** spg27o7rlx
- **Protocol:** HTTP
- **Total Proxies:** 10

## 🔄 How Rotation Works

1. **Round-robin selection** - Cycles through all 10 proxies
2. **Health tracking** - Monitors success/failure rates per proxy
3. **Automatic failover** - Switches proxy on HTTP 403 or timeouts
4. **Smart selection** - Prioritizes proxies with higher success rates

## ⚙️ Tuning for Decodo

Decodo proxies are residential, so they're less likely to be blocked. You can adjust timing:

```python
# In zalando_playwright.py, current settings:
MIN_PRODUCT_DELAY = 3   # seconds between products
MAX_PRODUCT_DELAY = 8
MIN_PAGE_DELAY = 10     # seconds between pages
MAX_PAGE_DELAY = 20

# With good residential proxies, you might be able to go faster:
MIN_PRODUCT_DELAY = 2
MAX_PRODUCT_DELAY = 5
MIN_PAGE_DELAY = 5
MAX_PAGE_DELAY = 10
```

But start conservative and monitor the logs!

## 📊 Monitoring

During scraping, watch for these in the logs:

```
🌐 Using proxy: gate.decodo.com:10001         ← Proxy in use
✅ Scraped Product #50                         ← Success
🚫 HTTP 403 Forbidden                          ← Blocking detected
🔄 Rotating to new proxy                       ← Automatic failover
```

At the end, you'll see statistics:

```
============================================================
📊 Proxy Rotation Statistics
============================================================
Total Proxies: 10
Active Proxies: 9
Total Requests: 500
Successful: 485
Failed: 15
Success Rate: 97.00%
Rotations: 12
============================================================
```

## 🔧 Troubleshooting

### Problem: All proxies fail test

**Check:**
1. Is your Decodo subscription active?
2. Are you connected to the internet?
3. Did you copy credentials correctly?

**Test manually:**
```bash
curl -x http://spg27o7rlx:~zA4wHts7JfgtSq1g1@gate.decodo.com:10001 https://api.ipify.org
```

### Problem: Some proxies work, others don't

**Normal behavior** - Proxies can have temporary issues. The scraper will:
- Skip failed proxies automatically
- Use only working proxies
- Retry failed proxies after 5 minutes

### Problem: Still getting HTTP 403

**Solutions:**
1. Increase delays between requests
2. Check if you're hitting Decodo's request limits
3. Verify proxies are residential (not datacenter)
4. Contact Decodo support to check your account status

### Problem: Slow scraping

**Check:**
- Proxy response times in test results
- Network latency to gate.decodo.com
- Decodo bandwidth limits

## 🔒 Security

⚠️ **Important:**

1. **proxies.json is in .gitignore** - Your credentials won't be committed
2. **Never share proxies.json** - Contains your Decodo credentials
3. **Rotate passwords regularly** - Best practice for security

## 💰 Decodo Limits

Check your Decodo plan for:
- **Bandwidth limits** (GB per month)
- **Request limits** (requests per minute)
- **Concurrent connections** (how many simultaneous requests)

Your scraper uses 1 connection at a time, so this shouldn't be an issue.

## 📈 Expected Performance

With 10 Decodo residential proxies:
- **Products per hour:** ~200-400 (with conservative timing)
- **Daily capacity:** ~5,000-10,000 products
- **Success rate:** 90-95% (normal for residential proxies)

## 🆘 Need Help?

1. **Run proxy test first:** `python test_decodo_proxies.py`
2. **Check logs** for detailed error messages
3. **Contact Decodo support** if all proxies fail
4. **Adjust timing** if getting blocked

## ✅ Next Steps

1. ✅ Test proxies: `python test_decodo_proxies.py`
2. ✅ Start with small batch: `max_pages=2`
3. ✅ Monitor logs for issues
4. ✅ Scale up gradually: `max_pages=10`, then `max_pages=50`, etc.
5. ✅ Check Decodo dashboard for usage stats

---

**Ready to scrape!** 🚀

Run the test script first, then start scraping with confidence.
