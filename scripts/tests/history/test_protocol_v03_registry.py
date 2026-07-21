import json
import unittest
from pathlib import Path

from core.protocol import ProtocolRegistry, load_base_implementation


ROOT = Path(__file__).resolve().parents[3]


class ProtocolV03RegistryTest(unittest.TestCase):
    def test_protocol_v03_is_registered_and_recognized_but_not_supported(self):
        registry = ProtocolRegistry(ROOT)
        self.assertFalse(registry.supports_protocol("CF-FARP", "0.3"))
        self.assertTrue(registry.recognizes_protocol("CF-FARP", "0.3"))
        self.assertEqual("recognized", registry.protocol_lifecycle("CF-FARP", "0.3")["status"])

        base = load_base_implementation(ROOT)
        supported = {
            (str(item.get("id")), str(item.get("version"))): item
            for item in base.get("supported_protocols") or []
            if isinstance(item, dict)
        }
        self.assertNotIn(("CF-FARP", "0.3"), supported)

    def test_protocol_v03_document_path_exists(self):
        protocol = json.loads((ROOT / "protocol" / "CF-FARP-0.3.json").read_text(encoding="utf-8"))
        document = ROOT / protocol["document"]
        self.assertTrue(document.is_file(), protocol["document"])
        self.assertEqual(protocol["supersedes"], {"id": "CF-FARP", "version": "0.2"})

    def test_protocol_v03_documents_interactive_decision_model(self):
        protocol = json.loads((ROOT / "protocol" / "CF-FARP-0.3.json").read_text(encoding="utf-8"))
        document = ROOT / protocol["document"]
        text = document.read_text(encoding="utf-8")

        self.assertIn("## 20. AI 决策节点", text)
        self.assertIn("decision_envelope.v1", text)
        self.assertIn("paused_waiting_user", text)
        self.assertIn("runtime_resume_after_user_input", text)

    def test_protocol_v03_capability_vocabulary_contains_interactive_decision_contract(self):
        capabilities = json.loads((ROOT / "protocol" / "capabilities.json").read_text(encoding="utf-8"))
        ids = {
            str(item.get("id"))
            for item in capabilities.get("capabilities") or []
            if isinstance(item, dict)
        }

        required = {
            "decision_envelope_v1",
            "decision_envelope_validate",
            "runtime_user_input_request",
            "paused_waiting_user_status",
            "pending_interaction_record",
            "runtime_resume_after_user_input",
        }
        self.assertTrue(required <= ids, sorted(required - ids))

        base = load_base_implementation(ROOT)
        base_capabilities = set(base.get("capabilities") or [])
        self.assertIn("runtime_resume_after_user_input", base_capabilities)


if __name__ == "__main__":
    unittest.main()
