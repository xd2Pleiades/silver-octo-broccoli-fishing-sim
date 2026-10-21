"""Headless tests for V13V1-10 skill-weighted crew reports and second opinions."""
import ast
import math
from pathlib import Path
import random
import statistics
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.crew_reports import (
    report_bearing, report_distance, report_speed, bearing_difference_degrees,
    SECOND_OPINION_WINDOW_SECONDS, DESIGN_UNITS_PER_NAUTICAL_MILE,
)


class CrewReportMeasurementTests(unittest.TestCase):
    def test_bearing_uses_nautical_compass_convention(self):
        origin = (0.0, 0.0)
        cases = [
            ((0.0, -10.0), 0.0),
            ((10.0, 0.0), math.pi / 2.0),
            ((0.0, 10.0), math.pi),
            ((-10.0, 0.0), 3.0 * math.pi / 2.0),
        ]
        for target, expected in cases:
            self.assertAlmostEqual(report_bearing(origin, target, 1.0, random.Random(5)), expected)

    def test_seeded_measurements_are_reproducible(self):
        self.assertEqual(
            report_bearing((0, 0), (40, -20), 0.25, random.Random(1962)),
            report_bearing((0, 0), (40, -20), 0.25, random.Random(1962)),
        )
        self.assertEqual(
            report_distance((0, 0), (555.6, 0), 3, 0.3, random.Random(1962)),
            report_distance((0, 0), (555.6, 0), 3, 0.3, random.Random(1962)),
        )
        self.assertEqual(report_speed(320, 0.2, random.Random(1962)),
                         report_speed(320, 0.2, random.Random(1962)))

    def test_higher_skill_reduces_bearing_error_variance(self):
        truth = math.pi / 2.0
        low_rng, high_rng = random.Random(1), random.Random(2)
        low = [((report_bearing((0, 0), (10, 0), 0.15, low_rng) - truth + math.pi)
                % math.tau) - math.pi for _ in range(2500)]
        high = [((report_bearing((0, 0), (10, 0), 0.85, high_rng) - truth + math.pi)
                 % math.tau) - math.pi for _ in range(2500)]
        self.assertLess(statistics.pvariance(high), statistics.pvariance(low))

    def test_higher_skill_reduces_distance_error_variance(self):
        target = (DESIGN_UNITS_PER_NAUTICAL_MILE * 3.0, 0.0)
        low_rng, high_rng = random.Random(3), random.Random(4)
        low = [report_distance((0, 0), target, 3.0, 0.1, low_rng) for _ in range(2500)]
        high = [report_distance((0, 0), target, 3.0, 0.9, high_rng) for _ in range(2500)]
        self.assertLess(statistics.pvariance(high), statistics.pvariance(low))
        self.assertAlmostEqual(statistics.mean(low), 1.0, delta=0.02)
        self.assertAlmostEqual(statistics.mean(high), 1.0, delta=0.01)

    def test_higher_skill_reduces_speed_error_variance_and_speed_is_nonnegative(self):
        low_rng, high_rng = random.Random(5), random.Random(6)
        low = [report_speed(400, 0.1, low_rng) for _ in range(2500)]
        high = [report_speed(400, 0.9, high_rng) for _ in range(2500)]
        self.assertLess(statistics.pvariance(high), statistics.pvariance(low))
        self.assertEqual(report_speed(0, 0.1, random.Random(7)), 0.0)

    def test_bearing_difference_wraps_across_north(self):
        self.assertAlmostEqual(bearing_difference_degrees(359.0, 1.0), 2.0)
        self.assertAlmostEqual(bearing_difference_degrees(10.0, 350.0), 20.0)

    def test_second_opinion_window_is_five_simulation_seconds(self):
        self.assertEqual(SECOND_OPINION_WINDOW_SECONDS, 5.0)


class CrewReportIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def method(self, class_name, name):
        cls = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
        return ast.get_source_segment(self.source, node)

    def test_requests_have_distinct_bearing_range_and_speed_keys(self):
        handle = self.method("Game", "handle")
        self.assertIn("pygame.K_i", handle)
        self.assertIn('self._request_crew_report("bearing_distance")', handle)
        self.assertIn("pygame.K_o", handle)
        self.assertIn('self._request_crew_report("speed")', handle)

    def test_observations_use_skill_weighted_functions_and_do_not_change_truth_or_belief(self):
        make = self.method("Game", "_make_crew_report")
        for name in ("report_bearing", "report_distance", "report_speed"):
            self.assertIn(name, make)
        self.assertNotIn("ship_pos =", make)
        self.assertNotIn("believed_pos =", make)

    def test_report_requires_an_able_main_deck_sailor(self):
        eligible = self.method("Game", "_crew_report_eligible")
        self.assertIn("sailor.mode == Sailor.ABOARD", eligible)
        self.assertIn("sailor.level == Level.MAIN", eligible)
        self.assertIn("sailor.ladder is None", eligible)
        self.assertIn("sailor.health > 0.0", eligible)

    def test_second_opinion_reuses_the_original_kind_and_target(self):
        second = self.method("Game", "_try_second_opinion")
        self.assertIn("pending[\"kind\"]", second)
        self.assertIn("pending[\"target_name\"]", second)
        self.assertIn("pending[\"target_design\"]", second)
        self.assertIn("pending[\"deadline\"]", second)
        self.assertIn("self._crew_report_comparison(first, second)", second)
        update = self.method("Game", "update")
        self.assertIn('w.time >= self.crew_report_pending["deadline"]', update)

    def test_clicking_a_different_sailor_triggers_second_opinion(self):
        handle = self.method("Game", "handle")
        self.assertIn("self._try_second_opinion(hit)", handle)
        self.assertIn("self.select(hit)", handle)

    def test_comparison_panel_does_not_expose_true_position_or_error_vector(self):
        panel = self.method("Game", "draw_crew_report_panel")
        comparison = self.method("Game", "_crew_report_comparison")
        for forbidden in ("ship_pos", "believed_pos", "position_error"):
            self.assertNotIn(forbidden, panel)
            self.assertNotIn(forbidden, comparison)
        self.assertIn("BROADLY CONSISTENT", comparison)
        self.assertIn("READINGS DISAGREE", comparison)

    def test_controls_advertise_both_report_actions(self):
        hud = self.method("Game", "draw_hud")
        self.assertIn("I bearing/range report", hud)
        self.assertIn("O speed report", hud)
        self.assertIn("second opinion", hud)


if __name__ == "__main__":
    unittest.main(verbosity=2)
