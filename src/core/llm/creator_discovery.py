"""Strict model adapter for the Creator Studio's open-thinking entry point."""
from __future__ import annotations

import json
import re
from typing import Any


class CreatorDiscoveryError(ValueError):
    """A model result that cannot safely enter the creator journey."""


_ID = re.compile(r"^[a-z][a-z0-9-]{1,47}$")
_FORBIDDEN_TEXT = re.compile(r"https?://|\b(api|endpoint|mcp|dlc|root flow|token|secret|credential)\b", re.IGNORECASE)
_POSSIBILITY_KEYS = frozenset({"id", "title", "outcome", "why_it_fits", "first_week_output", "needs_confirmation", "recipe"})
_RECIPE_KEYS = frozenset({"intent", "steps"})
_STEP_KEYS = frozenset({"id", "intent", "inputs", "outputs"})
_SOURCE_CANDIDATE_KEYS = frozenset({"id", "name", "provides", "why_recommended", "risk", "review_focus", "remote_url", "rss_url"})
_DEFAULT_RECIPE_KEYS = frozenset({"recipe"})


def build_creator_discovery_messages(context: str) -> list[dict]:
    """Constrain the model to creator language and a small, reviewable recipe shape."""
    normalized = " ".join(str(context).split())
    if not normalized:
        raise CreatorDiscoveryError("A discovery context is required.")
    contract = {
        "possibilities": [{
            "id": "lowercase-slug", "title": "short creator-facing title", "outcome": "concrete outcome",
            "why_it_fits": "why this direction fits the supplied context", "first_week_output": "a small first-week result",
            "needs_confirmation": ["one question to confirm"],
            "recipe": {"intent": "creator-facing recipe intent", "steps": [{"id": "lowercase-slug", "intent": "creator-facing step", "inputs": [], "outputs": []}]},
        }],
    }
    return [
        {"role": "system", "content": "Return JSON only. Produce exactly three distinct possibilities for a creator with an open-ended idea. Use only the supplied context; do not claim facts, invent sources, or imply that any source was checked. Write in the user's language and creator language. Do not mention implementation, APIs, models, tools, nodes, protocols, credentials, URLs, or technical terms. Each recipe must have two to five plain-language steps."},
        {"role": "user", "content": json.dumps({"context": normalized, "response_contract": contract}, ensure_ascii=False)},
    ]


def parse_creator_discovery(content: str) -> list[dict]:
    """Validate and normalize a model response before it becomes selectable work."""
    try:
        payload: Any = json.loads(str(content or ""))
    except json.JSONDecodeError as exc:
        raise CreatorDiscoveryError("AI discovery response must be JSON.") from exc
    possibilities = payload.get("possibilities") if isinstance(payload, dict) and set(payload) == {"possibilities"} else None
    if not isinstance(possibilities, list) or len(possibilities) != 3:
        raise CreatorDiscoveryError("AI discovery response must contain exactly three possibilities.")
    normalized = [_normalize_possibility(item) for item in possibilities]
    if len({item["id"] for item in normalized}) != len(normalized):
        raise CreatorDiscoveryError("AI discovery possibility ids must be unique.")
    return normalized


def build_default_recipe_messages(context: str) -> list[dict]:
    normalized = " ".join(str(context).split())
    if not normalized:
        raise CreatorDiscoveryError("A creation goal is required.")
    contract = {"recipe": {"intent": "creator goal", "steps": [{"id": "lowercase-slug", "intent": "creator-facing default step", "inputs": [], "outputs": []}]}}
    return [{"role": "system", "content": "Return JSON only. Turn the supplied creator goal into one default, editable flow with three to six steps. This is an untrusted starting draft, not a verified or runnable plan. Use the user's language and creator language. Do not mention implementation, APIs, models, tools, nodes, protocols, credentials, URLs, or technical terms. Every step must be a plain-language outcome the creator can review."}, {"role": "user", "content": json.dumps({"goal": normalized, "response_contract": contract}, ensure_ascii=False)}]


def parse_default_recipe(content: str) -> dict:
    try:
        payload: Any = json.loads(str(content or ""))
    except json.JSONDecodeError as exc:
        raise CreatorDiscoveryError("AI default recipe response must be JSON.") from exc
    recipe = payload.get("recipe") if isinstance(payload, dict) and set(payload) == _DEFAULT_RECIPE_KEYS else None
    if not isinstance(recipe, dict) or set(recipe) != _RECIPE_KEYS or not isinstance(recipe.get("steps"), list) or not 3 <= len(recipe["steps"]) <= 6:
        raise CreatorDiscoveryError("AI default recipe shape is invalid.")
    steps = [_normalize_step(item) for item in recipe["steps"]]
    if len({item["id"] for item in steps}) != len(steps):
        raise CreatorDiscoveryError("AI default recipe step ids must be unique.")
    return {"intent": _text(recipe["intent"], "recipe intent", 300), "steps": steps}


