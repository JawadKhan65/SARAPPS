"""
Playwright-based scraper for Zalando.nl shoes.

Scrapes product links from paginated search results, then extracts:
  - Brand name
  - Product name
  - Product URL
  - Number of product images

Returns a list of dictionaries with product metadata.
"""

import asyncio
import json
import re
from pathlib import Path
from io import BytesIO
from typing import List, Dict, Any, Optional
from PIL import Image
import requests
from playwright.async_api import async_playwright, Page

# get_chromium_launch_config no longer used with custom launch args
import logging
import sys

# Add backend to path to import models
sys.path.insert(0, str(Path(__file__).parent.parent))
from scrapers.base_scraper_mixin import BatchProcessingMixin


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CRITICAL FIX: Reduce timeouts to prevent hanging (Fix #8)
DEFAULT_TIMEOUT = 10000  # 10 seconds for faster blocked URL detection
NAVIGATION_TIMEOUT = 10000  # 10 seconds for faster blocked URL detection
MAX_RETRIES = 2  # Max 2 retries per URL (Fix #1)
RETRY_DELAY = 3  # seconds between retries
MAIN_CONTENT_SELECTOR = "#main-content"
CONSENT_BUTTON_SELECTOR = '[data-testid="uc-accept-all-button"]'
COOKIE_IFRAME_PREFIX = "sp_message_iframe"
COOKIE_BUTTON_TEXTS = ["OK", "Akkoord", "Alles toestaan", "Alle cookies accepteren"]
STORAGE_STATE_PATH = Path(__file__).parent / ".storage" / "zalando_storage.json"

# Enhanced stealth initialization script (Fix #9: Enhanced stealth mode)
STEALTH_INIT_SCRIPT = """
// CRITICAL: Remove webdriver property (Fix #9)
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Add chrome object with more realistic properties
Object.defineProperty(window, 'chrome', { 
    value: { 
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {}
    } 
});

// Override plugins to appear more realistic
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
        },
        {
            0: {type: "application/x-nacl", suffixes: "", description: "Native Client Executable"},
            1: {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client Executable"},
            description: "",
            filename: "internal-nacl-plugin",
            length: 2,
            name: "Native Client"
        }
    ]
});

// Languages
Object.defineProperty(navigator, 'languages', { get: () => ['nl-NL', 'nl', 'en-US', 'en'] });

// Platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// Hardware concurrency
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

// Device memory
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// Permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters);

// Override userAgent getter
Object.defineProperty(navigator, 'userAgent', {
    get: () => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.86 Safari/537.36'
});

// Screen properties for more realistic headless
if (window.outerWidth === 0) {
    Object.defineProperty(window, 'outerWidth', { get: () => 1280 });
    Object.defineProperty(window, 'outerHeight', { get: () => 800 });
}

// Fix iframe contentWindow
try {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
    };
} catch (err) {}
"""

# Enhanced context options with more realistic settings
BASE_CONTEXT_OPTIONS = {
    "viewport": {"width": 1920, "height": 1080},
    "device_scale_factor": 1,
    "is_mobile": False,
    "has_touch": False,
    "locale": "nl-NL",
    "timezone_id": "Europe/Amsterdam",
    "color_scheme": "light",
    "java_script_enabled": True,
    "bypass_csp": True,
    "ignore_https_errors": True,
    "extra_http_headers": {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    },
}


async def launch_browser_context(playwright, headless: bool = True):
    """
    Launch Chromium with anti-detection flags (AutomationControlled disabled).
    """

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
        "--window-size=1920,1080",
    ]

    if headless:
        args.append("--headless=new")

    launch_config = {
        "headless": False if headless else False,
        "args": args,
        "ignore_default_args": ["--enable-automation"],
    }

    browser = await playwright.chromium.launch(**launch_config)
    # Load persisted storage (cookies) if available to bypass consent
    context_options = BASE_CONTEXT_OPTIONS.copy()
    # Explicit UA to match expectation (can be tuned per env)
    ua_string = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    context_options["user_agent"] = ua_string
    if STORAGE_STATE_PATH.exists():
        context = await browser.new_context(
            **context_options, storage_state=str(STORAGE_STATE_PATH)
        )
    else:
        context = await browser.new_context(**context_options)
    await context.add_init_script(STEALTH_INIT_SCRIPT)
    page = await context.new_page()
    try:
        await page.emulate_media(color_scheme="light")
    except Exception:
        pass

    # Route: block trackers/ads/metrics; allow product images/fonts to reduce ERR noise
    # Fix #7: Block unnecessary requests (analytics, tracking, API calls)
    BLOCK_HOSTS = [
        "googleads.g.doubleclick.net",
        "ad.doubleclick.net",
        "www.google.com",
        "www.google.nl",
        "www.googletagmanager.com",
        "o4509038451032064.ingest.de.sentry.io",
        "app.eu.usercentrics.eu",
        "www.zalando.nl/api/cmag",
        "www.zalando.nl/api/otlp",
        "www.zalando.nl/api/t",
        "www.zalando.nl/api/otlp/metrics",
        "www.zalando.nl/api/otlp/trace",
        "facebook.com",
        "analytics.google.com",
        "google-analytics.com",
    ]

    # Fix #7: Block API paths that trigger detection
    BLOCK_PATHS = [
        "/api/otlp/",
        "/api/cmag",
        "/api/t/gtm/",
        "/api/graphql/",
    ]

    ALLOW_IMAGE_HOSTS = [
        ".ztat.net",
        "cloudfront.net",
    ]

    async def _route_handler(route):
        req = route.request
        url = req.url
        host = ""
        try:
            from urllib.parse import urlparse

            host = urlparse(url).netloc
        except Exception:
            pass

        # Fix #7: Block noisy telemetry/ads
        if any(h in host for h in BLOCK_HOSTS):
            return await route.abort()

        # Fix #7: Block API paths
        if any(path in url for path in BLOCK_PATHS):
            return await route.abort()

        # Fix #7: Block all POST requests to /api/ endpoints
        if req.method == "POST" and "/api/" in url:
            return await route.abort()

        # Allow product media from known CDN hosts; otherwise continue
        if req.resource_type in ("image", "font", "media"):
            if any(h in host for h in ALLOW_IMAGE_HOSTS):
                return await route.continue_()
            # For other image hosts, still allow; blocking causes ERR_FAILED spam
            return await route.continue_()

        return await route.continue_()

    try:
        await context.route("**/*", _route_handler)
    except Exception:
        pass
    page.set_default_timeout(DEFAULT_TIMEOUT)
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
    return browser, context, page


