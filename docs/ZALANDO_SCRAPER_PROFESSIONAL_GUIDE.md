# Professional Zalando Scraper - Deployment Guide

## 🎯 Overview

This guide explains how to deploy and configure the professional-grade Zalando scraper capable of scraping thousands of products without detection.

---

## 🔧 Key Features

### ✅ Anti-Detection Measures
- **Proxy Rotation**: Automatic rotation with health tracking
- **Session Restarts**: Periodic browser restarts to reset fingerprints
- **Human-like Delays**: Randomized delays between requests (8-15s products, 30-60s pages)
- **Stealth Mode**: Advanced browser fingerprint masking
- **Request Blocking**: Blocks telemetry/tracking to reduce footprint

### ✅ Scalability Features
- **Batch Processing**: Real-time batch insertion to database
- **Uniqueness Checking**: Fuzzy name + brand matching (90% threshold)
- **Error Recovery**: Automatic retry with exponential backoff
- **Proxy Failover**: Automatic proxy rotation on 403/timeout
- **Statistics Tracking**: Detailed proxy & success rate logging

---

## 📋 Prerequisites

### 1. Proxy Service (Required for Large-Scale Scraping)

**Recommended Providers:**
- **Bright Data** (formerly Luminati) - Best for e-commerce
- **Oxylabs** - Enterprise-grade residential proxies
- **Smartproxy** - Good balance of price/performance
- **IPRoyal** - Affordable residential IPs

**Proxy Type Recommendations:**
- ✅ **Residential Proxies** - Best for avoiding detection
- ⚠️ **Datacenter Proxies** - Cheaper but higher block rate
- 💰 **Mobile Proxies** - Most expensive, highest success rate

**Recommended Setup:**
- **Quantity**: 10-20 rotating residential IPs
- **Location**: Netherlands-based IPs (to match Zalando.nl)
- **Type**: HTTP or SOCKS5 with authentication
- **Rotation**: Sticky sessions (5-10 min session persistence)

### 2. Server Requirements

**Minimum:**
- CPU: 4 cores
- RAM: 8 GB
- Disk: 50 GB SSD
- Network: 100 Mbps

**Recommended:**
- CPU: 8 cores
- RAM: 16 GB
- Disk: 100 GB SSD
- Network: 1 Gbps

---

## 🚀 Setup Instructions

### Step 1: Configure Proxies

1. **Copy the proxy template:**
```bash
cd backend/scrapers
cp proxies.json.example proxies.json
```

2. **Edit proxies.json with your proxy credentials:**
```json
{
  "proxies": [
    {
      "host": "proxy1.yourdomain.com",
      "port": 8080,
      "username": "your_username",
      "password": "your_password",
      "protocol": "http"
    },
    {
      "host": "proxy2.yourdomain.com",
      "port": 8080,
      "username": "your_username",
      "password": "your_password",
      "protocol": "http"
    }
  ]
}
```

3. **Test your proxies:**
```bash
curl -x http://username:password@proxy1.yourdomain.com:8080 https://www.zalando.nl
```

### Step 2: Configure Environment Variables

Add these to your `.env.production` file:

```bash
# Zalando Scraper Configuration
ZALANDO_MIN_PRODUCT_DELAY=8          # Min seconds between products
ZALANDO_MAX_PRODUCT_DELAY=15         # Max seconds between products
ZALANDO_MIN_PAGE_DELAY=30            # Min seconds between pages
ZALANDO_MAX_PAGE_DELAY=60            # Max seconds between pages
ZALANDO_PROXY_ROTATION_INTERVAL=15   # Rotate proxy every N products
ZALANDO_SESSION_RESTART_INTERVAL=50  # Restart browser every N products
ZALANDO_MAX_RETRIES_PER_PRODUCT=3    # Max retries per product
ZALANDO_ENABLE_PROXIES=true          # Enable proxy rotation
```

### Step 3: Update Crawler Configuration

1. **Update `backend/core/config/config.py` crawler settings:**

```python
# Minimum items before uniqueness check kicks in
CRAWLER_MIN_ITEMS_BEFORE_STOP = {
    'Zalando': 1000,     # Don't stop Zalando until 1000 items scraped
    'Default': 200
}

# Uniqueness thresholds per crawler
CRAWLER_UNIQUENESS_THRESHOLDS = {
    'Zalando': 15.0,     # Lower threshold for Zalando (more tolerance)
    'Default': 30.0
}

# Fuzzy name matching threshold
FUZZY_MATCH_THRESHOLD = 0.90  # 90% similarity for name + brand matching

# Batch size for processing
BATCH_SIZE = 300  # Process 300 items at once for efficiency
```

