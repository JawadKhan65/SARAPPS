"""
Crockett & Jones scraper using Playwright.

Scrapes shoes from https://eu.crockettandjones.com/collections/all-mens-styles
Handles pagination and extracts:
  - Brand name (hardcoded: "Crockett & Jones")
  - Shoe name (from "all-caps" and "regular" spans)
  - Product URL
  - Second image from product gallery

Professional features:
  - Pagination handling
  - Robust element waiting
  - Error tracking and retry logic
  - Comprehensive logging
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from playwright.async_api import async_playwright, Page
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))
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

# CSS Selectors
PAGINATION_CONTAINER_SELECTOR = ".paging"
PAGINATION_UL_SELECTOR = ".paging ul"
PAGINATION_LI_SELECTOR = ".paging ul li"
PRODUCTS_GRID_SELECTOR = ".products-grid"
PRODUCT_ITEM_SELECTOR = ".product-item"
PRODUCT_LINK_SELECTOR = "a"

# Selectors for product details
PRODUCT_CONTENT_SELECTOR = ".section-product__content"
PRODUCT_NAME_CAPS_SELECTOR = ".all-caps"
PRODUCT_NAME_REGULAR_SELECTOR = ".regular"
PRODUCT_IMAGES_CONTAINER_SELECTOR = ".slick-track"
PRODUCT_IMAGE_SELECTOR = "img"

BRAND_NAME = "Crockett & Jones"


class CrockettJonesScraper(BatchProcessingMixin):
    """Crockett & Jones shoes scraper with pagination support."""

    def __init__(
        self,
        base_url: str = "https://eu.crockettandjones.com/collections/all-mens-styles",
    ):
        self.base_url = base_url
        self.products: List[Dict[str, Any]] = []
        self.failed_urls: List[str] = []
        self.product_links: List[str] = []
        self.total_pages = 1
        self.start_time = None

    async def get_total_pages(self, page: Page) -> int:
        """
        Extract total number of pages from pagination element.

        Process:
        1. Wait for pagination container
        2. Get last <li> in pagination UL
        3. Extract inner text as page number
        """
        try:
            logger.info("Fetching total page count...")

            # Wait for pagination container
            await page.wait_for_selector(PAGINATION_CONTAINER_SELECTOR, timeout=10000)
            logger.debug("✓ Found pagination container")

            # Get all pagination LI elements
            pagination_items = await page.locator(PAGINATION_LI_SELECTOR).all()

            if not pagination_items:
                logger.warning("No pagination items found, assuming 1 page")
                return 1

            # Get the last LI element
            last_li = pagination_items[-1]
            last_page_text = await last_li.text_content()

            if last_page_text:
                last_page_text = last_page_text.strip()
                try:
                    total_pages = int(last_page_text)
                    logger.info(f"✓ Found {total_pages} total pages")
                    return total_pages
                except ValueError:
                    logger.warning(
                        f"Could not parse page number from: '{last_page_text}'"
                    )
                    return 1
            else:
                logger.warning("Last pagination item is empty")
                return 1

        except Exception as e:
            logger.warning(f"Error getting total pages: {e}. Assuming 1 page")
            return 1

    async def get_product_links_from_page(self, page: Page) -> List[str]:
        """
        Extract all product links from current page.

        Process:
        1. Wait for products grid to load
        2. Get all product items
        3. Extract <a> href from each item
        4. Return list of absolute URLs
        """
        try:
            # Wait for products grid
            await page.wait_for_selector(PRODUCTS_GRID_SELECTOR, timeout=15000)
            logger.debug("✓ Found products grid")

            # Wait for product items to be visible
            await page.wait_for_selector(PRODUCT_ITEM_SELECTOR, timeout=15000)
            logger.debug("✓ Product items are visible")

            # Give extra time for items to fully render
            await asyncio.sleep(1)

            # Get all product items
            product_items = await page.locator(PRODUCT_ITEM_SELECTOR).all()
            logger.debug(f"Found {len(product_items)} product items on this page")

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
                            product_links.append(
                                f"https://eu.crockettandjones.com{href}"
                            )
                        logger.debug(f"  Item {idx}: {href}")
                    else:
                        extraction_errors += 1
                        logger.debug(f"  Item {idx}: No href attribute")

                except Exception as e:
                    extraction_errors += 1
                    logger.debug(f"  Item {idx}: Error - {e}")
                    continue

            logger.info(
                f"✓ Extracted {len(product_links)} product links "
                f"({extraction_errors} errors)"
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
        1. Shoe name: concat "all-caps" and "regular" spans with "-"
        2. Second image from slick-track container
        """
        try:
            logger.debug(f"Navigating to: {url}")

            # Navigate with domcontentloaded (faster than networkidle)
            await page.goto(
                url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
            )

            # Wait for product content to load
            await page.wait_for_selector(PRODUCT_CONTENT_SELECTOR, timeout=15000)
            logger.debug("✓ Product content loaded")

            # Scroll to ensure images are in viewport and trigger loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)

            # Wait for images container with increased timeout
            await page.wait_for_selector(
                PRODUCT_IMAGES_CONTAINER_SELECTOR, timeout=20000
            )
            logger.debug("✓ Images container found")

            # Wait for actual images to load - look for img tags with src/data-src
            try:
                images_container = page.locator(PRODUCT_IMAGES_CONTAINER_SELECTOR).first
                # Wait for at least one image to be present
                await images_container.locator(PRODUCT_IMAGE_SELECTOR).first.wait_for(
                    timeout=15000
                )
                logger.debug("✓ Images are loading")
            except Exception as e:
                logger.debug(f"Image wait error (non-critical): {e}")

            # Give extra time for all images to fully render and load
            await asyncio.sleep(3)

            # Extract shoe name
            shoe_name = "Unknown"
            try:
                # Get the content section
                content_section = page.locator(PRODUCT_CONTENT_SELECTOR).first

                # Get "all-caps" span
                caps_element = content_section.locator(PRODUCT_NAME_CAPS_SELECTOR).first
                caps_text = await caps_element.text_content(timeout=5000)
                caps_text = caps_text.strip() if caps_text else ""

                # Get "regular" span
                regular_element = content_section.locator(
                    PRODUCT_NAME_REGULAR_SELECTOR
                ).first
                regular_text = await regular_element.text_content(timeout=5000)
                regular_text = regular_text.strip() if regular_text else ""

                # Combine with "-" separator
                if caps_text and regular_text:
                    shoe_name = f"{caps_text} - {regular_text}"
                elif caps_text:
                    shoe_name = caps_text
                elif regular_text:
                    shoe_name = regular_text

                if shoe_name != "Unknown":
                    logger.debug(f"  Shoe name: {shoe_name}")

            except Exception as e:
                logger.warning(f"Failed to extract shoe name: {e}")

            # Extract second image (index 1) from background-image CSS
            second_image_url = None
            try:
                logger.debug("Extracting second image from slick-track...")

                # Get the slick-track container
                slick_track = page.locator(PRODUCT_IMAGES_CONTAINER_SELECTOR).first

                if slick_track:
                    # Find the div with data-slick-index="1"
                    image_div = page.locator(
                        f'{PRODUCT_IMAGES_CONTAINER_SELECTOR} div[data-slick-index="1"]'
                    ).first

                    if image_div:
                        logger.debug("✓ Found image div with data-slick-index='1'")

                        # Get the span with class "section-product__image"
                        image_span = image_div.locator(".section-product__image").first

                        if image_span:
                            logger.debug("✓ Found section-product__image span")

                            # Get the style attribute
                            style_attr = await image_span.get_attribute("style")

                            if style_attr:
                                logger.debug(f"Style attribute: {style_attr}")

                                # Extract URL from background-image: url('...')
                                import re

                                url_match = re.search(
                                    r"url\(['\"]?(.+?)['\"]?\)", style_attr
                                )

                                if url_match:
                                    second_image_url = url_match.group(1)

                                    # Remove any extra characters from URL
                                    second_image_url = second_image_url.strip()

                                    # Ensure absolute URL (handle protocol-relative URLs)
                                    if second_image_url.startswith("//"):
                                        second_image_url = f"https:{second_image_url}"
                                    elif not second_image_url.startswith("http"):
                                        if second_image_url.startswith("/"):
                                            second_image_url = f"https://eu.crockettandjones.com{second_image_url}"
                                        else:
                                            second_image_url = f"https://eu.crockettandjones.com/{second_image_url}"

                                    logger.debug(
                                        f"✓ Extracted image URL: {second_image_url}"
                                    )
                                else:
                                    logger.warning(
                                        "Could not extract URL from style attribute"
                                    )
                            else:
                                logger.warning("No style attribute found on image span")
                        else:
                            logger.warning("Could not find section-product__image span")
                    else:
                        logger.warning("Could not find div with data-slick-index='1'")
                else:
                    logger.warning("Could not find slick-track container")

            except Exception as e:
                logger.warning(f"Failed to extract second image: {e}", exc_info=True)

            return {
                "brand": BRAND_NAME,
                "name": shoe_name,
                "source_url": url,
                "image_url": second_image_url,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to extract details from {url}: {e}", exc_info=True)
            return None

    async def scrape(
        self,
        max_pages: Optional[int] = None,
        batch_callback=None,
        batch_size: int = 20,
        is_cancelled=None,
    ):
        """
        Main scraping function with batch processing support.

        Args:
            max_pages: Maximum number of pages to scrape
            batch_callback: Async function to call with each batch of products
            batch_size: Number of products to collect before calling batch_callback
            is_cancelled: Optional function to check if scraping should be cancelled

        Process:
        1. Navigate to base URL
        2. Get total page count
        3. For each page:
           a. Navigate to page URL
           b. Extract product links
           c. Scrape each product (with real-time batch processing)
        """
        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

        logger.info("Starting Crockett & Jones scraper")
        logger.info(f"Base URL: {self.base_url}")
        if batch_callback:
            logger.info("Using in-memory image processing (no temp files)")
        self.start_time = datetime.now()

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
                        # Wait for pagination element to appear after DOM loads
                        await page.wait_for_selector(
                            PAGINATION_CONTAINER_SELECTOR, timeout=15000
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
                                f"Failed to navigate after {MAX_RETRIES} attempts"
                            )
                            raise

                # Step 2: Get total pages
                logger.info("Step 2: Fetching pagination info...")
                self.total_pages = await self.get_total_pages(page)

                # Limit pages if specified
                pages_to_scrape = (
                    min(self.total_pages, max_pages) if max_pages else self.total_pages
                )
                logger.info(f"Will scrape {pages_to_scrape} pages")

                # Step 3: Scrape each page with batch processing
                logger.info("Step 3: Scraping all pages...")
                current_batch = []
                should_stop = False

                for page_num in range(1, pages_to_scrape + 1):
                    if should_stop:
                        logger.info("Stopping scraper early due to low uniqueness")
                        break

                    logger.info(f"\n--- Page {page_num}/{pages_to_scrape} ---")

                    # Navigate to page
                    page_url = f"{self.base_url}?page={page_num}"
                    logger.info(f"Navigating to page URL: {page_url}")

                    for attempt in range(MAX_RETRIES):
                        try:
                            await page.goto(
                                page_url,
                                wait_until="domcontentloaded",
                                timeout=NAVIGATION_TIMEOUT,
                            )
                            # Wait for products grid to appear
                            await page.wait_for_selector(
                                PRODUCTS_GRID_SELECTOR, timeout=15000
                            )
                            await asyncio.sleep(1)  # Extra time for items to render
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

                    # Extract product links from this page
                    page_links = await self.get_product_links_from_page(page)
                    self.product_links.extend(page_links)

                    # Scrape each product with batch processing
                    for idx, product_url in enumerate(page_links, 1):
                        # Check for cancellation
                        if is_cancelled and is_cancelled():
                            logger.warning(
                                "🛑 Cancellation detected - stopping scraper immediately"
                            )
                            should_stop = True
                            break

                        if should_stop:
                            break

                        # Check if page is still open
                        if page.is_closed():
                            logger.warning("Page has been closed, stopping scraper")
                            should_stop = True
                            break

                        logger.info(f"  Product {idx}/{len(page_links)}: Scraping...")
                        details = await self.extract_product_details(page, product_url)

                        if details:
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
                        else:
                            self.failed_urls.append(product_url)
                            logger.error(f"  ✗ Failed to scrape {product_url}")

                        await asyncio.sleep(1)  # Delay between requests

                    # Delay between pages
                    if page_num < pages_to_scrape:
                        await asyncio.sleep(2)

                # Process remaining items in final batch
                if current_batch and batch_callback and not should_stop:
                    logger.info(
                        f"🔄 Processing final batch of {len(current_batch)} products..."
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
                logger.error(f"Scraping failed: {e}", exc_info=True)
            finally:
                await browser.close()

    def save_results(self, output_dir: Optional[str] = None):
        """Save scraped products to JSON file."""
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # Save main results
        output_file = output_dir / "crockettandjones_shoes.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.products, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Saved {len(self.products)} products to {output_file}")

        # Save failed URLs
        if self.failed_urls:
            failed_file = output_dir / "crockettandjones_failed_urls.txt"
            with open(failed_file, "w", encoding="utf-8") as f:
                f.write("\n".join(self.failed_urls))
            logger.info(f"✓ Saved {len(self.failed_urls)} failed URLs to {failed_file}")

        # Save summary
        summary_file = output_dir / "crockettandjones_summary.json"
        summary = {
            "total_products": len(self.products),
            "failed_products": len(self.failed_urls),
            "total_pages_scraped": self.total_pages,
            "success_rate": (
                f"{100 * len(self.products) / (len(self.products) + len(self.failed_urls)):.1f}%"
                if (len(self.products) + len(self.failed_urls)) > 0
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
        print("\n" + "=" * 120)
        print("CROCKETT & JONES SCRAPER - SUMMARY")
        print("=" * 120)
        print(f"\nTotal Pages Scraped: {self.total_pages}")
        print(f"Total Products Scraped: {len(self.products)}")
        print(f"Failed URLs: {len(self.failed_urls)}")

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

        print("=" * 120 + "\n")


async def main():
    """Main entry point."""
    scraper = CrocettJonesScraper(
        base_url="https://eu.crockettandjones.com/collections/all-mens-styles"
    )

    try:
        # Scrape all pages
        # Production: scrape all pages
        await scraper.scrape(max_pages=None)

        # Save results
        scraper.save_results()

        # Print summary
        scraper.print_summary()

    except Exception as e:
        logger.error(f"Scraper failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
