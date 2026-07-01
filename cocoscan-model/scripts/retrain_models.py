import argparse
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import tensorflow as tf
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cocoscan.data import TARGET_SIZE, TARGET_SIZE_LITE, get_image_generators
from cocoscan.model import (
    build_efficientnet_b0,
    build_lightweight_cnn,
    build_mobilenet_v2,
    compile_model,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Optimized retraining for CocoScan classifiers and YOLO detector")
    parser.add_argument("--pest_data_dir", default="dataset", help="Path to pest classification dataset")
    parser.add_argument("--severity_data_dir", default="severity_dataset", help="Path to severity dataset")
    parser.add_argument("--yolo_data_config", default="yolo_leaf_detection.yaml", help="YOLO data config YAML")
    parser.add_argument("--output_dir", default="models/retrained", help="Directory for retrained models")
    parser.add_argument("--pest_output", default=None, help="Path to save the retrained pest model")
    parser.add_argument("--severity_output", default=None, help="Path to save the retrained severity model")
    parser.add_argument("--pest_model", choices=["mobilenetv2", "efficientnetb0", "lightweight"], default="mobilenetv2")
    parser.add_argument("--severity_model", choices=["mobilenetv2", "efficientnetb0", "lightweight"], default="mobilenetv2")
    parser.add_argument("--epochs", type=int, default=20, help="Training epochs for the classifiers")
    parser.add_argument("--batch_size", type=int, default=16, help="Batch size for classifier training")
    parser.add_argument("--learning_rate", type=float, default=1e-4, help="Initial learning rate")
    parser.add_argument("--lite", action="store_true", help="Use 160x160 input size for faster training")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--mixed_precision", action="store_true", help="Enable mixed precision on GPU")
    parser.add_argument("--yolo_model", default="yolov8n.pt", help="YOLO model spec or weights (for example yolov8n.pt or yolov8s.pt)")
    parser.add_argument("--yolo_epochs", type=int, default=25, help="YOLO training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="YOLO input image size")
    parser.add_argument("--device", default="cuda", help="YOLO device: cpu or cuda")
    parser.add_argument("--cache", action="store_true", help="Cache YOLO images for faster training")
    parser.add_argument("--project", default="runs/train", help="YOLO training output directory")
    parser.add_argument("--name", default="cocoscan_yolo", help="YOLO run name")
    return parser.parse_args()


def setup_runtime(args):
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    tf.keras.utils.set_random_seed(args.seed)

    if args.mixed_precision and tf.config.list_physical_devices("GPU"):
        tf.keras.mixed_precision.set_global_policy("mixed_float16")
        print("Enabled mixed precision training on GPU")
    else:
        print("Using default float32 training")


def resolve_data_config(data_config_path):
    config_path = os.path.abspath(data_config_path)
    with open(config_path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    base_dir = os.path.dirname(config_path)
    dataset_root = data.get("path", ".")
    if dataset_root:
        if os.path.isabs(dataset_root):
            resolved_root = dataset_root
        else:
            resolved_root = os.path.abspath(os.path.join(base_dir, dataset_root))
    else:
        resolved_root = base_dir

    resolved = dict(data)
    resolved["path"] = resolved_root

    for key in ("train", "val", "test"):
        value = resolved.get(key)
        if not isinstance(value, str) or not value:
            continue
        if value.startswith(("http://", "https://", "s3://", "gs://")):
            continue
        if os.path.isabs(value):
            resolved[key] = value
        else:
            resolved[key] = os.path.abspath(os.path.join(resolved_root, value))

    if "val" not in resolved and "valid" in resolved:
        resolved["val"] = resolved["valid"]

    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"resolved_{os.path.basename(config_path)}")
    with open(temp_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(resolved, handle, sort_keys=False)
    return temp_path


def build_classifier_model(model_name, num_classes, lite):
    input_shape = (160, 160, 3) if lite else (224, 224, 3)
    if model_name == "lightweight":
        if not lite:
            print("Warning: lightweight model performs best with --lite")
        return build_lightweight_cnn(num_classes=num_classes, input_shape=input_shape)
    if model_name == "efficientnetb0":
        return build_efficientnet_b0(num_classes=num_classes, input_shape=input_shape)
    return build_mobilenet_v2(num_classes=num_classes, input_shape=input_shape)


def compute_class_weights(train_gen):
    classes = np.asarray(train_gen.classes, dtype=np.int32)
    class_count = np.bincount(classes, minlength=len(train_gen.class_indices))
    total = class_count.sum()
    weights = total / (len(class_count) * class_count.astype(np.float32))
    return {idx: float(weight) for idx, weight in enumerate(weights)}


def train_classifier(data_dir, output_path, model_name, epochs, batch_size, learning_rate, lite):
    target_size = TARGET_SIZE_LITE if lite else TARGET_SIZE

    train_gen = get_image_generators(
        data_dir,
        "train",
        augment=True,
        batch_size=batch_size,
        target_size=target_size,
    )
    val_gen = get_image_generators(
        data_dir,
        "validation",
        augment=False,
        batch_size=batch_size,
        target_size=target_size,
    )

    model = build_classifier_model(model_name, train_gen.num_classes, lite)
    model = compile_model(model, learning_rate=learning_rate)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    class_weights = compute_class_weights(train_gen)
    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=6, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3, min_lr=1e-7),
        tf.keras.callbacks.ModelCheckpoint(output_path, monitor="val_loss", save_best_only=True),
    ]

    print(f"Training {model_name} classifier on {data_dir} with target size {target_size}")
    model.fit(
        train_gen,
        validation_data=val_gen,
        epochs=epochs,
        callbacks=callbacks,
        class_weight=class_weights,
    )

    model.save(output_path)
    print(f"Saved classifier to {output_path}")


def resolve_yolo_model(model_name):
    if model_name in {"yolov5s", "yolov5m", "yolov5l", "yolov5x"}:
        print(f"Converting YOLO model '{model_name}' to the supported Ultralytics preset 'yolov8n.pt'")
        return "yolov8n.pt"
    if os.path.isfile(model_name):
        return model_name
    return model_name


def train_yolo(data_config_path, model_name, epochs, imgsz, batch_size, device, cache, project, name):
    if importlib.util.find_spec("ultralytics") is None:
        print("Ultralytics is not installed. Skip YOLO retraining. Install it with: pip install ultralytics")
        return

    from ultralytics import YOLO

    resolved_model_name = resolve_yolo_model(model_name)
    resolved_config_path = resolve_data_config(data_config_path)
    print(f"Starting YOLO training with config: {resolved_config_path}")
    print(f"Using YOLO model: {resolved_model_name}")
    yolo_model = YOLO(resolved_model_name)
    yolo_model.train(
        data=resolved_config_path,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch_size,
        device=device,
        project=project,
        name=name,
        cache=cache,
    )
    print("YOLO training complete")


def main():
    args = parse_args()
    setup_runtime(args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pest_output = Path(args.pest_output) if args.pest_output else output_dir / "pest_classifier.h5"
    severity_output = Path(args.severity_output) if args.severity_output else output_dir / "severity_classifier.h5"

    train_classifier(
        data_dir=args.pest_data_dir,
        output_path=str(pest_output),
        model_name=args.pest_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        lite=args.lite,
    )

    train_classifier(
        data_dir=args.severity_data_dir,
        output_path=str(severity_output),
        model_name=args.severity_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        lite=args.lite,
    )

    train_yolo(
        data_config_path=args.yolo_data_config,
        model_name=args.yolo_model,
        epochs=args.yolo_epochs,
        imgsz=args.imgsz,
        batch_size=args.batch_size,
        device=args.device,
        cache=args.cache,
        project=args.project,
        name=args.name,
    )


if __name__ == "__main__":
    main()
