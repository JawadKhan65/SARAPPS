"""
Resilient Zalando Scraper with Production-Grade Error Handling

Features:
- Circuit breaker for automatic cooldown on repeated failures
- Adaptive rate limiting that responds to site behavior
- Product deduplication to prevent re-scraping
- Failed URL tracking with persistent storage
- Checkpoint/resume capability for crash recovery
- Graceful shutdown with progress preservation
- Comprehensive logging and error handling
- Stealth mode to reduce detection

NEVER HANGS - Always makes forward progress even after failures
"""

import asyncio
import json
import logging
import signal
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from collections import defaultdict
import random
import hashlib

from playwright.async_api import async_playwright, Page, BrowserContext
from PIL import Image
from io import BytesIO

# Import base scraper mixin
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from scrapers.base_scraper_mixin import BatchProcessingMixin

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class FailedUrl:
    """Record of a failed URL scrape attempt"""

    url: str
    reason: str
    status_code: Optional[int]
    timestamp: str
    retry_count: int
    error_message: str = ""


@dataclass
class Checkpoint:
    """Scraping progress checkpoint for resume capability"""

    current_page: int
    products_scraped: int
    unique_products: int
    last_successful_index: int
    blocked_urls_count: int
    failed_urls_count: int
    timestamp: str
    elapsed_seconds: float


class CircuitBreaker:
    """
    Prevents scraper from hammering blocked endpoints
    Trips after N consecutive failures, forces cooldown period
    """

    def __init__(
        self,
        max_consecutive_403: int = 3,
        max_consecutive_429: int = 3,
        cooldown_seconds: int = 300,
    ):
        self.max_consecutive_403 = max_consecutive_403
        self.max_consecutive_429 = max_consecutive_429
        self.cooldown_seconds = cooldown_seconds

        self.consecutive_403 = 0
        self.consecutive_429 = 0
        self.is_tripped = False
        self.trip_time: Optional[float] = None

        logger.info(
            f"🔌 Circuit breaker initialized: "
            f"403 threshold={max_consecutive_403}, "
            f"429 threshold={max_consecutive_429}, "
            f"cooldown={cooldown_seconds}s"
        )

    def record_403(self):
        """Record a 403 Forbidden error"""
        self.consecutive_403 += 1
        self.consecutive_429 = 0  # Reset 429 counter

        logger.warning(
            f"⚠️  HTTP 403 count: {self.consecutive_403}/{self.max_consecutive_403}"
        )

        if self.consecutive_403 >= self.max_consecutive_403:
            self._trip()

    def record_429(self):
        """Record a 429 Rate Limited error"""
        self.consecutive_429 += 1
        self.consecutive_403 = 0  # Reset 403 counter

        logger.warning(
            f"⚠️  HTTP 429 count: {self.consecutive_429}/{self.max_consecutive_429}"
        )

        if self.consecutive_429 >= self.max_consecutive_429:
            self._trip()

    def record_success(self):
        """Record successful scrape - resets all counters"""
        if self.consecutive_403 > 0 or self.consecutive_429 > 0:
            logger.info("✅ Success - resetting failure counters")

        self.consecutive_403 = 0
        self.consecutive_429 = 0

    def _trip(self):
        """Trip the circuit breaker"""
        if not self.is_tripped:
            self.is_tripped = True
            self.trip_time = time.time()
            logger.error(
                f"🔴 CIRCUIT BREAKER TRIPPED! "
                f"(403: {self.consecutive_403}, 429: {self.consecutive_429}) "
                f"Cooldown: {self.cooldown_seconds}s"
            )

    def check_and_wait(self) -> bool:
        """
        Check if circuit breaker is tripped
        If tripped and cooldown expired, reset and return True
        If still cooling down, return False
        """
        if not self.is_tripped:
            return True

        elapsed = time.time() - self.trip_time
        remaining = self.cooldown_seconds - elapsed

        if remaining <= 0:
            logger.info("🟢 Circuit breaker cooldown complete - resetting")
            self.reset()
            return True

        logger.warning(f"🔴 Circuit breaker active - {remaining:.1f}s remaining")
        return False

    def reset(self):
        """Reset circuit breaker to initial state"""
        self.consecutive_403 = 0
        self.consecutive_429 = 0
        self.is_tripped = False
        self.trip_time = None
        logger.info("🔌 Circuit breaker reset")


