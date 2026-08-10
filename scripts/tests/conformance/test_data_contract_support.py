from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.protocol import (
    CartridgeSettingsStore,
    DataContractError,
    DataContractRegistry,
    DataContractValidationError,
    ProtocolKnowledgeRegistry,
    build_data_contract_support_report,
    build_runtime_profile_compatibility_report,
    apply_cartridge_settings,
    load_base_implementation,
    resolve_protocol_registry,
    validate_data_contract_instance,
    validate_cartridge_presentation_contracts,
)


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_PATH = ROOT / "config" / "base" / "capability_evidence.json"


class DataContractSupportTests(unittest.TestCase):
    def test_base_supports_all_active_contract_releases(self):
        report = build_data_contract_support_report(ROOT)

        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual(31, report["summary"]["active_releases"])
        self.assertEqual(31, report["summary"]["declared_releases"])
        self.assertEqual(31, report["summary"]["supported_releases"])
        self.assertEqual({"supported"}, {item["status"] for item in report["items"]})

    def test_missing_support_or_failure_evidence_fails_closed(self):
        base = copy.deepcopy(load_base_implementation(ROOT))
        base["supported_data_contracts"] = base["supported_data_contracts"][1:]
        report = build_data_contract_support_report(ROOT, base=base)
        self.assertIn("data_contract_support_missing", {item["code"] for item in report["findings"]})

        evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        evidence["evidence_sets"]["data_contract_governance"]["failure_tests"] = []
        report = build_data_contract_support_report(ROOT, evidence=evidence)
        self.assertIn("data_contract_failure_test_missing", {item["code"] for item in report["findings"]})

    def test_registered_json_contracts_accept_valid_values(self):
        values = {
            "cartridgeflow.capability.settings": self._example("cartridgeflow.capability.settings", "valid"),
            "cartridgeflow.capability.settings-binding": self._example("cartridgeflow.capability.settings-binding", "valid"),
            "cartridgeflow.capability.ui": self._example("cartridgeflow.capability.ui", "valid"),
            "cartridgeflow.runtime.target": [{"id": "CF-DRP", "version": "1.0"}],
        }
        for contract_id, value in values.items():
            with self.subTest(contract_id=contract_id):
                self.assertIs(value, validate_data_contract_instance(contract_id, "1.0.0", value, root=ROOT))

    def test_registered_json_contracts_reject_invalid_values(self):
        values = {
            "cartridgeflow.capability.settings": self._example("cartridgeflow.capability.settings", "invalid"),
            "cartridgeflow.capability.settings-binding": {
                "schema": "cartridgeflow.cartridge_settings_bindings.v1",
                "bindings": [{"setting_id": "voice", "target": {"kind": "process_param", "node_id": "render", "param": "bad-param"}}],
            },
            "cartridgeflow.capability.ui": {
                "schema": "cartridgeflow.cartridge_ui.v1",
                "mode": "sandboxed",
                "host_capabilities": [],
            },
            "cartridgeflow.runtime.target": [],
        }
        for contract_id, value in values.items():
            with self.subTest(contract_id=contract_id):
                with self.assertRaises(DataContractValidationError) as raised:
                    validate_data_contract_instance(contract_id, "1.0.0", value, root=ROOT)
                self.assertEqual("data_contract_instance_invalid", raised.exception.code)

    def test_presentation_contract_applies_settings_only_to_an_in_memory_flow_copy(self):
        settings = self._example("cartridgeflow.capability.settings", "valid")
        bindings = self._example("cartridgeflow.capability.settings-binding", "valid")
        ui = self._example("cartridgeflow.capability.ui", "valid")
        flow = {"states": {"generate_brief": {"type": "process", "params": {"length": "short"}}}}

        report = validate_cartridge_presentation_contracts(settings, bindings, ui, flow, root=ROOT)
        applied = apply_cartridge_settings(
            flow,
            settings,
            bindings,
            ui,
            {"brief_length": "long"},
            root=ROOT,
        )

        self.assertEqual(1, report["binding_count"])
        self.assertEqual("short", flow["states"]["generate_brief"]["params"]["length"])
        self.assertEqual("long", applied["states"]["generate_brief"]["params"]["length"])

    def test_presentation_contract_rejects_missing_targets_and_unknown_values(self):
        settings = self._example("cartridgeflow.capability.settings", "valid")
        bindings = self._example("cartridgeflow.capability.settings-binding", "valid")
        ui = self._example("cartridgeflow.capability.ui", "valid")
        with self.assertRaises(DataContractValidationError) as raised:
            validate_cartridge_presentation_contracts(settings, bindings, ui, {"states": {}}, root=ROOT)
        self.assertEqual("settings_binding_target_invalid", raised.exception.code)

        flow = {"states": {"generate_brief": {"type": "process", "params": {}}}}
        with self.assertRaises(DataContractValidationError) as raised:
            apply_cartridge_settings(
                flow,
                settings,
                bindings,
                ui,
                {"private_prompt": "forbidden"},
                root=ROOT,
            )
        self.assertEqual("settings_value_unknown", raised.exception.code)

    def test_settings_store_isolates_publisher_and_cartridge_identities(self):
        settings = self._example("cartridgeflow.capability.settings", "valid")
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CartridgeSettingsStore(temp_dir)
            store.save("publisher.one", "brief", settings, {"brief_length": "short"})
            store.save("publisher.two", "brief", settings, {"brief_length": "long"})

            self.assertEqual("short", store.load("publisher.one", "brief", settings)["brief_length"])
            self.assertEqual("long", store.load("publisher.two", "brief", settings)["brief_length"])
            with self.assertRaises(DataContractValidationError) as raised:
                store.save("../escape", "brief", settings, {})
            self.assertEqual("settings_identity_invalid", raised.exception.code)

            invalid_contract = copy.deepcopy(settings)
            invalid_contract["fields"][0]["sensitive"] = True
            with self.assertRaises(DataContractValidationError) as raised:
                store.save("publisher.one", "brief", invalid_contract, {})
            self.assertEqual("settings_sensitive_default_forbidden", raised.exception.code)

    def test_runtime_profile_accepts_derived_supported_payload(self):
        manifest = {
            "runtime_contract": {
                "protocol": "CF-FARP",
                "protocol_version": "1.1",
                "target_runtimes": [{"id": "CF-DRP", "version": "1.0"}],
            },
            "llm_recipe": {"roles": [{"id": "writer", "wire_api": "chat_completions"}]},
        }
        flow = {
            "protocol": {"id": "CF-FARP", "version": "1.1"},
            "states": {
                "generate": {
                    "type": "process",
                    "action": "tool_call",
                    "inputs": {"brief": {"binding": {"source": "run_input"}}},
                    "tools": [{"type": "mcp"}],
                }
            },
            "execution_plan": {"edges": []},
        }

        report = build_runtime_profile_compatibility_report(
            manifest,
            flow,
            {"mode": "none"},
            root=ROOT,
        )

        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual({"id": "CF-DRP", "version": "1.0"}, report["target"])

    def test_runtime_profile_rejects_target_and_derived_capability_mismatches(self):
        missing = build_runtime_profile_compatibility_report(
            {"runtime_contract": {"protocol": "CF-FARP", "protocol_version": "1.1"}},
            {},
            root=ROOT,
        )
        self.assertEqual({"cre_runtime_target_missing"}, {item["code"] for item in missing["findings"]})

        invalid = build_runtime_profile_compatibility_report(
            {"runtime_contract": {"target_runtimes": []}},
            {},
            root=ROOT,
        )
        self.assertEqual({"cre_runtime_target_invalid"}, {item["code"] for item in invalid["findings"]})

        manifest = {
            "runtime_contract": {
                "protocol": "CF-FARP",
                "protocol_version": "9.9",
                "target_runtimes": [{"id": "CF-DRP", "version": "1.0"}],
            },
            "llm_recipe": {"roles": [{"wire_api": "responses"}]},
        }
        flow = {
            "states": {
                "a": {
                    "type": "process",
                    "action": "unknown_action",
                    "inputs": {"value": {"binding": {"source": "implicit"}}},
                    "tools": [{"type": "unknown_transport"}],
                },
                "b": {"type": "unknown_state"},
                "c": {"type": "terminal"},
            },
            "execution_plan": {
                "edges": [
                    {"kind": "sequence", "from": "a", "to": "b"},
                    {"kind": "sequence", "from": "a", "to": "c"},
                    {"kind": "sequence", "from": "b", "to": "a"},
                    {"kind": "fork", "from": "a", "to": "c"},
                ]
            },
        }
        report = build_runtime_profile_compatibility_report(
            manifest,
            flow,
            {"mode": "sandboxed"},
            root=ROOT,
        )
        codes = {item["code"] for item in report["findings"]}
        self.assertTrue(
            {
                "cre_runtime_flow_protocol_unsupported",
                "cre_runtime_state_type_unsupported",
                "cre_runtime_action_unsupported",
                "cre_runtime_binding_source_unsupported",
                "cre_runtime_tool_transport_unsupported",
                "cre_runtime_edge_kind_unsupported",
                "cre_runtime_sequence_fanout_unsupported",
                "cre_runtime_cycle_unsupported",
                "cre_runtime_model_wire_api_unsupported",
                "cre_runtime_ui_mode_unsupported",
            }.issubset(codes)
        )

    def test_registry_requires_an_exact_known_schema_release(self):
        registry = DataContractRegistry(ROOT)
        with self.assertRaises(DataContractError) as raised:
            registry.schema("cartridgeflow.capability.settings", "9.0.0")
        self.assertEqual("data_contract_release_unknown", raised.exception.code)
        with self.assertRaises(DataContractError) as raised:
            registry.schema("cartridgeflow.flow.root", "1.0.0")
        self.assertEqual("data_contract_schema_unavailable", raised.exception.code)

    def _example(self, contract_id: str, kind: str) -> dict:
        with ProtocolKnowledgeRegistry(resolve_protocol_registry(ROOT)) as registry:
            row = registry.connection.execute(
                """
                SELECT artifact.source_id, artifact.artifact_path
                FROM data_contract_example AS example
                JOIN data_contract_release AS contract USING(contract_release_key)
                JOIN artifact USING(artifact_id)
                WHERE contract.contract_id = ? AND contract.version = '1.0.0'
                  AND example.example_kind = ?
                ORDER BY example.example_key
                LIMIT 1
                """,
                (contract_id, kind),
            ).fetchone()
            self.assertIsNotNone(row, f"missing {kind} example for {contract_id}")
            return registry.artifact_json(str(row["source_id"]), str(row["artifact_path"]))


if __name__ == "__main__":
    unittest.main()
