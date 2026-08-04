"""Fail-closed developer recipe templates for CF-TUNING@1.3."""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .tuning import TuningProtocolError, canonical_digest


TEMPLATE_PROTOCOL = {"id": "CF-TUNING", "version": "1.3"}
_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_FORBIDDEN = re.compile(r"token|secret|password|credential|api[_-]?key|authorization|cookie|code|script|executor|permission|topology|execution", re.I)


def _id(value: object, label: str) -> str:
    text = str(value or "")
    if not _ID.fullmatch(text):
        raise TuningProtocolError(f"{label} must be a stable identifier")
    return text


def validate_template(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"schema", "protocol", "id", "revision", "steps"}:
        raise TuningProtocolError("developer recipe template fields are invalid")
    if value["schema"] != "cartridgeflow.developer_recipe_template.v1" or value["protocol"] != TEMPLATE_PROTOCOL:
        raise TuningProtocolError("developer recipe template protocol is invalid")
    _id(value["id"], "template id")
    if not isinstance(value["revision"], int) or value["revision"] < 1 or not isinstance(value["steps"], list) or not value["steps"]:
        raise TuningProtocolError("template revision and steps are invalid")
    steps, seen = [], set()
    for step in value["steps"]:
        if not isinstance(step, dict) or set(step) != {"id", "creator_label", "editable_fields", "developer_mapping_key", "required"}:
            raise TuningProtocolError("template step fields are invalid")
        step_id = _id(step["id"], "template step id")
        _id(step["developer_mapping_key"], "developer mapping key")
        if step_id in seen or not isinstance(step["creator_label"], str) or not step["creator_label"].strip() or not isinstance(step["required"], bool):
            raise TuningProtocolError("template step identity is invalid")
        fields = step["editable_fields"]
        if not isinstance(fields, list) or len(set(fields)) != len(fields) or any(not isinstance(item, str) or not _ID.fullmatch(item) or _FORBIDDEN.search(item) for item in fields):
            raise TuningProtocolError("template editable fields are invalid")
        seen.add(step_id); steps.append(deepcopy(step))
    return {"schema": value["schema"], "protocol": deepcopy(value["protocol"]), "id": value["id"], "revision": value["revision"], "steps": steps}


def create_instance(template: dict, instance_id: str, values: dict[str, dict[str, Any]]) -> dict:
    template = validate_template(template); _id(instance_id, "instance id")
    if not isinstance(values, dict) or set(values) - {item["id"] for item in template["steps"]}:
        raise TuningProtocolError("instance values target an unknown template step")
    steps = []
    for step in template["steps"]:
        fields = values.get(step["id"], {})
        if not isinstance(fields, dict) or set(fields) - set(step["editable_fields"]):
            raise TuningProtocolError("instance fields exceed the template contract")
        steps.append({"id": step["id"], "creator_label": step["creator_label"], "values": deepcopy(fields), "developer_mapping_key": step["developer_mapping_key"], "required": step["required"]})
    body = {"schema": "cartridgeflow.creator_recipe_instance.v1", "protocol": deepcopy(TEMPLATE_PROTOCOL), "id": instance_id, "template": {"id": template["id"], "revision": template["revision"], "digest": canonical_digest(template)}, "steps": steps}
    return {**body, "digest": canonical_digest(body)}


def creator_blueprint_from_instance(instance: dict) -> tuple[list[dict], dict]:
    """Project a pinned template instance into legacy immutable authoring facts.

    The mapping remains alongside the projection and is never creator-visible.
    """
    if not isinstance(instance, dict) or instance.get("schema") != "cartridgeflow.creator_recipe_instance.v1":
        raise TuningProtocolError("creator recipe instance is invalid")
    steps = []
    mappings = {}
    for item in instance.get("steps", []):
        step_id = _id(item.get("id"), "instance step id")
        mapping = _id(item.get("developer_mapping_key"), "instance mapping key")
        steps.append({"id": step_id, "intent": str(item.get("creator_label") or "").strip(), "inputs": {}, "outputs": {}})
        mappings[step_id] = mapping
    if not steps:
        raise TuningProtocolError("creator recipe instance has no steps")
    return steps, mappings
