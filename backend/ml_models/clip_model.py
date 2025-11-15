import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel


class SoleDetectorCLIP:
    def __init__(self):
        self.model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        self.processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)

    def is_sole(
        self, image, threshold=0.45
    ):  # Lower threshold since prompts are sharper
        """
        AGGRESSIVE version with highly distinctive prompts.
        Use this if the standard version still misses obvious soles.
        """

        texts = [
            # SOLE: Ultra-specific visual markers
            "close-up of shoe sole showing zigzag tread pattern and rubber texture",
            "shoe outsole with waffle pattern grip and deep channels",
            "shoe sole",
            "shoe sole with intricate tread design",
            "bottom surface of shoe with hexagonal or diamond tread design",
            "rubber sole with raised lugs and drainage grooves",
            "shoe sole showing wear pattern on textured rubber surface",
            # SOLE WITH UPPER: Very specific top-down scenarios
            "bird's eye view of entire shoe showing sole outline and upper",
            "flat lay photo of shoe with sole edges clearly visible",
            # NON-SOLE: Unmistakable opposite views
            "shoe photographed from side showing heel counter and ankle height",
            "frontal view of shoe showing toe cap and lacing system",
            "three-quarter view of shoe emphasizing upper construction",
            "close-up of shoe leather or suede material without any sole visible",
        ]

        inputs = self.processor(
            text=texts, images=image, return_tensors="pt", padding=True
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits_per_image = outputs.logits_per_image
            probs = logits_per_image.softmax(dim=1)

        scores = {
            "sole_zigzag_texture": probs[0, 0].item(),
            "sole_waffle_grip": probs[0, 1].item(),
            "sole_plain": probs[0, 2].item(),
            "sole_intricate_tread": probs[0, 3].item(),
            "sole_hexagon_tread": probs[0, 4].item(),
            "sole_raised_lugs": probs[0, 5].item(),
            "sole_wear_pattern": probs[0, 6].item(),
            "topview_sole_outline": probs[0, 7].item(),
            "flatlay_sole_edges": probs[0, 8].item(),
            "side_heel_ankle": probs[0, 9].item(),
            "front_toe_laces": probs[0, 10].item(),
            "threequarter_upper": probs[0, 11].item(),
            "closeup_leather_nosole": probs[0, 12].item(),
        }

        # Pure sole score (very specific tread patterns)
        pure_sole_score = (
            scores["sole_zigzag_texture"]
            + scores["sole_waffle_grip"]
            + scores["sole_plain"]
            + scores["sole_intricate_tread"]
            + scores["sole_hexagon_tread"]
            + scores["sole_raised_lugs"]
            + scores["sole_wear_pattern"]
        ) / 7
        # Top-down with sole visible
        topdown_score = (
            scores["topview_sole_outline"] + scores["flatlay_sole_edges"]
        ) / 2

        # Weighted combination (heavy weight on pure sole)
        sole_score = (pure_sole_score * 0.75) + (topdown_score * 0.25)

        # Non-sole score
        non_sole_score = (
            scores["side_heel_ankle"]
            + scores["front_toe_laces"]
            + scores["threequarter_upper"]
            + scores["closeup_leather_nosole"]
        ) / 4

        # Confidence calculation
        confidence = sole_score / (sole_score + non_sole_score)
        is_sole_img = confidence > threshold

        return is_sole_img, confidence, scores
