"""Headless route-editing, coordinate persistence, and autopilot contract tests."""
import ast
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.navigation_chart import (
    CHART_BOUNDS, MAX_CHART_WAYPOINTS, WaypointRoute, chart_to_pixel,
    chart_transform, pixel_to_chart,
)


class WaypointRouteModelTests(unittest.TestCase):
    def test_chart_to_pixel_roundtrip_keeps_design_coordinates(self):
        for size in ((900, 640), (400, 300), (1400, 780)):
            transform = chart_transform(*size)
            for expected in ((0.0, 0.0), (-3000.0, 2100.0), (6200.0, -3000.0)):
                pixel = chart_to_pixel(*expected, transform)
                got = pixel_to_chart(*pixel, transform)
                self.assertAlmostEqual(got[0], expected[0], delta=1.0 / max(transform[0], 1e-6))
                self.assertAlmostEqual(got[1], expected[1], delta=1.0 / max(transform[0], 1e-6))

    def test_eight_waypoint_cap(self):
        route = WaypointRoute()
        for i in range(MAX_CHART_WAYPOINTS):
            self.assertTrue(route.add((float(i * 700 + 500), 800.0), start=(0.0, 0.0)))
        self.assertEqual(len(route.points), 8)
        self.assertFalse(route.add((6200.0, 5000.0), start=(0.0, 0.0)))

    def test_invalid_and_out_of_chart_points_are_rejected(self):
        route = WaypointRoute()
        self.assertFalse(route.add((CHART_BOUNDS[2] + 1, 0), start=(0, 0)))
        self.assertFalse(route.add((math.nan, 0), start=(0, 0)))
        self.assertEqual(route.points, [])

    def test_zero_length_and_near_duplicate_legs_are_rejected(self):
        route = WaypointRoute()
        self.assertTrue(route.add((1000, 1000), start=(0, 0)))
        self.assertFalse(route.add((1000, 1000), start=(0, 0)))
        self.assertFalse(route.insert(0, (1010, 1010), start=(0, 0)))
        self.assertEqual(len(route.points), 1)

    def test_shift_insert_selects_leg_and_keeps_order(self):
        route = WaypointRoute([(1000.0, 1000.0), (2500.0, 1000.0)])
        hit = route.nearest_leg((1750.0, 1008.0), (0.0, 0.0), 50.0)
        self.assertIsNotNone(hit)
        index, distance, projected = hit
        self.assertEqual(index, 1)
        self.assertLess(distance, 50.0)
        self.assertTrue(route.insert(index, (1750.0, 1008.0), start=(0.0, 0.0)))
        self.assertEqual(route.points[1], (1750.0, 1008.0))
        self.assertEqual(len(route.points), 3)

    def test_nearest_leg_can_insert_before_first_waypoint(self):
        route = WaypointRoute([(1000.0, 1000.0)])
        hit = route.nearest_leg((450.0, 450.0), (0.0, 0.0), 50.0)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[0], 0)
        self.assertTrue(route.insert(hit[0], (450.0, 450.0), start=(0.0, 0.0)))
        self.assertEqual(route.points[0], (450.0, 450.0))

    def test_move_delete_and_empty_route(self):
        route = WaypointRoute([(1000.0, 1000.0), (2500.0, 1000.0)])
        self.assertTrue(route.move(0, (1100.0, 1200.0), start=(0.0, 0.0)))
        self.assertFalse(route.move(0, (9000.0, 0.0), start=(0.0, 0.0)))
        self.assertTrue(route.delete(0))
        self.assertFalse(route.delete(10))
        route.clear()
        self.assertEqual(route.points, [])

    def test_click_hit_testing_uses_configured_tolerance(self):
        route = WaypointRoute([(1000.0, 1000.0)])
        self.assertEqual(route.nearest_waypoint((1010, 1005), 20), 0)
        self.assertIsNone(route.nearest_waypoint((1100, 1000), 20))


class GameIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        game_cls = next(node for node in cls.tree.body if isinstance(node, ast.ClassDef) and node.name == "Game")
        cls.methods = {n.name: n for n in game_cls.body if isinstance(n, ast.FunctionDef)}
        world_cls = next(node for node in cls.tree.body if isinstance(node, ast.ClassDef) and node.name == "World")
        cls.world_methods = {n.name: n for n in world_cls.body if isinstance(n, ast.FunctionDef)}

    def method_source(self, methods, name):
        return ast.get_source_segment(self.source, methods[name])

    def test_chart_handler_supports_add_move_insert_delete_commit_and_clear(self):
        handler = self.method_source(self.methods, "handle")
        for token in ("_handle_chart_left_click", "_handle_chart_right_click", "_commit_chart_route", "_clear_chart_route"):
            self.assertIn(token, handler)
        self.assertIn("KMOD_SHIFT", handler)
        self.assertIn("K_RETURN", handler)
        self.assertIn("K_ESCAPE", handler)

    def test_course_persists_in_chart_coordinates_until_commit(self):
        draw = self.method_source(self.methods, "draw_navigation_chart")
        opener = self.method_source(self.methods, "_open_navigation_chart")
        commit = self.method_source(self.methods, "_commit_chart_route")
        self.assertIn("pixel_to_chart", self.source)
        self.assertIn("chart_to_pixel", draw)
        self.assertIn("WaypointRoute(points)", opener)
        self.assertIn("x * w.scale, y * w.scale", commit)

    def test_route_has_eight_point_cap_and_visible_numbered_legs(self):
        self.assertIn("MAX_CHART_WAYPOINTS = 8", (ROOT / "systems" / "navigation_chart.py").read_text(encoding="utf-8"))
        draw = self.method_source(self.methods, "draw_navigation_chart")
        self.assertIn("leg_nm", draw)
        self.assertIn("str(i + 1)", draw)
        self.assertIn("Waypoints: %d / %d", draw)

    def test_autopilot_consumes_reached_waypoints_in_order(self):
        autopilot = self.method_source(self.world_methods, "_autopilot")
        self.assertIn("self.route_waypoints.pop(0)", autopilot)
        self.assertIn("self.route_waypoints[0]", autopilot)
        self.assertIn("self.destination = V(self.route_waypoints[0])", autopilot)
        self.assertIn("Helm reached a plotted waypoint", autopilot)
        self.assertIn("Helm completed the plotted course", autopilot)

    def test_closing_chart_discards_staging_without_mutating_active_route(self):
        close = self.method_source(self.methods, "_close_navigation_chart")
        self.assertIn("self.chart_route_editor = None", close)
        self.assertNotIn("self.world.route_waypoints.clear()", close)
        self.assertNotIn("self.world.destination = None", close)

    def test_escape_clears_active_route_and_records_the_event(self):
        clear = self.method_source(self.methods, "_clear_chart_route")
        self.assertIn("w.route_waypoints.clear()", clear)
        self.assertIn("Manual chart course cleared with Escape.", clear)

    def test_new_destination_cancels_route_unless_explicitly_preserved(self):
        setter = self.method_source(self.world_methods, "set_destination")
        self.assertIn("preserve_route=False", setter)
        self.assertIn("if not preserve_route:", setter)
        self.assertIn("self.route_waypoints.clear()", setter)

    def test_auto_fishing_priority_is_explicit_and_logged(self):
        handle = self.method_source(self.methods, "handle")
        self.assertIn("Auto-fishing takes priority. Manual waypoint route cancelled.", handle)
        self.assertIn("Manual chart route cancelled because auto-fishing took priority.", handle)
        commit = self.method_source(self.methods, "_commit_chart_route")
        self.assertIn("self.line.auto or self.line.stage != \"off\"", commit)

    def test_docking_and_rescue_have_priority_over_manual_route_commit(self):
        commit = self.method_source(self.methods, "_commit_chart_route")
        self.assertIn("w.dock_state is not None", commit)
        self.assertIn("w.rescue_to is not None", commit)
        self.assertIn("self.crew.alarm_target is not None", commit)


if __name__ == "__main__":
    unittest.main()
