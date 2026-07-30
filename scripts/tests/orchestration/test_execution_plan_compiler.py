from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.orchestration import ExecutionPlanCompileError, compile_execution_plan


def comprehensive_flow() -> dict:
    return {
        "protocol": {"id": "CF-FARP", "version": "1.0"},
        "states": {
            "start": {"type": "control"},
            "left": {"type": "control"},
            "right": {"type": "control"},
            "all_done": {"type": "control"},
            "loop_gate": {"type": "control"},
            "loop_body": {"type": "control"},
            "batch_source": {"type": "control"},
            "wait_source": {"type": "control"},
            "complete": {"type": "terminal"},
            "timed_out": {"type": "terminal"},
            "any_left": {"type": "control"},
            "any_right": {"type": "control"},
            "any_done": {"type": "terminal"},
            "keyed_left": {"type": "control"},
            "keyed_right": {"type": "control"},
            "keyed_done": {"type": "terminal"},
        },
        "execution_plan": {
            "schema": "cartridgeflow.execution_plan.v1",
            "entry": "start",
            "edges": [
                {"id": "start_left", "kind": "fork", "from": "start", "to": "left", "fork": {"id": "prepare", "branch": "left"}},
                {"id": "start_right", "kind": "fork", "from": "start", "to": "right", "fork": {"id": "prepare", "branch": "right"}},
                {"id": "left_all", "kind": "join", "from": "left", "to": "all_done", "join": {"id": "all_assets", "mode": "all", "branch": "left", "branches": ["right", "left"]}},
                {"id": "right_all", "kind": "join", "from": "right", "to": "all_done", "join": {"id": "all_assets", "mode": "all", "branch": "right", "branches": ["right", "left"]}},
                {"id": "all_loop", "kind": "sequence", "from": "all_done", "to": "loop_gate"},
                {"id": "loop_body", "kind": "loop", "from": "loop_gate", "to": "loop_body", "loop": {"id": "retry", "max_iterations": 3, "continue_when": "$loop.retry", "exit_to": "batch_source"}},
                {"id": "body_gate", "kind": "sequence", "from": "loop_body", "to": "loop_gate"},
                {"id": "batch_wait", "kind": "batch", "from": "batch_source", "to": "wait_source", "batch": {"id": "files", "items_ref": "$files.items", "size": 10, "max_concurrency": 3, "ordering": "preserve"}},
                {"id": "wait_complete", "kind": "wait", "from": "wait_source", "to": "complete", "wait": {"id": "approval", "mode": "signal", "signal": "approval.completed", "timeout_ms": 60000, "resume_key": "approval_response"}},
                {"id": "wait_timeout", "kind": "failure", "from": "wait_source", "to": "timed_out", "failure": {"id": "approval_timeout", "causes": ["timeout"]}},
                {"id": "any_left_done", "kind": "join", "from": "any_left", "to": "any_done", "join": {"id": "first_result", "mode": "any", "branch": "left", "branches": ["left", "right"], "remaining": "cancel"}},
                {"id": "any_right_done", "kind": "join", "from": "any_right", "to": "any_done", "join": {"id": "first_result", "mode": "any", "branch": "right", "branches": ["left", "right"], "remaining": "cancel"}},
                {"id": "keyed_left_done", "kind": "join", "from": "keyed_left", "to": "keyed_done", "join": {"id": "by_item", "mode": "keyed", "branch": "left", "branches": ["right", "left"], "key_ref": "$item.id"}},
                {"id": "keyed_right_done", "kind": "join", "from": "keyed_right", "to": "keyed_done", "join": {"id": "by_item", "mode": "keyed", "branch": "right", "branches": ["right", "left"], "key_ref": "$item.id"}},
            ],
        },
    }


class CallableAction(str):
    calls = 0

    def __call__(self):
        type(self).calls += 1
        raise AssertionError("node execution is forbidden during compilation")


