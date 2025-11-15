"""
Footlocker scraper - NOT YET IMPLEMENTED

This scraper is a placeholder and needs to be implemented.
To implement:
1. Create a FootlockerScraper class
2. Add a scrape() method with batch_callback and batch_size parameters
3. Follow the pattern used in johnloob_playwright_en_gb.py
"""

import logging

logger = logging.getLogger(__name__)


class FootlockerScraper:
    """Placeholder scraper for Footlocker - NOT YET IMPLEMENTED"""

    def __init__(self):
        logger.warning("⚠️  FootlockerScraper is not yet implemented")

    async def scrape(
        self, batch_callback=None, batch_size: int = 20, is_cancelled=None
    ):
        """
        Scrape method - NOT YET IMPLEMENTED

        Args:
            batch_callback: Async function to call with each batch of products
            batch_size: Number of products to collect before calling batch_callback
            is_cancelled: Sync function to check if scraper should be cancelled
        """
        logger.error("❌ FootlockerScraper.scrape() is not yet implemented")
        raise NotImplementedError(
            "Footlocker scraper is not yet implemented. "
            "Please implement this scraper or disable the Footlocker crawler."
        )
