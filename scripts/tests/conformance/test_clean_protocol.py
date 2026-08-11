from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import (
    CLEAN_CONTRACT_IDS,
    CLEAN_SOURCE_ID,
    DataContractError,
    ImplementationSource,
    ProtocolKnowledgeRegistry,
    build_clean_base_candidate,
    build_clean_protocol_support_report,
    publish_protocol_knowledge_registry,
    resolve_clean_protocol_adapter,
    validate_clean_contract,
)


class CleanProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.registry = Path(cls._temporary.name) / "protocol-registry.sqlite"
        publish_protocol_knowledge_registry(
            cls.registry,
            ROOT / "protocol-source" / "protocol-source.sqlite",
            implementation_sources=[ImplementationSource(CLEAN_SOURCE_ID, ROOT)],
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_base_supports_the_complete_clean_generation(self):
        report = build_clean_protocol_support_report(
            ROOT,
            base=build_clean_base_candidate(ROOT),
            registry_path=self.registry,
        )
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual(
            {"protocols": 4, "contracts": 75, "findings": 0},
            report["summary"],
        )

    def test_all_contract_examples_have_executable_positive_and_failure_paths(self):
        with ProtocolKnowledgeRegistry(self.registry) as registry:
            rows = registry.connection.execute(
                "SELECT release.contract_id, example.example_kind, artifact.text_content "
                "FROM data_contract_release AS release "
                "JOIN data_contract_example AS example USING(contract_release_key) "
                "JOIN artifact ON artifact.artifact_id = example.artifact_id "
                "WHERE release.source_id = ? ORDER BY release.contract_id, example.example_kind",
                (CLEAN_SOURCE_ID,),
            ).fetchall()
        by_contract: dict[str, dict[str, dict]] = {}
        for row in rows:
            by_contract.setdefault(str(row["contract_id"]), {})[
                str(row["example_kind"])
            ] = json.loads(str(row["text_content"]))
        self.assertEqual(set(CLEAN_CONTRACT_IDS), set(by_contract))
        for contract_id, examples in by_contract.items():
            self.assertEqual({"valid", "invalid"}, set(examples), contract_id)
            validate_clean_contract(
                contract_id,
                examples["valid"],
                root=ROOT,
                registry_path=self.registry,
            )
            with self.assertRaises(DataContractError, msg=contract_id):
                validate_clean_contract(
                    contract_id,
                    examples["invalid"],
                    root=ROOT,
                    registry_path=self.registry,
                )

    def test_missing_contract_or_adapter_fails_closed(self):
        base = build_clean_base_candidate(ROOT)
        base["supported_data_contracts"] = base["supported_data_contracts"][:-1]
        base["supported_protocol_adapters"] = [
            item
            for item in base["supported_protocol_adapters"]
            if item.get("id") != "cartridgeflow.runtime.v1"
        ]
        report = build_clean_protocol_support_report(
            ROOT,
            base=base,
            registry_path=self.registry,
        )
        self.assertFalse(report["ok"])
        codes = {item["code"] for item in report["findings"]}
        self.assertIn("base_clean_adapter_missing", codes)
        self.assertIn("data_contract_support_missing", codes)

    def test_unknown_contract_and_cross_layer_validation_fail_closed(self):
        with self.assertRaisesRegex(DataContractError, "unknown clean-v1 contract"):
            validate_clean_contract("cartridgeflow.unknown", {}, registry_path=self.registry)
        with self.assertRaisesRegex(DataContractError, "unknown clean-v1 protocol adapter"):
            resolve_clean_protocol_adapter("cartridgeflow.unknown.v1")
        with self.assertRaisesRegex(DataContractError, "does not belong to layer"):
            resolve_clean_protocol_adapter("cartridgeflow.foundation.v1").validate(
                "cartridgeflow.delivery.result",
                {},
                registry_path=self.registry,
            )
