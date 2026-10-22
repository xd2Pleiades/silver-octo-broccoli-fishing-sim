"""Headless regression tests for autonomous AI-vessel MAYDAY response (M9)."""
from __future__ import annotations

import math
import unittest
from pathlib import Path

from fishing_sim.systems.ai_rescue import (
    AIDistressResponseManager,
    AI_RESCUE_DISPATCH_DELAY_S,
    AI_RESCUE_STORM_DISPATCH_DELAY_S,
    AI_RESCUE_RETRY_INTERVAL_S,
    AI_RESCUE_ON_SCENE_RADIUS_NM,
)
from fishing_sim.world.traffic import Activity, Archetype, TrafficWorld

ROOT = Path(__file__).resolve().parents[2]
GAME_SOURCE = (ROOT / "fishing_sim" / "core" / "game.py").read_text(encoding="utf-8")

_RESPONSE_ARCHETYPES = {
    Archetype.COAST_GUARD,
    Archetype.INDEPENDENT_LONGLINE,
    Archetype.INDEPENDENT_GILLNET,
    Archetype.CORPORATE_CATCHER,
    Archetype.CORPORATE_LONGLINER,
}


def setup_incident(*, started=0.0, status="none", now=100.0):
    traffic = TrafficWorld(world_seed=1962, active_cap=30, phase="A")
    traffic.advance(now, focus_nm=(0.0, 0.0), force=True)
    target = next(s for s in traffic.ships.values()
                  if s.archetype == Archetype.INDEPENDENT_LONGLINE)
    responder = next(s for s in traffic.ships.values()
                     if s.archetype == Archetype.COAST_GUARD and s.id != target.id)
    target.position_nm = (100.0, 100.0)
    target.position_override_nm = target.position_nm
    target.distress_position_nm = target.position_nm
    target.activity_override = Activity.DISTRESSED
    target.activity = Activity.DISTRESSED
    target.mayday_sent = True
    target.mayday_resolved = status not in ("none", "awaiting_dispatch")
    target.distress_started_s = float(started)
    target.distress_kind = "engine_failure"
    target.distress_decision = "ignore" if status == "ignored" else None
    target.distress_assistance_status = status
    traffic.index.upsert(target.id, target.position_nm)
    # Force the test to use exactly one responder. In production, ETA and role
    # priority select one suitable scheduled vessel from the real phase fleet.
    for ship in traffic.ships.values():
        if ship.id != target.id and ship.archetype in _RESPONSE_ARCHETYPES:
            ship.speed_kn = 0.0
    responder.speed_kn = 8.0
    responder.position_nm = (98.0, 100.0)
    responder.position_override_nm = None
    responder.activity_override = None
    responder.heading_rad = 0.0
    responder.mayday_sent = False
    responder.activity = Activity.TRANSIT
    traffic.index.upsert(responder.id, responder.position_nm)
    return traffic, target, responder


