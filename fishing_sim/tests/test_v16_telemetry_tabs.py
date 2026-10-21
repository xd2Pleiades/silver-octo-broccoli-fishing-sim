"""Source-contract regression checks for the compact 12v17 HUD and F1 details sheet."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

def method(class_name, method_name):
    cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return ast.get_source_segment(SOURCE, node)

class V17HudAndSheetTests(unittest.TestCase):
    def test_persistent_hud_is_two_line_critical_summary(self):
        lines = method("Game", "_compact_hud_lines")
        draw = method("Game", "draw_telemetry_panel")
        self.assertIn('return ["SPD %.1f kt  HDG %03d deg"', lines)
        self.assertIn('"MAN OVERBOARD"', lines)
        self.assertIn('"MUSTER %d/%d"', lines)
        self.assertIn('panel_w = min(230, max(194, W - 20))', draw)
        self.assertIn('lines = self._compact_hud_lines()', draw)
        self.assertNotIn('"SHIP & CATCH"', draw)
        self.assertNotIn('"TELEMETRY"', draw)

    def test_f7_switches_hud_mode_and_f8_hides_it(self):
        handle = method("Game", "handle")
        self.assertIn('self.hud_mode = "operations" if self.hud_mode == "navigation" else "navigation"', handle)
        self.assertIn('self.telemetry_visible = not self.telemetry_visible', handle)
        self.assertIn('if self.telemetry_panel_rect.collidepoint(ev.pos)', handle)

    def test_f1_sheet_has_three_detail_tabs_and_crew_subtabs(self):
        sheet = method("Game", "draw_crew_sheet")
        detail = method("Game", "_information_sheet_rows")
        self.assertIn('("ship_catch", "SHIP & CATCH")', sheet)
        self.assertIn('("telemetry", "TELEMETRY")', sheet)
        self.assertIn('("crew", "CREW")', sheet)
        self.assertIn('("shore", "SHORE")', sheet)
        self.assertIn('("hire", "HIRE")', sheet)
        self.assertIn('"ENGINE BILGE"', detail)
        self.assertIn('"HOLD CATCH"', detail)
        self.assertIn('"SPEED / HEADING"', detail)
        self.assertIn('"RADIO WATCH"', detail)

    def test_fishing_bar_geometry_avoids_hud_without_minimap_dependency(self):
        geometry = method("Game", "_fishing_bar_geometry")
        self.assertIn("left = self.telemetry_panel_rect.right + 8", geometry)
        self.assertIn("right = W - 10", geometry)
        self.assertIn("safe_width >= 260", geometry)
        self.assertNotIn("MM_RECT", geometry)
        self.assertNotIn("draw_minimap", SOURCE)

    def test_f1_opens_ship_catch_and_keeps_existing_shore_actions(self):
        handle = method("Game", "handle")
        sheet_action = method("Game", "_sheet_action")
        self.assertIn('self.info_sheet_tab = "ship_catch"', handle)
        self.assertIn('if action == "wait_shore":', sheet_action)
        self.assertIn('self._bring_sailor_aboard(value)', sheet_action)
        self.assertIn('self.hire_from_dock(value, stay_ashore=False)', sheet_action)
        self.assertIn('self.docked()', method("Game", "draw_crew_sheet"))

    def test_information_sheet_modal_freezes_world_except_explicit_shore_wait(self):
        update = method("Game", "update")
        self.assertIn('if self.crew_sheet_open and not self.shore_wait_active:', update)
        self.assertIn('return', update[update.index('if self.crew_sheet_open and not self.shore_wait_active:'):])

if __name__ == "__main__":
    unittest.main(verbosity=2)
