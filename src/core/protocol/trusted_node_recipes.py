"""Fail-closed CF-TUNING@1.4 trusted-node and dynamic-recipe facts."""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .tuning import TuningProtocolError, canonical_digest


TRUSTED_NODE_PROTOCOL = {"id": "CF-TUNING", "version": "1.4"}
_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_FORBIDDEN = re.compile(
    r"token|secret|password|credential|api[_-]?key|authorization|cookie|private[_-]?key|"
    r"code|script|command|executor|permission|topology|execution[_-]?plan|endpoint|model|tool",
    re.I,
)
_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|var|etc|tmp)/)")
_VALUE_TYPES = frozenset({"string", "string_list", "boolean", "number"})
_RELATIONS = frozenset({"uses", "produces", "informs"})


def _id(value: object, label: str) -> str:
    text = str(value or "")
    if not _ID.fullmatch(text):
        raise TuningProtocolError(f"{label} must be a stable identifier")
    return text


def _text(value: object, label: str, limit: int = 1000) -> str:
    text = " ".join(value.split()) if isinstance(value, str) else ""
    if not text or len(text) > limit or _FORBIDDEN.search(text) or _PATH.match(text):
        raise TuningProtocolError(f"{label} is invalid")
    return text


def _safe_value(value: Any, value_type: str, label: str) -> Any:
    if value_type == "string":
        return _text(value, label, 2000)
    if value_type == "string_list":
        if not isinstance(value, list) or len(value) > 100:
            raise TuningProtocolError(f"{label} must be a bounded string list")
        return [_text(item, label, 500) for item in value]
    if value_type == "boolean" and isinstance(value, bool):
        return value
    if value_type == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    raise TuningProtocolError(f"{label} does not match {value_type}")


def validate_preset(value: object) -> dict:
    expected = {
        "schema", "protocol", "id", "revision", "creator_label",
        "creator_description", "match_terms", "editable_fields",
        "developer_mapping_key",
    }
    if not isinstance(value, dict) or set(value) not in {frozenset(expected), frozenset({*expected, "digest"})}:
        raise TuningProtocolError("trusted node preset fields are invalid")
    if value["schema"] != "cartridgeflow.trusted_node_preset.v1" or value["protocol"] != TRUSTED_NODE_PROTOCOL:
        raise TuningProtocolError("trusted node preset protocol is invalid")
    preset_id = _id(value["id"], "trusted node preset id")
    mapping = _id(value["developer_mapping_key"], "developer mapping key")
    revision = value["revision"]
    if not isinstance(revision, int) or revision < 1:
        raise TuningProtocolError("trusted node preset revision is invalid")
    terms = value["match_terms"]
    if not isinstance(terms, list) or not terms or len(terms) > 32:
        raise TuningProtocolError("trusted node match terms are invalid")
    terms = [_text(item, "trusted node match term", 100) for item in terms]
    fields = value["editable_fields"]
    if not isinstance(fields, list) or len(fields) > 32:
        raise TuningProtocolError("trusted node editable fields are invalid")
    normalized_fields, seen = [], set()
    for field in fields:
        if not isinstance(field, dict) or set(field) != {"id", "label", "value_type", "required", "default"}:
            raise TuningProtocolError("trusted node editable field contract is invalid")
        field_id = _id(field["id"], "trusted node field id")
        if field_id in seen or _FORBIDDEN.search(field_id) or field["value_type"] not in _VALUE_TYPES or not isinstance(field["required"], bool):
            raise TuningProtocolError("trusted node editable field contract is invalid")
        default = field["default"]
        if default is None:
            if field["required"]:
                raise TuningProtocolError("required trusted node fields need a safe default")
        else:
            default = _safe_value(default, field["value_type"], f"default {field_id}")
        normalized_fields.append({
            "id": field_id,
            "label": _text(field["label"], "trusted node field label", 120),
            "value_type": field["value_type"],
            "required": field["required"],
            "default": deepcopy(default),
        })
        seen.add(field_id)
    normalized = {
        "schema": value["schema"],
        "protocol": deepcopy(TRUSTED_NODE_PROTOCOL),
        "id": preset_id,
        "revision": revision,
        "creator_label": _text(value["creator_label"], "trusted node creator label", 160),
        "creator_description": _text(value["creator_description"], "trusted node creator description", 500),
        "match_terms": terms,
        "editable_fields": normalized_fields,
        "developer_mapping_key": mapping,
    }
    if "digest" in value and value["digest"] != canonical_digest(normalized):
        raise TuningProtocolError("trusted node preset digest is invalid")
    return normalized


