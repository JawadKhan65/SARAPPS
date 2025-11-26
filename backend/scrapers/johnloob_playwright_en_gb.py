"""
John Lobb shoes scraper using Playwright.

Scrapes shoes from https://www.johnlobb.com/en_gb/shoes/shoes-all
Collects:
  - Brand name (hardcoded: "John Lobb")
  - Shoe name (from XPath)
  - Product URL
  - Last image from product page
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
CATEGORY_LISTING_GRID_SELECTOR = ".category-listing-grid"
PRODUCT_ITEM_SELECTOR = ".category-listing-item"
PRODUCT_LINK_SELECTOR = "a"

# XPaths
SHOE_NAME_XPATH = '//*[@id="content-container"]/product-view/div/product-page/div[1]/div/div/product-main/div/ng-include/div/div/div[2]/div/ng-include/p'
IMAGES_CONTAINER_ID = "product-main-new-images-container"


class JohnLobbScraper:
    """John Lobb shoes scraper."""

    def __init__(
        self, base_url: str = "https://www.johnlobb.com/en_gb/shoes/shoes-all"
    ):
        self.base_url = base_url
        self.products: List[Dict[str, Any]] = []
        self.failed_urls: List[str] = []
        self.product_links: List[str] = []
        self.start_time = None

    async def scroll_to_load_all_products(
        self,
        page: Page,
        max_scroll_attempts: int = 50,
        timeout_between_scrolls: int = 2,
    ):
        """
        Scroll to bottom of page to load all products via infinite scroll.

        This is essential for pages that load products dynamically.
        Strategy:
        1. Scroll to bottom
        2. Wait for new items to load
        3. Repeat until no new items appear
        4. Verify we've loaded everything
        """
        logger.info("Starting infinite scroll to load all products...")

        previous_count = 0
        no_change_count = 0
        max_no_change_attempts = 3  # If count doesn't change 3 times, we're done

        for attempt in range(max_scroll_attempts):
            try:
                # Get current product count
                current_items = await page.locator(PRODUCT_ITEM_SELECTOR).all()
                current_count = len(current_items)

                logger.info(
                    f"Scroll attempt {attempt + 1}: {current_count} products loaded"
                )

                # Check if new items were added
                if current_count == previous_count:
                    no_change_count += 1
                    logger.debug(
                        f"No new items loaded (no-change count: {no_change_count}/{max_no_change_attempts})"
                    )

                    # If count hasn't changed multiple times, we've likely reached the end
                    if no_change_count >= max_no_change_attempts:
                        logger.info(
                            f"✓ Infinite scroll complete. Total products: {current_count}"
                        )
                        break
                else:
                    # Reset counter when new items are found
                    no_change_count = 0
                    previous_count = current_count

                # Scroll to bottom of page
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                # Wait for new items to load
                await asyncio.sleep(timeout_between_scrolls)

            except Exception as e:
                logger.warning(f"Error during scroll attempt {attempt + 1}: {e}")
                await asyncio.sleep(1)

        # Final count
        final_items = await page.locator(PRODUCT_ITEM_SELECTOR).all()
        logger.info(f"✓ Scrolling complete. Final product count: {len(final_items)}")

    async def get_product_links_from_listing(self, page: Page) -> List[str]:
        """
        Extract all product links from listing page.

        Process:
        1. Wait for grid container to load
        2. Wait for product items to appear
        3. Scroll to bottom to load all products
        4. Extract href from each product link
        5. Return deduplicated list of URLs
        """
        try:
            # Step 1: Wait for the category listing grid to load
            logger.info("Waiting for category listing grid...")
            await page.wait_for_selector(CATEGORY_LISTING_GRID_SELECTOR, timeout=15000)
            logger.info("✓ Found category listing grid")

            # Step 2: Wait for product items to be visible
            logger.info("Waiting for product items...")
            await page.wait_for_selector(PRODUCT_ITEM_SELECTOR, timeout=15000)
            logger.info("✓ Product items are visible")

            # Step 3: Scroll to load all products (critical for infinite scroll)
            await self.scroll_to_load_all_products(page)

            # Step 4: Wait a bit more to ensure all items are fully rendered
            await asyncio.sleep(2)

            # Step 5: Get all product items
            product_items = await page.locator(PRODUCT_ITEM_SELECTOR).all()
            logger.info(f"Total product items to process: {len(product_items)}")

            if len(product_items) == 0:
                logger.error("No product items found after scrolling!")
                title = await page.title()
                logger.error(f"Page title: {title}")
                return []

            # Step 6: Extract links from each product item
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
                            product_links.append(f"https://www.johnlobb.com{href}")
                        logger.debug(f"  Product {idx}: {href}")
                    else:
                        extraction_errors += 1
                except Exception as e:
                    logger.warning(f"Failed to extract link from product {idx}: {e}")
                    extraction_errors += 1
                    continue

            logger.info(
                f"✓ Extracted {len(product_links)} product links "
                f"({extraction_errors} extraction errors)"
            )
            return product_links

        except Exception as e:
            logger.error(f"Failed to get product links: {e}", exc_info=True)
            # Try to print page content for debugging
            try:
                content = await page.content()
                logger.debug(f"Page content length: {len(content)}")
                # Check if selectors exist in HTML
                if ".category-listing-grid" in content:
                    logger.warning(
                        "Category listing grid found in HTML but selector failed"
                    )
                if ".category-listing-item" in content:
                    logger.warning(
                        "Category listing items found in HTML but selector failed"
                    )
            except Exception as e:
                logger.debug(f"Could not debug page content: {e}")
            return []

    async def extract_product_details(
        self, page: Page, url: str
    ) -> Optional[Dict[str, Any]]:
        """Extract product details from product page."""
        try:
            logger.info(f"Navigating to product: {url}")
            await page.goto(url, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)

            # Wait for main content and images to load
            try:
                await page.wait_for_selector("#content-container", timeout=15000)
            except Exception as e:
                logger.warning(f"Content container not found: {e}")

            # Wait for images container specifically
            try:
                await page.wait_for_selector(f"#{IMAGES_CONTAINER_ID}", timeout=15000)
            except Exception as e:
                logger.warning(f"Images container not found: {e}")

            await asyncio.sleep(2)  # Give extra time for images to fully load

            # Extract shoe name
            shoe_name = "Unknown"
            try:
                name_elem = page.locator(f"xpath={SHOE_NAME_XPATH}").first
                shoe_name_text = await name_elem.text_content(timeout=5000)
                if shoe_name_text:
                    shoe_name = shoe_name_text.strip()
                    logger.debug(f"  Shoe name: {shoe_name}")
            except Exception as e:
                logger.warning(f"Failed to extract shoe name: {e}")

            # Get the last image from the images container
            last_image_url = None
            try:
                # Find the images container by ID
                images_container = page.locator(f"#{IMAGES_CONTAINER_ID}").first

                if images_container:
                    # Get all images in the container
                    images = await images_container.locator("img").all()

                    if images:
                        # Get the last image
                        last_image = images[-1]

                        # Try to get src or data-src
                        last_image_url = await last_image.get_attribute("src")
                        if not last_image_url:
                            last_image_url = await last_image.get_attribute("data-src")

                        if last_image_url:
                            # Ensure absolute URL
                            if not last_image_url.startswith("http"):
                                if last_image_url.startswith("/"):
                                    last_image_url = (
                                        f"https://www.johnlobb.com{last_image_url}"
                                    )
                                else:
                                    last_image_url = (
                                        f"https://www.johnlobb.com/{last_image_url}"
                                    )

                            logger.debug(f"  Last image: {last_image_url}")
                    else:
                        logger.warning(f"No images found in container for {url}")
                else:
                    logger.warning(f"Images container not found for {url}")
            except Exception as e:
                logger.warning(f"Failed to extract last image: {e}")

            return {
                "brand": "John Lobb",
                "name": shoe_name,
                "url": url,
                "last_image_url": last_image_url,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to extract details from {url}: {e}")
            return None

    def _download_image_to_memory(self, image_url: str) -> Optional[bytes]:
        """Download image directly to memory as bytes - no disk I/O"""
        import requests

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

    def _prepare_batch_for_processing(self, batch: List[Dict]) -> List[Dict]:
        """Download images to memory and prepare batch for processing"""
        processed_batch = []

        for product in batch:
            # Download image to memory if available
            image_bytes = None
            if product.get("last_image_url"):
                image_bytes = self._download_image_to_memory(product["last_image_url"])

            if image_bytes:
                # Convert to format expected by scraper_service
                # Pass image_bytes instead of image_path for in-memory processing
                processed_product = {
                    "url": product["url"],
                    "brand": product["brand"],
                    "product_name": product["name"],
                    "product_type": "shoe",  # Default for John Lobb
                    "image_bytes": image_bytes,  # In-memory image data
                    "image_url": product["last_image_url"],  # Keep URL for reference
                }
                processed_batch.append(processed_product)
            else:
                logger.warning(f"Skipping product without image: {product['url']}")

        return processed_batch

    async def scrape(
        self,
        max_products: Optional[int] = None,
        batch_callback=None,
        batch_size: int = 20,
        is_cancelled=None,
    ):
        """Main scraping function with real-time batch processing.

        Args:
            max_products: Maximum number of products to scrape
            batch_callback: Async function to call with each batch of products
            batch_size: Number of products to collect before calling batch_callback
            is_cancelled: Optional function to check if scraping should be cancelled
        """
        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

        logger.info(f"Starting John Lobb scraper for {self.base_url}")
        self.start_time = datetime.now()
        logger.info("Using in-memory image processing (no temp files)")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT)
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

            try:
                # Step 1: Navigate to listing page and get product links
                logger.info("Step 1: Fetching product links from listing page...")
                for attempt in range(MAX_RETRIES):
                    try:
                        await page.goto(
                            self.base_url,
                            wait_until="networkidle",
                            timeout=NAVIGATION_TIMEOUT,
                        )
                        # Wait additional time for JavaScript to render dynamically loaded content
                        await asyncio.sleep(3)
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

                # Extract product links from listing page
                self.product_links = await self.get_product_links_from_listing(page)

                if not self.product_links:
                    logger.error("No product links found")
                    return

                # Limit products if specified
                urls_to_scrape = (
                    self.product_links[:max_products]
                    if max_products
                    else self.product_links
                )

                # Step 2: Scrape each product with batch processing
                logger.info(f"\nStep 2: Scraping {len(urls_to_scrape)} products...")
                current_batch = []
                should_stop = False

                for idx, product_url in enumerate(urls_to_scrape, 1):
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

                    logger.info(f"\n[{idx}/{len(urls_to_scrape)}] Scraping product...")
                    details = await self.extract_product_details(page, product_url)

                    if details:
                        # Log scraped product details
                        logger.info(f"✅ Scraped Product #{idx}:")
                        logger.info(f"   Brand: {details.get('brand', 'N/A')}")
                        logger.info(f"   Product Name: {details.get('name', 'N/A')}")
                        logger.info(f"   Product URL: {details.get('url', 'N/A')}")
                        logger.info(
                            f"   Sole Image URL: {details.get('last_image_url', 'N/A')[:80] if details.get('last_image_url') else 'N/A'}..."
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
                            processed_batch = self._prepare_batch_for_processing(
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
                        processed_batch = self._prepare_batch_for_processing(
                            current_batch
                        )
                        if processed_batch:
                            await batch_callback(processed_batch)

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
        output_file = output_dir / "johnlobb_shoes.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.products, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Saved {len(self.products)} products to {output_file}")

        # Save failed URLs
        if self.failed_urls:
            failed_file = output_dir / "johnlobb_failed_urls.txt"
            with open(failed_file, "w", encoding="utf-8") as f:
                f.write("\n".join(self.failed_urls))
            logger.info(f"✓ Saved {len(self.failed_urls)} failed URLs to {failed_file}")

        # Save summary
        summary_file = output_dir / "johnlobb_summary.json"
        summary = {
            "total_products": len(self.products),
            "failed_products": len(self.failed_urls),
            "success_rate": (
                f"{100 * len(self.products) / (len(self.products) + len(self.failed_urls)):.1f}%"
                if (len(self.products) + len(self.failed_urls)) > 0
                else "N/A"
            ),
            "products_with_image": sum(
                1 for p in self.products if p.get("last_image_url")
            ),
            "image_rate": (
                f"{100 * sum(1 for p in self.products if p.get('last_image_url')) / len(self.products):.1f}%"
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
        print("JOHN LOBB SCRAPER - SUMMARY")
        print("=" * 120)
        print(f"\nTotal Products Scraped: {len(self.products)}")
        print(f"Failed URLs: {len(self.failed_urls)}")
        image_count = sum(1 for p in self.products if p.get("last_image_url"))
        print(f"Products with Images: {image_count}/{len(self.products)}")

        if self.products:
            print("\nScraped Products:")
            for idx, p in enumerate(self.products, 1):
                print(f"\n{idx}. {p['brand']} - {p['name']}")
                print(f"   URL: {p['url']}")
                if p.get("last_image_url"):
                    print(f"   ✓ Image: {p['last_image_url']}")
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
    scraper = JohnLobbScraper(base_url="https://www.johnlobb.com/en_gb/shoes/shoes-all")

    try:
        # Scrape products
        # Set max_products=5 for testing, None for all
        await scraper.scrape(max_products=None)

        # Save results
        scraper.save_results()

        # Print summary
        scraper.print_summary()

    except Exception as e:
        logger.error(f"Scraper failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
