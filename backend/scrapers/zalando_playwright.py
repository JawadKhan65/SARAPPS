"""
Playwright-based scraper for Zalando.nl shoes.

Scrapes product links from paginated search results, then extracts:
  - Brand name
  - Product name
  - Product URL
  - Number of product images

Returns a list of dictionaries with product metadata.
"""

import asyncio
import json
import re
from pathlib import Path
from io import BytesIO
from typing import List, Dict, Any
from PIL import Image
import requests
from playwright.async_api import async_playwright, Page
import logging
import sys

# Add backend to path to import models
sys.path.insert(0, str(Path(__file__).parent.parent))


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Increase timeouts and add retry settings
DEFAULT_TIMEOUT = 60000  # 60 seconds
NAVIGATION_TIMEOUT = 90000  # 90 seconds for page navigation
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds between retries

# XPaths for pagination and product elements
PAGINATION_XPATH = (
    '//*[@id="main-content"]/div/div[5]/div/div[2]/div[3]/ul/li[85]/nav/div/span'
)
PRODUCTS_CONTAINER_XPATH = '//*[@id="main-content"]/div/div[5]/div/div[2]/div[3]/ul'

# XPaths for product detail page
BRAND_XPATH = '//*[@id="main-content"]/div[1]/div/div[2]/h1/div/a/span/span'
PRODUCT_NAME_XPATH = '//*[@id="main-content"]/div[1]/div/div[2]/h1/span/span'
IMAGES_CONTAINER_XPATH = (
    '//*[@id="main-content"]/div[1]/div/div[1]/section/div[1]/div/div/div[2]/div[1]'
)


async def get_pagination_info(page: Page) -> int:
    """
    Extract total page count from pagination element.
    Expected format: "Pagina 1 van 428" -> returns 428
    Falls back to checking page content if XPath fails.
    """
    try:
        # Try XPath first
        try:
            pagination_text = await page.text_content(PAGINATION_XPATH, timeout=5000)
            if pagination_text:
                parts = pagination_text.strip().split("van ")
                if len(parts) == 2:
                    total_pages = int(parts[1].strip())
                    logger.info(f"Found {total_pages} total pages")
                    return total_pages
        except Exception as e:
            logger.debug(f"XPath pagination failed, trying alternative method: {e}")

        # Fallback: look for pagination text anywhere on page
        page_content = await page.content()
        if "van" in page_content:
            # Try to find pattern like "Pagina 1 van 428"
            import re

            match = re.search(r"Pagina\s+\d+\s+van\s+(\d+)", page_content)
            if match:
                total_pages = int(match.group(1))
                logger.info(f"Found {total_pages} total pages (via regex)")
                return total_pages
    except Exception as e:
        logger.warning(f"Failed to extract pagination info: {e}")

    logger.info("Using default: 1 page")
    return 1


async def get_product_links(page: Page) -> List[str]:
    """
    Extract product links from the current page.
    Finds all <a> tags with href containing product URLs inside the products container.
    """
    try:
        # Wait for products container to be visible
        await page.wait_for_selector(PRODUCTS_CONTAINER_XPATH, timeout=10000)

        # Get all product links
        links = await page.locator(
            f'{PRODUCTS_CONTAINER_XPATH}//a[contains(@href, ".html")]'
        ).all()
        product_links = []

        for link in links:
            href = await link.get_attribute("href")
            if href and ".html" in href:
                # Ensure absolute URL
                if href.startswith("http"):
                    product_links.append(href)
                else:
                    product_links.append(f"https://www.zalando.nl{href}")

        logger.info(f"Found {len(product_links)} product links on this page")
        return product_links
    except Exception as e:
        logger.error(f"Failed to extract product links: {e}")
        return []


