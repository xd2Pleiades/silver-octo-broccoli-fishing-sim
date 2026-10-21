"""Headless lifecycle, coordinate, weather and cap tests for the V18 foam model."""
import ast
import math
from collections import Counter
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.sea_foam import SeaFoamSystem, world_to_view


class SeaFoamModelTests(unittest.TestCase):
    def advance(self, *, sea, speed, seconds=8.0, dt=0.1, cap=240):
        foam = SeaFoamSystem(max_particles=cap, seed=1962)
        steps = int(round(seconds / dt))
        angle = 0.7
        for frame in range(steps):
            tick = frame * dt
            foam.update(
                dt,
                ship_position=(0.0, 0.0),
                heading=0.0,
                ship_speed_fraction=speed,
                sea_state=sea,
                wave_strength=sea,
                wave_direction=angle,
                ship_length=1100.0,
                ship_beam=280.0,
                current_velocity=(0.0, 0.0),
                visible_radius=1300.0,
                wave_height=lambda x, y: 30.0 * math.sin(
                    (x * math.cos(angle) + y * math.sin(angle)) / 120.0 + tick * 0.2
                ),
            )
        return foam

    def test_calm_stationary_water_does_not_emit_powered_wake(self):
        foam = self.advance(sea=0.05, speed=0.0, seconds=5.0)
        self.assertEqual(foam.active_count, 0)
        self.assertEqual(foam.emitted_total, 0)

    def test_rough_water_generates_whitecaps_without_ship_motion(self):
        foam = self.advance(sea=0.95, speed=0.0, seconds=10.0)
        kinds = Counter(p.kind for p in foam.patches)
        self.assertGreater(kinds["crest"], 0)
        self.assertLessEqual(foam.active_count, foam.max_particles)

    def test_powered_ship_emits_distinct_wake_categories(self):
        foam = self.advance(sea=0.5, speed=0.8, seconds=5.0)
        kinds = Counter(p.kind for p in foam.patches)
        self.assertGreater(kinds["wake"], 0)
        self.assertGreater(kinds["bow"] + kinds["side"], 0)

    def test_old_patches_stay_in_water_coordinates_when_ship_moves(self):
        foam = SeaFoamSystem(seed=4)
        foam.update(0.5, ship_position=(0, 0), heading=0,
                    ship_speed_fraction=1.0, sea_state=0.0, wave_strength=0.0,
                    wave_direction=0.0, ship_length=1100, ship_beam=280,
                    current_velocity=(0, 0), visible_radius=2000)
        self.assertTrue(foam.patches)
        patch = foam.patches[0]
        original = (patch.x, patch.y)
        foam.update(0.1, ship_position=(1600, 500), heading=1.2,
                    ship_speed_fraction=0.0, sea_state=0.0, wave_strength=0.0,
                    wave_direction=0.0, ship_length=1100, ship_beam=280,
                    current_velocity=(0, 0), visible_radius=5000)
        # The patch may drift slightly, but it remains in the old water area
        # instead of being rebased/rotated with the ship camera.
        self.assertLess(abs(patch.x - original[0]), 2.0)
        self.assertLess(abs(patch.y - original[1]), 2.0)

    def test_patch_lifecycle_ages_fades_and_expires(self):
        foam = SeaFoamSystem(seed=8)
        foam.update(0.3, ship_position=(0, 0), heading=0,
                    ship_speed_fraction=1.0, sea_state=0.0, wave_strength=0.0,
                    wave_direction=0.0, ship_length=1100, ship_beam=280,
                    current_velocity=(0, 0), visible_radius=5000)
        patch = foam.patches[0]
        patch.age = patch.lifetime * 0.5
        mid_opacity = patch.opacity
        patch.age = patch.lifetime - 0.2
        self.assertLess(patch.opacity, mid_opacity)
        patch.age = patch.lifetime
        foam.update(0.01, ship_position=(0, 0), heading=0,
                    ship_speed_fraction=0.0, sea_state=0.0, wave_strength=0.0,
                    wave_direction=0.0, ship_length=1100, ship_beam=280,
                    current_velocity=(0, 0), visible_radius=5000)
        self.assertNotIn(patch, foam.patches)

    def test_particle_cap_is_strict_under_heavy_conditions(self):
        foam = self.advance(sea=1.0, speed=1.0, seconds=25.0, dt=0.1, cap=64)
        self.assertLessEqual(foam.active_count, 64)
        self.assertLessEqual(foam.peak_active, 64)
        self.assertGreater(foam.recycled_total, 0)

    def test_heading_relative_projection_is_correct(self):
        self.assertEqual(world_to_view(10, 20, 10, 20, 1.0), (0.0, 0.0))
        x, y = world_to_view(110, 20, 10, 20, 0.0)
        self.assertAlmostEqual(x, 100.0)
        self.assertAlmostEqual(y, 0.0)
        # A point on the vessel's forward axis projects forward when heading is rotated.
        x, y = world_to_view(10 + 100 * math.cos(0.5), 20 + 100 * math.sin(0.5), 10, 20, 0.5)
        self.assertAlmostEqual(x, 100.0)
        self.assertAlmostEqual(y, 0.0)

    def test_renderer_shape_points_appends_to_its_initialized_list(self):
        # Prevent a runtime NameError in the render-only foam geometry helper.
        source_path = ROOT / "core" / "game.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        shape_functions = []
        class ShapePointFinder(ast.NodeVisitor):
            def visit_FunctionDef(self, node):
                if node.name == "shape_points":
                    shape_functions.append(node)
                self.generic_visit(node)
        ShapePointFinder().visit(tree)
        self.assertTrue(shape_functions, "expected a shape_points helper in the renderer")
        for function in shape_functions:
            initialized = set()
            appended = set()
            returned = set()
            for node in ast.walk(function):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.List) and not node.value.elts:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            initialized.add(target.id)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append":
                    if isinstance(node.func.value, ast.Name):
                        appended.add(node.func.value.id)
                elif isinstance(node, ast.Return) and isinstance(node.value, ast.Name):
                    returned.add(node.value.id)
            self.assertTrue(
                initialized & appended,
                f"{function.name} appends to {sorted(appended)} but initializes {sorted(initialized)}",
            )
            self.assertTrue(
                initialized & returned,
                f"{function.name} returns {sorted(returned)} but initializes {sorted(initialized)}",
            )

    def test_wake_emission_is_approximately_frame_rate_independent(self):
        slow_frames = self.advance(sea=0.1, speed=0.6, seconds=4.0, dt=0.1)
        fast_frames = self.advance(sea=0.1, speed=0.6, seconds=4.0, dt=0.05)
        # Counts can differ by one around an event boundary, but should not scale
        # with FPS as the old per-frame decorative puffs effectively did.
        self.assertLessEqual(abs(slow_frames.emitted_total - fast_frames.emitted_total), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
