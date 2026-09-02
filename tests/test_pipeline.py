#!/usr/bin/env python3

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_world  # noqa: E402
import contours  # noqa: E402
import filter_masks  # noqa: E402
import validate_world  # noqa: E402


def create_fixture(root):
    work = root / "work"
    masks = work / "masks"
    masks.mkdir(parents=True)
    source = Image.new("RGB", (800, 600), (244, 239, 230))
    source_draw = ImageDraw.Draw(source)
    shapes = [
        ("polygon", [(0, 520), (200, 480), (500, 540), (799, 500), (799, 599), (0, 599)]),
        ("ellipse", [380, 300, 470, 400]),
        ("rectangle", [250, 380, 400, 410]),
        ("polygon", [(600, 300), (620, 260), (640, 300)]),
        ("ellipse", [120, 200, 150, 230]),
        ("ellipse", [400, 320, 430, 350]),
        ("rectangle", [0, 0, 799, 599]),
        ("ellipse", [700, 10, 706, 16]),
    ]
    colors = ["#608c42", "#3878d8", "#8f7057", "#d74242", "#f1c232", "#222222", "#eeeeee", "#000000"]
    for index, ((kind, points), color) in enumerate(zip(shapes, colors)):
        mask = Image.new("L", source.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        getattr(mask_draw, kind)(points, fill=255)
        getattr(source_draw, kind)(points, fill=color)
        mask.save(masks / f"raw_{index:03d}.png")
    source.save(work / "source.png")
    return work


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work = create_fixture(self.root)
        self.filtered = self.work / "filtered"
        self.contact = self.work / "contact.png"
        self.manifest = filter_masks.filter_masks(
            self.work / "masks", self.filtered, self.work / "source.png", self.contact,
            18, 0.0015, 0.55, 0.75, 3,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_fixture_filters_and_regressions(self):
        self.assertEqual(self.manifest["report"], {
            "raw": 8, "dropped_area": 2, "dropped_border": 0,
            "dropped_nested": 1, "dropped_cap": 0, "kept": 5,
        })
        self.assertEqual([item["source_mask"] for item in self.manifest["assets"]], [f"raw_{i:03d}.png" for i in range(5)])
        self.assertTrue(self.contact.exists())
        bboxes = [item["bbox"] for item in self.manifest["assets"]]
        placed = []
        for bbox in bboxes:
            rect = filter_masks.choose_badge_rect(bbox, (800, 600), placed)
            own = (bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3])
            if bbox[2] <= 60 or bbox[3] <= 54:
                self.assertFalse(filter_masks._intersects(rect, own))
            self.assertFalse(any(filter_masks._intersects(rect, prior) for prior in placed))
            placed.append(rect)

    def test_contours(self):
        polygons = []
        for item in self.manifest["assets"]:
            mask = np.asarray(Image.open(self.filtered / item["mask"]).convert("L")) > 127
            polygon, _ = contours.mask_to_polygon(mask)
            polygons.append(polygon)
            self.assertGreaterEqual(len(polygon), 3)
            self.assertLessEqual(len(polygon), 24)
            self.assertGreater(contours.polygon_area(polygon), 0)
        self.assertGreaterEqual(len(polygons[0]), 5)
        self.assertEqual(len(polygons[2]), 4)
        self.assertEqual(len(polygons[3]), 3)

    def _write_broken_labels(self):
        labels = {
            "mode": "side",
            "tuning": {"gravityY": 40, "moveSpeed": 4, "jumpVelocity": 11, "drag": 0.02},
            "assets": [
                {"index": 0, "label": "ground", "role": "ground", "z": 20},
                {"index": 1, "label": "player", "role": "player", "z": 60},
                {"index": 2, "label": "platform", "role": "platform", "z": 40},
                {"index": 3, "label": "hazard", "role": "hazard", "z": 45},
                {"index": 4, "label": "coin", "role": "collectible", "z": 50},
                {"index": 9, "role": "decor"},
            ],
            "rules": [
                {"trigger": {"on": "collect_all"}, "action": {"do": "open", "target": "asset_02"}},
                {"trigger": {"on": "collide", "a": "player", "b": "asset_99"}, "action": {"do": "win"}},
                {"trigger": {"on": "start"}, "action": {"do": "win"}},
                {"trigger": {"on": "timer", "every": 900}, "action": {"do": "spawn", "target": "asset_04"}},
                {"trigger": {"on": "hover"}, "action": {"do": "explode"}},
            ],
        }
        (self.work / "labels.json").write_text(json.dumps(labels), encoding="utf-8")

    def test_build_and_exact_five_repairs(self):
        self._write_broken_labels()
        world = build_world.build(self.work, self.root / "out", 0.01)
        unrepaired = copy.deepcopy(world)
        report = validate_world.validate(world)
        self.assertEqual(len(report.repairs), 5, report.repairs)
        self.assertFalse(report.fatal)
        self.assertEqual(world["tuning"]["gravityY"], 2.5)
        self.assertEqual(world["rules"][1]["trigger"]["every"], 30)
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is a test-time optional dependency")
        schema = json.loads((ROOT / "assets" / "world.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertEqual(list(jsonschema.Draft202012Validator(schema).iter_errors(world)), [])
        self.assertGreaterEqual(len(list(jsonschema.Draft202012Validator(schema).iter_errors(unrepaired))), 4)

    def test_all_decor_promotes_player_and_defaults_rules(self):
        labels = {
            "mode": "side",
            "assets": [{"index": item["index"], "label": f"object {item['index']}", "role": "decor", "z": 50} for item in self.manifest["assets"]],
            "rules": [],
        }
        (self.work / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
        world = build_world.build(self.work, self.root / "out", 0.01)
        report = validate_world.validate(world)
        self.assertEqual(sum(asset["role"] == "player" for asset in world["assets"]), 1)
        self.assertEqual(world["rules"], validate_world.DEFAULT_RULES)
        self.assertTrue(any("promoted" in repair for repair in report.repairs))

    def test_segment_backends_name_missing_environment(self):
        for backend, variable in (("fal", "FAL_KEY"), ("local", "SAM2_CHECKPOINT"), ("replicate", "REPLICATE_API_TOKEN")):
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "segment.py"), str(self.work / "source.png"), "--out", str(self.root / backend), "--backend", backend],
                text=True, capture_output=True, env={}, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(variable, result.stderr)


if __name__ == "__main__":
    unittest.main()
