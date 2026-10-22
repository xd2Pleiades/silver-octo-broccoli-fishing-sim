"""Headless regression tests for v13.1.32 Coast Guard tow escort state."""
from __future__ import annotations

import ast
import math
from pathlib import Path
import random
import unittest

from fishing_sim.systems.tow_escort import (
    TowEscort, CHECKIN_INTERVAL, STALE_TOW_REPORT, DEPART_DELAY,
    CHART_UNITS_PER_NAUTICAL_MILE, format_chart_position, dashed_segments,
)

ROOT = Path(__file__).resolve().parents[2]
GAME_SOURCE = (ROOT / "fishing_sim" / "core" / "game.py").read_text(encoding="utf-8")


class TowEscortStateTests(unittest.TestCase):
    def setUp(self):
        self.escort = TowEscort.coast_guard((1000.0, -500.0), enroute_duration=20.0, rng=random.Random(7))

    def test_coast_guard_has_own_named_captain_callsign_and_four_person_crew(self):
        self.assertTrue(self.escort.callsign)
        self.assertTrue(self.escort.captain_name.startswith("Captain "))
        self.assertEqual(len(self.escort.crew), 4)
        self.assertIn("radio operator", [m.duty for m in self.escort.crew])
        self.assertEqual(self.escort.state, "EN_ROUTE")

    def test_position_report_is_independent_of_true_position(self):
        true_pos = (3000.0, 4000.0)
        self.escort.refresh_report(true_pos, rng=random.Random(2))
        self.assertNotEqual(self.escort.reported_position, true_pos)
        self.assertEqual(self.escort.true_position, (1000.0, -500.0))

    def test_marker_becomes_stale_after_45_game_minutes(self):
        self.assertFalse(self.escort.marker_stale)
        self.escort.elapsed = STALE_TOW_REPORT - 0.01
        self.assertFalse(self.escort.marker_stale)
        self.escort.elapsed = STALE_TOW_REPORT
        self.assertTrue(self.escort.marker_stale)
        self.assertEqual(self.escort.report_age_game_minutes, 45)

    def test_report_age_uses_in_game_minutes(self):
        self.escort.elapsed = 12.5
        self.assertEqual(self.escort.report_age_game_minutes, 30)

    def test_refresh_report_resets_age_and_missed_checkins(self):
        self.escort.elapsed = 50.0
        self.escort.missed_checkins = 2
        self.escort.refresh_report((25.0, 30.0), rng=random.Random(1))
        self.assertEqual(self.escort.last_report_elapsed, 50.0)
        self.assertEqual(self.escort.missed_checkins, 0)
        self.assertEqual(self.escort.report_age_game_minutes, 0)

    def test_report_error_uses_nm_scaled_chart_units(self):
        position = (0.0, 0.0)
        self.escort.refresh_report(position, rng=random.Random(10))
        error_nm = math.dist(position, self.escort.reported_position) / CHART_UNITS_PER_NAUTICAL_MILE
        self.assertGreater(error_nm, 0.0)
        self.assertLessEqual(error_nm, 3.0)

    def test_position_report_format_includes_bearing_and_range(self):
        text = format_chart_position((0.0, 185.2), origin=(0.0, 0.0))
        self.assertIn("000°", text)
        self.assertIn("1.0 nm", text)

    def test_dashed_towline_is_a_bounded_sequence_of_segments(self):
        pieces = dashed_segments((0, 0), (100, 0), dash=10, gap=5)
        self.assertGreaterEqual(len(pieces), 6)
        self.assertEqual(pieces[0], ((0, 0), (10, 0)))
        self.assertEqual(pieces[-1][1], (100, 0))

    def test_in_game_time_constants_match_30_and_45_game_minutes(self):
        self.assertAlmostEqual(CHECKIN_INTERVAL, 12.5)
        self.assertAlmostEqual(STALE_TOW_REPORT, 18.75)
        self.assertAlmostEqual(DEPART_DELAY, 12.5)


class TowEscortIntegrationSourceTests(unittest.TestCase):
    def test_game_owns_and_updates_separate_tow_escort_entity(self):
        self.assertIn("self.tow_escort = None", GAME_SOURCE)
        self.assertIn("def _update_tow_escort(self, dt):", GAME_SOURCE)
        self.assertIn("self._update_tow_escort(dt)", GAME_SOURCE)

    def test_chart_draws_coast_guard_marker_and_towline(self):
        self.assertIn('prefix = "CG " if getattr(ship, "runtime_kind", "scheduled") == "tow_escort" else ""', GAME_SOURCE)
        self.assertIn("if escort.line_at_risk", GAME_SOURCE)
        self.assertIn("self.draw_traffic_chart_contacts(chart_surface, point, map_w, map_h, pal)", GAME_SOURCE)
        self.assertIn("M8: the shared traffic entity supplies the Coast Guard marker", GAME_SOURCE)
        self.assertIn('section("COAST GUARD ESCORT"', GAME_SOURCE)

    def test_periodic_checkin_and_unsolicited_radio_conversations_exist(self):
        self.assertIn('source="tow_escort_checkin"', GAME_SOURCE)
        self.assertIn('source="tow_escort_unscheduled"', GAME_SOURCE)
        self.assertIn("escort.since_checkin >= CHECKIN_INTERVAL", GAME_SOURCE)

    def test_player_can_hail_and_cycle_topics(self):
        self.assertIn("def tow_escort_talk(self, topic=None, *, via_radio_ui=False):", GAME_SOURCE)
        self.assertIn("elif k == pygame.K_g:", GAME_SOURCE)
        self.assertIn('self.tow_escort_talk("position")', GAME_SOURCE)

    def test_arrival_keeps_marker_temporarily_then_removes_escort(self):
        self.assertIn('self.tow_escort.state = "ARRIVED"', GAME_SOURCE)
        self.assertIn("escort.depart_elapsed >= DEPART_DELAY", GAME_SOURCE)
        self.assertIn('self.tow_escort = None', GAME_SOURCE)


if __name__ == "__main__":
    unittest.main()
