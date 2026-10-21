"""Regression contracts for hauling alignment, storm steering, hatch work and context menus."""
from pathlib import Path
import ast
import math
import unittest

from fishing_sim.systems.gear_handling import starboard_roller_heading

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"


def method_src(source, cls_name, method_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return ast.get_source_segment(source, node)


class StarboardHaulingTests(unittest.TestCase):
    def test_heading_points_starboard_aft_quarter_toward_line_bearing(self):
        bearing = 1.16
        length, beam = 1100.0, 280.0
        heading = starboard_roller_heading(bearing, length, beam)
        pickup_angle = math.atan2(beam * 0.5, -length * 0.32)
        err = (heading + pickup_angle - bearing + math.pi) % (2 * math.pi) - math.pi
        self.assertAlmostEqual(err, 0.0, places=9)

    def test_heading_helper_is_finite_for_degenerate_dimensions(self):
        for bearing in (0.0, 0.3, math.pi, 5.9):
            result = starboard_roller_heading(bearing, 0.0, 0.0)
            self.assertTrue(math.isfinite(result))
            self.assertGreaterEqual(result, 0.0)
            self.assertLess(result, math.tau)


class DeckOperationsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GAME.read_text(encoding="utf-8")

    def test_haul_autopilot_uses_starboard_quarter_with_finite_turn_rate(self):
        autopilot = method_src(self.source, "World", "_autopilot")
        self.assertIn("line.phase == Longline.HAULING", autopilot)
        self.assertIn("starboard_roller_heading", autopilot)
        self.assertIn("self.turn_rate * authority * dt", autopilot)
        self.assertIn("self.g.ship.length * 0.32", autopilot)

    def test_buoys_and_line_spans_can_pause_hauling_as_a_physical_snag(self):
        exposure = method_src(self.source, "Longline", "_buoy_line_snag_exposure")
        update = method_src(self.source, "Longline", "_update_roller_and_line")
        self.assertIn("point.get(\"float\")", exposure)
        self.assertIn("closest_on_seg", exposure)
        self.assertIn("self.buoy_snag_meter", update)
        self.assertIn("starboard-quarter drum roller", update)
        haul = method_src(self.source, "Longline", "_tick_hauling")
        self.assertIn("if self.roller_snag_timer > 0.0", haul)

    def test_bow_task_uses_resolved_path_endpoint_instead_of_chasing_unsafe_goal(self):
        walk = method_src(self.source, "Sailor", "_walk")
        nav = method_src(self.source, "NavMap", "find_path")
        self.assertIn("self.path_target", walk)
        self.assertIn("self.path_target = V(planned[-1]) if planned else V(requested)", walk)
        self.assertIn("start_component", nav)
        self.assertIn("reachable = [cell for cell, component in self.comp.items()", nav)
        build = method_src(self.source, "Ship", "_build_nav")
        self.assertIn("self.below_solids, 17.0", build)

    def test_fish_stowing_automatically_opens_and_closes_ice_hold_hatch(self):
        dress = method_src(self.source, "Sailor", "_task_dress")
        self.assertIn("g._start_hatch_action(self, hatch_key, automatic=True)", dress)
        self.assertIn("Catch stowed", dress)
        finish = method_src(self.source, "Game", "_finish_deck_action")
        self.assertIn("elif sailor.auto_close_hatch == key", finish)
        self.assertIn("automatically.", finish)

    def test_context_hatch_order_routes_sailor_and_works_only_at_hatch(self):
        queue = method_src(self.source, "Game", "_queue_hatch_context_order")
        sailor = method_src(self.source, "Sailor", "_aboard")
        self.assertIn("sailor.order_to(pos, sailor.level)", queue)
        self.assertIn("sailor.hatch_order", queue)
        self.assertIn("self.g._start_hatch_action(self, key, automatic=False)", sailor)
        self.assertIn("self.pos.distance_to(order.get(\"pos\", self.pos)) <= 58.0", sailor)

    def test_context_menu_covers_objects_and_empty_walkable_deck(self):
        menu = method_src(self.source, "Game", "_open_context_menu_at")
        draw = method_src(self.source, "Game", "draw_context_menu")
        action = method_src(self.source, "Game", "_perform_context_action")
        handle = method_src(self.source, "Game", "handle")
        self.assertIn("DECK ORDER", menu)
        self.assertIn("FISHING GEAR", menu)
        self.assertIn("hatch_order", menu)
        self.assertIn("STERN ROLLER", menu.upper())
        self.assertIn("pygame.Rect", draw)
        self.assertIn("move_here", action)
        self.assertIn("_open_context_menu_at(ev.pos, d)", handle)

    def test_storm_degrades_ocean_order_range_instead_of_disabling_steering(self):
        allowed = method_src(self.source, "Game", "_ocean_plot_order_allowed")
        convert = method_src(self.source, "Game", "_ocean_world_at_screen")
        self.assertIn("Poor visibility", allowed)
        self.assertIn("persistent=False", allowed)
        self.assertNotIn("if not self._ocean_visibility_ready():\n            # A skipper may still make a short visual manoeuvre in bad weather.\n            # The target conversion below sharply reduces the range and uncertainty\n            # grows with rain, fog and darkness; the chart remains the long-leg tool.\n            self.crew.say(\"Captain: Poor visibility. Keep that ocean mark close; use the chart for any longer leg.\")\n            return False", allowed)
        self.assertIn("quality = clamp", convert)
        self.assertIn("self.weather.fog", convert)
        self.assertIn("self.weather.rain", convert)

    def test_manual_haul_allows_short_steer_to_but_persistent_plot_waits_for_gear(self):
        allowed = method_src(self.source, "Game", "_ocean_plot_order_allowed")
        quick = method_src(self.source, "Game", "_handle_ocean_right_click")
        drag = method_src(self.source, "Game", "_finish_ocean_plot_drag")
        self.assertIn("Longline.SOAKING, Longline.HAULING", allowed)
        self.assertIn("persistent=shift", quick)
        self.assertIn("persistent=True", drag)
        self.assertIn("self.line.stage != \"off\"", allowed)

    def test_completed_plots_discard_waypoints_and_stale_origin(self):
        autopilot = method_src(self.source, "World", "_autopilot")
        self.assertIn("self.route_origin = None  # completed A→B geometry is discarded", autopilot)
        self.assertIn("plot erased", autopilot)
        self.assertIn("self.route_origin = None  # no stale course origin", autopilot)

    def test_snag_context_order_sends_a_hand_to_the_stern(self):
        queue = method_src(self.source, "Game", "_queue_stern_snag_clear")
        perform = method_src(self.source, "Game", "_perform_context_action")
        sailor = method_src(self.source, "Sailor", "_aboard")
        self.assertIn("sailor.order_to(target, Level.MAIN)", queue)
        self.assertIn("gear_order = \"clear_snag\"", queue)
        self.assertIn("self._queue_stern_snag_clear(sailor)", perform)
        self.assertIn("self.g.line.operate_roller(self)", sailor)

    def test_hold_ladder_operates_the_cover_it_is_physically_aligned_with(self):
        link_key = method_src(self.source, "Ship", "hatch_key_for_link")
        self.assertIn('if link.name == "hold ladder":', link_key)
        self.assertIn('return "hold_1"', link_key)
        finish = method_src(self.source, "Game", "_finish_deck_action")
        self.assertIn('"hold_1": "aft ice-hold hatch"', finish)
        self.assertIn('"hold_2": "forward ice-hold hatch"', finish)


if __name__ == "__main__":
    unittest.main(verbosity=2)
