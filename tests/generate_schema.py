#!/usr/bin/env python3
"""Generate assets/world.schema.json from validator constants."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_world as validator  # noqa: E402


def number(minimum, maximum):
    return {"type": "number", "minimum": minimum, "maximum": maximum}


def target_schema():
    return {"type": "string", "minLength": 1}


def make_schema():
    trigger_variants = [
        {"type": "object", "additionalProperties": False, "required": ["on", "a", "b"], "properties": {"on": {"const": "collide"}, "a": target_schema(), "b": target_schema()}},
        {"type": "object", "additionalProperties": False, "required": ["on"], "properties": {"on": {"const": "collect_all"}}},
        {"type": "object", "additionalProperties": False, "required": ["on", "count"], "properties": {"on": {"const": "collect_count"}, "count": {"type": "number", "minimum": 1, "maximum": 99}}},
        {"type": "object", "additionalProperties": False, "required": ["on", "every"], "properties": {"on": {"const": "timer"}, "every": number(1, 30)}},
        {"type": "object", "additionalProperties": False, "required": ["on"], "properties": {"on": {"const": "start"}}},
    ]
    action_variants = [
        {"type": "object", "additionalProperties": False, "required": ["do"], "properties": {"do": {"const": "respawn"}, "target": target_schema()}},
        *[{"type": "object", "additionalProperties": False, "required": ["do"], "properties": {"do": {"const": name}}} for name in ("win", "lose")],
        *[{"type": "object", "additionalProperties": False, "required": ["do", "target"], "properties": {"do": {"const": name}, "target": target_schema()}} for name in ("remove", "open", "spawn")],
        {"type": "object", "additionalProperties": False, "required": ["do", "amount"], "properties": {"do": {"const": "score"}, "amount": number(-100, 100)}},
        {"type": "object", "additionalProperties": False, "required": ["do", "target", "dx", "dy"], "properties": {"do": {"const": "move"}, "target": target_schema(), "dx": number(-400, 400), "dy": number(-400, 400)}},
    ]
    rule = {
        "type": "object",
        "additionalProperties": False,
        "required": ["trigger", "action"],
        "properties": {"trigger": {"oneOf": trigger_variants}, "action": {"oneOf": action_variants}},
        "not": {"properties": {"trigger": {"properties": {"on": {"const": "start"}}, "required": ["on"]}, "action": {"properties": {"do": {"const": "win"}}, "required": ["do"]}}, "required": ["trigger", "action"]},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/image-to-world/world.schema.json",
        "title": "Image to World v2",
        "type": "object",
        "additionalProperties": False,
        "required": ["version", "mode", "width", "height", "tuning", "assets", "rules"],
        "properties": {
            "version": {"const": 2},
            "mode": {"enum": sorted(validator.MODES)},
            "width": {"type": "integer", "minimum": 1},
            "height": {"type": "integer", "minimum": 1},
            "background": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
            "tuning": {
                "type": "object", "additionalProperties": False,
                "required": list(validator.RANGES),
                "properties": {key: number(bounds[0], bounds[1]) for key, bounds in validator.RANGES.items()},
            },
            "assets": {
                "type": "array", "minItems": 1,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["id", "file", "role", "bbox", "z", "polygon"],
                    "properties": {
                        "id": {"type": "string", "pattern": "^asset_[0-9]{2,}$"},
                        "file": {"type": "string", "minLength": 1},
                        "label": {"type": "string"},
                        "role": {"enum": sorted(validator.ROLES)},
                        "bbox": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "integer"}},
                        "areaRatio": number(0, 1),
                        "z": number(0, 100),
                        "polygon": {"type": "array", "minItems": 3, "maxItems": 24, "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}}},
                    },
                },
            },
            "rules": {"type": "array", "maxItems": 12, "items": rule},
        },
    }


if __name__ == "__main__":
    destination = ROOT / "assets" / "world.schema.json"
    destination.write_text(json.dumps(make_schema(), indent=2) + "\n", encoding="utf-8")
    print(destination)
