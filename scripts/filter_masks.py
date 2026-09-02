#!/usr/bin/env python3
"""Filter raw masks and render the numbered semantic-labeling contact sheet."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PALETTE = ["#ff3b30", "#007aff", "#34c759", "#ff9500", "#af52de", "#00c7be", "#ff2d55", "#5856d6"]
BADGE_HALF = (20, 18)


def _bbox(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return [x0, y0, x1 - x0 + 1, y1 - y0 + 1]


def _intersects(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def choose_badge_rect(bbox, image_size, placed):
    x, y, w, h = bbox
    iw, ih = image_size
    hw, hh = BADGE_HALF
    center = (x + w // 2, y + h // 2)
    centers = []
    if w > 60 and h > 54:
        centers.append(center)
    centers.extend([
        (x + w + hw + 4, y - hh - 4),
        (x + w + hw + 4, y + h + hh + 4),
        (x - hw - 4, y - hh - 4),
        (x - hw - 4, y + h + hh + 4),
        (x + w // 2, y - hh - 4),
        (x + w // 2, y + h + hh + 4),
    ])
    own = (x, y, x + w, y + h)
    candidates = []
    for cx, cy in centers:
        cx = min(max(hw, cx), iw - hw)
        cy = min(max(hh, cy), ih - hh)
        rect = (cx - hw, cy - hh, cx + hw, cy + hh)
        candidates.append(rect)
        if (w > 60 and h > 54 and rect[0] >= x and rect[2] <= x + w and rect[1] >= y and rect[3] <= y + h):
            if not any(_intersects(rect, other) for other in placed):
                return rect
        elif not _intersects(rect, own) and not any(_intersects(rect, other) for other in placed):
            return rect
    for cy in range(hh, ih - hh + 1, 12):
        for cx in range(hw, iw - hw + 1, 12):
            rect = (cx - hw, cy - hh, cx + hw, cy + hh)
            if not _intersects(rect, own) and not any(_intersects(rect, other) for other in placed):
                return rect
    return candidates[0]


def make_contact(source_path, contact_path, kept):
    if not source_path or not source_path.exists():
        print("warning: source image missing; contact sheet skipped", file=sys.stderr)
        return []
    image = Image.open(source_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    placed = []
    for index, item in enumerate(kept):
        color = PALETTE[index % len(PALETTE)]
        mask_image = Image.fromarray((item["array"] * 255).astype(np.uint8), "L")
        edges = np.asarray(mask_image.filter(ImageFilter.FIND_EDGES)) > 40
        overlay = Image.new("RGB", image.size, color)
        image.paste(overlay, mask=Image.fromarray((edges * 210).astype(np.uint8), "L"))
        draw = ImageDraw.Draw(image)
        rect = choose_badge_rect(item["bbox"], image.size, placed)
        placed.append(rect)
        x, y, w, h = item["bbox"]
        object_center = (x + w // 2, y + h // 2)
        badge_center = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
        centered = rect[0] >= x and rect[2] <= x + w and rect[1] >= y and rect[3] <= y + h
        if not centered:
            draw.line([object_center, badge_center], fill=color, width=2)
        draw.rounded_rectangle(rect, radius=6, fill=color, outline="white", width=2)
        text = str(index)
        text_box = draw.textbbox((0, 0), text, font=font)
        tw, th = text_box[2] - text_box[0], text_box[3] - text_box[1]
        draw.text((badge_center[0] - tw / 2, badge_center[1] - th / 2 - text_box[1]), text, fill="white", font=font)
    contact_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(contact_path)
    return placed


def filter_masks(mask_dir, output, source, contact, max_assets, min_area, max_area, nest_thresh, max_border_touch):
    paths = sorted(mask_dir.glob("*.png"))
    if not paths:
        raise SystemExit("no PNG masks found")
    loaded = []
    shape = None
    for path in paths:
        array = np.asarray(Image.open(path).convert("L")) > 127
        if shape is None:
            shape = array.shape
        elif array.shape != shape:
            raise SystemExit("mask dimensions are inconsistent; rerun segmentation")
        loaded.append((path, array))
    height, width = shape
    report = {"raw": len(loaded), "dropped_area": 0, "dropped_border": 0, "dropped_nested": 0, "dropped_cap": 0, "kept": 0}
    candidates = []
    for path, array in loaded:
        area = int(array.sum())
        ratio = area / (width * height)
        if ratio < min_area or ratio > max_area:
            report["dropped_area"] += 1
            continue
        touches = sum([array[0, :].any(), array[-1, :].any(), array[:, 0].any(), array[:, -1].any()])
        if touches > max_border_touch:
            report["dropped_border"] += 1
            continue
        candidates.append({"path": path, "array": array, "area": area, "areaRatio": ratio})
    accepted = []
    for candidate in sorted(candidates, key=lambda item: item["area"], reverse=True):
        nested = False
        for prior in accepted:
            intersection = np.logical_and(candidate["array"], prior["array"]).sum()
            if intersection / min(candidate["area"], prior["area"]) > nest_thresh:
                nested = True
                break
        if nested:
            report["dropped_nested"] += 1
        else:
            accepted.append(candidate)
    if len(accepted) > max_assets:
        report["dropped_cap"] = len(accepted) - max_assets
        accepted = accepted[:max_assets]
    report["kept"] = len(accepted)
    if len(accepted) < 2:
        print(json.dumps(report), file=sys.stderr)
        raise SystemExit("fewer than 2 masks survived; do not loosen thresholds blindly. Check which filter removed the most and prefer asking for a clearer image")

    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("asset_*.png"):
        stale.unlink()
    manifest_assets = []
    for index, item in enumerate(accepted):
        filename = f"asset_{index:02d}.png"
        Image.fromarray((item["array"] * 255).astype(np.uint8), "L").save(output / filename)
        item["bbox"] = _bbox(item["array"])
        manifest_assets.append({
            "index": index,
            "mask": filename,
            "bbox": item["bbox"],
            "areaRatio": round(item["areaRatio"], 6),
            "source_mask": item["path"].name,
        })
    manifest = {"width": width, "height": height, "assets": manifest_assets, "report": report}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if contact:
        make_contact(source, contact, accepted)
    print(json.dumps(report))
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("masks_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--contact", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--max-assets", type=int, default=18)
    parser.add_argument("--min-area", type=float, default=0.0015)
    parser.add_argument("--max-area", type=float, default=0.55)
    parser.add_argument("--nest-thresh", type=float, default=0.75)
    parser.add_argument("--max-border-touch", type=int, default=3)
    args = parser.parse_args()
    filter_masks(args.masks_dir, args.out, args.source, args.contact, args.max_assets, args.min_area, args.max_area, args.nest_thresh, args.max_border_touch)


if __name__ == "__main__":
    main()
