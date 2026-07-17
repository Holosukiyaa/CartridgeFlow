import unittest

from core.protocol import build_v02_flow_contract_report


def manifest_with_tools():
    return {
        "id": "test.v02",
        "version": "0.0.1",
        "mcp_tools": [
            {
                "id": "knowledge_search",
                "type": "builtin",
                "server": "filesystem",
                "tool": "read_file",
                "contract": {"side_effect": "none"},
            },
            {
                "id": "render_episode",
                "type": "builtin",
                "server": "media",
                "tool": "render",
                "contract": {"side_effect": "writes_run_artifacts"},
            },
        ],
    }


def valid_flow(extra_states=None):
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
        "decide": {
            "type": "process",
            "kind": "decision",
            "executor": "llm",
            "effect": "none",
            "input": "brief",
            "output": "decision",
            "output_contract": "decision.v1",
            "next": "deliver",
        },
        "deliver": {
            "type": "process",
            "kind": "delivery",
            "executor": "deterministic",
            "effect": "writes_store",
            "input": "decision",
            "output": "episode_delivery",
            "next": "complete",
        },
        "complete": {"type": "terminal"},
    }
    if extra_states:
        states.update(extra_states)
    return {
        "schema_version": "1.0",
        "id": "test.v02.root",
        "protocol": {"id": "CF-FARP", "version": "0.2"},
        "start": "start",
        "states": states,
    }


class ProtocolV02FlowContractTest(unittest.TestCase):
    def test_valid_minimal_flow_passes(self):
        report = build_v02_flow_contract_report(valid_flow(), manifest_with_tools())
        self.assertTrue(report["ok"], report["findings"])

    def test_missing_kind_blocks(self):
        flow = valid_flow({
            "broken": {
                "type": "process",
                "executor": "llm",
                "effect": "none",
            }
        })
        report = build_v02_flow_contract_report(flow, manifest_with_tools())
        self.assertFalse(report["ok"])
        self.assertIn("v02_process_kind_missing", [item["code"] for item in report["findings"]])

    def test_legacy_business_type_blocks(self):
        flow = valid_flow({
            "legacy_ui": {"type": "ui", "action": "show_ui"}
        })
        report = build_v02_flow_contract_report(flow, manifest_with_tools())
        self.assertFalse(report["ok"])
        self.assertIn("v02_business_node_must_be_process", [item["code"] for item in report["findings"]])

    def test_transfer_must_not_bind_tools(self):
        flow = valid_flow({
            "transfer_with_tool": {
                "type": "process",
                "kind": "transfer",
                "executor": "deterministic",
                "effect": "writes_store",
                "tools": [{"type": "builtin", "server": "filesystem", "tool": "read_file"}],
            }
        })
        report = build_v02_flow_contract_report(flow, manifest_with_tools())
        self.assertFalse(report["ok"])
        self.assertIn("v02_transfer_has_side_capability", [item["code"] for item in report["findings"]])

    def test_mcp_read_rejects_side_effecting_tool(self):
        flow = valid_flow({
            "unsafe_read": {
                "type": "process",
                "kind": "mcp_read",
                "executor": "mcp",
                "effect": "read_only",
                "mcp_binding": {"mode": "read_only", "allowed_tools": ["render_episode"]},
                "output": "context_pack",
            }
        })
        report = build_v02_flow_contract_report(flow, manifest_with_tools())
        self.assertFalse(report["ok"])
        self.assertIn("v02_mcp_read_tool_has_side_effect", [item["code"] for item in report["findings"]])

    def test_mcp_execute_requires_allowed_tools(self):
        flow = valid_flow({
            "execute_without_allowlist": {
                "type": "process",
                "kind": "mcp_execute",
                "executor": "mcp",
                "effect": "writes_artifacts",
                "tool_binding": "static_params",
                "failure_policy": "fail_closed",
                "permission": "write_run_artifacts",
                "audit_log": True,
                "output": "render_bundle",
            }
        })
        report = build_v02_flow_contract_report(flow, manifest_with_tools())
        self.assertFalse(report["ok"])
        self.assertIn("v02_mcp_execute_allowed_tools_missing", [item["code"] for item in report["findings"]])

    def test_decision_must_not_execute_tools_directly(self):
        flow = valid_flow({
            "unsafe_decision": {
                "type": "process",
                "kind": "decision",
                "executor": "llm",
                "effect": "none",
                "action": "tool_call",
                "output": "decision",
            }
        })
        report = build_v02_flow_contract_report(flow, manifest_with_tools())
        self.assertFalse(report["ok"])
        self.assertIn("v02_decision_direct_side_effect", [item["code"] for item in report["findings"]])


if __name__ == "__main__":
    unittest.main()