# Simple resource blocker matching the requested API
async def block_resources(page: Page):
    async def _route(route):
        url = route.request.url
        block_domains = [
            "otlp",
            "gtm",
            "analytics",
            "facebook",
            "doubleclick",
        ]
        if any(d in url for d in block_domains):
            return await route.abort()
        return await route.continue_()

    try:
        await page.route("**/*", _route)
    except Exception:
        pass


async def _dismiss_cookie_iframe(page: Page):
    """
    Handle SourcePoint cookie dialogs that render inside cross-origin iframes.
    """

    # Try via frame locator first (more robust for cross-origin)
    try:
        fl = page.frame_locator(f"iframe[name^='{COOKIE_IFRAME_PREFIX}']")
        for text in COOKIE_BUTTON_TEXTS:
            try:
                btn = fl.locator(f"button:has-text('{text}')")
                await btn.first.click(timeout=1500)
                await asyncio.sleep(0.5)
                return True
            except Exception:
                continue
    except Exception:
        pass

    # Fallback: iterate frames and try buttons by text
    try:
        for frame in page.frames:
            name = frame.name or ""
            if COOKIE_IFRAME_PREFIX in name:
                for text in COOKIE_BUTTON_TEXTS:
                    try:
                        btn = frame.locator(f"button:has-text('{text}')")
                        if await btn.first.is_visible(timeout=1000):
                            logger.debug(
                                f"Clicking cookie iframe button '{text}' in frame {name}"
                            )
                            await btn.first.click(timeout=2000)
                            await asyncio.sleep(0.5)
                            return True
                    except Exception:
                        continue
    except Exception:
        pass

    return False


async def wait_for_main_content(
    page: Page, consent_button_selector: Optional[str] = None
):
    """
    Wait for Zalando's main content area to be present/visible, handling cookie prompts.

    This is more reliable in headless mode where Zalando sometimes delays rendering
    #main-content. We repeatedly try to dismiss the consent dialog and look for the
    target selector within the overall DEFAULT_TIMEOUT window.
    """

    deadline = asyncio.get_running_loop().time() + (DEFAULT_TIMEOUT / 1000)
    attempt = 1

    # Ensure basic DOM is ready
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=8000)
        await page.locator("body").wait_for(state="attached", timeout=8000)
    except Exception:
        pass

    while asyncio.get_running_loop().time() < deadline:
        dismissed_iframe = await _dismiss_cookie_iframe(page)

        if consent_button_selector and not dismissed_iframe:
            try:
                consent_btn = page.locator(consent_button_selector)
                if await consent_btn.count():
                    if await consent_btn.is_visible(timeout=1000):
                        logger.debug(
                            "Consent button visible while waiting for main content."
                        )
                        await consent_btn.click(timeout=3000)
                        await asyncio.sleep(0.5)
            except Exception:
                pass

        # Nudge rendering in headless: small scroll can trigger lazy mounts
        try:
            await page.evaluate("() => window.scrollBy(0, 100)")
        except Exception:
            pass

        locator = page.locator(MAIN_CONTENT_SELECTOR)
        try:
            await locator.wait_for(state="attached", timeout=2000)
            if await locator.first.is_visible():
                logger.debug("Main content is visible.")
                return True
            # If attached but hidden behind animation/popup, wait a bit and continue.
            logger.debug("Main content attached but not yet visible; retrying...")
        except Exception:
            logger.debug(
                f"Attempt {attempt}: main content not ready yet, retrying...",
                exc_info=False,
            )

        attempt += 1
        await asyncio.sleep(1)

    raise TimeoutError(
        "Timed out waiting for Zalando #main-content to become available"
    )


# XPaths for pagination and product elements
PAGINATION_XPATH = (
    '//*[@id="main-content"]/div/div[5]/div/div[2]/div[3]/ul/li[85]/nav/div/span'
)


PRODUCTS_CONTAINER_XPATH = '//*[@id="main-content"]/div/div[5]/div/div[2]/div[3]/ul'

# XPaths for product detail page
BRAND_XPATH = '//*[@id="main-content"]/div[1]/div/div[2]/h1/div/a/span/span'
PRODUCT_NAME_XPATH = '//*[@id="main-content"]/div[1]/div/div[2]/h1/span/span'
IMAGES_CONTAINER_XPATH = (
    '//*[@id="main-content"]/div[1]/div/div[1]/section/div[1]/div/div/div[2]/div[1]'
)


