from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .base_manifest import load_base_implementation, validate_base_implementation
from .data_contracts import (
    DataContractError,
    DataContractRegistry,
    build_data_contract_support_report,
    validate_data_contract_instance,
)
from .knowledge_registry import ProtocolKnowledgeRegistry


CLEAN_GENERATION = "clean-v1"
CLEAN_SOURCE_ID = "cartridgeflow-authoritative"
CLEAN_CONTRACT_VERSION = "1.0.0"
CLEAN_PROTOCOLS = (
    (1, "CF-FOUNDATION", "1.0.0", "cartridgeflow.foundation.v1"),
    (2, "CF-AUTHORING", "1.0.0", "cartridgeflow.authoring.v1"),
    (3, "CF-DISTRIBUTION", "1.0.0", "cartridgeflow.distribution.v1"),
    (4, "CF-RUNTIME", "1.0.0", "cartridgeflow.runtime.v1"),
)
CLEAN_CONTRACT_IDS = (
    "cartridgeflow.foundation.implementation",
    "cartridgeflow.foundation.support",
    "cartridgeflow.foundation.conformance-report",
    "cartridgeflow.foundation.finding",
    "cartridgeflow.foundation.evidence",
    "cartridgeflow.governance.protocol-release",
    "cartridgeflow.governance.registry-lock",
    "cartridgeflow.governance.change",
    "cartridgeflow.intent.project",
    "cartridgeflow.intent.node",
    "cartridgeflow.intent.field",
    "cartridgeflow.intent.review",
    "cartridgeflow.intent.capability-gap",
    "cartridgeflow.intent.capability-proposal",
    "cartridgeflow.capability.definition",
    "cartridgeflow.capability.port",
    "cartridgeflow.capability.field",
    "cartridgeflow.capability.dependency",
    "cartridgeflow.capability.verification",
    "cartridgeflow.capability.release",
    "cartridgeflow.flow.definition",
    "cartridgeflow.flow.node",
    "cartridgeflow.flow.edge",
    "cartridgeflow.flow.plan",
    "cartridgeflow.flow.decision",
    "cartridgeflow.flow.interaction",
    "cartridgeflow.data.value-type",
    "cartridgeflow.data.binding",
    "cartridgeflow.data.store-access",
    "cartridgeflow.data.output-write",
    "cartridgeflow.data.lineage",
    "cartridgeflow.presentation.settings",
    "cartridgeflow.presentation.settings-binding",
    "cartridgeflow.presentation.ui",
    "cartridgeflow.integration.model-binding",
    "cartridgeflow.integration.tool",
    "cartridgeflow.integration.tool-binding",
    "cartridgeflow.integration.resource",
    "cartridgeflow.integration.extension",
    "cartridgeflow.composition.request",
    "cartridgeflow.composition.resolution",
    "cartridgeflow.composition.materialization",
    "cartridgeflow.composition.provenance",
    "cartridgeflow.package.manifest",
    "cartridgeflow.package.content-entry",
    "cartridgeflow.package.dependency-lock",
    "cartridgeflow.package.entrypoint",
    "cartridgeflow.integrity.manifest",
    "cartridgeflow.integrity.signature-payload",
    "cartridgeflow.integrity.verification",
    "cartridgeflow.trust.publisher",
    "cartridgeflow.trust.signature",
    "cartridgeflow.trust.decision",
    "cartridgeflow.installation.request",
    "cartridgeflow.installation.plan",
    "cartridgeflow.installation.result",
    "cartridgeflow.exposure.experience",
    "cartridgeflow.exposure.delivery",
    "cartridgeflow.host.profile",
    "cartridgeflow.host.target",
    "cartridgeflow.host.compatibility",
    "cartridgeflow.execution.request",
    "cartridgeflow.execution.run",
    "cartridgeflow.execution.node-state",
    "cartridgeflow.execution.error",
    "cartridgeflow.execution.event",
    "cartridgeflow.interaction.pending",
    "cartridgeflow.interaction.response",
    "cartridgeflow.recovery.checkpoint",
    "cartridgeflow.recovery.request",
    "cartridgeflow.recovery.result",
    "cartridgeflow.artifact.record",
    "cartridgeflow.artifact.content-reference",
    "cartridgeflow.delivery.result",
    "cartridgeflow.delivery.receipt",
)
CLEAN_LAYER_CONTRACTS = {
    1: CLEAN_CONTRACT_IDS[:8],
    2: CLEAN_CONTRACT_IDS[8:43],
    3: CLEAN_CONTRACT_IDS[43:58],
    4: CLEAN_CONTRACT_IDS[58:],
}


