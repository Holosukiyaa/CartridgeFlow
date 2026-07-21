import unittest
from pathlib import Path

from core.protocol import (
    build_protocol_certification_report,
    build_v04_flow_contract_report,
    load_base_implementation,
)


ROOT = Path(__file__).resolve().parents[3]


def v04_manifest(required_capabilities=None):
    return {
        "id": "test.v04",
        "version": "0.0.1",
        "base_contract": {"id": "CF-FARP", "version": "0.4"},
        "runtime_contract": {
            "protocol": "CF-FARP",
            "protocol_version": "0.4",
            "required_profiles": ["runtime_core", "interactive_decision_runtime"],
            "recommended_profiles": [],
            "required_capabilities": required_capabilities or [
                "root_flow_execution",
                "unified_process_node",
                "process_node_kind_parse",
                "process_executor_contract",
                "process_effect_contract",
                "decision_process",
                "decision_envelope_v1",
                "decision_envelope_validate",
                "decision_consume_contract",
                "decision_consume_projection",
                "runtime_user_input_request",
                "paused_waiting_user_status",
                "pending_interaction_record",
            ],
            "optional_capabilities": [],
            "required_tools": [],
            "optional_tools": [],
        },
        "delivery_readiness": {"level": "dev"},
        "branding": {"tags": []},
        "mcp_tools": [],
    }


def v04_flow(decision_patch=None):
    decision = {
        "type": "process",
        "kind": "decision",
        "executor": "llm",
        "effect": "none",
        "input": "brief",
        "output": "story_decision",
        "output_contract": "decision_envelope.v1",
        "decision_contract": {
            "schema": "decision_envelope.v1",
            "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
            "on_needs_user_input": "pause",
            "interaction": {
                "store_key": "story_decision_reply",
                "input_schema": "story_decision_reply.v1",
                "resume_policy": "resume_same_node",
            },
            "consume": {
                "mode": "payload_path",
                "path": "payload.decision",
                "as": "story_decision_payload",
                "required": True,
                "on_missing": "fail_closed",
            },
        },
        "next": "deliver",
    }
    if decision_patch:
        decision.update(decision_patch)
    return {
        "schema_version": "1.0",
        "id": "test.v04.root",
        "protocol": {"id": "CF-FARP", "version": "0.4"},
        "start": "start",
        "states": {
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
                "input": "story_decision_payload",
                "output": "episode_delivery",
                "next": "complete",
            },
            "complete": {"type": "terminal"},
        },
    }


class ProtocolV04FlowContractTest(unittest.TestCase):
    def test_valid_decision_consume_flow_passes(self):
        report = build_v04_flow_contract_report(v04_flow(), v04_manifest())
        self.assertTrue(report["ok"], report["findings"])

    def test_llm_decision_with_resolved_requires_consume_contract(self):
        flow = v04_flow({
            "decision_contract": {
                "schema": "decision_envelope.v1",
                "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
                "on_needs_user_input": "pause",
                "interaction": {
                    "store_key": "reply",
                    "input_schema": "reply.v1",
                    "resume_policy": "resume_same_node",
                },
            }
        })
        report = build_v04_flow_contract_report(flow, v04_manifest())
        self.assertFalse(report["ok"])
        self.assertIn("v04_decision_consume_missing", [item["code"] for item in report["findings"]])

    def test_consume_as_must_not_overwrite_envelope_output(self):
        flow = v04_flow({
            "decision_contract": {
                "schema": "decision_envelope.v1",
                "allowed_statuses": ["resolved"],
                "consume": {
                    "mode": "payload_path",
                    "path": "payload.decision",
                    "as": "story_decision",
                },
            }
        })
        report = build_v04_flow_contract_report(flow, v04_manifest())
        self.assertFalse(report["ok"])
        self.assertIn("v04_decision_consume_as_overwrites_output", [item["code"] for item in report["findings"]])

    def test_certification_is_blocked_after_v04_runtime_support_removal(self):
        report = build_protocol_certification_report(load_base_implementation(ROOT), v04_manifest(), v04_flow(), ROOT)
        self.assertFalse(report["ok"])
        self.assertIn("compatibility_blocked", [item["code"] for item in report["findings"]])


if __name__ == "__main__":
    unittest.main()
