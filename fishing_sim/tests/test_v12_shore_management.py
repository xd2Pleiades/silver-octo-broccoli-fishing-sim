"""Focused v12v12 tests for recovery thresholds and dockside shore management."""
from pathlib import Path
from types import SimpleNamespace
import ast
import unittest

from fishing_sim.systems.shore_leave import (
    READY_FATIGUE,
    READY_HEALTH,
    READY_MORALE,
    returning_shore_crew,
    shore_recovery_ready,
    shore_status_label,
)

ROOT = Path(__file__).resolve().parents[1]
GAME_PATH = ROOT / "core" / "game.py"
ZIP_ROOT = ROOT.parent


def method_source(source, class_name, method_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return ast.get_source_segment(source, method)


class ShoreRecoveryPolicyTests(unittest.TestCase):
    def sailor(self, **changes):
        state = dict(health=1.0, fatigue=0.0, morale=1.0, mode=4, keep_ashore=False)
        state.update(changes)
        return SimpleNamespace(**state)

    def test_ready_thresholds_are_bounded_and_independent(self):
        self.assertTrue(shore_recovery_ready(self.sailor()))
        self.assertFalse(shore_recovery_ready(self.sailor(health=READY_HEALTH - 0.001)))
        self.assertFalse(shore_recovery_ready(self.sailor(fatigue=READY_FATIGUE + 0.001)))
        self.assertFalse(shore_recovery_ready(self.sailor(morale=READY_MORALE - 0.001)))

    def test_return_list_excludes_keep_ashore_staff(self):
        ready = self.sailor()
        retained = self.sailor(keep_ashore=True)
        dead_mode = self.sailor(mode=3)
        self.assertEqual(returning_shore_crew([ready, retained, dead_mode], 4), [ready])

    def test_status_labels_distinguish_recovering_ready_and_retained(self):
        self.assertEqual(shore_status_label(self.sailor(health=0.6), 4), "RECOVERING")
        self.assertEqual(shore_status_label(self.sailor(), 4), "READY")
        self.assertEqual(shore_status_label(self.sailor(keep_ashore=True), 4), "KEEP ASHORE")
        self.assertEqual(shore_status_label(self.sailor(mode=0), 4), "NOT ASHORE")


class ShoreManagementWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GAME_PATH.read_text(encoding="utf-8")

    def test_wait_uses_single_recovery_policy_and_excludes_kept_ashore(self):
        update = method_source(self.src, "Game", "update")
        self.assertIn("returning = self._shore_returning_crew()", update)
        self.assertIn("all(shore_recovery_ready(s) for s in returning)", update)
        action = method_source(self.src, "Game", "_sheet_action")
        self.assertIn("eligible = self._shore_returning_crew()", action)

    def test_wait_cancel_restores_original_timescale_once(self):
        stop = method_source(self.src, "Game", "_stop_shore_wait")
        self.assertIn("if not self.shore_wait_active", stop)
        self.assertIn("self.shore_wait_previous_timescale", stop)
        self.assertIn("self.shore_wait_active = False", stop)

    def test_departure_stops_wait_and_does_not_return_kept_ashore(self):
        recall = method_source(self.src, "Game", "_recall_shore_leave")
        self.assertIn("if departure:", recall)
        self.assertIn("self._stop_shore_wait", recall)
        self.assertIn("if sailor.mode == Sailor.SHORE and not sailor.keep_ashore", recall)
        self.assertIn("if departure:\n            self.dock_shore_leave_started = False", recall)

    def test_individually_returning_radio_operator_regains_watch(self):
        bring = method_source(self.src, "Game", "_bring_sailor_aboard")
        self.assertIn("was_radio_operator = sailor is self.shore_radio_operator", bring)
        self.assertIn("self.assign_radio_operator(sailor, announce=False)", bring)
        self.assertIn("if self.radio_operator is None", bring)

    def test_hire_ashore_rolls_back_if_transfer_fails_and_new_crew_are_spaced(self):
        hire = method_source(self.src, "Game", "hire_from_dock")
        self.assertIn("if stay_ashore and not self._send_sailor_ashore", hire)
        self.assertIn("self.cash += candidate[\"fee\"]", hire)
        self.assertIn("embark_offsets", hire)

    def test_small_sheet_moves_wait_button_below_tabs_and_fits_row_text(self):
        draw = method_source(self.src, "Game", "draw_crew_sheet")
        self.assertIn("narrow_sheet = width < 900", draw)
        self.assertIn("wait_y = ty + (38 if narrow_sheet else 0)", draw)
        self.assertIn("self._fit(metrics, metrics_max)", draw)

    def test_required_launcher_and_preservation_marker_remain(self):
        self.assertTrue((ZIP_ROOT / "run_fishing_sim.py").exists())
        self.assertEqual((ZIP_ROOT / "docs" / "DO_NOT_REMOVE_THIS_IN_THE_ZIP.md").read_text(encoding="utf-8").strip(),
                         "DO NOT REMOVE THIS IN THE ZIP")


if __name__ == "__main__":
    unittest.main(verbosity=2)
