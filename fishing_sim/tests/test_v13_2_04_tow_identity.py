"""Headless M8 contract tests: one persistent Coast Guard identity end-to-end."""
from pathlib import Path
import unittest

from fishing_sim.systems.tow_escort import TowEscort, TowCrewMember
from fishing_sim.world.traffic import AIShip, Activity, Archetype, TrafficWorld
from fishing_sim.world.persistence import (
    dumps_tow_escort_snapshot, restore_tow_escort_snapshot,
)
from fishing_sim.systems.broadcasts import BroadcastDirector, PRIORITY_MEDIUM, PRIORITY_CRITICAL

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
GAME_SOURCE = (ROOT / "core" / "game.py").read_text(encoding="utf-8")


def make_runtime_contact(escort):
    return AIShip(
        id=escort.vessel_id, name=escort.callsign, callsign=escort.callsign,
        archetype=Archetype.COAST_GUARD, home_port="Hakodate Coast Guard",
        personality="official", schedule=(), period_s=0.0, speed_kn=0.0,
        radio_fit="SSB", radio_range_nm=49.0, position_nm=escort.world_position_nm,
        heading_rad=escort.world_heading_rad, activity=Activity.TRANSIT,
        known_to_player=True, last_reported_position_nm=escort.world_reported_position_nm,
        last_reported_heading_rad=escort.world_heading_rad, last_report_time_s=10.0,
        runtime_kind="tow_escort",
    )


class TowIdentityTests(unittest.TestCase):
    def setUp(self):
        self.escort = TowEscort.coast_guard((1852.0, -926.0), enroute_duration=20.0)
        self.escort.elapsed = 28.0
        self.escort.enroute_elapsed = 17.0
        self.escort.reported_position = (2040.0, -840.0)
        self.escort.last_report_elapsed = 21.0

    def test_vessel_id_is_stable_and_namespaced(self):
        self.assertTrue(self.escort.vessel_id.startswith("coast_guard_launch:"))
        snapshot = self.escort.snapshot()
        restored = TowEscort.from_snapshot(snapshot)
        self.assertEqual(restored.vessel_id, self.escort.vessel_id)
        self.assertEqual(restored.callsign, self.escort.callsign)

    def test_chart_and_traffic_coordinate_conversions_are_inverse_scaled(self):
        self.assertAlmostEqual(self.escort.world_position_nm[0], 10.0)
        self.assertAlmostEqual(self.escort.world_position_nm[1], 5.0)
        self.assertAlmostEqual(self.escort.world_reported_position_nm[0], 2040.0 / 185.2)
        self.assertAlmostEqual(self.escort.world_reported_position_nm[1], 840.0 / 185.2)

    def test_snapshot_roundtrip_preserves_mid_enroute_state_and_crew(self):
        self.escort.crew[0].name = "Radio Operator Endo"
        restored = TowEscort.loads(self.escort.dumps())
        self.assertEqual(restored.snapshot(), self.escort.snapshot())
        self.assertEqual(restored.state, "EN_ROUTE")
        self.assertAlmostEqual(restored.enroute_elapsed, 17.0)
        self.assertEqual(restored.crew[0].name, "Radio Operator Endo")
        self.assertEqual(restored.reported_position, (2040.0, -840.0))

    def test_snapshot_roundtrip_preserves_under_tow_state_and_warning(self):
        self.escort.state = "UNDER_TOW"
        self.escort.line_at_risk = True
        self.escort.warned_line_risk = True
        self.escort.fuel = 0.41
        self.escort.missed_checkins = 1
        restored = TowEscort.loads(self.escort.dumps())
        self.assertEqual(restored.state, "UNDER_TOW")
        self.assertTrue(restored.line_at_risk)
        self.assertTrue(restored.warned_line_risk)
        self.assertEqual(restored.missed_checkins, 1)
        self.assertAlmostEqual(restored.fuel, 0.41)

    def test_restore_rejects_unknown_schema_and_invalid_state(self):
        payload = self.escort.snapshot()
        payload["schema_version"] = 999
        with self.assertRaises(ValueError):
            TowEscort.from_snapshot(payload)
        payload = self.escort.snapshot()
        payload["state"] = "TELEPORTED"
        with self.assertRaises(ValueError):
            TowEscort.from_snapshot(payload)
        payload = self.escort.snapshot()
        payload["vessel_id"] = "coast_guard_launch:some_other_vessel"
        with self.assertRaises(ValueError):
            TowEscort.from_snapshot(payload)

    def test_versioned_persistence_wrapper_roundtrip_and_none(self):
        restored = restore_tow_escort_snapshot(dumps_tow_escort_snapshot(self.escort))
        self.assertEqual(restored.snapshot(), self.escort.snapshot())
        self.assertIsNone(restore_tow_escort_snapshot(dumps_tow_escort_snapshot(None)))

    def test_runtime_contact_is_same_id_in_index_and_known_chart_contacts(self):
        world = TrafficWorld(1962, active_cap=1)
        contact = make_runtime_contact(self.escort)
        world.register_runtime_ship(contact)
        self.assertIs(world.by_id(self.escort.vessel_id), contact)
        self.assertIn(self.escort.vessel_id, world.runtime_ship_ids)
        self.assertIn(self.escort.vessel_id, world.known_contact_ids)
        self.assertIn(contact, world.nearby(contact.position_nm, 0.1))
        self.assertIn(contact, world.known_contacts())
        self.assertIn(contact, world.radio_candidates(contact.position_nm))

    def test_schedule_advance_does_not_overwrite_runtime_tow_position(self):
        world = TrafficWorld(1962, active_cap=1)
        contact = make_runtime_contact(self.escort)
        world.register_runtime_ship(contact)
        expected = (72.25, -33.5)
        world.sync_runtime_ship(contact.id, position_nm=expected, heading_rad=0.75,
                                activity=Activity.TRANSIT,
                                reported_position_nm=(71.0, -32.0), report_time_s=14.0)
        world.advance(500.0, focus_nm=(0.0, 0.0), force=True)
        self.assertEqual(world.by_id(contact.id).position_nm, expected)
        self.assertEqual(world.index.positions[contact.id], expected)
        self.assertIn(contact.id, world.lod.active_ids)  # rescue override can exceed the cap

    def test_generic_visual_sighting_does_not_replace_captains_radio_plot(self):
        world = TrafficWorld(1962)
        contact = make_runtime_contact(self.escort)
        world.register_runtime_ship(contact)
        reported = contact.last_reported_position_nm
        world.observe_nearby(contact.position_nm, 120.0, radius_nm=2.0)
        self.assertEqual(contact.last_reported_position_nm, reported)

    def test_unregistration_removes_one_contact_from_queries_and_chart(self):
        world = TrafficWorld(1962)
        contact = make_runtime_contact(self.escort)
        world.register_runtime_ship(contact)
        world.unregister_runtime_ship(contact.id)
        self.assertIsNone(world.by_id(contact.id))
        self.assertNotIn(contact.id, world.index.positions)
        self.assertNotIn(contact.id, world.known_contact_ids)
        self.assertNotIn(contact.id, world.runtime_ship_ids)


