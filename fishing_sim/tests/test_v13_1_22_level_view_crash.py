"""Regression test for the v13.1.22 lower-deck rendering NameError."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"


class LevelViewCrashTests(unittest.TestCase):
    def test_level_view_defines_hull_length_and_beam_before_using_them(self):
        source = GAME.read_text(encoding="utf-8")
        tree = ast.parse(source)
        ship = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Ship")
        method = next(n for n in ship.body if isinstance(n, ast.FunctionDef) and n.name == "draw_level_view")

        assignments = [
            n for n in ast.walk(method)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Tuple) and [e.id for e in t.elts if isinstance(e, ast.Name)] == ["L", "B"] for t in n.targets)
        ]
        self.assertTrue(assignments, "draw_level_view must bind L and B from the current ship")
        assignment = assignments[0]
        rhs_names = {n.id for n in ast.walk(assignment.value) if isinstance(n, ast.Name)}
        rhs_attrs = {n.attr for n in ast.walk(assignment.value) if isinstance(n, ast.Attribute)}
        self.assertIn("self", rhs_names)
        self.assertIn("length", rhs_attrs)
        self.assertIn("beam", rhs_attrs)

        # Ensure they are local names, not unresolved module globals.
        loads = {n.id for n in ast.walk(method) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        stores = {n.id for n in ast.walk(method) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        self.assertTrue({"L", "B"}.issubset(loads))
        self.assertTrue({"L", "B"}.issubset(stores))

    def test_lower_deck_frame_and_hallway_use_the_bound_dimensions(self):
        source = GAME.read_text(encoding="utf-8")
        tree = ast.parse(source)
        ship = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Ship")
        method = next(n for n in ship.body if isinstance(n, ast.FunctionDef) and n.name == "draw_level_view")
        body = ast.get_source_segment(source, method)
        self.assertIn("L, B = self.length, self.beam", body)
        self.assertIn("xx = L * frac", body)
        self.assertIn("hallway = (-L * 0.455, -B * 0.09, L * 0.910, B * 0.18)", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
