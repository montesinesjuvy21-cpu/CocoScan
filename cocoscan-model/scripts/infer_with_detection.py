import os
import sys

# Ensure project root is on Python path so 'cocoscan' package resolves when running scripts
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
import json
from cocoscan.inference_with_detection import (
    predict_pest_with_detection,
    predict_severity_with_detection,
)
from cocoscan.detection import is_yolo_available


def parse_args():
    parser = argparse.ArgumentParser(description="Run inference with optional YOLO filtering")
    parser.add_argument("--task", choices=["pest", "severity"], required=True,
                        help="Prediction task: pest or severity")
    parser.add_argument("--model_path", required=True, help="Path to the trained Keras model (.h5)")
    parser.add_argument("--image_path", required=True, help="Path to the input image")
    parser.add_argument("--use_lite", action="store_true", help="Use smaller input size for the classifier")
    parser.add_argument("--yolo_weights_path", default=None,
                        help="Optional path to a custom YOLO weights file")
    parser.add_argument("--yolo_device", default="cpu", choices=["cpu", "cuda"],
                        help="Device to run YOLO on")
    parser.add_argument("--yolo_confidence", type=float, default=0.25,
                        help="Minimum YOLO confidence threshold for detections")
    parser.add_argument("--output_json", default=None,
                        help="Optional path to write the JSON result to disk")
    parser.add_argument("--quiet", action="store_true", help="Only print the JSON result")
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.isfile(args.image_path):
        raise FileNotFoundError(f"Input image not found: {args.image_path}")

    if not os.path.isfile(args.model_path):
        raise FileNotFoundError(f"Model file not found: {args.model_path}")

    if not is_yolo_available() and args.yolo_weights_path is None:
        print("WARNING: YOLO is not available in this environment. Running classifier without detection.")

    if args.task == "pest":
        result = predict_pest_with_detection(
            args.model_path,
            args.image_path,
            use_lite_size=args.use_lite,
            yolo_weights_path=args.yolo_weights_path,
            yolo_device=args.yolo_device,
            yolo_confidence=args.yolo_confidence,
        )
    else:
        result = predict_severity_with_detection(
            args.model_path,
            args.image_path,
            use_lite_size=args.use_lite,
            yolo_weights_path=args.yolo_weights_path,
            yolo_device=args.yolo_device,
            yolo_confidence=args.yolo_confidence,
        )

    output = json.dumps(result, indent=2)
    if args.output_json:
        os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            f.write(output)

    if args.quiet:
        print(output)
    else:
        print("Inference result:")
        print(output)


if __name__ == "__main__":
    main()