class AdaptiveRateLimiter:
    """
    Dynamically adjusts delays between requests based on site responses
    Increases delay on errors, decreases on success
    """

    def __init__(
        self,
        base_delay: float = 3.0,
        max_delay: float = 60.0,
        min_delay: float = 3.0,
        jitter_max: float = 2.0,
    ):
        self.base_delay = base_delay
        self.current_delay = base_delay
        self.max_delay = max_delay
        self.min_delay = min_delay
        self.jitter_max = jitter_max

        logger.info(
            f"⏱️  Rate limiter initialized: base={base_delay}s, max={max_delay}s"
        )

    def get_delay(self) -> float:
        """Get current delay with random jitter"""
        jitter = random.uniform(0, self.jitter_max)
        total = self.current_delay + jitter
        logger.debug(
            f"⏱️  Delay: {total:.2f}s (base: {self.current_delay:.2f}s + jitter: {jitter:.2f}s)"
        )
        return total

    async def wait(self):
        """Apply rate limit delay"""
        delay = self.get_delay()
        await asyncio.sleep(delay)

    def on_429(self):
        """Triple delay on rate limit"""
        old_delay = self.current_delay
        self.current_delay = min(self.current_delay * 3.0, self.max_delay)
        logger.warning(
            f"🐌 Rate limit hit - delay: {old_delay:.1f}s → {self.current_delay:.1f}s"
        )

    def on_403(self):
        """Double delay on forbidden"""
        old_delay = self.current_delay
        self.current_delay = min(self.current_delay * 2.0, self.max_delay)
        logger.warning(
            f"🚫 403 Forbidden - delay: {old_delay:.1f}s → {self.current_delay:.1f}s"
        )

    def on_success(self):
        """Decrease delay slightly on success"""
        old_delay = self.current_delay
        self.current_delay = max(self.current_delay * 0.9, self.min_delay)
        if old_delay != self.current_delay:
            logger.debug(
                f"✅ Success - delay: {old_delay:.1f}s → {self.current_delay:.1f}s"
            )

    def reset(self):
        """Reset to base delay"""
        self.current_delay = self.base_delay
        logger.info(f"⏱️  Rate limiter reset to {self.base_delay}s")


class ProductDeduplicator:
    """
    Prevents re-scraping same products
    Tracks by URL and by brand+name combination
    """

    def __init__(self):
        self.seen_urls: Set[str] = set()
        self.seen_products: Set[str] = set()

    def is_duplicate_url(self, url: str) -> bool:
        """Check if URL already scraped"""
        return url in self.seen_urls

    def is_duplicate_product(self, brand: str, name: str) -> bool:
        """Check if product (brand+name) already scraped"""
        product_key = self._make_product_key(brand, name)
        return product_key in self.seen_products

    def mark_url_seen(self, url: str):
        """Mark URL as seen"""
        self.seen_urls.add(url)

    def mark_product_seen(self, brand: str, name: str):
        """Mark product as seen"""
        product_key = self._make_product_key(brand, name)
        self.seen_products.add(product_key)

    def _make_product_key(self, brand: str, name: str) -> str:
        """Create unique key for brand+name"""
        combined = f"{brand.lower().strip()}::{name.lower().strip()}"
        return hashlib.md5(combined.encode()).hexdigest()

    def get_stats(self) -> Dict[str, int]:
        """Get deduplication statistics"""
        return {
            "unique_urls": len(self.seen_urls),
            "unique_products": len(self.seen_products),
        }


