import math
import unittest

from fishing_sim.world.coordinates import (
    HIGH_SEAS_PROJECTION, PHASE_B_BOUNDS_NM, PHASE_B_BOUNDS,
    wrap_longitude_delta,
)
from fishing_sim.world.seeding import stable_vessel_id
from fishing_sim.world.traffic import (
    TrafficWorld, PHASE_A_FLEET_TOTAL, PHASE_B_FLEET_TOTAL,
    SOURCE_FLEET_TOTAL, Archetype,
)
from fishing_sim.world.weather_grid import WeatherGrid, PHASE_B_COARSE_CELL_SIZE_NM
from fishing_sim.world.context import WorldContext


class PhaseBExpansionTests(unittest.TestCase):
    def test_phase_b_catalogue_matches_source_plan_population(self):
        world = TrafficWorld(1962, phase="B")
        self.assertEqual(PHASE_B_FLEET_TOTAL, SOURCE_FLEET_TOTAL)
        self.assertEqual(len(world.ships), 461)
        self.assertEqual(world.phase, "B")
        self.assertEqual(sum(s.archetype == Archetype.MOTHERSHIP for s in world.ships.values()), 11)
        self.assertEqual(sum(s.archetype == Archetype.CORPORATE_CATCHER for s in world.ships.values()), 300)
        self.assertEqual(len(TrafficWorld(1962).ships), PHASE_A_FLEET_TOTAL)

    def test_phase_b_schedule_generation_is_deterministic(self):
        a = TrafficWorld(1962, phase="B")
        b = TrafficWorld(1962, phase="B")
        self.assertEqual(
            [(s.id, s.name, s.schedule, s.period_s) for s in a.ships.values()],
            [(s.id, s.name, s.schedule, s.period_s) for s in b.ships.values()],
        )

    def test_every_phase_b_route_point_stays_in_high_seas_bounds(self):
        world = TrafficWorld(1962, phase="B")
        min_x, max_x, min_y, max_y = PHASE_B_BOUNDS_NM
        for ship in world.ships.values():
            for point in ship.schedule:
                self.assertGreaterEqual(point.x_nm, min_x - 1e-7, ship.name)
                self.assertLessEqual(point.x_nm, max_x + 1e-7, ship.name)
                self.assertGreaterEqual(point.y_nm, min_y - 1e-7, ship.name)
                self.assertLessEqual(point.y_nm, max_y + 1e-7, ship.name)

    def test_date_line_projection_is_continuous_and_round_trips(self):
        east = HIGH_SEAS_PROJECTION.to_nm(179.9, 50.0)
        west = HIGH_SEAS_PROJECTION.to_nm(-179.9, 50.0)
        self.assertLess(math.dist(east, west), 10.0)
        lon, lat = HIGH_SEAS_PROJECTION.to_lonlat(*HIGH_SEAS_PROJECTION.to_nm(-175.0, 62.0))
        self.assertAlmostEqual(lon, -175.0, places=7)
        self.assertAlmostEqual(lat, 62.0, places=7)
        self.assertAlmostEqual(wrap_longitude_delta(-175.0 - 160.0), 25.0)
        self.assertLess(PHASE_B_BOUNDS_NM[0], 0.0)
        self.assertGreater(PHASE_B_BOUNDS_NM[1], 0.0)
        self.assertEqual(PHASE_B_BOUNDS["east_lon"], -175.0)

    def test_motherships_and_corporate_catchers_are_clustered(self):
        world = TrafficWorld(1962, phase="B")
        # Stable IDs are independent of dict sorting, so compare by original index.
        for index in range(33):
            catcher = world.ships[stable_vessel_id(1962, Archetype.CORPORATE_CATCHER.value, index)]
            mothership = world.ships[stable_vessel_id(1962, Archetype.MOTHERSHIP.value, index % 11)]
            self.assertEqual(catcher.mothership_id, mothership.id)
            self.assertEqual(mothership.mothership_id, mothership.id)
            self.assertLess(math.dist(catcher.position_nm, mothership.position_nm), 100.0)

    def test_active_cap_applies_even_with_full_phase_b_fleet(self):
        world = TrafficWorld(1962, phase="B", active_cap=30)
        self.assertLessEqual(len(world.lod.active_ids), 30)
        world.advance(3.0, focus_nm=(400.0, 350.0), month=6, day=15, force=True)
        self.assertLessEqual(len(world.lod.active_ids), 30)
        self.assertEqual(len(world.ships), 461)

    def test_out_of_season_corporate_fleet_is_sparse_but_ids_survive(self):
        world = TrafficWorld(1962, phase="B")
        before_ids = set(world.ships)
        world.advance(3.0, focus_nm=(-700.0, -180.0), month=4, day=5, force=True)
        self.assertLess(len(world.index.positions), len(world.ships))
        self.assertGreater(len(world.index.positions), 0)
        self.assertEqual(set(world.ships), before_ids)
        # Persisted/known contacts stay queryable even during lay-up.
        known = next(s for s in world.ships.values() if s.archetype == Archetype.CORPORATE_CATCHER)
        known.known_to_player = True
        world.advance(6.0, focus_nm=known.position_nm, month=4, day=5, force=True)
        self.assertIn(known.id, world.index.positions)

    def test_phase_b_schedule_positions_regenerate_after_snapshot_restore(self):
        first = TrafficWorld(1962, phase="B")
        focus = HIGH_SEAS_PROJECTION.to_nm(165.0, 52.0)
        first.advance(840.0, focus_nm=focus, month=6, day=15, force=True)
        selected = next(iter(first.ships.values()))
        selected.contact_count = 1
        selected.trust = 0.45
        saved_position = selected.position_nm
        snapshot = first.snapshot_contacts()

        restored = TrafficWorld(1962, phase="B")
        restored.advance(840.0, focus_nm=focus, month=6, day=15, force=True)
        restored.restore_contacts(snapshot)
        self.assertEqual(restored.ships[selected.id].position_nm, saved_position)
        self.assertAlmostEqual(restored.ships[selected.id].trust, 0.45)
        self.assertEqual(restored.ships[selected.id].mothership_id, selected.mothership_id)

    def test_phase_tagged_contact_snapshot_roundtrip(self):
        world = TrafficWorld(1962, phase="B")
        ship = next(iter(world.ships.values()))
        ship.contact_count = 2
        ship.trust = 0.65
        snapshot = world.snapshot_contacts()
        self.assertEqual(snapshot["phase"], "B")
        restored = TrafficWorld(1962, phase="B")
        restored.restore_contacts(snapshot)
        self.assertAlmostEqual(restored.ships[ship.id].trust, 0.65)
        with self.assertRaisesRegex(ValueError, "phase does not match"):
            TrafficWorld(1962, phase="A").restore_contacts(snapshot)

    def test_phase_b_weather_bounds_cover_box_and_default_coarse_for_performance(self):
        weather = WeatherGrid(1962, phase="B")
        self.assertEqual(weather.bounds_nm, PHASE_B_BOUNDS_NM)
        self.assertEqual(weather.cell_size_nm, PHASE_B_COARSE_CELL_SIZE_NM)
        self.assertLessEqual(weather.dimensions[0] * weather.dimensions[1], 500)
        self.assertTrue(math.isfinite(weather.sample(HIGH_SEAS_PROJECTION.to_nm(-175.0, 62.0)).sea_state))
        fine = WeatherGrid(1962, phase="B", cell_size_nm=20.0)
        self.assertEqual(fine.cell_size_nm, 20.0)
        self.assertGreater(fine.dimensions[0] * fine.dimensions[1], 5000)

    def test_phase_b_weather_snapshot_roundtrip_keeps_projection_scale(self):
        weather = WeatherGrid(123, phase="B")
        weather.advance(30.0)
        restored = WeatherGrid.from_snapshot(weather.snapshot())
        self.assertEqual(restored.phase, "B")
        self.assertEqual(restored.bounds_nm, weather.bounds_nm)
        self.assertEqual(restored.cell_size_nm, weather.cell_size_nm)
        self.assertEqual(restored.sample((100.0, 500.0)), weather.sample((100.0, 500.0)))

    def test_world_context_selects_consistent_phase_b_traffic_and_weather(self):
        context = WorldContext(world_seed=1962, phase="B")
        self.assertEqual(context.traffic.phase, "B")
        self.assertEqual(len(context.traffic.ships), PHASE_B_FLEET_TOTAL)
        self.assertEqual(context.weather.phase, "B")
        focus = HIGH_SEAS_PROJECTION.to_nm(165.0, 52.0)
        context.advance(10.0, focus, month=6, day=1)
        self.assertEqual(context.traffic.sim_time_s, 10.0)
        self.assertEqual(context.weather.sim_time_s, 10.0)

    def test_unknown_phase_is_rejected(self):
        with self.assertRaises(ValueError):
            TrafficWorld(1962, phase="D")
        with self.assertRaises(ValueError):
            WorldContext(phase="D")


if __name__ == "__main__":
    unittest.main()
