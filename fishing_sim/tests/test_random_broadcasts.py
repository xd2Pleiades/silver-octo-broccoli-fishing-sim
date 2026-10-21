"""Focused tests for V9 ambient incoming radio broadcasts."""
import random
import unittest
from types import SimpleNamespace

from fishing_sim.systems.radio import RadioSystem


class FakeWorld:
    def __init__(self, distance=500.0, sea_state=0.3, hour=14.0):
        self._distance = distance
        self.sea_state = sea_state
        self._hour = hour

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


class RandomBroadcastTests(unittest.TestCase):
    def setUp(self):
        random.seed(12345)
        self.game = SimpleNamespace(
            world=FakeWorld(), weather=FakeWeather(), market=1.08,
        )
        self.radio = RadioSystem(self.game)

    def test_no_broadcast_before_timer_expires(self):
        self.radio.broadcast_timer = 2.0
        self.assertIsNone(self.radio.poll_random_broadcast(1.0, staffed=True))
        self.assertEqual(self.radio.broadcasts_received, 0)

    def test_broadcast_is_delivered_when_staffed_and_idle(self):
        self.radio.broadcast_timer = 0.01
        message = self.radio.poll_random_broadcast(0.1, staffed=True, busy=False)
        self.assertIsNotNone(message)
        self.assertTrue(message.startswith("Radio:"))
        self.assertGreater(self.radio.broadcasts_received, 0)
        self.assertGreater(self.radio.broadcast_timer, 0.0)

    def test_unstaffed_set_misses_broadcast_without_dispatching_crew(self):
        self.radio.broadcast_timer = 0.01
        self.assertIsNone(self.radio.poll_random_broadcast(0.1, staffed=False))
        self.assertEqual(self.radio.broadcasts_missed, 1)
        self.assertEqual(self.radio.broadcasts_received, 0)

    def test_requested_radio_traffic_has_priority_over_random_traffic(self):
        self.radio.broadcast_timer = 0.01
        self.assertIsNone(self.radio.poll_random_broadcast(0.1, staffed=True, busy=True))
        self.assertEqual(self.radio.broadcasts_received, 0)

    def test_random_traffic_has_variety(self):
        messages = set()
        for _ in range(30):
            self.radio.broadcast_timer = 0.0
            message = self.radio.poll_random_broadcast(0.0, staffed=True, busy=False)
            messages.add(message)
        self.assertGreaterEqual(len(messages), 4)
        self.assertTrue(all(m.startswith("Radio:") for m in messages))

    def test_severe_weather_changes_broadcast_content(self):
        self.game.weather = FakeWeather(storm=0.9, wind=0.95, label="Thunderstorm")
        self.radio.signal_quality = 1.0
        self.radio.broadcast_timer = 0.0
        message = self.radio.poll_random_broadcast(0.0, staffed=True, busy=False)
        self.assertTrue(any(word in message.lower() for word in ("weather warning", "squall", "heavy motion")))

    def test_random_broadcast_does_not_invoke_outgoing_call(self):
        def forbidden_outgoing_call(_kind):
            raise AssertionError("ambient traffic must not start an outgoing radio call")
        self.game.radio_call = forbidden_outgoing_call
        self.radio.broadcast_timer = 0.0
        message = self.radio.poll_random_broadcast(0.0, staffed=True, busy=False)
        self.assertTrue(message.startswith("Radio:"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