def preset_digest(preset: dict) -> str:
    return canonical_digest(validate_preset(preset))


def creator_preset_projection(preset: dict) -> dict:
    item = validate_preset(preset)
    return {
        "id": item["id"],
        "revision": item["revision"],
        "digest": canonical_digest(item),
        "label": item["creator_label"],
        "description": item["creator_description"],
        "match_terms": deepcopy(item["match_terms"]),
        "editable_fields": deepcopy(item["editable_fields"]),
    }


def create_dynamic_recipe(recipe_id: str, goal: str, draft: object, presets: list[dict]) -> dict:
    """Resolve an AI draft against exact registry facts; mappings never come from AI."""
    recipe_id = _id(recipe_id, "dynamic recipe id")
    goal = _text(goal, "dynamic recipe goal", 2000)
    if not isinstance(draft, dict) or set(draft) != {"nodes", "relations"}:
        raise TuningProtocolError("dynamic recipe draft fields are invalid")
    registry = {item["id"]: item for item in (validate_preset(value) for value in presets)}
    nodes = draft["nodes"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 8:
        raise TuningProtocolError("dynamic recipe needs one to eight trusted nodes")
    result_nodes, seen = [], set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "preset_id", "values"}:
            raise TuningProtocolError("dynamic recipe node fields are invalid")
        node_id = _id(node["id"], "dynamic recipe node id")
        preset_id = _id(node["preset_id"], "dynamic recipe preset id")
        if node_id in seen or preset_id not in registry or not isinstance(node["values"], dict):
            raise TuningProtocolError("dynamic recipe references an unknown trusted node preset")
        preset = registry[preset_id]
        contracts = {item["id"]: item for item in preset["editable_fields"]}
        if set(node["values"]) - set(contracts):
            raise TuningProtocolError("dynamic recipe values exceed the trusted node contract")
        values = {}
        for field_id, contract in contracts.items():
            raw = node["values"].get(field_id, contract["default"])
            if raw is None:
                if contract["required"]:
                    raise TuningProtocolError("dynamic recipe is missing a required creator value")
                continue
            values[field_id] = _safe_value(raw, contract["value_type"], f"node {node_id}.{field_id}")
        result_nodes.append({
            "id": node_id,
            "preset": {"id": preset_id, "revision": preset["revision"], "digest": canonical_digest(preset)},
            "creator_label": preset["creator_label"],
            "values": values,
            "developer_mapping_key": preset["developer_mapping_key"],
        })
        seen.add(node_id)
    relations = draft["relations"]
    if not isinstance(relations, list):
        raise TuningProtocolError("dynamic recipe relations are invalid")
    result_relations, relation_ids = [], set()
    for relation in relations:
        if not isinstance(relation, dict) or set(relation) != {"id", "from_node_id", "to_node_id", "relation"}:
            raise TuningProtocolError("dynamic recipe relation fields are invalid")
        relation_id = _id(relation["id"], "dynamic recipe relation id")
        source = _id(relation["from_node_id"], "dynamic recipe relation source")
        target = _id(relation["to_node_id"], "dynamic recipe relation target")
        if relation_id in relation_ids or source not in seen or target not in seen or source == target or relation["relation"] not in _RELATIONS:
            raise TuningProtocolError("dynamic recipe relation is invalid")
        result_relations.append({"id": relation_id, "from_node_id": source, "to_node_id": target, "relation": relation["relation"]})
        relation_ids.add(relation_id)
    _require_acyclic(seen, result_relations)
    body = {
        "schema": "cartridgeflow.dynamic_creator_recipe.v1",
        "protocol": deepcopy(TRUSTED_NODE_PROTOCOL),
        "id": recipe_id,
        "goal": goal,
        "nodes": result_nodes,
        "relations": result_relations,
    }
    return {**body, "digest": canonical_digest(body)}


