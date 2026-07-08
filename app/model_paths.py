import os
from pathlib import Path
from typing import Optional


def resolve_model_path(env_var_name: str, default_filename: str, model_dir: Optional[str] = None, env_value: Optional[str] = None) -> str:
    """Resolve a model path from environment config, falling back to the local model folder."""
    candidates = []

    configured_value = env_value if env_value is not None else os.getenv(env_var_name, "")
    if configured_value:
        cleaned_value = os.path.expandvars(os.path.expanduser(str(configured_value).strip()))
        if os.path.isabs(cleaned_value):
            candidates.append(cleaned_value)
        else:
            project_root = Path(__file__).resolve().parent.parent
            candidates.extend([
                str((project_root / cleaned_value).resolve()),
                str((project_root / "model" / cleaned_value).resolve()),
            ])

    resolved_model_dir = Path(model_dir) if model_dir else (Path(__file__).resolve().parent.parent / "model")
    candidates.extend([
        str((resolved_model_dir / default_filename).resolve()),
        str((resolved_model_dir / "pest_classifier_YOLO.tflite").resolve()),
        str((resolved_model_dir / "pest_classifier.tflite").resolve()),
    ])

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return str((resolved_model_dir / default_filename).resolve())
