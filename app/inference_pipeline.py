"""
Integrated inference pipeline for CocoScan using TFLite models.
Handles: Resize -> Pest Classification -> Severity Classification -> Recommendations
"""

import os
import logging
import venv
import numpy as np
from PIL import Image
from typing import Union, Tuple, Dict, Optional
import tensorflow as tf

logger = logging.getLogger(__name__)

# Model labels
PEST_LABELS = ["Rhinoceros Beetle", "Brontispa", "Healthy Coconut Leaf"]
SEVERITY_LABELS = ["Mild", "Moderate", "Severe"]

# Target sizes for models (default to 160x160, matching TFLite models)
TARGET_SIZE = (160, 160)
TARGET_SIZE_LITE = (160, 160)

# Model cache for efficiency
_MODEL_CACHE = {
    'pest_classifier': None,
    'severity_classifier': None
}

def load_tflite_model(model_path: str, model_type: str):
    """Load TFLite model for pest or severity classification."""
    global _MODEL_CACHE
    
    if model_type == 'pest' and _MODEL_CACHE['pest_classifier'] is None:
        try:
            interpreter = tf.lite.Interpreter(model_path=model_path)
            interpreter.allocate_tensors()
            _MODEL_CACHE['pest_classifier'] = interpreter
            logger.info(f"Pest classifier TFLite model loaded from {model_path}")
        except Exception as e:
            logger.error(f"Failed to load pest classifier TFLite model: {str(e)}")
            raise
    elif model_type == 'severity' and _MODEL_CACHE['severity_classifier'] is None:
        try:
            interpreter = tf.lite.Interpreter(model_path=model_path)
            interpreter.allocate_tensors()
            _MODEL_CACHE['severity_classifier'] = interpreter
            logger.info(f"Severity classifier TFLite model loaded from {model_path}")
        except Exception as e:
            logger.error(f"Failed to load severity classifier TFLite model: {str(e)}")
            raise
    
    if model_type == 'pest':
        return _MODEL_CACHE['pest_classifier']
    else:
        return _MODEL_CACHE['severity_classifier']


def resize_full_image(image_source: Union[str, np.ndarray, Image.Image], target_size: Tuple[int, int] = TARGET_SIZE) -> np.ndarray:
    """Resize the full image to the model's expected input size and normalize."""
    try:
        if isinstance(image_source, Image.Image):
            image = image_source.convert("RGB")
        elif isinstance(image_source, np.ndarray):
            image = Image.fromarray(image_source.astype("uint8"), "RGB")
        else:
            image = Image.open(image_source).convert("RGB")

        # Resize (may distort aspect ratio but keeps implementation simple)
        resized = image.resize(target_size)
        img_array = np.array(resized).astype(np.float32) / 255.0
        logger.info(f"Image resized to {target_size} for classification")
        return img_array
    except Exception as e:
        logger.error(f"Image resize error: {str(e)}")
        raise



def crop_and_resize_image(image_source: Union[str, np.ndarray, Image.Image], box: Tuple[float, float, float, float], target_size: Tuple[int, int] = TARGET_SIZE) -> np.ndarray:
    """Crop detected region and resize for model input."""
    try:
        # Convert to PIL Image
        if isinstance(image_source, Image.Image):
            image = image_source.convert("RGB")
        elif isinstance(image_source, np.ndarray):
            image = Image.fromarray(image_source.astype("uint8"), "RGB")
        else:
            image = Image.open(image_source).convert("RGB")
        
        # Crop
        x1, y1, x2, y2 = [int(max(0, coord)) for coord in box]
        x2 = min(image.width, x2)
        y2 = min(image.height, y2)
        
        cropped = image.crop((x1, y1, x2, y2))
        if cropped.width == 0 or cropped.height == 0:
            logger.warning("Cropped image has zero dimensions, using full image")
            cropped = image
        
        # Resize
        cropped = cropped.resize(target_size)
        
        # Convert to numpy and normalize
        img_array = np.array(cropped).astype(np.float32)
        img_array = img_array / 255.0
        
        logger.info(f"Image cropped and resized to {target_size}")
        return img_array
        
    except Exception as e:
        logger.error(f"Image cropping/resizing error: {str(e)}")
        raise


