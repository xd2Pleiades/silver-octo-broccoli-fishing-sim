"""Condition checks and measurement models for V13 navigation position fixes.

All distances in this module are chart/design units unless a caller explicitly
converts them. It never accesses or mutates the vessel's physical state.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Callable

LANDMARK_VISIBILITY_RANGE_PER_KM = 300.0
SEXTANT_WINDOWS = ((5.0, 7.0), (11.0, 13.0), (17.0, 19.0))
SEXTANT_MAX_CLOUD = 0.70
MIN_SEXTANT_SKILL = 0.40
MIN_RDF_SKILL = 0.40
RDF_MAX_RANGE_UNITS = 3200.0
SOUNDER_MATCH_TOLERANCE_M = 4.0
CHARTED_DEPTH_NOISE = (0.93, 1.07)


@dataclass(frozen=True)
class FixAssessment:
    available: bool
    reason: str
    accuracy_units: float = 0.0  # one-sigma positional accuracy in chart units


def assess_landmark_bearing(distance_units: float, visibility_km: float,
                            skill: float, sea_state: float,
                            observer_available: bool) -> FixAssessment:
    """Check a landmark bearing and estimate its positional uncertainty."""
    if not observer_available:
        return FixAssessment(False, "NEED DECK OBSERVER")
    visibility_range = max(0.0, float(visibility_km)) * LANDMARK_VISIBILITY_RANGE_PER_KM
    distance = max(0.0, float(distance_units))
    if distance > visibility_range:
        return FixAssessment(False, "NO LANDMARK IN SIGHT")
    skill = max(0.0, min(1.0, float(skill)))
    sea = max(0.0, min(1.0, float(sea_state)))
    bearing_sigma = 0.02 * (1.0 - skill) * (1.0 + sea)
    # In chart units: a stronger watchkeeper and calmer sea produce a tighter fix.
    accuracy = max(3.0, bearing_sigma * distance)
    return FixAssessment(True, "LANDMARK VISIBLE", accuracy)


def assess_sextant(hour: float, cloud: float, skill: float,
                   observer_available: bool) -> FixAssessment:
    """Sextant observation requires a useful sun window, clear sky, and skill."""
    hour = float(hour) % 24.0
    if not any(start < hour < end for start, end in SEXTANT_WINDOWS):
        return FixAssessment(False, "WAIT FOR DAWN / NOON / DUSK")
    if float(cloud) > SEXTANT_MAX_CLOUD:
        return FixAssessment(False, "SKY TOO OVERCAST")
    if not observer_available:
        return FixAssessment(False, "NEED DECK OBSERVER")
    skill = max(0.0, min(1.0, float(skill)))
    if skill < MIN_SEXTANT_SKILL:
        return FixAssessment(False, "OBSERVER SKILL BELOW 0.40")
    accuracy = max(12.0, 200.0 * (1.0 - skill) / 0.7)
    return FixAssessment(True, "SUN SIGHT AVAILABLE", accuracy)


def assess_rdf(distance_units: float, station_working: bool,
               operator_skill: float) -> FixAssessment:
    """Radio direction finding requires an attended set and a coastal signal."""
    if not station_working:
        return FixAssessment(False, "RADIO SET UNATTENDED")
    distance = max(0.0, float(distance_units))
    if distance > RDF_MAX_RANGE_UNITS:
        return FixAssessment(False, "COAST STATION OUT OF RANGE")
    skill = max(0.0, min(1.0, float(operator_skill)))
    if skill < MIN_RDF_SKILL:
        return FixAssessment(False, "RADIO OPERATOR SKILL BELOW 0.40")
    bearing_sigma = 0.05 * (1.0 - skill) * (1.0 + distance / RDF_MAX_RANGE_UNITS)
    accuracy = max(5.0, bearing_sigma * distance)
    return FixAssessment(True, "COAST STATION BEARING AVAILABLE", accuracy)


def charted_depth_at(x: float, y: float,
                     bottom_depth_m: Callable[[float], float]) -> float:
    """Stable old-survey depth in metres at the crew's believed chart position."""
    x, y = float(x), float(y)
    distance = math.hypot(x, y)
    seed = (int(x // 100) * 73856093) ^ (int(y // 100) * 19349663)
    rng = random.Random(seed)
    return max(0.0, float(bottom_depth_m(distance))) * rng.uniform(*CHARTED_DEPTH_NOISE)


def assess_echo_sounder(sounded_depth_m: float, charted_depth_m: float,
                        charted_water: bool,
                        tolerance_m: float = SOUNDER_MATCH_TOLERANCE_M) -> FixAssessment:
    """The echo sounder is a cross-check, not a correction when readings disagree."""
    if not charted_water:
        return FixAssessment(False, "OUTSIDE CHARTED SOUNDINGS")
    if abs(float(sounded_depth_m) - float(charted_depth_m)) > max(0.0, float(tolerance_m)):
        return FixAssessment(False, "SOUNDING MISMATCH", abs(float(sounded_depth_m) - float(charted_depth_m)))
    return FixAssessment(True, "SOUNDING MATCH", 0.0)


def sample_position_error(sigma_units: float, rng=random) -> tuple[float, float]:
    """Sample an isotropic two-axis fix error using the supplied random generator."""
    sigma = max(0.0, float(sigma_units))
    return rng.gauss(0.0, sigma), rng.gauss(0.0, sigma)


def sample_rdf_error(sigma_units: float, bearing_to_station: float,
                     rng=random) -> tuple[float, float, float]:
    """Sample RDF error elongated along the station bearing line.

    Returns (dx, dy, uncertainty_radius), all in chart units. Distance along the
    line is less certain than cross-track position, mimicking a single bearing.
    """
    sigma = max(0.0, float(sigma_units))
    along_sigma = max(6.0, sigma * 3.0)
    across_sigma = max(2.0, sigma * 0.3)
    along = rng.gauss(0.0, along_sigma)
    across = rng.gauss(0.0, across_sigma)
    angle = float(bearing_to_station)
    dx = along * math.cos(angle + math.pi / 2.0) + across * math.cos(angle)
    dy = along * math.sin(angle + math.pi / 2.0) + across * math.sin(angle)
    return dx, dy, along_sigma
