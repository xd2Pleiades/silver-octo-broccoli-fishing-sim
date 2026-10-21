import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"
DOCS = ROOT.parent / "docs"


class V13130TowPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GAME.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.top_methods = {
            node.name: node for node in ast.walk(cls.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def method_source(self, name):
        node = self.top_methods[name]
        lines = self.source.splitlines()
        return "\n".join(lines[node.lineno - 1:node.end_lineno])

    def test_version_is_bumped(self):
        version = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "13.1.30"', version)

    def test_persistent_tow_state_is_initialized(self):
        self.assertIn("self.tow_request_active = False", self.source)
        self.assertIn("self.adrift_elapsed = 0.0", self.source)

    def test_retry_is_not_gated_on_empty_fuel(self):
        update_radio = self.method_source("_update_radio")
        self.assertIn("if self.tow_request_active and not tow_in_flight", update_radio)
        self.assertNotIn("and self.fuel <= 0", update_radio)
        self.assertIn('accepted = self.radio_call("tow")', update_radio)

    def test_automatic_tow_has_low_fuel_and_adrift_triggers(self):
        self.assertIn("TOW_TRIGGER_FUEL_FRACTION = 0.05", self.source)
        self.assertIn("TOW_TRIGGER_DRIFT_SECONDS = DAY_LEN * TOW_TRIGGER_DRIFT_HOURS / 24.0", self.source)
        logistics = self.method_source("_logistics")
        self.assertIn("fuel_trigger = self.fuel <= FUEL_CAP * TOW_TRIGGER_FUEL_FRACTION", logistics)
        self.assertIn("drift_trigger = self.adrift_elapsed >= TOW_TRIGGER_DRIFT_SECONDS", logistics)

    def test_adrift_timer_excludes_deliberate_anchoring(self):
        logistics = self.method_source("_logistics")
        self.assertIn("not self.anchor_deployed", logistics)
        self.assertIn("and (not self._engine_on or self.fuel <= 0.0)", logistics)

    def test_long_range_tow_reception_is_faded_but_not_zero(self):
        call = self.method_source("_start_radio_call")
        self.assertIn("long_range_fade", call)
        self.assertIn("0.004, 0.075", call)
        self.assertNotIn(") if in_range else 0.0", call)

    def test_tow_status_persists_on_hud(self):
        draw_hud = self.method_source("draw_hud")
        self.assertIn("TOW REQUEST ACTIVE — retransmitting until answered", draw_hud)
        self.assertIn("TOW ACCEPTED — tug towing us back to berth", draw_hud)

    def test_arrival_clears_persistent_request(self):
        transit = self.method_source("_update_tow_transit")
        self.assertIn("self.tow_request_active = False", transit)
        self.assertIn("self.adrift_elapsed = 0.0", transit)
        self.assertIn("w.ship_pos += direction * step", transit)

    def test_design_and_diagnosis_docs_are_present(self):
        design = (DOCS / "SINKING_AND_ABANDONMENT.md").read_text(encoding="utf-8")
        diagnosis = (DOCS / "TOW_TRIGGER_DIAGNOSIS.md").read_text(encoding="utf-8")
        self.assertIn("Status:** Proposed design", design)
        self.assertIn("Confirmed cause 1", diagnosis)
        self.assertIn("DAY_LEN = 600", diagnosis)


if __name__ == "__main__":
    unittest.main()
