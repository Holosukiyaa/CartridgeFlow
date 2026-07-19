import json
import unittest
from pathlib import Path

from core.protocol import ProtocolRegistry, load_base_implementation


ROOT = Path(__file__).resolve().parents[5]
PACKAGE = Path(__file__).resolve().parents[2]
PROTOCOL_DIR = PACKAGE / "dlc" / "protocols"


class CreativeRecastProtocolRegistryTest(unittest.TestCase):
    def test_crcp_is_visible_only_through_package_overlay(self):
        self.assertFalse(ProtocolRegistry(ROOT).supports_protocol("CF-CRCP", "0.1"))
        registry = ProtocolRegistry(ROOT, overlay_dirs=[PROTOCOL_DIR])
        self.assertTrue(registry.supports_protocol("CF-CRCP", "0.1"))

        protocol = json.loads((PROTOCOL_DIR / "CF-CRCP-0.1.json").read_text(encoding="utf-8"))
        self.assertEqual("active", protocol["status"])
        self.assertTrue(protocol["governance"]["read_only"])
        self.assertEqual("user", protocol["governance"]["approval_authority"])

    def test_crcp_document_is_packaged_with_the_card(self):
        document = PROTOCOL_DIR / "CARTRIDGEFLOW_CREATIVE_RECAST_CONTROL_PROTOCOL_v0.1.md"
        self.assertTrue(document.is_file())
        text = document.read_text(encoding="utf-8")
        for marker in ["ChangeProposal", "Shot Control Bundle", "CreativeSpec"]:
            self.assertIn(marker, text)

    def test_base_does_not_claim_card_owned_crcp(self):
        descriptor = json.loads((PACKAGE / "dlc" / "descriptor.json").read_text(encoding="utf-8"))
        self.assertIn(("CF-CRCP", "0.1"), {(item["id"], item["version"]) for item in descriptor["protocols"]})
        base = load_base_implementation(ROOT)
        supported = {(str(item.get("id")), str(item.get("version"))) for item in base.get("supported_protocols") or []}
        self.assertNotIn(("CF-CRCP", "0.1"), supported)


if __name__ == "__main__":
    unittest.main()
