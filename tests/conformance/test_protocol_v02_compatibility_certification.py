import unittest
from pathlib import Path

from core.protocol import build_compatibility_report, build_protocol_certification_report, load_base_implementation


ROOT = Path(__file__).resolve().parents[2]


def v02_manifest():
    return {
        "id": "test.v02.certifiable",
        "version": "0.0.1",
        "base_contract": {"id": "CF-FARP", "version": "0.2"},
        "runtime_contract": {
            "protocol": "CF-FARP",
            "protocol_version": "0.2",
            "required_profiles": ["runtime_core", "dynamic_decision_runtime"],
            "recommended_profiles": [],
            "required_capabilities": [
                "root_flow_execution",
                "unified_process_node",
                "process_node_kind_parse",
                "process_executor_contract",
                "process_effect_contract",
            ],
            "optional_capabilities": [],
            "required_tools": [],
            "optional_tools": [],
        },
        "delivery_readiness": {"level": "dev"},
        "branding": {"tags": []},
        "mcp_tools": [],
    }


def v02_flow(missing_effect=False):
    decision = {
        "type": "process",
        "kind": "decision",
        "executor": "llm",
        "effect": "none",
        "input": "brief",
        "output": "decision",
        "output_contract": "decision.v1",
        "next": "deliver",
    }
    if missing_effect:
        decision.pop("effect")
    return {
        "schema_version": "1.0",
        "id": "test.v02.root",
        "protocol": {"id": "CF-FARP", "version": "0.2"},
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
                "input": "decision",
                "output": "episode_delivery",
                "next": "complete",
            },
            "complete": {"type": "terminal"},
        },
    }


class ProtocolV02CompatibilityCertificationTest(unittest.TestCase):
    def test_current_base_supports_v02_partial_for_declared_capabilities(self):
        base = load_base_implementation(ROOT)
        report = build_compatibility_report(base, v02_manifest(), v02_flow(), ROOT)
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual("partial", next(
            item.get("status")
            for item in base.get("supported_protocols") or []
            if item.get("id") == "CF-FARP" and item.get("version") == "0.2"
        ))

    def test_v02_certification_passes_with_capable_base_and_valid_flow(self):
        report = build_protocol_certification_report(load_base_implementation(ROOT), v02_manifest(), v02_flow(), ROOT)
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual(report["label"], "cf-farp-0-2-certified")

    def test_v02_certification_blocks_missing_effect(self):
        report = build_protocol_certification_report(load_base_implementation(ROOT), v02_manifest(), v02_flow(missing_effect=True), ROOT)
        self.assertFalse(report["ok"])
        self.assertIn("v02_process_effect_missing", [item["code"] for item in report["findings"]])


if __name__ == "__main__":
    unittest.main()
