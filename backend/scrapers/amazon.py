import asyncio
import logging
import sys
import json
import random
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import requests
from PIL import Image
from io import BytesIO

from playwright.async_api import async_playwright, Page
from .chromium_config import get_chromium_launch_config
from urllib.parse import urlparse, parse_qs, unquote

# Make sure ml_models package is importable (workspace layout: backend/ml_models)
sys.path.insert(0, str(Path(__file__).parent.parent))
from ml_models.clip_model import SoleDetectorCLIP
from scrapers.base_scraper_mixin import BatchProcessingMixin

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Config
START_URL = "https://www.amazon.nl/s?k=shoes&language=en"
NAV_TIMEOUT = 90000  # Increased to 90s for slow networks with proxies
SELECTOR_TIMEOUT = 15000  # Increased to 15s for lazy-loaded elements
SCROLL_PAUSE = 0.6
IMAGE_DOWNLOAD_TIMEOUT = 10
MAX_DOWNLOAD_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "en-US,en;q=0.9"

# Scraping delays to appear human-like (increased to avoid blocking)
MIN_PRODUCT_DELAY = 25  # minimum seconds between products
MAX_PRODUCT_DELAY = 35  # maximum seconds between products
MIN_PAGE_DELAY = 28  # minimum seconds between pages
MAX_PAGE_DELAY = 35  # maximum seconds between pages
BACKOFF_MULTIPLIER = 2  # exponential backoff multiplier on failures
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds between retries

# Proxy configuration
PROXY_CONFIG_PATH = Path(__file__).parent / "proxies.json"

# Scraping delays to appear human-like
MIN_PRODUCT_DELAY = 3  # minimum seconds between products
MAX_PRODUCT_DELAY = 8  # maximum seconds between products
MIN_PAGE_DELAY = 10  # minimum seconds between pages
MAX_PAGE_DELAY = 20  # maximum seconds between pages
BACKOFF_MULTIPLIER = 2  # exponential backoff multiplier on failures
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds between retries

# Proxy configuration
PROXY_CONFIG_PATH = Path(__file__).parent / "proxies.json"


@dataclass
class ProxyInfo:
    """Data class for tracking proxy statistics and health."""

    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"  # http or socks5

    # Statistics
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    consecutive_failures: int = 0
    is_active: bool = True
    avg_response_time: float = 0.0

    def __post_init__(self):
        """Validate proxy configuration."""
        if not self.host or not self.port:
            raise ValueError("Proxy host and port are required")

    @property
    def url(self) -> str:
        """Get proxy URL string."""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"

    @property
    def server_url(self) -> str:
        """Get proxy server URL for Playwright."""
        return f"{self.protocol}://{self.host}:{self.port}"

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    def record_success(self, response_time: float = 0.0):
        """Record successful request."""
        self.success_count += 1
        self.consecutive_failures = 0
        self.last_used = datetime.now()
        if response_time > 0:
            if self.avg_response_time == 0:
                self.avg_response_time = response_time
            else:
                self.avg_response_time = (self.avg_response_time * 0.7) + (
                    response_time * 0.3
                )

    def record_failure(self):
        """Record failed request."""
        self.failure_count += 1
        self.consecutive_failures += 1
        self.last_failure = datetime.now()

        # Deactivate proxy after too many consecutive failures
        if self.consecutive_failures >= 5:
            self.is_active = False
            logger.warning(
                f"Proxy {self.host}:{self.port} deactivated after {self.consecutive_failures} consecutive failures"
            )

    def should_rest(self, rest_period: int = 300) -> bool:
        """Check if proxy should rest after recent failure."""
        if not self.last_failure:
            return False
        return (datetime.now() - self.last_failure).total_seconds() < rest_period


