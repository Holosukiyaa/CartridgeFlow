"""CF-TUNING@1.1 immutable AI authoring facts.

This module deliberately owns no topology compilation or runtime execution.
It only creates auditable recipe facts that a CF-FARP host may later compile.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .tuning import TuningProtocolError, canonical_digest


AUTHORING_PROTOCOL = {"id": "CF-TUNING", "version": "1.1"}
BLUEPRINT_SCHEMA = "cartridgeflow.recipe_blueprint.v1"
INSTANCE_SCHEMA = "cartridgeflow.recipe_instance.v1"
CHANGE_SET_SCHEMA = "cartridgeflow.authoring_change_set.v1"
FREEZE_SCHEMA = "cartridgeflow.authoring_freeze_snapshot.v1"
_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEY = re.compile(r"(?:token|secret|password|credential|api[_-]?key|authorization|cookie|private[_-]?key|code|script|command|executor|permission|topology|execution_plan)", re.I)
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|var|etc|tmp)/)")


def _id(value: object, label: str) -> str:
    value = str(value or "")
    if not _ID.fullmatch(value):
        raise TuningProtocolError(f"{label} must be a stable identifier")
    return value


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


def _digest_id(prefix: str, body: dict) -> tuple[str, str]:
    digest = canonical_digest(body)
    return f"{prefix}-{digest[:16]}", digest


def _reference(value: object, label: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"id", "digest", "kind"}:
        raise TuningProtocolError(f"{label} must contain exactly id, kind, and digest")
    _id(value["id"], f"{label}.id")
    if value["kind"] not in {"source", "schema", "asset", "resource_role", "compile"}:
        raise TuningProtocolError(f"{label}.kind is invalid")
    if not isinstance(value["digest"], str) or not _SHA256.fullmatch(value["digest"]):
        raise TuningProtocolError(f"{label}.digest must be sha256")
    return deepcopy(value)


def create_recipe_blueprint(recipe_id: str, intent: str, steps: list[dict], source_references: list[dict]) -> dict:
    """Create a portable, immutable recipe blueprint without executable values."""
    _id(recipe_id, "recipe_id")
    if not isinstance(intent, str) or not intent.strip() or len(intent) > 4000:
        raise TuningProtocolError("blueprint intent is required and bounded")
    if not isinstance(steps, list) or not steps:
        raise TuningProtocolError("blueprint steps are required")
    normalized_steps = []
    seen = set()
    for item in steps:
        if not isinstance(item, dict) or set(item) != {"id", "intent", "inputs", "outputs"}:
            raise TuningProtocolError("blueprint step fields are invalid")
        step_id = _id(item["id"], "blueprint step id")
        if step_id in seen or not isinstance(item["intent"], str) or not item["intent"].strip():
            raise TuningProtocolError("blueprint step identity or intent is invalid")
        _safe(item, "blueprint step")
        seen.add(step_id)
        normalized_steps.append(deepcopy(item))
    references = [_reference(item, "source reference") for item in source_references]
    body = {"schema": BLUEPRINT_SCHEMA, "protocol": dict(AUTHORING_PROTOCOL), "recipe_id": recipe_id,
            "intent": intent.strip(), "steps": normalized_steps, "source_references": references}
    item_id, digest = _digest_id("blueprint", body)
    return {"id": item_id, **body, "digest": digest}


def create_recipe_instance(blueprint: dict, bindings: dict, *, revision: int = 1) -> dict:
    validate_recipe_blueprint(blueprint)
    if not isinstance(bindings, dict) or not isinstance(revision, int) or revision < 1:
        raise TuningProtocolError("instance bindings and revision are invalid")
    _safe(bindings, "instance bindings")
    body = {"schema": INSTANCE_SCHEMA, "protocol": dict(AUTHORING_PROTOCOL), "blueprint_id": blueprint["id"],
            "blueprint_digest": blueprint["digest"], "revision": revision, "bindings": deepcopy(bindings)}
    item_id, digest = _digest_id("instance", body)
    return {"id": item_id, **body, "digest": digest}


def propose_change_set(instance: dict, changes: list[dict], author: str, summary: str) -> dict:
    validate_recipe_instance(instance)
    if not isinstance(changes, list) or not changes or not isinstance(author, str) or not author.strip() or not isinstance(summary, str) or not summary.strip():
        raise TuningProtocolError("change set requires changes, author, and summary")
    normalized = []
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"step_id", "operation", "value"}:
            raise TuningProtocolError("change set fields are invalid")
        _id(change["step_id"], "change step_id")
        if change["operation"] not in {"set_binding", "set_step_intent", "set_source_reference"}:
            raise TuningProtocolError("change set operation is unsupported")
        _safe(change["value"], "change set value")
        normalized.append(deepcopy(change))
    body = {"schema": CHANGE_SET_SCHEMA, "protocol": dict(AUTHORING_PROTOCOL), "instance_id": instance["id"],
            "expected_revision": instance["revision"], "changes": normalized, "author": author.strip(), "summary": summary.strip(), "status": "proposed"}
    item_id, digest = _digest_id("change", body)
    return {"id": item_id, **body, "digest": digest}


def accept_change_set(instance: dict, change_set: dict) -> dict:
    validate_recipe_instance(instance)
    validate_change_set(change_set)
    if change_set["status"] != "proposed" or change_set["instance_id"] != instance["id"] or change_set["expected_revision"] != instance["revision"]:
        raise TuningProtocolError("authoring change set is stale or not proposed")
    bindings = deepcopy(instance["bindings"])
    for change in change_set["changes"]:
        if change["operation"] == "set_binding":
            bindings[change["step_id"]] = deepcopy(change["value"])
    body = {"schema": INSTANCE_SCHEMA, "protocol": dict(AUTHORING_PROTOCOL), "blueprint_id": instance["blueprint_id"],
            "blueprint_digest": instance["blueprint_digest"], "revision": instance["revision"] + 1, "bindings": bindings}
    item_id, digest = _digest_id("instance", body)
    return {"id": item_id, **body, "digest": digest}


def freeze_snapshot(instance: dict, frozen_steps: list[dict], compile_reference: dict, author: str, summary: str) -> dict:
    validate_recipe_instance(instance)
    if not isinstance(frozen_steps, list) or not frozen_steps:
        raise TuningProtocolError("freeze snapshot must explicitly list frozen steps")
    normalized = []
    for step in frozen_steps:
        if not isinstance(step, dict) or set(step) != {"step_id", "semantic_digest"}:
            raise TuningProtocolError("freeze step fields are invalid")
        _id(step["step_id"], "freeze step_id")
        if not isinstance(step["semantic_digest"], str) or not _SHA256.fullmatch(step["semantic_digest"]):
            raise TuningProtocolError("freeze semantic digest must be sha256")
        normalized.append(deepcopy(step))
    if len({item["step_id"] for item in normalized}) != len(normalized):
        raise TuningProtocolError("freeze steps must be unique")
    body = {"schema": FREEZE_SCHEMA, "protocol": dict(AUTHORING_PROTOCOL), "instance_id": instance["id"],
            "instance_revision": instance["revision"], "frozen_steps": sorted(normalized, key=lambda item: item["step_id"]),
            "compile_reference": _reference(compile_reference, "compile reference"), "author": str(author or "").strip(), "summary": str(summary or "").strip()}
    if not body["author"] or not body["summary"]:
        raise TuningProtocolError("freeze author and summary are required")
    item_id, digest = _digest_id("freeze", body)
    return {"id": item_id, **body, "digest": digest}


def validate_recipe_blueprint(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != BLUEPRINT_SCHEMA or value.get("protocol") != AUTHORING_PROTOCOL:
        raise TuningProtocolError("recipe blueprint identity is invalid")
    body = {key: deepcopy(item) for key, item in value.items() if key not in {"id", "digest"}}
    item_id, digest = _digest_id("blueprint", body)
    if value.get("id") != item_id or value.get("digest") != digest:
        raise TuningProtocolError("recipe blueprint is not immutable")
    return value


def validate_recipe_instance(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != INSTANCE_SCHEMA or value.get("protocol") != AUTHORING_PROTOCOL:
        raise TuningProtocolError("recipe instance identity is invalid")
    _safe(value.get("bindings"), "instance bindings")
    body = {key: deepcopy(item) for key, item in value.items() if key not in {"id", "digest"}}
    item_id, digest = _digest_id("instance", body)
    if value.get("id") != item_id or value.get("digest") != digest:
        raise TuningProtocolError("recipe instance is not immutable")
    return value


def validate_change_set(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != CHANGE_SET_SCHEMA or value.get("protocol") != AUTHORING_PROTOCOL:
        raise TuningProtocolError("authoring change set identity is invalid")
    if value.get("status") != "proposed" or not isinstance(value.get("expected_revision"), int):
        raise TuningProtocolError("authoring change set status or revision is invalid")
    body = {key: deepcopy(item) for key, item in value.items() if key not in {"id", "digest"}}
    item_id, digest = _digest_id("change", body)
    if value.get("id") != item_id or value.get("digest") != digest:
        raise TuningProtocolError("authoring change set is not immutable")
    return value


def validate_freeze_snapshot(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != FREEZE_SCHEMA or value.get("protocol") != AUTHORING_PROTOCOL:
        raise TuningProtocolError("authoring freeze snapshot identity is invalid")
    if not isinstance(value.get("instance_revision"), int) or value["instance_revision"] < 1:
        raise TuningProtocolError("authoring freeze snapshot revision is invalid")
    steps = value.get("frozen_steps")
    if not isinstance(steps, list) or not steps:
        raise TuningProtocolError("authoring freeze snapshot must list frozen steps")
    seen = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"step_id", "semantic_digest"}:
            raise TuningProtocolError("authoring freeze step fields are invalid")
        step_id = _id(step["step_id"], "freeze step_id")
        if step_id in seen or not isinstance(step["semantic_digest"], str) or not _SHA256.fullmatch(step["semantic_digest"]):
            raise TuningProtocolError("authoring freeze step is invalid")
        seen.add(step_id)
    _reference(value.get("compile_reference"), "compile reference")
    body = {key: deepcopy(item) for key, item in value.items() if key not in {"id", "digest"}}
    item_id, digest = _digest_id("freeze", body)
    if value.get("id") != item_id or value.get("digest") != digest:
        raise TuningProtocolError("authoring freeze snapshot is not immutable")
    return value
