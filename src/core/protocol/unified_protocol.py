from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

from .base_manifest import load_base_implementation
from .data_contracts import (
    DataContractError,
    DataContractRegistry,
    build_data_contract_support_report,
    validate_data_contract_instance,
)
from .knowledge_registry import ProtocolKnowledgeRegistry


UNIFIED_GENERATION = "unified-v1"
UNIFIED_SOURCE_ID = "unified"
UNIFIED_CONTRACT_VERSION = "1.0.0"
UNIFIED_PROTOCOLS = (
    (1, "CF-FOUNDATION", "1.0.0", "cf.foundation.v1"),
    (2, "CF-AUTHORING", "1.0.0", "cf.authoring.v1"),
    (3, "CF-DISTRIBUTION", "1.0.0", "cf.distribution.v1"),
    (4, "CF-RUNTIME", "1.0.0", "cf.runtime.v1"),
)
UNIFIED_CONTRACT_IDS = (
    "cartridgeflow.foundation.implementation",
    "cartridgeflow.foundation.compatibility",
    "cartridgeflow.governance.change",
    "cartridgeflow.authoring.intent",
    "cartridgeflow.authoring.capability",
    "cartridgeflow.authoring.settings",
    "cartridgeflow.authoring.settings-binding",
    "cartridgeflow.authoring.ui",
    "cartridgeflow.flow.definition",
    "cartridgeflow.flow.plan",
    "cartridgeflow.flow.binding",
    "cartridgeflow.flow.decision",
    "cartridgeflow.flow.interaction",
    "cartridgeflow.flow.tool",
    "cartridgeflow.flow.resource",
    "cartridgeflow.distribution.envelope",
    "cartridgeflow.distribution.integrity",
    "cartridgeflow.distribution.signature",
    "cartridgeflow.distribution.experience",
    "cartridgeflow.distribution.delivery",
    "cartridgeflow.host.profile",
    "cartridgeflow.host.target",
    "cartridgeflow.host.compatibility",
    "cartridgeflow.execution.run-state",
    "cartridgeflow.execution.error",
    "cartridgeflow.execution.checkpoint",
    "cartridgeflow.delivery.artifact",
    "cartridgeflow.delivery.result",
)
UNIFIED_LAYER_CONTRACTS = {
    1: UNIFIED_CONTRACT_IDS[0:3],
    2: UNIFIED_CONTRACT_IDS[3:15],
    3: UNIFIED_CONTRACT_IDS[15:20],
    4: UNIFIED_CONTRACT_IDS[20:28],
}

