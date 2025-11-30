"""
Military1st footwear scraper using Playwright.
Scrapes product links, images, and detects sole images using CLIP model.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests
from PIL import Image
from io import BytesIO

from playwright.async_api import async_playwright, Page

# Add parent directory to path to import ml_models
sys.path.insert(0, str(Path(__file__).parent.parent))
from ml_models.clip_model import SoleDetectorCLIP
from scrapers.base_scraper_mixin import BatchProcessingMixin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://www.military1st.eu/footwear/boots"
NAVIGATION_TIMEOUT = 60000  # 60s for slow networks
SELECTOR_TIMEOUT = 15000  # 15s for lazy-loaded elements
SCROLL_PAUSE = 0.6
IMAGE_DOWNLOAD_TIMEOUT = 10
MAX_DOWNLOAD_RETRIES = 3


class Military1stScraper(BatchProcessingMixin):
    def __init__(self):
        """Initialize the scraper with CLIP model for sole detection."""
        logger.info("Initializing CLIP sole detector model...")
        self.clip = SoleDetectorCLIP()
        logger.info("✓ CLIP model loaded")
        self.products = []  # Store scraped products

    async def get_total_pages(self, page: Page) -> int:
        """
        Extract total number of pages from pagination using XPath.
        Gets the last li element in the pagination and extracts the page number.
        XPath: //*[@id="amasty-shopby-product-list"]/div[3]/div[1]/ul
        """
        try:
            logger.info("⏳ Searching for pagination using XPath...")

            # XPath to the pagination list
            pagination_xpath = '//*[@id="amasty-shopby-product-list"]/div[3]/div[1]/ul'

            # Try to get pagination with XPath
            try:
                pagination = page.locator(f"xpath={pagination_xpath}").first
                count = await pagination.count()
                logger.debug(f"Pagination locator count: {count}")

                if count > 0:
                    logger.info("✓ Pagination element found via XPath")
                    # Scroll pagination into view to ensure it's fully loaded
                    await pagination.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)

                    # Get all li elements and debug
                    li_count = await page.evaluate(
                        "(xpath) => { const el = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; if(!el) return 0; return el.querySelectorAll('li').length; }",
                        pagination_xpath,
                    )
                    logger.info(f"📄 Found {li_count} li elements in pagination")

                    logger.info(f"✓ Pagination detected: {li_count} pages")
                    return li_count
                else:
                    logger.info("⚠️  Pagination element not found via XPath (count = 0)")
            except Exception as e:
                logger.error(f"❌ Error checking pagination: {e}")
                import traceback

                traceback.print_exc()

            logger.info("No pagination found, assuming 1 page")
            return 1
        except Exception as e:
            logger.warning(f"Failed to get total pages: {e}")
            import traceback

            traceback.print_exc()
            return 1

    async def collect_product_links(self, page: Page) -> List[str]:
        """
        Collect product links from all pages using pagination param 'p'.
        """
        logger.info("Step 1: Collecting product links...")

        # Load initial page
        try:
            await page.goto(
                BASE_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
            )
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Failed to load initial page: {e}")
            return []

        # Detect total pages
        total_pages = await self.get_total_pages(page)
        logger.info(f"🧭 Detected {total_pages} pages")

        links: List[str] = []

        async def extract_links_from_page():
            """Extract all product links from current page."""
            try:
                # Wait for product container
                await page.wait_for_selector(
                    "ol.products",
                    timeout=SELECTOR_TIMEOUT,
                )
                logger.debug("✓ Product container found")
            except Exception as e:
                logger.warning(f"Product container not found: {e}")
                return

            # Scroll to load all products on page
            previous_count = 0
            for iteration in range(12):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(SCROLL_PAUSE)

                items = page.locator("ol.products li.item")
                elems = await items.count()
                logger.debug(f"Scroll iteration {iteration}: {elems} items found")
                if elems == previous_count:
                    logger.debug("✓ No new items loaded, stopping scroll")
                    break
                previous_count = elems

            logger.debug(f"Total items after scrolling: {previous_count}")

            # Extract links from each product
            items = page.locator("ol.products li.item")
            count = await items.count()
            logger.info(f"📦 Extracting {count} product links from page")

            for i in range(count):
                try:
                    item = items.nth(i)
                    # First try to find a.product-item-link (the actual product detail link)
                    link_el = item.locator("a.product-item-link").first

                    if await link_el.count() == 0:
                        logger.debug(
                            f"Item {i}: No a.product-item-link found, trying first a tag"
                        )
                        link_el = item.locator("a").first

                    if await link_el.count() > 0:
                        href = await link_el.get_attribute("href")
                        logger.debug(f"Item {i}: href = {href}")
                        if href and href != "javascript:void(0)":
                            # Fix malformed URLs from website (httpps://, htttps://, etc.)
                            href = href.replace("httpps://", "https://")
                            href = href.replace("htttps://", "https://")
                            href = href.replace("httttp://", "http://")

                            # Normalize to absolute URL
                            if href.startswith("/"):
                                href = "https://www.military1st.eu" + href
                            elif not href.startswith("http"):
                                href = "https://www.military1st.eu/" + href

                            if href not in links:
                                links.append(href)
                                logger.debug(f"  ✓ Added: {href[:80]}")
                            else:
                                logger.debug(f"  ⚠️  Duplicate: {href[:80]}")
                        else:
                            logger.debug(f"Item {i}: Skipping invalid href: {href}")
                    else:
                        logger.debug(f"Item {i}: No anchor tag found")
                except Exception as e:
                    logger.debug(f"Failed to extract link for item {i}: {e}")

        # Iterate through pages
        for page_num in range(1, int(total_pages) + 1):
            page_url = f"{BASE_URL}?p={page_num}" if page_num > 1 else BASE_URL
            logger.info(f"📄 Loading page {page_num}/{total_pages}: {page_url}")

            try:
                await page.goto(
                    page_url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
                )
                await asyncio.sleep(2)
                await extract_links_from_page()
            except Exception as e:
                logger.warning(f"Failed to load/extract page {page_num}: {e}")
                continue

        logger.info(f"✅ Collected {len(links)} product links")
        return links

    async def extract_product_details(self, page: Page, url: str) -> Dict[str, Any]:
        """
        Visit product page and extract product name and images.
        Then download images and run CLIP to pick the sole image.
        """
        logger.info(f"  Scraping: {url[:80]}")
        result: Dict[str, Any] = {
            "url": url,
            "product_name": None,
            "images": [],
            "sole": None,
        }

        try:
            await page.goto(
                url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
            )
            await asyncio.sleep(1)

            # Extract product name from h1.page-title span.base
            try:
                title_el = page.locator("h1.page-title span.base").first
                if await title_el.count() > 0:
                    title = await title_el.text_content()
                    result["product_name"] = title.strip() if title else "Unknown"
                else:
                    result["product_name"] = "Unknown"
            except Exception as e:
                logger.debug(f"Failed to get product name: {e}")
                result["product_name"] = "Unknown"

            # Scroll to load images
            for _ in range(6):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(0.5)

            # Extract images from div.slick-track
            try:
                slick_track = page.locator("div.slick-track").first
                if await slick_track.count() > 0:
                    images = slick_track.locator("img")
                    img_count = await images.count()
                    logger.info(f"📸 Found {img_count} images")

                    for i in range(img_count):
                        try:
                            img = images.nth(i)
                            src = await img.get_attribute("src")
                            if src:
                                # Handle protocol-relative and relative URLs
                                if src.startswith("//"):
                                    src = "https:" + src
                                elif src.startswith("/"):
                                    src = "https://www.military1st.eu" + src
                                elif not src.startswith("http"):
                                    src = "https://www.military1st.eu/" + src

                                if src not in result["images"]:
                                    result["images"].append(src)
                        except Exception as e:
                            logger.debug(f"Failed to get image {i}: {e}")
                else:
                    logger.warning("No slick-track container found")
            except Exception as e:
                logger.warning(f"Failed to extract images: {e}")

            # Download images and check with CLIP
            best = None
            checked: List[Dict[str, Any]] = []

            logger.info(
                f"🔍 Running CLIP sole detection on {len(result['images'])} images..."
            )
            for idx, img_url in enumerate(result["images"], 1):
                try:
                    pil = await asyncio.get_event_loop().run_in_executor(
                        None, self.download_image, img_url
                    )
                    if pil is None:
                        logger.debug(f"  Image {idx}: Failed to download")
                        continue

                    is_sole, conf, scores = self.clip.is_sole(pil)
                    sole_status = "✓ SOLE" if is_sole else "✗ NOT SOLE"
                    logger.info(
                        f"  Image {idx}: {sole_status} (confidence: {conf:.3f})"
                    )
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
                # Choose highest confidence
                best = max(soles, key=lambda x: x.get("confidence", 0))
                logger.info(
                    f"✅ Sole image found! Confidence: {best.get('confidence', 0):.3f}"
                )
                logger.info(f"📷 Sole image URL: {best.get('url')}")
            else:
                # Fallback: pick highest confidence even if not-is_sole
                if checked:
                    best = max(checked, key=lambda x: x.get("confidence", 0))
                    logger.warning(
                        f"⚠️  No sole detected, using highest confidence image (confidence: {best.get('confidence', 0):.3f})"
                    )
                    logger.info(f"📷 Fallback image URL: {best.get('url')}")
                else:
                    logger.warning("⚠️  No images could be processed")

            result["checked_images"] = checked
            result["sole"] = best

        except Exception as e:
            logger.error(f"Error scraping product {url}: {e}")

        return result

    def download_image(self, url: str) -> Optional[Image.Image]:
        """Download image with retries and return PIL Image or None."""
        if not url:
            return None

        # Headers to avoid 403 Forbidden
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.military1st.eu/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-origin",
        }

        for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
            try:
                resp = requests.get(
                    url, timeout=IMAGE_DOWNLOAD_TIMEOUT, headers=headers
                )
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
        1. Launch browser and navigate to base URL
        2. Collect all product links
        3. Extract product details for each link
        4. Process products in batches
        """
        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

        logger.info("Starting Military1st scraper")
        logger.info(f"Base URL: {BASE_URL}")
        if batch_callback:
            logger.info("Using real-time batch processing")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--disable-extensions'
                ]
            )
            page = await browser.new_page()

            # Set viewport to standard size
            await page.set_viewport_size({"width": 1280, "height": 1024})

            try:
                # Step 1: Collect product links
                links = await self.collect_product_links(page)

                if not links:
                    logger.error("❌ No product links collected!")
                    await browser.close()
                    return

                # Limit for safety during run
                links = links[:100]  # Adjust as needed
                logger.info(f"📌 Processing {len(links)} product links")

                # Step 2: Process products with batch support
                results = []
                current_batch = []
                should_stop = False

                for idx, url in enumerate(links, 1):
                    # Check for cancellation
                    if is_cancelled and is_cancelled():
                        logger.warning(
                            "🛑 Cancellation detected - stopping scraper immediately"
                        )
                        should_stop = True
                        break

                    if should_stop:
                        logger.info(
                            "Stopping scraper early due to batch callback signal"
                        )
                        break

                    try:
                        logger.info(f"[{idx}/{len(links)}] Processing: {url}")
                        product_data = await self.extract_product_details(page, url)

                        # Only add products that have a sole image
                        if product_data and product_data.get("sole"):
                            sole_info = product_data["sole"]

                            # Log scraped product details
                            logger.info(f"✅ Scraped Product #{idx}:")
                            logger.info(f"   Brand: Military 1st")
                            logger.info(
                                f"   Product Name: {product_data.get('product_name', 'Unknown')}"
                            )
                            logger.info(f"   Product URL: {product_data['url']}")
                            logger.info(
                                f"   Sole Image URL: {sole_info.get('url', 'N/A')[:80]}..."
                            )
                            logger.info(
                                f"   Sole Confidence: {sole_info.get('confidence', 0):.3f}"
                            )
                            logger.info(
                                f"   Total Images Found: {len(product_data.get('images', []))}"
                            )

                            # Normalize to expected format
                            normalized_product = {
                                "brand": "Military 1st",
                                "name": product_data.get("product_name", "Unknown"),
                                "url": product_data["url"],
                                "image_url": sole_info.get("url"),
                                "product_type": "boot",
                            }

                            results.append(normalized_product)
                            current_batch.append(normalized_product)

                            # Process batch when size is reached
                            if len(current_batch) >= batch_size and batch_callback:
                                logger.info(
                                    f"Processing batch of {len(current_batch)} products..."
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
                                    should_continue = await batch_callback(
                                        prepared_batch
                                    )
                                    if not should_continue:
                                        should_stop = True
                                        logger.info(
                                            "Batch callback returned False, stopping scraper"
                                        )

                                current_batch = []  # Reset batch
                        else:
                            logger.warning(f"  ⚠️  No sole image found for {url}")

                    except Exception as e:
                        logger.error(
                            f"[{idx}/{len(links)}] Failed to extract {url}: {e}"
                        )
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
                await browser.close()


async def main():
    """Main entry point for the scraper."""
    scraper = Military1stScraper()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-extensions'
            ]
        )
        page = await browser.new_page()

        # Set viewport to standard size
        await page.set_viewport_size({"width": 1280, "height": 1024})

        # Collect product links
        links = await scraper.collect_product_links(page)

        if not links:
            logger.error("❌ No product links collected!")
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

        await browser.close()

    # Print summary
    logger.info(f"✅ Scraped {len(results)} products")
    for r in results[:10]:
        sole_info = r.get("sole")
        sole_status = f"✓ ({sole_info.get('confidence', 0):.2f})" if sole_info else "✗"
        logger.info(f"  {r.get('product_name')} -> sole: {sole_status}")


if __name__ == "__main__":
    asyncio.run(main())
