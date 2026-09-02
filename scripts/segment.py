#!/usr/bin/env python3
"""Run a configured SAM backend and normalize its masks."""

import argparse
import base64
import io
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image


def _write(masks, output: Path, size):
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.png"):
        stale.unlink()
    written = 0
    for mask in masks:
        array = np.asarray(mask)
        if array.ndim == 3:
            array = array[:, :, 0]
        if array.ndim != 2:
            continue
        image = Image.fromarray((array > 0).astype(np.uint8) * 255, "L")
        if image.size != size:
            image = image.resize(size, Image.Resampling.NEAREST)
        image.save(output / f"raw_{written:03d}.png")
        written += 1
    print(written)
    if written == 0:
        raise SystemExit("segmentation returned zero masks; check the configured backend and input")


def _load_remote_mask(value):
    if isinstance(value, dict):
        value = value.get("url") or value.get("image") or value.get("mask")
    if not isinstance(value, str):
        return None
    if value.startswith("data:"):
        payload = value.split(",", 1)[1]
        raw = base64.b64decode(payload)
    else:
        with urllib.request.urlopen(value, timeout=60) as response:
            raw = response.read()
    return np.asarray(Image.open(io.BytesIO(raw)).convert("L"))


def run_fal(source: Path):
    if not os.environ.get("FAL_KEY"):
        raise SystemExit("fal backend is not configured; set FAL_KEY")
    try:
        import fal_client
    except ImportError as error:
        raise SystemExit("fal backend requires the optional fal-client package") from error
    mime = "image/png"
    data_uri = f"data:{mime};base64,{base64.b64encode(source.read_bytes()).decode('ascii')}"
    result = fal_client.subscribe("fal-ai/sam2/auto-segment", arguments={"image_url": data_uri})
    values = result.get("individual_masks") or result.get("masks") or []
    return [mask for mask in (_load_remote_mask(value) for value in values) if mask is not None]


def run_local(source: Path):
    checkpoint = os.environ.get("SAM2_CHECKPOINT")
    if not checkpoint:
        raise SystemExit("local backend is not configured; set SAM2_CHECKPOINT")
    try:
        import torch
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
        from sam2.build_sam import build_sam2
    except ImportError as error:
        raise SystemExit("local backend requires the optional torch and sam2 packages") from error
    config = os.environ.get("SAM2_CONFIG", "configs/sam2.1/sam2.1_hiera_l.yaml")
    device = os.environ.get("SAM2_DEVICE", "cpu")
    points = int(os.environ.get("SAM2_POINTS_PER_SIDE", "24"))
    threshold = float(os.environ.get("SAM2_PRED_IOU", "0.8"))
    # points_per_side is the main quality/time lever. 16 roughly quarters the
    # work compared with 32 and is often enough for flat drawings.
    model = build_sam2(config, checkpoint, device=device)
    generator = SAM2AutomaticMaskGenerator(model, points_per_side=points, pred_iou_thresh=threshold)
    with torch.inference_mode():
        records = generator.generate(np.asarray(Image.open(source).convert("RGB")))
    return [record["segmentation"] for record in records if "segmentation" in record]


def run_replicate(source: Path):
    if not os.environ.get("REPLICATE_API_TOKEN"):
        raise SystemExit("replicate backend is not configured; set REPLICATE_API_TOKEN")
    try:
        import replicate
    except ImportError as error:
        raise SystemExit("replicate backend requires the optional replicate package") from error
    with source.open("rb") as handle:
        result = replicate.run("meta/sam-2", input={"image": handle, "mask_limit": 100})
    if isinstance(result, dict):
        result = result.get("individual_masks") or result.get("masks") or result.get("output") or []
    if not isinstance(result, (list, tuple)):
        result = [result]
    return [mask for mask in (_load_remote_mask(value) for value in result) if mask is not None]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", choices=["fal", "local", "replicate"], default="fal")
    args = parser.parse_args()
    with Image.open(args.source) as image:
        size = image.size
    runners = {"fal": run_fal, "local": run_local, "replicate": run_replicate}
    try:
        masks = runners[args.backend](args.source)
        _write(masks, args.out, size)
    except SystemExit:
        raise
    except Exception as error:
        print(f"{args.backend} segmentation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
