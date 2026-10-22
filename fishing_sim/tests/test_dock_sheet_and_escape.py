"""Static regression contracts for V10 dock leave, hiring sheet, and cabin exits."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME_PATH = ROOT / "core" / "game.py"
ZIP_ROOT = ROOT.parent


def node_for(source, class_name, method_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return ast.get_source_segment(source, next(
        n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name
    ))


class DockSheetEscapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GAME_PATH.read_text(encoding="utf-8")
        cls.game_init = node_for(cls.src, "Game", "__init__")
        cls.sailor_init = node_for(cls.src, "Sailor", "__init__")

    def test_shore_is_a_distinct_sailor_mode_and_recovers_needs(self):
        self.assertIn("ABOARD, SWIMMING, CLIMBING, DEAD, SHORE, RESCUE_BOAT = range(6)", self.src)
        update = node_for(self.src, "Sailor", "update")
        self.assertIn("self.mode == self.SHORE", update)
        self.assertIn("self.health = min(1.0, self.health + 0.075 * dt)", update)
        self.assertIn("self.fatigue = max(0.0, self.fatigue - 0.055 * dt)", update)

    def test_dock_settlement_starts_shore_leave(self):
        settle = node_for(self.src, "Game", "settle")
        self.assertGreaterEqual(settle.count("self._start_dock_shore_leave()"), 2)
        self.assertIn("def _start_dock_shore_leave(self):", self.src)
        self.assertIn('"shore"', node_for(self.src, "Game", "_send_sailor_ashore"))

    def test_destination_recalls_crew_before_departure(self):
        world = node_for(self.src, "World", "set_destination")
        self.assertIn("self.g._recall_shore_leave(departure=True)", world)
        self.assertIn("sailor.mode == Sailor.SHORE and not sailor.keep_ashore", node_for(self.src, "Game", "_recall_shore_leave"))

    def test_headcount_does_not_mark_shore_leave_as_missing(self):
        headcount = node_for(self.src, "Crew", "headcount")
        self.assertIn('if v not in ("aboard", "shore")', headcount)
        self.assertIn("ashore = sum", headcount)

    def test_f1_full_sheet_has_crew_shore_and_hire_tabs(self):
        handle = node_for(self.src, "Game", "handle")
        draw = node_for(self.src, "Game", "draw_crew_sheet")
        self.assertIn("pygame.K_F1", handle)
        self.assertIn('("crew", "ABOARD")', draw)
        self.assertIn('("shore", "SHORE")', draw)
        self.assertIn('("hire", "HIRE")', draw)
        self.assertIn("self.draw_crew_sheet()", node_for(self.src, "Game", "draw"))

    def test_dock_hire_supports_aboard_or_shore(self):
        hire = node_for(self.src, "Game", "hire_from_dock")
        self.assertIn("stay_ashore=False", hire)
        self.assertIn("if stay_ashore and not self._send_sailor_ashore", hire)
        self.assertIn("self.cash < candidate[\"fee\"]", hire)

    def test_only_deckhands_can_be_retained_permanently_ashore(self):
        send = node_for(self.src, "Game", "_send_sailor_ashore")
        self.assertIn("sailor.role != Sailor.DECKHAND and not automatic", send)
        self.assertIn("sailor.role != Sailor.DECKHAND and keep_ashore", send)
        self.assertIn("automatic=True", node_for(self.src, "Game", "_start_dock_shore_leave"))

    def test_station_owner_exit_hands_over_before_route(self):
        exit_method = node_for(self.src, "Game", "request_wheelhouse_exit")
        self.assertIn("self._set_helm_operator(veteran)", exit_method)
        self.assertIn("self.radio_operator, self.radio_duty_active = None, False", exit_method)
        self.assertIn("sailor.order_to(goal, Level.MAIN)", exit_method)

    def test_stuck_wheelhouse_has_bounded_ladder_failsafe(self):
        recover = node_for(self.src, "Game", "_recover_wheelhouse_exit")
        self.assertIn("sailor.wheelhouse_exit_attempts += 1", recover)
        self.assertIn("sailor.start_climb(link)", recover)
        self.assertIn("self.wheelhouse_exit_elapsed >= 2.4", node_for(self.src, "Sailor", "_aboard"))

    def test_relief_is_veteran_only_not_random_deckhands(self):
        station = node_for(self.src, "Game", "_update_station_roles")
        self.assertIn("relief = self.relief_helmsman", station)
        self.assertNotIn("options = [s for s in self.sailors if s.mode == Sailor.ABOARD and s.role != Sailor.CAPTAIN", station)

    def test_launcher_and_do_not_remove_marker_are_in_zip_root(self):
        launcher = ZIP_ROOT / "run_fishing_sim.py"
        marker = ZIP_ROOT / "docs" / "DO_NOT_REMOVE_THIS_IN_THE_ZIP.md"
        self.assertTrue(launcher.exists())
        self.assertIn("from fishing_sim.core.game import Game", launcher.read_text(encoding="utf-8"))
        self.assertEqual(marker.read_text(encoding="utf-8").strip(), "DO NOT REMOVE THIS IN THE ZIP")


if __name__ == "__main__":
    unittest.main(verbosity=2)
