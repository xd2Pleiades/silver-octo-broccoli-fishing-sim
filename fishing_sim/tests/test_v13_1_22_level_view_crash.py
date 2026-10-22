"""Regression contracts for the redesigned lower-deck cutaway renderer."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"


class LevelViewCrashTests(unittest.TestCase):
    def test_level_view_defines_dimensions_before_dispatching_to_lower_deck(self):
        source = GAME.read_text(encoding="utf-8")
        tree = ast.parse(source)
        ship = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Ship")
        method = next(n for n in ship.body if isinstance(n, ast.FunctionDef) and n.name == "draw_level_view")
        body = ast.get_source_segment(source, method)
        self.assertIn("L, B = self.length, self.beam", body)
        self.assertIn("self._draw_lower_deck(g)", body)

    def test_lower_deck_renderer_uses_bound_geometry_and_compartment_zones(self):
        source = GAME.read_text(encoding="utf-8")
        tree = ast.parse(source)
        ship = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Ship")
        method = next(n for n in ship.body if isinstance(n, ast.FunctionDef) and n.name == "_draw_lower_deck")
        body = ast.get_source_segment(source, method)
        self.assertIn("L, B = self.length, self.beam", body)
        self.assertIn("self.zone_polys", body)
        self.assertIn("for bx, door_y, door_w in self.bulkheads", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
