"""
Quick start script to test Zalando scraper with Decodo proxies.
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers.zalando_playwright import ZalandoScraper
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_scraper_with_decodo(max_pages: int = 2):
    """
    Test the Zalando scraper with Decodo proxy rotation.

    Args:
        max_pages: Number of pages to scrape (default: 2 for testing)
    """

    logger.info("=" * 80)
    logger.info("🚀 Starting Zalando Scraper with Decodo Proxies")
    logger.info("=" * 80)
    logger.info(f"Pages to scrape: {max_pages}")
    logger.info("Proxy rotation: ENABLED")
    logger.info("=" * 80 + "\n")

    # Initialize scraper with proxy rotation enabled
    scraper = ZalandoScraper(
        base_url="https://www.zalando.nl/schoenen",
        enable_proxy_rotation=True,  # Loads proxies from proxies.json
    )

    try:
        # Scrape with batch processing
        results = await scraper.scrape(
            max_pages=max_pages,
            batch_size=20,  # Process in batches of 20
        )

        logger.info("\n" + "=" * 80)
        logger.info("✅ SCRAPING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Total products scraped: {len(results)}")

        if results:
            logger.info("\n📦 Sample products:")
            for i, product in enumerate(results[:5], 1):
                logger.info(f"\n{i}. {product.get('brand')} - {product.get('name')}")
                logger.info(f"   URL: {product.get('url')}")
                logger.info(f"   Image: {product.get('image_url', '')[:80]}...")

        return results

    except Exception as e:
        logger.error(f"❌ Scraping failed: {e}", exc_info=True)
        return []


async def main():
    """Main entry point with argument parsing"""

    # Default to 2 pages for testing
    max_pages = 2

    # Check for command line argument
    if len(sys.argv) > 1:
        try:
            max_pages = int(sys.argv[1])
        except ValueError:
            logger.error(f"Invalid page number: {sys.argv[1]}")
            logger.info("Usage: python run_zalando_scraper.py [max_pages]")
            logger.info("Example: python run_zalando_scraper.py 10")
            return

    # Check if proxies.json exists
    from pathlib import Path

    proxies_file = Path(__file__).parent / "proxies.json"

    if not proxies_file.exists():
        logger.error("❌ proxies.json not found!")
        logger.info("Expected location: backend/scrapers/proxies.json")
        logger.info("Please ensure your Decodo proxy configuration is in place.")
        return

    logger.info(f"✅ Found proxy configuration: {proxies_file}")
    logger.info("Testing proxies before scraping...\n")

    # Quick proxy connectivity check (first proxy only)
    try:
        from test_decodo_proxies import test_proxy
        import json

        with open(proxies_file, "r") as f:
            config = json.load(f)
            first_proxy = config["proxies"][0]

        logger.info("Quick connectivity test...")
        success, response_time, error = await test_proxy(first_proxy)

        if not success:
            logger.warning("⚠️  First proxy test failed. Continue anyway? (y/n)")
            response = input().lower()
            if response != "y":
                logger.info(
                    "Aborted. Run 'python test_decodo_proxies.py' to test all proxies."
                )
                return
        else:
            logger.info(f"✅ Proxy working ({response_time:.2f}s)")
            logger.info("Starting scraper in 3 seconds...\n")
            await asyncio.sleep(3)

    except Exception as e:
        logger.warning(f"Could not test proxy: {e}")
        logger.info("Continuing anyway...\n")

    # Run the scraper
    results = await test_scraper_with_decodo(max_pages=max_pages)

    # Save results if successful
    if results:
        from pathlib import Path
        import json

        output_file = Path(__file__).parent.parent / "data" / "zalando_decodo_test.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        logger.info(f"\n💾 Results saved to: {output_file}")


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║         Zalando Scraper with Decodo Proxies                 ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

    asyncio.run(main())
