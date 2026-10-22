"""Headless tests for player-directed Coast Guard routing from reported radio plots."""
from __future__ import annotations

import math
import unittest
from pathlib import Path

from fishing_sim.systems.coast_guard_routing import (
    PlayerCoastGuardRoutingManager,
    COAST_GUARD_ROUTE_ON_SCENE_RADIUS_NM,
)
from fishing_sim.systems.rescue_survivors import RescueSurvivorRegistry
from fishing_sim.world.traffic import Activity, Archetype, TrafficWorld, SIM_NM_PER_KNOT_SECOND

ROOT = Path(__file__).resolve().parents[2]
GAME = (ROOT / "fishing_sim" / "core" / "game.py").read_text(encoding="utf-8")


def route_world():
    traffic = TrafficWorld(world_seed=1962, active_cap=30, phase="A")
    traffic.advance(100.0, focus_nm=(0.0, 0.0), force=True)
    target = next(s for s in traffic.ships.values() if s.archetype == Archetype.INDEPENDENT_LONGLINE)
    patrols = [s for s in traffic.ships.values() if s.archetype == Archetype.COAST_GUARD]
    responder = patrols[0]
    for patrol in patrols:
        patrol.speed_kn = 0.0
        patrol.position_override_nm = None
        patrol.activity_override = None
    responder.speed_kn = 10.0
    responder.position_nm = (49.0, 50.0)
    responder.heading_rad = 0.0
    responder.activity = Activity.TRANSIT
    target.position_nm = (50.0, 50.0)
    target.position_override_nm = target.position_nm
    target.distress_position_nm = target.position_nm
    target.activity_override = Activity.DISTRESSED
    target.activity = Activity.DISTRESSED
    target.mayday_sent = True
    target.mayday_player_heard = True
    target.mayday_resolved = False
    target.distress_started_s = 90.0
    target.distress_kind = "taking_water"
    target.distress_assistance_status = "none"
    target.last_reported_position_nm = (51.0, 50.0)
    target.last_report_time_s = 100.0
    target.known_to_player = True
    traffic.index.upsert(target.id, target.position_nm)
    traffic.index.upsert(responder.id, responder.position_nm)
    return traffic, target, responder


