"""Headless tests for V13V1-12: uncertain fishing reports on the chart."""
import ast
import random
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.fishing_reports import (
    DEFAULT_GROUNDED_CHANCE,
    FishingSpotReport,
    MAX_CHART_REPORTS,
    create_fishing_report,
    report_map_color,
)
from fishing_sim.systems.hotspots import Hotspot
from fishing_sim.systems.navigation_chart import CHART_BOUNDS


class FishingReportModelTests(unittest.TestCase):
    def setUp(self):
        self.school = Hotspot(12000, 7500, "yellowfin", strength=0.9, radius=1800, life=600)

    @staticmethod
    def is_water(_x, _y):
        return True

    def test_true_report_can_be_grounded_in_a_real_school_but_has_position_error(self):
        report = create_fishing_report(
            random.Random(12), [self.school], 3.0, self.is_water, 1,
            grounded_chance=1.0,
        )
        self.assertIsNotNone(report)
        self.assertTrue(report.grounded)
        self.assertLessEqual(((report.x - 4000) ** 2 + (report.y - 2500) ** 2) ** 0.5, 3 * report.accuracy_radius)
        self.assertNotEqual((report.x, report.y), (4000.0, 2500.0))

    def test_false_report_is_a_plausible_water_lead_away_from_live_schools(self):
        report = create_fishing_report(
            random.Random(22), [self.school], 3.0, self.is_water, 2,
            grounded_chance=0.0,
        )
        self.assertIsNotNone(report)
        self.assertFalse(report.grounded)
        self.assertTrue(CHART_BOUNDS[0] <= report.x <= CHART_BOUNDS[2])
        self.assertTrue(CHART_BOUNDS[1] <= report.y <= CHART_BOUNDS[3])
        self.assertGreater(((report.x - 4000) ** 2 + (report.y - 2500) ** 2) ** 0.5, 1000)
        self.assertIn(report.species, ("albacore", "yellowfin", "bigeye", "swordfish", "mixed"))

    def test_reports_can_be_created_without_any_live_hotspots(self):
        report = create_fishing_report(
            random.Random(99), [], 3.0, self.is_water, 3,
            grounded_chance=DEFAULT_GROUNDED_CHANCE,
        )
        self.assertIsNotNone(report)
        self.assertFalse(report.grounded)

    def test_generation_is_repeatable_for_the_same_rng_seed(self):
        a = create_fishing_report(random.Random(144), [self.school], 3, self.is_water, 4)
        b = create_fishing_report(random.Random(144), [self.school], 3, self.is_water, 4)
        self.assertEqual(
            (a.report_id, a.x, a.y, a.species, a.source, a.confidence, a.lifetime, a.grounded),
            (b.report_id, b.x, b.y, b.species, b.source, b.confidence, b.lifetime, b.grounded),
        )

    def test_report_ages_and_expires_without_touching_hotspots(self):
        report = create_fishing_report(random.Random(34), [], 3, self.is_water, 5, grounded_chance=0)
        self.assertTrue(report.update(60))
        self.assertEqual(report.age_minutes, 1)
        self.assertTrue(report.update(report.lifetime - 61))
        self.assertFalse(report.update(2))
        self.assertTrue(report.expired)

    def test_staleness_changes_with_age(self):
        report = FishingSpotReport(1, 10, 20, "mixed", "TENYO MARU", 0.8, 300, 1000)
        self.assertEqual(report.age_band, "FRESH")
        report.age = 400
        self.assertEqual(report.age_band, "AGING")
        report.age = 800
        self.assertEqual(report.age_band, "STALE")

    def test_source_credibility_does_not_encode_ground_truth(self):
        fresh_false = FishingSpotReport(1, 0, 0, "bigeye", "TENYO MARU", 0.82, 300, 1000, grounded=False)
        fresh_true = FishingSpotReport(2, 0, 0, "bigeye", "TENYO MARU", 0.82, 300, 1000, grounded=True)
        self.assertEqual(report_map_color(fresh_false.confidence), report_map_color(fresh_true.confidence))

    def test_map_color_uses_source_confidence_and_age_only(self):
        high = report_map_color(0.9, 0.0)
        low = report_map_color(0.3, 0.0)
        stale = report_map_color(0.9, 1.0)
        self.assertNotEqual(high, low)
        self.assertTrue(all(s <= h for s, h in zip(stale, high)))

    def test_display_tags_do_not_expose_truth(self):
        report = FishingSpotReport(9, 1, 2, "yellowfin", "HARBOUR TALK", 0.44, 500, 1200, grounded=False)
        shown = " ".join((report.source_tag, report.species_tag, report.short_age, report.age_band))
        self.assertIn("YEL?", shown)
        self.assertNotIn("FALSE", shown)
        self.assertNotIn("TRUE", shown)
        self.assertNotIn("grounded", shown.lower())

    def test_report_cap_is_small_enough_for_chart(self):
        self.assertEqual(MAX_CHART_REPORTS, 5)


class ChartReportIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def method(self, class_name, name):
        cls = next(node for node in self.tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
        node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
        return ast.get_source_segment(self.source, node)

    def test_world_ages_and_generates_reports_after_hotspot_update(self):
        update = self.method("World", "update")
        self.assertIn("self._update_hotspots(dt)", update)
        self.assertIn("self._update_fishing_reports(dt)", update)
        method = self.method("World", "_update_fishing_reports")
        self.assertIn("create_fishing_report", method)
        self.assertIn("report.update(dt)", method)
        self.assertIn("record_log_entry", method)

    def test_chart_draws_uncertainty_markers_and_reports_side_panel(self):
        draw = self.method("Game", "draw_navigation_chart")
        self.assertIn("w.fishing_reports", draw)
        self.assertIn("report_map_color", draw)
        self.assertIn('section("FISHING SPOT REPORTS (?)"', draw)
        self.assertIn("Leads may be false or stale", draw)
        self.assertIn('render("?"', draw)
        # Truth state must not feed the chart's visible classification.
        self.assertNotIn("report.grounded", draw)

    def test_report_ui_has_an_explicit_uncertainty_legend(self):
        draw = self.method("Game", "draw_navigation_chart")
        self.assertIn("R# ring: unconfirmed report", draw)
        self.assertIn("Leads may be false or stale", draw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
