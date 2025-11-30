"""
Decathlon footwear scraper using Playwright.
Scrapes product links, images, and detects sole images using CLIP model.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, Optional
from pathlib import Path

from playwright.async_api import async_playwright, Page

# Add parent directory to path
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
BASE_URL = "https://www.decathlon.com/collections/footwear"
OUTPUT_DIR = Path("../../data")
OUTPUT_FILE = OUTPUT_DIR / "decathlon_products.json"
NAVIGATION_TIMEOUT = 60000  # Increased to 60s for slow networks
SCROLL_PAUSE_TIME = 0.5
IMAGE_LOAD_TIMEOUT = 5000


class DecathlonScraper(BatchProcessingMixin):
    def __init__(self):
        """Initialize the scraper with CLIP model for sole detection."""
        self.products = []
        self.failed_urls = []
        logger.info("Initializing CLIP sole detector model...")
        self.clip_model = SoleDetectorCLIP()
        logger.info("✓ CLIP model loaded")

    def is_sole_image(self, image_path: str) -> tuple[bool, float, dict]:
        """
        Download image and check if it's a sole image using CLIP model.

        Args:
            image_path: URL of the image (may start with //)

        Returns:
            Tuple of (is_sole: bool, confidence: float, scores: dict)
        """
        try:
            # Ensure proper URL format
            if image_path.startswith("//"):
                image_url = f"https:{image_path}"
            elif not image_path.startswith("http"):
                image_url = f"https://www.decathlon.com{image_path}"
            else:
                image_url = image_path

            logger.debug(f"Downloading image from {image_url[:100]}...")

            # Download image
            import requests

            response = requests.get(image_url, timeout=10, stream=True)
            response.raise_for_status()

            from PIL import Image
            from io import BytesIO

            image = Image.open(BytesIO(response.content))

            # Crop left half for sole detection
            width = image.width
            half_width = width // 2
            cropped_image = image.crop((0, 0, half_width, image.height))

            # Run CLIP model
            is_sole, confidence, scores = self.clip_model.is_sole(cropped_image)

            logger.debug(
                f"Image sole detection: is_sole={is_sole}, confidence={confidence:.2f}"
            )

            return is_sole, confidence, scores

        except Exception as e:
            logger.warning(
                f"⚠️ Failed to download/process image {image_path[:100]}: {e}"
            )
            return False, 0.0, {}

    async def get_product_links(self, page: Page) -> list[str]:
        """
        Extract all product links from the footwear collection page.
        Handles infinite scroll by scrolling to bottom to load all products.

        Returns:
            List of product URLs
        """
        logger.info("Step 2: Extracting product links...")

        # Wait for product grid to load
        grid_locator = page.locator("#product-grid")
        await grid_locator.wait_for(state="visible", timeout=NAVIGATION_TIMEOUT)
        logger.debug("✓ Product grid found")

        product_links = set()  # Use set to avoid duplicates
        previous_count = 0

        # Scroll to load all products
        logger.info("⏳ Scrolling to load all products...")
        while True:
            # Get all current product links
            product_items = await page.locator("#product-grid li.grid__item").all()
            logger.debug(f"Found {len(product_items)} product items")

            # Extract links from each item
            for item in product_items:
                try:
                    heading = item.locator("h3.card__heading").first
                    link_element = heading.locator("a").first

                    link = await link_element.get_attribute("href")
                    if link:
                        # Convert relative URL to absolute
                        if link.startswith("/"):
                            link = f"https://www.decathlon.com{link}"
                        product_links.add(link)
                except Exception as e:
                    logger.debug(f"⚠️ Could not extract link from item: {e}")

            # Check if we loaded more products
            current_count = len(product_links)
            if current_count == previous_count:
                logger.debug(
                    f"No new products found after scroll (total: {current_count})"
                )
                break

            previous_count = current_count
            logger.debug(f"Loaded {current_count} unique products, scrolling more...")

            # Scroll to bottom to trigger lazy loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(SCROLL_PAUSE_TIME)

        logger.info(f"✓ Extracted {len(product_links)} product links (0 errors)")
        return sorted(list(product_links))

    async def extract_product_details(
        self, page: Page, url: str, product_index: int, total_products: int
    ) -> Optional[Dict[str, Any]]:
        """
        Extract product details from a product page.
        Includes name, images, and sole detection.

        Args:
            page: Playwright page object
            url: Product URL
            product_index: Current product index
            total_products: Total products to scrape

        Returns:
            Dictionary with product details or None if extraction failed
        """
        try:
            logger.info(f"\n  Product {product_index}/{total_products}: Scraping...")

            # Navigate to product page
            logger.debug("⏳ Navigating to product page...")
            await page.goto(
                url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
            )
            await asyncio.sleep(1)

            product_name = None
            image_urls = []

            # Get product name
            try:
                title_locator = page.locator(".product__title").first
                await title_locator.wait_for(state="visible", timeout=5000)
                product_name = await title_locator.text_content()
                product_name = product_name.strip() if product_name else "Unknown"
                logger.debug(f"Product name: {product_name}")
            except Exception as e:
                logger.warning(f"⚠️ Could not extract product name: {e}")
                product_name = "Unknown"

            # Get product images
            try:
                media_list = page.locator(".product__media-list").first
                await media_list.wait_for(state="visible", timeout=5000)
                logger.debug("✓ Product media list found")

                # Scroll media list into view
                await media_list.evaluate("el => el.scrollIntoView(true)")
                await asyncio.sleep(1)

                # Get all image items
                image_items = await media_list.locator("li").all()
                total_images = len(image_items)
                logger.info(f"📸 Found {total_images} images for product")

                # Scroll through all images to trigger lazy loading
                logger.debug("⏳ Scrolling through images to load them...")
                for idx in range(total_images):
                    try:
                        # Get current image item
                        if idx < len(image_items):
                            item = image_items[idx]
                            await item.evaluate("el => el.scrollIntoView(true)")
                            await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.debug(f"⚠️ Could not scroll image {idx}: {e}")

                logger.info("✓ Image loading process complete")

                # Extract image URLs using JavaScript
                logger.debug("⏳ Extracting image URLs...")
                image_data = await media_list.evaluate("""
                (container) => {
                    const images = [];
                    const imgElements = container.querySelectorAll('img');
                    
                    imgElements.forEach((img) => {
                        let url = null;
                        let source = null;
                        
                        // Try src attribute first
                        let src = img.getAttribute('src') || '';
                        if (src && (src.startsWith('http') || src.startsWith('//'))) {
                            url = src;
                            source = 'src';
                        }
                        
                        // Try srcset if src didn't work
                        if (!url) {
                            const srcset = img.getAttribute('srcset') || '';
                            if (srcset) {
                                try {
                                    // Extract all URLs from srcset
                                    const urlRegex = /(https?:\\/\\/[^,\\s]+|\\/\\/[^,\\s]+)/g;
                                    const matches = [];
                                    let m;
                                    while ((m = urlRegex.exec(srcset)) !== null) {
                                        matches.push(m[0]);
                                    }
                                    if (matches.length) {
                                        // Take highest resolution (last one)
                                        url = matches[matches.length - 1];
                                        source = 'srcset';
                                    }
                                } catch (e) {
                                    // ignore
                                }
                            }
                        }
                        
                        // Try data-src as fallback
                        if (!url) {
                            const data_src = img.getAttribute('data-src') || '';
                            if (data_src && (data_src.startsWith('http') || data_src.startsWith('//'))) {
                                url = data_src;
                                source = 'data-src';
                            }
                        }
                        
                        if (url && !url.includes('data:')) {
                            // Normalize: convert HTML entities and protocol-relative URLs
                            url = url.replace(/&amp;/g, '&');
                            if (url.startsWith('//')) {
                                url = 'https:' + url;
                            }
                            images.push({ url: url, source: source });
                        }
                    });
                    
                    return images;
                }
                """)

                logger.debug(f"✓ JavaScript query returned {len(image_data)} images")

                # Process extracted image data
                for idx, img_info in enumerate(image_data, 1):
                    url = img_info.get("url", "")
                    source = img_info.get("source", "unknown")

                    if url:
                        image_urls.append(url)
                        logger.info(f"Image {idx}: Extracted from {source}")
                        logger.info(f"✓ Image {idx}: {url[:100]}...")

            except Exception as e:
                logger.error(f"❌ Could not extract images: {e}")

            logger.info(
                f"✅ Extracted {len(image_urls)} image URLs from {total_images} found"
            )

            # Check images with CLIP model
            if not image_urls:
                logger.warning("⚠️ No images were extracted - skipping product")
                return None

            checked_images = []
            sole_image_url = None
            highest_confidence = 0

            for idx, img_url in enumerate(image_urls, 1):
                logger.debug(
                    f"Checking image {idx}/{len(image_urls)} with CLIP model..."
                )

                is_sole, confidence, scores = self.is_sole_image(img_url)

                # Get top sole and non-sole scores
                sole_scores = {
                    k: v
                    for k, v in scores.items()
                    if any(
                        x in k for x in ["sole", "zigzag", "waffle", "tread", "lugs"]
                    )
                }
                non_sole_scores = {
                    k: v
                    for k, v in scores.items()
                    if any(x in k for x in ["side", "front", "upper", "leather"])
                }

                top_sole = (
                    max(sole_scores.items(), key=lambda x: x[1])[0]
                    if sole_scores
                    else "N/A"
                )
                top_non_sole = (
                    max(non_sole_scores.items(), key=lambda x: x[1])[0]
                    if non_sole_scores
                    else "N/A"
                )

                if is_sole:
                    logger.info(
                        f"  ✓ Image {idx}: IS A SOLE (conf={confidence:.2f}) | Top sole: {top_sole}({scores.get(top_sole, 0):.3f}) | Top non-sole: {top_non_sole}({scores.get(top_non_sole, 0):.3f})"
                    )
                    if confidence > highest_confidence:
                        highest_confidence = confidence
                        sole_image_url = img_url
                else:
                    logger.info(
                        f"  ✗ Image {idx}: Not a sole (conf={confidence:.2f}) | Top sole: {top_sole}({scores.get(top_sole, 0):.3f}) | Top non-sole: {top_non_sole}({scores.get(top_non_sole, 0):.3f})"
                    )

                checked_images.append(
                    {
                        "url": img_url,
                        "is_sole": is_sole,
                        "confidence": confidence,
                        "scores": scores,
                    }
                )

            # Select sole image or best available image
            if sole_image_url:
                logger.info(
                    f"✅ Selected sole image with confidence {highest_confidence:.2f}"
                )
                selected_image = sole_image_url
            elif checked_images:
                # Fallback: select highest confidence image
                selected_image = max(checked_images, key=lambda x: x["confidence"])[
                    "url"
                ]
                logger.warning(
                    f"⚠️ No sole images detected - selecting highest confidence image ({max([x['confidence'] for x in checked_images]):.2f})"
                )
            else:
                logger.warning("⚠️ No images could be checked - skipping product")
                return None

            return {
                "brand": "Decathlon",
                "product_name": product_name,
                "product_url": url,
                "image_url": selected_image,
                "all_images": checked_images,
                "total_images_found": len(image_urls),
            }

        except Exception as e:
            logger.error(f"❌ Failed to extract details from {url}: {e}", exc_info=True)
            return None

    async def scrape(
        self, batch_callback=None, batch_size: int = 20, is_cancelled=None
    ) -> Dict[str, Any]:
        """Main scraping method with batch processing support.

        Args:
            batch_callback: Async function to call with each batch of products
            batch_size: Number of products to collect before calling batch_callback
            is_cancelled: Optional function to check if scraping should be cancelled
        """
        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

        logger.info("Starting Decathlon scraper")
        logger.info(f"Base URL: {BASE_URL}")
        if batch_callback:
            logger.info("Using in-memory image processing (no temp files)")

        async with async_playwright() as p:
            logger.info("Step 0: Launching browser...")
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

            try:
                page = await browser.new_page()

                logger.info("Step 1: Navigating to base URL...")
                await page.goto(
                    BASE_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
                )
                await asyncio.sleep(3)  # Extra wait for JavaScript rendering

                # Close dialogs that appear on page load
                logger.debug("⏳ Closing popup dialogs...")
                try:
                    # Close first dialog with class "spicegems_cr_main"
                    spice_dialog = page.locator(".spicegems_cr_main").first
                    if await spice_dialog.count() > 0:
                        try:
                            # Try to find and click close button inside this dialog
                            close_btn = spice_dialog.locator(
                                "button, [role='button'], .close, [aria-label='close']"
                            ).first
                            if await close_btn.count() > 0:
                                await close_btn.click(timeout=2000)
                                logger.debug("✓ Closed spicegems dialog")
                            else:
                                # If no close button found, try to click the dialog itself or escape
                                await page.keyboard.press("Escape")
                                logger.debug("✓ Closed spicegems dialog (via Escape)")
                        except Exception:
                            pass
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.debug(f"⚠️ Could not close spicegems dialog: {e}")

                try:
                    # Close second dialog with class "needsclick"
                    needs_click = page.locator(".needsclick").first
                    if await needs_click.count() > 0:
                        try:
                            # Try to find and click close button inside this dialog
                            close_btn = needs_click.locator(
                                "button, [role='button'], .close, [aria-label='close']"
                            ).first
                            if await close_btn.count() > 0:
                                await close_btn.click(timeout=2000)
                                logger.debug("✓ Closed needsclick dialog")
                            else:
                                # If no close button found, try Escape key
                                await page.keyboard.press("Escape")
                                logger.debug("✓ Closed needsclick dialog (via Escape)")
                        except Exception:
                            pass
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.debug(f"⚠️ Could not close needsclick dialog: {e}")

                await asyncio.sleep(1)

                # Extract product links
                product_links = await self.get_product_links(page)

                if not product_links:
                    logger.warning("⚠️ No products found")
                    return {"status": "error", "message": "No products found"}

                logger.info(f"✓ Found {len(product_links)} products")

                # Scrape each product with batch processing
                logger.info("Step 3: Scraping product details...")
                products = []
                current_batch = []
                should_stop = False

                for idx, product_url in enumerate(product_links, 1):
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

                    try:
                        product_data = await self.extract_product_details(
                            page, product_url, idx, len(product_links)
                        )
                        if product_data:
                            # Log scraped product details
                            logger.info(f"✅ Scraped Product #{idx}:")
                            logger.info(f"   Brand: {product_data.get('brand', 'N/A')}")
                            logger.info(
                                f"   Product Name: {product_data.get('product_name', 'N/A')}"
                            )
                            logger.info(
                                f"   Product URL: {product_data.get('product_url', 'N/A')}"
                            )
                            logger.info(
                                f"   Sole Image URL: {product_data.get('image_url', 'N/A')[:80] if product_data.get('image_url') else 'N/A'}..."
                            )
                            logger.info(
                                f"   Sole Confidence: {product_data.get('sole_confidence', 0):.3f}"
                            )

                            products.append(product_data)
                            self.products.append(product_data)
                            current_batch.append(product_data)

                            # Process batch when size is reached
                            if len(current_batch) >= batch_size and batch_callback:
                                should_continue = (
                                    await self._process_batch_with_callback(
                                        current_batch,
                                        batch_callback,
                                        brand_field="brand",
                                        name_field="product_name",
                                        url_field="product_url",
                                        image_url_field="image_url",
                                    )
                                )

                                if not should_continue:
                                    should_stop = True

                                current_batch = []  # Reset batch

                        logger.info("")
                    except Exception as e:
                        logger.error(
                            f"Error scraping product {idx}: {e}", exc_info=True
                        )

                # Process remaining items in final batch
                if current_batch and batch_callback and not should_stop:
                    logger.info(
                        f"Processing final batch of {len(current_batch)} products..."
                    )
                    await self._process_batch_with_callback(
                        current_batch,
                        batch_callback,
                        brand_field="brand",
                        name_field="product_name",
                        url_field="product_url",
                        image_url_field="image_url",
                    )

                logger.info(f"\n{'=' * 60}")
                logger.info(
                    f"Scraping complete: {len(products)}/{len(product_links)} products"
                )
                logger.info(f"{'=' * 60}\n")

                # Save results
                output_data = {
                    "total_products_found": len(product_links),
                    "total_products_scraped": len(products),
                    "products": products,
                }

                # Ensure output directory exists
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

                with open(OUTPUT_FILE, "w") as f:
                    json.dump(output_data, f, indent=2)

                logger.info(f"✓ Results saved to {OUTPUT_FILE}")

                return {
                    "status": "success",
                    "total_products_found": len(product_links),
                    "total_products_scraped": len(products),
                    "output_file": str(OUTPUT_FILE),
                }

            finally:
                await browser.close()


async def main():
    """Entry point."""
    scraper = DecathlonScraper()
    result = await scraper.scrape()
    logger.info(f"Final result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
