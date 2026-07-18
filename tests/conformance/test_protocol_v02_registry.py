import json
import unittest
from pathlib import Path

from core.protocol import ProtocolRegistry, load_base_implementation


ROOT = Path(__file__).resolve().parents[2]


class ProtocolV02RegistryTest(unittest.TestCase):
    def test_protocol_v02_is_registered_and_claimed_partial_by_base(self):
        registry = ProtocolRegistry(ROOT)
        self.assertTrue(registry.supports_protocol("CF-FARP", "0.2"))

        base = load_base_implementation(ROOT)
        supported = {
            (str(item.get("id")), str(item.get("version"))): item
            for item in base.get("supported_protocols") or []
            if isinstance(item, dict)
        }
        self.assertIn(("CF-FARP", "0.2"), supported)
        self.assertEqual("partial", supported[("CF-FARP", "0.2")].get("status"))

    @unittest.skipUnless(
        (ROOT / "docs" / "protocol" / "CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.2.md").is_file(),
        "historical FARP v0.2 source document is intentionally absent from this workspace",
    )
    def test_protocol_v02_document_path_exists(self):
        protocol = json.loads((ROOT / "protocol" / "CF-FARP-0.2.json").read_text(encoding="utf-8"))
        document = ROOT / protocol["document"]
        self.assertTrue(document.is_file(), protocol["document"])
        self.assertEqual(protocol["supersedes"], {"id": "CF-FARP", "version": "0.1"})

    @unittest.skipUnless(
        (ROOT / "docs" / "protocol" / "CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.2.md").is_file(),
        "historical FARP v0.2 source document is intentionally absent from this workspace",
    )
    def test_protocol_v02_documents_unified_process_model(self):
        protocol = json.loads((ROOT / "protocol" / "CF-FARP-0.2.json").read_text(encoding="utf-8"))
        document = ROOT / protocol["document"]
        text = document.read_text(encoding="utf-8")

        self.assertIn("## 13. 节点统一模型", text)
        self.assertIn('"type": "process"', text)
        self.assertIn('"kind": "input | transfer | retrieval | decision', text)
        self.assertIn('"effect": "none | read_only | writes_store', text)
        self.assertIn("kind=mcp_execute", text)
        self.assertNotIn("process_kind", text)

    def test_protocol_v02_capability_vocabulary_contains_layered_process_contract(self):
        capabilities = json.loads((ROOT / "protocol" / "capabilities.json").read_text(encoding="utf-8"))
        ids = {
            str(item.get("id"))
            for item in capabilities.get("capabilities") or []
            if isinstance(item, dict)
        }

        required = {
            "unified_process_node",
            "process_node_kind_parse",
            "process_executor_contract",
            "process_effect_contract",
            "mcp_read_process",
            "mcp_execute_process",
        }
        self.assertTrue(required <= ids, sorted(required - ids))


if __name__ == "__main__":
    unittest.main()
