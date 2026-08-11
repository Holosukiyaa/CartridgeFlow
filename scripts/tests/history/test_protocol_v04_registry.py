import unittest
from pathlib import Path

from core.protocol import (
    ProtocolArtifactStore,
    ProtocolRegistry,
    load_base_implementation,
    load_protocol_artifact_json,
    load_protocol_artifact_text,
)


ROOT = Path(__file__).resolve().parents[3]
CLEAN_V1_ACTIVE = load_base_implementation(ROOT)["protocol_generation"]["id"] == "clean-v1"


class ProtocolV04RegistryTest(unittest.TestCase):
    def test_protocol_v04_is_registered_and_recognized_but_not_supported(self):
        registry = ProtocolRegistry(ROOT)
        self.assertFalse(registry.supports_protocol("CF-FARP", "0.4"))
        self.assertTrue(registry.recognizes_protocol("CF-FARP", "0.4"))
        self.assertEqual("recognized", registry.protocol_lifecycle("CF-FARP", "0.4")["status"])

        base = load_base_implementation(ROOT)
        supported = {
            (str(item.get("id")), str(item.get("version"))): item
            for item in base.get("supported_protocols") or []
            if isinstance(item, dict)
        }
        self.assertNotIn(("CF-FARP", "0.4"), supported)

    @unittest.skipIf(CLEAN_V1_ACTIVE, "CF-FARP@0.4 source snapshot requires an explicit historical registry")
    def test_protocol_v04_document_path_exists(self):
        protocol = load_protocol_artifact_json("flow-authoring/0.4/release.json", ROOT)
        self.assertTrue(ProtocolArtifactStore(ROOT).exists(protocol["document"]), protocol["document"])
        self.assertEqual(protocol["supersedes"], {"id": "CF-FARP", "version": "0.3"})

    @unittest.skipIf(CLEAN_V1_ACTIVE, "CF-FARP@0.4 source snapshot requires an explicit historical registry")
    def test_protocol_v04_documents_explicit_decision_consume(self):
        protocol = load_protocol_artifact_json("flow-authoring/0.4/release.json", ROOT)
        text = load_protocol_artifact_text(protocol["document"], ROOT)

        self.assertIn("## 23. decision_contract.consume", text)
        self.assertIn("decision_consume_projection", text)
        self.assertIn("禁止通过隐式命名生成消费 key", text)

    @unittest.skipIf(CLEAN_V1_ACTIVE, "CF-FARP@0.4 source snapshot requires an explicit historical registry")
    def test_protocol_v04_is_complete_standalone_protocol_text(self):
        protocol = load_protocol_artifact_json("flow-authoring/0.4/release.json", ROOT)
        text = load_protocol_artifact_text(protocol["document"], ROOT)

        required_sections = [
            "## 7. 卡带包结构",
            "## 8. Manifest 契约",
            "## 9. Runtime Contract",
            "## 10. Delivery Readiness",
            "## 11. Root Flow 结构",
            "## 13. 节点统一模型",
            "## 21. AI 决策节点",
            "## 22. decision_envelope.v1 契约",
            "## 23. decision_contract.consume",
            "## 30. 数据链与 Store",
            "## 31. tool_plan.v1 契约",
            "## 32. Artifact 与 Delivery",
            "## 34. 测试台与探针",
            "## 35. 兼容性报告",
            "## 36. 认证要求",
        ]
        for section in required_sections:
            self.assertIn(section, text)

        self.assertIn("不再是 v0.3 的增量补丁", text)

    @unittest.skipIf(CLEAN_V1_ACTIVE, "CF-FARP@0.4 source snapshot requires an explicit historical registry")
    def test_protocol_v04_capability_vocabulary_contains_consume_contract(self):
        capabilities = load_protocol_artifact_json("flow-authoring/0.4/capabilities.json", ROOT)
        ids = {
            str(item.get("id"))
            for item in capabilities.get("capabilities") or []
            if isinstance(item, dict)
        }

        required = {
            "decision_consume_contract",
            "decision_consume_projection",
        }
        self.assertTrue(required <= ids, sorted(required - ids))

        base = load_base_implementation(ROOT)
        base_capabilities = set(base.get("capabilities") or [])
        self.assertTrue(required <= base_capabilities, sorted(required - base_capabilities))


if __name__ == "__main__":
    unittest.main()
