"""Deterministic, performance-bounded world simulation foundations for v13.2."""
from .coordinates import EquirectangularProjection, PHASE_A_PROJECTION
from .traffic import Activity, Archetype, AIShip, TrafficWorld
from .weather_grid import WeatherGrid, WeatherCell, WeatherForecastPoint

__all__ = [
    "EquirectangularProjection", "PHASE_A_PROJECTION",
    "Activity", "Archetype", "AIShip", "TrafficWorld",
    "WeatherGrid", "WeatherCell", "WeatherForecastPoint",
]
