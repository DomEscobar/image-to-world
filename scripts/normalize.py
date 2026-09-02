#!/usr/bin/env python3
"""Sanitize, orient, resize, and describe an input image."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageOps


def sample_background(image: Image.Image) -> str:
    pixels = image.load()
    corners = [
        pixels[0, 0],
        pixels[image.width - 1, 0],
        pixels[0, image.height - 1],
        pixels[image.width - 1, image.height - 1],
    ]
    rgb = tuple(round(sum(pixel[channel] for pixel in corners) / 4) for channel in range(3))
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def normalize(source: Path, output: Path, max_side: int) -> dict:
    if max_side < 1:
        raise SystemExit("--max-side must be at least 1")

    # Re-encoding through Pillow sanitizes the file. Uploads are untrusted and must
    # never reach a segmentation backend, or a user, as their original bytes.
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        original_size = list(image.size)
        if image.mode in {"RGBA", "LA", "P"}:
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            image = background.convert("RGB")
        else:
            image = image.convert("RGB")

        longest = max(image.size)
        if longest > max_side:
            scale = max_side / longest
            size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            image = image.resize(size, Image.Resampling.LANCZOS)

        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
        aspect = image.width / image.height
        if aspect > 1.5:
            hint = "wide — often a side view"
        elif aspect < 0.7:
            hint = "tall — often a vertical or top-down view"
        else:
            hint = "squarish — could be top-down; look carefully"
        meta = {
            "width": image.width,
            "height": image.height,
            "original_size": original_size,
            "background": sample_background(image),
            "aspect": round(aspect, 6),
            "aspect_hint": hint,
        }

    meta_path = output.with_name("meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-side", type=int, default=1024)
    args = parser.parse_args()
    print(json.dumps(normalize(args.input, args.out, args.max_side), ensure_ascii=False))


if __name__ == "__main__":
    main()
