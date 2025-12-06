# Zalando Scraper - Proxy Rotation System

## Overview

The Zalando scraper now includes a sophisticated proxy rotation system to avoid IP blocking and rate limiting. The system automatically rotates proxies, tracks their performance, and implements intelligent failover mechanisms.

## Features

### 1. **Automatic Proxy Rotation**
- Round-robin rotation among active proxies
- Intelligent proxy selection based on success rate and response time
- Automatic failover on failures

### 2. **Health Tracking**
- Success/failure rate monitoring per proxy
- Response time tracking
- Consecutive failure detection
- Automatic proxy deactivation after 5 consecutive failures

### 3. **Rate Limiting Protection**
- Random delays between products (3-8 seconds)
- Random delays between pages (10-20 seconds)
- Exponential backoff on failures
- Human-like browsing patterns

### 4. **Error Detection & Recovery**
- HTTP 403 detection (rate limiting/blocking)
- Timeout detection
- Automatic browser restart with new proxy
- Detailed logging of failures

## Configuration

### Option 1: JSON Configuration File

Create `backend/scrapers/proxies.json`:

```json
{
  "proxies": [
    {
      "host": "proxy1.example.com",
      "port": 8080,
      "username": "your_username",
      "password": "your_password",
      "protocol": "http"
    },
    {
      "host": "proxy2.example.com",
      "port": 8080,
      "username": "your_username",
      "password": "your_password",
      "protocol": "http"
    },
    {
      "host": "socks-proxy.example.com",
      "port": 1080,
      "protocol": "socks5"
    }
  ]
}
```

### Option 2: Programmatic Configuration

```python
from scrapers.zalando_playwright import ZalandoScraper

# Define proxy list
proxy_list = [
    {
        "host": "proxy1.example.com",
        "port": 8080,
        "username": "user",
        "password": "pass",
        "protocol": "http"
    },
    {
        "host": "proxy2.example.com",
        "port": 8080,
        "protocol": "http"  # No auth
    }
]

# Initialize scraper with proxy rotation
scraper = ZalandoScraper(
    base_url="https://www.zalando.nl/schoenen",
    proxy_list=proxy_list,
    enable_proxy_rotation=True
)

# Run scraper
results = await scraper.scrape(max_pages=10)
```

## Proxy Protocols

The system supports two proxy protocols:

1. **HTTP/HTTPS Proxies** (`protocol: "http"`)
   - Most common proxy type
   - Good for web scraping
   - Supports authentication

2. **SOCKS5 Proxies** (`protocol: "socks5"`)
   - Lower-level protocol
   - Better for bypassing restrictions
   - Can handle any TCP/UDP traffic

## Usage Examples

### Basic Usage (No Proxies)

```python
from scrapers.zalando_playwright import ZalandoScraper

scraper = ZalandoScraper()
results = await scraper.scrape(max_pages=5)
```

### With Proxy Rotation (JSON Config)

```bash
# Create proxies.json in backend/scrapers/
cat > backend/scrapers/proxies.json << 'EOF'
{
  "proxies": [
    {"host": "proxy1.com", "port": 8080},
    {"host": "proxy2.com", "port": 8080}
  ]
}
EOF
```

```python
scraper = ZalandoScraper(enable_proxy_rotation=True)
results = await scraper.scrape(max_pages=10)
```

### With Custom Proxy List

```python
my_proxies = [
    {"host": "10.0.0.1", "port": 3128, "protocol": "http"},
    {"host": "10.0.0.2", "port": 1080, "protocol": "socks5"},
]

scraper = ZalandoScraper(
    proxy_list=my_proxies,
    enable_proxy_rotation=True
)
results = await scraper.scrape(max_pages=20)
```

## How It Works

### 1. Initial Setup
```
┌─────────────────┐
│ Initialize      │
│ ProxyManager    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Load proxies    │
│ from config     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Select first    │
│ proxy (best)    │
└─────────────────┘
```

### 2. Normal Operation
```
┌──────────────────┐
│ Scrape product   │
└────────┬─────────┘
         │
    ┌────▼─────┐
    │ Success? │
    └────┬─────┘
         │
    ┌────▼───────────┐
    │ Yes: Record     │
    │ success stats   │
    └─────────────────┘
```

### 3. Failure & Recovery
```
┌──────────────────┐
│ HTTP 403 or      │
│ Timeout detected │
└────────┬─────────┘
         │
    ┌────▼────────────┐
    │ Record failure  │
    │ for proxy       │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │ Rotate to next  │
    │ proxy           │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │ Restart browser │
    │ with new proxy  │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │ Exponential     │
    │ backoff delay   │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │ Retry request   │
    └─────────────────┘
```

## Timing & Delays

The scraper implements several timing strategies:

| Action | Delay Range | Purpose |
|--------|-------------|---------|
| Between products | 3-8 seconds | Simulate human browsing |
| Between pages | 10-20 seconds | Avoid rate limiting |
| After HTTP 403 | Exponential (5-60s) | Give time for IP cooldown |
| Browser restart | 5 seconds | Ensure clean state |

