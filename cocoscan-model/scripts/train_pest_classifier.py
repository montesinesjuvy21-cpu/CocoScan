import sys, os
# Ensure project root is on Python path so 'cocoscan' package resolves when running scripts
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from cocoscan.data import get_image_generators, TARGET_SIZE, TARGET_SIZE_LITE
from cocoscan.model import build_mobilenet_v2, build_lightweight_cnn, build_efficientnet_b0, compile_model


def parse_args():
    parser = argparse.ArgumentParser(description="Train the Cocosan pest classifier")
    parser.add_argument("--data_dir", required=True, help="Path to dataset directory")
    parser.add_argument("--output_path", required=True, help="Path to save trained model")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--model", choices=["mobilenetv2", "efficientnetb0", "lightweight"], default="mobilenetv2",
                        help="Model architecture to use")
    parser.add_argument("--lite", action="store_true", help="Use lighter input size (160x160)")
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Choose target size
    target_size = TARGET_SIZE_LITE if args.lite else TARGET_SIZE
    
    train_gen = get_image_generators(args.data_dir, "train", augment=True, batch_size=args.batch_size, target_size=target_size)
    val_gen = get_image_generators(args.data_dir, "validation", augment=False, batch_size=args.batch_size, target_size=target_size)

    # Choose model
    if args.model == "lightweight":
        if not args.lite:
            print("Warning: lightweight model works best with --lite flag (160x160 input)")
        model = build_lightweight_cnn(num_classes=train_gen.num_classes)
    elif args.model == "efficientnetb0":
        model = build_efficientnet_b0(num_classes=train_gen.num_classes)
    else:  # mobilenetv2
        model = build_mobilenet_v2(num_classes=train_gen.num_classes)
    
    model = compile_model(model)

    os.makedirs(os.path.dirname(args.output_path), exist_ok=True)

    callbacks = [
        EarlyStopping(monitor="val_loss", patience=7, restore_best_weights=True),
        ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=4, min_lr=1e-7),
        ModelCheckpoint(args.output_path, monitor="val_loss", save_best_only=True),
    ]

    history = model.fit(
        train_gen,
        validation_data=val_gen,
        epochs=args.epochs,
        callbacks=callbacks,
    )

    model.save(args.output_path)
    print(f"Saved pest classifier ({args.model}) to {args.output_path}")


if __name__ == "__main__":
    main()