class ZalandoScraper(BatchProcessingMixin):
    """
    Zalando scraper wrapper class for integration with scraper manager.
    Wraps the standalone scrape_zalando_shoes function.
    """

    def __init__(self, base_url: str = "https://www.zalando.nl/schoenen"):
        # Ensure we always use the correct .nl shoes page, not just zalando.com
        if base_url and "zalando.com" in base_url and "zalando.nl" not in base_url:
            logger.warning(
                f"Correcting base_url from {base_url} to https://www.zalando.nl/schoenen"
            )
            base_url = "https://www.zalando.nl/schoenen"
        elif base_url and "zalando.nl" in base_url and "/schoenen" not in base_url:
            # If it's zalando.nl but missing /schoenen, add it
            base_url = "https://www.zalando.nl/schoenen"

        self.base_url = base_url
        logger.info(f"Zalando scraper initialized with base_url: {self.base_url}")

    async def scrape(
        self,
        max_pages: int = None,
        batch_callback=None,
        batch_size: int = 20,
        is_cancelled=None,
    ):
        """
        Recovery-enabled scrape with:
        - Progressive backoff on 403 (5s -> 10s -> 20s ... capped at 60s)
        - Random delays between pages (3–8s) and products (0.6–1.8s)
        - User-agent + viewport rotation every N pages
        - Session rotation/cookie clearing on repeated failures
        - Circuit breaker: pause 5 minutes after 3 consecutive page failures
        - Checkpoint/resume (page, totals, failed URLs)
        - Graceful shutdown on SIGTERM/SIGINT (save state, close browser)
        """
        import random, signal, time
        from urllib.parse import urlparse

        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

        # Load external config if present
        try:
            cfg_path = Path(__file__).parent / "config" / "zalando_config.json"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text())
                global DEFAULT_TIMEOUT, NAVIGATION_TIMEOUT, MAX_RETRIES
                DEFAULT_TIMEOUT = int(cfg.get("default_timeout_ms", DEFAULT_TIMEOUT))
                NAVIGATION_TIMEOUT = int(
                    cfg.get("navigation_timeout_ms", NAVIGATION_TIMEOUT)
                )
                MAX_RETRIES = int(cfg.get("max_retries", MAX_RETRIES))
                page_delay = cfg.get("page_delay_seconds", {"min": 3, "max": 8})
                product_delay = cfg.get(
                    "product_delay_seconds", {"min": 0.6, "max": 1.8}
                )
                backoff_cfg = cfg.get(
                    "backoff",
                    {"initial_seconds": 5, "factor": 2.0, "max_seconds": 60},
                )
                pages_per_session = int(cfg.get("pages_per_session", 5))
                cb_failures = int(
                    cfg.get("consecutive_failures_for_circuit_breaker", 3)
                )
                cb_sleep = int(cfg.get("circuit_breaker_sleep_seconds", 300))
                checkpoint_interval = int(cfg.get("checkpoint_interval_products", 20))
                rotate_on_failures = int(cfg.get("session_rotation_on_failures", 2))
                health_timeout = int(cfg.get("healthcheck_timeout_seconds", 10))
            else:
                page_delay = {"min": 3, "max": 8}
                product_delay = {"min": 0.6, "max": 1.8}
                backoff_cfg = {"initial_seconds": 5, "factor": 2.0, "max_seconds": 60}
                pages_per_session = 5
                cb_failures = 3
                cb_sleep = 300
                checkpoint_interval = 20
                rotate_on_failures = 2
                health_timeout = 10
        except Exception as e:
            logger.warning(f"Failed loading zalando_config.json: {e}")
            page_delay = {"min": 3, "max": 8}
            product_delay = {"min": 0.6, "max": 1.8}
            backoff_cfg = {"initial_seconds": 5, "factor": 2.0, "max_seconds": 60}
            pages_per_session = 5
            cb_failures = 3
            cb_sleep = 300
            checkpoint_interval = 20
            rotate_on_failures = 2
            health_timeout = 10

        # Fix #1: URL Blocklist - NEVER retry blocked URLs
        blocked_urls = set()  # Permanently blocked (403/429)
        blocked_urls_file = Path(__file__).parent / "zalando_blocked_urls.json"

        # Fix #3: Deduplication - Skip duplicate products
        seen_urls = set()  # Track visited URLs
        seen_products = set()  # Track brand+name combinations

        # Fix #4: Adaptive Rate Limiter
        current_delay = 3.0  # Start with 3 seconds
        min_delay = 3.0
        max_delay = 60.0

        # Fix #5: Failed URLs tracking
        failed_urls_file = Path(__file__).parent / "zalando_failed_urls.json"
        failed_urls_list = []  # Track all failures with details

        # Fix #2: Circuit breaker counters
        consecutive_403_count = 0
        consecutive_429_count = 0
        circuit_breaker_tripped = False

        # Load blocklist if exists
        if blocked_urls_file.exists():
            try:
                blocked_urls = set(json.loads(blocked_urls_file.read_text()))
                logger.info(
                    f"📋 Loaded {len(blocked_urls)} blocked URLs from previous run"
                )
            except Exception as e:
                logger.warning(f"Could not load blocked URLs: {e}")

        # Checkpointing
        checkpoint_file = Path(__file__).parent / "scraper_checkpoint.json"
        state = {
            "current_page": 1,
            "products_scraped": 0,
            "unique_products": 0,
            "duplicates_skipped": 0,
            "blocked_count": 0,
            "failed_urls": [],
            "total_pages": None,
            "last_successful_index": 0,
        }

        def load_checkpoint():
            try:
                if checkpoint_file.exists():
                    s = json.loads(checkpoint_file.read_text())
                    state.update(s)
                    logger.info(
                        f"🔁 Resuming from checkpoint: page {state['current_page']}"
                    )
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")

        def save_checkpoint():
            try:
                checkpoint_file.write_text(json.dumps(state, indent=2))
                logger.info(
                    f"💾 Checkpoint: page={state['current_page']}, products={state['products_scraped']}, unique={state['unique_products']}, blocked={state['blocked_count']}"
                )
            except Exception as e:
                logger.warning(f"Failed to save checkpoint: {e}")

        # Fix #1: Blocklist management
        def add_to_blocklist(url: str, status_code: int):
            nonlocal blocked_urls, state
            if url not in blocked_urls:
                blocked_urls.add(url)
                state["blocked_count"] += 1
                try:
                    blocked_urls_file.write_text(
                        json.dumps(list(blocked_urls), indent=2)
                    )
                    logger.error(f"🚫 URL BLOCKED (HTTP {status_code}): {url[:80]}")
                except Exception as e:
                    logger.error(f"Could not save blocked URL: {e}")

        def is_blocked(url: str) -> bool:
            return url in blocked_urls

        # Fix #3: Deduplication helpers
        def is_duplicate_url(url: str) -> bool:
            return url in seen_urls

        def is_duplicate_product(brand: str, name: str) -> bool:
            key = f"{brand.lower().strip()}::{name.lower().strip()}"
            return key in seen_products

        def mark_url_seen(url: str):
            seen_urls.add(url)

        def mark_product_seen(brand: str, name: str):
            key = f"{brand.lower().strip()}::{name.lower().strip()}"
            seen_products.add(key)

        # Fix #4: Adaptive rate limiting
        def adjust_delay_on_429():
            nonlocal current_delay
            old = current_delay
            current_delay = min(current_delay * 3.0, max_delay)
            logger.warning(
                f"⏱️  Rate limit (429) - delay: {old:.1f}s → {current_delay:.1f}s"
            )

        def adjust_delay_on_403():
            nonlocal current_delay
            old = current_delay
            current_delay = min(current_delay * 2.0, max_delay)
            logger.warning(
                f"⏱️  Forbidden (403) - delay: {old:.1f}s → {current_delay:.1f}s"
            )

        def adjust_delay_on_success():
            nonlocal current_delay
            old = current_delay
            current_delay = max(current_delay * 0.9, min_delay)
            if old != current_delay:
                logger.debug(f"⏱️  Success - delay: {old:.1f}s → {current_delay:.1f}s")

        def get_current_delay() -> float:
            import random

            jitter = random.uniform(0, 2.0)
            return current_delay + jitter

        # Fix #5: Failed URLs tracking
        def save_failed_url(
            url: str, reason: str, status_code: int = None, error_msg: str = ""
        ):
            nonlocal failed_urls_list
            from datetime import datetime, timezone

            failed_entry = {
                "url": url,
                "reason": reason,
                "status_code": status_code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error_message": error_msg,
            }
            failed_urls_list.append(failed_entry)
            try:
                failed_urls_file.write_text(json.dumps(failed_urls_list, indent=2))
                logger.warning(f"📝 Failed URL logged: {reason} - {url[:80]}")
            except Exception as e:
                logger.error(f"Could not save failed URL: {e}")

        # Fix #2: Circuit breaker helpers
        def record_403():
            nonlocal \
                consecutive_403_count, \
                consecutive_429_count, \
                circuit_breaker_tripped
            consecutive_403_count += 1
            consecutive_429_count = 0  # Reset 429 counter
            logger.warning(f"⚠️  HTTP 403 count: {consecutive_403_count}/3")
            if consecutive_403_count >= 3:
                circuit_breaker_tripped = True
                logger.error(f"🔴 CIRCUIT BREAKER TRIPPED (3 consecutive 403s)")

        def record_429():
            nonlocal \
                consecutive_403_count, \
                consecutive_429_count, \
                circuit_breaker_tripped
            consecutive_429_count += 1
            consecutive_403_count = 0  # Reset 403 counter
            logger.warning(f"⚠️  HTTP 429 count: {consecutive_429_count}/3")
            if consecutive_429_count >= 3:
                circuit_breaker_tripped = True
                logger.error(f"🔴 CIRCUIT BREAKER TRIPPED (3 consecutive 429s)")

        def record_success():
            nonlocal consecutive_403_count, consecutive_429_count
            if consecutive_403_count > 0 or consecutive_429_count > 0:
                logger.info(
                    f"✅ Success - resetting failure counters (403={consecutive_403_count}, 429={consecutive_429_count})"
                )
            consecutive_403_count = 0
            consecutive_429_count = 0

        async def handle_circuit_breaker():
            nonlocal circuit_breaker_tripped, browser, context, page, current_delay
            if circuit_breaker_tripped:
                logger.error(f"🔴 Circuit breaker active - pausing for {cb_sleep}s")
                save_checkpoint()
                await asyncio.sleep(cb_sleep)

                # Close and recreate browser context
                try:
                    await context.close()
                    await browser.close()
                except Exception:
                    pass

                logger.info("🔄 Creating fresh browser context after circuit breaker")
                browser, context, page = await open_context_with_rotation(
                    random.choice(USER_AGENTS)
                )

                # Fix #5: Re-register event handlers after reset
                page.on("requestfailed", _handle_request_failed)
                page.on("response", _handle_response)

                # Reset state
                circuit_breaker_tripped = False
                consecutive_403_count = 0
                consecutive_429_count = 0
                current_delay = min_delay  # Reset delay
                logger.info("🟢 Circuit breaker reset - resuming scraping")
                return browser, context, page
            return browser, context, page

        # Backoff helpers
        def progressive_backoff(attempt):
            base = backoff_cfg.get("initial_seconds", 5)
            factor = backoff_cfg.get("factor", 2.0)
            max_s = backoff_cfg.get("max_seconds", 60)
            delay = min(max_s, base * (factor ** max(0, attempt)))
            # add small jitter
            delay += random.uniform(0, 1.5)
            return delay

        # UA rotation
        USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.86 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.86 Safari/537.36",
        ]

        def random_viewport():
            w = random.randint(1280, 1920)
            h = random.randint(768, 1200)
            return {"width": w, "height": h}

        # Health check
        def site_health_ok():
            try:
                r = requests.get(
                    self.base_url,
                    timeout=health_timeout,
                    headers={
                        "User-Agent": random.choice(USER_AGENTS),
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    },
                )
                return r.status_code < 500
            except Exception:
                return False

        # Graceful shutdown
        shutting_down = {"flag": False}

        def _shutdown_handler(signum, frame):
            logger.warning(
                f"Received signal {signum}; saving checkpoint and exiting..."
            )
            shutting_down["flag"] = True
            save_checkpoint()

        # Register signals (Linux containers)
        try:
            signal.signal(signal.SIGTERM, _shutdown_handler)
            signal.signal(signal.SIGINT, _shutdown_handler)
        except Exception:
            pass

        # Random delay helpers
        def sleep_page_delay():
            return asyncio.sleep(random.uniform(page_delay["min"], page_delay["max"]))

        def sleep_product_delay():
            return asyncio.sleep(
                random.uniform(product_delay["min"], product_delay["max"])
            )

        # Begin
        logger.info("Starting Zalando scraper with recovery + checkpointing")
        logger.info(f"Base URL: {self.base_url}")
        load_checkpoint()

        results = []
        current_batch = []
        should_stop = False
        global_idx = 1
        consecutive_failures = 0
        failures_in_session = 0
        pages_in_session = 0

        async with async_playwright() as p:
            # launcher/context factory
            async def open_context_with_rotation(user_agent=None):
                nonlocal p
                browser, context, page = await launch_browser_context(p, headless=True)
                # override UA by recreating context for stricter UA rotation
                if user_agent:
                    await context.close()
                    context_opts = BASE_CONTEXT_OPTIONS.copy()
                    context_opts["viewport"] = random_viewport()
                    context_opts["user_agent"] = user_agent
                    browser = await p.chromium.launch(
                        headless=True,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--no-sandbox",
                        ],
                        ignore_default_args=["--enable-automation"],
                    )
                    context = await browser.new_context(**context_opts)
                    await context.add_init_script(STEALTH_INIT_SCRIPT)
                    page = await context.new_page()
                await block_resources(page)
                page.set_default_timeout(DEFAULT_TIMEOUT)
                page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
                return browser, context, page

            # initial context
            browser, context, page = await open_context_with_rotation(
                random.choice(USER_AGENTS)
            )
            consent_button_selector = CONSENT_BUTTON_SELECTOR

            # Event wiring
            def _handle_request_failed(request):
                try:
                    from urllib.parse import urlparse

                    host = urlparse(request.url).netloc
                    suppress_hosts = {
                        "googleads.g.doubleclick.net",
                        "ad.doubleclick.net",
                        "www.googletagmanager.com",
                        "www.google.com",
                        "www.google.nl",
                        "o4509038451032064.ingest.de.sentry.io",
                        "app.eu.usercentrics.eu",
                    }
                    if host in suppress_hosts:
                        return
                    failure = request.failure
                    logger.debug(
                        f"Request failed: {request.method} {request.url} -> {failure}"
                    )
                except Exception:
                    pass

            def _handle_response(response):
                try:
                    if response.status == 403:
                        logger.warning(
                            f"HTTP 403 for {response.request.method} {response.url}"
                        )
                    # Fix #4: Add 429 detection to trigger circuit breaker
                    if response.status == 429:
                        logger.warning(
                            f"HTTP 429 for {response.request.method} {response.url}"
                        )
                        # If it's a main navigation (not just API), trigger circuit breaker
                        if ".html" in response.url or "/schoenen" in response.url:
                            record_429()  # This will trip circuit breaker after 3
                except Exception:
                    pass

            page.on("requestfailed", _handle_request_failed)
            page.on("response", _handle_response)

            try:
                # Navigate to base URL with retry/backoff
                for attempt in range(MAX_RETRIES):
                    try:
                        await page.goto(
                            self.base_url,
                            wait_until="domcontentloaded",
                            timeout=NAVIGATION_TIMEOUT,
                        )
                        try:
                            consent_btn = page.locator(consent_button_selector)
                            if await consent_btn.is_visible(timeout=2000):
                                await consent_btn.click(timeout=5000)
                                await asyncio.sleep(1)
                        except Exception:
                            pass
                        await wait_for_main_content(page, consent_button_selector)
                        try:
                            STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                            await page.context.storage_state(
                                path=str(STORAGE_STATE_PATH)
                            )
                        except Exception:
                            pass
                        break
                    except Exception as e:
                        if attempt < MAX_RETRIES - 1:
                            d = progressive_backoff(attempt)
                            logger.warning(
                                f"Base navigation failed: {e}. Retrying in {d:.1f}s"
                            )
                            await asyncio.sleep(d)
                        else:
                            raise

                # Resolve pages to scrape (respect checkpoint)
                total_pages = await get_pagination_info(page)
                state["total_pages"] = total_pages
                start_page = max(1, int(state["current_page"]))
                last_page = min(total_pages, max_pages) if max_pages else total_pages
                logger.info(
                    f"🧭 Detected {total_pages} total pages; scraping {start_page}..{last_page}"
                )

                page_num = start_page
                while page_num <= last_page:
                    if should_stop or (is_cancelled and is_cancelled()):
                        logger.warning("🛑 Cancellation detected; saving and exiting")
                        save_checkpoint()
                        break

                    # Circuit breaker
                    if consecutive_failures >= cb_failures:
                        logger.warning(
                            f"⛔ Circuit breaker: {consecutive_failures} consecutive failures; sleeping {cb_sleep}s"
                        )
                        save_checkpoint()
                        await asyncio.sleep(cb_sleep)
                        consecutive_failures = 0
                        failures_in_session = 0
                        # rotate session after breaker
                        try:
                            await context.close()
                            await browser.close()
                        except Exception:
                            pass
                        browser, context, page = await open_context_with_rotation(
                            random.choice(USER_AGENTS)
                        )

                    # UA/viewport rotation every N pages
                    if pages_in_session >= pages_per_session:
                        pages_in_session = 0
                        try:
                            await context.close()
                            await browser.close()
                        except Exception:
                            pass
                        browser, context, page = await open_context_with_rotation(
                            random.choice(USER_AGENTS)
                        )

                    page_url = f"{self.base_url}?p={page_num}"
                    logger.info(f"\n📄 Loading page {page_num}/{last_page}: {page_url}")

                    page_loaded = False
                    for attempt in range(MAX_RETRIES):
                        try:
                            response = await page.goto(
                                page_url,
                                wait_until="domcontentloaded",
                                timeout=NAVIGATION_TIMEOUT,
                            )
                            if response and response.status == 403:
                                d = progressive_backoff(attempt)
                                logger.warning(
                                    f"HTTP 403 for GET {page_url}; backoff {d:.1f}s"
                                )
                                await asyncio.sleep(d)
                                # rotate session on repeated 403s
                                failures_in_session += 1
                                if failures_in_session >= rotate_on_failures:
                                    failures_in_session = 0
                                    try:
                                        await context.close()
                                        await browser.close()
                                    except Exception:
                                        pass
                                    (
                                        browser,
                                        context,
                                        page,
                                    ) = await open_context_with_rotation(
                                        random.choice(USER_AGENTS)
                                    )
                                continue

                            try:
                                consent_btn = page.locator(consent_button_selector)
                                if await consent_btn.is_visible(timeout=2000):
                                    await consent_btn.click(timeout=5000)
                                    await asyncio.sleep(1)
                            except Exception:
                                pass

                            await wait_for_main_content(page, consent_button_selector)
                            page_loaded = True
                            break
                        except Exception as e:
                            if attempt < MAX_RETRIES - 1:
                                d = progressive_backoff(attempt)
                                logger.warning(
                                    f"Page load failed: {e}; retrying in {d:.1f}s"
                                )
                                await asyncio.sleep(d)
                            else:
                                logger.error(f"Failed to load page {page_num}: {e}")

                    if not page_loaded:
                        consecutive_failures += 1
                        # Health check to differentiate broader outage
                        if not site_health_ok():
                            logger.warning(
                                "Site health check failed; pausing briefly before next attempt"
                            )
                            await asyncio.sleep(30)
                        page_num += 1  # skip to next page instead of getting stuck
                        pages_in_session += 1
                        continue

                    # Reset failure counters on success
                    consecutive_failures = 0
                    failures_in_session = 0
                    pages_in_session += 1

                    # Links
                    product_links = await get_product_links(page)
                    logger.info(
                        f"🔗 Page {page_num}: Found {len(product_links)} product links"
                    )
                    if not product_links:
                        logger.warning(f"No product links found on page {page_num}")
                        await sleep_page_delay()
                        page_num += 1
                        state["current_page"] = page_num
                        save_checkpoint()
                        continue

                    # Scrape products with comprehensive error handling
                    for local_idx, product_url in enumerate(product_links, 1):
                        if is_cancelled and is_cancelled():
                            logger.warning("🛑 Cancellation detected; aborting scrape")
                            should_stop = True
                            break

                        # Fix #2: Check circuit breaker before each product
                        if circuit_breaker_tripped:
                            browser, context, page = await handle_circuit_breaker()

                        # Fix #1: Skip if URL is permanently blocked
                        if is_blocked(product_url):
                            logger.info(
                                f"⏭️  Product {local_idx}: BLOCKED (in blocklist) - skipping"
                            )
                            global_idx += 1
                            continue

                        # Fix #3: Skip if URL already visited
                        if is_duplicate_url(product_url):
                            logger.info(
                                f"⏭️  Product {local_idx}: DUPLICATE URL - skipping"
                            )
                            state["duplicates_skipped"] += 1
                            global_idx += 1
                            continue

                        # Mark URL as seen
                        mark_url_seen(product_url)

                        # Fix #4: Apply adaptive rate limiting
                        delay = get_current_delay()
                        await asyncio.sleep(delay)

                        logger.info(
                            f"\n🔍 Product {local_idx}/{len(product_links)}: Scraping..."
                        )

                        # Rotate user-agent for each product to avoid detection
                        try:
                            current_ua = random.choice(USER_AGENTS)
                            await page.evaluate(f"""() => {{
                                Object.defineProperty(navigator, 'userAgent', {{
                                    get: () => '{current_ua}'
                                }});
                            }}""")
                        except Exception:
                            pass

                        # Fix #2: Wrap product navigation in retry loop with early exit
                        product_loaded = False
                        response = None
                        for product_attempt in range(MAX_RETRIES):
                            try:
                                response = await page.goto(
                                    product_url,
                                    wait_until="domcontentloaded",
                                    timeout=NAVIGATION_TIMEOUT,
                                )

                                # Check status immediately - DON'T retry 403/429
                                if response and response.status in [403, 429]:
                                    if response.status == 403:
                                        logger.error(
                                            f"❌ Product {local_idx}: HTTP 403 FORBIDDEN"
                                        )
                                        add_to_blocklist(product_url, 403)
                                        save_failed_url(product_url, "blocked_403", 403)
                                        record_403()
                                        adjust_delay_on_403()
                                    elif response.status == 429:
                                        logger.error(
                                            f"❌ Product {local_idx}: HTTP 429 RATE LIMITED"
                                        )
                                        add_to_blocklist(product_url, 429)
                                        save_failed_url(
                                            product_url, "rate_limited_429", 429
                                        )
                                        record_429()
                                        adjust_delay_on_429()

                                    # Fix #1: Check circuit breaker IMMEDIATELY after detection
                                    if circuit_breaker_tripped:
                                        (
                                            browser,
                                            context,
                                            page,
                                        ) = await handle_circuit_breaker()
                                        # Re-register handlers again (in case handle_circuit_breaker was just defined)
                                        page.on("requestfailed", _handle_request_failed)
                                        page.on("response", _handle_response)

                                    break  # Don't retry blocked URLs

                                if response and response.status >= 500:
                                    logger.error(
                                        f"❌ Product {local_idx}: HTTP {response.status} SERVER ERROR"
                                    )
                                    save_failed_url(
                                        product_url, "server_error", response.status
                                    )
                                    break

                                # Success - page loaded
                                product_loaded = True
                                break

                            except asyncio.TimeoutError:
                                logger.warning(
                                    f"Product attempt {product_attempt + 1}/{MAX_RETRIES} timed out after {NAVIGATION_TIMEOUT / 1000}s"
                                )
                                if product_attempt < MAX_RETRIES - 1:
                                    await asyncio.sleep(3)
                                else:
                                    save_failed_url(
                                        product_url,
                                        "timeout",
                                        None,
                                        f"Timeout after {MAX_RETRIES} attempts",
                                    )
                                    break
                            except Exception as e:
                                logger.warning(
                                    f"Product attempt {product_attempt + 1}/{MAX_RETRIES} failed: {str(e)[:100]}"
                                )
                                if product_attempt < MAX_RETRIES - 1:
                                    await asyncio.sleep(3)
                                else:
                                    save_failed_url(
                                        product_url,
                                        "navigation_error",
                                        None,
                                        str(e)[:200],
                                    )
                                    break

                        # Fix #3: Skip ALL remaining code if product didn't load or was blocked
                        if not product_loaded:
                            logger.error(
                                f"❌ Product {local_idx}: Failed to load - SKIPPING"
                            )
                            global_idx += 1
                            # Fix #6: Save checkpoint every 5 attempts (not just successes)
                            if global_idx % 5 == 0:
                                save_checkpoint()
                            continue

                        # ONLY check for main content if page loaded successfully
                        try:
                            await page.wait_for_selector("#main-content", timeout=5000)
                        except Exception:
                            logger.warning(
                                f"⚠️  Product {local_idx}: Main content not found within 5s"
                            )
                            save_failed_url(
                                product_url, "timeout", None, "Main content timeout"
                            )
                            global_idx += 1
                            if global_idx % 5 == 0:
                                save_checkpoint()
                            continue

                            await asyncio.sleep(1)  # Give page time to render

                            # Extract brand and name
                            brand = "Unknown"
                            try:
                                brand_elem = await page.locator(
                                    BRAND_XPATH
                                ).first.text_content(timeout=5000)
                                brand = brand_elem.strip() if brand_elem else "Unknown"
                            except Exception:
                                pass

                            product_name = "Unknown"
                            try:
                                name_elem = await page.locator(
                                    PRODUCT_NAME_XPATH
                                ).first.text_content(timeout=5000)
                                product_name = (
                                    name_elem.strip() if name_elem else "Unknown"
                                )
                            except Exception:
                                pass

                            # Fix #3: Check for duplicate product by brand+name
                            if is_duplicate_product(brand, product_name):
                                logger.info(
                                    f"⏭️  Product {local_idx}: DUPLICATE PRODUCT ({brand} - {product_name}) - skipping"
                                )
                                state["duplicates_skipped"] += 1
                                global_idx += 1
                                continue

                            # Get images
                            image_entries = await get_product_images(page)
                            sole_image_url = (
                                find_shoe_sole_image(image_entries)
                                if image_entries
                                else None
                            )

                            if not sole_image_url:
                                logger.warning(
                                    f"⚠️  Product {local_idx}: No sole image found"
                                )
                                save_failed_url(
                                    product_url,
                                    "no_data",
                                    None,
                                    "No sole image detected",
                                )
                                global_idx += 1
                                continue

                            # SUCCESS!
                            mark_product_seen(brand, product_name)
                            record_success()  # Fix #2: Reset circuit breaker counters
                            adjust_delay_on_success()  # Fix #4: Decrease delay on success

                            normalized_product = {
                                "brand": brand,
                                "name": product_name,
                                "url": product_url,
                                "image_url": sole_image_url,
                                "product_type": "shoe",
                            }
                            results.append(normalized_product)
                            current_batch.append(normalized_product)
                            state["products_scraped"] += 1
                            state["unique_products"] += 1
                            state["last_successful_index"] = local_idx

                            logger.info(
                                f"✅ Product {local_idx}: SUCCESS - {brand} - {product_name}"
                            )

                            # Process batch
                            if len(current_batch) >= batch_size and batch_callback:
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

                            # Fix #6: Checkpoint more frequently (every 5 successful products)
                            if state["products_scraped"] % 5 == 0:
                                save_checkpoint()

                            global_idx += 1

                        except asyncio.TimeoutError:
                            logger.error(
                                f"❌ Product {local_idx}: TIMEOUT after {NAVIGATION_TIMEOUT / 1000}s"
                            )
                            save_failed_url(
                                product_url,
                                "timeout",
                                None,
                                f"Timeout after {NAVIGATION_TIMEOUT / 1000}s",
                            )
                            global_idx += 1
                            # Fix #6: Save checkpoint on failures too
                            if global_idx % 5 == 0:
                                save_checkpoint()
                            continue

                        except Exception as e:
                            logger.error(
                                f"❌ Product {local_idx}: EXTRACTION ERROR - {str(e)[:100]}"
                            )
                            save_failed_url(
                                product_url, "extraction_error", None, str(e)[:200]
                            )
                            global_idx += 1
                            # Fix #6: Save checkpoint on failures too
                            if global_idx % 5 == 0:
                                save_checkpoint()
                            continue  # after page
                    if should_stop or shutting_down["flag"]:
                        save_checkpoint()
                        break

                    await sleep_page_delay()
                    page_num += 1
                    state["current_page"] = page_num
                    save_checkpoint()

                # flush remaining batch
                if current_batch and batch_callback and not should_stop:
                    prepared_batch = self._prepare_batch_for_processing(
                        current_batch,
                        brand_field="brand",
                        name_field="name",
                        url_field="url",
                        image_url_field="image_url",
                    )
                    if prepared_batch:
                        await batch_callback(prepared_batch)

                # Fix #10: Comprehensive final statistics
                logger.info("\n" + "=" * 80)
                logger.info("📊 SCRAPING COMPLETE - FINAL STATISTICS")
                logger.info("=" * 80)
                logger.info(f"✅ Products scraped: {state['products_scraped']}")
                logger.info(f"🎯 Unique products: {state['unique_products']}")
                logger.info(f"⏭️  Duplicates skipped: {state['duplicates_skipped']}")
                logger.info(f"🚫 URLs blocked: {state['blocked_count']}")
                logger.info(f"❌ URLs failed: {len(failed_urls_list)}")
                logger.info(f"📄 Pages completed: {page_num - start_page}")
                logger.info(f"💾 Checkpoint saved to: {checkpoint_file}")
                logger.info(f"📝 Failed URLs saved to: {failed_urls_file}")
                logger.info(f"🚫 Blocked URLs saved to: {blocked_urls_file}")
                logger.info("=" * 80)
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass

        return results


