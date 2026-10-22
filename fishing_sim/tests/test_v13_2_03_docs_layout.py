"""Release-contract tests for the v13.2.03 central Markdown documentation layout."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
DOCS = PROJECT / "docs"


class DocumentationLayoutTests(unittest.TestCase):
    def test_every_markdown_file_lives_under_project_docs(self):
        outside = [p.relative_to(PROJECT).as_posix() for p in PROJECT.rglob("*.md")
                   if DOCS not in p.parents and p != DOCS]
        self.assertEqual(outside, [])
        nested = [p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*.md") if p.parent != DOCS]
        self.assertEqual(nested, [])

    def test_roadmap_plan_controls_and_changelog_are_centralized(self):
        for name in ("Roadmap_V13_2_Optimized.md", "Plan 13.2.xx.md", "CONTROLS.md",
                     "CHANGELOG_V13_2_03.md", "V13_2_03_IMPLEMENTATION_STATUS.md"):
            with self.subTest(name=name):
                self.assertTrue((DOCS / name).is_file())

    def test_document_move_preserves_required_zip_marker(self):
        marker = DOCS / "DO_NOT_REMOVE_THIS_IN_THE_ZIP.md"
        self.assertEqual(marker.read_text(encoding="utf-8").strip(), "DO NOT REMOVE THIS IN THE ZIP")

    def test_game_integrates_grid_without_replacing_player_weather(self):
        source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        self.assertIn("self.world_weather_grid = WeatherGrid(world_seed=1962, phase=\"A\")", source)
        self.assertIn("self.world_weather_grid.advance(w.time)", source)
        self.assertIn("responder_weather_phrase=(remote_weather.phrase", source)
        self.assertIn("self.weather.update(dt)", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
