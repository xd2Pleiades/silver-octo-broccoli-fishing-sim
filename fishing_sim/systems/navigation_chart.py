"""Pure geometry and deterministic cartography helpers for the V13 chart UI.

This module deliberately has no Pygame dependency so chart geometry can be tested
headlessly. Coordinates are in the simulation's design units (world pixels divided
by World.scale), with positive Y pointing south/down to match the simulation camera and screen coordinates.
"""
from __future__ import annotations

import math
import random
from typing import Callable, Sequence

# A harbour-centred sheet which includes the town, the mapped coastal radius, and
# the current game's normal fishing-ground area. Everything outside the survey
# radius remains visibly marked as uncharted rather than being implied as surveyed.
# The original sheet ended before many real offshore schools spawned by the world.
# This wider coastal sheet gives the player room to navigate roughly 100+ nm while
# keeping only the central 6,000-unit radius marked as surveyed.
CHART_BOUNDS = (-12000.0, -10000.0, 12000.0, 10000.0)
KNOWN_AREA_RADIUS = 6000.0
SOUNDING_SPACING = 500
METRES_PER_FATHOM = 1.8288

CHART_PALETTE = {
    "paper": (216, 203, 168),
    "water": (184, 200, 192),
    "water_inner": (177, 197, 190),
    "water_harbour": (164, 190, 184),
    "land": (200, 184, 144),
    "coast": (74, 48, 32),
    "landmark": (122, 48, 32),
    "sounding": (106, 96, 80),
    "grid": (160, 172, 157),
    "uncharted": (129, 139, 130),
    "danger": (138, 59, 47),
    "ship": (242, 208, 75),
    "course": (138, 59, 47),
    "fix": (61, 106, 138),
    "gold": (201, 162, 39),
    "ink": (74, 48, 32),
}


def chart_transform(width: int, height: int,
                    bounds: tuple[float, float, float, float] = CHART_BOUNDS,
                    margin: int = 12) -> tuple[float, float, float]:
    """Return (scale, offset_x, offset_y) to fit design-unit chart coordinates."""
    width = max(1, int(width))
    height = max(1, int(height))
    xmin, ymin, xmax, ymax = bounds
    span_x = max(1.0, xmax - xmin)
    span_y = max(1.0, ymax - ymin)
    k = min(max(0.0, width - 2 * margin) / span_x,
            max(0.0, height - 2 * margin) / span_y)
    ox = (width - span_x * k) * 0.5 - xmin * k
    oy = (height - span_y * k) * 0.5 - ymin * k
    return k, ox, oy


def chart_to_pixel(x: float, y: float,
                   transform: tuple[float, float, float]) -> tuple[int, int]:
    """Convert a chart coordinate to rounded local surface pixels."""
    k, ox, oy = transform
    return int(round(ox + float(x) * k)), int(round(oy + float(y) * k))


def within_chart_bounds(x: float, y: float,
                        bounds: tuple[float, float, float, float] = CHART_BOUNDS) -> bool:
    xmin, ymin, xmax, ymax = bounds
    return xmin <= x <= xmax and ymin <= y <= ymax


def clamp_to_chart_bounds(x: float, y: float,
                          bounds: tuple[float, float, float, float] = CHART_BOUNDS,
                          inset: float = 0.0) -> tuple[float, float]:
    xmin, ymin, xmax, ymax = bounds
    return (min(xmax - inset, max(xmin + inset, float(x))),
            min(ymax - inset, max(ymin + inset, float(y))))