def validate_dynamic_recipe(recipe: object, presets: list[dict]) -> dict:
    if not isinstance(recipe, dict) or recipe.get("schema") != "cartridgeflow.dynamic_creator_recipe.v1":
        raise TuningProtocolError("dynamic creator recipe is invalid")
    expected_digest = recipe.get("digest")
    draft = {
        "nodes": [{"id": item.get("id"), "preset_id": (item.get("preset") or {}).get("id"), "values": item.get("values")} for item in recipe.get("nodes") or []],
        "relations": deepcopy(recipe.get("relations") or []),
    }
    rebuilt = create_dynamic_recipe(str(recipe.get("id") or ""), str(recipe.get("goal") or ""), draft, presets)
    if rebuilt != recipe or expected_digest != rebuilt["digest"]:
        raise TuningProtocolError("dynamic creator recipe lineage is invalid")
    return rebuilt


def creator_recipe_projection(recipe: dict, presets: list[dict]) -> dict:
    recipe = validate_dynamic_recipe(recipe, presets)
    contracts = {item["id"]: creator_preset_projection(item) for item in presets}
    return {
        "id": recipe["id"],
        "goal": recipe["goal"],
        "nodes": [{
            "id": node["id"],
            "label": node["creator_label"],
            "description": contracts[node["preset"]["id"]]["description"],
            "preset": {key: node["preset"][key] for key in ("id", "revision", "digest")},
            "values": deepcopy(node["values"]),
            "editable_fields": deepcopy(contracts[node["preset"]["id"]]["editable_fields"]),
        } for node in recipe["nodes"]],
        "relations": deepcopy(recipe["relations"]),
    }


def capability_gap(goal: str, needed_capabilities: list[str], available_preset_ids: list[str]) -> dict:
    goal = _text(goal, "capability gap goal", 2000)
    if not isinstance(needed_capabilities, list) or not needed_capabilities or len(needed_capabilities) > 8:
        raise TuningProtocolError("capability gap needs one to eight missing capabilities")
    return {
        "schema": "cartridgeflow.creator_capability_gap.v1",
        "protocol": deepcopy(TRUSTED_NODE_PROTOCOL),
        "goal": goal,
        "needed_capabilities": [_text(item, "needed capability", 200) for item in needed_capabilities],
        "available_preset_ids": [_id(item, "available preset id") for item in available_preset_ids],
    }


def validate_node_values(preset: dict, values: object, *, require_required: bool = True) -> dict:
    preset = validate_preset(preset)
    if not isinstance(values, dict):
        raise TuningProtocolError("node values must be an object")
    contracts = {item["id"]: item for item in preset["editable_fields"]}
    if set(values) - set(contracts):
        raise TuningProtocolError("node values exceed the trusted node contract")
    if require_required:
        missing = {field_id for field_id, contract in contracts.items() if contract["required"]} - set(values)
        if missing:
            raise TuningProtocolError("node values are missing required trusted fields")
    normalized = {}
    for field_id, raw in values.items():
        normalized[field_id] = _safe_value(raw, contracts[field_id]["value_type"], f"node field {field_id}")
    return normalized


def _require_acyclic(node_ids: set[str], relations: list[dict]) -> None:
    outgoing = {node_id: [] for node_id in node_ids}
    indegree = {node_id: 0 for node_id in node_ids}
    for item in relations:
        outgoing[item["from_node_id"]].append(item["to_node_id"])
        indegree[item["to_node_id"]] += 1
    ready = [node_id for node_id, count in indegree.items() if count == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for target in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if visited != len(node_ids):
        raise TuningProtocolError("dynamic recipe relations contain a cycle")
