"""Whole-flow product skill: preserve intent before resolving implementations."""
from __future__ import annotations

import json
from typing import Any

from core.protocol.capability_cartridges import (
    CapabilityCartridgeError,
    create_semantic_recipe,
    creator_capability_projection,
)
from core.protocol.trusted_node_recipes import create_dynamic_recipe
from core.protocol.tuning import TuningProtocolError


class CreatorFlowSkillError(ValueError):
    pass


def _load_json_payload(content: str) -> Any:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        fence = text.rfind("```")
        if fence >= 0:
            text = text[:fence].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _creator_safe_capability(item: dict) -> dict:
    if item.get("schema") != "cartridgeflow.trusted_node_preset.v1":
        return creator_capability_projection(item)
    return {
        "id": item["id"],
        "revision": item["revision"],
        "trust_scope": "workspace",
        "label": item["creator_label"],
        "description": item["creator_description"],
        "match_terms": list(item["match_terms"]),
        "editable_fields": list(item["editable_fields"]),
        "inputs": [],
        "outputs": [],
    }


def build_creator_flow_messages(goal: str, capabilities: list[dict]) -> list[dict]:
    safe_capabilities = [_creator_safe_capability(item) for item in capabilities]
    contract = {
        "nodes": [{
            "id": "unique-stable-id",
            "label": "short user-facing outcome",
            "description": "what this step accomplishes and what the user should review",
            "needed_capability": "plain-language implementation requirement",
            "capability_id": "one supplied capability id or null",
            "values": {"declared_field": "value"},
        }],
            "relations": [{"id": "unique-relation-id", "from_node_id": "known node id", "to_node_id": "known node id", "relation": "uses|produces|informs"}],
    }
    return [
        {
            "role": "system",
            "content": (
                "Return JSON only. Create a complete one-to-eight step semantic recipe for the user's outcome. "
                "Do not remove or refuse a useful step merely because no implementation is supplied. For every step state its needed capability. "
                "When, and only when, one supplied capability clearly implements the step, copy its exact id and fill only declared editable fields. "
                "Otherwise set capability_id to null and use values={}. Never invent an implementation, tool, model, permission, secret, endpoint, or executable fact. "
                "Keep steps at a user-auditable capability granularity and use only uses, produces, or informs relations. Write all user-facing text in the user's language."
            ),
        },
        {"role": "user", "content": json.dumps({"goal": " ".join(str(goal).split()), "trusted_capabilities": safe_capabilities, "response_contract": contract}, ensure_ascii=False)},
    ]


def build_creator_flow_repair_messages(goal: str, capabilities: list[dict], invalid_content: str, reason: str) -> list[dict]:
    messages = build_creator_flow_messages(goal, capabilities)
    messages.append({"role": "assistant", "content": str(invalid_content or "")[:12_000]})
    messages.append({
        "role": "user",
        "content": (
            f"The previous response was rejected because: {str(reason or 'invalid output')[:300]} "
            "Return JSON only. The object must contain exactly nodes and relations, matching response_contract. "
            "Do not wrap the JSON in markdown."
        ),
    })
    return messages


def parse_creator_flow_result(content: str, goal: str, recipe_id: str, capabilities: list[dict]) -> tuple[dict, dict[str, dict]]:
    try:
        value: Any = _load_json_payload(content)
    except json.JSONDecodeError as exc:
        raise CreatorFlowSkillError("Whole-flow AI response must be JSON.") from exc
    if isinstance(value, dict) and set(value) == {"recipe"}:
        legacy_capabilities = [item for item in capabilities if (item.get("implementation") or {}).get("kind") == "node_snapshot"]
        presets = [item["implementation"]["preset"] for item in legacy_capabilities]
        presets.extend(item for item in capabilities if item.get("schema") == "cartridgeflow.trusted_node_preset.v1")
        try:
            recipe = create_dynamic_recipe(recipe_id, goal, value["recipe"], presets)
        except TuningProtocolError as exc:
            raise CreatorFlowSkillError(str(exc)) from exc
        return recipe, {item["id"]: item for item in legacy_capabilities}
    if not isinstance(value, dict) or set(value) != {"nodes", "relations"}:
        raise CreatorFlowSkillError("Whole-flow AI response shape is invalid.")
    try:
        return create_semantic_recipe(recipe_id, goal, value, capabilities)
    except CapabilityCartridgeError as exc:
        raise CreatorFlowSkillError(str(exc)) from exc