# Backwards/explicit name requested in requirements
class ZalandoScraperWithRecovery(ZalandoScraper):
    pass


async def get_pagination_info(page: Page) -> int:
    """
    Extract total page count from pagination element.
    Expected format: "Pagina 1 van 428" -> returns 428
    Falls back to checking page content if XPath fails.
    """
    try:
        # Try XPath first
        try:
            pagination_text = await page.text_content(PAGINATION_XPATH, timeout=5000)
            if pagination_text:
                parts = pagination_text.strip().split("van ")
                if len(parts) == 2:
                    total_pages = int(parts[1].strip())
                    logger.info(f"Found {total_pages} total pages")
                    return total_pages
        except Exception as e:
            logger.debug(f"XPath pagination failed, trying alternative method: {e}")

        # Fallback: look for pagination text anywhere on page
        page_content = await page.content()
        if "van" in page_content:
            # Try to find pattern like "Pagina 1 van 428"
            import re

            match = re.search(r"Pagina\s+\d+\s+van\s+(\d+)", page_content)
            if match:
                total_pages = int(match.group(1))
                logger.info(f"Found {total_pages} total pages (via regex)")
                return total_pages
    except Exception as e:
        logger.warning(f"Failed to extract pagination info: {e}")

    logger.info("Using default: 1 page")
    return 1