### Step 4: Deploy Backend Services

```bash
# On backend server (10.110.0.6)
ssh keyadmin@10.110.0.6
cd /opt/sarapps

# Pull latest code
git pull origin main

# Stop services
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production stop backend worker

# Rebuild with latest changes
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production build --no-cache backend worker

# Start services
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production up -d backend worker

# Monitor logs
sudo docker logs -f stip_worker
```

---

## 🎮 Usage

### Starting a Crawler

1. **Via Admin Panel:**
   - Go to `https://stip.sarapps.com/admin`
   - Login with admin credentials
   - Navigate to "Crawlers"
   - Select "Zalando" crawler
   - Click "Start Crawler"

2. **Monitor Progress:**
```bash
# Watch worker logs for real-time updates
sudo docker logs -f stip_worker | grep -E "Fuzzy|Progress|Uniqueness|Proxy|Product #"
```

### Expected Output

```
🌐 Proxy rotation enabled with 10 proxies
✅ Loaded Zalando scraper configuration from Config
   Product delays: 8-15s
   Page delays: 30-60s
   Proxy rotation: every 15 products
   Session restart: every 50 products
🎯 Base URL: https://www.zalando.nl/schoenen

📄 Page 1: Found 228 product links
  Product 1 (Page 1:1/228): Scraping...
✅ Scraped Product #1:
   Brand: Nike Sportswear
   Product Name: AIR MAX 90 - Sneakers laag
   Product URL: https://www.zalando.nl/nike-...
   Sole Image URL: https://img01.ztat.net/...

🔄 Proactive proxy rotation after 15 products
✅ Switched to proxy proxy2.example.com:8080

🔄 Periodic session restart after 50 products (anti-fingerprinting)
✅ Session restarted with proxy proxy3.example.com:8080

📊 Progress: 100/1000 | Uniqueness: 85.0% | Batch: 20 items
✅ Fuzzy match found: Nike Air Max 90 vs Nike Air Max 90 White (98.5% similar)
```

---

## 📊 Monitoring & Troubleshooting

### Check Crawler Status

```bash
# View current crawlers
sudo docker exec -it stip_backend flask crawlers list

# Check specific crawler stats
sudo docker exec -it stip_backend flask crawlers stats <crawler_id>
```

### Common Issues

#### Issue 1: Still Getting 403 Errors

**Causes:**
- Proxies not configured or invalid
- Too aggressive scraping (delays too short)
- Proxy pool too small

**Solutions:**
```bash
# Increase delays
export ZALANDO_MIN_PRODUCT_DELAY=12
export ZALANDO_MAX_PRODUCT_DELAY=20
export ZALANDO_MIN_PAGE_DELAY=45
export ZALANDO_MAX_PAGE_DELAY=90

# Restart services
sudo docker-compose -f docker-compose.backend.yml --env-file .env.production restart backend worker
```

#### Issue 2: Proxies Not Working

**Debug:**
```bash
# Check proxy configuration
cat backend/scrapers/proxies.json

# Test proxy manually
curl -x http://username:password@proxy.com:8080 https://www.zalando.nl

# Check worker logs for proxy errors
sudo docker logs stip_worker | grep -i proxy
```

#### Issue 3: Low Uniqueness Causing Early Stop

**Solution:**
- Adjust `CRAWLER_MIN_ITEMS_BEFORE_STOP` to higher value (e.g., 2000)
- Lower `CRAWLER_UNIQUENESS_THRESHOLDS` for more tolerance
- Check duplicate detection logic is working correctly

```bash
# Monitor uniqueness checks
sudo docker logs -f stip_worker | grep -E "Fuzzy|Duplicate|Uniqueness"
```

#### Issue 4: Crawler Stops After ~360 Products

**Causes:**
- IP ban from Zalando
- Proxy blacklisted
- Session fingerprinting detected

**Solutions:**
1. Add more diverse proxies (10-20 minimum)
2. Increase session restart frequency:
   ```bash
   export ZALANDO_SESSION_RESTART_INTERVAL=30  # Restart every 30 products
   ```
3. Use residential proxies instead of datacenter
4. Increase delays to be more human-like

---

## 🔐 Security Best Practices

### 1. Proxy Credentials
```bash
# Never commit proxies.json to git
echo "backend/scrapers/proxies.json" >> .gitignore

# Set restrictive permissions
chmod 600 backend/scrapers/proxies.json
```

### 2. Rate Limiting
- **Start conservative**: High delays initially, then optimize
- **Monitor success rates**: Aim for >90% success rate
- **Rotate aggressively**: Change proxy every 15-20 products

