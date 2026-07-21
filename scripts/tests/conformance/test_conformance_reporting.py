import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from core.conformance.reporting import REPORT_SCHEMA, build_conformance_report, load_latest_report, write_conformance_report
from core.data_paths import CONFORMANCE_REPORT
from core.llm.retry import RetryConfig


ROOT = Path(__file__).resolve().parents[3]


class ConformanceReportingTests(unittest.TestCase):
    def test_versioned_retry_policy_matches_code_fallback(self):
        configured = json.loads((ROOT / "config" / "defaults" / "llm_retry.json").read_text(encoding="utf-8"))
        fallback = asdict(RetryConfig())

        self.assertEqual(configured["max_retries"], fallback["max_retries"])
        self.assertEqual(configured["initial_delay"], fallback["initial_delay"])
        self.assertEqual(configured["max_delay"], fallback["max_delay"])
        self.assertEqual(configured["exponential_base"], fallback["exponential_base"])
        self.assertEqual(configured["retry_on_status"], list(fallback["retry_on_status"]))
        self.assertEqual(configured["retry_on_errors"], list(fallback["retry_on_errors"]))

    def test_every_declared_capability_has_existing_evidence_entries(self):
        base = json.loads((ROOT / "config" / "base" / "BASE_IMPLEMENTATION.json").read_text(encoding="utf-8"))
        evidence = json.loads((ROOT / "config" / "base" / "capability_evidence.json").read_text(encoding="utf-8"))

        self.assertEqual(set(base["capabilities"]), set(evidence["capabilities"]))
        for capability, set_id in evidence["capabilities"].items():
            record = evidence["evidence_sets"].get(set_id)
            self.assertIsInstance(record, dict, f"{capability}: missing evidence set {set_id}")
            self.assertIn(record.get("verification"), {
                "verified", "happy_path_only", "mock_only", "external_unverified", "implementation_only",
            })
            for reference in record.get("implementation") or []:
                self.assertTrue((ROOT / reference.split("#", 1)[0]).is_file(), f"{capability}: {reference}")
            ui = record.get("ui") or {}
            if ui.get("status") != "not_applicable":
                self.assertTrue(ui.get("entries"), f"{capability}: UI visibility is not mapped")
            for reference in ui.get("entries") or []:
                self.assertTrue((ROOT / reference.split("#", 1)[0]).is_file(), f"{capability}: {reference}")

    def test_current_capabilities_do_not_use_history_tests_as_evidence(self):
        evidence = json.loads((ROOT / "config" / "base" / "capability_evidence.json").read_text(encoding="utf-8"))
        history_modules = {path.stem for path in (ROOT / "scripts" / "tests" / "history").glob("test_*.py")}

        for set_id, record in evidence["evidence_sets"].items():
            selectors = (record.get("positive_tests") or []) + (record.get("failure_tests") or [])
            for selector in selectors:
                module = str(selector).split(".", 1)[0]
                self.assertNotIn(module, history_modules, f"{set_id}: current capability uses history test {selector}")

    def test_base_manifest_references_generated_report_not_manual_pass_list(self):
        base = json.loads((ROOT / "config" / "base" / "BASE_IMPLEMENTATION.json").read_text(encoding="utf-8"))
        conformance = base["conformance"]

        self.assertNotIn("passed_cases", conformance)
        self.assertEqual(REPORT_SCHEMA, conformance["report_schema"])
        self.assertEqual(CONFORMANCE_REPORT.as_posix(), conformance["report_path"])
        self.assertEqual("scripts/run_conformance.py", conformance["report_command"].split()[-1])

    def test_report_expands_all_declared_capabilities_and_round_trips(self):
        evidence = json.loads((ROOT / "config" / "base" / "capability_evidence.json").read_text(encoding="utf-8"))
        selectors = set()
        for record in evidence["evidence_sets"].values():
            selectors.update(record.get("positive_tests") or [])
            selectors.update(record.get("failure_tests") or [])
        cases = [{"id": selector, "status": "passed", "duration_ms": 1.0} for selector in sorted(selectors)]
        report = build_conformance_report(ROOT, cases)

        self.assertEqual(REPORT_SCHEMA, report["schema"])
        self.assertEqual(65, report["capabilities"]["declared"])
        self.assertFalse(report["capabilities"]["configuration_errors"])
        self.assertEqual(0, report["capabilities"]["counts"]["failing"])
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "latest.json"
            write_conformance_report(ROOT, report, target)
            loaded = load_latest_report(ROOT, target)
        self.assertEqual(report, loaded)


if __name__ == "__main__":
    unittest.main()
