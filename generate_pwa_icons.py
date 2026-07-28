import os
from PIL import Image, ImageDraw, ImageFont
import math

def create_cocoscan_icon(size, is_maskable=False):
    # Colors matching CocoScan header & user request (White background, Green tree-city icon)
    white_bg = (255, 255, 255)
    primary_green = (42, 123, 76) # #2A7B4C - Vibrant leaf green from header
    border_color = (230, 235, 232)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Draw White Background
    if is_maskable:
        # Full bleed white background for maskable icon
        draw.rectangle([0, 0, size, size], fill=white_bg)
    else:
        # Smooth rounded rectangle (squircle) for standard icon
        radius = int(size * 0.22)
        draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=white_bg)
        # Add subtle inner border for crispness on white screens
        border_w = max(1, int(size * 0.015))
        draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, outline=border_color, width=border_w)

    # 2. Draw Green fa-tree-city Emblem Centered
    # We scale coordinates proportionally to size (based on 512px canvas)
    scale = size / 512.0

    # Ground base line
    ground_y1 = int(380 * scale)
    ground_y2 = int(396 * scale)
    draw.rectangle([int(90 * scale), ground_y1, int(422 * scale), ground_y2], fill=primary_green)

    # --- LEFT SIDE: TREE ---
    # Trunk
    trunk_x1 = int(160 * scale)
    trunk_x2 = int(190 * scale)
    draw.rectangle([trunk_x1, int(240 * scale), trunk_x2, ground_y1], fill=primary_green)

    # Canopy (Foliage) - layered circles for a lush tree look
    canopy_center_x = int(175 * scale)
    canopy_center_y = int(210 * scale)
    canopy_r = int(75 * scale)
    draw.ellipse(
        [canopy_center_x - canopy_r, canopy_center_y - canopy_r, canopy_center_x + canopy_r, canopy_center_y + canopy_r],
        fill=primary_green
    )
    # Extra side foliage lobes for a realistic icon tree canopy
    lobe_r = int(55 * scale)
    draw.ellipse(
        [canopy_center_x - int(55 * scale) - lobe_r, canopy_center_y + int(15 * scale) - lobe_r,
         canopy_center_x - int(55 * scale) + lobe_r, canopy_center_y + int(15 * scale) + lobe_r],
        fill=primary_green
    )
    draw.ellipse(
        [canopy_center_x + int(55 * scale) - lobe_r, canopy_center_y + int(15 * scale) - lobe_r,
         canopy_center_x + int(55 * scale) + lobe_r, canopy_center_y + int(15 * scale) + lobe_r],
        fill=primary_green
    )

    # --- RIGHT SIDE: CITY BUILDINGS ---
    # Taller main building
    b1_x1 = int(255 * scale)
    b1_x2 = int(335 * scale)
    b1_y1 = int(150 * scale)
    draw.rectangle([b1_x1, b1_y1, b1_x2, ground_y1], fill=primary_green)

    # Shorter right building extension
    b2_x1 = int(335 * scale)
    b2_x2 = int(400 * scale)
    b2_y1 = int(220 * scale)
    draw.rectangle([b2_x1, b2_y1, b2_x2, ground_y1], fill=primary_green)

    # Windows (White cutouts on buildings)
    win_w = max(2, int(18 * scale))
    win_h = max(2, int(22 * scale))
    
    # Building 1 Windows (3 rows x 2 cols)
    for row in range(3):
        wy = b1_y1 + int(28 * scale) + row * int(55 * scale)
        for col in range(2):
            wx = b1_x1 + int(18 * scale) + col * int(38 * scale)
            draw.rectangle([wx, wy, wx + win_w, wy + win_h], fill=white_bg)

    # Building 2 Windows (2 rows x 2 cols)
    for row in range(2):
        wy = b2_y1 + int(30 * scale) + row * int(55 * scale)
        for col in range(2):
            wx = b2_x1 + int(15 * scale) + col * int(32 * scale)
            draw.rectangle([wx, wy, wx + win_w, wy + win_h], fill=white_bg)

    return img

def main():
    icons_dir = os.path.join("static", "icons")
    os.makedirs(icons_dir, exist_ok=True)

    sizes = {
        "icon-192x192.png": (192, False),
        "icon-512x512.png": (512, False),
        "icon-maskable-512x512.png": (512, True),
        "apple-touch-icon.png": (180, False),
    }

    for filename, (size, maskable) in sizes.items():
        img = create_cocoscan_icon(size, is_maskable=maskable)
        filepath = os.path.join(icons_dir, filename)
        img.save(filepath, "PNG")
        print(f"Generated {filepath}")

    # Generate favicon.ico (multi-resolution 32x32 and 16x16)
    fav_32 = create_cocoscan_icon(32, is_maskable=False)
    fav_16 = create_cocoscan_icon(16, is_maskable=False)
    fav_path = os.path.join(icons_dir, "favicon.ico")
    fav_32.save(fav_path, format="ICO", sizes=[(32, 32), (16, 16)])
    print(f"Generated {fav_path}")

if __name__ == "__main__":
    main()
