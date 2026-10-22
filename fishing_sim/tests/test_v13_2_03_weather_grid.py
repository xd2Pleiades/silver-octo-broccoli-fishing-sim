"""Dependency-free tests for the v13.2.03 regional weather grid."""
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from fishing_sim.world.weather_grid import (
    WeatherGrid, WeatherCell, WEATHER_TICK_INTERVAL_S, WEATHER_SCHEMA_VERSION,
)
from fishing_sim.world.context import WorldContext
from fishing_sim.world.persistence import dumps_weather_snapshot, restore_weather_snapshot
from fishing_sim.world.traffic import TrafficWorld, Archetype
from fishing_sim.systems.ship_radio import ShipRadioService

ROOT = Path(__file__).resolve().parents[1]


class AlwaysAnswerRng:
    def __init__(self, *_args, **_kwargs): pass
    def random(self): return 0.0
    def uniform(self, a, b): return (float(a) + float(b)) / 2.0
    def randrange(self, n): return 0


class WeatherGridTests(unittest.TestCase):
    def setUp(self):
        self.grid = WeatherGrid(world_seed=1962, phase="A")

    def test_phase_a_grid_uses_twenty_nm_cells_and_covers_region(self):
        self.assertEqual(self.grid.cell_size_nm, 20.0)
        self.assertGreater(self.grid.cell_count, 300)
        self.assertGreater(self.grid.dimensions[0], 15)
        self.assertGreater(self.grid.dimensions[1], 10)

    def test_initialization_is_seed_deterministic(self):
        other = WeatherGrid(world_seed=1962, phase="A")
        self.assertEqual(self.grid.dumps(), other.dumps())
        self.assertNotEqual(self.grid.dumps(), WeatherGrid(world_seed=1963, phase="A").dumps())

    def test_weather_sample_is_finite_and_normalized(self):
        for pos in ((0.0, 0.0), (-210.0, -100.0), (210.0, 250.0), (900.0, -900.0)):
            sample = self.grid.sample(pos)
            values = (sample.pressure_hpa, sample.wind_u_kt, sample.wind_v_kt,
                      sample.precipitation, sample.cloud, sample.fog, sample.sea_state)
            self.assertTrue(all(math.isfinite(v) for v in values))
            for value in (sample.precipitation, sample.cloud, sample.fog, sample.sea_state):
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)
            self.assertTrue(sample.phrase)

    def test_fixed_tick_does_not_run_early(self):
        self.assertFalse(self.grid.advance(WEATHER_TICK_INTERVAL_S - 0.01))
        self.assertEqual(self.grid.tick_count, 0)
        self.assertTrue(self.grid.advance(WEATHER_TICK_INTERVAL_S))
        self.assertEqual(self.grid.tick_count, 1)
        self.assertFalse(self.grid.advance(WEATHER_TICK_INTERVAL_S + 0.01))
        self.assertEqual(self.grid.tick_count, 1)

    def test_fast_forward_and_incremental_steps_match_exactly(self):
        fast = WeatherGrid(1962)
        slow = WeatherGrid(1962)
        target = 5.0 * 24.0
        fast.advance(target)
        for t in range(5, int(target) + 1, 5):
            slow.advance(float(t))
        self.assertEqual(fast.snapshot(), slow.snapshot())

    def test_snapshot_roundtrip_preserves_all_state_and_future(self):
        self.grid.advance(117.3)
        self.grid.observe_local((1.0, 1.0), cloud=0.9, precipitation=0.7, fog=0.2,
                                wind_speed_kt=24.0, wind_direction_rad=1.2, sea_state=0.8)
        data = dumps_weather_snapshot(self.grid)
        clone = WeatherGrid.loads(data)
        self.assertEqual(self.grid.snapshot(), clone.snapshot())
        self.grid.advance(150.0)
        clone.advance(150.0)
        self.assertEqual(self.grid.snapshot(), clone.snapshot())

    def test_restore_into_matching_grid_and_reject_bad_schema(self):
        self.grid.advance(15.0)
        payload = self.grid.snapshot()
        other = WeatherGrid(1962)
        restore_weather_snapshot(other, payload)
        self.assertEqual(self.grid.snapshot(), other.snapshot())
        bad = dict(payload, schema_version=WEATHER_SCHEMA_VERSION + 1)
        with self.assertRaises(ValueError):
            other.restore(bad)

    def test_invalid_cell_fields_are_rejected(self):
        payload = self.grid.snapshot()
        payload["cells"] = [row[:] for row in payload["cells"]]
        payload["cells"][0][5] = float("nan")
        with self.assertRaises(ValueError):
            WeatherGrid.from_snapshot(payload)

    def test_forecast_has_zero_to_seventy_two_hour_points(self):
        points = self.grid.forecast((0.0, 0.0))
        self.assertEqual(points[0].hours_ahead, 0.0)
        self.assertEqual(points[-1].hours_ahead, 72.0)
        self.assertEqual(len(points), 13)
        self.assertTrue(all(points[i].hours_ahead < points[i + 1].hours_ahead
                            for i in range(len(points) - 1)))

    def test_forecast_does_not_mutate_live_weather_or_tick(self):
        self.grid.advance(127.0)
        before = self.grid.snapshot()
        self.grid.forecast((3.0, -2.0), horizon_hours=72.0, step_hours=6.0)
        self.assertEqual(before, self.grid.snapshot())

    def test_forecast_weather_evolves_and_uses_copy_state(self):
        points = self.grid.forecast((0.0, 0.0), horizon_hours=72.0, step_hours=12.0)
        self.assertEqual(len(points), 7)
        self.assertTrue(any(abs(p.sample.pressure_hpa - points[0].sample.pressure_hpa) > 0.01
                            for p in points[1:]))

    def test_local_observation_is_authoritative(self):
        self.grid.observe_local((0.0, 0.0), cloud=0.91, precipitation=0.82, fog=0.73,
                                wind_speed_kt=18.0, wind_direction_rad=0.0, sea_state=0.88)
        sample = self.grid.cells[self.grid.cell_for((0.0, 0.0))]
        self.assertAlmostEqual(sample.cloud, 0.91)
        self.assertAlmostEqual(sample.precipitation, 0.82)
        self.assertAlmostEqual(sample.sea_state, 0.88)

    def test_world_context_advances_traffic_and_weather(self):
        world = WorldContext(world_seed=1962)
        self.assertIsNotNone(world.weather)
        self.assertIsNotNone(world.traffic)
        world.advance(10.0, (0.0, 0.0))
        self.assertEqual(world.weather.tick_count, 2)
        self.assertEqual(world.traffic.sim_time_s, 10.0)

    def test_package_version_updated(self):
        self.assertIn('__version__ = "13.2.05"', (ROOT / "__init__.py").read_text(encoding="utf-8"))


