"""Source-contract checks for the v12v11 deck work, controls, engine and muster additions.

These are deliberately static checks: they verify source wiring, not the full Pygame loop.
"""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME_PATH = ROOT / "core" / "game.py"
ZIP_ROOT = ROOT.parent


def node_for(source, class_name, method_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return ast.get_source_segment(source, next(
        n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name
    ))


class V11DeckWorkMusterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GAME_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.src)

    def test_controls_overlay_toggle_is_separate_from_gameplay_inputs(self):
        handle = node_for(self.src, "Game", "handle")
        draw_hud = node_for(self.src, "Game", "draw_hud")
        self.assertIn("pygame.K_F5", handle)
        self.assertIn("self.show_controls = not self.show_controls", handle)
        self.assertIn("if self.show_controls and strip_w >= 420", draw_hud)
        self.assertIn("F5: SHOW CONTROLS", draw_hud)

    def test_minigame_status_bars_are_higher_and_fit_short_windows(self):
        bar_y = node_for(self.src, "Game", "_bar_y")
        self.assertIn("int(H * 0.52)", bar_y)
        self.assertIn("clamp(target, 72, max(72, H - 96))", bar_y)

    def test_deck_fish_have_life_exposure_and_bounded_handling_damage(self):
        catch_init = node_for(self.src, "Catch", "__init__")
        catch_tick = node_for(self.src, "Catch", "tick")
        fish_update = node_for(self.src, "Game", "_update_deck_fish")
        self.assertIn("self.alive = True", catch_init)
        self.assertIn("self.deck_exposure += dt", catch_tick)
        self.assertIn("def damage_from_handling(self, amount)", self.src)
        self.assertIn("self.patches.append(Patch(item.pos, \"slime\", radius=55.0))", fish_update)
        self.assertIn("The live %s thrashes on deck!", fish_update)
        self.assertIn("Rough handling bruises the %s", fish_update)
        self.assertIn("slips on fish slime", fish_update)

    def test_catch_processing_outranks_optional_work_and_stowing_is_reported(self):
        think = node_for(self.src, "Sailor", "_think")
        dress = node_for(self.src, "Sailor", "_task_dress")
        self.assertIn("Fresh catch outranks optional cleaning", think)
        self.assertLess(think.index("self.g.table.has_work(self)"), think.index("self._enter(self.duty if self.duty"))
        self.assertIn("Catch stowed:", dress)
        self.assertIn("f.alive = False", dress)

    def test_unattended_engine_keeps_running_but_accumulates_load_dependent_risk(self):
        engine = node_for(self.src, "Game", "update_engine_room")
        self.assertIn("running = self.fuel > 0 and self.engine_ok and demand", engine)
        self.assertIn("self.engine_unattended_time += dt", engine)
        self.assertIn("wear_multiplier = 1.35", engine)
        self.assertIn("wear_multiplier = 0.68", engine)
        self.assertIn("fault_rate = (0.00004 + 0.00008 * load) * exposure", engine)
        self.assertIn("Unattended engine fault:", engine)

    def test_headcount_orders_a_pathfinding_muster_without_duplicate_calls(self):
        handle = node_for(self.src, "Game", "handle")
        start = node_for(self.src, "Game", "start_muster")
        update = node_for(self.src, "Game", "_update_muster")
        task = node_for(self.src, "Sailor", "_do_task")
        hud = node_for(self.src, "Game", "_information_sheet_rows")
        self.assertIn("self.start_muster()", handle)
        self.assertIn("if self.muster_active", start)
        self.assertIn("Captain: HEADCOUNT!", start)
        self.assertIn("sailor._enter(\"muster\")", start)
        self.assertIn("unable to reach muster point", update)
        self.assertIn('elif t == "muster":', task)
        self.assertIn("self.g._muster_arrive(self)", task)
        self.assertIn('MUSTER %d/%d reported', hud)

    def test_launcher_and_required_zip_marker_are_preserved(self):
        launcher = ZIP_ROOT / "run_fishing_sim.py"
        marker = ZIP_ROOT / "DO_NOT_REMOVE_THIS_IN_THE_ZIP.md"
        self.assertTrue(launcher.exists())
        self.assertEqual(marker.read_text(encoding="utf-8").strip(), "DO NOT REMOVE THIS IN THE ZIP")


if __name__ == "__main__":
    unittest.main(verbosity=2)