LEGACY_TO_UNIFIED = {
    "cartridgeflow.base.implementation-manifest@1.0.0": "cartridgeflow.foundation.implementation",
    "cartridgeflow.base.compatibility-report@1.0.0": "cartridgeflow.foundation.compatibility",
    "cartridgeflow.intent.recipe@1.0.0": "cartridgeflow.authoring.intent",
    "cartridgeflow.capability.release@1.0.0": "cartridgeflow.authoring.capability",
    "cartridgeflow.capability.public-port@1.0.0": "cartridgeflow.authoring.capability",
    "cartridgeflow.capability.settings@1.0.0": "cartridgeflow.authoring.settings",
    "cartridgeflow.capability.settings-binding@1.0.0": "cartridgeflow.authoring.settings-binding",
    "cartridgeflow.capability.ui@1.0.0": "cartridgeflow.authoring.ui",
    "cartridgeflow.flow.root@1.0.0": "cartridgeflow.flow.definition",
    "cartridgeflow.flow.node@1.0.0": "cartridgeflow.flow.definition",
    "cartridgeflow.flow.execution-plan@1.0.0": "cartridgeflow.flow.plan",
    "cartridgeflow.flow.data-binding@1.0.0": "cartridgeflow.flow.binding",
    "cartridgeflow.flow.decision-envelope@1.0.0": "cartridgeflow.flow.decision",
    "cartridgeflow.flow.pending-interaction@1.0.0": "cartridgeflow.flow.interaction",
    "cartridgeflow.flow.tool-plan@1.0.0": "cartridgeflow.flow.tool",
    "cartridgeflow.flow.manifest-tool-contract@1.0.0": "cartridgeflow.flow.tool",
    "cartridgeflow.flow.resource-requirement@1.0.0": "cartridgeflow.flow.resource",
    "cartridgeflow.release.envelope@1.0.0": "cartridgeflow.distribution.envelope",
    "cartridgeflow.release.envelope@2.0.0": "cartridgeflow.distribution.envelope",
    "cartridgeflow.release.hash-manifest@1.0.0": "cartridgeflow.distribution.integrity",
    "cartridgeflow.release.publisher-signature@1.0.0": "cartridgeflow.distribution.signature",
    "cartridgeflow.release.public-experience@1.0.0": "cartridgeflow.distribution.experience",
    "cartridgeflow.release.public-delivery@1.0.0": "cartridgeflow.distribution.delivery",
    "cartridgeflow.runtime.host-profile@1.0.0": "cartridgeflow.host.profile",
    "cartridgeflow.runtime.target@1.0.0": "cartridgeflow.host.target",
    "cartridgeflow.runtime.compatibility-report@1.0.0": "cartridgeflow.host.compatibility",
    "cartridgeflow.runtime.run-state@1.0.0": "cartridgeflow.execution.run-state",
    "cartridgeflow.runtime.error@1.0.0": "cartridgeflow.execution.error",
    "cartridgeflow.runtime.checkpoint@1.0.0": "cartridgeflow.execution.checkpoint",
    "cartridgeflow.runtime.artifact@1.0.0": "cartridgeflow.delivery.artifact",
    "cartridgeflow.runtime.delivery-result@1.0.0": "cartridgeflow.delivery.result",
}


@dataclass(frozen=True)
class UnifiedProtocolAdapter:
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
                "unified_contract_layer_mismatch",
                f"{contract_id} does not belong to layer {self.layer} ({self.protocol_id})",
            )
        return validate_unified_contract(
            contract_id,
            value,
            root=root,
            registry_path=registry_path,
        )


UNIFIED_ADAPTERS = {
    adapter_id: UnifiedProtocolAdapter(
        layer=layer,
        protocol_id=protocol_id,
        version=version,
        adapter_id=adapter_id,
        contract_ids=UNIFIED_LAYER_CONTRACTS[layer],
    )
    for layer, protocol_id, version, adapter_id in UNIFIED_PROTOCOLS
}


def resolve_unified_protocol_adapter(adapter_id: str) -> UnifiedProtocolAdapter:
    try:
        return UNIFIED_ADAPTERS[adapter_id]
    except KeyError as exc:
        raise DataContractError(
            "unified_protocol_adapter_unknown",
            f"unknown {UNIFIED_GENERATION} protocol adapter: {adapter_id}",
        ) from exc