def clip_segment_to_bounds(start: Sequence[float], end: Sequence[float],
                           bounds: tuple[float, float, float, float] = CHART_BOUNDS
                           ) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Clip a segment to the chart rectangle with Liang–Barsky clipping."""
    x0, y0 = float(start[0]), float(start[1])
    x1, y1 = float(end[0]), float(end[1])
    xmin, ymin, xmax, ymax = bounds
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - xmin), (dx, xmax - x0),
                 (-dy, y0 - ymin), (dy, ymax - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    return ((x0 + t0 * dx, y0 + t0 * dy),
            (x0 + t1 * dx, y0 + t1 * dy))


def charted_depth_fathoms(x: float, y: float,
                          bottom_depth_m: Callable[[float], float]) -> int:
    """Return a stable, hand-survey-like sounding at a design-unit coordinate.

    Depth uses the game's existing harbour-distance seabed model and a deterministic
    +/-7% survey variation, so values never flicker or change between chart redraws.
    """
    distance = math.hypot(float(x), float(y))
    seed_x = int(float(x) // 100)
    seed_y = int(float(y) // 100)
    seed = (seed_x * 73856093) ^ (seed_y * 19349663)
    rng = random.Random(seed)
    depth_m = max(0.0, float(bottom_depth_m(distance))) * rng.uniform(0.93, 1.07)
    return max(1, int(round(depth_m / METRES_PER_FATHOM)))


def generate_soundings(is_land: Callable[[float, float], bool],
                       bottom_depth_m: Callable[[float], float],
                       radius: float = KNOWN_AREA_RADIUS,
                       spacing: int = SOUNDING_SPACING
                       ) -> list[tuple[float, float, int]]:
    """Build deterministic soundings inside the surveyed radius, excluding land."""
    radius = max(0.0, float(radius))
    spacing = max(1, int(spacing))
    edge = int(radius // spacing) * spacing
    out: list[tuple[float, float, int]] = []
    for y in range(-edge, edge + 1, spacing):
        for x in range(-edge, edge + 1, spacing):
            if math.hypot(x, y) > radius:
                continue
            if is_land(float(x), float(y)):
                continue
            out.append((float(x), float(y), charted_depth_fathoms(x, y, bottom_depth_m)))
    return out

# --- v13v1-06: editable course geometry -------------------------------------
MAX_CHART_WAYPOINTS = 8
MIN_WAYPOINT_SEPARATION = 35.0


def pixel_to_chart(px: float, py: float,
                   transform: tuple[float, float, float]) -> tuple[float, float]:
    """Inverse of chart_to_pixel, preserving design-unit coordinates on resize."""
    k, ox, oy = transform
    if abs(k) < 1e-12:
        return 0.0, 0.0
    return (float(px) - ox) / k, (float(py) - oy) / k


def point_segment_distance(point: Sequence[float], start: Sequence[float],
                           end: Sequence[float]) -> tuple[float, tuple[float, float]]:
    """Distance from a point to a segment and the closest point on it."""
    px, py = float(point[0]), float(point[1])
    ax, ay = float(start[0]), float(start[1])
    bx, by = float(end[0]), float(end[1])
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        closest = (ax, ay)
    else:
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
        closest = (ax + t * dx, ay + t * dy)
    return math.hypot(px - closest[0], py - closest[1]), closest


class WaypointRoute:
    """Small, testable route editor in chart design coordinates (not pixels/world px).

    Points survive window resizing because the saved values are chart coordinates. The
    editor rejects duplicate/near-zero legs and never accepts points outside the sheet.
    """
    def __init__(self, points: Sequence[Sequence[float]] | None = None,
                 max_points: int = MAX_CHART_WAYPOINTS,
                 min_separation: float = MIN_WAYPOINT_SEPARATION):
        self.max_points = max(1, int(max_points))
        self.min_separation = max(0.0, float(min_separation))
        self.points: list[tuple[float, float]] = []
        for value in points or ():
            if len(self.points) >= self.max_points:
                break
            p = (float(value[0]), float(value[1]))
            if within_chart_bounds(*p) and all(math.dist(p, q) >= self.min_separation for q in self.points):
                self.points.append(p)

    def clear(self) -> None:
        self.points.clear()

    def _valid(self, point: Sequence[float]) -> tuple[float, float] | None:
        if len(point) < 2:
            return None
        p = (float(point[0]), float(point[1]))
        if not all(math.isfinite(v) for v in p) or not within_chart_bounds(*p):
            return None
        return p

    def add(self, point: Sequence[float], start: Sequence[float] | None = None) -> bool:
        if len(self.points) >= self.max_points:
            return False
        p = self._valid(point)
        if p is None or any(math.dist(p, q) < self.min_separation for q in self.points):
            return False
        if not self.points and start is not None and math.dist(p, start) < self.min_separation:
            return False
        self.points.append(p)
        return True

    def insert(self, index: int, point: Sequence[float],
               start: Sequence[float] | None = None) -> bool:
        if len(self.points) >= self.max_points or not 0 <= int(index) <= len(self.points):
            return False
        p = self._valid(point)
        if p is None or any(math.dist(p, q) < self.min_separation for q in self.points):
            return False
        i = int(index)
        previous = self.points[i - 1] if i > 0 else start
        following = self.points[i] if i < len(self.points) else None
        if previous is not None and math.dist(p, previous) < self.min_separation:
            return False
        if following is not None and math.dist(p, following) < self.min_separation:
            return False
        self.points.insert(i, p)
        return True

    def move(self, index: int, point: Sequence[float],
             start: Sequence[float] | None = None) -> bool:
        if not 0 <= int(index) < len(self.points):
            return False
        p = self._valid(point)
        if p is None:
            return False
        i = int(index)
        if any(j != i and math.dist(p, q) < self.min_separation
               for j, q in enumerate(self.points)):
            return False
        previous = self.points[i - 1] if i > 0 else start
        following = self.points[i + 1] if i + 1 < len(self.points) else None
        if previous is not None and math.dist(p, previous) < self.min_separation:
            return False
        if following is not None and math.dist(p, following) < self.min_separation:
            return False
        self.points[i] = p
        return True

    def delete(self, index: int) -> bool:
        if not 0 <= int(index) < len(self.points):
            return False
        del self.points[int(index)]
        return True

    def nearest_waypoint(self, point: Sequence[float], tolerance: float) -> int | None:
        if not self.points:
            return None
        distances = [math.dist(point, p) for p in self.points]
        i = min(range(len(distances)), key=distances.__getitem__)
        return i if distances[i] <= max(0.0, float(tolerance)) else None

    def nearest_leg(self, point: Sequence[float], start: Sequence[float],
                    tolerance: float) -> tuple[int, float, tuple[float, float]] | None:
        """Return (insertion index, distance, projection) for the nearest route leg.

        Index zero denotes the current estimated ship position -> waypoint one; index
        one denotes waypoint one -> waypoint two, and so on.
        """
        if not self.points:
            return None
        path = [(float(start[0]), float(start[1]))] + self.points
        best = None
        for seg_i, (a, b) in enumerate(zip(path, path[1:])):
            if math.dist(a, b) < self.min_separation:
                continue
            distance, projection = point_segment_distance(point, a, b)
            if best is None or distance < best[1]:
                best = (seg_i, distance, projection)
        if best is None or best[1] > max(0.0, float(tolerance)):
            return None
        return best
