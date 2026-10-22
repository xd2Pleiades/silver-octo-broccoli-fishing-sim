"""Dependency-free tests for v13.2.02 selectable radio conversations."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from fishing_sim.world.traffic import TrafficWorld, Archetype
from fishing_sim.systems.ship_radio import ShipRadioService

ROOT = Path(__file__).resolve().parents[1]


class AlwaysAnswerRng:
    """Deterministic zero-noise RNG to test dialogue policy, not probability tuning."""
    def __init__(self, *_args, **_kwargs):
        pass
    def random(self):
        return 0.0
    def uniform(self, a, b):
        return (float(a) + float(b)) / 2.0
    def randrange(self, n):
        return 0


class RadioTopicTests(unittest.TestCase):
    def setUp(self):
        self.world = TrafficWorld(1962)
        self.ship = next(s for s in self.world.ships.values()
                         if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        self.ship.position_nm = (0.5, 0.0)
        self.ship.radio_range_nm = 27.0
        self.service = ShipRadioService(1962)
        self.kwargs = dict(player_name="Kōei Maru", player_port="Hakodate",
                           player_position_nm=(0.0, 0.0), sim_time_s=30.0,
                           sea_state=0.1, weather_phrase="fair conditions", radio_clarity=1.0)

    def _ask(self, topic):
        with patch("fishing_sim.systems.ship_radio.random.Random", AlwaysAnswerRng):
            return self.service.interact(self.ship, topic, **self.kwargs)

    def test_supported_topics_produce_staged_multi_turn_exchange(self):
        for topic in ("position", "weather", "activity", "grounds", "crew", "name"):
            with self.subTest(topic=topic):
                exchange = self._ask(topic)
                self.assertTrue(exchange.delivered)
                self.assertEqual(exchange.intent, topic)
                self.assertTrue(exchange.transmit_text)
                self.assertGreaterEqual(len(exchange.turns), 2)
                self.assertTrue(all(len(turn) == 4 for turn in exchange.turns))

    def test_position_question_returns_reported_not_actual_position(self):
        exchange = self._ask("position")
        self.assertTrue(exchange.delivered)
        self.assertIsNotNone(exchange.reported_position_nm)
        self.assertNotEqual(exchange.reported_position_nm, self.ship.position_nm)
        self.assertIn("reported fix", exchange.turns[0][2])

    def test_corporate_vessel_declines_fishing_grounds(self):
        corp = next(s for s in self.world.ships.values()
                    if s.archetype == Archetype.CORPORATE_CATCHER)
        corp.position_nm = (0.5, 0.0)
        with patch("fishing_sim.systems.ship_radio.random.Random", AlwaysAnswerRng):
            exchange = self.service.interact(corp, "grounds", **self.kwargs)
        self.assertTrue(exchange.delivered)
        self.assertIn("company business", exchange.turns[0][2].lower())
        self.assertNotEqual(exchange.intent, "grounds_misdirect")

    def test_out_of_range_topic_does_not_leak_position(self):
        self.ship.position_nm = (35.0, 0.0)
        exchange = self.service.interact(self.ship, "position", **self.kwargs)
        self.assertFalse(exchange.delivered)
        self.assertEqual(exchange.intent, "out_of_range")
        self.assertIsNone(exchange.reported_position_nm)


class RadioUiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game_source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.game_ast = ast.parse(cls.game_source)
        cls.methods = {node.name for node in ast.walk(cls.game_ast)
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def test_radio_ui_draw_open_and_modal_handlers_exist(self):
        self.assertTrue({"open_radio_ui", "draw_radio_ui", "_handle_radio_ui",
                         "_radio_ui_start_topic", "_radio_ui_next"}.issubset(self.methods))
        self.assertIn('"topic:" + topic', self.game_source)
        self.assertIn('next_label = "NEXT LINE  →" if pending else "NEXT SHIP  →"', self.game_source)

    def test_hud_button_and_ctrl_f11_are_bound_to_ui(self):
        self.assertIn("self.radio_hud_rect", self.game_source)
        self.assertIn("self.open_radio_ui()", self.game_source)
        self.assertIn("self.radio_ui_open:\n            return self._handle_radio_ui(ev)", self.game_source)

    def test_f11_fullscreen_binding_is_preserved(self):
        self.assertIn("pygame.display.toggle_fullscreen()", self.game_source)

    def test_package_version_is_updated(self):
        init = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "13.2.05"', init)


if __name__ == "__main__":
    unittest.main()
