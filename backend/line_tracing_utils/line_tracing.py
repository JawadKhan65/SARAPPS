import cv2 as cv
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from skimage.feature import local_binary_pattern


def process_reference_sole(
    image_path, target_size=(512, 512), keep_aspect=True, use_polar=True, debug=False
):
    """
    Preprocess shoe sole image (reference or print) for rotation-robust similarity matching.

    Steps:
      1. Resize & pad to fixed size
      2. Denoise + enhance contrast
      3. Edge extraction (Sobel + adaptive threshold)
      4. (Optional) Convert to polar coordinates for rotation robustness

    Args:
        image_path (str): Path to image
        target_size (tuple): Desired (width, height)
        keep_aspect (bool): Maintain aspect ratio when resizing
        use_polar (bool): Convert to polar representation for rotation-invariance
        debug (bool): Show visual debug outputs

    Returns:
        np.ndarray: Processed edge (or polar-edge) image, same size for all
    """
    # 1. Load image
    img = cv.imread(image_path, cv.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Cannot load image: {image_path}")

    # 2. Resize and pad to fixed size
    if keep_aspect:
        h, w = img.shape[:2]
        scale = min(target_size[0] / w, target_size[1] / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv.resize(img, (new_w, new_h), interpolation=cv.INTER_AREA)

        # pad into a centered canvas
        canvas = np.zeros(target_size[::-1], dtype=np.uint8)
        y_off = (target_size[1] - new_h) // 2
        x_off = (target_size[0] - new_w) // 2
        canvas[y_off : y_off + new_h, x_off : x_off + new_w] = resized
        img = canvas
    else:
        img = cv.resize(img, target_size, interpolation=cv.INTER_AREA)

    # 3. Denoise + enhance
    img = cv.GaussianBlur(img, (3, 3), 1)
    img = cv.equalizeHist(img)

    # 4. Edge extraction (Sobel)
    sobelX = cv.Sobel(img, cv.CV_16S, 1, 0, ksize=3)
    sobelY = cv.Sobel(img, cv.CV_16S, 0, 1, ksize=3)
    absX = cv.convertScaleAbs(sobelX)
    absY = cv.convertScaleAbs(sobelY)
    sobel_edges = cv.addWeighted(absX, 0.5, absY, 0.5, 0)

    # Binary threshold (adaptive for lighting)
    _, edges = cv.threshold(sobel_edges, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)

    # 5. Morphological clean-up (optional)
    kernel = np.ones((3, 3), np.uint8)
    edges = cv.morphologyEx(edges, cv.MORPH_CLOSE, kernel)
    edges = cv.morphologyEx(edges, cv.MORPH_OPEN, kernel)

    # 6. Convert to polar space (rotation → horizontal shift)
    if use_polar:
        center = (target_size[0] // 2, target_size[1] // 2)
        max_radius = min(center)
        polar = cv.warpPolar(
            edges,
            dsize=target_size,
            center=center,
            maxRadius=max_radius,
            # flags=cv.INTER_LINEAR
            # + cv.WARP_FILL_OUTLIERS
            # + cv.WARP_INVERSE_MAP
            # + cv.WARP_POLAR_LOG,
            flags=cv.WARP_POLAR_LINEAR,
        )
        processed = polar
    else:
        processed = edges

    if debug:
        cv.imshow("Input", img)
        cv.imshow("Edges", edges)
        if use_polar:
            cv.imshow("Polar Transform", processed)
        cv.waitKey(0)
        cv.destroyAllWindows()

    return processed


def compare_sole_images(img1_path, img2_path, debug=False):
    """
    Compare two shoe sole images using hybrid (ORB + Cosine) similarity.
    Returns a score between 0 and 1.
    """
    # 1. Preprocess both images
    edges1 = process_reference_sole(img1_path)
    edges2 = process_reference_sole(img2_path)

    # 2. --- ORB similarity ---
    orb = cv.ORB_create(nfeatures=10000)
    kp1, des1 = orb.detectAndCompute(edges1, None)
    kp2, des2 = orb.detectAndCompute(edges2, None)

    orb_similarity = 0
    if des1 is not None and des2 is not None and len(kp1) > 0 and len(kp2) > 0:
        bf = cv.BFMatcher(cv.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        if max(len(kp1), len(kp2)) > 0:
            orb_similarity = len(matches) / max(len(kp1), len(kp2))

    # 3. --- Cosine similarity ---
    f1 = edges1.flatten().astype(np.float32).reshape(1, -1)
    f2 = edges2.flatten().astype(np.float32).reshape(1, -1)
    cos_sim = cosine_similarity(f1, f2)[0][0]

    # 4. --- Combined score ---
    final_score = 0.6 * orb_similarity + 0.4 * cos_sim

    if debug:
        print(f"ORB similarity: {orb_similarity:.3f}")
        print(f"Cosine similarity: {cos_sim:.3f}")
        print(f"Final hybrid score: {final_score:.3f}")

        # Optional: visualize matches
        if des1 is not None and des2 is not None and len(kp1) > 0 and len(kp2) > 0:
            matches = sorted(matches, key=lambda x: x.distance)
            match_vis = cv.drawMatches(
                edges1,
                kp1,
                edges2,
                kp2,
                matches[:50],
                None,
                flags=cv.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
            )
            cv.imshow("ORB Matches", match_vis)
            cv.waitKey(0)
            cv.destroyAllWindows()

    return final_score


def extract_shoeprint_features(image_path):
    """
    This is a feature extraction pipeline designed specifically for
    identifying shoeprints in noisy substrates like sand, dust, or mud.

    It extracts two key items:
    1.  A clean, binary mask of the print's PATTERN.
    2.  A mathematical FEATURE VECTOR (LBP) of the print's TEXTURE.
    """

    img_color = cv.imread(image_path)
    if img_color is None:
        raise FileNotFoundError(f"Cannot open {image_path}")

    # --- Step 1: Isolate Illumination (L*a*b* Channel) ---
    # This is the best way to see a 3D impression, independent of color
    lab_image = cv.cvtColor(img_color, cv.COLOR_BGR2Lab)
    l_channel, a_channel, b_channel = cv.split(lab_image)

    # --- Step 2: Denoise Substrate (NL-Means Denoising) ---
    # This is critical for sand/dust. It removes grain noise.
    # h=10 is a good starting point (denoising strength)
    denoised_l = cv.fastNlMeansDenoising(
        l_channel, None, h=10, templateWindowSize=7, searchWindowSize=21
    )

    # --- Step 3: Enhance Print Contrast (CLAHE) ---
    # This makes the faint impressions "pop"
    clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced_l = clahe.apply(denoised_l)

    # --- Step 4: Extract Print Pattern (Adaptive Thresholding) ---
    # This is the core logic. It finds all "locally dark" areas (the print)
    # and converts them to a solid white shape.

    # We use THRESH_BINARY_INV because the print (shadow) is darker
    # than the substrate (sand). Adjust 'blockSize' and 'C' as needed.
    # 'blockSize' must be odd. 'C' subtracts from the mean.
    binary_pattern = cv.adaptiveThreshold(
        enhanced_l,
        maxValue=255,
        adaptiveMethod=cv.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv.THRESH_BINARY_INV,
        blockSize=51,  # Large block size to span tread blocks
        C=5,  # Small constant, very sensitive to shadows
    )

    # --- Step 5: Clean the Pattern (Morphological Operations) ---
    # This removes noise from the binary image

    # Kernel size: 3x3 or 5x5
    kernel = np.ones((3, 3), np.uint8)

    # 1. Open: Removes small white dots (salt noise / bright sand grains)
    cleaned_pattern = cv.morphologyEx(
        binary_pattern, cv.MORPH_OPEN, kernel, iterations=2
    )

    # 2. Close: Fills small black holes (pepper noise / gaps in print)
    cleaned_pattern = cv.morphologyEx(
        cleaned_pattern, cv.MORPH_CLOSE, kernel, iterations=2
    )

    # --- Step 6: Extract Database Features (LBP) ---
    # This creates the mathematical "fingerprint" of the print's texture
    # for your database.

    # LBP parameters
    P = 8  # number of points
    R = 1  # radius

    # Calculate LBP on the enhanced grayscale image (it has the texture)
    lbp = local_binary_pattern(enhanced_l, P, R, method="uniform")

    # Only keep LBP features that are *inside* our cleaned print pattern
    # (where cleaned_pattern == 255)
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
