#!/usr/bin/env python3
"""Register a transparent replacement or missed asset in an image-to-world work directory."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def _fit_rgba(asset: Image.Image, bbox):
    x, y, width, height = bbox
    rgba = asset.convert("RGBA")
    alpha_bbox = rgba.getchannel("A").getbbox()
    if not alpha_bbox:
        raise ValueError("asset alpha is empty")
    rgba = rgba.crop(alpha_bbox)
    scale = min(width / rgba.width, height / rgba.height)
    size = (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale)))
    rgba = rgba.resize(size, Image.Resampling.LANCZOS)
    position = [x + (width - size[0]) // 2, y + (height - size[1]) // 2]
    fitted_alpha_bbox = rgba.getchannel("A").getbbox()
    if not fitted_alpha_bbox:
        raise ValueError("asset alpha is empty after resizing")
    position[0] += fitted_alpha_bbox[0]
    position[1] += fitted_alpha_bbox[1]
    rgba = rgba.crop(fitted_alpha_bbox)
    return rgba, tuple(position)


def register(work: Path, asset_path: Path, bbox, index=None):
    source_path = work / "source.png"
    manifest_path = work / "filtered" / "manifest.json"
    if not source_path.exists() or not manifest_path.exists():
        raise SystemExit("work/source.png and work/filtered/manifest.json are required")
    with Image.open(source_path) as source:
        source_size = source.size
    x, y, width, height = bbox
    if width < 1 or height < 1 or x < 0 or y < 0 or x + width > source_size[0] or y + height > source_size[1]:
        raise SystemExit("--bbox must be a positive rectangle inside source.png")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("assets", [])
    existing = {entry["index"]: entry for entry in entries}
    if index is None:
        index = max(existing, default=-1) + 1
    with Image.open(asset_path) as asset:
        fitted, position = _fit_rgba(asset, bbox)
    recovered_dir = work / "recovered"
    recovered_dir.mkdir(parents=True, exist_ok=True)
    recovered_path = recovered_dir / f"asset_{index:02d}.png"
    fitted.save(recovered_path)

    full_mask = Image.new("L", source_size, 0)
    full_mask.paste(fitted.getchannel("A"), position)
    mask_path = work / "filtered" / f"asset_{index:02d}.png"
    full_mask.save(mask_path)
    mask_array = np.asarray(full_mask) > 127
    ys, xs = np.where(mask_array)
    if not len(xs):
        raise SystemExit("recovered asset has no opaque pixels after fitting")
    actual_bbox = [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
    entry = {
        "index": index,
        "mask": mask_path.name,
        "bbox": actual_bbox,
        "areaRatio": round(float(mask_array.mean()), 6),
        "source_mask": "recovered",
    }
    if index in existing:
        entries[entries.index(existing[index])] = entry
    else:
        entries.append(entry)
    entries.sort(key=lambda item: item["index"])
    manifest["assets"] = entries
    manifest.setdefault("report", {})["kept"] = len(entries)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"index": index, "bbox": actual_bbox, "recovered": str(recovered_path)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("asset", type=Path)
    parser.add_argument("--bbox", type=int, nargs=4, metavar=("X", "Y", "W", "H"), required=True)
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    register(args.work_dir, args.asset, args.bbox, args.index)


if __name__ == "__main__":
    main()