def build_source_discovery_messages(intent: str, steps: list[dict], request: str) -> list[dict]:
    """Ask for source candidates without treating the model's claims as accepted facts."""
    normalized_request = " ".join(str(request).split())
    if not normalized_request:
        raise CreatorDiscoveryError("A source discovery request is required.")
    recipe = {"intent": " ".join(str(intent).split()), "steps": [" ".join(str(item.get("intent") or "").split()) for item in steps if isinstance(item, dict)]}
    contract = {"candidates": [{"id": "lowercase-slug", "name": "source identity", "provides": "what it may provide", "why_recommended": "why to review it", "risk": "a plain-language limitation", "review_focus": "what the creator should inspect before adopting", "remote_url": "https URL", "rss_url": "https RSS URL or empty string"}]}
    return [
        {"role": "system", "content": "Return JSON only. Produce exactly three distinct public source candidates for the supplied creator request and recipe. Every candidate is only a suggestion for review, not a verified fact. Use creator language. Do not state that content was checked or is current. Do not mention implementation, APIs, models, tools, nodes, protocols, credentials, or technical configuration. Only use credential-free HTTPS URLs. The risk and review focus must be concrete."},
        {"role": "user", "content": json.dumps({"recipe": recipe, "source_request": normalized_request, "response_contract": contract}, ensure_ascii=False)},
    ]


def parse_source_discovery(content: str) -> list[dict]:
    """Accept only bounded, public candidate descriptions from the model."""
    try:
        payload: Any = json.loads(str(content or ""))
    except json.JSONDecodeError as exc:
        raise CreatorDiscoveryError("AI source discovery response must be JSON.") from exc
    candidates = payload.get("candidates") if isinstance(payload, dict) and set(payload) == {"candidates"} else None
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise CreatorDiscoveryError("AI source discovery response must contain exactly three candidates.")
    normalized = [_normalize_source_candidate(item) for item in candidates]
    if len({item["id"] for item in normalized}) != len(normalized):
        raise CreatorDiscoveryError("AI source candidate ids must be unique.")
    return normalized


def _normalize_possibility(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) != _POSSIBILITY_KEYS:
        raise CreatorDiscoveryError("AI discovery possibility shape is invalid.")
    recipe = value["recipe"]
    if not isinstance(recipe, dict) or set(recipe) != _RECIPE_KEYS:
        raise CreatorDiscoveryError("AI discovery recipe shape is invalid.")
    identifier = _identifier(value["id"], "possibility")
    confirmations = value["needs_confirmation"]
    if not isinstance(confirmations, list) or not 1 <= len(confirmations) <= 4:
        raise CreatorDiscoveryError("AI discovery confirmations are invalid.")
    steps = recipe["steps"]
    if not isinstance(steps, list) or not 2 <= len(steps) <= 5:
        raise CreatorDiscoveryError("AI discovery recipes need two to five steps.")
    result_steps = [_normalize_step(item) for item in steps]
    if len({item["id"] for item in result_steps}) != len(result_steps):
        raise CreatorDiscoveryError("AI discovery step ids must be unique.")
    return {"id": identifier, "title": _text(value["title"], "title", 100), "outcome": _text(value["outcome"], "outcome", 300), "why_it_fits": _text(value["why_it_fits"], "why_it_fits", 300), "first_week_output": _text(value["first_week_output"], "first_week_output", 300), "needs_confirmation": [_text(item, "confirmation", 120) for item in confirmations], "recipe": {"intent": _text(recipe["intent"], "recipe intent", 300), "steps": result_steps}}


def _normalize_step(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) != _STEP_KEYS or value["inputs"] != [] or value["outputs"] != []:
        raise CreatorDiscoveryError("AI discovery step shape is invalid.")
    return {"id": _identifier(value["id"], "step"), "intent": _text(value["intent"], "step intent", 300), "inputs": [], "outputs": []}


def _normalize_source_candidate(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) != _SOURCE_CANDIDATE_KEYS:
        raise CreatorDiscoveryError("AI source candidate shape is invalid.")
    remote_url = _https_url(value["remote_url"], "source URL")
    rss_url = str(value["rss_url"] or "").strip()
    if rss_url:
        rss_url = _https_url(rss_url, "RSS URL")
    return {"id": _identifier(value["id"], "source candidate"), "name": _text(value["name"], "source name", 160), "provides": _text(value["provides"], "source provides", 300), "why_recommended": _text(value["why_recommended"], "source recommendation", 300), "risk": _text(value["risk"], "source risk", 300), "review_focus": _text(value["review_focus"], "source review focus", 300), "remote_url": remote_url, "rss_url": rss_url}


def _identifier(value: Any, field: str) -> str:
    identifier = _text(value, f"{field} id", 48)
    if not _ID.fullmatch(identifier):
        raise CreatorDiscoveryError("AI discovery ids must be lowercase slugs.")
    return identifier


def _text(value: Any, field: str, limit: int) -> str:
    text = " ".join(str(value).split()) if isinstance(value, str) else ""
    if not text or len(text) > limit or _FORBIDDEN_TEXT.search(text):
        raise CreatorDiscoveryError(f"AI discovery {field} is invalid.")
    return text


def _https_url(value: Any, field: str) -> str:
    from urllib.parse import urlsplit

    url = str(value or "").strip()
    parsed = urlsplit(url)
    if len(url) > 2048 or parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise CreatorDiscoveryError(f"AI discovery {field} is invalid.")
    if any(re.search(r"token|secret|password|credential|api[_-]?key|authorization|cookie|sig|signature|key", key, re.IGNORECASE) for key in parsed.query.split("&")):
        raise CreatorDiscoveryError(f"AI discovery {field} is invalid.")
    return url
