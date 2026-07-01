import os
import sys
import argparse
from pathlib import Path
from PIL import Image

# Ensure project root is on Python path so helper modules resolve if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import importlib.util


def is_ultralytics_available() -> bool:
    return importlib.util.find_spec('ultralytics') is not None


def parse_args():
    parser = argparse.ArgumentParser(description='Crop YOLO detections for classifier retraining')
    parser.add_argument('--yolo_weights', required=True, help='Path to trained YOLO weights (.pt or model spec)')
    parser.add_argument('--source_dir', required=True, help='Directory with images to crop')
    parser.add_argument('--output_dir', required=True, help='Directory to write cropped images')
    parser.add_argument('--confidence', type=float, default=0.25, help='Minimum detection confidence')
    parser.add_argument('--imgsz', type=int, default=224, help='Final crop image size')
    parser.add_argument('--label', default='leaf', help='Optional label folder name for the cropped output')
    parser.add_argument('--device', default='cpu', help='Device for YOLO inference')
    parser.add_argument('--recursive', action='store_true', help='Recursively scan source_dir for images')
    return parser.parse_args()


def load_yolo_model(weights_path, device='cpu'):
    from ultralytics import YOLO
    return YOLO(weights_path).to(device)


def normalize_box(box, width, height):
    x1, y1, x2, y2 = box
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(0, min(x2, width))
    y2 = max(0, min(y2, height))
    return int(x1), int(y1), int(x2), int(y2)


def process_image(image_path, model, confidence, imgsz):
    image = Image.open(image_path).convert('RGB')
    results = model(image)
    detections = []
    if len(results) == 0 or len(results[0].boxes) == 0:
        return detections

    for box in results[0].boxes:
        conf = float(box.conf[0])
        if conf < confidence:
            continue
        xyxy = box.xyxy[0].tolist()
        x1, y1, x2, y2 = normalize_box(xyxy, image.width, image.height)
        detections.append((conf, (x1, y1, x2, y2)))
    return sorted(detections, key=lambda x: x[0], reverse=True)


def crop_and_save(image_path, output_path, box, imgsz):
    image = Image.open(image_path).convert('RGB')
    cropped = image.crop(box)
    if cropped.width == 0 or cropped.height == 0:
        cropped = image
    cropped = cropped.resize((imgsz, imgsz))
    cropped.save(output_path)


def main():
    args = parse_args()

    if not is_ultralytics_available():
        raise ImportError('Ultralytics package is required. Install it with: pip install ultralytics')

    if not os.path.isfile(args.yolo_weights):
        raise FileNotFoundError(f'YOLO weights not found: {args.yolo_weights}')

    model = load_yolo_model(args.yolo_weights, device=args.device)
    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    image_paths = list(source_dir.rglob('*.jpg')) + list(source_dir.rglob('*.jpeg')) + list(source_dir.rglob('*.png'))
    if not image_paths:
        raise FileNotFoundError(f'No images found in {args.source_dir}')

    for image_path in image_paths:
        detections = process_image(str(image_path), model, args.confidence, args.imgsz)
        if not detections:
            continue

        best_box = detections[0][1]
        relative = image_path.relative_to(source_dir)
        output_path = output_dir / relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        crop_and_save(str(image_path), str(output_path), best_box, args.imgsz)

    print(f'Cropped images saved to {output_dir}')


if __name__ == '__main__':
    main()