class PlayerCoastGuardRoutingTests(unittest.TestCase):
    def test_dispatch_reuses_existing_patrol_and_uses_reported_fix(self):
        traffic, target, responder = route_world()
        registry = RescueSurvivorRegistry()
        before = len(traffic.ships)
        start = tuple(responder.position_nm)
        manager = PlayerCoastGuardRoutingManager()
        event = manager.dispatch(
            traffic, target_kind="distress", target_id=target.id,
            target_vessel_id=target.id, target_callsign=target.callsign,
            target_position_nm=target.last_reported_position_nm, sim_time_s=100.0)
        self.assertEqual(event["type"], "dispatched")
        self.assertEqual(len(traffic.ships), before)
        self.assertEqual(event["responder_vessel_id"], responder.id)
        self.assertEqual(responder.runtime_kind, "scheduled")
        self.assertEqual(tuple(responder.position_nm), start, "dispatch must not teleport a patrol")
        self.assertEqual(manager.mission["target_position_nm"], [51.0, 50.0])
        self.assertNotEqual(manager.mission["target_position_nm"], list(target.position_nm),
                            "route must preserve the uncertain reported fix, not copy hidden truth")
        self.assertEqual(target.distress_assistance_status, "en_route")
        self.assertTrue(target.mayday_resolved)
        self.assertEqual(manager.dispatch(
            traffic, target_kind="distress", target_id=target.id, target_vessel_id=target.id,
            target_callsign=target.callsign, target_position_nm=target.last_reported_position_nm,
            sim_time_s=101.0)["type"], "unavailable")

    def test_route_steers_with_finite_turn_then_completes_physical_assistance(self):
        traffic, target, responder = route_world()
        registry = RescueSurvivorRegistry()
        manager = PlayerCoastGuardRoutingManager()
        manager.dispatch(traffic, target_kind="distress", target_id=target.id,
                         target_vessel_id=target.id, target_callsign=target.callsign,
                         target_position_nm=target.last_reported_position_nm, sim_time_s=100.0)
        manager.update(101.0, traffic, registry, sea_state=0.0)
        self.assertLess(abs(responder.heading_rad), math.pi / 2)
        self.assertGreater(responder.position_nm[0], 49.0)
        self.assertLess(responder.position_nm[0], 51.0, "route must not teleport to the target")
        self.assertLessEqual(responder.position_nm[0] - 49.0, responder.speed_kn * SIM_NM_PER_KNOT_SECOND + 1e-6,
                             "one-second movement must respect the physical speed limit")
        # Simulate arriving at the reported plot; true contact is then detectable on scene.
        responder.position_nm = (51.0, 50.0)
        responder.position_override_nm = responder.position_nm
        events = manager.update(102.0, traffic, registry, sea_state=0.0)
        self.assertIn("on_scene", [event["type"] for event in events])
        self.assertEqual(manager.mission["state"], "on_scene")
        self.assertLessEqual(math.dist(responder.position_nm, target.position_nm), 1.0)
        # On-scene physical proximity allows a short assistance period to complete.
        events = []
        for now in range(103, 112):
            events.extend(manager.update(float(now), traffic, registry, sea_state=0.0))
            if any(event["type"] == "completed" for event in events):
                break
        self.assertIn("completed", [event["type"] for event in events])
        self.assertEqual(target.distress_assistance_status, "completed")
        self.assertEqual(manager.mission["state"], "returning")

    def test_dispatch_fails_when_no_uncommitted_patrol_is_in_range(self):
        traffic, target, responder = route_world()
        for ship in traffic.ships.values():
            if ship.archetype == Archetype.COAST_GUARD:
                ship.position_nm = (0.0, 0.0)
                ship.speed_kn = 0.0
        target.last_reported_position_nm = (120.0, 120.0)
        manager = PlayerCoastGuardRoutingManager()
        event = manager.dispatch(traffic, target_kind="distress", target_id=target.id,
                                 target_vessel_id=target.id, target_callsign=target.callsign,
                                 target_position_nm=target.last_reported_position_nm, sim_time_s=100.0)
        self.assertEqual(event["type"], "unavailable")
        self.assertIsNone(manager.mission)
        self.assertIsNone(responder.position_override_nm)

    def test_liferaft_route_uses_received_beacon_and_recovers_only_inside_radius(self):
        traffic, target, responder = route_world()
        target.position_nm = (50.0, 50.0)
        target.distress_position_nm = target.position_nm
        target.last_reported_position_nm = (50.0, 50.0)
        responder.position_nm = (50.0, 50.0)
        responder.position_override_nm = None
        responder.activity_override = None
        responder.speed_kn = 10.0
        traffic.index.upsert(responder.id, responder.position_nm)
        registry = RescueSurvivorRegistry()
        first = registry.update(traffic, 100.0, player_position_nm=(50.0, 50.0), radio_staffed=True)
        self.assertIn("liferaft_beacon_received", [event["type"] for event in first])
        report = registry.reported_liferaft_targets(100.0)[0]
        raft = registry.incidents[target.id]["liferaft"]
        # Arrange a physically close arrival without changing the saved/report plot.
        raft["position_nm"] = [50.0, 50.0]
        raft["last_update_s"] = 102.0
        manager = PlayerCoastGuardRoutingManager()
        event = manager.dispatch(traffic, target_kind="liferaft", target_id=report["raft_id"],
                                 target_vessel_id=target.id, target_callsign=target.callsign,
                                 target_position_nm=report["position_nm"], target_reported_at_s=report["reported_at_s"],
                                 target_report_sequence=report["sequence"], sim_time_s=100.0)
        self.assertEqual(event["type"], "dispatched")
        self.assertEqual(manager.mission["target_position_nm"], list(report["position_nm"]))
        manager.update(100.0, traffic, registry, sea_state=0.0)
        events = manager.update(102.0, traffic, registry, sea_state=0.0)
        completed = next(event for event in events if event["type"] == "completed")
        self.assertEqual(completed["survivor_result"]["liferafts_recovered"], 1)
        self.assertEqual(completed["survivor_result"]["liferaft_occupants_recovered"], 2)
        self.assertEqual(raft["status"], "recovered")

    def test_fresh_beacon_replots_a_patrol_already_at_old_raft_fix(self):
        traffic, target, responder = route_world()
        target.position_nm = (20.0, 20.0)
        target.distress_position_nm = target.position_nm
        responder.position_nm = (20.0, 20.0)
        responder.speed_kn = 10.0
        traffic.index.upsert(responder.id, responder.position_nm)
        registry = RescueSurvivorRegistry()
        registry.update(traffic, 100.0, player_position_nm=(20.0, 20.0), radio_staffed=True)
        report1 = registry.reported_liferaft_targets(100.0)[0]
        manager = PlayerCoastGuardRoutingManager()
        manager.dispatch(traffic, target_kind="liferaft", target_id=report1["raft_id"],
                         target_vessel_id=target.id, target_callsign=target.callsign,
                         target_position_nm=report1["position_nm"], target_reported_at_s=report1["reported_at_s"],
                         target_report_sequence=report1["sequence"], sim_time_s=100.0)
        # Keep the patrol physically at the old plot/on scene.
        responder.position_nm = tuple(report1["position_nm"])
        responder.position_override_nm = responder.position_nm
        manager.update(100.0, traffic, registry, sea_state=0.0)
        registry.update(traffic, 190.0, player_position_nm=(20.0, 20.0), radio_staffed=True)
        report2 = registry.reported_liferaft_targets(190.0)[0]
        self.assertGreater(report2["sequence"], report1["sequence"])
        manager.update(190.0, traffic, registry, sea_state=0.0)
        self.assertEqual(manager.mission["target_report_sequence"], report2["sequence"])
        self.assertEqual(manager.mission["target_position_nm"], list(report2["position_nm"]))

    def test_route_snapshot_round_trip_and_validation(self):
        traffic, target, responder = route_world()
        manager = PlayerCoastGuardRoutingManager()
        manager.dispatch(traffic, target_kind="distress", target_id=target.id,
                         target_vessel_id=target.id, target_callsign=target.callsign,
                         target_position_nm=target.last_reported_position_nm, sim_time_s=100.0)
        payload = manager.snapshot()
        restored = PlayerCoastGuardRoutingManager.from_snapshot(payload)
        self.assertEqual(restored.mission, manager.mission)
        payload["mission"]["target_position_nm"] = [float("nan"), 4.0]
        with self.assertRaises(ValueError):
            PlayerCoastGuardRoutingManager.validate_snapshot(payload)

    def test_game_integration_radio_controls_save_load_and_single_response_guard(self):
        for token in (
            "from fishing_sim.systems.coast_guard_routing import PlayerCoastGuardRoutingManager",
            '"coast_guard_routing": self.coast_guard_routing_manager.snapshot()',
            "PlayerCoastGuardRoutingManager.from_snapshot(",
            'data.get("coast_guard_routing")',
            'self._radio_ui_route_coast_guard("distress")',
            'self._radio_ui_route_coast_guard("liferaft")',
            'self.coast_guard_routing_manager.update(',
            '"route:distress"',
            '"route:liferaft"',
        ):
            self.assertIn(token, GAME)
        self.assertIn("no additional launch is being created", GAME)


if __name__ == "__main__":
    unittest.main()
