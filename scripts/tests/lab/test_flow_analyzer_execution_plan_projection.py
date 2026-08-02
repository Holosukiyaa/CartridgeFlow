import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.lab.flow_analyzer import analyze_flow, build_authoring_readiness


def flow(states, edges):
    return {
        "protocol": {"id": "CF-FARP", "version": "1.0"},
        "states": states,
        "execution_plan": {
            "schema": "cartridgeflow.execution_plan.v1",
            "entry": next(iter(states)),
            "edges": edges,
        },
    }


class FlowAnalyzerExecutionPlanProjectionTests(unittest.TestCase):
    def test_readiness_combines_input_contract_and_local_model_binding_blockers(self):
        manifest = {
            "id": "dev.readiness",
            "inputs": [{"id": "title", "label": "标题", "type": "text", "required": True}],
        }
        root_flow = {"states": {
            "collect": {
                "type": "process",
                "action": "collect_inputs",
                "input_kind": "initial",
                "params": {"preset": "user_form", "fields": ["brief"]},
            },
        }}
        model_report = {
            "status": "blocked",
            "items": [{
                "id": "node:generate",
                "node_id": "generate",
                "status": "blocked",
                "message": "AI decision node generate has no explicit model connection binding",
            }],
        }

        with patch("core.llm.config_manager.build_model_binding_report", return_value=model_report):
            report = build_authoring_readiness(manifest, root_flow, {"findings": [], "source_digest": "sha256:test"})

        self.assertFalse(report["can_run"])
        self.assertEqual(2, report["summary"]["blockers"])
        self.assertEqual(
            {"RUN_INPUT_CONTRACT_MISMATCH", "MODEL_BINDING_REQUIRED"},
            {item["code"] for item in report["items"]},
        )
        self.assertEqual("“AI 节点”尚未选择执行模型", next(item for item in report["items"] if item["area"] == "models")["message"])

    def test_readiness_hides_node_model_blocker_when_flow_role_is_the_root_cause(self):
        manifest = {"id": "dev.readiness", "inputs": []}
        root_flow = {"states": {"generate": {"display_name": "生成摘要", "model_role": "runtime"}}}
        model_report = {
            "status": "blocked",
            "items": [
                {"id": "runtime", "status": "blocked", "message": "当前卡带尚未显式绑定模型角色：runtime"},
                {"id": "node:generate", "node_id": "generate", "model_role": "runtime", "status": "blocked", "message": "模型角色 runtime 尚未就绪"},
            ],
        }

        with patch("core.llm.config_manager.build_model_binding_report", return_value=model_report):
            report = build_authoring_readiness(manifest, root_flow, {"findings": []})

        self.assertEqual(1, report["summary"]["blockers"])
        self.assertEqual("当前流程还没有可用的执行模型", report["items"][0]["message"])

    @patch("core.llm.config_manager.build_model_binding_report", return_value={"status": "ok", "items": []})
    def test_readiness_combines_fields_from_multiple_input_nodes(self, _model_report):
        manifest = {
            "id": "dev.readiness",
            "inputs": [{"id": "brief"}, {"id": "audience"}],
        }
        root_flow = {"states": {
            "collect_brief": {"action": "collect_inputs", "params": {"preset": "user_form", "fields": ["brief"]}},
            "collect_audience": {"action": "collect_inputs", "params": {"preset": "user_form", "fields": ["audience"]}},
        }}

        report = build_authoring_readiness(manifest, root_flow, {"findings": []})

        self.assertTrue(report["can_run"])
        self.assertEqual([], report["items"])

    @patch("core.llm.config_manager.build_model_binding_report", return_value={"status": "ok", "items": []})
    def test_readiness_blocks_an_unavailable_inline_tool(self, _model_report):
        root_flow = {"states": {"fetch": {
            "type": "process",
            "title": "读取资料",
            "action": "tool_call",
            "tools": [{"server": "missing", "tool": "fetch", "enabled": True}],
        }}}

        report = build_authoring_readiness(
            {"id": "dev.readiness", "inputs": []},
            root_flow,
            {"findings": []},
            {"tools": [], "findings": []},
        )

        self.assertFalse(report["can_run"])
        self.assertEqual("TOOL_RESOURCE_UNAVAILABLE", report["items"][0]["code"])
        self.assertEqual("tools", report["items"][0]["action"]["target"])

    @patch("core.llm.config_manager.build_model_binding_report", return_value={"status": "ok", "items": []})
    def test_readiness_accepts_an_available_builtin_inline_tool(self, _model_report):
        root_flow = {"states": {"read": {
            "type": "process",
            "action": "tool_call",
            "tools": [{"server": "filesystem", "tool": "read_file", "enabled": True}],
        }}}
        catalog = {"tools": [{
            "server": "filesystem",
            "tool": "read_file",
            "source": "base_builtin",
            "status": "available",
        }], "findings": []}

        report = build_authoring_readiness(
            {"id": "dev.readiness", "inputs": []}, root_flow, {"findings": []}, catalog,
        )

        self.assertTrue(report["can_run"])

    def test_compiled_visual_relations_keep_the_plan_edge_identity(self):
        report = analyze_flow(flow(
            {
                "start": {"type": "control"},
                "gate": {"type": "control"},
                "body": {"type": "control"},
                "done": {"type": "terminal"},
            },
            [
                {"id": "start_gate", "kind": "sequence", "from": "start", "to": "gate"},
                {"id": "gate_body", "kind": "loop", "from": "gate", "to": "body", "loop": {"id": "retry", "max_iterations": 3, "continue_when": "$gate.retry", "exit_to": "done"}},
                {"id": "body_gate", "kind": "sequence", "from": "body", "to": "gate"},
            ],
        ))

        self.assertEqual("compiled", report["execution_plan"]["status"])
        self.assertFalse(report["summary"]["runnable"])
        self.assertFalse(report["summary"]["packagable"])
        self.assertFalse(report["summary"]["publishable"])
        self.assertEqual("unsupported", report["execution_plan"]["runtime_status"])
        self.assertIn("v10_base_runtime_unsupported", {item["code"] for item in report["findings"]})
        self.assertTrue(all(item["kind"] == "execution_plan_edge" for item in report["relations"]))
        self.assertTrue(all(item["runtime_effect"] and item["executable"] for item in report["relations"]))
        self.assertTrue(all(item["plan_edge_id"] for item in report["relations"]))

        loop_relations = [item for item in report["relations"] if item["plan_edge_id"] == "gate_body"]
        self.assertEqual({"body", "done"}, {item["to"]["node_id"] for item in loop_relations})
        self.assertEqual({"transition", "loop_exit"}, {item["plan_transition"] for item in loop_relations})

    def test_base_runtime_declaration_is_required_to_open_execution_gates(self):
        report = analyze_flow(
            flow(
                {"start": {"type": "control"}, "done": {"type": "terminal"}},
                [{"id": "start_done", "kind": "sequence", "from": "start", "to": "done"}],
            ),
            target="publish",
            base={"implementation_id": "test-base", "supported_protocols": [{"id": "CF-FARP", "version": "1.0", "status": "partial"}]},
        )

        self.assertEqual("compiled", report["execution_plan"]["status"])
        self.assertEqual("supported", report["execution_plan"]["runtime_status"])
        self.assertTrue(report["summary"]["runnable"])
        self.assertTrue(report["summary"]["packagable"])
        self.assertTrue(report["summary"]["publishable"])
        self.assertNotIn("v10_base_runtime_unsupported", {item["code"] for item in report["findings"]})

    def test_legacy_routes_and_implicit_join_are_chinese_diagnostics_not_runtime_relations(self):
        legacy = flow(
            {
                "start": {"type": "control", "action_routes": {"approve": "done"}, "failure_route": "done"},
                "done": {"type": "terminal"},
            },
            [{"id": "start_done", "kind": "sequence", "from": "start", "to": "done"}],
        )
        legacy_report = analyze_flow(legacy)
        legacy_codes = {item["code"] for item in legacy_report["findings"]}

        self.assertEqual("rejected", legacy_report["execution_plan"]["status"])
        self.assertEqual([], legacy_report["relations"])
        self.assertTrue({"v10_legacy_action_route_forbidden", "v10_legacy_failure_route_forbidden"} <= legacy_codes)
        self.assertTrue(all("旧" in item["message"] and "请" in item["message"] for item in legacy_report["findings"]))

        implicit_join = flow(
            {"a": {"type": "control"}, "b": {"type": "control"}, "merge": {"type": "terminal"}},
            [
                {"id": "a_merge", "kind": "sequence", "from": "a", "to": "merge"},
                {"id": "b_merge", "kind": "sequence", "from": "b", "to": "merge"},
            ],
        )
        join_report = analyze_flow(implicit_join)
        join_finding = next(item for item in join_report["findings"] if item["code"] == "v10_implicit_join_forbidden")

        self.assertEqual([], join_report["relations"])
        self.assertEqual("merge", join_finding["node_id"])
        self.assertIn("隐式合流", join_finding["message"])
        self.assertIn("join.id", join_finding["message"])


if __name__ == "__main__":
    unittest.main()
