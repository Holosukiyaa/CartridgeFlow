"""Fail-closed immutable CF-TUNING@1.1 AI authoring facts."""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .tuning import TuningProtocolError, canonical_digest


AUTHORING_PROTOCOL = {"id": "CF-TUNING", "version": "1.1"}
BLUEPRINT_SCHEMA = "cartridgeflow.recipe_blueprint.v1"
INSTANCE_SCHEMA = "cartridgeflow.recipe_instance.v1"
CHANGE_SET_SCHEMA = "cartridgeflow.authoring_change_set.v1"
ACCEPTANCE_SCHEMA = "cartridgeflow.authoring_acceptance.v1"
FREEZE_SCHEMA = "cartridgeflow.authoring_freeze_snapshot.v1"
_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEY = re.compile(r"(?:token|secret|password|credential|api[_-]?key|authorization|cookie|private[_-]?key|code|script|command|executor|permission|topology|execution_plan|endpoint)", re.I)
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|var|etc|tmp)/)")
_OPERATIONS = frozenset({"set_binding", "set_step_intent", "set_source_reference"})


def _id(value: object, label: str) -> str:
    value = str(value or "")
    if not _ID.fullmatch(value):
        raise TuningProtocolError(f"{label} must be a stable identifier")
    return value


def _digest_id(prefix: str, body: dict) -> tuple[str, str]:
    digest = canonical_digest(body)
    return f"{prefix}-{digest[:16]}", digest


def _safe(value: Any, label: str = "value") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or _FORBIDDEN_KEY.search(key):
                raise TuningProtocolError(f"{label} contains forbidden field: {key}")
            _safe(item, f"{label}.{key}")
    elif isinstance(value, list):
        for item in value:
            _safe(item, label)
    elif isinstance(value, str) and _ABSOLUTE_PATH.match(value):
        raise TuningProtocolError(f"{label} contains a local absolute path")


def _reference(value: object, label: str, *, kind: str | None = None) -> dict:
    if not isinstance(value, dict) or set(value) != {"id", "digest", "kind"}:
        raise TuningProtocolError(f"{label} must contain exactly id, kind, and digest")
    _id(value["id"], f"{label}.id")
    if value["kind"] not in {"source", "schema", "asset", "resource_role", "compile"} or (kind and value["kind"] != kind):
        raise TuningProtocolError(f"{label}.kind is invalid")
    if not isinstance(value["digest"], str) or not _SHA256.fullmatch(value["digest"]):
        raise TuningProtocolError(f"{label}.digest must be sha256")
    return deepcopy(value)


def _blueprint_body(recipe_id: str, intent: str, steps: list[dict], source_references: list[dict]) -> dict:
    _id(recipe_id, "recipe_id")
    if not isinstance(intent, str) or not intent.strip() or len(intent) > 4000 or not isinstance(steps, list) or not steps:
        raise TuningProtocolError("blueprint intent and steps are required")
    normalized_steps, seen = [], set()
    for item in steps:
        if not isinstance(item, dict) or set(item) != {"id", "intent", "inputs", "outputs"}:
            raise TuningProtocolError("blueprint step fields are invalid")
        step_id = _id(item["id"], "blueprint step id")
        if step_id in seen or not isinstance(item["intent"], str) or not item["intent"].strip():
            raise TuningProtocolError("blueprint step identity or intent is invalid")
        _safe(item, "blueprint step")
        seen.add(step_id)
        normalized_steps.append(deepcopy(item))
    references = [_reference(item, "source reference", kind="source") for item in source_references]
    if len({item["id"] for item in references}) != len(references):
        raise TuningProtocolError("source references must have unique ids")
    return {"schema": BLUEPRINT_SCHEMA, "protocol": dict(AUTHORING_PROTOCOL), "recipe_id": recipe_id,
            "intent": intent.strip(), "steps": normalized_steps, "source_references": references}


def create_recipe_blueprint(recipe_id: str, intent: str, steps: list[dict], source_references: list[dict]) -> dict:
    body = _blueprint_body(recipe_id, intent, steps, source_references)
    item_id, digest = _digest_id("blueprint", body)
    return {"id": item_id, **body, "digest": digest}


