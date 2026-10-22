"""Regression checks for visible Coast Guard placeholder hull and real approach."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from fishing_sim.systems.tow_escort import tow_intercept_position, lerp_chart_position, TOW_ESCORT_SEPARATION_NM, CHART_UNITS_PER_NAUTICAL_MILE

ROOT = Path(__file__).resolve().parents[2]
GAME_PATH = ROOT / "fishing_sim" / "core" / "game.py"
GAME = GAME_PATH.read_text(encoding="utf-8")
TREE = ast.parse(GAME)
METHODS = {
    node.name: node for node in ast.walk(TREE)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}


def method_source(name: str) -> str:
    node = METHODS[name]
    lines = GAME.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


class TowPlaceholderShipTests(unittest.TestCase):
    def test_version_bumped(self):
        init = (ROOT / "fishing_sim" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "13.2.13"', init)

    def test_placeholder_hull_reuses_player_ship_geometry_with_coast_guard_livery(self):
        draw = method_source("draw_tow_escort")
        self.assertIn("PLACE HOLDER SHIP", draw)
        self.assertIn("self.ship.hull", draw)
        self.assertIn("hull_length_scale, hull_beam_scale", draw)
        self.assertIn("232, 104, 41", draw)  # orange Coast Guard stripe
        self.assertIn("self.S(centre_local + local)", draw)

    def test_physical_towline_is_drawn_in_world_view(self):
        draw = method_source("draw_tow_escort_towline")
        self.assertIn('escort.state != "UNDER_TOW"', draw)
        self.assertIn("self._draw_dashed_screen_line", draw)
        game_draw = method_source("draw")
        self.assertIn("self.draw_tow_escort()", game_draw)
        self.assertIn("self.draw_tow_escort_towline()", game_draw)

    def test_enroute_launch_starts_at_harbour_and_moves_to_intercept(self):
        update = method_source("_update_tow_escort")
        self.assertIn("tow_intercept_position(harbor_chart, ship_chart)", update)
        self.assertIn("lerp_chart_position(harbor_chart, intercept, progress)", update)
        self.assertIn('escort.state = "ALONGSIDE"', update)
        self.assertIn("escort.enroute_elapsed / max(0.1, escort.enroute_duration)", update)

    def test_intercept_is_between_harbour_and_ship_with_tow_separation(self):
        harbour = (0.0, 0.0)
        ship = (2500.0, 0.0)
        intercept = tow_intercept_position(harbour, ship)
        self.assertGreater(intercept[0], harbour[0])
        self.assertLess(intercept[0], ship[0])
        gap_nm = (ship[0] - intercept[0]) / CHART_UNITS_PER_NAUTICAL_MILE
        self.assertAlmostEqual(gap_nm, TOW_ESCORT_SEPARATION_NM, places=5)

    def test_launch_path_starts_at_harbour_and_ends_at_intercept(self):
        harbour = (200.0, -400.0)
        ship = (2200.0, 1600.0)
        intercept = tow_intercept_position(harbour, ship)
        self.assertEqual(lerp_chart_position(harbour, intercept, 0.0), harbour)
        self.assertEqual(lerp_chart_position(harbour, intercept, 1.0), intercept)
        middle = lerp_chart_position(harbour, intercept, 0.5)
        self.assertGreater(middle[0], harbour[0])
        self.assertLess(middle[0], intercept[0])

    def test_tow_eta_is_not_a_teleport_trigger(self):
        update = method_source("_update_radio")
        self.assertIn("# The timer is an ETA for the launch, not a teleport trigger.", update)
        self.assertNotIn("if self.tow_arrival_t <= 0 and not self.docked():\n                self.tow_in()", update)

    def test_tow_does_not_begin_while_launch_still_en_route(self):
        tow_in = method_source("tow_in")
        self.assertIn('if self.tow_escort.state == "EN_ROUTE":\n            return False', tow_in)
        self.assertIn('self.tow_escort.state = "UNDER_TOW"', tow_in)
        self.assertNotIn("self.tow_escort.true_position = escort_position", tow_in)

    def test_alongside_phase_turns_before_tow_start(self):
        update = method_source("_update_tow_escort")
        self.assertIn('elif escort.state == "ALONGSIDE":', update)
        self.assertIn("escort.handover_elapsed >= TOW_ESCORT_HANDOVER_SECONDS", update)
        self.assertIn("self.tow_in()", update)

    def test_chart_and_radio_accept_alongside_state(self):
        self.assertIn('escort.state in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW", "ARRIVED")', GAME)
        self.assertIn('self.tow_escort.state in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW")', GAME)

    def test_communication_spec_describes_actual_placeholder_hull(self):
        spec = (ROOT / "docs" / "TOW_ESCORT_COMMUNICATION.md").read_text(encoding="utf-8")
        self.assertIn("PLACE HOLDER SHIP", spec)
        self.assertIn("harbour", spec.lower())
        self.assertIn("physical towline", spec.lower())


if __name__ == "__main__":
    unittest.main()
