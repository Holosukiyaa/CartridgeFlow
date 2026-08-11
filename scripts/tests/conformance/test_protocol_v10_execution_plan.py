import json
import unittest
from copy import deepcopy
from pathlib import Path

from core.protocol import (
    ProtocolRegistry,
    build_compatibility_report,
    load_base_implementation,
    load_protocol_artifact_json,
    load_protocol_artifact_text,
    load_protocol_release_catalog,
)
from core.protocol.flow_contract import build_v10_flow_contract_report, validate_v10_flow_contract


ROOT = Path(__file__).resolve().parents[3]
RELEASE_DIR = "flow-authoring/1.0"
DOCUMENT = f"{RELEASE_DIR}/README.md"


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


def codes(root_flow):
    return {finding["code"] for finding in validate_v10_flow_contract(root_flow)}


class ProtocolV10ExecutionPlanTests(unittest.TestCase):
    def assert_valid(self, root_flow):
        report = build_v10_flow_contract_report(root_flow)
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual("compatible", report["status"])
        self.assertEqual("supported", report["implementation_status"])

    def test_registry_is_current_and_base_supports_execution(self):
        catalog = load_protocol_release_catalog(ROOT)
        release = catalog.get("CF-FARP", "1.0")
        self.assertEqual("supported_previous", release["lifecycle"])
        self.assertEqual("active", release["status"])
        self.assertEqual("supported", release["implementation_status"])
        self.assertEqual({"id": "CF-FARP", "version": "1.1"}, catalog.data["default_for_new_flows"])

        registry = ProtocolRegistry(ROOT)
        self.assertTrue(registry.recognizes_protocol("CF-FARP", "1.0"))
        self.assertTrue(registry.supports_protocol("CF-FARP", "1.0"))
        base = load_base_implementation(ROOT)
        self.assertIn(("CF-FARP", "1.0"), {(item["id"], item["version"]) for item in base["supported_protocols"]})

        report = build_compatibility_report(
            base,
            {
                "base_contract": base["base_contract"],
                "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "1.0"},
                "delivery_readiness": {"level": "dev"},
            },
            flow(
                {"start": {"type": "control"}, "done": {"type": "terminal"}},
                [{"id": "start_done", "kind": "sequence", "from": "start", "to": "done"}],
            ),
            project_root=ROOT,
        )
        self.assertTrue(report["ok"], report["findings"])

    def test_sequence_has_positive_and_negative_conformance(self):
        valid = flow(
            {"start": {"type": "control"}, "done": {"type": "terminal"}},
            [{"id": "start_done", "kind": "sequence", "from": "start", "to": "done"}],
        )
        self.assert_valid(valid)
        invalid = deepcopy(valid)
        invalid["execution_plan"]["edges"].append({"id": "start_other", "kind": "sequence", "from": "start", "to": "done"})
        self.assertIn("v10_ambiguous_successor_forbidden", codes(invalid))

    def test_fork_has_positive_and_negative_conformance(self):
        valid = flow(
            {"split": {"type": "control"}, "left": {"type": "terminal"}, "right": {"type": "terminal"}},
            [
                {"id": "split_left", "kind": "fork", "from": "split", "to": "left", "fork": {"id": "parallel", "branch": "left"}},
                {"id": "split_right", "kind": "fork", "from": "split", "to": "right", "fork": {"id": "parallel", "branch": "right"}},
            ],
        )
        self.assert_valid(valid)
        invalid = deepcopy(valid)
        invalid["execution_plan"]["edges"].pop()
        self.assertIn("v10_fork_group_invalid", codes(invalid))

    def test_all_join_has_positive_and_negative_conformance(self):
        valid = self._join_flow("all")
        self.assert_valid(valid)
        invalid = deepcopy(valid)
        invalid["execution_plan"]["edges"][0]["join"]["branches"] = ["left"]
        self.assertIn("v10_join_group_invalid", codes(invalid))

    def test_any_join_has_positive_and_negative_conformance(self):
        valid = self._join_flow("any", remaining="cancel")
        self.assert_valid(valid)
        invalid = deepcopy(valid)
        for edge in invalid["execution_plan"]["edges"]:
            edge["join"].pop("remaining")
        self.assertIn("v10_any_join_remaining_policy_missing", codes(invalid))

    def test_keyed_join_has_positive_and_negative_conformance(self):
        valid = self._join_flow("keyed", key_ref="$item.id")
        self.assert_valid(valid)
        invalid = deepcopy(valid)
        invalid["execution_plan"]["edges"][1]["join"]["key_ref"] = "$item.other_id"
        self.assertIn("v10_keyed_join_key_inconsistent", codes(invalid))

    def test_loop_has_positive_and_negative_conformance(self):
        valid = flow(
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
        )
        self.assert_valid(valid)
        invalid = deepcopy(valid)
        invalid["execution_plan"]["edges"][1]["loop"]["max_iterations"] = 0
        self.assertIn("v10_loop_contract_invalid", codes(invalid))

    def test_batch_has_positive_and_negative_conformance(self):
        valid = flow(
            {"files": {"type": "control"}, "render": {"type": "control"}},
            [{"id": "files_render", "kind": "batch", "from": "files", "to": "render", "batch": {"id": "render_files", "items_ref": "$files.items", "size": 10, "max_concurrency": 3, "ordering": "preserve"}}],
        )
        self.assert_valid(valid)
        invalid = deepcopy(valid)
        invalid["execution_plan"]["edges"][0]["batch"]["size"] = 0
        self.assertIn("v10_batch_contract_invalid", codes(invalid))

    def test_wait_has_positive_and_negative_conformance(self):
        valid = flow(
            {"request": {"type": "control"}, "approved": {"type": "terminal"}, "timeout": {"type": "terminal"}},
            [
                {"id": "await_approval", "kind": "wait", "from": "request", "to": "approved", "wait": {"id": "approval", "mode": "signal", "signal": "approval.completed", "timeout_ms": 60000, "resume_key": "approval_response"}},
                {"id": "approval_timeout", "kind": "failure", "from": "request", "to": "timeout", "failure": {"id": "approval_failed", "causes": ["timeout"]}},
            ],
        )
        self.assert_valid(valid)
        invalid = deepcopy(valid)
        invalid["execution_plan"]["edges"].pop()
        self.assertIn("v10_wait_timeout_failure_missing", codes(invalid))

    def test_failure_has_positive_and_negative_conformance(self):
        valid = flow(
            {"render": {"type": "process", "effect": "read_only"}, "failed": {"type": "terminal"}},
            [{"id": "render_failed", "kind": "failure", "from": "render", "to": "failed", "failure": {"id": "render_exception", "causes": ["exception"]}}],
        )
        self.assert_valid(valid)
        invalid = deepcopy(valid)
        invalid["execution_plan"]["edges"] = []
        self.assertIn("v10_failure_exit_missing", codes(invalid))

    def test_implicit_join_unbounded_loop_legacy_route_and_visible_edge_are_rejected(self):
        implicit_join = flow(
            {"a": {"type": "control"}, "b": {"type": "control"}, "merge": {"type": "terminal"}},
            [
                {"id": "a_merge", "kind": "sequence", "from": "a", "to": "merge"},
                {"id": "b_merge", "kind": "sequence", "from": "b", "to": "merge"},
            ],
        )
        self.assertIn("v10_implicit_join_forbidden", codes(implicit_join))

        unbounded_loop = flow(
            {"gate": {"type": "control"}, "body": {"type": "control"}, "done": {"type": "terminal"}},
            [
                {"id": "gate_body", "kind": "loop", "from": "gate", "to": "body", "loop": {"id": "bad", "max_iterations": 0, "continue_when": "$again", "exit_to": "done"}},
                {"id": "body_gate", "kind": "sequence", "from": "body", "to": "gate"},
            ],
        )
        self.assertIn("v10_loop_contract_invalid", codes(unbounded_loop))

        legacy_route = flow(
            {"start": {"type": "control", "action_routes": {"approve": "done"}}, "done": {"type": "terminal"}},
            [{"id": "start_done", "kind": "sequence", "from": "start", "to": "done"}],
        )
        self.assertIn("v10_legacy_action_route_forbidden", codes(legacy_route))

        legacy_control_edge = flow(
            {"start": {"type": "control"}, "done": {"type": "terminal"}},
            [{"id": "start_done", "kind": "sequence", "from": "start", "to": "done"}],
        )
        legacy_control_edge["control_edges"] = [{"kind": "action_route", "from": "start", "to": "done"}]
        self.assertIn("v10_legacy_action_route_forbidden", codes(legacy_control_edge))

        visible_edge = flow(
            {"start": {"type": "control"}, "done": {"type": "terminal"}},
            [{"id": "not_real", "kind": "sequence", "from": "start", "to": "done", "executable": False}],
        )
        self.assertIn("v10_visible_non_executable_edge", codes(visible_edge))

    @unittest.skipIf(
        load_base_implementation(ROOT)["protocol_generation"]["id"] == "clean-v1",
        "CF-FARP@1.0 source snapshots are historical after the clean-v1 cutover",
    )
    def test_registry_document_and_vocabulary_are_current_and_standalone(self):
        registry_data = load_protocol_artifact_json(f"{RELEASE_DIR}/release.json")
        self.assertEqual("active", registry_data["status"])
        self.assertEqual("supported", registry_data["implementation_status"])
        self.assertEqual({"id": "CF-FARP", "version": "0.9"}, registry_data["supersedes"])
        document = load_protocol_artifact_text(DOCUMENT)
        self.assertIn("execution-plan.md", document)
        self.assertIn("完整规范发布单元", document)
        execution_plan = load_protocol_artifact_text(f"{RELEASE_DIR}/execution-plan.md")
        self.assertIn("执行计划是唯一控制事实", execution_plan)
        capabilities = load_protocol_artifact_json(f"{RELEASE_DIR}/capabilities.json")
        self.assertIn("execution_plan_failure_contract", {item["id"] for item in capabilities["capabilities"]})
        self.assertIn("execution_plan_runtime", {item["profile"] for item in capabilities["capabilities"]})

    @staticmethod
    def _join_flow(mode, *, remaining=None, key_ref=None):
        join = {"id": "merge", "mode": mode, "branches": ["left", "right"]}
        if remaining:
            join["remaining"] = remaining
        if key_ref:
            join["key_ref"] = key_ref
        left = deepcopy(join)
        left["branch"] = "left"
        right = deepcopy(join)
        right["branch"] = "right"
        return flow(
            {"left": {"type": "control"}, "right": {"type": "control"}, "done": {"type": "terminal"}},
            [
                {"id": "left_done", "kind": "join", "from": "left", "to": "done", "join": left},
                {"id": "right_done", "kind": "join", "from": "right", "to": "done", "join": right},
            ],
        )


if __name__ == "__main__":
    unittest.main()
