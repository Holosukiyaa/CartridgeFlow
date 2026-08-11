from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from audit_protocol_governance import audit
from core.protocol import (
    ProtocolRegistry,
    load_protocol_release_catalog,
    load_runtime_protocol_catalog,
)


class ProtocolReleaseGovernanceTests(unittest.TestCase):
    def test_runtime_compatibility_catalog_is_product_owned_and_minimal(self):
        runtime = load_runtime_protocol_catalog(ROOT)
        self.assertEqual(
            {
                "cartridgeflow.capability.settings",
                "cartridgeflow.capability.settings-binding",
                "cartridgeflow.capability.ui",
                "cartridgeflow.host.compatibility",
                "cartridgeflow.host.target",
                "cartridgeflow.runtime.target",
                "cartridgeflow.runtime.host-profile",
            },
            {item["id"] for item in runtime["data_contracts"]},
        )
        serialized_manifest = str(runtime["release_manifest"])
        for governance_field in ("'registry':", "'document':"):
            self.assertNotIn(governance_field, serialized_manifest)
        bindings = {
            (release["id"], release["version"]): tuple(
                item["binding"] for item in release.get("trusted_subprotocols", [])
            )
            for release in runtime["release_manifest"]["releases"]
        }
        self.assertEqual(("creator_service_contract",), bindings[("CF-FARP", "1.3")])

    def test_release_catalog_drives_current_and_legacy_lifecycle(self):
        catalog = load_protocol_release_catalog(ROOT)
        self.assertEqual({"id": "CF-FARP", "version": "1.1"}, catalog.data["default_for_new_flows"])
        self.assertEqual("current", catalog.get("CF-FARP", "1.1")["lifecycle"])
        self.assertEqual("supported_previous", catalog.get("CF-FARP", "1.5")["lifecycle"])
        self.assertEqual("supported_previous", catalog.get("CF-FARP", "1.6")["lifecycle"])
        self.assertEqual("supported_previous", catalog.get("CF-FARP", "1.0")["lifecycle"])
        self.assertEqual("supported_previous", catalog.get("CF-FARP", "0.9")["lifecycle"])
        self.assertEqual("supported_previous", catalog.get("CF-FARP", "0.8")["lifecycle"])
        self.assertEqual({"id": "CF-FARP", "version": "0.6"}, catalog.lifecycle("CF-FARP", "0.5")["migration_target"])

        registry = ProtocolRegistry(ROOT)
        self.assertTrue(registry.supports_protocol("CF-FARP", "1.0"))
        self.assertTrue(registry.supports_protocol("CF-FARP", "1.1"))
        self.assertTrue(registry.supports_protocol("CF-FARP", "0.9"))
        self.assertTrue(registry.supports_protocol("CF-FARP", "0.8"))
        self.assertFalse(registry.supports_protocol("CF-FARP", "0.5"))
        self.assertTrue(registry.recognizes_protocol("CF-FARP", "0.5"))

    def test_project_protocol_governance_audit_passes(self):
        self.assertEqual([], audit(ROOT))
