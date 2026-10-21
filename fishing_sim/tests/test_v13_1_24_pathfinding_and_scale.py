"""v13.1.24 regression contracts for clearance-aware crew routing and chart scale."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"


def method_src(source, cls_name, method_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return ast.get_source_segment(source, node)


class PathfindingContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GAME.read_text(encoding="utf-8")

    def test_nav_grid_uses_clearance_penalties_for_safer_routes(self):
        init = method_src(self.source, "NavMap", "__init__")
        self.assertIn("wall_clearance", init)
        self.assertIn("solid_clearance", init)
        self.assertIn("scrape_cost", init)
        self.assertIn("edge_cost", init)

    def test_astar_discards_stale_entries_and_prevents_corner_cutting(self):
        path = method_src(self.source, "NavMap", "find_path")
        self.assertIn("queued_g > best.get(cur, math.inf)", path)
        self.assertIn("(cur[0] + dx, cur[1]) not in self.nav", path)
        self.assertIn("_line_ok(pts[i], pts[j], obstacles)", path)
        self.assertIn("def point_safe(self, point)", method_src(self.source, "NavMap", "point_safe"))

    def test_string_pulling_validates_the_actual_destination_segment(self):
        path = method_src(self.source, "NavMap", "find_path")
        self.assertIn("pts = [V(a)] + cells + [V(goal)]", path)
        self.assertNotIn("out.append(goal)", path)

    def test_sailor_replans_when_goal_distance_stops_improving(self):
        move = method_src(self.source, "Sailor", "_move")
        self.assertIn("self.progress_distance", move)
        self.assertIn("self.no_progress_t > 1.0", move)
        self.assertIn("self._plan_path(self.pos, self.target, self.level)", move)
        self.assertIn("collision/avoidance leaves some sideways velocity", move)

    def test_nautical_conversion_is_shared_and_not_off_by_ten(self):
        nav = (ROOT / "systems" / "navigation.py").read_text(encoding="utf-8")
        self.assertIn("DESIGN_UNITS_PER_NAUTICAL_MILE = 185.2", nav)
        self.assertIn("return DESIGN_UNITS_PER_NAUTICAL_MILE *", nav)
        self.assertNotIn("1852.0 * w.scale", self.source)

    def test_chart_was_expanded_to_include_far_offshore_grounds(self):
        nav = (ROOT / "systems" / "navigation_chart.py").read_text(encoding="utf-8")
        self.assertIn("CHART_BOUNDS = (-12000.0, -10000.0, 12000.0, 10000.0)", nav)
        self.assertIn("KNOWN_AREA_RADIUS = 6000.0", nav)
        chart = method_src(self.source, "Game", "draw_navigation_chart")
        self.assertIn("Known radius: 6,000 units (32 nm)", chart)


if __name__ == "__main__":
    unittest.main(verbosity=2)
