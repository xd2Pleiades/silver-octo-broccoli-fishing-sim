"""Headless tests for the atomic, versioned career-save container."""
import json
import tempfile
import unittest
from pathlib import Path

from fishing_sim.world.career_save import (
    CAREER_SAVE_SCHEMA_VERSION, SAVE_FORMAT, atomic_write, build_envelope,
    read_envelope, validate_envelope,
)


class CareerSaveEnvelopeTests(unittest.TestCase):
    def test_envelope_round_trip_and_schema(self):
        payload = {"payload_schema_version": 1, "world": {"time": 42.5}, "crew": ["Ishida"]}
        envelope = build_envelope(payload, "13.2.08")
        self.assertEqual(envelope["format"], SAVE_FORMAT)
        self.assertEqual(envelope["schema_version"], CAREER_SAVE_SCHEMA_VERSION)
        self.assertEqual(validate_envelope(envelope), payload)

    def test_modified_payload_fails_checksum(self):
        envelope = build_envelope({"cash": 100}, "13.2.08")
        envelope["payload"]["cash"] = 999
        with self.assertRaisesRegex(ValueError, "checksum"):
            validate_envelope(envelope)

    def test_unknown_future_schema_fails_clearly(self):
        envelope = build_envelope({}, "13.2.08")
        envelope["schema_version"] = CAREER_SAVE_SCHEMA_VERSION + 1
        with self.assertRaisesRegex(ValueError, "unsupported"):
            validate_envelope(envelope)

    def test_atomic_write_keeps_previous_valid_save_as_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "career.json"
            first = build_envelope({"cash": 111}, "13.2.08")
            second = build_envelope({"cash": 222}, "13.2.08")
            atomic_write(path, first)
            atomic_write(path, second)
            current, recovered = read_envelope(path)
            self.assertFalse(recovered)
            self.assertEqual(validate_envelope(current)["cash"], 222)
            backup, recovered = read_envelope(path.with_suffix(".json.bak"))
            self.assertFalse(recovered)
            self.assertEqual(validate_envelope(backup)["cash"], 111)

    def test_corrupt_primary_recovers_last_good_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "career.json"
            atomic_write(path, build_envelope({"day": 1}, "13.2.08"))
            atomic_write(path, build_envelope({"day": 2}, "13.2.08"))
            path.write_text("{ definitely broken", encoding="utf-8")
            restored, used_backup = read_envelope(path)
            self.assertTrue(used_backup)
            self.assertEqual(validate_envelope(restored)["day"], 1)

    def test_non_finite_payload_cannot_be_checksummed(self):
        with self.assertRaises(ValueError):
            build_envelope({"position": float("nan")}, "13.2.08")

    def test_invalid_json_and_wrong_format_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text(json.dumps({"not": "a career"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unusable"):
                read_envelope(path)


if __name__ == "__main__":
    unittest.main()
