"""Coordinate adapters between the legacy Hakodate plane and Phase B high seas.

The hull simulation still stores positions in the legacy local design plane. This
module maps those positions through lon/lat into the Phase B equirectangular plane,
allowing the traffic/radio/weather systems and high-seas chart to share coordinates
without changing the ship physics origin.
"""
from __future__ import annotations

import math
from .coordinates import (
    HIGH_SEAS_PROJECTION,
    PHASE_A_PROJECTION,
    PHASE_B_BOUNDS_NM,
)

DESIGN_UNITS_PER_NAUTICAL_MILE = 185.2


def legacy_nm_to_phase_b_nm(position_nm: tuple[float, float]) -> tuple[float, float]:
    """Convert Hakodate-local (east, north) nautical miles to Phase B NM."""
    x, y = float(position_nm[0]), float(position_nm[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("legacy position must be finite")
    lon, lat = PHASE_A_PROJECTION.to_lonlat(x, y)
    return HIGH_SEAS_PROJECTION.to_nm(lon, lat)


def phase_b_nm_to_legacy_nm(position_nm: tuple[float, float]) -> tuple[float, float]:
    """Convert Phase B projected NM back to the legacy Hakodate-local plane."""
    x, y = float(position_nm[0]), float(position_nm[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("Phase B position must be finite")
    lon, lat = HIGH_SEAS_PROJECTION.to_lonlat(x, y)
    return PHASE_A_PROJECTION.to_nm(lon, lat)


def legacy_design_to_phase_b_nm(position_design: tuple[float, float]) -> tuple[float, float]:
    """Convert chart design units (positive y south) to Phase B projected NM."""
    x, y = float(position_design[0]), float(position_design[1])
    return legacy_nm_to_phase_b_nm((x / DESIGN_UNITS_PER_NAUTICAL_MILE,
                                    -y / DESIGN_UNITS_PER_NAUTICAL_MILE))


def phase_b_nm_to_legacy_design(position_nm: tuple[float, float]) -> tuple[float, float]:
    """Inverse of ``legacy_design_to_phase_b_nm`` for waypoint editing."""
    x_nm, y_nm = phase_b_nm_to_legacy_nm(position_nm)
    return (x_nm * DESIGN_UNITS_PER_NAUTICAL_MILE,
            -y_nm * DESIGN_UNITS_PER_NAUTICAL_MILE)


def phase_b_legacy_design_bounds(padding: float = 250.0) -> tuple[float, float, float, float]:
    """Return a safe local-design rectangle containing the entire Phase B chart."""
    min_x, max_x, min_y, max_y = PHASE_B_BOUNDS_NM
    corners = [
        phase_b_nm_to_legacy_design((min_x, min_y)),
        phase_b_nm_to_legacy_design((min_x, max_y)),
        phase_b_nm_to_legacy_design((max_x, min_y)),
        phase_b_nm_to_legacy_design((max_x, max_y)),
    ]
    return (min(p[0] for p in corners) - padding,
            min(p[1] for p in corners) - padding,
            max(p[0] for p in corners) + padding,
            max(p[1] for p in corners) + padding)


def phase_b_nm_inside(position_nm: tuple[float, float], *, inset: float = 0.0) -> bool:
    x, y = float(position_nm[0]), float(position_nm[1])
    min_x, max_x, min_y, max_y = PHASE_B_BOUNDS_NM
    inset = max(0.0, float(inset))
    return min_x + inset <= x <= max_x - inset and min_y + inset <= y <= max_y - inset


def phase_b_chart_bounds() -> tuple[float, float, float, float]:
    """Bounds for chart drawing (x east, y down), derived from high-seas NM bounds."""
    min_x, max_x, min_y, max_y = PHASE_B_BOUNDS_NM
    return (min_x, -max_y, max_x, -min_y)
