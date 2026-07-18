import json
import unittest
from pathlib import Path

from core.protocol import ProtocolRegistry, load_base_implementation


ROOT = Path(__file__).resolve().parents[2]


class CreativeRecastProtocolRegistryTest(unittest.TestCase):
    def test_crcp_v01_is_registered_as_active_read_only_extension(self):
        registry = ProtocolRegistry(ROOT)
        self.assertTrue(registry.supports_protocol("CF-CRCP", "0.1"))

        protocol = json.loads((ROOT / "protocol" / "CF-CRCP-0.1.json").read_text(encoding="utf-8"))
        self.assertEqual("active", protocol["status"])
        self.assertEqual({"id": "CF-FARP", "version": "0.4"}, protocol["extends"])
        self.assertTrue(protocol["governance"]["read_only"])
        self.assertEqual("user", protocol["governance"]["approval_authority"])

    def test_crcp_v01_document_is_complete_and_exists(self):
        protocol = json.loads((ROOT / "protocol" / "CF-CRCP-0.1.json").read_text(encoding="utf-8"))
        document = ROOT / protocol["document"]
        self.assertTrue(document.is_file(), protocol["document"])

        text = document.read_text(encoding="utf-8")
        required_sections = [
            "## 4. 版本治理与只读规则",
            "## 7. 锁定项与自由项",
            "## 10. Shot Control Bundle 契约",
            "## 11. CreativeSpec 契约",
            "## 14. 变更提案与用户批准",
            "## 17. 失败、重试与回滚",
            "## 20. 兼容性、能力与认证",
            "## 23. 禁止事项",
        ]
        for section in required_sections:
            self.assertIn(section, text)

        self.assertIn("ChangeProposal", text)
        self.assertIn("LLM 不能作为自己的批准人", text)
        self.assertIn("不得原地修改任何规范性规则", text)

    def test_crcp_vocabulary_is_registered_but_base_does_not_claim_support(self):
        profiles = json.loads((ROOT / "protocol" / "profiles.json").read_text(encoding="utf-8"))
        profile_ids = {str(item.get("id")) for item in profiles.get("profiles") or []}
        self.assertTrue({
            "creative_control_runtime",
            "creative_control_testbench",
            "creative_control_authoring",
        } <= profile_ids)

        capabilities = json.loads((ROOT / "protocol" / "capabilities.json").read_text(encoding="utf-8"))
        capability_ids = {str(item.get("id")) for item in capabilities.get("capabilities") or []}
        self.assertTrue({
            "control_bundle_v1",
            "control_bundle_validate",
            "creative_spec_v1",
            "creative_workflow_allowlist",
            "creative_change_proposal",
            "creative_approval_gate",
            "creative_run_snapshot",
            "creative_failure_record",
            "creative_quality_gates",
            "creative_artifact_audit",
        } <= capability_ids)

        base = load_base_implementation(ROOT)
        supported = {
            (str(item.get("id")), str(item.get("version")))
            for item in base.get("supported_protocols") or []
            if isinstance(item, dict)
        }
        self.assertNotIn(("CF-CRCP", "0.1"), supported)

        base_capabilities = set(base.get("capabilities") or [])
        self.assertNotIn("creative_approval_gate", base_capabilities)

    def test_action_plan_defers_to_crcp_protocol(self):
        text = (ROOT / "docs" / "production" / "DIGITAL_SURROGATE_COMFYUI_COMPLEMENT_ACTION_PLAN.md").read_text(encoding="utf-8")
        self.assertIn("文档性质：非规范实施指南", text)
        self.assertIn("CF-CRCP@0.1", text)


if __name__ == "__main__":
    unittest.main()
