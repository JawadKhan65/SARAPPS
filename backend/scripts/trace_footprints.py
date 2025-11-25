"""
Simple script to trace shoe sole footprint patterns with high-quality edge detection.
"""

from line_tracing_utils import trace_sole_patterns_enhanced, trace_sole_edges
from pathlib import Path


def trace_single_footprint(image_path, method="enhanced"):
    """
    Trace a single footprint image.
    
    Args:
        image_path: Path to the footprint image
        method: "enhanced" (recommended) or "basic"
    """
    if method == "enhanced":
        # Enhanced method - filters ground noise, focuses on shoe patterns
        print("Using enhanced edge tracing (recommended for footprints on rough ground)...")
        original, traced, mask = trace_sole_patterns_enhanced(
            image_path,
            min_pattern_size=100,  # Adjust to filter smaller/larger noise
            noise_removal=True,
            enhance_patterns=True,
            show_result=True  # Display the result
        )
    else:
        # Basic method - pure edge detection
        print("Using basic edge tracing...")
        original, traced = trace_sole_edges(
            image_path,
            edge_method="hybrid",  # Options: "canny", "sobel", "laplacian", "hybrid"
            detail_level="high",   # Options: "low", "medium", "high", "ultra"
            denoise_strength=2,    # 0-3
            invert_output=True,    # True = white edges on black, False = black edges on white
            show_result=True
        )
    
    print("✓ Done!")


def trace_all_footprints(folder_path, method="enhanced"):
    """
    Trace all footprint images in a folder.
    
    Args:
        folder_path: Path to folder containing footprint images
        method: "enhanced" (recommended) or "basic"
    """
    folder = Path(folder_path)
    images = list(folder.glob("image*.jpeg")) + list(folder.glob("image*.jpg"))
    
    if not images:
        print(f"No footprint images found in {folder_path}")
        return
    
    print(f"Found {len(images)} footprint images")
    
    output_folder = folder / ("enhanced_traced" if method == "enhanced" else "traced_edges")
    output_folder.mkdir(exist_ok=True)
    
    for img_path in images:
        print(f"\nProcessing: {img_path.name}")
        output_path = output_folder / f"{img_path.stem}_traced.jpeg"
        
        if method == "enhanced":
            trace_sole_patterns_enhanced(
                str(img_path),
                output_path=str(output_path),
                min_pattern_size=100,
                show_result=False
            )
        else:
            trace_sole_edges(
                str(img_path),
                output_path=str(output_path),
                edge_method="hybrid",
                detail_level="high",
                denoise_strength=2,
                invert_output=True,
                show_result=False
            )
    
    print(f"\n✓ All images processed!")
    print(f"Results saved in: {output_folder}")


if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("SHOE SOLE FOOTPRINT EDGE TRACING")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        # Process single image from command line
        image_path = sys.argv[1]
        method = sys.argv[2] if len(sys.argv) > 2 else "enhanced"
        trace_single_footprint(image_path, method)
    else:
        # Interactive mode
        print("\nOptions:")
        print("1. Trace single footprint (with display)")
        print("2. Trace all footprints in test folder")
        print("3. Trace all footprints in custom folder")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            img_path = input("Enter image path: ").strip()
            method = input("Method (enhanced/basic) [enhanced]: ").strip() or "enhanced"
            trace_single_footprint(img_path, method)
            
        elif choice == "2":
            method = input("Method (enhanced/basic) [enhanced]: ").strip() or "enhanced"
            trace_all_footprints("data/images/test", method)
            
        elif choice == "3":
            folder = input("Enter folder path: ").strip()
            method = input("Method (enhanced/basic) [enhanced]: ").strip() or "enhanced"
            trace_all_footprints(folder, method)
        
        else:
            print("Invalid choice. Using default: trace test folder with enhanced method")
            trace_all_footprints("data/images/test", "enhanced")
    
    print("\n" + "=" * 60)
    print("COMPLETE!")
    print("=" * 60)

