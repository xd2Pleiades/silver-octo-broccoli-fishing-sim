"""Dependency-free M11 Phase A content, ambient radio, and balance contracts."""
from __future__ import annotations
import ast
import random
import unittest
from pathlib import Path

from fishing_sim.world.traffic import TrafficWorld, PHASE_A_COUNTS, PHASE_A_FLEET_TOTAL, Archetype
from fishing_sim.systems.ambient_ship_radio import AmbientShipRadioDirector
from fishing_sim.systems.ship_radio import ShipRadioService

ROOT = Path(__file__).resolve().parents[1]


def co_locate_fleet(world):
    """Make deterministic nearby candidates for tests without advancing schedules."""
    for i, ship in enumerate(world.ships.values()):
        ship.position_nm = ((i % 10) * 0.6 + 0.1, (i // 10) * 0.6 + 0.1)
        world.index.upsert(ship.id, ship.position_nm)


class PhaseAContentTests(unittest.TestCase):
    def test_phase_a_pool_expands_without_enabling_source_plan_full_fleet(self):
        self.assertEqual(PHASE_A_FLEET_TOTAL, 40)
        self.assertEqual(PHASE_A_FLEET_TOTAL, sum(PHASE_A_COUNTS.values()))
        self.assertLess(PHASE_A_FLEET_TOTAL, 100)
        world = TrafficWorld(1962)
        self.assertEqual(len(world.ships), 40)
        self.assertEqual({s.archetype for s in world.ships.values()}, set(Archetype) - {Archetype.PLAYER})
        self.assertEqual(len({s.id for s in world.ships.values()}), 40)
        self.assertEqual(len({s.callsign for s in world.ships.values()}), 40)

    def test_fleet_and_names_remain_deterministic_between_processes(self):
        a = TrafficWorld(1962)
        b = TrafficWorld(1962)
        self.assertEqual([(s.id, s.name, s.personality, s.schedule) for s in a.ships.values()],
                         [(s.id, s.name, s.personality, s.schedule) for s in b.ships.values()])
        self.assertNotEqual([s.id for s in a.ships.values()],
                            [s.id for s in TrafficWorld(1963).ships.values()])

    def test_ambient_is_not_emitted_at_start_or_more_than_once_per_slot(self):
        world = TrafficWorld(1962)
        co_locate_fleet(world)
        director = AmbientShipRadioDirector(1962)
        kwargs = dict(radio_staffed=True, channel_busy=False, radio_clarity=1.0,
                      sea_state=0.35, hour=23.0, month=6, day=10)
        self.assertIsNone(director.update(world, 0.0, (0.0, 0.0), **kwargs))
        first = director.update(world, 42.0, (0.0, 0.0), **kwargs)
        again_same_slot = director.update(world, 42.5, (0.0, 0.0), **kwargs)
        self.assertIsNone(again_same_slot)
        # Some seeded slots may be quiet; eventually an exchange must occur.
        emitted = first
        for slot in range(2, 80):
            if emitted is not None:
                break
            emitted = director.update(world, slot * 42.0, (0.0, 0.0), **kwargs)
        self.assertIsNotNone(emitted)
        self.assertGreater(director.emitted_count, 0)

    def test_busy_or_unstaffed_radio_does_not_backlog_ambient_lines(self):
        world = TrafficWorld(1962)
        co_locate_fleet(world)
        director = AmbientShipRadioDirector(1962)
        args = (world,)
        common = dict(player_position_nm=(0.0, 0.0), radio_clarity=1.0, sea_state=0.2, hour=2.0)
        self.assertIsNone(director.update(*args, 0.0, radio_staffed=True, channel_busy=False, **common))
        self.assertIsNone(director.update(*args, 42.0, radio_staffed=True, channel_busy=True, **common))
        skipped = director.skipped_busy_count
        result = director.update(*args, 42.1, radio_staffed=True, channel_busy=False, **common)
        self.assertIsNone(result)
        self.assertEqual(director.skipped_busy_count, skipped)
        self.assertIsNone(director.update(*args, 84.0, radio_staffed=False, channel_busy=False, **common))

    def test_ambient_plots_are_noisy_and_not_exact_truth(self):
        world = TrafficWorld(1962)
        co_locate_fleet(world)
        director = AmbientShipRadioDirector(1962)
        common = dict(player_position_nm=(0.0, 0.0), radio_staffed=True, channel_busy=False,
                      radio_clarity=1.0, sea_state=0.35, hour=23.0, month=6, day=10)
        director.update(world, 0.0, **common)
        event = None
        for slot in range(1, 100):
            event = director.update(world, slot * 42.0, **common)
            if event:
                break
        self.assertIsNotNone(event)
        for vessel_id in event.contact_ids:
            ship = world.by_id(vessel_id)
            self.assertTrue(ship.known_to_player)
            self.assertIsNotNone(ship.last_reported_position_nm)
            self.assertNotEqual(ship.last_reported_position_nm, ship.position_nm)
            self.assertGreaterEqual(ship.report_age_s(event.turns and slot * 42.0), 0.0)
        text = " ".join(turn[2] for turn in event.turns).lower()
        self.assertNotIn("exact coordinates", text)
        self.assertNotIn("guaranteed catch", text)

    def test_ambient_snapshot_round_trip_preserves_cadence_and_cooldowns(self):
        world = TrafficWorld(1962)
        co_locate_fleet(world)
        director = AmbientShipRadioDirector(1962)
        common = dict(player_position_nm=(0.0, 0.0), radio_staffed=True, channel_busy=False,
                      radio_clarity=1.0, sea_state=0.35, hour=23.0, month=6, day=10)
        director.update(world, 0.0, **common)
        for slot in range(1, 60):
            director.update(world, slot * 42.0, **common)
        snapshot = director.snapshot()
        restored = AmbientShipRadioDirector(1962)
        restored.restore(snapshot)
        self.assertEqual(restored.snapshot(), snapshot)
        with self.assertRaises(ValueError):
            AmbientShipRadioDirector(7).restore(snapshot)

    def test_docked_port_gossip_does_not_require_a_nearby_ship(self):
        world = TrafficWorld(1962)
        # Move all contacts out of radio range; harbour station still has its own path.
        for i, ship in enumerate(world.ships.values()):
            ship.position_nm = (200.0 + i, 200.0)
            world.index.upsert(ship.id, ship.position_nm)
        director = AmbientShipRadioDirector(1962)
        common = dict(player_position_nm=(0.0, 0.0), radio_staffed=True, channel_busy=False,
                      radio_clarity=1.0, sea_state=0.2, hour=10.0, month=6, day=10, docked=True)
        director.update(world, 0.0, **common)
        seen = None
        for slot in range(1, 150):
            seen = director.update(world, slot * 42.0, **common)
            if seen is not None:
                break
        self.assertIsNotNone(seen)
        self.assertEqual(seen.kind, "port_gossip")
        self.assertEqual(seen.source_id, "harbour-station")

    def test_m11_ui_hint_does_not_disclose_personality_or_truth(self):
        source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        self.assertIn("Notebook hint: a peer's fishing report is a lead, not a guarantee.", source)
        self.assertIn("Notebook hint: numbered company callsigns", source)
        hint_region = source[source.index("# These hints describe observable conventions only"):
                             source.index("else:\n            self.radio_ui_status = \"%s — %s\"")]
        self.assertNotIn("ship.personality", hint_region)
        self.assertNotIn("ship.trust", hint_region)

    def test_ambient_radio_is_integrated_and_persisted(self):
        source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        self.assertIn("self.ambient_ship_radio.update(", source)
        self.assertIn('"ambient_ship_radio": self.ambient_ship_radio.snapshot()', source)
        self.assertIn('"ship_radio_service": self.ship_radio_service.snapshot()', source)
        self.assertIn("self.ambient_ship_radio.restore(ambient_snapshot)", source)
        self.assertIn("self.ship_radio_service.restore(radio_service_snapshot)", source)
        self.assertIn('startswith("ambient_ship_radio:")', source)
        # Earlier v13.2 saves did not have these optional sections and remain loadable.
        self.assertIn('radio_service_snapshot = snapshot.get("ship_radio_service")', source)

    def test_ship_radio_topic_cooldown_blocks_repeated_topic_but_allows_other_topics(self):
        world = TrafficWorld(1962)
        ship = next(s for s in world.ships.values() if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        ship.position_nm = (2.0, 0.0)
        service = ShipRadioService(1962)
        common = dict(player_name="Koei Maru", player_port="Hakodate",
                      player_position_nm=(0.0, 0.0), sea_state=0.0,
                      radio_clarity=1.0, month=6, day=10)
        first = service.interact(ship, "weather", sim_time_s=100.0, **common)
        self.assertNotEqual(first.intent, "cooldown")
        attempts_after_first = ship.contact_attempts
        repeated = service.interact(ship, "weather", sim_time_s=101.0, **common)
        self.assertEqual(repeated.intent, "cooldown")
        self.assertEqual(ship.contact_attempts, attempts_after_first,
                         "a throttled request must not consume a deterministic radio attempt")
        other_topic = service.interact(ship, "activity", sim_time_s=101.0, **common)
        self.assertNotEqual(other_topic.intent, "cooldown")
        after_cooldown = service.interact(ship, "weather", sim_time_s=146.0, **common)
        self.assertNotEqual(after_cooldown.intent, "cooldown")

    def test_ship_radio_topic_cooldowns_round_trip(self):
        service = ShipRadioService(1962)
        world = TrafficWorld(1962)
        ship = next(iter(world.ships.values()))
        service._cooldown_reason(ship, "weather", 25.0)
        snapshot = service.snapshot()
        restored = ShipRadioService(1962)
        restored.restore(snapshot)
        self.assertEqual(restored.snapshot(), snapshot)
        with self.assertRaises(ValueError):
            ShipRadioService(42).restore(snapshot)

    def test_radio_clock_modifier_changes_by_time_and_archetype(self):
        world = TrafficWorld(1962)
        peer = next(s for s in world.ships.values() if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        coast = next(s for s in world.ships.values() if s.archetype == Archetype.COAST_GUARD)
        self.assertGreater(ShipRadioService._clock_modifier(peer, 575.0, 6, 10),
                           ShipRadioService._clock_modifier(peer, 250.0, 6, 10))
        self.assertGreater(ShipRadioService._clock_modifier(coast, 250.0, 6, 10),
                           ShipRadioService._clock_modifier(coast, 575.0, 6, 10))
        corporate = next(s for s in world.ships.values() if s.archetype == Archetype.CORPORATE_CATCHER)
        self.assertGreater(ShipRadioService._clock_modifier(corporate, 250.0, 6, 10),
                           ShipRadioService._clock_modifier(corporate, 250.0, 4, 10))
        self.assertAlmostEqual(ShipRadioService._clock_modifier(corporate, 250.0, 6, 10) -
                               ShipRadioService._clock_modifier(corporate, 250.0, 4, 10), 0.025)

    def test_treaty_edge_only_selects_near_45n_soviet_pair(self):
        world = TrafficWorld(1962)
        ships = list(world.ships.values())
        soviet = next(s for s in ships if s.archetype == Archetype.SOVIET_TRAWLER)
        peer = next(s for s in ships if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        director = AmbientShipRadioDirector(1962)
        soviet.position_nm = (0.0, (45.0 - 41.8) * 60.0)
        peer.position_nm = (4.0, (45.0 - 41.8) * 60.0 + 2.0)
        kind, pair = director._pick_pair([soviet, peer], random.Random(1))
        self.assertEqual(kind, "treaty_edge")
        self.assertEqual({s.id for s in pair}, {soviet.id, peer.id})
        peer.position_nm = (4.0, 0.0)
        kind, _pair = director._pick_pair([soviet, peer], random.Random(1))
        self.assertNotEqual(kind, "treaty_edge")


if __name__ == "__main__":
    unittest.main(verbosity=2)
