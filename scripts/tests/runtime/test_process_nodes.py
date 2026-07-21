import tempfile
import unittest
from pathlib import Path

from core.lab.node_executor import LabNodeExecutor
from core.protocol import build_v06_flow_contract_report


ROOT = Path(__file__).resolve().parents[3]


def current_manifest():
    return {
        "id": "test.process.nodes",
        "version": "1.0.0",
        "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
        "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.6"},
        "mcp_tools": [
            {
                "id": "read_note",
                "type": "builtin",
                "server": "filesystem",
                "tool": "read_file",
                "contract": {"side_effect": "read_only"},
            }
        ],
    }


def current_flow(decision_patch=None, extra_states=None):
    decision = {
        "type": "process",
        "kind": "decision",
        "executor": "llm",
        "effect": "none",
        "input": "brief",
        "output": "decision",
        "output_contract": "decision_envelope.v1",
        "decision_contract": {
            "schema": "decision_envelope.v1",
            "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
            "on_needs_user_input": "pause",
            "interaction": {
                "store_key": "decision_reply",
                "input_schema": "decision_reply.v1",
                "resume_policy": "resume_same_node",
            },
            "consume": {
                "mode": "payload_path",
                "path": "payload.decision",
                "as": "decision_payload",
                "required": True,
                "on_missing": "fail_closed",
            },
        },
        "next": "deliver",
    }
    if decision_patch:
        decision.update(decision_patch)
    states = {
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
            "next": "decide",
        },
        "decide": decision,
        "deliver": {
            "type": "process",
            "kind": "delivery",
            "executor": "deterministic",
            "effect": "writes_store",
            "input": "decision_payload",
            "output": "delivery",
            "primary_output": "delivery",
            "next": "complete",
        },
        "complete": {"type": "terminal"},
    }
    if extra_states:
        states.update(extra_states)
    return {
        "schema_version": "1.0",
        "id": "test.process.nodes.root",
        "protocol": {"id": "CF-FARP", "version": "0.6"},
        "start": "start",
        "states": states,
    }


class ProcessNodeContractTests(unittest.TestCase):
    def test_current_process_contract_accepts_v06_flow(self):
        report = build_v06_flow_contract_report(current_flow(), current_manifest())
        self.assertTrue(report["ok"], report["findings"])

    def test_process_kind_is_required(self):
        flow = current_flow()
        flow["states"]["decide"].pop("kind")
        report = build_v06_flow_contract_report(flow, current_manifest())
        self.assertFalse(report["ok"])
        self.assertIn("v02_process_kind_missing", [item["code"] for item in report["findings"]])

    def test_transfer_rejects_tool_binding(self):
        flow = current_flow(extra_states={
            "unsafe_transfer": {
                "type": "process",
                "kind": "transfer",
                "executor": "deterministic",
                "effect": "writes_store",
                "input": "brief",
                "output": "brief_copy",
                "tools": [{"type": "builtin", "server": "filesystem", "tool": "read_file"}],
            }
        })
        report = build_v06_flow_contract_report(flow, current_manifest())
        self.assertFalse(report["ok"])
        self.assertIn("v02_transfer_has_side_capability", [item["code"] for item in report["findings"]])

    def test_resolved_decision_requires_consume_contract(self):
        flow = current_flow({
            "decision_contract": {
                "schema": "decision_envelope.v1",
                "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
                "on_needs_user_input": "pause",
                "interaction": {
                    "store_key": "decision_reply",
                    "input_schema": "decision_reply.v1",
                    "resume_policy": "resume_same_node",
                },
            }
        })
        report = build_v06_flow_contract_report(flow, current_manifest())
        self.assertFalse(report["ok"])
        self.assertIn("v04_decision_consume_missing", [item["code"] for item in report["findings"]])


