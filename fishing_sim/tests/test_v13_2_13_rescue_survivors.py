"""Headless tests for persistent casualty transfer and liferaft survival (M9)."""
from __future__ import annotations

import copy
import math
import unittest
from pathlib import Path

from fishing_sim.systems.distress_dispatcher import DistressDispatcher
from fishing_sim.systems.rescue_survivors import (
    RescueSurvivorRegistry, CASUALTY_SURVIVAL_S, LIFERAFT_PICKUP_RADIUS_NM,
    LIFERAFT_SURVIVAL_S, LIFERAFT_BEACON_INTERVAL_S, LIFERAFT_BEACON_RANGE_NM,
)
from fishing_sim.world.traffic import Archetype, TrafficWorld

ROOT = Path(__file__).resolve().parents[2]
GAME_SOURCE = (ROOT / "fishing_sim" / "core" / "game.py").read_text(encoding="utf-8")


def incident(kind: str, now: float = 100.0):
    traffic = TrafficWorld(world_seed=1962, active_cap=30, phase="A")
    traffic.advance(now, focus_nm=(0.0, 0.0), force=True)
    ship = next(s for s in traffic.ships.values()
                if s.archetype == Archetype.INDEPENDENT_LONGLINE)
    ship.position_nm = (2.0, -3.0)
    traffic.index.upsert(ship.id, ship.position_nm)
    event = DistressDispatcher(world_seed=1962).trigger(ship, now, kind=kind, radio_staffed=True)
    assert event is not None
    return traffic, ship


