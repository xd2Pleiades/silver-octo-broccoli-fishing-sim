"""Static regression contracts for the 12v14 MOB state machine and catch report."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "core" / "game.py").read_text(encoding="utf-8")


def method_block(class_name, method_name):
    tree = ast.parse(SOURCE)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    method = next(n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name)
    return ast.get_source_segment(SOURCE, method)


class V14SeaRescueTests(unittest.TestCase):
    def test_sighting_triggers_all_stop_before_recovery_decision(self):
        block = method_block("Game", "begin_mob_rescue")
        self.assertIn("w.brake = True", block)
        self.assertIn("w.throttle = 0.0", block)
        self.assertIn("w.destination = None", block)
        self.assertIn("ALL STOP", block)
        self.assertIn("self._update_station_roles(0.0)", block)

    def test_rough_sea_refuses_launch_and_selects_ship_turn(self):
        block = method_block("Game", "begin_mob_rescue")
        self.assertIn("ROUGH_SEA_NO_BOAT = 0.75", SOURCE)
        self.assertIn("w.sea_state >= self.ROUGH_SEA_NO_BOAT", block)
        self.assertIn("self._switch_rescue_to_ship_turn", block)
        steer = method_block("World", "_rescue_steer")
        self.assertIn('self.g.mob_rescue_mode != "ship_turn"', steer)
        self.assertIn("if self.speed > 28.0", steer)

    def test_calm_far_rescue_assembles_real_crew_and_requires_stop(self):
        block = method_block("Game", "_update_rescue_operation")
        self.assertIn('mode == "boat_assembly"', block)
        self.assertIn('"phase": "launching"', block)
        self.assertIn("w.speed <= 28.0", block)
        self.assertIn('self.mob_rescue_mode = "boat_out"', block)
        self.assertIn("paddle_speed", block)
        self.assertIn('self.mob_rescue_mode = "boat_pickup"', block)
        self.assertIn('self.mob_rescue_mode = "boat_return"', block)

    def test_rescue_fsm_runs_in_the_game_loop_and_boat_is_drawn(self):
        update = method_block("Game", "update")
        draw = method_block("Game", "draw")
        self.assertIn("self._update_rescue_operation(dt)", update)
        self.assertIn("self.draw_rescue_boat()", draw)
        self.assertIn("def draw_rescue_boat(self):", SOURCE)
        self.assertIn('self.mob_rescue_mode.upper()', method_block("Game", "_information_sheet_rows"))

    def test_rescue_cleanup_handles_recovery_and_drowning(self):
        on_back = method_block("Crew", "on_back")
        on_drowned = method_block("Crew", "on_drowned")
        finish = method_block("Game", "finish_mob_rescue")
        self.assertIn("finish_mob_rescue(s, survivor=True)", on_back)
        self.assertIn("finish_mob_rescue(s, survivor=False)", on_drowned)
        self.assertIn("self.world.brake = False", finish)
        self.assertIn('boat["phase"] = "return"', finish)


class V14CatchReportTests(unittest.TestCase):
    def test_report_covers_quality_grade_handling_temperature_and_storage(self):
        report = method_block("Game", "catch_report_lines")
        self.assertIn("average quality", report)
        self.assertIn("fish.grade()", report)
        self.assertIn("fish.core", report)
        self.assertIn("fish.deck_exposure", report)
        self.assertIn("warming", report)
        self.assertIn("bled and dressed", report)

    def test_settlement_reports_before_clearing_hold(self):
        settle = method_block("Game", "settle")
        self.assertIn("self.catch_report_lines(limit=4)", settle)
        self.assertLess(settle.index("self.catch_report_lines(limit=4)"), settle.index("self.hold.clear()"))

    def test_existing_quality_model_and_cold_storage_remain_in_use(self):
        catch = method_block("Catch", "tick")
        self.assertIn("self.quality = max(0.0, self.quality - rate * dt)", catch)
        update = method_block("Game", "update")
        self.assertIn("for c in self.hold:", update)
        self.assertIn("c.tick(dt, self.hold_temp, iced, True)", update)
        self.assertIn("self._ice(dt)", update)


if __name__ == "__main__":
    unittest.main(verbosity=2)
