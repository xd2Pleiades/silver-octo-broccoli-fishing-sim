"""Headless behavior tests for V13V1-09 navigation position fixes."""
import ast
import math
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.navigation_fixes import (
    assess_landmark_bearing, assess_sextant, assess_rdf, assess_echo_sounder,
    charted_depth_at, sample_position_error, sample_rdf_error,
    RDF_MAX_RANGE_UNITS, SOUNDER_MATCH_TOLERANCE_M,
)


class LandmarkFixTests(unittest.TestCase):
    def test_landmark_requires_a_deck_observer(self):
        check = assess_landmark_bearing(300, 10, 0.9, 0.1, False)
        self.assertFalse(check.available)
        self.assertEqual(check.reason, "NEED DECK OBSERVER")

    def test_landmark_must_be_within_weather_visibility(self):
        self.assertFalse(assess_landmark_bearing(1500, 2, 0.8, 0.2, True).available)
        self.assertTrue(assess_landmark_bearing(1500, 8, 0.8, 0.2, True).available)

    def test_landmark_accuracy_improves_with_skill_and_calm_sea(self):
        expert = assess_landmark_bearing(1800, 10, 0.9, 0.1, True)
        green = assess_landmark_bearing(1800, 10, 0.2, 0.8, True)
        self.assertLess(expert.accuracy_units, green.accuracy_units)

    def test_landmark_accuracy_has_a_finite_floor(self):
        check = assess_landmark_bearing(0, 10, 1.0, 0.0, True)
        self.assertGreater(check.accuracy_units, 0)


class SextantFixTests(unittest.TestCase):
    def test_only_dawn_noon_and_dusk_windows_allow_sun_sight(self):
        for hour in (6.0, 12.0, 18.0):
            self.assertTrue(assess_sextant(hour, 0.2, 0.8, True).available)
        for hour in (2.0, 8.0, 15.0, 21.0):
            self.assertFalse(assess_sextant(hour, 0.2, 0.8, True).available)

    def test_cloud_and_minimum_skill_conditions_are_enforced(self):
        self.assertEqual(assess_sextant(12, 0.8, 0.8, True).reason, "SKY TOO OVERCAST")
        self.assertEqual(assess_sextant(12, 0.2, 0.3, True).reason, "OBSERVER SKILL BELOW 0.40")
        self.assertEqual(assess_sextant(12, 0.2, 0.8, False).reason, "NEED DECK OBSERVER")

    def test_sextant_accuracy_improves_with_skill(self):
        self.assertLess(assess_sextant(12, 0.2, 0.9, True).accuracy_units,
                        assess_sextant(12, 0.2, 0.4, True).accuracy_units)


class RadioDirectionFixTests(unittest.TestCase):
    def test_rdf_requires_staffed_working_set(self):
        check = assess_rdf(400, False, 0.9)
        self.assertFalse(check.available)
        self.assertEqual(check.reason, "RADIO SET UNATTENDED")

    def test_rdf_requires_skill_and_coastal_range(self):
        self.assertEqual(assess_rdf(400, True, 0.2).reason, "RADIO OPERATOR SKILL BELOW 0.40")
        self.assertEqual(assess_rdf(RDF_MAX_RANGE_UNITS + 0.1, True, 0.9).reason,
                         "COAST STATION OUT OF RANGE")
        self.assertTrue(assess_rdf(RDF_MAX_RANGE_UNITS, True, 0.9).available)

    def test_rdf_error_is_reproducible_and_more_uncertain_along_bearing(self):
        a = sample_rdf_error(14, math.pi / 3, random.Random(1962))
        b = sample_rdf_error(14, math.pi / 3, random.Random(1962))
        self.assertEqual(a, b)
        self.assertAlmostEqual(a[2], 42.0)
        # Over multiple samples, the long-axis variance should exceed the cross-track variance.
        rng = random.Random(72)
        along, across = [], []
        angle = math.pi / 3
        for _ in range(1000):
            dx, dy, _uncertainty = sample_rdf_error(10, angle, rng)
            across.append(dx * math.cos(angle) + dy * math.sin(angle))
            along.append(dx * math.cos(angle + math.pi / 2) + dy * math.sin(angle + math.pi / 2))
        mean_a = sum(along) / len(along)
        mean_c = sum(across) / len(across)
        var_a = sum((v - mean_a) ** 2 for v in along) / len(along)
        var_c = sum((v - mean_c) ** 2 for v in across) / len(across)
        self.assertGreater(var_a, var_c * 10)


