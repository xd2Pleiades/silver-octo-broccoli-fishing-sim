"""Headless regression tests for physical player-vessel assistance missions."""
from __future__ import annotations

import ast
import copy
import math
import unittest
from pathlib import Path

from fishing_sim.systems.distress_dispatcher import DistressDispatcher
from fishing_sim.systems.rescue_missions import (
    PlayerRescueMissionManager, RESCUE_ON_SCENE_RADIUS_NM, RESCUE_WORK_DURATION_S,
)
from fishing_sim.world.traffic import Activity, Archetype, TrafficWorld

ROOT = Path(__file__).resolve().parents[2]
GAME_SOURCE = (ROOT / "fishing_sim" / "core" / "game.py").read_text(encoding="utf-8")


def setup_distress(kind="engine_failure", now=100.0):
    world = TrafficWorld(world_seed=1962, active_cap=30, phase="A")
    world.advance(now, focus_nm=(0.0, 0.0), force=True)
    ship = next(s for s in world.ships.values() if s.archetype == Archetype.INDEPENDENT_LONGLINE)
    # Make this test fixture local and reindex it; the real dispatcher remains range-agnostic
    # for explicit scenarios in the same way as Game's coarse scheduled event path.
    ship.position_nm = (3.0, -2.0)
    world.index.upsert(ship.id, ship.position_nm)
    dispatcher = DistressDispatcher(world_seed=1962)
    event = dispatcher.trigger(ship, now, radio_staffed=True, kind=kind)
    assert event is not None and event.reported_position_nm is not None
    return world, dispatcher, ship, event


