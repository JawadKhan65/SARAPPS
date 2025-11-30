"""
Clarks shoes scraper using Playwright.

Scrapes men's boots from https://www.clarks.com/en-gb/mens/mens-boots/m_boots_uk-c
Features:
  - Dynamic loading via "Load More" button clicking
  - Extracts product links from grid
  - Collects product details: name, images, links
  - Uses CLIP model to detect sole images
  - Comprehensive error handling and logging

Professional features:
  - Robust button detection and clicking with scroll-into-view
  - Waits for images to load completely
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

# Brand name
BRAND_NAME = "Clarks"

# Selectors
BASE_URL = "https://www.clarks.com/en-gb/mens/mens-boots/m_boots_uk-c"
LOAD_MORE_BUTTON_SELECTOR = '[data-testid="loadMoreButton"]'
PRODUCTS_CONTAINER_SELECTOR = '[data-testid="plpContainer"]'
PRODUCT_ITEM_SELECTOR = '[data-testid="productListItem"]'
PRODUCT_IMAGE_SELECTOR = 'img[data-testid="productListImage"]'
PRODUCT_NAME_SELECTOR = '[data-testid="productName"]'
PRODUCT_MEDIA_CONTAINER_SELECTOR = '[data-testid="productMediaContainer"]'


class ClarksScraper(BatchProcessingMixin):
    """Scraper for Clarks men's boots"""

    def __init__(self):
        self.products = []  # Store scraped products
        self.failed_urls = []
        logger.info("Initializing CLIP sole detector model...")
        self.sole_detector = SoleDetectorCLIP()
        logger.info("✓ CLIP model loaded")

    async def navigate_with_retries(
        self, page: Page, url: str, *, max_retries: int = MAX_RETRIES
    ) -> Page:
        """Navigate to a URL with retry and backoff, returning the (possibly new) page.

        Uses stricter wait on first try, then relaxes to domcontentloaded.
        Retries on common transient network errors.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                if page.is_closed():
                    try:
                        ctx = page.context  # type: ignore[attr-defined]
                        page = await ctx.new_page()
                        logger.warning("Page was closed; created a new page for retry")
                    except Exception:
                        pass

                wait_state = "networkidle" if attempt == 1 else "domcontentloaded"
                timeout = NAVIGATION_TIMEOUT + (attempt - 1) * 10000
                logger.debug(
                    f"Navigating to {url} (attempt {attempt}/{max_retries}, wait_until={wait_state})"
                )
                await page.goto(url, wait_until=wait_state, timeout=timeout)
                return page
            except Exception as e:
                msg = str(e)
                last_exc = e
                transient_markers = [
                    "ERR_ADDRESS_UNREACHABLE",
                    "ERR_NETWORK_CHANGED",
                    "ERR_CONNECTION_RESET",
                    "ERR_NAME_NOT_RESOLVED",
                    "ETIMEDOUT",
                    "ERR_TIMED_OUT",
                ]
                if any(m in msg for m in transient_markers) and attempt < max_retries:
                    delay = RETRY_DELAY * attempt
                    logger.warning(
                        f"Navigation error: {msg}. Retrying in {delay}s ({attempt}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue
                break

        if last_exc:
            raise last_exc
        return page

    async def close_modal_overlays(self, page: Page) -> None:
        """
        Close any modal overlays, popups, or promotional cards that might block content.

        Looks for common close button patterns:
        - buttons with aria-label containing "close"
        - buttons with class/id containing "close" or "dismiss"
        - aria-label="dismiss"
        - data-testid containing "close" or "modal-close"
        """
        try:
            logger.debug("🔍 Searching for modal overlays to close...")

            # Common close button selectors
            close_selectors = [
                'button[aria-label*="close" i]',  # aria-label with "close"
                'button[aria-label*="dismiss" i]',  # aria-label with "dismiss"
                'button[aria-label*="Close" i]',  # Case insensitive
                '[data-testid*="close" i]',  # data-testid with "close"
                '[data-testid*="modal" i] button[aria-label]',  # Modal close buttons
                ".modal-close, .modal__close, .modal_close",  # Common class names
                "#modal-close, .dismiss-btn, .close-btn",  # ID/class patterns
                'button:has-text("Close")',  # Text content
                'button:has-text("Dismiss")',
                'button:has-text("X")',
            ]

            close_buttons_found = 0

            for selector in close_selectors:
                try:
                    buttons = page.locator(selector)
                    count = await buttons.count()

                    if count > 0:
                        # Try to close first visible button (most likely the modal close)
                        for idx in range(count):
                            try:
                                button = buttons.nth(idx)
                                is_visible = await button.is_visible(timeout=1000)
                                is_enabled = await button.is_enabled(timeout=500)

                                if is_visible and is_enabled:
                                    await button.click(timeout=2000)
                                    logger.debug(
                                        f"✓ Closed modal with selector: {selector}"
                                    )
                                    close_buttons_found += 1
                                    await asyncio.sleep(0.3)
                                    break
                            except Exception:
                                continue
                except Exception:
                    continue

            if close_buttons_found > 0:
                logger.info(f"✓ Closed {close_buttons_found} modal overlay(s)")
                await asyncio.sleep(1)
            else:
                logger.debug("✓ No modal overlays found")

        except Exception as e:
            logger.debug(f"Modal overlay close attempt: {e}")

    def is_sole_image(self, image_url: str):
        """
        Download image from URL, crop left half, and check if it's a sole image using CLIP.

        For top-down shoe views, the left half typically shows the sole better.
        Includes retry logic for 403 errors.

        Returns:
            tuple: (is_sole: bool, confidence: float, scores: dict)
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Download image with headers to avoid 403
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = requests.get(image_url, timeout=15, headers=headers)
                response.raise_for_status()

                # Open image from bytes
                image = Image.open(BytesIO(response.content)).convert("RGB")

                # Convert PIL to OpenCV format for cropping
                cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                height, width = cv_image.shape[:2]

                # Crop left half (from x=0 to x=width/2)
                left_half = cv_image[:, : width // 2]

                # Convert back to PIL
                cropped_image = Image.fromarray(
                    cv2.cvtColor(left_half, cv2.COLOR_BGR2RGB)
                )

                logger.debug(
                    f"Original image: {width}x{height}, Cropped to left half: {width // 2}x{height}"
                )

                # Check if it's a sole image
                is_sole, confidence, scores = self.sole_detector.is_sole(cropped_image)

                # Log detailed breakdown by label
                if scores:
                    logger.debug("📊 CLIP Scores Breakdown (left half cropped):")
                    logger.debug("   Sole-related labels:")
                    logger.debug(
                        f"     • sole_tread: {scores.get('sole_tread', 0):.3f}"
                    )
                    logger.debug(
                        f"     • sole_rubber: {scores.get('sole_rubber', 0):.3f}"
                    )
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
                    logger.debug(
                        f"     • front_view: {scores.get('front_view', 0):.3f}"
                    )
                    logger.debug(
                        f"     • upper_only: {scores.get('upper_only', 0):.3f}"
                    )
                    logger.debug(
                        f"   Confidence: {confidence:.3f}, Result: {'✓ SOLE' if is_sole else '✗ NOT SOLE'}"
                    )

                return is_sole, confidence, scores

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.debug(
                            f"⚠️ Got 403, retrying ({retry_count}/{max_retries})..."
                        )
                        asyncio.run(asyncio.sleep(1))  # Wait before retry
                        continue
                    else:
                        logger.warning(
                            f"⚠️ Error checking sole image (403 after {max_retries} retries): {e}"
                        )
                        return False, 0.0, {}
                else:
                    logger.warning(f"⚠️ Error checking sole image: {e}")
                    return False, 0.0, {}

            except Exception as e:
                logger.warning(f"⚠️ Error checking sole image: {e}")
                return False, 0.0, {}

    async def load_more_products(self, page: Page) -> int:
        """
        Click the "Load More" button repeatedly to load all products.

        Process:
        1. Find button with data-testid="loadMoreButton"
        2. While button exists and is visible:
           a. Scroll into view
           b. Click the button
           c. Wait for images to load
           d. Check if button is still visible
        3. Stop when button disappears from UI or max attempts reached
        """
        try:
            logger.info("Loading all products via Load More button...")
            click_count = 0
            max_clicks = 100  # Safety limit

            while click_count < max_clicks:
                try:
                    # Find the load more button
                    button = page.locator(LOAD_MORE_BUTTON_SELECTOR)

                    # Check if button is visible
                    is_visible = await button.is_visible(timeout=3000)

                    if not is_visible:
                        logger.info(
                            f"✓ Load More button no longer visible (after {click_count} clicks)"
                        )
                        break

                    # Scroll button into view using JavaScript
                    await button.evaluate("el => el.scrollIntoView(true)")
                    logger.debug("✓ Scrolled Load More button into view")

                    # Wait a bit for page to settle
                    await asyncio.sleep(1)

                    # Click the button
                    await button.click(timeout=5000)
                    click_count += 1
                    logger.info(f"✓ Clicked Load More button (#{click_count})")

                    # Wait for images to load
                    await asyncio.sleep(2)

                    # Wait for product images to load
                    images = page.locator(PRODUCT_IMAGE_SELECTOR)
                    await images.first.wait_for(state="visible", timeout=5000)
                    logger.debug("✓ Products loaded, total images visible")

                except TimeoutError:
                    logger.debug("⏱️ Timeout waiting for button, checking if visible...")
                    try:
                        is_still_visible = await button.is_visible(timeout=2000)
                        if not is_still_visible:
                            logger.info(
                                f"✓ Load More button no longer visible (after {click_count} clicks)"
                            )
                            break
                    except Exception:
                        logger.info(
                            f"✓ Load More button disappeared (after {click_count} clicks)"
                        )
                        break

                except Exception as e:
                    logger.warning(f"⚠️ Error clicking Load More: {e}")
                    try:
                        is_still_visible = await button.is_visible(timeout=2000)
                        if not is_still_visible:
                            break
                    except Exception:
                        break

            logger.info(f"✓ Load More complete after {click_count} clicks")
            return click_count

        except Exception as e:
            logger.error(f"❌ Failed to load products: {e}", exc_info=True)
            return 0

    async def get_product_links(self, page: Page) -> List[str]:
        """
        Extract all product links from the products container.

        Looks for:
        - Container: div[data-testid="plpContainer"]
        - Items: div[data-testid="productListItem"]
        - Links: First <a> tag in each item
        """
        try:
            logger.info("Extracting product links...")

            # Find products container
            container = page.locator(PRODUCTS_CONTAINER_SELECTOR).first

            # Wait for container to be visible
            await container.wait_for(state="visible", timeout=10000)
            logger.debug("✓ Products container found")

            # Get all product items
            product_items = await container.locator(PRODUCT_ITEM_SELECTOR).all()
            logger.info(f"📦 Found {len(product_items)} product items")

            product_links = []
            errors = 0

            for idx, item in enumerate(product_items, 1):
                try:
                    # Get first <a> tag in item
                    link_element = item.locator("a").first
                    href = await link_element.get_attribute("href")

                    if href:
                        # Ensure absolute URL
                        if not href.startswith("http"):
                            href = f"https://www.clarks.com{href}"

                        product_links.append(href)
                        logger.debug(f"Product {idx}: {href}")
                    else:
                        logger.debug(f"Product {idx}: No href found")
                        errors += 1

                except Exception as e:
                    logger.debug(f"Product {idx}: Failed to extract - {e}")
                    errors += 1

            logger.info(
                f"✓ Extracted {len(product_links)} product links ({errors} errors)"
            )
            return product_links

        except Exception as e:
            logger.error(f"❌ Failed to extract product links: {e}", exc_info=True)
            return []

    async def extract_product_details(
        self, page: Page, url: str, product_index: int, total_products: int
    ) -> Optional[Dict[str, Any]]:
        """
        Extract product details from product page.
        """
        try:
            logger.info(f"\n  Product {product_index}/{total_products}: Scraping...")

            # Navigate to product page
            logger.debug("⏳ Navigating to product page...")
            page = await self.navigate_with_retries(page, url)
            await asyncio.sleep(2)

            # Handle cookie consent
            try:
                cookie_button = page.locator("#onetrust-accept-btn-handler")
                is_visible = await cookie_button.is_visible(timeout=2000)
                if is_visible:
                    await cookie_button.click(timeout=5000)
                    logger.debug("✓ Clicked cookie button on product page")
                    await asyncio.sleep(0.5)
            except Exception:
                pass

            # Close any modal overlays
            await self.close_modal_overlays(page)
            await asyncio.sleep(1)

            product_name = None
            image_url = None

            try:
                # Get product name
                name_element = page.locator(PRODUCT_NAME_SELECTOR).first
                await name_element.wait_for(state="visible", timeout=5000)
                product_name = await name_element.text_content()
                product_name = product_name.strip() if product_name else "Unknown"
                logger.debug(f"Product name: {product_name}")

                # Get media container
                media_container = page.locator(PRODUCT_MEDIA_CONTAINER_SELECTOR).first
                await media_container.wait_for(state="visible", timeout=5000)
                logger.debug("✓ Product media container found")

                # Scroll media container into view
                logger.debug("⏳ Scrolling media container into view...")
                await media_container.evaluate("el => el.scrollIntoView(true)")
                await asyncio.sleep(1)

                # Scroll down multiple times to trigger lazy loading
                logger.debug("⏳ Scrolling to trigger lazy loading...")
                for _ in range(5):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await asyncio.sleep(0.5)

                # Scroll back to media container
                logger.debug("⏳ Scrolling back to media container...")
                await media_container.evaluate("el => el.scrollIntoView(true)")
                await asyncio.sleep(1)

                # Get all images from thumbnail container
                # This is the static container with all image thumbnails
                thumbnail_container_xpath = (
                    '//*[@id="pdp-container-desktop"]/section/div[2]'
                )
                try:
                    thumbnail_container = page.locator(
                        f"xpath={thumbnail_container_xpath}"
                    ).first
                    await thumbnail_container.wait_for(state="visible", timeout=5000)

                    # Count total images in thumbnail container
                    total_images = len(await thumbnail_container.locator("img").all())
                    logger.info(f"📸 Found {total_images} images for product")

                    # Get carousel next button XPath and click it N times to load all images
                    carousel_button_xpath = (
                        '//*[@id="pdp-container-desktop"]/section/div[1]/button[2]'
                    )
                    carousel_button = page.locator(
                        f"xpath={carousel_button_xpath}"
                    ).first

                    logger.debug(
                        f"⏳ Clicking carousel next button {total_images} times to load all images..."
                    )
                    for click_idx in range(total_images):
                        try:
                            await carousel_button.click(timeout=3000)
                            logger.debug(
                                f"✓ Clicked carousel next button (iteration {click_idx + 1}/{total_images})"
                            )
                            await asyncio.sleep(
                                0.8
                            )  # Wait for image to load in carousel
                        except Exception as e:
                            logger.debug(
                                f"⚠️ Could not click carousel button at iteration {click_idx + 1}: {e}"
                            )

                except Exception as e:
                    logger.warning(f"⚠️ Could not interact with carousel button: {e}")
                    total_images = 0

                logger.info("✓ Image loading process complete")

                # Extract image URLs from the thumbnail container using JavaScript
                # After clicking through carousel, the src attributes should be populated
                logger.debug("⏳ Extracting image URLs from thumbnail container...")
                image_urls = []
                try:
                    thumbnail_container_xpath = (
                        '//*[@id="pdp-container-desktop"]/section/div[2]'
                    )
                    thumbnail_container = page.locator(
                        f"xpath={thumbnail_container_xpath}"
                    ).first

                    # Extract all image URLs from thumbnails
                    image_data = await thumbnail_container.evaluate("""
                    (container) => {
                        const images = [];

                        const normalize = (u) => {
                            if (!u) return null;
                            // Decode common HTML entities
                            u = u.replace(/&amp;/g, '&').trim();
                            if (u.startsWith('//')) return 'https:' + u;
                            return u;
                        };

                        const imgElements = container.querySelectorAll('img');

                        imgElements.forEach((img) => {
                            const alt = img.getAttribute('alt') || '';
                            let url = null;
                            let source = null;

                            // Try src first (should be populated after carousel clicks)
                            let src = img.getAttribute('src') || '';
                            const norm_src = normalize(src);
                            if (norm_src && (norm_src.startsWith('http') || norm_src.startsWith('//'))) {
                                if (!norm_src.includes('data:')) {
                                    url = norm_src;
                                    source = 'src';
                                }
                            }

                            // Try srcset if src didn't yield a valid URL
                            if (!url) {
                                const srcset = img.getAttribute('srcset') || img.getAttribute('data-srcset') || '';
                                if (srcset) {
                                    try {
                                        const urlRegex = /(https?:\\/\\/[^,\\s]+|\\/\\/[^,\\s]+)/g;
                                        const matches = [];
                                        let m;
                                        while ((m = urlRegex.exec(srcset)) !== null) {
                                            matches.push(normalize(m[0]));
                                        }
                                        if (matches.length) {
                                            url = matches[matches.length - 1];
                                            source = 'srcset';
                                        }
                                    } catch (e) {
                                        // ignore
                                    }
                                }
                            }

                            // Last resort: data-src or data-original
                            if (!url) {
                                const data_src = img.getAttribute('data-src') || img.getAttribute('data-original') || '';
                                const norm_data = normalize(data_src);
                                if (norm_data && (norm_data.startsWith('http') || norm_data.startsWith('//'))) {
                                    url = norm_data;
                                    source = 'data-src';
                                }
                            }

                            if (url && !url.includes('data:')) {
                                images.push({ url: url, source: source, alt: alt });
                            }
                        });

                        return images;
                    }
                    """)

                    logger.debug(
                        f"✓ JavaScript query returned {len(image_data)} images from thumbnail container"
                    )

                    # Process extracted image data
                    for idx, img_info in enumerate(image_data, 1):
                        url = img_info.get("url")
                        source = img_info.get("source", "unknown")

                        if url:
                            # Ensure absolute URL
                            if not url.startswith("http"):
                                if url.startswith("/"):
                                    url = f"https://www.clarks.com{url}"
                                else:
                                    url = f"https://www.clarks.com/{url}"

                            image_urls.append(url)
                            logger.info(f"Image {idx}: Extracted from {source}")
                            logger.info(f"✓ Image {idx}: {url[:100]}...")

                except Exception as e:
                    logger.error(f"❌ Thumbnail container extraction failed: {e}")
                    logger.debug(
                        "Falling back to media container element-by-element extraction..."
                    )

                    # Fallback: Use media container if thumbnail container fails
                    try:
                        images = await media_container.locator("img").all()
                        for idx, img_element in enumerate(images, 1):
                            try:
                                img_url = None

                                # Try src first
                                src = await img_element.get_attribute("src")
                                if (
                                    src
                                    and not src.startswith("data:")
                                    and src.startswith("http")
                                ):
                                    img_url = src
                                    logger.info(f"Image {idx}: Extracted from src")

                                # Try srcset if src didn't work
                                if not img_url:
                                    srcset = await img_element.get_attribute("srcset")
                                    if srcset:
                                        try:
                                            urls = [
                                                part.strip().split(" ")[0]
                                                for part in srcset.split(",")
                                            ]
                                            img_url = urls[-1] if urls else None
                                            if img_url and not img_url.startswith(
                                                "data:"
                                            ):
                                                logger.info(
                                                    f"Image {idx}: Extracted from srcset"
                                                )
                                        except Exception:
                                            pass

                                if img_url and img_url.startswith("http"):
                                    image_urls.append(img_url)
                                    logger.info(f"✓ Image {idx}: {img_url[:100]}...")
                            except Exception as e:
                                logger.debug(f"⚠️ Could not extract image {idx}: {e}")
                    except Exception as fallback_e:
                        logger.error(
                            f"❌ Fallback extraction also failed: {fallback_e}"
                        )

                logger.info(
                    f"✅ Extracted {len(image_urls)} image URLs from {total_images} found"
                )

                # Check images with CLIP model
                if not image_urls:
                    logger.warning("⚠️ No images were extracted - skipping product")
                    return None

                checked_images = []
                for idx, img_url in enumerate(image_urls, 1):
                    logger.debug(
                        f"Checking image {idx}/{len(image_urls)} with CLIP model..."
                    )
                    is_sole, confidence, scores = self.is_sole_image(img_url)

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
                            top_non_sole = max(non_sole_scores, key=non_sole_scores.get)

                            logger.info(
                                f"  ✗ Image {idx}: Not a sole (conf={confidence:.2f}) | "
                                f"Top sole: {top_sole}({sole_scores[top_sole]:.3f}) | "
                                f"Top non-sole: {top_non_sole}({non_sole_scores[top_non_sole]:.3f})"
                            )

                # Select best sole image
                sole_candidates = [c for c in checked_images if c["is_sole"]]

                if sole_candidates:
                    best = max(sole_candidates, key=lambda x: x["confidence"])
                    image_url = best["url"]
                    logger.info(
                        f"✅ Selected sole image: {image_url} (conf={best['confidence']:.2f})"
                    )
                else:
                    logger.warning(
                        f"⚠️ No sole images detected in {len(image_urls)} images - using fallback heuristic..."
                    )

                    # Fallback 1: Look for GW_3 pattern in URL (common sole image indicator)
                    gw3_candidates = [c for c in checked_images if "GW_3" in c["url"]]

                    if gw3_candidates:
                        # If multiple GW_3 images, pick the one with highest confidence
                        best = max(gw3_candidates, key=lambda x: x["confidence"])
                        image_url = best["url"]
                        logger.info(
                            f"✅ Selected fallback image (GW_3 pattern): {image_url} (conf={best['confidence']:.2f})"
                        )
                    else:
                        # Fallback 2: Select image with highest sole-related confidence score
                        scored_images = []
                        for img in checked_images:
                            if img["scores"]:
                                # Calculate sole likelihood from individual sole scores
                                sole_scores = {
                                    "sole_tread": img["scores"].get("sole_tread", 0),
                                    "sole_rubber": img["scores"].get("sole_rubber", 0),
                                    "sole_outsole": img["scores"].get(
                                        "sole_outsole", 0
                                    ),
                                    "sole_with_upper": img["scores"].get(
                                        "sole_with_upper", 0
                                    ),
                                    "sole_visible": img["scores"].get(
                                        "sole_visible", 0
                                    ),
                                }
                                sole_avg = (
                                    sum(sole_scores.values()) / len(sole_scores)
                                    if sole_scores
                                    else 0
                                )
                                scored_images.append(
                                    {"image": img, "sole_avg": sole_avg}
                                )

                        if scored_images:
                            best_scored = max(
                                scored_images, key=lambda x: x["sole_avg"]
                            )
                            image_url = best_scored["image"]["url"]
                            logger.info(
                                f"✅ Selected fallback image (highest sole score): {image_url} (sole_avg={best_scored['sole_avg']:.3f})"
                            )
                        else:
                            logger.warning(
                                "⚠️ No fallback images available - skipping product"
                            )
                            return None

            except Exception as e:
                logger.warning(f"❌ Failed to extract images: {e}")
                return None

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

            return product_data

        except Exception as e:
            logger.error(f"Failed to extract details from {url}: {e}", exc_info=True)
            return None

    async def scrape(
        self, batch_callback=None, batch_size: int = 20, is_cancelled=None
    ) -> Dict[str, Any]:
        """
        Main scraper function with batch processing support.

        Args:
            batch_callback: Async function to call with each batch of products
            batch_size: Number of products to collect before calling batch_callback
            is_cancelled: Optional function to check if scraping should be cancelled

        Steps:
        1. Navigate to base URL
        2. Load all products via Load More button
        3. Extract product links
        4. For each link, extract product details and sole image (with real-time batching)
        5. Save results to JSON
        """
        if is_cancelled:
            logger.info("🛑 Cancellation support enabled for this scraper")

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

            try:
                logger.info("Starting Clarks scraper")
                logger.info(f"Base URL: {BASE_URL}")
                if batch_callback:
                    logger.info("Using in-memory image processing (no temp files)")

                # Step 1: Navigate to base URL
                logger.info("Step 1: Navigating to base URL...")
                page = await self.navigate_with_retries(page, BASE_URL)
                await asyncio.sleep(2)

                # Step 1.5: Handle cookie consent
                logger.info("Step 1.5: Handling cookie consent...")
                try:
                    cookie_button = page.locator("#onetrust-accept-btn-handler")
                    is_visible = await cookie_button.is_visible(timeout=3000)

                    if is_visible:
                        await cookie_button.click(timeout=5000)
                        logger.info("✓ Clicked cookie acceptance button")
                        await asyncio.sleep(1)
                    else:
                        logger.debug(
                            "✓ Cookie button not visible (may already be accepted)"
                        )
                except Exception as e:
                    logger.debug(f"✓ Cookie handling skipped: {e}")

                # Step 2: Load all products via Load More button
                logger.info("Step 2: Loading all products via Load More button...")
                await self.load_more_products(page)

                # Step 3: Extract product links
                logger.info("Step 3: Extracting product links...")
                product_links = await self.get_product_links(page)

                if not product_links:
                    logger.warning("⚠️ No product links found")
                    return {
                        "brand": BRAND_NAME,
                        "base_url": BASE_URL,
                        "products": [],
                        "summary": {
                            "total_scraped": 0,
                            "total_skipped": 0,
                            "errors": 0,
                        },
                    }

                logger.info(f"✓ Found {len(product_links)} products")

                # Step 4: Scrape product details with batch processing
                logger.info("Step 4: Scraping product details...")
                products = []
                skipped = 0
                errors = 0
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
                                f"   Product Name: {product_data.get('name', 'N/A')}"
                            )
                            logger.info(
                                f"   Product URL: {product_data.get('source_url', 'N/A')}"
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
                                        name_field="name",
                                        url_field="source_url",
                                        image_url_field="image_url",
                                    )
                                )

                                if not should_continue:
                                    should_stop = True

                                current_batch = []  # Reset batch
                        else:
                            skipped += 1

                    except Exception as e:
                        logger.error(f"❌ Error scraping product {idx}: {e}")
                        errors += 1

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

                # Build result
                result = {
                    "brand": BRAND_NAME,
                    "base_url": BASE_URL,
                    "products": products,
                    "summary": {
                        "total_found": len(product_links),
                        "total_scraped": len(products),
                        "total_skipped": skipped,
                        "errors": errors,
                    },
                }

                return result

            except Exception as e:
                logger.error(f"❌ Fatal error during scraping: {e}", exc_info=True)
                return {
                    "brand": BRAND_NAME,
                    "base_url": BASE_URL,
                    "products": [],
                    "error": str(e),
                }

            finally:
                await context.close()
                await browser.close()


async def main():
    """Main entry point"""
    scraper = ClarksScraper()
    result = await scraper.scrape()

    # Save results to JSON
    output_file = Path(__file__).parent / "clarks_boots.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info(f"✓ Results saved to {output_file}")

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 SCRAPING SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Brand: {result['brand']}")
    logger.info(f"Base URL: {result['base_url']}")
    logger.info(f"Total found: {result['summary'].get('total_found', 0)}")
    logger.info(f"Total scraped: {result['summary'].get('total_scraped', 0)}")
    logger.info(f"Total skipped: {result['summary'].get('total_skipped', 0)}")
    logger.info(f"Errors: {result['summary'].get('errors', 0)}")
    logger.info("=" * 60)

    # Print products
    if result["products"]:
        logger.info("\n✅ PRODUCTS COLLECTED:")
        for product in result["products"]:
            logger.info(f"  • {product['name']}")
            logger.info(f"    Link: {product['source_url']}")
            if product["image_url"]:
                logger.info(f"    Image: {product['image_url']}")


if __name__ == "__main__":
    asyncio.run(main())
