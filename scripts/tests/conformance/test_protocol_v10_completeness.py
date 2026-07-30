import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOCUMENT = ROOT / "docs/protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v1.0.md"


def vocabulary(version: str, field: str) -> list[dict]:
    path = ROOT / f"protocol/vocabulary/{field}-{version}.json"
    return json.loads(path.read_text(encoding="utf-8"))[field]


class ProtocolV10CompletenessTests(unittest.TestCase):
    def test_v10_profiles_are_a_complete_superset_of_v08_and_v09(self):
        inherited = {
            item["id"]
            for version in ("0.8", "0.9")
            for item in vocabulary(version, "profiles")
        }
        current = {item["id"] for item in vocabulary("1.0", "profiles")}

        self.assertFalse(inherited - current)
        self.assertIn("execution_plan_runtime", current)

    def test_v10_capabilities_are_a_complete_superset_of_v08_and_v09(self):
        inherited = {
            item["id"]
            for version in ("0.8", "0.9")
            for item in vocabulary(version, "capabilities")
        }
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

        self.assertFalse(inherited - current)
        self.assertFalse(required_v10 - current)

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

    def test_v10_document_contains_all_three_self_contained_contract_layers(self):
        document = DOCUMENT.read_text(encoding="utf-8")
        for heading in (
            "第一部分：基础流程、运行、资源与交付合同",
            "第二部分：MCP/DLC 透明执行合同",
            "第三部分：显式执行计划与令牌运行合同",
            "## 5. 卡带包结构",
            "## 50. 统一 Flow 资源目录",
            "## 51. 执行计划是唯一控制事实",
            "## 56. 1.0 完成门槛",
        ):
            self.assertIn(heading, document)
        self.assertGreater(len(document.encode("utf-8")), 150_000)

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
