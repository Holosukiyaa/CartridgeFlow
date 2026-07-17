import unittest
from pathlib import Path

from core.protocol import load_base_implementation, build_compatibility_report


ROOT = Path(__file__).resolve().parents[2]


class CompatibilityReportConformanceTest(unittest.TestCase):
    def _root_flow(self):
        return {
            "schema_version": "1.0",
            "id": "test.root",
            "start": "start",
            "states": {
                "start": {"type": "terminal", "next": "complete"},
                "complete": {"type": "terminal"},
            },
        }

    def test_missing_required_capability_blocks(self):
        base = load_base_implementation(ROOT)
        manifest = {
            "id": "test.protocol",
            "version": "0.0.1",
            "runtime_contract": {
                "protocol": "CF-FARP",
                "protocol_version": "0.1",
                "required_profiles": ["runtime_core"],
                "required_capabilities": ["missing_capability"],
            },
            "delivery_readiness": {"level": "dev"},
            "mcp_tools": [],
        }
        report = build_compatibility_report(base, manifest, self._root_flow(), ROOT)
        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "blocked")
        self.assertIn("missing_required_capability", [item["code"] for item in report["findings"]])

    def test_required_manifest_tool_is_checked(self):
        base = load_base_implementation(ROOT)
        manifest = {
            "id": "test.protocol",
            "version": "0.0.1",
            "runtime_contract": {
                "protocol": "CF-FARP",
                "protocol_version": "0.1",
                "required_profiles": ["runtime_core"],
                "required_capabilities": ["builtin_tool_call"],
            },
            "delivery_readiness": {"level": "dev"},
            "mcp_tools": [
                {
                    "id": "required_filesystem",
                    "type": "builtin",
                    "server": "filesystem",
                    "tool": "read_file",
                    "required": True,
                }
            ],
        }
        report = build_compatibility_report(base, manifest, self._root_flow(), ROOT)
        self.assertTrue(report["ok"])
        self.assertIn("required_filesystem", report["tools"]["required"])

    def test_unsupported_required_tool_pack_blocks(self):
        base = load_base_implementation(ROOT)
        manifest = {
            "id": "test.protocol",
            "version": "0.0.1",
            "runtime_contract": {
                "protocol": "CF-FARP",
                "protocol_version": "0.1",
                "required_profiles": ["runtime_core"],
                "required_capabilities": ["builtin_tool_call"],
            },
            "delivery_readiness": {"level": "dev"},
            "mcp_tools": [
                {
                    "id": "required_unknown",
                    "type": "builtin",
                    "server": "unknown_server",
                    "tool": "run",
                    "required": True,
                }
            ],
        }
        report = build_compatibility_report(base, manifest, self._root_flow(), ROOT)
        self.assertFalse(report["ok"])
        self.assertIn("unsupported_required_tool_pack", [item["code"] for item in report["findings"]])


if __name__ == "__main__":
    unittest.main()
