"""
Givenchy shoes scraper using Playwright.

Scrapes men's shoes from https://www.givenchy.com/nl/en/men/shoes
Features:
  - Infinite scroll with "Load More" button clicking
  - Extracts product links from grid
  - Collects product details: name, images, links
  - Uses CLIP model to detect sole images
  - Comprehensive error handling and logging

Professional features:
  - Robust button detection and clicking
  - Scroll-into-view for dynamic content
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
import cv2
import numpy as np

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
BASE_URL = "https://www.givenchy.com/nl/en/men/shoes"
LOAD_MORE_BUTTON_XPATH = "//*[@id='activate-infinite-scroll']"
PRODUCTS_CONTAINER_SELECTOR = "ul.search-results-items"
PRODUCT_ITEM_SELECTOR = "li.grid-tile"
PRODUCT_LINK_SELECTOR = "a"
PRODUCT_NAME_SELECTOR = "h1.product-name"
PRODUCT_IMAGES_CONTAINER_SELECTOR = "div.product-block-images"
PRODUCT_IMAGE_SELECTOR = "li"

BRAND_NAME = "Givenchy"


class GivenchyScraper(BatchProcessingMixin):
    """Givenchy men's shoes scraper with infinite scroll support."""

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

    def is_sole_image(self, image_url: str):
        """
        Download image from URL, crop left half, and check if it's a sole image using CLIP.

        For top-down shoe views, the left half typically shows the sole better.

        Returns:
            tuple: (is_sole: bool, confidence: float, scores: dict)
        """
        try:
            # Download image
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()

            # Open image from bytes
            image = Image.open(BytesIO(response.content)).convert("RGB")

            # Convert PIL to OpenCV format for cropping
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            height, width = cv_image.shape[:2]

            # Crop left half (from x=0 to x=width/2)
            left_half = cv_image[:, : width // 2]

            # Convert back to PIL
            cropped_image = Image.fromarray(cv2.cvtColor(left_half, cv2.COLOR_BGR2RGB))

            logger.debug(
                f"Original image: {width}x{height}, Cropped to left half: {width // 2}x{height}"
            )

            # Check if it's a sole image
            is_sole, confidence, scores = self.sole_detector.is_sole(cropped_image)

            # Log detailed breakdown by label
            if scores:
                logger.debug("📊 CLIP Scores Breakdown (left half cropped):")
                logger.debug("   Sole-related labels:")
                logger.debug(f"     • sole_tread: {scores.get('sole_tread', 0):.3f}")
                logger.debug(f"     • sole_rubber: {scores.get('sole_rubber', 0):.3f}")
                logger.debug(
                    f"     • sole_outsole: {scores.get('sole_outsole', 0):.3f}"
                )
                logger.debug(
                    f"     • sole_with_upper: {scores.get('sole_with_upper', 0):.3f}"
                )
                logger.debug(
                    f"     • sole_visible: {scores.get('sole_visible', 0):.3f}"
                )
                logger.debug("   Non-sole labels:")
                logger.debug(f"     • side_view: {scores.get('side_view', 0):.3f}")
                logger.debug(f"     • front_view: {scores.get('front_view', 0):.3f}")
                logger.debug(f"     • upper_only: {scores.get('upper_only', 0):.3f}")
                logger.debug(
                    f"   Confidence: {confidence:.3f}, Result: {'✓ SOLE' if is_sole else '✗ NOT SOLE'}"
                )

            return is_sole, confidence, scores

        except Exception as e:
            logger.warning(f"⚠️ Error checking sole image: {e}")
            # If error occurs, return safe defaults
            return False, 0.0, {}

    async def load_all_products(self, page: Page) -> int:
        """
        Load all products by clicking the infinite scroll button repeatedly.

        Process:
        1. Find the button with XPath: //*[@id='activate-infinite-scroll']
        2. While button exists and is clickable:
           a. Scroll button into view
           b. Click the button
           c. Wait for new products to load
           d. Check if button still exists
        3. Stop when button is no longer found or clickable
        """
        try:
            logger.info("Loading all products with infinite scroll...")
            click_count = 0
            max_clicks = 50  # Safety limit

            while click_count < max_clicks:
                try:
                    # Try to find the load more button
                    button = page.locator(f"xpath={LOAD_MORE_BUTTON_XPATH}")

                    # Check if button exists and is visible
                    is_visible = await button.is_visible(timeout=3000)

                    if not is_visible:
                        logger.info(
                            f"✓ No more products to load (after {click_count} clicks)"
                        )
                        break

                    # Scroll button into view
                    await button.scroll_into_view()
                    logger.debug("✓ Scrolled button into view")

                    # Wait a bit for page to settle
                    await asyncio.sleep(1)

                    # Click the button
                    await button.click(timeout=5000)
                    logger.debug(
                        f"✓ Clicked load more button (click #{click_count + 1})"
                    )

                    # Wait for new products to load
                    await asyncio.sleep(2)

                    click_count += 1

                except Exception as e:
                    logger.debug(f"Load more button click error: {e}")
                    # If button not found or error, assume all products loaded
                    break

            logger.info(f"✓ Infinite scroll complete after {click_count} clicks")
            return click_count

        except Exception as e:
            logger.error(f"Error during infinite scroll: {e}", exc_info=True)
            return 0

    async def get_product_links(self, page: Page) -> List[str]:
        """
        Extract all product links from the loaded products container.

        Process:
        1. Wait for ul.search-results-items container
        2. Get all li.grid-tile items
        3. Extract <a> href from each item
        4. Return list of absolute URLs
        """
        try:
            logger.info("Extracting product links...")

            # Wait for products container
            await page.wait_for_selector(PRODUCTS_CONTAINER_SELECTOR, timeout=15000)
            logger.debug("✓ Products container found")

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
                            product_links.append(f"https://www.givenchy.com{href}")
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
        self, page: Page, url: str, product_index: int, total_products: int
    ) -> Optional[Dict[str, Any]]:
        """
        Extract product details from product page.

        Extract:
        1. Product name: h1.product-name
        2. Images from div.product-block-images li elements
        3. Select 5th image if not last product, 6th if last product

        Skip product if total images <= 5
        """
        try:
            logger.debug(f"Navigating to: {url}")

            # Navigate with domcontentloaded
            await page.goto(
                url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
            )

            # Wait for product name to load
            await page.wait_for_selector(PRODUCT_NAME_SELECTOR, timeout=15000)
            logger.debug("✓ Product name loaded")

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

            # Extract images
            image_url = None
            if images_container_found:
                try:
                    # Get images container
                    images_container = page.locator(
                        PRODUCT_IMAGES_CONTAINER_SELECTOR
                    ).first

                    # Get all image li elements
                    image_elements = await images_container.locator(
                        PRODUCT_IMAGE_SELECTOR
                    ).all()
                    total_images = len(image_elements)

                    logger.info(f"📸 Found {total_images} images for product")

                    # Extract URLs from all images and check each one with CLIP
                    image_urls = []

                    for idx, img_li_element in enumerate(image_elements, 1):
                        try:
                            # Get img tag from li
                            img_element = img_li_element.locator("img").first

                            # Extract image URL using multiple attributes
                            img_url = None

                            # 1. Try kl-img attribute first
                            img_url = await img_element.get_attribute("kl-img")
                            if not img_url:
                                # 2. Try data-srcset
                                data_srcset = await img_element.get_attribute(
                                    "data-srcset"
                                )
                                if data_srcset:
                                    try:
                                        img_url = (
                                            data_srcset.split(",")[0]
                                            .strip()
                                            .split(" ")[0]
                                        )
                                    except Exception:
                                        pass

                            # 3. Try srcset
                            if not img_url:
                                srcset = await img_element.get_attribute("srcset")
                                if srcset and not srcset.startswith("data:image"):
                                    try:
                                        img_url = (
                                            srcset.split(",")[0].strip().split(" ")[0]
                                        )
                                    except Exception:
                                        pass

                            # 4. Try src
                            if not img_url:
                                src = await img_element.get_attribute("src")
                                if src and not src.startswith("data:image"):
                                    img_url = src

                            # 5. Try data-src
                            if not img_url:
                                img_url = await img_element.get_attribute("data-src")
                                if img_url and img_url.startswith("data:image"):
                                    img_url = None

                            if img_url:
                                # Ensure absolute URL
                                if not img_url.startswith("http"):
                                    if img_url.startswith("/"):
                                        img_url = f"https://www.givenchy.com{img_url}"
                                    else:
                                        img_url = f"https://www.givenchy.com/{img_url}"

                                image_urls.append(img_url)
                                logger.debug(f"Image {idx}: Extracted URL")
                        except Exception as e:
                            logger.debug(f"Image {idx}: Failed to extract URL - {e}")

                    # Check every image with CLIP, collect confidences
                    checked_images = []  # list of dicts: {url, is_sole, confidence, scores}
                    for idx, img_url in enumerate(image_urls, 1):
                        logger.debug(
                            f"Checking image {idx}/{len(image_urls)} with CLIP model..."
                        )
                        is_sole, confidence, scores = self.is_sole_image(img_url)
                        print(
                            {
                                "url": img_url,
                                "is_sole": is_sole,
                                "confidence": confidence,
                                "scores": scores,
                            }
                        )
                        checked_images.append(
                            {
                                "url": img_url,
                                "is_sole": is_sole,
                                "confidence": confidence,
                                "scores": scores,
                            }
                        )

                        if is_sole:
                            logger.info(
                                f"  ✓ Image {idx}: Detected as SOLE (conf={confidence:.2f})"
                            )
                        else:
                            # Log which labels dominated the non-sole prediction
                            if scores:
                                sole_scores = {
                                    "sole_tread": scores.get("sole_tread", 0),
                                    "sole_rubber": scores.get("sole_rubber", 0),
                                    "sole_outsole": scores.get("sole_outsole", 0),
                                    "sole_with_upper": scores.get("sole_with_upper", 0),
                                    "sole_visible": scores.get("sole_visible", 0),
                                }
                                non_sole_scores = {
                                    "side_view": scores.get("side_view", 0),
                                    "front_view": scores.get("front_view", 0),
                                    "upper_only": scores.get("upper_only", 0),
                                }

                                top_sole = max(sole_scores, key=sole_scores.get)
                                top_non_sole = max(
                                    non_sole_scores, key=non_sole_scores.get
                                )

                                logger.info(
                                    f"  ✗ Image {idx}: Not a sole (conf={confidence:.2f}) | "
                                    f"Top sole: {top_sole}({sole_scores[top_sole]:.3f}) | "
                                    f"Top non-sole: {top_non_sole}({non_sole_scores[top_non_sole]:.3f})"
                                )
                            else:
                                logger.debug(
                                    f"  ✗ Image {idx}: Not a sole image (conf={confidence:.2f})"
                                )

                    # Choose best image: only accept sole images
                    image_url = None
                    if checked_images:
                        # Filter those predicted as sole
                        sole_candidates = [c for c in checked_images if c["is_sole"]]

                        if sole_candidates:
                            # pick the candidate with highest confidence
                            best = max(sole_candidates, key=lambda x: x["confidence"])
                            image_url = best["url"]
                            logger.info(
                                f"✅ Selected sole image: {image_url} (conf={best['confidence']:.2f})"
                            )
                        else:
                            # No sole images detected - skip product
                            logger.warning(
                                f"⚠️ No sole images detected in {len(image_urls)} images - skipping product"
                            )
                            return None
                    else:
                        logger.warning(
                            "⚠️ No images were available to check (0 extracted)"
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
        2. Load all products via infinite scroll
        3. Extract product links
        4. Scrape each product detail
        5. Save results
        """
        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

        logger.info("Starting Givenchy scraper")
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

                # Step 2: Load all products via infinite scroll
                logger.info("Step 2: Loading all products via infinite scroll...")
                click_count = await self.load_all_products(page)
                logger.info(f"✓ Infinite scroll complete ({click_count} clicks)")

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

                    # Check if page is still open
                    if page.is_closed():
                        logger.warning("Page has been closed, stopping scraper")
                        should_stop = True
                        break

                    logger.info(
                        f"\n  Product {idx}/{self.total_products_found}: Scraping..."
                    )
                    try:
                        details = await self.extract_product_details(
                            page, product_url, idx, self.total_products_found
                        )

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
                                f"   Sole Image URL: {details.get('image_url', 'N/A')[:80] if details.get('image_url') else 'N/A'}..."
                            )

                            self.products.append(details)
                            current_batch.append(details)

                            # Process batch when size is reached
                            if len(current_batch) >= batch_size and batch_callback:
                                should_continue = (
                                    await self._process_batch_with_callback(
                                        current_batch,
                                        batch_callback,
                                        brand_field="brand",
                                        name_field="name",
                                        url_field="source_url",
                                        image_url_field="image_url",
                                    )
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
                        url_field="source_url",
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
        output_file = output_dir / "givenchy_shoes.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.products, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Saved {len(self.products)} products to {output_file}")

        # Save failed URLs
        if self.failed_urls:
            failed_file = output_dir / "givenchy_failed_urls.txt"
            with open(failed_file, "w", encoding="utf-8") as f:
                f.write("\n".join(self.failed_urls))
            logger.info(f"✓ Saved {len(self.failed_urls)} failed URLs to {failed_file}")

        # Save summary
        summary_file = output_dir / "givenchy_summary.json"
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
        print("GIVENCHY SCRAPER - SUMMARY")
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
    scraper = GivenchyScraper(base_url=BASE_URL)

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
