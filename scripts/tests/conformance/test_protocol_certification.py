import unittest
from pathlib import Path

from core.protocol import (
    apply_protocol_certification_label,
    build_protocol_certification_report,
    load_base_implementation,
)


ROOT = Path(__file__).resolve().parents[3]


def root_flow():
    return {
        "schema_version": "1.0",
        "id": "test.root",
        "start": "start",
        "states": {
            "start": {"type": "terminal", "next": "complete"},
            "complete": {"type": "terminal"},
        },
        "protocol": {"id": "CF-FARP", "version": "0.6"},
    }


def certified_manifest():
    return {
        "id": "test.certifiable",
        "version": "0.0.1",
        "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
        "runtime_contract": {
            "protocol": "CF-FARP",
            "protocol_version": "0.6",
            "required_profiles": ["runtime_core"],
            "recommended_profiles": ["testbench_core"],
            "required_capabilities": ["root_flow_execution", "basic_node_execution"],
            "optional_capabilities": [],
            "required_tools": [],
            "optional_tools": [],
        },
        "delivery_readiness": {"level": "dev"},
        "branding": {"tags": []},
        "mcp_tools": [],
    }


class ProtocolCertificationConformanceTest(unittest.TestCase):
    def test_legacy_manifest_cannot_be_certified(self):
        base = load_base_implementation(ROOT)
        report = build_protocol_certification_report(base, {"id": "legacy", "version": "0.0.1"}, root_flow(), ROOT)
        self.assertFalse(report["ok"])
        self.assertIn("legacy_not_certifiable", [item["code"] for item in report["findings"]])

    def test_certifiable_manifest_passes(self):
        base = load_base_implementation(ROOT)
        report = build_protocol_certification_report(base, certified_manifest(), root_flow(), ROOT)
        self.assertTrue(report["ok"])
        self.assertEqual(report["label"], "cf-farp-0-6-certified")

    def test_apply_certification_label_requires_ok_report(self):
        base = load_base_implementation(ROOT)
        manifest = certified_manifest()
        report = build_protocol_certification_report(base, manifest, root_flow(), ROOT)
        updated = apply_protocol_certification_label(manifest, report)
        self.assertEqual(updated["protocol_certification"]["status"], "certified")
        self.assertIn("cf-farp-0-6-certified", updated["branding"]["tags"])


if __name__ == "__main__":
    unittest.main()
