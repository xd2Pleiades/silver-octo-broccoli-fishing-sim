"""Dependency-free tests for the first v13.2 world/traffic deliverable."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from fishing_sim.world.coordinates import (
    EquirectangularProjection, PHASE_A_PROJECTION, HIGH_SEAS_PROJECTION,
    distance_nm, bearing_degrees, wrap_longitude_delta,
)
from fishing_sim.world.seeding import chunk_seed, stable_seed, stable_vessel_id
from fishing_sim.world.traffic import (
    Activity, Archetype, TrafficWorld, PHASE_A_COUNTS, PHASE_A_FLEET_TOTAL,
    SOURCE_FLEET_COUNTS, SOURCE_FLEET_TOTAL, REPORT_STALE_AFTER_SIM_SECONDS,
)
from fishing_sim.world.chunk_manager import SpatialIndex, LODManager
from fishing_sim.world.persistence import dumps_contact_snapshot, restore_contact_snapshot
from fishing_sim.systems.ship_radio import ShipRadioService, RadioExchange

ROOT = Path(__file__).resolve().parents[1]


class DeterministicWorldTests(unittest.TestCase):
    def test_current_package_version(self):
        init = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "13.2.13"', init)

    def test_stable_seed_and_ids_are_fixed(self):
        self.assertEqual(chunk_seed(42, 3, 7), chunk_seed(42, 3, 7))
        self.assertNotEqual(stable_seed(1, "traffic", "ship"), stable_seed(1, "radio", "ship"))
        self.assertEqual(stable_vessel_id(1962, "ind_longline", 2),
                         stable_vessel_id(1962, "ind_longline", 2))
        self.assertNotEqual(stable_vessel_id(1962, "ind_longline", 2),
                            stable_vessel_id(1962, "ind_longline", 3))

    def test_fleet_is_deterministic_across_processes(self):
        code = "from fishing_sim.world.traffic import TrafficWorld; w=TrafficWorld(1962); print('|'.join(f'{s.id}:{s.name}:{s.position_nm[0]:.6f}:{s.position_nm[1]:.6f}' for s in w.ships.values()))"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT.parent) + os.pathsep + env.get("PYTHONPATH", "")
        one = subprocess.check_output([sys.executable, "-c", code], env=env, text=True)
        two = subprocess.check_output([sys.executable, "-c", code], env=env, text=True)
        self.assertEqual(one, two)

    def test_explicit_population_totals(self):
        self.assertEqual(PHASE_A_FLEET_TOTAL, sum(PHASE_A_COUNTS.values()))
        self.assertEqual(PHASE_A_FLEET_TOTAL, 40)
        self.assertEqual(SOURCE_FLEET_TOTAL, sum(SOURCE_FLEET_COUNTS.values()))
        self.assertEqual(SOURCE_FLEET_TOTAL, 461)
        self.assertEqual(len(TrafficWorld(1962).ships), PHASE_A_FLEET_TOTAL)

    def test_no_python_hash_used_for_identity(self):
        traffic_source = (ROOT / "world" / "traffic.py").read_text(encoding="utf-8")
        seed_source = (ROOT / "world" / "seeding.py").read_text(encoding="utf-8")
        # Inspect calls, not docstrings/comments that mention the forbidden API.
        for source in (traffic_source, seed_source):
            tree = ast.parse(source)
            calls = [node for node in ast.walk(tree)
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name)
                     and node.func.id == "hash"]
            self.assertEqual(calls, [])

    def test_waypoint_interpolation_is_continuous_at_route_wrap(self):
        traffic = TrafficWorld(1962)
        for ship in traffic.ships.values():
            p0, _, _ = ship.position_at(0.0)
            pend, _, _ = ship.position_at(ship.period_s - 1e-7)
            pnext, _, _ = ship.position_at(ship.period_s)
            self.assertLess(distance_nm(p0, pnext), 1e-8)
            self.assertLess(distance_nm(pend, pnext), 0.01)

    def test_chart_contact_collection_only_contains_reported_ships(self):
        traffic = TrafficWorld(1962)
        self.assertEqual(traffic.known_contacts(), ())
        ship = next(iter(traffic.ships.values()))
        ship.report_position(10.0, error_nm=0.0)
        traffic.mark_known(ship.id)
        self.assertEqual(tuple(s.id for s in traffic.known_contacts()), (ship.id,))

    def test_fast_forward_samples_directly_without_catchup_loop(self):
        traffic = TrafficWorld(1962)
        before_ticks = traffic.tick_count
        traffic.advance(600.0 * 20.0, focus_nm=(0, 0), force=True)
        self.assertEqual(traffic.tick_count, before_ticks + 1)
        self.assertEqual(traffic.sim_time_s, 12000.0)

    def test_positions_remain_inside_legacy_chart_bounds(self):
        traffic = TrafficWorld(1962)
        for ship in traffic.ships.values():
            x, y = ship.position_nm
            self.assertLessEqual(abs(x), 59.0)
            self.assertLessEqual(abs(y), 53.0)

    def test_april_and_peak_season_behavior(self):
        traffic = TrafficWorld(1962)
        catcher = next(s for s in traffic.ships.values() if s.archetype == Archetype.CORPORATE_CATCHER)
        mothership = next(s for s in traffic.ships.values() if s.archetype == Archetype.MOTHERSHIP)
        traffic.advance(0, month=4, day=5, focus_nm=(0, 0), force=True)
        self.assertEqual(catcher.activity, Activity.TRANSIT)
        self.assertEqual(mothership.activity, Activity.ANCHORED)
        traffic.advance(100, month=6, day=10, focus_nm=(0, 0), force=True)
        self.assertIn(catcher.activity, set(Activity))
        # At least one corp catcher has schedule phase activity restored in-season.
        self.assertTrue(any(s.activity != Activity.TRANSIT for s in traffic.ships.values()
                            if s.archetype == Archetype.CORPORATE_CATCHER))


class CoordinateTests(unittest.TestCase):
    def test_phase_a_origin(self):
        self.assertEqual(PHASE_A_PROJECTION.to_nm(140.7, 41.8), (0.0, 0.0))

    def test_projection_roundtrip(self):
        for projection, pairs in ((PHASE_A_PROJECTION, [(140.7, 41.8), (148, 46), (138, 40)]),
                                  (HIGH_SEAS_PROJECTION, [(160, 45), (175, 62), (140, 41)])):
            for lon, lat in pairs:
                x, y = projection.to_nm(lon, lat)
                lon2, lat2 = projection.to_lonlat(x, y)
                self.assertLess(abs(wrap_longitude_delta(lon2 - lon)), 1e-8)
                self.assertAlmostEqual(lat2, lat, places=8)

    def test_date_line_is_short_delta_not_359_degrees(self):
        projection = EquirectangularProjection(179.0, 50.0)
        x, y = projection.to_nm(-179.0, 50.0)
        self.assertAlmostEqual(y, 0.0)
        self.assertGreater(x, 0.0)
        self.assertLess(x, 121.0)

    def test_bearing_and_distance(self):
        self.assertAlmostEqual(distance_nm((0, 0), (3, 4)), 5.0)
        self.assertAlmostEqual(bearing_degrees((0, 0), (0, 1)), 0.0)
        self.assertAlmostEqual(bearing_degrees((0, 0), (1, 0)), 90.0)


class SpatialIndexTests(unittest.TestCase):
    def test_cell_move_does_not_duplicate_id(self):
        index = SpatialIndex(20)
        index.upsert("vessel-a", (1, 1))
        self.assertTrue(index.upsert("vessel-a", (21, 1)))
        self.assertEqual(index.candidates((21, 1), 2), ["vessel-a"])
        self.assertEqual(len(index.positions), 1)

    def test_queries_are_sorted_by_distance_then_stable_id(self):
        index = SpatialIndex(20)
        index.upsert("z", (2, 0))
        index.upsert("b", (-2, 0))
        index.upsert("a", (2, 0))
        self.assertEqual([h.vessel_id for h in index.query((0, 0), 5)], ["a", "b", "z"])

    def test_radio_query_not_clipped_to_active_radius(self):
        traffic = TrafficWorld(1962)
        # Force a known vessel to a radio-reachable point outside the 12-NM active ring.
        ship = next(iter(traffic.ships.values()))
        ship.position_nm = (20.0, 0.0)
        traffic.index.upsert(ship.id, ship.position_nm)
        self.assertNotIn(ship.id, traffic.lod.active_ids)
        self.assertIn(ship, traffic.radio_candidates((0.0, 0.0)))

    def test_active_cap_is_bounded_and_nearest_first(self):
        lod = LODManager(active_radius_nm=12, warm_radius_nm=40, active_cap=3)
        points = {f"s{i}": (float(i), 0.0) for i in range(10)}
        lod.assign(points, (0.0, 0.0))
        self.assertEqual(len(lod.active_ids), 3)
        self.assertEqual(lod.active_ids, ("s0", "s1", "s2"))


class RadioPolicyTests(unittest.TestCase):
    def test_radio_range_gate(self):
        traffic = TrafficWorld(1962)
        ship = next(s for s in traffic.ships.values() if s.radio_fit == "DSB")
        ship.position_nm = (28, 0)
        self.assertFalse(ShipRadioService.can_hail(ship, (0, 0)))
        ship.position_nm = (27, 0)
        self.assertTrue(ShipRadioService.can_hail(ship, (0, 0)))

    def test_corporate_intents_do_not_include_rival_misdirection(self):
        traffic = TrafficWorld(1962)
        ship = next(s for s in traffic.ships.values() if s.archetype == Archetype.CORPORATE_CATCHER)
        ship.trust = -0.8
        self.assertNotIn("grounds_misdirect", ShipRadioService.eligible_intents(ship))
        self.assertIn("grounds_declined", ShipRadioService.eligible_intents(ship))

    def test_competitive_peer_can_misdirect_at_low_trust(self):
        traffic = TrafficWorld(1962)
        ship = next(s for s in traffic.ships.values() if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        ship.personality = "competitive"
        ship.trust = 0.0
        self.assertIn("grounds_misdirect", ShipRadioService.eligible_intents(ship))

    def test_silent_listener_does_not_block_a_later_responder(self):
        traffic = TrafficWorld(1962)
        listeners = list(traffic.ships.values())[:2]
        service = ShipRadioService(1962)
        outcomes = [RadioExchange(False, "no_reply", "test TX", reason="silence"),
                    RadioExchange(True, "peer_exchange", "test TX", ((0.0, "PEER", "Roger", "radio"),))]
        called = []
        original_hail = service.hail
        def scripted_hail(ship, **kwargs):
            called.append(ship.id)
            return outcomes[len(called) - 1]
        service.hail = scripted_hail
        responder, exchange = service.hail_any(
            listeners, player_name="Koei Maru", player_port="Hakodate",
            player_position_nm=(0.0, 0.0), sim_time_s=0.0)
        self.assertEqual(called, [listeners[0].id, listeners[1].id])
        self.assertIs(responder, listeners[1])
        self.assertTrue(exchange.delivered)
        service.hail = original_hail

    def test_routine_hail_has_delivered_exchange_or_valid_no_reply(self):
        traffic = TrafficWorld(1962)
        service = ShipRadioService(1962)
        successes = []
        for ship in traffic.ships.values():
            ship.position_nm = (1.0, 0.0)
            exchange = service.hail(ship, player_name="Kōei Maru", player_port="Hakodate",
                                    player_position_nm=(0.0, 0.0), sim_time_s=30.0,
                                    sea_state=0.1, radio_clarity=1.0)
            if exchange.delivered:
                successes.append((ship, exchange))
                break
            self.assertIn(exchange.intent, ("no_reply", "out_of_range"))
        self.assertTrue(successes)
        ship, exchange = successes[0]
        self.assertTrue(ship.known_to_player)
        self.assertIsNotNone(ship.last_reported_position_nm)
        self.assertNotEqual(ship.position_nm, ship.last_reported_position_nm)
        self.assertTrue(exchange.turns)

    def test_contact_snapshot_roundtrip_preserves_identity_trust_and_report(self):
        traffic = TrafficWorld(1962)
        service = ShipRadioService(1962)
        for ship in traffic.ships.values():
            ship.position_nm = (1, 0)
            exchange = service.hail(ship, player_name="Kōei Maru", player_port="Hakodate",
                                    player_position_nm=(0, 0), sim_time_s=5, sea_state=0.1, radio_clarity=1)
            if exchange.delivered:
                ship.trust = 0.7
                target_id = ship.id
                target_report = ship.last_reported_position_nm
                break
        payload = dumps_contact_snapshot(traffic)
        decoded = json.loads(payload)
        restored = TrafficWorld(1962)
        restore_contact_snapshot(restored, payload)
        self.assertEqual(restored.by_id(target_id).trust, 0.7)
        self.assertEqual(restored.by_id(target_id).last_reported_position_nm, target_report)
        self.assertIn(target_id, {s.id for s in restored.known_contacts()})

    def test_bad_snapshot_schema_fails_safely(self):
        traffic = TrafficWorld(1962)
        with self.assertRaises(ValueError):
            traffic.restore_contacts({"schema_version": 999, "world_seed": 1962, "contacts": {}})


class GameIntegrationContractTests(unittest.TestCase):
    def test_game_integrates_traffic_only_after_world_physics_update(self):
        source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        self.assertIn("self.traffic_world = TrafficWorld(world_seed=1962", source)
        update = source[source.index("    def update(self, dt, keys):"):source.index("    def draw(self):", source.index("    def update(self, dt, keys):"))]
        self.assertLess(update.index("w.update(dt, keys, helm_ok, engine_ok"),
                        update.index("self._update_v13_2_traffic(dt)"))

    def test_ctrl_f11_opens_radio_ui_and_chart_markers_use_reported_positions(self):
        source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        self.assertIn("pygame.KMOD_CTRL", source)
        hotkey = source[source.index("# F11 remains fullscreen; Ctrl+F11 opens the selectable radio UI."):source.index("if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F12:")]
        self.assertIn("self.open_radio_ui()", hotkey)
        chart = source[source.index("    def draw_traffic_chart_contacts("):source.index("    def draw_tow_escort(")]
        self.assertIn("last_reported_position_nm", chart)
        self.assertIn("report_stale_at", chart)


if __name__ == "__main__":
    unittest.main(verbosity=2)
