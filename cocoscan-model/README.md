# CocoScan

CocoScan is a coconut leaf analysis project for detecting pests, estimating damage severity, and generating recommendations. The system combines TensorFlow/Keras classifiers with optional YOLO-based detection and a lightweight rule-based recommendation engine.

## What this repository contains

- A pest classifier for identifying healthy leaves, rhinoceros beetle damage, and brontispa damage.
- A severity classifier for mild, moderate, and severe damage levels.
- A YOLO-based detection pipeline for locating leaf regions before classification.
- Training, evaluation, conversion, and inference scripts for local use and mobile deployment.

## Repository structure

### Root files

- [README.md](README.md) - Main documentation for the project.
- [requirements.txt](requirements.txt) - Python dependencies.
- [yolo_leaf_detection.yaml](yolo_leaf_detection.yaml) - YOLO dataset configuration.

### Core package: [cocoscan](cocoscan)

- [cocoscan/__init__.py](cocoscan/__init__.py) - Exports the public API for the project.
- [cocoscan/data.py](cocoscan/data.py) - Loads image data and builds Keras data generators.
- [cocoscan/model.py](cocoscan/model.py) - Defines the classifier model architectures.
- [cocoscan/inference.py](cocoscan/inference.py) - Runs pest and severity prediction for images and batches.
- [cocoscan/inference_with_detection.py](cocoscan/inference_with_detection.py) - Combines classification with YOLO-based cropping.
- [cocoscan/detection.py](cocoscan/detection.py) - Handles YOLO detection and bounding-box processing.
- [cocoscan/evaluate.py](cocoscan/evaluate.py) - Calculates evaluation metrics and reports.
- [cocoscan/recommendations.py](cocoscan/recommendations.py) - Creates risk-based recommendations.

### Data folders

- [dataset](dataset) - Main pest-classification dataset with train, validation, and test splits.
- [severity_dataset](severity_dataset) - Severity-classification dataset with mild, moderate, and severe splits.
- [yolo_dataset](yolo_dataset) - YOLO-ready image and label folders for detector training.

### Scripts: [scripts](scripts)

- [scripts/train_pest_classifier.py](scripts/train_pest_classifier.py) - Trains the pest classifier.
- [scripts/train_severity_classifier.py](scripts/train_severity_classifier.py) - Trains the severity classifier.
- [scripts/train_yolo.py](scripts/train_yolo.py) - Trains the YOLO detector.
- [scripts/retrain_models.py](scripts/retrain_models.py) - Retrains the classifiers and YOLO detector together.
- [scripts/evaluate_model.py](scripts/evaluate_model.py) - Evaluates a trained classifier on test data.
- [scripts/infer_with_detection.py](scripts/infer_with_detection.py) - Runs inference with optional YOLO filtering.
- [scripts/convert_to_tflite.py](scripts/convert_to_tflite.py) - Converts a Keras model to TensorFlow Lite.
- [scripts/crop_yolo_detections.py](scripts/crop_yolo_detections.py) - Crops YOLO detections into classifier training images.

### Output folders

- [models](models) - Stores trained .h5 models and converted .tflite files.
- [runs](runs) - Stores experiment outputs from YOLO training runs.

## File-by-file guide

### Root files

- [requirements.txt](requirements.txt) lists the required Python packages such as TensorFlow, NumPy, scikit-learn, and Ultralytics.
- [yolo_leaf_detection.yaml](yolo_leaf_detection.yaml) tells YOLO where the training, validation, and test images are located.

### Core package files

- [cocoscan/__init__.py](cocoscan/__init__.py) exposes the main functions used across the project.
- [cocoscan/data.py](cocoscan/data.py) prepares datasets and provides image preprocessing helpers.
- [cocoscan/model.py](cocoscan/model.py) defines the lightweight CNN, MobileNetV2, and EfficientNetB0-based model builders.
- [cocoscan/inference.py](cocoscan/inference.py) loads a trained classifier and returns pest or severity predictions.
- [cocoscan/inference_with_detection.py](cocoscan/inference_with_detection.py) runs detection first, crops the best leaf region, and then classifies it.
- [cocoscan/detection.py](cocoscan/detection.py) runs YOLO inference and extracts bounding boxes.
- [cocoscan/evaluate.py](cocoscan/evaluate.py) computes accuracy, confusion matrices, and classification reports.
- [cocoscan/recommendations.py](cocoscan/recommendations.py) translates model outputs into practical actions and risk levels.

### Script files

- [scripts/train_pest_classifier.py](scripts/train_pest_classifier.py) trains the pest classifier from the data directory.
- [scripts/train_severity_classifier.py](scripts/train_severity_classifier.py) trains the severity classifier.
- [scripts/train_yolo.py](scripts/train_yolo.py) trains the YOLO object detector from the YAML config.
- [scripts/retrain_models.py](scripts/retrain_models.py) retrains the classifiers and YOLO detector together with optimized settings.
- [scripts/evaluate_model.py](scripts/evaluate_model.py) evaluates a trained model on test images.
- [scripts/infer_with_detection.py](scripts/infer_with_detection.py) runs inference from the command line with optional YOLO filtering.
- [scripts/convert_to_tflite.py](scripts/convert_to_tflite.py) exports a trained model to TensorFlow Lite.
- [scripts/crop_yolo_detections.py](scripts/crop_yolo_detections.py) crops detected leaf regions to build or expand classifier training data.

## Dataset layout

