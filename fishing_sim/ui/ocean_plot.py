"""Pure input geometry and visibility rules for ocean-space course orders."""
from __future__ import annotations

import math


def visibility_allows_ocean_plot(daylight: float, fog: float, rain: float,
                                visibility_km: float) -> bool:
    """Ocean targets need enough light and a clear, reasonably dry line of sight."""
    return (float(daylight) >= 0.38 and float(fog) <= 0.32
            and float(rain) <= 0.38 and float(visibility_km) >= 4.5)


def screen_to_relative(screen_point, center, zoom: float) -> tuple[float, float]:
    z = max(1e-6, float(zoom))
    return ((float(screen_point[0]) - float(center[0])) / z,
            (float(screen_point[1]) - float(center[1])) / z)


def clamp_relative_distance(point, max_distance: float) -> tuple[float, float]:
    x, y = float(point[0]), float(point[1])
    length = math.hypot(x, y)
    limit = max(0.0, float(max_distance))
    if length <= limit or length < 1e-9:
        return x, y
    ratio = limit / length
    return x * ratio, y * ratio


def extend_edge_target(point, screen_point, viewport_size, zoom: float,
                       max_distance: float, edge_margin: float = 28.0,
                       extension_pixels: float = 160.0) -> tuple[float, float]:
    """Extend a near-edge target beyond the viewport without making it infinite."""
    x, y = float(point[0]), float(point[1])
    sx, sy = float(screen_point[0]), float(screen_point[1])
    width, height = float(viewport_size[0]), float(viewport_size[1])
    near_edge = (sx <= edge_margin or sx >= width - edge_margin
                 or sy <= edge_margin or sy >= height - edge_margin)
    length = math.hypot(x, y)
    if not near_edge or length < 1e-9:
        return clamp_relative_distance((x, y), max_distance)
    extended = min(max(0.0, float(max_distance)), length + max(0.0, float(extension_pixels)) / max(1e-6, float(zoom)))
    return x * extended / length, y * extended / length
