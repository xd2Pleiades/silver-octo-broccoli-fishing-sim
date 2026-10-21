"""Small, deterministic 2-D collision helpers for surface fishing/rescue gear.

The helpers deliberately operate on ordinary ``(x, y)`` tuples, so geometry can
be tested headlessly without importing Pygame. Coordinates are world units.
"""
from __future__ import annotations

import math

_EPS = 1e-8


def _xy(p):
    if hasattr(p, "x") and hasattr(p, "y"):
        return float(p.x), float(p.y)
    return float(p[0]), float(p[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _mul(a, k):
    return (a[0] * k, a[1] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _length(a):
    return math.hypot(a[0], a[1])


def _closest_on_segment_xy(p, a, b):
    """Allocation-free closest point for already-normalized coordinate pairs."""
    px, py = p
    ax, ay = a
    bx, by = b
    abx, aby = bx - ax, by - ay
    denom = abx * abx + aby * aby
    if denom <= _EPS:
        return ax, ay
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / denom))
    return ax + abx * t, ay + aby * t


def closest_on_segment(point, start, end):
    """Return the closest point to ``point`` on segment ``start``—``end``."""
    return _closest_on_segment_xy(_xy(point), _xy(start), _xy(end))


def _vertices_xy(polygon):
    """Reuse pre-normalized immutable coordinate tuples where possible."""
    if isinstance(polygon, tuple) and all(
        isinstance(v, tuple) and len(v) == 2 and
        isinstance(v[0], (int, float)) and isinstance(v[1], (int, float))
        for v in polygon
    ):
        return polygon
    return tuple(_xy(v) for v in polygon)


def _point_in_polygon_xy(x, y, vertices):
    if len(vertices) < 3:
        return False
    inside = False
    xj, yj = vertices[-1]
    for xi, yi in vertices:
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / ((yj - yi) or _EPS) + xi
            if x < x_cross:
                inside = not inside
        xj, yj = xi, yi
    return inside


def point_in_polygon(point, polygon):
    """Ray-cast point-in-polygon test for simple polygons."""
    x, y = _xy(point)
    return _point_in_polygon_xy(x, y, _vertices_xy(polygon))


def resolve_circle_segment(point, radius, start, end):
    """Push a circle centre out of a segment capsule; return ``(point, hit)``."""
    p, a, b = _xy(point), _xy(start), _xy(end)
    radius = max(0.0, float(radius))
    c = _closest_on_segment_xy(p, a, b)
    dx, dy = p[0] - c[0], p[1] - c[1]
    distance_sq = dx * dx + dy * dy
    if distance_sq >= radius * radius or radius <= 0.0:
        return p, False
    distance = math.sqrt(distance_sq)
    if distance > _EPS:
        normal = (dx / distance, dy / distance)
    else:
        ex, ey = b[0] - a[0], b[1] - a[1]
        edge_len = math.hypot(ex, ey)
        normal = (-ey / edge_len, ex / edge_len) if edge_len > _EPS else (0.0, 1.0)
    return (c[0] + normal[0] * (radius + 0.01),
            c[1] + normal[1] * (radius + 0.01)), True


def resolve_circle_polygon(point, radius, polygon):
    """Push a circle centre outside a polygon by at least ``radius``.

    Immutable tuple polygons can be cached by callers, avoiding a point/tuple
    allocation for every rope point in every physics constraint pass.
    """
    p = _xy(point)
    vertices = _vertices_xy(polygon)
    radius = max(0.0, float(radius))
    if len(vertices) < 3 or radius <= 0.0:
        return p, False
    inside = _point_in_polygon_xy(p[0], p[1], vertices)
    best_c, best_edge, best_d_sq = None, None, float("inf")
    for i, a in enumerate(vertices):
        b = vertices[(i + 1) % len(vertices)]
        c = _closest_on_segment_xy(p, a, b)
        dx, dy = p[0] - c[0], p[1] - c[1]
        d_sq = dx * dx + dy * dy
        if d_sq < best_d_sq:
            best_c, best_edge, best_d_sq = c, (a, b), d_sq
    if not inside and best_d_sq >= radius * radius:
        return p, False

    dx, dy = p[0] - best_c[0], p[1] - best_c[1]
    distance = math.sqrt(dx * dx + dy * dy)
    if not inside and distance > _EPS:
        normal = (dx / distance, dy / distance)
    else:
        ex, ey = best_edge[1][0] - best_edge[0][0], best_edge[1][1] - best_edge[0][1]
        edge_len = math.hypot(ex, ey)
        normal = (-ey / max(edge_len, _EPS), ex / max(edge_len, _EPS))
        probe = (best_c[0] + normal[0] * 0.1, best_c[1] + normal[1] * 0.1)
        if _point_in_polygon_xy(probe[0], probe[1], vertices):
            normal = (-normal[0], -normal[1])
    resolved = (best_c[0] + normal[0] * (radius + 0.01),
                best_c[1] + normal[1] * (radius + 0.01))
    # Degenerate/concave corners can make the nearest-edge normal ambiguous.
    if _point_in_polygon_xy(resolved[0], resolved[1], vertices):
        normal = (-normal[0], -normal[1])
        resolved = (best_c[0] + normal[0] * (radius + 0.01),
                    best_c[1] + normal[1] * (radius + 0.01))
    return resolved, True


def segment_intersects_rect(start, end, rect, step=18.0):
    """Return true when a segment crosses the *interior* of (xmin,xmax,ymin,ymax)."""
    ax, ay = _xy(start)
    bx, by = _xy(end)
    xmin, xmax, ymin, ymax = (float(v) for v in rect)
    distance = math.hypot(bx - ax, by - ay)
    n = max(2, int(math.ceil(distance / max(1.0, float(step)))))
    for i in range(1, n):
        t = i / n
        x, y = ax + (bx - ax) * t, ay + (by - ay) * t
        if xmin + 1e-4 < x < xmax - 1e-4 and ymin + 1e-4 < y < ymax - 1e-4:
            return True
    return False


def route_around_rect(start, target, rect):
    """Return local-space waypoints avoiding a rectangular ship-hull envelope.

    The returned route excludes ``start`` and includes ``target``. When the
    direct leg is clear, only the target is returned. Otherwise it compares
    paths that pass around the bow or stern, staying outside the expanded hull.
    """
    a, b = _xy(start), _xy(target)
    xmin, xmax, ymin, ymax = (float(v) for v in rect)
    if not segment_intersects_rect(a, b, (xmin, xmax, ymin, ymax)):
        return [b]
    start_side = ymin if a[1] <= (ymin + ymax) * 0.5 else ymax
    target_side = ymin if b[1] <= (ymin + ymax) * 0.5 else ymax
    candidates = []
    for edge_x in (xmin, xmax):
        route = [(edge_x, start_side), (edge_x, target_side), b]
        points = [a] + route
        # Discard any route segment that cuts back into the hull envelope.
        if any(segment_intersects_rect(p0, p1, (xmin, xmax, ymin, ymax))
               for p0, p1 in zip(points, points[1:])):
            continue
        length = sum(_length(_sub(p1, p0)) for p0, p1 in zip(points, points[1:]))
        candidates.append((length, route))
    if candidates:
        return min(candidates, key=lambda item: item[0])[1]
    # Fallback for a start exactly at an obstacle edge: route around the nearest
    # end first and retain a final target leg for the normal collision resolver.
    edge_x = xmin if abs(a[0] - xmin) < abs(a[0] - xmax) else xmax
    return [(edge_x, start_side), (edge_x, target_side), b]
