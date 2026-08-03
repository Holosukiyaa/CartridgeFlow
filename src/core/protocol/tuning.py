from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone


TUNING_PROTOCOL = {"id": "CF-TUNING", "version": "1.0"}
TUNING_REPOSITORY_SCHEMA = "cartridgeflow.tuning_repository.v1"
TUNING_RELEASE_SCHEMA = "cartridgeflow.tuning_release.v1"
ALLOWED_PATCH_FIELDS = frozenset({
    "title",
    "display_name",
    "description",
    "experience",
    "params",
    "timeout_ms",
    "model_role",
    "agent",
    "endpoint",
    "tools",
    "input_binding",
    "inputs",
    "outputs",
})
_SENSITIVE_KEYS = re.compile(
    r"^(?:token|api[_-]?key|secret|password|authorization|cookie|private[_-]?key|credentials?|access[_-]?token|refresh[_-]?token|bearer)$",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(r"(?:^|\s)(?:sk-[A-Za-z0-9_-]{12,}|bearer\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----)", re.IGNORECASE)
_LOCAL_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|var|etc|tmp)/)", re.IGNORECASE)
_EXECUTABLE_KEYS = re.compile(r"^(?:code|script|command|args|python|javascript|shell|executable|entrypoint)$", re.IGNORECASE)
_UNSAFE_PARAMETER = re.compile(
    r"(?:^|[._-])(?:api[_-]?key|secret|password|token|credential|authorization|cookie|private[_-]?key|code|script|command|shell|executable)(?:$|[._-])",
    re.IGNORECASE,
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION_ID = re.compile(r"^rev-[0-9a-f]{16}$")


class TuningProtocolError(ValueError):
    pass


class TuningConflictError(TuningProtocolError):
    pass


def canonical_digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def flow_source_digest(root_flow: dict) -> str:
    if not isinstance(root_flow, dict):
        raise TuningProtocolError("root flow must be an object")
    source = deepcopy(root_flow)
    source.pop("annotations", None)
    source.pop("layout", None)
    states = source.get("states")
    if isinstance(states, dict):
        for state in states.values():
            if isinstance(state, dict):
                state.pop("layout", None)
    return canonical_digest(source)


def create_tuning_repository(flow_id: str, root_flow: dict) -> dict:
    host_protocol = _host_protocol(root_flow)
    if host_protocol != {"id": "CF-FARP", "version": "1.1"}:
        raise TuningProtocolError("CF-TUNING@1.0 requires trusted host CF-FARP@1.1")
    normalized_flow_id = str(flow_id or "").strip()
    if not normalized_flow_id:
        raise TuningProtocolError("tuning repository flow_id is required")
    return {
        "schema": TUNING_REPOSITORY_SCHEMA,
        "protocol": dict(TUNING_PROTOCOL),
        "host_protocol": host_protocol,
        "flow_id": normalized_flow_id,
        "repository_revision": 0,
        "node_heads": {},
        "revisions": [],
        "releases": [],
        "active_release_id": None,
    }


def validate_tuning_patch(patch: dict) -> dict:
    if not isinstance(patch, dict) or not patch:
        raise TuningProtocolError("tuning patch must be a non-empty object")
    unknown = sorted(set(patch) - ALLOWED_PATCH_FIELDS)
    if unknown:
        raise TuningProtocolError(f"tuning patch contains forbidden fields: {', '.join(unknown)}")
    _reject_sensitive_values(patch, "patch")
    normalized = deepcopy(patch)
    if "params" in normalized and not isinstance(normalized["params"], dict):
        raise TuningProtocolError("tuning patch params must be an object")
    if "experience" in normalized:
        _validate_node_experience(normalized["experience"])
    for field in ("input_binding", "inputs", "outputs"):
        if field in normalized and normalized[field] is not None and not isinstance(normalized[field], dict):
            raise TuningProtocolError(f"tuning patch {field} must be an object or null")
    if "tools" in normalized and normalized["tools"] is not None and not isinstance(normalized["tools"], list):
        raise TuningProtocolError("tuning patch tools must be an array or null")
    timeout = normalized.get("timeout_ms")
    if timeout is not None and (not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0):
        raise TuningProtocolError("tuning patch timeout_ms must be a positive integer or null")
    return normalized


def _validate_node_experience(experience: object) -> None:
    if not isinstance(experience, dict) or experience.get("schema") != "cartridgeflow.node_experience.v1":
        raise TuningProtocolError("tuning patch experience schema is invalid")
    _require_exact_fields(
        experience,
        {"schema", "visible", "stage", "interaction", "materials", "outcome", "controls"},
        "experience",
    )
    if not isinstance(experience.get("visible"), bool):
        raise TuningProtocolError("tuning patch experience.visible must be boolean")

    stage = experience.get("stage")
    _require_exact_fields(stage, {"label", "description", "waiting", "running", "success"}, "experience.stage")
    _require_strings(stage, {"label", "description", "waiting", "running", "success"}, "experience.stage")

    interaction = experience.get("interaction")
    _require_exact_fields(
        interaction,
        {"mode", "prompt", "action_labels", "fields", "allow_retry", "allow_cancel"},
        "experience.interaction",
    )
    if interaction.get("mode") not in {"automatic", "input", "review", "choice"}:
        raise TuningProtocolError("tuning patch experience.interaction.mode is invalid")
    _require_strings(interaction, {"prompt"}, "experience.interaction")
    if not isinstance(interaction.get("allow_retry"), bool) or not isinstance(interaction.get("allow_cancel"), bool):
        raise TuningProtocolError("tuning patch experience interaction capabilities must be boolean")
    action_labels = interaction.get("action_labels")
    if not isinstance(action_labels, dict) or any(not isinstance(key, str) or not key or not isinstance(value, str) for key, value in action_labels.items()):
        raise TuningProtocolError("tuning patch experience action_labels must map action ids to labels")
    input_fields = interaction.get("fields")
    if not isinstance(input_fields, list) or len(input_fields) > 64:
        raise TuningProtocolError("tuning patch experience interaction fields must be a bounded list")
    seen_input_fields: set[str] = set()
    for index, field in enumerate(input_fields):
        label = f"experience.interaction.fields[{index}]"
        _require_exact_fields(field, {"field", "label", "help", "placeholder", "control", "required", "options"}, label)
        _require_strings(field, {"field", "label", "help", "placeholder"}, label)
        field_id = field["field"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,127}", field_id) or _UNSAFE_PARAMETER.search(field_id):
            raise TuningProtocolError(f"tuning patch {label}.field is invalid or unsafe")
        if field_id in seen_input_fields:
            raise TuningProtocolError("tuning patch experience interaction fields contain duplicate ids")
        if field.get("control") not in {"text", "textarea", "number", "date", "select", "toggle"}:
            raise TuningProtocolError(f"tuning patch {label}.control is invalid")
        if not isinstance(field.get("required"), bool):
            raise TuningProtocolError(f"tuning patch {label}.required must be boolean")
        _require_string_list(field.get("options"), f"{label}.options")
        seen_input_fields.add(field_id)

    materials = experience.get("materials")
    _require_exact_fields(
        materials,
        {"visibility", "label", "live_updates", "allow_download", "hidden_fields"},
        "experience.materials",
    )
    if materials.get("visibility") not in {"none", "output", "input_output"}:
        raise TuningProtocolError("tuning patch experience.materials.visibility is invalid")
    _require_strings(materials, {"label"}, "experience.materials")
    if not isinstance(materials.get("live_updates"), bool) or not isinstance(materials.get("allow_download"), bool):
        raise TuningProtocolError("tuning patch experience material capabilities must be boolean")
    hidden_fields = materials.get("hidden_fields")
    if not isinstance(hidden_fields, list) or len(hidden_fields) > 64 or any(not isinstance(item, str) or not item for item in hidden_fields):
        raise TuningProtocolError("tuning patch experience hidden_fields must be a string list")

    outcome = experience.get("outcome")
    outcome_strings = {"success_title", "result_label", "empty_text", "error_title", "error_message", "retry_label"}
    _require_exact_fields(outcome, {*outcome_strings, "preserve_partial"}, "experience.outcome")
    _require_strings(outcome, outcome_strings, "experience.outcome")
    if not isinstance(outcome.get("preserve_partial"), bool):
        raise TuningProtocolError("tuning patch experience.outcome.preserve_partial must be boolean")

    controls = experience.get("controls")
    if not isinstance(controls, list) or len(controls) > 64:
        raise TuningProtocolError("tuning patch experience.controls must be a bounded list")
    seen_parameters: set[str] = set()
    for index, control in enumerate(controls):
        label = f"experience.controls[{index}]"
        _require_exact_fields(control, {"parameter", "label", "help", "control", "required", "options", "minimum", "maximum", "step"}, label)
        _require_strings(control, {"parameter", "label", "help"}, label)
        parameter = control["parameter"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,127}", parameter):
            raise TuningProtocolError(f"tuning patch {label}.parameter is invalid")
        if _SENSITIVE_KEYS.match(parameter) or _EXECUTABLE_KEYS.match(parameter) or _UNSAFE_PARAMETER.search(parameter):
            raise TuningProtocolError(f"tuning patch {label}.parameter cannot expose secrets or executable fields")
        if parameter in seen_parameters:
            raise TuningProtocolError("tuning patch experience controls contain duplicate parameters")
        if control.get("control") not in {"text", "number", "slider", "select", "toggle"}:
            raise TuningProtocolError(f"tuning patch {label}.control is invalid")
        if not isinstance(control.get("required"), bool):
            raise TuningProtocolError(f"tuning patch {label}.required must be boolean")
        _require_string_list(control.get("options"), f"{label}.options")
        for numeric_field in ("minimum", "maximum", "step"):
            number = control.get(numeric_field)
            if number is not None and (not isinstance(number, (int, float)) or isinstance(number, bool)):
                raise TuningProtocolError(f"tuning patch {label}.{numeric_field} must be numeric or null")
        if control.get("step") is not None and control["step"] <= 0:
            raise TuningProtocolError(f"tuning patch {label}.step must be positive")
        if control.get("minimum") is not None and control.get("maximum") is not None and control["minimum"] > control["maximum"]:
            raise TuningProtocolError(f"tuning patch {label} numeric range is invalid")
        seen_parameters.add(parameter)


def _require_exact_fields(value: object, fields: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise TuningProtocolError(f"tuning patch {label} fields are invalid")


def _require_strings(value: dict, fields: set[str], label: str) -> None:
    for field in fields:
        item = value.get(field)
        if not isinstance(item, str) or len(item) > 4000:
            raise TuningProtocolError(f"tuning patch {label}.{field} must be a bounded string")


def _require_string_list(value: object, label: str) -> None:
    if not isinstance(value, list) or len(value) > 64 or any(not isinstance(item, str) or not item or len(item) > 500 for item in value):
        raise TuningProtocolError(f"tuning patch {label} must be a bounded string list")


def validate_tuning_repository(repository: dict, root_flow: dict | None = None) -> dict:
    if not isinstance(repository, dict) or repository.get("schema") != TUNING_REPOSITORY_SCHEMA:
        raise TuningProtocolError("unknown tuning repository schema")
    if repository.get("protocol") != TUNING_PROTOCOL:
        raise TuningProtocolError("tuning repository protocol identity is invalid")
    if not isinstance(repository.get("flow_id"), str) or not repository["flow_id"]:
        raise TuningProtocolError("tuning repository flow_id is required")
    if repository.get("host_protocol") != {"id": "CF-FARP", "version": "1.1"}:
        raise TuningProtocolError("tuning repository host protocol identity is invalid")
    if not isinstance(repository.get("repository_revision"), int) or repository["repository_revision"] < 0:
        raise TuningProtocolError("tuning repository revision is invalid")
    heads = repository.get("node_heads")
    revisions = repository.get("revisions")
    releases = repository.get("releases")
    if not isinstance(heads, dict) or not isinstance(revisions, list) or not isinstance(releases, list):
        raise TuningProtocolError("tuning repository collections are invalid")
    revision_by_id: dict[str, dict] = {}
    for revision in revisions:
        _validate_revision(revision)
        revision_id = revision["id"]
        if revision_id in revision_by_id:
            raise TuningProtocolError(f"duplicate tuning revision: {revision_id}")
        revision_by_id[revision_id] = revision
    for node_id, revision_id in heads.items():
        revision = revision_by_id.get(revision_id)
        if revision is None or revision.get("node_id") != node_id:
            raise TuningProtocolError(f"node head does not resolve: {node_id}")
    release_ids: set[str] = set()
    for expected_sequence, release in enumerate(releases, start=1):
        validate_tuning_release(release, root_flow=None)
        if release.get("sequence") != expected_sequence:
            raise TuningProtocolError("recipe release sequence is not contiguous")
        if release.get("flow_id") != repository["flow_id"]:
            raise TuningProtocolError(f"recipe release flow identity differs from repository: {release['id']}")
        if release.get("host_protocol") != repository["host_protocol"]:
            raise TuningProtocolError(f"recipe release host protocol differs from repository: {release['id']}")
        if release["id"] in release_ids:
            raise TuningProtocolError(f"duplicate recipe release: {release['id']}")
        for node_id, revision_id in release["node_revisions"].items():
            revision = revision_by_id.get(revision_id)
            if revision is None or revision.get("node_id") != node_id:
                raise TuningProtocolError(f"recipe release revision does not resolve: {release['id']}:{node_id}")
            if release["patches"].get(node_id) != revision.get("patch"):
                raise TuningProtocolError(f"recipe release patch differs from its revision: {release['id']}:{node_id}")
        release_ids.add(release["id"])
    active = repository.get("active_release_id")
    if active is not None and active not in release_ids:
        raise TuningProtocolError("active recipe release does not resolve")
    if root_flow is not None:
        if repository.get("host_protocol") != _host_protocol(root_flow):
            raise TuningProtocolError("tuning repository host protocol does not match root flow")
        states = root_flow.get("states") if isinstance(root_flow.get("states"), dict) else {}
        missing = sorted(node_id for node_id in heads if node_id not in states)
        if missing:
            raise TuningProtocolError(f"tuning repository references missing nodes: {', '.join(missing)}")
        for node_id, revision_id in heads.items():
            patch = revision_by_id[revision_id]["patch"]
            if "experience" in patch:
                _validate_experience_bindings(patch["experience"], {**states[node_id], **patch})
    return repository


def create_node_revision(
    repository: dict,
    root_flow: dict,
    node_id: str,
    patch: dict,
    *,
    expected_head: str | None,
    author: str,
    message: str,
    created_at: str | None = None,
) -> tuple[dict, dict]:
    validate_tuning_repository(repository)
    states = root_flow.get("states") if isinstance(root_flow.get("states"), dict) else {}
    if node_id not in states:
        raise TuningProtocolError(f"root flow node not found: {node_id}")
    current_head = repository["node_heads"].get(node_id)
    if expected_head != current_head:
        raise TuningConflictError(f"node tuning head changed: expected {expected_head or 'none'}, current {current_head or 'none'}")
    incoming = validate_tuning_patch(patch)
    normalized_author = str(author or "local-developer")
    normalized_message = str(message or "更新关键参数")
    _validate_audit_metadata(normalized_author, normalized_message, "tuning revision")
    full_patch: dict = {}
    if current_head:
        current_revision = next(item for item in repository["revisions"] if item["id"] == current_head)
        full_patch.update(deepcopy(current_revision["patch"]))
    full_patch.update(incoming)
    full_patch = validate_tuning_patch(full_patch)
    if "experience" in full_patch:
        _validate_experience_bindings(full_patch["experience"], {**states[node_id], **full_patch})
    timestamp = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    body = {
        "node_id": node_id,
        "parent_id": current_head,
        "flow_digest": flow_source_digest(root_flow),
        "patch": full_patch,
        "author": normalized_author,
        "message": normalized_message,
        "created_at": timestamp,
    }
    digest = canonical_digest(body)
    revision = {"id": f"rev-{digest[:16]}", **body, "digest": digest}
    updated = deepcopy(repository)
    updated["repository_revision"] += 1
    updated["revisions"].append(revision)
    updated["node_heads"][node_id] = revision["id"]
    return updated, revision


def publish_recipe_release(
    repository: dict,
    root_flow: dict,
    *,
    author: str,
    message: str,
    created_at: str | None = None,
    activate: bool = True,
) -> tuple[dict, dict]:
    validate_tuning_repository(repository, root_flow)
    normalized_author = str(author or "local-developer")
    normalized_message = str(message or f"发布配方 v{len(repository['releases']) + 1}")
    _validate_audit_metadata(normalized_author, normalized_message, "recipe release")
    source_digest = flow_source_digest(root_flow)
    updated = deepcopy(repository)
    revisions = {item["id"]: item for item in updated["revisions"]}
    patches: dict[str, dict] = {}
    timestamp = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    for node_id, revision_id in sorted(updated["node_heads"].items()):
        revision = revisions[revision_id]
        if revision.get("flow_digest") != source_digest:
            carry_body = {
                "node_id": node_id,
                "parent_id": revision_id,
                "flow_digest": source_digest,
                "patch": deepcopy(revision["patch"]),
                "author": normalized_author,
                "message": f"随配方发布继承：{normalized_message}",
                "created_at": timestamp,
            }
            carry_digest = canonical_digest(carry_body)
            revision = {"id": f"rev-{carry_digest[:16]}", **carry_body, "digest": carry_digest}
            updated["revisions"].append(revision)
            updated["node_heads"][node_id] = revision["id"]
            revisions[revision["id"]] = revision
        patches[node_id] = deepcopy(revision["patch"])
    sequence = len(updated["releases"]) + 1
    body = {
        "schema": TUNING_RELEASE_SCHEMA,
        "protocol": dict(TUNING_PROTOCOL),
        "host_protocol": _host_protocol(root_flow),
        "flow_id": updated["flow_id"],
        "flow_digest": source_digest,
        "sequence": sequence,
        "status": "published",
        "node_revisions": dict(sorted(updated["node_heads"].items())),
        "patches": patches,
        "created_at": timestamp,
        "created_by": normalized_author,
        "message": normalized_message,
    }
    digest = canonical_digest(body)
    release = {**body, "id": f"recipe-v{sequence:04d}-{digest[:8]}", "digest": digest}
    validate_tuning_release(release, root_flow)
    updated["repository_revision"] += 1
    updated["releases"].append(release)
    if activate:
        updated["active_release_id"] = release["id"]
    return updated, release


def activate_recipe_release(repository: dict, release_id: str) -> tuple[dict, dict]:
    validate_tuning_repository(repository)
    release = next((item for item in repository["releases"] if item.get("id") == release_id), None)
    if release is None:
        raise TuningProtocolError(f"recipe release not found: {release_id}")
    updated = deepcopy(repository)
    updated["repository_revision"] += 1
    updated["active_release_id"] = release_id
    return updated, deepcopy(release)


def validate_tuning_release(release: dict, root_flow: dict | None = None) -> dict:
    if not isinstance(release, dict) or release.get("schema") != TUNING_RELEASE_SCHEMA:
        raise TuningProtocolError("unknown tuning release schema")
    if release.get("protocol") != TUNING_PROTOCOL or release.get("status") != "published":
        raise TuningProtocolError("tuning release identity or status is invalid")
    if not isinstance(release.get("flow_id"), str) or not release["flow_id"]:
        raise TuningProtocolError("tuning release flow_id is required")
    if release.get("host_protocol") != {"id": "CF-FARP", "version": "1.1"}:
        raise TuningProtocolError("tuning release host protocol identity is invalid")
    _validate_audit_metadata(release.get("created_by"), release.get("message"), "recipe release")
    if not isinstance(release.get("patches"), dict) or not isinstance(release.get("node_revisions"), dict):
        raise TuningProtocolError("tuning release patches and node revisions are required")
    if set(release["patches"]) != set(release["node_revisions"]):
        raise TuningProtocolError("tuning release patch and revision node sets differ")
    for node_id, patch in release["patches"].items():
        revision_id = release["node_revisions"].get(node_id)
        if not isinstance(node_id, str) or not node_id or not isinstance(revision_id, str) or not _REVISION_ID.fullmatch(revision_id):
            raise TuningProtocolError("tuning release node revision identity is invalid")
        validate_tuning_patch(patch)
    if not isinstance(release.get("flow_digest"), str) or not _SHA256.fullmatch(release["flow_digest"]):
        raise TuningProtocolError("tuning release flow digest is invalid")
    body = {key: deepcopy(value) for key, value in release.items() if key not in {"id", "digest"}}
    expected = canonical_digest(body)
    if release.get("digest") != expected:
        raise TuningProtocolError("tuning release digest does not match content")
    sequence = release.get("sequence")
    if not isinstance(sequence, int) or sequence < 1 or release.get("id") != f"recipe-v{sequence:04d}-{expected[:8]}":
        raise TuningProtocolError("tuning release id or sequence is invalid")
    if root_flow is not None:
        if release.get("host_protocol") != _host_protocol(root_flow):
            raise TuningProtocolError("tuning release host protocol does not match root flow")
        if release.get("flow_digest") != flow_source_digest(root_flow):
            raise TuningProtocolError("tuning release root flow digest is stale")
        states = root_flow.get("states") if isinstance(root_flow.get("states"), dict) else {}
        missing = sorted(node_id for node_id in release["patches"] if node_id not in states)
        if missing:
            raise TuningProtocolError(f"tuning release references missing nodes: {', '.join(missing)}")
        for node_id, patch in release["patches"].items():
            if "experience" in patch:
                _validate_experience_bindings(patch["experience"], {**states[node_id], **patch})
    return release


def materialize_tuning(root_flow: dict, source: dict | None, *, draft: bool = False) -> tuple[dict, dict]:
    flow = deepcopy(root_flow)
    if not source:
        context = _empty_context(flow, draft)
        context["materialization_digest"] = canonical_digest(flow)
        return flow, context
    if source.get("schema") == TUNING_REPOSITORY_SCHEMA:
        validate_tuning_repository(source, root_flow)
        if draft:
            revision_by_id = {item["id"]: item for item in source["revisions"]}
            patches = {node_id: revision_by_id[revision_id]["patch"] for node_id, revision_id in source["node_heads"].items()}
            context = {
                "mode": "draft",
                "protocol": dict(TUNING_PROTOCOL),
                "release_id": None,
                "release_digest": None,
                "flow_digest": flow_source_digest(root_flow),
                "node_revisions": dict(source["node_heads"]),
                "repository_revision": source["repository_revision"],
                "active_release_id": source.get("active_release_id"),
            }
        else:
            active = source.get("active_release_id")
            if not active:
                raise TuningProtocolError("tuning repository has no active recipe release")
            release = next(item for item in source["releases"] if item["id"] == active)
            return materialize_tuning(root_flow, release, draft=False)
    else:
        release = validate_tuning_release(source, root_flow)
        patches = release["patches"]
        context = {
            "mode": "published",
            "protocol": dict(TUNING_PROTOCOL),
            "release_id": release["id"],
            "release_digest": release["digest"],
            "flow_digest": release["flow_digest"],
            "node_revisions": dict(release["node_revisions"]),
        }
    states = flow.get("states") if isinstance(flow.get("states"), dict) else {}
    for node_id, patch in patches.items():
        state = states[node_id]
        for field, value in patch.items():
            if value is None:
                state.pop(field, None)
            else:
                state[field] = deepcopy(value)
    context["materialization_digest"] = canonical_digest(flow)
    return flow, context


def _validate_revision(revision: dict) -> None:
    if not isinstance(revision, dict) or not isinstance(revision.get("node_id"), str) or not revision["node_id"]:
        raise TuningProtocolError("tuning revision is invalid")
    if not isinstance(revision.get("flow_digest"), str) or not _SHA256.fullmatch(revision["flow_digest"]):
        raise TuningProtocolError("tuning revision flow digest is invalid")
    _validate_audit_metadata(revision.get("author"), revision.get("message"), "tuning revision")
    validate_tuning_patch(revision.get("patch"))
    body = {key: deepcopy(value) for key, value in revision.items() if key not in {"id", "digest"}}
    expected = canonical_digest(body)
    if revision.get("digest") != expected or revision.get("id") != f"rev-{expected[:16]}":
        raise TuningProtocolError("tuning revision digest does not match content")


def _validate_experience_bindings(experience: dict, node: dict) -> None:
    params = node.get("params") if isinstance(node.get("params"), dict) else {}
    input_schema = node.get("input_schema") if isinstance(node.get("input_schema"), dict) else {}
    properties = input_schema.get("properties") if isinstance(input_schema.get("properties"), dict) else {}
    declared_fields = {
        str(item)
        for item in params.get("fields") or []
        if isinstance(item, str) and item
    } | set(properties)
    projected_fields = {item["field"] for item in experience["interaction"]["fields"]}
    unknown_fields = sorted(projected_fields - declared_fields)
    if unknown_fields:
        raise TuningProtocolError(f"tuning experience references undeclared input fields: {', '.join(unknown_fields)}")
    unknown_parameters = sorted(item["parameter"] for item in experience["controls"] if item["parameter"] not in params)
    if unknown_parameters:
        raise TuningProtocolError(f"tuning experience exposes unknown parameters: {', '.join(unknown_parameters)}")


def _host_protocol(root_flow: dict) -> dict:
    protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
    return {"id": str(protocol.get("id") or ""), "version": str(protocol.get("version") or "")}


def _reject_sensitive_values(value: object, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _SENSITIVE_KEYS.match(str(key)) and item is not None and item != "":
                raise TuningProtocolError(f"tuning data cannot contain secrets: {path}.{key}")
            if _EXECUTABLE_KEYS.match(str(key)) and item is not None and item != "":
                raise TuningProtocolError(f"tuning data cannot contain executable content: {path}.{key}")
            _reject_sensitive_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_sensitive_values(item, f"{path}[{index}]")
    elif isinstance(value, str):
        if _SECRET_VALUE.search(value):
            raise TuningProtocolError(f"tuning data contains a credential value: {path}")
        if _LOCAL_ABSOLUTE_PATH.match(value.strip()):
            raise TuningProtocolError(f"tuning data contains a local absolute path: {path}")


def _validate_audit_metadata(author: object, message: object, label: str) -> None:
    if not isinstance(author, str) or not author.strip():
        raise TuningProtocolError(f"{label} author is required")
    if not isinstance(message, str) or not message.strip():
        raise TuningProtocolError(f"{label} message is required")
    _reject_sensitive_values({"author": author, "message": message}, label)


def _empty_context(root_flow: dict, draft: bool) -> dict:
    return {
        "mode": "draft" if draft else "published",
        "protocol": dict(TUNING_PROTOCOL),
        "release_id": None,
        "release_digest": None,
        "flow_digest": flow_source_digest(root_flow),
        "node_revisions": {},
        "repository_revision": 0 if draft else None,
    }
