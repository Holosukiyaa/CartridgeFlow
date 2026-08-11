import json
import re
import unittest
from pathlib import Path

from core.protocol import (
    ProtocolRegistry,
    build_compatibility_report,
    load_base_implementation,
    load_protocol_artifact_json,
    load_protocol_artifact_text,
)


ROOT = Path(__file__).resolve().parents[3]
DOCUMENT = "protocol/flow-authoring/0.8/specification.md"


@unittest.skipIf(
    load_base_implementation(ROOT)["protocol_generation"]["id"] == "clean-v1",
    "CF-FARP@0.8 source snapshots are historical after the clean-v1 cutover",
)
class ProtocolV08SpecificationTests(unittest.TestCase):
    def test_registry_and_base_publish_v08_support(self):
        registry_data = load_protocol_artifact_json("flow-authoring/0.8/release.json")
        self.assertEqual("0.8", registry_data["version"])
        self.assertEqual({"id": "CF-FARP", "version": "0.7"}, registry_data["supersedes"])
        self.assertEqual("flow-authoring/0.8/capabilities.json", registry_data["capabilities_file"])
        self.assertEqual("flow-authoring/0.8/profiles.json", registry_data["profiles_file"])
        self.assertEqual(DOCUMENT, registry_data["document"])

        registry = ProtocolRegistry(ROOT)
        self.assertTrue(registry.recognizes_protocol("CF-FARP", "0.8"))
        supported = {
            (item["id"], item["version"])
            for item in load_base_implementation(ROOT)["supported_protocols"]
        }
        self.assertIn(("CF-FARP", "0.8"), supported)
        self.assertIn(("CF-FARP", "0.7"), supported)

        report = build_compatibility_report(
            load_base_implementation(ROOT),
            {
                "id": "test.v08.supported",
                "version": "0.0.1",
                "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
                "runtime_contract": {
                    "protocol": "CF-FARP",
                    "protocol_version": "0.8",
                    "required_profiles": ["runtime_core", "flow_analysis"],
                    "recommended_profiles": [],
                    "required_capabilities": ["root_flow_execution", "flow_analysis_report_v1"],
                    "optional_capabilities": [],
                    "required_tools": [],
                    "optional_tools": [],
                },
                "asset_registry": "assets/registry.json",
                "delivery_readiness": {"level": "dev"},
                "mcp_tools": [],
            },
            {
                "protocol": {"id": "CF-FARP", "version": "0.8"},
                "start": "start",
                "states": {"start": {"type": "system", "next": "complete"}, "complete": {"type": "terminal"}},
            },
            ROOT,
        )
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual("cartridgeflow.flow_analysis.v1", report["flow_contract"]["analysis"]["schema"])
        self.assertTrue(report["flow_contract"]["analysis"]["analysis_id"].startswith("analysis:"))

    def test_v08_is_complete_standalone_and_has_valid_toc(self):
        text = load_protocol_artifact_text(DOCUMENT)
        v07 = load_protocol_artifact_text("flow-authoring/0.7/specification.md")
        self.assertGreater(len(text.splitlines()), len(v07.splitlines()))
        for section in [
            "## 6. Manifest 契约",
            "## 28. Portable DLC",
            "## 41. 三层创作模型与唯一事实来源",
            "## 42. 结构化输入输出与数据绑定",
            "## 43. 可执行控制拓扑",
            "## 44. Flow Analyzer",
            "## 45. 派生工程关系",
            "## 46. 诊断、门禁与修复",
            "## 47. Authoring API 与创作 AI",
            "## 48. 从 v0.7 迁移",
            "## 49. v0.7 条款处置矩阵",
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
        self.assertEqual(50, len(targets))
        self.assertEqual([], [target for target in targets if target not in heading_anchors])

    def test_v08_json_examples_and_versioned_vocabulary_are_valid(self):
        text = load_protocol_artifact_text(DOCUMENT)
        json_blocks = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
        self.assertGreaterEqual(len(json_blocks), 45)
        for index, block in enumerate(json_blocks, 1):
            try:
                json.loads(block)
            except json.JSONDecodeError as exc:
                self.fail(f"v0.8 JSON example {index} is invalid: {exc}")

        capability_section = re.search(r"^## 34\..*?\n(.*?)^## 35\.", text, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(capability_section)
        capability_block = re.search(r"```text\n(.*?)\n```", capability_section.group(1), re.DOTALL)
        self.assertIsNotNone(capability_block)
        documented = {item.strip() for item in capability_block.group(1).splitlines() if item.strip()}
        capabilities = load_protocol_artifact_json("flow-authoring/0.8/capabilities.json")
        registered = {item["id"] for item in capabilities["capabilities"]}
        self.assertEqual(registered, documented)

        profiles = load_protocol_artifact_json("flow-authoring/0.8/profiles.json")
        profile_ids = {item["id"] for item in profiles["profiles"]}
        self.assertIn("flow_analysis", profile_ids)
        self.assertEqual([], [item["profile"] for item in capabilities["capabilities"] if item["profile"] not in profile_ids])

    def test_v08_separates_authoring_facts_relations_and_runtime_edges(self):
        text = load_protocol_artifact_text(DOCUMENT)
        for term in [
            "Authoring Facts",
            "cartridgeflow.flow_analysis.v1",
            "source_digest",
            "control_edges",
            "runtime_effect=false",
            "DERIVED_RELATION_IN_CONTROL_GRAPH",
            "INPUT_NOT_AVAILABLE_ON_ALL_PATHS",
            "analysis_report_freshness_guard",
            "safe_autofix_contract",
            "Analyzer 只提出修复，不应用修复",
        ]:
            self.assertIn(term, text)

    def test_v07_published_files_are_not_rewritten_as_v08(self):
        registry_data = load_protocol_artifact_json("flow-authoring/0.7/release.json")
        self.assertEqual("0.7", registry_data["version"])
        self.assertEqual(
            "# CartridgeFlow Flow Authoring Runtime Protocol v0.7",
            load_protocol_artifact_text("flow-authoring/0.7/specification.md")
            .splitlines()[0],
        )


if __name__ == "__main__":
    unittest.main()
