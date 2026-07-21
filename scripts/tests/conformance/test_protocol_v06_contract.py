import json
import re
import unittest
from pathlib import Path

from core.extensions import PortableDlcValidationError, load_portable_dlc_descriptor
from core.protocol import (
    ProtocolRegistry,
    build_compatibility_report,
    build_protocol_certification_report,
    build_v06_flow_contract_report,
    load_base_implementation,
)
from scripts.tests.fixtures.portable_dlc import PortableDlcFixture


ROOT = Path(__file__).resolve().parents[3]


def v06_manifest(required_capabilities=None, mcp_tools=None):
    return {
        "id": "test.v06",
        "version": "0.0.1",
        "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
        "runtime_contract": {
            "protocol": "CF-FARP",
            "protocol_version": "0.6",
            "required_profiles": ["runtime_core"],
            "recommended_profiles": [],
            "required_capabilities": required_capabilities or [
                "root_flow_execution",
                "runtime_error_envelope_v1",
                "runtime_state_machine",
                "checkpoint_persistence",
                "delivery_primary_output_guard",
            ],
            "optional_capabilities": [],
            "required_tools": [],
            "optional_tools": [],
        },
        "delivery_readiness": {"level": "dev"},
        "branding": {"tags": []},
        "mcp_tools": mcp_tools or [],
    }


def v06_flow(states=None):
    return {
        "schema_version": "1.0",
        "id": "test.v06.root",
        "protocol": {"id": "CF-FARP", "version": "0.6"},
        "start": "start",
        "states": states or {
            "start": {"type": "system", "next": "collect"},
            "collect": {
                "type": "process",
                "kind": "input",
                "executor": "user",
                "effect": "writes_store",
                "input_kind": "initial",
                "source": "user_form",
                "input_schema": "brief.v1",
                "output": "brief",
                "next": "deliver",
            },
            "deliver": {
                "type": "process",
                "kind": "delivery",
                "executor": "deterministic",
                "effect": "writes_store",
                "input": "brief",
                "output": "delivery",
                "primary_output": "delivery",
                "next": "complete",
            },
            "complete": {"type": "terminal"},
        },
    }


