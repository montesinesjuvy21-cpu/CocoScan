# Severity classification dataset

This folder contains the images used to train the severity classifier.

## Structure

- train: training images for mild, moderate, and severe damage
- validation: validation images for tuning
- test: test images for performance reporting

## Expected layout

Each split should contain these severity folders:

- mild
- moderate
- severe

Each severity folder may include pest subfolders such as:

- rhinoceros_beetle
- brontispa

## Notes

- Use the same image quality and preprocessing approach as the pest dataset.
- The severity labels should reflect the damage level, not the pest species.
