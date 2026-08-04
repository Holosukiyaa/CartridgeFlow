"""Node product skill: deepen one trusted node through declared fields only."""
from __future__ import annotations

import json
from typing import Any

from core.protocol.trusted_node_recipes import creator_preset_projection, validate_node_values
from core.protocol.tuning import TuningProtocolError


class CreatorNodeSkillError(ValueError):
    pass


def build_creator_node_messages(node: dict, preset: dict, request: str) -> list[dict]:
    safe_preset = creator_preset_projection(preset)
    facts = {
        "node_id": node["id"],
        "label": node["creator_label"],
        "current_values": node["values"],
        "editable_fields": safe_preset["editable_fields"],
    }
    return [
        {
            "role": "system",
            "content": (
                "Return JSON only as {\"values\": {...}}. Deepen exactly the supplied node. "
                "Return only declared editable fields with their declared value types. Keep useful current values unless the request changes them. "
                "Do not change node identity, preset, topology, sources, mappings, implementation, tools, models, permissions, secrets, or endpoints."
            ),
        },
        {"role": "user", "content": json.dumps({"node": facts, "request": str(request)[:4000]}, ensure_ascii=False)},
    ]


def parse_creator_node_result(content: str, preset: dict) -> dict:
    try:
        value: Any = json.loads(str(content or ""))
    except json.JSONDecodeError as exc:
        raise CreatorNodeSkillError("Node AI response must be JSON.") from exc
    if not isinstance(value, dict) or set(value) != {"values"}:
        raise CreatorNodeSkillError("Node AI response shape is invalid.")
    try:
        return validate_node_values(preset, value["values"], require_required=False)
    except TuningProtocolError as exc:
        raise CreatorNodeSkillError(str(exc)) from exc
