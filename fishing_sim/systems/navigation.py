"""Small, deterministic navigation-geometry helpers for line-based steering.

Coordinates use the simulation's world/design convention: +X is starboard/east
on a north-up chart and +Y is south.  No Pygame dependency is required.
"""
from __future__ import annotations

import math
from typing import Sequence


DESIGN_UNITS_PER_NAUTICAL_MILE = 185.2

def world_units_per_nautical_mile(world_scale: float = 1.0) -> float:
    """Return this game's world-coordinate units per nautical mile.

    Chart/design coordinates use 185.2 units per NM; world coordinates are those
    units multiplied by World.scale.  Do not use 1,852 here: that introduces a
    tenfold range/ETA error in ocean-space helm orders.
    """
    return DESIGN_UNITS_PER_NAUTICAL_MILE * max(1e-6, float(world_scale))


def xy(point) -> tuple[float, float]:
    """Accept a pair, vector-like object, or any object exposing x/y."""
    if hasattr(point, "x") and hasattr(point, "y"):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


def distance(a, b) -> float:
    ax, ay = xy(a)
    bx, by = xy(b)
    return math.hypot(bx - ax, by - ay)


def bearing_degrees(start, end) -> float:
    """Compass bearing from north, clockwise, in degrees (0..360)."""
    ax, ay = xy(start)
    bx, by = xy(end)
    dx, dy = bx - ax, by - ay
    if math.hypot(dx, dy) < 1e-12:
        return 0.0
    return math.degrees(math.atan2(dx, -dy)) % 360.0


def heading_radians(start, end) -> float:
    """Simulation heading: zero points +X and positive angles point +Y."""
    ax, ay = xy(start)
    bx, by = xy(end)
    return math.atan2(by - ay, bx - ax)


def along_track_distance(position, start, end) -> float:
    """Signed projection of position onto the start-to-end line, in coordinate units."""
    px, py = xy(position)
    ax, ay = xy(start)
    bx, by = xy(end)
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return 0.0
    return ((px - ax) * dx + (py - ay) * dy) / length


def cross_track_error(position, start, end) -> float:
    """Signed perpendicular offset from the leg; positive means right of track."""
    px, py = xy(position)
    ax, ay = xy(start)
    bx, by = xy(end)
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return distance(position, start)
    return (dx * (py - ay) - dy * (px - ax)) / length


def arrived(position, target, radius: float) -> bool:
    return distance(position, target) <= max(0.0, float(radius))


def eta_minutes(distance_units: float, speed_knots: float,
                 units_per_nautical_mile: float = 1852.0) -> float | None:
    """Estimated minutes for a distance expressed in chart/design units."""
    speed = max(0.0, float(speed_knots))
    units_per_nautical_mile = max(1e-9, float(units_per_nautical_mile))
    if speed < 0.05:
        return None
    nautical_miles = max(0.0, float(distance_units)) / units_per_nautical_mile
    return 60.0 * nautical_miles / speed


def leg_metrics(start, end, position=None, speed_knots: float = 0.0,
                units_per_nautical_mile: float = 1852.0) -> dict[str, float | None]:
    """Return readable leg data for HUDs, notebooks, and regression tests."""
    length = distance(start, end)
    along = along_track_distance(position, start, end) if position is not None else 0.0
    return {
        "bearing": bearing_degrees(start, end),
        "distance": length,
        "along_track": along,
        "cross_track": cross_track_error(position, start, end) if position is not None else 0.0,
        "progress": max(0.0, min(1.0, along / length)) if length > 1e-12 else 1.0,
        "eta_minutes": eta_minutes(length, speed_knots, units_per_nautical_mile),
    }
