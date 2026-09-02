#!/usr/bin/env python3
"""Validate and repair world.json without third-party schema dependencies."""

import argparse
import json
import math
import sys
from pathlib import Path

MODES = {"side", "topdown", "float", "sandbox"}
ROLES = {"player", "ground", "platform", "hazard", "collectible", "goal", "decor"}
TRIGGERS = {"collide", "collect_all", "collect_count", "timer", "start"}
ACTIONS = {"respawn", "win", "lose", "remove", "open", "spawn", "score", "move"}
MODE_DEFAULTS = {
    "side": {"gravityY": 1.2, "moveSpeed": 4, "jumpVelocity": 11, "drag": 0.02},
    "topdown": {"gravityY": 0, "moveSpeed": 4, "jumpVelocity": 0, "drag": 0.15},
    "float": {"gravityY": 0.25, "moveSpeed": 3, "jumpVelocity": 0, "drag": 0.08},
    "sandbox": {"gravityY": 1.0, "moveSpeed": 4, "jumpVelocity": 10, "drag": 0.02},
}
RANGES = {
    "gravityY": (0, 2.5), "moveSpeed": (1, 10), "jumpVelocity": (0, 20), "drag": (0, 0.2),
}
DEFAULT_RULES = [
    {"trigger": {"on": "collide", "a": "player", "b": "hazard"}, "action": {"do": "respawn"}},
    {"trigger": {"on": "collide", "a": "player", "b": "goal"}, "action": {"do": "win"}},
    {"trigger": {"on": "collect_all"}, "action": {"do": "win"}},
]


class Report:
    def __init__(self):
        self.repairs = []
        self.fatal = []

    def repair(self, message):
        self.repairs.append(message)

    def fail(self, message):
        self.fatal.append(message)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def clamp(container, key, low, high, default, report, path):
    value = container.get(key)
    if not _number(value):
        container[key] = default
        report.repair(f"{path} replaced {value!r} with default {default}")
        return
    changed = max(low, min(high, value))
    if changed != value:
        container[key] = changed
        report.repair(f"{path} clamped {value}→{changed}")


def validate_assets(world, report):
    raw_assets = world.get("assets")
    if not isinstance(raw_assets, list) or not raw_assets:
        report.fail("assets is absent or empty")
        return []
    assets = []
    seen = set()
    for index, asset in enumerate(raw_assets):
        if not isinstance(asset, dict):
            report.repair(f"asset entry {index} dropped because it is not an object")
            continue
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id:
            report.repair(f"asset entry {index} dropped because id is missing")
            continue
        if asset_id in seen:
            report.repair(f"duplicate asset id {asset_id} dropped")
            continue
        seen.add(asset_id)
        if asset.get("role") not in ROLES:
            old = asset.get("role")
            asset["role"] = "decor"
            report.repair(f"{asset_id} unknown role {old!r} replaced with decor")
        clamp(asset, "z", 0, 100, 50, report, f"{asset_id}.z")
        bbox = asset.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4 or any(not _number(value) for value in bbox):
            report.fail(f"{asset_id} bbox is missing or not four numbers")
            continue
        polygon = asset.get("polygon")
        valid_polygon = isinstance(polygon, list) and all(
            isinstance(point, list) and len(point) == 2 and all(_number(value) for value in point)
            for point in polygon
        )
        if not valid_polygon or len(polygon) < 3:
            width, height = bbox[2], bbox[3]
            asset["polygon"] = [[0, 0], [width, 0], [width, height], [0, height]]
            report.repair(f"{asset_id} polygon replaced with bbox rectangle")
        elif len(polygon) > 24:
            asset["polygon"] = polygon[:24]
            report.repair(f"{asset_id} polygon truncated to 24 vertices")
        assets.append(asset)
    if not assets:
        report.fail("no usable assets remain")
        return []
    players = [asset for asset in assets if asset.get("role") == "player"]
    if not players:
        candidates = [asset for asset in assets if asset.get("role") != "decor"] or assets
        promoted = min(candidates, key=lambda asset: asset.get("areaRatio", 1.0) if _number(asset.get("areaRatio")) else 1.0)
        promoted["role"] = "player"
        report.repair(f"promoted {promoted['id']} ({promoted.get('label', 'unlabeled')}) to player")
    elif len(players) > 1:
        for extra in players[1:]:
            extra["role"] = "decor"
            report.repair(f"demoted extra player {extra['id']} to decor")
    world["assets"] = assets
    return assets