async def get_product_images(page: Page) -> List[Dict[str, str]]:
    """
    Extract all image URLs and their alt text from the images container on current product page.
    Returns a list of dictionaries: {"url": absolute_url, "alt": alt_text}
    """
    try:
        images = await page.locator(f"{IMAGES_CONTAINER_XPATH}//img").all()
        entries: List[Dict[str, str]] = []

        for img in images:
            try:
                # Try srcset first (responsive images), then src
                srcset = await img.get_attribute("srcset")
                src = await img.get_attribute("src")
                alt = await img.get_attribute("alt") or ""

                url = None
                if srcset:
                    # Extract first URL from srcset
                    url = srcset.split(",")[0].split()[0]
                elif src:
                    url = src

                if url and url.startswith("http"):
                    entries.append({"url": url, "alt": alt})
            except Exception as e:
                logger.debug(f"Failed to extract image info: {e}")
                continue

        logger.info(f"Found {len(entries)} product images (with alt text)")
        return entries
    except Exception as e:
        logger.debug(f"Failed to extract product images: {e}")
        return []


def find_shoe_sole_image(image_entries: List[Dict[str, str]]) -> str:
    """
    Identify shoe sole image by searching for keywords in the image alt text.

    Accepts image_entries as returned by `get_product_images`: list of {"url","alt"}.

    Returns the URL of the first image whose alt text contains a sole-related keyword
    in English, Dutch, or German. Returns None if no match.
    """
    if not image_entries:
        return None

    # Keywords in different languages (lowercase)
    keywords = [
        # English
        "sole",
        "outsole",
        "bottom",
        # Dutch
        "zool",
        "onderkant",
        "onderzijde",
        # German
        "sohle",
        "laufsohle",
    ]

    for idx, entry in enumerate(image_entries):
        alt = (entry.get("alt") or "").lower()
        url = entry.get("url")
        try:
            if not alt:
                # skip images without alt text
                continue

            # Split by ',' and check only the first segment (index 0)
            alt_parts = alt.split(",")
            first_part = alt_parts[0].strip() if alt_parts else ""

            if any(k in first_part for k in keywords):
                logger.info(
                    f"✓ Found shoe sole by alt (image {idx}): {url} (alt='{alt}')"
                )
                return url
        except Exception as e:
            logger.debug(f"Error checking alt for image {idx}: {e}")
            continue

    logger.warning("No shoe sole image detected via alt text in product images")
    return None


async def extract_product_details(page: Page, url: str) -> Dict[str, Any]:
    """
    Extract brand, product name, image count, and shoe sole image URL from a product detail page.
    """
    try:
        await page.goto(url, wait_until="load", timeout=NAVIGATION_TIMEOUT)
        # Wait for main content instead of networkidle
        try:
            await page.wait_for_selector("#main-content", timeout=DEFAULT_TIMEOUT)
        except Exception:
            pass  # Continue even if main-content doesn't load

        await asyncio.sleep(1)  # Give page time to render

        # Extract brand
        brand = "Unknown"
        try:
            brand_elem = await page.locator(BRAND_XPATH).first.text_content(
                timeout=5000
            )
            brand = brand_elem.strip() if brand_elem else "Unknown"
        except Exception as e:
            logger.debug(f"Failed to extract brand: {e}")

        # Extract product name
        product_name = "Unknown"
        try:
            name_elem = await page.locator(PRODUCT_NAME_XPATH).first.text_content(
                timeout=5000
            )
            product_name = name_elem.strip() if name_elem else "Unknown"
        except Exception as e:
            logger.debug(f"Failed to extract product name: {e}")

        # Get product images
        image_entries = await get_product_images(page)
        image_count = len(image_entries)

        # Find shoe sole image via alt text
        sole_image_url = None
        if image_entries:
            logger.info(
                f"Analyzing {image_count} images for shoe sole detection (alt-text)..."
            )
            sole_image_url = find_shoe_sole_image(image_entries)

        logger.info(
            f"Extracted: {brand} - {product_name} ({image_count} images, sole: {'found' if sole_image_url else 'not found'})"
        )

        return {
            "brand": brand,
            "name": product_name,
            "source_url": url,
            "image_count": image_count,
            "sole_image_url": sole_image_url,
        }
    except Exception as e:
        logger.error(f"Failed to extract details from {url}: {e}")
        return None


