"""Headless acceptance checks for v13v1-15 marine collisions, rescue routing, and HUD continuity."""
from pathlib import Path
import ast
import math
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def method_block(class_name, method_name):
    cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in cls.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name)
    return ast.get_source_segment(SOURCE, node)


class MarineCollisionGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        if str(ROOT.parent) not in sys.path:
            sys.path.insert(0, str(ROOT.parent))
        from fishing_sim.systems.marine_collisions import (
            resolve_circle_polygon, resolve_circle_segment, route_around_rect,
            segment_intersects_rect,
        )
        cls.resolve_circle_polygon = staticmethod(resolve_circle_polygon)
        cls.resolve_circle_segment = staticmethod(resolve_circle_segment)
        cls.route_around_rect = staticmethod(route_around_rect)
        cls.segment_intersects_rect = staticmethod(segment_intersects_rect)

    def test_circle_is_pushed_clear_of_rope_or_buoy_capsule(self):
        point, hit = self.resolve_circle_segment((5, 1), 8, (0, 0), (10, 0))
        self.assertTrue(hit)
        self.assertGreaterEqual(math.hypot(point[0] - 5, point[1]), 8.0)

    def test_buoy_or_hook_is_pushed_out_of_land_polygon(self):
        square = [(-10, -10), (10, -10), (10, 10), (-10, 10)]
        point, hit = self.resolve_circle_polygon((0, 0), 4, square)
        self.assertTrue(hit)
        self.assertFalse(-10 < point[0] < 10 and -10 < point[1] < 10)

    def test_rescue_route_goes_around_ship_hull_envelope(self):
        rect = (-20, 20, -30, 30)
        start, target = (0, -100), (0, 100)
        route = self.route_around_rect(start, target, rect)
        points = [start] + route
        self.assertGreater(len(route), 1)
        for a, b in zip(points, points[1:]):
            self.assertFalse(self.segment_intersects_rect(a, b, rect))
        self.assertEqual(route[-1], target)


class MarineCollisionIntegrationTests(unittest.TestCase):
    def test_longline_particles_and_rope_segments_are_collided_after_constraints(self):
        physics = method_block("Longline", "_physics")
        self.assertIn("w.collide_longline_point(", physics)
        self.assertIn("w.collide_longline_segment(", physics)
        self.assertIn('radius = 27.0 if p["float"] else 8.0', physics)
        self.assertIn("depth_m=depth_m", physics)
        self.assertIn("Keep the stern attachment anchored", physics)

    def test_world_line_collision_covers_land_reef_hull_and_rescue_boat(self):
        collision = method_block("World", "collide_longline_point")
        for expected in ("self._land_collision_bounds", "self._land_collision_polygon",
                         "self._reef_collision_bounds", "self._reef_collision_segment",
                         "self._hull_collision_bounds", "self._hull_collision_polygon",
                         "getattr(self.g, \"rescue_boat_state\", None)",
                         "within_expanded_bounds", "resolve_circle_polygon", "resolve_circle_segment"):
            self.assertIn(expected, collision)
        segment = method_block("World", "collide_longline_segment")
        self.assertIn("self.collide_longline_point", segment)
        self.assertIn("math.ceil(distance / step)", segment)

    def test_rescue_boat_collides_with_hull_land_reef_line_and_buoys(self):
        collision = method_block("World", "collide_rescue_boat_position")
        for expected in ("self._land_collision_bounds", "self._land_collision_polygon",
                         "self._reef_collision_bounds", "self._reef_collision_segment",
                         "self._hull_collision_bounds", "self._hull_collision_polygon",
                         "for point in line.pts", 'point.get("float")',
                         "segment_overlaps_bounds", "resolve_circle_polygon"):
            self.assertIn(expected, collision)
        self.assertIn("depth_m > 3.0", collision)

    def test_rescue_boat_uses_hull_avoidance_route_and_contact_resolution_outbound_and_return(self):
        waypoint = method_block("Game", "_rescue_boat_waypoint")
        mover = method_block("Game", "_move_rescue_boat")
        operation = method_block("Game", "_update_rescue_operation")
        self.assertIn("route_around_rect", waypoint)
        self.assertIn("self._rescue_boat_safe_target", waypoint)
        self.assertIn("w.collide_rescue_boat_position(proposed)", mover)
        self.assertIn("trial_fixed, trial_contact", mover)
        self.assertGreaterEqual(operation.count("self._move_rescue_boat("), 2)

    def test_rough_sea_ship_approach_is_slow_and_turns_starboard_rail_toward_swimmer(self):
        steer = method_block("World", "_rescue_steer")
        self.assertIn("approach_radius = self.g.ship.beam * 0.5 + 105.0", steer)
        self.assertIn("safe_aim = self._clear_heading(aim)", steer)
        self.assertIn("starboard_heading = bearing - math.pi / 2.0", steer)
        self.assertIn("self.throttle = 0.0", steer)

    def test_rescue_boat_people_have_an_explicit_starboard_facing_mark(self):
        draw = method_block("Game", "draw_rescue_boat")
        self.assertIn("Faces are deliberately turned to the boat's starboard gunwale (+y)", draw)
        self.assertIn("point(x, 4)", draw)
        self.assertIn("point(x, 9)", draw)

    def test_hotspots_retry_quickly_and_have_offshore_fallback(self):
        init = method_block("World", "__init__")
        spawn = method_block("World", "_spawn_hotspot")
        update = method_block("World", "_update_hotspots")
        self.assertIn("random.uniform(10.0, 18.0)", init)
        self.assertIn("attempts=48", spawn)
        self.assertIn("if ship_distance >= 3000.0", spawn)
        self.assertIn("min_distance=1000.0, max_distance=3600.0, attempts=32", spawn)
        self.assertIn("for radius_units in (1400.0, 1800.0, 2300.0, 2900.0, 3600.0, 4300.0)", spawn)
        self.assertIn("self.fishing_ground()", spawn)
        self.assertIn("random.uniform(45.0, 75.0)", update)
        self.assertIn("random.uniform(6.0, 12.0)", update)

    def test_hook_minimap_remains_removed_and_depth_hud_stays_under_cash(self):
        for symbol in ("draw_minimap", "MM_RECT", "mm_level", "mm_surf", "def mm_pt", "def mm_world"):
            self.assertNotIn(symbol, SOURCE)
        money = method_block("Game", "draw_money_counter")
        profile = method_block("Game", "draw_profile")
        hud = method_block("Game", "draw_hud")
        self.assertIn("pygame.Rect(W - width - 10, 10, width, 44)", money)
        self.assertIn("pygame.Rect(W - profile_w - 10, 82, profile_w, 110)", profile)
        self.assertIn("self.draw_profile()", method_block("Game", "draw"))
        self.assertLess(hud.index("self.draw_money_counter()"), hud.index("date_rect ="))


if __name__ == "__main__":
    unittest.main(verbosity=2)
