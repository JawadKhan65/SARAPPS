import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests
from PIL import Image
from io import BytesIO

from playwright.async_api import async_playwright, Page
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
NAV_TIMEOUT = 60000  # Increased to 60s for slow networks
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


class AmazonScraper(BatchProcessingMixin):
    def __init__(self):
        logger.info("Initializing CLIP sole detector model...")
        self.clip = SoleDetectorCLIP()
        logger.info("✓ CLIP model loaded")
        self.products = []  # Store scraped products

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

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--disable-extensions'
                ]
            )
            context = await browser.new_context(
                user_agent=USER_AGENT,
                locale="en-US",
                extra_http_headers={"Accept-Language": ACCEPT_LANGUAGE},
            )
            page = await context.new_page()

            # Set viewport to standard size
            await page.set_viewport_size({"width": 1280, "height": 1024})

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
                    try:
                        page = await self.navigate_with_retries(
                            page, page_url, max_retries=3, first_wait="domcontentloaded"
                        )
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.warning(f"Failed to load page {pg}: {e}")
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
                        try:
                            logger.info(
                                f"\n  Product {global_idx}/{len(page_links)} (Page {pg}): Scraping..."
                            )
                            product_data = await self.extract_product_details(page, url)

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
                                f"[Page {pg}:Product {global_idx}] Failed to extract {url}: {e}"
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

            except Exception as e:
                logger.error(f"Scraper failed: {e}", exc_info=True)
            finally:
                await context.close()
                await browser.close()


async def main():
    scraper = AmazonScraper()
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-extensions'
            ]
        )
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
