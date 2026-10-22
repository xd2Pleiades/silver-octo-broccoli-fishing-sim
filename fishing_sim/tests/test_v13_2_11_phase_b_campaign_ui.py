"""Phase B campaign/chart integration contracts; no pygame display needed."""
import ast
import math
import unittest
from pathlib import Path

from fishing_sim.systems.navigation_chart import WaypointRoute
from fishing_sim.world.coordinates import PHASE_B_BOUNDS_NM, HIGH_SEAS_PROJECTION
from fishing_sim.world.phase_adapter import (
    legacy_nm_to_phase_b_nm,
    phase_b_nm_to_legacy_nm,
    legacy_design_to_phase_b_nm,
    phase_b_nm_to_legacy_design,
    phase_b_legacy_design_bounds,
    phase_b_chart_bounds,
    phase_b_nm_inside,
)
from fishing_sim.world.weather_grid import WeatherGrid, WEATHER_TICK_INTERVAL_S

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT / "fishing_sim" / "core" / "game.py"


class PhaseBCampaignAdapterTests(unittest.TestCase):
    def test_legacy_phase_b_round_trip_is_stable(self):
        for point in ((0.0, 0.0), (500.0, -100.0), (1000.0, 500.0), (-500.0, 500.0)):
            restored = phase_b_nm_to_legacy_nm(legacy_nm_to_phase_b_nm(point))
            self.assertAlmostEqual(restored[0], point[0], places=7)
            self.assertAlmostEqual(restored[1], point[1], places=7)

    def test_legacy_design_waypoint_round_trip_keeps_screen_y_convention(self):
        for point in ((0.0, 0.0), (5000.0, -1500.0), (-2200.0, 4400.0)):
            restored = phase_b_nm_to_legacy_design(legacy_design_to_phase_b_nm(point))
            self.assertAlmostEqual(restored[0], point[0], places=5)
            self.assertAlmostEqual(restored[1], point[1], places=5)

    def test_phase_b_chart_bounds_invert_north_positive_y(self):
        min_x, max_x, min_y, max_y = PHASE_B_BOUNDS_NM
        chart_bounds = phase_b_chart_bounds()
        self.assertEqual(chart_bounds, (min_x, -max_y, max_x, -min_y))
        self.assertLess(chart_bounds[1], chart_bounds[3])
        self.assertTrue(phase_b_nm_inside((min_x, min_y)))
        self.assertTrue(phase_b_nm_inside((max_x, max_y)))

    def test_high_seas_chart_waypoints_are_accepted_by_route_editor(self):
        bounds = phase_b_legacy_design_bounds()
        editor = WaypointRoute(bounds=bounds)
        far_design = phase_b_nm_to_legacy_design(HIGH_SEAS_PROJECTION.to_nm(170.0, 55.0))
        self.assertTrue(editor.add(far_design, start=(0.0, 0.0)))
        self.assertEqual(editor.points[0], far_design)
        self.assertTrue(bounds[0] <= far_design[0] <= bounds[2])
        self.assertTrue(bounds[1] <= far_design[1] <= bounds[3])

    def test_unvisited_phase_weather_can_rebase_without_replaying_old_ticks(self):
        grid = WeatherGrid(1962, phase="B")
        target = 1234.0
        grid.rebase_time(target)
        before = grid.snapshot()
        grid.advance(target)
        after = grid.snapshot()
        self.assertEqual(grid.sim_time_s, target)
        self.assertEqual(grid.tick_index, math.floor((target + 1e-9) / WEATHER_TICK_INTERVAL_S))
        self.assertEqual(before["sim_time_s"], after["sim_time_s"])
        self.assertEqual(before["tick_index"], after["tick_index"])
        restored = WeatherGrid.from_snapshot(after)
        self.assertEqual(restored.phase, "B")
        self.assertEqual(restored.sim_time_s, target)


class PhaseBCampaignSourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GAME.read_text(encoding="utf-8")
        tree = ast.parse(cls.source)
        cls.game_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Game")
        cls.methods = {n.name: n for n in cls.game_class.body if isinstance(n, ast.FunctionDef)}

    def method_source(self, name):
        return ast.get_source_segment(self.source, self.methods[name])

    def test_chart_has_interactive_phase_tabs_and_phase_b_renderer(self):
        draw = self.method_source("draw_navigation_chart")
        handle = self.method_source("handle")
        self.assertIn('"A / REGIONAL"', draw)
        self.assertIn('"B / HIGH SEAS"', draw)
        self.assertIn("self._draw_phase_b_navigation_chart(map_rect, side_rect, outer)", draw)
        self.assertIn("self._set_campaign_phase(phase_hit)", handle)
        self.assertIn("self._select_phase_b_contact_at(ev.pos)", handle)
        phase_draw = self.method_source("_draw_phase_b_navigation_chart")
        self.assertIn("contacts.sort(key=lambda ship: (math.dist(player_nm, ship.last_reported_position_nm), ship.id))", phase_draw)

    def test_phase_b_route_editing_converts_y_and_returns_to_legacy_waypoint_units(self):
        point_method = self.method_source("_chart_design_point")
        draw = self.method_source("_draw_phase_b_navigation_chart")
        self.assertIn("phase_b_y_nm = -float(y)", point_method)
        self.assertIn("phase_b_nm_to_legacy_design((float(x), phase_b_y_nm))", point_method)
        self.assertIn("legacy_design_to_phase_b_nm(p)", draw)
        self.assertIn("Waypoint coordinates convert back to ship plane", draw)

    def test_sea_view_uses_active_phase_coordinate_adapter(self):
        draw = self.method_source("draw_ai_traffic")
        tow = self.method_source("_sync_tow_escort_world_entity")
        self.assertIn("self._active_nm_to_legacy_nm(ship.position_nm)", draw)
        self.assertIn("self._legacy_nm_to_active_nm(escort.world_position_nm)", tow)
        self.assertIn("self._legacy_nm_to_active_nm(escort.world_reported_position_nm)", tow)

    def test_phase_switch_caches_traffic_weather_and_relationship_dynamics(self):
        switch = self.method_source("_set_campaign_phase")
        self.assertIn("self._phase_traffic_worlds[current] = self.traffic_world", switch)
        self.assertIn("self._phase_weather_grids[current] = self.world_weather_grid", switch)
        self.assertIn("self._phase_relationship_dynamics[current] = self.relationship_dynamics", switch)
        self.assertIn("new_grid.rebase_time(self.world.time)", switch)
        self.assertIn("self.world_weather_grid.observe_local", switch)

    def test_career_save_persists_inactive_phase_snapshots(self):
        snap = self.method_source("_career_snapshot")
        validate = self.method_source("_validate_career_snapshot")
        restore = self.method_source("_restore_career_snapshot")
        self.assertIn('"inactive_phase_worlds": inactive_phase_worlds', snap)
        self.assertIn('snapshot.get("inactive_phase_worlds", {})', validate)
        self.assertIn('data.get("inactive_phase_worlds", {}).items()', restore)
        self.assertIn("phase_payload[\"traffic_contacts\"]", restore)
        self.assertIn("phase_payload[\"world_weather_grid\"]", restore)

    def test_full_game_version_is_v13_2_12(self):
        version = (ROOT / "fishing_sim" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "13.2.13"', version)


if __name__ == "__main__":
    unittest.main()
