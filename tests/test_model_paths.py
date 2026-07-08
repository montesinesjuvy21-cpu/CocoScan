import os
import tempfile
import unittest

from app.model_paths import resolve_model_path


class ModelPathTests(unittest.TestCase):
    def test_resolve_model_path_prefers_existing_local_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = os.path.join(tmpdir, 'model')
            os.makedirs(model_dir, exist_ok=True)
            target = os.path.join(model_dir, 'pest_classifier_YOLO.tflite')
            with open(target, 'w', encoding='utf-8') as f:
                f.write('model')

            resolved = resolve_model_path('PEST_MODEL_PATH', 'pest_classifier_YOLO.tflite', model_dir=model_dir, env_value='cocoscan-model/models/pest_classifier.tflite')

            self.assertEqual(resolved, target)
