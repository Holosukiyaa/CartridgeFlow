import unittest
from pathlib import Path

from core.protocol import (
    build_flow_contract_report_for_adapter,
    load_base_implementation,
    load_protocol_release_catalog,
    supports_protocol_release,
)
from core.lab.flow_analyzer import analyze_flow
from core.orchestration import compile_execution_plan


ROOT = Path(__file__).resolve().parents[3]
EXECUTION_PLAN_ADAPTER = "cf-farp.execution-plan.v1"


def execution_plan_flow(version: str) -> dict:
    return {
        "id": "adapter.dispatch.root",
        "protocol": {"id": "CF-FARP", "version": version},
        "start": "start",
        "states": {
            "start": {"type": "control"},
            "complete": {"type": "terminal"},
        },
        "execution_plan": {
            "schema": "cartridgeflow.execution_plan.v1",
            "entry": "start",
            "edges": [{"id": "start_complete", "kind": "sequence", "from": "start", "to": "complete"}],
        },
    }


class ProtocolAdapterDispatchTests(unittest.TestCase):
    def test_current_release_declares_runtime_adapter_and_features(self):
        catalog = load_protocol_release_catalog(ROOT)
        release = catalog.get("CF-FARP", "1.0")
        self.assertEqual(EXECUTION_PLAN_ADAPTER, catalog.runtime_adapter("CF-FARP", "1.0"))
        self.assertIn("execution_plan", catalog.features("CF-FARP", "1.0"))
        self.assertEqual(EXECUTION_PLAN_ADAPTER, release["runtime_adapter"])

    def test_same_adapter_accepts_a_followup_release_without_a_version_branch(self):
        base = load_base_implementation(ROOT)
        future_release = {
            "id": "CF-FARP",
            "version": "1.1",
            "runtime_adapter": EXECUTION_PLAN_ADAPTER,
        }
        self.assertTrue(supports_protocol_release(base, future_release))

        report = build_flow_contract_report_for_adapter(
            future_release["runtime_adapter"],
            execution_plan_flow(future_release["version"]),
            protocol_id=future_release["id"],
            protocol_version=future_release["version"],
        )
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual(f"{future_release['id']}@{future_release['version']}", report["protocol"])

        analysis = analyze_flow(
            execution_plan_flow(future_release["version"]),
            target="dev",
            base=base,
            runtime_adapter=future_release["runtime_adapter"],
        )
        self.assertTrue(analysis["summary"]["runnable"], analysis["findings"])
        self.assertEqual("1.1", analysis["protocol"]["version"])

        plan = compile_execution_plan(
            execution_plan_flow(future_release["version"]),
            protocol_id=future_release["id"],
            protocol_version=future_release["version"],
        )
        self.assertEqual(
            {"id": future_release["id"], "version": future_release["version"]},
            plan["protocol"],
        )


if __name__ == "__main__":
    unittest.main()
