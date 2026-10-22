from __future__ import annotations
import math
import unittest
from pathlib import Path

from fishing_sim.systems.distress_dispatcher import DistressDispatcher
from fishing_sim.world.traffic import Activity, Archetype, TrafficWorld


class DistressDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.world = TrafficWorld(1962)
        self.dispatcher = DistressDispatcher(1962)
        self.ship = next(s for s in self.world.ships.values()
                         if s.archetype == Archetype.INDEPENDENT_LONGLINE)
        self.ship.position_nm = (1.0, 0.0)
        self.ship.heading_rad = 0.4
        self.world.index.upsert(self.ship.id, self.ship.position_nm)

    def test_trigger_emits_one_shot_mayday_and_reported_position(self):
        event = self.dispatcher.trigger(self.ship, 90.0, radio_staffed=True, kind="engine_failure")
        self.assertIsNotNone(event)
        self.assertTrue(event.heard_by_player)
        self.assertTrue(self.ship.mayday_sent)
        self.assertTrue(self.ship.mayday_player_heard)
        self.assertEqual(self.ship.activity_override, Activity.DISTRESSED)
        self.assertIsNotNone(self.ship.last_reported_position_nm)
        self.assertNotEqual(self.ship.last_reported_position_nm, self.ship.position_nm)
        self.assertIsNone(self.dispatcher.trigger(self.ship, 120.0, radio_staffed=True))
        self.assertEqual(self.dispatcher.events_emitted, 1)

    def test_distress_dispatches_for_coarse_non_rendered_vessel(self):
        self.ship.activity_override = Activity.DISTRESSED
        self.ship.lod = "coarse"
        events = self.dispatcher.update(self.world, 0.0, (0.0, 0.0), sea_state=0.3, radio_staffed=True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].vessel_id, self.ship.id)
        self.assertTrue(events[0].heard_by_player)
        self.assertIn(self.ship.id, self.world.known_contact_ids)
        self.assertIn(self.ship.id, self.world.rescue_contact_ids)

    def test_active_rescue_promotions_are_bounded(self):
        eligible = [s for s in self.world.ships.values()
                    if s.archetype == Archetype.INDEPENDENT_LONGLINE][:4]
        promoted = [self.world.promote_rescue_contact(s.id) for s in eligible]
        self.assertEqual(sum(promoted), 3)
        self.assertLessEqual(len(self.world.rescue_contact_ids), 3)
        self.world.advance(10.0, focus_nm=(0.0, 0.0), force=True)
        self.assertTrue(set(self.world.rescue_contact_ids).issubset(set(self.world.lod.active_ids)))

    def test_assist_changes_trust_once(self):
        self.dispatcher.trigger(self.ship, 90.0, radio_staffed=True, kind="taking_water")
        before = self.ship.trust
        applied, _ = self.dispatcher.decide(self.ship, "assist", 95.0)
        self.assertTrue(applied)
        self.assertAlmostEqual(self.ship.trust, before + 0.40)
        applied2, reason = self.dispatcher.decide(self.ship, "assist", 100.0)
        self.assertFalse(applied2)
        self.assertIn("already", reason)
        self.assertAlmostEqual(self.ship.trust, before + 0.40)
        self.assertEqual(self.ship.distress_decision, "assist")

    def test_ignore_changes_trust_once(self):
        self.dispatcher.trigger(self.ship, 90.0, radio_staffed=True, kind="gear_entanglement")
        before = self.ship.trust
        applied, _ = self.dispatcher.decide(self.ship, "ignore", 95.0)
        self.assertTrue(applied)
        self.assertAlmostEqual(self.ship.trust, before - 0.50)
        applied2, _ = self.dispatcher.decide(self.ship, "ignore", 100.0)
        self.assertFalse(applied2)
        self.assertAlmostEqual(self.ship.trust, before - 0.50)
        self.assertTrue(self.ship.is_rival)

    def test_unstaffed_receiver_does_not_get_actionable_mayday(self):
        event = self.dispatcher.trigger(self.ship, 90.0, radio_staffed=False, kind="injury")
        self.assertIsNotNone(event)
        self.assertFalse(event.heard_by_player)
        self.assertFalse(self.ship.mayday_player_heard)
        applied, reason = self.dispatcher.decide(self.ship, "assist", 95.0)
        self.assertFalse(applied)
        self.assertIn("No received MAYDAY", reason)

    def test_contact_snapshot_preserves_mayday_sent_and_decision(self):
        self.dispatcher.trigger(self.ship, 90.0, radio_staffed=True, kind="taking_water")
        self.dispatcher.decide(self.ship, "assist", 95.0)
        snapshot = self.world.snapshot_contacts()
        restored_world = TrafficWorld(1962)
        restored_world.restore_contacts(snapshot)
        restored = restored_world.by_id(self.ship.id)
        self.assertTrue(restored.mayday_sent)
        self.assertTrue(restored.mayday_resolved)
        self.assertTrue(restored.mayday_player_heard)
        self.assertEqual(restored.distress_decision, "assist")
        self.assertEqual(restored.activity_override, Activity.DISTRESSED)
        self.assertIsNone(DistressDispatcher(1962).trigger(restored, 150.0, radio_staffed=True))

    def test_contact_snapshot_includes_uncontacted_distress(self):
        self.dispatcher.trigger(self.ship, 90.0, radio_staffed=False, kind="engine_failure")
        self.ship.known_to_player = False
        self.ship.contact_count = 0
        self.ship.contact_attempts = 0
        data = self.world.snapshot_contacts()
        self.assertIn(self.ship.id, data["contacts"])
        self.assertTrue(data["contacts"][self.ship.id]["mayday_sent"])

    def test_deterministic_update_does_not_recheck_each_frame(self):
        self.dispatcher.update(self.world, 0.0, (0.0, 0.0), sea_state=1.0, radio_staffed=True)
        last_slot = self.dispatcher._last_slot
        self.dispatcher.update(self.world, 0.2, (0.0, 0.0), sea_state=1.0, radio_staffed=True)
        self.assertEqual(self.dispatcher._last_slot, last_slot)


class DistressGameIntegrationContracts(unittest.TestCase):
    def test_game_dispatches_critical_mayday_and_has_actions(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "core" / "game.py").read_text(encoding="utf-8")
        self.assertIn("self.distress_dispatcher.update(", source)
        self.assertIn("priority=PRIORITY_CRITICAL", source)
        self.assertIn('name == "distress:assist"', source)
        self.assertIn('name == "distress:ignore"', source)
        self.assertIn('def _radio_ui_decide_distress(self, decision):', source)
        self.assertIn("MAYDAY ACTIVE", source)


if __name__ == "__main__":
    unittest.main()