class RadioWeatherIntegrationTests(unittest.TestCase):
    def test_selected_ship_weather_reply_uses_remote_grid_sample(self):
        fleet = TrafficWorld(1962)
        ship = next(s for s in fleet.ships.values() if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        ship.position_nm = (0.5, 0.0)
        service = ShipRadioService(1962)
        with patch("fishing_sim.systems.ship_radio.random.Random", AlwaysAnswerRng):
            exchange = service.interact(
                ship, "weather", player_name="Kōei Maru", player_port="Hakodate",
                player_position_nm=(0.0, 0.0), sim_time_s=30.0, sea_state=0.1,
                weather_phrase="fair player conditions", responder_sea_state=0.85,
                responder_weather_phrase="heavy swell and poor working conditions",
                radio_clarity=1.0)
        self.assertTrue(exchange.delivered)
        self.assertIn("heavy swell and poor working conditions", exchange.turns[0][2])

    def test_radio_remote_weather_parameters_remain_optional(self):
        # Existing callers can omit the remote weather fields without breaking API compatibility.
        fleet = TrafficWorld(1962)
        ship = next(s for s in fleet.ships.values() if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        ship.position_nm = (0.1, 0.1)
        service = ShipRadioService(1962)
        with patch("fishing_sim.systems.ship_radio.random.Random", AlwaysAnswerRng):
            exchange = service.interact(ship, "weather", player_name="Kōei Maru", player_port="Hakodate",
                                        player_position_nm=(0, 0), sim_time_s=10,
                                        sea_state=0.1, weather_phrase="clear", radio_clarity=1.0)
        self.assertTrue(exchange.delivered)
        self.assertIn("clear", exchange.turns[0][2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
