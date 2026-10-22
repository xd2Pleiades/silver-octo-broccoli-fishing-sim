"""Dependency-free contracts for features merged from v13.1.32 and v13.1.33."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
INIT = (ROOT / "__init__.py").read_text(encoding="utf-8")
CONTROLS = (ROOT.parent / "docs" / "CONTROLS.md").read_text(encoding="utf-8")


class MergedReleaseContracts(unittest.TestCase):
    def test_release_version_is_merged_version(self):
        self.assertIn('__version__ = "13.2.13"', INIT)
        self.assertIn("v13.2.01", GAME)

    def test_captain_trip_order_and_return_order_are_preserved(self):
        self.assertIn("def start_fishing_trip(self, days=None):", GAME)
        self.assertIn("def order_return_to_port(self):", GAME)
        self.assertIn("ln.trip_end = w.time + days * DAY_LEN", GAME)

    def test_trip_returns_early_for_fuel_bait_or_ice(self):
        trip = GAME[GAME.index("    def _trip_over(self):"):GAME.index("    def trip_hud(self):")]
        self.assertIn("g.fuel", trip)
        self.assertIn("bait_total()", trip)
        self.assertIn("g.ice", trip)

    def test_trip_progress_hud_remains_available(self):
        self.assertIn("def trip_hud(self):", GAME)
        self.assertIn('"TRIP %.1f/%dd"', GAME)

    def test_idle_crew_below_deck_is_sent_up(self):
        self.assertIn("Nobody lingers in the cabin or the engine room between jobs", GAME)
        self.assertIn("self._go_to(m[\"rest_spot\"] + self.spot_off * 0.25, 40, Level.MAIN)", GAME)

    def test_social_partners_must_be_awake_and_on_same_level(self):
        partner = GAME[GAME.index("    def _find_partner(self):"):GAME.index("    def _task_social(self, dt):")]
        self.assertIn("if o.level != self.level or o.sleeping_in_bunk:", partner)

    def test_sleepers_have_better_recovery_rates(self):
        self.assertIn("(0.045 if asleep else 0.028)", GAME)
        self.assertIn("(0.008 if asleep else 0.005)", GAME)

    def test_below_deck_man_overboard_response_is_delayed(self):
        self.assertIn("if o.level == Level.BELOW:", GAME)
        self.assertIn("delay += 1.2 + (1.8 if o.sleeping_in_bunk else 0.0)", GAME)

    def test_placeholder_coast_guard_hull_is_drawn(self):
        self.assertIn("def draw_tow_escort(self):", GAME)
        self.assertIn("PLACE HOLDER SHIP", GAME)
        self.assertIn("self.ship.hull", GAME)

    def test_launch_approaches_from_harbour_before_towing(self):
        escort_update = GAME[GAME.index("    def _update_tow_escort(self, dt):"):GAME.index("    def tow_in(self):")]
        self.assertIn("tow_intercept_position(harbor_chart, ship_chart)", escort_update)
        self.assertIn("lerp_chart_position(harbor_chart, intercept, progress)", escort_update)
        self.assertIn('escort.state = "ALONGSIDE"', escort_update)

    def test_controls_document_both_captain_and_escort_workflows(self):
        self.assertIn("Fish: 3-day trip", CONTROLS)
        self.assertIn("Return to port", CONTROLS)
        self.assertIn("`G` while the Coast Guard escort is active", CONTROLS)
        self.assertIn("comes alongside, turns, and then leads the tow", CONTROLS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
