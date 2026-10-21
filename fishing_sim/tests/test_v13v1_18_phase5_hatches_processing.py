"""Source contracts for Phase 5 processing, dogged hatches and bilge control."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME_PATH = ROOT / "core" / "game.py"


def source_method(source, class_name, method_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name)
    return ast.get_source_segment(source, node)


class Phase5HatchAndBilgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GAME_PATH.read_text(encoding="utf-8")

    def test_engine_and_both_hold_hatches_start_dogged(self):
        ship_init = source_method(self.src, "Ship", "__init__")
        self.assertIn('{"engine": False, "hold_1": False, "hold_2": False}', ship_init)
        self.assertIn('"engine": False', ship_init)
        self.assertIn('"hold_1": False', ship_init)
        self.assertIn('"hold_2": False', ship_init)

    def test_manual_hatch_control_is_advertised_and_has_timed_action(self):
        self.assertIn("U open/dog nearby hatch", self.src)
        action = source_method(self.src, "Game", "_start_hatch_action")
        self.assertIn('"kind": "hatch"', action)
        self.assertIn('"duration": 1.35', action)
        self.assertIn("toggle_nearby_hatch", self.src)

    def test_closed_hatches_block_manual_climb_until_opened(self):
        climb = source_method(self.src, "Game", "press_climb")
        self.assertIn("if hatch_key and not self.ship.hatch_is_open(hatch_key):", climb)
        self.assertIn("Press U to open it before climbing", climb)
        self.assertIn("self.ship.hatch_states[key] = opening", source_method(self.src, "Game", "_finish_deck_action"))

    def test_auto_level_transit_opens_then_dogs_hatch(self):
        sailor_go_to = source_method(self.src, "Sailor", "_go_to")
        ladder_step = source_method(self.src, "Sailor", "_ladder_step")
        self.assertIn("_start_hatch_action(self, hatch_key, automatic=True)", sailor_go_to)
        self.assertIn("_close_hatch_after_crossing", ladder_step)

    def test_hatch_open_state_controls_engine_and_hold_water_ingress(self):
        update = source_method(self.src, "Ship", "update_water")
        self.assertIn('if self.hatch_is_open("engine"):', update)
        self.assertIn('sum(1 for key in ("hold_1", "hold_2") if self.hatch_is_open(key))', update)
        self.assertIn("self.engine_flood = clamp", update)
        self.assertIn("self.hold_flood = clamp", update)

    def test_engine_and_hold_bilges_require_hands_in_the_respective_room(self):
        bucket = source_method(self.src, "Game", "_update_bucket_chain")
        self.assertIn("engine_hands = [s for s in self.sailors", bucket)
        self.assertIn("hold_hands = [s for s in self.sailors", bucket)
        self.assertIn("self.ship.engine_flood - 0.035", bucket)
        self.assertIn("self.ship.hold_flood - 0.03", bucket)
        self.assertIn("if self.ship.engine_flood > 0.65", bucket)

    def test_three_distinct_processing_stages_precede_carry_to_hold(self):
        task = source_method(self.src, "Sailor", "_task_dress")
        self.assertIn("if not f.bled:", task)
        self.assertIn("elif not f.gutted:", task)
        self.assertIn("elif not f.sliced:", task)
        self.assertIn('self.carry = [f]', task)
        self.assertIn('m["hatch_%d" % (self.hatch_idx + 1)]', task)

    def test_stow_through_a_closed_hatch_is_rejected(self):
        stow = source_method(self.src, "Game", "stow")
        self.assertIn('if hatch_idx is not None and not self.ship.hatch_is_open("hold_%d" % (int(hatch_idx) + 1)):', stow)
        self.assertIn("return False", stow)
        self.assertIn("self.hold.append(c)", stow)

    def test_hose_wash_cleans_table_blood_and_nearby_patches(self):
        finish = source_method(self.src, "Game", "_finish_deck_action")
        start = source_method(self.src, "Game", "start_hose_wash")
        self.assertIn('elif kind == "hose":', finish)
        self.assertIn("self.table_blood = max(0.0, self.table_blood - 0.85)", finish)
        self.assertIn("patch.cleaning", finish)
        self.assertIn('"kind": "hose"', start)

    def test_ice_trim_reduces_melt_and_hold_water_worsens_cooling(self):
        finish = source_method(self.src, "Game", "_finish_deck_action")
        ice = source_method(self.src, "Game", "_ice")
        self.assertIn("self.ice_trimmed_time = 180.0", finish)
        self.assertIn("melt_factor = 0.68 if self.ice_trimmed_time > 0.0 else 1.0", ice)
        self.assertIn("melt_factor *= 1.0 + 0.9 * hold_water", ice)
        self.assertIn("target_temp = 0.5 + 7.0 * hold_water", ice)

    def test_phase5_controls_and_roofmap_are_included(self):
        self.assertIn("F sluice table with hose", self.src)
        self.assertIn("V trim ice (below deck)", self.src)
        self.assertIn('"hose_station"', self.src)
        self.assertIn('"hold_1"', self.src)
        self.assertIn('"hold_2"', self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
