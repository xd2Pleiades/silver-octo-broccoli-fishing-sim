from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "core" / "game.py").read_text(encoding="utf-8")

class V13SourceContracts(unittest.TestCase):
    def test_muster_does_not_exempt_station_keepers(self):
        block = SOURCE.split("def start_muster(self):", 1)[1].split("def _muster_arrive", 1)[0]
        self.assertNotIn('"on helm watch"', block)
        self.assertNotIn('"on radio watch"', block)
        self.assertNotIn('"on engine watch"', block)

    def test_fishing_overlay_toggle_and_top_position(self):
        self.assertIn("pygame.K_F6", SOURCE)
        self.assertIn("self.show_fishing_minigame", SOURCE)
        self.assertIn("return int(clamp(target, 42, max(42, H - 96)))", SOURCE)

    def test_space_gives_manual_tension_and_gaff(self):
        self.assertIn("keys[pygame.K_SPACE]", SOURCE)
        self.assertIn('gf["manual"] = bool(keys[pygame.K_SPACE])', SOURCE)
        self.assertIn("SPACE: heave", SOURCE)

    def test_storm_bucket_line_assigns_real_tasks_and_requires_hands_at_station(self):
        self.assertIn("self.engine_flood", SOURCE)
        self.assertIn("self.bucket_count", SOURCE)
        self.assertIn("def _update_bucket_chain(self, dt):", SOURCE)
        self.assertIn('sailor._enter("bucket")', SOURCE)
        self.assertIn("self._go_to(target, 28.0, Level.MAIN)", SOURCE)
        self.assertIn("len(working) >= 2", SOURCE)
        self.assertIn("throws it over the stern", SOURCE)
        self.assertIn("bails water from the engine-room bilge with a bucket", SOURCE)
        # Buckets are reusable equipment, not consumed every time someone bails.
        self.assertNotIn("self.ship.bucket_count -= 1", SOURCE)

    def test_slip_overboard_has_defined_game_reference_and_single_fall_transition(self):
        move = SOURCE.split("def _move(self, dt):", 1)[1].split("def _plan_path", 1)[0]
        self.assertIn("g = self.g", move)
        self.assertIn("for ea, eb in g.ship.open_edges", move)
        self.assertIn("self._fall()", move)
        self.assertIn("slips over the side", SOURCE)
        aboard = SOURCE.split("def _aboard(self, dt):", 1)[1].split("def _plan_path", 1)[0]
        self.assertIn("self.mode == self.ABOARD and self.level == Level.MAIN", aboard)

if __name__ == "__main__":
    unittest.main()
