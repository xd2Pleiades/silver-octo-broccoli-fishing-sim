"""Pure geometry and source-level contracts for v13.1.23 navigation/rescue refit."""
from pathlib import Path
import ast
import math
import unittest

from fishing_sim.systems.navigation import (
    along_track_distance, arrived, bearing_degrees, cross_track_error,
    distance, eta_minutes, heading_radians, leg_metrics,
    world_units_per_nautical_mile,
)
from fishing_sim.systems.helm import (
    desired_track_heading, engine_order_label, predicted_turn_arc, rudder_step, shortest_angle,
)
from fishing_sim.ui.ocean_plot import (
    clamp_relative_distance, extend_edge_target, screen_to_relative,
    visibility_allows_ocean_plot,
)

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"


def method_src(source, cls_name, method_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return ast.get_source_segment(source, node)


class NavigationGeometryTests(unittest.TestCase):
    def test_compass_bearings_are_north_clockwise(self):
        origin = (0, 0)
        self.assertAlmostEqual(bearing_degrees(origin, (0, -10)), 0.0)
        self.assertAlmostEqual(bearing_degrees(origin, (10, 0)), 90.0)
        self.assertAlmostEqual(bearing_degrees(origin, (0, 10)), 180.0)
        self.assertAlmostEqual(bearing_degrees(origin, (-10, 0)), 270.0)

    def test_heading_and_bearing_use_different_but_consistent_conventions(self):
        self.assertAlmostEqual(heading_radians((0, 0), (10, 0)), 0.0)
        self.assertAlmostEqual(heading_radians((0, 0), (0, 10)), math.pi / 2)
        self.assertAlmostEqual(bearing_degrees((0, 0), (10, 0)), 90.0)

    def test_cross_track_sign_and_along_track_progress(self):
        self.assertAlmostEqual(cross_track_error((50, 10), (0, 0), (100, 0)), 10.0)
        self.assertAlmostEqual(cross_track_error((50, -10), (0, 0), (100, 0)), -10.0)
        self.assertAlmostEqual(along_track_distance((50, 10), (0, 0), (100, 0)), 50.0)
        self.assertTrue(arrived((9, 0), (0, 0), 10))
        self.assertFalse(arrived((11, 0), (0, 0), 10))

    def test_world_distance_conversion_matches_the_chart_scale(self):
        self.assertAlmostEqual(world_units_per_nautical_mile(1.0), 185.2)
        self.assertAlmostEqual(world_units_per_nautical_mile(3.0), 555.6)
        self.assertAlmostEqual(555.6 / world_units_per_nautical_mile(3.0), 1.0)

    def test_distance_eta_and_leg_metrics(self):
        self.assertAlmostEqual(distance((0, 0), (3, 4)), 5.0)
        self.assertAlmostEqual(eta_minutes(1852 * 2, 5), 24.0)
        self.assertIsNone(eta_minutes(1000, 0))
        metrics = leg_metrics((0, 0), (1852, 0), (926, 25), 5, 1852)
        self.assertAlmostEqual(metrics["distance"], 1852)
        self.assertAlmostEqual(metrics["cross_track"], 25)
        self.assertAlmostEqual(metrics["eta_minutes"], 12.0)


class HelmAndVisibilityTests(unittest.TestCase):
    def test_ocean_plot_visibility_gates_dark_fog_and_heavy_rain(self):
        self.assertTrue(visibility_allows_ocean_plot(1.0, 0.0, 0.0, 10.0))
        self.assertFalse(visibility_allows_ocean_plot(0.1, 0.0, 0.0, 10.0))
        self.assertFalse(visibility_allows_ocean_plot(1.0, 0.8, 0.0, 2.0))
        self.assertFalse(visibility_allows_ocean_plot(1.0, 0.0, 0.9, 3.0))

    def test_screen_mapping_and_edge_extension_are_bounded(self):
        self.assertEqual(screen_to_relative((700, 350), (500, 250), 2), (100.0, 50.0))
        self.assertAlmostEqual(math.hypot(*clamp_relative_distance((300, 400), 100)), 100.0)
        normal = extend_edge_target((100, 0), (400, 200), (800, 400), 1, 1000)
        self.assertEqual(normal, (100.0, 0.0))
        edge = extend_edge_target((100, 0), (5, 200), (800, 400), 1, 500, extension_pixels=160)
        self.assertAlmostEqual(math.hypot(*edge), 260.0)
        cap = extend_edge_target((900, 0), (0, 200), (800, 400), 1, 500)
        self.assertAlmostEqual(math.hypot(*cap), 500.0)

    def test_rudder_rate_is_finite_and_angle_wrap_is_shortest_path(self):
        self.assertAlmostEqual(rudder_step(0, 1, 0.5, 0.6), 0.3)
        self.assertAlmostEqual(rudder_step(0.8, -1, 0.5, 0.6), 0.5)
        self.assertAlmostEqual(abs(shortest_angle(math.radians(1), math.radians(359))), math.radians(2), places=6)

    def test_skilled_helmsman_corrects_cross_track_more_cleanly(self):
        track = 0.0
        novice = desired_track_heading(track, 200, 800, 0.0, 10.0)
        skilled = desired_track_heading(track, 200, 800, 1.0, 10.0)
        self.assertLess(skilled, novice)
        self.assertLess(abs(skilled - track), math.pi / 2)

    def test_telegraph_and_predicted_turn_arc_are_readable(self):
        self.assertEqual(engine_order_label(0, 1), "STOP")
        self.assertEqual(engine_order_label(0.2, 1), "SLOW AHEAD")
        self.assertEqual(engine_order_label(0.8, 1), "FULL AHEAD")
        self.assertEqual(engine_order_label(0, -1), "STOP / ASTERN")
        self.assertEqual(engine_order_label(0, 1, True), "REVERSING — WAIT")
        arc = predicted_turn_arc((0, 0), 0, math.pi / 2, 100, 0.3)
        self.assertGreater(len(arc), 2)
        self.assertTrue(all(math.isfinite(v) for point in arc for v in point))


class GameIntegrationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GAME.read_text(encoding="utf-8")

    def test_world_motion_models_rudder_lag_reversing_and_environmental_set(self):
        update = method_src(self.source, "World", "update")
        self.assertIn("_update_propulsion_direction(dt)", update)
        self.assertIn("rudder_step", update)
        self.assertIn("current_set", update)
        self.assertIn("wind_leeway", update)
        self.assertIn("prop_walk", update)
        direction = method_src(self.source, "World", "_update_propulsion_direction")
        self.assertIn("self.speed <= 22.0", direction)
        self.assertIn("self.reversing_elapsed >= 2.4", direction)

    def test_route_controller_tracks_estimated_position_and_holds_slow_ahead(self):
        autopilot = method_src(self.source, "World", "_autopilot")
        self.assertIn("cross_track_error(self.believed_pos", autopilot)
        self.assertIn("desired_track_heading", autopilot)
        self.assertIn("self.route_origin", autopilot)
        self.assertIn("holding heading for orders", autopilot)
        self.assertIn("helm_ok and engine_ok", autopilot)

    def test_ocean_controls_distinguish_quick_order_from_persistent_plot(self):
        handle = method_src(self.source, "Game", "handle")
        self.assertIn("_handle_ocean_right_click(ev.pos, shift)", handle)
        self.assertIn("_finish_ocean_plot_drag(ev.pos)", handle)
        self.assertIn("pygame.KMOD_SHIFT", handle)
        quick = method_src(self.source, "Game", "_handle_ocean_right_click")
        plot = method_src(self.source, "Game", "_finish_ocean_plot_drag")
        self.assertIn("Quick order, not a plotted leg", quick)
        self.assertIn("w.route_waypoints = [V(end)] if near_ship else [V(start), V(end)]", plot)
        self.assertIn("visibility_allows_ocean_plot", method_src(self.source, "Game", "_ocean_visibility_ready"))

    def test_ocean_click_range_is_capped_to_nearby_visible_water(self):
        convert = method_src(self.source, "Game", "_ocean_world_at_screen")
        self.assertIn("min(1100.0 * w.scale", convert)
        self.assertIn("longer legs belong on the estimated-position chart", convert)
        self.assertIn("world_units_per_nautical_mile(w.scale)", self.source)
        self.assertNotIn("1852.0 * w.scale", self.source)

    def test_ocean_view_has_textual_helm_feedback_but_no_route_lines_on_water(self):
        draw = method_src(self.source, "Game", "draw_ocean_plot")
        self.assertIn("world_units_per_nautical_mile(w.scale)", draw)
        self.assertIn("cross_track_error", draw)
        self.assertIn("WIDE TURN / EXPECT OVERSHOOT", draw)
        self.assertIn("NO LINE IS DRAWN ON THE WATER", draw)
        self.assertNotIn("_draw_dashed_screen_line", draw)
        self.assertNotIn("predicted_turn_arc", draw)
        self.assertNotIn("pygame.draw.lines", draw)

    def test_persistent_course_editing_is_kept_on_the_chart_not_invisible_ocean_hitboxes(self):
        handle = method_src(self.source, "Game", "handle")
        ocean_branch = handle[handle.index("if ev.button == 3 and self.view_level() == Level.MAIN:"):]
        ocean_branch = ocean_branch.split("if ev.button == 1:", 1)[0]
        self.assertIn("Persistent course editing belongs on the chart table", ocean_branch)
        self.assertNotIn("_ocean_waypoint_at(ev.pos)", ocean_branch)
        quick = method_src(self.source, "Game", "_handle_ocean_right_click")
        self.assertNotIn("_ocean_waypoint_at", quick)

    def test_storm_rescue_turns_without_waiting_to_fully_stop_and_is_faster(self):
        rescue = method_src(self.source, "World", "_rescue_steer")
        self.assertNotIn("if self.speed > 28.0:\n            self.throttle = 0.0\n            return", rescue)
        self.assertIn("Do not just wait with the bow pointing away", rescue)
        self.assertIn("Captain is coming about now", self.source)
        self.assertIn("self.rescue_boat_assembly_elapsed > 18.0", self.source)
        self.assertIn('if boat["timer"] >= 1.45', self.source)
        self.assertIn('if boat["timer"] >= 1.65', self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