def validate_rules(world, assets, report):
    original = world.get("rules", [])
    if not isinstance(original, list):
        report.repair("rules replaced because it was not an array")
        original = []
    valid_targets = {asset["id"] for asset in assets} | ROLES
    retained = []
    for index, rule in enumerate(original):
        prefix = f"rule {index}"
        if not isinstance(rule, dict):
            report.repair(f"{prefix} dropped because it is not an object")
            continue
        trigger, action = rule.get("trigger"), rule.get("action")
        if not isinstance(trigger, dict) or not isinstance(action, dict):
            report.repair(f"{prefix} dropped because trigger or action is missing")
            continue
        on, do = trigger.get("on"), action.get("do")
        if on not in TRIGGERS:
            report.repair(f"{prefix} dropped for unknown trigger {on!r}")
            continue
        if do not in ACTIONS:
            report.repair(f"{prefix} dropped for unknown action {do!r}")
            continue
        if on == "start" and do == "win":
            report.repair(f"{prefix} dropped because start→win wins instantly")
            continue
        unresolved = None
        for key in ("a", "b"):
            if key in trigger and trigger[key] not in valid_targets:
                unresolved = trigger[key]
                break
        if unresolved is None and "target" in action and action["target"] not in valid_targets:
            unresolved = action["target"]
        if unresolved is not None:
            report.repair(f"{prefix} dropped for unresolved target {unresolved!r}")
            continue
        if on == "timer":
            clamp(trigger, "every", 1, 30, 3, report, f"{prefix}.trigger.every")
        if on == "collect_count":
            clamp(trigger, "count", 1, 99, 1, report, f"{prefix}.trigger.count")
        if do == "score":
            clamp(action, "amount", -100, 100, 1, report, f"{prefix}.action.amount")
        if do == "move":
            clamp(action, "dx", -400, 400, 0, report, f"{prefix}.action.dx")
            clamp(action, "dy", -400, 400, 0, report, f"{prefix}.action.dy")
        retained.append(rule)
    if len(retained) > 12:
        report.repair(f"rules capped from {len(retained)} to 12")
        retained = retained[:12]
    if not retained:
        if original:
            report.repair("all authored rules were dropped; applied default rules")
        else:
            report.repair("empty rule set replaced with default rules")
        retained = json.loads(json.dumps(DEFAULT_RULES))
    world["rules"] = retained


def validate(world):
    report = Report()
    if world.get("version") != 2:
        old = world.get("version")
        world["version"] = 2
        report.repair(f"version changed {old!r}→2")
    for key, default in (("width", 1024), ("height", 1024)):
        if not isinstance(world.get(key), int) or isinstance(world.get(key), bool) or world[key] < 1:
            old = world.get(key)
            world[key] = default
            report.repair(f"{key} replaced {old!r} with {default}")
    if not isinstance(world.get("background"), str) or len(world["background"]) != 7 or not world["background"].startswith("#"):
        world["background"] = "#ffffff"
        report.repair("background replaced with #ffffff")
    mode = world.get("mode")
    if mode not in MODES:
        world["mode"] = mode = "side"
        report.repair("unknown mode replaced with side")
    tuning = world.get("tuning")
    if not isinstance(tuning, dict):
        tuning = {}
        world["tuning"] = tuning
        report.repair(f"tuning replaced with {mode} defaults")
    defaults = MODE_DEFAULTS[mode]
    for key, (low, high) in RANGES.items():
        clamp(tuning, key, low, high, defaults[key], report, f"tuning.{key}")
    world["tuning"] = {key: tuning[key] for key in defaults}
    assets = validate_assets(world, report)
    if not report.fatal:
        validate_rules(world, assets, report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("world", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        world = json.loads(args.world.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FATAL unable to read world: {error}", file=sys.stderr)
        raise SystemExit(2)
    if not isinstance(world, dict):
        print("FATAL world root must be an object", file=sys.stderr)
        raise SystemExit(2)
    report = validate(world)
    if report.fatal:
        for message in report.fatal:
            print(f"FATAL {message}", file=sys.stderr)
        raise SystemExit(2)
    if args.write and report.repairs:
        args.world.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")
    if report.repairs and not args.quiet:
        for message in report.repairs:
            print(f"- {message}")
        if not args.write:
            print("(run with --write to persist these)")
    raise SystemExit(1 if report.repairs else 0)


if __name__ == "__main__":
    main()