class ProxyManager:
    """Manages proxy rotation with health tracking and automatic failover."""

    def __init__(
        self, proxy_list: List[Dict[str, Any]] = None, enable_rotation: bool = True
    ):
        """
        Initialize proxy manager.

        Args:
            proxy_list: List of proxy configurations
            enable_rotation: Enable proxy rotation (False = no proxy)
        """
        self.enable_rotation = enable_rotation
        self.proxies: List[ProxyInfo] = []
        self.current_index = 0
        self.rotation_count = 0

        if enable_rotation and proxy_list:
            self._load_proxies(proxy_list)
        elif enable_rotation and PROXY_CONFIG_PATH.exists():
            self._load_from_file()

        if self.enable_rotation and not self.proxies:
            logger.warning("Proxy rotation enabled but no proxies configured")
            self.enable_rotation = False

    def _load_proxies(self, proxy_list: List[Dict[str, Any]]):
        """Load proxies from list."""
        for proxy_config in proxy_list:
            try:
                proxy = ProxyInfo(
                    host=proxy_config["host"],
                    port=proxy_config["port"],
                    username=proxy_config.get("username"),
                    password=proxy_config.get("password"),
                    protocol=proxy_config.get("protocol", "http"),
                )
                self.proxies.append(proxy)
                logger.info(f"Loaded proxy: {proxy.host}:{proxy.port}")
            except Exception as e:
                logger.error(f"Failed to load proxy {proxy_config}: {e}")

    def _load_from_file(self):
        """Load proxies from JSON configuration file."""
        try:
            with open(PROXY_CONFIG_PATH, "r") as f:
                config = json.load(f)
                proxy_list = config.get("proxies", [])
                self._load_proxies(proxy_list)
                logger.info(
                    f"Loaded {len(self.proxies)} proxies from {PROXY_CONFIG_PATH}"
                )
        except Exception as e:
            logger.error(f"Failed to load proxies from file: {e}")

    def get_active_proxies(self) -> List[ProxyInfo]:
        """Get list of currently active proxies."""
        return [p for p in self.proxies if p.is_active and not p.should_rest()]

    def get_next_proxy(self) -> Optional[ProxyInfo]:
        """Get next proxy in rotation."""
        if not self.enable_rotation or not self.proxies:
            return None

        active_proxies = self.get_active_proxies()
        if not active_proxies:
            logger.error("No active proxies available")
            return None

        # Sort by success rate and response time
        active_proxies.sort(
            key=lambda p: (p.success_rate, -p.avg_response_time), reverse=True
        )

        # Use round-robin among top proxies
        proxy = active_proxies[self.current_index % len(active_proxies)]
        self.current_index = (self.current_index + 1) % len(active_proxies)
        self.rotation_count += 1

        logger.debug(
            f"Selected proxy {proxy.host}:{proxy.port} (success rate: {proxy.success_rate:.2%})"
        )
        return proxy

    def rotate_on_failure(self, failed_proxy: ProxyInfo) -> Optional[ProxyInfo]:
        """Rotate to next proxy after failure."""
        if failed_proxy:
            failed_proxy.record_failure()

        # Force rotation to a different proxy
        next_proxy = self.get_next_proxy()
        if next_proxy and next_proxy.host == failed_proxy.host:
            # Try to get a different one
            next_proxy = self.get_next_proxy()

        return next_proxy

    def get_stats(self) -> Dict[str, Any]:
        """Get proxy statistics."""
        active_count = len(self.get_active_proxies())
        total_success = sum(p.success_count for p in self.proxies)
        total_failure = sum(p.failure_count for p in self.proxies)

        return {
            "total_proxies": len(self.proxies),
            "active_proxies": active_count,
            "total_requests": total_success + total_failure,
            "total_success": total_success,
            "total_failures": total_failure,
            "overall_success_rate": total_success / (total_success + total_failure)
            if (total_success + total_failure) > 0
            else 0,
            "rotation_count": self.rotation_count,
        }


# Enhanced stealth initialization script
STEALTH_INIT_SCRIPT = """
// Remove webdriver property
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Add chrome object
Object.defineProperty(window, 'chrome', { 
    value: { 
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {}
    } 
});

// Override plugins
Object.defineProperty(navigator, 'plugins', { 
    get: () => [
        {
            0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
            description: "Portable Document Format",
            filename: "internal-pdf-viewer",
            length: 1,
            name: "Chrome PDF Plugin"
        },
        {
            0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
            description: "Portable Document Format", 
            filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
            length: 1,
            name: "Chrome PDF Viewer"
        }
    ]
});

// Languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'nl-NL', 'nl'] });

// Platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// Hardware concurrency
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

// Device memory
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// Override userAgent
Object.defineProperty(navigator, 'userAgent', {
    get: () => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
});

// Screen properties
if (window.outerWidth === 0) {
    Object.defineProperty(window, 'outerWidth', { get: () => 1280 });
    Object.defineProperty(window, 'outerHeight', { get: () => 800 });
}

try {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
    };
} catch (err) {}
"""


async def random_delay(min_seconds: float, max_seconds: float):
    """Add random delay to simulate human behavior."""
    delay = random.uniform(min_seconds, max_seconds)
    logger.debug(f"⏱️ Waiting {delay:.2f} seconds...")
    await asyncio.sleep(delay)


async def exponential_backoff_delay(
    attempt: int, base_delay: float = 5.0, max_delay: float = 60.0
):
    """Calculate and wait for exponential backoff delay."""
    delay = min(base_delay * (BACKOFF_MULTIPLIER**attempt), max_delay)
    jitter = random.uniform(0, delay * 0.1)
    total_delay = delay + jitter
    logger.warning(f"⏱️ Backoff delay: {total_delay:.2f} seconds (attempt {attempt})")
    await asyncio.sleep(total_delay)


async def launch_browser_with_proxy(playwright, proxy: Optional[ProxyInfo] = None):
    """Launch browser with anti-detection and proxy support."""

    # Anti-detection args
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",
        "--window-position=0,0",
        "--ignore-certifcate-errors",
        "--ignore-certificate-errors-spki-list",
        "--disable-accelerated-2d-canvas",
        "--no-zygote",
        "--window-size=1280,1024",
        "--headless=new",
    ]

    # Add proxy args if provided
    if proxy:
        args.append(f"--proxy-server={proxy.server_url}")
        logger.info(f"🌐 Using proxy: {proxy.host}:{proxy.port}")

    launch_config = {
        "headless": False,
        "args": args,
        "ignore_default_args": ["--enable-automation"],
    }

    browser = await playwright.chromium.launch(**launch_config)

    # Context options
    context_options = {
        "viewport": {"width": 1280, "height": 1024},
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "user_agent": USER_AGENT,
        "extra_http_headers": {
            "Accept-Language": ACCEPT_LANGUAGE,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        },
    }

    # Add proxy authentication if needed
    if proxy and proxy.username and proxy.password:
        context_options["proxy"] = {
            "server": proxy.server_url,
            "username": proxy.username,
            "password": proxy.password,
        }
    elif proxy:
        context_options["proxy"] = {"server": proxy.server_url}

    context = await browser.new_context(**context_options)
    await context.add_init_script(STEALTH_INIT_SCRIPT)

    # Block trackers and ads
    BLOCK_HOSTS = [
        "googleads.g.doubleclick.net",
        "ad.doubleclick.net",
        "www.googletagmanager.com",
        "analytics.amazon.com",
        "fls-na.amazon.com",
    ]

    async def _route_handler(route):
        req = route.request
        url = req.url
        host = ""

        try:
            parsed = urlparse(url)
            host = parsed.netloc
        except Exception:
            pass

        # Block trackers
        if any(h in host for h in BLOCK_HOSTS):
            return await route.abort()

        return await route.continue_()

    try:
        await context.route("**/*", _route_handler)
    except Exception:
        pass

    page = await context.new_page()
    page.set_default_timeout(NAV_TIMEOUT)
    page.set_default_navigation_timeout(NAV_TIMEOUT)

    return browser, context, page