class RescueSurvivorRegistryTests(unittest.TestCase):
    def test_taking_water_deploys_stable_two_person_raft_without_spawning_ship(self):
        traffic, ship = incident("taking_water")
        ship_count = len(traffic.ships)
        registry = RescueSurvivorRegistry()
        events = registry.update(traffic, 100.0, sea_state=0.25)
        self.assertEqual([event["type"] for event in events], ["liferaft_deployed"])
        incident_state = registry.incidents[ship.id]
        raft = incident_state["liferaft"]
        self.assertEqual(raft["raft_id"], ship.id + ":liferaft:01")
        self.assertEqual(raft["occupants"], 2)
        self.assertEqual(len(traffic.ships), ship_count, "a raft is not a second fleet vessel")
        self.assertTrue(registry.has_active_survivors)
        self.assertEqual(registry.update(traffic, 104.0, sea_state=0.25), [])

    def test_liferaft_beacon_requires_staffed_wireless_and_radio_range(self):
        traffic, ship = incident("taking_water")
        registry = RescueSurvivorRegistry()
        first = registry.update(traffic, 100.0, player_position_nm=(0.0, 0.0), radio_staffed=False)
        self.assertEqual([event["type"] for event in first], ["liferaft_deployed"])
        self.assertEqual(registry.reported_liferaft_targets(100.0), [])

        out_of_range = registry.update(traffic, 101.0,
                                       player_position_nm=(LIFERAFT_BEACON_RANGE_NM + 10.0, 0.0),
                                       radio_staffed=True)
        self.assertEqual(out_of_range, [])
        self.assertEqual(registry.reported_liferaft_targets(101.0), [])

        heard = registry.update(traffic, 102.0, player_position_nm=(0.0, 0.0), radio_staffed=True)
        beacon_events = [event for event in heard if event["type"] == "liferaft_beacon_received"]
        self.assertEqual(len(beacon_events), 1)
        raft = registry.incidents[ship.id]["liferaft"]
        self.assertTrue(raft["beacon_heard_by_player"])
        report = registry.reported_liferaft_targets(102.0)[0]
        self.assertNotEqual(report["position_nm"], tuple(raft["position_nm"]),
                            "the chart report must not expose the exact drifting raft fix")
        self.assertGreaterEqual(report["report_error_nm"], 0.25)
        self.assertLessEqual(report["report_error_nm"], 0.95)

    def test_liferaft_beacon_refreshes_and_stale_plot_does_not_follow_true_drift(self):
        traffic, ship = incident("taking_water")
        registry = RescueSurvivorRegistry()
        first = registry.update(traffic, 100.0, player_position_nm=(0.0, 0.0), radio_staffed=True)
        self.assertIn("liferaft_beacon_received", [event["type"] for event in first])
        first_report = registry.reported_liferaft_targets(100.0)[0]["position_nm"]
        # Out of range: the chart must keep the last transmitted fix rather than track
        # the raft's true drift. It becomes visibly stale after three simulation minutes.
        far_player = (LIFERAFT_BEACON_RANGE_NM + 20.0, 0.0)
        registry.update(traffic, 100.0 + LIFERAFT_BEACON_INTERVAL_S, player_position_nm=far_player, radio_staffed=True)
        stale_at = 100.0 + 2.0 * LIFERAFT_BEACON_INTERVAL_S
        registry.update(traffic, stale_at, player_position_nm=far_player, radio_staffed=True)
        stale_report = registry.reported_liferaft_targets(stale_at)[0]
        self.assertEqual(stale_report["position_nm"], first_report)
        self.assertTrue(stale_report["stale"])

        # Back in range on the next beacon interval, a fresh uncertain plot replaces it.
        refreshed_at = stale_at + 1.0
        refreshed = registry.update(traffic, refreshed_at, player_position_nm=(0.0, 0.0), radio_staffed=True)
        self.assertIn("liferaft_beacon_updated", [event["type"] for event in refreshed])
        new_report = registry.reported_liferaft_targets(refreshed_at)[0]
        self.assertFalse(new_report["stale"])
        self.assertGreaterEqual(new_report["sequence"], 2)

    def test_discovered_beacon_fix_round_trips_through_career_snapshot(self):
        traffic, ship = incident("taking_water")
        registry = RescueSurvivorRegistry()
        registry.update(traffic, 100.0, player_position_nm=(0.0, 0.0), radio_staffed=True)
        restored = RescueSurvivorRegistry.from_snapshot(registry.snapshot())
        self.assertEqual(restored.snapshot(), registry.snapshot())
        raft = restored.incidents[ship.id]["liferaft"]
        self.assertTrue(raft["beacon_heard_by_player"])
        self.assertEqual(len(restored.reported_liferaft_targets(100.0)), 1)

    def test_injury_casualty_transfers_once_and_uses_mission_identity(self):
        traffic, ship = incident("injury")
        registry = RescueSurvivorRegistry()
        registry.update(traffic, 100.0)
        registry.update(traffic, 150.0, sea_state=0.2)
        first = registry.complete_assistance(ship.id, "player-rescue-001", ship.position_nm, 150.0)
        second = registry.complete_assistance(ship.id, "player-rescue-001", ship.position_nm, 151.0)
        self.assertEqual(first["casualties_transferred"], 1)
        self.assertEqual(second["casualties_transferred"], 0)
        self.assertEqual(registry.casualties_transferred, 1)
        self.assertEqual(registry.incidents[ship.id]["casualty"]["status"], "recovered")

    def test_liferaft_pickup_requires_physical_range_and_counts_occupants(self):
        traffic, ship = incident("taking_water")
        registry = RescueSurvivorRegistry()
        registry.update(traffic, 100.0)
        raft = registry.incidents[ship.id]["liferaft"]
        far_position = (raft["position_nm"][0] + LIFERAFT_PICKUP_RADIUS_NM + 1.0,
                        raft["position_nm"][1])
        far_result = registry.complete_assistance(ship.id, "mission-far", far_position, 101.0)
        self.assertEqual(far_result["liferafts_recovered"], 0)
        self.assertEqual(far_result["liferafts_left_adrift"], 1)
        self.assertEqual(raft["status"], "afloat")
        close_result = registry.complete_assistance(ship.id, "mission-close", raft["position_nm"], 102.0)
        self.assertEqual(close_result["liferafts_recovered"], 1)
        self.assertEqual(close_result["liferaft_occupants_recovered"], 2)
        self.assertEqual(registry.liferaft_occupants_recovered, 2)
        self.assertEqual(raft["status"], "recovered")
        self.assertFalse(registry.has_active_survivors)

    def test_liferaft_drifts_and_weather_reduces_survival_time(self):
        normal_traffic, normal_ship = incident("taking_water")
        storm_traffic, storm_ship = incident("taking_water")
        normal = RescueSurvivorRegistry()
        storm = RescueSurvivorRegistry()
        normal.update(normal_traffic, 100.0, sea_state=0.0)
        storm.update(storm_traffic, 100.0, sea_state=0.0)
        normal_start = tuple(normal.incidents[normal_ship.id]["liferaft"]["position_nm"])
        storm_start = tuple(storm.incidents[storm_ship.id]["liferaft"]["position_nm"])
        normal.update(normal_traffic, 150.0, sea_state=0.1)
        storm.update(storm_traffic, 150.0, sea_state=1.5)
        normal_raft = normal.incidents[normal_ship.id]["liferaft"]
        storm_raft = storm.incidents[storm_ship.id]["liferaft"]
        self.assertNotEqual(tuple(normal_raft["position_nm"]), normal_start)
        self.assertNotEqual(tuple(storm_raft["position_nm"]), storm_start)
        self.assertLess(storm_raft["remaining_s"], normal_raft["remaining_s"])

    def test_expired_liferaft_survival_marks_occupants_lost_once(self):
        traffic, ship = incident("taking_water")
        registry = RescueSurvivorRegistry()
        registry.update(traffic, 100.0, sea_state=1.5)
        # Use a deterministic large clock advance to pass the sea-state-adjusted clock.
        events = registry.update(traffic, 100.0 + LIFERAFT_SURVIVAL_S, sea_state=1.5)
        self.assertEqual([event["type"] for event in events], ["liferaft_survivors_lost"])
        self.assertEqual(registry.survivors_lost, 2)
        self.assertEqual(registry.update(traffic, 100.0 + LIFERAFT_SURVIVAL_S + 10.0, sea_state=1.5), [])
        self.assertEqual(registry.survivors_lost, 2)

    def test_expired_medical_casualty_is_not_transferred(self):
        traffic, ship = incident("injury")
        registry = RescueSurvivorRegistry()
        registry.update(traffic, 100.0)
        events = registry.update(traffic, 100.0 + CASUALTY_SURVIVAL_S, sea_state=0.0)
        self.assertEqual([event["type"] for event in events], ["casualty_lost"])
        result = registry.complete_assistance(ship.id, "late-mission", ship.position_nm,
                                              100.0 + CASUALTY_SURVIVAL_S + 1)
        self.assertEqual(result["casualties_transferred"], 0)
        self.assertEqual(registry.casualties_transferred, 0)
        self.assertEqual(registry.survivors_lost, 1)

    def test_snapshot_round_trip_preserves_stable_ids_drift_and_survival(self):
        traffic, ship = incident("taking_water")
        registry = RescueSurvivorRegistry()
        registry.update(traffic, 100.0, sea_state=0.4)
        registry.update(traffic, 120.0, sea_state=0.8)
        restored = RescueSurvivorRegistry.from_snapshot(registry.snapshot())
        self.assertEqual(restored.snapshot(), registry.snapshot())
        raft = restored.incidents[ship.id]["liferaft"]
        self.assertTrue(raft["raft_id"].startswith(ship.id + ":liferaft:"))

    def test_snapshot_rejects_nonfinite_raft_position_and_bad_counters(self):
        traffic, _ship = incident("taking_water")
        registry = RescueSurvivorRegistry()
        registry.update(traffic, 100.0)
        malformed = copy.deepcopy(registry.snapshot())
        vessel_id = next(iter(malformed["incidents"]))
        malformed["incidents"][vessel_id]["liferaft"]["position_nm"][0] = math.nan
        with self.assertRaises(ValueError):
            RescueSurvivorRegistry.validate_snapshot(malformed)
        malformed = registry.snapshot()
        malformed["survivors_lost"] = -1
        with self.assertRaises(ValueError):
            RescueSurvivorRegistry.validate_snapshot(malformed)

    def test_game_loop_and_career_save_use_shared_survivor_ledger(self):
        self.assertIn("self.rescue_survivor_registry = RescueSurvivorRegistry()", GAME_SOURCE)
        self.assertIn('"rescue_survivors": self.rescue_survivor_registry.snapshot()', GAME_SOURCE)
        self.assertIn("RescueSurvivorRegistry.from_snapshot(data.get(\"rescue_survivors\"))", GAME_SOURCE)
        self.assertIn("self.rescue_survivor_registry.update(", GAME_SOURCE)
        self.assertIn("self.rescue_survivor_registry.complete_assistance(", GAME_SOURCE)
        self.assertIn(".rescue_survivor_registry", GAME_SOURCE)
        self.assertIn("has_active_survivors", GAME_SOURCE)
        self.assertIn("def _handle_rescue_survivor_event(self, event):", GAME_SOURCE)
        self.assertIn('"RAFT / %d" % int(raft.get("occupants", 0))', GAME_SOURCE)
        self.assertIn("pygame.draw.ellipse(self.screen, (235, 171, 62)", GAME_SOURCE)
        self.assertIn("player_position_nm=player_nm, radio_staffed=self.radio_station_ok()", GAME_SOURCE)
        self.assertIn('"liferaft_beacon_received", "liferaft_beacon_updated"', GAME_SOURCE)
        self.assertIn("reported_liferaft_targets(now)", GAME_SOURCE)
        self.assertIn("Amber diamond: radio-reported liferaft", GAME_SOURCE)


if __name__ == "__main__":
    unittest.main()