## Monitoring & Statistics

At the end of each scraping session, detailed statistics are logged:

```
============================================================
📊 Proxy Rotation Statistics
============================================================
Total Proxies: 3
Active Proxies: 2
Total Requests: 387
Successful: 360
Failed: 27
Success Rate: 93.02%
Rotations: 5
============================================================

Proxy proxy1.example.com:8080 - Success: 150, Failed: 10, Rate: 93.75%, Avg Time: 2.34s
Proxy proxy2.example.com:8080 - Success: 210, Failed: 17, Rate: 92.51%, Avg Time: 2.89s
```

## Best Practices

### 1. **Use Multiple Proxies**
- Minimum: 3-5 proxies for basic rotation
- Recommended: 10+ proxies for large-scale scraping
- Mix residential and datacenter proxies

### 2. **Choose Quality Proxies**
- Avoid free proxies (unreliable)
- Use dedicated or semi-dedicated proxies
- Prefer proxies in the target country (Netherlands for Zalando.nl)

### 3. **Configure Delays Appropriately**
```python
# In zalando_playwright.py, adjust these constants:
MIN_PRODUCT_DELAY = 5  # Increase for more caution
MAX_PRODUCT_DELAY = 12
MIN_PAGE_DELAY = 15
MAX_PAGE_DELAY = 30
```

### 4. **Monitor Logs**
Watch for these warning signs:
- Consecutive HTTP 403 errors
- High failure rates (>20%)
- Proxy deactivations
- Timeout patterns

## Proxy Providers (Recommended)

Popular proxy providers for web scraping:

1. **Bright Data** (formerly Luminati)
   - High-quality residential proxies
   - Expensive but very reliable

2. **Oxylabs**
   - Good for e-commerce scraping
   - Netherlands proxy locations available

3. **Smartproxy**
   - Affordable residential proxies
   - Good for medium-scale scraping

4. **ProxyMesh**
   - Rotating proxy service
   - Easy integration

5. **ScraperAPI**
   - Managed proxy rotation
   - Built-in JavaScript rendering

## Troubleshooting

### Problem: All proxies get deactivated

**Solution:**
- Proxies are likely blacklisted by Zalando
- Get fresh proxy IPs
- Increase delays between requests
- Use residential proxies instead of datacenter

### Problem: High failure rate

**Solution:**
- Check proxy authentication credentials
- Verify proxy protocol (http vs socks5)
- Test proxies manually:
  ```bash
  curl -x http://username:password@proxy:port https://www.zalando.nl
  ```

### Problem: Slow scraping

**Solution:**
- Reduce delays (but stay above 3 seconds between products)
- Use faster proxies
- Check proxy response times in statistics

### Problem: Still getting blocked

**Solution:**
- Increase `MIN_PRODUCT_DELAY` and `MIN_PAGE_DELAY`
- Add more proxies to rotation
- Use residential proxies
- Consider using proxy with session rotation

## Advanced Configuration

### Custom ProxyInfo

```python
from scrapers.zalando_playwright import ProxyInfo, ProxyManager

# Create custom proxy with specific settings
proxy = ProxyInfo(
    host="custom-proxy.com",
    port=8080,
    username="user",
    password="pass",
    protocol="http"
)

# Check proxy health
if not proxy.should_rest():
    print(f"Proxy is ready: {proxy.success_rate:.2%} success rate")
```

### Manual Proxy Management

```python
from scrapers.zalando_playwright import ProxyManager

# Initialize manager
manager = ProxyManager(enable_rotation=True)

# Get proxy statistics
stats = manager.get_stats()
print(f"Active proxies: {stats['active_proxies']}")

# Get active proxies
active = manager.get_active_proxies()
for proxy in active:
    print(f"{proxy.host}:{proxy.port} - {proxy.success_rate:.2%}")
```

## Environment Variables

You can also configure proxies via environment variables:

```bash
# Set proxy list as JSON
export ZALANDO_PROXIES='[{"host":"proxy1.com","port":8080},{"host":"proxy2.com","port":8080}]'

# Enable proxy rotation
export ENABLE_PROXY_ROTATION=true
```

## Security Notes

⚠️ **Important Security Considerations:**

1. **Never commit `proxies.json` to git**
   - Already added to `.gitignore`
   - Contains sensitive credentials

2. **Use environment variables for production**
   ```python
   import os
   import json
   
   proxy_list = json.loads(os.getenv('PROXY_LIST', '[]'))
   ```

3. **Rotate proxy credentials regularly**
   - Change passwords monthly
   - Monitor for unauthorized usage

4. **Use HTTPS for sensitive data**
   - Proxies can see unencrypted traffic
   - Trust your proxy provider

## License & Compliance

⚠️ **Legal Notice:**

- Always comply with website Terms of Service
- Respect robots.txt
- Implement rate limiting
- Do not overload target servers
- Use scraping for legitimate purposes only

This proxy rotation system is designed to be respectful of server resources while providing reliable data collection capabilities.
