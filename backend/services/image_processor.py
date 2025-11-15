import os
import sys
import numpy as np
from PIL import Image
from skimage.feature import local_binary_pattern
import cv2
import pickle

# Add line_tracing module to path
line_tracing_path = os.path.join(os.path.dirname(__file__), "..", "line_tracing_utils")
sys.path.insert(0, line_tracing_path)

try:
    from line_tracing import extract_shoeprint_features, process_reference_sole
except ImportError:
    extract_shoeprint_features = None
    process_reference_sole = None


class ImageProcessor:
    """Process images for sole matching"""

    def __init__(self, clip_model=None):
        self.clip_model = clip_model
        self.lbp_radius = 1
        self.lbp_points = 8

    def load_image(self, image_path):
        """Load image from file"""
        try:
            img = Image.open(image_path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            return img
        except Exception as e:
            raise ValueError(f"Failed to load image: {str(e)}")

    def validate_image(self, image, min_width=50, min_height=50):
        """Validate image dimensions"""
        width, height = image.size
        if width < min_width or height < min_height:
            raise ValueError(
                f"Image too small: {width}x{height}, minimum {min_width}x{min_height}"
            )
        return True

    def extract_lbp_features(self, image_array):
        """Extract Local Binary Pattern (texture) features from image"""
        if len(image_array.shape) == 3:
            # Convert to grayscale
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = image_array

        # Compute LBP
        lbp = local_binary_pattern(
            gray, self.lbp_points, self.lbp_radius, method="uniform"
        )

        # Create histogram of LBP values
        hist, _ = np.histogram(lbp.ravel(), bins=59, range=(0, 59))

        # Normalize histogram
        hist = hist.astype(np.float32)
        hist /= hist.sum() + 1e-6

        return hist

    def extract_clip_features(self, image_array):
        """Extract CLIP features using the model"""
        if self.clip_model is None:
            return None

        try:
            from PIL import Image
            import torch
            from torchvision.transforms import (
                Compose,
                Resize,
                CenterCrop,
                ToTensor,
                Normalize,
            )

            # Prepare image for CLIP
            preprocess = Compose(
                [
                    Resize(224, interpolation=Image.BICUBIC),
                    CenterCrop(224),
                    ToTensor(),
                    Normalize(
                        (0.48145466, 0.4578275, 0.40821073),
                        (0.26862954, 0.26130258, 0.27577711),
                    ),
                ]
            )

            image = Image.fromarray(image_array.astype("uint8"))
            image_input = preprocess(image).unsqueeze(0)

            with torch.no_grad():
                image_features = self.clip_model.encode_image(image_input)

            return image_features.cpu().numpy().flatten()
        except Exception:
            return None

    def extract_line_tracing_features(self, image_array, image_path=None):
        """Extract features using line tracing module"""
        if extract_shoeprint_features is None or image_path is None:
            return None

        try:
            # Extract comprehensive shoeprint features
            (
                l_channel,
                a_channel,
                b_channel,
                denoised_l,
                enhanced_l,
                binary_pattern,
                cleaned_pattern,
                lbp,
                lbp_features,
            ) = extract_shoeprint_features(image_path)

            # Create feature vector from LBP features
            if lbp_features.size > 0:
                # Compute histogram of LBP values
                hist, _ = np.histogram(lbp_features, bins=59, range=(0, 59))
                hist = hist.astype(np.float32) / (hist.sum() + 1e-6)
                return hist
            else:
                return None
        except Exception:
            return None

    def extract_edge_features(self, image_array):
        """Extract edge and contour features"""
        if len(image_array.shape) == 3:
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = image_array

        # Canny edge detection
        edges = cv2.Canny(gray, 50, 150)

        # Dilate to connect nearby edges
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=2)

        # Create histogram of edge orientations
        sobelx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)

        angles = np.arctan2(sobely, sobelx)
        hist_edges, _ = np.histogram(angles, bins=32, range=(-np.pi, np.pi))
        hist_edges = hist_edges.astype(np.float32) / (hist_edges.sum() + 1e-6)

        return hist_edges

    def extract_color_features(self, image_array):
        """Extract color histogram features"""
        # Resize for faster processing
        small_image = cv2.resize(image_array, (32, 32))

        # Extract color histogram
        hist_b = cv2.calcHist([small_image], [0], None, [32], [0, 256])
        hist_g = cv2.calcHist([small_image], [1], None, [32], [0, 256])
        hist_r = cv2.calcHist([small_image], [2], None, [32], [0, 256])

        # Normalize and concatenate
        hist = np.concatenate(
            [
                hist_b.flatten() / (hist_b.sum() + 1e-6),
                hist_g.flatten() / (hist_g.sum() + 1e-6),
                hist_r.flatten() / (hist_r.sum() + 1e-6),
            ]
        ).astype(np.float32)

        return hist

    def process_image(self, image_path, save_processed_path=None):
        """
        Process image and extract all features
        Returns: dict with all extracted features
        """
        # Load and validate image
        image = self.load_image(image_path)
        self.validate_image(image)

        # Convert to numpy array
        image_array = np.array(image)

        # Extract features
        features = {
            "lbp": self.extract_lbp_features(image_array),
            "edge": self.extract_edge_features(image_array),
            "color": self.extract_color_features(image_array),
            "clip": self.extract_clip_features(image_array),
            "line_tracing": self.extract_line_tracing_features(image_array, image_path),
        }

        # Calculate image quality score (0-1)
        # Based on contrast and sharpness
        gray = (
            cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
            if len(image_array.shape) == 3
            else image_array
        )
        contrast = gray.std() / 255.0
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness = laplacian_var / 5000.0  # Normalized
        quality_score = min(1.0, (contrast + sharpness) / 2.0)

        # Create processed image (resized for storage)
        processed_image = image.resize((512, 512), Image.Resampling.LANCZOS)
        
        result = {
            "features": features,
            "quality_score": quality_score,
            "image_size": image.size,
            "image_array": image_array,
            "processed_image": processed_image,  # Return processed image for in-memory storage
        }

        if save_processed_path:
            # Save processed image to disk (for legacy/fallback)
            processed_image.save(save_processed_path, quality=85)

        return result

    def serialize_features(self, features_dict):
        """Serialize feature dict to bytes for storage"""
        try:
            return pickle.dumps(features_dict)
        except Exception as e:
            raise ValueError(f"Failed to serialize features: {str(e)}")

    def deserialize_features(self, features_bytes):
        """Deserialize features from bytes"""
        try:
            return pickle.loads(features_bytes)
        except Exception as e:
            raise ValueError(f"Failed to deserialize features: {str(e)}")

    def calculate_similarity(self, features1, features2):
        """
        Calculate similarity between two feature sets
        Returns: similarity score (0-1)
        """
        if not features1 or not features2:
            return 0.0

        similarities = []

        # LBP similarity (histogram intersection)
        if "lbp" in features1 and "lbp" in features2:
            lbp_sim = np.minimum(features1["lbp"], features2["lbp"]).sum()
            similarities.append(lbp_sim)

        # Edge similarity
        if "edge" in features1 and "edge" in features2:
            edge_sim = np.minimum(features1["edge"], features2["edge"]).sum()
            similarities.append(edge_sim)

        # Color similarity
        if "color" in features1 and "color" in features2:
            color_sim = 1.0 - np.linalg.norm(
                features1["color"] - features2["color"]
            ) / np.sqrt(2)
            color_sim = max(0, color_sim)
            similarities.append(color_sim)

        # CLIP similarity (cosine if both available)
        if features1.get("clip") is not None and features2.get("clip") is not None:
            clip1 = features1["clip"] / (np.linalg.norm(features1["clip"]) + 1e-8)
            clip2 = features2["clip"] / (np.linalg.norm(features2["clip"]) + 1e-8)
            clip_sim = np.dot(clip1, clip2)
            similarities.append((clip_sim + 1) / 2)  # Normalize to 0-1

        # Line tracing similarity
        if (
            features1.get("line_tracing") is not None
            and features2.get("line_tracing") is not None
        ):
            lt1 = features1["line_tracing"]
            lt2 = features2["line_tracing"]
            if len(lt1) > 0 and len(lt2) > 0:
                lt_sim = 1.0 - np.linalg.norm(lt1 - lt2) / (
                    np.linalg.norm(lt1) + np.linalg.norm(lt2) + 1e-8
                )
                lt_sim = max(0, lt_sim)
                similarities.append(lt_sim)

        if not similarities:
            return 0.0

        # Weighted average: LBP=0.3, Edge=0.25, Color=0.2, CLIP=0.15, LineTracing=0.1
        weights = [0.3, 0.25, 0.2, 0.15, 0.1][: len(similarities)]
        total_weight = sum(weights)
        weighted_sim = sum(s * w for s, w in zip(similarities, weights)) / total_weight

        return float(weighted_sim)
