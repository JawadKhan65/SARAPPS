"""
Canterbury scraper using Playwright.

Scrapes rugby shoes from https://canterbury.nl/nl/rugbyschoenen/alles-bekijken
Handles pagination and extracts:
  - Brand name (hardcoded: "Canterbury")
  - Product name (from h1.page-title)
  - Product URL
  - Third image from fotorama gallery (imgs[2])

Professional features:
  - Pagination handling via query params (?p=1, ?p=2, etc)
  - Scroll-to-load pagination detection
  - Robust element waiting with multiple strategies
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
from .chromium_config import get_chromium_launch_config
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
PAGES_CONTAINER_SELECTOR = ".pages"
PAGINATION_UL_SELECTOR = ".pages ul.items"
PAGINATION_LI_SELECTOR = ".pages ul.items li"
PRODUCTS_CONTAINER_SELECTOR = "ol.products"
PRODUCT_ITEM_SELECTOR = "ol.products li.item"
PRODUCT_LINK_SELECTOR = "a"

# Product detail selectors
PRODUCT_NAME_SELECTOR = "h1.page-title"
PRODUCT_IMAGES_CONTAINER_SELECTOR = ".fotorama__nav"
PRODUCT_IMAGE_SELECTOR = "img"

BRAND_NAME = "Canterbury"


class CanterburyScraper(BatchProcessingMixin):
    """Canterbury rugby shoes scraper with pagination support."""

    def __init__(
        self,
        base_url: str = "https://canterbury.nl/nl/rugbyschoenen/alles-bekijken",
    ):
        self.base_url = base_url
        self.products: List[Dict[str, Any]] = []
        self.failed_urls: List[str] = []
        self.product_links: List[str] = []
        self.total_pages = 1
        self.start_time = None

    async def handle_cookie_consent(self, page: Page):
        """
        Handle cookie consent dialog by clicking 'Allow All' button.

        Looks for button with ID: CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll
        Only called on the initial page load.
        """
        try:
            # Wait a bit for cookie dialog to appear
            await asyncio.sleep(2)

            # Try to find and click the cookie button
            button_id = "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"
            button = page.locator(f"#{button_id}")

            logger.debug(f"🍪 Checking for cookie button with ID: {button_id}")

            # Check if button exists
            try:
                # Use wait_for with shorter timeout to check presence
                await button.wait_for(state="visible", timeout=5000)
                logger.info("🍪 Cookie consent dialog found, clicking 'Allow All'...")
                await button.click(timeout=5000)
                logger.info("✅ Cookie consent accepted")
                # Wait a bit for dialog to close
                await asyncio.sleep(2)
            except Exception:
                logger.info(
                    "🍪 Cookie consent dialog not found (OK if site doesn't use cookies)"
                )

        except Exception as e:
            logger.warning(f"⚠️ Cookie consent handling error (non-critical): {e}")

    async def get_total_pages(self, page: Page) -> int:
        """
        Extract total number of pages from pagination element.

        Process:
        1. Wait for .pages container
        2. Wait for ul.items inside
        3. Get all li elements
        4. Select SECOND-TO-LAST li (index -2)
        5. Extract page number from the second span (contains just the number, not "Pagina" label)
        """
        try:
            logger.info("Fetching total page count...")

            # Wait for pagination container
            await page.wait_for_selector(PAGES_CONTAINER_SELECTOR, timeout=15000)
            logger.debug("✓ Found pagination container")

            # Wait for pagination UL
            await page.wait_for_selector(PAGINATION_UL_SELECTOR, timeout=15000)
            logger.debug("✓ Found pagination UL")

            # Get all pagination LI elements
            pagination_items = await page.locator(PAGINATION_LI_SELECTOR).all()

            if not pagination_items:
                logger.warning("No pagination items found, assuming 1 page")
                return 1

            # Get the second-to-last LI element (index -2)
            if len(pagination_items) < 2:
                logger.warning("Not enough pagination items, assuming 1 page")
                return 1

            second_last_li = pagination_items[-2]

            # Extract the second span inside the li (contains the page number)
            # Structure: <li><a><span class="label">Pagina</span> <span>3</span></a></li>
            span_elements = await second_last_li.locator("span").all()

            if len(span_elements) < 2:
                logger.warning("Could not find page number span in pagination item")
                return 1

            # Get the second span (index 1) which contains the page number
            page_number_span = span_elements[1]
            page_number_text = await page_number_span.text_content()

            if page_number_text:
                page_number_text = page_number_text.strip()
                try:
                    total_pages = int(page_number_text)
                    logger.info(f"✓ Found {total_pages} total pages")
                    return total_pages
                except ValueError:
                    logger.warning(
                        f"Could not parse page number from: '{page_number_text}'"
                    )
                    return 1
            else:
                logger.warning("Page number span is empty")
                return 1

        except Exception as e:
            logger.warning(f"Error getting total pages: {e}. Assuming 1 page")
            return 1

    async def get_product_links_from_page(self, page: Page) -> List[str]:
        """
        Extract all product links from current page.

        Process:
        1. Wait for ol.products container
        2. Get all li.item elements
        3. Extract <a> href from each item
        4. Return list of absolute URLs
        """
        try:
            # Wait for products container
            await page.wait_for_selector(PRODUCTS_CONTAINER_SELECTOR, timeout=15000)
            logger.debug("✓ Found products container")

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
                            product_links.append(f"https://canterbury.nl{href}")
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
        1. Product name: h1.page-title inner text
        2. Third image (index 2) from .fotorama__nav container
        """
        try:
            logger.debug(f"Navigating to: {url}")

            # Navigate with domcontentloaded (faster than networkidle)
            await page.goto(
                url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
            )

            # Wait for product name to load
            await page.wait_for_selector(PRODUCT_NAME_SELECTOR, timeout=15000)
            logger.debug("✓ Product name loaded")

            # Scroll to ensure images are in viewport and trigger loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)

            # Wait for fotorama thumbnails to load
            try:
                # Wait for at least one fotorama__thumb element
                await page.wait_for_selector(".fotorama__thumb", timeout=20000)
                logger.debug("✓ Fotorama thumbnails found")

                # Wait for thumbnails to be visible
                thumb_elements = page.locator(".fotorama__thumb")
                await thumb_elements.first.wait_for(state="visible", timeout=20000)
                logger.debug("✓ Fotorama thumbnails are visible")

                # Get count of thumbnails
                thumb_count = await thumb_elements.count()
                logger.debug(f"✓ Found {thumb_count} fotorama thumbnails")

            except Exception as e:
                logger.warning(f"⚠️ Fotorama thumbnails not found or loading error: {e}")

            # Give extra time for all images to fully render
            await asyncio.sleep(2)

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

            # Extract third image (index 2)
            third_image_url = None
            try:
                logger.debug("Extracting third image from fotorama thumbs...")

                # Get all fotorama__thumb divs (each contains one img)
                thumb_divs = page.locator(".fotorama__thumb")
                thumb_count = await thumb_divs.count()
                logger.info(f"📸 Found {thumb_count} fotorama thumb divs")

                if thumb_count >= 3:
                    # Get the third thumb div (index 2)
                    third_thumb = thumb_divs.nth(2)
                    logger.debug("✓ Selected third fotorama thumb div")

                    # Get the img tag inside the third thumb
                    img_in_thumb = third_thumb.locator("img").first

                    # Try src first, then data-src
                    third_image_url = await img_in_thumb.get_attribute("src")
                    if not third_image_url:
                        third_image_url = await img_in_thumb.get_attribute("data-src")

                    if third_image_url:
                        logger.debug(
                            f"Raw image URL before conversion: {third_image_url}"
                        )

                        # Ensure absolute URL
                        if not third_image_url.startswith("http"):
                            if third_image_url.startswith("/"):
                                third_image_url = (
                                    f"https://canterbury.nl{third_image_url}"
                                )
                            else:
                                third_image_url = (
                                    f"https://canterbury.nl/{third_image_url}"
                                )

                        logger.info(f"✅ Image URL: {third_image_url}")
                    else:
                        logger.warning("⚠️ Third thumb's img tag has no src or data-src")
                else:
                    logger.warning(
                        f"⚠️ Not enough fotorama thumbs. Found {thumb_count}, need at least 3"
                    )

            except Exception as e:
                logger.warning(f"❌ Failed to extract third image: {e}")

            # Log final product data
            product_data = {
                "brand": BRAND_NAME,
                "name": product_name,
                "source_url": url,
                "image_url": third_image_url,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(f"📦 Product: {product_name}")
            logger.info(f"   Image: {third_image_url}")

            return product_data

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
           a. Navigate to page URL with ?p=N param
           b. Extract product links
           c. Scrape each product (with real-time batch processing)
        """
        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

        logger.info("Starting Canterbury scraper")
        logger.info(f"Base URL: {self.base_url}")
        if batch_callback:
            logger.info("Using in-memory image processing (no temp files)")
        self.start_time = datetime.now()

        async with async_playwright() as p:
            browser = await p.chromium.launch(**get_chromium_launch_config())
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

                        # Handle cookie consent dialog
                        await self.handle_cookie_consent(page)

                        # Wait for pagination element to appear
                        await page.wait_for_selector(
                            PAGES_CONTAINER_SELECTOR, timeout=15000
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

                    # Navigate to page with ?p= parameter
                    page_url = f"{self.base_url}?p={page_num}"
                    logger.info(f"Navigating to page URL: {page_url}")

                    for attempt in range(MAX_RETRIES):
                        try:
                            await page.goto(
                                page_url,
                                wait_until="domcontentloaded",
                                timeout=NAVIGATION_TIMEOUT,
                            )
                            # Wait for products container to appear
                            await page.wait_for_selector(
                                PRODUCTS_CONTAINER_SELECTOR, timeout=15000
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
                        try:
                            details = await self.extract_product_details(
                                page, product_url
                            )

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

                            else:
                                self.failed_urls.append(product_url)
                                logger.error(f"  ✗ Failed to scrape {product_url}")
                        except Exception as e:
                            logger.error(f"  ✗ Error scraping product {idx}: {e}")
                            self.failed_urls.append(product_url)

                        await asyncio.sleep(
                            2
                        )  # Longer delay between requests for stability

                    # Delay between pages
                    if page_num < pages_to_scrape:
                        await asyncio.sleep(2)

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
        output_file = output_dir / "canterbury_shoes.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.products, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Saved {len(self.products)} products to {output_file}")

        # Save failed URLs
        if self.failed_urls:
            failed_file = output_dir / "canterbury_failed_urls.txt"
            with open(failed_file, "w", encoding="utf-8") as f:
                f.write("\n".join(self.failed_urls))
            logger.info(f"✓ Saved {len(self.failed_urls)} failed URLs to {failed_file}")

        # Save summary
        summary_file = output_dir / "canterbury_summary.json"
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
        print("CANTERBURY SCRAPER - SUMMARY")
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
    scraper = CanterburyScraperr(
        base_url="https://canterbury.nl/nl/rugbyschoenen/alles-bekijken"
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
