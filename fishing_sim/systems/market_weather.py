"""Short-lived auction-market response to storm-related landing disruption."""
from __future__ import annotations
import math

BASE_MIN = 0.70
BASE_MAX = 1.30
EFFECTIVE_MAX = 1.85
SURGE_CAP = 0.65
STORM_SURGE_BASE = 0.22
STORM_SURGE_WIND = 0.12
SURGE_DECAY_DAYS = 2.5


def clamp(value, low, high):
    return max(low, min(high, float(value)))


def storm_price_index(base_index: float, surge: float) -> float:
    """Return the sale-price index after temporary storm scarcity premium."""
    return clamp(float(base_index) + clamp(surge, 0.0, SURGE_CAP), BASE_MIN, EFFECTIVE_MAX)


def add_storm_surge(current_surge: float, wind_strength: float) -> float:
    """A new storm adds a bounded scarcity premium, scaled by wind severity."""
    increment = STORM_SURGE_BASE + STORM_SURGE_WIND * clamp(wind_strength, 0.0, 1.0)
    return min(SURGE_CAP, max(0.0, float(current_surge)) + increment)


def decay_storm_surge(current_surge: float, dt: float, day_length: float = 600.0) -> float:
    """Exponentially recover the price premium over roughly a few game days."""
    surge = max(0.0, float(current_surge))
    dt = max(0.0, float(dt))
    day_length = max(1e-6, float(day_length))
    if surge <= 0.0 or dt <= 0.0:
        return surge
    remaining = surge * math.exp(-dt / (day_length * SURGE_DECAY_DAYS))
    return 0.0 if remaining < 0.005 else remaining
