"""Headless regression tests for M6/M11 trust decay, gossip and weather optimization."""
from __future__ import annotations

import math
import unittest
from pathlib import Path
from unittest.mock import patch

from fishing_sim.systems.relationship_dynamics import (
    RelationshipDynamics, RELATIONSHIP_SCHEMA_VERSION,
    TRUST_DECAY_PER_DAY_INDEPENDENT, TRUST_DECAY_PER_DAY_CORPORATE,
)
from fishing_sim.world.traffic import TrafficWorld, Archetype
from fishing_sim.world.weather_grid import WeatherGrid

ROOT = Path(__file__).resolve().parents[1]


def move_ship(traffic, ship, position):
    ship.position_nm = (float(position[0]), float(position[1]))
    traffic.index.upsert(ship.id, ship.position_nm)


class RelationshipDynamicsTests(unittest.TestCase):
    def setUp(self):
        self.traffic = TrafficWorld(1962)
        # Move everyone away so each test has controlled neighbors in the spatial index.
        for i, ship in enumerate(self.traffic.ships.values()):
            move_ship(self.traffic, ship, (500.0 + i * 100.0, 500.0))
        self.manager = RelationshipDynamics(1962)
        self.manager.seed_baseline(self.traffic, 0.0)

    def test_trust_decays_toward_neutral_at_independent_rate(self):
        ship = next(s for s in self.traffic.ships.values()
                    if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        ship.trust = 0.7
        self.manager.advance(self.traffic, 0.0)  # detect the external change, no elapsed decay
        self.manager.advance(self.traffic, 6000.0)  # ten in-game days
        self.assertAlmostEqual(ship.trust, 0.7 - TRUST_DECAY_PER_DAY_INDEPENDENT * 10)

    def test_corporate_trust_decays_twice_as_fast(self):
        ship = next(s for s in self.traffic.ships.values()
                    if s.archetype == Archetype.CORPORATE_CATCHER)
        ship.trust = 0.7
        self.manager.advance(self.traffic, 0.0)
        self.manager.advance(self.traffic, 6000.0)
        self.assertAlmostEqual(ship.trust, 0.7 - TRUST_DECAY_PER_DAY_CORPORATE * 10)

    def test_negative_trust_moves_toward_neutral_not_more_hostile(self):
        ship = next(s for s in self.traffic.ships.values()
                    if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        ship.trust = -0.5
        self.manager.advance(self.traffic, 0.0)
        self.manager.advance(self.traffic, 6000.0)
        self.assertAlmostEqual(ship.trust, -0.4)

    def test_recent_contact_pauses_decay_for_time_before_contact(self):
        ship = next(s for s in self.traffic.ships.values()
                    if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        ship.trust = 0.5
        self.manager.advance(self.traffic, 0.0)
        ship.last_contact_sim_time = 500.0
        self.manager.advance(self.traffic, 600.0)
        self.assertAlmostEqual(ship.trust, 0.5 - TRUST_DECAY_PER_DAY_INDEPENDENT * (100.0 / 600.0))

    def test_gossip_source_propagates_small_effect_to_nearby_independent_peers(self):
        ships = list(self.traffic.ships.values())
        source = next(s for s in ships if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        target = next(s for s in ships if s.archetype == Archetype.INDEPENDENT_GILLNET)
        source.personality = "gossip"
        move_ship(self.traffic, source, (0.0, 0.0))
        move_ship(self.traffic, target, (5.0, 0.0))
        self.manager.seed_baseline(self.traffic, 0.0)
        source.trust = 0.5
        with patch("fishing_sim.systems.relationship_dynamics.GOSSIP_PROPAGATION_CHANCE", 1.0):
            events = self.manager.advance(self.traffic, 0.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_id"], source.id)
        self.assertEqual(events[0]["target_id"], target.id)
        self.assertAlmostEqual(target.trust, 0.1)

    def test_gossip_is_one_hop_not_a_chain_in_same_update(self):
        source = next(s for s in self.traffic.ships.values()
                      if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        target1 = next(s for s in self.traffic.ships.values()
                       if s.archetype == Archetype.INDEPENDENT_GILLNET)
        target2 = next(s for s in self.traffic.ships.values()
                       if s.archetype == Archetype.INDEPENDENT_LONGLINE and s.id != source.id)
        source.personality = "gossip"
        target1.personality = "gossip"
        move_ship(self.traffic, source, (0, 0))
        move_ship(self.traffic, target1, (4, 0))
        move_ship(self.traffic, target2, (7, 0))
        self.manager.seed_baseline(self.traffic, 0)
        source.trust = 0.5
        with patch("fishing_sim.systems.relationship_dynamics.GOSSIP_PROPAGATION_CHANCE", 1.0):
            events = self.manager.advance(self.traffic, 0.0)
        self.assertLessEqual(len(events), 2)
        self.assertAlmostEqual(target1.trust, 0.1)
        # A follow-up call sees synchronized baselines and must not replay the rumour.
        self.assertEqual(self.manager.advance(self.traffic, 0.0), ())

    def test_corporate_or_official_contacts_do_not_spread_gossip(self):
        source = next(s for s in self.traffic.ships.values()
                      if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        corporate = next(s for s in self.traffic.ships.values()
                         if s.archetype == Archetype.CORPORATE_CATCHER)
        source.personality = "gossip"
        move_ship(self.traffic, source, (0, 0))
        move_ship(self.traffic, corporate, (2, 0))
        self.manager.seed_baseline(self.traffic, 0)
        source.trust = -0.6
        with patch("fishing_sim.systems.relationship_dynamics.GOSSIP_PROPAGATION_CHANCE", 1.0):
            events = self.manager.advance(self.traffic, 0)
        self.assertFalse(any(event["target_id"] == corporate.id for event in events))
        self.assertAlmostEqual(corporate.trust, 0.0)

    def test_rival_flag_updates_after_gossip(self):
        source = next(s for s in self.traffic.ships.values()
                      if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        target = next(s for s in self.traffic.ships.values()
                      if s.archetype == Archetype.INDEPENDENT_GILLNET)
        source.personality = "gossip"
        source.trust = -0.9
        target.trust = -0.19
        move_ship(self.traffic, source, (0, 0))
        move_ship(self.traffic, target, (2, 0))
        self.manager.seed_baseline(self.traffic, 0)
        source.trust = -0.99
        with patch("fishing_sim.systems.relationship_dynamics.GOSSIP_PROPAGATION_CHANCE", 1.0):
            self.manager.advance(self.traffic, 0)
        self.assertTrue(target.is_rival)

    def test_snapshot_roundtrip_does_not_replay_gossip(self):
        source = next(s for s in self.traffic.ships.values()
                      if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        source.personality = "gossip"
        target = next(s for s in self.traffic.ships.values()
                      if s.archetype == Archetype.INDEPENDENT_GILLNET)
        move_ship(self.traffic, source, (0, 0))
        move_ship(self.traffic, target, (2, 0))
        self.manager.seed_baseline(self.traffic, 0)
        source.trust = 0.4
        with patch("fishing_sim.systems.relationship_dynamics.GOSSIP_PROPAGATION_CHANCE", 1.0):
            self.manager.advance(self.traffic, 0)
        snapshot = self.manager.snapshot()
        restored = RelationshipDynamics.from_snapshot(snapshot)
        self.assertEqual(restored.snapshot(), snapshot)
        self.assertEqual(restored.advance(self.traffic, 0), ())

    def test_bad_relationship_snapshot_rejected(self):
        bad = self.manager.snapshot()
        bad["last_seen_trust"]["some-vessel"] = math.inf
        with self.assertRaises(ValueError):
            RelationshipDynamics.from_snapshot(bad)
        bad = self.manager.snapshot()
        bad["schema_version"] = RELATIONSHIP_SCHEMA_VERSION + 1
        with self.assertRaises(ValueError):
            RelationshipDynamics.from_snapshot(bad)

    def test_game_career_save_includes_and_restores_optional_relationship_state(self):
        game_source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        self.assertIn('"relationship_dynamics": self.relationship_dynamics.snapshot()', game_source)
        self.assertIn('relationship_snapshot = data.get("relationship_dynamics")', game_source)
        self.assertIn('relationship_snapshot = snapshot.get("relationship_dynamics")', game_source)
        self.assertIn('relationship baseline disagrees with saved traffic trust', game_source)


class WeatherGridOptimizationTests(unittest.TestCase):
    def test_cached_field_matches_cell_objects_after_local_observation(self):
        grid = WeatherGrid(1962)
        pos = (0.0, 0.0)
        grid.observe_local(pos, cloud=0.91, precipitation=0.72, fog=0.21,
                           wind_speed_kt=22.0, wind_direction_rad=0.8, sea_state=0.78)
        key = grid.cell_for(pos)
        flat = grid._flat_values[grid._flat_index[key]]
        cell = grid.cells[key]
        self.assertEqual(flat, grid._tuple(cell))

    def test_cached_field_remains_exact_after_tick_and_snapshot_restore(self):
        grid = WeatherGrid(1962)
        grid.observe_local((0, 0), cloud=0.7, precipitation=0.4, fog=0.2,
                           wind_speed_kt=17, wind_direction_rad=1.1, sea_state=0.5)
        grid.advance(85.0)
        restored = WeatherGrid.from_snapshot(grid.snapshot())
        self.assertEqual(grid.snapshot(), restored.snapshot())
        for key in grid._keys:
            self.assertEqual(grid._flat_values[grid._flat_index[key]], grid._tuple(grid.cells[key]))
            self.assertEqual(restored._flat_values[restored._flat_index[key]], restored._tuple(restored.cells[key]))
        grid.advance(125.0)
        restored.advance(125.0)
        self.assertEqual(grid.snapshot(), restored.snapshot())

    def test_weather_optimization_preserves_known_snapshot_exactly(self):
        import hashlib
        grid = WeatherGrid(1962)
        grid.advance(50.0)
        digest = hashlib.sha256(grid.dumps().encode("utf-8")).hexdigest()
        self.assertEqual(digest, "4d79b2b7721adfddabd5bfe76fe7950bc2d9f5f112cc67b219ab5e19b1fc400d")

    def test_package_version_updated(self):
        self.assertIn('__version__ = "13.2.13"', (ROOT / "__init__.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
