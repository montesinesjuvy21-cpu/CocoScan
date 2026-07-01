import os
from tensorflow.keras.preprocessing.image import ImageDataGenerator, load_img, img_to_array

TARGET_SIZE = (224, 224)
TARGET_SIZE_LITE = (160, 160)  # For lower-spec devices
BATCH_SIZE = 32
CLASS_MODE = "categorical"


def get_image_generators(data_dir, subset, augment=False, batch_size=BATCH_SIZE, target_size=TARGET_SIZE):
    if subset not in {"train", "validation", "test"}:
        raise ValueError("subset must be one of train, validation, test")

    if augment and subset == "train":
        generator = ImageDataGenerator(
            rescale=1.0 / 255.0,
            rotation_range=30,
            width_shift_range=0.20,
            height_shift_range=0.20,
            zoom_range=0.20,
            brightness_range=[0.8, 1.2],
            horizontal_flip=True,
            vertical_flip=True,
            fill_mode="nearest",
        )
    else:
        generator = ImageDataGenerator(rescale=1.0 / 255.0)

    directory = os.path.join(data_dir, subset)
    return generator.flow_from_directory(
        directory,
        target_size=target_size,
        batch_size=batch_size,
        class_mode=CLASS_MODE,
        shuffle=(subset == "train"),
    )


def get_single_image(image_path, target_size=TARGET_SIZE):
    img = load_img(image_path, target_size=target_size)
    arr = img_to_array(img) / 255.0
    return arr
