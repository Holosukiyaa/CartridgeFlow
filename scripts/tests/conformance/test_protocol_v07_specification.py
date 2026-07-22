import json
import re
import unittest
from pathlib import Path

from core.protocol import ProtocolRegistry, build_compatibility_report, load_base_implementation


ROOT = Path(__file__).resolve().parents[3]
DOCUMENT = ROOT / "docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.7.md"


def v07_manifest():
    return {
        "id": "test.v07.unsupported",
        "version": "0.0.1",
        "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
        "runtime_contract": {
            "protocol": "CF-FARP",
            "protocol_version": "0.7",
            "required_profiles": ["runtime_core", "interaction_runtime"],
            "recommended_profiles": [],
            "required_capabilities": ["root_flow_execution", "interaction_node"],
            "optional_capabilities": [],
            "required_tools": [],
            "optional_tools": [],
        },
        "asset_registry": "assets/registry.json",
        "interaction_components": "assets/components.json",
        "delivery_readiness": {"level": "dev"},
        "mcp_tools": [],
    }


def v07_flow():
    return {
        "schema_version": "1.0",
        "id": "test.v07.root",
        "protocol": {"id": "CF-FARP", "version": "0.7"},
        "start": "start",
        "states": {
            "start": {"type": "system", "next": "complete"},
            "complete": {"type": "terminal"},
        },
    }


class ProtocolV07SpecificationTests(unittest.TestCase):
    def test_registry_publishes_v07_with_passive_and_sandboxed_base_support(self):
        registry_data = json.loads((ROOT / "protocol/CF-FARP-0.7.json").read_text(encoding="utf-8"))
        self.assertEqual("0.7", registry_data["version"])
        self.assertEqual({"id": "CF-FARP", "version": "0.6"}, registry_data["supersedes"])
        self.assertEqual("capabilities-0.7.json", registry_data["capabilities_file"])
        self.assertEqual("profiles-0.7.json", registry_data["profiles_file"])
        self.assertEqual(DOCUMENT, ROOT / registry_data["document"])

        registry = ProtocolRegistry(ROOT)
        self.assertTrue(registry.recognizes_protocol("CF-FARP", "0.7"))
        base = load_base_implementation(ROOT)
        supported = {(item["id"], item["version"]) for item in base["supported_protocols"]}
        self.assertIn(("CF-FARP", "0.7"), supported)
        self.assertIn("interaction_runtime", base["profiles"])
        self.assertIn("passive_html_safety", base["capabilities"])
        self.assertIn("sandboxed_interaction_component", base["capabilities"])
        self.assertIn("interaction_process_isolation", base["capabilities"])
        self.assertIn("interaction_host_channel", base["capabilities"])
        self.assertIn("cartridge_portability_report", base["capabilities"])

        report = build_compatibility_report(base, v07_manifest(), v07_flow(), ROOT)
        self.assertTrue(report["ok"])
        self.assertEqual("supported", report["protocol"]["lifecycle"])

    def test_v07_is_complete_standalone_and_has_valid_toc(self):
        text = DOCUMENT.read_text(encoding="utf-8")
        v06 = (ROOT / "docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.6.md").read_text(encoding="utf-8")
        self.assertGreater(len(text.splitlines()), len(v06.splitlines()))
        for section in [
            "## 6. Manifest 契约",
            "## 11. 业务节点与两类搭建模型",
            "## 12. Kind 与交互节点约束",
            "## 16. Pending Interaction",
            "## 28. Portable DLC",
            "## 29. DLC Worker 与前端消息",
            "## 39. v0.6 条款处置矩阵",
        ]:
            self.assertIn(section, text)

        headings = re.findall(r"^## (.+)$", text, re.MULTILINE)

        def anchor(title):
            value = re.sub(r"[^\w\- ]", "", title.strip().lower(), flags=re.UNICODE)
            return re.sub(r" +", "-", value)

        heading_anchors = {anchor(item) for item in headings}
        first_section = re.search(r"^## 1\..+$", text, re.MULTILINE)
        self.assertIsNotNone(first_section)
        toc = text[text.index("## 目录"):first_section.start()]
        targets = re.findall(r"\]\(#([^\)]+)\)", toc)
        self.assertEqual(40, len(targets))
        self.assertEqual([], [target for target in targets if target not in heading_anchors])

    def test_v07_json_examples_and_versioned_vocabulary_are_valid(self):
        text = DOCUMENT.read_text(encoding="utf-8")
        json_blocks = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
        self.assertGreaterEqual(len(json_blocks), 35)
        for index, block in enumerate(json_blocks, 1):
            try:
                json.loads(block)
            except json.JSONDecodeError as exc:
                self.fail(f"v0.7 JSON example {index} is invalid: {exc}")

        capability_section = re.search(r"^## 34\..*?\n(.*?)^## 35\.", text, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(capability_section)
        capability_block = re.search(r"```text\n(.*?)\n```", capability_section.group(1), re.DOTALL)
        self.assertIsNotNone(capability_block)
        documented = {item.strip() for item in capability_block.group(1).splitlines() if item.strip()}
        capabilities = json.loads((ROOT / "protocol/capabilities-0.7.json").read_text(encoding="utf-8"))
        registered = {item["id"] for item in capabilities["capabilities"]}
        self.assertEqual(registered, documented)

        profiles = json.loads((ROOT / "protocol/profiles-0.7.json").read_text(encoding="utf-8"))
        profile_ids = {item["id"] for item in profiles["profiles"]}
        self.assertIn("interaction_runtime", profile_ids)
        self.assertEqual([], [item["profile"] for item in capabilities["capabilities"] if item["profile"] not in profile_ids])

    def test_v07_requires_asset_backed_interactions_and_static_routes(self):
        text = DOCUMENT.read_text(encoding="utf-8")
        for term in [
            "cartridgeflow.asset_registry.v1",
            "cartridgeflow.interaction_components.v1",
            "kind=interaction",
            "display_name",
            "component_ref",
            "action_routes",
            "resume_by_action_route",
            "interaction.propose",
            "kind=ui` 在 v0.7 中不是合法别名",
        ]:
            self.assertIn(term, text)
        self.assertIn("Component iframe 只能更新 run-scoped draft 或提出 action intent", text)
        self.assertIn("不得直接调用其他节点", text)
        self.assertIn("最终 action controls 必须由 Host 在 sandbox iframe 外", text)

    def test_v07_script_security_is_explicit_and_fail_closed(self):
        text = DOCUMENT.read_text(encoding="utf-8")
        for term in [
            "cartridgeflow.portable_dlc.v2",
            "external_hashed_only",
            "script-src 'self'",
            "connect-src 'none'",
            "navigate-to 'none'",
            "MUST NOT 启用 `allow-same-origin`",
            "专用不可信 origin",
            "interaction_process_isolation",
            "MessageChannel",
            "X-Content-Type-Options: nosniff",
            "Referrer-Policy: no-referrer",
            "INTERACTION_SCRIPT_FORBIDDEN",
            "INTERACTION_CHANNEL_SCOPE_MISMATCH",
        ]:
            self.assertIn(term, text)
        for forbidden in ["inline script", "`eval`", "WebAssembly", "Service Worker", "任意网络代理"]:
            self.assertIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
