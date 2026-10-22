"""Gameplay-grade equirectangular coordinates for regional and high-seas maps.

World positions are nautical miles (NM), x east and y north. This is deliberately
not navigational-grade geodesy; all longitude deltas are wrapped over the date line.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

NM_PER_DEGREE_LAT = 60.0
PHASE_A_BOUNDS = {"west_lon": 138.0, "east_lon": 148.0, "south_lat": 40.0, "north_lat": 46.0}
PHASE_A_PROJECTION_CENTER = (140.7, 41.8)  # Hakodate, for legacy chart integration
HIGH_SEAS_PROJECTION_CENTER = (160.0, 45.0)  # Source Plan 13.2.xx global reference


def wrap_longitude_delta(delta_deg: float) -> float:
    """Wrap a longitude difference into [-180, 180), including date-line crossings."""
    return (float(delta_deg) + 180.0) % 360.0 - 180.0


@dataclass(frozen=True)
class EquirectangularProjection:
    center_lon_deg: float = PHASE_A_PROJECTION_CENTER[0]
    center_lat_deg: float = PHASE_A_PROJECTION_CENTER[1]

    def __post_init__(self) -> None:
        if not math.isfinite(self.center_lon_deg) or not math.isfinite(self.center_lat_deg):
            raise ValueError("projection centre must be finite")
        if not -90.0 < float(self.center_lat_deg) < 90.0:
            raise ValueError("projection latitude must be strictly between the poles")

    @property
    def cos_lat(self) -> float:
        return math.cos(math.radians(self.center_lat_deg))

    def to_nm(self, lon_deg: float, lat_deg: float) -> tuple[float, float]:
        """Project lon/lat to local (east_nm, north_nm) with wrapped longitude."""
        lon, lat = float(lon_deg), float(lat_deg)
        if not math.isfinite(lon) or not math.isfinite(lat) or not -90.0 <= lat <= 90.0:
            raise ValueError("invalid geographic coordinate")
        dx = wrap_longitude_delta(lon - self.center_lon_deg) * NM_PER_DEGREE_LAT * self.cos_lat
        dy = (lat - self.center_lat_deg) * NM_PER_DEGREE_LAT
        return dx, dy

    def to_lonlat(self, x_nm: float, y_nm: float) -> tuple[float, float]:
        """Invert local NM coordinates; longitude is normalized to [-180, 180)."""
        x, y = float(x_nm), float(y_nm)
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("world coordinate must be finite")
        lon = self.center_lon_deg + x / (NM_PER_DEGREE_LAT * max(1e-12, self.cos_lat))
        lon = (lon + 180.0) % 360.0 - 180.0
        lat = self.center_lat_deg + y / NM_PER_DEGREE_LAT
        if not -90.0 <= lat <= 90.0:
            raise ValueError("inverse projection reaches beyond the poles")
        return lon, lat


def distance_nm(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def bearing_degrees(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Bearing clockwise from north, suitable for display on a nautical chart."""
    dx, dy = float(b[0]) - float(a[0]), float(b[1]) - float(a[1])
    return math.degrees(math.atan2(dx, dy)) % 360.0


PHASE_A_PROJECTION = EquirectangularProjection(*PHASE_A_PROJECTION_CENTER)
HIGH_SEAS_PROJECTION = EquirectangularProjection(*HIGH_SEAS_PROJECTION_CENTER)
