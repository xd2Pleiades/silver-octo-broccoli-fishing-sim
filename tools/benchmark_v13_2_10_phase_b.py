"""Repeatable Phase B world microbenchmark (stdlib only).

Run from repository root: python tools/benchmark_v13_2_10_phase_b.py
Results are workload diagnostics, not a frame-rate claim.
"""
from __future__ import annotations
import statistics
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fishing_sim.world.coordinates import HIGH_SEAS_PROJECTION
from fishing_sim.world.traffic import TrafficWorld, PHASE_B_FLEET_TOTAL
from fishing_sim.world.weather_grid import WeatherGrid, WEATHER_TICK_INTERVAL_S


def timed_ms(call, count: int) -> tuple[float, float, float]:
    samples = []
    for _ in range(count):
        t0 = time.perf_counter()
        call()
        samples.append((time.perf_counter() - t0) * 1000.0)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    return statistics.mean(samples), statistics.median(samples), p95


def main() -> None:
    t0 = time.perf_counter()
    traffic = TrafficWorld(1962, phase="B", active_cap=30)
    generation_ms = (time.perf_counter() - t0) * 1000.0
    # Anchor the benchmark near a mothership cluster to exercise nearby LOD promotion.
    focus = next(s.position_nm for s in traffic.ships.values() if s.archetype.value == "mothership")
    traffic.advance(3.0, focus_nm=focus, month=6, day=15, force=True)
    tick = [0]
    def update_traffic():
        tick[0] += 3
        traffic.advance(float(tick[0] + 3), focus_nm=focus, month=6, day=15, force=True)
    traffic_mean, traffic_median, traffic_p95 = timed_ms(update_traffic, 100)
    radio_mean, radio_median, radio_p95 = timed_ms(lambda: traffic.radio_candidates(focus), 250)

    weather = WeatherGrid(1962, phase="B")
    for _ in range(5):
        weather.advance(weather.sim_time_s + WEATHER_TICK_INTERVAL_S)
    weather_mean, weather_median, weather_p95 = timed_ms(
        lambda: weather.advance(weather.sim_time_s + WEATHER_TICK_INTERVAL_S), 100)
    t0 = time.perf_counter()
    forecast = weather.forecast(focus, horizon_hours=72.0)
    forecast_s = time.perf_counter() - t0
    snapshot_bytes = len(weather.dumps().encode("utf-8"))

    print(f"Phase B vessels: {len(traffic.ships)} (expected {PHASE_B_FLEET_TOTAL})")
    print(f"In-season indexed vessels: {len(traffic.index.positions)}")
    print(f"Active cap: {traffic.lod.active_cap}; current active: {len(traffic.lod.active_ids)}")
    print(f"Weather cells: {weather.dimensions[0]} x {weather.dimensions[1]} = {len(weather.cells)} at {weather.cell_size_nm:g} NM")
    print(f"Fleet generation: {generation_ms:.3f} ms")
    print(f"Traffic tick mean/median/p95: {traffic_mean:.4f}/{traffic_median:.4f}/{traffic_p95:.4f} ms")
    print(f"Radio query mean/median/p95: {radio_mean:.4f}/{radio_median:.4f}/{radio_p95:.4f} ms")
    print(f"Weather tick mean/median/p95: {weather_mean:.4f}/{weather_median:.4f}/{weather_p95:.4f} ms")
    print(f"72-hour forecast: {forecast_s:.4f} s ({len(forecast)} points)")
    print(f"Weather snapshot: {snapshot_bytes} bytes")

if __name__ == "__main__":
    main()
