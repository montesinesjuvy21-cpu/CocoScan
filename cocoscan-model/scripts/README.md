# Scripts guide

This folder contains the command-line utilities for the CocoScan pipeline.

## Files

- train_pest_classifier.py: trains the pest classifier.
- train_severity_classifier.py: trains the severity classifier.
- train_yolo.py: trains the YOLO object detector.
- retrain_models.py: retrains classifiers and YOLO together.
- evaluate_model.py: evaluates a trained classifier on test data.
- infer_with_detection.py: runs inference with optional YOLO filtering.
- convert_to_tflite.py: converts a Keras model to TensorFlow Lite.
- crop_yolo_detections.py: crops YOLO-detected leaf regions for classifier training.

## How to use

Run each script from the project root.

Example:

```bash
python scripts/train_yolo.py --data_config yolo_leaf_detection.yaml --model yolov8n.pt --epochs 10 --imgsz 640 --batch_size 8 --device cpu
```
