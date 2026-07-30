import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.lab.flow_analyzer import analyze_flow


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
