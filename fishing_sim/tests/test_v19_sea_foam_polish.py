"""Regression checks for 12v19 foam texture and emission stability."""
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.sea_foam import SeaFoamSystem


class SeaFoamPolishTests(unittest.TestCase):
    @staticmethod
    def update(foam, dt, *, speed=0.0, sea=0.0, wind=0.45):
        foam.update(
            dt,
            ship_position=(0.0, 0.0),
            heading=0.0,
            ship_speed_fraction=speed,
            sea_state=sea,
            wave_strength=sea,
            wave_direction=0.6,
            ship_length=1100.0,
            ship_beam=280.0,
            current_velocity=(0.0, 0.0),
            visible_radius=1800.0,
            wind_strength=wind,
        )

    def test_slow_frame_does_not_queue_a_later_foam_dump(self):
        foam = SeaFoamSystem(seed=1962)
        self.update(foam, 10.0, speed=1.0, sea=0.0)
        first_total = foam.emitted_total
        self.assertGreater(first_total, 0)
        # A large frame must not leave an integral backlog in the emission timers.
        self.update(foam, 0.1, speed=0.0, sea=0.0)
        self.assertEqual(foam.emitted_total, first_total)

    def test_weather_wind_strength_is_part_of_the_public_update_contract(self):
        light_wind = SeaFoamSystem(seed=91)
        strong_wind = SeaFoamSystem(seed=91)
        self.update(light_wind, 1.0, speed=0.5, sea=0.6, wind=0.0)
        self.update(strong_wind, 1.0, speed=0.5, sea=0.6, wind=0.95)
        self.assertGreater(light_wind.active_count, 0)
        self.assertEqual(light_wind.active_count, strong_wind.active_count)
        displacement = sum(
            abs(a.x - b.x) + abs(a.y - b.y)
            for a, b in zip(light_wind.patches, strong_wind.patches)
        )
        self.assertGreater(displacement, 0.1)
        self.assertLessEqual(strong_wind.active_count, strong_wind.max_particles)

    def test_renderer_has_seeded_texture_and_layered_crest_detail(self):
        source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("Seeded micro-froth", source)
        self.assertIn("Ragged whitecap lips", source)
        self.assertIn("wind_strength=self.g.weather.wind", source)
        self.assertIn("wind_direction=self.g.weather.wind_dir", source)
        # Texture is derived from patch seeds and should not be regenerated randomly
        # during each render, which would create visual sparkle/flicker.
        wake_start = source.index("    def _wake(self, g, ov):")
        wake_end = source.index("\n    def _land(self, g):", wake_start)
        wake_source = source[wake_start:wake_end]
        self.assertIn("def seeded(seed, index, salt=0):", wake_source)
        self.assertNotIn("random.random(", wake_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
