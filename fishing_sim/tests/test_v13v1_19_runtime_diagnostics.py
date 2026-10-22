"""Regression tests for the manual-setting crash and runtime diagnostics."""
import ast
import logging
import math
from pathlib import Path
import sys
import tempfile
import types
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from fishing_sim import diagnostics


class LonglinePhysicsRegressionTests(unittest.TestCase):
    def test_verlet_history_loop_binds_particle_index_before_using_it(self):
        source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        longline = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Longline")
        physics = next(n for n in longline.body if isinstance(n, ast.FunctionDef) and n.name == "_physics")
        # The first particle-history loop must bind i, which is used for the
        # anchored head/winch check. This previously raised UnboundLocalError as
        # soon as a line point existed during SETTING or HAULING.
        loop = next(n for n in physics.body if isinstance(n, ast.For))
        self.assertIsInstance(loop.target, ast.Tuple)
        self.assertEqual([x.id for x in loop.target.elts if isinstance(x, ast.Name)], ["i", "p"])
        self.assertIn("if i == 0 and hauling:", ast.get_source_segment(source, physics))

    def test_manual_set_is_instrumented_before_it_mutates_line_state(self):
        source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        longline = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Longline")
        method = next(n for n in longline.body if isinstance(n, ast.FunctionDef) and n.name == "begin_manual_set")
        body = ast.get_source_segment(source, method)
        self.assertIn('log_event("manual_line_set_requested"', body)
        self.assertIn('log_event("manual_line_set_started"', body)

    def test_first_setting_physics_tick_runs_with_a_single_float(self):
        source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        longline = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Longline")
        method = next(n for n in longline.body if isinstance(n, ast.FunctionDef) and n.name == "_physics")
        method = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))

        class Vec:
            def __init__(self, x=0.0, y=None):
                if isinstance(x, Vec):
                    self.x, self.y = x.x, x.y
                elif y is None and isinstance(x, (tuple, list)):
                    self.x, self.y = float(x[0]), float(x[1])
                else:
                    self.x, self.y = float(x), float(0.0 if y is None else y)

            def __add__(self, other): return Vec(self.x + other.x, self.y + other.y)
            def __sub__(self, other): return Vec(self.x - other.x, self.y - other.y)
            def __mul__(self, k): return Vec(self.x * k, self.y * k)
            __rmul__ = __mul__
            def __truediv__(self, k): return Vec(self.x / k, self.y / k)
            def __iadd__(self, other): self.x += other.x; self.y += other.y; return self
            def __isub__(self, other): self.x -= other.x; self.y -= other.y; return self
            def length_squared(self): return self.x * self.x + self.y * self.y
            def distance_to(self, other): return math.hypot(self.x - other.x, self.y - other.y)
            def length(self): return math.hypot(self.x, self.y)
            def lerp(self, other, t): return Vec(self.x + (other.x-self.x)*t, self.y+(other.y-self.y)*t)
            def scale_to_length(self, target):
                length = self.length()
                if length: self.x *= target / length; self.y *= target / length

        # Compile the real method body without importing Pygame, which is absent
        # in the headless builder. The old unindexed loop raised UnboundLocalError.
        namespace = {"V": Vec, "HARBOUR": Vec(0, 0), "DEPTH_M": 10.0,
                     "math": __import__("math"), "random": __import__("random"),
                     "clamp": lambda x, lo, hi: max(lo, min(hi, x)), "SPECIES": {}}
        exec(compile(method, "longline_physics_test.py", "exec"), namespace)
        physics = namespace["_physics"]
        world = types.SimpleNamespace(
            scale=3.0, current=lambda depth: Vec(0, 0), bottom_m=lambda distance: 1000.0,
            time=0.0,
        )
        point = {"pos": Vec(1000, 1000), "z": 0.0, "vel": Vec(), "vz": 0.0,
                 "link": 260.0, "float": True, "fish": False, "name": "", "bottom": False}
        line = types.SimpleNamespace(g=types.SimpleNamespace(world=world), pts=[point],
                                     phase=1, HAULING=3)
        physics(line, 1.0 / 60.0)
        self.assertEqual(point["z"], 0.0)
        self.assertFalse(point["bottom"])



class RuntimeDiagnosticsTests(unittest.TestCase):
    def test_crash_report_contains_traceback_and_game_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous_dir = diagnostics.ERROR_DIR
            logger = diagnostics.get_logger()
            was_disabled, was_propagating = logger.disabled, logger.propagate
            logger.disabled, logger.propagate = True, False
            diagnostics.ERROR_DIR = Path(tmp)
            try:
                try:
                    raise RuntimeError("simulated line setting crash")
                except RuntimeError:
                    report = diagnostics.write_exception_report(
                        "test crash",
                        exc_info=sys.exc_info(),
                        context={
                            "last_input_event": "KEYDOWN:p",
                            "longline": {"phase": 1, "stage": "set", "point_count": 1},
                        },
                    )
                self.assertIsNotNone(report)
                text = Path(report).read_text(encoding="utf-8")
                self.assertIn("simulated line setting crash", text)
                self.assertIn("KEYDOWN:p", text)
                self.assertIn('"point_count": 1', text)
                self.assertIn("Traceback", text)
            finally:
                diagnostics.ERROR_DIR = previous_dir
                logger.disabled, logger.propagate = was_disabled, was_propagating

    def test_error_cache_folder_has_documentation_and_is_created_by_launcher(self):
        readme = PROJECT / "docs" / "cache_errors__README.md"
        self.assertTrue(readme.exists())
        self.assertIn("crash_*.txt", readme.read_text(encoding="utf-8"))
        launcher = (PROJECT / "run_fishing_sim.py").read_text(encoding="utf-8")
        self.assertIn("install_diagnostics()", launcher)
        self.assertLess(launcher.index("install_diagnostics()"), launcher.index("from fishing_sim.core.game import Game"))

    def test_uncaught_exception_hook_writes_a_crash_file_and_runtime_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = (
                "from fishing_sim.diagnostics import install_diagnostics; "
                "install_diagnostics(r'" + tmp.replace("\\", "\\\\") + "'); "
                "raise RuntimeError('diagnostic-hook-test')"
            )
            result = subprocess.run(
                [sys.executable, "-c", code], cwd=PROJECT,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            cache = Path(tmp)
            reports = list(cache.glob("crash_*.txt"))
            self.assertEqual(len(reports), 1)
            report = reports[0].read_text(encoding="utf-8")
            self.assertIn("diagnostic-hook-test", report)
            self.assertIn("Traceback", report)
            self.assertTrue((cache / "runtime.log").exists())
            self.assertTrue((cache / "errors.log").exists())
            self.assertTrue((cache / "faults.log").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
