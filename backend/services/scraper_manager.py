"""
Scraper Manager Service

Handles batch processing, uniqueness detection, and automated crawler management.
"""

import asyncio
import importlib
import logging
import hashlib
import requests
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from core.extensions import db
from core.models import Crawler, CrawlerRun, SoleImage
from services.scraper_service import ScraperService

logger = logging.getLogger(__name__)


class ScraperManager:
    """Manages scraper execution with batch processing and uniqueness tracking"""

    def __init__(self, crawler_id: str, admin_id: Optional[str] = None):
        self.crawler_id = crawler_id
        self.admin_id = admin_id
        self.crawler: Optional[Crawler] = None
        self.current_run: Optional[CrawlerRun] = None
        self.batch_size = 50  # Process items in batches of 50 for better throughput
        self.uniqueness_window = 100  # Check uniqueness over last 100 items
        self.stop_requested = False
        self.scraper_service: Optional[ScraperService] = None
        self.temp_image_dir = None

    def load_crawler(self) -> bool:
        """Load crawler from database"""
        self.crawler = Crawler.query.get(self.crawler_id)
        if not self.crawler:
            logger.error(f"Crawler {self.crawler_id} not found")
            return False
        return True

    def create_run_record(self, run_type: str = "manual") -> CrawlerRun:
        """Create a new crawler run record"""
        run = CrawlerRun(
            crawler_id=self.crawler_id,
            run_type=run_type,
            started_by=self.admin_id,
            status="running",
        )
        db.session.add(run)

        # Update crawler status
        self.crawler.is_running = True
        self.crawler.run_type = run_type
        self.crawler.started_by = self.admin_id
        self.crawler.last_started_at = datetime.utcnow()
        self.crawler.current_run_items = 0
        self.crawler.current_batch = 0
        self.crawler.cancel_requested = False
        self.crawler.consecutive_errors = 0

        db.session.commit()
        self.current_run = run
        return run

    async def start_scraper(self, run_type: str = "manual") -> Dict:
        """Start the scraper with batch processing"""
        if not self.load_crawler():
            return {"success": False, "error": "Crawler not found"}

        if self.crawler.is_running:
            return {"success": False, "error": "Crawler already running"}

        if not self.crawler.is_active:
            return {"success": False, "error": "Crawler is disabled"}

        # Reset cancellation flags for new run (important for reused instances)
        self.stop_requested = False

        # Create run record
        self.create_run_record(run_type)

        # Initialize scraper service for image processing
        self.scraper_service = ScraperService(self.crawler_id)

        # Create temp directory for downloaded images
        self.temp_image_dir = (
            Path(self.scraper_service.upload_folder) / "temp" / self.crawler_id
        )
        self.temp_image_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"🚀 Starting crawler: {self.crawler.name} (Run ID: {self.current_run.id})"
        )

        try:
            # Load scraper module dynamically
            scraper_module = self._load_scraper_module()
            if not scraper_module:
                raise Exception(
                    f"Scraper module not found: {self.crawler.scraper_module}"
                )

            # Execute scraper with batch processing
            result = await self._execute_with_batches(scraper_module)

            # Update completion status
            self._complete_run(result)

            return {"success": True, "run_id": self.current_run.id, "result": result}

        except Exception as e:
            logger.error(f"Scraper error: {str(e)}", exc_info=True)
            self._fail_run(str(e))
            return {"success": False, "error": str(e)}
        finally:
            # Cleanup temp directory
            if self.temp_image_dir and self.temp_image_dir.exists():
                import shutil

                try:
                    shutil.rmtree(self.temp_image_dir)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp directory: {e}")

    def _load_scraper_module(self):
        """Dynamically load scraper module"""
        if not self.crawler.scraper_module:
            # Try to infer from name
            module_name = self.crawler.name.lower().replace(" ", "_").replace("-", "_")
            module_name = module_name.replace("crawler", "").strip("_")
        else:
            module_name = self.crawler.scraper_module

        try:
            # Import from scrapers directory
            module = importlib.import_module(f"scrapers.{module_name}")
            return module
        except ImportError as e:
            logger.error(f"Failed to import scraper module '{module_name}': {e}")
            return None

    async def _execute_with_batches(self, scraper_module) -> Dict:
        """Execute scraper and process results in batches during scraping"""
        total_scraped = 0
        total_unique = 0
        total_duplicates = 0
        batches_processed = 0
        cancelled = False

        # Find scraper class (usually named like ZapposScraper, AmazonScraper, etc.)
        scraper_class = None
        for name in dir(scraper_module):
            obj = getattr(scraper_module, name)
            if isinstance(obj, type) and "Scraper" in name and name != "BaseScraper":
                scraper_class = obj
                break

        if not scraper_class:
            raise Exception("No scraper class found in module")

        # Initialize scraper with flexible parameters
        import inspect

        sig = inspect.signature(scraper_class.__init__)
        params = sig.parameters

        # Build initialization arguments based on what the scraper accepts
        init_kwargs = {}
        if "max_pages" in params:
            init_kwargs["max_pages"] = 5  # Limit pages for testing
        if "base_url" in params and self.crawler.website_url:
            init_kwargs["base_url"] = self.crawler.website_url

        scraper_instance = scraper_class(**init_kwargs)

        # Define cancellation check function that scrapers can poll
        def is_cancelled() -> bool:
            """Check if cancellation was requested - can be called frequently"""
            if self.stop_requested:
                logger.debug("🛑 Cancellation detected via stop_requested flag")
                return True
            # Refresh from DB to get latest cancel_requested state
            try:
                db.session.refresh(self.crawler)
                if self.crawler.cancel_requested:
                    logger.debug(
                        "🛑 Cancellation detected via DB cancel_requested flag"
                    )
                return self.crawler.cancel_requested
            except Exception as e:
                logger.warning(f"Failed to check cancellation state: {e}")
                return False

        # Define batch callback that will be called during scraping
        async def batch_callback(batch: List[Dict]):
            """Process a batch of products during scraping

            Returns:
                bool: True to continue scraping, False to stop
            """
            nonlocal \
                total_scraped, \
                total_unique, \
                total_duplicates, \
                batches_processed, \
                cancelled

            logger.info(f"Processing batch of {len(batch)} items during scraping...")

            result = await self._process_batch(batch)
            total_scraped += len(batch)
            total_unique += result["unique"]
            total_duplicates += result["duplicates"]
            batches_processed += 1

            # Update progress
            self._update_progress(
                batches_processed, total_scraped, total_unique, total_duplicates
            )

            # Report per-batch uniqueness percentage (diagnostic only)
            if len(batch) > 0:
                batch_uniqueness_pct = (result["unique"] / len(batch)) * 100
                logger.info(
                    f"Batch {batches_processed} uniqueness: {batch_uniqueness_pct:.1f}%"
                )

            # Check for cancel request
            if self._check_cancel_requested():
                logger.info("Cancel requested, stopping scraper")
                cancelled = True
                return False  # Stop scraping

            return True  # Continue scraping

        # Execute scraper with batch callback
        logger.info(
            f"Executing scraper: {scraper_class.__name__} with real-time batch processing"
        )

        # Check if scraper supports batch_callback parameter
        scrape_sig = None
        if hasattr(scraper_instance, "scrape"):
            scrape_sig = inspect.signature(scraper_instance.scrape)
        elif hasattr(scraper_instance, "run"):
            scrape_sig = inspect.signature(scraper_instance.run)
        else:
            raise Exception(
                f"Scraper {scraper_class.__name__} has no run() or scrape() method"
            )

        scrape_params = scrape_sig.parameters

        # Call scraper with batch_callback if supported
        if "batch_callback" in scrape_params:
            logger.info("Scraper supports batch_callback - using real-time processing")
            # Check if scraper supports is_cancelled parameter
            kwargs = {"batch_callback": batch_callback, "batch_size": self.batch_size}
            if "is_cancelled" in scrape_params:
                kwargs["is_cancelled"] = is_cancelled
                logger.info(
                    "Scraper supports is_cancelled - enabling responsive cancellation"
                )

            if hasattr(scraper_instance, "scrape"):
                await scraper_instance.scrape(**kwargs)
            elif hasattr(scraper_instance, "run"):
                await scraper_instance.run(**kwargs)
        else:
            # Fallback: scraper doesn't support batch_callback, process after completion
            logger.warning("Scraper doesn't support batch_callback - using legacy mode")
            if hasattr(scraper_instance, "run"):
                await scraper_instance.run()
            elif hasattr(scraper_instance, "scrape"):
                await scraper_instance.scrape()

            # Collect results from scraper instance
            scraped_items = []
            if hasattr(scraper_instance, "products"):
                scraped_items = scraper_instance.products
            elif hasattr(scraper_instance, "results"):
                scraped_items = scraper_instance.results

            logger.info(f"Scraper collected {len(scraped_items)} items (legacy mode)")

            # Process all collected items in batches
            if scraped_items:
                for i in range(0, len(scraped_items), self.batch_size):
                    batch = scraped_items[i : i + self.batch_size]

                    # Check for cancellation before processing each batch
                    if self._check_cancel_requested():
                        logger.info("Scraper cancelled during batch processing")
                        cancelled = True
                        break

                    result = await self._process_batch(batch)
                    total_scraped += len(batch)
                    total_unique += result["unique"]
                    total_duplicates += result["duplicates"]
                    batches_processed += 1

                    # Update progress
                    self._update_progress(
                        batches_processed, total_scraped, total_unique, total_duplicates
                    )

                    # Do not stop on global uniqueness threshold; continue processing

        return {
            "total_scraped": total_scraped,
            "total_unique": total_unique,  # Changed from "unique" for consistency
            "total_duplicates": total_duplicates,  # Changed from "duplicates" for consistency
            "batches": batches_processed,
            "cancelled": cancelled,
        }

    async def _process_batch(self, batch: List[Dict]) -> Dict:
        """Process a batch of scraped items - download images and insert to DB"""

        # Normalize and download images for batch
        processed_products = []

        for idx, item in enumerate(batch):
            try:
                # Normalize field names from different scrapers
                normalized = self._normalize_scraper_item(item)

                # Download image (send Referer to satisfy CDN protections)
                image_path = await self._download_image(
                    normalized["image_url"], idx, referer=normalized.get("url")
                )
                if not image_path:
                    logger.warning(f"Failed to download image for {normalized['url']}")
                    continue

                # Add image path to product data
                normalized["image_path"] = image_path
                processed_products.append(normalized)

                # Early cancellation check after each product
                if self._check_cancel_requested():
                    logger.info(
                        "Cancellation detected mid-batch; stopping batch processing early"
                    )
                    break

            except Exception as e:
                logger.error(f"Error processing item: {e}", exc_info=True)
                continue

        if not processed_products:
            logger.warning("No products successfully processed in batch")
            return {"unique": 0, "duplicates": 0}

        # Use ScraperService to batch insert with uniqueness checking
        try:
            result = self.scraper_service.batch_insert_sole_images(processed_products)

            logger.info(
                f"Batch processed: {len(processed_products)} items "
                f"({result['inserted']} inserted, {result['duplicates']} duplicates, {result['errors']} errors)"
            )

            # Log any errors in detail
            if result["errors"] > 0 and result.get("error_details"):
                for error_detail in result["error_details"]:
                    logger.error(f"  - {error_detail}")

            return {
                "unique": result["inserted"],
                "duplicates": result["duplicates"] + result["skipped"],
            }
        except Exception as e:
            logger.error(f"Failed to insert batch to database: {e}", exc_info=True)
            return {"unique": 0, "duplicates": 0}

    def _normalize_scraper_item(self, item: Dict) -> Dict:
        """Normalize field names from different scraper formats"""
        # Handle different field name conventions
        image_url = (
            item.get("image_url")
            or item.get("last_image_url")
            or item.get("sole_image_url")
        )
        product_url = item.get("url") or item.get("product_url")
        product_name = item.get("name") or item.get("product_name") or "Unknown Product"
        brand = item.get("brand", "Unknown Brand")

        # Default product_type to 'shoe' if not specified
        product_type = item.get("product_type", "shoe")

        return {
            "url": product_url,
            "brand": brand,
            "product_type": product_type,
            "product_name": product_name,
            "image_url": image_url,
        }

    async def _download_image(
        self, image_url: str, idx: int, referer: Optional[str] = None
    ) -> Optional[str]:
        """Download image from URL and return local path"""
        if not image_url:
            return None

        try:
            # Generate filename
            ext = image_url.split("?")[0].split(".")[-1]
            if ext not in ["jpg", "jpeg", "png", "webp"]:
                ext = "jpg"
            filename = f"item_{idx}_{hash(image_url)}.{ext}"
            filepath = self.temp_image_dir / filename

            # Prepare headers (include Referer to avoid CDN blocks)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            if referer:
                headers["Referer"] = referer

            # Download with simple retry/backoff to mitigate transient ERR_FAILED/403
            attempts = 3
            backoff_sec = 1.0
            for attempt in range(1, attempts + 1):
                try:
                    response = requests.get(
                        image_url,
                        timeout=30,
                        headers=headers,
                    )
                    response.raise_for_status()
                    break
                except Exception as e:
                    if attempt < attempts:
                        logger.warning(
                            f"Image request failed (attempt {attempt}): {e}; retrying in {backoff_sec}s"
                        )
                        import time

                        time.sleep(backoff_sec)
                        backoff_sec *= 2
                    else:
                        raise

            # Save to disk
            with open(filepath, "wb") as f:
                f.write(response.content)

            logger.debug(f"Downloaded image: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to download image from {image_url}: {e}")
            return None

    def _update_progress(self, batches: int, total: int, unique: int, duplicates: int):
        """Update crawler progress"""
        self.crawler.current_batch = batches
        self.crawler.current_run_items = total

        # Calculate uniqueness percentage
        if total > 0:
            uniqueness = (unique / total) * 100
            self.crawler.uniqueness_percentage = uniqueness
            self.current_run.uniqueness_percentage = uniqueness

        self.current_run.items_scraped = total
        self.current_run.unique_items = unique
        self.current_run.duplicate_items = duplicates
        self.current_run.batches_processed = batches

        db.session.commit()

        logger.info(
            f"Progress: Batch {batches}, Total: {total}, "
            f"Unique: {unique}, Duplicates: {duplicates}, "
            f"Uniqueness: {self.crawler.uniqueness_percentage:.1f}%"
        )

    def _check_uniqueness_threshold(self, unique: int, total: int) -> bool:
        """Check if uniqueness is above threshold with smart minimum thresholds"""

        # Minimum items to scrape before considering stopping based on uniqueness
        # Large e-commerce sites should scrape more before stopping
        MIN_ITEMS_THRESHOLDS = {
            "Zalando": 1000,  # Large catalog
            "Amazon": 1000,  # Large catalog
            "Nike": 500,
            "Adidas": 500,
        }

        # Get minimum threshold for this crawler (default 200)
        min_items = 200
        for name_pattern, threshold in MIN_ITEMS_THRESHOLDS.items():
            if name_pattern.lower() in self.crawler.name.lower():
                min_items = threshold
                break

        # Don't stop until minimum items threshold reached
        if total < min_items:
            logger.debug(
                f"Continuing scrape: {total}/{min_items} items "
                f"(waiting for minimum threshold)"
            )
            return True

        # Also need minimum samples for statistical validity
        if total < 50:
            return True

        uniqueness = (unique / total) * 100

        if uniqueness < self.crawler.min_uniqueness_threshold:
            logger.warning(
                f"⚠️  Uniqueness below threshold: {uniqueness:.1f}% < "
                f"{self.crawler.min_uniqueness_threshold}% "
                f"(Scraped: {total}, Unique: {unique})"
            )

            if self.crawler.notify_admin_on_low_uniqueness:
                self._notify_admin_low_uniqueness(uniqueness)

            # Only auto-stop after minimum threshold AND if configured
            if self.crawler.notify_admin_on_low_uniqueness and total >= min_items:
                self.current_run.auto_stopped_low_uniqueness = True
                self.current_run.cancelled_reason = (
                    f"Auto-stopped: Uniqueness {uniqueness:.1f}% below threshold "
                    f"{self.crawler.min_uniqueness_threshold}% after {total} items"
                )
                logger.info(
                    f"🛑 Stopping crawler after {total} items due to low uniqueness"
                )
                return False
            else:
                logger.info(
                    f"⚠️  Low uniqueness but continuing (min threshold: {min_items})"
                )

        return True

    def _check_cancel_requested(self) -> bool:
        """Check if cancellation was requested"""
        # Reload crawler to get latest state
        db.session.refresh(self.crawler)

        if self.crawler.cancel_requested:
            logger.info("🛑 Cancellation requested")
            self.current_run.status = "cancelled"
            self.current_run.cancelled_reason = "Manually cancelled by admin"
            return True

        return False

    def _notify_admin_low_uniqueness(self, uniqueness: float):
        """Notify admin about low uniqueness"""
        logger.warning(
            f"📧 Admin notification: Low uniqueness detected for {self.crawler.name}: "
            f"{uniqueness:.1f}%"
        )
        # TODO: Implement email/notification system
        # send_admin_notification(...)

    def _complete_run(self, result: Dict):
        """Mark run as completed"""
        # Honor cancellation state: do not overwrite if already cancelled
        if self.current_run.status == "cancelled" or result.get("cancelled"):
            self._finalize_cancel_run(result)
            return
        self.current_run.status = "completed"
        self.current_run.completed_at = datetime.utcnow()

        duration = (
            self.current_run.completed_at - self.current_run.started_at
        ).total_seconds()
        self.current_run.duration_seconds = duration

        # Update crawler
        self.crawler.is_running = False
        self.crawler.last_completed_at = datetime.utcnow()
        self.crawler.last_run_duration_minutes = duration / 60
        self.crawler.total_runs += 1
        self.crawler.items_scraped += result.get("total_scraped", 0)
        self.crawler.total_images_crawled += result.get("total_scraped", 0)
        self.crawler.unique_images_added += result.get("total_unique", 0)
        self.crawler.duplicate_count += result.get("total_duplicates", 0)
        self.crawler.last_error = None
        self.crawler.consecutive_errors = 0

        db.session.commit()

        logger.info(
            f"✅ Crawler completed: {self.crawler.name} "
            f"({result.get('total_scraped', 0)} items, "
            f"{result.get('total_unique', 0)} unique, "
            f"{duration:.1f}s)"
        )

    def _finalize_cancel_run(self, result: Dict):
        """Finalize a cancelled run without marking it completed"""
        self.current_run.completed_at = datetime.utcnow()
        duration = (
            self.current_run.completed_at - self.current_run.started_at
        ).total_seconds()
        self.current_run.duration_seconds = duration
        if not self.current_run.cancelled_reason:
            self.current_run.cancelled_reason = "Manually cancelled by admin"

        # Update crawler partial stats
        self.crawler.is_running = False
        self.crawler.last_completed_at = datetime.utcnow()
        self.crawler.last_run_duration_minutes = duration / 60
        self.crawler.items_scraped += result.get("total_scraped", 0)
        self.crawler.total_images_crawled += result.get("total_scraped", 0)
        self.crawler.unique_images_added += result.get("total_unique", 0)
        self.crawler.duplicate_count += result.get("total_duplicates", 0)
        db.session.commit()

        logger.info(
            f"🛑 Crawler run cancelled: {self.crawler.name} after processing {result.get('total_scraped', 0)} items"
        )

    def _fail_run(self, error: str):
        """Mark run as failed"""
        self.current_run.status = "failed"
        self.current_run.error_message = error
        self.current_run.completed_at = datetime.utcnow()

        duration = (
            self.current_run.completed_at - self.current_run.started_at
        ).total_seconds()
        self.current_run.duration_seconds = duration

        # Update crawler
        self.crawler.is_running = False
        self.crawler.last_error = error
        self.crawler.last_error_at = datetime.utcnow()
        self.crawler.consecutive_errors += 1

        db.session.commit()

        logger.error(f"❌ Crawler failed: {self.crawler.name} - {error}")

    def cancel_run(self, reason: str = "Manual cancellation") -> bool:
        """Request cancellation of current run"""
        if not self.load_crawler():
            return False

        if not self.crawler.is_running:
            return False

        self.crawler.cancel_requested = True
        self.crawler.cancelled_by = self.admin_id
        self.crawler.cancelled_at = datetime.utcnow()
        self.stop_requested = True

        db.session.commit()

        logger.info(f"🛑 Cancel requested for: {self.crawler.name}")
        return True


# Singleton instance manager
_active_scrapers: Dict[str, ScraperManager] = {}


def get_scraper_manager(
    crawler_id: str, admin_id: Optional[str] = None
) -> ScraperManager:
    """Get or create scraper manager for a crawler"""
    if crawler_id not in _active_scrapers:
        _active_scrapers[crawler_id] = ScraperManager(crawler_id, admin_id)
    return _active_scrapers[crawler_id]


def cleanup_scraper_manager(crawler_id: str):
    """Remove scraper manager from active list"""
    if crawler_id in _active_scrapers:
        del _active_scrapers[crawler_id]
