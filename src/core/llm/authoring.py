"""Strict AI-authoring proposal adapter; conversation is context, never a fact store."""
from __future__ import annotations

import json
from typing import Any

from core.protocol.authoring_contract import _validate_change  # Contract-owned validation boundary.
from core.protocol.tuning import TuningProtocolError


class AuthoringProposalError(ValueError):
    code = "AI_AUTHORING_PROPOSAL_INVALID"


def build_authoring_messages(instance: dict, capabilities: list[str], prompt: str) -> list[dict]:
    """Expose only immutable design facts and explicitly declared proposal capabilities."""
    allowed = sorted({str(x) for x in capabilities} & {"set_binding", "set_step_intent", "set_source_reference"})
    if not allowed:
        raise AuthoringProposalError("AI authoring has no declared proposal capabilities.")
    facts = {"instance_id": instance["id"], "instance_digest": instance["digest"], "revision": instance["revision"],
             "steps": instance["blueprint"]["steps"], "source_references": instance["blueprint"]["source_references"]}
    return [{"role": "system", "content": "Return JSON only. Propose only the listed operations. Chat is not a source of facts; cite only supplied source ids."},
            {"role": "user", "content": json.dumps({"facts": facts, "capabilities": allowed, "request": str(prompt)[:4000]}, ensure_ascii=False)}]


def parse_authoring_proposal(content: str, instance: dict, capabilities: list[str]) -> list[dict]:
    """Reject model output outside the declared semantic editing surface."""
    try:
        data: Any = json.loads(str(content or ""))
    except json.JSONDecodeError as exc:
        raise AuthoringProposalError("AI authoring response must be JSON.") from exc
    changes = data.get("changes") if isinstance(data, dict) else None
    if not isinstance(changes, list) or not changes:
        raise AuthoringProposalError("AI authoring response must contain non-empty changes.")
    declared = set(capabilities)
    normalized = []
    try:
        for change in changes:
            if not isinstance(change, dict) or change.get("operation") not in declared:
                raise AuthoringProposalError("AI proposed an undeclared capability.")
            normalized.append(_validate_change(change, instance["blueprint"]))
    except TuningProtocolError as exc:
        raise AuthoringProposalError(str(exc)) from exc
    if len({item["id"] for item in normalized}) != len(normalized):
        raise AuthoringProposalError("AI authoring change ids must be unique.")
    return normalized
