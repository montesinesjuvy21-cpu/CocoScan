import numpy as np
import tensorflow as tf
from .data import get_single_image, TARGET_SIZE, TARGET_SIZE_LITE
from .evaluate import calculate_batch_accuracy

PEST_LABELS = ["Rhinoceros Beetle", "Brontispa", "Healthy Coconut Leaf"]
SEVERITY_LABELS = ["Mild", "Moderate", "Severe"]


def predict_pest(model_path, image_path, use_lite_size=False):
    model = tf.keras.models.load_model(model_path)
    target_size = TARGET_SIZE_LITE if use_lite_size else TARGET_SIZE
    image = get_single_image(image_path, target_size=target_size)
    probabilities = model.predict(np.expand_dims(image, axis=0))[0]
    index = int(np.argmax(probabilities))
    return {
        "predicted_pest": PEST_LABELS[index],
        "confidence_score": float(probabilities[index]),
        "probabilities": {label: float(score) for label, score in zip(PEST_LABELS, probabilities)},
    }


def predict_severity(model_path, image_path, use_lite_size=False):
    model = tf.keras.models.load_model(model_path)
    target_size = TARGET_SIZE_LITE if use_lite_size else TARGET_SIZE
    image = get_single_image(image_path, target_size=target_size)
    probabilities = model.predict(np.expand_dims(image, axis=0))[0]
    index = int(np.argmax(probabilities))
    severity = SEVERITY_LABELS[index]
    damage_percentage = {"Mild": 18, "Moderate": 48, "Severe": 78}[severity]
    return {
        "severity": severity,
        "damage_percentage": damage_percentage,
        "confidence_score": float(probabilities[index]),
        "probabilities": {label: float(score) for label, score in zip(SEVERITY_LABELS, probabilities)},
    }


def batch_predict_pest(model_path, image_paths, use_lite_size=False, true_labels=None):
    """
    Predict pest for multiple images and optionally calculate accuracy.
    
    Args:
        model_path: Path to trained pest model
        image_paths: List of image file paths
        use_lite_size: Use 160x160 input if True
        true_labels: Optional list of true labels for accuracy calculation
    
    Returns:
        Dictionary with predictions and optional accuracy metrics
    """
    model = load_model(model_path)
    target_size = TARGET_SIZE_LITE if use_lite_size else TARGET_SIZE
    
    predictions = []
    pred_labels = []
    
    for image_path in image_paths:
        image = get_single_image(image_path, target_size=target_size)
        probabilities = model.predict(np.expand_dims(image, axis=0), verbose=0)[0]
        pred_index = int(np.argmax(probabilities))
        pred_label = PEST_LABELS[pred_index]
        pred_labels.append(pred_label)
        
        result = {
            "image": image_path,
            "predicted_pest": pred_label,
            "confidence_score": float(probabilities[pred_index]),
            "probabilities": {label: float(score) for label, score in zip(PEST_LABELS, probabilities)},
        }
        
        if true_labels:
            result["true_label"] = true_labels[len(predictions)]
            result["correct"] = pred_label == result["true_label"]
        
        predictions.append(result)
    
    output = {
        "total_predictions": len(image_paths),
        "predictions": predictions,
    }
    
    if true_labels:
        accuracy_metrics = calculate_batch_accuracy(pred_labels, true_labels)
        output.update(accuracy_metrics)
    
    return output


def batch_predict_severity(model_path, image_paths, use_lite_size=False, true_labels=None):
    """
    Predict severity for multiple images and optionally calculate accuracy.
    
    Args:
        model_path: Path to trained severity model
        image_paths: List of image file paths
        use_lite_size: Use 160x160 input if True
        true_labels: Optional list of true labels for accuracy calculation
    
    Returns:
        Dictionary with predictions and optional accuracy metrics
    """
    model = load_model(model_path)
    target_size = TARGET_SIZE_LITE if use_lite_size else TARGET_SIZE
    
    predictions = []
    pred_labels = []
    
    for image_path in image_paths:
        image = get_single_image(image_path, target_size=target_size)
        probabilities = model.predict(np.expand_dims(image, axis=0), verbose=0)[0]
        pred_index = int(np.argmax(probabilities))
        severity = SEVERITY_LABELS[pred_index]
        pred_labels.append(severity)
        damage_percentage = {"Mild": 18, "Moderate": 48, "Severe": 78}[severity]
        
        result = {
            "image": image_path,
            "severity": severity,
            "damage_percentage": damage_percentage,
            "confidence_score": float(probabilities[pred_index]),
            "probabilities": {label: float(score) for label, score in zip(SEVERITY_LABELS, probabilities)},
        }
        
        if true_labels:
            result["true_label"] = true_labels[len(predictions)]
            result["correct"] = severity == result["true_label"]
        
        predictions.append(result)
    
    output = {
        "total_predictions": len(image_paths),
        "predictions": predictions,
    }
    
    if true_labels:
        accuracy_metrics = calculate_batch_accuracy(pred_labels, true_labels)
        output.update(accuracy_metrics)
    
    return output