def create_recipe_instance(blueprint: dict, bindings: dict, *, revision: int = 1, parent_instance: dict | None = None) -> dict:
    validate_recipe_blueprint(blueprint)
    if not isinstance(bindings, dict) or not isinstance(revision, int) or revision < 1:
        raise TuningProtocolError("instance bindings and revision are invalid")
    _safe(bindings, "instance bindings")
    parent = None
    if parent_instance is not None:
        validate_recipe_instance(parent_instance)
        parent = {"id": parent_instance["id"], "digest": parent_instance["digest"], "revision": parent_instance["revision"]}
    body = {"schema": INSTANCE_SCHEMA, "protocol": dict(AUTHORING_PROTOCOL), "blueprint_id": blueprint["id"],
            "blueprint_digest": blueprint["digest"], "blueprint": deepcopy(blueprint), "revision": revision,
            "bindings": deepcopy(bindings), "parent_instance": parent}
    item_id, digest = _digest_id("instance", body)
    return {"id": item_id, **body, "digest": digest}


def _validate_change(change: object, blueprint: dict) -> dict:
    if not isinstance(change, dict) or set(change) != {"id", "target_id", "operation", "value"}:
        raise TuningProtocolError("change item fields are invalid")
    item_id = _id(change["id"], "change item id")
    target = _id(change["target_id"], "change target id")
    operation = change["operation"]
    if operation not in _OPERATIONS:
        raise TuningProtocolError("change item operation is unsupported")
    step_ids = {item["id"] for item in blueprint["steps"]}
    source_ids = {item["id"] for item in blueprint["source_references"]}
    if operation == "set_binding":
        if target not in step_ids or not isinstance(change["value"], dict):
            raise TuningProtocolError("set_binding target or value is invalid")
        _safe(change["value"], "set_binding value")
    elif operation == "set_step_intent":
        if target not in step_ids or not isinstance(change["value"], str) or not change["value"].strip() or len(change["value"]) > 4000:
            raise TuningProtocolError("set_step_intent target or value is invalid")
        _safe(change["value"], "set_step_intent value")
    else:
        if target not in source_ids:
            raise TuningProtocolError("set_source_reference target is invalid")
        _reference(change["value"], "set_source_reference value", kind="source")
        if change["value"]["id"] != target:
            raise TuningProtocolError("set_source_reference must preserve target identity")
    return {"id": item_id, "target_id": target, "operation": operation, "value": deepcopy(change["value"])}


def propose_change_set(instance: dict, changes: list[dict], author: str, summary: str) -> dict:
    validate_recipe_instance(instance)
    if not isinstance(changes, list) or not changes or not isinstance(author, str) or not author.strip() or not isinstance(summary, str) or not summary.strip():
        raise TuningProtocolError("change set requires changes, author, and summary")
    normalized = [_validate_change(item, instance["blueprint"]) for item in changes]
    if len({item["id"] for item in normalized}) != len(normalized):
        raise TuningProtocolError("change item ids must be unique")
    body = {"schema": CHANGE_SET_SCHEMA, "protocol": dict(AUTHORING_PROTOCOL), "instance_id": instance["id"],
            "instance_digest": instance["digest"], "expected_revision": instance["revision"], "changes": normalized,
            "author": author.strip(), "summary": summary.strip(), "status": "proposed"}
    item_id, digest = _digest_id("change", body)
    return {"id": item_id, **body, "digest": digest}


def _frozen_step_ids(instance: dict, snapshots: list[dict] | None) -> set[str]:
    frozen: set[str] = set()
    for snapshot in snapshots or []:
        validate_freeze_snapshot(snapshot)
        if snapshot["instance_id"] == instance["id"] and snapshot["instance_revision"] == instance["revision"]:
            frozen.update(item["step_id"] for item in snapshot["frozen_steps"])
    return frozen


