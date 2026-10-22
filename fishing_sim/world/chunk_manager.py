"""Sparse uniform-grid spatial index and deterministic low-detail promotion.

The grid is an index only: it does not own vessel state or run a world simulation.
Query order is distance, then stable vessel ID. Updates are expected at scheduled
simulation ticks, not every rendered frame.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Iterable, Mapping

DEFAULT_CELL_SIZE_NM = 20.0
ACTIVE_RADIUS_NM = 12.0
WARM_RADIUS_NM = 40.0
DEFAULT_ACTIVE_CAP = 30


@dataclass(frozen=True)
class SpatialHit:
    vessel_id: str
    position_nm: tuple[float, float]
    distance_nm: float


class SpatialIndex:
    def __init__(self, cell_size_nm: float = DEFAULT_CELL_SIZE_NM):
        if not math.isfinite(float(cell_size_nm)) or float(cell_size_nm) <= 0.0:
            raise ValueError("cell_size_nm must be positive and finite")
        self.cell_size_nm = float(cell_size_nm)
        self.cells: dict[tuple[int, int], set[str]] = {}
        self.positions: dict[str, tuple[float, float]] = {}
        self.membership: dict[str, tuple[int, int]] = {}

    def cell_for(self, pos: tuple[float, float]) -> tuple[int, int]:
        x, y = float(pos[0]), float(pos[1])
        return math.floor(x / self.cell_size_nm), math.floor(y / self.cell_size_nm)

    def upsert(self, vessel_id: str, pos: tuple[float, float]) -> bool:
        """Insert/update a point. Returns True only when its containing cell changed."""
        vessel_id = str(vessel_id)
        p = (float(pos[0]), float(pos[1]))
        if not all(math.isfinite(v) for v in p):
            raise ValueError("spatial position must be finite")
        cell = self.cell_for(p)
        old_cell = self.membership.get(vessel_id)
        changed = old_cell != cell
        if old_cell is not None and changed:
            old = self.cells.get(old_cell)
            if old is not None:
                old.discard(vessel_id)
                if not old:
                    self.cells.pop(old_cell, None)
        if old_cell is None or changed:
            self.cells.setdefault(cell, set()).add(vessel_id)
            self.membership[vessel_id] = cell
        self.positions[vessel_id] = p
        return changed

    def remove(self, vessel_id: str) -> None:
        vessel_id = str(vessel_id)
        cell = self.membership.pop(vessel_id, None)
        self.positions.pop(vessel_id, None)
        if cell is None:
            return
        members = self.cells.get(cell)
        if members is not None:
            members.discard(vessel_id)
            if not members:
                self.cells.pop(cell, None)

    def candidates(self, centre: tuple[float, float], radius_nm: float) -> list[str]:
        x, y = float(centre[0]), float(centre[1])
        radius = max(0.0, float(radius_nm))
        lo_x, lo_y = self.cell_for((x - radius, y - radius))
        hi_x, hi_y = self.cell_for((x + radius, y + radius))
        found: set[str] = set()
        for cx in range(lo_x, hi_x + 1):
            for cy in range(lo_y, hi_y + 1):
                found.update(self.cells.get((cx, cy), ()))
        return sorted(found)

    def query(self, centre: tuple[float, float], radius_nm: float) -> list[SpatialHit]:
        x, y = float(centre[0]), float(centre[1])
        radius = max(0.0, float(radius_nm))
        hits = []
        for vessel_id in self.candidates((x, y), radius):
            px, py = self.positions[vessel_id]
            distance = math.hypot(px - x, py - y)
            if distance <= radius + 1e-9:
                hits.append(SpatialHit(vessel_id, (px, py), distance))
        hits.sort(key=lambda hit: (hit.distance_nm, hit.vessel_id))
        return hits


class LODManager:
    """Nearest-first tier assignment; coarse schedules do not become full AI entities."""
    def __init__(self, active_radius_nm: float = ACTIVE_RADIUS_NM,
                 warm_radius_nm: float = WARM_RADIUS_NM, active_cap: int = DEFAULT_ACTIVE_CAP):
        self.active_radius_nm = float(active_radius_nm)
        self.warm_radius_nm = max(self.active_radius_nm, float(warm_radius_nm))
        self.active_cap = max(1, int(active_cap))
        self.active_ids: tuple[str, ...] = ()
        self.warm_ids: tuple[str, ...] = ()
        self.coarse_ids: tuple[str, ...] = ()

    def assign(self, positions: Mapping[str, tuple[float, float]], focus: tuple[float, float]) -> None:
        rows = sorted((math.hypot(p[0] - focus[0], p[1] - focus[1]), str(key))
                      for key, p in positions.items())
        active_candidates = [vessel_id for distance, vessel_id in rows if distance <= self.active_radius_nm]
        self.active_ids = tuple(active_candidates[:self.active_cap])
        active = set(self.active_ids)
        warm = [vessel_id for distance, vessel_id in rows
                if distance <= self.warm_radius_nm and vessel_id not in active]
        warm_set = set(warm)
        self.warm_ids = tuple(warm)
        self.coarse_ids = tuple(vessel_id for _, vessel_id in rows
                                if vessel_id not in active and vessel_id not in warm_set)
