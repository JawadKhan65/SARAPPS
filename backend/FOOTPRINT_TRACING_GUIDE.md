# Shoe Sole Footprint Edge Tracing Guide

This guide explains how to create crystal-clear edge traced visualizations of shoe sole footprints.

## 🎯 Quick Start

### Process All Test Images
```bash
python trace_footprints.py
# Then select option 2
```

### Process a Single Image
```python
from line_tracing_utils import trace_sole_patterns_enhanced

trace_sole_patterns_enhanced('data/images/test/image0.jpeg', show_result=True)
```

## 📁 Output Locations

Your traced footprints are saved in:
- **Enhanced traced images**: `data/images/test/enhanced_traced/`
- **Basic traced images**: `data/images/test/traced_edges/`

## 🔧 Two Methods Available

### Method 1: Enhanced (Recommended)
**Best for**: Footprints on rough ground (asphalt, concrete, dirt)

```python
from line_tracing_utils import trace_sole_patterns_enhanced

trace_sole_patterns_enhanced(
    'path/to/footprint.jpeg',
    min_pattern_size=100,      # Larger value = less noise
    noise_removal=True,         # Filters ground texture
    enhance_patterns=True,      # Sharpens shoe patterns
    show_result=True           # Display results
)
```

**Features:**
- Automatically detects footprint regions
- Filters out ground texture noise
- Focuses on shoe tread patterns
- Creates clean black-on-white visualizations

### Method 2: Basic
**Best for**: Clean backgrounds or when you want pure edge detection

```python
from line_tracing_utils import trace_sole_edges

trace_sole_edges(
    'path/to/footprint.jpeg',
    edge_method='hybrid',       # Options: 'canny', 'sobel', 'laplacian', 'hybrid'
    detail_level='high',        # Options: 'low', 'medium', 'high', 'ultra'
    denoise_strength=2,         # 0-3 (0=none, 3=maximum)
    invert_output=True,         # True = white edges on black
    show_result=True
)
```

**Features:**
- Pure edge detection without masking
- Multiple detection algorithms
- Adjustable detail levels
- Fast processing

## 📊 Parameter Guide

### Enhanced Method Parameters

| Parameter | Default | Description | Adjust When |
|-----------|---------|-------------|-------------|
| `min_pattern_size` | 100 | Minimum size of patterns to keep | Too much noise: increase<br>Missing patterns: decrease |
| `noise_removal` | True | Apply denoising | Ground is rough: True<br>Clean surface: False |
| `enhance_patterns` | True | Sharpen patterns before detection | Faint prints: True<br>Clear prints: False |

### Basic Method Parameters

| Parameter | Default | Description | Options |
|-----------|---------|-------------|---------|
| `edge_method` | 'hybrid' | Edge detection algorithm | 'canny', 'sobel', 'laplacian', 'hybrid' |
| `detail_level` | 'high' | How much detail to capture | 'low', 'medium', 'high', 'ultra' |
| `denoise_strength` | 1 | Noise reduction strength | 0 (none) - 3 (maximum) |
| `invert_output` | False | Color scheme | True: white edges on black<br>False: black edges on white |

## 💡 Tips for Best Results

### For Faint Footprints
```python
trace_sole_patterns_enhanced(
    image_path,
    min_pattern_size=50,        # Lower to capture faint patterns
    noise_removal=True,
    enhance_patterns=True       # Boost pattern visibility
)
```

### For Very Clear Footprints
```python
trace_sole_edges(
    image_path,
    edge_method='canny',        # Fast and clean for clear images
    detail_level='medium',      # Avoid over-detection
    denoise_strength=1
)
```

### For Maximum Detail
```python
trace_sole_edges(
    image_path,
    edge_method='hybrid',       # Combines multiple methods
    detail_level='ultra',       # Capture every edge
    denoise_strength=0          # No smoothing
)
```

### For Noisy Backgrounds
```python
trace_sole_patterns_enhanced(
    image_path,
    min_pattern_size=200,       # Filter more aggressively
    noise_removal=True,
    enhance_patterns=True
)
```

## 🚀 Batch Processing

### Process Multiple Images
```python
from line_tracing_utils import process_multiple_footprints

# Using enhanced method (default)
process_multiple_footprints(
    'data/images/test',
    file_pattern='*.jpeg'
)

# Using basic method
process_multiple_footprints(
    'data/images/test',
    file_pattern='*.jpeg',
    edge_method='hybrid',
    detail_level='high',
    denoise_strength=2
)
```

### Using the Demo Script
```bash
# Interactive mode
python trace_footprints.py

# Command line mode
python trace_footprints.py path/to/image.jpeg enhanced
python trace_footprints.py path/to/image.jpeg basic
```

## 📝 Examples

### Your Test Images

All 4 test images have been processed:
- `image0.jpeg` → `enhanced_traced/image0_enhanced.jpeg` ✓
- `image1.jpeg` → `enhanced_traced/image1_enhanced.jpeg` ✓
- `image2.jpeg` → `enhanced_traced/image2_enhanced.jpeg` ✓
- `image3.jpeg` → `enhanced_traced/image3_enhanced.jpeg` ✓

Results show:
- Crystal-clear tread patterns
- Minimal ground texture noise
- Black edges on white background
- Every fine detail preserved

## 🔍 Understanding the Output

**Enhanced Method** creates three outputs:
1. **Original image**: Your input footprint
2. **Footprint region mask**: Shows detected footprint area (white)
3. **Edge traced pattern**: Final result with shoe sole details

**Basic Method** creates two outputs:
1. **Original image**: Your input footprint  
2. **Edge traced pattern**: Direct edge detection result

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| Too much noise | Increase `min_pattern_size` or `denoise_strength` |
| Missing details | Decrease `min_pattern_size` or use `detail_level='ultra'` |
| Footprint not detected | Use basic method instead, or decrease `min_pattern_size` |
| Too slow | Use basic method with `detail_level='low'` |
| Output is mostly white/black | Try inverting: toggle `invert_output` |

## 📚 Function Reference

### Main Functions

```python
# Enhanced edge tracing
trace_sole_patterns_enhanced(image_path, output_path, min_pattern_size, 
                            noise_removal, enhance_patterns, show_result)

# Basic edge tracing  
trace_sole_edges(image_path, output_path, edge_method, detail_level,
                denoise_strength, invert_output, show_result)

# Batch processing
process_multiple_footprints(input_folder, output_folder, file_pattern, **kwargs)
```

## 🎨 Customization

Want different colors? Modify the output in code:
```python
# Load the traced image
traced = cv2.imread('path/to/traced.jpeg', 0)

# Create colored version (e.g., green on black)
colored = np.zeros((traced.shape[0], traced.shape[1], 3), dtype=np.uint8)
colored[traced < 128] = [0, 255, 0]  # BGR: Green

# Save
cv2.imwrite('path/to/colored_traced.jpeg', colored)
```

---

## ✅ Summary

- ✨ **Enhanced method**: Best for real-world footprints on rough surfaces
- ⚡ **Basic method**: Fast edge detection for clean images  
- 🎯 **Results**: Crystal-clear shoe sole patterns with every detail visible
- 🔧 **Customizable**: Adjust parameters for different footprint conditions

