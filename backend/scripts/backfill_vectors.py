"""
Backfill Vector Embeddings for Existing Images

This script processes existing images in the database and populates the
vector embedding columns (clip_embedding, edge_embedding, texture_embedding)
for fast similarity search using pgvector.

Usage:
    python scripts/backfill_vectors.py
    python scripts/backfill_vectors.py --batch-size 50
    python scripts/backfill_vectors.py --start-offset 1000
"""

import sys
import click
import logging
from pathlib import Path
from datetime import datetime
import numpy as np
import cv2 as cv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from core.models import SoleImage
from services.image_processor import ImageProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def backfill_vectors(batch_size=100, start_offset=0, limit=None):
    """
    Backfill vector embeddings for existing sole images
    
    Args:
        batch_size: Number of images to process per batch
        start_offset: Skip first N images (useful for resuming)
        limit: Maximum number of images to process (None for all)
    """
    logger.info("=" * 60)
    logger.info("VECTOR EMBEDDINGS BACKFILL")
    logger.info("=" * 60)
    
    processor = ImageProcessor()
    
    # Count total images
    total_query = SoleImage.query
    if limit:
        total_query = total_query.limit(limit)
    
    total_images = SoleImage.query.count()
    images_to_process = limit if limit else (total_images - start_offset)
    
    logger.info(f"Total images in database: {total_images}")
    logger.info(f"Starting from offset: {start_offset}")
    logger.info(f"Images to process: {images_to_process}")
    logger.info(f"Batch size: {batch_size}")
    logger.info("-" * 60)
    
    processed_count = 0
    success_count = 0
    error_count = 0
    skip_count = 0
    
    start_time = datetime.now()
    
    # Process in batches
    current_offset = start_offset
    remaining = images_to_process
    
    while remaining > 0:
        current_batch_size = min(batch_size, remaining)
        batch_num = (current_offset - start_offset) // batch_size + 1
        total_batches = (images_to_process - 1) // batch_size + 1
        
        logger.info(f"\n📦 Processing batch {batch_num}/{total_batches} "
                   f"(offset: {current_offset}, size: {current_batch_size})")
        
        # Fetch batch
        images = SoleImage.query.offset(current_offset).limit(current_batch_size).all()
        
        if not images:
            logger.info("No more images to process")
            break
        
        batch_success = 0
        batch_errors = 0
        batch_skipped = 0
        
        for sole_image in images:
            processed_count += 1
            
            try:
                # Skip if vectors already exist
                if (sole_image.clip_embedding is not None and
                    sole_image.edge_embedding is not None and
                    sole_image.texture_embedding is not None):
                    skip_count += 1
                    batch_skipped += 1
                    logger.debug(f"  ⏭️  {sole_image.id[:8]}... (already has vectors)")
                    continue
                
                # Load image from database binary data (preferred)
                if sole_image.processed_image_data:
                    img_array = cv.imdecode(
                        np.frombuffer(sole_image.processed_image_data, np.uint8),
                        cv.IMREAD_COLOR
                    )
                elif sole_image.original_image_data:
                    img_array = cv.imdecode(
                        np.frombuffer(sole_image.original_image_data, np.uint8),
                        cv.IMREAD_COLOR
                    )
                elif sole_image.processed_image_path:
                    img_array = cv.imread(sole_image.processed_image_path, cv.IMREAD_COLOR)
                elif sole_image.original_image_path:
                    img_array = cv.imread(sole_image.original_image_path, cv.IMREAD_COLOR)
                else:
                    logger.warning(f"  ✗ {sole_image.id[:8]}... No image data available")
                    error_count += 1
                    batch_errors += 1
                    continue
                
                if img_array is None:
                    logger.warning(f"  ✗ {sole_image.id[:8]}... Failed to decode image")
                    error_count += 1
                    batch_errors += 1
                    continue
                
                # Extract vector embeddings
                vectors = processor.extract_vector_embeddings(
                    img_array,
                    sole_image.processed_image_path or sole_image.original_image_path
                )
                
                # Update database record with vectors
                if vectors.get('clip_vector') is not None:
                    sole_image.clip_embedding = vectors['clip_vector'].tolist()
                if vectors.get('edge_vector') is not None:
                    sole_image.edge_embedding = vectors['edge_vector'].tolist()
                if vectors.get('texture_vector') is not None:
                    sole_image.texture_embedding = vectors['texture_vector'].tolist()
                
                success_count += 1
                batch_success += 1
                
                logger.debug(
                    f"  ✓ {sole_image.id[:8]}... {sole_image.brand} - {sole_image.product_type}"
                )
                
            except Exception as e:
                logger.error(f"  ✗ {sole_image.id[:8]}... Error: {str(e)}")
                error_count += 1
                batch_errors += 1
                continue
        
        # Commit batch
        try:
            db.session.commit()
            logger.info(
                f"  💾 Batch {batch_num} committed: "
                f"✓ {batch_success} success, ✗ {batch_errors} errors, ⏭️  {batch_skipped} skipped"
            )
        except Exception as e:
            logger.error(f"  ✗ Failed to commit batch {batch_num}: {str(e)}")
            db.session.rollback()
        
        # Progress report
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = processed_count / elapsed if elapsed > 0 else 0
        eta_seconds = (images_to_process - processed_count) / rate if rate > 0 else 0
        eta_minutes = eta_seconds / 60
        
        logger.info(
            f"  📊 Progress: {processed_count}/{images_to_process} "
            f"({processed_count/images_to_process*100:.1f}%) | "
            f"Rate: {rate:.1f} img/s | ETA: {eta_minutes:.1f} min"
        )
        
        current_offset += current_batch_size
        remaining -= current_batch_size
    
    # Final summary
    elapsed_total = (datetime.now() - start_time).total_seconds()
    
    logger.info("\n" + "=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("=" * 60)
    logger.info(f"✓ Successfully processed: {success_count}")
    logger.info(f"⏭️  Skipped (already had vectors): {skip_count}")
    logger.info(f"✗ Errors: {error_count}")
    logger.info(f"⏱️  Total time: {elapsed_total/60:.1f} minutes")
    logger.info(f"📈 Average rate: {processed_count/elapsed_total:.1f} images/second")
    logger.info("=" * 60)
    
    # Remind about indexes
    if success_count > 0:
        logger.info("\n⚠️  IMPORTANT: After backfilling, rebuild vector indexes for optimal performance:")
        logger.info("   Run: python scripts/init_db.py init")
        logger.info("   Or manually rebuild:")
        logger.info("   REINDEX INDEX idx_sole_images_clip_embedding;")
        logger.info("   REINDEX INDEX idx_sole_images_edge_embedding;")
        logger.info("   REINDEX INDEX idx_sole_images_texture_embedding;")
    
    return success_count, error_count, skip_count


@click.command()
@click.option('--batch-size', default=100, help='Number of images to process per batch')
@click.option('--start-offset', default=0, help='Skip first N images (for resuming)')
@click.option('--limit', default=None, type=int, help='Maximum number of images to process')
@click.option('--dry-run', is_flag=True, help='Run without committing changes')
def main(batch_size, start_offset, limit, dry_run):
    """Backfill vector embeddings for existing images"""
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be committed")
    
    app = create_app()
    
    with app.app_context():
        try:
            if dry_run:
                logger.info("Dry run completed - no changes made")
            else:
                backfill_vectors(batch_size, start_offset, limit)
        except KeyboardInterrupt:
            logger.warning("\n⚠️  Process interrupted by user")
            logger.info("Progress has been saved. You can resume with:")
            logger.info(f"   python scripts/backfill_vectors.py --start-offset {start_offset + batch_size}")
        except Exception as e:
            logger.error(f"✗ Backfill failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise


if __name__ == "__main__":
    main()