@dataclass(frozen=True)
class CleanProtocolAdapter:
    layer: int
    protocol_id: str
    version: str
    adapter_id: str
    contract_ids: tuple[str, ...]

    def validate(
        self,
        contract_id: str,
        value: Any,
        *,
        root: str | Path | None = None,
        registry_path: str | Path | None = None,
    ) -> Any:
        if contract_id not in self.contract_ids:
            raise DataContractError(
                "clean_contract_layer_mismatch",
                f"{contract_id} does not belong to layer {self.layer} ({self.protocol_id})",
            )
        return validate_clean_contract(
            contract_id,
            value,
            root=root,
            registry_path=registry_path,
        )


CLEAN_ADAPTERS = {
    adapter_id: CleanProtocolAdapter(
        layer=layer,
        protocol_id=protocol_id,
        version=version,
        adapter_id=adapter_id,
        contract_ids=CLEAN_LAYER_CONTRACTS[layer],
    )
    for layer, protocol_id, version, adapter_id in CLEAN_PROTOCOLS
}


def resolve_clean_protocol_adapter(adapter_id: str) -> CleanProtocolAdapter:
    try:
        return CLEAN_ADAPTERS[adapter_id]
    except KeyError as exc:
        raise DataContractError(
            "clean_protocol_adapter_unknown",
            f"unknown {CLEAN_GENERATION} protocol adapter: {adapter_id}",
        ) from exc


def build_clean_base_candidate(
    root: str | Path,
    *,
    base: dict | None = None,
) -> dict:
    """Build a validated clean-v1 Base candidate without changing the active manifest."""
    project_root = Path(root).resolve()
    candidate = copy.deepcopy(base if base is not None else load_base_implementation(project_root))
    candidate["protocol_generation"] = {
        "id": CLEAN_GENERATION,
        "source_id": CLEAN_SOURCE_ID,
        "layers": [
            {
                "layer": layer,
                "id": protocol_id,
                "version": version,
                "runtime_adapter": adapter_id,
            }
            for layer, protocol_id, version, adapter_id in CLEAN_PROTOCOLS
        ],
    }
    candidate["supported_data_contracts"] = [
        {
            "id": contract_id,
            "version": CLEAN_CONTRACT_VERSION,
            "status": "supported",
            "evidence": "clean_protocol_generation",
        }
        for contract_id in CLEAN_CONTRACT_IDS
    ]
    replaced_adapters = {
        "cf.foundation.v1",
        "cf.authoring.v1",
        "cf.distribution.v1",
        "cf.runtime.v1",
        *(adapter_id for _layer, _protocol_id, _version, adapter_id in CLEAN_PROTOCOLS),
    }
    candidate["supported_protocol_adapters"] = [
        item
        for item in candidate.get("supported_protocol_adapters") or []
        if isinstance(item, dict) and item.get("id") not in replaced_adapters
    ] + [
        {"id": adapter_id, "status": "supported"}
        for _layer, _protocol_id, _version, adapter_id in CLEAN_PROTOCOLS
    ]
    validate_base_implementation(candidate)
    return candidate