class FailedUrlTracker:
    """
    Tracks and persists failed URLs for later retry
    Separate files for blocked vs failed URLs
    """

    def __init__(self, failed_file: Path, blocked_file: Path):
        self.failed_file = failed_file
        self.blocked_file = blocked_file

        self.failed_urls: List[FailedUrl] = []
        self.blocked_urls: Set[str] = set()

        # Load existing data
        self._load_failed()
        self._load_blocked()

        logger.info(
            f"📝 URL tracker initialized: "
            f"{len(self.failed_urls)} failed, {len(self.blocked_urls)} blocked"
        )

    def is_blocked(self, url: str) -> bool:
        """Check if URL is in blocklist"""
        return url in self.blocked_urls

    def add_failed(
        self,
        url: str,
        reason: str,
        status_code: Optional[int] = None,
        retry_count: int = 0,
        error_message: str = "",
    ):
        """Add failed URL to tracker"""
        failed = FailedUrl(
            url=url,
            reason=reason,
            status_code=status_code,
            timestamp=datetime.now(timezone.utc).isoformat(),
            retry_count=retry_count,
            error_message=error_message,
        )

        self.failed_urls.append(failed)
        self._save_failed()

        logger.warning(f"❌ Failed URL recorded: {reason} - {url[:80]}")

    def add_blocked(self, url: str, status_code: int):
        """Add blocked URL (403/429) - will never retry"""
        if url not in self.blocked_urls:
            self.blocked_urls.add(url)
            self._save_blocked()

            # Also add to failed tracker
            self.add_failed(
                url=url,
                reason=f"blocked_{status_code}",
                status_code=status_code,
                error_message=f"Permanently blocked with HTTP {status_code}",
            )

            logger.error(f"🚫 URL BLOCKED: HTTP {status_code} - {url[:80]}")

    def _load_failed(self):
        """Load failed URLs from file"""
        if self.failed_file.exists():
            try:
                with open(self.failed_file, "r") as f:
                    data = json.load(f)
                    self.failed_urls = [FailedUrl(**item) for item in data]
            except Exception as e:
                logger.warning(f"Could not load failed URLs: {e}")

    def _load_blocked(self):
        """Load blocked URLs from file"""
        if self.blocked_file.exists():
            try:
                with open(self.blocked_file, "r") as f:
                    self.blocked_urls = set(json.load(f))
            except Exception as e:
                logger.warning(f"Could not load blocked URLs: {e}")

    def _save_failed(self):
        """Save failed URLs to file"""
        try:
            with open(self.failed_file, "w") as f:
                json.dump([asdict(url) for url in self.failed_urls], f, indent=2)
        except Exception as e:
            logger.error(f"Could not save failed URLs: {e}")

    def _save_blocked(self):
        """Save blocked URLs to file"""
        try:
            with open(self.blocked_file, "w") as f:
                json.dump(list(self.blocked_urls), f, indent=2)
        except Exception as e:
            logger.error(f"Could not save blocked URLs: {e}")

    def get_stats(self) -> Dict[str, int]:
        """Get tracker statistics"""
        return {
            "failed_urls": len(self.failed_urls),
            "blocked_urls": len(self.blocked_urls),
        }


class CheckpointManager:
    """
    Manages scraping checkpoints for resume capability
    Saves progress regularly and on shutdown
    """

    def __init__(self, checkpoint_file: Path):
        self.checkpoint_file = checkpoint_file
        self.start_time = time.time()

        logger.info(f"💾 Checkpoint manager initialized: {checkpoint_file}")

    def save(
        self,
        current_page: int,
        products_scraped: int,
        unique_products: int,
        last_successful_index: int,
        blocked_count: int,
        failed_count: int,
    ):
        """Save checkpoint"""
        checkpoint = Checkpoint(
            current_page=current_page,
            products_scraped=products_scraped,
            unique_products=unique_products,
            last_successful_index=last_successful_index,
            blocked_urls_count=blocked_count,
            failed_urls_count=failed_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=time.time() - self.start_time,
        )

        try:
            with open(self.checkpoint_file, "w") as f:
                json.dump(asdict(checkpoint), f, indent=2)

            logger.info(
                f"💾 Checkpoint saved: page={current_page}, "
                f"scraped={products_scraped}, unique={unique_products}"
            )
        except Exception as e:
            logger.error(f"Could not save checkpoint: {e}")

    def load(self) -> Optional[Checkpoint]:
        """Load checkpoint if exists"""
        if not self.checkpoint_file.exists():
            return None

        try:
            with open(self.checkpoint_file, "r") as f:
                data = json.load(f)
                checkpoint = Checkpoint(**data)

                logger.info(
                    f"📂 Checkpoint loaded: page={checkpoint.current_page}, "
                    f"scraped={checkpoint.products_scraped}"
                )

                return checkpoint
        except Exception as e:
            logger.warning(f"Could not load checkpoint: {e}")
            return None