async def get_product_links(page: Page) -> List[str]:
    """
    Extract product links from the current page.
    Finds all <a> tags with href containing product URLs inside the products container.
    """
    try:
        # Try XPath container first, then fallback to CSS in main-content
        try:
            await page.locator(PRODUCTS_CONTAINER_XPATH).first.wait_for(timeout=8000)
            links = await page.locator(
                f'{PRODUCTS_CONTAINER_XPATH}//a[contains(@href, ".html")]'
            ).all()
        except Exception:
            await page.locator("#main-content").first.wait_for(timeout=8000)
            links = await page.locator('#main-content a[href*=".html"]').all()
        product_links = []

        for link in links:
            href = await link.get_attribute("href")
            if href and ".html" in href:
                # Ensure absolute URL
                if href.startswith("http"):
                    product_links.append(href)
                else:
                    product_links.append(f"https://www.zalando.nl{href}")

        logger.info(f"Found {len(product_links)} product links on this page")
        return product_links
    except Exception as e:
        logger.error(f"Failed to extract product links: {e}")
        return []


async def get_product_images(page: Page) -> List[Dict[str, str]]:
    """
    Extract all image URLs and their alt text from the images container on current product page.
    Returns a list of dictionaries: {"url": absolute_url, "alt": alt_text}
    """
    try:
        images = await page.locator(f"{IMAGES_CONTAINER_XPATH}//img").all()
        entries: List[Dict[str, str]] = []

        for img in images:
            try:
                # Try srcset first (responsive images), then src
                srcset = await img.get_attribute("srcset")
                src = await img.get_attribute("src")
                alt = await img.get_attribute("alt") or ""

                url = None
                if srcset:
                    # Extract first URL from srcset
                    url = srcset.split(",")[0].split()[0]
                elif src:
                    url = src

                if url and url.startswith("http"):
                    entries.append({"url": url, "alt": alt})
            except Exception as e:
                logger.debug(f"Failed to extract image info: {e}")
                continue

        logger.info(f"Found {len(entries)} product images (with alt text)")
        return entries
    except Exception as e:
        logger.debug(f"Failed to extract product images: {e}")
        return []


