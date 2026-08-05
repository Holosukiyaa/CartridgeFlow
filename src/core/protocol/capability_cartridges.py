"""Recursive capability-cartridge contracts for Creator and Developer."""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Iterable

from core.protocol.tuning import canonical_digest


class CapabilityCartridgeError(ValueError):
    """Protocol-level capability or semantic-recipe validation error."""

    def __init__(self, code: str, message: str, *, status: int = 400):
        self.code, self.status = code, status
        super().__init__(message)

    def as_dict(self) -> dict:
        return {"schema": "cartridgeflow.capability_error.v1", "code": self.code, "message": str(self)}


AuthoringServiceError = CapabilityCartridgeError


CAPABILITY_RELEASE_SCHEMA = "cartridgeflow.capability_cartridge_release.v1"
SEMANTIC_RECIPE_SCHEMA = "cartridgeflow.semantic_creator_recipe.v2"
CAPABILITY_PROTOCOL = {"id": "CF-TUNING", "version": "1.5"}
TRUST_SCOPES = frozenset({"system", "organization", "workspace"})
FIELD_TYPES = frozenset({"string", "string_list", "boolean", "number"})
RELATIONS = frozenset({"uses", "produces", "informs"})
MAX_SOURCE_FILE_BYTES = 4 * 1024 * 1024
_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,119}$")
_FIELD_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,119}$")
_UNSAFE_PATH = re.compile(
    r"token|secret|password|credential|api[_-]?key|authorization|cookie|private[_-]?key|"
    r"code|script|command|executor|permission|topology|execution[_-]?plan|endpoint|model|tool",
    re.I,
)