class ProcessNodeExecutionTests(unittest.TestCase):
    def test_input_process_collects_declared_inputs(self):
        state_doc = {"context": {"store": {}}}
        run = {"inputs": {"episode_id": "ep_001", "goal": "open with a chase"}}
        state = {
            "type": "process",
            "protocol_version": "0.6",
            "kind": "input",
            "executor": "user",
            "effect": "writes_store",
            "input_kind": "initial",
            "source": "user_form",
            "input_schema": {"fields": ["episode_id", "goal"]},
            "output": "brief",
        }
        result = LabNodeExecutor().execute("collect", state, state_doc, run, ".")
        self.assertEqual("collect_inputs", result["action"])
        self.assertEqual({"episode_id": "ep_001", "goal": "open with a chase"}, state_doc["context"]["store"]["brief"])

    def test_transfer_process_passes_result(self):
        state_doc = {"context": {"store": {"brief": {"episode_id": "ep_001"}}}}
        state = {
            "type": "process",
            "protocol_version": "0.6",
            "kind": "transfer",
            "executor": "deterministic",
            "effect": "writes_store",
            "input": "brief",
            "output": "brief_copy",
        }
        result = LabNodeExecutor().execute("transfer", state, state_doc, {"inputs": {}}, ".")
        self.assertEqual("pass_result", result["action"])
        self.assertEqual({"episode_id": "ep_001"}, state_doc["context"]["store"]["brief_copy"])

    def test_rules_decision_maps_to_custom_action(self):
        state_doc = {"context": {"store": {"brief": "episode brief"}}}
        state = {
            "type": "process",
            "protocol_version": "0.6",
            "kind": "decision",
            "executor": "rules",
            "effect": "none",
            "input": "brief",
            "output": "decision",
        }
        result = LabNodeExecutor().execute("decide", state, state_doc, {"inputs": {}}, ".")
        self.assertEqual("custom_action", result["action"])
        self.assertIn("episode brief", state_doc["context"]["store"]["decision"])

    def test_read_only_process_rejects_side_effecting_tool(self):
        state_doc = {"context": {"store": {}}}
        run = {
            "inputs": {},
            "mcp_tools": [{
                "id": "write_note",
                "type": "builtin",
                "server": "filesystem",
                "tool": "write_file",
                "contract": {"side_effect": "writes_files"},
            }],
        }
        state = {
            "type": "process",
            "protocol_version": "0.6",
            "kind": "mcp_read",
            "executor": "mcp",
            "effect": "read_only",
            "mcp_binding": {"mode": "read_only", "allowed_tools": ["write_note"]},
            "output": "read_result",
        }
        with self.assertRaisesRegex(RuntimeError, "side-effecting tool"):
            LabNodeExecutor(ROOT).execute("unsafe_read", state, state_doc, run, ".")

    def test_execute_process_consumes_tool_plan(self):
        with tempfile.TemporaryDirectory(prefix="cartridgeflow-tool-plan-") as temp_dir:
            workspace = Path(temp_dir)
            target = workspace / "tool_plan_runtime.txt"
            state_doc = {
                "context": {
                    "store": {
                        "plan": {
                            "schema": "tool_plan.v1",
                            "tool_id": "write_note",
                            "params": {"path": "tool_plan_runtime.txt", "content": "tool plan ok"},
                            "expected_output": "write_result",
                            "failure_policy": "fail_closed",
                        }
                    }
                }
            }
            run = {
                "inputs": {},
                "mcp_tools": [{
                    "id": "write_note",
                    "type": "builtin",
                    "server": "filesystem",
                    "tool": "write_file",
                    "required": True,
                    "contract": {"side_effect": "writes_files"},
                    "params_schema": {
                        "type": "object",
                        "required": ["path", "content"],
                        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    },
                }],
            }
            state = {
                "type": "process",
                "protocol_version": "0.6",
                "kind": "mcp_execute",
                "executor": "mcp",
                "effect": "writes_files",
                "tool_binding": "from_tool_plan",
                "allowed_tools": ["write_note"],
                "failure_policy": "fail_closed",
                "permission": "write_run_artifacts",
                "audit_log": True,
                "input": "plan",
                "output": "write_result",
            }
            result = LabNodeExecutor(workspace).execute("write_note", state, state_doc, run, workspace)
            self.assertEqual("tool_call", result["action"])
            self.assertTrue(target.is_file())
            self.assertEqual("tool plan ok", target.read_text(encoding="utf-8"))
            self.assertIn("write_result", state_doc["context"]["store"])


if __name__ == "__main__":
    unittest.main()