### 3. Error Handling
- **Max retries**: 3 attempts per product
- **Exponential backoff**: Increase delays on failures
- **Proxy rotation on errors**: Switch proxy on 403/timeout

---

## 📈 Performance Optimization

### For Maximum Speed (with good proxies)

```bash
# Aggressive settings (requires excellent proxy pool)
ZALANDO_MIN_PRODUCT_DELAY=5
ZALANDO_MAX_PRODUCT_DELAY=10
ZALANDO_MIN_PAGE_DELAY=20
ZALANDO_MAX_PAGE_DELAY=40
ZALANDO_PROXY_ROTATION_INTERVAL=10
ZALANDO_SESSION_RESTART_INTERVAL=30
```

### For Maximum Stealth (avoid detection)

```bash
# Conservative settings (safer, slower)
ZALANDO_MIN_PRODUCT_DELAY=15
ZALANDO_MAX_PRODUCT_DELAY=25
ZALANDO_MIN_PAGE_DELAY=60
ZALANDO_MAX_PAGE_DELAY=120
ZALANDO_PROXY_ROTATION_INTERVAL=20
ZALANDO_SESSION_RESTART_INTERVAL=40
```

### Recommended Balanced Settings

```bash
# Good balance of speed and stealth
ZALANDO_MIN_PRODUCT_DELAY=8
ZALANDO_MAX_PRODUCT_DELAY=15
ZALANDO_MIN_PAGE_DELAY=30
ZALANDO_MAX_PAGE_DELAY=60
ZALANDO_PROXY_ROTATION_INTERVAL=15
ZALANDO_SESSION_RESTART_INTERVAL=50
```

---

## 📊 Expected Results

### With Proper Configuration

- **Success Rate**: >90%
- **Products/Hour**: 200-400 (depending on delays)
- **Total Catalog**: 10,000-15,000 shoes from Zalando
- **Run Time**: 30-75 hours for full catalog
- **Proxy Usage**: ~500-1000 requests per proxy

### Cost Estimate (for 10,000 products)

**Proxy Costs:**
- Residential proxies: $50-150/month (10-20 IPs)
- Datacenter proxies: $10-30/month (higher risk)

**Server Costs:**
- Cloud VPS: $40-80/month
- Or use existing infrastructure

**Total**: ~$90-230/month for professional scraping setup

---

## 🎓 Advanced Tips

### 1. Time-Based Scraping
- **Best times**: Off-peak EU hours (late night/early morning CET)
- **Avoid**: Peak shopping hours (12pm-9pm CET)

### 2. Proxy Pool Management
- Rotate proxies that succeed
- Rest proxies after failures (5 min cooldown)
- Track proxy performance and prioritize best ones

### 3. Session Management
- Restart browser every 50 products (resets fingerprint)
- Clear cookies/cache between sessions
- Vary user agents (built-in)

### 4. Error Recovery
- Log all 403s for analysis
- Implement circuit breaker for failing proxies
- Automatic crawler resume on failure

---

## 📞 Support

### Logs Location
- **Worker logs**: `sudo docker logs stip_worker`
- **Backend logs**: `sudo docker logs stip_backend`
- **Proxy stats**: Check worker logs for "Proxy Rotation Statistics"

### Debugging Commands
```bash
# Check crawler status
sudo docker exec -it stip_backend flask crawlers list

# View proxy stats in logs
sudo docker logs stip_worker | grep "Proxy Rotation Statistics" -A 15

# Monitor real-time scraping
sudo docker logs -f stip_worker | grep -E "Product #|Fuzzy|Proxy"

# Check database for scraped items
sudo docker exec -it stip_backend flask db query "SELECT COUNT(*) FROM sole_images WHERE source='zalando'"
```

---

## ✅ Checklist

Before starting a large-scale scrape:

- [ ] Proxies configured in `backend/scrapers/proxies.json`
- [ ] Proxy authentication tested
- [ ] Environment variables set in `.env.production`
- [ ] Backend and worker services rebuilt
- [ ] Services running healthy
- [ ] Test crawl with max_pages=1 first
- [ ] Monitor logs for 403 errors
- [ ] Adjust delays if needed
- [ ] Start full crawl
- [ ] Monitor progress (uniqueness, proxy stats)

---

## 🎉 Expected Outcome

With proper configuration:
- ✅ Scrape 10,000+ Zalando products
- ✅ 90%+ success rate
- ✅ No IP bans
- ✅ Fuzzy duplicate detection working
- ✅ Automatic batch insertion to database
- ✅ Real-time progress monitoring

**Good luck and happy scraping! 🚀**