def find_shoe_sole_image(image_entries: List[Dict[str, str]]) -> str:
    """
    Identify shoe sole image by searching for keywords in the image alt text.

    Accepts image_entries as returned by `get_product_images`: list of {"url","alt"}.

    Returns the URL of the first image whose alt text contains a sole-related keyword
    in English, Dutch, or German. Returns None if no match.
    """
    if not image_entries:
        return None

    # Keywords in different languages (lowercase)
    keywords = [
        # English
        "sole",
        "outsole",
        "bottom",
        # Dutch
        "zool",
        "onderkant",
        "onderzijde",
        # German
        "sohle",
        "laufsohle",
    ]

    for idx, entry in enumerate(image_entries):
        alt = (entry.get("alt") or "").lower()
        url = entry.get("url")
        try:
            if not alt:
                # skip images without alt text
                continue

            # Split by ',' and check only the first segment (index 0)
            alt_parts = alt.split(",")
            first_part = alt_parts[0].strip() if alt_parts else ""

            if any(k in first_part for k in keywords):
                logger.info(
                    f"✓ Found shoe sole by alt (image {idx}): {url} (alt='{alt}')"
                )
                return url
        except Exception as e:
            logger.debug(f"Error checking alt for image {idx}: {e}")
            continue

    logger.warning("No shoe sole image detected via alt text in product images")
    return None


