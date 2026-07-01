# YOLO annotation starter

## Sample label file

A label file should be a text file with one line per object:

```text
0 0.50 0.50 0.40 0.60
```

Meaning:
- `0` = class id (`leaf`)
- `0.50 0.50` = object center (x, y)
- `0.40 0.60` = object width and height

## Annotation checklist

1. Put each image in `images/train` or `images/val`.
2. Create a matching `.txt` file in the corresponding `labels` folder.
3. Draw one bounding box around the coconut leaf region.
4. If the image does not contain a clear leaf, skip it or remove it from the training set.
5. Save the label file with the same filename as the image.
6. Keep the box tight around the leaf, not the whole image.
7. Use the same class id `0` for all leaf boxes.