class ExecutionPlanCompilerTests(unittest.TestCase):
    def test_compiles_every_v1_relation_with_stable_identity_and_digests(self):
        plan = compile_execution_plan(comprehensive_flow())

        self.assertEqual("cartridgeflow.execution_plan.compiled.v1", plan["schema"])
        self.assertEqual("start", plan["entry"])
        self.assertTrue(plan["source_digest"].startswith("sha256:"))
        self.assertTrue(plan["plan_digest"].startswith("sha256:"))
        self.assertEqual(
            {"sequence", "fork", "join", "loop", "batch", "wait", "failure"},
            {edge["kind"] for edge in plan["edges"]},
        )
        self.assertEqual(sorted(edge["id"] for edge in plan["edges"]), [edge["id"] for edge in plan["edges"]])
        self.assertEqual(sorted(node["id"] for node in plan["nodes"]), [node["id"] for node in plan["nodes"]])
        edges_by_id = {edge["id"]: edge for edge in plan["edges"]}
        self.assertEqual(["left", "right"], edges_by_id["left_all"]["join"]["branches"])
        self.assertEqual("batch_source", next(item for item in plan["schedule"]["loops"] if item["edge_id"] == "loop_body")["loop"]["exit_to"])
        self.assertEqual(["wait_timeout"], plan["schedule"]["waits"][0]["timeout_failure_edge_ids"])
        self.assertEqual({"all", "any", "keyed"}, {join["mode"] for join in plan["schedule"]["joins"]})
        json.dumps(plan, ensure_ascii=False, sort_keys=True)

    def test_equivalent_author_fact_order_produces_the_same_bound_plan(self):
        first = compile_execution_plan(comprehensive_flow())
        reordered = comprehensive_flow()
        reordered["states"] = dict(reversed(list(reordered["states"].items())))
        reordered["execution_plan"]["edges"].reverse()
        for edge in reordered["execution_plan"]["edges"]:
            if isinstance(edge.get("join"), dict):
                edge["join"]["branches"].reverse()
        second = compile_execution_plan(reordered)

        self.assertEqual(first["source_digest"], second["source_digest"])
        self.assertEqual(first, second)

    def test_invalid_contract_has_a_stable_machine_readable_compile_error(self):
        invalid = comprehensive_flow()
        invalid["execution_plan"]["edges"].append(
            {"id": "start_extra", "kind": "sequence", "from": "start", "to": "complete"}
        )

        with self.assertRaises(ExecutionPlanCompileError) as first:
            compile_execution_plan(invalid)
        with self.assertRaises(ExecutionPlanCompileError) as second:
            compile_execution_plan(copy.deepcopy(invalid))

        self.assertEqual("execution_plan_contract_invalid", first.exception.code)
        self.assertEqual(first.exception.as_dict(), second.exception.as_dict())
        self.assertIn(
            "v10_fork_mixed_outgoing_forbidden",
            {finding["code"] for finding in first.exception.findings},
        )

    def test_compilation_does_not_execute_nodes_or_perform_io(self):
        CallableAction.calls = 0
        flow = comprehensive_flow()
        flow["states"]["start"] = {"type": "process", "action": CallableAction("forbidden")}
        flow["states"]["start_failed"] = {"type": "terminal"}
        flow["execution_plan"]["edges"].append(
            {"id": "start_failure", "kind": "failure", "from": "start", "to": "start_failed", "failure": {"id": "start_exception", "causes": ["exception"]}}
        )
        before = copy.deepcopy(flow)

        with patch("builtins.open", side_effect=AssertionError("file access is forbidden")), patch.object(
            Path, "write_text", side_effect=AssertionError("runtime writes are forbidden")
        ), patch.object(
            subprocess, "run", side_effect=AssertionError("process execution is forbidden")
        ), patch.object(
            urllib.request, "urlopen", side_effect=AssertionError("network access is forbidden")
        ):
            plan = compile_execution_plan(flow)

        self.assertEqual(0, CallableAction.calls)
        self.assertEqual(before, flow)
        self.assertIn("start_failure", {edge["id"] for edge in plan["edges"]})

    def test_shared_store_facts_are_not_reinterpreted_as_plan_dataflow(self):
        flow = comprehensive_flow()
        flow["states"]["start"]["params"] = {
            "store": {"implicit_route": "shared-store-value"},
        }

        plan = compile_execution_plan(flow)

        self.assertNotIn("shared-store-value", json.dumps(plan, sort_keys=True))
        self.assertEqual(
            {"id", "type", "entry", "may_fail"},
            set(next(node for node in plan["nodes"] if node["id"] == "start")),
        )


if __name__ == "__main__":
    unittest.main()
