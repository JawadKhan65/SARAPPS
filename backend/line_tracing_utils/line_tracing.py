import cv2 as cv
import numpy as np
from skimage.feature import local_binary_pattern
from skimage.metrics import structural_similarity as ssim


def process_reference_sole(
    img, target_size=(512, 512), keep_aspect=True, use_polar=True, debug=False
):
    """
    Robust preprocessing pipeline for shoe sole matching.
    Returns multiple representations for comprehensive matching.

    Args:
        img: Input image (grayscale or color)
        target_size: Target dimensions (width, height)
        keep_aspect: Maintain aspect ratio (pad to fit)
        use_polar: Apply polar transform for rotation invariance
        debug: Show debug visualizations
    """
    # Ensure grayscale
    if len(img.shape) == 3:
        img = cv.cvtColor(img, cv.COLOR_BGR2GRAY)

    # Resize with optional aspect ratio preservation
    if keep_aspect:
        h, w = img.shape[:2]
        scale = min(target_size[0] / w, target_size[1] / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv.resize(img, (new_w, new_h), interpolation=cv.INTER_AREA)

        # Pad into centered canvas
        canvas = np.zeros(target_size[::-1], dtype=np.uint8)
        y_off = (target_size[1] - new_h) // 2
        x_off = (target_size[0] - new_w) // 2
        canvas[y_off : y_off + new_h, x_off : x_off + new_w] = resized
        processed = canvas
    else:
        processed = cv.resize(img, target_size, interpolation=cv.INTER_AREA)

    # Multiple enhancement passes
    # Pass 1: Denoise
    denoised = cv.fastNlMeansDenoising(
        processed, None, h=10, templateWindowSize=7, searchWindowSize=21
    )

    # Pass 2: CLAHE for contrast
    clahe = cv.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    # Pass 3: Edge detection with multiple methods
    # Canny edges
    canny = cv.Canny(enhanced, 50, 150)

    # Sobel edges
    sobelX = cv.Sobel(enhanced, cv.CV_16S, 1, 0, ksize=3)
    sobelY = cv.Sobel(enhanced, cv.CV_16S, 0, 1, ksize=3)
    absX = cv.convertScaleAbs(sobelX)
    absY = cv.convertScaleAbs(sobelY)
    sobel = cv.addWeighted(absX, 0.5, absY, 0.5, 0)

    # Combine edge methods
    combined_edges = cv.bitwise_or(canny, sobel)

    # Morphological refinement
    kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (3, 3))
    refined = cv.morphologyEx(combined_edges, cv.MORPH_CLOSE, kernel, iterations=2)
    refined = cv.morphologyEx(refined, cv.MORPH_OPEN, kernel, iterations=1)

    # Apply polar transform for rotation invariance if requested
    if use_polar:
        center = (target_size[0] // 2, target_size[1] // 2)
        max_radius = min(center)
        polar_refined = cv.warpPolar(
            refined,
            dsize=target_size,
            center=center,
            maxRadius=max_radius,
            flags=cv.WARP_POLAR_LINEAR,
        )
        # Also create polar version of enhanced image
        polar_enhanced = cv.warpPolar(
            enhanced,
            dsize=target_size,
            center=center,
            maxRadius=max_radius,
            flags=cv.WARP_POLAR_LINEAR,
        )
    else:
        polar_refined = None
        polar_enhanced = None

    if debug:
        cv.imshow("Original", img)
        cv.imshow("Enhanced", enhanced)
        cv.imshow("Canny", canny)
        cv.imshow("Sobel", sobel)
        cv.imshow("Refined Edges", refined)
        if use_polar and polar_refined is not None:
            cv.imshow("Polar Edges", polar_refined)
            cv.imshow("Polar Enhanced", polar_enhanced)
        cv.waitKey(0)
        cv.destroyAllWindows()

    # Return both enhanced and edges for rich feature extraction
    # If use_polar is True, return polar-transformed versions (rotation invariant)
    # Otherwise return regular versions
    if use_polar and polar_refined is not None:
        return {
            "enhanced": polar_enhanced,
            "edges": polar_refined
        }
    else:
        return {
            "enhanced": enhanced,
            "edges": refined
        }


def extract_robust_features(processed_dict):
    """
    Extract multiple feature types for robust matching.
    """
    enhanced = processed_dict["enhanced"]
    edges = processed_dict["edges"]

    features = {}

    # 1. SIFT features (scale and rotation invariant, better than ORB)
    sift = cv.SIFT_create(nfeatures=5000, contrastThreshold=0.03, edgeThreshold=10)
    kp_sift, des_sift = sift.detectAndCompute(enhanced, None)
    features["sift_kp"] = kp_sift
    features["sift_des"] = des_sift

    # 2. ORB features (fast, binary)
    orb = cv.ORB_create(nfeatures=10000, scaleFactor=1.2, nlevels=8)
    kp_orb, des_orb = orb.detectAndCompute(edges, None)
    features["orb_kp"] = kp_orb
    features["orb_des"] = des_orb

    # 3. AKAZE features (good for textured patterns)
    akaze = cv.AKAZE_create()
    kp_akaze, des_akaze = akaze.detectAndCompute(enhanced, None)
    features["akaze_kp"] = kp_akaze
    features["akaze_des"] = des_akaze

    # 4. HOG descriptor (good for shape)
    win_size = (enhanced.shape[1] // 8 * 8, enhanced.shape[0] // 8 * 8)
    if win_size[0] > 0 and win_size[1] > 0:
        resized_for_hog = cv.resize(enhanced, win_size)
        hog = cv.HOGDescriptor(win_size, (16, 16), (8, 8), (8, 8), 9)
        hog_features = hog.compute(resized_for_hog)
        features["hog"] = hog_features.flatten() if hog_features is not None else None
    else:
        features["hog"] = None

    # 5. Contour features
    contours, _ = cv.findContours(edges, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    if contours:
        largest_contour = max(contours, key=cv.contourArea)
        features["contour_area"] = cv.contourArea(largest_contour)
        features["contour_perimeter"] = cv.arcLength(largest_contour, True)
        features["contour"] = largest_contour
    else:
        features["contour_area"] = 0
        features["contour_perimeter"] = 0
        features["contour"] = None

    return features


def match_sift_features(des1, des2, kp1, kp2, ratio_thresh=0.75):
    """SIFT matching with ratio test and spatial verification."""
    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        return 0, 0, []

    # FLANN matcher for SIFT
    FLANN_INDEX_KDTREE = 1
    index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
    search_params = dict(checks=50)
    flann = cv.FlannBasedMatcher(index_params, search_params)

    matches = flann.knnMatch(des1, des2, k=2)

    # Ratio test
    good_matches = []
    for m_n in matches:
        if len(m_n) == 2:
            m, n = m_n
            if m.distance < ratio_thresh * n.distance:
                good_matches.append(m)

    if len(good_matches) < 4:
        return 0, 0, good_matches

    # RANSAC verification
    src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    M, mask = cv.findHomography(src_pts, dst_pts, cv.RANSAC, 5.0)

    if mask is None:
        return len(good_matches) / max(len(kp1), len(kp2)), 0, good_matches

    inliers = mask.ravel().sum()
    spatial_conf = inliers / len(good_matches)
    match_ratio = len(good_matches) / max(len(kp1), len(kp2))

    return match_ratio, spatial_conf, good_matches


def match_orb_features(des1, des2, kp1, kp2, ratio_thresh=0.85):
    """ORB matching with Hamming distance."""
    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        return 0, 0, []

    bf = cv.BFMatcher(cv.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(des1, des2, k=2)

    good_matches = []
    for m_n in matches:
        if len(m_n) == 2:
            m, n = m_n
            if m.distance < ratio_thresh * n.distance:
                good_matches.append(m)

    if len(good_matches) < 4:
        return 0, 0, good_matches

    # RANSAC verification
    src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    M, mask = cv.findHomography(src_pts, dst_pts, cv.RANSAC, 5.0)

    if mask is None:
        return len(good_matches) / max(len(kp1), len(kp2)), 0, good_matches

    inliers = mask.ravel().sum()
    spatial_conf = inliers / len(good_matches)
    match_ratio = len(good_matches) / max(len(kp1), len(kp2))

    return match_ratio, spatial_conf, good_matches


def match_akaze_features(des1, des2, kp1, kp2, ratio_thresh=0.80):
    """AKAZE matching."""
    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        return 0, 0, []

    bf = cv.BFMatcher(cv.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(des1, des2, k=2)

    good_matches = []
    for m_n in matches:
        if len(m_n) == 2:
            m, n = m_n
            if m.distance < ratio_thresh * n.distance:
                good_matches.append(m)

    if len(good_matches) < 4:
        return 0, 0, good_matches

    match_ratio = len(good_matches) / max(len(kp1), len(kp2))

    # RANSAC verification
    src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    M, mask = cv.findHomography(src_pts, dst_pts, cv.RANSAC, 5.0)

    if mask is None:
        return match_ratio, 0, good_matches

    inliers = mask.ravel().sum()
    spatial_conf = inliers / len(good_matches)

    return match_ratio, spatial_conf, good_matches


def compare_sole_images(img1, img2, debug=False):
    """
    COMPLETELY REDESIGNED: Multi-algorithm ensemble matching.

    This uses multiple feature detectors and sophisticated scoring
    to ensure related soles are matched even with variations.

    Args:
        img1: Query image (uploaded by user, will be fully processed)
        img2: Database image (already processed with polar transform)
        debug: Show detailed comparison info
    """
    # Process query image (img1) with polar transform
    processed1 = process_reference_sole(img1, use_polar=True, debug=False)

    # img2 should be a dict with 'enhanced' and 'edges', but handle backward compatibility
    if isinstance(img2, dict):
        processed2 = img2
    else:
        # Old format: single matrix (assume it's edges)
        processed2 = {"edges": img2, "enhanced": img2}

    # Use the processed dictionaries directly
    features1_dict = processed1
    features2_dict = processed2

    # Extract comprehensive features
    features1 = extract_robust_features(features1_dict)
    features2 = extract_robust_features(features2_dict)

    scores = {}

    # === 1. SIFT Matching (PRIMARY - Best for shoe soles) ===
    sift_ratio, sift_spatial, sift_matches = match_sift_features(
        features1["sift_des"],
        features2["sift_des"],
        features1["sift_kp"],
        features2["sift_kp"],
        ratio_thresh=0.75,
    )
    # Boost score with spatial confidence
    sift_score = (
        sift_ratio * (0.5 + 0.5 * sift_spatial) if sift_spatial > 0 else sift_ratio
    )
    scores["sift"] = min(1.0, sift_score * 1.5)  # Amplify SIFT since it's most reliable

    # === 2. ORB Matching (SECONDARY - Fast verification) ===
    orb_ratio, orb_spatial, orb_matches = match_orb_features(
        features1["orb_des"],
        features2["orb_des"],
        features1["orb_kp"],
        features2["orb_kp"],
        ratio_thresh=0.85,
    )
    orb_score = orb_ratio * (0.5 + 0.5 * orb_spatial) if orb_spatial > 0 else orb_ratio
    scores["orb"] = orb_score

    # === 3. AKAZE Matching (TERTIARY - Texture patterns) ===
    akaze_ratio, akaze_spatial, akaze_matches = match_akaze_features(
        features1["akaze_des"],
        features2["akaze_des"],
        features1["akaze_kp"],
        features2["akaze_kp"],
        ratio_thresh=0.80,
    )
    akaze_score = (
        akaze_ratio * (0.5 + 0.5 * akaze_spatial) if akaze_spatial > 0 else akaze_ratio
    )
    scores["akaze"] = akaze_score

    # === 4. HOG Similarity (Shape descriptor) ===
    if features1["hog"] is not None and features2["hog"] is not None:
        hog1_norm = features1["hog"] / (np.linalg.norm(features1["hog"]) + 1e-8)
        hog2_norm = features2["hog"] / (np.linalg.norm(features2["hog"]) + 1e-8)
        hog_sim = np.dot(hog1_norm, hog2_norm)
        scores["hog"] = (hog_sim + 1) / 2  # Map to [0, 1]
    else:
        scores["hog"] = 0

    # === 5. SSIM (Structural Similarity) ===
    # Use edges for SSIM comparison (polar transformed)
    ssim_score = ssim(features1_dict["edges"], features2_dict["edges"], data_range=255)
    scores["ssim"] = max(0, ssim_score)

    # === 6. Template Matching (Multi-scale) ===
    template_scores = []
    scales = [0.8, 0.9, 1.0, 1.1, 1.2]
    edge1 = features1_dict["edges"]
    edge2 = features2_dict["edges"]

    for scale in scales:
        try:
            h, w = edge1.shape
            new_h, new_w = int(h * scale), int(w * scale)
            if 50 < new_h < edge2.shape[0] and 50 < new_w < edge2.shape[1]:
                scaled = cv.resize(edge1, (new_w, new_h))
                result = cv.matchTemplate(edge2, scaled, cv.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv.minMaxLoc(result)
                template_scores.append(max_val)
        except Exception as e:
            # Template matching can fail at certain scales, continue with other scales
            pass
    scores["template"] = max(template_scores) if template_scores else 0

    # === 7. Contour Matching ===
    if features1["contour"] is not None and features2["contour"] is not None:
        contour_match = cv.matchShapes(
            features1["contour"], features2["contour"], cv.CONTOURS_MATCH_I1, 0
        )
        # Lower is better for matchShapes, convert to similarity
        scores["contour"] = 1 / (1 + contour_match)
    else:
        scores["contour"] = 0

    # === 8. Normalized Cross-Correlation ===
    if edge1.shape == edge2.shape:
        result = cv.matchTemplate(edge1, edge2, cv.TM_CCORR_NORMED)
        scores["ncc"] = max(0, min(1, result[0][0]))
    else:
        scores["ncc"] = 0

    # === INTELLIGENT ENSEMBLE SCORING ===
    # If ANY strong signal exists, boost the score
    max_feature_score = max(scores["sift"], scores["orb"], scores["akaze"])

    # Adaptive weights based on feature quality
    if max_feature_score > 0.3:  # Strong feature match found
        weights = {
            "sift": 0.40,
            "orb": 0.20,
            "akaze": 0.15,
            "ssim": 0.10,
            "hog": 0.05,
            "template": 0.05,
            "contour": 0.03,
            "ncc": 0.02,
        }
    else:  # Rely more on global metrics
        weights = {
            "sift": 0.25,
            "orb": 0.15,
            "akaze": 0.10,
            "ssim": 0.20,
            "hog": 0.10,
            "template": 0.10,
            "contour": 0.05,
            "ncc": 0.05,
        }

    final_score = sum(weights[k] * scores[k] for k in weights.keys())

    # Boost if multiple strong signals
    strong_signals = sum(
        1 for s in [scores["sift"], scores["orb"], scores["akaze"]] if s > 0.25
    )
    if strong_signals >= 2:
        final_score = min(1.0, final_score * 1.2)

    # Boost if spatial confidence is very high
    if sift_spatial > 0.7 or orb_spatial > 0.7:
        final_score = min(1.0, final_score * 1.15)

    if debug:
        print(f"\n{'=' * 60}")
        print(f"COMPREHENSIVE SHOE SOLE MATCHING ANALYSIS")
        print(f"{'=' * 60}")
        print(f"\n--- Feature Matching ---")
        print(
            f"SIFT: {scores['sift']:.3f} ({len(sift_matches)} matches, spatial: {sift_spatial:.3f})"
        )
        print(
            f"ORB:  {scores['orb']:.3f} ({len(orb_matches)} matches, spatial: {orb_spatial:.3f})"
        )
        print(
            f"AKAZE: {scores['akaze']:.3f} ({len(akaze_matches)} matches, spatial: {akaze_spatial:.3f})"
        )
        print(f"\n--- Global Metrics ---")
        print(f"HOG:      {scores['hog']:.3f}")
        print(f"SSIM:     {scores['ssim']:.3f}")
        print(f"Template: {scores['template']:.3f}")
        print(f"Contour:  {scores['contour']:.3f}")
        print(f"NCC:      {scores['ncc']:.3f}")
        print(f"\n--- Final Result ---")
        print(f"Weighted Score: {final_score:.3f}")
        print(f"Strong Signals: {strong_signals}/3")
        print(f"Max Feature Score: {max_feature_score:.3f}")
        print(f"{'=' * 60}\n")

        # Visualize best matches
        if len(sift_matches) > 0:
            sift_vis = cv.drawMatches(
                features1_dict["enhanced"],
                features1["sift_kp"],
                features2_dict["enhanced"],
                features2["sift_kp"],
                sorted(sift_matches, key=lambda x: x.distance)[:30],
                None,
                flags=cv.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
            )
            cv.imshow("SIFT Matches (Top 30)", sift_vis)

        # Side-by-side comparison
        comparison = np.hstack([features1_dict["edges"], features2_dict["edges"]])
        cv.imshow("Edge Comparison", comparison)
        cv.waitKey(0)
        cv.destroyAllWindows()

    return final_score


def extract_shoeprint_features(image_path):
    """
    Feature extraction for shoeprints in noisy substrates.
    """
    img_color = cv.imread(image_path)
    if img_color is None:
        raise FileNotFoundError(f"Cannot open {image_path}")

    lab_image = cv.cvtColor(img_color, cv.COLOR_BGR2Lab)
    l_channel, a_channel, b_channel = cv.split(lab_image)

    denoised_l = cv.fastNlMeansDenoising(
        l_channel, None, h=10, templateWindowSize=7, searchWindowSize=21
    )

    clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced_l = clahe.apply(denoised_l)

    binary_pattern = cv.adaptiveThreshold(
        enhanced_l,
        maxValue=255,
        adaptiveMethod=cv.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv.THRESH_BINARY_INV,
        blockSize=51,
        C=5,
    )

    kernel = np.ones((3, 3), np.uint8)
    cleaned_pattern = cv.morphologyEx(
        binary_pattern, cv.MORPH_OPEN, kernel, iterations=2
    )
    cleaned_pattern = cv.morphologyEx(
        cleaned_pattern, cv.MORPH_CLOSE, kernel, iterations=2
    )

    P = 8
    R = 1
    lbp = local_binary_pattern(enhanced_l, P, R, method="uniform")
    lbp_features = lbp[cleaned_pattern == 255]

    return (
        l_channel,
        a_channel,
        b_channel,
        denoised_l,
        enhanced_l,
        binary_pattern,
        cleaned_pattern,
        lbp,
        lbp_features,
    )
