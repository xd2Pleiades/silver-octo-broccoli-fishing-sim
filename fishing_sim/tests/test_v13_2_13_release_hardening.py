"""Dependency-free contract tests for the v13.2.13 release-hardening tools."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from tools.release_gate_v13_2_13 import VERSION, audit_docs, check_version
from tools.benchmark_v13_2_13_long_campaign import run as run_campaign_benchmark, summary

ROOT = Path(__file__).resolve().parents[2]


class ReleaseHardeningTests(unittest.TestCase):
    def test_package_version_and_required_release_artifacts_match(self):
        self.assertEqual(VERSION, "13.2.13")
        self.assertEqual(check_version(ROOT), [])

    def test_all_markdown_files_live_directly_under_docs_and_links_resolve(self):
        errors, metrics = audit_docs(ROOT)
        self.assertEqual(errors, [])
        self.assertGreaterEqual(metrics["markdown_files"], 100)
        self.assertGreater(metrics["links_checked"], 0)

    def test_rescue_doc_does_not_claim_unrun_graphical_tests(self):
        doc = (ROOT / "docs" / "PLAYER_ASSIST_RESCUE_V13_2_13.md").read_text(encoding="utf-8")
        self.assertIn("not been run", doc.lower())
        self.assertTrue((ROOT / "docs" / "PLAYER_ASSIST_RESCUE_V13_2_13.md").is_file())

    def test_one_day_phase_a_stress_benchmark_is_bounded_and_includes_contacts(self):
        data = run_campaign_benchmark(1, "A")
        self.assertEqual(data["version"], "13.2.13")
        self.assertEqual(data["phase"], "A")
        self.assertEqual(data["vessel_count"], 40)
        self.assertLessEqual(data["active_count"], data["active_cap"] + 3)
        self.assertGreater(data["benchmarked_known_contacts"], 0)
        self.assertGreater(data["combined_snapshot_bytes"], 0)
        self.assertGreater(data["timings"]["weather_tick"]["count"], 0)

    def test_benchmark_summary_handles_empty_and_nonempty_samples(self):
        self.assertEqual(summary([])["count"], 0)
        result = summary([0.001, 0.003, 0.002])
        self.assertEqual(result["count"], 3)
        self.assertGreater(result["p95_ms"], 0.0)

    def test_pygame_availability_is_not_assumed_by_release_gate(self):
        # This keeps release QA useful on a headless host and makes graphical QA separate.
        spec = importlib.util.find_spec("pygame")
        self.assertTrue(spec is None or spec.name == "pygame")


if __name__ == "__main__":
    unittest.main()