async def extract_product_details(page: Page, url: str) -> Dict[str, Any]:
    """
    Extract brand, product name, image count, and shoe sole image URL from a product detail page.
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)

        # Wait for main content instead of networkidle
        try:
            await page.wait_for_selector("#main-content", timeout=DEFAULT_TIMEOUT)
        except Exception:
            pass  # Continue even if main-content doesn't load

        await asyncio.sleep(1)  # Give page time to render

        # Extract brand
        brand = "Unknown"
        try:
            brand_elem = await page.locator(BRAND_XPATH).first.text_content(
                timeout=5000
            )
            brand = brand_elem.strip() if brand_elem else "Unknown"
        except Exception as e:
            logger.debug(f"Failed to extract brand: {e}")

        # Extract product name
        product_name = "Unknown"
        try:
            name_elem = await page.locator(PRODUCT_NAME_XPATH).first.text_content(
                timeout=5000
            )
            product_name = name_elem.strip() if name_elem else "Unknown"
        except Exception as e:
            logger.debug(f"Failed to extract product name: {e}")

        # Get product images
        image_entries = await get_product_images(page)
        image_count = len(image_entries)

        # Find shoe sole image via alt text
        sole_image_url = None
        if image_entries:
            logger.info(
                f"Analyzing {image_count} images for shoe sole detection (alt-text)..."
            )
            sole_image_url = find_shoe_sole_image(image_entries)

        logger.info(
            f"Extracted: {brand} - {product_name} ({image_count} images, sole: {'found' if sole_image_url else 'not found'})"
        )

        return {
            "brand": brand,
            "name": product_name,
            "source_url": url,
            "image_count": image_count,
            "sole_image_url": sole_image_url,
        }
    except Exception as e:
        logger.error(f"Failed to extract details from {url}: {e}")
        return None


async def scrape_zalando_shoes(
    url: str = "https://www.zalando.nl/schoenen",
    max_pages: int = None,
    headless: bool = True,
) -> List[Dict[str, Any]]:
    """
    Main scraper function.

    Args:
        url: Starting URL (Zalando shoes page)
        max_pages: Max pages to scrape (None = all pages)
        headless: Run browser in headless mode

    Returns:
        List of product dictionaries
    """
    products = []
    consent_button_selector = CONSENT_BUTTON_SELECTOR

    async with async_playwright() as p:
        browser, context, page = await launch_browser_context(p, headless=headless)

        try:
            # Navigate to base URL with retry logic
            logger.info(f"Navigating to {url}")
            for attempt in range(MAX_RETRIES):
                try:
                    await page.goto(
                        url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
                    )
                    # Wait for main content to load
                    await wait_for_main_content(page, consent_button_selector)
                    # Persist storage after first successful visit
                    try:
                        STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                        await page.context.storage_state(path=str(STORAGE_STATE_PATH))
                    except Exception:
                        pass
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            f"Navigation attempt {attempt + 1} failed: {e}. Retrying..."
                        )
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logger.error(f"Failed to navigate after {MAX_RETRIES} attempts")
                        raise

            # Get total pages
            total_pages = await get_pagination_info(page)
            pages_to_scrape = min(total_pages, max_pages) if max_pages else total_pages

            logger.info(f"Will scrape {pages_to_scrape} pages")

            for page_num in range(1, pages_to_scrape + 1):
                logger.info(f"\n--- Page {page_num} of {pages_to_scrape} ---")

                # Navigate to page with retry
                page_url = f"{url}?p={page_num}"
                for attempt in range(MAX_RETRIES):
                    try:
                        await page.goto(
                            page_url,
                            wait_until="domcontentloaded",
                            timeout=NAVIGATION_TIMEOUT,
                        )
                        await wait_for_main_content(page, consent_button_selector)
                        break
                    except Exception as e:
                        if attempt < MAX_RETRIES - 1:
                            logger.warning(
                                f"Page load attempt {attempt + 1} failed: {e}. Retrying..."
                            )
                            await asyncio.sleep(RETRY_DELAY)
                        else:
                            logger.error(f"Failed to load page {page_num}")
                            break

                # Get product links from this page
                product_links = await get_product_links(page)

                if not product_links:
                    logger.warning(f"No product links found on page {page_num}")

                # Extract details from each product
                for idx, product_url in enumerate(product_links, 1):
                    logger.info(f"  Product {idx}/{len(product_links)}: {product_url}")
                    details = await extract_product_details(page, product_url)
                    if details:
                        products.append(details)
                    await asyncio.sleep(1)  # Small delay between product requests

                # Pause between pages
                await asyncio.sleep(2)

            logger.info(f"\n✓ Scraping complete. Total products: {len(products)}")

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
        finally:
            await browser.close()

    return products


def print_products_summary(products: List[Dict[str, Any]]):
    """Print a summary of scraped products."""
    print("\n" + "=" * 120)
    print("SCRAPE SUMMARY - ZALANDO SHOES WITH SOLE DETECTION")
    print("=" * 120)
    for idx, p in enumerate(products, 1):
        print(f"\n{idx}. {p['brand']} - {p['name']}")
        print(f"   URL: {p['source_url']}")
        print(f"   Images: {p['image_count']}")
        if p.get("sole_image_url"):
            print(f"   ✓ Sole Image: {p['sole_image_url']}")
        else:
            print("   ✗ Sole Image: Not detected")
        print("-" * 120)

    print(f"\nTotal Products Scraped: {len(products)}")
    sole_detected = sum(1 for p in products if p.get("sole_image_url"))
    print(f"Products with Sole Images: {sole_detected}/{len(products)}")


def save_products_to_json(products: List[Dict[str, Any]], output_path: str):
    """Save products to JSON file."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(products)} products to {output_file}")


async def main():
    """Main entry point."""
    # Scrape first 2 pages (or set to None for all pages)
    products = await scrape_zalando_shoes(
        url="https://www.zalando.nl/schoenen",
        max_pages=None,
        headless=True,  # Set to True for headless mode
    )

    # Print summary
    print_products_summary(products)

    # Save to JSON
    output_path = Path(__file__).parent.parent / "data" / "zalando_shoes.json"
    save_products_to_json(products, str(output_path))


if __name__ == "__main__":
    asyncio.run(main())