def run_tflite_inference(interpreter, image_array: np.ndarray) -> np.ndarray:
    """Run TFLite model inference."""
    try:
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        # Prepare input tensor (ensure batch dim)
        input_data = np.expand_dims(image_array, axis=0)

        # Cast to expected dtype
        expected_dtype = input_details[0]['dtype']
        input_data = input_data.astype(expected_dtype)

        # Debug: log final tensor shape before inference
        try:
            logger.info(f"Final tensor shape before inference: {input_data.shape}, dtype={input_data.dtype}")
        except Exception:
            pass

        interpreter.set_tensor(input_details[0]['index'], input_data)

        # Run inference
        interpreter.invoke()

        # Get output
        output_data = interpreter.get_tensor(output_details[0]['index'])
        return output_data[0]
        
    except Exception as e:
        logger.error(f"TFLite inference error: {str(e)}")
        raise


def predict_pest_class(interpreter, image_array: np.ndarray) -> Dict:
    """Classify pest from cropped image."""
    try:
        probabilities = run_tflite_inference(interpreter, image_array)
        predicted_class = int(np.argmax(probabilities))
        confidence = float(probabilities[predicted_class])
        
        result = {
            "predicted_pest": PEST_LABELS[predicted_class],
            "confidence_score": confidence,
            "probabilities": {label: float(prob) for label, prob in zip(PEST_LABELS, probabilities)}
        }
        
        logger.info(f"Pest prediction: {result['predicted_pest']} ({confidence:.2%})")
        return result
        
    except Exception as e:
        logger.error(f"Pest classification error: {str(e)}")
        raise


def predict_severity_class(interpreter, image_array: np.ndarray) -> Dict:
    """Classify severity from cropped image."""
    try:
        probabilities = run_tflite_inference(interpreter, image_array)
        predicted_class = int(np.argmax(probabilities))
        confidence = float(probabilities[predicted_class])
        severity = SEVERITY_LABELS[predicted_class]
        
        # Map severity to damage percentage
        damage_map = {"Mild": 25, "Moderate": 50, "Severe": 75}
        damage_percentage = damage_map.get(severity, 50)
        
        result = {
            "severity": severity,
            "damage_percentage": damage_percentage,
            "confidence_score": confidence,
            "probabilities": {label: float(prob) for label, prob in zip(SEVERITY_LABELS, probabilities)}
        }
        
        logger.info(f"Severity prediction: {result['severity']} ({confidence:.2%})")
        return result
        
    except Exception as e:
        logger.error(f"Severity classification error: {str(e)}")
        raise


def generate_recommendations(pest: str, severity: str) -> Dict:
    """Generate action recommendations based on pest and severity."""
    from app.recommendations import recommend_actions
    
    try:
        # Risk score is based on severity
        risk_score_map = {"Mild": 30, "Moderate": 60, "Severe": 90}
        risk_score = risk_score_map.get(severity, 50)
        
        recommendations = recommend_actions(pest, severity, risk_score)
        logger.info(f"Generated recommendations for {pest} ({severity})")
        return recommendations
        
    except Exception as e:
        logger.error(f"Recommendation generation error: {str(e)}")
        raise