def validate_capability_release(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != CAPABILITY_RELEASE_SCHEMA:
        raise AuthoringServiceError("CAPABILITY_RELEASE_INVALID", "Capability release schema is invalid.")
    body = {key: deepcopy(item) for key, item in value.items() if key != "digest"}
    if value.get("digest") != canonical_digest(body):
        raise AuthoringServiceError("CAPABILITY_RELEASE_INTEGRITY_INVALID", "Capability release integrity check failed.")
    if value.get("protocol") != CAPABILITY_PROTOCOL:
        raise AuthoringServiceError("CAPABILITY_RELEASE_PROTOCOL_INVALID", "Capability release must declare CF-TUNING@1.5.")
    if not _valid_id(value.get("id")) or not isinstance(value.get("revision"), int) or value["revision"] < 1:
        raise AuthoringServiceError("CAPABILITY_RELEASE_IDENTITY_INVALID", "Capability release identity or revision is invalid.")
    if value.get("trust_scope") not in TRUST_SCOPES:
        raise AuthoringServiceError("CAPABILITY_RELEASE_TRUST_SCOPE_INVALID", "Capability trust scope is invalid.")
    creator = value.get("creator")
    if not isinstance(creator, dict) or not _text(creator.get("label"), 200) or not _text(creator.get("description"), 1000):
        raise AuthoringServiceError("CAPABILITY_RELEASE_CREATOR_CONTRACT_INVALID", "Capability Creator contract is incomplete.")
    _validate_fields(creator.get("editable_fields"))
    interface = value.get("interface")
    if not isinstance(interface, dict):
        raise AuthoringServiceError("CAPABILITY_RELEASE_INTERFACE_INVALID", "Capability public interface is missing.")
    _validate_ports(interface.get("inputs"), "input")
    normalized_outputs = _validate_ports(interface.get("outputs"), "output")
    implementation = value.get("implementation")
    if not isinstance(implementation, dict) or implementation.get("kind") not in {"flow", "node_snapshot"}:
        raise AuthoringServiceError("CAPABILITY_RELEASE_IMPLEMENTATION_INVALID", "Capability implementation is invalid.")
    if implementation["kind"] == "flow":
        if not isinstance(implementation.get("manifest"), dict) or not isinstance(implementation.get("root_flow"), dict):
            raise AuthoringServiceError("CAPABILITY_RELEASE_IMPLEMENTATION_INVALID", "Flow capability must carry its manifest and Root Flow.")
        boundary = validate_flow_capability_boundary(implementation["root_flow"], implementation["manifest"])
        _validate_capability_outputs(implementation["root_flow"], boundary, normalized_outputs)
        files = implementation.get("files")
        if not isinstance(files, dict) or any(
            not _safe_source_path(path)
            or not isinstance(content, str) or len(content.encode("utf-8")) > MAX_SOURCE_FILE_BYTES
            for path, content in files.items()
        ):
            raise AuthoringServiceError("CAPABILITY_RELEASE_FILES_INVALID", "Capability-owned files must be safe UTF-8 package-relative files.")
        bindings = implementation.get("creator_bindings")
        field_ids = {item["id"] for item in creator["editable_fields"]}
        if not isinstance(bindings, dict) or set(bindings) != field_ids:
            raise AuthoringServiceError("CAPABILITY_RELEASE_BINDINGS_INVALID", "Every Creator field must map to one internal Flow parameter.")
        for field_id, path in bindings.items():
            if not _valid_creator_path(path) or not _path_exists(implementation["root_flow"], path):
                raise AuthoringServiceError("CAPABILITY_RELEASE_BINDING_PATH_INVALID", f"Creator field {field_id} has an invalid internal binding.")
            field = next(item for item in creator["editable_fields"] if item["id"] == field_id)
            if not _value_matches(_path_value(implementation["root_flow"], path), field["value_type"]):
                raise AuthoringServiceError("CAPABILITY_RELEASE_BINDING_TYPE_INVALID", f"Creator field {field_id} does not match its internal parameter type.")
    dependencies = value.get("dependencies")
    if not isinstance(dependencies, list):
        raise AuthoringServiceError("CAPABILITY_RELEASE_DEPENDENCIES_INVALID", "Capability dependencies must be a list.")
    for dependency in dependencies:
        if not _valid_release_ref(dependency):
            raise AuthoringServiceError("CAPABILITY_RELEASE_DEPENDENCY_INVALID", "Capability dependency reference is invalid.")
    evidence = value.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("status") != "passed" or not evidence.get("source_digest"):
        raise AuthoringServiceError("CAPABILITY_RELEASE_EVIDENCE_REQUIRED", "A capability must pass validation before it can become trusted.")
    return deepcopy(value)


def validate_flow_capability_boundary(root_flow: dict, manifest: dict | None = None) -> dict:
    """Require one reachable success boundary and no orphan executable states."""
    states = root_flow.get("states") if isinstance(root_flow, dict) else None
    plan = root_flow.get("execution_plan") if isinstance(root_flow, dict) else None
    if not isinstance(states, dict) or not states or not isinstance(plan, dict) or plan.get("schema") != "cartridgeflow.execution_plan.v1":
        raise AuthoringServiceError("CAPABILITY_FLOW_BOUNDARY_INVALID", "Capability Flow must use an execution-plan Root Flow.")
    entry = str(plan.get("entry") or "")
    if entry not in states:
        raise AuthoringServiceError("CAPABILITY_FLOW_BOUNDARY_INVALID", "Capability Flow entry is invalid.")
    raw_edges = plan.get("edges")
    if not isinstance(raw_edges, list) or not raw_edges:
        raise AuthoringServiceError("CAPABILITY_FLOW_BOUNDARY_INVALID", "Capability Flow must contain a connected execution path.")
    edges = []
    for edge in raw_edges:
        source = str(edge.get("from") or "") if isinstance(edge, dict) else ""
        target = str(edge.get("to") or "") if isinstance(edge, dict) else ""
        if source not in states or target not in states or source == target:
            raise AuthoringServiceError("CAPABILITY_FLOW_BOUNDARY_INVALID", "Capability Flow contains an invalid execution edge.")
        edges.append((source, target, str(edge.get("kind") or "sequence")))
    failure_targets = {target for _, target, kind in edges if kind == "failure"}
    success_terminals = [
        state_id for state_id, state in states.items()
        if isinstance(state, dict) and state.get("type") == "terminal" and state_id not in failure_targets
    ]
    if len(success_terminals) != 1:
        raise AuthoringServiceError("CAPABILITY_FLOW_SUCCESS_BOUNDARY_INVALID", "Capability Flow must expose exactly one successful exit.")
    reachable = {entry}
    success_reachable = {entry}
    changed = True
    while changed:
        changed = False
        for source, target, kind in edges:
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
            if kind != "failure" and source in success_reachable and target not in success_reachable:
                success_reachable.add(target)
                changed = True
    if success_terminals[0] not in success_reachable:
        raise AuthoringServiceError("CAPABILITY_FLOW_SUCCESS_PATH_MISSING", "Capability Flow has no reachable successful exit.")
    can_reach_success = {success_terminals[0]}
    changed = True
    while changed:
        changed = False
        for source, target, kind in edges:
            if kind != "failure" and target in can_reach_success and source not in can_reach_success:
                can_reach_success.add(source)
                changed = True
    executable_states = sorted(
        state_id for state_id, state in states.items()
        if (
            isinstance(state, dict)
            and state.get("type") not in {"control", "system", "terminal"}
            and state_id in success_reachable
            and state_id in can_reach_success
        )
    )
    if not executable_states:
        raise AuthoringServiceError("CAPABILITY_FLOW_EXECUTION_MISSING", "Capability Flow must execute at least one real state before its successful exit.")
    manifest_tool_ids = {
        str(item.get("id") or "")
        for item in ((manifest or {}).get("mcp_tools") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for state_id in executable_states:
        state = states[state_id]
        action = str(state.get("action") or "").strip()
        if not action:
            raise AuthoringServiceError("CAPABILITY_FLOW_ACTION_MISSING", f"Capability executable state has no runtime action: {state_id}.")
        if action not in {"tool_call", "remote_call"}:
            continue
        params = state.get("params") if isinstance(state.get("params"), dict) else {}
        preset = params.get("preset_config") if isinstance(params.get("preset_config"), dict) else {}
        inline_tools = params.get("tools") if isinstance(params.get("tools"), list) else state.get("tools") if isinstance(state.get("tools"), list) else []
        has_inline_tool = any(
            isinstance(item, dict) and (item.get("mcp_tool_id") or (item.get("server") and item.get("tool")))
            for item in inline_tools
        )
        declared_ids = {
            str(item)
            for item in (
                state.get("allowed_tools")
                or ((state.get("mcp_binding") or {}).get("allowed_tools") if isinstance(state.get("mcp_binding"), dict) else [])
                or []
            )
            if str(item)
        }
        has_declared_tool = bool(declared_ids & manifest_tool_ids)
        has_param_tool = bool(
            params.get("mcp_tool_id")
            or preset.get("mcp_tool_id")
            or ((params.get("server") or preset.get("server")) and (params.get("tool") or preset.get("tool")))
        )
        if not (has_inline_tool or has_declared_tool or has_param_tool):
            raise AuthoringServiceError("CAPABILITY_FLOW_TOOL_BINDING_MISSING", f"Capability tool state has no callable tool binding: {state_id}.")
        endpoint = str(state.get("endpoint") or params.get("endpoint") or "").strip().casefold()
        if action == "remote_call" and (not endpoint or endpoint.endswith("pending")):
            raise AuthoringServiceError("CAPABILITY_FLOW_REMOTE_TARGET_MISSING", f"Capability remote state has no configured target: {state_id}.")
    orphaned = sorted(
        state_id for state_id, state in states.items()
        if isinstance(state, dict) and state.get("type") not in {"terminal"} and state_id not in reachable
    )
    if orphaned:
        raise AuthoringServiceError("CAPABILITY_FLOW_ORPHANED_STATE", f"Capability Flow contains unreachable executable states: {', '.join(orphaned)}.")
    return {"valid": True, "entry": entry, "success_exit": success_terminals[0], "executable_states": executable_states}


def _validate_capability_outputs(root_flow: dict, boundary: dict, outputs: list[dict]) -> None:
    produced_store_keys = {
        str((output.get("target") or {}).get("key") or "")
        for state_id in boundary["executable_states"]
        for output in ((root_flow.get("states") or {}).get(state_id, {}).get("outputs") or {}).values()
        if isinstance(output, dict) and isinstance(output.get("target"), dict) and output["target"].get("type") == "store"
    }
    missing_outputs = sorted(port["store_key"] for port in outputs if port["store_key"] not in produced_store_keys)
    if missing_outputs:
        raise AuthoringServiceError(
            "CAPABILITY_RELEASE_OUTPUT_UNPRODUCED",
            f"Capability public outputs are not produced on its successful path: {', '.join(missing_outputs)}.",
        )


def build_flow_capability_release(
    *, capability_id: str, revision: int, trust_scope: str, label: str, description: str,
    match_terms: list[str], editable_fields: list[dict], creator_bindings: dict[str, str],
    public_inputs: list[dict], public_outputs: list[dict], dependencies: list[dict],
    source_flow_id: str, manifest: dict, root_flow: dict, evidence: dict,
    source_files: dict[str, str] | None = None,
) -> dict:
    if not _valid_id(capability_id):
        raise AuthoringServiceError("CAPABILITY_RELEASE_IDENTITY_INVALID", "Capability id must use lowercase letters, numbers, dots, dashes, or underscores.")
    normalized_fields = _validate_fields(editable_fields)
    normalized_inputs = _validate_ports(public_inputs, "input")
    normalized_outputs = _validate_ports(public_outputs, "output")
    boundary = validate_flow_capability_boundary(root_flow, manifest)
    _validate_capability_outputs(root_flow, boundary, normalized_outputs)
    normalized_terms = sorted({_text(item, 120) for item in match_terms if _text(item, 120)}, key=str.casefold)
    normalized_files = {str(key): str(value) for key, value in sorted((source_files or {}).items())}
    source_digest = canonical_digest({"manifest": manifest, "root_flow": root_flow, "files": normalized_files})
    evidence_body = {
        "schema": "cartridgeflow.capability_validation_evidence.v1",
        "status": str(evidence.get("status") or ""),
        "source_digest": source_digest,
        "checks": deepcopy(evidence.get("checks") or []),
    }
    release = {
        "schema": CAPABILITY_RELEASE_SCHEMA,
        "protocol": deepcopy(CAPABILITY_PROTOCOL),
        "id": capability_id,
        "revision": revision,
        "trust_scope": trust_scope,
        "creator": {
            "label": _text(label, 200),
            "description": _text(description, 1000),
            "match_terms": normalized_terms,
            "editable_fields": normalized_fields,
        },
        "interface": {"inputs": normalized_inputs, "outputs": normalized_outputs},
        "implementation": {
            "kind": "flow",
            "source": {"flow_id": _text(source_flow_id, 200), "digest": source_digest},
            "manifest": deepcopy(manifest),
            "root_flow": deepcopy(root_flow),
            "creator_bindings": {str(key): str(value) for key, value in sorted(creator_bindings.items())},
            "files": normalized_files,
        },
        "dependencies": [deepcopy(item) for item in dependencies],
        "evidence": evidence_body,
    }
    release["digest"] = canonical_digest(release)
    return validate_capability_release(release)


def legacy_node_capability(publication: dict, *, trust_scope: str = "workspace") -> dict:
    """Expose CF-TUNING@1.4 publications through the recursive registry."""
    preset = deepcopy(publication["preset"])
    mapping = deepcopy(publication["mapping"])
    release = {
        "schema": CAPABILITY_RELEASE_SCHEMA,
        "protocol": deepcopy(CAPABILITY_PROTOCOL),
        "id": preset["id"],
        "revision": preset["revision"],
        "trust_scope": trust_scope,
        "creator": {
            "label": preset["creator_label"],
            "description": preset["creator_description"],
            "match_terms": deepcopy(preset["match_terms"]),
            "editable_fields": deepcopy(preset["editable_fields"]),
        },
        "interface": {"inputs": [], "outputs": []},
        "implementation": {
            "kind": "node_snapshot",
            "preset": preset,
            "mapping": mapping,
            "source": deepcopy(mapping["source"]),
        },
        "dependencies": [],
        "evidence": {
            "schema": "cartridgeflow.capability_validation_evidence.v1",
            "status": "passed",
            "source_digest": mapping["digest"],
            "checks": [{"id": "legacy_trusted_publication", "status": "passed"}],
        },
    }
    release["digest"] = canonical_digest(release)
    return validate_capability_release(release)


def creator_capability_projection(release: dict) -> dict:
    item = validate_capability_release(release)
    return {
        "id": item["id"],
        "revision": item["revision"],
        "digest": item["digest"],
        "trust_scope": item["trust_scope"],
        "label": item["creator"]["label"],
        "description": item["creator"]["description"],
        "match_terms": deepcopy(item["creator"]["match_terms"]),
        "editable_fields": deepcopy(item["creator"]["editable_fields"]),
        "inputs": [{key: port[key] for key in ("id", "label", "required", "schema") if key in port} for port in item["interface"]["inputs"]],
        "outputs": [{key: port[key] for key in ("id", "label", "required", "schema") if key in port} for port in item["interface"]["outputs"]],
    }


def create_semantic_recipe(recipe_id: str, goal: str, raw: dict, capabilities: list[dict]) -> tuple[dict, dict[str, dict]]:
    if not isinstance(raw, dict) or set(raw) != {"nodes", "relations"}:
        raise AuthoringServiceError("SEMANTIC_RECIPE_INVALID", "Semantic recipe must contain nodes and relations.")
    nodes = raw.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 8:
        raise AuthoringServiceError("SEMANTIC_RECIPE_INVALID", "Semantic recipe must contain one to eight nodes.")
    available = {item["id"]: validate_capability_release(item) for item in capabilities}
    normalized_nodes = []
    publications: dict[str, dict] = {}
    ids: set[str] = set()
    for index, raw_node in enumerate(nodes):
        if not isinstance(raw_node, dict):
            raise AuthoringServiceError("SEMANTIC_RECIPE_INVALID", "Semantic recipe node is invalid.")
        node_id = _text(raw_node.get("id"), 120)
        if not _FIELD_ID.fullmatch(node_id) or node_id in ids:
            raise AuthoringServiceError("SEMANTIC_RECIPE_INVALID", "Semantic recipe node ids must be unique and stable.")
        ids.add(node_id)
        label = _text(raw_node.get("label"), 200)
        description = _text(raw_node.get("description"), 1000)
        need = _text(raw_node.get("needed_capability") or description or label, 1000)
        if not label or not description or not need:
            raise AuthoringServiceError("SEMANTIC_RECIPE_INVALID", "Each semantic node needs a label, description, and capability requirement.")
        explicit = _text(raw_node.get("capability_id"), 120)
        release = available.get(explicit) if explicit else _best_match(f"{label} {description} {need}", available.values())
        fields = release["creator"]["editable_fields"] if release else _unresolved_fields(need)
        values = _normalize_values(fields, raw_node.get("values") if isinstance(raw_node.get("values"), dict) else {}, require_required=False)
        if release:
            publications[node_id] = release
        normalized_nodes.append({
            "id": node_id,
            "creator_label": label,
            "creator_description": description,
            "needed_capability": need,
            "values": values,
            "capability": _release_ref(release) if release else None,
            "order": index,
        })
    relations = _validate_relations(raw.get("relations"), ids)
    recipe = {
        "schema": SEMANTIC_RECIPE_SCHEMA,
        "protocol": deepcopy(CAPABILITY_PROTOCOL),
        "id": _text(recipe_id, 200),
        "goal": _text(goal, 2000),
        "nodes": normalized_nodes,
        "relations": relations,
    }
    recipe["digest"] = canonical_digest(recipe)
    return recipe, publications


def resolve_semantic_recipe(
    recipe: dict,
    capabilities: list[dict],
    *,
    rejected_capability_digests: dict[str, set[str]] | None = None,
) -> tuple[dict, dict[str, dict], list[str]]:
    current = deepcopy(recipe)
    available = {item["id"]: validate_capability_release(item) for item in capabilities}
    rejected_capability_digests = rejected_capability_digests or {}
    publications: dict[str, dict] = {}
    resolved: list[str] = []
    for node in current.get("nodes") or []:
        rejected = rejected_capability_digests.get(node["id"], set())
        ref = node.get("capability")
        release = available.get(str((ref or {}).get("id") or ""))
        if release and release["digest"] not in rejected and _release_ref(release) == ref:
            publications[node["id"]] = release
            continue
        release = _best_match(
            f"{node.get('creator_label', '')} {node.get('creator_description', '')} {node.get('needed_capability', '')}",
            (item for item in available.values() if item["digest"] not in rejected),
        )
        node["capability"] = _release_ref(release) if release else None
        if release:
            publications[node["id"]] = release
            resolved.append(node["id"])
            node["values"] = _normalize_values(release["creator"]["editable_fields"], node.get("values") or {}, require_required=False)
    current["digest"] = canonical_digest({key: value for key, value in current.items() if key != "digest"})
    return current, publications, resolved


def semantic_recipe_projection(recipe: dict, publications: dict[str, dict], bindings: dict) -> dict:
    nodes = []
    for node in sorted(recipe["nodes"], key=lambda item: item.get("order", 0)):
        release = publications.get(node["id"])
        fields = release["creator"]["editable_fields"] if release else _unresolved_fields(node["needed_capability"])
        nodes.append({
            "id": node["id"],
            "label": node["creator_label"],
            "description": node["creator_description"],
            "values": deepcopy(bindings.get(node["id"], node.get("values") or {})),
            "editable_fields": deepcopy(fields),
            "resolution": {
                "status": "resolved" if release else "unresolved",
                "needed_capability": node["needed_capability"],
                **({"capability": creator_capability_projection(release)} if release else {}),
            },
        })
    return {"id": recipe["id"], "goal": recipe["goal"], "nodes": nodes, "relations": deepcopy(recipe["relations"])}


def validate_values_for_node(node: dict, release: dict | None, values: object) -> dict:
    fields = release["creator"]["editable_fields"] if release else _unresolved_fields(node["needed_capability"])
    return _normalize_values(fields, values, require_required=False)


def _best_match(text: str, releases: Iterable[dict]) -> dict | None:
    haystack = " ".join(str(text).casefold().split())
    scored: list[tuple[int, str, dict]] = []
    for release in releases:
        terms = [release["creator"]["label"], *release["creator"].get("match_terms", [])]
        normalized_terms = [str(term).casefold().strip() for term in terms]
        score = sum(max(1, len(term) // 4) for term in normalized_terms if term and term in haystack)
        if score:
            scored.append((score, release["id"], release))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return deepcopy(scored[0][2])


def _release_ref(release: dict | None) -> dict | None:
    if release is None:
        return None
    return {key: release[key] for key in ("id", "revision", "digest", "trust_scope")}


def _unresolved_fields(need: str) -> list[dict]:
    return [{"id": "instructions", "label": "需求说明", "value_type": "string", "required": True, "default": need}]


def _validate_fields(value: object) -> list[dict]:
    if not isinstance(value, list) or len(value) > 24:
        raise AuthoringServiceError("CAPABILITY_RELEASE_FIELDS_INVALID", "Creator editable fields are invalid.")
    result = []
    ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise AuthoringServiceError("CAPABILITY_RELEASE_FIELDS_INVALID", "Creator editable field is invalid.")
        field_id = _text(raw.get("id"), 120)
        field_type = str(raw.get("value_type") or "")
        if not _FIELD_ID.fullmatch(field_id) or field_id in ids or field_type not in FIELD_TYPES:
            raise AuthoringServiceError("CAPABILITY_RELEASE_FIELDS_INVALID", "Creator editable field identity or type is invalid.")
        ids.add(field_id)
        item = {
            "id": field_id,
            "label": _text(raw.get("label"), 200),
            "value_type": field_type,
            "required": bool(raw.get("required")),
            "default": deepcopy(raw.get("default")),
        }
        if not item["label"] or not _value_matches(item["default"], field_type):
            raise AuthoringServiceError("CAPABILITY_RELEASE_FIELDS_INVALID", f"Creator field {field_id} has an invalid default.")
        result.append(item)
    return result


def _validate_ports(value: object, kind: str) -> list[dict]:
    if not isinstance(value, list) or len(value) > 24:
        raise AuthoringServiceError("CAPABILITY_RELEASE_INTERFACE_INVALID", f"Capability {kind} ports are invalid.")
    result = []
    ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise AuthoringServiceError("CAPABILITY_RELEASE_INTERFACE_INVALID", f"Capability {kind} port is invalid.")
        port_id = _text(raw.get("id"), 120)
        store_key = _text(raw.get("store_key"), 200)
        schema = raw.get("schema")
        if not _FIELD_ID.fullmatch(port_id) or port_id in ids or not store_key or not isinstance(schema, dict):
            raise AuthoringServiceError("CAPABILITY_RELEASE_INTERFACE_INVALID", f"Capability {kind} port contract is incomplete.")
        ids.add(port_id)
        result.append({
            "id": port_id,
            "label": _text(raw.get("label") or port_id, 200),
            "required": bool(raw.get("required", kind == "input")),
            "schema": deepcopy(schema),
            "store_key": store_key,
        })
    return result


def _validate_relations(value: object, node_ids: set[str]) -> list[dict]:
    if not isinstance(value, list):
        raise AuthoringServiceError("SEMANTIC_RECIPE_INVALID", "Semantic relations must be a list.")
    result = []
    ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise AuthoringServiceError("SEMANTIC_RECIPE_INVALID", "Semantic relation is invalid.")
        relation_id = _text(raw.get("id"), 120)
        source = _text(raw.get("from_node_id"), 120)
        target = _text(raw.get("to_node_id"), 120)
        relation = str(raw.get("relation") or "")
        if not _FIELD_ID.fullmatch(relation_id) or relation_id in ids or source not in node_ids or target not in node_ids or source == target or relation not in RELATIONS:
            raise AuthoringServiceError("SEMANTIC_RECIPE_INVALID", "Semantic relation contract is invalid.")
        ids.add(relation_id)
        result.append({"id": relation_id, "from_node_id": source, "to_node_id": target, "relation": relation})
    return result


def _normalize_values(fields: list[dict], value: object, *, require_required: bool) -> dict:
    incoming = value if isinstance(value, dict) else {}
    allowed = {item["id"]: item for item in fields}
    result = {}
    for field_id, field in allowed.items():
        selected = incoming.get(field_id, field["default"])
        if selected is None and not field["required"]:
            continue
        if not _value_matches(selected, field["value_type"]):
            selected = deepcopy(field["default"])
        if require_required and field["required"] and selected in {None, ""}:
            raise AuthoringServiceError("SEMANTIC_NODE_VALUE_REQUIRED", f"Creator field {field_id} is required.")
        result[field_id] = deepcopy(selected)
    return result


def _valid_release_ref(value: object) -> bool:
    return isinstance(value, dict) and _valid_id(value.get("id")) and isinstance(value.get("revision"), int) and value["revision"] > 0 and isinstance(value.get("digest"), str)


def _valid_creator_path(path: object) -> bool:
    value = str(path or "")
    parts = value.split(".")
    if len(parts) < 4 or parts[0] != "states" or parts[2] != "params" or not _FIELD_ID.fullmatch(parts[1]):
        return False
    if any(not (_FIELD_ID.fullmatch(part) or part.isdigit()) for part in parts[3:]) or parts[-1].isdigit():
        return False
    if "tools" in parts[3:]:
        if len(parts) < 7 or parts[3] != "tools" or not parts[4].isdigit() or parts[5] != "params":
            return False
        editable_parts = parts[6:]
    else:
        editable_parts = parts[3:]
    return bool(editable_parts) and not _UNSAFE_PATH.search(".".join(editable_parts))


def _safe_source_path(path: object) -> bool:
    if not isinstance(path, str) or not path or "\\" in path or ":" in path or len(path) > 500:
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} and len(part) <= 255 for part in parts)


def _path_exists(value: dict, path: str) -> bool:
    current: object = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False
    return True


def _path_value(value: dict, path: str) -> object:
    current: object = value
    for part in path.split("."):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _value_matches(value: object, field_type: str) -> bool:
    if field_type == "string":
        return isinstance(value, str)
    if field_type == "string_list":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if field_type == "boolean":
        return isinstance(value, bool)
    if field_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False
