"""
Integrated inference pipeline for CocoScan using the single TFLite model in the model folder.
Handles: image preparation -> pest classification -> recommendations.
"""

import base64
import io
import logging
from typing import Dict, Optional, Union

import numpy as np
from PIL import Image

from model.inference import predict_pest_from_base64

logger = logging.getLogger(__name__)

PEST_LABELS = ["Rhinoceros Beetle", "Brontispa", "Healthy Coconut Leaf"]


def _to_base64(image_source: Union[str, np.ndarray, Image.Image]) -> str:
    if isinstance(image_source, Image.Image):
        image = image_source.convert("RGB")
    elif isinstance(image_source, np.ndarray):
        image = Image.fromarray(image_source.astype("uint8"), "RGB")
    else:
        image = Image.open(image_source).convert("RGB")

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def run_full_inference_pipeline(
    image_source: Union[str, np.ndarray, Image.Image],
    yolo_model_path: Optional[str] = None,
    pest_model_path: Optional[str] = None,
    severity_model_path: Optional[str] = None,
    use_lite_size: bool = False,
) -> Dict:
    """
    Run the single-model inference pipeline.
    Severity classification is intentionally not used because the new TFLite model does not provide it.
    """
    try:
        logger.info("Starting single-model inference pipeline")

        payload = _to_base64(image_source)
        inference_result = predict_pest_from_base64(payload, model_path=pest_model_path)

        from app.recommendations import recommend_actions

        recommendations_result = recommend_actions(
            inference_result["predicted_pest"],
            "Moderate",
            risk_score=50,
        )

        return {
            "success": True,
            "pest": inference_result["predicted_pest"],
            "pest_confidence": inference_result["confidence_score"],
            "pest_probabilities": inference_result["probabilities"],
            "severity": "Not available",
            "damage_percentage": None,
            "severity_confidence": None,
            "severity_probabilities": None,
            "recommendations": recommendations_result["recommendation"],
            "risk_level": recommendations_result["risk"],
            "urgency": recommendations_result["urgency"],
            "risk_factors": recommendations_result["risk_factors"],
        }
    except Exception as exc:
        logger.error(f"Full pipeline error: {str(exc)}")
        return {
            "success": False,
            "error": str(exc),
            "pest": "Unknown",
            "severity": "Not available",
            "confidence": 0.0,
            "recommendations": [],
        }

