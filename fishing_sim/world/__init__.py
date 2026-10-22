"""Deterministic, performance-bounded world simulation foundations for v13.2."""
from .coordinates import (EquirectangularProjection, PHASE_A_PROJECTION, HIGH_SEAS_PROJECTION,
                          PHASE_A_BOUNDS_NM, PHASE_B_BOUNDS_NM, PHASE_B_BOUNDS, projected_bounds_nm)
from .traffic import (Activity, Archetype, AIShip, TrafficWorld, PHASE_A_COUNTS, PHASE_B_COUNTS,
                      PHASE_A_FLEET_TOTAL, PHASE_B_FLEET_TOTAL, SOURCE_FLEET_TOTAL)
from .weather_grid import WeatherGrid, WeatherCell, WeatherForecastPoint

__all__ = [
    "EquirectangularProjection", "PHASE_A_PROJECTION", "HIGH_SEAS_PROJECTION",
    "PHASE_A_BOUNDS_NM", "PHASE_B_BOUNDS_NM", "PHASE_B_BOUNDS", "projected_bounds_nm",
    "Activity", "Archetype", "AIShip", "TrafficWorld", "PHASE_A_COUNTS", "PHASE_B_COUNTS",
    "PHASE_A_FLEET_TOTAL", "PHASE_B_FLEET_TOTAL", "SOURCE_FLEET_TOTAL",
    "WeatherGrid", "WeatherCell", "WeatherForecastPoint",
]
