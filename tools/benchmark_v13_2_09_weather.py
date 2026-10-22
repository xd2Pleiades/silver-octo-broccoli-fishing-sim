#!/usr/bin/env python3
"""Repeatable stdlib benchmark for the optimized v13.2.09 regional weather field."""
from __future__ import annotations
import json
import statistics
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fishing_sim.world.weather_grid import WeatherGrid, WEATHER_TICK_INTERVAL_S


def main() -> None:
    grid = WeatherGrid(world_seed=1962, phase="A")
    # Warm interpreter paths before collecting one hundred independent tick timings.
    for _ in range(5):
        grid.advance(grid.sim_time_s + WEATHER_TICK_INTERVAL_S)
    tick_ms = []
    for _ in range(100):
        start = time.perf_counter()
        grid.advance(grid.sim_time_s + WEATHER_TICK_INTERVAL_S)
        tick_ms.append((time.perf_counter() - start) * 1000.0)
    start = time.perf_counter()
    forecast = grid.forecast((0.0, 0.0))
    forecast_s = time.perf_counter() - start
    snapshot_bytes = len(grid.dumps().encode("utf-8"))
    ordered = sorted(tick_ms)
    print(json.dumps({
        "version": "13.2.09",
        "phase": grid.phase,
        "grid_dimensions": grid.dimensions,
        "cell_count": grid.cell_count,
        "tick_interval_sim_seconds": WEATHER_TICK_INTERVAL_S,
        "samples": len(tick_ms),
        "warmup_ticks": 5,
        "tick_mean_ms": round(statistics.mean(tick_ms), 4),
        "tick_median_ms": round(statistics.median(tick_ms), 4),
        "tick_p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))], 4),
        "forecast_points": len(forecast),
        "forecast_72h_seconds": round(forecast_s, 4),
        "snapshot_json_bytes": snapshot_bytes,
        "target_tick_ms": 2.0,
        "target_met_on_this_host": statistics.mean(tick_ms) <= 2.0,
    }, indent=2))


if __name__ == "__main__":
    main()