def accept_change_set(instance: dict, change_set: dict, selected_change_ids: list[str] | None = None, *, frozen_snapshots: list[dict] | None = None) -> dict:
    """Atomically accept an explicit non-empty subset into new immutable facts."""
    validate_recipe_instance(instance)
    validate_change_set(change_set)
    if change_set["instance_id"] != instance["id"] or change_set["instance_digest"] != instance["digest"] or change_set["expected_revision"] != instance["revision"]:
        raise TuningProtocolError("authoring change set is stale")
    validated_changes = [_validate_change(item, instance["blueprint"]) for item in change_set["changes"]]
    if validated_changes != change_set["changes"] or len({item["id"] for item in validated_changes}) != len(validated_changes):
        raise TuningProtocolError("authoring change set items are invalid")
    all_changes = {item["id"]: item for item in validated_changes}
    selected = list(all_changes) if selected_change_ids is None else selected_change_ids
    if not isinstance(selected, list) or not selected or any(not isinstance(item, str) for item in selected):
        raise TuningProtocolError("accepted change selection must be a non-empty id list")
    if len(set(selected)) != len(selected) or any(item not in all_changes for item in selected):
        raise TuningProtocolError("accepted change selection contains duplicate or unknown item")
    accepted = [deepcopy(all_changes[item]) for item in selected]
    frozen = _frozen_step_ids(instance, frozen_snapshots)
    blueprint = deepcopy(instance["blueprint"])
    bindings = deepcopy(instance["bindings"])
    for change in accepted:
        if change["operation"] == "set_binding":
            if change["target_id"] in frozen:
                raise TuningProtocolError("frozen step requires an explicit new revision path")
            bindings[change["target_id"]] = change["value"]
        elif change["operation"] == "set_step_intent":
            if change["target_id"] in frozen:
                raise TuningProtocolError("frozen step requires an explicit new revision path")
            next(item for item in blueprint["steps"] if item["id"] == change["target_id"])["intent"] = change["value"]
        elif change["operation"] == "set_source_reference":
            next(item for item in blueprint["source_references"] if item["id"] == change["target_id"]).update(change["value"])
        else:  # Defensive: validation guarantees this is unreachable.
            raise TuningProtocolError("accepted change operation is unsupported")
    next_blueprint = create_recipe_blueprint(blueprint["recipe_id"], blueprint["intent"], blueprint["steps"], blueprint["source_references"])
    next_instance = create_recipe_instance(next_blueprint, bindings, revision=instance["revision"] + 1, parent_instance=instance)
    body = {"schema": ACCEPTANCE_SCHEMA, "protocol": dict(AUTHORING_PROTOCOL), "change_set_id": change_set["id"],
            "change_set_digest": change_set["digest"], "source_instance_id": instance["id"], "source_instance_digest": instance["digest"],
            "source_revision": instance["revision"], "accepted_change_ids": list(selected), "accepted_changes": accepted,
            "change_set": deepcopy(change_set), "blueprint": next_blueprint, "instance": next_instance}
    item_id, digest = _digest_id("acceptance", body)
    return {"id": item_id, **body, "digest": digest}


def _step_semantic_digest(instance: dict, step_id: str) -> str:
    step = next((item for item in instance["blueprint"]["steps"] if item["id"] == step_id), None)
    if step is None:
        raise TuningProtocolError("freeze step does not exist in instance blueprint")
    return canonical_digest({"step": step, "binding": instance["bindings"].get(step_id)})


def freeze_snapshot(instance: dict, frozen_steps: list[dict], compile_reference: dict, author: str, summary: str) -> dict:
    validate_recipe_instance(instance)
    if not isinstance(frozen_steps, list) or not frozen_steps:
        raise TuningProtocolError("freeze snapshot must explicitly list frozen steps")
    normalized, seen = [], set()
    for step in frozen_steps:
        if not isinstance(step, dict) or set(step) != {"step_id", "semantic_digest"}:
            raise TuningProtocolError("freeze step fields are invalid")
        step_id = _id(step["step_id"], "freeze step_id")
        if step_id in seen or step["semantic_digest"] != _step_semantic_digest(instance, step_id):
            raise TuningProtocolError("freeze step semantic digest is invalid")
        seen.add(step_id)
        normalized.append(deepcopy(step))
    body = {"schema": FREEZE_SCHEMA, "protocol": dict(AUTHORING_PROTOCOL), "instance_id": instance["id"], "instance_digest": instance["digest"],
            "blueprint_id": instance["blueprint_id"], "blueprint_digest": instance["blueprint_digest"], "instance_revision": instance["revision"],
            "frozen_steps": sorted(normalized, key=lambda item: item["step_id"]), "compile_reference": _reference(compile_reference, "compile reference", kind="compile"),
            "author": str(author or "").strip(), "summary": str(summary or "").strip()}
    if not body["author"] or not body["summary"]:
        raise TuningProtocolError("freeze author and summary are required")
    item_id, digest = _digest_id("freeze", body)
    return {"id": item_id, **body, "digest": digest}


