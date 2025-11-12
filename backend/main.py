from line_tracing_utils import compare_sole_images, extract_shoeprint_features
import json
import tempfile
from pathlib import Path
import subprocess
import sys
import os

# Load data/info.json into `info` with safe error handling.
DATA_INFO_PATH = Path(__file__).parent / "data" / "info.json"


def load_info(path: Path = DATA_INFO_PATH):
    """Read and parse the JSON file at `path`.

    Returns a list of metadata objects on success, otherwise returns an empty list.
    Prints a warning when the file is missing or invalid.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Warning: info file not found at {path!s}")
        return []

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"Error parsing JSON from {path!s}: {exc}")
        return []


def compute_score(target):
    """Compute similarity scores between `target` image path and all images in info.json.

    Returns a list of metadata dicts augmented with a numeric 'score' key, sorted
    descending by score.
    """
    scores = []
    info = load_info()
    for i in info:
        data_url = i.get("data_url")
        if not data_url:
            continue

        # Ensure we pass a filesystem path to compare_sole_images
        candidate_path = Path(data_url)
        if not candidate_path.is_absolute():
            candidate_path = Path(__file__).parent / data_url

        try:
            score = compare_sole_images(str(candidate_path), str(target), debug=False)
        except Exception as exc:
            # If an error occurs comparing this pair, skip and log
            print(f"Error comparing {candidate_path} to {target}: {exc}")
            continue

        # Work on a shallow copy to avoid mutating the loaded info file
        item = dict(i)
        item["score"] = score
        # Record resolved path for display
        item["_resolved_data_url"] = str(candidate_path)
        scores.append(item)

    return sorted(scores, key=lambda x: x["score"], reverse=True)


def run_streamlit_app():
    """Run a Streamlit UI that accepts an uploaded image and shows top matches."""
    try:
        import streamlit as st
    except Exception:
        print(
            "Streamlit is not installed. Install streamlit to run the web app: pip install streamlit"
        )
        return

    st.set_page_config(page_title="Sole matcher", layout="wide")
    st.title("Sole similarity explorer")

    st.markdown(
        "Upload a sole image (front or side) and the app will show the most similar images from the dataset."
    )

    uploaded = st.file_uploader(
        "Upload target image", type=["jpg", "jpeg", "png", "webp"]
    )
    k = st.sidebar.slider(
        "Number of matches to show", min_value=1, max_value=12, value=4
    )

    if uploaded is None:
        st.info(
            "Upload an image to start. You can also run this script from the command line: python main.py <image_path>"
        )
        return

    # Save uploaded file to a temp location
    tmp_dir = Path(tempfile.gettempdir())
    tmp_path = tmp_dir / uploaded.name
    with open(tmp_path, "wb") as f:
        f.write(uploaded.getbuffer())

    st.subheader("Target image")
    # Show the uploaded target at a moderate fixed width to avoid an overly large display
    st.image(str(tmp_path), width=350)

    # --- Extract and display shoeprint features ---
    try:
        # Import the extractor from the utils (import inside function to avoid heavy deps at module import)
        from line_tracing_utils.line_tracing import extract_shoeprint_features
    except Exception as exc:
        st.warning(f"Feature extractor unavailable: {exc}")
        extractor_available = False
    else:
        extractor_available = True

    if extractor_available:
        with st.expander("Show extracted features", expanded=True):
            try:
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
                ) = extract_shoeprint_features(str(tmp_path))
            except Exception as exc:
                st.error(f"Error extracting features: {exc}")
            else:
                import numpy as _np

                def _to_display(arr):
                    """Normalize numpy arrays to uint8 for Streamlit display."""
                    a = _np.asarray(arr)
                    # If already uint8, return as-is
                    if a.dtype == _np.uint8:
                        return a
                    # For 2D arrays, scale min..max -> 0..255
                    if a.ndim == 2:
                        amin = a.min()
                        amax = a.max()
                        if amax > amin:
                            norm = (a - amin).astype(_np.float32) / (amax - amin)
                            disp = (norm * 255.0).astype(_np.uint8)
                        else:
                            disp = _np.clip(a, 0, 255).astype(_np.uint8)
                        return disp
                    # For 3D arrays assume color BGR or RGB; convert BGR->RGB if 3 channels
                    if a.ndim == 3 and a.shape[2] == 3:
                        # Many OpenCV outputs are BGR; try converting to RGB for display
                        return a[:, :, ::-1].astype(_np.uint8)
                    # Fallback: convert to uint8
                    return _np.clip(a, 0, 255).astype(_np.uint8)

                imgs = [
                    ("L channel", l_channel),
                    ("A channel", a_channel),
                    ("B channel", b_channel),
                    ("Denoised L", denoised_l),
                    ("Enhanced L", enhanced_l),
                    ("Binary pattern", binary_pattern),
                    ("Cleaned pattern", cleaned_pattern),
                    ("LBP (map)", lbp),
                ]

                cols = st.columns(4)
                for idx, (title, arr) in enumerate(imgs):
                    col = cols[idx % 4]
                    with col:
                        try:
                            disp = _to_display(arr)
                            st.image(disp, caption=title, use_container_width=True)
                        except Exception as e:
                            st.write(f"{title}: (unable to render) {e}")

                # Show LBP feature vector summary / small chart
                try:
                    if lbp_features is not None:
                        lf = _np.asarray(lbp_features)
                        st.write(f"LBP feature vector length: {lf.size}")
                        # Show a small subset histogram (first 200 values) for quick inspection
                        st.bar_chart(lf.flatten()[:200])
                except Exception:
                    st.write("LBP features: (unable to display vector)")

    # Compute scores (could be cached if desired)
    with st.spinner("Computing similarity scores..."):
        results = compute_score(str(tmp_path))

    if not results:
        st.warning("No matches found or an error occurred during comparison.")
        return

    st.subheader(f"Top {min(k, len(results))} matches")

    cols = st.columns(k)
    for idx, res in enumerate(results[:k]):
        col = cols[idx]
        # Prefer resolved path if available
        img_path = res.get("_resolved_data_url") or res.get("data_url")
        # Ensure the image exists before trying to show it
        if img_path and not Path(img_path).exists():
            # try resolving relative to project
            alt = Path(__file__).parent / img_path
            if alt.exists():
                img_path = str(alt)

        with col:
            if img_path and Path(img_path).exists():
                st.image(img_path, use_container_width=True)
            else:
                st.write("(image missing)")

            st.markdown(f"**{res.get('name', '-')}**")
            st.write(f"Brand: {res.get('brand', '-')}")
            st.write(f"Year: {res.get('year', '-')}")
            st.write(f"Score: {res.get('score', 0):.4f}")
            src = res.get("source_url")
            if src:
                st.write(f"[Source]({src})")


if __name__ == "__main__":
    # Two supported ways to run the Streamlit UI:
    # 1) Preferred: `streamlit run main.py`  (recommended by Streamlit)
    # 2) Or: `python -m main --streamlit` which will invoke the streamlit CLI
    #    under the current interpreter so Streamlit runs in its expected context.

    # If user requested `--streamlit`, re-launch this file using `python -m streamlit run`.
    if "--streamlit" in sys.argv:
        # Build command to call streamlit via the current Python interpreter
        # Remove the `--streamlit` flag when passing through.
        extra_args = [a for a in sys.argv[1:] if a != "--streamlit"]
        cmd = [sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve())]
        if extra_args:
            cmd += ["--"] + extra_args

        print("Launching Streamlit server:", " ".join(cmd))
        try:
            subprocess.run(cmd)
        except FileNotFoundError:
            print(
                "Error: unable to launch Streamlit. Is Streamlit installed in the current environment?"
            )
        sys.exit(0)

    # If the script is being executed by Streamlit (e.g. `streamlit run main.py`),
    # the `streamlit` package will be importable. Prefer importing Streamlit
    # here and starting the app directly so the UI shows correctly.
    try:
        import streamlit as _st  # type: ignore
    except Exception:
        _st = None

    if _st is not None:
        run_streamlit_app()
        sys.exit(0)

    # Fallback: Streamlit also sets STREAMLIT_RUN_MAIN in some environments;
    # keep it as a backup check.
    if os.environ.get("STREAMLIT_RUN_MAIN") == "true":
        run_streamlit_app()
        sys.exit(0)

    # CLI mode: `python -m main <image_path>` computes and prints matches
    if len(sys.argv) == 2:
        target_image_path = sys.argv[1]
        results = compute_score(target_image_path)

        print("\nTop matches:")
        for res in results:
            print(
                f"Name: {res['name']}\n Year: {res['year']}\n Brand: {res['brand']}\n Score: {res['score']:.4f}\n Source: {res.get('source_url', '-')}"
            )
            print("-" * 50)
    else:
        print(
            "To use the web UI, run either:\n  streamlit run main.py\nor\n  python -m main --streamlit\n"
        )
