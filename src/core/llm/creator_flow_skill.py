"""Whole-flow product skill: compose only registered trusted node presets."""
from __future__ import annotations

import json
from typing import Any

from core.protocol.trusted_node_recipes import (
    capability_gap,
    create_dynamic_recipe,
    creator_preset_projection,
)
from core.protocol.tuning import TuningProtocolError


class CreatorFlowSkillError(ValueError):
    pass


def build_creator_flow_messages(goal: str, presets: list[dict]) -> list[dict]:
    safe_presets = [creator_preset_projection(item) for item in presets]
    if not safe_presets:
        raise CreatorFlowSkillError("No trusted node presets are available.")
    contract = {
        "recipe": {
            "nodes": [{"id": "unique-instance-id", "preset_id": "one supplied preset id", "values": {"declared_field": "value"}}],
            "relations": [{"id": "unique-relation-id", "from_node_id": "known node id", "to_node_id": "known node id", "relation": "uses|produces|informs"}],
        },
        "or": {"capability_gap": {"needed_capabilities": ["plain-language missing capability"]}},
    }
    return [
        {
            "role": "system",
            "content": (
                "Return JSON only. Dynamically compose a useful recipe using one to eight instances of only the supplied trusted preset ids. "
                "A preset may be reused. Fill only its declared editable fields and use only uses, produces, or informs relations. "
                "Never invent a preset, mapping, implementation, tool, model, permission, secret, endpoint, or executable fact. "
                "If the supplied presets cannot satisfy the goal, return capability_gap instead of a recipe. Write values and gaps in the user's language."
            ),
        },
        {"role": "user", "content": json.dumps({"goal": " ".join(str(goal).split()), "trusted_presets": safe_presets, "response_contract": contract}, ensure_ascii=False)},
    ]


def parse_creator_flow_result(content: str, goal: str, recipe_id: str, presets: list[dict]) -> dict:
    try:
        value: Any = json.loads(str(content or ""))
    except json.JSONDecodeError as exc:
        raise CreatorFlowSkillError("Whole-flow AI response must be JSON.") from exc
    if not isinstance(value, dict) or len(value) != 1:
        raise CreatorFlowSkillError("Whole-flow AI response shape is invalid.")
    if "capability_gap" in value:
        gap = value["capability_gap"]
        if not isinstance(gap, dict) or set(gap) != {"needed_capabilities"}:
            raise CreatorFlowSkillError("Whole-flow AI capability gap is invalid.")
        try:
            return capability_gap(goal, gap["needed_capabilities"], [item["id"] for item in presets])
        except TuningProtocolError as exc:
            raise CreatorFlowSkillError(str(exc)) from exc
    if "recipe" not in value:
        raise CreatorFlowSkillError("Whole-flow AI must return a recipe or capability gap.")
    try:
        return create_dynamic_recipe(recipe_id, goal, value["recipe"], presets)
    except TuningProtocolError as exc:
        raise CreatorFlowSkillError(str(exc)) from exc
