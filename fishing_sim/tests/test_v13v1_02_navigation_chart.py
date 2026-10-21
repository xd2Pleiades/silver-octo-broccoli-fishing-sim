"""Headless geometry, determinism, and integration checks for V13V1-02."""
import ast
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.navigation_chart import (
    CHART_BOUNDS, KNOWN_AREA_RADIUS, chart_transform, chart_to_pixel,
    clamp_to_chart_bounds, clip_segment_to_bounds, generate_soundings,
    within_chart_bounds,
)


class ChartGeometryTests(unittest.TestCase):
    def test_transform_keeps_landmarks_inside_local_surface(self):
        transform = chart_transform(900, 640)
        for x, y in ((0, 0), (-3000, 0), (3000, 0), (0, -3000), (0, 3000)):
            px, py = chart_to_pixel(x, y, transform)
            self.assertGreaterEqual(px, 0)
            self.assertLessEqual(px, 900)
            self.assertGreaterEqual(py, 0)
            self.assertLessEqual(py, 640)

    def test_small_chart_transform_is_finite(self):
        transform = chart_transform(1, 1)
        self.assertTrue(all(math.isfinite(v) for v in transform))
        self.assertGreaterEqual(transform[0], 0.0)

    def test_clamping_and_bounds(self):
        self.assertTrue(within_chart_bounds(0, 0))
        self.assertFalse(within_chart_bounds(13000, 0))
        self.assertEqual(clamp_to_chart_bounds(14000, -14000), (CHART_BOUNDS[2], CHART_BOUNDS[1]))

    def test_segment_clips_when_crossing_map_boundary(self):
        clipped = clip_segment_to_bounds((0, 0), (14000, 0))
        self.assertIsNotNone(clipped)
        self.assertAlmostEqual(clipped[0][0], 0)
        self.assertAlmostEqual(clipped[1][0], CHART_BOUNDS[2])
        self.assertTrue(within_chart_bounds(*clipped[0]))
        self.assertTrue(within_chart_bounds(*clipped[1]))

    def test_segment_outside_same_side_is_rejected(self):
        self.assertIsNone(clip_segment_to_bounds((14000, 100), (15000, 200)))

    def test_soundings_are_stable_and_inside_known_radius(self):
        bottom = lambda d: 25 + 700 * min(1.0, max(0.0, (d - 300) / 4200))
        is_land = lambda x, y: (x < -1000 and y < 1000)
        one = generate_soundings(is_land, bottom)
        two = generate_soundings(is_land, bottom)
        self.assertEqual(one, two)
        self.assertGreater(len(one), 100)
        self.assertGreater(KNOWN_AREA_RADIUS, 5000.0)
        self.assertGreater(CHART_BOUNDS[2] - CHART_BOUNDS[0], 20000.0)
        for x, y, depth in one:
            self.assertLessEqual(math.hypot(x, y), KNOWN_AREA_RADIUS)
            self.assertFalse(is_land(x, y))
            self.assertGreater(depth, 0)

    def test_land_exclusion_removes_only_affected_soundings(self):
        bottom = lambda d: 100.0
        all_sea = generate_soundings(lambda x, y: False, bottom)
        one_land_cell = generate_soundings(lambda x, y: x == 0 and y == 0, bottom)
        self.assertEqual(len(all_sea) - len(one_land_cell), 1)
        self.assertNotIn((0.0, 0.0), [(x, y) for x, y, _depth in one_land_cell])


class GameIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_game_imports_pure_chart_helpers(self):
        self.assertIn("from fishing_sim.systems.navigation_chart import", self.source)
        for symbol in ("generate_soundings", "chart_transform", "chart_to_pixel", "clip_segment_to_bounds"):
            self.assertIn(symbol, self.source)

    def test_chart_remains_available_by_keyboard_after_minimap_removal(self):
        self.assertIn("pygame.K_c", self.source)
        self.assertIn("self.chart_open = True", self.source)
        self.assertNotIn("_minimap_caption_rect", self.source)
        self.assertNotIn("draw_minimap", self.source)

    def test_draw_path_renders_chart_over_game(self):
        game_cls = next(node for node in self.tree.body
                        if isinstance(node, ast.ClassDef) and node.name == "Game")
        methods = {n.name: n for n in game_cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        draw_source = ast.get_source_segment(self.source, methods["draw"])
        self.assertIn("draw_navigation_chart", draw_source)
        self.assertIn("def draw_navigation_chart", self.source)

    def test_chart_supports_waypoint_editing_but_position_fixes_remain_later(self):
        # The chart became interactive in v13v1-06; position fixes remain v13v1-07.
        self.assertIn("_handle_chart_left_click", self.source)
        self.assertIn("_commit_chart_route", self.source)
        self.assertNotIn("fix_landmark(", self.source)

    def test_chart_masks_held_gameplay_keys_but_keeps_update_running(self):
        game_cls = next(node for node in self.tree.body
                        if isinstance(node, ast.ClassDef) and node.name == "Game")
        update_node = next(node for node in game_cls.body
                           if isinstance(node, ast.FunctionDef) and node.name == "update")
        update_source = ast.get_source_segment(self.source, update_node)
        self.assertIn("if self.chart_open", update_source)
        self.assertIn("keys = _NO_GAMEPLAY_KEYS", update_source)
        self.assertIn("w = self.world", update_source)

    def test_minimap_state_rendering_and_click_steering_are_removed(self):
        for symbol in ("MM_RECT", "MM_HALVES", "draw_minimap", "mm_world", "mm_level"):
            self.assertNotIn(symbol, self.source)
        handle_source = self.source.split("def handle(self, ev):", 1)[1].split("# --- simulation", 1)[0]
        self.assertNotIn("self.world.set_destination(self.mm_world(ev.pos))", handle_source)
        self.assertIn("pygame.K_c", handle_source)

    def test_resize_invalidates_static_chart_cache(self):
        game_cls = next(node for node in self.tree.body
                        if isinstance(node, ast.ClassDef) and node.name == "Game")
        resize_node = next(node for node in game_cls.body
                           if isinstance(node, ast.FunctionDef) and node.name == "resize")
        resize_source = ast.get_source_segment(self.source, resize_node)
        self.assertIn("self._chart_base_surface = None", resize_source)
        self.assertIn("self._chart_transform = None", resize_source)


if __name__ == "__main__":
    unittest.main()
