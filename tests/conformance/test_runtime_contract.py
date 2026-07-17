import unittest
from pathlib import Path

from core.protocol import load_base_implementation, build_compatibility_report


ROOT = Path(__file__).resolve().parents[2]


def minimal_root_flow():
    return {
        "schema_version": "1.0",
        "id": "test.root",
        "start": "start",
        "states": {
            "start": {"type": "terminal", "next": "complete"},
            "complete": {"type": "terminal"},
        },
    }


class RuntimeContractConformanceTest(unittest.TestCase):
    def test_protocol_manifest_is_compatible(self):
        base = load_base_implementation(ROOT)
        manifest = {
            "id": "test.protocol",
            "version": "0.0.1",
            "runtime_contract": {
                "protocol": "CF-FARP",
                "protocol_version": "0.1",
                "required_profiles": ["runtime_core"],
                "recommended_profiles": ["testbench_core"],
                "required_capabilities": ["root_flow_execution", "basic_node_execution"],
                "optional_capabilities": [],
                "required_tools": [],
                "optional_tools": [],
            },
            "delivery_readiness": {"level": "dev"},
            "mcp_tools": [],
        }
        report = build_compatibility_report(base, manifest, minimal_root_flow(), ROOT)
        self.assertTrue(report["ok"])
        self.assertEqual(report["summary"]["blocker"], 0)

    def test_legacy_manifest_warns_not_blocks(self):
        base = load_base_implementation(ROOT)
        report = build_compatibility_report(base, {"id": "legacy", "version": "0.0.1"}, minimal_root_flow(), ROOT)
        self.assertTrue(report["ok"])
        self.assertTrue(report["legacy"])
        self.assertGreaterEqual(report["summary"]["warning"], 1)


if __name__ == "__main__":
    unittest.main()
