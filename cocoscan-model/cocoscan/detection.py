import os
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

_YOLO_MODEL_CACHE = {}


def is_yolo_available() -> bool:
    return torch is not None and hasattr(torch, "hub")


def load_yolo_model(
    weights_path: Optional[str] = None,
    device: str = "cpu",
    force_reload: bool = False,
):
    if not is_yolo_available():
        raise ImportError(
            "YOLO support requires PyTorch. Install it with: pip install torch torchvision"
        )

    cache_key = f"{weights_path or 'yolov5s'}_{device}"
    if cache_key in _YOLO_MODEL_CACHE and not force_reload:
        return _YOLO_MODEL_CACHE[cache_key]

    if weights_path and os.path.isfile(weights_path):
        model = torch.hub.load(
            "ultralytics/yolov5",
            "custom",
            path=weights_path,
            force_reload=force_reload,
        )
    else:
        model = torch.hub.load(
            "ultralytics/yolov5",
            "yolov5s",
            pretrained=True,
            force_reload=force_reload,
        )

    model.to(device)
    model.eval()
    _YOLO_MODEL_CACHE[cache_key] = model
    return model


def run_yolo_detection(
    image_source: Union[str, np.ndarray, Image.Image],
    model=None,
    conf_threshold: float = 0.25,
    size: int = 640,
):
    if model is None:
        model = load_yolo_model()

    if isinstance(image_source, Image.Image):
        image_input = np.array(image_source)
    else:
        image_input = image_source

    results = model(image_input, size=size)
    detections = []

    if len(results.xyxy) == 0 or len(results.xyxy[0]) == 0:
        return detections

    for row in results.xyxy[0].cpu().numpy():
        x1, y1, x2, y2, confidence, class_id = row[:6]
        if confidence < conf_threshold:
            continue
        class_id = int(class_id)
        class_name = results.names[class_id] if hasattr(results, "names") else str(class_id)
        box = [float(x1), float(y1), float(x2), float(y2)]
        detections.append(
            {
                "label": class_name,
                "confidence": float(confidence),
                "box": box,
                "class_id": class_id,
            }
        )

    return detections


def crop_image_from_box(
    image_source: Union[str, np.ndarray, Image.Image],
    box: Tuple[float, float, float, float],
    target_size: Tuple[int, int] = (224, 224),
) -> np.ndarray:
    if isinstance(image_source, Image.Image):
        image = image_source.convert("RGB")
    elif isinstance(image_source, np.ndarray):
        image = Image.fromarray(image_source.astype("uint8"), "RGB")
    else:
        image = Image.open(image_source).convert("RGB")

    x1, y1, x2, y2 = [int(max(0, coord)) for coord in box]
    x2 = min(image.width, x2)
    y2 = min(image.height, y2)
    cropped = image.crop((x1, y1, x2, y2))
    if cropped.width == 0 or cropped.height == 0:
        cropped = image
    cropped = cropped.resize(target_size)
    return np.array(cropped) / 255.0


def select_best_detection(
    detections: List[Dict],
    allowed_labels: Optional[List[str]] = None,
):
    if allowed_labels is not None:
        detections = [d for d in detections if d["label"] in allowed_labels]

    if not detections:
        return None

    return max(detections, key=lambda d: d["confidence"])
