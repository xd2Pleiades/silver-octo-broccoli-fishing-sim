"""Source-contract tests for V13V1-03 physical cues and persistent money HUD."""
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

class HotspotCueAndHudTests(unittest.TestCase):
    def test_cues_draw_after_water_and_before_line_and_crew(self):
        draw = method("Game", "draw")
        self.assertLess(draw.index("self.world.draw(self)"), draw.index("self.draw_hotspot_cues()"))
        self.assertLess(draw.index("self.draw_hotspot_cues()"), draw.index("self.line.draw(self)"))

    def test_physical_cues_include_tint_debris_ripples_and_working_gulls(self):
        cues = method("Game", "draw_hotspot_cues")
        for marker in ("spot.strength_now", "pygame.draw.circle(overlay", "debris_count", "ripple_count", "bird_count"):
            self.assertIn(marker, cues)
        self.assertNotIn("random.random()", cues)
        self.assertNotIn("gut marker", cues.lower())

    def test_cue_render_cost_is_bounded_by_active_hotspot_model(self):
        cues = method("Game", "draw_hotspot_cues")
        self.assertIn("for spot in self.world.hotspots", cues)
        self.assertIn("working_bird_count(strength)", cues)
        self.assertIn("render_extent = min(max(4, int(spot.radius * self.zoom * 0.82))", cues)
        self.assertIn("if not self.world.hotspots", cues)
        self.assertIn("if flotsam_visible(strength)", cues)
        self.assertIn("if ripples_visible(strength)", cues)

    def test_money_balance_and_earnings_are_always_rendered(self):
        counter = method("Game", "draw_money_counter")
        hud = method("Game", "draw_hud")
        self.assertIn('"CASH  ¥%s" % f"{self.cash:,}"', counter)
        self.assertIn('"TOTAL EARNED  ¥%s" % f"{self.earned:,}"', counter)
        self.assertIn("self.draw_money_counter()", hud)
        self.assertIn("self.cash += max(0, price)", SOURCE)

    def test_money_counter_is_independent_of_f8_telemetry_toggle(self):
        hud = method("Game", "draw_hud")
        self.assertLess(hud.index("self.draw_telemetry_panel()"), hud.index("self.draw_money_counter()"))
        counter = method("Game", "draw_money_counter")
        self.assertNotIn("telemetry_visible", counter)

    def test_no_minimap_and_profile_has_new_layout(self):
        for symbol in ("draw_minimap", "MM_RECT", "mm_level", "mm_surf", "def mm_pt", "def mm_world"):
            self.assertNotIn(symbol, SOURCE)
        profile = method("Game", "draw_profile")
        self.assertIn("profile_w = min(240, max(180, W // 3))", profile)
        self.assertNotIn("MM_RECT", profile)

if __name__ == "__main__":
    unittest.main(verbosity=2)
