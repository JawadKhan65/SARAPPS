"""
Bergfreunde scraper using Playwright.

Scrapes men's hiking shoes from https://www.bergfreunde.nl/bergschoenen/voor--heren
Features:
  - Scroll-to-load pagination
  - Extracts product links from product list
  - Collects product details: name, images, links
  - Uses CLIP model to detect sole images
  - Comprehensive error handling and logging

Professional features:
  - Scroll-to-bottom for dynamic content loading
  - Robust product link extraction
  - CLIP-based sole image detection
  - Error tracking and retry logic
  - JSON output with summaries
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from playwright.async_api import async_playwright, Page
from PIL import Image
from io import BytesIO
import requests
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from ml_models.clip_model import SoleDetectorCLIP
from scrapers.base_scraper_mixin import BatchProcessingMixin

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_TIMEOUT = 60000
NAVIGATION_TIMEOUT = 90000
MAX_RETRIES = 3
RETRY_DELAY = 2

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# CSS/XPath Selectors
BASE_URL = "https://www.bergfreunde.nl/bergschoenen/voor--heren"
PRODUCTS_LIST_SELECTOR = "ul#product-list"
PRODUCT_ITEM_SELECTOR = "li.product-item"
PRODUCT_LINK_SELECTOR = "a"
PRODUCT_NAME_SELECTOR = "h1.highlight-1"
PRODUCT_IMAGES_CONTAINER_SELECTOR = "div.detail-gallery"
PRODUCT_IMAGE_SELECTOR = "img"

BRAND_NAME = "Bergfreunde"


class BergfreundeScraper(BatchProcessingMixin):
    """Bergfreunde hiking shoes scraper with scroll-to-load support."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.products: List[Dict[str, Any]] = []
        self.failed_urls: List[str] = []
        self.product_links: List[str] = []
        self.start_time = None
        self.total_products_found = 0

        # Initialize CLIP model for sole detection
        logger.info("Initializing CLIP sole detector model...")
        self.sole_detector = SoleDetectorCLIP()
        logger.info("✓ CLIP model loaded")

    def is_sole_image(self, image_url: str) -> bool:
        """
        Download image from URL and check if it's a sole image using CLIP.

        Returns:
            bool: True if image is detected as sole, False otherwise
        """
        try:
            # Download image
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()

            # Open image from bytes
            image = Image.open(BytesIO(response.content))

            # Check if it's a sole image
            is_sole, confidence, scores = self.sole_detector.is_sole(image)

            logger.debug(
                f"Sole detection - Is Sole: {is_sole}, Confidence: {confidence:.2f}"
            )
            logger.debug(f"  Scores: {scores}")

            return is_sole

        except Exception as e:
            logger.warning(f"⚠️ Error checking sole image: {e}")
            # If error occurs, assume it's not a sole image (safe default)
            return False

    async def load_all_products_by_scroll(self, page: Page) -> int:
        """
        Load all products by scrolling to bottom repeatedly.

        Process:
        1. Scroll to bottom of page
        2. Wait for new products to load
        3. Check if more products can be loaded
        4. Repeat until no new products appear
        """
        try:
            logger.info("Loading all products by scrolling...")
            scroll_count = 0
            max_scrolls = 50  # Safety limit
            previous_height = 0
            no_change_counter = 0

            while scroll_count < max_scrolls:
                try:
                    # Get current document height
                    current_height = await page.evaluate("document.body.scrollHeight")

                    # Check if height changed
                    if current_height == previous_height:
                        no_change_counter += 1
                        logger.debug(f"No height change (counter: {no_change_counter})")

                        if no_change_counter >= 3:
                            logger.info(
                                f"✓ No more products to load (height unchanged {no_change_counter} times)"
                            )
                            break
                    else:
                        no_change_counter = 0

                    previous_height = current_height

                    # Scroll to bottom
                    await page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight)"
                    )
                    logger.debug(f"Scrolled to bottom (scroll #{scroll_count + 1})")

                    # Wait for new products to load
                    await asyncio.sleep(2)

                    scroll_count += 1

                except Exception as e:
                    logger.debug(f"Scroll error: {e}")
                    break

            logger.info(f"✓ Scroll loading complete after {scroll_count} scrolls")
            return scroll_count

        except Exception as e:
            logger.error(f"Error during scroll loading: {e}", exc_info=True)
            return 0

    async def get_product_links(self, page: Page) -> List[str]:
        """
        Extract all product links from the loaded products list.

        Process:
        1. Wait for ul#product-list container
        2. Get all li.product-item items
        3. Extract <a> href from each item
        4. Return list of absolute URLs
        """
        try:
            logger.info("Extracting product links...")

            # Wait for products list
            await page.wait_for_selector(PRODUCTS_LIST_SELECTOR, timeout=15000)
            logger.debug("✓ Products list found")

            # Get all product items
            product_items = await page.locator(PRODUCT_ITEM_SELECTOR).all()
            logger.info(f"📦 Found {len(product_items)} product items")

            product_links = []
            extraction_errors = 0

            for idx, item in enumerate(product_items, 1):
                try:
                    # Get the <a> tag from this product item
                    link_element = item.locator(PRODUCT_LINK_SELECTOR).first
                    href = await link_element.get_attribute("href")

                    if href:
                        # Ensure absolute URL
                        if href.startswith("http"):
                            product_links.append(href)
                        else:
                            # Handle relative URLs
                            product_links.append(f"https://www.bergfreunde.nl{href}")
                        logger.debug(f"  Item {idx}: {href}")
                    else:
                        extraction_errors += 1
                        logger.debug(f"  Item {idx}: No href attribute")

                except Exception as e:
                    extraction_errors += 1
                    logger.debug(f"  Item {idx}: Error - {e}")
                    continue

            logger.info(
                f"✓ Extracted {len(product_links)} product links ({extraction_errors} errors)"
            )
            return product_links

        except Exception as e:
            logger.error(f"Failed to get product links: {e}", exc_info=True)
            return []

    async def extract_product_details(
        self, page: Page, url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract product details from product page.

        Extract:
        1. Product name: h1.highlight-1
        2. Images from div.detail-gallery img elements
        3. Select last image

        Skip product if total images <= 5
        """
        try:
            # Check if page is still open
            if page.is_closed():
                logger.warning(f"Page is closed, cannot navigate to {url}")
                return None

            logger.debug(f"Navigating to: {url}")

            # Navigate with domcontentloaded
            await page.goto(
                url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
            )

            # Wait for product name to load
            try:
                await page.wait_for_selector(PRODUCT_NAME_SELECTOR, timeout=15000)
                logger.debug("✓ Product name loaded")
            except Exception as e:
                logger.warning(f"⚠️ Product name selector not found: {e}")

            # Extract product name
            product_name = "Unknown"
            try:
                name_element = page.locator(PRODUCT_NAME_SELECTOR).first
                name_text = await name_element.text_content(timeout=5000)
                if name_text:
                    product_name = name_text.strip()
                    logger.debug(f"  Product name: {product_name}")
            except Exception as e:
                logger.warning(f"Failed to extract product name: {e}")

            # Wait for images container
            images_container_found = False
            try:
                await page.wait_for_selector(
                    PRODUCT_IMAGES_CONTAINER_SELECTOR, timeout=10000
                )
                logger.debug("✓ Images container found")
                images_container_found = True
            except Exception as e:
                logger.warning(f"⚠️ Images container not found: {e}")

            # Skip product if images container not found
            if not images_container_found:
                logger.warning("⚠️ Skipping product: detail gallery not found")
                return None

            # Extract images
            image_url = None
            try:
                # Get images container
                images_container = page.locator(PRODUCT_IMAGES_CONTAINER_SELECTOR).first

                # Get all image elements
                image_elements = await images_container.locator(
                    PRODUCT_IMAGE_SELECTOR
                ).all()
                total_images = len(image_elements)

                logger.info(f"📸 Found {total_images} images for product")

                # Extract URLs from all images and check each one with CLIP
                image_urls = []

                for idx, img_element in enumerate(image_elements, 1):
                    try:
                        # Extract image URL
                        img_url = None

                        # 1. Try src attribute
                        img_url = await img_element.get_attribute("src")
                        if img_url and img_url.startswith("data:image"):
                            img_url = None

                        # 2. Try data-src attribute
                        if not img_url:
                            img_url = await img_element.get_attribute("data-src")
                            if img_url and img_url.startswith("data:image"):
                                img_url = None

                        # 3. Try srcset attribute
                        if not img_url:
                            srcset = await img_element.get_attribute("srcset")
                            if srcset and not srcset.startswith("data:image"):
                                try:
                                    img_url = srcset.split(",")[0].strip().split(" ")[0]
                                except Exception:
                                    pass

                        # 4. Try data-srcset attribute
                        if not img_url:
                            data_srcset = await img_element.get_attribute("data-srcset")
                            if data_srcset:
                                try:
                                    img_url = (
                                        data_srcset.split(",")[0].strip().split(" ")[0]
                                    )
                                except Exception:
                                    pass

                        if img_url:
                            # Ensure absolute URL
                            if not img_url.startswith("http"):
                                if img_url.startswith("/"):
                                    img_url = f"https://www.bergfreunde.nl{img_url}"
                                else:
                                    img_url = f"https://www.bergfreunde.nl/{img_url}"

                            image_urls.append(img_url)
                            logger.debug(f"Image {idx}: Extracted URL")
                    except Exception as e:
                        logger.debug(f"Image {idx}: Failed to extract URL - {e}")

                # Filter images using CLIP sole detector
                sole_images = []
                for idx, img_url in enumerate(image_urls, 1):
                    logger.debug(
                        f"Checking image {idx}/{len(image_urls)} with CLIP model..."
                    )
                    is_sole = self.is_sole_image(img_url)

                    if is_sole:
                        sole_images.append(img_url)
                        logger.info(f"  ✓ Image {idx}: Detected as SOLE")
                    else:
                        logger.debug(f"  ✗ Image {idx}: Not a sole image")

                # Select sole image if found
                image_url = None
                if sole_images:
                    # Use the last sole image found
                    image_url = sole_images[-1]
                    logger.info(f"✅ Selected sole image: {image_url}")
                else:
                    logger.warning(
                        f"⚠️ No sole images detected in {len(image_urls)} images"
                    )

            except Exception as e:
                logger.warning(f"❌ Failed to extract images: {e}")

            # Build product data
            product_data = {
                "brand": BRAND_NAME,
                "name": product_name,
                "source_url": url,
                "image_url": image_url,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(f"📦 Product: {product_name}")
            if image_url:
                logger.info(f"   Image: {image_url}")
            else:
                logger.info("   Image: Not found")

            return product_data

        except Exception as e:
            logger.error(f"Failed to extract details from {url}: {e}", exc_info=True)
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
        1. Navigate to base URL
        2. Load all products via scroll
        3. Extract product links
        4. Scrape each product detail (with real-time batch processing)
        5. Save results
        """
        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

        logger.info("Starting Bergfreunde scraper")
        logger.info(f"Base URL: {self.base_url}")
        if batch_callback:
            logger.info("Using in-memory image processing (no temp files)")
        self.start_time = datetime.now()

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True, args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT)
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

            try:
                # Step 1: Navigate to base URL
                logger.info("Step 1: Navigating to base URL...")
                for attempt in range(MAX_RETRIES):
                    try:
                        await page.goto(
                            self.base_url,
                            wait_until="domcontentloaded",
                            timeout=NAVIGATION_TIMEOUT,
                        )
                        logger.debug("✓ Base URL loaded")
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

                # Step 2: Load all products via scroll
                logger.info("Step 2: Loading all products by scrolling...")
                scroll_count = await self.load_all_products_by_scroll(page)
                logger.info(f"✓ Scroll loading complete ({scroll_count} scrolls)")

                # Step 3: Extract product links
                logger.info("Step 3: Extracting product links...")
                self.product_links = await self.get_product_links(page)
                self.total_products_found = len(self.product_links)
                logger.info(f"✓ Found {self.total_products_found} product links")

                # Step 4: Scrape each product with batch processing
                logger.info("Step 4: Scraping product details...")
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
                        logger.info("Stopping scraper early due to low uniqueness")
                        break

                    logger.info(
                        f"\n  Product {idx}/{self.total_products_found}: Scraping..."
                    )
                    try:
                        # Check if page is still open before continuing
                        if page.is_closed():
                            logger.warning("Page has been closed, stopping scraper")
                            should_stop = True
                            break

                        details = await self.extract_product_details(page, product_url)

                        if details and details.get("image_url"):
                            # Log scraped product details
                            logger.info(f"✅ Scraped Product #{idx}:")
                            logger.info(f"   Brand: {details.get('brand', 'N/A')}")
                            logger.info(
                                f"   Product Name: {details.get('name', 'N/A')}"
                            )
                            logger.info(
                                f"   Product URL: {details.get('source_url', 'N/A')}"
                            )
                            logger.info(
                                f"   Sole Image URL: {details.get('image_url', 'N/A')[:80]}..."
                            )
                            logger.info(
                                f"   Total Images Checked: {details.get('images_checked', 0)}"
                            )

                            self.products.append(details)
                            current_batch.append(details)

                            # Process batch when size is reached
                            if len(current_batch) >= batch_size and batch_callback:
                                logger.info(
                                    f"🔄 Processing batch of {len(current_batch)} products..."
                                )
                                should_continue = await self._process_batch_with_callback(
                                    current_batch,
                                    batch_callback,
                                    brand_field="brand",
                                    name_field="name",
                                    url_field="source_url",  # FIXED: Changed from "url" to "source_url"
                                    image_url_field="image_url",
                                )

                                if not should_continue:
                                    should_stop = True

                                current_batch = []  # Reset batch

                        elif details:
                            # Product exists but no image (skipped due to insufficient images)
                            logger.warning(
                                f"  ⊘ {details['name']} - Skipped (insufficient images)"
                            )
                            self.failed_urls.append(product_url)
                        else:
                            # Failed to extract
                            self.failed_urls.append(product_url)
                            logger.error(f"  ✗ Failed to scrape {product_url}")
                    except Exception as e:
                        logger.error(f"  ✗ Error scraping product {idx}: {e}")
                        self.failed_urls.append(product_url)

                    await asyncio.sleep(2)  # Delay between products

                # Process remaining items in final batch
                if current_batch and batch_callback and not should_stop:
                    logger.info(
                        f"Processing final batch of {len(current_batch)} products..."
                    )
                    await self._process_batch_with_callback(
                        current_batch,
                        batch_callback,
                        brand_field="brand",
                        name_field="name",
                        url_field="source_url",  # FIXED: Changed from "url" to "source_url"
                        image_url_field="image_url",
                    )

                logger.info(
                    f"\n✓ Scraping complete. Total products: {len(self.products)}"
                )

            except Exception as e:
                logger.error(f"Scraper failed: {e}", exc_info=True)
            finally:
                try:
                    await context.close()
                except Exception as e:
                    logger.debug(f"Error closing context: {e}")
                try:
                    await browser.close()
                except Exception as e:
                    logger.debug(f"Error closing browser: {e}")

    def save_results(self, output_dir: Optional[str] = None):
        """Save scraped products to JSON file."""
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # Save main results
        output_file = output_dir / "bergfreunde_shoes.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.products, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Saved {len(self.products)} products to {output_file}")

        # Save failed URLs
        if self.failed_urls:
            failed_file = output_dir / "bergfreunde_failed_urls.txt"
            with open(failed_file, "w", encoding="utf-8") as f:
                f.write("\n".join(self.failed_urls))
            logger.info(f"✓ Saved {len(self.failed_urls)} failed URLs to {failed_file}")

        # Save summary
        summary_file = output_dir / "bergfreunde_summary.json"
        summary = {
            "total_products_found": self.total_products_found,
            "total_products_scraped": len(self.products),
            "failed_products": len(self.failed_urls),
            "success_rate": (
                f"{100 * len(self.products) / self.total_products_found:.1f}%"
                if self.total_products_found > 0
                else "N/A"
            ),
            "products_with_image": sum(1 for p in self.products if p.get("image_url")),
            "image_rate": (
                f"{100 * sum(1 for p in self.products if p.get('image_url')) / len(self.products):.1f}%"
                if self.products
                else "N/A"
            ),
            "execution_time_seconds": (
                (datetime.now() - self.start_time).total_seconds()
                if self.start_time
                else None
            ),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"✓ Saved summary to {summary_file}")

    def print_summary(self):
        """Print scraping summary."""
        print("\n" + "=" * 140)
        print("BERGFREUNDE SCRAPER - SUMMARY")
        print("=" * 140)
        print(f"\nTotal Products Found: {self.total_products_found}")
        print(f"Total Products Scraped: {len(self.products)}")
        print(f"Failed/Skipped: {len(self.failed_urls)}")

        image_count = sum(1 for p in self.products if p.get("image_url"))
        print(f"Products with Images: {image_count}/{len(self.products)}")

        if self.products:
            print("\nFirst 10 Products:")
            for idx, p in enumerate(self.products[:10], 1):
                print(f"\n{idx}. {p['brand']} - {p['name']}")
                print(f"   URL: {p['source_url']}")
                if p.get("image_url"):
                    print(f"   ✓ Image: {p['image_url']}")
                else:
                    print("   ✗ Image: Not found")

        if self.start_time:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            print(
                f"\nExecution Time: {elapsed:.1f} seconds ({elapsed / 60:.1f} minutes)"
            )
            if len(self.products) > 0:
                print(f"Speed: {len(self.products) / elapsed:.1f} products/sec")

        print("=" * 140 + "\n")


async def main():
    """Main entry point."""
    scraper = BergfreundeScraper(base_url=BASE_URL)

    try:
        # Scrape all products
        await scraper.scrape()

        # Save results
        scraper.save_results()

        # Print summary
        scraper.print_summary()

    except Exception as e:
        logger.error(f"Scraper failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
