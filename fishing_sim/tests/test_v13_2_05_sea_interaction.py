from __future__ import annotations
import math
import unittest
from pathlib import Path

from fishing_sim.systems.sea_interaction import (
    FloodingModel, HullWaveInteraction, RippleSystem, deck_to_world,
)


class FloatingModel:
    def __init__(self):
        self.flood = 0.0
        self.engine_flood = 0.0
        self.hold_flood = 0.0


class SeaInteractionTests(unittest.TestCase):
    def test_deck_to_world_is_heading_relative(self):
        x, y = deck_to_world(10.0, 20.0, math.pi / 2, 5.0, 0.0)
        self.assertAlmostEqual(x, 10.0, places=6)
        self.assertAlmostEqual(y, 25.0, places=6)

    def test_calm_flat_sea_does_not_overtop_hull(self):
        hull = HullWaveInteraction(length=400.0, beam=100.0)
        for _ in range(120):
            strikes = hull.update(0.05, ship_position=(0.0, 0.0), heading=0.0,
                                  wave_height=lambda x, y: 0.0)
            self.assertFalse(any(s.kind == "overtop" for s in strikes))
        self.assertEqual(hull.overtops_total, 0)

    def test_wave_interaction_produces_finite_values_and_bounded_events(self):
        hull = HullWaveInteraction(length=400.0, beam=100.0)
        strikes_seen = []
        def wave(x, y):
            return 190.0 * math.sin(x * 0.014 + y * 0.003) + 30.0 * math.sin(y * 0.025)
        for i in range(300):
            strikes_seen.extend(hull.update(0.04, ship_position=(i * 1.1, 0.0), heading=0.2,
                                            wave_height=wave, freeboard_factor=0.75, list_bias=0.1))
        self.assertTrue(all(math.isfinite(s.energy) and 0.0 <= s.energy <= 1.0 for s in strikes_seen))
        self.assertLessEqual(hull.strikes_total, 100)
        self.assertGreaterEqual(min(hull.immersion.values()), 0.0)

    def test_boarding_water_reduces_reserve_and_changes_list(self):
        ship = FloatingModel()
        FloodingModel.attach(ship)
        before = FloodingModel.reserve_buoyancy(ship)
        added = FloodingModel.boarded(ship, "stbd", 0.8)
        after = FloodingModel.reserve_buoyancy(ship)
        self.assertGreater(added, 0.0)
        self.assertLess(after, before)
        self.assertGreater(ship.list_lat, 0.0)

    def test_engine_bilge_pump_reduces_engine_and_hold_water(self):
        ship = FloatingModel()
        FloodingModel.attach(ship)
        ship.engine_flood = 0.5
        ship.hold_flood = 0.2
        report = FloodingModel.step(ship, 10.0, sea=0.1, slope_y=0.0,
                                   engine_hatch_open=False, open_hold_hatches=0,
                                   pump_power=1.0, immersion=0.0)
        self.assertLess(ship.engine_flood, 0.5)
        self.assertGreaterEqual(ship.hold_flood, 0.0)
        self.assertGreater(report.pump_flow, 0.0)
        self.assertGreaterEqual(report.reserve, 0.0)
        self.assertLessEqual(report.reserve, 1.0)

    def test_critical_flooding_is_reported(self):
        ship = FloatingModel()
        FloodingModel.attach(ship)
        ship.engine_flood = 0.96
        report = FloodingModel.step(ship, 0.5, sea=1.0, slope_y=0.8,
                                   engine_hatch_open=True, open_hold_hatches=2,
                                   pump_power=0.0, immersion=1.0)
        self.assertIn(report.state, {"FLOODED", "CRITICAL"})
        self.assertLess(report.reserve, 0.65)

    def test_ripples_respect_strict_cap(self):
        ripples = RippleSystem(max_ripples=8, seed=5)
        for i in range(100):
            ripples.emit(float(i), 0.0, 0.5)
        self.assertLessEqual(ripples.active_count, 8)

    def test_game_has_hull_wave_update_and_flood_report_wiring(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "core" / "game.py").read_text(encoding="utf-8")
        self.assertIn("def _update_hull_waves", source)
        self.assertIn("FloodingModel.step(", source)
        self.assertIn("def _apply_hull_strikes", source)
        self.assertIn("self.deck_foam", source)


if __name__ == "__main__":
    unittest.main()
