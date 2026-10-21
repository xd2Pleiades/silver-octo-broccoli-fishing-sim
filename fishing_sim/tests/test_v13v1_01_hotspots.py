"""Headless acceptance tests for V13V1-01 hotspot ecology/bite integration."""
import ast
import math
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.hotspots import (
    HOTSPOT_SPECIES, MAX_ACTIVE_HOTSPOTS, Hotspot,
    find_spawn_position, hotspot_multiplier,
)


class HotspotModelTests(unittest.TestCase):
    def test_spawn_position_is_offshore_and_scaled(self):
        rng = random.Random(1962)
        pos = find_spawn_position(rng, 3.0, lambda x, y: True, attempts=8)
        self.assertIsNotNone(pos)
        distance_in_design_units = math.hypot(pos[0], pos[1]) / 3.0
        self.assertGreaterEqual(distance_in_design_units, 4000.0)
        self.assertLessEqual(distance_in_design_units, 9000.0)

    def test_spawn_retries_invalid_water_and_stops_after_attempt_limit(self):
        calls = []
        def valid_on_third_attempt(x, y):
            calls.append((x, y))
            return len(calls) >= 3
        pos = find_spawn_position(random.Random(8), 3.0, valid_on_third_attempt, attempts=8)
        self.assertIsNotNone(pos)
        self.assertEqual(len(calls), 3)

        calls.clear()
        pos = find_spawn_position(random.Random(8), 3.0,
                                  lambda x, y: calls.append((x, y)) or False,
                                  attempts=8)
        self.assertIsNone(pos)
        self.assertEqual(len(calls), 8)

    def test_hotspot_species_and_strength_are_validated_and_bounded(self):
        self.assertEqual(HOTSPOT_SPECIES,
                         ("albacore", "yellowfin", "bigeye", "swordfish", "mixed"))
        self.assertEqual(MAX_ACTIVE_HOTSPOTS, 4)
        spot = Hotspot(0, 0, "yellowfin", strength=2.0, radius=100, life=30)
        self.assertEqual(spot.strength, 1.0)
        with self.assertRaises(ValueError):
            Hotspot(0, 0, "blue shark")

    def test_hotspot_drifts_and_decays_during_final_third(self):
        spot = Hotspot(100, 200, "bigeye", strength=0.9, radius=100,
                       life=90, drift_x=3, drift_y=-2)
        self.assertTrue(spot.update(30))
        self.assertEqual(spot.pos, (190.0, 140.0))
        self.assertAlmostEqual(spot.strength_now, 0.9)
        self.assertTrue(spot.update(35))
        self.assertLess(spot.strength_now, 0.9)
        self.assertGreater(spot.strength_now, 0.0)
        self.assertFalse(spot.update(25))
        self.assertEqual(spot.strength_now, 0.0)

    def test_hotspot_reverses_drift_instead_of_crossing_land(self):
        spot = Hotspot(0, 0, "albacore", life=100, drift_x=2, drift_y=0)
        self.assertTrue(spot.update(10, is_water=lambda x, y: x < 1))
        self.assertEqual(spot.pos, (0.0, 0.0))
        self.assertEqual(spot.drift, (-2.0, -0.0))
        self.assertTrue(spot.update(1, is_water=lambda x, y: True))
        self.assertEqual(spot.pos, (-2.0, 0.0))

    def test_specific_species_has_smooth_bounded_radial_bonus(self):
        spot = Hotspot(0, 0, "yellowfin", strength=1.0, radius=100, life=100)
        self.assertAlmostEqual(hotspot_multiplier([spot], (0, 0), "yellowfin"), 2.5)
        self.assertAlmostEqual(hotspot_multiplier([spot], (50, 0), "yellowfin"), 2.125)
        self.assertEqual(hotspot_multiplier([spot], (100, 0), "yellowfin"), 1.0)
        self.assertEqual(hotspot_multiplier([spot], (101, 0), "yellowfin"), 1.0)
        self.assertEqual(hotspot_multiplier([spot], (0, 0), "bigeye"), 1.0)

    def test_mixed_school_affects_species_less_and_overlapping_spots_do_not_stack(self):
        mixed = Hotspot(0, 0, "mixed", strength=1.0, radius=100, life=100)
        self.assertAlmostEqual(hotspot_multiplier([mixed], (0, 0), "albacore"), 1.6)
        specific = Hotspot(0, 0, "bigeye", strength=1.0, radius=100, life=100)
        self.assertEqual(hotspot_multiplier([mixed, specific], (0, 0), "bigeye"), 2.5)
        self.assertLessEqual(hotspot_multiplier([mixed, specific], (0, 0), "bigeye"), 2.5)

    def test_expired_or_zero_strength_spots_have_no_effect(self):
        spot = Hotspot(0, 0, "swordfish", strength=0.0, radius=100, life=1)
        self.assertEqual(hotspot_multiplier([spot], (0, 0), "swordfish"), 1.0)
        spot.strength_now = 0.0
        self.assertEqual(hotspot_multiplier([spot], (0, 0), "swordfish"), 1.0)


class HotspotIntegrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def method_source(self, class_name, method_name):
        cls = next(n for n in self.tree.body
                   if isinstance(n, ast.ClassDef) and n.name == class_name)
        node = next(n for n in cls.body
                    if isinstance(n, ast.FunctionDef) and n.name == method_name)
        return ast.get_source_segment(self.source, node)

    def test_world_owns_hotspots_and_updates_them_without_changing_ship_position(self):
        world_init = self.method_source("World", "__init__")
        world_update = self.method_source("World", "update")
        self.assertIn("self.hotspots = []", world_init)
        self.assertIn("self.hotspot_cd = random.uniform(10.0, 18.0)", world_init)
        self.assertIn("self._update_hotspots(dt)", world_update)
        self.assertIn("self.ship_pos = nxt", world_update)
        self.assertIn("self.foam.update(", world_update)

    def test_spawner_checks_land_shallows_coast_and_reef(self):
        water_check = self.method_source("World", "_hotspot_water_ok")
        spawn = self.method_source("World", "_spawn_hotspot")
        update = self.method_source("World", "_update_hotspots")
        self.assertIn("in_poly(pos, self.land_w)", water_check)
        self.assertIn("self.bottom_m(distance) < 150.0", water_check)
        self.assertIn("coast_clearance", water_check)
        self.assertIn("reef_clearance", water_check)
        self.assertIn("attempts=48", spawn)
        self.assertIn("center = self.fishing_ground()", spawn)
        self.assertIn("for radius_units in (1400.0, 1800.0, 2300.0, 2900.0, 3600.0, 4300.0)", spawn)
        self.assertIn("self.hotspot_cd = random.uniform(6.0, 12.0)", update)
        self.assertIn("len(self.hotspots) >= MAX_ACTIVE_HOTSPOTS", update)

    def test_bite_weights_modifies_existing_ecology_weight_not_a_new_catch_roll(self):
        bite = self.method_source("Longline", "bite_weights")
        self.assertIn("temp = w.temp_at(dm, hd)", bite)
        self.assertIn("bottom = w.bottom_m(hd)", bite)
        self.assertIn("BAIT_AFF[name].get(p[\"bait\"], 0.25)", bite)
        self.assertIn("base_weight * hotspot_multiplier(w.hotspots, p[\"pos\"], name)", bite)
        self.assertNotIn("random.random", bite)


if __name__ == "__main__":
    unittest.main(verbosity=2)
