import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"

class V13126RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GAME.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_debug_map_is_opt_in(self):
        self.assertIn("self.longline_minimap_debug = False", self.source)
        self.assertIn("if self.longline_minimap_debug:", self.source)
        self.assertIn("pygame.K_F10", self.source)

    def test_compass_and_wind_direction_hud(self):
        self.assertIn('"COMPASS  %03d°"', self.source)
        self.assertIn('"WIND %03d°"', self.source)

    def test_cabin_health_recovery_is_capped(self):
        self.assertIn("self.health < 0.60", self.source)
        self.assertIn("min(0.60, self.health + 0.0011 * dt)", self.source)

    def test_tow_retry_and_signal_quality(self):
        self.assertIn("self.tow_retry_elapsed", self.source)
        self.assertIn('self.radio_call("tow")', self.source)
        self.assertIn('getattr(self.radio, "signal_quality", 0.65)', self.source)

    def test_foundering_triggers_abandon_ship_state(self):
        self.assertIn("foundering =", self.source)
        self.assertIn("self.abandon_ship_started = True", self.source)
        self.assertIn("Sailor.SWIMMING, \"swim\"", self.source)

if __name__ == "__main__":
    unittest.main()
