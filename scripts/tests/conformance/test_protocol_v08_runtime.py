import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from core.cartridge.root_flow import RootFlowEngine
from core.lab.flow_analyzer import analyze_flow
from core.lab.node_executor import LabNodeExecutor
from core.protocol import build_compatibility_report, load_base_implementation


ROOT = Path(__file__).resolve().parents[3]
MINIMUM_CAPABILITIES = [
    "root_flow_execution",
    "structured_io_contract",
    "explicit_input_binding",
    "typed_control_edges",
    "executable_topology_filter",
    "flow_analysis_report_v1",
    "analysis_report_freshness_guard",
]


def v08_manifest():
    return {
        "id": "test.v08.runtime",
        "name": "V08 Runtime",
        "version": "1.0.0",
        "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
        "runtime_contract": {
            "protocol": "CF-FARP",
            "protocol_version": "0.8",
            "required_profiles": ["runtime_core", "flow_analysis"],
            "recommended_profiles": [],
            "required_capabilities": MINIMUM_CAPABILITIES,
            "optional_capabilities": [],
            "required_tools": [],
            "optional_tools": [],
        },
        "asset_registry": "assets/registry.json",
        "delivery_readiness": {"level": "dev"},
        "llm_recipe": {"schema": "cartridgeflow.llm_recipe.v1", "roles": []},
        "mcp_tools": [],
    }


def string_input(binding, required=True):
    return {"required": required, "schema": {"type": "string"}, "binding": binding}


def string_output(key):
    return {"target": {"type": "store", "key": key}, "schema": {"type": "string"}, "write_policy": "replace_revision"}


def v08_flow():
    return {
        "schema_version": "1.0",
        "id": "test.v08.runtime.root",
        "protocol": {"id": "CF-FARP", "version": "0.8"},
        "start": "start",
        "states": {
            "start": {"type": "system", "next": "copy"},
            "copy": {
                "type": "process",
                "kind": "transfer",
                "executor": "deterministic",
                "effect": "writes_store",
                "inputs": {"message": string_input({"source": "run_input", "key": "message"})},
                "outputs": {"copied": string_output("copied_message")},
                "next": "delivery",
            },
            "delivery": {
                "type": "process",
                "kind": "delivery",
                "executor": "deterministic",
                "effect": "writes_store",
                "inputs": {"message": string_input({"source": "node_output", "node_id": "copy", "output": "copied"})},
                "outputs": {"result": string_output("final_message")},
                "primary_output": "final_message",
                "next": "complete",
            },
            "complete": {"type": "terminal"},
        },
        "control_edges": [],
    }


class ProtocolV08RuntimeTests(unittest.TestCase):
    def test_valid_v08_flow_analyzes_and_runs_with_structured_bindings(self):
        manifest = v08_manifest()
        flow = v08_flow()
        base = load_base_implementation(ROOT)
        report = build_compatibility_report(base, manifest, flow, ROOT)
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual(0, report["flow_contract"]["analysis"]["summary"]["blockers"])

        executor = LabNodeExecutor(ROOT)
        state_doc = {"context": {"store": {}}}
        run = {
            "run_id": "run_v08_test",
            "inputs": {"message": "hello v0.8"},
            "mcp_tools": [],
            "flow_output_bindings": {
                "copy:copied": {"type": "store", "key": "copied_message"},
                "delivery:result": {"type": "store", "key": "final_message"},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            first = executor.execute("copy", flow["states"]["copy"], state_doc, run, Path(tmp))
            second = executor.execute("delivery", flow["states"]["delivery"], state_doc, run, Path(tmp))
        self.assertFalse(first.get("failed"), first)
        self.assertFalse(second.get("failed"), second)
        self.assertEqual("hello v0.8", state_doc["context"]["store"]["copied_message"])
        self.assertEqual("hello v0.8", state_doc["context"]["store"]["final_message"])
        self.assertEqual([], [key for key in state_doc["context"]["store"] if key.startswith("_cf_input:")])

    def test_analysis_digest_ignores_layout_but_changes_with_binding(self):
        manifest = v08_manifest()
        flow = v08_flow()
        first = analyze_flow(flow, manifest, target="package", base=load_base_implementation(ROOT))
        with_layout = deepcopy(flow)
        with_layout["states"]["copy"]["layout"] = {"x": 900, "y": 400}
        second = analyze_flow(with_layout, manifest, target="package", base=load_base_implementation(ROOT))
        changed = deepcopy(flow)
        changed["states"]["copy"]["inputs"]["message"]["binding"]["key"] = "other_message"
        third = analyze_flow(changed, manifest, target="package", base=load_base_implementation(ROOT))
        self.assertEqual(first["source_digest"], second["source_digest"])
        self.assertNotEqual(first["source_digest"], third["source_digest"])
        self.assertTrue(first["summary"]["packagable"])

    def test_derived_edge_and_missing_branch_data_fail_closed(self):
        flow = v08_flow()
        flow["edges"] = [{"kind": "data", "from": "copy", "to": "delivery"}]
        report = analyze_flow(flow, v08_manifest(), target="production")
        self.assertIn("DERIVED_RELATION_IN_CONTROL_GRAPH", [item["code"] for item in report["findings"]])

        branched = v08_flow()
        branched["states"]["start"].pop("next")
        branched["control_edges"] = [
            {"kind": "branch", "from": "start", "to": "copy", "condition_id": "with_copy", "condition": "store:mode == true"},
            {"kind": "branch", "from": "start", "to": "delivery", "condition_id": "without_copy", "condition": "store:mode != true"},
        ]
        report = analyze_flow(branched, v08_manifest(), target="production")
        self.assertIn("INPUT_NOT_AVAILABLE_ON_ALL_PATHS", [item["code"] for item in report["findings"]])
        self.assertFalse(report["summary"]["runnable"])

    def test_runner_filters_non_control_relations(self):
        flow = {
            "protocol": {"id": "CF-FARP", "version": "0.8"},
            "states": {"a": {}, "b": {}, "derived": {}},
            "control_edges": [
                {"kind": "control", "from": "a", "to": "b"},
                {"kind": "data", "from": "a", "to": "derived", "runtime_effect": False},
                {"kind": "tool_dependency", "from": "a", "to": "derived", "runtime_effect": False},
            ],
        }
        self.assertEqual(["b"], RootFlowEngine(flow).next_states("a", {"store": {}}))


if __name__ == "__main__":
    unittest.main()