def validate_unified_contract(
    contract_id: str,
    value: Any,
    *,
    root: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> Any:
    """Validate one unified-v1 value at its producer or consumer boundary."""
    if contract_id not in UNIFIED_CONTRACT_IDS:
        raise DataContractError(
            "unified_contract_unknown", f"unknown {UNIFIED_GENERATION} contract: {contract_id}"
        )
    return validate_data_contract_instance(
        contract_id,
        UNIFIED_CONTRACT_VERSION,
        value,
        root=root,
        registry_path=registry_path,
        use_runtime_compatibility=False,
    )


def build_foundation_implementation_contract(base: dict) -> dict:
    return {
        "schema": "cartridgeflow.foundation.implementation.v1",
        "implementation_id": str(base.get("implementation_id") or ""),
        "implementation_version": str(base.get("implementation_version") or ""),
        "protocol_generation": str((base.get("protocol_generation") or {}).get("id") or ""),
        "supported_contracts": [
            f"{item['id']}@{item['version']}"
            for item in base.get("supported_data_contracts") or []
            if isinstance(item, dict) and item.get("status") == "supported"
        ],
    }


def build_foundation_compatibility_contract(findings: list[dict]) -> dict:
    return {
        "schema": "cartridgeflow.foundation.compatibility.v1",
        "status": "compatible"
        if not any(item.get("severity") == "blocker" for item in findings)
        else "blocked",
        "findings": copy.deepcopy(findings),
    }


def build_host_compatibility_contract(report: dict) -> dict:
    """Project detailed negotiation facts to the public layer-4 compatibility contract."""
    findings = report.get("findings") if isinstance(report, dict) else None
    if not isinstance(findings, list):
        raise DataContractError(
            "unified_runtime_report_invalid", "runtime compatibility report requires findings"
        )
    return {
        "schema": "cartridgeflow.host.compatibility.v1",
        "status": "compatible"
        if bool(report.get("ok"))
        and not any(
            item.get("severity") == "blocker"
            for item in findings
            if isinstance(item, dict)
        )
        else "blocked",
        "findings": copy.deepcopy(findings),
    }


def migrate_legacy_contract(
    legacy_release: str,
    value: dict,
    *,
    root: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> dict:
    """Project one immutable legacy contract into its explicit unified-v1 successor."""
    target = LEGACY_TO_UNIFIED.get(legacy_release)
    if target is None:
        raise DataContractError(
            "unified_migration_unknown", f"no unified-v1 migration for {legacy_release}"
        )
    if not isinstance(value, dict):
        raise DataContractError("unified_migration_value_invalid", "legacy value must be an object")
    projector = _MIGRATORS.get(target)
    if projector is None:
        raise DataContractError(
            "unified_migration_missing", f"migration implementation is missing for {target}"
        )
    projected = projector(value, legacy_release)
    validate_unified_contract(target, projected, root=root, registry_path=registry_path)
    return projected


def build_unified_protocol_support_report(
    root: str | Path,
    *,
    base: dict | None = None,
    registry_path: str | Path | None = None,
) -> dict:
    """Fail closed unless the four new protocols and all contracts are fully implemented."""
    project_root = Path(root).resolve()
    contract_registry = DataContractRegistry(project_root, registry_path=registry_path)
    database = contract_registry.path
    base_data = base if base is not None else load_base_implementation(project_root)
    findings: list[dict] = []

    with ProtocolKnowledgeRegistry(database) as registry:
        metadata = dict(registry.connection.execute("SELECT key, value FROM registry_metadata"))
        if metadata.get("active_protocol_source") != UNIFIED_SOURCE_ID:
            _report_finding(
                findings,
                "unified_generation_not_active",
                "the authoritative registry has not activated source unified",
            )
        protocol_rows = registry.connection.execute(
            "SELECT protocol_id, version, runtime_adapter, release_json FROM protocol_release "
            "WHERE source_id = ? AND lifecycle = 'active' ORDER BY category",
            (UNIFIED_SOURCE_ID,),
        ).fetchall()
        actual_protocols = []
        for row in protocol_rows:
            release = json.loads(str(row["release_json"]))
            actual_protocols.append(
                (
                    int(release.get("layer") or 0),
                    str(row["protocol_id"]),
                    str(row["version"]),
                    str(row["runtime_adapter"] or ""),
                )
            )
        if tuple(actual_protocols) != UNIFIED_PROTOCOLS:
            _report_finding(
                findings,
                "unified_protocol_layers_invalid",
                f"active four-layer protocols differ from unified-v1: {actual_protocols}",
            )
        contract_rows = registry.connection.execute(
            "SELECT contract_release_key, contract_id, version, layer, definition_kind "
            "FROM data_contract_release JOIN data_contract_family USING(contract_id) "
            "WHERE source_id = ? AND generation = 'next' AND lifecycle = 'active' "
            "ORDER BY layer, domain_order, sort_order, contract_id",
            (UNIFIED_SOURCE_ID,),
        ).fetchall()
        actual_contracts = tuple(str(row["contract_id"]) for row in contract_rows)
        if set(actual_contracts) != set(UNIFIED_CONTRACT_IDS) or len(actual_contracts) != len(
            UNIFIED_CONTRACT_IDS
        ):
            _report_finding(
                findings,
                "unified_contract_catalog_invalid",
                "active unified-v1 contract identities are incomplete or contain extras",
            )
        if any(
            row["version"] != UNIFIED_CONTRACT_VERSION
            or row["definition_kind"] != "json_schema"
            for row in contract_rows
        ):
            _report_finding(
                findings,
                "unified_contract_format_invalid",
                "every unified-v1 contract must start at 1.0.0 and use JSON Schema",
            )
        layer_counts = {
            int(row["layer"]): int(row["count"])
            for row in registry.connection.execute(
                "SELECT family.layer, COUNT(*) AS count FROM data_contract_release AS contract "
                "JOIN data_contract_family AS family USING(contract_id) "
                "WHERE contract.source_id = ? AND contract.lifecycle = 'active' GROUP BY family.layer",
                (UNIFIED_SOURCE_ID,),
            )
        }
        if layer_counts != {1: 3, 2: 12, 3: 5, 4: 8}:
            _report_finding(
                findings,
                "unified_contract_layer_counts_invalid",
                f"unified-v1 layer contract counts are invalid: {layer_counts}",
            )
        legacy_active = registry.connection.execute(
            "SELECT COUNT(*) FROM data_contract_release WHERE generation = 'legacy' "
            "AND lifecycle IN ('active', 'legacy-active')"
        ).fetchone()[0]
        if legacy_active:
            _report_finding(
                findings,
                "legacy_contracts_still_active",
                f"{legacy_active} legacy contracts remain active after unified-v1 activation",
            )
        migrated_legacy = {
            str(row["from_contract_release_key"])
            for row in registry.connection.execute(
                "SELECT from_contract_release_key FROM data_contract_migration "
                "WHERE to_contract_release_key IN (SELECT contract_release_key "
                "FROM data_contract_release WHERE source_id = ?)",
                (UNIFIED_SOURCE_ID,),
            )
        }
        if migrated_legacy != set(LEGACY_TO_UNIFIED):
            _report_finding(
                findings,
                "unified_migration_coverage_invalid",
                "not every legacy data contract has exactly one explicit unified-v1 successor",
            )
        _audit_contract_examples(registry, contract_rows, findings)

    generation = base_data.get("protocol_generation")
    if not isinstance(generation, dict) or generation.get("id") != UNIFIED_GENERATION:
        _report_finding(
            findings,
            "base_unified_generation_missing",
            "Base does not select unified-v1 as its protocol generation",
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
    for _layer, protocol_id, version, adapter in UNIFIED_PROTOCOLS:
        if (protocol_id, version) not in supported_protocols:
            _report_finding(
                findings,
                "base_unified_protocol_missing",
                f"Base does not support {protocol_id}@{version}",
            )
        if adapter not in supported_adapters:
            _report_finding(
                findings,
                "base_unified_adapter_missing",
                f"Base does not support protocol adapter {adapter}",
            )

    data_contract_report = build_data_contract_support_report(
        project_root,
        base=base_data,
        registry_path=database,
    )
    findings.extend(data_contract_report["findings"])
    return {
        "schema": "cartridgeflow.unified_protocol_support_report.v1",
        "generation": UNIFIED_GENERATION,
        "ok": not findings,
        "summary": {
            "protocols": len(UNIFIED_PROTOCOLS),
            "contracts": len(UNIFIED_CONTRACT_IDS),
            "legacy_migrations": len(LEGACY_TO_UNIFIED),
            "findings": len(findings),
        },
        "data_contract_support": data_contract_report["summary"],
        "findings": findings,
    }


def assert_base_supports_unified_protocol(
    root: str | Path,
    *,
    registry_path: str | Path | None = None,
) -> dict:
    report = build_unified_protocol_support_report(root, registry_path=registry_path)
    if not report["ok"]:
        first = report["findings"][0]
        raise DataContractError(str(first["code"]), str(first["message"]))
    return report


def _audit_contract_examples(
    registry: ProtocolKnowledgeRegistry,
    contracts: list[Any],
    findings: list[dict],
) -> None:
    for contract in contracts:
        identity = str(contract["contract_release_key"])
        schema_row = registry.connection.execute(
            "SELECT artifact.text_content FROM data_contract_release AS release "
            "JOIN artifact ON artifact.artifact_id = release.schema_artifact_id "
            "WHERE release.contract_release_key = ?",
            (identity,),
        ).fetchone()
        examples = registry.connection.execute(
            "SELECT example.example_kind, artifact.text_content FROM data_contract_example AS example "
            "JOIN artifact ON artifact.artifact_id = example.artifact_id "
            "WHERE example.contract_release_key = ? ORDER BY example.example_kind",
            (identity,),
        ).fetchall()
        try:
            schema = json.loads(str(schema_row[0])) if schema_row else None
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
        except Exception as exc:
            _report_finding(
                findings,
                "unified_schema_invalid",
                f"{identity} has an invalid JSON Schema: {exc}",
            )
            continue
        kinds = {str(row["example_kind"]) for row in examples}
        if kinds != {"valid", "invalid"}:
            _report_finding(
                findings,
                "unified_examples_incomplete",
                f"{identity} must contain one valid and one invalid example",
            )
            continue
        for example in examples:
            value = json.loads(str(example["text_content"]))
            errors = list(validator.iter_errors(value))
            if example["example_kind"] == "valid" and errors:
                _report_finding(
                    findings,
                    "unified_valid_example_rejected",
                    f"{identity} rejects its valid example",
                )
            if example["example_kind"] == "invalid" and not errors:
                _report_finding(
                    findings,
                    "unified_invalid_example_accepted",
                    f"{identity} accepts its invalid example",
                )


def _report_finding(findings: list[dict], code: str, message: str) -> None:
    findings.append({"severity": "blocker", "code": code, "message": message})


def _pick(value: dict, *names: str, default: Any = "") -> Any:
    for name in names:
        candidate = value.get(name)
        if candidate is not None:
            return candidate
    return default


def _foundation_implementation(value: dict, _legacy: str) -> dict:
    return build_foundation_implementation_contract(value)


def _foundation_compatibility(value: dict, _legacy: str) -> dict:
    return build_foundation_compatibility_contract(list(value.get("findings") or []))


def _intent(value: dict, _legacy: str) -> dict:
    return {
        "id": str(_pick(value, "id", "intent_id", default="legacy.intent")),
        "goal": str(_pick(value, "goal", "objective", "prompt", default="Legacy intent")),
        "acceptance": list(_pick(value, "acceptance", "acceptance_criteria", default=["reviewed"])),
    }


def _capability(value: dict, _legacy: str) -> dict:
    return {
        "id": str(_pick(value, "id", "capability_id", default="legacy.capability")),
        "version": str(_pick(value, "version", default="1.0.0")),
        "ports": list(_pick(value, "ports", "public_ports", default=[])),
    }


def _settings(value: dict, _legacy: str) -> dict:
    return {
        "schema": "cartridgeflow.authoring.settings.v1",
        "fields": list(_pick(value, "fields", "settings", default=[])),
    }


def _settings_binding(value: dict, _legacy: str) -> dict:
    return {
        "schema": "cartridgeflow.authoring.settings-binding.v1",
        "bindings": list(_pick(value, "bindings", default=[])),
    }


def _ui(value: dict, _legacy: str) -> dict:
    return {
        "schema": "cartridgeflow.authoring.ui.v1",
        "mode": str(_pick(value, "mode", default="none")),
        "entry": _pick(value, "entry", "entrypoint", default=None),
    }


def _flow_definition(value: dict, legacy: str) -> dict:
    states = _pick(value, "states", "nodes", default=[])
    if isinstance(states, dict):
        states = [{"id": key, **(item if isinstance(item, dict) else {})} for key, item in states.items()]
    if legacy == "cartridgeflow.flow.node@1.0.0":
        node_id = str(_pick(value, "id", "node_id", default="legacy-node"))
        states = [{"id": node_id, **copy.deepcopy(value)}]
        entry = node_id
    else:
        entry = str(_pick(value, "entry", "entry_state", "start", default="legacy-entry"))
    return {
        "id": str(_pick(value, "id", "flow_id", default="legacy.flow")),
        "entry": entry,
        "states": list(states),
    }


def _flow_plan(value: dict, _legacy: str) -> dict:
    return {
        "version": str(_pick(value, "version", default="1.0.0")),
        "edges": list(_pick(value, "edges", default=[])),
    }


def _flow_binding(value: dict, _legacy: str) -> dict:
    return {"source": str(_pick(value, "source")), "target": str(_pick(value, "target"))}


def _decision(value: dict, _legacy: str) -> dict:
    return {
        "status": str(_pick(value, "status", "decision", default="accepted")),
        "outputs": dict(_pick(value, "outputs", "result", default={})),
    }


def _interaction(value: dict, _legacy: str) -> dict:
    target = _pick(value, "resume_target", default={"node": _pick(value, "node_id")})
    return {
        "interaction_id": str(_pick(value, "interaction_id", "id", default="legacy-interaction")),
        "resume_target": dict(target) if isinstance(target, dict) else {"token": str(target)},
    }


def _tool(value: dict, _legacy: str) -> dict:
    return {
        "tool_id": str(_pick(value, "tool_id", "id", default="legacy.tool")),
        "transport": str(_pick(value, "transport", default="builtin")),
        "permissions": list(_pick(value, "permissions", default=[])),
    }


def _resource(value: dict, _legacy: str) -> dict:
    return {
        "resource_id": str(_pick(value, "resource_id", "id", default="legacy.resource")),
        "kind": str(_pick(value, "kind", "type", default="generic")),
        "requirements": dict(_pick(value, "requirements", default={})),
    }


def _envelope(value: dict, _legacy: str) -> dict:
    return {
        "schema": "cartridgeflow.distribution.envelope.v1",
        "protocol": "CF-DISTRIBUTION@1.0.0",
        "payload": dict(_pick(value, "payload", default={})),
        "public": dict(_pick(value, "public", "public_contracts", default={})),
        "runtime": dict(_pick(value, "runtime", default={})),
    }


def _integrity(value: dict, _legacy: str) -> dict:
    return {
        "algorithm": str(_pick(value, "algorithm", default="sha256")),
        "files": dict(_pick(value, "files", default={})),
    }


def _signature(value: dict, _legacy: str) -> dict:
    return {
        "algorithm": str(_pick(value, "algorithm", default="ed25519")),
        "key_id": str(_pick(value, "key_id", default="legacy.publisher")),
        "signature": str(_pick(value, "signature", default="legacy-signature")),
    }


def _experience(value: dict, _legacy: str) -> dict:
    return {
        "title": str(_pick(value, "title", "name", default="Legacy cartridge")),
        "description": str(_pick(value, "description", "summary", default="Migrated cartridge")),
        "entry": _pick(value, "entry", default=None),
    }


def _distribution_delivery(value: dict, _legacy: str) -> dict:
    return {"outputs": list(_pick(value, "outputs", "artifacts", default=[]))}


def _host_profile(value: dict, _legacy: str) -> dict:
    return {
        "schema": "cartridgeflow.host.profile.v1",
        "id": str(_pick(value, "id", default="legacy-host")),
        "version": str(_pick(value, "version", default="1.0.0")),
        "protocols": list(_pick(value, "protocols", "supported_protocols", default=[])),
    }


def _host_target(value: dict, _legacy: str) -> dict:
    return {
        "schema": "cartridgeflow.host.target.v1",
        "protocol": str(_pick(value, "protocol", default="CF-RUNTIME@1.0.0")),
        "state_types": list(_pick(value, "state_types", "required_state_types", default=[])),
    }


def _host_compatibility(value: dict, _legacy: str) -> dict:
    return {
        "schema": "cartridgeflow.host.compatibility.v1",
        "status": str(_pick(value, "status", default="compatible")),
        "findings": list(_pick(value, "findings", default=[])),
    }


def _run_state(value: dict, _legacy: str) -> dict:
    return {
        "run_id": str(_pick(value, "run_id", "id", default="legacy-run")),
        "status": str(_pick(value, "status", default="ready")),
        "nodes": dict(_pick(value, "nodes", "node_states", default={})),
    }


def _runtime_error(value: dict, _legacy: str) -> dict:
    return {
        "code": str(_pick(value, "code", default="legacy_error")),
        "message": str(_pick(value, "message", default="Legacy runtime error")),
        "retryable": bool(_pick(value, "retryable", default=False)),
    }


def _checkpoint(value: dict, _legacy: str) -> dict:
    return {
        "run_id": str(_pick(value, "run_id", default="legacy-run")),
        "plan_digest": str(_pick(value, "plan_digest", "execution_plan_digest", default="legacy")),
        "state": dict(_pick(value, "state", "snapshot", default={})),
    }


def _artifact(value: dict, _legacy: str) -> dict:
    return {
        "artifact_id": str(_pick(value, "artifact_id", "id", default="legacy-artifact")),
        "kind": str(_pick(value, "kind", "type", default="file")),
        "provenance": dict(_pick(value, "provenance", default={})),
    }


def _delivery_result(value: dict, _legacy: str) -> dict:
    return {
        "status": str(_pick(value, "status", default="delivered")),
        "artifacts": list(_pick(value, "artifacts", "outputs", default=[])),
    }


_MIGRATORS: dict[str, Callable[[dict, str], dict]] = {
    "cartridgeflow.foundation.implementation": _foundation_implementation,
    "cartridgeflow.foundation.compatibility": _foundation_compatibility,
    "cartridgeflow.authoring.intent": _intent,
    "cartridgeflow.authoring.capability": _capability,
    "cartridgeflow.authoring.settings": _settings,
    "cartridgeflow.authoring.settings-binding": _settings_binding,
    "cartridgeflow.authoring.ui": _ui,
    "cartridgeflow.flow.definition": _flow_definition,
    "cartridgeflow.flow.plan": _flow_plan,
    "cartridgeflow.flow.binding": _flow_binding,
    "cartridgeflow.flow.decision": _decision,
    "cartridgeflow.flow.interaction": _interaction,
    "cartridgeflow.flow.tool": _tool,
    "cartridgeflow.flow.resource": _resource,
    "cartridgeflow.distribution.envelope": _envelope,
    "cartridgeflow.distribution.integrity": _integrity,
    "cartridgeflow.distribution.signature": _signature,
    "cartridgeflow.distribution.experience": _experience,
    "cartridgeflow.distribution.delivery": _distribution_delivery,
    "cartridgeflow.host.profile": _host_profile,
    "cartridgeflow.host.target": _host_target,
    "cartridgeflow.host.compatibility": _host_compatibility,
    "cartridgeflow.execution.run-state": _run_state,
    "cartridgeflow.execution.error": _runtime_error,
    "cartridgeflow.execution.checkpoint": _checkpoint,
    "cartridgeflow.delivery.artifact": _artifact,
    "cartridgeflow.delivery.result": _delivery_result,
}
