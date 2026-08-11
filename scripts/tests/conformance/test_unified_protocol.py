from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
TEST_REGISTRY = (
    Path(os.environ["CARTRIDGEFLOW_TEST_PROTOCOL_REGISTRY"]).resolve()
    if os.environ.get("CARTRIDGEFLOW_TEST_PROTOCOL_REGISTRY")
    else None
)

from core.protocol import (
    DataContractError,
    DataContractRegistry,
    LEGACY_TO_UNIFIED,
    ProtocolKnowledgeRegistry,
    UNIFIED_CONTRACT_IDS,
    build_unified_protocol_support_report,
    load_base_implementation,
    migrate_legacy_contract,
    resolve_unified_protocol_adapter,
    validate_unified_contract,
)


class UnifiedProtocolTests(unittest.TestCase):
    def test_base_supports_the_complete_unified_generation(self):
        report = build_unified_protocol_support_report(ROOT, registry_path=TEST_REGISTRY)
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual(4, report["summary"]["protocols"])
        self.assertEqual(28, report["summary"]["contracts"])
        self.assertEqual(31, report["summary"]["legacy_migrations"])

    def test_all_contract_examples_have_executable_positive_and_failure_paths(self):
        contract_registry = DataContractRegistry(ROOT, registry_path=TEST_REGISTRY)
        with ProtocolKnowledgeRegistry(contract_registry.path) as registry:
            rows = registry.connection.execute(
                "SELECT release.contract_id, example.example_kind, artifact.text_content "
                "FROM data_contract_release AS release "
                "JOIN data_contract_example AS example USING(contract_release_key) "
                "JOIN artifact ON artifact.artifact_id = example.artifact_id "
                "WHERE release.source_id = 'unified' ORDER BY release.contract_id, example.example_kind"
            ).fetchall()
        by_contract: dict[str, dict[str, dict]] = {}
        for row in rows:
            by_contract.setdefault(str(row["contract_id"]), {})[str(row["example_kind"])] = json.loads(
                str(row["text_content"])
            )
        self.assertEqual(set(UNIFIED_CONTRACT_IDS), set(by_contract))
        for contract_id, examples in by_contract.items():
            self.assertEqual({"valid", "invalid"}, set(examples), contract_id)
            validate_unified_contract(
                contract_id, examples["valid"], root=ROOT, registry_path=TEST_REGISTRY
            )
            with self.assertRaises(DataContractError, msg=contract_id):
                validate_unified_contract(
                    contract_id, examples["invalid"], root=ROOT, registry_path=TEST_REGISTRY
                )
        for adapter_id in (
            "cf.foundation.v1",
            "cf.authoring.v1",
            "cf.distribution.v1",
            "cf.runtime.v1",
        ):
            adapter = resolve_unified_protocol_adapter(adapter_id)
            for contract_id in adapter.contract_ids:
                adapter.validate(
                    contract_id,
                    by_contract[contract_id]["valid"],
                    root=ROOT,
                    registry_path=TEST_REGISTRY,
                )

    def test_every_legacy_contract_has_an_executable_migration(self):
        self.assertEqual(31, len(LEGACY_TO_UNIFIED))
        for legacy_release, target in LEGACY_TO_UNIFIED.items():
            migrated = migrate_legacy_contract(
                legacy_release, {}, root=ROOT, registry_path=TEST_REGISTRY
            )
            validate_unified_contract(
                target, migrated, root=ROOT, registry_path=TEST_REGISTRY
            )

    def test_missing_layer_contract_or_adapter_fails_closed(self):
        base = copy.deepcopy(load_base_implementation(ROOT))
        base["supported_protocols"] = [
            item for item in base["supported_protocols"] if item.get("id") != "CF-RUNTIME"
        ]
        base["supported_protocol_adapters"] = [
            item
            for item in base["supported_protocol_adapters"]
            if item.get("id") != "cf.runtime.v1"
        ]
        report = build_unified_protocol_support_report(
            ROOT, base=base, registry_path=TEST_REGISTRY
        )
        self.assertFalse(report["ok"])
        codes = {item["code"] for item in report["findings"]}
        self.assertIn("base_unified_protocol_missing", codes)
        self.assertIn("base_unified_adapter_missing", codes)

    def test_unknown_contract_and_migration_fail_closed(self):
        with self.assertRaisesRegex(DataContractError, "unknown unified-v1 contract"):
            validate_unified_contract("cartridgeflow.unknown", {}, root=ROOT)
        with self.assertRaisesRegex(DataContractError, "no unified-v1 migration"):
            migrate_legacy_contract("cartridgeflow.unknown@1.0.0", {}, root=ROOT)
        with self.assertRaisesRegex(DataContractError, "unknown unified-v1 protocol adapter"):
            resolve_unified_protocol_adapter("cf.unknown.v1")
        with self.assertRaisesRegex(DataContractError, "does not belong to layer"):
            resolve_unified_protocol_adapter("cf.foundation.v1").validate(
                "cartridgeflow.delivery.result", {"status": "delivered", "artifacts": []}, root=ROOT
            )


if __name__ == "__main__":
    unittest.main()
