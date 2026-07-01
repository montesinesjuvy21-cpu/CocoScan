import os
import sys
import argparse
import importlib.util
import tempfile
import yaml

# Ensure project root is on Python path so helper modules resolve if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def is_ultralytics_available() -> bool:
    return importlib.util.find_spec('ultralytics') is not None


def resolve_data_config(data_config_path):
    config_path = os.path.abspath(data_config_path)
    with open(config_path, 'r', encoding='utf-8') as handle:
        data = yaml.safe_load(handle) or {}

    base_dir = os.path.dirname(config_path)
    dataset_root = data.get('path', '.')
    if dataset_root:
        if os.path.isabs(dataset_root):
            resolved_root = dataset_root
        else:
            resolved_root = os.path.abspath(os.path.join(base_dir, dataset_root))
    else:
        resolved_root = base_dir

    resolved = dict(data)
    resolved['path'] = resolved_root

    for key in ('train', 'val', 'test'):
        value = resolved.get(key)
        if not isinstance(value, str) or not value:
            continue
        if value.startswith(('http://', 'https://', 's3://', 'gs://')):
            continue
        if os.path.isabs(value):
            resolved[key] = value
        else:
            resolved[key] = os.path.abspath(os.path.join(resolved_root, value))

    if 'val' not in resolved and 'valid' in resolved:
        resolved['val'] = resolved['valid']

    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"resolved_{os.path.basename(config_path)}")
    with open(temp_path, 'w', encoding='utf-8') as handle:
        yaml.safe_dump(resolved, handle, sort_keys=False)
    return temp_path


def parse_args():
    parser = argparse.ArgumentParser(description='Train a YOLO model for leaf/pest detection')
    parser.add_argument('--data_config', required=True,
                        help='Path to the YOLO data config YAML file')
    parser.add_argument('--model', default='yolov8n.pt',
                        help='YOLO model spec or weights to use (for example yolov8n.pt, yolov8s.pt, or a local .pt path)')
    parser.add_argument('--epochs', type=int, default=50,
                        help='Number of training epochs')
    parser.add_argument('--imgsz', type=int, default=640,
                        help='Input image size for training/evaluation')
    parser.add_argument('--batch_size', type=int, default=16,
                        help='Batch size for training')
    parser.add_argument('--device', default='cpu',
                        help='Device to run training on (cpu or cuda)')
    parser.add_argument('--project', default='runs/train',
                        help='Project directory for training outputs')
    parser.add_argument('--name', default='yolo_train',
                        help='Name of the training run folder')
    parser.add_argument('--cache', action='store_true',
                        help='Cache images for faster training')
    return parser.parse_args()


def resolve_model_name(model_name):
    if model_name in {'yolov5s', 'yolov5m', 'yolov5l', 'yolov5x'}:
        print(f"Converting YOLO model '{model_name}' to the supported Ultralytics preset 'yolov8n.pt'")
        return 'yolov8n.pt'
    return model_name


def main():
    args = parse_args()

    if not os.path.isfile(args.data_config):
        raise FileNotFoundError(f'YOLO data config not found: {args.data_config}')

    if not is_ultralytics_available():
        raise ImportError(
            'Ultralytics package is required for YOLO training. Install it with: pip install ultralytics'
        )

    resolved_config = resolve_data_config(args.data_config)

    from ultralytics import YOLO

    print('Starting YOLO training...')
    print(f'  data config: {args.data_config}')
    print(f'  resolved config: {resolved_config}')
    print(f'  model: {args.model}')
    print(f'  epochs: {args.epochs}')
    print(f'  imgsz: {args.imgsz}')
    print(f'  batch size: {args.batch_size}')
    print(f'  device: {args.device}')
    print(f'  project: {args.project}')
    print(f'  name: {args.name}')

    resolved_model_name = resolve_model_name(args.model)
    yolo = YOLO(resolved_model_name)
    yolo.train(
        data=resolved_config,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch_size,
        device=args.device,
        project=args.project,
        name=args.name,
        cache=args.cache,
    )

    print('YOLO training complete.')


if __name__ == '__main__':
    main()
