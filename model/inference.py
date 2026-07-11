from pathlib import Path
import base64
import importlib
import io
from typing import Optional

import numpy as np
from PIL import Image

MODEL_DIR = Path(__file__).resolve().parent.parent / "model"
MODEL_FILE_NAME = "pest_classifier_YOLO.tflite"
# The TFLite model outputs 4 scores. The class order is aligned to the trained labels:
# [Brontispa, Healthy Coconut Leaf, Rhinoceros Beetle, Not a Coconut Leaf Image]
PEST_LABELS = ["Brontispa", "Healthy Coconut Leaf", "Rhinoceros Beetle", "Not a Coconut Leaf Image"]
# Lowered confidence cutoff to 25% so more valid leaf scans are accepted.
MIN_CONFIDENCE_THRESHOLD = 0.25
NOT_COCONUT_LEAF_LABEL = "Not a Coconut Leaf Image"
UNKNOWN_LABEL_BASE = NOT_COCONUT_LEAF_LABEL
MIN_IMAGE_DIMENSION = 32
GREEN_MEAN_THRESHOLD = 20.0
LEAF_GREEN_RATIO_THRESHOLD = 0.05

_cached_interpreter = None
_cached_model_path: Optional[Path] = None


def _import_tflite_interpreter():
    try:
        from tensorflow.lite import Interpreter
        return Interpreter
    except ImportError:
        pass

    try:
        import tensorflow as tf
        return tf.lite.Interpreter
    except ImportError:
        pass

    raise RuntimeError(
        "Neither TensorFlow Lite nor tflite-runtime is installed."
    )


def get_model_path(model_path: Optional[str] = None) -> Path:
    target_path = Path(model_path) if model_path else MODEL_DIR / MODEL_FILE_NAME
    if not target_path.exists():
        raise FileNotFoundError(f"TFLite model not found: {target_path}")
    return target_path


def _get_interpreter(model_path: Optional[str] = None):
    global _cached_interpreter, _cached_model_path
    model_path = get_model_path(model_path)
    if _cached_interpreter is None or _cached_model_path != model_path:
        Interpreter = _import_tflite_interpreter()
        interpreter = Interpreter(model_path=str(model_path))
        interpreter.allocate_tensors()
        _cached_interpreter = interpreter
        _cached_model_path = model_path
    return _cached_interpreter


def _softmax(values):
    values = np.asarray(values, dtype=np.float32)
    values = values - np.max(values)
    exp_values = np.exp(values)
    return exp_values / np.sum(exp_values)


def _decode_base64_image(image_data: str) -> Image.Image:
    if "," in image_data:
        image_data = image_data.split(",", 1)[1]
    image_bytes = base64.b64decode(image_data)
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def _validate_leaf_image(image: Image.Image):
    array = np.asarray(image).astype(np.float32)
    if array.ndim == 2:
        array = np.stack([array] * 3, axis=-1)

    if array.shape[-1] != 3:
        raise ValueError("Unsupported image format for inference.")

    height, width = array.shape[0], array.shape[1]
    if height < MIN_IMAGE_DIMENSION or width < MIN_IMAGE_DIMENSION:
        raise ValueError("Image is too small for reliable leaf detection.")

    red_mean = np.mean(array[..., 0])
    green_mean = np.mean(array[..., 1])
    blue_mean = np.mean(array[..., 2])
    green_ratio = green_mean / max(red_mean, blue_mean, 1.0)

    if green_mean < GREEN_MEAN_THRESHOLD or green_ratio < LEAF_GREEN_RATIO_THRESHOLD:
        raise ValueError("Image does not appear to be a coconut leaf or plant sample.")


def _prepare_input(image: Image.Image, input_details):
    shape = tuple(input_details[0]["shape"])
    dtype = np.dtype(input_details[0]["dtype"])

    if len(shape) == 4:
        batch, dim1, dim2, dim3 = shape
        if dim1 in (1, 3) and dim3 not in (1, 3):
            # NCHW format
            layout = 'nchw'
            channels = dim1
            height = dim2
            width = dim3
        else:
            # NHWC format
            layout = 'nhwc'
            height = dim1
            width = dim2
            channels = dim3
    elif len(shape) == 3:
        layout = 'nhwc'
        height, width, channels = shape
    else:
        raise ValueError(f"Unsupported input tensor shape: {shape}")

    if channels not in (1, 3):
        raise ValueError(f"Unsupported input channel count: {channels}")

    image = image.resize((width, height), Image.BILINEAR)
    array = np.asarray(image).astype(np.float32)

    if array.ndim == 2 and channels == 3:
        array = np.stack([array] * 3, axis=-1)

    if array.ndim == 3 and array.shape[-1] != channels:
        array = array[..., :channels]

    if dtype == np.float32 or dtype == np.float64:
        array = array / 255.0
    else:
        scale, zero_point = input_details[0].get("quantization", (0.0, 0))
        if scale and zero_point is not None:
            array = np.round(array / scale + zero_point).astype(dtype)
        else:
            array = array.astype(dtype)

    if len(shape) == 4:
        if layout == 'nchw':
            array = np.transpose(array, (2, 0, 1))
        array = np.expand_dims(array, 0)

    return array


def _run_inference(image: Image.Image, model_path: Optional[str] = None):
    _validate_leaf_image(image)
    interpreter = _get_interpreter(model_path)
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    input_tensor = _prepare_input(image, input_details)
    interpreter.set_tensor(input_details[0]["index"], input_tensor)
    interpreter.invoke()

    output_data = interpreter.get_tensor(output_details[0]["index"])
    output_data = np.squeeze(output_data)

    scale, zero_point = output_details[0].get("quantization", (0.0, 0))
    if scale and zero_point is not None:
        output_data = scale * (output_data.astype(np.float32) - zero_point)

    if output_data.ndim > 1 and output_data.shape[0] == 1:
        output_data = output_data[0]

    probabilities = _softmax(output_data)
    label_index = int(np.argmax(probabilities))
    labels = _get_labels(len(probabilities))
    label = labels[label_index]
    confidence = float(probabilities[label_index])

    if label == NOT_COCONUT_LEAF_LABEL:
        raise ValueError("This appears not to be a coconut leaf image. Please upload a proper coconut leaf photo.")

    if confidence < MIN_CONFIDENCE_THRESHOLD:
        raise ValueError("Prediction confidence is too low. Please upload a clearer leaf image.")

    return label, confidence, probabilities.tolist()


def _get_labels(num_classes: int):
    if num_classes <= len(PEST_LABELS):
        return PEST_LABELS[:num_classes]
    extra_labels = [UNKNOWN_LABEL_BASE] * (num_classes - len(PEST_LABELS))
    return PEST_LABELS + extra_labels


def predict_pest_from_base64(image_data: str, model_path: Optional[str] = None):
    image = _decode_base64_image(image_data)
    label, confidence, probabilities = _run_inference(image, model_path)
    labels = _get_labels(len(probabilities))
    return {
        "predicted_pest": label,
        "confidence_score": confidence,
        "probabilities": {labels[idx]: float(probabilities[idx]) for idx in range(len(probabilities))},
    }

