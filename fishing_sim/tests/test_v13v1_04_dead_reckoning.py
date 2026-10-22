"""Headless model and source-contract tests for V13V1-04 navigation belief."""
import ast
from pathlib import Path
import math
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.dead_reckoning import (
    advance_belief, dr_error_rate, evolve_biases, format_fix_age,
    MAX_COMPASS_BIAS, MAX_LOG_BIAS,
)


class DeadReckoningModelTests(unittest.TestCase):
    def test_belief_uses_estimated_heading_and_speed_without_touching_truth(self):
        true_position = (100.0, 50.0)
        bx, by, heading, speed = advance_belief(
            0.0, 0.0, 0.0, 10.0, 2.0, math.pi / 2, 0.1
        )
        self.assertAlmostEqual(bx, 0.0, places=7)
        self.assertAlmostEqual(by, 22.0, places=7)
        self.assertAlmostEqual(heading, math.pi / 2)
        self.assertAlmostEqual(speed, 11.0)
        self.assertEqual(true_position, (100.0, 50.0))

    def test_zero_or_negative_dt_cannot_advance_belief(self):
        for dt in (0.0, -2.0):
            self.assertEqual(advance_belief(8, 9, 1.2, 100, dt, 0.1, 0.01)[:2], (8.0, 9.0))

    def test_biases_are_bounded_and_reproducible(self):
        one = random.Random(1962)
        two = random.Random(1962)
        a = evolve_biases(0.01, 0.01, 4.0, one)
        b = evolve_biases(0.01, 0.01, 4.0, two)
        self.assertEqual(a, b)
        self.assertLessEqual(abs(a[0]), MAX_COMPASS_BIAS)
        self.assertLessEqual(abs(a[1]), MAX_LOG_BIAS)
        self.assertEqual(evolve_biases(*a, 0.0, one), a)

    def test_doubt_growth_worsens_with_weather_night_and_low_skill(self):
        fair_skilled = dr_error_rate(0.9, 0.1, 1.0, 0.0, 0.0)
        fair_green = dr_error_rate(0.15, 0.1, 1.0, 0.0, 0.0)
        fog_night = dr_error_rate(0.15, 0.9, 0.0, 1.0, 0.7)
        self.assertGreater(fair_green, fair_skilled)
        self.assertGreater(fog_night, fair_green)
        self.assertAlmostEqual(fair_skilled, (10 / 60) * 1.1 * 1.1)

    def test_uncorrected_travel_accumulates_belief_error_and_doubt(self):
        rng = random.Random(404)
        truth_x = truth_y = belief_x = belief_y = 0.0
        compass_bias = log_bias = 0.0
        true_heading, true_speed, dt = 0.3, 120.0, 1.0 / 60.0
        doubt = 0.0
        for _ in range(600):
            compass_bias, log_bias = evolve_biases(compass_bias, log_bias, dt, rng)
            belief_x, belief_y, _heading, _speed = advance_belief(
                belief_x, belief_y, true_heading, true_speed, dt, compass_bias, log_bias
            )
            truth_x += math.cos(true_heading) * true_speed * dt
            truth_y += math.sin(true_heading) * true_speed * dt
            doubt += dr_error_rate(0.7, 0.3, 1.0, 0.0, 0.0) * dt
        self.assertGreater(math.hypot(belief_x - truth_x, belief_y - truth_y), 0.01)
        self.assertGreater(doubt, 0.0)
        # The model computes a parallel estimate; the truth variables advance independently.
        self.assertAlmostEqual(truth_x, math.cos(true_heading) * true_speed * 10.0, places=6)
        self.assertAlmostEqual(truth_y, math.sin(true_heading) * true_speed * 10.0, places=6)

    def test_fix_age_formatting_is_compact(self):
        self.assertEqual(format_fix_age(-4), "0s")
        self.assertEqual(format_fix_age(39), "39s")
        self.assertEqual(format_fix_age(134), "2m14s")
        self.assertEqual(format_fix_age(8050), "2h14m")


class DeadReckoningIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def method(self, class_name, name):
        cls = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
        return ast.get_source_segment(self.source, node)

    def test_world_initializes_parallel_belief_and_hidden_error(self):
        init = self.method("World", "__init__")
        for field in ("believed_pos", "believed_heading", "believed_speed", "last_fix",
                      "position_error", "compass_bias", "log_bias", "dr_uncertainty"):
            self.assertIn("self.%s" % field, init)

    def test_dead_reckoning_never_writes_physical_ship_position(self):
        update = self.method("World", "update")
        dr = self.method("World", "_update_dead_reckoning")
        self.assertIn("self.ship_pos = nxt", update)
        self.assertIn("self._update_dead_reckoning(dt, helm_ok)", update)
        self.assertIn("self.believed_pos = V(bx, by)", dr)
        self.assertIn("self.position_error = self.believed_pos - self.ship_pos", dr)
        self.assertNotIn("self.ship_pos =", dr)

    def test_fix_resets_belief_bias_and_uncertainty(self):
        fix = self.method("World", "reset_position_fix")
        for field in ("self.believed_pos = V(self.ship_pos)", "self.position_error = V(0, 0)",
                      "self.compass_bias = 0.0", "self.log_bias = 0.0", "self.dr_uncertainty = 0.0",
                      "self.last_fix = self.time"):
            self.assertIn(field, fix)

    def test_chart_and_navigation_hud_show_belief_not_true_position(self):
        chart = self.method("Game", "draw_navigation_chart")
        telemetry = self.method("Game", "_compact_hud_lines")
        sheet = self.method("Game", "_information_sheet_rows")
        self.assertIn("V(w.believed_pos) / w.scale", chart)
        self.assertIn("w.believed_heading", chart)
        self.assertIn("w.dr_uncertainty", chart)
        self.assertNotIn("w.ship_pos", chart)
        self.assertIn("w.believed_speed", telemetry)
        self.assertIn("w.believed_heading", telemetry)
        self.assertIn("self._dr_telemetry_line()", telemetry)
        self.assertIn("NAVIGATION DOUBT", sheet)

    def test_hook_depth_profile_is_shifted_down_exactly_twenty_pixels(self):
        profile = self.method("Game", "draw_profile")
        resize = self.method("Game", "resize")
        self.assertIn("pygame.Rect(W - profile_w - 10, 82, profile_w, 110)", profile)
        self.assertIn("self.profile_rect = pygame.Rect(W - 250, 82, 240, 110)", resize)

    def test_tow_and_berth_reset_known_position(self):
        dock = self.method("World", "_dock")
        tow = self.method("Game", "tow_in")
        self.assertIn('self.reset_position_fix("BERTH")', dock)
        # Tow placement is continuous; the known-position reset occurs only at
        # arrival, not when the Coast Guard first takes the line.
        transit = self.method("Game", "_update_tow_transit")
        self.assertNotIn("w.ship_pos =", tow)
        self.assertIn('w.reset_position_fix("TOW ARRIVAL")', transit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
