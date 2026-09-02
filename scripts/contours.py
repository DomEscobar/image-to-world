#!/usr/bin/env python3
"""Trace binary masks into simplified bbox-local collision polygons."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

NEIGHBORS = [(-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1)]


def trace_outer_contour(mask: np.ndarray):
    binary = np.asarray(mask, dtype=bool)
    if not binary.any():
        return None
    padded = np.pad(binary, 1)
    ys, xs = np.nonzero(padded)
    first = min(zip(xs.tolist(), ys.tolist()), key=lambda p: (p[1], p[0]))
    current = first
    backtrack = (first[0] - 1, first[1])
    contour = [current]
    limit = padded.size * 4

    for _ in range(limit):
        relative = (backtrack[0] - current[0], backtrack[1] - current[1])
        try:
            start_index = NEIGHBORS.index(relative)
        except ValueError:
            start_index = 0
        found = None
        previous_examined = backtrack
        for offset in range(1, 9):
            neighbor_index = (start_index + offset) % 8
            dx, dy = NEIGHBORS[neighbor_index]
            candidate = (current[0] + dx, current[1] + dy)
            if padded[candidate[1], candidate[0]]:
                found = candidate
                backtrack = previous_examined
                break
            previous_examined = candidate
        if found is None:
            break
        current = found
        if current == first and len(contour) > 2:
            break
        contour.append(current)
    if len(contour) < 3:
        return None
    return [(x - 1, y - 1) for x, y in contour]


def _point_segment_distance(point, start, end):
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def douglas_peucker(points, epsilon):
    if len(points) <= 2:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        maximum = -1.0
        index = -1
        for candidate in range(start + 1, end):
            distance = _point_segment_distance(points[candidate], points[start], points[end])
            if distance > maximum:
                maximum, index = distance, candidate
        if index >= 0 and maximum > epsilon:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [point for point, retained in zip(points, keep) if retained]


def polygon_area(points):
    return 0.5 * sum(
        points[i][0] * points[(i + 1) % len(points)][1]
        - points[(i + 1) % len(points)][0] * points[i][1]
        for i in range(len(points))
    )


def mask_to_polygon(mask, epsilon_factor=0.01, max_vertices=24):
    binary = np.asarray(mask, dtype=bool)
    ys, xs = np.nonzero(binary)
    if len(xs) == 0:
        return None, None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    width, height = x1 - x0 + 1, y1 - y0 + 1
    bbox = [x0, y0, width, height]
    rectangle = [[0, 0], [width, 0], [width, height], [0, height]]
    contour = trace_outer_contour(binary)
    if not contour or len(contour) < 3:
        return rectangle, bbox

    epsilon = max(2.0, epsilon_factor * max(width, height))
    closed = contour + [contour[0]]
    simplified = douglas_peucker(closed, epsilon)
    if simplified and simplified[-1] == simplified[0]:
        simplified = simplified[:-1]
    attempts = 0
    while len(simplified) > max_vertices and attempts < 6:
        epsilon *= 1.5
        simplified = douglas_peucker(closed, epsilon)
        if simplified and simplified[-1] == simplified[0]:
            simplified = simplified[:-1]
        attempts += 1

    deduped = []
    for point in simplified:
        if not deduped or math.dist(point, deduped[-1]) > epsilon:
            deduped.append(point)
    if len(deduped) > 1 and math.dist(deduped[-1], deduped[0]) <= epsilon:
        deduped.pop()
    local = [[int(x - x0), int(y - y0)] for x, y in deduped]
    if len(local) < 3 or abs(polygon_area(local)) < 1.0:
        return rectangle, bbox
    if polygon_area(local) < 0:
        local.reverse()
    return local[:max_vertices], bbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mask", type=Path)
    parser.add_argument("--epsilon-factor", type=float, default=0.01)
    parser.add_argument("--max-vertices", type=int, default=24)
    args = parser.parse_args()
    mask = np.asarray(Image.open(args.mask).convert("L")) > 127
    polygon, bbox = mask_to_polygon(mask, args.epsilon_factor, args.max_vertices)
    print(json.dumps({"bbox": bbox, "vertices": len(polygon or []), "polygon": polygon}))


if __name__ == "__main__":
    main()