class AmazonScraper(BatchProcessingMixin):
    def __init__(
        self,
        proxy_list: List[Dict[str, Any]] = None,
        enable_proxy_rotation: bool = None,  # None = auto-detect from proxies.json
    ):
        logger.info("Initializing CLIP sole detector model...")
        self.clip = SoleDetectorCLIP()
        logger.info("✓ CLIP model loaded")
        self.products = []  # Store scraped products

        # Auto-enable proxy rotation if proxies.json exists (unless explicitly disabled)
        if enable_proxy_rotation is None:
            if PROXY_CONFIG_PATH.exists():
                enable_proxy_rotation = True
                logger.info(
                    "✅ Found proxies.json - enabling proxy rotation automatically"
                )
            else:
                enable_proxy_rotation = False
                logger.info("ℹ️  No proxies.json found - running without proxy rotation")

        self.proxy_manager = ProxyManager(
            proxy_list=proxy_list, enable_rotation=enable_proxy_rotation
        )

        if self.proxy_manager.enable_rotation:
            logger.info(
                f"🌐 Proxy rotation enabled with {len(self.proxy_manager.proxies)} proxies"
            )
        else:
            logger.info("🔓 Running without proxy rotation")

    async def navigate_with_retries(
        self,
        page: Page,
        url: str,
        *,
        max_retries: int = 3,
        first_wait: str = "networkidle",
    ) -> Page:
        """Navigate with retries and relaxed wait state on subsequent attempts."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                if page.is_closed():
                    try:
                        ctx = page.context  # type: ignore[attr-defined]
                        page = await ctx.new_page()
                        logger.warning("Page was closed; created new page for retry")
                    except Exception:
                        pass

                wait_state = first_wait if attempt == 1 else "domcontentloaded"
                timeout = NAV_TIMEOUT + (attempt - 1) * 10000
                logger.debug(
                    f"Navigating to {url} (attempt {attempt}/{max_retries}, wait_until={wait_state})"
                )
                await page.goto(url, wait_until=wait_state, timeout=timeout)
                return page
            except Exception as e:
                last_exc = e
                msg = str(e)
                transient = [
                    "ERR_ADDRESS_UNREACHABLE",
                    "ERR_NETWORK_CHANGED",
                    "ERR_CONNECTION_RESET",
                    "ERR_NAME_NOT_RESOLVED",
                    "ETIMEDOUT",
                    "ERR_TIMED_OUT",
                ]
                if any(t in msg for t in transient) and attempt < max_retries:
                    delay = 1.5 * attempt
                    logger.warning(f"Navigation error: {msg}. Retrying in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    continue
                break

        if last_exc:
            raise last_exc
        return page

    def _unwrap_sspa_url(self, url: str) -> str:
        """Unwrap Amazon sspa/click (sponsored) redirect URLs to the real product URL.

        If `url` contains /sspa/click with a `url=` parameter, decode and return it.
        Returns the original url if no unwrap could be performed.
        """
        try:
            if "/sspa/click" in url or "sspa/click" in url:
                parsed = urlparse(url)
                qs = parse_qs(parsed.query)
                target = None
                # Amazon sometimes puts target path in `url` param (percent-encoded)
                if "url" in qs and qs["url"]:
                    target = qs["url"][0]
                elif "u" in qs and qs["u"]:
                    target = qs["u"][0]
                if target:
                    target = unquote(target)
                    if target.startswith("//"):
                        target = "https:" + target
                    if target.startswith("/"):
                        target = "https://www.amazon.nl" + target
                    if target.startswith("http"):
                        logger.debug(f"Unwrapped sponsored URL to: {target}")
                        return target
        except Exception:
            pass
        return url

    async def _extract_links_from_current_page(self, page: Page) -> List[str]:
        """Extract product links from the currently loaded Amazon search page."""
        links: List[str] = []

        # Ensure main slot is present (best-effort)
        try:
            await page.wait_for_selector("div.s-main-slot", timeout=SELECTOR_TIMEOUT)
        except Exception:
            pass

        # Scroll to load lazy items
        previous_count = 0
        for _ in range(14):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(SCROLL_PAUSE)
            elems = await page.locator(
                "div.s-main-slot div[data-asin][data-component-type='s-search-result']"
            ).count()
            if elems == previous_count:
                break
            previous_count = elems

        # Primary selector
        items = page.locator(
            "div.s-main-slot div[data-asin][data-component-type='s-search-result']"
        )
        count = await items.count()
        if count == 0:
            items = page.locator(
                "div[data-asin][data-component-type='s-search-result']"
            )
            count = await items.count()
        if count == 0:
            items = page.locator(
                "div[cel_widget_id^='MAIN-SEARCH_RESULTS'] div[data-asin]"
            )
            count = await items.count()

        logger.info(f"📦 Found {count} product items on page")

        for i in range(count):
            try:
                item = items.nth(i)
                h2 = item.locator(
                    "h2 a.a-link-normal, h2 a.a-link-normal.s-no-outline"
                ).first
                href = None
                if await h2.count() > 0:
                    href = await h2.get_attribute("href")
                else:
                    anchors = item.locator(
                        "a.a-link-normal, a[href*='/dp/'], a[href*='/gp/']"
                    )
                    for a_idx in range(min(3, await anchors.count())):
                        a = anchors.nth(a_idx)
                        h = await a.get_attribute("href")
                        if not h:
                            continue
                        if "/dp/" in h or "/gp/" in h:
                            href = h
                            break
                        if h.startswith("http") or h.startswith("/"):
                            href = h
                            break

                if not href:
                    continue

                # Normalize absolute URL
                if href.startswith("/"):
                    href = "https://www.amazon.nl" + href
                elif not href.startswith("http"):
                    href = "https://www.amazon.nl/" + href

                normalized = self._unwrap_sspa_url(href)
                if normalized not in links:
                    links.append(normalized)
            except Exception:
                continue

        return links

    async def _get_total_pages(self, page: Page) -> int:
        """Read total pages from the pagination strip on the current page."""
        try:
            pagination = page.locator("span.s-pagination-strip ul")
            if await pagination.count() > 0:
                await pagination.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)
                total_pages = await page.evaluate(
                    "(sel) => { const ul = document.querySelector(sel); if(!ul) return 1; const lis = ul.querySelectorAll('li'); if(lis.length < 2) return 1; const secondLast = lis[lis.length-2]; const txt = secondLast.textContent || secondLast.innerText || ''; const n = parseInt(txt.trim()); return isNaN(n) ? 1 : n; }",
                    "span.s-pagination-strip ul",
                )
                return int(total_pages) if total_pages else 1
        except Exception:
            pass
        return 1

    async def collect_product_links(self, page: Page) -> List[str]:
        """
        Collect product links from the search page, handling pagination.
        Strategy:
        - Load first page
        - Read total pages from pagination strip (span.s-pagination-strip ul li second last)
        - Iterate pages by adding &page=N (or ?page=N) and collect links
        - For each page, wait for content to load with graceful error handling
        """
        # Load initial page to detect pagination
        try:
            page = await self.navigate_with_retries(
                page, START_URL, max_retries=3, first_wait="domcontentloaded"
            )
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Failed to load initial page: {e}")
            return []

        # Handle cookie consent
        logger.debug("⏳ Handling cookie consent...")
        try:
            # Try to click the input#sp-cc-accept directly
            cookie_input = page.locator("input#sp-cc-accept").first
            if await cookie_input.count() > 0:
                try:
                    # Scroll into view and click
                    await cookie_input.scroll_into_view_if_needed()
                    await cookie_input.click(timeout=3000)
                    logger.debug("✓ Accepted cookies (clicked input)")
                    await asyncio.sleep(1)
                except Exception:
                    # If direct click fails, try clicking parent span
                    try:
                        parent_span = page.locator("span.a-button-primary").first
                        if await parent_span.count() > 0:
                            await parent_span.click(timeout=3000)
                            logger.debug("✓ Accepted cookies (clicked parent span)")
                            await asyncio.sleep(1)
                    except Exception:
                        # Try using JavaScript to submit the form
                        try:
                            await page.evaluate(
                                "document.querySelector('input#sp-cc-accept').click()"
                            )
                            logger.debug("✓ Accepted cookies (JavaScript click)")
                            await asyncio.sleep(1)
                        except Exception as e:
                            logger.debug(f"⚠️ Could not accept cookies: {e}")
        except Exception as e:
            logger.debug(f"⚠️ Cookie consent handling error: {e}")

        # Scroll to bottom to load all content and make pagination visible
        logger.debug("⏳ Scrolling to bottom to load all content...")
        previous_height = 0
        for _ in range(20):  # Max 20 scroll iterations
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(SCROLL_PAUSE)
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == previous_height:
                break
            previous_height = new_height
        logger.debug("✓ Scrolled to bottom")

        # Try to read total pages
        total_pages = 1
        try:
            pagination = page.locator("span.s-pagination-strip ul")
            if await pagination.count() > 0:
                # Scroll pagination into view to ensure it's fully loaded
                await pagination.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)

                # Use evaluate to get second last li text safely
                total_pages = await page.evaluate(
                    "(sel) => { const ul = document.querySelector(sel); if(!ul) return 1; const lis = ul.querySelectorAll('li'); if(lis.length < 2) return 1; const secondLast = lis[lis.length-2]; const txt = secondLast.textContent || secondLast.innerText || ''; const n = parseInt(txt.trim()); return isNaN(n) ? 1 : n; }",
                    "span.s-pagination-strip ul",
                )
        except Exception:
            total_pages = 1

        logger.info(f"🧭 Detected ~{total_pages} pages (pagination)")

        links: List[str] = []

        # Helper to extract links from a loaded search page
        async def extract_links_from_page():
            # Prefer modern main slot based selector
            try:
                await page.wait_for_selector(
                    "div.s-main-slot", timeout=SELECTOR_TIMEOUT
                )
            except Exception:
                logger.debug("Main slot not detected quickly; continuing anyway")

            logger.debug("✓ Attempting to load product items (scrolling)")

            # Scroll to bottom in steps to load lazy content
            previous_count = 0
            for _ in range(14):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(SCROLL_PAUSE)
                elems = await page.locator(
                    "div.s-main-slot div[data-asin][data-component-type='s-search-result']"
                ).count()
                if elems == previous_count:
                    break
                previous_count = elems

            # Collect product links - try multiple selector strategies
            items = page.locator(
                "div.s-main-slot div[data-asin][data-component-type='s-search-result']"
            )
            count = await items.count()

            # Fallback selector if main slot yields none
            if count == 0:
                items = page.locator(
                    "div[data-asin][data-component-type='s-search-result']"
                )
                count = await items.count()
            if count == 0:
                items = page.locator(
                    "div[cel_widget_id^='MAIN-SEARCH_RESULTS'] div[data-asin]"
                )
                count = await items.count()

            logger.info(f"📦 Found {count} product items")

            for i in range(count):
                try:
                    item = items.nth(i)

                    # Find the main product link - typically in h2 > a or direct a.a-link-normal
                    # Try h2 first (more reliable structure)
                    h2 = item.locator(
                        "h2 a.a-link-normal, h2 a.a-link-normal.s-no-outline"
                    ).first
                    href = None

                    if await h2.count() > 0:
                        href = await h2.get_attribute("href")
                    else:
                        # Fallback: find any a.a-link-normal that looks like a product link
                        anchors = item.locator(
                            "a.a-link-normal, a[href*='/dp/'], a[href*='/gp/']"
                        )
                        for a_idx in range(
                            min(3, await anchors.count())
                        ):  # Check first 3 anchors
                            a = anchors.nth(a_idx)
                            h = await a.get_attribute("href")
                            if not h:
                                continue
                            # Prefer /dp/ or /gp/ paths (product detail pages)
                            if "/dp/" in h or "/gp/" in h:
                                href = h
                                break
                            # Also accept full URLs or root-relative paths
                            if h.startswith("http") or h.startswith("/"):
                                href = h
                                break

                    if not href:
                        logger.debug(f"Item {i}: No href found")
                        continue

                    # Normalize to absolute URL
                    if href.startswith("/"):
                        href = "https://www.amazon.nl" + href
                    elif not href.startswith("http"):
                        href = "https://www.amazon.nl/" + href

                    # Unwrap sponsored sspa/click URLs to the real product URL
                    normalized = self._unwrap_sspa_url(href)

                    # Skip duplicate links
                    if normalized not in links:
                        links.append(normalized)
                        logger.debug(f"Item {i}: Added {normalized[:80]}")
                except Exception as e:
                    logger.debug(f"Failed to extract link for item {i}: {e}")

        # Iterate pages
        for pg in range(1, int(total_pages) + 1):
            # Build page URL - Amazon uses &page= or ?page=
            if "?" in START_URL:
                page_url = f"{START_URL}&page={pg}"
            else:
                page_url = f"{START_URL}?page={pg}"

            logger.info(f"📄 Loading search page {pg}/{total_pages}: {page_url}")
            try:
                page = await self.navigate_with_retries(
                    page, page_url, max_retries=3, first_wait="domcontentloaded"
                )
                await asyncio.sleep(2)  # Extra wait for JavaScript rendering
                await extract_links_from_page()
            except Exception as e:
                logger.warning(f"Failed to load/extract page {pg}: {e}")
                continue

        logger.info(f"✅ Collected {len(links)} product links")
        return links

    async def extract_product_details(self, page: Page, url: str) -> Dict[str, Any]:
        """
        Visit product page and extract product name and thumbnail image srcs.
        Then download images and run CLIP to pick the sole image.
        """
        # Normalize/unwrap sponsored URLs before navigating
        url = self._unwrap_sspa_url(url)
        logger.info(f"  Scraping product: {url}")
        result: Dict[str, Any] = {
            "url": url,
            "product_name": None,
            "images": [],
            "sole": None,
        }
        try:
            page = await self.navigate_with_retries(
                page, url, max_retries=3, first_wait="domcontentloaded"
            )
            await asyncio.sleep(1)

            # Handle cookie consent on product page
            logger.debug("  ⏳ Checking for cookies on product page...")
            try:
                cookie_input = page.locator("input#sp-cc-accept").first
                if await cookie_input.count() > 0:
                    try:
                        await cookie_input.scroll_into_view_if_needed()
                        await cookie_input.click(timeout=3000)
                        logger.debug("  ✓ Accepted cookies on product page")
                        await asyncio.sleep(1)
                    except Exception:
                        try:
                            parent_span = page.locator("span.a-button-primary").first
                            if await parent_span.count() > 0:
                                await parent_span.click(timeout=3000)
                                logger.debug("  ✓ Accepted cookies (parent span)")
                                await asyncio.sleep(1)
                        except Exception:
                            try:
                                await page.evaluate(
                                    "document.querySelector('input#sp-cc-accept').click()"
                                )
                                logger.debug("  ✓ Accepted cookies (JavaScript)")
                                await asyncio.sleep(1)
                            except Exception:
                                pass
            except Exception:
                pass

            # product title
            try:
                await page.wait_for_selector("h1#title", timeout=7000)
                title_el = page.locator("h1#title").first
                title = (await title_el.text_content()) or ""
                result["product_name"] = title.strip()
            except Exception:
                result["product_name"] = "Unknown"

            # Scroll to bottom to help lazy-load
            for _ in range(6):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(0.5)

            # thumbnails
            try:
                thumbs_sel = 'ul[aria-label="Image thumbnails"].a-unordered-list'
                await page.wait_for_selector(thumbs_sel, timeout=5000)
                thumbs = page.locator(thumbs_sel + " li")
                count = await thumbs.count()
                logger.info(f"📸 Found {count} thumbnails")
                for i in range(count):
                    try:
                        img = thumbs.nth(i).locator("img").first
                        src = await img.get_attribute("src")
                        # some src may be protocol-relative or have &amp; entities
                        if src:
                            src = src.replace("&amp;", "&")
                            if src.startswith("//"):
                                src = "https:" + src
                            result["images"].append(src)
                    except Exception as e:
                        logger.debug(f"Failed to get image for thumb {i}: {e}")
            except Exception as e:
                logger.warning(f"No thumbnail container found: {e}")

            # If no images found, try image gallery alternative
            if not result["images"]:
                try:
                    gallery_imgs = page.locator("ul.a-unordered-list img")
                    for i in range(await gallery_imgs.count()):
                        s = await gallery_imgs.nth(i).get_attribute("src")
                        if s:
                            s = s.replace("&amp;", "&")
                            if s.startswith("//"):
                                s = "https:" + s
                            if s not in result["images"]:
                                result["images"].append(s)
                except Exception:
                    pass

            # Download images and check with CLIP
            best = None
            checked: List[Dict[str, Any]] = []
            for idx, img_url in enumerate(result["images"], 1):
                try:
                    logger.info(f" Image URL {idx}/{len(result['images'])}: {img_url}")
                    pil = await asyncio.get_event_loop().run_in_executor(
                        None, self.download_image, img_url
                    )
                    if pil is None:
                        continue
                    is_sole, conf, scores = self.clip.is_sole(pil)
                    checked.append(
                        {
                            "url": img_url,
                            "is_sole": is_sole,
                            "confidence": conf,
                            "scores": scores,
                        }
                    )
                except Exception as e:
                    logger.debug(f"CLIP check failed for {img_url}: {e}")

            # Select best sole if any
            soles = [c for c in checked if c.get("is_sole")]
            if soles:
                # choose highest confidence
                best = max(soles, key=lambda x: x.get("confidence", 0))
            else:
                # fallback: pick highest confidence even if not-is_sole
                if checked:
                    best = max(checked, key=lambda x: x.get("confidence", 0))

            result["checked_images"] = checked
            result["sole"] = best

        except Exception as e:
            logger.error(f"Error scraping product {url}: {e}")

        return result

    def download_image(self, url: str) -> Optional[Image.Image]:
        """Download image with retries and return PIL Image or None."""
        if not url:
            return None
        for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
            try:
                resp = requests.get(url, timeout=IMAGE_DOWNLOAD_TIMEOUT)
                if resp.status_code == 200:
                    img = Image.open(BytesIO(resp.content)).convert("RGB")

                    # Validate image size - skip very small/corrupted images
                    width, height = img.size
                    if width < 50 or height < 50:
                        logger.debug(
                            f"Image too small ({width}x{height}), skipping: {url[:80]}"
                        )
                        return None

                    return img
                else:
                    logger.debug(
                        f"Image download returned {resp.status_code} for {url}"
                    )
            except Exception as e:
                logger.debug(f"Download attempt {attempt} failed for {url}: {e}")
                asyncio.sleep(0.2 * attempt)
        return None

    async def scrape(
        self, batch_callback=None, batch_size: int = 20, is_cancelled=None
    ):
        """
        Main scraping function with batch processing support.

        Args:
            batch_callback: Async function to call with each batch of products
            batch_size: Number of products to collect before calling batch_callback
            is_cancelled: Optional function to check if scraping should be cancelled

        Process:
        1. Launch browser and navigate to Amazon search
        2. Collect all product links
        3. Extract product details for each link
        4. Process products in batches
        """
        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

        logger.info("Starting Amazon scraper")
        logger.info(f"Start URL: {START_URL}")
        if batch_callback:
            logger.info("Using real-time batch processing")

        # Get initial proxy
        current_proxy = (
            self.proxy_manager.get_next_proxy()
            if self.proxy_manager.enable_rotation
            else None
        )

        async with async_playwright() as p:
            browser, context, page = await launch_browser_with_proxy(
                p, proxy=current_proxy
            )

            try:
                # Step 1: Navigate to start page, get total pages
                page = await self.navigate_with_retries(
                    page, START_URL, max_retries=3, first_wait="domcontentloaded"
                )
                await asyncio.sleep(2)

                # Handle cookie consent (best-effort)
                try:
                    cookie_input = page.locator("input#sp-cc-accept").first
                    if await cookie_input.count() > 0:
                        await cookie_input.scroll_into_view_if_needed()
                        await cookie_input.click(timeout=3000)
                        await asyncio.sleep(1)
                except Exception:
                    pass

                # Scroll to reveal pagination and read total pages
                previous_height = 0
                for _ in range(12):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await asyncio.sleep(SCROLL_PAUSE)
                    new_height = await page.evaluate("document.body.scrollHeight")
                    if new_height == previous_height:
                        break
                    previous_height = new_height

                total_pages = await self._get_total_pages(page)
                logger.info(f"🧭 Detected ~{total_pages} pages (pagination)")

                # Step 2: Process each page sequentially
                results: List[Dict[str, Any]] = []
                current_batch: List[Dict[str, Any]] = []
                should_stop = False

                for pg in range(1, int(total_pages) + 1):
                    # Check for cancellation
                    if is_cancelled and is_cancelled():
                        logger.warning(
                            "🛑 Cancellation detected - stopping scraper immediately"
                        )
                        should_stop = True
                        break

                    if should_stop:
                        break

                    # Build page URL
                    if "?" in START_URL:
                        page_url = f"{START_URL}&page={pg}"
                    else:
                        page_url = f"{START_URL}?page={pg}"

                    logger.info(
                        f"📄 Loading search page {pg}/{total_pages}: {page_url}"
                    )

                    # Add delay between pages
                    if pg > 1:
                        await random_delay(MIN_PAGE_DELAY, MAX_PAGE_DELAY)

                    # Try with retries and proxy rotation on failure
                    retry_count = 0
                    while retry_count < MAX_RETRIES:
                        try:
                            page = await self.navigate_with_retries(
                                page,
                                page_url,
                                max_retries=2,
                                first_wait="domcontentloaded",
                            )
                            await asyncio.sleep(2)

                            # Success - record it
                            if current_proxy:
                                current_proxy.record_success()
                            break

                        except Exception as e:
                            error_msg = str(e)
                            retry_count += 1

                            # Check for 403 or timeout
                            if "403" in error_msg or "timeout" in error_msg.lower():
                                logger.warning(
                                    f"🚫 Navigation failed (attempt {retry_count}/{MAX_RETRIES}): {error_msg}"
                                )

                                # Rotate proxy and restart browser if available
                                if (
                                    self.proxy_manager.enable_rotation
                                    and retry_count < MAX_RETRIES
                                ):
                                    logger.info(
                                        "🔄 Rotating to new proxy and restarting browser..."
                                    )

                                    # Close old browser
                                    try:
                                        await page.close()
                                        await context.close()
                                        await browser.close()
                                    except Exception:
                                        pass

                                    # Get new proxy
                                    current_proxy = (
                                        self.proxy_manager.rotate_on_failure(
                                            current_proxy
                                        )
                                    )
                                    if not current_proxy:
                                        logger.error("No more active proxies available")
                                        should_stop = True
                                        break

                                    # Launch with new proxy
                                    (
                                        browser,
                                        context,
                                        page,
                                    ) = await launch_browser_with_proxy(
                                        p, proxy=current_proxy
                                    )

                                    # Exponential backoff
                                    await exponential_backoff_delay(retry_count)
                                else:
                                    logger.warning(f"Failed to load page {pg}: {e}")
                                    break
                            else:
                                logger.warning(f"Failed to load page {pg}: {e}")
                                break

                    if should_stop or retry_count >= MAX_RETRIES:
                        if retry_count >= MAX_RETRIES:
                            logger.error(f"Max retries exceeded for page {pg}")
                        continue

                    page_links = await self._extract_links_from_current_page(page)
                    logger.info(
                        f"🔗 Page {pg}: Collected {len(page_links)} product links"
                    )

                    # Process products on this page before moving to next
                    global_idx = len(results) + 1
                    for local_idx, url in enumerate(page_links, 1):
                        # Check for cancellation
                        if is_cancelled and is_cancelled():
                            logger.warning(
                                "🛑 Cancellation detected - stopping scraper immediately"
                            )
                            should_stop = True
                            break

                        if should_stop:
                            break

                        # Add delay between products
                        if local_idx > 1:
                            await random_delay(MIN_PRODUCT_DELAY, MAX_PRODUCT_DELAY)

                        # Try with retry logic
                        product_retry = 0
                        product_data = None

                        while product_retry < MAX_RETRIES:
                            try:
                                logger.info(
                                    f"\n  Product {global_idx}/{len(page_links)} (Page {pg}): Scraping..."
                                )
                                product_data = await self.extract_product_details(
                                    page, url
                                )

                                # Success
                                if current_proxy:
                                    current_proxy.record_success()
                                break

                            except Exception as e:
                                error_msg = str(e)
                                product_retry += 1

                                # Check for blocking
                                if "403" in error_msg or "timeout" in error_msg.lower():
                                    logger.warning(
                                        f"Product scraping failed (attempt {product_retry}/{MAX_RETRIES}): {error_msg}"
                                    )

                                    # Rotate proxy if available
                                    if (
                                        self.proxy_manager.enable_rotation
                                        and product_retry < MAX_RETRIES
                                    ):
                                        logger.info("🔄 Rotating proxy...")

                                        # Close and restart
                                        try:
                                            await page.close()
                                            await context.close()
                                            await browser.close()
                                        except Exception:
                                            pass

                                        current_proxy = (
                                            self.proxy_manager.rotate_on_failure(
                                                current_proxy
                                            )
                                        )
                                        if not current_proxy:
                                            logger.error("No more active proxies")
                                            should_stop = True
                                            break

                                        (
                                            browser,
                                            context,
                                            page,
                                        ) = await launch_browser_with_proxy(
                                            p, proxy=current_proxy
                                        )

                                        await exponential_backoff_delay(product_retry)
                                    else:
                                        break
                                else:
                                    logger.error(
                                        f"[Page {pg}:Product {global_idx}] Failed to extract {url}: {e}"
                                    )
                                    break

                        if should_stop:
                            break

                        if not product_data:
                            global_idx += 1
                            continue

                        try:
                            # Extract data for logging
                            name = (
                                product_data.get("product_name")
                                if product_data
                                else "Unknown"
                            )
                            sole = product_data.get("sole") if product_data else None
                            images = (
                                product_data.get("images", []) if product_data else []
                            )
                            sole_url = (sole or {}).get("url") if sole else None
                            sole_conf = (
                                (sole or {}).get("confidence", 0.0) if sole else 0.0
                            )

                            # Log scraped product details (always, even if no sole found)
                            logger.info(f"✅ Scraped Product #{global_idx}:")
                            logger.info("   Brand: Amazon")
                            logger.info(f"   Product Name: {name}")
                            logger.info(f"   Product URL: {url}")
                            logger.info(
                                f"   Sole Image URL: {sole_url[:80] + '...' if sole_url and len(sole_url) > 80 else sole_url or 'N/A'}"
                            )
                            logger.info(f"   Sole Confidence: {sole_conf:.3f}")
                            logger.info(f"   Total Images Found: {len(images)}")

                            # Only enqueue if we have a chosen sole
                            if product_data and sole:
                                normalized_product = {
                                    "brand": "Amazon",
                                    "name": name or "Unknown",
                                    "url": product_data["url"],
                                    "image_url": sole_url,
                                    "product_type": "shoe",
                                }
                                results.append(normalized_product)
                                current_batch.append(normalized_product)
                                self.products.append(normalized_product)

                                if len(current_batch) >= batch_size and batch_callback:
                                    logger.info(
                                        f"Processing batch of {len(current_batch)} products..."
                                    )
                                    prepared_batch = self._prepare_batch_for_processing(
                                        current_batch,
                                        brand_field="brand",
                                        name_field="name",
                                        url_field="url",
                                        image_url_field="image_url",
                                    )
                                    if prepared_batch:
                                        should_continue = await batch_callback(
                                            prepared_batch
                                        )
                                        if not should_continue:
                                            should_stop = True
                                    current_batch = []

                            global_idx += 1
                        except Exception as e:
                            logger.error(
                                f"[Page {pg}:Product {global_idx}] Processing error: {e}"
                            )
                            global_idx += 1
                            continue

                # Process remaining items in final batch
                if current_batch and batch_callback and not should_stop:
                    logger.info(
                        f"Processing final batch of {len(current_batch)} products..."
                    )
                    # Prepare batch with image downloads
                    prepared_batch = self._prepare_batch_for_processing(
                        current_batch,
                        brand_field="brand",
                        name_field="name",
                        url_field="url",
                        image_url_field="image_url",
                    )

                    if prepared_batch:
                        await batch_callback(prepared_batch)

                logger.info(f"✅ Scraped {len(results)} products with sole images")

                # Log proxy statistics
                if self.proxy_manager.enable_rotation:
                    stats = self.proxy_manager.get_stats()
                    logger.info("\n" + "=" * 50)
                    logger.info("📊 Proxy Rotation Statistics:")
                    logger.info(f"   Total Proxies: {stats['total_proxies']}")
                    logger.info(f"   Active Proxies: {stats['active_proxies']}")
                    logger.info(f"   Total Requests: {stats['total_requests']}")
                    logger.info(f"   Successful: {stats['total_success']}")
                    logger.info(f"   Failed: {stats['total_failures']}")
                    logger.info(f"   Success Rate: {stats['overall_success_rate']:.2%}")
                    logger.info(f"   Rotations: {stats['rotation_count']}")
                    logger.info("=" * 50 + "\n")

            except Exception as e:
                logger.error(f"Scraper failed: {e}", exc_info=True)
            finally:
                try:
                    await context.close()
                    await browser.close()
                except Exception:
                    pass


async def main():
    scraper = AmazonScraper()
    async with async_playwright() as p:
        browser = await p.chromium.launch(**get_chromium_launch_config())
        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            extra_http_headers={"Accept-Language": ACCEPT_LANGUAGE},
        )
        page = await context.new_page()

        # Set viewport to standard size
        await page.set_viewport_size({"width": 1280, "height": 1024})

        links = await scraper.collect_product_links(page)

        if not links:
            logger.error("❌ No product links collected!")
            await context.close()
            await browser.close()
            return

        # Limit for safety during first run
        links = links[:50]
        logger.info(f"📌 Processing {len(links)} product links")

        results = []
        for idx, url in enumerate(links, 1):
            try:
                logger.info(f"[{idx}/{len(links)}] Processing: {url}")
                res = await scraper.extract_product_details(page, url)
                results.append(res)
            except Exception as e:
                logger.error(f"[{idx}/{len(links)}] Failed to extract {url}: {e}")
                continue

        await context.close()
        await browser.close()

    # Simple print summary
    logger.info(f"✅ Scraped {len(results)} products")
    for r in results[:10]:
        logger.info(f"  {r.get('product_name')} -> sole: {r.get('sole')}")


if __name__ == "__main__":
    asyncio.run(main())
