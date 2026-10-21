"""Headless acceptance tests for V13V1-13 one-button manual line setting."""
import ast
import copy
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))


class ManualLineSettingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        longline = next(n for n in cls.tree.body if isinstance(n, ast.ClassDef) and n.name == "Longline")
        method = next(n for n in longline.body if isinstance(n, ast.FunctionDef) and n.name == "begin_manual_set")
        method = copy.deepcopy(method)
        method.decorator_list = []
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        # The method emits diagnostic events in the running game; keep the unit
        # test isolated from file logging while preserving its state-machine focus.
        namespace = {"log_event": lambda *args, **kwargs: None}
        exec(compile(module, "manual_line_setting.py", "exec"), namespace)
        cls.manual_method = namespace["begin_manual_set"]

    @staticmethod
    def line(auto=False, stage="off", phase=0, distance=5000, route=None, dock=None, rescue=None, alarm=None):
        logs, spoken = [], []
        world = types.SimpleNamespace(
            route_waypoints=list(route or []), destination=object(), manual_helm=True,
            dock_state=dock, rescue_to=rescue, dist=lambda: distance,
        )
        crew = types.SimpleNamespace(alarm_target=alarm, say=spoken.append)
        game = types.SimpleNamespace(world=world, crew=crew, record_log_entry=logs.append)
        obj = types.SimpleNamespace(
            g=game, auto=auto, stage=stage, phase=phase, IDLE=0, SETTING=1,
            _begin_set=lambda: None,
        )
        obj.begin_manual_set = types.MethodType(ManualLineSettingTests.manual_method, obj)
        return obj, logs, spoken

    def test_manual_order_starts_one_set_without_enabling_auto(self):
        line, logs, _ = self.line(route=["waypoint-a", "waypoint-b"])
        def begin():
            line.phase, line.stage = line.SETTING, "set"
            line.g.world.destination = "forward-setting-run"
        line._begin_set = begin
        self.assertTrue(line.begin_manual_set())
        self.assertFalse(line.auto)
        self.assertEqual((line.phase, line.stage), (line.SETTING, "set"))
        self.assertEqual(line.g.world.route_waypoints, [])
        self.assertFalse(line.g.world.manual_helm)
        self.assertEqual(line.g.world.destination, "forward-setting-run")
        self.assertTrue(any("Manual line setting started" in item for item in logs))

    def test_manual_set_is_refused_while_auto_fishing_is_enabled(self):
        line, _, spoken = self.line(auto=True)
        called = []
        line._begin_set = lambda: called.append(True)
        self.assertFalse(line.begin_manual_set())
        self.assertTrue(line.auto)
        self.assertEqual(called, [])
        self.assertTrue(any("Stand down auto-fishing" in item for item in spoken))

    def test_manual_set_is_refused_while_a_line_operation_is_active(self):
        line, _, spoken = self.line(stage="soak", phase=2)
        called = []
        line._begin_set = lambda: called.append(True)
        self.assertFalse(line.begin_manual_set())
        self.assertEqual(called, [])
        self.assertTrue(any("line is already out" in item for item in spoken))

    def test_manual_set_is_refused_in_harbour_or_during_docking_or_rescue(self):
        for kwargs in (
            {"distance": 899}, {"dock": "approach"},
            {"rescue": (2.0, 3.0)}, {"alarm": object()},
        ):
            with self.subTest(kwargs=kwargs):
                line, _, spoken = self.line(**kwargs)
                called = []
                line._begin_set = lambda: called.append(True)
                self.assertFalse(line.begin_manual_set())
                self.assertEqual(called, [])
                self.assertTrue(spoken)

    def test_p_key_starts_manual_set_without_toggling_auto(self):
        game_class = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "Game")
        handler = next(n for n in game_class.body if isinstance(n, ast.FunctionDef) and n.name == "handle")
        source = ast.get_source_segment(self.source, handler)
        self.assertIn("elif k == pygame.K_p:", source)
        self.assertIn("self.line.begin_manual_set()", source)
        branch = source[source.find("elif k == pygame.K_p:"):source.find("elif k == pygame.K_j:")]
        self.assertNotIn("toggle_auto", branch)

    def test_controls_advertise_the_one_button_manual_set(self):
        self.assertIn("P manual set (one set)", self.source)

    def test_normal_set_state_machine_moves_the_vessel_and_runs_one_shot_cycle(self):
        longline = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "Longline")
        methods = {n.name: ast.get_source_segment(self.source, n)
                   for n in longline.body if isinstance(n, ast.FunctionDef)}
        begin, auto = methods["_begin_set"], methods["_auto"]
        self.assertIn('self.stage = "set"', begin)
        self.assertIn('w.destination = w.ship_pos + V(1, 0).rotate_rad(w.heading) * 40000', begin)
        self.assertIn('elif self.stage == "set":', auto)
        self.assertIn('elif self.stage == "soak":', auto)
        self.assertIn('elif self.stage == "haul":', auto)
        self.assertIn('else:\n                    self.stage = "off"', auto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
