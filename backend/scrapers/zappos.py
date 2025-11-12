import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Optional

import requests
from PIL import Image
from bs4 import BeautifulSoup
from playwright.async_api import Browser, Page, async_playwright

# Setup imports for CLIP model
sys.path.insert(0, str(Path(__file__).parent.parent))
from models.clip_model import SoleDetectorCLIP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ZapposScraper:
    def __init__(self, max_pages: int = 1):
        self.base_url = "https://www.zappos.com/men-shoes/.zso?t=men%20shoes"
        self.max_pages = max_pages
        self.clip = SoleDetectorCLIP()
        logger.info(
            f"✅ ZapposScraper initialized with CLIP model (max_pages={max_pages})"
        )

    async def run(self):
        """Main scraper execution"""
        logger.info(f"🚀 Starting Zappos scraper for: {self.base_url}")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            try:
                await self.scrape_products(browser, page)
            finally:
                await browser.close()

    async def scrape_products(self, browser: Browser, page: Page):
        """Main scraping workflow"""
        try:
            # Navigate to the page
            logger.info("📄 Loading Zappos men's shoes page...")
            await page.goto(
                self.base_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            # Wait for products container to be visible
            logger.info("⏳ Waiting for products to load...")
            try:
                await page.locator('xpath=//*[@id="products"]').wait_for(timeout=15000)
            except Exception as e:
                logger.warning(f"Products selector not found immediately: {e}")

            # Scroll to load all products dynamically
            product_links = await self.load_all_products(page)
            logger.info(f"📦 Total products found: {len(product_links)}")

            if not product_links:
                logger.warning("❌ No product links found!")
                return

            # Process each product
            for idx, link in enumerate(product_links, 1):
                logger.info(f"\n{'=' * 80}")
                logger.info(f"Processing product {idx}/{len(product_links)}")
                logger.info(f"{'=' * 80}")
                try:
                    await self.process_product(browser, link)
                except Exception as e:
                    logger.error(f"Failed to process product {link}: {e}")

        except Exception as e:
            logger.error(f"Error in scrape_products: {e}")

    async def load_all_products(self, page: Page) -> List[str]:
        """
        Scrape products using pagination (Selenium-inspired with Playwright).
        - Navigate through pages using next button href
        - Scroll to bottom to load lazy content
        - Parse with BeautifulSoup to find article.pZ-z containers
        - Extract first <a> tag with href from each article
        - Filter for /p/ product links
        """
        logger.info("🔄 Loading products using pagination...")
        product_links: List[str] = []
        current_page = 1
        next_page_url = self.base_url
        max_pages = self.max_pages

        while next_page_url and current_page <= max_pages:
            logger.info(f"📄 Scraping page {current_page}: {next_page_url}")

            # Navigate to the page
            try:
                await page.goto(
                    next_page_url, wait_until="domcontentloaded", timeout=60000
                )
            except Exception as e:
                logger.error(f"Failed to navigate to {next_page_url}: {e}")
                break

            # Wait for products container
            try:
                await page.locator('xpath=//*[@id="products"]').wait_for(timeout=15000)
            except Exception as e:
                logger.warning(f"Products container not found: {e}")
                break

            # Scroll to bottom to load lazy-loaded content
            logger.debug("↓ Scrolling to bottom to load lazy content...")
            try:
                last_height = await page.evaluate("document.body.scrollHeight")
                scroll_count = 0
                while True:
                    await page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    await asyncio.sleep(1.0)
                    new_height = await page.evaluate("document.body.scrollHeight")
                    scroll_count += 1
                    if new_height == last_height or scroll_count > 20:
                        logger.debug(f"  ✓ Reached bottom after {scroll_count} scrolls")
                        break
                    last_height = new_height
            except Exception as e:
                logger.debug(f"Error during scroll: {e}")

            # Parse page source with BeautifulSoup
            page_links_count_before = len(product_links)
            try:
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                # Find all article containers with class pZ-z
                articles = soup.select("article.pZ-z")
                logger.debug(f"Found {len(articles)} article.pZ-z containers")

                for article in articles:
                    try:
                        # Find first <a> tag with href inside the article
                        link_element = article.find("a", href=True)
                        if link_element:
                            href = link_element.get("href")
                            # Only accept product links starting with /p/
                            if href and href.startswith("/p/"):
                                full_url = f"https://www.zappos.com{href}"
                                if full_url not in product_links:
                                    product_links.append(full_url)
                    except Exception as e:
                        logger.debug(f"Error processing article: {e}")

                page_links_added = len(product_links) - page_links_count_before
                logger.info(
                    f"  → Found {page_links_added} unique product links on page {current_page}"
                )
                logger.info(f"  ✓ Total: {len(product_links)} product links so far")

            except Exception as e:
                logger.error(f"Error parsing page content: {e}")
                break

            # Find next page button and get href
            try:
                next_button = await page.query_selector('a[rel="next"]')
                if next_button:
                    next_page_url = await next_button.get_attribute("href")
                    if next_page_url:
                        # Make absolute URL if needed
                        if not next_page_url.startswith("http"):
                            next_page_url = f"https://www.zappos.com{next_page_url}"
                        current_page += 1
                        logger.info("➡️ Found next page")
                        await asyncio.sleep(2.0)  # Be polite
                    else:
                        logger.info("🔚 Next button has no href — reached last page")
                        next_page_url = None
                else:
                    logger.info("🔚 No 'Next' button found. Ending pagination.")
                    next_page_url = None

            except Exception as e:
                logger.debug(f"Error finding next button: {e}")
                logger.info("🔚 Pagination ended")
                next_page_url = None

        logger.info(
            f"✅ Finished pagination: {len(product_links)} total links collected"
        )
        return product_links

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

    async def analyze_product_images(self, page: Page, product_name: str):
        """
        Find product images from the specific image carousel (div.p0-z)
        and analyze them with CLIP to identify sole images
        """
        try:
            # Wait for the image container (div.p0-z)
            try:
                await page.wait_for_selector("div.p0-z", timeout=10000)
            except Exception:
                logger.debug("Image container (div.p0-z) not found on page")
                return

            # Get all img.Lo-z images from the carousel
            images = await page.query_selector_all("div.p0-z img.Lo-z")
            logger.info(f"🖼️  Found {len(images)} product images in carousel")

            if not images:
                logger.warning("No images found in carousel")
                return

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

            # Analyze images with CLIP
            if image_urls:
                await self.detect_sole_images(image_urls, product_name)
            else:
                logger.warning("No valid image URLs to analyze")

        except Exception as e:
            logger.error(f"Error analyzing product images: {e}")

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

    async def process_product(self, browser: Browser, product_url: str):
        """
        Process individual product:
        1. Navigate to product page
        2. Extract product name
        3. Extract and analyze product images for soles
        """
        page = await browser.new_page()
        try:
            logger.info(f"🔗 Loading product: {product_url}")

            # Navigate to product page
            await page.goto(
                product_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            # Extract product name
            product_name = await self.extract_product_name(page)
            logger.info(f"📦 Product Name: {product_name}")

            # Extract and analyze images
            await self.analyze_product_images(page, product_name)

        except Exception as e:
            logger.error(f"Error processing product {product_url}: {e}")
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
    # Set max_pages=1 for testing, increase for production
    scraper = ZapposScraper(max_pages=1)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
