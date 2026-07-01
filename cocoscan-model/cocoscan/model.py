from tensorflow.keras import layers, models, optimizers
from tensorflow.keras.applications import MobileNetV2, EfficientNetB0


def build_lightweight_cnn(num_classes, input_shape=(160, 160, 3)):
    """Lightweight CNN optimized for low-spec devices (~2MB final size)."""
    inputs = layers.Input(shape=input_shape)
    x = layers.Conv2D(16, (3, 3), activation="relu", padding="same")(inputs)
    x = layers.MaxPooling2D((2, 2))(x)
    x = layers.Conv2D(32, (3, 3), activation="relu", padding="same")(x)
    x = layers.MaxPooling2D((2, 2))(x)
    x = layers.Conv2D(64, (3, 3), activation="relu", padding="same")(x)
    x = layers.MaxPooling2D((2, 2))(x)
    x = layers.Flatten()(x)
    x = layers.Dense(128, activation="relu")(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)

    model = models.Model(inputs=inputs, outputs=outputs, name="cocoscan_lightweight_cnn")
    return model


def build_base_cnn(num_classes, input_shape=(224, 224, 3)):
    inputs = layers.Input(shape=input_shape)
    x = layers.Conv2D(32, (3, 3), activation="relu", padding="same")(inputs)
    x = layers.MaxPooling2D((2, 2))(x)
    x = layers.Conv2D(64, (3, 3), activation="relu", padding="same")(x)
    x = layers.MaxPooling2D((2, 2))(x)
    x = layers.Conv2D(128, (3, 3), activation="relu", padding="same")(x)
    x = layers.MaxPooling2D((2, 2))(x)
    x = layers.Conv2D(256, (3, 3), activation="relu", padding="same")(x)
    x = layers.MaxPooling2D((2, 2))(x)
    x = layers.Flatten()(x)
    x = layers.Dense(512, activation="relu")(x)
    x = layers.Dropout(0.5)(x)
    x = layers.Dense(256, activation="relu")(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)

    model = models.Model(inputs=inputs, outputs=outputs, name="cocoscan_base_cnn")
    return model


def build_mobilenet_v2(num_classes, freeze_until_layer=100, input_shape=(224, 224, 3)):
    """MobileNetV2 with transfer learning for efficient deployment."""
    base = MobileNetV2(include_top=False, weights="imagenet", input_shape=input_shape, pooling="avg")

    # Freeze most layers for efficient training; only train top layers
    for layer in base.layers[:freeze_until_layer]:
        layer.trainable = False

    inputs = layers.Input(shape=input_shape)
    x = base(inputs, training=False)
    x = layers.Dense(512, activation="relu")(x)
    x = layers.Dropout(0.5)(x)
    x = layers.Dense(256, activation="relu")(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)

    model = models.Model(inputs=inputs, outputs=outputs, name="cocoscan_mobilenetv2")
    return model


def build_efficientnet_b0(num_classes, input_shape=(224, 224, 3)):
    """EfficientNetB0 for ultra-efficient inference on edge devices."""
    base = EfficientNetB0(include_top=False, weights="imagenet", input_shape=input_shape, pooling="avg")

    # Freeze base model for efficient training
    base.trainable = False

    inputs = layers.Input(shape=input_shape)
    x = base(inputs, training=False)
    x = layers.Dense(256, activation="relu")(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)

    model = models.Model(inputs=inputs, outputs=outputs, name="cocoscan_efficientnet_b0")
    return model


def compile_model(model, learning_rate=1e-4):
    optimizer = optimizers.Adam(learning_rate=learning_rate)
    model.compile(
        optimizer=optimizer,
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model
