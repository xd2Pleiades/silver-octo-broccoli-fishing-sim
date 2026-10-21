"""Phase 6 acceptance checks: powered hauler, stern roller, line wear and injury risk."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def method_block(class_name, method_name):
    cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in cls.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name)
    return ast.get_source_segment(SOURCE, node)


class GearHandlingMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        if str(ROOT.parent) not in sys.path:
            sys.path.insert(0, str(ROOT.parent))
        from fishing_sim.systems.gear_handling import (
            ROLLER_WORKING, ROLLER_BYPASSED, ROLLER_JAMMED,
            calculate_hauler_slip, line_wear_per_second, roller_snag_rate,
        )
        cls.WORKING, cls.BYPASSED, cls.JAMMED = ROLLER_WORKING, ROLLER_BYPASSED, ROLLER_JAMMED
        cls.slip = staticmethod(calculate_hauler_slip)
        cls.wear = staticmethod(line_wear_per_second)
        cls.snag_rate = staticmethod(roller_snag_rate)

    def test_line_wear_increases_from_working_to_bypassed_to_jammed(self):
        working = self.wear(1.0, self.WORKING)
        bypassed = self.wear(1.0, self.BYPASSED)
        jammed = self.wear(1.0, self.JAMMED)
        self.assertLess(working, bypassed)
        self.assertLess(bypassed, jammed)

    def test_bypassing_and_wear_increase_snag_risk(self):
        good = self.snag_rate(0.8, self.WORKING, 100)
        worn = self.snag_rate(0.8, self.WORKING, 25)
        bypassed = self.snag_rate(0.8, self.BYPASSED, 100)
        self.assertLess(good, worn)
        self.assertLess(worn, bypassed)

    def test_friction_drum_slips_more_with_load_and_weak_engine(self):
        easy = self.slip(0.45, 1.0, 2, 100)
        loaded = self.slip(1.45, 1.0, 2, 100)
        weak = self.slip(1.0, 0.35, 1, 100)
        self.assertEqual(easy, 0.0)
        self.assertGreater(loaded, easy)
        self.assertGreater(weak, easy)

    def test_more_crew_and_healthy_drum_increase_pull_capacity(self):
        understaffed = self.slip(1.0, 0.9, 0, 35)
        staffed = self.slip(1.0, 0.9, 2, 100)
        self.assertLess(staffed, understaffed)


class Phase6IntegrationTests(unittest.TestCase):
    def test_roller_state_can_be_engaged_bypassed_and_cleared_by_a_deckhand(self):
        init = method_block("Longline", "__init__")
        operate = method_block("Longline", "operate_roller")
        self.assertIn("self.roller_bypassed = False", init)
        self.assertIn("self.roller_jammed = False", init)
        self.assertIn("self.roller_condition = 100.0", init)
        self.assertIn("s.pos.distance_to(target) <= 245.0", operate)
        self.assertIn("self.roller_bypassed = not self.roller_bypassed", operate)
        self.assertIn("self.roller_jammed = False", operate)

    def test_setting_and_hauling_both_apply_stern_gear_checks(self):
        update = method_block("Longline", "update")
        setting = method_block("Longline", "_tick_setting")
        hauling = method_block("Longline", "_tick_hauling")
        self.assertIn("self._update_roller_and_line(dt)", update)
        self.assertIn("self.roller_jammed or self.roller_snag_timer > 0.0", setting)
        self.assertIn("if self.roller_jammed:", hauling)
        self.assertIn("if self.roller_snag_timer > 0.0:", hauling)

    def test_hauler_slip_is_load_and_engine_dependent_and_reduces_pull_speed(self):
        hauling = method_block("Longline", "_tick_hauling")
        self.assertIn("calculate_hauler_slip(load, g.engine_power, working_hands, self.hauler_drum_condition)", hauling)
        self.assertIn("power = base_power * (1.0 - 0.72 * self.hauler_slip)", hauling)
        self.assertIn("self.hauler_drum_condition", hauling)
        self.assertIn("if not g.engine_running() or not g.engine_ok:", hauling)

    def test_chafe_can_snag_wear_and_part_the_line_and_y_harness_reduces_injury_risk(self):
        update = method_block("Longline", "_update_roller_and_line")
        part = method_block("Longline", "_part_line_from_chafe")
        self.assertIn("line_wear_per_second(load, state)", update)
        self.assertIn("roller_snag_rate(load, state, self.roller_condition)", update)
        self.assertIn("self.line_condition < 18.0 and load > 1.12", update)
        self.assertIn("if not g.harness:", part)
        self.assertIn("whipped by a parted longline", part)

    def test_roller_and_drum_status_are_visible_and_controls_documented(self):
        draw = method_block("Ship", "draw")
        status = method_block("Longline", "status_text")
        handle = method_block("Game", "handle")
        self.assertIn("line.roller_jammed", draw)
        self.assertIn("line.roller_bypassed", draw)
        self.assertIn("hauler_slip", draw)
        self.assertIn("Roller %s %d%%", status)
        self.assertIn("pygame.K_m", handle)
        self.assertIn("M engage/bypass stern roller", SOURCE)

    def test_rewritten_sailor_sprite_renderer_is_preserved(self):
        # Phase 6 should not regress the more detailed V13 sailor painter.
        draw = method_block("Sailor", "draw")
        for expected in ("jacket_light", "self._head", "self.carry", "self._health_bar"):
            self.assertIn(expected, draw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
