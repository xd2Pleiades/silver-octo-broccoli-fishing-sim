import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"

class V13127RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GAME.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_cabin_tuple_does_not_use_rect_api(self):
        self.assertIn("cx, cy, cw, ch = cabin", self.source)
        self.assertNotIn("cabin.collidepoint", self.source)

    def test_stalled_sailors_can_replan_around_crowd(self):
        self.assertIn("ignore_crew=True", self.source)
        self.assertIn("def _plan_path(self, start, goal, level=None, ignore_crew=False)", self.source)

    def test_haul_destination_accounts_for_station_offset(self):
        self.assertIn("haul_offset = V(-g.ship.length * 0.32, g.ship.beam * 0.5).rotate_rad(w.heading)", self.source)
        self.assertIn("w.destination = V(head) - haul_offset", self.source)

    def test_depth_profile_is_debug_only(self):
        self.assertIn('"DEPTH %dm" % depth', self.source)
        self.assertIn("if self.longline_minimap_debug:\n            self.draw_profile()", self.source)

if __name__ == "__main__":
    unittest.main()
