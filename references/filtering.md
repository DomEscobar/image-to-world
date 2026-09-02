# Mask Filtering

Filters run cheaply first so the quadratic nesting comparison sees fewer masks.

| Order | Filter | Rule |
|---:|---|---|
| 1 | Area | drop below `0.0015` or above `0.55` of the image |
| 2 | Edge | drop when touching more than 3 image borders |
| 3 | Nesting | large-first; drop when intersection / smaller area exceeds `0.75` |
| 4 | Cap | retain the largest 18 |

Nesting divides by `min(areaA, areaB)`, not union. A small mask fully inside a large one is therefore recognized as duplicate coverage regardless of the size gap. Large-first ordering keeps the outer shape.

## When to change the defaults

- For icon sheets with many legitimate tiny objects, lower `--min-area` from `0.0015` to `0.0008`, then verify every survivor on the contact sheet.
- For one intentional scene-spanning terrain mask, raise `--max-area` from `0.55` to `0.75`; do not accept a full-image background mask.
- For touching or overlapping characters that produce useful inner masks, raise `--nest-thresh` from `0.75` to `0.90` so only near-complete containment is removed.
- For maps where walls legitimately touch every border, raise `--max-border-touch` from `3` to `4`, then inspect whether the result is really terrain rather than background.

## What not to do

The script exits instead of auto-loosening when fewer than two masks survive. Auto-loosening converts a clear “this image will not work” into a world full of noise fragments; the failure then resurfaces much later as an unplayable result nobody can explain. Read the report, identify the dominant filter, and prefer a clearer image before changing one threshold deliberately.

The contact sheet is the entire input to semantic labeling. Unreadable, overlapping, or object-covering numbers produce wrong labels regardless of segmentation quality, so treat badge clarity as a hard precondition.