def prepare_image_for_interpreter(interpreter, image_source: Union[str, np.ndarray, Image.Image]):
    """Prepare and resize image to the exact input size expected by the TFLite interpreter.

    Returns an image array with shape (H, W, 3) ready for batching.
    Also logs original and resized shapes.
    """
    # Get input details
    input_details = interpreter.get_input_details()[0]
    shape = list(input_details.get('shape', []))

    # Default fallback
    target_h, target_w = TARGET_SIZE
    try:
        if len(shape) >= 4:
            # shape is typically [1, H, W, C]
            target_h = int(shape[1])
            target_w = int(shape[2])
    except Exception:
        logger.warning('Unable to read interpreter input shape, falling back to default')

    # Load image as PIL
    if isinstance(image_source, Image.Image):
        pil_img = image_source.convert('RGB')
    elif isinstance(image_source, np.ndarray):
        pil_img = Image.fromarray(image_source.astype('uint8'), 'RGB')
    else:
        pil_img = Image.open(image_source).convert('RGB')

    original_size = pil_img.size  # (width, height)
    logger.info(f'Original image size: {original_size}')

    # Resize to target (PIL uses (width, height))
    resized = pil_img.resize((target_w, target_h))
    resized_size = resized.size
    logger.info(f'Resized image size: {resized_size} -> target (H,W)=({target_h},{target_w})')

    img_array = np.array(resized).astype(np.float32)
    # Normalize to 0-1 if interpreter expects float
    if input_details.get('dtype') == np.float32:
        img_array = img_array / 255.0

    # Ensure shape (H, W, 3)
    if img_array.ndim == 2:
        img_array = np.stack([img_array] * 3, axis=-1)

    logger.info(f'Prepared image array shape (H,W,C): {img_array.shape}')
    return img_array


def run_full_inference_pipeline(
    image_source: Union[str, np.ndarray, Image.Image],
    yolo_model_path: str,
    pest_model_path: str,
    severity_model_path: str,
    use_lite_size: bool = False
) -> Dict:
    """
    Execute the complete inference pipeline (no object detection):
    1. Resize full image
    2. Run pest classifier
    3. Run severity classifier
    4. Generate recommendations
    """
    try:
        logger.info("Starting full inference pipeline (no detection) - using full image")

        # Step 1: Load pest classifier and prepare image for it
        pest_interpreter = load_tflite_model(pest_model_path, 'pest')
        pest_image = prepare_image_for_interpreter(pest_interpreter, image_source)
        pest_result = predict_pest_class(pest_interpreter, pest_image)

        # Step 2: Load severity classifier and prepare image for it (may differ in input size)
        severity_interpreter = load_tflite_model(severity_model_path, 'severity')
        # If severity model expects same shape as pest model, reuse; otherwise prepare separately
        try:
            pest_input = pest_interpreter.get_input_details()[0]['shape']
            sev_input = severity_interpreter.get_input_details()[0]['shape']
            same_shape = list(pest_input) == list(sev_input)
        except Exception:
            same_shape = False

        if same_shape:
            severity_image = pest_image
        else:
            severity_image = prepare_image_for_interpreter(severity_interpreter, image_source)

        severity_result = predict_severity_class(severity_interpreter, severity_image)
        
        # Step 6: Generate recommendations
        recommendations_result = generate_recommendations(
            pest_result['predicted_pest'],
            severity_result['severity']
        )
        
        # Compile results
        final_result = {
            'success': True,
            'pest': pest_result['predicted_pest'],
            'pest_confidence': pest_result['confidence_score'],
            'pest_probabilities': pest_result['probabilities'],
            'severity': severity_result['severity'],
            'damage_percentage': severity_result['damage_percentage'],
            'severity_confidence': severity_result['confidence_score'],
            'severity_probabilities': severity_result['probabilities'],
            'recommendations': recommendations_result['recommendation'],
            'risk_level': recommendations_result['risk'],
            'urgency': recommendations_result['urgency'],
            'risk_factors': recommendations_result['risk_factors']
        }
        
        logger.info(f"Pipeline complete: {pest_result['predicted_pest']} - {severity_result['severity']}")
        return final_result
        
    except Exception as e:
        logger.error(f"Full pipeline error: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'pest': 'Unknown',
            'severity': 'Unknown',
            'confidence': 0.0,
            'recommendations': []
        }