class TowIdentityIntegrationContracts(unittest.TestCase):
    def test_game_syncs_escort_after_both_world_controllers_advance(self):
        update = GAME_SOURCE.index("self._update_tow_escort(dt)")
        traffic = GAME_SOURCE.index("self._update_v13_2_traffic(dt)", update)
        sync = GAME_SOURCE.index("self._sync_tow_escort_world_entity()", traffic)
        self.assertLess(update, traffic)
        self.assertLess(traffic, sync)
        self.assertIn('runtime_kind="tow_escort"', GAME_SOURCE)

    def test_radio_ui_routes_selected_escort_vessel_id_to_captain_dialogue(self):
        self.assertIn('ship.id == getattr(escort, "vessel_id", None)', GAME_SOURCE)
        self.assertIn('return self.tow_escort_talk(topic_map.get(topic, "position"), via_radio_ui=True)', GAME_SOURCE)
        self.assertIn('self.radio_ui_histories.setdefault(escort.vessel_id', GAME_SOURCE)

    def test_chart_marker_is_shared_and_sea_hull_is_not_drawn_twice(self):
        self.assertIn('prefix = "CG " if getattr(ship, "runtime_kind", "scheduled") == "tow_escort" else ""', GAME_SOURCE)
        self.assertIn('if ship.id == tow_id or ship.lod != "active":', GAME_SOURCE)
        self.assertIn('self.draw_traffic_chart_contacts(chart_surface, point, map_w, map_h, pal)', GAME_SOURCE)
        self.assertIn('M8: the shared traffic entity supplies the Coast Guard marker', GAME_SOURCE)

    def test_transcript_metadata_includes_stable_tow_entity_id(self):
        self.assertIn('source = "%s:%s" % (source, escort.vessel_id)', GAME_SOURCE)

    def test_critical_traffic_closes_modal_radio_and_discards_unheard_reply(self):
        self.assertIn('if priority >= PRIORITY_CRITICAL and getattr(self, "radio_ui_open", False):', GAME_SOURCE)
        self.assertIn('self.radio_ui_status = "DISTRESS TRAFFIC — current exchange interrupted."', GAME_SOURCE)
        self.assertIn('del history["lines"][visible_count:]', GAME_SOURCE)

    def test_critical_mayday_interrupts_medium_priority_tow_conversation(self):
        director = BroadcastDirector()
        emitted = []
        can_emit = lambda _channel, _priority: True
        emit = lambda conversation, turn: emitted.append((conversation.source, turn.speaker))
        director.enqueue([(0.0, "KIKU MARU", "Line holding. Over.", "radio"),
                          (10.0, "KIKU MARU", "Continue homeward. Over.", "radio")],
                         priority=PRIORITY_MEDIUM, source="tow_escort:coast_guard_launch:kiku_maru")
        director.update(0.0, can_emit, emit)
        self.assertEqual(emitted[-1][0], "tow_escort:coast_guard_launch:kiku_maru")
        director.enqueue([(0.0, "SRT-204", "MAYDAY, taking water. Over.", "radio")],
                         priority=PRIORITY_CRITICAL, source="mayday:srt-204")
        self.assertGreaterEqual(director.interrupted_count, 1)
        director.update(0.0, can_emit, emit)
        self.assertEqual(emitted[-1], ("mayday:srt-204", "SRT-204"))

    def test_package_version_updated(self):
        version = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "13.2.13"', version)


if __name__ == "__main__":
    unittest.main(verbosity=2)
