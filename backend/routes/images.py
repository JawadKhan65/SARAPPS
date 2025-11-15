"""
Image Routes - Serve images from database binary storage

Provides endpoints to retrieve original and processed images directly from the database.
Falls back to filesystem if binary data is not available (legacy support).
"""

from flask import Blueprint, send_file, jsonify, Response
from models import SoleImage, UploadedImage
from extensions import db
import io
import logging

logger = logging.getLogger(__name__)

images_bp = Blueprint('images', __name__, url_prefix='/api/images')


@images_bp.route('/sole/<string:image_id>', methods=['GET'])
def get_sole_image(image_id):
    """
    Get sole image by ID
    
    Returns the processed sole image (preferred) or original if processed not available.
    Serves from database binary storage if available, falls back to filesystem.
    """
    try:
        sole_image = SoleImage.query.get(image_id)
        
        if not sole_image:
            return jsonify({"error": "Image not found"}), 404
        
        # Try to serve from binary data (preferred)
        if sole_image.processed_image_data:
            image_format = sole_image.image_format or 'PNG'
            mimetype = f'image/{image_format.lower()}'
            
            logger.debug(f"Serving processed image from database: {image_id} ({len(sole_image.processed_image_data)} bytes)")
            
            return Response(
                sole_image.processed_image_data,
                mimetype=mimetype,
                headers={
                    'Content-Disposition': f'inline; filename="{image_id}.{image_format.lower()}"',
                    'Cache-Control': 'public, max-age=31536000'  # Cache for 1 year
                }
            )
        
        elif sole_image.original_image_data:
            image_format = sole_image.image_format or 'PNG'
            mimetype = f'image/{image_format.lower()}'
            
            logger.debug(f"Serving original image from database: {image_id} ({len(sole_image.original_image_data)} bytes)")
            
            return Response(
                sole_image.original_image_data,
                mimetype=mimetype,
                headers={
                    'Content-Disposition': f'inline; filename="{image_id}.{image_format.lower()}"',
                    'Cache-Control': 'public, max-age=31536000'
                }
            )
        
        # Fallback to filesystem (legacy)
        elif sole_image.processed_image_path:
            logger.debug(f"Serving processed image from filesystem: {sole_image.processed_image_path}")
            return send_file(sole_image.processed_image_path)
        
        elif sole_image.original_image_path:
            logger.debug(f"Serving original image from filesystem: {sole_image.original_image_path}")
            return send_file(sole_image.original_image_path)
        
        else:
            return jsonify({"error": "No image data available"}), 404
            
    except Exception as e:
        logger.error(f"Error serving sole image {image_id}: {str(e)}")
        return jsonify({"error": "Failed to retrieve image"}), 500


@images_bp.route('/sole/<string:image_id>/original', methods=['GET'])
def get_sole_image_original(image_id):
    """
    Get original (unprocessed) sole image by ID
    """
    try:
        sole_image = SoleImage.query.get(image_id)
        
        if not sole_image:
            return jsonify({"error": "Image not found"}), 404
        
        # Try to serve from binary data (preferred)
        if sole_image.original_image_data:
            image_format = sole_image.image_format or 'PNG'
            mimetype = f'image/{image_format.lower()}'
            
            logger.debug(f"Serving original image from database: {image_id}")
            
            return Response(
                sole_image.original_image_data,
                mimetype=mimetype,
                headers={
                    'Content-Disposition': f'inline; filename="{image_id}_original.{image_format.lower()}"',
                    'Cache-Control': 'public, max-age=31536000'
                }
            )
        
        # Fallback to filesystem (legacy)
        elif sole_image.original_image_path:
            logger.debug(f"Serving original image from filesystem: {sole_image.original_image_path}")
            return send_file(sole_image.original_image_path)
        
        else:
            return jsonify({"error": "No original image data available"}), 404
            
    except Exception as e:
        logger.error(f"Error serving original sole image {image_id}: {str(e)}")
        return jsonify({"error": "Failed to retrieve image"}), 500


@images_bp.route('/sole/<string:image_id>/info', methods=['GET'])
def get_sole_image_info(image_id):
    """
    Get metadata about a sole image including storage information
    """
    try:
        sole_image = SoleImage.query.get(image_id)
        
        if not sole_image:
            return jsonify({"error": "Image not found"}), 404
        
        info = {
            "id": sole_image.id,
            "brand": sole_image.brand,
            "product_name": sole_image.product_name,
            "product_type": sole_image.product_type,
            "source_url": sole_image.source_url,
            "image_hash": sole_image.image_hash,
            "image_width": sole_image.image_width,
            "image_height": sole_image.image_height,
            "file_size_kb": sole_image.file_size_kb,
            "image_format": sole_image.image_format,
            "quality_score": sole_image.quality_score,
            "uniqueness_score": sole_image.uniqueness_score,
            "crawled_at": sole_image.crawled_at.isoformat() if sole_image.crawled_at else None,
            "processed_at": sole_image.processed_at.isoformat() if sole_image.processed_at else None,
            "storage": {
                "has_original_binary": sole_image.original_image_data is not None,
                "has_processed_binary": sole_image.processed_image_data is not None,
                "has_original_path": sole_image.original_image_path is not None,
                "has_processed_path": sole_image.processed_image_path is not None,
                "original_binary_size": len(sole_image.original_image_data) if sole_image.original_image_data else 0,
                "processed_binary_size": len(sole_image.processed_image_data) if sole_image.processed_image_data else 0,
            }
        }
        
        return jsonify(info), 200
        
    except Exception as e:
        logger.error(f"Error getting sole image info {image_id}: {str(e)}")
        return jsonify({"error": "Failed to retrieve image info"}), 500


@images_bp.route('/uploaded/<string:image_id>', methods=['GET'])
def get_uploaded_image(image_id):
    """
    Get user-uploaded image by ID
    """
    try:
        uploaded_image = UploadedImage.query.get(image_id)
        
        if not uploaded_image:
            return jsonify({"error": "Image not found"}), 404
        
        # For uploaded images, serve from filesystem for now
        # TODO: Migrate uploaded images to binary storage as well
        if uploaded_image.processed_image_path:
            return send_file(uploaded_image.processed_image_path)
        elif uploaded_image.file_path:
            return send_file(uploaded_image.file_path)
        else:
            return jsonify({"error": "No image data available"}), 404
            
    except Exception as e:
        logger.error(f"Error serving uploaded image {image_id}: {str(e)}")
        return jsonify({"error": "Failed to retrieve image"}), 500