class ProtocolV06ContractTest(unittest.TestCase):
    def test_base_and_runtime_protocols_are_registered_as_separate_contracts(self):
        registry = ProtocolRegistry(ROOT)
        self.assertTrue(registry.supports_protocol("CARTRIDGEFLOW-BASE", "0.2"))
        self.assertTrue(registry.supports_protocol("CF-FARP", "0.6"))

        base = load_base_implementation(ROOT)
        self.assertEqual({"id": "CARTRIDGEFLOW-BASE", "version": "0.2"}, base["base_contract"])
        self.assertIn(("CF-FARP", "0.6"), {(item["id"], item["version"]) for item in base["supported_protocols"]})

    def test_v06_documents_are_complete_standalone_protocols(self):
        base_registry = json.loads((ROOT / "protocol" / "CARTRIDGEFLOW-BASE-0.2.json").read_text(encoding="utf-8"))
        farp_registry = json.loads((ROOT / "protocol" / "CF-FARP-0.6.json").read_text(encoding="utf-8"))
        base_text = (ROOT / base_registry["document"]).read_text(encoding="utf-8")
        farp_text = (ROOT / farp_registry["document"]).read_text(encoding="utf-8")

        for section in ["## 3. 所有权模型", "## 5. 协议版本生命周期", "## 9. 运行状态与错误", "## 16. 发布与变更"]:
            self.assertIn(section, base_text)
        for section in ["## 6. Manifest 契约", "## 20. Runtime Error Envelope", "## 22. Retry、Resume、Rollback 与 Restart", "## 28. Portable DLC"]:
            self.assertIn(section, farp_text)
        self.assertNotIn("某个具体供应商", farp_text)

        old_lines = len((ROOT / "docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.5.md").read_text(encoding="utf-8").splitlines())
        new_lines = len(farp_text.splitlines())
        self.assertGreaterEqual(new_lines, old_lines)
        self.assertIn("## 目录", farp_text)
        self.assertIn("## 38. 完整示例", farp_text)
        self.assertIn("## 39. v0.5 条款处置矩阵", farp_text)
        self.assertIn("## 40. 规范追踪与演进", farp_text)
        for section in [
            "### 11.3 Executor 规则",
            "### 11.4 Effect 规则",
            "### 15.1 Consume 字段规则",
            "### 16.1 Interaction 记录",
            "### 21.1 Checkpoint 内容",
            "### 24.1 Provenance",
            "### 28.2 Descriptor 完整结构",
            "### 29.2 Worker 生命周期",
            "### 31.5 无残留验收",
        ]:
            self.assertIn(section, farp_text)
        for term in ["Manifest", "Root Flow", "Decision Envelope", "Tool Plan", "Artifact", "Delivery", "Worker", "兼容性报告", "认证"]:
            self.assertIn(term, farp_text)

    def test_v06_table_of_contents_targets_real_sections(self):
        text = (ROOT / "docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.6.md").read_text(encoding="utf-8")
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

    def test_v06_json_examples_and_capability_vocabulary_are_machine_valid(self):
        text = (ROOT / "docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.6.md").read_text(encoding="utf-8")
        json_blocks = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
        self.assertGreaterEqual(len(json_blocks), 30)
        for index, block in enumerate(json_blocks, 1):
            try:
                json.loads(block)
            except json.JSONDecodeError as exc:
                self.fail(f"v0.6 JSON example {index} is invalid: {exc}")

        capability_section = re.search(r"^## 34\..*?\n(.*?)^## 35\.", text, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(capability_section)
        capability_block = re.search(r"```text\n(.*?)\n```", capability_section.group(1), re.DOTALL)
        self.assertIsNotNone(capability_block)
        documented = {item.strip() for item in capability_block.group(1).splitlines() if item.strip()}
        registry = json.loads((ROOT / "protocol/capabilities.json").read_text(encoding="utf-8"))
        registered = {item["id"] for item in registry["capabilities"]}
        self.assertEqual(registered, documented)

    def test_valid_v06_flow_passes_and_can_be_certified(self):
        base = load_base_implementation(ROOT)
        manifest = v06_manifest()
        flow = v06_flow()
        contract = build_v06_flow_contract_report(flow, manifest)
        self.assertTrue(contract["ok"], contract["findings"])

        compatibility = build_compatibility_report(base, manifest, flow, ROOT)
        self.assertTrue(compatibility["ok"], compatibility["findings"])
        self.assertEqual("CARTRIDGEFLOW-BASE@0.2", compatibility["base_contract"]["required"])

        certification = build_protocol_certification_report(base, manifest, flow, ROOT)
        self.assertTrue(certification["ok"], certification["findings"])
        self.assertEqual("cf-farp-0-6-certified", certification["label"])

    def test_v06_rejects_local_endpoint_and_requires_resource_role(self):
        tools = [{"id": "lookup", "type": "mcp", "server": "docs", "tool": "search"}]
        states = {
            "start": {"type": "system", "next": "lookup"},
            "lookup": {
                "type": "process",
                "kind": "remote_call",
                "executor": "remote",
                "effect": "read_only",
                "allowed_tools": ["lookup"],
                "endpoint": "https://local.example.invalid",
                "timeout_ms": 1000,
                "failure_policy": "fail_closed",
                "output": "result",
                "next": "complete",
            },
            "complete": {"type": "terminal"},
        }
        report = build_v06_flow_contract_report(v06_flow(states), v06_manifest(mcp_tools=tools))
        codes = {item["code"] for item in report["findings"]}
        self.assertIn("v06_remote_resource_role_missing", codes)
        self.assertIn("v06_local_binding_forbidden", codes)

    def test_portable_dlc_protocol_tracks_v06_runtime(self):
        with PortableDlcFixture() as fixture:
            fixture.manifest["runtime_contract"]["protocol_version"] = "0.6"
            fixture.manifest["portable_dlc"]["protocol"] = "CF-FARP@0.6"
            descriptor = load_portable_dlc_descriptor(fixture.package, fixture.manifest)
            self.assertEqual("CF-FARP@0.6", descriptor["_protocol"])

    def test_recognized_old_protocol_reports_migration_and_cannot_activate_dlc(self):
        manifest = v06_manifest()
        manifest["base_contract"] = {"id": "CF-FARP", "version": "0.5"}
        manifest["runtime_contract"]["protocol_version"] = "0.5"
        flow = v06_flow()
        flow["protocol"]["version"] = "0.5"
        report = build_compatibility_report(load_base_implementation(ROOT), manifest, flow, ROOT)
        self.assertFalse(report["ok"])
        self.assertEqual("recognized", report["protocol"]["lifecycle"])
        self.assertEqual({"id": "CF-FARP", "version": "0.6"}, report["protocol"]["migration_target"])
        self.assertIn("recognized_unsupported_protocol", [item["code"] for item in report["findings"]])

        with PortableDlcFixture() as fixture:
            fixture.manifest["runtime_contract"]["protocol_version"] = "0.5"
            fixture.manifest["portable_dlc"]["protocol"] = "CF-FARP@0.5"
            with self.assertRaises(PortableDlcValidationError):
                load_portable_dlc_descriptor(fixture.package, fixture.manifest)


if __name__ == "__main__":
    unittest.main()
