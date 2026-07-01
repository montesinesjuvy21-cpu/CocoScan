# Pest classification dataset

This folder contains the main image dataset used to train the pest classifier.

## Structure

- train: training images grouped by class
- validation: validation images for hyperparameter tuning
- test: held-out images for final evaluation

## Expected class folders

Each split should contain these class folders:

- rhinoceros_beetle
- brontispa
- healthy

## Notes

- Images should be RGB and preferably resized to a consistent format before training.
- Keep the class folders balanced as much as possible for better learning.
- Use the same folder structure for both training and evaluation.
