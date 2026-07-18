import tempfile
import unittest
from pathlib import Path

from core.cartridge.validator import ManifestValidationError, ManifestValidator
from core.protocol import build_compatibility_report, load_base_implementation


ROOT = Path(__file__).resolve().parents[2]


class ProtocolExtensionCompatibilityTest(unittest.TestCase):
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

    def _manifest(self, extensions=None, protocol_version="0.1"):
        return {
            "id": "test.extension",
            "version": "0.0.1",
            "runtime_contract": {
                "protocol": "CF-FARP",
                "protocol_version": protocol_version,
                "required_profiles": ["runtime_core"],
                "required_capabilities": ["root_flow_execution", "basic_node_execution"],
            },
            "protocol_extensions": extensions or [],
            "delivery_readiness": {"level": "dev"},
            "mcp_tools": [],
        }

    def test_declared_crcp_extension_is_blocked_by_current_base(self):
        base = load_base_implementation(ROOT)
        manifest = self._manifest([
            {
                "id": "CF-CRCP",
                "version": "0.1",
                "required_profiles": ["creative_control_runtime"],
                "required_capabilities": ["control_bundle_validate", "creative_approval_gate"],
            }
        ], protocol_version="0.4")
        report = build_compatibility_report(base, manifest, self._root_flow(), ROOT)
        self.assertFalse(report["ok"])
        self.assertIn("unsupported_protocol_extension", [item["code"] for item in report["findings"]])
        self.assertIn("missing_extension_required_profile", [item["code"] for item in report["findings"]])
        self.assertIn("missing_extension_required_capability", [item["code"] for item in report["findings"]])
        self.assertEqual("CF-CRCP", report["extensions"][0]["id"])
        self.assertFalse(report["extensions"][0]["supported"])

    def test_unknown_extension_is_blocked_and_reported(self):
        base = load_base_implementation(ROOT)
        report = build_compatibility_report(
            base,
            self._manifest([{"id": "CF-UNKNOWN", "version": "9.9"}]),
            self._root_flow(),
            ROOT,
        )
        self.assertFalse(report["ok"])
        self.assertIn("unknown_protocol_extension", [item["code"] for item in report["findings"]])

    def test_extension_must_extend_the_declared_primary_protocol(self):
        base = load_base_implementation(ROOT)
        report = build_compatibility_report(
            base,
            self._manifest([
                {
                    "id": "CF-CRCP",
                    "version": "0.1",
                    "extends": {"id": "CF-FARP", "version": "0.3"},
                }
            ], protocol_version="0.4"),
            self._root_flow(),
            ROOT,
        )
        self.assertIn("protocol_extension_base_mismatch", [item["code"] for item in report["findings"]])

    def test_manifest_validator_requires_extension_identity_and_arrays(self):
        manifest = self._manifest([{"id": "CF-CRCP", "required_capabilities": "not-an-array"}])
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir)
            (package / "root.flow.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ManifestValidationError) as context:
                ManifestValidator().validate_package(package, manifest)
        message = str(context.exception)
        self.assertIn("manifest.protocol_extensions[0].version is required", message)
        self.assertIn("manifest.protocol_extensions[0].required_capabilities must be an array", message)

    def test_manifests_without_extensions_remain_compatible(self):
        base = load_base_implementation(ROOT)
        report = build_compatibility_report(base, self._manifest(), self._root_flow(), ROOT)
        self.assertTrue(report["ok"])
        self.assertEqual([], report["extensions"])


if __name__ == "__main__":
    unittest.main()
