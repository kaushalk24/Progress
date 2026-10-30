"""Small, dependency-free planar geometry helpers (drawing units = US feet)."""
from __future__ import annotations

import math

Point = tuple[float, float]


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def polyline_length(pts: list[Point], closed: bool = False) -> float:
    total = sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if closed and len(pts) > 2:
        total += dist(pts[-1], pts[0])
    return total


def bbox(pts: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def area(poly: list[Point]) -> float:
    n = len(poly)
    return abs(sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))) / 2.0


def point_in_polygon(pt: Point, poly: list[Point]) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return dist(p, (ax + t * dx, ay + t * dy))


def point_polyline_distance(p: Point, pts: list[Point], closed: bool = False) -> float:
    if len(pts) == 1:
        return dist(p, pts[0])
    best = min(point_segment_distance(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if closed and len(pts) > 2:
        best = min(best, point_segment_distance(p, pts[-1], pts[0]))
    return best


class Region:
    """A polygon with a cached bounding box for fast containment tests."""

    __slots__ = ("name", "handle", "poly", "bb")

    def __init__(self, name: str, handle: str, poly: list[Point]):
        self.name = name
        self.handle = handle
        self.poly = poly
        self.bb = bbox(poly)

    def contains(self, p: Point) -> bool:
        x0, y0, x1, y1 = self.bb
        if p[0] < x0 or p[0] > x1 or p[1] < y0 or p[1] > y1:
            return False
        return point_in_polygon(p, self.poly)

    def distance(self, p: Point) -> float:
        if self.contains(p):
            return 0.0
        return point_polyline_distance(p, self.poly, closed=True)


def length_inside(pts: list[Point], regions: list[Region], step: float = 5.0) -> float:
    """Length of a polyline lying inside the union of regions (sampled every `step` ft)."""
    inside = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = dist(a, b)
        if seg == 0:
            continue
        n = max(1, int(math.ceil(seg / step)))
        piece = seg / n
        for k in range(n):
            t = (k + 0.5) / n
            m = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            if any(r.contains(m) for r in regions):
                inside += piece
    return inside
