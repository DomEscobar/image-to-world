#!/usr/bin/env python3
"""Assemble cut-outs and world.json from deterministic masks and semantic labels."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from contours import mask_to_polygon  # noqa: E402

MODE_DEFAULTS = {
    "side": {"gravityY": 1.2, "moveSpeed": 4, "jumpVelocity": 11, "drag": 0.02},
    "topdown": {"gravityY": 0, "moveSpeed": 4, "jumpVelocity": 0, "drag": 0.15},
    "float": {"gravityY": 0.25, "moveSpeed": 3, "jumpVelocity": 0, "drag": 0.08},
    "sandbox": {"gravityY": 1.0, "moveSpeed": 4, "jumpVelocity": 10, "drag": 0.02},
}


def sample_background(image):
    px = image.load()
    corners = [px[0, 0], px[image.width - 1, 0], px[0, image.height - 1], px[image.width - 1, image.height - 1]]
    rgb = tuple(round(sum(pixel[channel] for pixel in corners) / 4) for channel in range(3))
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def build(work: Path, output: Path, epsilon_factor: float):
    manifest_path = work / "filtered" / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("filtered/manifest.json is missing; run filter_masks.py first")
    source_path = work / "source.png"
    if not source_path.exists():
        raise SystemExit("source.png is missing; run normalize.py first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    labels_path = work / "labels.json"
    labels_exist = labels_path.exists()
    if labels_exist:
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
    else:
        print("warning: labels.json is absent; every asset becomes decor and the validator will promote a player", file=sys.stderr)
        labels = {}
    label_entries = {}
    for entry in labels.get("assets", []):
        if isinstance(entry, dict) and isinstance(entry.get("index"), int):
            label_entries[entry["index"]] = entry

    manifest_indices = {entry["index"] for entry in manifest.get("assets", [])}
    nonexistent = sorted(set(label_entries) - manifest_indices)
    if nonexistent:
        print(f"warning: label indices absent from manifest: {nonexistent}", file=sys.stderr)

    source = Image.open(source_path).convert("RGB")
    output.mkdir(parents=True, exist_ok=True)
    assets_dir = output / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    assets = []
    for item in manifest.get("assets", []):
        index = item["index"]
        if labels_exist and index not in label_entries:
            continue
        mask_path = work / "filtered" / item["mask"]
        mask_array = np.asarray(Image.open(mask_path).convert("L")) > 127
        polygon, bbox = mask_to_polygon(mask_array, epsilon_factor=epsilon_factor)
        if not polygon or not bbox:
            print(f"warning: asset {index} produced no polygon and was skipped", file=sys.stderr)
            continue
        x, y, width, height = bbox
        crop = source.crop((x, y, x + width, y + height)).convert("RGBA")
        alpha = Image.fromarray((mask_array[y:y + height, x:x + width] * 255).astype(np.uint8), "L")
        crop.putalpha(alpha)
        filename = f"asset_{index:02d}.png"
        crop.save(assets_dir / filename)
        label = label_entries.get(index, {})
        assets.append({
            "id": f"asset_{index:02d}",
            "file": f"assets/{filename}",
            "label": label.get("label", f"object {index}"),
            "role": label.get("role", "decor"),
            "bbox": bbox,
            "areaRatio": item.get("areaRatio", round(float(mask_array.mean()), 6)),
            "z": label.get("z", 50),
            "polygon": polygon,
        })

    mode = labels.get("mode", "side")
    if mode not in MODE_DEFAULTS:
        print(f"warning: unknown mode {mode!r}; falling back to side", file=sys.stderr)
        mode = "side"
    tuning = dict(MODE_DEFAULTS[mode])
    supplied = labels.get("tuning", {})
    if isinstance(supplied, dict):
        for key in tuning:
            if key in supplied:
                tuning[key] = supplied[key]
    world = {
        "version": 2,
        "mode": mode,
        "width": source.width,
        "height": source.height,
        "background": sample_background(source),
        "tuning": tuning,
        "assets": assets,
        "rules": labels.get("rules", []),
    }
    (output / "world.json").write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")
    print(f"built {len(assets)} assets in {mode} mode")
    print("Now run validate_world.py. Do not hand this to the user unvalidated.")
    return world


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epsilon-factor", type=float, default=0.01)
    args = parser.parse_args()
    build(args.work_dir, args.out, args.epsilon_factor)


if __name__ == "__main__":
    main()
