import json
import unittest
from pathlib import Path

from core.protocol import ProtocolRegistry, build_compatibility_report, build_protocol_certification_report, load_base_implementation


ROOT = Path(__file__).resolve().parents[3]


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


class ProtocolHistoryCompatibilityTests(unittest.TestCase):
    def test_current_base_rejects_v02_after_support_matrix_removal(self):
        base = load_base_implementation(ROOT)
        report = build_compatibility_report(base, v02_manifest(), v02_flow(), ROOT)
        self.assertFalse(report["ok"], report["findings"])
        self.assertIn("recognized_unsupported_protocol", [item["code"] for item in report["findings"]])

    def test_v02_certification_is_blocked_by_support_matrix(self):
        report = build_protocol_certification_report(load_base_implementation(ROOT), v02_manifest(), v02_flow(), ROOT)
        self.assertFalse(report["ok"], report["findings"])
        self.assertIn("compatibility_blocked", [item["code"] for item in report["findings"]])

    def test_v02_certification_remains_blocked_even_for_invalid_flow(self):
        report = build_protocol_certification_report(load_base_implementation(ROOT), v02_manifest(), v02_flow(missing_effect=True), ROOT)
        self.assertFalse(report["ok"])
        self.assertIn("compatibility_blocked", [item["code"] for item in report["findings"]])

    def test_v05_is_recognized_but_not_supported(self):
        protocol = json.loads((ROOT / "protocol" / "CF-FARP-0.5.json").read_text(encoding="utf-8"))
        registry = ProtocolRegistry(ROOT)
        supported = {(item["id"], item["version"]) for item in load_base_implementation(ROOT)["supported_protocols"]}

        self.assertTrue(protocol["standalone"])
        self.assertTrue(registry.recognizes_protocol("CF-FARP", "0.5"))
        self.assertEqual("recognized", registry.protocol_lifecycle("CF-FARP", "0.5")["status"])
        self.assertNotIn(("CF-FARP", "0.5"), supported)


if __name__ == "__main__":
    unittest.main()