class AIDistressResponseTests(unittest.TestCase):
    def test_uses_existing_scheduled_ship_and_does_not_spawn_duplicate_hull(self):
        traffic, target, responder = setup_incident()
        count_before = len(traffic.ships)
        manager = AIDistressResponseManager()
        events = manager.update(100.0, traffic, sea_state=0.0)
        self.assertEqual([event["type"] for event in events], ["dispatched"])
        self.assertEqual(len(traffic.ships), count_before)
        self.assertEqual(manager.mission["responder_vessel_id"], responder.id)
        self.assertEqual(responder.runtime_kind, "scheduled")
        self.assertEqual(target.distress_assistance_status, "en_route")
        self.assertTrue(target.mayday_resolved)
        self.assertTrue(manager.has_active_mission)

    def test_normal_dispatch_has_grace_period_and_storm_dispatch_is_faster(self):
        traffic, target, _responder = setup_incident(started=100.0)
        manager = AIDistressResponseManager()
        self.assertEqual(manager.update(100.0, traffic, sea_state=0.0), [])
        self.assertEqual(manager.update(100.0 + AI_RESCUE_DISPATCH_DELAY_S - 1.0,
                                        traffic, sea_state=0.0), [])
        normal = manager.update(100.0 + AI_RESCUE_DISPATCH_DELAY_S + AI_RESCUE_RETRY_INTERVAL_S,
                                traffic, sea_state=0.0)
        self.assertEqual([event["type"] for event in normal], ["dispatched"])

        storm_traffic, _storm_target, _storm_responder = setup_incident(started=100.0)
        storm_manager = AIDistressResponseManager()
        self.assertEqual(storm_manager.update(100.0, storm_traffic, sea_state=0.9), [])
        storm = storm_manager.update(100.0 + AI_RESCUE_STORM_DISPATCH_DELAY_S,
                                     storm_traffic, sea_state=0.0,
                                     sea_state_at=lambda _target: 0.9)
        self.assertEqual([event["type"] for event in storm], ["dispatched"])
        self.assertLess(AI_RESCUE_STORM_DISPATCH_DELAY_S, AI_RESCUE_DISPATCH_DELAY_S)

    def test_ignored_distress_can_receive_another_vessel_response_immediately(self):
        traffic, target, _responder = setup_incident(started=100.0, status="ignored")
        manager = AIDistressResponseManager()
        events = manager.update(100.0, traffic, sea_state=0.0)
        self.assertEqual([event["type"] for event in events], ["dispatched"])
        self.assertEqual(target.distress_assistance_status, "en_route")

    def test_route_uses_finite_turn_and_completes_assistance_at_working_range(self):
        traffic, target, responder = setup_incident()
        responder.position_nm = (100.0, 98.0)
        responder.heading_rad = 0.0
        traffic.index.upsert(responder.id, responder.position_nm)
        start = tuple(responder.position_nm)
        manager = AIDistressResponseManager()
        manager.update(100.0, traffic, sea_state=0.0)
        self.assertEqual(tuple(responder.position_nm), start, "dispatch must not teleport the responder")
        manager.update(101.0, traffic, sea_state=0.0)
        self.assertAlmostEqual(responder.heading_rad, -0.34, places=5,
                               msg="the responder must turn at a finite rate toward its desired track")
        events = manager.update(106.0, traffic, sea_state=0.0)
        self.assertEqual([event["type"] for event in events], ["on_scene"])
        self.assertLessEqual(math.dist(responder.position_nm, target.position_nm), AI_RESCUE_ON_SCENE_RADIUS_NM)
        self.assertEqual(responder.activity_override, Activity.ANCHORED)
        done = manager.update(112.0, traffic, sea_state=0.0)
        self.assertEqual([event["type"] for event in done], ["completed"])
        self.assertEqual(manager.mission["state"], "returning")
        self.assertEqual(target.distress_assistance_status, "completed")
        self.assertEqual(target.activity_override, Activity.ANCHORED)
        self.assertTrue(target.distress_outcome)
        manager.update(124.0, traffic, sea_state=0.0)
        self.assertEqual(manager.mission["state"], "returning")
        self.assertIsNotNone(responder.position_override_nm)
        self.assertNotEqual(tuple(responder.position_nm), tuple(responder.position_at(124.0)[0]),
                            "return-to-patrol must steer before rejoining the schedule")

    def test_waiting_dispatch_retries_and_player_committed_targets_are_excluded(self):
        traffic, target, responder = setup_incident()
        responder.speed_kn = 0.0
        manager = AIDistressResponseManager()
        self.assertEqual(manager.update(100.0, traffic, sea_state=0.0), [])
        self.assertEqual(target.distress_assistance_status, "awaiting_dispatch")
        self.assertEqual(manager.update(104.0, traffic, sea_state=0.0), [])
        responder.speed_kn = 8.0
        self.assertEqual(manager.update(108.0, traffic, sea_state=0.0,
                                        player_rescue_target_id=target.id), [])
        self.assertEqual(target.distress_assistance_status, "awaiting_dispatch")
        self.assertEqual([event["type"] for event in manager.update(112.0, traffic, sea_state=0.0)],
                         ["dispatched"])

    def test_active_mission_and_traffic_overrides_round_trip(self):
        traffic, target, responder = setup_incident()
        manager = AIDistressResponseManager()
        manager.update(100.0, traffic, sea_state=0.0)
        manager.update(106.0, traffic, sea_state=0.0)
        mission_snapshot = manager.snapshot()
        traffic_snapshot = traffic.snapshot_contacts()

        restored_world = TrafficWorld(world_seed=1962, active_cap=30, phase="A")
        restored_world.advance(106.0, focus_nm=(0.0, 0.0), force=True)
        restored_world.restore_contacts(traffic_snapshot)
        restored_world.advance(106.0, focus_nm=(0.0, 0.0), force=True)
        restored_manager = AIDistressResponseManager.from_snapshot(mission_snapshot)
        restored_target = restored_world.by_id(target.id)
        restored_responder = restored_world.by_id(responder.id)
        self.assertEqual(restored_manager.mission["state"], "on_scene")
        self.assertEqual(restored_target.distress_assistance_status, "on_scene")
        self.assertEqual(restored_responder.position_nm, responder.position_nm)
        self.assertEqual(restored_responder.heading_rad, responder.heading_rad)
        self.assertEqual(restored_manager.update(112.0, restored_world, sea_state=0.0)[0]["type"], "completed")

    def test_snapshot_rejects_invalid_state_and_non_finite_clocks(self):
        manager = AIDistressResponseManager()
        with self.assertRaises(ValueError):
            manager.restore({"schema_version": 999, "mission": None})
        payload = manager.snapshot()
        payload["last_scan_s"] = float("nan")
        with self.assertRaises(ValueError):
            AIDistressResponseManager.validate_snapshot(payload)
        traffic, _target, _responder = setup_incident()
        manager.update(100.0, traffic, sea_state=0.0)
        payload = manager.snapshot()
        payload["mission"]["target_vessel_id"] = payload["mission"]["responder_vessel_id"]
        with self.assertRaises(ValueError):
            AIDistressResponseManager.validate_snapshot(payload)

    def test_game_loop_persists_mission_and_guards_player_and_phase_conflicts(self):
        self.assertIn("self.ai_rescue_manager.update(", GAME_SOURCE)
        self.assertIn('"ai_rescue_mission": self.ai_rescue_manager.snapshot()', GAME_SOURCE)
        self.assertIn("AIDistressResponseManager.from_snapshot", GAME_SOURCE)
        self.assertIn("AIDistressResponseManager.validate_snapshot", GAME_SOURCE)
        self.assertIn("self.ai_rescue_manager.is_responding_to(ship.id)", GAME_SOURCE)
        phase_method = GAME_SOURCE[GAME_SOURCE.index("def _set_campaign_phase(self, phase):"):]
        phase_method = phase_method[:phase_method.index("def _traffic_visual_range_nm(self):")]
        self.assertIn("self.ai_rescue_manager.has_active_mission", phase_method)


if __name__ == "__main__":
    unittest.main()