def validate_recipe_blueprint(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != BLUEPRINT_SCHEMA or value.get("protocol") != AUTHORING_PROTOCOL:
        raise TuningProtocolError("recipe blueprint identity is invalid")
    body = _blueprint_body(value.get("recipe_id"), value.get("intent"), value.get("steps"), value.get("source_references"))
    item_id, digest = _digest_id("blueprint", body)
    if value.get("id") != item_id or value.get("digest") != digest or set(value) != {*body, "id", "digest"}:
        raise TuningProtocolError("recipe blueprint is not immutable")
    return value


def validate_recipe_instance(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != INSTANCE_SCHEMA or value.get("protocol") != AUTHORING_PROTOCOL:
        raise TuningProtocolError("recipe instance identity is invalid")
    validate_recipe_blueprint(value.get("blueprint"))
    if value.get("blueprint_id") != value["blueprint"]["id"] or value.get("blueprint_digest") != value["blueprint"]["digest"] or not isinstance(value.get("revision"), int) or value["revision"] < 1 or not isinstance(value.get("bindings"), dict):
        raise TuningProtocolError("recipe instance facts are invalid")
    _safe(value["bindings"], "instance bindings")
    parent = value.get("parent_instance")
    if parent is not None and (not isinstance(parent, dict) or set(parent) != {"id", "digest", "revision"} or not isinstance(parent["revision"], int)):
        raise TuningProtocolError("recipe instance parent is invalid")
    body = {key: deepcopy(item) for key, item in value.items() if key not in {"id", "digest"}}
    item_id, digest = _digest_id("instance", body)
    if value.get("id") != item_id or value.get("digest") != digest:
        raise TuningProtocolError("recipe instance is not immutable")
    return value


def validate_change_set(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != CHANGE_SET_SCHEMA or value.get("protocol") != AUTHORING_PROTOCOL or value.get("status") != "proposed":
        raise TuningProtocolError("authoring change set identity is invalid")
    if not isinstance(value.get("expected_revision"), int) or not isinstance(value.get("instance_digest"), str) or not _SHA256.fullmatch(value["instance_digest"]):
        raise TuningProtocolError("authoring change set revision is invalid")
    body = {key: deepcopy(item) for key, item in value.items() if key not in {"id", "digest"}}
    item_id, digest = _digest_id("change", body)
    if value.get("id") != item_id or value.get("digest") != digest:
        raise TuningProtocolError("authoring change set is not immutable")
    return value


def validate_acceptance(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != ACCEPTANCE_SCHEMA or value.get("protocol") != AUTHORING_PROTOCOL:
        raise TuningProtocolError("authoring acceptance identity is invalid")
    validate_recipe_blueprint(value.get("blueprint")); validate_recipe_instance(value.get("instance")); validate_change_set(value.get("change_set"))
    ids = value.get("accepted_change_ids")
    changes = value.get("accepted_changes")
    if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) or not isinstance(changes, list) or [item.get("id") for item in changes] != ids:
        raise TuningProtocolError("authoring acceptance selected changes are invalid")
    proposed = {item["id"]: item for item in value["change_set"]["changes"]}
    if value.get("change_set_id") != value["change_set"]["id"] or value.get("change_set_digest") != value["change_set"]["digest"] or any(proposed.get(item["id"]) != item for item in changes):
        raise TuningProtocolError("authoring acceptance change set lineage is invalid")
    parent = value["instance"].get("parent_instance", {})
    if value["instance"]["revision"] != value.get("source_revision", 0) + 1 or parent.get("id") != value.get("source_instance_id") or parent.get("digest") != value.get("source_instance_digest") or parent.get("revision") != value.get("source_revision"):
        raise TuningProtocolError("authoring acceptance instance lineage is invalid")
    body = {key: deepcopy(item) for key, item in value.items() if key not in {"id", "digest"}}
    item_id, digest = _digest_id("acceptance", body)
    if value.get("id") != item_id or value.get("digest") != digest:
        raise TuningProtocolError("authoring acceptance is not immutable")
    return value


def validate_freeze_snapshot(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != FREEZE_SCHEMA or value.get("protocol") != AUTHORING_PROTOCOL:
        raise TuningProtocolError("authoring freeze snapshot identity is invalid")
    required = {"schema", "protocol", "instance_id", "instance_digest", "blueprint_id", "blueprint_digest", "instance_revision", "frozen_steps", "compile_reference", "author", "summary", "id", "digest"}
    if set(value) != required or not isinstance(value["instance_revision"], int) or value["instance_revision"] < 1:
        raise TuningProtocolError("authoring freeze snapshot facts are invalid")
    steps = value["frozen_steps"]
    if not isinstance(steps, list) or not steps or len({item.get("step_id") for item in steps if isinstance(item, dict)}) != len(steps):
        raise TuningProtocolError("authoring freeze snapshot must list unique frozen steps")
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"step_id", "semantic_digest"} or not _ID.fullmatch(str(step["step_id"])) or not _SHA256.fullmatch(str(step["semantic_digest"])):
            raise TuningProtocolError("authoring freeze step is invalid")
    _reference(value["compile_reference"], "compile reference", kind="compile")
    body = {key: deepcopy(item) for key, item in value.items() if key not in {"id", "digest"}}
    item_id, digest = _digest_id("freeze", body)
    if value["id"] != item_id or value["digest"] != digest:
        raise TuningProtocolError("authoring freeze snapshot is not immutable")
    return value
