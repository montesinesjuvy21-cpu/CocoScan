import numpy as np
import tensorflow as tf
from .data import get_single_image, TARGET_SIZE, TARGET_SIZE_LITE
from .detection import (
    is_yolo_available,
    load_yolo_model,
    run_yolo_detection,
    crop_image_from_box,
    select_best_detection,
)

PEST_LABELS = ["Rhinoceros Beetle", "Brontispa", "Healthy Coconut Leaf"]
SEVERITY_LABELS = ["Mild", "Moderate", "Severe"]


def _prepare_image_for_inference(image_path, target_size, detection_model=None, detection_confidence=0.25):
    if detection_model is None:
        return get_single_image(image_path, target_size=target_size), None

    detections = run_yolo_detection(image_path, model=detection_model, conf_threshold=detection_confidence)
    best = select_best_detection(detections)
    if best is None:
        return None, detections

    cropped = crop_image_from_box(image_path, best["box"], target_size=target_size)
    return cropped, detections


def predict_pest(
    model_path,
    image_path,
    use_lite_size=False,
    yolo_weights_path=None,
    yolo_device="cpu",
    yolo_confidence=0.25,
):
    model = tf.keras.models.load_model(model_path)
    target_size = TARGET_SIZE_LITE if use_lite_size else TARGET_SIZE

    detection_model = None
    if yolo_weights_path or is_yolo_available():
        detection_model = load_yolo_model(weights_path=yolo_weights_path, device=yolo_device)

    image, detections = _prepare_image_for_inference(
        image_path,
        target_size,
        detection_model=detection_model,
        detection_confidence=yolo_confidence,
    )

    if image is None:
        return {
            "predicted_pest": None,
            "confidence_score": 0.0,
            "probabilities": {},
            "detection_failure": True,
            "detections": detections,
            "message": "No valid object detected by YOLO.",
        }

    probabilities = model.predict(np.expand_dims(image, axis=0))[0]
    index = int(np.argmax(probabilities))
    return {
        "predicted_pest": PEST_LABELS[index],
        "confidence_score": float(probabilities[index]),
        "probabilities": {label: float(score) for label, score in zip(PEST_LABELS, probabilities)},
        "detections": detections,
    }


def predict_severity(
    model_path,
    image_path,
    use_lite_size=False,
    yolo_weights_path=None,
    yolo_device="cpu",
    yolo_confidence=0.25,
):
    model = tf.keras.models.load_model(model_path)
    target_size = TARGET_SIZE_LITE if use_lite_size else TARGET_SIZE

    detection_model = None
    if yolo_weights_path or is_yolo_available():
        detection_model = load_yolo_model(weights_path=yolo_weights_path, device=yolo_device)

    image, detections = _prepare_image_for_inference(
        image_path,
        target_size,
        detection_model=detection_model,
        detection_confidence=yolo_confidence,
    )

    if image is None:
        return {
            "severity": None,
            "damage_percentage": 0,
            "confidence_score": 0.0,
            "probabilities": {},
            "detection_failure": True,
            "detections": detections,
            "message": "No valid object detected by YOLO.",
        }

    probabilities = model.predict(np.expand_dims(image, axis=0))[0]
    index = int(np.argmax(probabilities))
    severity = SEVERITY_LABELS[index]
    damage_percentage = {"Mild": 18, "Moderate": 48, "Severe": 78}[severity]
    return {
        "severity": severity,
        "damage_percentage": damage_percentage,
        "confidence_score": float(probabilities[index]),
        "probabilities": {label: float(score) for label, score in zip(SEVERITY_LABELS, probabilities)},
        "detections": detections,
    }
