import unittest
from pathlib import Path

from core.protocol import (
    build_compatibility_report,
    build_protocol_certification_report,
    build_v03_flow_contract_report,
    load_base_implementation,
)


ROOT = Path(__file__).resolve().parents[2]


def v03_manifest(required_capabilities=None):
    return {
        "id": "test.v03",
        "version": "0.0.1",
        "base_contract": {"id": "CF-FARP", "version": "0.3"},
        "runtime_contract": {
            "protocol": "CF-FARP",
            "protocol_version": "0.3",
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


def v03_flow(decision_patch=None):
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
        },
        "next": "deliver",
    }
    if decision_patch:
        decision.update(decision_patch)
    return {
        "schema_version": "1.0",
        "id": "test.v03.root",
        "protocol": {"id": "CF-FARP", "version": "0.3"},
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
                "input": "story_decision",
                "output": "episode_delivery",
                "next": "complete",
            },
            "complete": {"type": "terminal"},
        },
    }


class ProtocolV03FlowContractTest(unittest.TestCase):
    def test_valid_interactive_decision_flow_passes(self):
        report = build_v03_flow_contract_report(v03_flow(), v03_manifest())
        self.assertTrue(report["ok"], report["findings"])

    def test_llm_decision_requires_decision_envelope_contract(self):
        report = build_v03_flow_contract_report(v03_flow({"output_contract": "decision.v1"}), v03_manifest())
        self.assertFalse(report["ok"])
        self.assertIn("v03_decision_envelope_contract_missing", [item["code"] for item in report["findings"]])

    def test_llm_decision_requires_interaction_contract_when_it_can_ask_user(self):
        report = build_v03_flow_contract_report(v03_flow({
            "decision_contract": {
                "schema": "decision_envelope.v1",
                "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
                "on_needs_user_input": "pause",
            }
        }), v03_manifest())
        self.assertFalse(report["ok"])
        self.assertIn("v03_decision_interaction_missing", [item["code"] for item in report["findings"]])

    def test_v03_certification_passes_for_supported_partial_capabilities(self):
        report = build_protocol_certification_report(load_base_implementation(ROOT), v03_manifest(), v03_flow(), ROOT)
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual("cf-farp-0-3-certified", report["label"])

    def test_runtime_resume_capability_is_supported_by_base(self):
        manifest = v03_manifest(required_capabilities=[
            "root_flow_execution",
            "decision_envelope_v1",
            "runtime_resume_after_user_input",
        ])
        report = build_compatibility_report(load_base_implementation(ROOT), manifest, v03_flow(), ROOT)
        self.assertTrue(report["ok"], report["findings"])


if __name__ == "__main__":
    unittest.main()
