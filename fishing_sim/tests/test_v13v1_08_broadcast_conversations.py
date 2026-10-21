"""Behavioral and wiring checks for V13V1-08 timed broadcast conversations."""
import ast
from pathlib import Path
import random
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.broadcasts import (
    BroadcastDirector, PRIORITY_LOW, PRIORITY_MEDIUM, PRIORITY_HIGH,
    PRIORITY_CRITICAL,
)
from fishing_sim.systems.radio import RadioSystem


class BroadcastDirectorTests(unittest.TestCase):
    def setUp(self):
        self.director = BroadcastDirector()
        self.delivered = []
        self.ready = {"radio": True, "crew": True, "intercom": True, "harbour": True}

    def can_emit(self, channel, priority):
        return self.ready.get(channel, True)

    def emit(self, conversation, turn):
        self.delivered.append((conversation.source, conversation.priority, turn.speaker, turn.text, turn.channel))

    def test_lines_are_attributed_and_respect_interline_delays(self):
        self.director.enqueue([
            (0, "TENYO MARU", "Kōei Maru, this is Tenyo Maru. Over.", "radio"),
            (2.5, "VESSEL", "Tenyo Maru, Kōei Maru. Roger. Out.", "radio"),
        ], priority=PRIORITY_LOW, source="position_exchange")
        self.director.update(0, self.can_emit, self.emit)
        self.assertEqual(len(self.delivered), 1)
        self.director.update(1.0, self.can_emit, self.emit)
        self.assertEqual(len(self.delivered), 1)
        self.director.update(1.4, self.can_emit, self.emit)
        self.assertEqual(len(self.delivered), 1)
        self.director.update(0.2, self.can_emit, self.emit)
        self.assertEqual(len(self.delivered), 2)
        self.assertEqual(self.delivered[1][2], "VESSEL")

    def test_channel_readiness_prevents_overlapping_transmissions(self):
        self.director.enqueue([
            (0, "Takeda", "Fish alongside. Hold her head to the swell.", "intercom"),
            (3, "Captain Ishida", "Aye. Hold her there.", "intercom"),
        ], priority=PRIORITY_LOW, source="deck_intercom")
        self.ready["intercom"] = False
        self.director.update(0, self.can_emit, self.emit)
        self.assertEqual(self.delivered, [])
        self.ready["intercom"] = True
        self.director.update(0, self.can_emit, self.emit)
        self.assertEqual(len(self.delivered), 1)

    def test_critical_mayday_interrupts_low_priority_conversation(self):
        self.director.enqueue([
            (0, "TENYO MARU", "Position twenty-five by eight. Over.", "radio"),
            (5, "VESSEL", "Roger, Tenyo Maru. Out.", "radio"),
        ], priority=PRIORITY_LOW, source="routine_traffic")
        self.director.update(0, self.can_emit, self.emit)
        interrupted = self.director.enqueue([
            (0, "SHINWA MARU", "Mayday, Mayday, Mayday. We are sinking. Over.", "radio"),
            (4, "COAST STATION", "Shinwa Maru, coast station. We have received your Mayday. Over.", "radio"),
        ], priority=PRIORITY_CRITICAL, source="mayday")
        self.assertTrue(interrupted)
        self.assertEqual(self.director.interrupted_count, 1)
        self.director.update(0, self.can_emit, self.emit)
        self.assertEqual(self.delivered[-1][0], "mayday")
        self.assertEqual(self.delivered[-1][1], PRIORITY_CRITICAL)

    def test_pending_conversations_are_priority_sorted_and_fifo_for_ties(self):
        self.director.enqueue([(0, "LOW", "low", "crew")], priority=PRIORITY_LOW, source="low1")
        self.director.enqueue([(0, "MEDIUM", "medium", "radio")], priority=PRIORITY_MEDIUM, source="medium")
        self.director.enqueue([(0, "LOW", "low two", "crew")], priority=PRIORITY_LOW, source="low2")
        self.director.update(0, self.can_emit, self.emit)
        self.assertEqual(self.delivered[0][0], "medium")
        self.director.update(0, self.can_emit, self.emit)
        self.assertEqual(self.delivered[1][0], "low1")
        self.director.update(0, self.can_emit, self.emit)
        self.assertEqual(self.delivered[2][0], "low2")

    def test_player_call_can_discard_pending_low_priority_ambient_traffic(self):
        self.director.enqueue([(0, "LOW", "low", "crew")], priority=PRIORITY_LOW, source="low")
        self.director.enqueue([(0, "MEDIUM", "medium", "radio")], priority=PRIORITY_MEDIUM, source="medium")
        self.assertEqual(self.director.discard_pending_below(PRIORITY_MEDIUM), 1)
        self.assertEqual([c.source for c in self.director.pending], ["medium"])

    def test_empty_lines_are_ignored_and_do_not_create_a_stuck_conversation(self):
        self.director.enqueue([(0, "", "", "radio")], priority=PRIORITY_HIGH)
        self.assertFalse(self.director.is_busy())


class FakeWorld:
    def __init__(self, distance=500.0, zone=1, hour=14.0, sea_state=0.3):
        self._distance = distance
        self.zone = zone
        self._hour = hour
        self.sea_state = sea_state

    def dist(self):
        return self._distance

    def hour(self):
        return self._hour


class FakeWeather:
    def __init__(self, *, storm=0.0, wind=0.25, fog=0.0, label="Clear"):
        self.storm = storm
        self.wind = wind
        self.fog = fog
        self._label = label

    def wind_kt(self):
        return int(8 + self.wind * 30)

    def wind_from(self):
        return "northwest"

    def visibility_km(self):
        return 8.0 if self.fog < 0.4 else 1.2

    def label(self):
        return self._label


