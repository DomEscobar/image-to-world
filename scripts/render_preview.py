#!/usr/bin/env python3
"""Render a world plus a cut-out gallery for mandatory visual verification."""

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size=18):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _checker(size, block=16):
    image = Image.new("RGB", size, "#eeeeee")
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if (x // block + y // block) % 2:
                draw.rectangle((x, y, min(x + block, size[0]), min(y + block, size[1])), fill="#cfcfcf")
    return image


def render(world_path: Path, output: Path):
    world = json.loads(world_path.read_text(encoding="utf-8"))
    root = world_path.parent
    width, height = int(world["width"]), int(world["height"])
    scene = Image.new("RGBA", (width, height), world.get("background", "#ffffff"))
    ordered = sorted(world.get("assets", []), key=lambda asset: asset.get("z", 50))
    loaded = []
    for asset in ordered:
        path = root / asset["file"]
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
        x, y, box_width, box_height = asset["bbox"]
        if rgba.size != (box_width, box_height):
            rgba = rgba.resize((box_width, box_height), Image.Resampling.LANCZOS)
        scene.alpha_composite(rgba, (x, y))
        loaded.append((asset, rgba))

    overlay = ImageDraw.Draw(scene)
    font = _font(16)
    for asset, _ in loaded:
        x, y, _, _ = asset["bbox"]
        polygon = [(x + point[0], y + point[1]) for point in asset.get("polygon", [])]
        if len(polygon) >= 3:
            overlay.line(polygon + [polygon[0]], fill="#ff00ff", width=2)
        overlay.text((x + 3, y + 3), f"{asset['id']} {asset.get('role', '')}", fill="#111111", stroke_width=3, stroke_fill="#ffffff", font=font)

    thumb = 190
    label_height = 48
    columns = max(1, min(5, math.ceil(math.sqrt(max(1, len(loaded))))))
    rows = math.ceil(max(1, len(loaded)) / columns)
    gallery_width = columns * thumb
    gallery_height = rows * (thumb + label_height)
    gallery = Image.new("RGB", (gallery_width, gallery_height), "#ffffff")
    draw = ImageDraw.Draw(gallery)
    for index, (asset, rgba) in enumerate(loaded):
        column, row = index % columns, index // columns
        left, top = column * thumb, row * (thumb + label_height)
        cell = _checker((thumb, thumb))
        content = rgba.copy()
        content.thumbnail((thumb - 20, thumb - 20), Image.Resampling.LANCZOS)
        position = ((thumb - content.width) // 2, (thumb - content.height) // 2)
        cell.paste(content, position, content)
        gallery.paste(cell, (left, top))
        draw.rectangle((left, top, left + thumb - 1, top + thumb + label_height - 1), outline="#555555", width=1)
        draw.text((left + 6, top + thumb + 4), asset["id"], fill="#111111", font=font)
        draw.text((left + 6, top + thumb + 24), f"{asset.get('label', '')} · {asset.get('role', '')}", fill="#333333", font=_font(12))

    max_width = max(width, gallery_width)
    header_height = 42
    board = Image.new("RGB", (max_width, header_height + height + header_height + gallery_height), "#f7f7f7")
    board_draw = ImageDraw.Draw(board)
    board_draw.text((10, 9), "FINAL WORLD RENDER - inspect placement, scale, omissions", fill="#111111", font=_font(18))
    board.paste(scene.convert("RGB"), ((max_width - width) // 2, header_height))
    gallery_top = header_height + height + header_height
    board_draw.text((10, header_height + height + 9), "CUT-OUT GALLERY - inspect edges, completeness, transparency", fill="#111111", font=_font(18))
    board.paste(gallery, ((max_width - gallery_width) // 2, gallery_top))
    output.parent.mkdir(parents=True, exist_ok=True)
    board.save(output)
    print(json.dumps({"assets": len(loaded), "output": str(output), "size": list(board.size)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("world", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    render(args.world, args.out)


if __name__ == "__main__":
    main()
