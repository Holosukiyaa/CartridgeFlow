from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from audit_protocol_governance import audit
from core.protocol import ProtocolRegistry, load_protocol_release_catalog


class ProtocolReleaseGovernanceTests(unittest.TestCase):
    def test_release_catalog_drives_current_and_legacy_lifecycle(self):
        catalog = load_protocol_release_catalog(ROOT)
        self.assertEqual({"id": "CF-FARP", "version": "0.9"}, catalog.data["default_for_new_flows"])
        self.assertEqual("current", catalog.get("CF-FARP", "0.9")["lifecycle"])
        self.assertEqual("supported_previous", catalog.get("CF-FARP", "0.8")["lifecycle"])
        self.assertEqual({"id": "CF-FARP", "version": "0.6"}, catalog.lifecycle("CF-FARP", "0.5")["migration_target"])

        registry = ProtocolRegistry(ROOT)
        self.assertTrue(registry.supports_protocol("CF-FARP", "0.9"))
        self.assertTrue(registry.supports_protocol("CF-FARP", "0.8"))
        self.assertFalse(registry.supports_protocol("CF-FARP", "0.5"))
        self.assertTrue(registry.recognizes_protocol("CF-FARP", "0.5"))

    def test_project_protocol_governance_audit_passes(self):
        self.assertEqual([], audit(ROOT))
