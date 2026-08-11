from __future__ import annotations

import ast
import copy
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .artifact_store import resolve_protocol_registry
from .base_manifest import load_base_implementation
from .governance_registry import ProtocolKnowledgeRegistry, ProtocolKnowledgeRegistryError


ACTIVE_CONTRACT_LIFECYCLES = ("active", "legacy-active")
EVIDENCE_RELATIVE_PATH = Path("config/base/capability_evidence.json")


class DataContractError(ValueError):
    """Raised when a governed data contract cannot be resolved or trusted."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class DataContractValidationError(DataContractError):
    """Raised when a value violates one exact governed contract release."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        contract_id: str,
        version: str,
        instance_path: str = "$",
    ):
        super().__init__(code, message)
        self.contract_id = contract_id
        self.version = version
        self.instance_path = instance_path


class DataContractRegistry:
    """Read exact-version contract records from the published product snapshot."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        registry_path: str | Path | None = None,
    ):
        self.root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[3]
        self.path = Path(registry_path).resolve() if registry_path is not None else resolve_protocol_registry(self.root)

    def releases(self, *, active_only: bool = True) -> list[dict]:
        where = "WHERE contract.lifecycle IN (?, ?)" if active_only else ""
        parameters = ACTIVE_CONTRACT_LIFECYCLES if active_only else ()
        with ProtocolKnowledgeRegistry(self.path) as registry:
            rows = registry.connection.execute(
                f"""
                SELECT overview.*, contract.contract_release_key,
                       contract.definition_artifact_id, contract.definition_section_key,
                       contract.schema_artifact_id
                FROM data_contract_overview AS overview
                JOIN data_contract_release AS contract
                  ON contract.contract_id = overview.contract_id
                 AND contract.version = overview.version
                {where}
                ORDER BY overview.layer, overview.domain_order, overview.sort_order,
                         overview.contract_id, overview.version
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, contract_id: str, version: str) -> dict:
        with ProtocolKnowledgeRegistry(self.path) as registry:
            row = registry.connection.execute(
                """
                SELECT overview.*, contract.contract_release_key,
                       contract.definition_artifact_id, contract.definition_section_key,
                       contract.schema_artifact_id
                FROM data_contract_overview AS overview
                JOIN data_contract_release AS contract
                  ON contract.contract_id = overview.contract_id
                 AND contract.version = overview.version
                WHERE overview.contract_id = ? AND overview.version = ?
                """,
                (contract_id, version),
            ).fetchone()
        if row is None:
            raise DataContractError(
                "data_contract_release_unknown",
                f"data contract release is not registered: {contract_id}@{version}",
            )
        return dict(row)

    def definition_text(self, contract_id: str, version: str) -> str:
        record = self.get(contract_id, version)
        with ProtocolKnowledgeRegistry(self.path) as registry:
            row = registry.connection.execute(
                "SELECT source_id, artifact_path FROM artifact WHERE artifact_id = ?",
                (record["definition_artifact_id"],),
            ).fetchone()
            if row is None:
                raise DataContractError(
                    "data_contract_definition_missing",
                    f"definition artifact is missing: {contract_id}@{version}",
                )
            return registry.artifact_text(str(row["source_id"]), str(row["artifact_path"]))

    def schema(self, contract_id: str, version: str) -> dict:
        record = self.get(contract_id, version)
        if record["definition_kind"] != "json_schema" or not record["schema_artifact_id"]:
            raise DataContractError(
                "data_contract_schema_unavailable",
                f"data contract is not JSON Schema-backed: {contract_id}@{version}",
            )
        with ProtocolKnowledgeRegistry(self.path) as registry:
            row = registry.connection.execute(
                "SELECT source_id, artifact_path FROM artifact WHERE artifact_id = ?",
                (record["schema_artifact_id"],),
            ).fetchone()
            if row is None:
                raise DataContractError(
                    "data_contract_schema_missing",
                    f"schema artifact is missing: {contract_id}@{version}",
                )
            schema = registry.artifact_json(str(row["source_id"]), str(row["artifact_path"]))
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            raise DataContractError(
                "data_contract_schema_invalid",
                f"registered JSON Schema is invalid: {contract_id}@{version}: {exc}",
            ) from exc
        return schema


