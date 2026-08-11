"""
imaging.py — Pillow-based image transforms.

Used to derive extra output formats (e.g. 4:5 and 1:1) from a single generated
banner by cropping from the CENTER. This pairs with the "safe center" brief
instruction: critical content sits in the middle of the frame, so center-crops
to other aspect ratios never lose it.
"""

import io

from PIL import Image


def dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Return the (width, height) of an encoded image."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        return img.size


def center_crop_to(image_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """Center-crop `image_bytes` to the target aspect ratio, then resize to
    exactly target_w x target_h. Returns PNG bytes.

    If the source already matches the target ratio, this is just a clean resize
    (no content lost). Otherwise the longer dimension is cropped equally from
    both sides, keeping the centre of the frame.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # Source is wider than target — crop the width, keep full height.
        new_w = round(src_h * target_ratio)
        left = (src_w - new_w) // 2
        box = (left, 0, left + new_w, src_h)
    else:
        # Source is taller than target — crop the height, keep full width.
        new_h = round(src_w / target_ratio)
        top = (src_h - new_h) // 2
        box = (0, top, src_w, top + new_h)

    cropped = img.crop(box)
    if cropped.size != (target_w, target_h):
        cropped = cropped.resize((target_w, target_h), Image.LANCZOS)

    out = io.BytesIO()
    cropped.save(out, format="PNG")
    return out.getvalue()