class ResilientZalandoScraper(BatchProcessingMixin):
    """
    Production-grade Zalando scraper that NEVER HANGS

    Key features:
    - Circuit breaker prevents hammering blocked endpoints
    - Adaptive rate limiting responds to site behavior
    - Deduplication prevents re-scraping
    - Failed URL tracking with persistent storage
    - Checkpoint/resume for crash recovery
    - Graceful shutdown with progress preservation
    - Always makes forward progress
    """

    def __init__(
        self,
        base_url: str = "https://www.zalando.nl/schoenen",
        config_path: Optional[Path] = None,
    ):
        self.base_url = base_url

        # Load configuration
        if config_path is None:
            config_path = (
                Path(__file__).parent / "config" / "zalando_scraper_config.json"
            )

        with open(config_path, "r") as f:
            self.config = json.load(f)

        # Initialize components
        self.circuit_breaker = CircuitBreaker(
            max_consecutive_403=self.config["circuit_breaker"]["max_consecutive_403"],
            max_consecutive_429=self.config["circuit_breaker"]["max_consecutive_429"],
            cooldown_seconds=self.config["circuit_breaker"]["cooldown_seconds"],
        )

        self.rate_limiter = AdaptiveRateLimiter(
            base_delay=self.config["rate_limiting"]["base_delay"],
            max_delay=self.config["rate_limiting"]["max_delay"],
            min_delay=self.config["rate_limiting"]["min_delay"],
            jitter_max=self.config["rate_limiting"]["random_jitter_max"],
        )

        self.deduplicator = ProductDeduplicator()

        # File paths
        scraper_dir = Path(__file__).parent
        self.failed_tracker = FailedUrlTracker(
            failed_file=scraper_dir / self.config["checkpointing"]["failed_urls_file"],
            blocked_file=scraper_dir
            / self.config["checkpointing"]["blocked_urls_file"],
        )

        self.checkpoint_manager = CheckpointManager(
            checkpoint_file=scraper_dir
            / self.config["checkpointing"]["checkpoint_file"]
        )

        # Statistics
        self.stats = {
            "products_scraped": 0,
            "unique_products": 0,
            "duplicates_skipped": 0,
            "urls_blocked": 0,
            "urls_failed": 0,
            "pages_completed": 0,
        }

        # Shutdown flag
        self.shutdown_requested = False
        self._setup_signal_handlers()

        logger.info("🚀 Resilient Zalando Scraper initialized")

    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""

        def shutdown_handler(signum, frame):
            logger.warning(
                f"⚠️  Received signal {signum} - initiating graceful shutdown"
            )
            self.shutdown_requested = True

        try:
            signal.signal(signal.SIGTERM, shutdown_handler)
            signal.signal(signal.SIGINT, shutdown_handler)
        except Exception as e:
            logger.warning(f"Could not setup signal handlers: {e}")

    async def scrape(
        self,
        max_pages: Optional[int] = None,
        batch_callback: Optional[Callable] = None,
        batch_size: int = 50,
        is_cancelled: Optional[Callable] = None,
    ):
        """
        Main scraping method with full resilience

        GUARANTEES:
        - Never hangs on blocked URLs
        - Always makes forward progress
        - Saves checkpoints regularly
        - Handles shutdown gracefully
        """
        logger.info("=" * 80)
        logger.info("🎯 Starting resilient Zalando scrape")
        logger.info("=" * 80)

        # Load checkpoint if exists
        checkpoint = self.checkpoint_manager.load()
        start_page = checkpoint.current_page if checkpoint else 1

        results = []
        current_batch = []

        async with async_playwright() as p:
            # Launch browser with stealth
            browser, context, page = await self._launch_stealth_browser(p)

            try:
                # Navigate to base URL
                await self._navigate_with_retry(page, self.base_url)

                # Get total pages
                total_pages = await self._get_total_pages(page)
                pages_to_scrape = (
                    min(total_pages, max_pages) if max_pages else total_pages
                )

                logger.info(f"📄 Will scrape pages {start_page} to {pages_to_scrape}")

                # Main scraping loop
                for page_num in range(start_page, pages_to_scrape + 1):
                    # Check for shutdown or cancellation
                    if self.shutdown_requested or (is_cancelled and is_cancelled()):
                        logger.warning(
                            "🛑 Shutdown requested - saving progress and exiting"
                        )
                        break

                    # Check circuit breaker
                    if not self.circuit_breaker.check_and_wait():
                        logger.warning(
                            "⏸️  Circuit breaker active - waiting for cooldown"
                        )
                        await asyncio.sleep(self.circuit_breaker.cooldown_seconds)

                        # Reset context after cooldown
                        await context.close()
                        context = await self._create_new_context(browser)
                        page = await context.new_page()
                        self.rate_limiter.reset()
                        continue

                    logger.info(f"\n{'=' * 80}")
                    logger.info(f"📄 PAGE {page_num}/{pages_to_scrape}")
                    logger.info(f"{'=' * 80}")

                    # Navigate to page
                    page_url = f"{self.base_url}?p={page_num}"
                    nav_success = await self._navigate_with_retry(page, page_url)

                    if not nav_success:
                        logger.error(f"❌ Could not load page {page_num} - skipping")
                        continue

                    # Get product links
                    product_links = await self._extract_product_links(page)

                    if not product_links:
                        logger.warning(f"⚠️  No products found on page {page_num}")
                        continue

                    logger.info(f"🔗 Found {len(product_links)} product links")

                    # Scrape each product
                    for idx, product_url in enumerate(product_links, 1):
                        # Check shutdown
                        if self.shutdown_requested or (is_cancelled and is_cancelled()):
                            break

                        # Check circuit breaker before each product
                        if not self.circuit_breaker.check_and_wait():
                            logger.warning(
                                "🔴 Circuit breaker tripped - saving and pausing"
                            )
                            self._save_checkpoint(page_num, idx)
                            await asyncio.sleep(self.circuit_breaker.cooldown_seconds)

                            # Reset after cooldown
                            await context.close()
                            context = await self._create_new_context(browser)
                            page = await context.new_page()
                            self.rate_limiter.reset()
                            self.circuit_breaker.reset()
                            continue

                        # Check if blocked
                        if self.failed_tracker.is_blocked(product_url):
                            logger.info(
                                f"⏭️  Product {idx}: BLOCKED (in blocklist) - skipping"
                            )
                            continue

                        # Check if duplicate URL
                        if self.deduplicator.is_duplicate_url(product_url):
                            logger.info(f"⏭️  Product {idx}: DUPLICATE URL - skipping")
                            self.stats["duplicates_skipped"] += 1
                            continue

                        # Mark URL as seen
                        self.deduplicator.mark_url_seen(product_url)

                        # Apply rate limiting
                        await self.rate_limiter.wait()

                        # Scrape product
                        logger.info(
                            f"\n🔍 Product {idx}/{len(product_links)}: Scraping..."
                        )
                        product = await self._scrape_product_resilient(
                            page, product_url, idx
                        )

                        if product:
                            # Check for duplicate product by name
                            if self.deduplicator.is_duplicate_product(
                                product.get("brand", ""), product.get("name", "")
                            ):
                                logger.info(
                                    f"⏭️  Product {idx}: DUPLICATE PRODUCT - skipping"
                                )
                                self.stats["duplicates_skipped"] += 1
                                continue

                            # Mark product as seen
                            self.deduplicator.mark_product_seen(
                                product.get("brand", ""), product.get("name", "")
                            )

                            results.append(product)
                            current_batch.append(product)
                            self.stats["products_scraped"] += 1
                            self.stats["unique_products"] += 1

                            logger.info(
                                f"✅ Product {idx}: SUCCESS - {product['brand']} - {product['name']}"
                            )

                            # Process batch
                            if len(current_batch) >= batch_size and batch_callback:
                                prepared = self._prepare_batch_for_processing(
                                    current_batch,
                                    brand_field="brand",
                                    name_field="name",
                                    url_field="url",
                                    image_url_field="image_url",
                                )

                                if prepared:
                                    should_continue = await batch_callback(prepared)
                                    if not should_continue:
                                        logger.warning(
                                            "🛑 Batch callback returned False - stopping"
                                        )
                                        self.shutdown_requested = True
                                        break

                                current_batch = []

                            # Save checkpoint periodically
                            if (
                                self.stats["products_scraped"]
                                % self.config["checkpointing"]["save_every_n_products"]
                                == 0
                            ):
                                self._save_checkpoint(page_num, idx)

                        else:
                            logger.warning(f"❌ Product {idx}: FAILED")

                    self.stats["pages_completed"] += 1

                    # Save checkpoint after each page
                    self._save_checkpoint(page_num, len(product_links))

                # Process final batch
                if current_batch and batch_callback and not self.shutdown_requested:
                    prepared = self._prepare_batch_for_processing(
                        current_batch,
                        brand_field="brand",
                        name_field="name",
                        url_field="url",
                        image_url_field="image_url",
                    )

                    if prepared:
                        await batch_callback(prepared)

            finally:
                # Always cleanup
                try:
                    await context.close()
                    await browser.close()
                except Exception:
                    pass

                # Final checkpoint
                self._save_checkpoint(pages_to_scrape, 0)

                # Print final statistics
                self._print_final_stats()

        return results

    async def _scrape_product_resilient(
        self, page: Page, url: str, product_index: int
    ) -> Optional[Dict]:
        """
        Scrape single product with full error handling
        NEVER HANGS - Always returns (success or failure) within timeout
        """
        max_retries = self.config["retries"]["max_per_url"]

        for attempt in range(1, max_retries + 1):
            try:
                # Navigate with timeout
                logger.debug(
                    f"  Attempt {attempt}/{max_retries}: Navigating to {url[:80]}"
                )

                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.config["timeouts"]["page_load"],
                )

                # Check response status
                if response:
                    status = response.status

                    # Handle blocking responses
                    if status == 403:
                        self.failed_tracker.add_blocked(url, 403)
                        self.circuit_breaker.record_403()
                        self.rate_limiter.on_403()
                        self.stats["urls_blocked"] += 1
                        logger.error(f"  🚫 HTTP 403 FORBIDDEN - URL BLOCKED")
                        return None  # NEVER RETRY

                    elif status == 429:
                        self.failed_tracker.add_blocked(url, 429)
                        self.circuit_breaker.record_429()
                        self.rate_limiter.on_429()
                        self.stats["urls_blocked"] += 1
                        logger.error(f"  🚫 HTTP 429 RATE LIMITED - URL BLOCKED")
                        return None  # NEVER RETRY

                    elif status >= 500:
                        logger.warning(f"  ⚠️  HTTP {status} Server Error")
                        if attempt < max_retries:
                            await asyncio.sleep(2)
                            continue
                        else:
                            self.failed_tracker.add_failed(
                                url, "server_error", status, attempt
                            )
                            return None

                # Extract product details
                product = await self._extract_product_details(page, url)

                if not product or not product.get("sole_image_url"):
                    logger.warning(f"  ⚠️  No data extracted")

                    if attempt < max_retries:
                        await asyncio.sleep(1)
                        continue
                    else:
                        self.failed_tracker.add_failed(
                            url,
                            "no_data",
                            None,
                            attempt,
                            "Could not extract product data",
                        )
                        self.stats["urls_failed"] += 1
                        return None

                # SUCCESS
                self.circuit_breaker.record_success()
                self.rate_limiter.on_success()
                return product

            except asyncio.TimeoutError:
                logger.warning(f"  ⏱️  Timeout on attempt {attempt}")

                if attempt < max_retries:
                    continue
                else:
                    self.failed_tracker.add_failed(
                        url, "timeout", None, attempt, "Page load timeout"
                    )
                    self.stats["urls_failed"] += 1
                    return None

            except Exception as e:
                logger.error(f"  ❌ Error on attempt {attempt}: {e}")

                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue
                else:
                    self.failed_tracker.add_failed(
                        url, "extraction_error", None, attempt, str(e)
                    )
                    self.stats["urls_failed"] += 1
                    return None

        return None

    async def _navigate_with_retry(self, page: Page, url: str) -> bool:
        """Navigate to URL with retry logic"""
        max_retries = self.config["retries"]["max_per_page"]

        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(f"Navigating to {url} (attempt {attempt}/{max_retries})")

                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.config["timeouts"]["navigation"],
                )

                if response and response.status < 400:
                    # Wait for main content
                    try:
                        await page.wait_for_selector(
                            "#main-content",
                            timeout=self.config["timeouts"]["stuck_page_check"] * 1000,
                        )
                    except Exception:
                        logger.warning("Main content not found quickly, but continuing")

                    return True

                logger.warning(
                    f"Navigation returned status {response.status if response else 'unknown'}"
                )

                if attempt < max_retries:
                    await asyncio.sleep(2)
                    continue

            except Exception as e:
                logger.error(f"Navigation error: {e}")

                if attempt < max_retries:
                    await asyncio.sleep(2)
                    continue

        return False

    async def _extract_product_links(self, page: Page) -> List[str]:
        """Extract product links from listing page"""
        try:
            # Wait for products
            await page.wait_for_selector(
                'article[data-testid="product-card"]', timeout=10000
            )

            # Extract links
            links = await page.eval_on_selector_all(
                'article[data-testid="product-card"] a',
                """
                elements => elements
                    .map(el => el.href)
                    .filter(href => href && href.includes('/schoenen'))
                """,
            )

            # Deduplicate and validate
            unique_links = list(
                set([link for link in links if link and link.startswith("http")])
            )

            return unique_links

        except Exception as e:
            logger.error(f"Error extracting product links: {e}")
            return []

    async def _extract_product_details(self, page: Page, url: str) -> Optional[Dict]:
        """Extract product details from product page"""
        try:
            # Wait for product info
            await page.wait_for_selector("h1", timeout=10000)

            # Extract brand and name
            brand = (
                await page.eval_on_selector(
                    'h1 a[href*="/"]', 'el => el ? el.textContent.trim() : "Unknown"'
                )
                or "Unknown"
            )

            name = (
                await page.eval_on_selector(
                    "h1 span:last-child", 'el => el ? el.textContent.trim() : "Unknown"'
                )
                or "Unknown"
            )

            # Extract images
            image_urls = await page.eval_on_selector_all(
                'img[src*="mosaic"]',
                "elements => elements.map(el => el.src).filter(src => src)",
            )

            if not image_urls:
                return None

            # Find sole image (use last image as heuristic)
            sole_image_url = image_urls[-1] if len(image_urls) > 1 else image_urls[0]

            return {
                "brand": brand,
                "name": name,
                "url": url,
                "image_url": sole_image_url,
                "product_type": "shoe",
                "image_count": len(image_urls),
            }

        except Exception as e:
            logger.error(f"Error extracting product details: {e}")
            return None

    async def _get_total_pages(self, page: Page) -> int:
        """Get total number of pages"""
        try:
            # Try to find pagination
            pagination_text = await page.eval_on_selector(
                'nav[aria-label="pagination"] span', "el => el ? el.textContent : null"
            )

            if pagination_text and "van" in pagination_text:
                # Extract number after "van"
                parts = pagination_text.split("van")
                if len(parts) > 1:
                    total = int(parts[1].strip())
                    return total

            # Fallback: assume 428 pages (known from previous runs)
            return 428

        except Exception as e:
            logger.warning(f"Could not determine total pages: {e}, assuming 428")
            return 428

    async def _launch_stealth_browser(self, playwright):
        """Launch browser with stealth configuration"""
        user_agent = random.choice(self.config["stealth"]["user_agents"])
        viewport = random.choice(self.config["stealth"]["viewports"])

        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        context = await browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            locale="nl-NL",
            timezone_id="Europe/Amsterdam",
        )

        # Add stealth scripts
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """)

        page = await context.new_page()

        # Setup request blocking
        await self._setup_request_blocking(page)

        page.set_default_timeout(self.config["timeouts"]["default"])
        page.set_default_navigation_timeout(self.config["timeouts"]["navigation"])

        return browser, context, page

    async def _create_new_context(self, browser):
        """Create new browser context with fresh settings"""
        user_agent = random.choice(self.config["stealth"]["user_agents"])
        viewport = random.choice(self.config["stealth"]["viewports"])

        context = await browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            locale="nl-NL",
            timezone_id="Europe/Amsterdam",
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        return context

    async def _setup_request_blocking(self, page: Page):
        """Block unnecessary requests to reduce detection"""
        blocked_domains = self.config["blocking"]["domains"]
        blocked_paths = self.config["blocking"]["paths"]

        async def route_handler(route):
            url = route.request.url

            # Block by domain
            if any(domain in url for domain in blocked_domains):
                await route.abort()
                return

            # Block by path
            if any(path in url for path in blocked_paths):
                await route.abort()
                return

            # Block POST to analytics
            if route.request.method == "POST" and "/api/" in url:
                await route.abort()
                return

            await route.continue_()

        await page.route("**/*", route_handler)

    def _save_checkpoint(self, current_page: int, last_index: int):
        """Save current progress checkpoint"""
        self.checkpoint_manager.save(
            current_page=current_page,
            products_scraped=self.stats["products_scraped"],
            unique_products=self.stats["unique_products"],
            last_successful_index=last_index,
            blocked_count=len(self.failed_tracker.blocked_urls),
            failed_count=len(self.failed_tracker.failed_urls),
        )

    def _print_final_stats(self):
        """Print final scraping statistics"""
        logger.info("\n" + "=" * 80)
        logger.info("📊 FINAL STATISTICS")
        logger.info("=" * 80)
        logger.info(f"✅ Products scraped: {self.stats['products_scraped']}")
        logger.info(f"🎯 Unique products: {self.stats['unique_products']}")
        logger.info(f"⏭️  Duplicates skipped: {self.stats['duplicates_skipped']}")
        logger.info(f"🚫 URLs blocked: {self.stats['urls_blocked']}")
        logger.info(f"❌ URLs failed: {self.stats['urls_failed']}")
        logger.info(f"📄 Pages completed: {self.stats['pages_completed']}")
        logger.info("=" * 80)


# Convenience function for direct usage
async def scrape_zalando_resilient(
    base_url: str = "https://www.zalando.nl/schoenen",
    max_pages: Optional[int] = None,
    config_path: Optional[Path] = None,
) -> List[Dict]:
    """
    Scrape Zalando with full resilience

    Args:
        base_url: Starting URL
        max_pages: Maximum pages to scrape (None = all)
        config_path: Path to config file (uses default if None)

    Returns:
        List of scraped products
    """
    scraper = ResilientZalandoScraper(base_url, config_path)
    return await scraper.scrape(max_pages=max_pages)


if __name__ == "__main__":
    # Test scraping
    asyncio.run(scrape_zalando_resilient(max_pages=5))
