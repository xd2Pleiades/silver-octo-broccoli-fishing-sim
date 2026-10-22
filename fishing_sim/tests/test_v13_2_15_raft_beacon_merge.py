"""Merge-contract checks: keep v13.2.15 systems while adding M9 liferaft beacons."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
GAME = (ROOT / "fishing_sim" / "core" / "game.py").read_text(encoding="utf-8")


class V13215RaftBeaconMergeTests(unittest.TestCase):
    def test_newer_chapter_a_and_b_systems_are_preserved(self):
        self.assertIn("from fishing_sim.systems import sailor_motion as motion", GAME)
        self.assertIn("from fishing_sim.systems.conversations import ConversationDirector", GAME)
        self.assertIn("self.crew_conversations = ConversationDirector", GAME)
        self.assertIn("def _update_bracing(self, dt):", GAME)
        self.assertIn("self.roll_rate_deg_s, self._roll_deg_prev = 0.0, 0.0", GAME)

    def test_ship_overhaul_geometry_and_static_helper_fix_are_preserved(self):
        self.assertIn('"aft_stores": (-0.470, -0.42, 0.085, 0.84)', GAME)
        self.assertIn('"engine_room": (-0.385, -0.45, 0.190, 0.90)', GAME)
        self.assertIn('self.cap_poly = self._inset_poly(self.hull, 4.0)', GAME)
        self.assertIn('"crew_quarters"', GAME)

    def test_survivor_registry_is_wired_to_save_load_and_both_rescue_roles(self):
        self.assertIn("from fishing_sim.systems.rescue_survivors import RescueSurvivorRegistry", GAME)
        self.assertIn('"rescue_survivors": self.rescue_survivor_registry.snapshot()', GAME)
        self.assertIn('RescueSurvivorRegistry.from_snapshot(data.get("rescue_survivors"))', GAME)
        self.assertIn("self.rescue_survivor_registry.complete_assistance(", GAME)
        self.assertIn("self.rescue_survivor_registry.update(", GAME)
        self.assertIn("has_active_survivors", GAME)

    def test_both_chart_planes_only_use_uncertain_reported_beacon_fixes(self):
        self.assertGreaterEqual(GAME.count("reported_liferaft_targets("), 2)
        self.assertIn("Amber diamond: radio-reported liferaft", GAME)
        self.assertIn('pygame.draw.ellipse(self.screen, (235, 171, 62)', GAME)

    def test_markdown_files_are_all_under_docs(self):
        outside = [p.relative_to(ROOT) for p in ROOT.rglob("*.md") if p.parent != ROOT / "docs"]
        self.assertEqual(outside, [])
        self.assertTrue((ROOT / "docs" / "CHAPTER_B_MOTION_STATUS.md").is_file())
        self.assertTrue((ROOT / "docs" / "RAFT_BEACON_MERGE_V13_2_15.md").is_file())


if __name__ == "__main__":
    unittest.main()
