"""Headless model for temporary offshore fishing concentrations (V13V1-01).

This module deliberately has no Pygame dependency. Simulation code can use the
same world-space positions as hook points, while lifecycle and bite modifiers
remain directly testable without opening a window.
"""
from __future__ import annotations

import math


HOTSPOT_SPECIES = ("albacore", "yellowfin", "bigeye", "swordfish", "mixed")
MAX_ACTIVE_HOTSPOTS = 4
MAX_SPECIFIC_MULTIPLIER = 2.5
MIXED_MULTIPLIER = 1.6
AUTO_HUNT_MIN_CONFIDENCE = 0.70
AUTO_HUNT_MIN_STRENGTH = 0.40


def _xy(point):
    """Accept a Pygame Vector2, an (x, y) tuple, or any x/y-like object."""
    if hasattr(point, "x") and hasattr(point, "y"):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


class Hotspot:
    """A temporary school concentration at an absolute world-space position."""

    def __init__(self, x, y, species, strength=1.0, radius=1800.0, life=600.0,
                 drift_x=0.0, drift_y=0.0, phase=0.0):
        if species not in HOTSPOT_SPECIES:
            raise ValueError("unsupported hotspot species: %s" % species)
        self.x = float(x)
        self.y = float(y)
        self.species = species
        self.strength = max(0.0, min(1.0, float(strength)))
        self.strength_now = self.strength
        self.radius = max(1.0, float(radius))
        self.life = max(0.01, float(life))
        self.age = 0.0
        self.drift_x = float(drift_x)
        self.drift_y = float(drift_y)
        self.phase = float(phase)
        # The lookout records the first confident observer and game-time stamp.
        self.detected_by = None
        self.detected_at = None

    @property
    def pos(self):
        """Return a plain coordinate tuple so this model stays Pygame-free."""
        return (self.x, self.y)

    @property
    def drift(self):
        return (self.drift_x, self.drift_y)

    def update(self, dt, is_water=None):
        """Advance lifecycle and drift; return False when the spot has expired.

        If drift would put the concentration on land/shallow water, it remains
        in its current water position and reverses drift instead of crossing the
        coastline. `is_water(x, y)` may be supplied by the world simulation.
        """
        dt = max(0.0, float(dt))
        self.age += dt
        if self.age >= self.life:
            self.strength_now = 0.0
            return False

        fade_start = self.life * (2.0 / 3.0)
        if self.age <= fade_start:
            self.strength_now = self.strength
        else:
            fade_span = max(1e-9, self.life - fade_start)
            remaining = max(0.0, 1.0 - (self.age - fade_start) / fade_span)
            self.strength_now = self.strength * remaining

        nx = self.x + self.drift_x * dt
        ny = self.y + self.drift_y * dt
        if is_water is None or is_water(nx, ny):
            self.x, self.y = nx, ny
        else:
            self.drift_x *= -1.0
            self.drift_y *= -1.0
        return True


def find_spawn_position(rng, scale, is_water, harbour=(0.0, 0.0),
                        min_distance=4000.0, max_distance=9000.0, attempts=8):
    """Pick offshore world coordinates, rejecting land/shallow-water candidates.

    Distances are expressed in the game's design units and multiplied by its
    world scale, matching the existing harbour/depth model. `is_water` must
    perform the world's actual polygon, reef, coast and depth checks.
    """
    scale = max(0.001, float(scale))
    hx, hy = _xy(harbour)
    for _ in range(max(0, int(attempts))):
        angle = rng.uniform(0.0, math.tau)
        distance = rng.uniform(float(min_distance), float(max_distance)) * scale
        x = hx + math.cos(angle) * distance
        y = hy + math.sin(angle) * distance
        if is_water(x, y):
            return (x, y)
    return None


def select_detected_hotspot(sailors, hotspots,
                            min_confidence=AUTO_HUNT_MIN_CONFIDENCE,
                            min_strength=AUTO_HUNT_MIN_STRENGTH):
    """Choose the best live school the crew are sufficiently confident about.

    The caller is responsible for filtering to crew currently eligible for lookout
    duty. Identity checks are deliberate: an expired Hotspot object must never be
    treated as live just because a sailor still holds a stale reference to it.
    """
    live = {id(spot): spot for spot in hotspots}
    best = None
    best_score = None
    for sailor in sailors:
        spot = getattr(sailor, "gut_spot", None)
        if spot is None or id(spot) not in live:
            continue
        confidence = max(0.0, min(1.0, float(getattr(sailor, "gut_confidence", 0.0))))
        strength = max(0.0, min(1.0, float(getattr(spot, "strength_now", 0.0))))
        if confidence <= float(min_confidence) or strength <= float(min_strength):
            continue
        score = (confidence * strength, confidence, strength)
        if best_score is None or score > best_score:
            best, best_score = spot, score
    return best


def estimated_hotspot_destination(spot_position, position_error):
    """Plot the school using the crew's position estimate, not hidden truth.

    `position_error` is believed position minus physical position. Applying the
    same offset to a detected school's true world coordinate models the crew's
    dead-reckoning plot: poor navigation can steer the ship beside productive
    water rather than directly into it.
    """
    sx, sy = _xy(spot_position)
    ex, ey = _xy(position_error)
    return (sx + ex, sy + ey)


def hotspot_multiplier(hotspots, position, species):
    """Return the strongest local modifier for a species (never stack spots).

    A matching-species school peaks at 2.5x. A mixed school peaks at 1.6x.
    The smooth quadratic falloff reaches exactly 1.0 at/outside the radius.
    The caller multiplies this by the existing ecology/bait weight, so a spot
    never replaces those rules or adds a separate chance of catching fish.
    """
    px, py = _xy(position)
    best = 1.0
    for spot in hotspots:
        if spot.strength_now <= 0.0 or spot.radius <= 0.0:
            continue
        dx, dy = px - spot.x, py - spot.y
        distance = math.hypot(dx, dy)
        if distance >= spot.radius:
            continue
        falloff = max(0.0, 1.0 - (distance / spot.radius) ** 2)
        if spot.species == species:
            multiplier = 1.0 + (MAX_SPECIFIC_MULTIPLIER - 1.0) * spot.strength_now * falloff
        elif spot.species == "mixed":
            multiplier = 1.0 + (MIXED_MULTIPLIER - 1.0) * spot.strength_now * falloff
        else:
            continue
        best = max(best, min(MAX_SPECIFIC_MULTIPLIER, multiplier))
    return best
