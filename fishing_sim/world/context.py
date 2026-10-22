"""Small integration context for the new world systems.

The legacy Game/World objects remain authoritative for vessel physics during the
v13.2 migration. This object owns only the deterministic traffic clock and seed.
"""
from __future__ import annotations
from dataclasses import dataclass
from .traffic import TrafficWorld
from .weather_grid import WeatherGrid

@dataclass
class WorldContext:
    world_seed: int = 1962
    phase: str = "A"
    sim_time_s: float = 0.0
    traffic: TrafficWorld | None = None
    weather: WeatherGrid | None = None

    def __post_init__(self) -> None:
        if self.phase not in ("A", "B", "C"):
            raise ValueError("phase must be A, B, or C")
        if self.traffic is None:
            self.traffic = TrafficWorld(self.world_seed)
        if self.weather is None:
            self.weather = WeatherGrid(self.world_seed, phase=self.phase)

    def advance(self, sim_time_s: float, player_position_nm: tuple[float, float]) -> bool:
        self.sim_time_s = max(0.0, float(sim_time_s))
        assert self.traffic is not None
        changed = self.traffic.advance(self.sim_time_s, focus_nm=player_position_nm)
        self.traffic.observe_nearby(player_position_nm, self.sim_time_s)
        assert self.weather is not None
        self.weather.advance(self.sim_time_s)
        return changed
