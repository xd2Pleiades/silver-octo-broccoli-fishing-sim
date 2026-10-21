"""Headless source-contract checks for the v13v1-16 performance pass."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def class_source(class_name):
    node = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return ast.get_source_segment(SOURCE, node)


def method_source(class_name, method_name):
    cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in cls.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name)
    return ast.get_source_segment(SOURCE, node)


class RenderCacheTests(unittest.TestCase):
    def test_world_background_is_reused_between_refreshes(self):
        draw = method_source("World", "draw")
        self.assertIn('getattr(g, "_world_background_target", None)', draw)
        self.assertIn('g._world_background_target = target', draw)
        self.assertIn('age >= g._world_background_interval', draw)
        self.assertIn('screen.blit(g._world_background_cache, (0, 0))', draw)

    def test_world_background_and_ship_staging_surfaces_rebuilt_only_for_size(self):
        resize = method_source("Game", "resize")
        self.assertIn('self._world_background_target = pygame.Surface((W, H)).convert()', resize)
        self.assertIn('self._ship_static_target_surface = pygame.Surface((W, H), pygame.SRCALPHA).convert_alpha()', resize)
        ship = method_source("Game", "_draw_ship_cached")
        self.assertIn('getattr(self, "_ship_static_target_surface", None)', ship)
        self.assertIn('target.fill((0, 0, 0, 0))', ship)
        self.assertIn('self.ship.draw(self)', ship)
        self.assertIn('if target is None or target.get_size() != size:', ship)
        self.assertIn('self._ship_static_target_surface = target', ship)

    def test_font_render_and_ui_panels_use_bounded_caches(self):
        cached_font = class_source("CachedFont")
        self.assertIn('self._renders = OrderedDict()', cached_font)
        self.assertIn('self._sizes = OrderedDict()', cached_font)
        self.assertIn('self._renders.move_to_end(key)', cached_font)
        self.assertIn('self._renders.popitem(last=False)', cached_font)
        panel_cache = method_source("Game", "_cached_panel_surface")
        self.assertIn('self._ui_surface_cache', panel_cache)
        self.assertIn('pygame.Surface(size, pygame.SRCALPHA).convert_alpha()', panel_cache)

    def test_cash_date_and_telemetry_cards_use_cached_panel_surfaces(self):
        telemetry = method_source("Game", "draw_telemetry_panel")
        money = method_source("Game", "draw_money_counter")
        hud = method_source("Game", "draw_hud")
        self.assertIn('self._cached_panel_surface(', telemetry)
        self.assertIn('self._cached_panel_surface(', money)
        self.assertIn('self._cached_panel_surface(', hud)
        self.assertIn('self.hud_compact_font.render(', money)

    def test_static_background_surfaces_are_invalidated_on_resize(self):
        resize = method_source("Game", "resize")
        for expected in ('self._world_background_cache = None',
                         'self._world_background_state = None',
                         'self._ship_static_cache = None',
                         'self._profile_background_cache.clear()'):
            self.assertIn(expected, resize)


class SimulationHotPathTests(unittest.TestCase):
    def test_longline_particle_hull_collision_is_broad_phase_rejected(self):
        collision = method_source("World", "collide_longline_point")
        self.assertIn('self._hull_collision_radius + radius', collision)
        self.assertLess(collision.index('dx * dx + dy * dy <= hull_r * hull_r'),
                        collision.index('local = self.deck_of(p)'))
        self.assertIn('position if isinstance(position, V) else V(position)', collision)

    def test_rescue_collision_uses_the_same_hull_broad_phase(self):
        collision = method_source("World", "collide_rescue_boat_position")
        self.assertIn('self._hull_collision_radius + radius', collision)
        self.assertLess(collision.index('dx * dx + dy * dy <= hull_r * hull_r'),
                        collision.index('local = self.deck_of(p)'))

    def test_rope_solver_avoids_duplicate_vector_snapshot_and_extra_z_clamp_pass(self):
        physics = method_source("Longline", "_physics")
        self.assertIn('old.append((p["pos"].x, p["pos"].y, p["z"]))', physics)
        self.assertIn('ox, oy, oz = old[i]', physics)
        self.assertIn('# Clamp in the same pass', physics)
        self.assertNotIn('for p in pts:\n                if p["float"] or p["z"] < 0:', physics)

    def test_seeded_foam_math_and_normalized_shapes_are_bounded_cached(self):
        seeded = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_foam_seeded")
        shape = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_foam_shape_template")
        self.assertTrue(any(isinstance(d, ast.Call) and getattr(d.func, 'id', None) == 'lru_cache'
                            and any(k.arg == 'maxsize' and isinstance(k.value, ast.Constant) and k.value.value == 8192
                                    for k in d.keywords) for d in seeded.decorator_list))
        self.assertTrue(any(isinstance(d, ast.Call) and getattr(d.func, 'id', None) == 'lru_cache'
                            and any(k.arg == 'maxsize' and isinstance(k.value, ast.Constant) and k.value.value == 2048
                                    for k in d.keywords) for d in shape.decorator_list))
        wake = method_source("World", "_wake")
        self.assertIn('_foam_seeded(', wake)
        self.assertIn('_foam_shape_template(', wake)

    def test_fish_rotation_transforms_remain_in_a_bounded_cache(self):
        fish = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "draw_fish")
        fish_source = ast.get_source_segment(SOURCE, fish)
        self.assertIn('_fish_rotation_cache.get(rkey)', fish_source)
        self.assertIn('_fish_rotation_cache.move_to_end(rkey)', fish_source)
        self.assertIn('_FISH_ROTATION_CACHE_LIMIT', fish_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