class PlayerRescueMissionTests(unittest.TestCase):
    def test_assist_starts_single_mission_using_the_reported_plot(self):
        world, dispatcher, ship, event = setup_distress()
        self.assertTrue(dispatcher.decide(ship, "assist", 101.0)[0])
        manager = PlayerRescueMissionManager()
        backup = {"destination": [100.0, 200.0], "throttle": 0.1}
        mission = manager.dispatch(ship, 101.0, reported_position_nm=event.reported_position_nm,
                                   navigation_backup=backup, route_target_world=(800.0, -700.0))
        self.assertEqual(mission["state"], "en_route")
        self.assertEqual(mission["reported_position_nm"], list(event.reported_position_nm))
        self.assertEqual(mission["route_target_world"], [800.0, -700.0])
        self.assertTrue(manager.has_active_mission)
        with self.assertRaises(ValueError):
            manager.dispatch(ship, 102.0, reported_position_nm=event.reported_position_nm)

    def test_target_remains_at_distress_scene_instead_of_following_its_schedule(self):
        world, dispatcher, ship, event = setup_distress(now=100.0)
        frozen = tuple(ship.distress_position_nm)
        world.advance(300.0, focus_nm=(0.0, 0.0), force=True)
        self.assertEqual(tuple(ship.position_nm), frozen)
        self.assertEqual(ship.activity, Activity.DISTRESSED)

    def test_player_must_reach_target_before_on_scene_state(self):
        world, dispatcher, ship, event = setup_distress()
        dispatcher.decide(ship, "assist", 101.0)
        manager = PlayerRescueMissionManager()
        manager.dispatch(ship, 101.0, reported_position_nm=event.reported_position_nm,
                         route_target_world=(500.0, 500.0))
        far = (ship.position_nm[0] + RESCUE_ON_SCENE_RADIUS_NM + 3.0, ship.position_nm[1])
        self.assertIsNone(manager.update(110.0, far, world))
        self.assertEqual(manager.mission["state"], "en_route")

    def test_on_scene_and_completion_are_separate_timed_transitions(self):
        world, dispatcher, ship, event = setup_distress()
        dispatcher.decide(ship, "assist", 101.0)
        manager = PlayerRescueMissionManager()
        manager.dispatch(ship, 101.0, reported_position_nm=event.reported_position_nm,
                         route_target_world=(500.0, 500.0))
        player = tuple(ship.position_nm)
        arrived = manager.update(110.0, player, world)
        self.assertEqual(arrived["type"], "on_scene")
        self.assertEqual(manager.mission["state"], "on_scene")
        self.assertIsNone(manager.update(110.0 + RESCUE_WORK_DURATION_S - 0.01, player, world))
        done = manager.update(110.0 + RESCUE_WORK_DURATION_S + 0.1, player, world)
        self.assertEqual(done["type"], "completed")
        self.assertFalse(manager.has_active_mission)
        self.assertEqual(manager.completed_count, 1)
        self.assertEqual(ship.distress_assistance_status, "completed")
        self.assertTrue(ship.distress_outcome)
        self.assertEqual(ship.activity_override, Activity.ANCHORED)
        self.assertEqual(tuple(ship.position_nm), tuple(ship.distress_position_nm))

    def test_assist_trust_is_not_applied_by_manager_or_replayed_by_mission(self):
        world, dispatcher, ship, event = setup_distress()
        before = ship.trust
        self.assertTrue(dispatcher.decide(ship, "assist", 101.0)[0])
        after = ship.trust
        manager = PlayerRescueMissionManager()
        manager.dispatch(ship, 101.0, reported_position_nm=event.reported_position_nm)
        player = tuple(ship.position_nm)
        manager.update(105.0, player, world)
        manager.update(105.0 + RESCUE_WORK_DURATION_S, player, world)
        self.assertAlmostEqual(after, before + 0.4)
        self.assertAlmostEqual(ship.trust, after)

    def test_on_scene_mission_loses_rendezvous_if_player_leaves(self):
        world, dispatcher, ship, event = setup_distress()
        dispatcher.decide(ship, "assist", 101.0)
        manager = PlayerRescueMissionManager()
        manager.dispatch(ship, 101.0, reported_position_nm=event.reported_position_nm)
        self.assertEqual(manager.update(110.0, tuple(ship.position_nm), world)["type"], "on_scene")
        far = (ship.position_nm[0] + RESCUE_ON_SCENE_RADIUS_NM * 2.0, ship.position_nm[1])
        out = manager.update(111.0, far, world)
        self.assertEqual(out["type"], "rendezvous_lost")
        self.assertEqual(manager.mission["state"], "en_route")

    def test_active_mission_snapshot_round_trip_preserves_navigation_and_timer(self):
        world, dispatcher, ship, event = setup_distress()
        dispatcher.decide(ship, "assist", 101.0)
        manager = PlayerRescueMissionManager()
        manager.dispatch(ship, 101.0, reported_position_nm=event.reported_position_nm,
                         navigation_backup={"destination": [12.5, -6.0], "route_waypoints": [[4.0, 5.0]]},
                         route_target_world=[100.0, 200.0])
        manager.update(110.0, tuple(ship.position_nm), world)
        snapshot = manager.snapshot()
        restored = PlayerRescueMissionManager.from_snapshot(snapshot)
        self.assertEqual(restored.mission, manager.mission)
        self.assertEqual(restored.mission["state"], "on_scene")
        self.assertEqual(restored.mission["navigation_backup"]["destination"], [12.5, -6.0])

    def test_invalid_snapshots_are_rejected(self):
        manager = PlayerRescueMissionManager()
        with self.assertRaises(ValueError):
            manager.restore({"schema_version": 99, "mission": None})
        base = {"schema_version": 1, "mission": None, "completed_count": 0, "failed_count": 0}
        bad = copy.deepcopy(base)
        bad["completed_count"] = -1
        with self.assertRaises(ValueError):
            manager.restore(bad)
        world, dispatcher, ship, event = setup_distress()
        dispatcher.decide(ship, "assist", 101.0)
        manager.dispatch(ship, 101.0, reported_position_nm=event.reported_position_nm)
        malformed = manager.snapshot()
        malformed["mission"]["reported_position_nm"] = [float("nan"), 1.0]
        with self.assertRaises(ValueError):
            PlayerRescueMissionManager.validate_snapshot(malformed)

    def test_reported_plot_validation_rejects_non_finite_coordinates(self):
        world, dispatcher, ship, event = setup_distress()
        dispatcher.decide(ship, "assist", 101.0)
        manager = PlayerRescueMissionManager()
        with self.assertRaises(ValueError):
            manager.dispatch(ship, 101.0, reported_position_nm=(math.inf, 0.0))

    def test_game_routes_to_reported_plot_and_never_teleports_player_hull(self):
        self.assertIn("def _rescue_world_target(self, reported_position_nm):", GAME_SOURCE)
        self.assertIn("world.set_destination(V(target_world[0], target_world[1]), keep_dock=False)", GAME_SOURCE)
        self.assertIn("No instant player", GAME_SOURCE)
        method = GAME_SOURCE[GAME_SOURCE.index("def _start_player_rescue_mission(self, ship):"):]
        method = method[:method.index("def _restore_rescue_navigation(self, mission):")]
        self.assertNotIn("world.ship_pos =", method)
        self.assertNotIn("world.believed_pos =", method)

    def test_game_updates_mission_after_traffic_and_saves_it(self):
        self.assertIn("self._update_player_rescue_mission()", GAME_SOURCE)
        self.assertIn('"player_rescue_mission": self.player_rescue_manager.snapshot()', GAME_SOURCE)
        self.assertIn("PlayerRescueMissionManager.from_snapshot", GAME_SOURCE)
        self.assertIn("PlayerRescueMissionManager.validate_snapshot", GAME_SOURCE)

    def test_phase_switch_is_blocked_during_active_physical_mission(self):
        method = GAME_SOURCE[GAME_SOURCE.index("def _set_campaign_phase(self, phase):"):]
        method = method[:method.index("def _traffic_visual_range_nm(self):")]
        self.assertIn("self.player_rescue_manager.has_active_mission", method)
        self.assertIn("return False", method)

    def test_rescue_transitions_add_radio_transcript_and_outcome(self):
        self.assertIn("def _handle_player_rescue_transition(self, event):", GAME_SOURCE)
        self.assertIn("_append_rescue_radio_history", GAME_SOURCE)
        self.assertIn("Rescue complete:", GAME_SOURCE)
        self.assertIn("priority=PRIORITY_HIGH", GAME_SOURCE)

    def test_save_envelope_version_matches_package(self):
        self.assertIn('__version__ = "13.2.13"', (ROOT / "fishing_sim" / "__init__.py").read_text(encoding="utf-8"))
        self.assertIn('build_career_save_envelope(payload, "13.2.13")', GAME_SOURCE)


if __name__ == "__main__":
    unittest.main()