def validate_clean_contract(
    contract_id: str,
    value: Any,
    *,
    root: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> Any:
    if contract_id not in CLEAN_CONTRACT_IDS:
        raise DataContractError(
            "clean_contract_unknown",
            f"unknown {CLEAN_GENERATION} contract: {contract_id}",
        )
    return validate_data_contract_instance(
        contract_id,
        CLEAN_CONTRACT_VERSION,
        value,
        root=root,
        registry_path=registry_path,
        use_runtime_compatibility=False,
    )


def build_clean_protocol_support_report(
    root: str | Path,
    *,
    base: dict | None = None,
    registry_path: str | Path | None = None,
) -> dict:
    project_root = Path(root).resolve()
    contract_registry = DataContractRegistry(project_root, registry_path=registry_path)
    base_data = base if base is not None else load_base_implementation(project_root)
    findings: list[dict[str, str]] = []

    with ProtocolKnowledgeRegistry(contract_registry.path) as registry:
        metadata = dict(registry.connection.execute("SELECT key, value FROM registry_metadata"))
        if metadata.get("generation") != CLEAN_GENERATION:
            _finding(findings, "clean_generation_not_active", "the registry does not publish clean-v1")
        if metadata.get("source_id") != CLEAN_SOURCE_ID:
            _finding(
                findings,
                "clean_source_invalid",
                f"the registry source is not {CLEAN_SOURCE_ID}",
            )
        protocol_rows = registry.connection.execute(
            "SELECT family.layer, release.protocol_id, release.version, release.lifecycle "
            "FROM protocol_release AS release JOIN protocol_family AS family "
            "ON family.source_id = release.source_id AND family.protocol_id = release.protocol_id "
            "WHERE release.source_id = ? ORDER BY family.layer",
            (CLEAN_SOURCE_ID,),
        ).fetchall()
        actual_protocols = tuple(
            (int(row["layer"]), str(row["protocol_id"]), str(row["version"]))
            for row in protocol_rows
        )
        expected_protocols = tuple(
            (layer, protocol_id, version)
            for layer, protocol_id, version, _adapter in CLEAN_PROTOCOLS
        )
        if actual_protocols != expected_protocols or any(
            row["lifecycle"] != "published" for row in protocol_rows
        ):
            _finding(
                findings,
                "clean_protocol_layers_invalid",
                f"published four-layer releases differ from clean-v1: {actual_protocols}",
            )
        contract_rows = registry.connection.execute(
            "SELECT release.contract_id, release.version, release.lifecycle, release.generation, "
            "release.definition_kind, family.layer FROM data_contract_release AS release "
            "JOIN data_contract_family AS family USING(contract_id) "
            "WHERE release.source_id = ? ORDER BY family.layer, family.domain_order, "
            "family.sort_order, family.contract_id",
            (CLEAN_SOURCE_ID,),
        ).fetchall()
        actual_contracts = tuple(str(row["contract_id"]) for row in contract_rows)
        if actual_contracts != CLEAN_CONTRACT_IDS:
            _finding(
                findings,
                "clean_contract_catalog_invalid",
                "the active clean-v1 contract identities are incomplete or reordered",
            )
        if any(
            row["version"] != CLEAN_CONTRACT_VERSION
            or row["lifecycle"] != "published"
            or row["generation"] != CLEAN_GENERATION
            or row["definition_kind"] != "json_schema"
            for row in contract_rows
        ):
            _finding(
                findings,
                "clean_contract_format_invalid",
                "every clean-v1 contract must be a published 1.0.0 JSON Schema",
            )
        layer_counts = {
            int(row["layer"]): int(row["count"])
            for row in registry.connection.execute(
                "SELECT family.layer, COUNT(*) AS count FROM data_contract_release AS release "
                "JOIN data_contract_family AS family USING(contract_id) "
                "WHERE release.source_id = ? GROUP BY family.layer",
                (CLEAN_SOURCE_ID,),
            )
        }
        if layer_counts != {1: 8, 2: 35, 3: 15, 4: 17}:
            _finding(
                findings,
                "clean_contract_layer_counts_invalid",
                f"clean-v1 layer contract counts are invalid: {layer_counts}",
            )
        if registry.connection.execute("SELECT COUNT(*) FROM data_contract_migration").fetchone()[0]:
            _finding(
                findings,
                "clean_migration_rows_forbidden",
                "clean-v1 must not contain old-generation migration rows",
            )
        _audit_contract_examples(registry, contract_rows, findings)

    generation = base_data.get("protocol_generation")
    expected_layers = [
        {
            "layer": layer,
            "id": protocol_id,
            "version": version,
            "runtime_adapter": adapter_id,
        }
        for layer, protocol_id, version, adapter_id in CLEAN_PROTOCOLS
    ]
    if not isinstance(generation, dict) or (
        generation.get("id"), generation.get("source_id"), generation.get("layers")
    ) != (CLEAN_GENERATION, CLEAN_SOURCE_ID, expected_layers):
        _finding(
            findings,
            "base_clean_generation_missing",
            "Base does not select the exact clean-v1 layers from the authoritative source",
        )
    supported_protocols = {
        (str(item.get("id") or ""), str(item.get("version") or ""))
        for item in base_data.get("supported_protocols") or []
        if isinstance(item, dict) and item.get("status") == "supported"
    }
    supported_adapters = {
        str(item.get("id") or "")
        for item in base_data.get("supported_protocol_adapters") or []
        if isinstance(item, dict) and item.get("status") == "supported"
    }
    for _layer, protocol_id, version, adapter_id in CLEAN_PROTOCOLS:
        if (protocol_id, version) not in supported_protocols:
            _finding(
                findings,
                "base_clean_protocol_missing",
                f"Base does not support {protocol_id}@{version}",
            )
        if adapter_id not in supported_adapters:
            _finding(
                findings,
                "base_clean_adapter_missing",
                f"Base does not support protocol adapter {adapter_id}",
            )

    data_contract_report = build_data_contract_support_report(
        project_root,
        base=base_data,
        registry_path=contract_registry.path,
    )
    findings.extend(
        {"code": str(item["code"]), "message": str(item["message"])}
        for item in data_contract_report["findings"]
    )
    return {
        "schema": "cartridgeflow.clean_protocol_support_report.v1",
        "generation": CLEAN_GENERATION,
        "ok": not findings,
        "summary": {
            "protocols": len(CLEAN_PROTOCOLS),
            "contracts": len(CLEAN_CONTRACT_IDS),
            "findings": len(findings),
        },
        "data_contract_support": data_contract_report["summary"],
        "findings": findings,
    }


def assert_base_supports_clean_protocol(
    root: str | Path,
    *,
    registry_path: str | Path | None = None,
) -> dict:
    report = build_clean_protocol_support_report(root, registry_path=registry_path)
    if not report["ok"]:
        first = report["findings"][0]
        raise DataContractError(str(first["code"]), str(first["message"]))
    return report


def _audit_contract_examples(
    registry: ProtocolKnowledgeRegistry,
    contracts: list[Any],
    findings: list[dict[str, str]],
) -> None:
    for contract in contracts:
        contract_id = str(contract["contract_id"])
        rows = registry.connection.execute(
            "SELECT example.example_kind, artifact.text_content FROM data_contract_example AS example "
            "JOIN artifact ON artifact.artifact_id = example.artifact_id "
            "WHERE example.contract_release_key = ? ORDER BY example.example_kind",
            (f"{contract_id}@{CLEAN_CONTRACT_VERSION}",),
        ).fetchall()
        examples: dict[str, Any] = {}
        try:
            for row in rows:
                examples[str(row["example_kind"])] = json.loads(str(row["text_content"]))
        except json.JSONDecodeError:
            _finding(findings, "clean_example_invalid", f"{contract_id} has invalid example JSON")
            continue
        if set(examples) != {"valid", "invalid"}:
            _finding(findings, "clean_examples_incomplete", f"{contract_id} lacks valid/invalid examples")
            continue
        schema = DataContractRegistry(registry_path=registry.path).schema(
            contract_id, CLEAN_CONTRACT_VERSION
        )
        validator = Draft202012Validator(schema)
        if list(validator.iter_errors(examples["valid"])):
            _finding(findings, "clean_valid_example_rejected", f"{contract_id} rejects its valid example")
        if not list(validator.iter_errors(examples["invalid"])):
            _finding(findings, "clean_invalid_example_accepted", f"{contract_id} accepts its invalid example")


def _finding(findings: list[dict[str, str]], code: str, message: str) -> None:
    findings.append({"code": code, "message": message})
