import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Optional, Dict

import requests
from PIL import Image
from playwright.async_api import Browser, Page, async_playwright

# Setup imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from ml_models.clip_model import SoleDetectorCLIP
from scrapers.base_scraper_mixin import BatchProcessingMixin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ZapposScraper(BatchProcessingMixin):
    def __init__(self, max_pages: int = None):
        self.base_url = "https://www.zappos.com/men-shoes/.zso?t=men%20shoes"
        self.max_pages = max_pages  # None = all pages (production mode)
        self.clip = SoleDetectorCLIP()
        self.products = []  # Store scraped products
        logger.info(
            f"✅ ZapposScraper initialized with CLIP model (max_pages={max_pages or 'unlimited'})"
        )

    async def run(self, batch_callback=None, batch_size: int = 20, is_cancelled=None):
        """Main scraper execution with batch processing support

        Args:
            batch_callback: Async function to call with each batch of products
            batch_size: Number of products to collect before calling batch_callback
            is_cancelled: Callable that returns True if scraper should stop
        """
        logger.info(f"🚀 Starting Zappos scraper for: {self.base_url}")
        if batch_callback:
            logger.info("Using in-memory image processing (no temp files)")
        if is_cancelled:
            logger.info("Cancellation support enabled")

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
            page = await browser.new_page()
            try:
                await self.scrape_products(
                    browser, page, batch_callback, batch_size, is_cancelled
                )
            finally:
                await browser.close()

    async def scrape_products(
        self,
        browser: Browser,
        page: Page,
        batch_callback=None,
        batch_size: int = 20,
        is_cancelled=None,
    ):
        """Main scraping workflow with page-by-page batch processing"""
        try:
            # Navigate to the first page
            logger.info("📄 Loading Zappos men's shoes page...")
            await page.goto(
                self.base_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            # Extra wait for JavaScript to render products
            await asyncio.sleep(3)

            # Wait for products container to be visible
            logger.info("⏳ Waiting for products to load...")
            try:
                await page.locator('xpath=//*[@id="products"]').wait_for(timeout=15000)
                logger.debug("✓ Products container loaded")
            except Exception as e:
                logger.warning(f"Products container not found: {e}")
                return

            # Process products page by page
            current_batch = []
            should_stop = False
            current_page = 1
            next_page_url = self.base_url
            global_idx = 1

            while (
                next_page_url
                and (self.max_pages is None or current_page <= self.max_pages)
                and not should_stop
            ):
                # Check for cancellation at page boundary
                if is_cancelled and is_cancelled():
                    logger.warning(
                        "🛑 Cancellation detected - stopping scraper immediately"
                    )
                    should_stop = True
                    break

                logger.info(f"\n📄 Scraping page {current_page}...")

                # If not first page, navigate to it
                if current_page > 1:
                    try:
                        await page.goto(
                            next_page_url, wait_until="domcontentloaded", timeout=60000
                        )
                        await asyncio.sleep(3)
                        await page.locator('xpath=//*[@id="products"]').wait_for(
                            timeout=15000
                        )
                    except Exception as e:
                        logger.error(f"Failed to navigate to page {current_page}: {e}")
                        break

                # Scroll to load lazy content on current page
                await self._scroll_page(page)

                # Extract product links from current page
                page_links = await self._extract_links_from_current_page(page)
                logger.info(
                    f"🔗 Page {current_page}: Found {len(page_links)} product links"
                )

                if not page_links:
                    logger.warning(f"No product links found on page {current_page}")
                    break

                # Process each product on current page
                for local_idx, link in enumerate(page_links, 1):
                    # Fast cancellation check before each product
                    if should_stop or (is_cancelled and is_cancelled()):
                        if is_cancelled and is_cancelled():
                            logger.warning(
                                "🛑 Cancellation detected during product loop"
                            )
                        should_stop = True
                        break

                    try:
                        logger.info(
                            f"\n  Product {global_idx} (Page {current_page}:{local_idx}/{len(page_links)}): Scraping..."
                        )
                        product_data = await self.process_product(browser, link)

                        if product_data and product_data.get("image_url"):
                            # Log scraped product details
                            logger.info(f"✅ Scraped Product #{global_idx}:")
                            logger.info(f"   Brand: {product_data.get('brand', 'N/A')}")
                            logger.info(
                                f"   Product Name: {product_data.get('product_name', 'N/A')}"
                            )
                            logger.info(
                                f"   Product URL: {product_data.get('product_url', 'N/A')}"
                            )
                            sole_url = product_data.get("image_url", "")
                            logger.info(
                                f"   Sole Image URL: {sole_url[:80] + '...' if len(sole_url) > 80 else sole_url}"
                            )
                            logger.info(
                                f"   Sole Confidence: {product_data.get('sole_confidence', 0.0):.3f}"
                            )
                            logger.info(
                                f"   Total Images Found: {product_data.get('total_images', 0)}"
                            )

                            self.products.append(product_data)
                            current_batch.append(product_data)

                            # Process batch when size is reached
                            if len(current_batch) >= batch_size and batch_callback:
                                logger.info(
                                    f"Processing batch of {len(current_batch)} products..."
                                )
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
                                    logger.info(
                                        "Batch callback returned False, stopping"
                                    )
                                    should_stop = True

                                current_batch = []  # Reset batch

                        global_idx += 1

                    except Exception as e:
                        logger.error(f"Failed to process product {link}: {e}")
                        global_idx += 1
                        continue

                # Find next page button after processing current page
                if not should_stop:
                    next_page_url = await self._find_next_page(page)
                    if next_page_url:
                        current_page += 1
                        logger.info("➡️ Moving to next page...")
                        await asyncio.sleep(2)
                    else:
                        logger.info("🔚 No more pages to scrape")
                        break

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

            logger.info(f"✅ Scraped {len(self.products)} products with sole images")

        except Exception as e:
            logger.error(f"Error in scrape_products: {e}")

    async def _scroll_page(self, page: Page):
        """Scroll page to load lazy-loaded content"""
        logger.debug("↓ Scrolling to load lazy content...")
        try:
            last_height = await page.evaluate("document.body.scrollHeight")
            scroll_count = 0
            while True:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await asyncio.sleep(1.0)
                new_height = await page.evaluate("document.body.scrollHeight")
                scroll_count += 1
                if new_height == last_height or scroll_count > 20:
                    logger.debug(f"  ✓ Reached bottom after {scroll_count} scrolls")
                    break
                last_height = new_height
        except Exception as e:
            logger.debug(f"Error during scroll: {e}")

    async def _extract_links_from_current_page(self, page: Page) -> List[str]:
        """Extract product links from the current page"""
        product_links = []
        try:
            # Find all article elements within the products container
            articles = await page.locator('xpath=//*[@id="products"]//article').all()
            logger.debug(
                f"Found {len(articles)} article elements in products container"
            )

            for article in articles:
                try:
                    # Find first link in the article
                    link = await article.locator("a").first.get_attribute("href")
                    if link and link.startswith("/p/"):
                        full_url = f"https://www.zappos.com{link}"
                        if full_url not in product_links:
                            product_links.append(full_url)
                except Exception as e:
                    logger.debug(f"Error extracting link from article: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error extracting product links: {e}")

        return product_links

    async def _find_next_page(self, page: Page) -> Optional[str]:
        """Find next page URL from pagination"""
        try:
            # Look for Next link with rel="next" in the pagination container
            next_button = await page.locator(
                'xpath=//*[@id="searchPagination"]//a[@rel="next"]'
            ).first

            # Check if Next button exists and is not disabled
            if await next_button.count() > 0:
                # Check if it's visible (not disabled/invisible)
                classes = await next_button.get_attribute("class")
                if classes and "invisible" in classes:
                    logger.debug("Next button is disabled — reached last page")
                    return None
                else:
                    next_page_url = await next_button.get_attribute("href")
                    if next_page_url:
                        # Make absolute URL if needed
                        if not next_page_url.startswith("http"):
                            next_page_url = f"https://www.zappos.com{next_page_url}"
                        return next_page_url
            return None

        except Exception as e:
            logger.debug(f"Error finding next button: {e}")
            return None

    async def extract_product_name(self, page: Page) -> str:
        """Extract product name from page"""
        try:
            # Try to find product name in h1 tag
            h1 = await page.query_selector("h1")
            if h1:
                name = await h1.text_content()
                return name.strip() if name else "Unknown Product"

            # Fallback: try span.productTitle
            title_span = await page.query_selector("span.productTitle")
            if title_span:
                name = await title_span.text_content()
                return name.strip() if name else "Unknown Product"

            return "Unknown Product"
        except Exception as e:
            logger.debug(f"Error extracting product name: {e}")
            return "Unknown Product"

    async def extract_brand(self, page: Page) -> str:
        """Extract brand from page"""
        try:
            # Try to find brand in meta tag
            brand_meta = await page.query_selector('meta[property="og:brand"]')
            if brand_meta:
                brand = await brand_meta.get_attribute("content")
                if brand:
                    return brand.strip()

            # Try itemprop="brand"
            brand_elem = await page.query_selector('[itemprop="brand"]')
            if brand_elem:
                brand = await brand_elem.text_content()
                if brand:
                    return brand.strip()

            return "Unknown"
        except Exception as e:
            logger.debug(f"Error extracting brand: {e}")
            return "Unknown"

    async def extract_product_image_urls(self, page: Page) -> List[str]:
        """Extract product image URLs from the page using XPath for stage container"""
        image_urls: List[str] = []

        try:
            # Wait for the stage container to load
            try:
                await page.locator('xpath=//*[@id="stage"]').wait_for(timeout=10000)
                logger.debug("✓ Stage container loaded")
            except Exception as e:
                logger.debug(f"Stage container not found: {e}")
                return []

            # Wait a bit for images to render
            await asyncio.sleep(2)

            # Strategy 1: Get images with itemprop="image" inside stage div
            try:
                images = await page.locator(
                    'xpath=//*[@id="stage"]//img[@itemprop="image"]'
                ).all()
                logger.debug(
                    f"Found {len(images)} images with itemprop='image' in stage"
                )

                for img in images:
                    try:
                        # Try src first
                        src = await img.get_attribute("src")
                        if not src:
                            # Try data-src for lazy-loaded images
                            src = await img.get_attribute("data-src")

                        if src and src.startswith("http"):
                            # Get the higher resolution version from srcset if available
                            srcset = await img.get_attribute("srcset")
                            if srcset:
                                # Parse srcset to get highest resolution image
                                # Format: "url1 2x, url2 1x" or "url1 1840w, url2 920w"
                                srcset_parts = srcset.split(",")
                                best_src = src
                                max_resolution = 0

                                for part in srcset_parts:
                                    part = part.strip()
                                    if " " in part:
                                        url, descriptor = part.rsplit(" ", 1)
                                        url = url.strip()
                                        # Check for width descriptor (e.g., "1840w")
                                        if descriptor.endswith("w"):
                                            width = int(descriptor[:-1])
                                            if width > max_resolution:
                                                max_resolution = width
                                                best_src = url
                                        # Check for pixel density descriptor (e.g., "2x")
                                        elif descriptor == "2x":
                                            best_src = url
                                            break

                                src = best_src

                            if src not in image_urls:
                                image_urls.append(src)
                                logger.debug(f"  Added image: {src[:80]}...")
                    except Exception as e:
                        logger.debug(f"Error extracting src from image: {e}")
                        continue

                if image_urls:
                    logger.debug(
                        f"📸 Extracted {len(image_urls)} valid image URLs from stage"
                    )
                    return image_urls

            except Exception as e:
                logger.debug(f"Strategy 1 failed: {e}")

            # Strategy 2: Fallback - get all images from stage div
            if not image_urls:
                logger.debug("Fallback: Extracting all images from stage div")
                images = await page.locator('xpath=//*[@id="stage"]//img').all()
                logger.debug(f"Found {len(images)} total images in stage")

                for img in images:
                    try:
                        src = await img.get_attribute("src")
                        if not src:
                            src = await img.get_attribute("data-src")

                        if src and src.startswith("http"):
                            # Filter out tiny thumbnails
                            if not any(
                                x in src.lower()
                                for x in ["icon", "logo", "_SS40_", "_SS50_"]
                            ):
                                if src not in image_urls:
                                    image_urls.append(src)
                    except Exception:
                        continue

            logger.debug(f"📸 Extracted {len(image_urls)} valid image URLs")
            return image_urls

        except Exception as e:
            logger.error(f"Error extracting product image URLs: {e}")
            return []

    async def analyze_product_images_and_get_best(
        self, page: Page, product_name: str
    ) -> Optional[str]:
        """
        Find product images from the specific image carousel (div.p0-z)
        and analyze them with CLIP to identify the best sole image

        Returns:
            URL of the best sole image, or None if no suitable image found
        """
        try:
            # Wait for the image container (div.p0-z)
            try:
                await page.wait_for_selector("div.p0-z", timeout=10000)
            except Exception:
                logger.debug("Image container (div.p0-z) not found on page")
                return None

            # Get all img.Lo-z images from the carousel
            images = await page.query_selector_all("div.p0-z img.Lo-z")
            logger.info(f"🖼️  Found {len(images)} product images in carousel")

            if not images:
                logger.warning("No images found in carousel")
                return None

            # Extract image URLs from src attribute
            image_urls: List[str] = []
            for idx, img in enumerate(images):
                try:
                    src = await img.get_attribute("src")
                    if src and src.startswith("http"):
                        image_urls.append(src)
                        logger.debug(f"  Image {idx + 1}: {src[:80]}...")
                except Exception as e:
                    logger.debug(f"Error extracting image URL {idx}: {e}")

            logger.info(f"📸 Extracted {len(image_urls)} valid image URLs")

            # Analyze images with CLIP and return best sole URL
            if image_urls:
                return await self.detect_sole_images_and_return_best(
                    image_urls, product_name
                )
            else:
                logger.warning("No valid image URLs to analyze")
                return None

        except Exception as e:
            logger.error(f"Error analyzing product images: {e}")
            return None

    async def detect_sole_images(self, image_urls: List[str], product_name: str):
        """
        Download images and use CLIP to detect sole images
        Log sole image URLs and product name
        """
        logger.info(f"🔍 Running CLIP sole detection on {len(image_urls)} images...")

        best_sole = None
        best_sole_confidence = 0
        checked_images: List[dict] = []

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
                logger.info(
                    f"    Image {idx}: {sole_status} (confidence: {confidence:.3f})"
                )

                checked_images.append(
                    {
                        "url": img_url,
                        "is_sole": is_sole,
                        "confidence": confidence,
                        "scores": scores,
                    }
                )

                # Track best sole
                if is_sole and confidence > best_sole_confidence:
                    best_sole = img_url
                    best_sole_confidence = confidence

            except Exception as e:
                logger.debug(f"CLIP check failed for image {idx}: {e}")

        # Log results
        logger.info(f"\n📋 CLIP Analysis Summary for: {product_name}")
        logger.info(f"  Total images analyzed: {len(checked_images)}")

        if best_sole:
            logger.info("✅ Sole image found!")
            logger.info(f"      Product: {product_name}")
            logger.info(f"      Confidence: {best_sole_confidence:.3f}")
            logger.info(f"      📷 Sole URL: {best_sole}")
        else:
            # Fallback: pick highest confidence image
            if checked_images:
                fallback = max(checked_images, key=lambda x: x.get("confidence", 0))
                logger.warning("⚠️  No sole detected, using highest confidence image")
                logger.info(f"      Product: {product_name}")
                logger.info(f"      Confidence: {fallback.get('confidence', 0):.3f}")
                logger.info(f"      📷 Fallback URL: {fallback.get('url')}")
            else:
                logger.warning(f"  ⚠️  No images could be processed for {product_name}")

    async def detect_sole_images_and_return_best(
        self, image_urls: List[str], product_name: str
    ) -> tuple[Optional[str], float, int]:
        """
        Download images and use CLIP to detect sole images

        Returns:
            Tuple of (best_sole_url, confidence, total_images_checked)
        """
        logger.info(f"🔍 Running CLIP sole detection on {len(image_urls)} images...")

        best_sole = None
        best_sole_confidence = 0.0
        checked_images: List[dict] = []

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

                checked_images.append(
                    {
                        "url": img_url,
                        "is_sole": is_sole,
                        "confidence": confidence,
                        "scores": scores,
                    }
                )

                # Track best sole
                if is_sole and confidence > best_sole_confidence:
                    best_sole = img_url
                    best_sole_confidence = confidence

            except Exception as e:
                logger.debug(f"CLIP check failed for image {idx}: {e}")

        # Return best sole or fallback
        if best_sole:
            logger.info(f"✅ Sole image found! Confidence: {best_sole_confidence:.3f}")
            return best_sole, best_sole_confidence, len(checked_images)
        else:
            # Fallback: pick highest confidence image
            if checked_images:
                fallback = max(checked_images, key=lambda x: x.get("confidence", 0))
                logger.warning(
                    f"⚠️  No sole detected, using highest confidence image: {fallback.get('confidence', 0):.3f}"
                )
                return (
                    fallback.get("url"),
                    fallback.get("confidence", 0),
                    len(checked_images),
                )
            else:
                logger.warning("  ⚠️  No images could be processed")
                return None, 0.0, 0
        """
        Download images and use CLIP to detect sole images
        Returns the URL of the best sole image found
        """
        logger.info(f"🔍 Running CLIP sole detection on {len(image_urls)} images...")

        best_sole = None
        best_sole_confidence = 0
        checked_images: List[dict] = []

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
                logger.info(
                    f"    Image {idx}: {sole_status} (confidence: {confidence:.3f})"
                )

                checked_images.append(
                    {
                        "url": img_url,
                        "is_sole": is_sole,
                        "confidence": confidence,
                        "scores": scores,
                    }
                )

                # Track best sole
                if is_sole and confidence > best_sole_confidence:
                    best_sole = img_url
                    best_sole_confidence = confidence

            except Exception as e:
                logger.debug(f"CLIP check failed for image {idx}: {e}")

        # Return best result
        if best_sole:
            logger.info("✅ Sole image found!")
            logger.info(f"      Product: {product_name}")
            logger.info(f"      Confidence: {best_sole_confidence:.3f}")
            return best_sole
        else:
            # Fallback: pick highest confidence image
            if checked_images:
                fallback = max(checked_images, key=lambda x: x.get("confidence", 0))
                logger.warning("⚠️  No sole detected, using highest confidence image")
                logger.info(f"      Product: {product_name}")
                logger.info(f"      Confidence: {fallback.get('confidence', 0):.3f}")
                return fallback.get("url")
            else:
                logger.warning(f"  ⚠️  No images could be processed for {product_name}")
                return None

    async def process_product(
        self, browser: Browser, product_url: str
    ) -> Optional[Dict]:
        """
        Process individual product:
        1. Navigate to product page
        2. Extract product name and brand
        3. Extract and analyze product images for soles

        Returns:
            Dict with product data or None if failed
        """
        page = await browser.new_page()
        try:
            logger.debug(f"🔗 Loading product: {product_url}")

            # Navigate to product page
            await page.goto(
                product_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            # Extract product name
            product_name = await self.extract_product_name(page)
            logger.debug(f"📦 Product Name: {product_name}")

            # Extract brand
            brand = await self.extract_brand(page)

            # Extract image URLs
            image_urls = await self.extract_product_image_urls(page)

            if not image_urls:
                logger.warning(f"No images found for {product_name}")
                return None

            # Analyze images with CLIP to get best sole image
            (
                best_sole_url,
                confidence,
                total_images,
            ) = await self.detect_sole_images_and_return_best(image_urls, product_name)

            if best_sole_url:
                return {
                    "product_url": product_url,
                    "product_name": product_name,
                    "brand": brand or "Zappos",
                    "image_url": best_sole_url,
                    "sole_confidence": confidence,
                    "total_images": total_images,
                }
            else:
                logger.warning(f"No sole image found for {product_name}")
                return None

        except Exception as e:
            logger.error(f"Error processing product {product_url}: {e}")
            return None
        finally:
            await page.close()

    def download_image(
        self, url: str, timeout: int = 10, retries: int = 3
    ) -> Optional[Image.Image]:
        """Download image from URL and return PIL Image"""
        for attempt in range(retries):
            try:
                response = requests.get(url, timeout=timeout)
                if response.status_code == 200:
                    img = Image.open(requests.get(url, stream=True).raw).convert("RGB")
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


async def main():
    """Entry point"""
    # Production: scrape all pages (no limit)
    scraper = ZapposScraper(max_pages=None)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
