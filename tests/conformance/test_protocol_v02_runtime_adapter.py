import unittest
from pathlib import Path

from core.lab.node_executor import LabNodeExecutor


ROOT = Path(__file__).resolve().parents[2]


class ProtocolV02RuntimeAdapterTest(unittest.TestCase):
    def test_v02_input_process_maps_to_collect_inputs(self):
        state_doc = {"context": {"store": {}}}
        run = {"inputs": {"episode_id": "ep_001", "goal": "open with a chase"}}
        state = {
            "type": "process",
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

    def test_v02_transfer_process_maps_to_pass_result(self):
        state_doc = {"context": {"store": {"brief": {"episode_id": "ep_001"}}}}
        run = {"inputs": {}}
        state = {
            "type": "process",
            "kind": "transfer",
            "executor": "deterministic",
            "effect": "writes_store",
            "input": "brief",
            "output": "brief_copy",
        }
        result = LabNodeExecutor().execute("transfer", state, state_doc, run, ".")
        self.assertEqual("pass_result", result["action"])
        self.assertEqual({"episode_id": "ep_001"}, state_doc["context"]["store"]["brief_copy"])

    def test_v02_rules_decision_maps_to_custom_action(self):
        state_doc = {"context": {"store": {"brief": "episode brief"}}}
        run = {"inputs": {}}
        state = {
            "type": "process",
            "kind": "decision",
            "executor": "rules",
            "effect": "none",
            "input": "brief",
            "output": "decision",
        }
        result = LabNodeExecutor().execute("decide", state, state_doc, run, ".")
        self.assertEqual("custom_action", result["action"])
        self.assertIn("episode brief", state_doc["context"]["store"]["decision"])

    def test_v02_mcp_read_rejects_side_effecting_tool_at_runtime(self):
        state_doc = {"context": {"store": {}}}
        run = {
            "inputs": {},
            "mcp_tools": [
                {
                    "id": "write_note",
                    "type": "builtin",
                    "server": "filesystem",
                    "tool": "write_file",
                    "contract": {"side_effect": "writes_files"},
                }
            ],
        }
        state = {
            "type": "process",
            "kind": "mcp_read",
            "executor": "mcp",
            "effect": "read_only",
            "mcp_binding": {"mode": "read_only", "allowed_tools": ["write_note"]},
            "output": "read_result",
        }
        with self.assertRaisesRegex(RuntimeError, "side-effecting tool"):
            LabNodeExecutor(ROOT).execute("unsafe_read", state, state_doc, run, ".")

    def test_v02_mcp_execute_can_consume_tool_plan(self):
        target = ROOT / "temp" / "v02_tool_plan_runtime.txt"
        target.unlink(missing_ok=True)
        state_doc = {
            "context": {
                "store": {
                    "plan": {
                        "schema": "tool_plan.v1",
                        "tool_id": "write_note",
                        "params": {
                            "path": "temp/v02_tool_plan_runtime.txt",
                            "content": "v0.2 tool plan ok",
                        },
                        "expected_output": "write_result",
                        "failure_policy": "fail_closed",
                    }
                }
            }
        }
        run = {
            "inputs": {},
            "mcp_tools": [
                {
                    "id": "write_note",
                    "type": "builtin",
                    "server": "filesystem",
                    "tool": "write_file",
                    "required": True,
                    "contract": {"side_effect": "writes_files"},
                    "params_schema": {
                        "type": "object",
                        "required": ["path", "content"],
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                }
            ],
        }
        state = {
            "type": "process",
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
        try:
            result = LabNodeExecutor(ROOT).execute("write_note", state, state_doc, run, ".")
            self.assertEqual("tool_call", result["action"])
            self.assertTrue(target.is_file())
            self.assertEqual("v0.2 tool plan ok", target.read_text(encoding="utf-8"))
            self.assertIn("write_result", state_doc["context"]["store"])
        finally:
            target.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
