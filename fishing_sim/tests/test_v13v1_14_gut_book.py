"""Headless acceptance tests for V13V1-14 gut-book history and chart gut plots."""
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.fishing_gut_book import (
    GUT_BOOK_CONFIDENCE_THRESHOLD,
    MAX_GUT_BOOK_ENTRIES,
    GutBookEntry,
    believed_chart_position,
    entry_is_active,
)
from fishing_sim.systems.hotspots import Hotspot


class GutBookModelTests(unittest.TestCase):
    def test_position_applies_navigation_belief_error_before_chart_scaling(self):
        self.assertEqual(believed_chart_position((300, 600), (90, -30), 3), (130.0, 190.0))

    def test_position_accepts_xy_objects_and_guards_zero_scale(self):
        class Point:
            x = 20
            y = -40
        self.assertEqual(believed_chart_position(Point(), (5, 10), 0), (25000.0, -30000.0))

    def test_gut_book_entry_preserves_timing_species_guess_and_believed_plot(self):
        entry = GutBookEntry(3, "12 APR 1962", "07:42", 720.0, "Takeda", 0.8,
                             "yellowfin", 123.0, -456.0, 0.65, 0.72)
        self.assertEqual(entry.chart_position, (123.0, -456.0))
        self.assertEqual((entry.date, entry.clock, entry.sailor), ("12 APR 1962", "07:42", "Takeda"))
        self.assertEqual(entry.species_guess, "yellowfin")
        self.assertNotIn("hotspot_ref", repr(entry))

    def test_entry_is_active_only_for_the_same_live_hotspot_object(self):
        spot = Hotspot(100, 200, "bigeye")
        other = Hotspot(100, 200, "bigeye")
        entry = GutBookEntry(1, "01 APR 1962", "06:30", 0, "Sato", 0.2,
                             "bigeye", 1, 2, 0.5, 0.6, hotspot_ref=spot)
        self.assertTrue(entry_is_active(entry, [spot, other]))
        self.assertFalse(entry_is_active(entry, [other]))
        # The entry itself is unchanged when the live hotspot expires/disappears.
        self.assertEqual(entry.chart_position, (1, 2))

    def test_history_limit_is_bounded(self):
        self.assertEqual(MAX_GUT_BOOK_ENTRIES, 100)
        self.assertEqual(GUT_BOOK_CONFIDENCE_THRESHOLD, 0.5)


class GutBookGameIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.game = next(n for n in cls.tree.body if isinstance(n, ast.ClassDef) and n.name == "Game")
        cls.methods = {n.name: n for n in cls.game.body if isinstance(n, ast.FunctionDef)}

    def method_source(self, name):
        return ast.get_source_segment(self.source, self.methods[name])

    def test_game_owns_a_bounded_gut_book_and_monotonic_ids(self):
        self.assertIn("self.gut_book_entries: list[GutBookEntry] = []", self.source)
        self.assertIn("self.next_gut_book_id = 1", self.source)
        record = self.method_source("_record_gut_book_detection")
        self.assertIn("self.gut_book_entries.append(entry)", record)
        self.assertIn("del self.gut_book_entries[:-limit]", record)
        self.assertIn("believed_chart_position", record)

    def test_detection_threshold_records_first_confident_lookout(self):
        update = self.method_source("_update_hotspot_lookouts")
        self.assertIn("old_confidence < GUT_BOOK_CONFIDENCE_THRESHOLD <= sailor.gut_confidence", update)
        self.assertIn("self._record_gut_book_detection(sailor, best)", update)
        self.assertIn("best.detected_by is None", update)

    def test_notebook_has_gut_book_tab_and_1_to_5_access(self):
        self.assertIn('labels = ("CREW LOG", "RADIO LOG", "CALENDAR", "FORECAST", "GUT BOOK")', self.source)
        self.assertIn("(self.notebook_section + 1) % 5", self.source)
        self.assertIn("pygame.K_5", self.source)
        self.assertIn("self.notebook_section = int(clamp(section, 0, 4))", self.source)
        self.assertIn('elif section == 4:', self.method_source("draw_notebook"))

    def test_gut_book_marks_old_entries_historical_without_deleting_them(self):
        draw = self.method_source("draw_notebook")
        self.assertIn('status = "ACTIVE" if entry_is_active(entry, self.world.hotspots) else "HISTORICAL"', draw)
        self.assertIn("PLOTTED X%+.0f  Y%+.0f", draw)
        self.assertIn("Historical positions are the crew's plot at detection time.", draw)

    def test_chart_draws_deduplicated_belief_offset_gut_markers(self):
        draw = self.method_source("draw_navigation_chart")
        self.assertIn("live_spots = {id(spot): spot for spot in w.hotspots}", draw)
        self.assertIn("gut_contacts", draw)
        self.assertIn("estimated_hotspot_destination(spot.pos, w.position_error)", draw)
        self.assertIn('render("G%02d"', draw)
        self.assertIn('"G# diamond: crew gut plot (DR)"', draw)
        self.assertIn("confidence < GUT_BOOK_CONFIDENCE_THRESHOLD", draw)

    def test_recorded_position_and_live_marker_can_move_differently_after_a_fix(self):
        record = self.method_source("_record_gut_book_detection")
        draw = self.method_source("draw_navigation_chart")
        self.assertIn("believed_chart_position(spot.pos, self.world.position_error, self.world.scale)", record)
        self.assertIn("estimated_hotspot_destination(spot.pos, w.position_error)", draw)
        self.assertIn("self.gut_book_entries.append(entry)", record)


if __name__ == "__main__":
    unittest.main(verbosity=2)
