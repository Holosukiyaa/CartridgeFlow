import json
import re
import unittest
from pathlib import Path

from core.protocol import (
    load_base_implementation,
    load_protocol_artifact_json,
    load_protocol_artifact_text,
)


ROOT = Path(__file__).resolve().parents[3]
RELEASE_DIR = "flow-authoring/1.0"
DOCUMENT = f"{RELEASE_DIR}/README.md"


def vocabulary(version: str, field: str) -> list[dict]:
    return load_protocol_artifact_json(f"flow-authoring/{version}/{field}.json")[field]


class ProtocolV10CompletenessTests(unittest.TestCase):
    @unittest.skipIf(
        load_base_implementation(ROOT)["protocol_generation"]["id"] == "clean-v1",
        "CF-FARP@1.0 source snapshots are historical after the clean-v1 cutover",
    )
    def test_v10_profiles_are_declared_by_this_release(self):
        current = {item["id"] for item in vocabulary("1.0", "profiles")}

        self.assertTrue({"runtime_core", "flow_analysis", "tool_transparency"}.issubset(current))

    @unittest.skipIf(
        load_base_implementation(ROOT)["protocol_generation"]["id"] == "clean-v1",
        "CF-FARP@1.0 source snapshots are historical after the clean-v1 cutover",
    )
    def test_v10_capabilities_are_declared_by_this_release(self):
        current = {item["id"] for item in vocabulary("1.0", "capabilities")}
        required_v10 = {
            "execution_plan_v1_authoring",
            "execution_plan_static_conformance",
            "execution_plan_compile",
            "execution_plan_sequence_contract",
            "execution_plan_fork_contract",
            "execution_plan_join_all_contract",
            "execution_plan_join_any_contract",
            "execution_plan_join_keyed_contract",
            "execution_plan_loop_contract",
            "execution_plan_batch_contract",
            "execution_plan_wait_contract",
            "execution_plan_failure_contract",
            "execution_plan_token_ledger",
            "execution_plan_join_runtime",
            "execution_plan_wait_resume",
            "execution_plan_cancellation",
            "execution_plan_source_digest_guard",
        }

        self.assertFalse(required_v10 - current)

    @unittest.skipIf(
        load_base_implementation(ROOT)["protocol_generation"]["id"] == "clean-v1",
        "CF-FARP@1.0 source snapshots are historical after the clean-v1 cutover",
    )
    def test_every_base_declared_v10_capability_has_evidence(self):
        base = json.loads((ROOT / "config/base/BASE_IMPLEMENTATION.json").read_text(encoding="utf-8"))
        evidence = json.loads((ROOT / "config/base/capability_evidence.json").read_text(encoding="utf-8"))
        v10_capabilities = {item["id"] for item in vocabulary("1.0", "capabilities")}
        declared = set(base["capabilities"])
        missing = (declared & v10_capabilities) - set(evidence["capabilities"])

        self.assertFalse(missing, sorted(missing))
        for capability in declared & v10_capabilities:
            evidence_id = evidence["capabilities"][capability]
            record = evidence["evidence_sets"].get(evidence_id)
            self.assertIsInstance(record, dict, capability)
            self.assertTrue(record.get("implementation"), capability)

    @unittest.skipIf(
        load_base_implementation(ROOT)["protocol_generation"]["id"] == "clean-v1",
        "CF-FARP@1.0 source snapshots are historical after the clean-v1 cutover",
    )
    def test_v10_documentation_is_modular_and_self_contained(self):
        document = load_protocol_artifact_text(DOCUMENT)
        modules = {
            "overview.md": "协议目标",
            "package-and-resources.md": "Manifest 契约",
            "flow-and-data.md": "Root Flow",
            "runtime-and-recovery.md": "Run 与节点状态",
            "extensions-and-lifecycle.md": "Portable DLC",
            "authoring-and-analysis.md": "Authoring facts",
            "tool-transparency.md": "MCP/DLC 透明执行原则",
            "execution-plan.md": "执行计划是唯一控制事实",
            "conformance.md": "Conformance requirements",
        }
        for filename, marker in modules.items():
            self.assertIn(filename, document)
            text = load_protocol_artifact_text(f"{RELEASE_DIR}/{filename}")
            self.assertIn(marker, text)
            self.assertLess(len(text.encode("utf-8")), 40_000)
            self.assertIsNone(re.search(r"v0\\.\\d", text), filename)

        self.assertIn("非规范迁移资料", document)
        migration = load_protocol_artifact_text(f"{RELEASE_DIR}/migration.md")
        self.assertIn("non-normative", migration)

    def test_v10_analyzer_applies_the_transparency_gate(self):
        from core.lab.flow_analyzer import analyze_flow

        report = analyze_flow(
            {
                "protocol": {"id": "CF-FARP", "version": "1.0"},
                "states": {"start": {"type": "control"}, "done": {"type": "terminal"}},
                "execution_plan": {
                    "schema": "cartridgeflow.execution_plan.v1",
                    "entry": "start",
                    "edges": [{"id": "start_done", "kind": "sequence", "from": "start", "to": "done"}],
                },
            },
            {
                "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "1.0", "required_profiles": []},
                "mcp_tools": [{"id": "external", "type": "remote_mcp", "transparency": "declared_graph"}],
            },
            base={"supported_protocols": [{"id": "CF-FARP", "version": "1.0", "status": "supported"}]},
        )
        codes = {finding["code"] for finding in report["findings"]}
        self.assertIn("TOOL_TRANSPARENCY_PROFILE_MISSING", codes)
        self.assertIn("REMOTE_MCP_TRANSPARENCY_INVALID", codes)


if __name__ == "__main__":
    unittest.main()
