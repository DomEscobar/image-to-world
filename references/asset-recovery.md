# Asset Recovery

Use this branch only after visual inspection proves that a required subject is missing or that its cut-out is unusable. SAM remains the default because extraction preserves the source exactly; generation is a repair path, not a substitute for inspecting masks.

## Decision path

1. If the subject is missing, try one focused SAM point inside it and regenerate the contact sheet.
2. If SAM still misses it, or the surviving cut-out is incomplete, use Seedream Edit with a tight source crop. This preserves the source design better than text-only generation.
3. Use Seedream text-to-image only when the required asset is absent or too occluded to serve as a reference. State that this invents pixels and require the user's permission when that changes the source materially.
4. Run Bria Remove Background on every generated or edited asset. Reject outputs without real transparency.
5. Inspect the recovered PNG on a checkerboard before registration. Reject changed identity, wrong style, extra objects, shadows, halos, clipped edges, or missing parts.
6. Register the approved cut-out at the intended source-space bbox, rebuild, validate, render the verification board, and inspect again.

WaveSpeed submissions are billed. Confirm spend authorization before the first charged request in a task. Never blindly retry a submission POST: the first request may have been accepted and billed even when its response was lost.

## Commands

Repair or extract a visible subject from the normalized source:

```bash
python scripts/wavespeed_asset.py \
  --reference work/source.png --reference-bbox X Y W H \
  --prompt "Create one complete isolated game asset matching this exact subject, design, colors, proportions, and art style. Center only the subject. No extra objects, text, floor, shadow, or scenery. Use a plain background." \
  --out work/recovery/player.png
```

Generate a required asset that has no usable visual reference:

```bash
python scripts/wavespeed_asset.py \
  --mode generate \
  --prompt "One complete isolated 2D game asset: <description>. Match <source style description>. Centered, full object visible, no extra objects, text, floor, shadow, or scenery. Plain background." \
  --out work/recovery/missing.png
```

The script uses `bytedance/seedream-v5.0-pro/edit` when a reference is supplied, `bytedance/seedream-v5.0-pro` otherwise, and then `bria/remove-background`. It requires `WAVESPEED_API_KEY`, downloads temporary outputs immediately, and writes a provenance sidecar next to the PNG.

Register a replacement at an existing index or add a missed asset with the next index:

```bash
python scripts/register_asset.py work/ work/recovery/player.png --bbox X Y W H --index N
python scripts/register_asset.py work/ work/recovery/missing.png --bbox X Y W H
```

For a new index, add its semantic entry to `labels.json`. `build_world.py` automatically prefers `work/recovered/asset_NN.png` over the original source crop.

## Acceptance checks

- The recovered PNG has a non-empty alpha channel and no opaque background rectangle.
- The subject is complete and visually consistent with the source.
- The registered bbox and scale match the intended location.
- Collision geometry follows the recovered alpha rather than the failed SAM mask.
- The final verification board contains no missing required subject, bad edge, unexpected duplicate, or obstructive background fragment.
