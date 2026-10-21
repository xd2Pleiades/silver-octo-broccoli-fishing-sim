"""Headless acceptance tests for V13V1-11 auto-fishing hotspot hunting and speech routing."""
import ast
import copy
import re
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.hotspots import (
    AUTO_HUNT_MIN_CONFIDENCE,
    AUTO_HUNT_MIN_STRENGTH,
    Hotspot,
    estimated_hotspot_destination,
    select_detected_hotspot,
)


class HotspotHuntModelTests(unittest.TestCase):
    def setUp(self):
        self.strong = Hotspot(1000, 2000, "yellowfin", strength=0.9, radius=1600, life=600)
        self.mixed = Hotspot(3000, 4000, "mixed", strength=0.7, radius=1800, life=600)

    @staticmethod
    def lookout(spot, confidence):
        return types.SimpleNamespace(gut_spot=spot, gut_confidence=confidence)

    def test_hunt_requires_confidence_and_strength_above_plan_thresholds(self):
        candidates = [
            self.lookout(self.strong, AUTO_HUNT_MIN_CONFIDENCE),
            self.lookout(self.mixed, 0.95),
        ]
        self.strong.strength_now = AUTO_HUNT_MIN_STRENGTH
        self.mixed.strength_now = AUTO_HUNT_MIN_STRENGTH
        self.assertIsNone(select_detected_hotspot(candidates, [self.strong, self.mixed]))

    def test_selects_best_credible_school_and_ignores_stale_references(self):
        deckhand = self.lookout(self.strong, 0.78)
        veteran = self.lookout(self.mixed, 0.95)
        self.assertIs(select_detected_hotspot([deckhand, veteran], [self.strong, self.mixed]), self.strong)
        self.assertIsNone(select_detected_hotspot([veteran], [self.strong]))

    def test_destination_carries_dead_reckoning_error_without_mutating_hotspot(self):
        estimate = estimated_hotspot_destination(self.strong.pos, (125.0, -240.0))
        self.assertEqual(estimate, (1125.0, 1760.0))
        self.assertEqual(self.strong.pos, (1000.0, 2000.0))

    def test_expired_and_weak_targets_do_not_remain_eligible(self):
        lookout = self.lookout(self.strong, 0.99)
        self.strong.strength_now = 0.35
        self.assertIsNone(select_detected_hotspot([lookout], [self.strong]))
        self.strong.strength_now = 0.9
        self.assertIsNone(select_detected_hotspot([lookout], []))


class AutoFishingIntegrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def method(self, class_name, name):
        cls = next(node for node in self.tree.body
                   if isinstance(node, ast.ClassDef) and node.name == class_name)
        node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
        return ast.get_source_segment(self.source, node)

    def test_auto_fish_only_uses_live_eligible_main_deck_lookouts(self):
        method = self.method("Longline", "_best_detected_hotspot")
        self.assertIn("s.mode == Sailor.ABOARD", method)
        self.assertIn("s.level == Level.MAIN", method)
        self.assertIn("s.ladder is None", method)
        self.assertIn("s.health > 0.0", method)
        self.assertIn("select_detected_hotspot(lookouts, w.hotspots)", method)

    def test_routes_to_belief_based_position_and_remembers_target(self):
        route = self.method("Longline", "_route_to_hotspot")
        self.assertIn("estimated_hotspot_destination(spot.pos, w.position_error)", route)
        self.assertIn("self.auto_hotspot_target = spot", route)
        self.assertIn("self.auto_hotspot_destination = V(target)", route)
        self.assertIn("w.set_destination(target)", route)

    def test_no_detection_falls_back_to_existing_fishing_grounds(self):
        route = self.method("Longline", "_route_to_best_hotspot_or_grounds")
        self.assertIn("if spot is None", route)
        self.assertIn("self.g.world.set_destination(self.g.world.fishing_ground())", route)

    def test_travel_abandons_expired_or_weak_school_and_uses_fallback_or_replacement(self):
        live = self.method("Longline", "_auto_hotspot_is_live")
        auto = self.method("Longline", "_auto")
        self.assertIn("any(spot is target for spot in self.g.world.hotspots)", live)
        self.assertIn("AUTO_HUNT_MIN_STRENGTH", live)
        self.assertIn("not self._auto_hotspot_is_live()", auto)
        self.assertIn("replacement = self._best_detected_hotspot()", auto)
        self.assertIn("w.set_destination(w.fishing_ground())", auto)

    def test_hotspot_arrival_uses_stored_plot_and_starts_setting_near_target(self):
        auto = self.method("Longline", "_auto")
        self.assertIn("target = self.auto_hotspot_destination", auto)
        self.assertIn("w.ship_pos.distance_to(target) <= max(w.arrive * 1.5, 650.0)", auto)
        self.assertIn("self._begin_set()", auto)

    def test_hunting_state_is_cleared_when_auto_is_disabled_or_set_begins(self):
        init = self.method("Longline", "__init__")
        toggle = self.method("Longline", "toggle_auto")
        begin = self.method("Longline", "_begin_set")
        for method in (init, toggle, begin):
            self.assertIn("auto_hotspot_target", method)
            self.assertIn("auto_hotspot_destination", method)


class SpeechBubbleRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        crew = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Crew")
        method = next(node for node in crew.body
                      if isinstance(node, ast.FunctionDef) and node.name == "_should_show_speech_bubble")
        method = copy.deepcopy(method)
        method.decorator_list = []
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        namespace = {"re": re}
        exec(compile(module, "crew_bubble_filter.py", "exec"), namespace)
        cls_filter = namespace["_should_show_speech_bubble"]
        cls.should_show = staticmethod(cls_filter)
        cls.say_source = next(ast.get_source_segment(source, node)
                              for node in crew.body
                              if isinstance(node, ast.FunctionDef) and node.name == "say")

    def test_actual_speech_and_direct_warnings_keep_bubbles(self):
        spoken = (
            "Takeda: Lighthouse bears 273 degrees; range about 2.8 nautical miles.",
            "Captain: Setting the line. Hands to the stern.",
            "The line's come up short! Bring her closer!",
            "A yellowfin on the line! Mind the brake.",
            "The yellowfin is alongside. Gaff!",
            "Captain: The lookout has found birds. Let's work that water.",
            "Captain: The sky's clearing.",
            "Dockmaster: Heard a good catch came in from Tenyo Maru last night.",
        )
        for line in spoken:
            with self.subTest(line=line):
                self.assertTrue(self.should_show(line))

    def test_action_context_and_system_notices_stay_in_log(self):
        log_only = (
            "A sea comes green over the bow!",
            "A yellowfin comes over the rail!",
            "Haul complete: 3 fish landed. Get them stowed.",
            "Line depth setting: x1.20 (medium). Applies to hooks set from now on.",
            "Captain: Heading for the fishing grounds.",
            "Captain: Auto-fishing takes priority. Manual waypoint route cancelled.",
            "Navigator: No named landmark is visible. Wait for clearer water before taking a bearing.",
            "Engine room: Main pump is low (23%). Send the engineer below.",
            "Wheelhouse access is controlled: helm watch or assigned radio operator only.",
            "Sato reports for headcount.",
            "Thunder rolls across the water.",
            "Dockmaster: Shore leave is available only while alongside.",
        )
        for line in log_only:
            with self.subTest(line=line):
                self.assertFalse(self.should_show(line))

    def test_every_message_is_logged_before_bubble_filtering(self):
        self.assertLess(self.say_source.index("recorder(text)"), self.say_source.index("_should_show_speech_bubble(text)"))
        self.assertLess(self.say_source.index("self.log.append(text)"), self.say_source.index("_should_show_speech_bubble(text)"))
        self.assertIn("if not self._should_show_speech_bubble(text):", self.say_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
