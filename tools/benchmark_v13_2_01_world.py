"""Reproducible, dependency-free micro-benchmark for the v13.2.01 traffic slice.

Run from the project root with: python tools/benchmark_v13_2_01_world.py
The timings are diagnostic, not CI thresholds; compare only on the same host/runtime.
"""
from __future__ import annotations
from time import perf_counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fishing_sim.world.traffic import TrafficWorld, PHASE_A_FLEET_TOTAL


def main() -> None:
    world = TrafficWorld(1962, active_cap=30)
    focus = (1.9, 0.7)

    start = perf_counter()
    for i in range(1000):
        # 1,000 scheduled updates, each three simulation seconds apart.
        world.advance((i + 1) * 3.0, focus_nm=focus, month=6, day=10, hour=12.0)
    tick_ms = (perf_counter() - start) * 1000.0 / 1000.0

    start = perf_counter()
    for _ in range(10000):
        world.radio_candidates(focus)
    radio_query_us = (perf_counter() - start) * 1_000_000.0 / 10000.0

    start = perf_counter()
    for _ in range(50):
        TrafficWorld(1962, active_cap=30)
    generation_ms = (perf_counter() - start) * 1000.0 / 50.0

    print(f"fleet_count={PHASE_A_FLEET_TOTAL}")
    print(f"mean_traffic_update_ms={tick_ms:.4f}")
    print(f"mean_radio_candidate_query_us={radio_query_us:.2f}")
    print(f"mean_world_generation_ms={generation_ms:.3f}")
    print(f"active_count={len(world.lod.active_ids)}")
    print(f"known_contact_count={len(world.known_contacts())}")


if __name__ == "__main__":
    main()
