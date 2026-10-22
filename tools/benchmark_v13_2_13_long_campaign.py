#!/usr/bin/env python3
"""Fixed-seed subsystem stress benchmark for v13.2 release hardening.

This is deliberately not described as a full rendered-frame benchmark. It drives
traffic/weather on their simulation-time cadence and records timing distributions,
snapshot size and candidate-query cost for a reproducible campaign duration.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from fishing_sim.world.traffic import TrafficWorld
from fishing_sim.world.weather_grid import WeatherGrid

SIM_SECONDS_PER_GAME_DAY = 600.0


def summary(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    if not ordered:
        return {"count": 0, "mean_ms": 0.0, "median_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        "count": len(ordered),
        "mean_ms": statistics.fmean(ordered) * 1000.0,
        "median_ms": statistics.median(ordered) * 1000.0,
        "p95_ms": ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)] * 1000.0,
        "max_ms": ordered[-1] * 1000.0,
    }


def measure(fn: Callable[[], object], samples: list[float]) -> object:
    start = time.perf_counter()
    result = fn()
    samples.append(time.perf_counter() - start)
    return result


def run(days: int, phase: str) -> dict:
    if days < 1 or days > 365:
        raise ValueError("days must be in 1..365")
    phase = phase.upper()
    world_create: list[float] = []
    traffic_ticks: list[float] = []
    radio_queries: list[float] = []
    weather_ticks: list[float] = []
    snapshots: list[float] = []
    traffic = measure(lambda: TrafficWorld(world_seed=1962, phase=phase), world_create)
    grid = WeatherGrid(world_seed=1962, phase=phase)
    # Give the long-campaign snapshot a repeatable set of contacted vessels;
    # otherwise the contact-delta serialization would measure the empty baseline only.
    sampled_ships = list(traffic.ships.values())
    contact_stride = max(1, len(sampled_ships) // 8)
    known_ships = sampled_ships[::contact_stride][:8]
    for idx, ship in enumerate(known_ships):
        ship.trust = round(-0.25 + idx * 0.07, 3)
        ship.contact_count = idx + 1
        ship.known_to_player = True
        ship.last_contact_sim_time = 0.0
        ship.report_position(0.0, error_nm=0.2 + idx * 0.05)
        traffic.mark_known(ship.id)
    total_s = days * SIM_SECONDS_PER_GAME_DAY
    t = 0.0
    next_radio = 0.0
    while t <= total_s + 1e-9:
        sim_t = t
        if t % 3.0 < 1e-8:
            measure(lambda sim_t=sim_t: traffic.advance(
                sim_t, focus_nm=(0.0, 0.0), month=(6 if phase == "B" else 4), day=1), traffic_ticks)
        if t % 5.0 < 1e-8:
            measure(lambda sim_t=sim_t: grid.advance(sim_t), weather_ticks)
        if t + 1e-8 >= next_radio:
            measure(lambda: traffic.radio_candidates((0.0, 0.0)), radio_queries)
            next_radio += 30.0
        if t > 0 and abs((t % SIM_SECONDS_PER_GAME_DAY)) < 1e-8:
            # Simulate a fresh check-in from known contacts once per in-game day.
            for idx, ship in enumerate(known_ships):
                ship.contact_count += 1
                ship.last_contact_sim_time = t
                ship.report_position(t, error_nm=0.2 + idx * 0.05)
            start = time.perf_counter()
            # Serialize both deterministic world contact deltas and regional weather.
            payload = {"traffic": traffic.snapshot_contacts(), "weather": grid.snapshot()}
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            snapshots.append(time.perf_counter() - start)
        t += 1.0
    final_payload = {"traffic": traffic.snapshot_contacts(), "weather": grid.snapshot()}
    final_size = len(json.dumps(final_payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
    return {
        "version": "13.2.13",
        "seed": 1962,
        "phase": phase,
        "campaign_days_simulated": days,
        "vessel_count": len(traffic.ships),
        "active_cap": traffic.lod.active_cap,
        "active_count": len(traffic.lod.active_ids),
        "weather_cells": len(grid.cells),
        "simulation_time_s": traffic.sim_time_s,
        "benchmark_scope": "world subsystem tick/query/save snapshot only; no Pygame rendering",
        "timings": {
            "world_generation": summary(world_create),
            "traffic_tick": summary(traffic_ticks),
            "radio_candidate_query": summary(radio_queries),
            "weather_tick": summary(weather_ticks),
            "daily_snapshot_serialize": summary(snapshots),
        },
        "final_traffic_contact_count": len(final_payload["traffic"].get("contacts", {})),
        "benchmarked_known_contacts": len(known_ships),
        "final_weather_snapshot_bytes": len(json.dumps(grid.snapshot(), separators=(",", ":"), allow_nan=False).encode("utf-8")),
        "combined_snapshot_bytes": final_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--phase", choices=("A", "B"), default="A")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = run(args.days, args.phase)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
