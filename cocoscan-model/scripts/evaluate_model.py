import sys, os
# Ensure project root is on Python path so 'cocoscan' package resolves when running scripts
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
import numpy as np
import tensorflow as tf
from cocoscan.data import get_image_generators, TARGET_SIZE, TARGET_SIZE_LITE
from cocoscan.evaluate import evaluate_predictions, build_roc_curves


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate trained model on test dataset")
    parser.add_argument("--model_path", required=True, help="Path to trained model (.h5)")
    parser.add_argument("--data_dir", required=True, help="Path to dataset directory containing test split")
    parser.add_argument("--model_type", choices=["pest", "severity"], default="pest", help="Model type: pest or severity")
    parser.add_argument("--lite", action="store_true", help="Use lite input size (160x160)")
    parser.add_argument("--batch_size", type=int, default=32)
    return parser.parse_args()


def get_class_names(model_type):
    if model_type == "pest":
        return ["Rhinoceros Beetle", "Brontispa", "Healthy Coconut Leaf"]
    else:  # severity
        return ["Mild", "Moderate", "Severe"]


def main():
    args = parse_args()
    
    # Load model
    model = tf.keras.models.load_model(args.model_path)
    print(f"✓ Loaded model from {args.model_path}")
    
    # Prepare test data
    target_size = TARGET_SIZE_LITE if args.lite else TARGET_SIZE
    test_gen = get_image_generators(
        args.data_dir, 
        "test", 
        augment=False, 
        batch_size=args.batch_size,
        target_size=target_size
    )
    
    class_names = get_class_names(args.model_type)
    num_test_samples = test_gen.samples
    num_classes = len(class_names)
    
    print(f"✓ Loaded test data: {num_test_samples} images, {num_classes} classes")
    print(f"  Classes: {', '.join(class_names)}\n")
    
    # Get predictions
    print("Running inference on test set...")
    y_pred_all = []
    y_true_all = []
    y_prob_all = []
    
    for _ in range(int(np.ceil(num_test_samples / args.batch_size))):
        images, labels = next(test_gen)
        predictions = model.predict(images, verbose=0)
        y_prob_all.append(predictions)
        y_pred_all.append(np.argmax(predictions, axis=1))
        y_true_all.append(np.argmax(labels, axis=1))
    
    y_pred = np.concatenate(y_pred_all)[:num_test_samples]
    y_true = np.concatenate(y_true_all)[:num_test_samples]
    y_prob = np.concatenate(y_prob_all)[:num_test_samples]
    
    # Evaluate
    metrics = evaluate_predictions(y_true, y_pred, y_prob, class_names)
    
    # Display results
    print("\n" + "="*60)
    print("OVERALL ACCURACY")
    print("="*60)
    overall_accuracy = metrics["accuracy_percentage"]
    print(f"✓ Correct Identifications: {overall_accuracy:.2f}%")
    print(f"✗ Incorrect Identifications: {100 - overall_accuracy:.2f}%")
    print(f"Total Test Images: {num_test_samples}")
    print(f"Correctly Classified: {int(metrics['accuracy'] * num_test_samples)}")
    print(f"Incorrectly Classified: {num_test_samples - int(metrics['accuracy'] * num_test_samples)}")
    
    print("\n" + "="*60)
    print("PER-CLASS ACCURACY")
    print("="*60)
    for idx, class_name in enumerate(class_names):
        class_report = metrics["classification_report"][class_name]
        precision = class_report["precision"] * 100
        recall = class_report["recall"] * 100
        f1 = class_report["f1-score"] * 100
        support = int(class_report["support"])
        print(f"\n{class_name}:")
        print(f"  Precision: {precision:.2f}%")
        print(f"  Recall (True Positive Rate): {recall:.2f}%")
        print(f"  F1-Score: {f1:.2f}%")
        print(f"  Test Images: {support}")
    
    if metrics.get("roc_auc"):
        print("\n" + "="*60)
        print("ADDITIONAL METRICS")
        print("="*60)
        print(f"ROC-AUC Score: {metrics['roc_auc']:.4f}")
    
    print("\n" + "="*60)
    print("CONFUSION MATRIX")
    print("="*60)
    confusion_matrix_arr = np.array(metrics["confusion_matrix"])
    print("\nRows: Actual | Columns: Predicted\n")
    print(f"{'':20}", end="")
    for class_name in class_names:
        print(f"{class_name:20}", end="")
    print()
    
    for i, class_name in enumerate(class_names):
        print(f"{class_name:20}", end="")
        for j in range(len(class_names)):
            print(f"{confusion_matrix_arr[i, j]:20}", end="")
        print()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Model Accuracy: {overall_accuracy:.2f}%")
    print(f"Macro F1-Score: {metrics['classification_report']['macro avg']['f1-score']*100:.2f}%")
    print(f"Weighted F1-Score: {metrics['classification_report']['weighted avg']['f1-score']*100:.2f}%")
    
    print("\n✓ Evaluation complete!")


if __name__ == "__main__":
    main()
