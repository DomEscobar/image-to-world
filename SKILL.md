---
name: image-to-world
description: Turn a single image into structured 2D world data with world.json, cut-out PNGs, and collision polygons. Use for asset extraction, explorable scenes, SAM/image-to-level pipelines, or validation and repair of an existing world.json. For a faithful playable reconstruction of a game screenshot, use screenshot-to-game instead.
---

# Image to World

Produce data, never executable game logic, so the result can be validated, cached, diffed, repaired, and safely interpreted by an engine.

## Route before processing

- Use this skill when the deliverable is structured world data, reusable cut-outs, collision shapes, or an explorable interpretation.
- Use `screenshot-to-game` when the user asks to recreate, clone, or make the pictured game itself. A game screenshot requires HUD parsing, scene relationships, a background plate, mechanics data, and browser verification that this asset pipeline does not provide.
- When wording is ambiguous, inspect the input. A screenshot with HUD, counters, minimaps, inventory, projectiles, or an existing game interface defaults to `screenshot-to-game`; art, maps, and standalone scenes default here.

## The split that makes this work

| Work | Owner | Why |
|---|---|---|
| Segmentation, mask filtering, contour tracing, validation | Python scripts | Deterministic work should produce the same output from the same input. |
| Deciding what each object is and how the world should play | The model | Semantics require understanding the picture. |
| Preview rendering | Python script | A deterministic verification render exposes bad cut-outs, scale, placement, and omissions before handoff. |

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

4. **FILTER AND INSPECT.** Run:
   ```bash
   python scripts/filter_masks.py work/masks/ --out work/filtered/ --source work/source.png --contact work/contact.png
   ```
   Open `work/contact.png`; file existence is not inspection. Compare it with the source and check every required subject, whole-object coverage, edge quality, duplicates, and background fragments. If a required subject is missing, rerun Hugging Face once with `SAM2_FOCUS_X` and `SAM2_FOCUS_Y` inside it, then regenerate and reopen the contact sheet. If fewer than two masks survive, stop and report the dominant filter. Do not auto-loosen thresholds; read [references/filtering.md](references/filtering.md) only for deliberate changes.

5. **RECOVER MISSED OR BAD ASSETS.** If focused SAM still misses a required subject or produces an unusable cut-out, read [references/asset-recovery.md](references/asset-recovery.md). Prefer WaveSpeed Seedream Edit with a tight source crop; use text-to-image only when no usable reference exists. Run Bria Remove Background, inspect the transparent result, then register it with `scripts/register_asset.py`. WaveSpeed calls cost money, so confirm authorization before the first charged request. Do not generate replacements for masks that are already usable.

6. **LABEL THE WORLD.** Use the inspected contact sheet plus any approved recovered assets. Read [references/modes.md](references/modes.md), choose the mode from visual evidence, and write `work/labels.json` using [references/schema.md](references/schema.md). Assign every kept index a useful label, role, and z value. Choose exactly one `player`. Verify every badge number is readable before labeling.

7. **Add rules only when the image suggests behavior.** Use only the closed trigger/action grammar in [references/schema.md](references/schema.md). If a behavior cannot be expressed, extend the schema with a new Action variant instead of hiding code in a string. Skip authored rules when the image suggests none; the validator supplies safe defaults for an empty set.

8. **Build.** Run:
   ```bash
   python scripts/build_world.py work/ --out out/
   ```
   Check the reported asset count and mode. Inspect warnings for missing or nonexistent label indices. Do not hand off the result yet.

9. **VALIDATE AND REPAIR.** Always run:
   ```bash
   python scripts/validate_world.py out/world.json --write
   ```
   Read every repair because repeated repairs diagnose labeling or schema drift. Re-run without `--write` and require exit code 0 before handoff. Never deliver an unvalidated world.

10. **RENDER AND VISUALLY VERIFY.** Always run:
   ```bash
   python scripts/render_preview.py out/world.json --out out/verification.png
   ```
   Open `out/verification.png` and inspect both the final world render and every cut-out on its checkerboard. Compare against the source for missing subjects, clipped or contaminated edges, wrong scale or position, duplicates, and background pieces mistaken for assets. If any required check fails, return to segmentation or asset recovery, rebuild, revalidate, and rerender. A schema-valid world is not finished until this visual gate passes.

11. **Report.** State raw/kept/recovered asset counts, the selected mode and visual reason, every validator repair, and the visual verification outcome. Deliver `world.json`, cut-out PNGs, `contact.png`, and `verification.png`. Never say “finished” or hand off the package when either visual artifact was not opened and inspected. For engine integration, consult [references/renderers.md](references/renderers.md).

## When the user already has a world.json

Skip to step 9, then render and inspect step 10 before handoff.

- **Player falls through the floor:** the renderer probably passed a concave polygon to an engine that requires decomposition. Fix the renderer; do not retrace the image.
- **Wrong player picked:** edit the relevant asset `role`, re-validate, and do not re-run the pipeline.
- **Wants it floatier:** change `tuning`; this is not a segmentation problem.

## Failure modes worth naming

- **Too many tiny assets:** segmentation produced fragments. Review the contact sheet and filtering report before changing `min-area` or the cap.
- **One giant mask:** the backend saw the composition as one object. Ask for clearer separation or try another configured backend; filtering cannot invent boundaries.
- **Missing or contaminated required asset:** try focused SAM once, then use the bounded WaveSpeed recovery branch and verify the generated cut-out.
- **Everything labeled decor:** correct roles in `labels.json`; validation can promote a player but cannot infer useful semantics.
- **Copyrighted input:** process only material the user is authorized to use, and do not imply that extracting assets changes its ownership or license.

## Files in this skill

- `references/schema.md` — read first; formats, roles, rules, defaults, and ranges.
- `references/modes.md` — mode selection and tuning evidence.
- `references/filtering.md` — filter behavior and deliberate threshold changes.
- `references/asset-recovery.md` — WaveSpeed Seedream repair/generation, Bria background removal, registration, and acceptance checks.
- `references/renderers.md` — safe consumption in Phaser, Godot, canvas, and rule interpreters.
- `scripts/normalize.py` — sanitize, orient, resize, and inspect input.
- `scripts/segment.py` — optional Hugging Face ZeroGPU, FAL, local, or Replicate SAM backends to raw masks. The `fal-ai/sam2/auto-segment` `individual_masks` response shape remains an open item until a funded live run completes; do not claim it has been live-verified.
- `scripts/filter_masks.py` — deterministic filtering and contact sheet creation.
- `scripts/contours.py` — masks to bbox-local polygons.
- `scripts/build_world.py` — assemble assets and `world.json`.
- `scripts/validate_world.py` — validate and repair worlds.
- `scripts/wavespeed_asset.py` — repair or generate one asset and remove its background through WaveSpeed.
- `scripts/register_asset.py` — fit a recovered transparent asset into the filtered manifest.
- `scripts/render_preview.py` — render the mandatory world-and-cutout verification board.
- `assets/world.schema.json` — machine-readable JSON Schema.
