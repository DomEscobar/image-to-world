#!/usr/bin/env python3
"""Generate or repair one image asset with WaveSpeed, then remove its background."""

import argparse
import base64
import io
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image


API_ROOT = "https://api.wavespeed.ai/api/v3"
GENERATE_MODEL = "bytedance/seedream-v5.0-pro"
EDIT_MODEL = "bytedance/seedream-v5.0-pro/edit"
REMOVE_BACKGROUND_MODEL = "bria/remove-background"
TERMINAL_FAILURES = {"failed", "cancelled", "timeout", "deleted"}


def _image_data_uri(path: Path, bbox=None) -> str:
    """Re-encode local input instead of sending untrusted original bytes."""
    with Image.open(path) as image:
        clean = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        if bbox:
            x, y, width, height = bbox
            if width < 1 or height < 1 or x < 0 or y < 0 or x + width > clean.width or y + height > clean.height:
                raise ValueError("reference bbox must be a positive rectangle inside the reference image")
            clean = clean.crop((x, y, x + width, y + height))
        payload = io.BytesIO()
        clean.save(payload, format="PNG")
    encoded = base64.b64encode(payload.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _request_json(url: str, api_key: str, payload=None, timeout=60):
    headers = {"Authorization": f"Bearer {api_key}"}
    data = None
    method = "GET"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
        method = "POST"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"WaveSpeed HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"WaveSpeed request failed: {exc.reason}") from exc


def submit_and_wait(model: str, payload: dict, api_key: str, timeout: int):
    # Do not retry submission POSTs: a lost response may still represent a billed task.
    body = _request_json(f"{API_ROOT}/{model}", api_key, payload)
    task = body.get("data", body)
    prediction_id = task.get("id")
    if not prediction_id:
        raise RuntimeError("WaveSpeed submission returned no prediction id")
    result_url = task.get("urls", {}).get("get") or f"{API_ROOT}/predictions/{prediction_id}/result"
    deadline = time.monotonic() + timeout
    interval = 2.0
    while time.monotonic() < deadline:
        result_body = _request_json(result_url, api_key, timeout=min(60, timeout))
        result = result_body.get("data", result_body)
        status = result.get("status")
        if status == "completed":
            outputs = result.get("outputs") or []
            if not outputs:
                raise RuntimeError("WaveSpeed task completed without outputs")
            return outputs[0], prediction_id
        if status in TERMINAL_FAILURES:
            raise RuntimeError(f"WaveSpeed task ended with status {status}: {result.get('error') or result.get('message') or result}")
        time.sleep(interval)
        interval = min(5.0, interval + 0.5)
    raise RuntimeError(f"WaveSpeed task {prediction_id} exceeded {timeout}s")


def _download_image(value: str, output: Path, timeout: int):
    if value.startswith("data:"):
        raw = base64.b64decode(value.split(",", 1)[1])
    elif value.startswith("http://") or value.startswith("https://"):
        with urlopen(value, timeout=timeout) as response:
            raw = response.read()
    else:
        raw = base64.b64decode(value)
    with Image.open(io.BytesIO(raw)) as image:
        clean = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        clean.load()
    output.parent.mkdir(parents=True, exist_ok=True)
    clean.save(output, format="PNG")


def recover(prompt: str, output: Path, reference: Path | None, reference_bbox, mode: str,
            remove_background: bool, aspect_ratio: str, resolution: str, optimization: str, timeout: int):
    api_key = os.environ.get("WAVESPEED_API_KEY")
    if not api_key:
        raise SystemExit("WAVESPEED_API_KEY is not set; configure it before using WaveSpeed asset recovery")
    selected = "edit" if mode == "auto" and reference else "generate" if mode == "auto" else mode
    if selected == "edit" and not reference:
        raise SystemExit("--reference is required in edit mode")
    model = EDIT_MODEL if selected == "edit" else GENERATE_MODEL
    payload = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "output_format": "png",
        "prompt_optimization_mode": optimization,
    }
    if selected == "edit":
        payload["images"] = [_image_data_uri(reference, reference_bbox)]
    generated, generation_id = submit_and_wait(model, payload, api_key, timeout)
    stage = output.with_name(f".{output.stem}.generated.png") if remove_background else output
    _download_image(generated, stage, timeout)
    removal_id = None
    if remove_background:
        cutout, removal_id = submit_and_wait(
            REMOVE_BACKGROUND_MODEL,
            {"image": _image_data_uri(stage)},
            api_key,
            timeout,
        )
        _download_image(cutout, output, timeout)
        stage.unlink(missing_ok=True)
        with Image.open(output) as image:
            if "A" not in image.getbands() or image.getchannel("A").getextrema()[0] == 255:
                raise RuntimeError("Bria output has no transparent pixels; reject this cutout and do not register it")
    metadata = {
        "mode": selected,
        "generation_model": model,
        "generation_prediction": generation_id,
        "background_removal_model": REMOVE_BACKGROUND_MODEL if remove_background else None,
        "background_removal_prediction": removal_id,
        "reference": str(reference) if reference else None,
        "reference_bbox": reference_bbox,
        "output": str(output),
    }
    output.with_suffix(output.suffix + ".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-bbox", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    parser.add_argument("--mode", choices=("auto", "edit", "generate"), default="auto")
    parser.add_argument("--keep-background", action="store_true", help="debug only; recovered world assets normally need transparency")
    parser.add_argument("--aspect-ratio", default="1:1")
    parser.add_argument("--resolution", choices=("1k", "1.5k", "2k"), default="1k")
    parser.add_argument("--prompt-optimization", choices=("standard", "fast"), default="standard")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    recover(args.prompt, args.out, args.reference, args.reference_bbox, args.mode, not args.keep_background,
            args.aspect_ratio, args.resolution, args.prompt_optimization, args.timeout)


if __name__ == "__main__":
    main()
