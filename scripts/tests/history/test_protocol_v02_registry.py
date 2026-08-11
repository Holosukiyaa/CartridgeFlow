import unittest
from pathlib import Path

from core.protocol import ProtocolRegistry, load_base_implementation, load_protocol_artifact_json


ROOT = Path(__file__).resolve().parents[3]
CLEAN_V1_ACTIVE = load_base_implementation(ROOT)["protocol_generation"]["id"] == "clean-v1"


class ProtocolV02RegistryTest(unittest.TestCase):
    def test_protocol_v02_is_registered_but_not_claimed_by_base(self):
        registry = ProtocolRegistry(ROOT)
        self.assertFalse(registry.supports_protocol("CF-FARP", "0.2"))
        self.assertTrue(registry.recognizes_protocol("CF-FARP", "0.2"))

        base = load_base_implementation(ROOT)
        supported = {
            (str(item.get("id")), str(item.get("version"))): item
            for item in base.get("supported_protocols") or []
            if isinstance(item, dict)
        }
        self.assertNotIn(("CF-FARP", "0.2"), supported)

    @unittest.skipIf(CLEAN_V1_ACTIVE, "CF-FARP@0.2 source snapshot requires an explicit historical registry")
    def test_protocol_v02_capability_vocabulary_contains_layered_process_contract(self):
        capabilities = load_protocol_artifact_json("flow-authoring/0.2/capabilities.json", ROOT)
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
