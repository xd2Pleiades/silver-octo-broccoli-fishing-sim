"""Source contracts for Roadmap V2 Phase 3 roof cutaway and Phase 4 engine-room quarters."""
from pathlib import Path
import ast
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME_PATH = ROOT / "core" / "game.py"


def node_for(source, class_name, method_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return ast.get_source_segment(source, next(
        n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name
    ))


class Phase3WheelhouseCutawayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GAME_PATH.read_text(encoding="utf-8")

    def test_wheelhouse_is_drawn_as_local_cutaway_not_full_hull_veil(self):
        method = node_for(self.src, "Ship", "draw_level_view")
        self.assertIn("if vl != Level.WHEELHOUSE:", method)
        self.assertIn("leave the surrounding main deck unobscured", method)
        self.assertIn("pygame.draw.polygon(s, hexc(\"#8a7f6a\"), poly(fl))", method)

    def test_main_deck_sailors_remain_visible_around_cutaway(self):
        self.assertIn("visible_on_cutaway = (vl == Level.WHEELHOUSE and s.level == Level.MAIN)", self.src)
        self.assertIn("s.level in visible_levels", self.src)
        self.assertIn("(vl, Level.MAIN) if vl == Level.WHEELHOUSE", self.src)

    def test_physical_wheelhouse_stations_and_helm_interlock_remain(self):
        self.assertIn('"helm":', self.src)
        self.assertIn('"throttle":', self.src)
        self.assertIn('"compass":', self.src)
        self.assertIn('"radio":', self.src)
        self.assertIn("if not helm_ok:", node_for(self.src, "World", "update"))


class Phase4EngineRoomAndQuartersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GAME_PATH.read_text(encoding="utf-8")

    def test_six_bunks_and_stands_are_defined_below_deck(self):
        below = self.src.split('"below": {', 1)[1].split('"bunk_stands": [', 1)[0]
        bunk_rows = re.findall(r'^\s*\(0\.\d+,\s*-?0\.\d+,\s*0\.\d+,\s*0\.\d+\),?$', below, re.M)
        self.assertEqual(len(bunk_rows), 6)
        self.assertIn('"bunk_stands": [', self.src)

    def test_bunks_are_collision_solids_but_engine_casing_draw_state_is_separate(self):
        layout = node_for(self.src, "Ship", "_layout")
        draw = node_for(self.src, "Ship", "draw_level_view")
        self.assertIn("self.below_solids = [self.below_casing] + self.bunks", layout)
        self.assertIn("for i, r in enumerate(self.bunks):", draw)
        self.assertIn("poly(self.below_casing)", draw)

    def test_rest_duty_routes_to_reserved_bunk_on_below_level(self):
        task = node_for(self.src, "Sailor", "_do_task")
        reserve = node_for(self.src, "Game", "rest_bunk_for")
        self.assertIn("rest_pos = self.g.rest_bunk_for(self)", task)
        self.assertIn("self._go_to(rest_pos, 22, Level.BELOW)", task)
        self.assertIn("occupied = {", reserve)
        self.assertIn("sailor.rest_bunk_index = idx", reserve)

    def test_engine_components_degrade_trip_recover_and_gate_power(self):
        engine = node_for(self.src, "Game", "update_engine_room")
        self.assertIn("self.engine_oil", engine)
        self.assertIn("self.cooling_intake", engine)
        self.assertIn("self.shaft_seal", engine)
        self.assertIn("self.engine_ok = False", engine)
        self.assertIn("self.engine_ok = True", engine)
        self.assertIn("self.engine_power = min(oil_factor, cooling_factor, seal_factor) if self.engine_ok else 0.0", engine)
        self.assertIn('self.power("hauler") * clamp(g.engine_power, 0.0, 1.0)', self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
