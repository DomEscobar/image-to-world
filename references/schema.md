# Data Schema

## Contents

- [labels.json](#labelsjson)
- [world.json](#worldjson)
- [Roles](#roles)
- [Rule grammar](#rule-grammar)
- [Default rules](#default-rules)
- [Ranges and clamping](#ranges-and-clamping)

## labels.json

Write this semantic input after inspecting the contact sheet:

```json
{
  "mode": "side",
  "tuning": {"gravityY": 1.2, "moveSpeed": 4, "jumpVelocity": 11, "drag": 0.02},
  "assets": [
    {"index": 0, "label": "grassy ground", "role": "ground", "z": 30},
    {"index": 1, "label": "round hero", "role": "player", "z": 60},
    {"index": 2, "label": "stone ledge", "role": "platform", "z": 40}
  ],
  "rules": [
    {"trigger": {"on": "collide", "a": "player", "b": "goal"}, "action": {"do": "win"}}
  ]
}
```

Omitted indices are dropped from semantic selection. Indices that do not exist in the manifest are ignored with a warning. Neither case is an error because partial labeling should remain buildable.

## world.json

```json
{
  "version": 2,
  "mode": "side",
  "width": 800,
  "height": 600,
  "background": "#f4efe6",
  "tuning": {"gravityY": 1.2, "moveSpeed": 4, "jumpVelocity": 11, "drag": 0.02},
  "assets": [
    {
      "id": "asset_00",
      "file": "assets/asset_00.png",
      "label": "grassy ground",
      "role": "ground",
      "bbox": [0, 480, 800, 120],
      "areaRatio": 0.14719,
      "z": 30,
      "polygon": [[0, 40], [200, 0], [500, 60], [800, 20], [800, 120], [0, 120]]
    }
  ],
  "rules": []
}
```

`bbox` is `[x, y, width, height]`. `polygon` coordinates are **local to the bbox**, not global image coordinates. Local polygons move with an asset and let a cut-out be reused; a global polygon cannot be moved or reused without rewriting every vertex.

## Roles

| Role | Body | Meaning |
|---|---|---|
| `player` | dynamic, fixed rotation | exactly one per world |
| `ground` | static | terrain; a wall in `topdown` |
| `platform` | static | standalone surface |
| `hazard` | static sensor | contact triggers respawn under default rules |
| `collectible` | static sensor | counts toward `collect_all` |
| `goal` | static sensor | reaching wins; ignored in `sandbox` |
| `decor` | none | rendered only; the safe default |

When unsure between `platform` and `decor`, choose `decor`: too few colliders leaves a world explorable, while turning a visual background into one solid body leaves the player stuck.

## Rule grammar

```ts
type Target = string; // asset id or role name
type Trigger =
  | { on: "collide"; a: Target; b: Target }
  | { on: "collect_all" }
  | { on: "collect_count"; count: number }
  | { on: "timer"; every: number }
  | { on: "start" };

type Action =
  | { do: "respawn"; target?: Target }
  | { do: "win" }
  | { do: "lose" }
  | { do: "remove"; target: Target }
  | { do: "open"; target: Target }
  | { do: "spawn"; target: Target }
  | { do: "score"; amount: number }
  | { do: "move"; target: Target; dx: number; dy: number };

type Rule = { trigger: Trigger; action: Action };
```

Rules are objects, capped at 12. Triggers and actions must use a listed variant. All `a`, `b`, and `target` references must resolve to an asset id or role name. `start` plus `win` is rejected because it wins immediately. Numeric values are clamped to the documented ranges.

Keys open a door after all collectibles are found:

```json
{"trigger":{"on":"collect_all"},"action":{"do":"open","target":"asset_05"}}
```

A platform patrols every three seconds:

```json
{"trigger":{"on":"timer","every":3},"action":{"do":"move","target":"asset_02","dx":120,"dy":0}}
```

## Default rules

When validation ends with no usable rules, it installs:

```json
[
  {"trigger":{"on":"collide","a":"player","b":"hazard"},"action":{"do":"respawn"}},
  {"trigger":{"on":"collide","a":"player","b":"goal"},"action":{"do":"win"}},
  {"trigger":{"on":"collect_all"},"action":{"do":"win"}}
]
```

An empty rule set means nothing can ever happen, so the fallback provides basic hazard, goal, and collection behavior. Renderers may ignore rules whose roles do not occur.

## Ranges and clamping

| Field | Range | Default |
|---|---:|---:|
| `gravityY` | 0–2.5 | per mode |
| `moveSpeed` | 1–10 | 4 |
| `jumpVelocity` | 0–20 | 11 |
| `drag` | 0–0.2 | 0.02 |
| asset `z` | 0–100 | 50 |
| `timer.every` | 1–30 | 3 |
| `collect_count.count` | 1–99 | 1 |
| `score.amount` | -100–100 | 1 |
| `move.dx`, `move.dy` | -400–400 | 0 |
| polygon vertices | 3–24 | bbox rectangle |

Mode defaults are: `side` = `1.2/4/11/0.02`; `topdown` = `0/4/0/0.15`; `float` = `0.25/3/0/0.08`; `sandbox` = `1.0/4/10/0.02`, ordered as gravity, speed, jump, drag.
