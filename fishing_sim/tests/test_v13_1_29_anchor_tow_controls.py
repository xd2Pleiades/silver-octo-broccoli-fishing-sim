import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"

class V13129AnchorTowControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GAME.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_anchor_is_keyboard_and_hud_control(self):
        self.assertIn("self.anchor_deployed = False", self.source)
        self.assertIn("elif k == pygame.K_a:", self.source)
        self.assertIn("anchor_hud_rect", self.source)
        self.assertIn("def toggle_anchor(self):", self.source)

    def test_anchor_reduces_drift_and_cancels_course(self):
        self.assertIn("self.ship_pos.lerp(nxt, 0.012)", self.source)
        self.assertIn("w.route_waypoints.clear()", self.source)
        self.assertIn("or bool(getattr(self.g, \"anchor_deployed\", False))", self.source)

    def test_no_fuel_empty_teleport_fallback(self):
        self.assertIn("def _update_tow_transit(self, dt):", self.source)
        self.assertIn("w.ship_pos += direction * step", self.source)
        self.assertNotIn('w.ship_pos, w.heading = V(w.berth + V(1500, 0)), math.pi', self.source)

    def test_out_of_fuel_requests_radio_and_retries(self):
        self.assertIn('accepted = self.radio_call("tow")', self.source)
        self.assertIn('"tow" in self.pending_radio_calls', self.source)
        self.assertIn("self.tow_retry_elapsed = 8.0", self.source)

    def test_controls_reference_mentions_anchor_and_tow(self):
        controls = (ROOT.parent / "CONTROLS.md").read_text(encoding="utf-8")
        self.assertIn("click **ANCHOR**", controls)
        self.assertIn("keeps transmitting", controls)

if __name__ == "__main__":
    unittest.main()
