"""Static tests for scaled sprites and speed/sea-state foam in 12v17."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

def method(cls_name, method_name):
    cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return ast.get_source_segment(SOURCE, node)

class V17VisualPassTests(unittest.TestCase):
    def test_rescue_boat_has_person_sized_hull_seats_oars_and_occupants(self):
        boat = method("Game", "draw_rescue_boat")
        self.assertIn("176 x 66 world units", boat)
        self.assertIn("hull = [point(90, 0)", boat)
        self.assertIn("def seated_sailor", boat)
        self.assertIn("Oar blades extend outboard", boat)
        self.assertIn('boat.get("passenger")', boat)

    def test_sailor_uniforms_have_highlights_and_role_trim(self):
        sailor = method("Sailor", "draw")
        self.assertIn("jacket_light = mix(self.jacket", sailor)
        self.assertIn("collar = [P(-5, -13)", sailor)
        self.assertIn("if self.role == self.CAPTAIN:", sailor)
        self.assertIn("pygame.draw.lines(s, jacket_light, True, pocket", sailor)

    def test_bucket_prop_is_larger_and_recognizable(self):
        sailor = method("Sailor", "draw")
        self.assertIn('bw = max(10, int(18 * sc * z))', sailor)
        self.assertIn('bh = max(12, int(20 * sc * z))', sailor)
        self.assertIn('(116, 78, 43)', sailor)
        self.assertIn('(104, 184, 202)', sailor)

    def test_foam_uses_persistent_world_space_patches(self):
        wake = method("World", "_wake")
        update = method("World", "update")
        self.assertIn('self.foam.patches', wake)
        self.assertIn('world_to_view(patch.x, patch.y', wake)
        self.assertIn('SeaFoamSystem', SOURCE)
        self.assertIn('self.foam.update(', update)
        self.assertIn('ship_speed_fraction=self.speed / max(1.0, self.max_speed)', update)
        self.assertIn('wave_height=lambda x, y: self.waves.height(V(x, y))', update)

    def test_foam_draws_before_hull_and_rescue_boat_remains_above_water(self):
        world_draw = method("World", "draw")
        game_draw = method("Game", "draw")
        self.assertIn('self._wake(g, ov)', world_draw)
        self.assertLess(world_draw.index('self._wake(g, ov)'), world_draw.index('target.blit(ov, (0, 0))'))
        self.assertIn('self.draw_rescue_boat()', game_draw)
        self.assertIn('self._draw_ship_cached()', game_draw)

if __name__ == "__main__":
    unittest.main(verbosity=2)
