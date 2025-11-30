"""
Playwright-based scraper for Gearpoint.nl shoes.

Scrapes product links from paginated search results, then extracts:
  - Product name
  - Product images (passed through CLIP model for sole detection)
  - Product URL

Returns a list of dictionaries with product metadata.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from playwright.async_api import async_playwright, Page
import sys
import requests
from PIL import Image
import io

# Setup imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from ml_models.clip_model import SoleDetectorCLIP
from scrapers.base_scraper_mixin import BatchProcessingMixin

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_TIMEOUT = 60000  # 60 seconds
NAVIGATION_TIMEOUT = 90000  # 90 seconds
MAX_RETRIES = 3
RETRY_DELAY = 2

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# CSS Selectors
PRODUCTS_CONTAINER_SELECTOR = "div.products"
PRODUCT_ITEM_SELECTOR = "div.product"
PAGINATION_NAV_SELECTOR = "nav.pagination-a"
PRODUCT_TITLE_SELECTOR = "h1.page-title span.base"
FEATURED_CONTAINER_SELECTOR = "div.featured"
PRODUCT_IMG_NAV_SELECTOR = "div.product-img-nav"
OWL_ITEM_SELECTOR = "div.owl-item"


class GearPointScraper(BatchProcessingMixin):
    """GearPoint.nl shoes scraper."""

    def __init__(self, base_url: str = "https://www.gearpoint.nl/en/search/shoes"):
        self.base_url = base_url
        self.products: List[Dict[str, Any]] = []
        self.failed_urls: List[str] = []
        self.product_links: List[str] = []
        self.start_time = None
        self.clip = SoleDetectorCLIP()
        logger.info("✅ GearPointScraper initialized with CLIP model")

    async def get_total_pages(self, page: Page) -> int:
        """
        Get total number of pages from pagination.

        Process:
        1. Find nav tag with class "pagination-a"
        2. Get all li tags inside ol
        3. Select second-to-last li for total pages

        Returns:
            int: Total number of pages
        """
        try:
            # Wait for pagination nav to load
            await page.wait_for_selector(PAGINATION_NAV_SELECTOR, timeout=10000)

            # Get all li elements in the pagination
            li_elements = await page.locator(f"{PAGINATION_NAV_SELECTOR} ol li").all()

            if len(li_elements) < 2:
                logger.warning("Not enough pagination elements found, assuming 1 page")
                return 1

            # Get the second-to-last li element (total pages)
            second_last_li = li_elements[-2]
            page_text = await second_last_li.text_content()

            if page_text:
                total_pages = int(page_text.strip())
                logger.info(f"✓ Total pages detected: {total_pages}")
                return total_pages
            else:
                logger.warning("Could not extract total pages, defaulting to 1")
                return 1

        except Exception as e:
            logger.warning(f"Failed to get pagination info: {e}. Defaulting to 1 page")
            return 1

    async def get_product_links_from_page(self, page: Page, page_num: int) -> List[str]:
        """
        Extract all product links from a single search results page.

        Process:
        1. Wait for products container to load
        2. Find all product divs
        3. Extract data-url attribute from each
        4. Return list of product URLs
        """
        try:
            logger.info(f"Extracting product links from page {page_num}...")

            # Wait for products container to load
            await page.wait_for_selector(PRODUCTS_CONTAINER_SELECTOR, timeout=15000)
            logger.debug("✓ Found products container")

            # Get all product items
            product_items = await page.locator(
                f"{PRODUCTS_CONTAINER_SELECTOR} {PRODUCT_ITEM_SELECTOR}"
            ).all()
            logger.info(f"Found {len(product_items)} products on page {page_num}")

            if len(product_items) == 0:
                logger.warning(f"No products found on page {page_num}")
                return []

            # Extract data-url from each product
            product_links = []
            for idx, item in enumerate(product_items, 1):
                try:
                    data_url = await item.get_attribute("data-url")

                    if data_url:
                        # Remove ?format=json suffix if present
                        data_url = data_url.replace("?format=json", "")

                        # Ensure absolute URL
                        if data_url.startswith("http"):
                            product_links.append(data_url)
                        elif data_url.startswith("/"):
                            product_links.append(f"https://www.gearpoint.nl{data_url}")
                        else:
                            product_links.append(f"https://www.gearpoint.nl/{data_url}")

                        logger.debug(f"  Product {idx}: {data_url}")
                    else:
                        logger.warning(f"  Product {idx}: No data-url attribute found")

                except Exception as e:
                    logger.warning(f"Failed to extract URL from product {idx}: {e}")
                    continue

            logger.info(
                f"✓ Extracted {len(product_links)} product links from page {page_num}"
            )
            return product_links

        except Exception as e:
            logger.error(f"Failed to get product links from page {page_num}: {e}")
            return []

    async def navigate_to_page(self, page: Page, page_num: int) -> bool:
        """
        Navigate to a specific page number.

        Args:
            page: Playwright page object
            page_num: Page number to navigate to

        Returns:
            bool: True if navigation successful, False otherwise
        """
        try:
            # Construct URL with page parameter
            url = f"{self.base_url}?page={page_num}"
            logger.info(f"Navigating to page {page_num}: {url}")

            await page.goto(url, wait_until="load", timeout=NAVIGATION_TIMEOUT)
            await page.wait_for_selector(
                PRODUCTS_CONTAINER_SELECTOR, timeout=DEFAULT_TIMEOUT
            )

            # Wait a bit for dynamic content to load
            await asyncio.sleep(2)

            return True

        except Exception as e:
            logger.error(f"Failed to navigate to page {page_num}: {e}")
            return False

    async def extract_product_details(
        self, page: Page, url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract product details from product page.

        Process:
        1. Navigate to product page
        2. Extract product name from header.title h1
        3. Find all images in div.featured > div.product-img-nav > div.owl-item
        4. Extract src from each img tag
        5. Return product details with all image URLs
        """
        try:
            logger.info(f"Navigating to product: {url}")

            # Navigate with retry logic
            for attempt in range(MAX_RETRIES):
                try:
                    await page.goto(
                        url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
                    )
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            f"Navigation attempt {attempt + 1} failed: {e}. Retrying..."
                        )
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logger.error(
                            f"Failed to navigate to {url} after {MAX_RETRIES} attempts: {e}"
                        )
                        raise

            # Wait for main content to load
            try:
                await page.wait_for_selector(PRODUCT_TITLE_SELECTOR, timeout=15000)
                logger.debug("  ✓ Product title loaded")
            except Exception as e:
                logger.error(f"Product title selector not found: {e}")
                # Try to capture page state for debugging
                try:
                    page_title = await page.title()
                    logger.error(f"  Page title: {page_title}")
                    # Check if we got redirected or blocked
                    current_url = page.url
                    if current_url != url:
                        logger.error(f"  Redirected from {url} to {current_url}")
                except Exception:
                    pass
                raise

            await asyncio.sleep(2)  # Give extra time for images to load

            # Extract product name
            product_name = "Unknown"
            try:
                name_elem = page.locator(PRODUCT_TITLE_SELECTOR).first
                name_text = await name_elem.text_content(timeout=5000)
                if name_text:
                    product_name = name_text.strip()
                    logger.debug(f"  Product name: {product_name}")
            except Exception as e:
                logger.warning(f"Failed to extract product name: {e}")

            # Extract all product images
            image_urls = []
            try:
                # Wait for featured container
                logger.debug("  Waiting for featured container...")
                await page.wait_for_selector(FEATURED_CONTAINER_SELECTOR, timeout=10000)
                logger.debug("  ✓ Featured container found")

                # Find all owl-item divs inside product-img-nav
                owl_items = await page.locator(
                    f"{FEATURED_CONTAINER_SELECTOR} {PRODUCT_IMG_NAV_SELECTOR} {OWL_ITEM_SELECTOR}"
                ).all()

                logger.debug(f"  Found {len(owl_items)} owl-item containers")

                if len(owl_items) == 0:
                    logger.warning(
                        "  No owl-item containers found, trying alternative selectors..."
                    )
                    # Try to find any images in featured container
                    all_images = await page.locator(
                        f"{FEATURED_CONTAINER_SELECTOR} img"
                    ).all()
                    logger.debug(
                        f"  Found {len(all_images)} total images in featured container"
                    )

                for idx, owl_item in enumerate(owl_items, 1):
                    try:
                        # Find img tag inside owl-item
                        img_elem = owl_item.locator("img").first
                        img_src = await img_elem.get_attribute("src")

                        # Also try data-src if src is not available
                        if not img_src:
                            img_src = await img_elem.get_attribute("data-src")

                        if img_src:
                            # Ensure absolute URL
                            if not img_src.startswith("http"):
                                if img_src.startswith("/"):
                                    img_src = f"https://www.gearpoint.nl{img_src}"
                                else:
                                    img_src = f"https://www.gearpoint.nl/{img_src}"

                            image_urls.append(img_src)
                            logger.debug(f"    Image {idx}: {img_src[:80]}...")
                        else:
                            logger.warning(f"    Image {idx}: No src attribute found")

                    except Exception as e:
                        logger.warning(f"Failed to extract image {idx}: {e}")
                        continue

                if image_urls:
                    logger.info(f"  ✓ Extracted {len(image_urls)} product images")
                else:
                    logger.warning("  ⚠️ No product images extracted")

            except Exception as e:
                logger.error(f"Failed to extract images: {e}")
                # Log page structure for debugging
                try:
                    html_content = await page.content()
                    if FEATURED_CONTAINER_SELECTOR in html_content:
                        logger.debug(
                            "  Featured container exists in HTML but selector failed"
                        )
                    else:
                        logger.error("  Featured container not found in page HTML")
                except Exception:
                    pass

            # Return product details
            # Note: image_urls will be processed by CLIP model to find sole image
            return {
                "brand": "GearPoint",  # Can be extracted if available on page
                "name": product_name,
                "url": url,
                "image_urls": image_urls,  # Multiple images for CLIP processing
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to extract details from {url}: {e}")
            # Log additional debugging info
            try:
                if not page.is_closed():
                    current_url = page.url
                    logger.error(f"  Current URL: {current_url}")
                    page_title = await page.title()
                    logger.error(f"  Page title: {page_title}")
            except Exception:
                pass
            return None

    def download_image(
        self, url: str, timeout: int = 10, retries: int = 3
    ) -> Optional[Image.Image]:
        """Download image from URL and return PIL Image"""
        for attempt in range(retries):
            try:
                response = requests.get(
                    url, timeout=timeout, headers={"User-Agent": USER_AGENT}
                )
                if response.status_code == 200:
                    img = Image.open(io.BytesIO(response.content)).convert("RGB")
                    # Validate image size
                    if img.size[0] > 50 and img.size[1] > 50:
                        return img
                    else:
                        logger.debug(f"Image too small: {img.size}, skipping")
                        return None
            except Exception as e:
                if attempt < retries - 1:
                    logger.debug(f"Retry {attempt + 1}/{retries} for {url}: {e}")
                else:
                    logger.debug(f"Failed to download {url} after {retries} retries")
        return None

    def _download_image_to_memory(self, image_url: str) -> Optional[bytes]:
        """Download image directly to memory as bytes - no disk I/O"""
        try:
            response = requests.get(
                image_url, timeout=10, headers={"User-Agent": USER_AGENT}
            )
            response.raise_for_status()
            logger.debug(f"Downloaded image to memory: {len(response.content)} bytes")
            return response.content
        except Exception as e:
            logger.error(f"Failed to download image {image_url}: {e}")
            return None

    async def _find_sole_image(self, image_urls: List[str]) -> Optional[Dict[str, Any]]:
        """
        Download all images and use CLIP model to identify the sole image.

        Args:
            image_urls: List of image URLs to check

        Returns:
            Dict with 'url' and 'bytes' of the sole image, or None if not found
        """
        try:
            logger.info(
                f"🔍 Running CLIP sole detection on {len(image_urls)} images..."
            )

            best_sole = None
            best_sole_confidence = 0.0
            best_sole_bytes = None

            for idx, img_url in enumerate(image_urls, 1):
                try:
                    # Download image
                    logger.debug(f"  Downloading image {idx}/{len(image_urls)}...")
                    pil_image = await asyncio.get_event_loop().run_in_executor(
                        None, self.download_image, img_url
                    )

                    if pil_image is None:
                        logger.debug(f"    Image {idx}: Failed to download")
                        continue

                    # Run CLIP detection
                    logger.debug(f"  Analyzing image {idx} with CLIP...")
                    is_sole, confidence, scores = self.clip.is_sole(pil_image)

                    sole_status = "✓ SOLE" if is_sole else "✗ NOT SOLE"
                    logger.debug(
                        f"    Image {idx}: {sole_status} (confidence: {confidence:.3f})"
                    )

                    # Track best sole
                    if is_sole and confidence > best_sole_confidence:
                        best_sole = img_url
                        best_sole_confidence = confidence
                        # Convert PIL image to bytes
                        img_bytes_io = io.BytesIO()
                        pil_image.save(img_bytes_io, format="PNG")
                        best_sole_bytes = img_bytes_io.getvalue()

                except Exception as e:
                    logger.debug(f"CLIP check failed for image {idx}: {e}")

            # Return best result
            if best_sole:
                logger.info(
                    f"✅ Sole image found! Confidence: {best_sole_confidence:.3f}"
                )
                return {"url": best_sole, "bytes": best_sole_bytes}
            else:
                logger.warning("⚠️  No sole image detected among product images")
                return None

        except Exception as e:
            logger.error(f"Error in sole detection: {e}")
            return None

    async def _prepare_batch_for_processing(self, batch: List[Dict]) -> List[Dict]:
        """
        Download images and identify sole images using CLIP model.

        For GearPoint, we have multiple images per product that need to be
        checked with the CLIP model to identify the sole image.
        """
        processed_batch = []

        for product in batch:
            image_urls = product.get("image_urls", [])

            if not image_urls:
                logger.warning(f"Skipping product without images: {product['url']}")
                continue

            # Find the sole image using CLIP model
            sole_image = await self._find_sole_image(image_urls)

            if sole_image:
                # Log the sole image URL
                logger.info(f"   📷 Sole Image URL: {sole_image['url']}")

                # Convert to format expected by scraper_service
                processed_product = {
                    "url": product["url"],
                    "brand": product["brand"],
                    "product_name": product["name"],
                    "product_type": "shoe",
                    "image_bytes": sole_image["bytes"],  # Single sole image
                    "image_url": sole_image["url"],  # Keep URL for reference
                    "scraped_at": product.get("scraped_at"),
                }
                processed_batch.append(processed_product)
            else:
                logger.warning(
                    f"Skipping product - no sole image found: {product['url']}"
                )

        logger.info(
            f"✅ Prepared {len(processed_batch)}/{len(batch)} products with sole images"
        )
        return processed_batch

    async def scrape(
        self,
        max_pages: Optional[int] = None,
        batch_callback=None,
        batch_size: int = 20,
        is_cancelled=None,
    ):
        """
        Main scraping function with real-time batch processing.

        Args:
            max_pages: Maximum number of pages to scrape (None = all pages)
            batch_callback: Async function to call with each batch of products
            batch_size: Number of products to collect before calling batch_callback
            is_cancelled: Optional function to check if scraping should be cancelled
        """
        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

        logger.info(f"Starting GearPoint scraper for {self.base_url}")
        self.start_time = datetime.now()
        logger.info("Using in-memory image processing (no temp files)")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--disable-extensions',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-accelerated-2d-canvas',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--single-process'
                ]
            )
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT)
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

            try:
                # Step 1: Navigate to first page and get total pages
                logger.info("Step 1: Navigating to search page...")
                for attempt in range(MAX_RETRIES):
                    try:
                        await page.goto(
                            self.base_url,
                            wait_until="load",
                            timeout=NAVIGATION_TIMEOUT,
                        )

                        # Handle cookie consent dialog
                        try:
                            cookie_button = page.locator(
                                "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"
                            )
                            if await cookie_button.count() > 0:
                                logger.info("🍪 Accepting cookies...")
                                await cookie_button.click()
                                await asyncio.sleep(1)
                        except Exception as e:
                            logger.debug(
                                f"No cookie dialog found or already accepted: {e}"
                            )

                        await page.wait_for_selector(
                            PRODUCTS_CONTAINER_SELECTOR, timeout=DEFAULT_TIMEOUT
                        )
                        await asyncio.sleep(2)
                        break
                    except Exception as e:
                        if attempt < MAX_RETRIES - 1:
                            logger.warning(
                                f"Navigation attempt {attempt + 1} failed: {e}. Retrying..."
                            )
                            await asyncio.sleep(RETRY_DELAY)
                        else:
                            logger.error(
                                f"Failed to navigate after {MAX_RETRIES} attempts"
                            )
                            raise

                # Get total pages from pagination
                total_pages = await self.get_total_pages(page)
                pages_to_scrape = (
                    min(total_pages, max_pages) if max_pages else total_pages
                )

                logger.info(f"🧭 Total pages available: {total_pages}")
                logger.info(f"📄 Will scrape {pages_to_scrape} pages")

                # Step 2: Iterate through pages and collect product links
                logger.info("\nStep 2: Collecting product links from all pages...")
                all_product_links = []

                for page_num in range(1, pages_to_scrape + 1):
                    # Check for cancellation
                    if is_cancelled and is_cancelled():
                        logger.warning(
                            "🛑 Cancellation detected - stopping page iteration"
                        )
                        break

                    logger.info(f"\n📄 Processing page {page_num}/{pages_to_scrape}...")

                    # Navigate to page (except first page, already loaded)
                    if page_num > 1:
                        success = await self.navigate_to_page(page, page_num)
                        if not success:
                            logger.error(
                                f"Failed to navigate to page {page_num}, skipping"
                            )
                            continue

                    # Extract product links from this page
                    page_links = await self.get_product_links_from_page(page, page_num)
                    all_product_links.extend(page_links)

                    logger.info(
                        f"✓ Total product links collected so far: {len(all_product_links)}"
                    )

                    # Small delay between pages
                    await asyncio.sleep(1)

                self.product_links = all_product_links
                logger.info(
                    f"\n✅ Total product links collected: {len(self.product_links)}"
                )

                if not self.product_links:
                    logger.error("No product links found")
                    return

                # Step 3: Scrape each product with batch processing
                logger.info(f"\nStep 3: Scraping {len(self.product_links)} products...")
                current_batch = []
                should_stop = False

                for idx, product_url in enumerate(self.product_links, 1):
                    # Check for cancellation
                    if is_cancelled and is_cancelled():
                        logger.warning(
                            "🛑 Cancellation detected - stopping scraper immediately"
                        )
                        should_stop = True
                        break

                    if should_stop:
                        logger.info("Stopping scraper early")
                        break

                    # Check if page is still open
                    if page.is_closed():
                        logger.warning("Page has been closed, stopping scraper")
                        should_stop = True
                        break

                    logger.info(
                        f"\n[{idx}/{len(self.product_links)}] Scraping product..."
                    )
                    details = await self.extract_product_details(page, product_url)

                    if details:
                        # Log scraped product details
                        logger.info(f"✅ Scraped Product #{idx}:")
                        logger.info(f"   Brand: {details.get('brand', 'N/A')}")
                        logger.info(f"   Product Name: {details.get('name', 'N/A')}")
                        logger.info(f"   Product URL: {details.get('url', 'N/A')}")
                        logger.info(
                            f"   Images Count: {len(details.get('image_urls', []))}"
                        )

                        self.products.append(details)
                        current_batch.append(details)

                        # Check for cancellation before processing batch
                        if is_cancelled and is_cancelled():
                            logger.warning(
                                "🛑 Cancellation detected - stopping scraper immediately"
                            )
                            should_stop = True
                            break

                        # Process batch when size is reached
                        if len(current_batch) >= batch_size and batch_callback:
                            logger.info(
                                f"Preparing batch of {len(current_batch)} products for processing..."
                            )

                            # Download images to memory and prepare batch
                            processed_batch = await self._prepare_batch_for_processing(
                                current_batch
                            )

                            if processed_batch:
                                logger.info(
                                    f"Processing {len(processed_batch)} products with images..."
                                )
                                should_continue = await batch_callback(processed_batch)

                                if not should_continue:
                                    logger.warning(
                                        "Batch callback returned False, stopping scraper"
                                    )
                                    should_stop = True
                            else:
                                logger.warning(
                                    "No products with images in this batch, continuing..."
                                )

                            current_batch = []  # Reset batch
                    else:
                        self.failed_urls.append(product_url)
                        logger.error(f"✗ Failed to scrape {product_url}")

                    await asyncio.sleep(1)  # Delay between requests

                # Process remaining items in final batch
                if current_batch and batch_callback and not should_stop:
                    # Check for cancellation before processing final batch
                    if is_cancelled and is_cancelled():
                        logger.warning(
                            "🛑 Cancellation detected - skipping final batch"
                        )
                    else:
                        logger.info(
                            f"Processing final batch of {len(current_batch)} products..."
                        )
                        processed_batch = await self._prepare_batch_for_processing(
                            current_batch
                        )

                        if processed_batch:
                            await batch_callback(processed_batch)

                # Summary
                elapsed = datetime.now() - self.start_time
                logger.info("\n" + "=" * 80)
                logger.info("SCRAPING COMPLETE")
                logger.info("=" * 80)
                logger.info(f"Total products scraped: {len(self.products)}")
                logger.info(f"Failed URLs: {len(self.failed_urls)}")
                logger.info(f"Time elapsed: {elapsed}")
                logger.info("=" * 80)

            except Exception as e:
                logger.error(f"Scraper error: {e}", exc_info=True)
                raise
            finally:
                await browser.close()


# Standalone test function
async def main():
    """Test the GearPoint scraper standalone"""
    scraper = GearPointScraper()

    # Test callback function
    async def test_callback(batch):
        logger.info(f"\n📦 Test callback received batch of {len(batch)} products")
        for idx, product in enumerate(batch, 1):
            logger.info(f"  {idx}. {product['brand']} - {product['product_name']}")
            logger.info(f"     URL: {product['url']}")
            logger.info(f"     Images: {len(product.get('image_bytes_list', []))}")
        return True  # Continue scraping

    # Run scraper with test callback
    await scraper.scrape(
        max_pages=None,  # Production: scrape all pages
        batch_callback=test_callback,
        batch_size=5,
    )


if __name__ == "__main__":
    asyncio.run(main())
