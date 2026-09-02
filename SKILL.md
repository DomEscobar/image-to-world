---
name: image-to-world
description: Turn a single image into a structured 2D world with world.json, cut-out asset PNGs, and collision polygons for Phaser, Godot, three.js, or custom engines. Use when making an image playable, interactive, or explorable; turning art, drawings, sketches, maps, or screenshots into a game, level, scene, or world; extracting sprites, assets, or collision shapes from a picture; or building any pipeline mentioning segmentation, SAM, or image-to-level conversion. The request need not say "world" or "schema". Also use when an existing world.json needs validation, repair, re-labeling, or re-rendering.
---

# Image to World

Produce data, never executable game logic, so the result can be validated, cached, diffed, repaired, and safely interpreted by an engine.

## The split that makes this work

| Work | Owner | Why |
|---|---|---|
| Segmentation, mask filtering, contour tracing, validation | Python scripts | Deterministic work should produce the same output from the same input. |
| Deciding what each object is and how the world should play | The model | Semantics require understanding the picture. |
| Rendering | The target engine | Keep rendering reusable and outside this skill. |

Never reimplement the scripts inline, never eyeball contours, never let the semantic step emit executable code.

## Workflow

1. **Read the schema.** Read [references/schema.md](references/schema.md) before doing anything else. Confirm the labels format, role set, rule grammar, and numeric ranges. Guessing field names wastes the expensive segmentation work when validation later rejects the result.

2. **Normalize.** Run:
   ```bash
   python scripts/normalize.py <image> --out work/source.png
   ```
   Check `work/meta.json`, especially the normalized dimensions and aspect hint. If the input is an angled photograph of a 3D space, say so plainly and offer to continue anyway because a flat 2D interpretation may be awkward. Do not feed the original upload bytes to segmentation; normalization sanitizes and re-encodes them.

3. **Segment.** Run:
   ```bash
   python scripts/segment.py work/source.png --out work/masks/ --backend huggingface
   ```
   Use `huggingface` for the deployed ZeroGPU Space, `fal` for FAL, `local` for an installed checkpoint, or `replicate` for Replicate. Set `HF_SPACE` to override the default `neridonk/image-to-world-sam2` Space; set `HF_TOKEN` to use the signed-in account's ZeroGPU quota. Check that numbered single-channel masks were created at the exact source dimensions. If no backend is configured, stop and name the environment variable reported by the script. Never fabricate masks.

4. **Filter.** Run:
   ```bash
   python scripts/filter_masks.py work/masks/ --out work/filtered/ --source work/source.png --contact work/contact.png
   ```
   Check the JSON report and inspect the contact sheet. If fewer than two masks survive, stop, report which filter removed the most, and ask for a clearer image. Do not auto-loosen thresholds; read [references/filtering.md](references/filtering.md) only when the defaults need deliberate adjustment.

5. **LABEL THE WORLD.** Inspect `work/contact.png`; it is the complete visual input to this semantic step. Read [references/modes.md](references/modes.md), choose the mode from visual evidence, and write `work/labels.json` using [references/schema.md](references/schema.md). Assign every kept index a useful label, role, and z value. Choose exactly one `player`. Verify every badge number is readable before labeling; an unreadable contact sheet silently corrupts the world.

6. **Add rules only when the image suggests behavior.** Use only the closed trigger/action grammar in [references/schema.md](references/schema.md). If a behavior cannot be expressed, extend the schema with a new Action variant instead of hiding code in a string. Skip authored rules when the image suggests none; the validator supplies safe defaults for an empty set.

7. **Build.** Run:
   ```bash
   python scripts/build_world.py work/ --out out/
   ```
   Check the reported asset count and mode. Inspect warnings for missing or nonexistent label indices. Do not hand off the result yet.

8. **VALIDATE AND REPAIR.** Always run:
   ```bash
   python scripts/validate_world.py out/world.json --write
   ```
   Read every repair because repeated repairs diagnose labeling or schema drift. Re-run without `--write` and require exit code 0 before handoff. Never deliver an unvalidated world.

9. **Report.** State how many masks survived from the raw set, the selected mode and the visual reason, every repair made, and the locations of `world.json` and the cut-out PNGs. Show `contact.png` when the interface can display it. For rendering integration, consult [references/renderers.md](references/renderers.md) for the target engine rather than generating bespoke game code.

## When the user already has a world.json

Skip to step 8, then repair only what the symptom requires.

- **Player falls through the floor:** the renderer probably passed a concave polygon to an engine that requires decomposition. Fix the renderer; do not retrace the image.
- **Wrong player picked:** edit the relevant asset `role`, re-validate, and do not re-run the pipeline.
- **Wants it floatier:** change `tuning`; this is not a segmentation problem.

## Failure modes worth naming

- **Too many tiny assets:** segmentation produced fragments. Review the contact sheet and filtering report before changing `min-area` or the cap.
- **One giant mask:** the backend saw the composition as one object. Ask for clearer separation or try another configured backend; filtering cannot invent boundaries.
- **Everything labeled decor:** correct roles in `labels.json`; validation can promote a player but cannot infer useful semantics.
- **Copyrighted input:** process only material the user is authorized to use, and do not imply that extracting assets changes its ownership or license.

## Files in this skill

- `references/schema.md` — read first; formats, roles, rules, defaults, and ranges.
- `references/modes.md` — mode selection and tuning evidence.
- `references/filtering.md` — filter behavior and deliberate threshold changes.
- `references/renderers.md` — safe consumption in Phaser, Godot, canvas, and rule interpreters.
- `scripts/normalize.py` — sanitize, orient, resize, and inspect input.
- `scripts/segment.py` — optional Hugging Face ZeroGPU, FAL, local, or Replicate SAM backends to raw masks. The `fal-ai/sam2/auto-segment` `individual_masks` response shape remains an open item until a funded live run completes; do not claim it has been live-verified.
- `scripts/filter_masks.py` — deterministic filtering and contact sheet creation.
- `scripts/contours.py` — masks to bbox-local polygons.
- `scripts/build_world.py` — assemble assets and `world.json`.
- `scripts/validate_world.py` — validate and repair worlds.
- `assets/world.schema.json` — machine-readable JSON Schema.
