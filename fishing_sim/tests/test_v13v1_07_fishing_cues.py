"""Headless contracts for proportional fishing cues and crew discovery (V13V1-07)."""
from pathlib import Path
import ast
import unittest

from fishing_sim.systems.hotspot_visuals import (
    flotsam_visible, follow_bird_count, lookout_confidence_rate,
    lookout_detection_range, ripples_visible, screen_edge_intersection,
    working_bird_count, working_bird_half_span, working_bird_orbit_radius,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

def method(class_name, method_name):
    cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return ast.get_source_segment(SOURCE, node)


class HotspotVisualRulesTests(unittest.TestCase):
    def test_working_gulls_are_sailor_scale_at_normal_zoom(self):
        # A sailor's torso is about 24 screen pixels wide at zoom 0.6.
        self.assertGreaterEqual(2 * working_bird_half_span(0.4, 0.6), 24)
        self.assertGreaterEqual(2 * working_bird_half_span(1.0, 0.6), 32)

    def test_stronger_hotspot_has_more_tightly_clustered_birds(self):
        self.assertGreater(working_bird_count(1.0), working_bird_count(0.2))
        self.assertLess(working_bird_orbit_radius(1.0, 0.6), working_bird_orbit_radius(0.2, 0.6))
        self.assertEqual(working_bird_count(0.14), 0)

    def test_fading_hotspot_spreads_birds_out_and_reduces_count(self):
        self.assertGreater(working_bird_orbit_radius(0.2), working_bird_orbit_radius(0.8))
        self.assertGreater(working_bird_count(0.8), working_bird_count(0.2))

    def test_flotsam_and_ripples_follow_exact_strength_thresholds(self):
        self.assertFalse(flotsam_visible(0.299))
        self.assertTrue(flotsam_visible(0.30))
        self.assertFalse(ripples_visible(0.199))
        self.assertTrue(ripples_visible(0.20))

    def test_lookout_range_rewards_skill_and_visibility(self):
        deckhand = lookout_detection_range(0.2, 10, 1.0)
        veteran = lookout_detection_range(0.8, 10, 1.0)
        fogged = lookout_detection_range(0.8, 1.0, 1.0)
        night = lookout_detection_range(0.8, 10, 0.1)
        self.assertLess(deckhand, veteran)
        self.assertLess(fogged, veteran)
        self.assertLess(night, veteran)
        self.assertLessEqual(veteran, 2000)

    def test_veteran_builds_confidence_faster_than_green_hand(self):
        self.assertGreater(lookout_confidence_rate(0.8), lookout_confidence_rate(0.2))
        self.assertGreater(lookout_confidence_rate(0.8) * 20, 0.5)

    def test_follow_birds_only_when_fishing_in_daylight_and_no_storm(self):
        self.assertEqual(follow_bird_count(0, 1.0, 0.0), 0)
        self.assertEqual(follow_bird_count(1, 1.0, 0.0), 8)
        self.assertEqual(follow_bird_count(2, 1.0, 0.0), 4)
        self.assertEqual(follow_bird_count(3, 1.0, 0.0), 14)
        self.assertEqual(follow_bird_count(3, 0.2, 0.0), 0)
        self.assertEqual(follow_bird_count(3, 1.0, 0.61), 0)

    def test_edge_arrow_intersects_safe_screen_edge(self):
        x, y = screen_edge_intersection(1280, 800, (1800, 180), margin=46)
        self.assertGreaterEqual(x, 46)
        self.assertLessEqual(x, 1280 - 46)
        self.assertGreaterEqual(y, 46)
        self.assertLessEqual(y, 800 - 46)
        self.assertGreater(x, 640)


class HotspotVisualIntegrationTests(unittest.TestCase):
    def test_sailors_own_confidence_state_and_update_uses_lookout_rules(self):
        sailor_init = method("Sailor", "__init__")
        update = method("Game", "_update_hotspot_lookouts")
        self.assertIn("self.gut_spot, self.gut_confidence, self.gut_last_comment", sailor_init)
        self.assertIn("lookout_detection_range", update)
        self.assertIn("lookout_confidence_rate", update)
        self.assertIn("math.pi * 0.5", update)
        self.assertIn("best.detected_by is None", update)

    def test_marker_requires_half_confidence_and_draws_edge_arrow(self):
        markers = method("Game", "draw_hotspot_lookout_markers")
        self.assertIn("if confidence < 0.5", markers)
        self.assertIn("screen_edge_intersection", markers)
        self.assertIn("pygame.draw.polygon(overlay, fill, pts)", markers)

    def test_follow_birds_are_removed_at_night_or_storm_and_drawn_before_hud(self):
        update = method("Game", "_update_follow_birds")
        draw_birds = method("Game", "draw_follow_birds")
        draw = method("Game", "draw")
        self.assertIn("follow_bird_count", update)
        self.assertIn("self.weather.storm", update)
        self.assertIn("pygame.draw.lines(self.screen", draw_birds)
        self.assertLess(draw.index("self.draw_follow_birds()"), draw.index("self.draw_hud()"))

    def test_physical_cues_are_drawn_without_any_sailor_detection(self):
        cues = method("Game", "draw_hotspot_cues")
        self.assertIn("tint_radii", cues)
        self.assertIn("flotsam_visible(strength)", cues)
        self.assertIn("ripples_visible(strength)", cues)
        self.assertIn("working_bird_half_span(strength, self.zoom)", cues)
        self.assertNotIn("gut_confidence", cues)


if __name__ == "__main__":
    unittest.main(verbosity=2)