async def scrape_zalando_shoes(
    url: str = "https://www.zalando.nl/schoenen",
    max_pages: int = None,
    headless: bool = True,
) -> List[Dict[str, Any]]:
    """
    Main scraper function.

    Args:
        url: Starting URL (Zalando shoes page)
        max_pages: Max pages to scrape (None = all pages)
        headless: Run browser in headless mode

    Returns:
        List of product dictionaries
    """
    products = []

    async with async_playwright() as p:
        # Launch browser with user-agent to avoid bot detection
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

        try:
            # Navigate to base URL with retry logic
            logger.info(f"Navigating to {url}")
            for attempt in range(MAX_RETRIES):
                try:
                    await page.goto(url, wait_until="load", timeout=NAVIGATION_TIMEOUT)
                    # Wait for main content to load
                    await page.wait_for_selector(
                        "#main-content", timeout=DEFAULT_TIMEOUT
                    )
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            f"Navigation attempt {attempt + 1} failed: {e}. Retrying..."
                        )
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logger.error(f"Failed to navigate after {MAX_RETRIES} attempts")
                        raise

            # Get total pages
            total_pages = await get_pagination_info(page)
            pages_to_scrape = min(total_pages, max_pages) if max_pages else total_pages

            logger.info(f"Will scrape {pages_to_scrape} pages")

            for page_num in range(1, pages_to_scrape + 1):
                logger.info(f"\n--- Page {page_num} of {pages_to_scrape} ---")

                # Navigate to page with retry
                page_url = f"{url}?p={page_num}"
                for attempt in range(MAX_RETRIES):
                    try:
                        await page.goto(
                            page_url, wait_until="load", timeout=NAVIGATION_TIMEOUT
                        )
                        await page.wait_for_selector(
                            "#main-content", timeout=DEFAULT_TIMEOUT
                        )
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

                # Get product links from this page
                product_links = await get_product_links(page)

                if not product_links:
                    logger.warning(f"No product links found on page {page_num}")

                # Extract details from each product
                for idx, product_url in enumerate(product_links, 1):
                    logger.info(f"  Product {idx}/{len(product_links)}: {product_url}")
                    details = await extract_product_details(page, product_url)
                    if details:
                        products.append(details)
                    await asyncio.sleep(1)  # Small delay between product requests

                # Pause between pages
                await asyncio.sleep(2)

            logger.info(f"\n✓ Scraping complete. Total products: {len(products)}")

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
        finally:
            await browser.close()

    return products


def print_products_summary(products: List[Dict[str, Any]]):
    """Print a summary of scraped products."""
    print("\n" + "=" * 120)
    print("SCRAPE SUMMARY - ZALANDO SHOES WITH SOLE DETECTION")
    print("=" * 120)
    for idx, p in enumerate(products, 1):
        print(f"\n{idx}. {p['brand']} - {p['name']}")
        print(f"   URL: {p['source_url']}")
        print(f"   Images: {p['image_count']}")
        if p.get("sole_image_url"):
            print(f"   ✓ Sole Image: {p['sole_image_url']}")
        else:
            print("   ✗ Sole Image: Not detected")
        print("-" * 120)

    print(f"\nTotal Products Scraped: {len(products)}")
    sole_detected = sum(1 for p in products if p.get("sole_image_url"))
    print(f"Products with Sole Images: {sole_detected}/{len(products)}")


def save_products_to_json(products: List[Dict[str, Any]], output_path: str):
    """Save products to JSON file."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(products)} products to {output_file}")


async def main():
    """Main entry point."""
    # Scrape first 2 pages (or set to None for all pages)
    products = await scrape_zalando_shoes(
        url="https://www.zalando.nl/schoenen",
        max_pages=None,
        headless=False,  # Set to True for headless mode
    )

    # Print summary
    print_products_summary(products)

    # Save to JSON
    output_path = Path(__file__).parent.parent / "data" / "zalando_shoes.json"
    save_products_to_json(products, str(output_path))


if __name__ == "__main__":
    asyncio.run(main())
