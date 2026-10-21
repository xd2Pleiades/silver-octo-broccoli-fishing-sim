"""Static source-contract checks for V8 station and radio regressions.

These deliberately do not pretend to be graphical integration tests; they verify
that the previously regressed ownership/dispatch paths remain wired into the build.
"""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME_PATH = ROOT / "core" / "game.py"
RADIO_PATH = ROOT / "systems" / "radio.py"


def source(path):
    return path.read_text(encoding="utf-8")


def method_node(tree, class_name, method_name):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return next(n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name)


class StationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game_src = source(GAME_PATH)
        cls.game_ast = ast.parse(cls.game_src)
        cls.radio_src = source(RADIO_PATH)

    def test_helm_owner_is_initialized_to_captain_and_veteran_is_relief(self):
        self.assertIn("self.helm_operator = self.sailors[0]", self.game_src)
        self.assertIn("self.relief_helmsman = next((s for s in self.sailors if s.role == Sailor.VETERAN), None)", self.game_src)

    def test_deckhands_no_longer_self_assign_to_helm(self):
        self.assertNotIn("not captain_at_helm", self.game_src)
        self.assertIn("an unattended helm never summons every deckhand into the wheelhouse", self.game_src)
        think = ast.get_source_segment(self.game_src, method_node(self.game_ast, "Sailor", "_think"))
        self.assertIn("if self is self.g.helm_operator", think)
        self.assertIn('self._enter("post")', think)

    def test_relieved_helmsman_is_sent_back_to_main_deck(self):
        method = ast.get_source_segment(self.game_src, method_node(self.game_ast, "Game", "_set_helm_operator"))
        self.assertIn('old.order_to(self.ship.markers["rest_spot"], Level.MAIN)', method)
        self.assertIn('old.level == Level.WHEELHOUSE', method)

    def test_station_owners_are_prioritized_over_background_ai(self):
        think = ast.get_source_segment(self.game_src, method_node(self.game_ast, "Sailor", "_think"))
        self.assertLess(think.index("if self is self.g.helm_operator"), think.index("if self.g.rescue_engineer is self"))
        self.assertLess(think.index("if self is self.g.radio_operator"), think.index("if self.g.rescue_engineer is self"))

    def test_wheelhouse_destination_is_authorized_by_assigned_station(self):
        self.assertIn("def can_enter_wheelhouse(self, sailor):", self.game_src)
        self.assertIn("sailor in (self.helm_operator, self.radio_operator)", self.game_src)
        self.assertIn("if level == Level.WHEELHOUSE and not self.g.wheelhouse_goal_allowed(self, pos):", self.game_src)

    def test_manual_radio_assignment_persists(self):
        self.assertIn('if hit is not None and hit[0] == "radio":', self.game_src)
        self.assertIn('sailor.duty = "radio"', self.game_src)
        self.assertIn("if self is self.g.radio_operator", self.game_src)
        self.assertIn('elif t == "radio":', self.game_src)

    def test_f2_f3_f4_route_through_radio_autostaffing(self):
        self.assertIn('self.radio_call("weather")', self.game_src)
        self.assertIn('self.radio_call("auction")', self.game_src)
        self.assertIn('self.radio_call("tow")', self.game_src)
        self.assertIn("self.pending_radio_calls.append(kind)", self.game_src)
        self.assertIn("self.pending_radio_calls.pop(0)", self.game_src)

    def test_radio_bubble_displays_full_dialogue(self):
        self.assertIn("def show_radio_dialogue(self, text):", self.game_src)
        self.assertIn("def draw_radio_bubble(self):", self.game_src)
        self.assertIn("self.draw_radio_bubble()", self.game_src)
        self.assertIn('text.strip().lower().startswith("radio:")', self.game_src)

    def test_ladder_level_switch_occurs_only_at_completion(self):
        ladder = ast.get_source_segment(self.game_src, method_node(self.game_ast, "Sailor", "_ladder_step"))
        self.assertNotIn("k >= 0.5", ladder)
        self.assertIn("if k >= 1.0:", ladder)

    def test_docking_retry_is_bounded_and_opposite_side_is_used(self):
        self.assertIn("def _retry_dock_approach", self.game_src)
        self.assertIn("if self.dock_retries >= 2:", self.game_src)
        self.assertIn("self.dock_side *= -1", self.game_src)
        self.assertIn('self.dock_state, self.dock_result = None, "failed"', self.game_src)

    def test_radio_facade_reports_rejected_tows(self):
        self.assertIn('accepted = self.game.radio_call("tow")', self.radio_src)
        self.assertIn("if not accepted:", self.radio_src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
