"""Skill-weighted crew observations for V13V1-10.

These functions report noisy observations; they never change simulation state.
Coordinates are world-space points. Distances are returned in nautical miles,
using the chart's established 185.2 design-units-per-nautical-mile convention.
"""
from __future__ import annotations

import math
import random
from typing import Any, Tuple

BEARING_SIGMA_RAD_AT_ZERO_SKILL = 0.02
DISTANCE_SIGMA_FRACTION_AT_ZERO_SKILL = 0.10
SPEED_SIGMA_KNOTS_AT_ZERO_SKILL = 0.20
WORLD_SPEED_UNITS_PER_KNOT = 50.0
DESIGN_UNITS_PER_NAUTICAL_MILE = 185.2
SECOND_OPINION_WINDOW_SECONDS = 5.0


def _xy(point: Any) -> Tuple[float, float]:
    """Read a pygame.Vector2-like point or a simple (x, y) pair."""
    if hasattr(point, "x") and hasattr(point, "y"):
        return float(point.x), float(point.y)
    x, y = point
    return float(x), float(y)


def _skill(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def report_bearing(observer: Any, target: Any, skill: float,
                   rng: Any = random) -> float:
    """Return a noisy compass bearing in radians (0 north, clockwise).

    The error is a zero-mean Gaussian with the plan's 0.02*(1-skill) radian
    standard deviation. Passing a seeded random.Random makes tests repeatable.
    """
    ox, oy = _xy(observer)
    tx, ty = _xy(target)
    true_bearing = math.atan2(tx - ox, oy - ty)
    error = rng.gauss(0.0, BEARING_SIGMA_RAD_AT_ZERO_SKILL * (1.0 - _skill(skill)))
    return (true_bearing + error) % math.tau


def report_distance(observer: Any, target: Any, scale: float, skill: float,
                    rng: Any = random) -> float:
    """Return a noisy range in nautical miles, never a negative distance."""
    ox, oy = _xy(observer)
    tx, ty = _xy(target)
    world_scale = max(1e-9, abs(float(scale)))
    true_nm = math.hypot(tx - ox, ty - oy) / world_scale / DESIGN_UNITS_PER_NAUTICAL_MILE
    error_sigma = DISTANCE_SIGMA_FRACTION_AT_ZERO_SKILL * (1.0 - _skill(skill)) * true_nm
    return max(0.0, true_nm + rng.gauss(0.0, error_sigma))


def report_speed(speed_world_units_per_second: float, skill: float,
                 rng: Any = random) -> float:
    """Return a noisy speed-log estimate in knots, never a negative speed."""
    true_knots = max(0.0, float(speed_world_units_per_second)) / WORLD_SPEED_UNITS_PER_KNOT
    error_sigma = SPEED_SIGMA_KNOTS_AT_ZERO_SKILL * (1.0 - _skill(skill))
    return max(0.0, true_knots + rng.gauss(0.0, error_sigma))


def bearing_difference_degrees(a: float, b: float) -> float:
    """Smallest unsigned separation between two bearings in degrees."""
    return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)
