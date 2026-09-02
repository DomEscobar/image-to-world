# Rendering `world.json`

## Contents

- [Shared concepts](#shared-concepts)
- [Phaser 3](#phaser-3)
- [Godot 4](#godot-4)
- [Plain canvas](#plain-canvas)
- [Rule interpreter](#rule-interpreter)

## Shared concepts

Each `bbox` is `[x, y, width, height]`; each polygon is local to that box. Position the texture at the bbox and pass the local vertices to physics. Polygons can be concave. Engines often silently misbehave rather than error, so always decompose when the engine requires convex fixtures. Vertices are counter-clockwise; reverse once at load time if the target engine expects clockwise.

| Role | Body |
|---|---|
| `player` | dynamic, fixed rotation |
| `ground`, `platform` | static collider |
| `hazard`, `collectible`, `goal` | static sensor |
| `decor` | no physics body |

In `topdown`, `ground` and `platform` are walls: the body type is unchanged, but the meaning differs because gravity, not geometry, determines traversal.

## Phaser 3

Load `poly-decomp` onto `window.decomp` before creating **any** Matter polygon body. Without it, concave shapes collapse to their convex hull without warning.

```js
import decomp from "poly-decomp";
window.decomp = decomp;

function addAsset(scene, asset) {
  const [x, y, w, h] = asset.bbox;
  const image = scene.matter.add.image(x + w / 2, y + h / 2, asset.id);
  image.setDisplaySize(w, h).setDepth(asset.z);
  if (asset.role === "decor") {
    scene.matter.world.remove(image.body);
    return image;
  }
  const sensor = ["hazard", "collectible", "goal"].includes(asset.role);
  const dynamic = asset.role === "player";
  image.setBody({ type: "fromVertices", verts: asset.polygon }, {
    isStatic: !dynamic,
    isSensor: sensor,
    inertia: dynamic ? Infinity : undefined,
    label: asset.id
  });
  image.gameRole = asset.role;
  return image;
}
```

For side-mode ground checks, attach a thin sensor rectangle beneath the player and count contacts. Do not use a raycast: raycasts miss sloped traced terrain often enough to make jumping feel broken.

## Godot 4

`CollisionPolygon2D` handles concavity itself, so this path has one fewer dependency than Phaser.

```gdscript
func add_asset(a: Dictionary) -> Node2D:
    var root := Node2D.new()
    root.position = Vector2(a.bbox[0], a.bbox[1])
    var sprite := Sprite2D.new()
    sprite.texture = load("res://" + a.file)
    sprite.centered = false
    sprite.z_index = int(a.z)
    root.add_child(sprite)
    if a.role != "decor":
        var body = CharacterBody2D.new() if a.role == "player" else StaticBody2D.new()
        var collision := CollisionPolygon2D.new()
        collision.polygon = PackedVector2Array(a.polygon.map(func(p): return Vector2(p[0], p[1])))
        body.add_child(collision)
        root.add_child(body)
    add_child(root)
    return root
```

Use `Area2D` rather than `StaticBody2D` for sensor roles.

## Plain canvas

Draw assets in ascending `z` order using their bbox. Canvas does not supply physics, so keep rendering separate from the collision library and feed it the same bbox-local polygons.

```js
for (const a of [...world.assets].sort((x, y) => x.z - y.z)) {
  const [x, y, w, h] = a.bbox;
  ctx.drawImage(images[a.id], x, y, w, h);
}
```

## Rule interpreter

Interpret the closed grammar with a `switch` over `action.do`:

```js
function perform(action, scene) {
  const body = action.target ? scene.resolve(action.target) : null;
  if (body?.destroyed) return;
  switch (action.do) {
    case "respawn": return scene.respawn(action.target);
    case "win": return scene.win();
    case "lose": return scene.lose();
    case "remove": return body?.remove();
    case "open": body?.setSensor(true); body?.setAlpha(0.4); return;
    case "spawn": return scene.liveCloneCount < 30 && scene.spawn(action.target);
    case "score": return scene.addScore(action.amount);
    case "move": return body?.moveBy(action.dx, action.dy);
    default: return;
  }
}
```

Never use `eval`, `new Function`, or dynamic import. The closed grammar lets untrusted model output drive behavior without becoming executable; reaching for evaluation throws that guarantee away entirely.

Operational rules:

1. Register collision handlers once while building the scene, not once per frame.
2. Use the engine scheduler for timers so pause and teardown work correctly.
3. Implement `open` by making the body a sensor and setting alpha to `0.4`, rather than deleting it, so the player can see that the door opened.
4. Cap `spawn` at 30 live clones across the whole scene.
5. Fire rules in array order for deterministic conflicts.
6. Guard every action against destroyed bodies.
