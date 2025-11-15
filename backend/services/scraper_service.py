import os
import sys
import logging
from datetime import datetime
import uuid
from flask import current_app
from extensions import db
from models import SoleImage, Crawler, CrawlerStatistics
from services.image_processor import ImageProcessor
import hashlib

# Add line_tracing module to path
line_tracing_path = os.path.join(os.path.dirname(__file__), "..", "line_tracing_utils")
sys.path.insert(0, line_tracing_path)

try:
    from line_tracing import compare_sole_images
except ImportError:
    compare_sole_images = None


class ScraperService:
    """Handle scraper operations with batch insertion and uniqueness checking"""

    def __init__(self, crawler_id, batch_size=None, similarity_threshold=None):
        self.crawler_id = crawler_id
        self.crawler = Crawler.query.get(crawler_id)

        if not self.crawler:
            raise ValueError(f"Crawler {crawler_id} not found")

        self.batch_size = batch_size or current_app.config.get("BATCH_SIZE", 50)
        self.similarity_threshold = similarity_threshold or current_app.config.get(
            "SIMILARITY_THRESHOLD", 0.85
        )
        self.logger = logging.getLogger(__name__)
        self.processor = ImageProcessor()
        self.upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")

    def calculate_image_hash(self, image_array):
        """Calculate SHA256 hash of image for deduplication"""
        image_bytes = image_array.tobytes()
        return hashlib.sha256(image_bytes).hexdigest()

    def batch_insert_sole_images(self, products):
        """
        Insert batch of products with uniqueness checking

        Args:
            products: List of dicts with keys: {
                'url': str (unique source URL),
                'brand': str,
                'product_type': str,
                'product_name': str,
                'image_path': str (local path to downloaded image),
                'image_urls': list (optional, original URLs from crawl)
            }

        Returns:
            {
                'inserted': int,
                'skipped': int,
                'duplicates': int,
                'errors': int,
                'stop_scraping': bool (True if batch uniqueness < threshold),
                'uniqueness_percent': float,
                'error_details': list
            }
        """
        result = {
            "inserted": 0,
            "skipped": 0,
            "duplicates": 0,
            "errors": 0,
            "stop_scraping": False,
            "uniqueness_percent": 0,
            "error_details": [],
        }

        if not products:
            return result

        unique_count = 0
        processed_hashes = set()

        for idx, product in enumerate(products):
            try:
                # Validate required fields - support both image_path (file) and image_bytes (memory)
                if not product.get("url"):
                    result["errors"] += 1
                    result["error_details"].append(f"Product {idx}: Missing URL")
                    continue

                if not product.get("image_path") and not product.get("image_bytes"):
                    result["errors"] += 1
                    result["error_details"].append(
                        f"Product {idx}: Missing both image_path and image_bytes"
                    )
                    continue

                # Check if URL already exists
                existing = SoleImage.query.filter_by(source_url=product["url"]).first()

                if existing:
                    result["duplicates"] += 1
                    self.logger.info(f"Skipping duplicate URL: {product['url']}")
                    continue

                # Prepare processed image path
                processed_path = os.path.join(
                    self.upload_folder, "sole_images", f"{uuid.uuid4()}.png"
                )
                os.makedirs(os.path.dirname(processed_path), exist_ok=True)

                # Process image - handle both in-memory (image_bytes) and file (image_path)
                original_image_bytes = None
                processed_image_bytes = None
                image_format = "PNG"  # Default format

                if product.get("image_bytes"):
                    # In-memory processing - convert bytes to PIL Image
                    from PIL import Image
                    import io

                    # Store original image bytes
                    original_image_bytes = product["image_bytes"]

                    image_pil = Image.open(io.BytesIO(original_image_bytes))

                    # Detect image format
                    image_format = image_pil.format or "PNG"

                    process_result = self.processor.process_image(
                        image_pil, save_processed_path=processed_path
                    )

                    # Convert processed image to bytes for database storage
                    if process_result.get("processed_image"):
                        processed_img = process_result["processed_image"]
                        processed_buffer = io.BytesIO()
                        processed_img.save(processed_buffer, format=image_format)
                        processed_image_bytes = processed_buffer.getvalue()

                else:
                    # File-based processing (legacy)
                    if not os.path.exists(product["image_path"]):
                        result["errors"] += 1
                        result["error_details"].append(
                            f"Product {idx}: Image file not found: {product['image_path']}"
                        )
                        continue

                    # Load file into bytes for database storage
                    with open(product["image_path"], "rb") as f:
                        original_image_bytes = f.read()

                    process_result = self.processor.process_image(
                        product["image_path"], save_processed_path=processed_path
                    )

                    # Load processed image into bytes
                    if os.path.exists(processed_path):
                        with open(processed_path, "rb") as f:
                            processed_image_bytes = f.read()

                # Calculate image hash
                image_hash = self.calculate_image_hash(process_result["image_array"])

                # Check for hash duplicates within batch
                if image_hash in processed_hashes:
                    result["duplicates"] += 1
                    continue

                processed_hashes.add(image_hash)

                # Check against database for similarity
                # For in-memory images, pass the image array directly
                is_unique = self._check_uniqueness(
                    process_result["features"],
                    image_array=process_result.get("image_array"),
                )

                if is_unique:
                    unique_count += 1
                    self.logger.debug(
                        f"Product {idx}: Unique image found - {product.get('brand')}/{product.get('product_name')}"
                    )
                else:
                    self.logger.debug(
                        f"Product {idx}: Duplicate detected - {product.get('brand')}/{product.get('product_name')}"
                    )

                # Create sole image record
                # Convert numpy types to Python native types for PostgreSQL compatibility
                quality_score = (
                    float(process_result["quality_score"])
                    if process_result.get("quality_score") is not None
                    else None
                )

                # For in-memory processing, store the image URL instead of a local path
                original_image_ref = product.get("image_url") or product.get(
                    "image_path", ""
                )

                # Get image dimensions
                image_width = None
                image_height = None
                if process_result.get("image_array") is not None:
                    height, width = process_result["image_array"].shape[:2]
                    image_width = int(width)
                    image_height = int(height)

                # Calculate file size in KB
                file_size_kb = None
                if original_image_bytes:
                    file_size_kb = len(original_image_bytes) / 1024

                sole_image = SoleImage(
                    id=str(uuid.uuid4()),
                    crawler_id=self.crawler_id,
                    source_url=product["url"],
                    brand=product.get("brand", "Unknown").strip()[:100],
                    product_type=product.get("product_type", "Unknown").strip()[:100],
                    product_name=product.get("product_name", "").strip()[:255],
                    # File paths (legacy/fallback - optional)
                    original_image_path=original_image_ref,
                    processed_image_path=processed_path,
                    # Binary data (preferred for data integrity)
                    original_image_data=original_image_bytes,
                    processed_image_data=processed_image_bytes,
                    image_format=image_format,
                    # Hash and vectors
                    image_hash=image_hash,
                    feature_vector=self.processor.serialize_features(
                        process_result["features"]
                    ),
                    lbp_histogram=process_result["features"]["lbp"].tobytes()
                    if process_result["features"].get("lbp") is not None
                    else None,
                    # Metadata
                    image_width=image_width,
                    image_height=image_height,
                    file_size_kb=file_size_kb,
                    quality_score=quality_score,
                    uniqueness_score=1.0 if is_unique else 0.5,
                    # Timestamps
                    crawled_at=datetime.utcnow(),
                    processed_at=datetime.utcnow(),
                )

                self.logger.debug(
                    f"💾 Storing image in database: "
                    f"original={len(original_image_bytes) if original_image_bytes else 0} bytes, "
                    f"processed={len(processed_image_bytes) if processed_image_bytes else 0} bytes, "
                    f"format={image_format}"
                )

                db.session.add(sole_image)
                result["inserted"] += 1

            except Exception as e:
                result["errors"] += 1
                result["error_details"].append(
                    f"Product {idx} ({product.get('url', 'unknown')}): {str(e)}"
                )
                self.logger.error(f"Error processing product {idx}: {str(e)}")

        # Calculate uniqueness percentage
        processed_count = (
            result["inserted"]
            + result["duplicates"]
            + result["skipped"]
            - result["errors"]
        )

        if processed_count > 0:
            result["uniqueness_percent"] = (unique_count / processed_count) * 100
        else:
            result["uniqueness_percent"] = 0

        # Check if we should stop scraping
        if result["uniqueness_percent"] < (self.similarity_threshold * 100):
            result["stop_scraping"] = True
            self.logger.warning(
                f"⚠️  STOP SCRAPING: Batch uniqueness {result['uniqueness_percent']:.1f}% "
                f"is below threshold {self.similarity_threshold * 100:.1f}%. "
                f"Inserted: {result['inserted']}, Duplicates: {result['duplicates']}, "
                f"Errors: {result['errors']}"
            )
        else:
            self.logger.info(
                f"✓ Batch passed uniqueness check: {result['uniqueness_percent']:.1f}% "
                f"(threshold: {self.similarity_threshold * 100:.1f}%). "
                f"Inserted: {result['inserted']}, Duplicates: {result['duplicates']}"
            )

        # Commit to database
        if result["inserted"] > 0:
            try:
                db.session.commit()

                # Update crawler statistics
                self._update_crawler_stats(result["inserted"], unique_count)

                self.logger.info(
                    f"Batch insertion complete: {result['inserted']} inserted, "
                    f"{result['duplicates']} duplicates, "
                    f"{result['errors']} errors, "
                    f"uniqueness {result['uniqueness_percent']:.1f}%"
                )
            except Exception as e:
                db.session.rollback()
                self.logger.error(f"Failed to commit batch: {str(e)}")
                result["errors"] += result["inserted"]
                result["inserted"] = 0

        return result

    def _check_uniqueness(self, features, image_path=None, image_array=None, top_n=5):
        """
        Check if features are unique in database
        Uses line_tracing for advanced shoe sole comparison
        Returns: True if image is unique (doesn't match existing > threshold)

        Args:
            features: Extracted features from image
            image_path: Path to image file (legacy, optional)
            image_array: Numpy array of image (for in-memory processing, optional)
            top_n: Number of top matches to check
        """
        try:
            # If line_tracing available and image provided (path or array), use advanced comparison
            if compare_sole_images is not None and (
                image_path is not None or image_array is not None
            ):
                # Get recent sole images from database (last 100)
                recent_images = (
                    SoleImage.query.filter_by(crawler_id=self.crawler_id)
                    .order_by(SoleImage.crawled_at.desc())
                    .limit(100)
                    .all()
                )

                max_similarity = 0

                # For file-based images, use advanced line_tracing comparison
                if image_path and os.path.exists(image_path):
                    for existing in recent_images:
                        try:
                            if existing.original_image_path and os.path.exists(
                                existing.original_image_path
                            ):
                                # Use advanced line_tracing comparison (hybrid ORB + Cosine)
                                similarity = compare_sole_images(
                                    image_path,
                                    existing.original_image_path,
                                    debug=False,
                                )
                                max_similarity = max(max_similarity, similarity)

                                # Early exit if we find high match
                                if max_similarity >= self.similarity_threshold:
                                    return False
                        except Exception as e:
                            self.logger.debug(
                                f"Error comparing with image {existing.id}: {str(e)}"
                            )
                            continue

                    # If max similarity below threshold, it's unique
                    return max_similarity < self.similarity_threshold

                # For in-memory images, fall through to feature-based comparison below

            # Fallback to standard feature comparison
            all_images = (
                SoleImage.query.filter_by(crawler_id=self.crawler_id)
                .order_by(SoleImage.crawled_at.desc())
                .limit(top_n)
                .all()
            )

            if not all_images:
                return True  # No existing images, definitely unique

            max_similarity = 0
            for existing in all_images:
                try:
                    existing_features = self.processor.deserialize_features(
                        existing.feature_vector
                    )
                    similarity = self.processor.calculate_similarity(
                        features, existing_features
                    )
                    max_similarity = max(max_similarity, similarity)

                    # Early exit if high match found
                    if max_similarity >= self.similarity_threshold:
                        return False
                except Exception as e:
                    self.logger.debug(
                        f"Error comparing features for image {existing.id}: {str(e)}"
                    )
                    continue

            # If max similarity below threshold, it's unique
            return max_similarity < self.similarity_threshold

        except Exception as e:
            self.logger.error(f"Error checking uniqueness: {str(e)}")
            return True  # Assume unique on error

    def _update_crawler_stats(self, images_added, unique_images):
        """Update crawler statistics after batch insertion"""
        try:
            self.crawler.total_images_crawled += images_added
            self.crawler.unique_images_added += unique_images

            # Update unique brands count
            unique_brands = (
                db.session.query(SoleImage.brand)
                .filter_by(crawler_id=self.crawler_id)
                .distinct()
                .count()
            )
            self.crawler.unique_brands_count = unique_brands

            self.crawler.last_completed_at = datetime.utcnow()

            db.session.commit()

            # Update global statistics
            self._update_global_stats()

        except Exception as e:
            self.logger.error(f"Error updating crawler stats: {str(e)}")

    def _update_global_stats(self):
        """Update global crawler statistics"""
        try:
            stats = CrawlerStatistics.query.first()
            if not stats:
                stats = CrawlerStatistics()
                db.session.add(stats)

            # Count unique stats across all crawlers
            stats.unique_sole_images = db.session.query(SoleImage.id).distinct().count()

            stats.unique_brands = db.session.query(SoleImage.brand).distinct().count()

            stats.total_crawlers = Crawler.query.count()

            # Calculate matching statistics
            stats.last_updated = datetime.utcnow()

            db.session.commit()

        except Exception as e:
            self.logger.error(f"Error updating global stats: {str(e)}")

    def start_crawler(self):
        """Mark crawler as running"""
        self.crawler.is_running = True
        self.crawler.last_started_at = datetime.utcnow()
        db.session.commit()
        self.logger.info(f"Crawler {self.crawler.name} started")

    def stop_crawler(self, reason="Manual stop"):
        """Mark crawler as stopped"""
        self.crawler.is_running = False
        self.crawler.last_completed_at = datetime.utcnow()

        if self.crawler.last_started_at:
            duration = (
                self.crawler.last_completed_at - self.crawler.last_started_at
            ).total_seconds()
            self.crawler.last_run_duration = duration

        db.session.commit()
        self.logger.info(f"Crawler {self.crawler.name} stopped: {reason}")

    def record_error(self, error_message):
        """Record crawler error"""
        self.crawler.last_error = error_message
        self.crawler.last_error_at = datetime.utcnow()
        db.session.commit()
        self.logger.error(f"Crawler error: {error_message}")
