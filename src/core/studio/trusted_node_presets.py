"""Atomic Developer-owned storage for executable trusted-node revisions."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from threading import RLock

from core.protocol.trusted_node_recipes import creator_preset_projection, preset_digest, validate_preset
from core.protocol.tuning import TuningProtocolError, canonical_digest
from core.studio.authoring_service import AuthoringServiceError


MAPPING_SCHEMA = "cartridgeflow.trusted_node_mapping.v1"
PUBLICATION_SCHEMA = "cartridgeflow.trusted_node_publication.v1"
_STATE_TOPOLOGY_FIELDS = {"id", "next", "x", "y", "position", "scope", "entry_kind", "locked"}
_LOCAL_ASSET_ACTIONS = {"render_interaction", "render_template", "show_ui", "show_welcome", "render_ui", "show_result", "custom_action"}
_MANIFEST_REQUIREMENT_FIELDS = {
    "inputs", "outputs", "permissions", "mcp_tools", "resource_requirements",
    "llm_recipe", "artifacts", "delivery",
}
_UNSAFE_CREATOR_PARAMETER = re.compile(
    r"token|secret|password|credential|api[_-]?key|authorization|cookie|private[_-]?key|"
    r"code|script|command|executor|permission|topology|execution[_-]?plan|endpoint|model|tool",
    re.I,
)


def build_trusted_node_mapping(
    preset: dict,
    state: dict,
    *,
    source_flow_id: str,
    source_node_id: str,
    creator_bindings: dict[str, str],
    source_manifest: dict | None = None,
) -> dict:
    """Create a portable, topology-free snapshot from one Developer process node."""
    item = validate_preset(preset)
    if not isinstance(state, dict) or state.get("type") != "process":
        raise AuthoringServiceError(
            "TRUSTED_NODE_MAPPING_NODE_INVALID",
            "Only executable process nodes can be published as trusted capabilities.",
        )
    template = deepcopy(state)
    for field in _STATE_TOPOLOGY_FIELDS:
        template.pop(field, None)
    for field in ("action", "kind", "executor", "effect"):
        if not isinstance(template.get(field), str) or not template[field].strip():
            raise AuthoringServiceError(
                "TRUSTED_NODE_MAPPING_NODE_INVALID",
                f"Trusted process node must declare {field}.",
            )
    from core.lab.node_executor import SUPPORTED_ACTIONS
    if template["action"] not in SUPPORTED_ACTIONS:
        raise AuthoringServiceError(
            "TRUSTED_NODE_MAPPING_ACTION_UNSUPPORTED",
            "The Developer node action is not supported by the current Base runtime.",
        )
    if template["action"] in _LOCAL_ASSET_ACTIONS or template.get("component_ref"):
        raise AuthoringServiceError(
            "TRUSTED_NODE_MAPPING_RESOURCE_UNSUPPORTED",
            "Nodes that depend on package-local UI assets cannot yet be published as reusable trusted capabilities.",
        )
    if template.get("action_routes") or _contains_key(template, "target_node"):
        raise AuthoringServiceError(
            "TRUSTED_NODE_MAPPING_TOPOLOGY_UNSUPPORTED",
            "A single trusted node cannot publish action routes to nodes outside its snapshot.",
        )
    if not str(source_flow_id or "").strip() or not str(source_node_id or "").strip():
        raise AuthoringServiceError("TRUSTED_NODE_MAPPING_SOURCE_INVALID", "Trusted node mapping must identify its Developer source node.")

    fields = {field["id"]: field for field in item["editable_fields"]}
    field_ids = set(fields)
    if not isinstance(creator_bindings, dict) or set(creator_bindings) != field_ids:
        raise AuthoringServiceError(
            "TRUSTED_NODE_MAPPING_BINDINGS_INVALID",
            "Every Creator-editable field must bind to exactly one Developer parameter.",
        )
    normalized_bindings: dict[str, str] = {}
    for field_id in sorted(field_ids):
        path = str(creator_bindings.get(field_id) or "").strip()
        if not path.startswith("params.") or not _valid_path(path) or _UNSAFE_CREATOR_PARAMETER.search(path) or not _path_exists(template, path):
            raise AuthoringServiceError(
                "TRUSTED_NODE_MAPPING_BINDING_PATH_INVALID",
                f"Creator field {field_id} must bind to an existing params.* path.",
            )
        if not _value_matches_type(_get_path(template, path), fields[field_id]["value_type"]):
            raise AuthoringServiceError(
                "TRUSTED_NODE_MAPPING_BINDING_TYPE_INVALID",
                f"Creator field {field_id} does not match its Developer parameter type.",
            )
        normalized_bindings[field_id] = path
    if len(set(normalized_bindings.values())) != len(normalized_bindings):
        raise AuthoringServiceError(
            "TRUSTED_NODE_MAPPING_BINDINGS_INVALID",
            "Creator-editable fields cannot target the same Developer parameter.",
        )

    manifest = source_manifest if isinstance(source_manifest, dict) else {}
    requirements = _requirements_for_state(manifest, template)
    mapping = {
        "schema": MAPPING_SCHEMA,
        "key": item["developer_mapping_key"],
        "source": {"flow_id": source_flow_id, "node_id": source_node_id},
        "state_template": template,
        "creator_bindings": normalized_bindings,
        "requirements": requirements,
    }
    mapping["digest"] = canonical_digest(mapping)
    return mapping


def validate_trusted_node_mapping(mapping: dict, preset: dict) -> dict:
    """Validate a stored mapping and its binding boundary before every use."""
    item = validate_preset(preset)
    if not isinstance(mapping, dict) or mapping.get("schema") != MAPPING_SCHEMA:
        raise AuthoringServiceError("TRUSTED_NODE_MAPPING_INVALID", "Trusted node mapping schema is invalid.")
    if mapping.get("key") != item["developer_mapping_key"]:
        raise AuthoringServiceError("TRUSTED_NODE_MAPPING_KEY_MISMATCH", "Preset and Developer mapping identities differ.")
    digest = mapping.get("digest")
    body = {key: deepcopy(value) for key, value in mapping.items() if key != "digest"}
    if digest != canonical_digest(body):
        raise AuthoringServiceError("TRUSTED_NODE_MAPPING_INTEGRITY_INVALID", "Trusted node mapping integrity check failed.")
    rebuilt = build_trusted_node_mapping(
        item,
        body.get("state_template"),
        source_flow_id=str((body.get("source") or {}).get("flow_id") or ""),
        source_node_id=str((body.get("source") or {}).get("node_id") or ""),
        creator_bindings=body.get("creator_bindings"),
        source_manifest=body.get("requirements"),
    )
    if rebuilt != mapping:
        raise AuthoringServiceError("TRUSTED_NODE_MAPPING_INVALID", "Trusted node mapping is not canonical.")
    return deepcopy(mapping)


def materialize_trusted_node_state(mapping: dict, preset: dict, values: dict) -> dict:
    """Apply Creator-safe values to a previously validated Developer snapshot."""
    normalized = validate_trusted_node_mapping(mapping, preset)
    state = deepcopy(normalized["state_template"])
    for field_id, path in normalized["creator_bindings"].items():
        if field_id not in values:
            raise AuthoringServiceError(
                "TRUSTED_NODE_MAPPING_VALUE_MISSING",
                f"Creator value is missing for {field_id}.",
            )
        _set_path(state, path, deepcopy(values[field_id]))
    state["trusted_mapping"] = {
        "key": normalized["key"],
        "digest": normalized["digest"],
        "preset_id": preset["id"],
        "preset_revision": preset["revision"],
    }
    return state


class TrustedNodePresetStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def put(self, preset: dict, mapping: dict, *, expected_revision: int | None = None) -> dict:
        try:
            item = validate_preset(preset)
        except TuningProtocolError as exc:
            raise AuthoringServiceError("TRUSTED_NODE_PRESET_INVALID", str(exc)) from exc
        executable_mapping = validate_trusted_node_mapping(mapping, item)
        with self._lock:
            path = self._path(item["id"])
            state = self._read(path) if path.exists() else None
            current = state["current"]["preset"]["revision"] if state else 0
            if expected_revision is not None and expected_revision != current:
                raise AuthoringServiceError("TRUSTED_NODE_PRESET_REVISION_CONFLICT", "Trusted node preset revision is stale.", status=409)
            if item["revision"] != current + 1:
                raise AuthoringServiceError("TRUSTED_NODE_PRESET_REVISION_INVALID", "Trusted node preset revision must advance by one.", status=409)
            published_preset = {**deepcopy(item), "digest": preset_digest(item)}
            publication = {
                "schema": PUBLICATION_SCHEMA,
                "preset": published_preset,
                "mapping": executable_mapping,
            }
            publication["digest"] = canonical_digest(publication)
            revisions = [*(state["revisions"] if state else []), publication]
            body = {
                "schema": "cartridgeflow.trusted_node_registry_entry.v2",
                "id": item["id"],
                "current": publication,
                "revisions": revisions,
            }
            body["digest"] = canonical_digest(body)
            self._write(path, body)
            return deepcopy(publication)

    def list_developer(self) -> list[dict]:
        """Return protocol presets only, for AI composition and mapping-free callers."""
        with self._lock:
            return [deepcopy(self._read(path)["current"]["preset"]) for path in sorted(self.root.glob("*.json"))]

    def list_published(self) -> list[dict]:
        with self._lock:
            return [deepcopy(self._read(path)["current"]) for path in sorted(self.root.glob("*.json"))]

    def list_creator(self) -> list[dict]:
        return [creator_preset_projection(item) for item in self.list_developer()]

    def get(self, preset_id: str, revision: int | None = None) -> dict:
        return deepcopy(self.get_publication(preset_id, revision)["preset"])

    def get_publication(self, preset_id: str, revision: int | None = None) -> dict:
        with self._lock:
            path = self._path(preset_id)
            if not path.exists():
                raise AuthoringServiceError("TRUSTED_NODE_PRESET_UNKNOWN", "Trusted node preset was not found.", status=404)
            state = self._read(path)
            if revision is None:
                return deepcopy(state["current"])
            item = next((value for value in state["revisions"] if value["preset"]["revision"] == revision), None)
            if item is None:
                raise AuthoringServiceError("TRUSTED_NODE_PRESET_REVISION_UNKNOWN", "Trusted node preset revision was not found.", status=404)
            return deepcopy(item)

    def mappings_for_recipe(self, recipe: dict) -> dict[str, dict]:
        mappings: dict[str, dict] = {}
        for node in recipe.get("nodes") or []:
            preset_ref = node.get("preset") if isinstance(node, dict) else {}
            publication = self.get_publication(str(preset_ref.get("id") or ""), preset_ref.get("revision"))
            if publication["preset"].get("digest") != preset_ref.get("digest"):
                raise AuthoringServiceError("TRUSTED_NODE_PRESET_DIGEST_MISMATCH", "Recipe preset revision no longer matches its publication.", status=409)
            if publication["mapping"].get("key") != node.get("developer_mapping_key"):
                raise AuthoringServiceError("TRUSTED_NODE_MAPPING_KEY_MISMATCH", "Recipe and Developer mapping identities differ.", status=409)
            mappings[node["id"]] = deepcopy(publication["mapping"])
        return mappings

    def _path(self, preset_id: str) -> Path:
        if not isinstance(preset_id, str) or not preset_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in preset_id):
            raise AuthoringServiceError("TRUSTED_NODE_PRESET_ID_INVALID", "Trusted node preset id is invalid.")
        return self.root / f"{preset_id}.json"

    @staticmethod
    def _read(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthoringServiceError("TRUSTED_NODE_PRESET_STORE_INVALID", "Trusted node preset storage is invalid.", status=500) from exc
        body = {key: value[key] for key in value if key != "digest"}
        if value.get("digest") != canonical_digest(body) or value.get("schema") != "cartridgeflow.trusted_node_registry_entry.v2":
            raise AuthoringServiceError("TRUSTED_NODE_PRESET_STORE_INVALID", "Trusted node preset storage integrity check failed.", status=500)
        return value

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        pending = path.with_suffix(".tmp")
        pending.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        pending.replace(path)


def _valid_path(path: str) -> bool:
    parts = path.split(".")
    return all(part and part.replace("_", "a").replace("-", "a").isalnum() for part in parts)


def _contains_key(value: object, target: str) -> bool:
    if isinstance(value, dict):
        return target in value or any(_contains_key(item, target) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, target) for item in value)
    return False


def _requirements_for_state(manifest: dict, state: dict) -> dict:
    params = state.get("params") if isinstance(state.get("params"), dict) else {}
    requirements = {
        key: deepcopy(manifest[key])
        for key in sorted(_MANIFEST_REQUIREMENT_FIELDS - {"permissions", "mcp_tools", "resource_requirements", "llm_recipe"})
        if key in manifest
    }

    permission_id = str(state.get("permission") or params.get("permission") or "").strip()
    if permission_id:
        requirements["permissions"] = _select_manifest_items(manifest, "permissions", {permission_id})

    tool_ids = _string_set(state.get("allowed_tools") or params.get("allowed_tools"))
    binding = state.get("mcp_binding") if isinstance(state.get("mcp_binding"), dict) else {}
    tool_ids.update(_string_set(binding.get("allowed_tools")))
    for tool in state.get("tools") or params.get("tools") or []:
        if isinstance(tool, dict):
            tool_id = str(tool.get("mcp_tool_id") or tool.get("id") or "").strip()
            if tool_id:
                tool_ids.add(tool_id)
    if tool_ids:
        tools = _select_manifest_items(manifest, "mcp_tools", tool_ids)
        if any(str(tool.get("type") or "") == "cartridge_dlc" for tool in tools):
            raise AuthoringServiceError(
                "TRUSTED_NODE_MAPPING_RESOURCE_UNSUPPORTED",
                "Package-local DLC tools cannot be carried by a single trusted node snapshot.",
            )
        requirements["mcp_tools"] = tools

    model_role = str(state.get("model_role") or params.get("model_role") or "").strip()
    if model_role:
        recipe = manifest.get("llm_recipe") if isinstance(manifest.get("llm_recipe"), dict) else {}
        roles = _select_items(recipe.get("roles"), {model_role}, "llm_recipe.roles")
        requirements["llm_recipe"] = {"schema": "cartridgeflow.llm_recipe.v1", "roles": roles}

    resource_roles = _string_set(state.get("resource_role") or params.get("resource_role"))
    for tool in requirements.get("mcp_tools") or []:
        role = str(tool.get("resource_role") or "").strip()
        if role:
            resource_roles.add(role)
    if resource_roles:
        requirements["resource_requirements"] = _select_items(
            manifest.get("resource_requirements"), resource_roles, "resource_requirements", identity="role",
        )
    return requirements


def _select_manifest_items(manifest: dict, field: str, identities: set[str]) -> list[dict]:
    return _select_items(manifest.get(field), identities, field)


def _select_items(value: object, identities: set[str], label: str, *, identity: str = "id") -> list[dict]:
    items = value if isinstance(value, list) else []
    selected = [deepcopy(item) for item in items if isinstance(item, dict) and str(item.get(identity) or "") in identities]
    found = {str(item.get(identity) or "") for item in selected}
    missing = sorted(identities - found)
    if missing:
        raise AuthoringServiceError(
            "TRUSTED_NODE_MAPPING_REQUIREMENT_MISSING",
            f"Developer node references undeclared {label}: {', '.join(missing)}.",
        )
    return selected


def _string_set(value: object) -> set[str]:
    values = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    return {str(item).strip() for item in values if str(item).strip()}


def _path_exists(value: dict, path: str) -> bool:
    current: object = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _get_path(value: dict, path: str) -> object:
    current: object = value
    for part in path.split("."):
        if not isinstance(current, dict):
            raise KeyError(path)
        current = current[part]
    return current


def _value_matches_type(value: object, value_type: str) -> bool:
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "string_list":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _set_path(value: dict, path: str, replacement: object) -> None:
    current = value
    parts = path.split(".")
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = replacement
