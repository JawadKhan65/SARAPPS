"""
Test script to verify Decodo proxy connectivity before running the scraper.
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_proxy(proxy_config: dict, test_url: str = "https://www.zalando.nl"):
    """
    Test a single proxy by attempting to load Zalando homepage.

    Args:
        proxy_config: Dict with host, port, username, password
        test_url: URL to test (default: Zalando homepage)

    Returns:
        Tuple of (success: bool, response_time: float, error: str)
    """
    proxy_str = f"{proxy_config['host']}:{proxy_config['port']}"

    try:
        async with async_playwright() as p:
            # Launch browser with proxy
            browser = await p.chromium.launch(headless=True)

            context_options = {
                "proxy": {
                    "server": f"http://{proxy_config['host']}:{proxy_config['port']}",
                    "username": proxy_config["username"],
                    "password": proxy_config["password"],
                }
            }

            context = await browser.new_context(**context_options)
            page = await context.new_page()

            # Measure response time
            start_time = asyncio.get_running_loop().time()

            try:
                response = await page.goto(
                    test_url, timeout=30000, wait_until="domcontentloaded"
                )
                response_time = asyncio.get_running_loop().time() - start_time

                if response and response.status < 400:
                    logger.info(
                        f"✅ {proxy_str} - SUCCESS (HTTP {response.status}, {response_time:.2f}s)"
                    )
                    return True, response_time, None
                else:
                    error_msg = f"HTTP {response.status if response else 'Unknown'}"
                    logger.warning(f"⚠️  {proxy_str} - FAILED ({error_msg})")
                    return False, 0, error_msg

            except Exception as e:
                response_time = asyncio.get_running_loop().time() - start_time
                error_msg = str(e)[:100]
                logger.error(f"❌ {proxy_str} - ERROR: {error_msg}")
                return False, 0, error_msg
            finally:
                await browser.close()

    except Exception as e:
        error_msg = str(e)[:100]
        logger.error(f"❌ {proxy_str} - LAUNCH ERROR: {error_msg}")
        return False, 0, error_msg


async def test_all_proxies():
    """Test all Decodo proxies from proxies.json"""

    proxies_file = Path(__file__).parent / "proxies.json"

    if not proxies_file.exists():
        logger.error(f"❌ proxies.json not found at {proxies_file}")
        return

    with open(proxies_file, "r") as f:
        config = json.load(f)
        proxies = config.get("proxies", [])

    if not proxies:
        logger.error("❌ No proxies found in proxies.json")
        return

    logger.info(f"🔍 Testing {len(proxies)} Decodo proxies...\n")
    logger.info("=" * 80)

    results = []

    for i, proxy in enumerate(proxies, 1):
        logger.info(
            f"\n[{i}/{len(proxies)}] Testing {proxy['host']}:{proxy['port']}..."
        )
        success, response_time, error = await test_proxy(proxy)
        results.append(
            {
                "proxy": f"{proxy['host']}:{proxy['port']}",
                "success": success,
                "response_time": response_time,
                "error": error,
            }
        )

        # Small delay between tests
        await asyncio.sleep(2)

    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 80)

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    logger.info(f"\n✅ Successful: {len(successful)}/{len(results)}")
    logger.info(f"❌ Failed: {len(failed)}/{len(results)}")

    if successful:
        avg_time = sum(r["response_time"] for r in successful) / len(successful)
        logger.info(f"⏱️  Average Response Time: {avg_time:.2f}s")

        logger.info("\n🎯 Working Proxies:")
        for r in successful:
            logger.info(f"  • {r['proxy']} ({r['response_time']:.2f}s)")

    if failed:
        logger.info("\n❌ Failed Proxies:")
        for r in failed:
            logger.info(f"  • {r['proxy']} - {r['error']}")

    logger.info("\n" + "=" * 80)

    if len(successful) >= len(results) * 0.7:  # 70% success rate
        logger.info("✅ Proxy configuration looks good! Ready to scrape.")
    elif len(successful) > 0:
        logger.warning(
            "⚠️  Some proxies failed. You can still proceed but may want to investigate."
        )
    else:
        logger.error(
            "❌ All proxies failed! Check your Decodo credentials and network."
        )


async def test_single_proxy_detailed():
    """Test a single proxy with detailed diagnostics"""

    proxies_file = Path(__file__).parent / "proxies.json"

    with open(proxies_file, "r") as f:
        config = json.load(f)
        proxy = config["proxies"][0]  # Test first proxy

    logger.info(f"🔍 Detailed test of {proxy['host']}:{proxy['port']}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Visible for debugging

        context_options = {
            "proxy": {
                "server": f"http://{proxy['host']}:{proxy['port']}",
                "username": proxy["username"],
                "password": proxy["password"],
            }
        }

        context = await browser.new_context(**context_options)
        page = await context.new_page()

        # Test 1: Check IP
        logger.info("Test 1: Checking IP address...")
        try:
            await page.goto("https://api.ipify.org?format=json", timeout=15000)
            content = await page.content()
            logger.info(f"  Result: {content}")
        except Exception as e:
            logger.error(f"  Failed: {e}")

        await asyncio.sleep(2)

        # Test 2: Load Zalando
        logger.info("\nTest 2: Loading Zalando homepage...")
        try:
            response = await page.goto(
                "https://www.zalando.nl", timeout=30000, wait_until="domcontentloaded"
            )
            logger.info(f"  Status: HTTP {response.status}")
            logger.info(f"  URL: {page.url}")
            title = await page.title()
            logger.info(f"  Title: {title}")
        except Exception as e:
            logger.error(f"  Failed: {e}")

        logger.info("\n✅ Test complete. Press Enter to close browser...")
        input()

        await browser.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--detailed":
        # Detailed single proxy test
        asyncio.run(test_single_proxy_detailed())
    else:
        # Test all proxies
        asyncio.run(test_all_proxies())