class RadioConversationCatalogueTests(unittest.TestCase):
    def make_radio(self, *, zone=1, weather=None):
        game = SimpleNamespace(
            world=FakeWorld(zone=zone), weather=weather or FakeWeather(), market=1.08,
            broadcast_harbour_gossip_count=0,
        )
        return game, RadioSystem(game)

    def test_random_conversation_is_sparse_and_returns_none_before_due(self):
        _, radio = self.make_radio()
        radio.conversation_timer = 9.0
        self.assertIsNone(radio.poll_random_conversation(8.0, staffed=True, busy=False))
        self.assertGreater(radio.conversation_timer, 0)

    def test_conversation_turns_are_attributed_timed_and_period_appropriate(self):
        random.seed(13)
        _, radio = self.make_radio(zone=0)
        radio.conversation_timer = 0
        result = radio.poll_random_conversation(0, staffed=True, busy=False)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(len(result["lines"]), 1)
        for turn in result["lines"]:
            self.assertEqual(len(turn), 4)
            delay, speaker, text, channel = turn
            self.assertGreaterEqual(delay, 0)
            self.assertTrue(speaker)
            self.assertTrue(text)
            self.assertIn(channel, ("radio", "harbour"))
        all_text = " ".join(turn[2] for turn in result["lines"]).lower()
        if len(result["lines"]) > 1:
            self.assertTrue(any(word in all_text for word in ("over", "out", "roger", "standing by")))
        self.assertNotIn("copy that", all_text)

    def test_unstaffed_radio_misses_routine_traffic_without_dispatching_an_operator(self):
        _, radio = self.make_radio(zone=1)
        radio.conversation_timer = 0
        result = radio.poll_random_conversation(0, staffed=False, busy=False, docked=False)
        self.assertIsNone(result)
        self.assertEqual(radio.broadcasts_missed, 1)

    def test_critical_mayday_uses_a_single_five_percent_session_roll(self):
        _, radio = self.make_radio(zone=1)
        radio.conversation_timer = 0
        with patch("fishing_sim.systems.radio.random.random", return_value=0.01):
            result = radio.poll_random_conversation(0, staffed=True, busy=False)
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "mayday")
        self.assertEqual(result["priority"], PRIORITY_CRITICAL)
        self.assertIn("Mayday, Mayday, Mayday", result["lines"][0][2])
        self.assertTrue(radio.distress_checked)

    def test_distress_roll_does_not_repeat_after_the_session_roll(self):
        _, radio = self.make_radio(zone=1)
        radio.distress_checked = True
        radio.conversation_timer = 0
        with patch("fishing_sim.systems.radio.random.random", return_value=0.99):
            result = radio.poll_random_conversation(0, staffed=True, busy=False)
        self.assertIsNotNone(result)
        self.assertNotEqual(result["source"], "mayday")

    def test_harbour_gossip_is_limited_to_three_exchanges_per_visit(self):
        game, radio = self.make_radio(zone=0)
        game.broadcast_harbour_gossip_count = 3
        radio.conversation_timer = 0
        with patch("fishing_sim.systems.radio.random.random", return_value=0.0):
            result = radio.poll_random_conversation(0, staffed=True, busy=False, docked=True)
        self.assertNotEqual(result["source"] if result else None, "harbour_gossip")


class GameBroadcastIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        game = next(node for node in cls.tree.body if isinstance(node, ast.ClassDef) and node.name == "Game")
        cls.methods = {node.name: node for node in game.body if isinstance(node, ast.FunctionDef)}

    def method(self, name):
        return ast.get_source_segment(self.source, self.methods[name])

    def test_director_is_integrated_into_the_radio_update_loop(self):
        update = self.method("_update_radio")
        self.assertIn("poll_random_conversation", update)
        self.assertIn("broadcast_director.update", update)
        self.assertIn("_present_broadcast_turn", update)

    def test_conversation_is_recorded_only_as_each_turn_is_presented(self):
        present = self.method("_present_broadcast_turn")
        self.assertIn('"Radio: [%s]: %s"', present)
        self.assertIn("self.crew.say", present)
        self.assertIn("self.broadcast_visible_priority = conversation.priority", present)

    def test_higher_priority_event_can_interrupt_lower_priority_ui(self):
        queue = self.method("queue_broadcast_conversation")
        clear = self.method("_clear_lower_priority_broadcast")
        self.assertIn("self.broadcast_director.enqueue", queue)
        self.assertIn("self._clear_lower_priority_broadcast", queue)
        self.assertIn("self.radio_transcript_queue.clear()", clear)

    def test_storm_transition_dispatches_a_high_priority_conversation(self):
        method = self.method("on_weather_transition")
        self.assertIn("queue_broadcast_conversation", method)
        self.assertIn("PRIORITY_HIGH", method)
        self.assertIn("storm disruption has reduced landings", method)

    def test_canned_radio_calls_retain_existing_weather_market_and_tow_effects(self):
        start = self.method("_start_radio_call")
        update = self.method("_update_radio")
        self.assertIn('if kind == "weather"', start)
        self.assertIn('elif kind == "auction"', start)
        self.assertIn("self.tow_arrival_t =", update)
        self.assertIn("self.radio_transcript_queue.extend(turns)", update)


if __name__ == "__main__":
    unittest.main(verbosity=2)
