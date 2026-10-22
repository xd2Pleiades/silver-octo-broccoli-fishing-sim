"""Static contract tests for Game save/load wiring; no Pygame display required."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT / "fishing_sim" / "core" / "game.py"


class CareerSaveGameContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GAME.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.game_class = next(n for n in cls.tree.body if isinstance(n, ast.ClassDef) and n.name == "Game")
        cls.methods = {n.name: n for n in cls.game_class.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def test_global_ctrl_s_and_ctrl_o_do_not_steal_plain_o(self):
        self.assertIn("pygame.KMOD_CTRL", self.source)
        self.assertIn("self.save_career()", self.source)
        self.assertIn("self.load_career()", self.source)
        self.assertIn("elif k == pygame.K_o:", self.source)

    def test_save_is_json_versioned_and_atomic(self):
        self.assertIn("build_career_save_envelope", self.source)
        self.assertIn("atomic_write_career_save", self.source)
        self.assertIn("career_v13_2.json", self.source)
        self.assertIn("_career_snapshot", self.methods)

    def test_round_trip_covers_weather_traffic_tow_radio_catch_and_crew(self):
        snap = ast.get_source_segment(self.source, self.methods["_career_snapshot"])
        for token in ("world_weather_grid", "traffic_contacts", "tow_escort", "ship_radio_service", "radio_ui_histories",
                      "radio_transcript_queue", "radio_calls", "pending_radio_calls",
                      "broadcast_director", "radio_system", "distress_dispatcher", "sailors",
                      "longline", "catch", "gut_book", "world_waves", "random_state"):
            self.assertIn(token, snap)

    def test_active_broadcast_cursor_and_timers_are_saved(self):
        snap = ast.get_source_segment(self.source, self.methods["_career_snapshot"])
        restore = ast.get_source_segment(self.source, self.methods["_restore_career_snapshot"])
        for token in ("sequence", "index", "timer", "turns"):
            self.assertIn(token, snap)
            self.assertIn(token, restore)

    def test_restore_rolls_back_if_reconstruction_fails(self):
        load = ast.get_source_segment(self.source, self.methods["load_career"])
        self.assertIn("before = self._career_snapshot()", load)
        self.assertIn("self._restore_career_snapshot(before)", load)

    def test_prng_state_validated_before_mutation_and_restored_last(self):
        validate = ast.get_source_segment(self.source, self.methods["_validate_career_snapshot"])
        restore = ast.get_source_segment(self.source, self.methods["_restore_career_snapshot"])
        self.assertIn("probe_rng.setstate", validate)
        self.assertGreater(restore.index("random.setstate(rng_state)"),
                           restore.index("self._update_station_roles(0.0)"))

    def test_load_validates_before_mutating(self):
        src = ast.get_source_segment(self.source, self.methods["load_career"])
        self.assertLess(src.index("_validate_career_snapshot(payload)"), src.index("_restore_career_snapshot(payload)"))
        self.assertIn("allow_backup=True", src)

    def test_restore_rebuilds_traffic_world_before_restoring_contact_deltas(self):
        restore = ast.get_source_segment(self.source, self.methods["_restore_career_snapshot"])
        self.assertIn("active_world = TrafficWorld", restore)
        self.assertLess(restore.index("active_world = TrafficWorld"),
                        restore.index("self.traffic_world.restore_contacts(traffic_data)"))
        self.assertIn("self.distress_dispatcher._last_slot", restore)

    def test_mid_rescue_boat_and_casualty_identity_are_persisted(self):
        snap = ast.get_source_segment(self.source, self.methods["_career_snapshot"])
        restore = ast.get_source_segment(self.source, self.methods["_restore_career_snapshot"])
        for token in ("rescue_operation", "rescue_boat_state", "rescue_boat_hands",
                      "rescue_boat_passenger", "alarm_target", "unseen_overboard", "sighting_timers"):
            self.assertIn(token, snap)
        for token in ("raw_boat", "by_name.get(raw_boat.get(\"target\"))",
                      "by_name.get(cstate.get(\"alarm_target\"))"):
            self.assertIn(token, restore)

    def test_mid_ladder_and_lifeline_references_are_saved_by_identity(self):
        snap = ast.get_source_segment(self.source, self.methods["_career_snapshot"])
        validate = ast.get_source_segment(self.source, self.methods["_validate_career_snapshot"])
        restore = ast.get_source_segment(self.source, self.methods["_restore_career_snapshot"])
        self.assertIn('"ladder_state"', snap)
        self.assertIn('"lifeline"', snap)
        self.assertIn('"rescue_target"', snap)
        self.assertIn('"link_index"', validate)
        self.assertIn('"link": self.ship.links[link_index]', restore)
        self.assertIn('sailor.lifeline = by_name.get(refs.get("lifeline"))', restore)

    def test_muster_and_bucket_chain_rebind_sailor_objects(self):
        snap = ast.get_source_segment(self.source, self.methods["_career_snapshot"])
        restore = ast.get_source_segment(self.source, self.methods["_restore_career_snapshot"])
        self.assertIn("crew_drills", snap)
        self.assertIn("muster_expected", snap)
        self.assertIn("bucket_chain_hands", snap)
        self.assertIn("self.muster_expected = {by_name[n]", restore)
        self.assertIn("self.bucket_chain_hands = {by_name[n]", restore)

    def test_bait_and_hatch_selection_are_in_game_snapshot_fields(self):
        fields = ast.get_source_segment(self.source, self.game_class)
        for token in ('"bait"', '"bait_fresh"', '"bait_sel"', '"bait_warned"', '"hatch_flip"'):
            self.assertIn(token, fields)
        snapshot = ast.get_source_segment(self.source, self.methods["_career_snapshot"])
        self.assertIn("for name in self.CAREER_GAME_FIELDS", snapshot)

    def test_traffic_contact_snapshot_is_validated_as_a_mapping(self):
        validate = ast.get_source_segment(self.source, self.methods["_validate_career_snapshot"])
        self.assertIn('for section in ("traffic_contacts",)', validate)
        self.assertIn('isinstance(snapshot.get(section), dict)', validate)
        self.assertIn('temp_world.restore_contacts(traffic_snapshot)', validate)

    def test_tow_ack_binds_world_before_reading_position(self):
        section = self.source[self.source.index('if call["kind"] == "tow":', self.source.index('def _update_radio')):]
        section = section[:section.index('self.tow_escort = TowEscort.coast_guard')]
        self.assertLess(section.index("w = self.world"), section.index("w.ship_pos.distance_to(w.berth)"))

    def test_package_version_is_updated(self):
        version = (ROOT / "fishing_sim" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('"13.2.13"', version)


if __name__ == "__main__":
    unittest.main()