```text
dataset/
├── train/
│   ├── rhinoceros_beetle/
│   ├── brontispa/
│   └── healthy/
├── validation/
│   ├── rhinoceros_beetle/
│   ├── brontispa/
│   └── healthy/
└── test/
    ├── rhinoceros_beetle/
    ├── brontispa/
    └── healthy/
```

The severity dataset follows the same structure, but with severity folders such as mild, moderate, and severe.

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Train the pest classifier

```bash
python scripts/train_pest_classifier.py --data_dir dataset --output_path models/pest_classifier.h5
```

### 3. Train the severity classifier

```bash
python scripts/train_severity_classifier.py --data_dir severity_dataset --output_path models/severity_classifier.h5
```

### 4. Train the YOLO detector

```bash
python scripts/train_yolo.py --data_config yolo_leaf_detection.yaml --model yolov8n.pt --epochs 10 --imgsz 640 --batch_size 8 --device cpu
```

### 5. Evaluate a trained classifier

```bash
python scripts/evaluate_model.py --model_path models/pest_classifier.h5 --data_dir dataset --model_type pest
```

### 6. Run inference

```bash
python scripts/infer_with_detection.py --task pest --model_path models/pest_classifier.h5 --image_path path/to/image.jpg
```

## How to run and integrate the models

### Run the pest classifier from Python

```python
from cocoscan.inference import predict_pest

result = predict_pest(
    model_path="models/pest_classifier.h5",
    image_path="path/to/leaf.jpg",
    use_lite_size=False,
)

print(result["predicted_pest"])
print(result["confidence_score"])
```

### Run the severity classifier from Python

```python
from cocoscan.inference import predict_severity

result = predict_severity(
    model_path="models/severity_classifier.h5",
    image_path="path/to/leaf.jpg",
    use_lite_size=False,
)

print(result["severity"])
print(result["damage_percentage"])
```

### Run inference with YOLO filtering

```python
from cocoscan.inference_with_detection import predict_pest

result = predict_pest(
    model_path="models/pest_classifier.h5",
    image_path="path/to/leaf.jpg",
    yolo_weights_path="yolov8n.pt",
    yolo_device="cpu",
    yolo_confidence=0.25,
)

print(result)
```

### Command-line inference

```bash
python scripts/infer_with_detection.py \
  --task pest \
  --model_path models/pest_classifier.h5 \
  --image_path path/to/leaf.jpg \
  --yolo_confidence 0.25 \
  --output_json results.json
```

### Integrating into a main application

A simple production flow is:

1. Load the YOLO detector and detect a coconut leaf region.
2. Crop the detected region and resize it.
3. Run the pest classifier.
4. Run the severity classifier.
5. Use the recommendation engine to suggest actions.

Example:

```python
from cocoscan.inference_with_detection import predict_pest
from cocoscan.inference import predict_severity
from cocoscan.recommendations import recommend_actions

pest_result = predict_pest(
    model_path="models/pest_classifier.h5",
    image_path="path/to/leaf.jpg",
    yolo_weights_path="yolov8n.pt",
    yolo_device="cpu",
)

severity_result = predict_severity(
    model_path="models/severity_classifier.h5",
    image_path="path/to/leaf.jpg",
    use_lite_size=False,
)

recommendation = recommend_actions(
    pest_result["predicted_pest"],
    severity_result["severity"],
    risk_score=70,
)

print(recommendation)
```

### Notes

- Use the lightweight model for mobile or low-resource environments.
- Use the YOLO detector when you want to crop leaf regions before classification.
- The project supports both 224x224 and 160x160 classifier inputs.


### The main YOLO integration file is detection.py.

It is the core module that:
- loads a YOLO model,
- runs detection on an image,
- extracts bounding boxes,
- and returns detections for the rest of the pipeline.

If you want the full end-to-end integration path, use:
- inference_with_detection.py for classifier inference with YOLO-based cropping.
- infer_with_detection.py if you want a command-line entry point.

For training, use:
train_yolo.py

So the short answer is:
Integration logic: detection.py
End-to-end YOLO + classifier usage: inference_with_detection.py

### Notes para sa YOLo and model integration
so when integrating the YOLO and the models the other developer needs the detection.py?

Yes — if the other developer is integrating the YOLO part into the full pipeline, they will need detection.py.

That file is the main bridge between YOLO and the rest of the system because it:

loads the YOLO model,
runs detection,
extracts bounding boxes,
and prepares detections for downstream use.
For a full integration, they would typically use:

detection.py for the YOLO logic
inference_with_detection.py for the combined “detect → crop → classify” flow
So the practical answer is:

Yes, they need detection.py if they want YOLO detection.
They may not need it directly if they only use the higher-level wrapper inference_with_detection.py.

### Another Note
so the classifiers that has a .h5 extension and tflite extension is the file the ,odel only needs then the detection.py or the infer is the one to completely integrate the yolo + models?

Yes — that is the right way to think about it.

The classifier model files such as .h5 and .tflite are the trained classification models.
They are used by the inference code to predict pest or severity.
They do not themselves contain the YOLO logic.
For integration, the flow is:

YOLO detects a leaf region

handled by detection.py
The detected region is cropped and passed to the classifier

handled by inference_with_detection.py
The classifier model (.h5 or .tflite) makes the prediction

loaded inside the inference functions
So:

If the developer only wants to use the trained classifier model, they need the .h5 or .tflite model file plus the inference module.
If they want the full YOLO + classifier pipeline, they need:
detection.py for YOLO detection
inference_with_detection.py for the combined pipeline
and the classifier model file (.h5 or .tflite)
In short:

Model file = classifier
detection.py = YOLO detection piece
inference_with_detection.py = full integration layer for YOLO + model