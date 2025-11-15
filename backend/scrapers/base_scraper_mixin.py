"""
Base Scraper Mixin - Reusable functionality for all scrapers
Provides in-memory image processing and batch callback support
"""

import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Default user agent to use for requests
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"


class BatchProcessingMixin:
    """Mixin to add batch processing and in-memory image download capabilities to scrapers"""
    
    def _download_image_to_memory(self, image_url: str, user_agent: str = DEFAULT_USER_AGENT) -> Optional[bytes]:
        """Download image directly to memory as bytes - no disk I/O
        
        Args:
            image_url: URL of the image to download
            user_agent: User agent string to use for the request
            
        Returns:
            bytes: Image data in memory, or None if download failed
        """
        import requests
        
        try:
            headers = {"User-Agent": user_agent}
            response = requests.get(image_url, timeout=10, headers=headers)
            response.raise_for_status()
            logger.debug(f"Downloaded image to memory: {len(response.content)} bytes from {image_url}")
            return response.content
        except Exception as e:
            logger.error(f"Failed to download image {image_url}: {e}")
            return None
    
    def _prepare_batch_for_processing(
        self, 
        batch: List[Dict], 
        brand_field: str = "brand",
        name_field: str = "name", 
        url_field: str = "url",
        image_url_field: str = "last_image_url",
        product_type: str = "shoe",
        user_agent: str = DEFAULT_USER_AGENT
    ) -> List[Dict]:
        """Download images to memory and prepare batch for processing
        
        Args:
            batch: List of product dictionaries from scraper
            brand_field: Field name containing brand
            name_field: Field name containing product name
            url_field: Field name containing product URL
            image_url_field: Field name containing image URL
            product_type: Type of product (default: "shoe")
            user_agent: User agent for image download requests
            
        Returns:
            List of products formatted for scraper_service with in-memory images
        """
        processed_batch = []
        
        logger.debug(f"📋 Preparing batch with field mappings: url_field='{url_field}', brand_field='{brand_field}', name_field='{name_field}', image_url_field='{image_url_field}'")
        
        for idx, product in enumerate(batch):
            logger.debug(f"  Product {idx}: keys={list(product.keys())}")
            
            # Download image to memory if available
            image_bytes = None
            image_url = product.get(image_url_field)
            product_url = product.get(url_field, "")
            
            logger.debug(f"  Product {idx}: url={product_url}, image_url={image_url[:50] if image_url else 'None'}...")
            
            if image_url:
                image_bytes = self._download_image_to_memory(image_url, user_agent)
            
            if image_bytes:
                # Convert to format expected by scraper_service
                processed_product = {
                    "url": product_url,
                    "brand": product.get(brand_field, "Unknown"),
                    "product_name": product.get(name_field, "Unknown"),
                    "product_type": product_type,
                    "image_bytes": image_bytes,  # In-memory image data
                    "image_url": image_url,  # Keep URL for reference
                }
                logger.debug(f"  ✅ Product {idx} processed: {processed_product['brand']} - {processed_product['product_name']} ({processed_product['url']})")
                processed_batch.append(processed_product)
            else:
                logger.warning(f"  ⚠️  Product {idx}: Skipping - no image bytes (url={product_url})")
        
        logger.info(f"✅ Prepared {len(processed_batch)}/{len(batch)} products with images")
        return processed_batch
    
    async def _process_batch_with_callback(
        self,
        current_batch: List[Dict],
        batch_callback,
        **prepare_kwargs
    ) -> bool:
        """Process a batch with the provided callback
        
        Args:
            current_batch: List of scraped products
            batch_callback: Async function to call with processed batch
            **prepare_kwargs: Additional kwargs for _prepare_batch_for_processing
            
        Returns:
            bool: True to continue scraping, False to stop
        """
        if not current_batch or not batch_callback:
            return True
        
        logger.info(f"Preparing batch of {len(current_batch)} products for processing...")
        
        # Download images to memory and prepare batch
        processed_batch = self._prepare_batch_for_processing(current_batch, **prepare_kwargs)
        
        if processed_batch:
            logger.info(f"Processing {len(processed_batch)} products with images...")
            should_continue = await batch_callback(processed_batch)
            
            if not should_continue:
                logger.warning("Batch callback returned False, stopping scraper")
                return False
        else:
            logger.warning("No products with images in this batch, continuing...")
        
        return True

