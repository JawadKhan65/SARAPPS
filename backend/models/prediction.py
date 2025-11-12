import torch
from pathlib import Path
from PIL import Image
import torchvision.transforms as T


# Construct absolute path to model file
MODEL_PATH = Path(__file__).parent / "shoe_sole_classifier_full.pth"

# Load model once
model = torch.load(str(MODEL_PATH), map_location="cpu", weights_only=False)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
model.eval()  # set once

# Define transform once
transform = T.Compose(
    [
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]
)


def predict(image_input):
    """
    Predict if an image is a shoe sole.

    Args:
        image_input: Either a file path (str) or a PIL Image object

    Returns:
        Tuple of (label, probability) where label is "Shoe Sole" or "Not Shoe Sole"
    """
    # Accept both file paths and PIL Image objects
    if isinstance(image_input, str):
        img = Image.open(image_input).convert("RGB")
    else:
        # Assume it's a PIL Image object
        img = (
            image_input.convert("RGB")
            if hasattr(image_input, "convert")
            else image_input
        )

    x = transform(img).unsqueeze(0).to(device)
    with torch.no_grad():
        out = model(x)
        prob = torch.sigmoid(out).item()
        return ("Shoe Sole" if prob > 0.5 else "Not Shoe Sole", prob)
