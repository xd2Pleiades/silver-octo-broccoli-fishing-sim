"""Deterministic, coarse regional weather field for v13.2.

The legacy shipboard Weather object remains the authority for conditions at the
player. This grid models spatial variation, remote-ship conditions, and forecasts.
It evolves on a fixed simulation-time cadence and never consumes global random state.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import random
from typing import Any

from .coordinates import PHASE_A_BOUNDS, PHASE_A_PROJECTION, PHASE_B_BOUNDS_NM
from .seeding import stable_seed

WEATHER_SCHEMA_VERSION = 1
DEFAULT_CELL_SIZE_NM = 20.0
PHASE_B_COARSE_CELL_SIZE_NM = 80.0  # coarse global overview; 20-NM remains opt-in for profiling
WEATHER_TICK_INTERVAL_S = 5.0  # 12 in-game minutes when one day is 600 sim seconds
SIM_SECONDS_PER_GAME_DAY = 600.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _finite(v: Any, label: str) -> float:
    result = float(v)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


@dataclass(frozen=True)
class WeatherCell:
    pressure_hpa: float
    wind_u_kt: float       # positive east
    wind_v_kt: float       # positive north
    precipitation: float   # 0..1
    cloud: float           # 0..1
    fog: float             # 0..1
    sea_state: float       # normalized 0..1

    @property
    def wind_speed_kt(self) -> float:
        return math.hypot(self.wind_u_kt, self.wind_v_kt)

    @property
    def wind_direction_deg(self) -> float:
        # Direction toward which the wind travels, clockwise from north.
        return math.degrees(math.atan2(self.wind_u_kt, self.wind_v_kt)) % 360.0

    @property
    def phrase(self) -> str:
        if self.sea_state >= 0.78 or self.precipitation >= 0.82:
            return "heavy swell and poor working conditions"
        if self.fog >= 0.72:
            return "dense fog and restricted visibility"
        if self.precipitation >= 0.48:
            return "rain squalls and a building sea"
        if self.sea_state >= 0.56:
            return "a building sea"
        if self.cloud >= 0.76:
            return "overcast with a moderate sea"
        if self.cloud >= 0.43:
            return "cloudy with fair visibility"
        return "fair conditions"


@dataclass(frozen=True)
class WeatherForecastPoint:
    hours_ahead: float
    sim_time_s: float
    sample: WeatherCell


class WeatherGrid:
    """Deterministic weather grid: 20-NM regional, coarse Phase B by default.

    Phase B intentionally starts with an 80-NM global field to avoid multiplying
    the optimized Phase A tick cost by ~15x. Pass cell_size_nm=20 for full-resolution
    high-seas profiling; finer global weather will be enabled after sparse-grid work.
    """

    def __init__(self, world_seed: int = 1962, *, cell_size_nm: float | None = None,
                 phase: str = "A", bounds_nm: tuple[float, float, float, float] | None = None):
        self.world_seed = int(world_seed)
        phase = str(phase).upper()
        if phase not in ("A", "B", "C"):
            raise ValueError("weather grid phase must be A, B, or C")
        self.phase = phase
        if cell_size_nm is None:
            cell_size_nm = DEFAULT_CELL_SIZE_NM if phase == "A" else PHASE_B_COARSE_CELL_SIZE_NM
        self.cell_size_nm = _finite(cell_size_nm, "cell_size_nm")
        if self.cell_size_nm <= 0.0:
            raise ValueError("cell_size_nm must be positive")
        if bounds_nm is None:
            if phase == "A":
                corners = [
                    PHASE_A_PROJECTION.to_nm(PHASE_A_BOUNDS["west_lon"], PHASE_A_BOUNDS["south_lat"]),
                    PHASE_A_PROJECTION.to_nm(PHASE_A_BOUNDS["west_lon"], PHASE_A_BOUNDS["north_lat"]),
                    PHASE_A_PROJECTION.to_nm(PHASE_A_BOUNDS["east_lon"], PHASE_A_BOUNDS["south_lat"]),
                    PHASE_A_PROJECTION.to_nm(PHASE_A_BOUNDS["east_lon"], PHASE_A_BOUNDS["north_lat"]),
                ]
                bounds_nm = (min(p[0] for p in corners), max(p[0] for p in corners),
                             min(p[1] for p in corners), max(p[1] for p in corners))
            else:
                # Phase B high-seas bounds include Hakodate's transit corridor and
                # wrap continuously from 140E across the date line to 175W.
                bounds_nm = PHASE_B_BOUNDS_NM
        if len(bounds_nm) != 4:
            raise ValueError("bounds_nm must be (min_x, max_x, min_y, max_y)")
        self.bounds_nm = tuple(_finite(v, "bound") for v in bounds_nm)
        min_x, max_x, min_y, max_y = self.bounds_nm
        if min_x >= max_x or min_y >= max_y:
            raise ValueError("weather bounds must have positive area")
        # Align cells to the regional bounding box rather than world zero. This
        # avoids wasteful partial rows near Hakodate and keeps Phase A near 20x20 NM.
        self.origin_x_nm, self.origin_y_nm = min_x, min_y
        self.min_gx = 0
        self.min_gy = 0
        self.max_gx = max(0, int(math.ceil((max_x - min_x) / self.cell_size_nm)) - 1)
        self.max_gy = max(0, int(math.ceil((max_y - min_y) / self.cell_size_nm)) - 1)
        self.cells: dict[tuple[int, int], WeatherCell] = {}
        self.sim_time_s = 0.0
        self.tick_index = 0
        self.tick_count = 0
        self._generate()
        self._keys = tuple(sorted(self.cells, key=lambda k: (k[1], k[0])))
        # Fast immutable row-major index for fixed-grid stepping. The public
        # cells mapping remains keyed by (gx, gy), but the hot loop avoids tuple
        # dictionary lookups for every upstream/neighbor sample.
        width, height = self.dimensions
        self._flat_index = {key: i for i, key in enumerate(self._keys)}
        self._center_xy = tuple(
            (self.origin_x_nm + (gx + 0.5) * self.cell_size_nm,
             self.origin_y_nm + (gy + 0.5) * self.cell_size_nm)
            for gx, gy in self._keys)
        self._neighbor_indices = tuple(
            (self._flat_index[(max(self.min_gx, gx - 1), gy)],
             self._flat_index[(min(self.max_gx, gx + 1), gy)],
             self._flat_index[(gx, max(self.min_gy, gy - 1))],
             self._flat_index[(gx, min(self.max_gy, gy + 1))])
            for gx, gy in self._keys)
        self._flat_width = width
        self._flat_height = height
        self._flat_values: list[tuple[float, ...]] = [self._tuple(self.cells[key]) for key in self._keys]

    def rebase_time(self, sim_time_s: float) -> None:
        """Start a never-visited phase grid at the current campaign time.

        An inactive phase has no historical observations to replay. Rebasing avoids
        thousands of catch-up ticks when the player first opens the Phase B chart
        late in a career. Once created, this grid evolves and persists normally.
        """
        now = max(0.0, _finite(sim_time_s, "sim_time_s"))
        self.sim_time_s = now
        self.tick_index = int(math.floor((now + 1e-9) / WEATHER_TICK_INTERVAL_S))
        self.tick_count = 0

    @property
    def next_tick_s(self) -> float:
        return (self.tick_index + 1) * WEATHER_TICK_INTERVAL_S

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.max_gx - self.min_gx + 1, self.max_gy - self.min_gy + 1

    @property
    def cell_count(self) -> int:
        return len(self.cells)

    def cell_for(self, position_nm: tuple[float, float]) -> tuple[int, int]:
        x, y = _finite(position_nm[0], "x_nm"), _finite(position_nm[1], "y_nm")
        gx = int(math.floor((x - self.origin_x_nm) / self.cell_size_nm))
        gy = int(math.floor((y - self.origin_y_nm) / self.cell_size_nm))
        return (max(self.min_gx, min(self.max_gx, gx)),
                max(self.min_gy, min(self.max_gy, gy)))

    def _generate(self) -> None:
        self.cells.clear()
        for gy in range(self.min_gy, self.max_gy + 1):
            for gx in range(self.min_gx, self.max_gx + 1):
                rng = random.Random(stable_seed(self.world_seed, "weather-cell", self.phase, gx, gy))
                x = self.origin_x_nm + (gx + 0.5) * self.cell_size_nm
                y = self.origin_y_nm + (gy + 0.5) * self.cell_size_nm
                pressure = 1013.0 + 2.2 * math.sin(x / 85.0) - 2.6 * math.cos(y / 72.0) + rng.uniform(-2.0, 2.0)
                direction = rng.random() * math.tau
                speed = rng.uniform(4.0, 22.0)
                u, v = math.sin(direction) * speed, math.cos(direction) * speed
                cloud = _clamp(0.48 + (1013.0 - pressure) / 18.0 + rng.uniform(-0.23, 0.23), 0.02, 0.98)
                precip = _clamp((cloud - 0.43) * 0.60 + rng.uniform(-0.12, 0.18), 0.0, 0.85)
                fog = _clamp((cloud - 0.65) * 1.25 + rng.uniform(0.0, 0.22), 0.0, 0.92)
                sea = _clamp(0.08 + speed / 48.0 + precip * 0.18, 0.0, 1.0)
                self.cells[(gx, gy)] = WeatherCell(pressure, u, v, precip, cloud, fog, sea)

    def _nearest_key(self, gx_f: float, gy_f: float) -> tuple[int, int]:
        gx = max(self.min_gx, min(self.max_gx, int(round(gx_f))))
        gy = max(self.min_gy, min(self.max_gy, int(round(gy_f))))
        return gx, gy

    def _interpolate(self, x_nm: float, y_nm: float, field: str,
                     cells: dict[tuple[int, int], WeatherCell] | None = None) -> float:
        source = self.cells if cells is None else cells
        # Continuous cell-centre coordinates; clamp at map edges instead of creating missing cells.
        fx = (x_nm - self.origin_x_nm) / self.cell_size_nm - 0.5
        fy = (y_nm - self.origin_y_nm) / self.cell_size_nm - 0.5
        x0f, y0f = math.floor(fx), math.floor(fy)
        tx, ty = fx - x0f, fy - y0f
        x0 = max(self.min_gx, min(self.max_gx, int(x0f)))
        x1 = max(self.min_gx, min(self.max_gx, int(x0f + 1)))
        y0 = max(self.min_gy, min(self.max_gy, int(y0f)))
        y1 = max(self.min_gy, min(self.max_gy, int(y0f + 1)))
        a = getattr(source[(x0, y0)], field)
        b = getattr(source[(x1, y0)], field)
        c = getattr(source[(x0, y1)], field)
        d = getattr(source[(x1, y1)], field)
        lo = a * (1.0 - tx) + b * tx
        hi = c * (1.0 - tx) + d * tx
        return lo * (1.0 - ty) + hi * ty

    def sample(self, position_nm: tuple[float, float], *, sim_time_s: float | None = None) -> WeatherCell:
        x, y = _finite(position_nm[0], "x_nm"), _finite(position_nm[1], "y_nm")
        # Grid edge clamp means all positions have a defined nearest weather region.
        x = _clamp(x, self.bounds_nm[0], self.bounds_nm[1] - 1e-9)
        y = _clamp(y, self.bounds_nm[2], self.bounds_nm[3] - 1e-9)
        vals = {field: self._interpolate(x, y, field) for field in (
            "pressure_hpa", "wind_u_kt", "wind_v_kt", "precipitation", "cloud", "fog", "sea_state")}
        return WeatherCell(
            pressure_hpa=vals["pressure_hpa"], wind_u_kt=vals["wind_u_kt"],
            wind_v_kt=vals["wind_v_kt"], precipitation=_clamp(vals["precipitation"], 0, 1),
            cloud=_clamp(vals["cloud"], 0, 1), fog=_clamp(vals["fog"], 0, 1),
            sea_state=_clamp(vals["sea_state"], 0, 1))

    @staticmethod
    def _tuple(cell: WeatherCell) -> tuple[float, ...]:
        return (cell.pressure_hpa, cell.wind_u_kt, cell.wind_v_kt, cell.precipitation,
                cell.cloud, cell.fog, cell.sea_state)

    @staticmethod
    def _deterministic_noise_triplet(world_seed: int, tick: int, gx: int, gy: int) -> tuple[float, float, float]:
        """Tiny process-stable integer mixer; avoids RNG and temporary list allocations."""
        mask = 0xFFFFFFFF
        value = ((int(world_seed) & mask) ^ ((int(tick) * 0x9E3779B1) & mask)
                 ^ ((int(gx) * 0x85EBCA6B) & mask) ^ ((int(gy) * 0xC2B2AE35) & mask))
        value ^= value >> 16
        value = (value * 0x7FEB352D) & mask
        value ^= value >> 15
        value = (value * 0x846CA68B) & mask
        value ^= value >> 16
        n0 = (value / 4294967295.0) * 2.0 - 1.0
        value = (value * 1664525 + 1013904223) & mask

        value ^= value >> 16
        value = (value * 0x7FEB352D) & mask
        value ^= value >> 15
        value = (value * 0x846CA68B) & mask
        value ^= value >> 16
        n1 = (value / 4294967295.0) * 2.0 - 1.0
        value = (value * 1664525 + 1013904223) & mask

        value ^= value >> 16
        value = (value * 0x7FEB352D) & mask
        value ^= value >> 15
        value = (value * 0x846CA68B) & mask
        value ^= value >> 16
        n2 = (value / 4294967295.0) * 2.0 - 1.0
        return n0, n1, n2

    def _step(self, next_tick: int) -> None:
        # Keep cells as a public keyed mapping, but run the numerical kernel on
        # compact row-major value tuples. This removes two dicts and a neighbor
        # tuple allocation per cell while preserving the original equations.
        old = self.cells
        keys = self._keys
        # Cached tuple field records are kept in sync with cells by observe_local/restore.
        # Rebuilding 414 tuples every tick was a measurable fraction of the fixed-step cost.
        old_values = self._flat_values
        updated_values: list[tuple[float, ...]] = []
        dt_hours = WEATHER_TICK_INTERVAL_S * 24.0 / SIM_SECONDS_PER_GAME_DAY
        width = self._flat_width
        origin_x, origin_y = self.origin_x_nm, self.origin_y_nm
        size = self.cell_size_nm
        min_gx, max_gx = self.min_gx, self.max_gx
        min_gy, max_gy = self.min_gy, self.max_gy
        mask = 0xFFFFFFFF

        for i, key in enumerate(keys):
            gx, gy = key
            local = old_values[i]
            cx, cy = self._center_xy[i]
            # Inline the hot bilinear sampler: one call per cell dominates a small
            # regional grid, and all seven channels share the same four neighbors.
            fx = (cx - local[1] * dt_hours - origin_x) / size - 0.5
            fy = (cy - local[2] * dt_hours - origin_y) / size - 0.5
            x0f, y0f = math.floor(fx), math.floor(fy)
            tx, ty = fx - x0f, fy - y0f
            x0 = max(min_gx, min(max_gx, int(x0f)))
            x1 = max(min_gx, min(max_gx, int(x0f + 1)))
            y0 = max(min_gy, min(max_gy, int(y0f)))
            y1 = max(min_gy, min(max_gy, int(y0f + 1)))
            a, b = old_values[y0 * width + x0], old_values[y0 * width + x1]
            c, d = old_values[y1 * width + x0], old_values[y1 * width + x1]
            omt = 1.0 - tx
            omy = 1.0 - ty
            adv0 = (a[0] * omt + b[0] * tx) * omy + (c[0] * omt + d[0] * tx) * ty
            adv1 = (a[1] * omt + b[1] * tx) * omy + (c[1] * omt + d[1] * tx) * ty
            adv2 = (a[2] * omt + b[2] * tx) * omy + (c[2] * omt + d[2] * tx) * ty
            adv3 = (a[3] * omt + b[3] * tx) * omy + (c[3] * omt + d[3] * tx) * ty
            adv4 = (a[4] * omt + b[4] * tx) * omy + (c[4] * omt + d[4] * tx) * ty
            adv5 = (a[5] * omt + b[5] * tx) * omy + (c[5] * omt + d[5] * tx) * ty
            adv6 = (a[6] * omt + b[6] * tx) * omy + (c[6] * omt + d[6] * tx) * ty
            ni_left, ni_right, ni_south, ni_north = self._neighbor_indices[i]
            left = old_values[ni_left]
            right = old_values[ni_right]
            south = old_values[ni_south]
            north = old_values[ni_north]
            n_pressure = (left[0] + right[0] + south[0] + north[0]) * 0.25
            n_u = (left[1] + right[1] + south[1] + north[1]) * 0.25
            n_v = (left[2] + right[2] + south[2] + north[2]) * 0.25
            n_precip = (left[3] + right[3] + south[3] + north[3]) * 0.25
            n_cloud = (left[4] + right[4] + south[4] + north[4]) * 0.25
            n_fog = (left[5] + right[5] + south[5] + north[5]) * 0.25
            n_sea = (left[6] + right[6] + south[6] + north[6]) * 0.25
            # Inline the tiny deterministic mixer too; no per-cell RNG/list/tuple
            # allocation is needed, and this stream remains independent of global RNG.
            value = ((int(self.world_seed) & mask) ^ ((int(next_tick) * 0x9E3779B1) & mask)
                     ^ ((int(gx) * 0x85EBCA6B) & mask) ^ ((int(gy) * 0xC2B2AE35) & mask))
            value ^= value >> 16
            value = (value * 0x7FEB352D) & mask
            value ^= value >> 15
            value = (value * 0x846CA68B) & mask
            value ^= value >> 16
            n0 = (value / 4294967295.0) * 2.0 - 1.0
            value = (value * 1664525 + 1013904223) & mask
            value ^= value >> 16
            value = (value * 0x7FEB352D) & mask
            value ^= value >> 15
            value = (value * 0x846CA68B) & mask
            value ^= value >> 16
            n1 = (value / 4294967295.0) * 2.0 - 1.0
            value = (value * 1664525 + 1013904223) & mask
            value ^= value >> 16
            value = (value * 0x7FEB352D) & mask
            value ^= value >> 15
            value = (value * 0x846CA68B) & mask
            value ^= value >> 16
            n2 = (value / 4294967295.0) * 2.0 - 1.0
            pressure = min(1045.0, max(975.0, adv0 * 0.68 + local[0] * 0.24 + n_pressure * 0.08 + n0 * 0.10))
            pressure_delta = pressure - local[0]
            wind_u = min(48.0, max(-48.0, adv1 * 0.62 + local[1] * 0.28 + n_u * 0.10 - pressure_delta * 0.04))
            wind_v = min(48.0, max(-48.0, adv2 * 0.62 + local[2] * 0.28 + n_v * 0.10 + pressure_delta * 0.03))
            wind_speed = math.hypot(wind_u, wind_v)
            cloud = min(1.0, max(0.0, adv4 * 0.66 + local[4] * 0.25 + n_cloud * 0.09
                                 + (1012.0 - pressure) * 0.003 + n1 * 0.012))
            precipitation = min(1.0, max(0.0, adv3 * 0.67 + local[3] * 0.23 + n_precip * 0.10
                                         + (cloud - 0.62) * 0.018 + n2 * 0.015))
            fog = min(1.0, max(0.0, adv5 * 0.60 + local[5] * 0.30 + n_fog * 0.10
                              + (cloud - 0.70) * 0.025 - precipitation * 0.006 + n0 * 0.012))
            target_sea = min(1.0, max(0.0, wind_speed / 48.0 + precipitation * 0.18))
            sea = min(1.0, max(0.0, (adv6 * 0.48 + local[6] * 0.28 + n_sea * 0.24) * 0.65
                               + target_sea * 0.35))
            updated_values.append((pressure, wind_u, wind_v, precipitation, cloud, fog, sea))
        # Build the entire new field before publishing it; then update the existing
        # mapping so consumers holding the cells mapping don't retain a stale object.
        for key, values in zip(keys, updated_values):
            old[key] = WeatherCell(*values)
        self._flat_values = updated_values
        self.tick_index = int(next_tick)
        self.tick_count += 1

    def advance(self, sim_time_s: float) -> bool:
        """Advance only on fixed 5-sim-second ticks; large jumps skip no weather ticks."""
        now = max(0.0, _finite(sim_time_s, "sim_time_s"))
        if now < self.sim_time_s:
            # Time rewind should be handled by restoring a prior snapshot, not evolving backwards.
            return False
        due_tick = int(math.floor((now + 1e-9) / WEATHER_TICK_INTERVAL_S))
        changed = False
        while self.tick_index < due_tick:
            self._step(self.tick_index + 1)
            changed = True
        self.sim_time_s = now
        return changed

    def observe_local(self, position_nm: tuple[float, float], *, cloud: float,
                      precipitation: float, fog: float, wind_speed_kt: float,
                      wind_direction_rad: float, sea_state: float,
                      pressure_hpa: float | None = None) -> None:
        """Assimilate authoritative legacy shipboard weather into the player's cell."""
        key = self.cell_for(position_nm)
        old = self.cells[key]
        speed = _clamp(wind_speed_kt, 0.0, 60.0)
        direction = _finite(wind_direction_rad, "wind_direction_rad")
        pressure = old.pressure_hpa if pressure_hpa is None else _clamp(pressure_hpa, 975, 1045)
        cell = WeatherCell(
            pressure_hpa=pressure,
            wind_u_kt=math.cos(direction) * speed,
            wind_v_kt=-math.sin(direction) * speed,
            precipitation=_clamp(precipitation, 0, 1), cloud=_clamp(cloud, 0, 1),
            fog=_clamp(fog, 0, 1), sea_state=_clamp(sea_state, 0, 1))
        self.cells[key] = cell
        self._flat_values[self._flat_index[key]] = self._tuple(cell)

    def snapshot(self) -> dict[str, Any]:
        rows = []
        for (gx, gy), cell in sorted(self.cells.items(), key=lambda item: (item[0][1], item[0][0])):
            rows.append([gx, gy, cell.pressure_hpa, cell.wind_u_kt, cell.wind_v_kt,
                         cell.precipitation, cell.cloud, cell.fog, cell.sea_state])
        return {
            "schema_version": WEATHER_SCHEMA_VERSION,
            "world_seed": self.world_seed,
            "phase": self.phase,
            "cell_size_nm": self.cell_size_nm,
            "bounds_nm": list(self.bounds_nm),
            "sim_time_s": self.sim_time_s,
            "tick_index": self.tick_index,
            "cells": rows,
        }

    def restore(self, payload: dict[str, Any]) -> None:
        """Replace grid state after strict schema, geometry, and finite-value checks."""
        if not isinstance(payload, dict):
            raise ValueError("weather snapshot must be an object")
        if int(payload.get("schema_version", 0)) != WEATHER_SCHEMA_VERSION:
            raise ValueError("unsupported weather snapshot schema")
        if int(payload.get("world_seed", self.world_seed)) != self.world_seed:
            raise ValueError("weather snapshot world seed does not match")
        if str(payload.get("phase", self.phase)).upper() != self.phase:
            raise ValueError("weather snapshot phase does not match")
        if abs(float(payload.get("cell_size_nm", self.cell_size_nm)) - self.cell_size_nm) > 1e-9:
            raise ValueError("weather snapshot cell size does not match")
        bounds = tuple(float(v) for v in payload.get("bounds_nm", self.bounds_nm))
        if len(bounds) != 4 or any(abs(a - b) > 1e-8 for a, b in zip(bounds, self.bounds_nm)):
            raise ValueError("weather snapshot bounds do not match")
        rows = payload.get("cells")
        if not isinstance(rows, list) or len(rows) != len(self.cells):
            raise ValueError("weather snapshot has the wrong cell count")
        restored: dict[tuple[int, int], WeatherCell] = {}
        for row in rows:
            if not isinstance(row, list) or len(row) != 9:
                raise ValueError("invalid weather cell row")
            gx, gy = int(row[0]), int(row[1])
            key = (gx, gy)
            if key not in self.cells or key in restored:
                raise ValueError("unknown or duplicate weather cell")
            vals = [_finite(v, "weather cell field") for v in row[2:]]
            pressure, u, v, precip, cloud, fog, sea = vals
            if not 900 <= pressure <= 1100 or not -60 <= u <= 60 or not -60 <= v <= 60:
                raise ValueError("weather cell pressure/wind outside safety bounds")
            if any(not 0 <= x <= 1 for x in (precip, cloud, fog, sea)):
                raise ValueError("weather cell normalized field outside 0..1")
            restored[key] = WeatherCell(pressure, u, v, precip, cloud, fog, sea)
        sim_time = _finite(payload.get("sim_time_s", 0.0), "sim_time_s")
        tick_index = int(payload.get("tick_index", 0))
        if sim_time < 0 or tick_index < 0 or tick_index > int(sim_time // WEATHER_TICK_INTERVAL_S):
            raise ValueError("invalid weather time/tick state")
        self.cells = restored
        self._flat_values = [self._tuple(restored[key]) for key in self._keys]
        self.sim_time_s = sim_time
        self.tick_index = tick_index
        self.tick_count = tick_index

    @classmethod
    def from_snapshot(cls, payload: dict[str, Any]) -> "WeatherGrid":
        grid = cls(world_seed=int(payload.get("world_seed", 1962)),
                   cell_size_nm=(float(payload["cell_size_nm"]) if "cell_size_nm" in payload else None),
                   phase=str(payload.get("phase", "A")),
                   bounds_nm=tuple(payload["bounds_nm"]) if "bounds_nm" in payload else None)
        grid.restore(payload)
        return grid

    def dumps(self) -> str:
        return json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def loads(cls, data: str | bytes) -> "WeatherGrid":
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        try:
            payload = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("invalid weather snapshot JSON") from exc
        return cls.from_snapshot(payload)

    def forecast(self, position_nm: tuple[float, float], *, horizon_hours: float = 72.0,
                 step_hours: float = 6.0, sim_time_s: float | None = None) -> tuple[WeatherForecastPoint, ...]:
        """Return a three-day (by default) forecast from a copied grid state."""
        horizon = _finite(horizon_hours, "horizon_hours")
        step = _finite(step_hours, "step_hours")
        if horizon < 0 or step <= 0:
            raise ValueError("forecast horizon must be nonnegative and step positive")
        base_time = self.sim_time_s if sim_time_s is None else max(0.0, _finite(sim_time_s, "sim_time_s"))
        future = WeatherGrid.from_snapshot(self.snapshot())
        # Forecast base must never move the live grid, even if asked at a later time.
        if base_time > future.sim_time_s:
            future.advance(base_time)
        points = [WeatherForecastPoint(0.0, base_time, future.sample(position_nm))]
        hours = step
        while hours <= horizon + 1e-9:
            target_time = base_time + hours * SIM_SECONDS_PER_GAME_DAY / 24.0
            future.advance(target_time)
            points.append(WeatherForecastPoint(hours, target_time, future.sample(position_nm)))
            hours += step
        if points[-1].hours_ahead < horizon - 1e-9:
            target_time = base_time + horizon * SIM_SECONDS_PER_GAME_DAY / 24.0
            future.advance(target_time)
            points.append(WeatherForecastPoint(horizon, target_time, future.sample(position_nm)))
        return tuple(points)
