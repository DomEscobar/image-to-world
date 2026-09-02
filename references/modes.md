# Choosing a Mode

Defaulting to `side` is the most common failure. Users experience a wrong mode as a broken tool rather than one incorrect field, so choose from visual evidence.

## side

Use for a profile view with a clear horizontal ground line, stacked ledges, or a character expected to move left/right and jump.

```json
{"gravityY":1.2,"moveSpeed":4,"jumpVelocity":11,"drag":0.02}
```

## topdown

This is the forgotten mode. If the drawing looks made by someone looking **down** at a table, map, maze, room plan, or board, choose `topdown`. Ground and platform shapes become walls because the difference is gravity, not geometry. Top-down needs high drag (`0.15`) or movement feels like ice.

```json
{"gravityY":0,"moveSpeed":4,"jumpVelocity":0,"drag":0.15}
```

## float

Use when the character should drift through open space: underwater scenes, balloons, birds, outer space, or compositions with no meaningful floor. Low gravity and moderate drag create controllable motion without jumping.

```json
{"gravityY":0.25,"moveSpeed":3,"jumpVelocity":0,"drag":0.08}
```

## sandbox

Use when the image is intentionally physical, abstract, or too confusing to imply a coherent traversal goal. Sandbox is the honest answer for a confusing image. A collapsing scribble is a good outcome; an unreachable platformer is not.

```json
{"gravityY":1.0,"moveSpeed":4,"jumpVelocity":10,"drag":0.02}
```

## Ambiguous cases

- **House with no ground line:** choose `topdown` when rooms, doors, and furniture are arranged like a plan; choose `side` only when floors and roof read as a cross-section.
- **Lone character on a blank background:** choose `float` if free movement fits the subject; choose `sandbox` when there is no implied movement or environment.
- **Children's drawing mixing projections:** choose the projection that governs the traversable space. If none dominates, use `sandbox` rather than forcing incompatible geometry into a platformer.
- **Pixel art of a game screen:** follow the depicted game's camera. Horizontal platforms indicate `side`; maze-like floor tiles indicate `topdown`.
- **Photograph of a room:** a straight-on room photo is not truly 2D. State the limitation. Use `topdown` only for an overhead shot or floor plan; otherwise `sandbox` is usually more honest.

## Tuning beyond the defaults

- Raise `gravityY` for visibly heavy characters or short, decisive arcs; lower it for airy scenes.
- Raise `moveSpeed` for large open maps; lower it for tight obstacle spacing.
- Raise `jumpVelocity` only when platform gaps or vertical spacing demand it.
- Raise `drag` when control should stop quickly, especially in top-down or floating scenes.

Keep the mode defaults when nothing in the image suggests a change. Reflexive tuning produces arbitrary-feeling worlds.
