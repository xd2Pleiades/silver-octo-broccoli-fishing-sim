"""Pure sizing and visibility rules for V13 fishing-cue rendering.

Kept free of Pygame so the important scale/threshold contracts can be tested
headlessly. Screen sizes intentionally preserve readable gull silhouettes at the
simulator's normal 0.6 zoom, where a sailor is about 24 px wide.
"""
from __future__ import annotations

import math


def clamp(value, low, high):
    return max(low, min(high, value))


def working_bird_count(strength):
    """Count grows with school strength; very weak schools no longer hold a flock."""
    strength = clamp(float(strength), 0.0, 1.0)
    if strength < 0.15:
        return 0
    return min(32, 6 + int(round(26 * strength)))


def _zoom_factor(zoom):
    # Keep clues readable at wide zoom, without making the gulls dominate close-ups.
    return clamp(math.sqrt(max(0.01, float(zoom)) / 0.6), 0.70, 1.65)


def working_bird_orbit_radius(strength, zoom=0.6):
    """Strong schools cluster tightly; fading schools spread out and disperse."""
    strength = clamp(float(strength), 0.0, 1.0)
    return clamp((34.0 + 72.0 * (1.0 - strength)) * _zoom_factor(zoom), 28.0, 150.0)


def working_bird_half_span(strength, zoom=0.6):
    """Half wing-span in screen pixels; at default zoom gulls are sailor-scale."""
    strength = clamp(float(strength), 0.0, 1.0)
    return clamp((10.0 + 7.0 * strength) * _zoom_factor(zoom), 8.0, 28.0)


def slick_visible(strength):
    """A smooth feeding slick drifts downwind of a school once it is reasonably active."""
    return float(strength) >= 0.25


def baitfish_fleck_count(strength):
    """Tiny silver flecks of nervous water; none from a school that is nearly gone."""
    strength = clamp(float(strength), 0.0, 1.0)
    return 0 if strength < 0.12 else int(6 + 22 * strength)


def boil_count(strength):
    """Fish-breaking-surface boils appear only over strong, feeding schools."""
    strength = clamp(float(strength), 0.0, 1.0)
    return 0 if strength < 0.35 else 1 + int(3 * strength)


def flotsam_visible(strength):
    return float(strength) >= 0.30


def ripples_visible(strength):
    return float(strength) >= 0.20


def lookout_detection_range(skill, visibility_km, daylight):
    """Distance in world units, capped at two ship-scale kilometres of design space."""
    skill = clamp(float(skill), 0.0, 1.0)
    visibility = clamp(float(visibility_km) / 10.0, 0.05, 1.0)
    night = 0.4 if float(daylight) < 0.3 else 1.0
    return min(2000.0, 2500.0 * skill) * visibility * night


def lookout_confidence_rate(skill):
    """A veteran reaches certainty materially sooner than a green deckhand.

    A capable lookout approaches full confidence over roughly twenty seconds;
    the half-confidence marker threshold is therefore earned, not instantaneous.
    """
    skill = clamp(float(skill), 0.0, 1.0)
    return (0.35 + 0.65 * skill) / 20.0


def follow_bird_count(phase, daylight, storm):
    """Phase codes mirror Longline: idle=0, setting=1, soaking=2, hauling=3."""
    if float(daylight) < 0.25 or float(storm) > 0.6:
        return 0
    return {1: 8, 2: 4, 3: 14}.get(int(phase), 0)


def screen_edge_intersection(width, height, target, margin=44):
    """Intersect a ray from screen centre to target with the safe inset rectangle."""
    width, height = max(1.0, float(width)), max(1.0, float(height))
    tx, ty = float(target[0]), float(target[1])
    cx, cy = width / 2.0, height / 2.0
    dx, dy = tx - cx, ty - cy
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return (cx, cy)
    half_w = max(1.0, cx - float(margin))
    half_h = max(1.0, cy - float(margin))
    candidates = []
    if abs(dx) > 1e-9:
        candidates.append(half_w / abs(dx))
    if abs(dy) > 1e-9:
        candidates.append(half_h / abs(dy))
    t = min(candidates) if candidates else 0.0
    return (cx + dx * t, cy + dy * t)