def validate_data_contract_instance(
    contract_id: str,
    version: str,
    value: Any,
    *,
    root: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> Any:
    """Validate a value against one exact registered JSON Schema release."""
    schema = DataContractRegistry(root, registry_path=registry_path).schema(contract_id, version)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda item: (list(item.absolute_path), item.message),
    )
    if errors:
        first = errors[0]
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}" for part in first.absolute_path
        )
        raise DataContractValidationError(
            "data_contract_instance_invalid",
            f"{contract_id}@{version} rejected {path}: {first.message}",
            contract_id=contract_id,
            version=version,
            instance_path=path,
        )
    return value


def validate_cartridge_presentation_contracts(
    settings: dict,
    bindings: dict,
    ui: dict,
    flow: dict,
    *,
    component_by_id: dict[str, dict] | None = None,
    root: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> dict:
    """Validate CF-FARP@1.1 settings, private bindings, UI, and Flow references."""
    fields_by_id = _validated_settings_fields(
        settings,
        root=root,
        registry_path=registry_path,
    )
    validate_data_contract_instance(
        "cartridgeflow.capability.settings-binding", "1.0.0", bindings, root=root, registry_path=registry_path
    )
    validate_data_contract_instance(
        "cartridgeflow.capability.ui", "1.0.0", ui, root=root, registry_path=registry_path
    )

    state_map = flow.get("states") if isinstance(flow.get("states"), dict) else {}
    bound_ids: set[str] = set()
    binding_items = bindings.get("bindings") if isinstance(bindings.get("bindings"), list) else []
    for binding in binding_items:
        setting_id = str(binding.get("setting_id") or "")
        if setting_id not in fields_by_id:
            _presentation_error("settings_binding_unknown_field", f"binding references an unknown setting: {setting_id}")
        if setting_id in bound_ids:
            _presentation_error("settings_binding_duplicate", f"setting has more than one binding: {setting_id}")
        bound_ids.add(setting_id)
        target = binding.get("target") if isinstance(binding.get("target"), dict) else {}
        node_id = str(target.get("node_id") or "")
        node = state_map.get(node_id)
        if not isinstance(node, dict) or node.get("type") != "process":
            _presentation_error("settings_binding_target_invalid", f"binding target must be an existing process state: {node_id}")
    missing = sorted(set(fields_by_id) - bound_ids)
    if missing:
        _presentation_error("settings_binding_missing", f"settings require exactly one binding: {missing}")

    mode = str(ui.get("mode") or "")
    capabilities = ui.get("host_capabilities") if isinstance(ui.get("host_capabilities"), list) else []
    if mode == "none" and capabilities:
        _presentation_error("ui_none_capability_forbidden", "mode=none cannot request Host capabilities", contract_id="cartridgeflow.capability.ui")
    if mode == "passive" and capabilities:
        _presentation_error("ui_passive_capability_forbidden", "passive UI cannot request Host capabilities", contract_id="cartridgeflow.capability.ui")
    if mode in {"passive", "sandboxed"}:
        component_id = str(ui.get("component_id") or "")
        component = (component_by_id or {}).get(component_id)
        if not isinstance(component, dict) or component.get("runtime") != mode:
            _presentation_error(
                "ui_component_runtime_mismatch",
                f"UI component must exist with runtime={mode}: {component_id}",
                contract_id="cartridgeflow.capability.ui",
            )
        declared_capabilities = component.get("host_capabilities")
        if isinstance(declared_capabilities, list) and not set(capabilities).issubset(set(declared_capabilities)):
            _presentation_error(
                "ui_component_capability_mismatch",
                f"UI requests capabilities not declared by component: {component_id}",
                contract_id="cartridgeflow.capability.ui",
            )
    return {
        "settings": settings,
        "bindings": bindings,
        "ui": ui,
        "field_count": len(fields_by_id),
        "binding_count": len(bound_ids),
        "ui_mode": mode,
    }


def apply_cartridge_settings(
    flow: dict,
    settings: dict,
    bindings: dict,
    ui: dict,
    values: dict,
    *,
    component_by_id: dict[str, dict] | None = None,
    root: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> dict:
    """Apply validated public settings to a deep-copied Flow and never mutate signed input."""
    validate_cartridge_presentation_contracts(
        settings,
        bindings,
        ui,
        flow,
        component_by_id=component_by_id,
        root=root,
        registry_path=registry_path,
    )
    resolved = validate_cartridge_settings_values(
        settings,
        values,
        root=root,
        registry_path=registry_path,
    )
    result = copy.deepcopy(flow)
    states = result["states"]
    for binding in bindings["bindings"]:
        target = binding["target"]
        node = states[target["node_id"]]
        params = node.get("params") if isinstance(node.get("params"), dict) else {}
        node["params"] = params
        params[target["param"]] = copy.deepcopy(resolved[binding["setting_id"]])
    return result


def validate_cartridge_settings_values(
    settings: dict,
    values: dict,
    *,
    root: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> dict:
    if not isinstance(values, dict):
        _presentation_error("settings_values_invalid", "settings values must be an object")
    fields_by_id = _validated_settings_fields(
        settings,
        root=root,
        registry_path=registry_path,
    )
    unknown = sorted(set(values) - set(fields_by_id))
    if unknown:
        _presentation_error("settings_value_unknown", f"unknown settings values: {unknown}")
    result: dict[str, Any] = {}
    for field_id, field in fields_by_id.items():
        if field_id in values:
            value = values[field_id]
        elif "default" in field:
            value = copy.deepcopy(field["default"])
        elif field.get("required") is True:
            _presentation_error("settings_value_required", f"required setting is missing: {field_id}")
        else:
            continue
        _validate_setting_value(field_id, field, value)
        result[field_id] = value
    return result


class CartridgeSettingsStore:
    """Persist public setting values under an explicit publisher/cartridge identity."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def save(self, publisher_id: str, cartridge_id: str, settings: dict, values: dict) -> dict:
        path = self._path(publisher_id, cartridge_id)
        resolved = validate_cartridge_settings_values(settings, values)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(resolved, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return resolved

    def load(self, publisher_id: str, cartridge_id: str, settings: dict) -> dict:
        path = self._path(publisher_id, cartridge_id)
        if not path.is_file():
            return validate_cartridge_settings_values(settings, {})
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _presentation_error("settings_store_invalid", f"stored settings are invalid: {exc}")
        return validate_cartridge_settings_values(settings, values)

    def _path(self, publisher_id: str, cartridge_id: str) -> Path:
        identity = (str(publisher_id), str(cartridge_id))
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", item) for item in identity):
            _presentation_error("settings_identity_invalid", "publisher and cartridge identities must be stable identifiers")
        target = (self.root / identity[0] / f"{identity[1]}.json").resolve()
        if self.root != target and self.root not in target.parents:
            _presentation_error("settings_identity_invalid", "settings identity escapes the storage root")
        return target


def build_runtime_profile_compatibility_report(
    manifest: dict,
    flow: dict,
    ui: dict | None = None,
    *,
    require_target: bool = True,
    profile: dict | None = None,
    root: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> dict:
    """Derive CF-DRP compatibility from signed payload facts, never from capability claims."""
    if profile is None:
        profile_text = DataContractRegistry(root, registry_path=registry_path).definition_text(
            "cartridgeflow.runtime.host-profile", "1.0.0"
        )
        try:
            profile = json.loads(profile_text)
        except json.JSONDecodeError as exc:
            raise DataContractError("runtime_profile_invalid", f"registered runtime profile is invalid: {exc}") from exc
    if not isinstance(profile, dict) or profile.get("schema") != "cartridgeflow.host_runtime_profile.v1":
        raise DataContractError("runtime_profile_invalid", "registered runtime profile has an invalid schema")

    report = {
        "schema": "cartridgeflow.host_runtime_profile_report.v1",
        "ok": True,
        "status": "compatible",
        "host_id": str(profile.get("host_id") or ""),
        "target": None,
        "findings": [],
    }
    runtime = manifest.get("runtime_contract") if isinstance(manifest.get("runtime_contract"), dict) else {}
    has_unified_target = "target" in runtime
    has_legacy_targets = "target_runtimes" in runtime
    if has_unified_target and has_legacy_targets:
        _runtime_finding(
            report,
            "cre_runtime_target_invalid",
            "runtime_contract must declare either target or target_runtimes, not both",
            "payload/manifest.json.runtime_contract",
        )
        return report
    if has_unified_target:
        target = runtime.get("target")
        try:
            validate_data_contract_instance(
                "cartridgeflow.host.target",
                "1.0.0",
                target,
                root=root,
                registry_path=registry_path,
            )
        except DataContractError as exc:
            _runtime_finding(
                report,
                "cre_runtime_target_invalid",
                str(exc),
                "payload/manifest.json.runtime_contract.target",
            )
            return report
        expected_protocol = "CF-RUNTIME@1.0.0"
        if target.get("protocol") != expected_protocol:
            _runtime_finding(
                report,
                "cre_runtime_target_unknown",
                f"cartridge does not target {expected_protocol}",
                "payload/manifest.json.runtime_contract.target.protocol",
            )
            return report
        unsupported_target_types = sorted(
            set(target.get("state_types") or []) - set(profile.get("state_types") or [])
        )
        if unsupported_target_types:
            _runtime_finding(
                report,
                "cre_runtime_state_type_unsupported",
                f"runtime target requires unsupported state types: {unsupported_target_types}",
                "payload/manifest.json.runtime_contract.target.state_types",
            )
        expected = {"id": "CF-RUNTIME", "version": "1.0.0"}
        report["target"] = expected
    elif not has_legacy_targets:
        if require_target:
            _runtime_finding(
                report,
                "cre_runtime_target_missing",
                "runtime_contract must declare target or target_runtimes",
                "payload/manifest.json.runtime_contract",
            )
        return report
    else:
        targets = runtime.get("target_runtimes")
        try:
            validate_data_contract_instance(
                "cartridgeflow.runtime.target",
                "1.0.0",
                targets,
                root=root,
                registry_path=registry_path,
            )
        except DataContractError as exc:
            _runtime_finding(report, "cre_runtime_target_invalid", str(exc), "payload/manifest.json.runtime_contract.target_runtimes")
            return report
        expected = {"id": str(profile.get("id") or ""), "version": str(profile.get("version") or "")}
        if expected not in targets:
            _runtime_finding(report, "cre_runtime_target_unknown", f"cartridge does not target {expected['id']}@{expected['version']}", "payload/manifest.json.runtime_contract.target_runtimes")
            return report
        report["target"] = expected

    flow_protocol = flow.get("protocol") if isinstance(flow.get("protocol"), dict) else {}
    protocol_id = str(flow_protocol.get("id") or runtime.get("protocol") or "")
    protocol_version = str(flow_protocol.get("version") or runtime.get("protocol_version") or "")
    supported_protocols = {
        (str(item.get("id") or ""), str(version))
        for item in profile.get("flow_protocols") or []
        if isinstance(item, dict)
        for version in item.get("versions") or []
    }
    supported_protocols.add(("CF-AUTHORING", "1.0.0"))
    if (protocol_id, protocol_version) not in supported_protocols:
        _runtime_finding(report, "cre_runtime_flow_protocol_unsupported", f"{expected['id']}@{expected['version']} does not support {protocol_id}@{protocol_version}", "payload/root.flow.json.protocol")

    allowed_types = set(profile.get("state_types") or [])
    allowed_actions = set(profile.get("process_actions") or [])
    allowed_bindings = set(profile.get("binding_sources") or [])
    allowed_transports = set(profile.get("tool_transports") or [])
    states = flow.get("states") if isinstance(flow.get("states"), dict) else {}
    for state_id, state in states.items():
        if not isinstance(state, dict):
            continue
        state_path = f"payload/root.flow.json.states.{state_id}"
        state_type = str(state.get("type") or "")
        if state_type not in allowed_types:
            _runtime_finding(report, "cre_runtime_state_type_unsupported", f"state type {state_type or 'missing'} is not supported by this runtime", f"{state_path}.type")
        if state_type == "process":
            action = str(state.get("action") or "")
            if action not in allowed_actions:
                _runtime_finding(report, "cre_runtime_action_unsupported", f"process action {action or 'missing'} is not supported by this runtime", f"{state_path}.action")
        inputs = state.get("inputs") if isinstance(state.get("inputs"), dict) else {}
        for input_id, input_value in inputs.items():
            input_item = input_value if isinstance(input_value, dict) else {}
            binding = input_item.get("binding") if isinstance(input_item.get("binding"), dict) else None
            if binding is not None and str(binding.get("source") or "") not in allowed_bindings:
                source = str(binding.get("source") or "missing")
                _runtime_finding(report, "cre_runtime_binding_source_unsupported", f"binding source {source} is not supported by this runtime", f"{state_path}.inputs.{input_id}.binding.source")
        for index, tool in enumerate(state.get("tools") if isinstance(state.get("tools"), list) else []):
            transport = str(tool.get("type") or "") if isinstance(tool, dict) else ""
            if transport not in allowed_transports:
                _runtime_finding(report, "cre_runtime_tool_transport_unsupported", f"tool transport {transport or 'missing'} is not supported by this runtime", f"{state_path}.tools[{index}].type")

    allowed_edges = set(profile.get("edge_kinds") or [])
    plan = flow.get("execution_plan") if isinstance(flow.get("execution_plan"), dict) else {}
    edges = plan.get("edges") if isinstance(plan.get("edges"), list) else []
    sequence_counts: dict[str, int] = {}
    graph: dict[str, list[str]] = {}
    for index, edge in enumerate(edges):
        item = edge if isinstance(edge, dict) else {}
        kind = str(item.get("kind") or "")
        source = str(item.get("from") or "")
        target = str(item.get("to") or "")
        if kind not in allowed_edges:
            _runtime_finding(report, "cre_runtime_edge_kind_unsupported", f"edge kind {kind or 'missing'} is not supported by this runtime", f"payload/root.flow.json.execution_plan.edges[{index}].kind")
        if kind == "sequence":
            sequence_counts[source] = sequence_counts.get(source, 0) + 1
        if source and target:
            graph.setdefault(source, []).append(target)
    maximum = int((profile.get("limits") or {}).get("max_sequence_out_degree") or 0)
    for source, count in sequence_counts.items():
        if count > maximum:
            _runtime_finding(report, "cre_runtime_sequence_fanout_unsupported", f"state {source} has {count} sequence exits; this runtime allows at most {maximum}", "payload/root.flow.json.execution_plan.edges")
    if not bool((profile.get("limits") or {}).get("allow_cycles")) and _has_directed_cycle(graph):
        _runtime_finding(report, "cre_runtime_cycle_unsupported", "flow contains a directed cycle, but this runtime only supports acyclic execution plans", "payload/root.flow.json.execution_plan.edges")

    allowed_wire_apis = set(profile.get("model_wire_apis") or [])
    recipe = manifest.get("llm_recipe") if isinstance(manifest.get("llm_recipe"), dict) else {}
    for index, role in enumerate(recipe.get("roles") if isinstance(recipe.get("roles"), list) else []):
        wire_api = str(role.get("wire_api") or "chat_completions") if isinstance(role, dict) else ""
        if wire_api not in allowed_wire_apis:
            _runtime_finding(report, "cre_runtime_model_wire_api_unsupported", f"model wire API {wire_api or 'missing'} is not supported by this runtime", f"payload/manifest.json.llm_recipe.roles[{index}].wire_api")
    ui_mode = str((ui or {}).get("mode") or "none")
    if ui_mode not in set(profile.get("ui_modes") or []):
        _runtime_finding(report, "cre_runtime_ui_mode_unsupported", f"UI mode {ui_mode} is not supported by this runtime", "public/ui.contract.json.mode")
    return report


def build_data_contract_support_report(
    root: str | Path,
    *,
    base: dict | None = None,
    evidence: dict | None = None,
    registry_path: str | Path | None = None,
) -> dict:
    """Prove that every active contract has an exact, tested Base implementation."""
    project_root = Path(root).resolve()
    contract_registry = DataContractRegistry(project_root, registry_path=registry_path)
    contracts = contract_registry.releases(active_only=True)
    base_data = base if base is not None else load_base_implementation(project_root)
    evidence_data = evidence if evidence is not None else _read_json(project_root / EVIDENCE_RELATIVE_PATH)
    evidence_sets = evidence_data.get("evidence_sets") if isinstance(evidence_data, dict) else None
    if not isinstance(evidence_sets, dict):
        raise DataContractError(
            "data_contract_evidence_invalid",
            f"{EVIDENCE_RELATIVE_PATH.as_posix()}.evidence_sets must be an object",
        )

    findings: list[dict] = []
    expected = {(item["contract_id"], item["version"]): item for item in contracts}
    declarations: dict[tuple[str, str], dict] = {}
    for index, declaration in enumerate(base_data.get("supported_data_contracts") or []):
        if not isinstance(declaration, dict):
            _finding(findings, "data_contract_support_invalid", f"support entry {index} must be an object")
            continue
        identity = (str(declaration.get("id") or ""), str(declaration.get("version") or ""))
        if identity in declarations:
            _finding(findings, "data_contract_support_duplicate", f"duplicate Base support declaration: {identity[0]}@{identity[1]}", *identity)
            continue
        declarations[identity] = declaration
        if identity not in expected:
            _finding(findings, "data_contract_support_unknown", f"Base declares an inactive or unknown contract: {identity[0]}@{identity[1]}", *identity)

    test_index = _build_test_index(project_root)
    items: list[dict] = []
    for identity, contract in expected.items():
        contract_id, version = identity
        start = len(findings)
        declaration = declarations.get(identity)
        evidence_id = str((declaration or {}).get("evidence") or "")
        record = evidence_sets.get(evidence_id) if evidence_id else None
        if declaration is None:
            _finding(findings, "data_contract_support_missing", f"Base support is missing: {contract_id}@{version}", contract_id, version)
        elif declaration.get("status") != "supported":
            _finding(findings, "data_contract_support_partial", f"Base support must be supported: {contract_id}@{version}", contract_id, version)
        if not evidence_id:
            _finding(findings, "data_contract_evidence_missing", f"support evidence is missing: {contract_id}@{version}", contract_id, version)
        elif not isinstance(record, dict):
            _finding(findings, "data_contract_evidence_unknown", f"unknown evidence set {evidence_id}: {contract_id}@{version}", contract_id, version)
        else:
            _audit_evidence(project_root, contract_id, version, evidence_id, record, test_index, findings)
        _audit_contract_definition(contract_registry, contract, findings)
        _audit_contract_rules(contract_registry.path, project_root, contract, findings)
        identity_has_findings = any(
            item.get("contract_id") == contract_id and item.get("version") == version
            for item in findings
        )
        items.append(
            {
                "contract_id": contract_id,
                "version": version,
                "layer": contract["layer"],
                "domain": contract["domain"],
                "source_id": contract["source_id"],
                "definition_kind": contract["definition_kind"],
                "evidence": evidence_id or None,
                "status": "supported" if len(findings) == start and not identity_has_findings else "failing",
            }
        )

    return {
        "schema": "cartridgeflow.data_contract_support_report.v1",
        "ok": not findings,
        "summary": {
            "active_releases": len(expected),
            "declared_releases": len(declarations),
            "supported_releases": sum(item["status"] == "supported" for item in items),
            "finding_count": len(findings),
        },
        "items": items,
        "findings": findings,
    }


def assert_base_supports_data_contracts(
    root: str | Path,
    *,
    registry_path: str | Path | None = None,
) -> dict:
    report = build_data_contract_support_report(root, registry_path=registry_path)
    if not report["ok"]:
        first = report["findings"][0]
        raise DataContractError(str(first["code"]), str(first["message"]))
    return report


def _audit_evidence(
    root: Path,
    contract_id: str,
    version: str,
    evidence_id: str,
    record: dict,
    test_index: set[str],
    findings: list[dict],
) -> None:
    if record.get("verification") != "verified":
        _finding(findings, "data_contract_evidence_unverified", f"evidence {evidence_id} is not verified", contract_id, version)
    implementation = record.get("implementation")
    if not isinstance(implementation, list) or not implementation:
        _finding(findings, "data_contract_implementation_missing", f"evidence {evidence_id} has no implementation reference", contract_id, version)
    else:
        for reference in implementation:
            if not _reference_path_exists(root, reference):
                _finding(findings, "data_contract_implementation_ref_missing", f"implementation reference does not exist: {reference}", contract_id, version)
    for field, code in (("positive_tests", "data_contract_positive_test_missing"), ("failure_tests", "data_contract_failure_test_missing")):
        references = record.get(field)
        if not isinstance(references, list) or not references:
            _finding(findings, code, f"evidence {evidence_id} has no {field}", contract_id, version)
            continue
        for reference in references:
            if str(reference) not in test_index:
                _finding(findings, "data_contract_test_ref_missing", f"test reference does not exist: {reference}", contract_id, version)


def _audit_contract_definition(
    registry: DataContractRegistry,
    contract: dict,
    findings: list[dict],
) -> None:
    contract_id = str(contract["contract_id"])
    version = str(contract["version"])
    try:
        text = registry.definition_text(contract_id, version)
        if not text.strip():
            raise DataContractError("data_contract_definition_empty", "definition is empty")
        if contract["definition_kind"] == "json_schema":
            registry.schema(contract_id, version)
        elif contract["definition_kind"] == "machine_contract":
            value = json.loads(text)
            required = {"schema", "id", "version"}
            if not isinstance(value, dict) or not required.issubset(value):
                raise DataContractError("data_contract_machine_definition_invalid", "machine contract requires schema, id, and version")
    except (DataContractError, ProtocolKnowledgeRegistryError, json.JSONDecodeError) as exc:
        _finding(findings, getattr(exc, "code", "data_contract_definition_invalid"), str(exc), contract_id, version)


def _audit_contract_rules(
    registry_path: Path,
    root: Path,
    contract: dict,
    findings: list[dict],
) -> None:
    with ProtocolKnowledgeRegistry(registry_path) as registry:
        rules = registry.connection.execute(
            "SELECT rule_code, validator_ref FROM data_contract_rule WHERE contract_release_key = ?",
            (contract["contract_release_key"],),
        ).fetchall()
    if not rules:
        _finding(findings, "data_contract_rule_missing", "active contract has no executable rule", contract["contract_id"], contract["version"])
    for rule in rules:
        reference = str(rule["validator_ref"] or "")
        if not reference or not _reference_path_exists(root, reference):
            _finding(findings, "data_contract_validator_ref_missing", f"rule {rule['rule_code']} validator does not exist: {reference or '<empty>'}", contract["contract_id"], contract["version"])


def _reference_path_exists(root: Path, reference: object) -> bool:
    path_text, separator, fragment = str(reference or "").partition("#")
    relative = path_text.strip()
    path = root / Path(relative)
    if not relative or not path.is_file():
        return False
    if not separator or not fragment.strip():
        return True
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return all(re.search(rf"\b{re.escape(part)}\b", content) for part in fragment.split(".") if part)


def _build_test_index(root: Path) -> set[str]:
    result: set[str] = set()
    for path in (root / "scripts" / "tests").rglob("test_*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError):
            continue
        module = path.stem
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_"):
                    result.add(f"{module}.{node.name}.{child.name}")
    return result


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataContractError("data_contract_evidence_invalid", f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DataContractError("data_contract_evidence_invalid", f"{path} must contain an object")
    return value


def _finding(
    target: list[dict],
    code: str,
    message: str,
    contract_id: str = "",
    version: str = "",
) -> None:
    target.append(
        {
            "code": code,
            "contract_id": contract_id,
            "version": version,
            "message": message,
        }
    )


def _presentation_error(
    code: str,
    message: str,
    *,
    contract_id: str = "cartridgeflow.capability.settings-binding",
) -> None:
    raise DataContractValidationError(
        code,
        message,
        contract_id=contract_id,
        version="1.0.0",
    )


def _stable_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validated_settings_fields(
    settings: dict,
    *,
    root: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> dict[str, dict]:
    validate_data_contract_instance(
        "cartridgeflow.capability.settings",
        "1.0.0",
        settings,
        root=root,
        registry_path=registry_path,
    )
    fields = settings.get("fields") if isinstance(settings.get("fields"), list) else []
    fields_by_id: dict[str, dict] = {}
    for field in fields:
        field_id = str(field.get("id") or "")
        if field_id in fields_by_id:
            _presentation_error(
                "settings_field_duplicate",
                f"settings field is duplicated: {field_id}",
                contract_id="cartridgeflow.capability.settings",
            )
        fields_by_id[field_id] = field
        if field.get("sensitive") is True and field.get("default") not in (None, ""):
            _presentation_error(
                "settings_sensitive_default_forbidden",
                f"sensitive setting cannot have a non-empty default: {field_id}",
                contract_id="cartridgeflow.capability.settings",
            )
        if field.get("type") == "enum":
            options = field.get("options") if isinstance(field.get("options"), list) else []
            option_values = [item.get("value") for item in options if isinstance(item, dict)]
            if (
                not options
                or len(option_values) != len(options)
                or len(set(map(_stable_value, option_values))) != len(options)
            ):
                _presentation_error(
                    "settings_enum_options_invalid",
                    f"enum setting requires unique non-empty options: {field_id}",
                    contract_id="cartridgeflow.capability.settings",
                )
    return fields_by_id


def _validate_setting_value(field_id: str, field: dict, value: Any) -> None:
    field_type = str(field.get("type") or "")
    valid_type = {
        "string": lambda item: isinstance(item, str),
        "file": lambda item: isinstance(item, str),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "enum": lambda item: True,
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
    }.get(field_type)
    if valid_type is None or not valid_type(value):
        _presentation_error("settings_value_type_invalid", f"setting {field_id} must be {field_type}")
    if field_type == "enum":
        allowed = [item.get("value") for item in field.get("options") or [] if isinstance(item, dict)]
        if value not in allowed:
            _presentation_error("settings_value_enum_invalid", f"setting {field_id} is not an allowed option")
    validation = field.get("validation") if isinstance(field.get("validation"), dict) else {}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in validation and value < validation["minimum"]:
            _presentation_error("settings_value_minimum", f"setting {field_id} is below its minimum")
        if "maximum" in validation and value > validation["maximum"]:
            _presentation_error("settings_value_maximum", f"setting {field_id} is above its maximum")
    if isinstance(value, str):
        if "min_length" in validation and len(value) < validation["min_length"]:
            _presentation_error("settings_value_min_length", f"setting {field_id} is too short")
        if "max_length" in validation and len(value) > validation["max_length"]:
            _presentation_error("settings_value_max_length", f"setting {field_id} is too long")
        pattern = validation.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            _presentation_error("settings_value_pattern", f"setting {field_id} does not match its pattern")


def _runtime_finding(report: dict, code: str, message: str, path: str) -> None:
    report["findings"].append(
        {"severity": "blocker", "code": code, "message": message, "path": path}
    )
    report["ok"] = False
    report["status"] = "blocked"


def _has_directed_cycle(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(target) for target in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)
