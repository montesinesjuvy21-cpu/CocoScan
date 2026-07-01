import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    classification_report,
    roc_auc_score,
    roc_curve,
)


def evaluate_predictions(y_true, y_pred, y_prob, target_names):
    report = classification_report(y_true, y_pred, target_names=target_names, output_dict=True)
    matrix = confusion_matrix(y_true, y_pred)
    accuracy = accuracy_score(y_true, y_pred)
    metrics = {
        "accuracy": accuracy,
        "accuracy_percentage": accuracy * 100,
        "classification_report": report,
        "confusion_matrix": matrix.tolist(),
    }

    if y_prob is not None and y_prob.shape[1] == len(target_names):
        try:
            auc = roc_auc_score(y_true, y_prob, multi_class="ovo")
            metrics["roc_auc"] = float(auc)
        except Exception:
            metrics["roc_auc"] = None

    return metrics


def build_roc_curves(y_true, y_prob, target_names):
    if y_prob is None:
        return {}

    curves = {}
    for idx, label in enumerate(target_names):
        fpr, tpr, thresholds = roc_curve(np.array(y_true) == idx, y_prob[:, idx])
        curves[label] = {
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist(),
            "thresholds": thresholds.tolist(),
        }
    return curves


def calculate_batch_accuracy(predictions, true_labels):
    """
    Calculate accuracy percentage from batch predictions.
    
    Args:
        predictions: List of predicted labels
        true_labels: List of true labels
    
    Returns:
        Dictionary with accuracy metrics
    """
    if len(predictions) != len(true_labels):
        raise ValueError("Predictions and true labels must have same length")
    
    correct_count = sum(1 for pred, true in zip(predictions, true_labels) if pred == true)
    total_count = len(predictions)
    accuracy = (correct_count / total_count) * 100
    
    return {
        "accuracy_percentage": accuracy,
        "correct_predictions": correct_count,
        "incorrect_predictions": total_count - correct_count,
        "total_predictions": total_count,
    }
