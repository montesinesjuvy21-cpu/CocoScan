import argparse
import os
import tensorflow as tf
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Convert a Keras model to TFLite")
    parser.add_argument("--model_path", required=True, help="Path to saved Keras model (.h5 or SavedModel)")
    parser.add_argument("--output_path", required=True, help="Path to write the TFLite model")
    parser.add_argument("--quantize", choices=["dynamic", "full_integer", "float16"], default="dynamic",
                        help="Quantization type: dynamic (default), full_integer, or float16")
    parser.add_argument("--representative_data", help="Path to folder with calibration images for full_integer quantization")
    return parser.parse_args()


def representative_data_gen(image_dir):
    """Generator for full-integer quantization calibration."""
    from tensorflow.keras.preprocessing.image import load_img, img_to_array
    image_files = os.listdir(image_dir)[:100]  # Use up to 100 images
    for image_file in image_files:
        img = load_img(os.path.join(image_dir, image_file), target_size=(224, 224))
        arr = img_to_array(img) / 255.0
        yield [np.expand_dims(arr, axis=0).astype(np.float32)]


def main():
    args = parse_args()
    model = tf.keras.models.load_model(args.model_path)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)

    if args.quantize == "dynamic":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
    elif args.quantize == "float16":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_types = [tf.float16]
    elif args.quantize == "full_integer":
        if not args.representative_data:
            raise ValueError("--representative_data required for full_integer quantization")
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_data = representative_data_gen(args.representative_data)
        converter.target_spec.supported_ops = [
            tf.lite.OpsSet.TFLITE_BUILTINS_INT8,
            tf.lite.OpsSet.TFLITE_BUILTINS,
        ]
        converter.inference_input_type = tf.uint8
        converter.inference_output_type = tf.uint8

    tflite_model = converter.convert()

    os.makedirs(os.path.dirname(args.output_path), exist_ok=True)
    with open(args.output_path, "wb") as f:
        f.write(tflite_model)

    model_size_kb = len(tflite_model) / 1024
    print(f"Converted model saved to {args.output_path}")
    print(f"Model size: {model_size_kb:.2f} KB")


if __name__ == "__main__":
    main()