class SounderTests(unittest.TestCase):
    def test_charted_depth_is_stable_and_uses_old_survey_noise(self):
        bottom = lambda distance: 25 + 700 * min(1.0, max(0.0, distance / 4500.0))
        first = charted_depth_at(800, -300, bottom)
        second = charted_depth_at(800, -300, bottom)
        self.assertEqual(first, second)
        base = bottom(math.hypot(800, -300))
        self.assertGreaterEqual(first, base * 0.93)
        self.assertLessEqual(first, base * 1.07)

    def test_sounder_mismatch_is_a_warning_not_a_fix(self):
        check = assess_echo_sounder(640, 610, True)
        self.assertFalse(check.available)
        self.assertEqual(check.reason, "SOUNDING MISMATCH")
        self.assertEqual(check.accuracy_units, 30)

    def test_sounder_requires_charted_water_and_match_tolerance(self):
        self.assertFalse(assess_echo_sounder(30, 30, False).available)
        self.assertEqual(assess_echo_sounder(30, 34, True).reason, "SOUNDING MATCH")
        self.assertEqual(assess_echo_sounder(30, 34.01, True).reason, "SOUNDING MISMATCH")
        self.assertEqual(SOUNDER_MATCH_TOLERANCE_M, 4.0)


class FixModelIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def method(self, class_name, name):
        cls = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
        return ast.get_source_segment(self.source, node)

    def test_fix_actions_are_available_from_chart_number_keys(self):
        handle = self.method("Game", "handle")
        self.assertIn("pygame.K_1", handle)
        self.assertIn("self._attempt_navigation_fix(fix_kind)", handle)
        chart = self.method("Game", "draw_navigation_chart")
        self.assertIn("POSITION FIXES (PRESS 1–4)", chart)
        self.assertIn("FIX 1 LANDMARK  2 SEXTANT  3 RDF  4 SOUNDER", chart)

    def test_approximate_fix_changes_belief_but_never_ship_truth(self):
        apply = self.method("World", "apply_approximate_position_fix")
        self.assertIn("self.believed_pos = V(estimate)", apply)
        self.assertIn("self.position_error = self.believed_pos - self.ship_pos", apply)
        self.assertNotIn("self.ship_pos =", apply)
        self.assertIn("self.dr_uncertainty = max(0.0, float(accuracy_world_units))", apply)

    def test_sounder_mismatch_branch_does_not_reset_or_correct_position(self):
        attempt = self.method("Game", "_attempt_navigation_fix")
        sounder = attempt.split('elif kind == "sounder":', 1)[1]
        mismatch = sounder.split('self.chart_status = "SOUNDER MISMATCH', 1)[1]
        self.assertIn("no correction applied", mismatch)
        self.assertNotIn('w.reset_position_fix("ECHO SOUNDER")', mismatch)
        self.assertIn('w.reset_position_fix("ECHO SOUNDER")', sounder.split("return True", 1)[0])

    def test_every_method_has_cooldown_and_logs_success_or_mismatch(self):
        init = self.method("Game", "__init__")
        attempt = self.method("Game", "_attempt_navigation_fix")
        self.assertIn('"sextant": 45.0', init)
        self.assertIn("self.navigation_fix_last_attempt[kind] = now", attempt)
        self.assertIn("self.record_log_entry(\"Navigation fix:", attempt)
        self.assertIn("self.record_log_entry(\"Navigation: echo-sounder mismatch", attempt)

    def test_chart_uses_believed_position_not_true_position_for_sounder_lookup(self):
        attempt = self.method("Game", "_attempt_navigation_fix")
        sounder = attempt.split('elif kind == "sounder":', 1)[1]
        self.assertIn("believed_design = V(w.believed_pos) / w.scale", sounder)
        self.assertIn("charted_depth_at(believed_design.x, believed_design.y, w.bottom_m)", sounder)


if __name__ == "__main__":
    unittest.main(verbosity=2)
