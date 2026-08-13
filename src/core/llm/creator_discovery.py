"""Strict model adapter for the Intent Studio discovery entry point."""
from __future__ import annotations

import json
import re
from typing import Any


class CreatorDiscoveryError(ValueError):
    """A model result that cannot safely enter the creator journey."""


class CreatorDiscoveryLanguageError(CreatorDiscoveryError):
    """The model returned valid structure in the wrong interface language."""


_ID = re.compile(r"^[a-z][a-z0-9-]{1,47}$")
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
_FORBIDDEN_TEXT = re.compile(r"https?://|\b(api|endpoint|mcp|dlc|root flow|token|secret|credential)\b", re.IGNORECASE)
_DISCOVERY_KEYS = frozenset({"mode", "clarification", "possibilities"})
_CLARIFICATION_KEYS = frozenset({"question", "why_it_matters", "suggested_answers"})
_POSSIBILITY_KEYS = frozenset({"id", "title", "outcome", "why_it_fits", "first_week_output", "needs_confirmation", "recipe"})
_RECIPE_KEYS = frozenset({"intent", "steps"})
_STEP_KEYS = frozenset({"id", "intent", "inputs", "outputs"})
_SOURCE_CANDIDATE_KEYS = frozenset({"id", "name", "provides", "why_recommended", "risk", "review_focus", "remote_url", "rss_url"})
_DEFAULT_RECIPE_KEYS = frozenset({"recipe"})


def build_creator_discovery_messages(context: str, output_locale: str = "zh-CN") -> list[dict]:
    """Ask the model whether to clarify the goal or propose reviewable directions."""
    normalized = " ".join(str(context).split())
    if not normalized:
        raise CreatorDiscoveryError("A discovery context is required.")
    valid_response_shapes = {
        "clarify": {
            "mode": "clarify",
            "clarification": {
                "question": "一个会改变方向选择的关键问题？",
                "why_it_matters": "这个答案会改变后续方向。",
                "suggested_answers": ["第一个简短选项", "第二个简短选项"],
            },
            "possibilities": [],
        },
        "propose": {
            "mode": "propose",
            "clarification": None,
            "possibilities": [
                {
                    "id": "first-direction", "title": "第一个方向", "outcome": "第一个具体结果。",
                    "why_it_fits": "说明第一个方向为什么合适。", "first_week_output": "第一周可以完成的小成果。",
                    "needs_confirmation": [],
                    "recipe": {"intent": "第一个方向的目标", "steps": [
                        {"id": "first-step", "intent": "完成第一个可理解步骤", "inputs": [], "outputs": []},
                        {"id": "second-step", "intent": "完成第二个可理解步骤", "inputs": [], "outputs": []},
                    ]},
                },
                {
                    "id": "second-direction", "title": "第二个方向", "outcome": "另一个不同的具体结果。",
                    "why_it_fits": "说明第二个方向为什么合适。", "first_week_output": "另一个第一周小成果。",
                    "needs_confirmation": [],
                    "recipe": {"intent": "第二个方向的目标", "steps": [
                        {"id": "compare-options", "intent": "比较相关选择", "inputs": [], "outputs": []},
                        {"id": "review-result", "intent": "审核形成的草稿", "inputs": [], "outputs": []},
                    ]},
                },
            ],
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "Return JSON only. Decide whether the creator's goal is specific enough to compare useful directions. "
                "If one missing answer would materially change the result, return mode=clarify, one decisive question, why it matters, "
                "two to four short suggested answers, and possibilities=[]. Otherwise return mode=propose, clarification=null, and two to four genuinely distinct possibilities. "
                "For each possibility, needs_confirmation must be a JSON list with zero to four short questions; use [] when the supplied context already answers everything important. "
                "Use only the supplied context; do not claim facts, invent sources, or imply that any source was checked. "
                f"Write every user-facing field in {output_locale}. "
                "Do not introduce implementation details, APIs, models, tools, nodes, protocols, credentials, URLs, or technical terms that the creator did not use. "
                "Preserve creator-supplied domain terms such as RSS or AI when they are central to the requested outcome. "
                "Each proposed recipe must have two to five plain-language steps."
            ),
        },
        {"role": "user", "content": json.dumps({"context": normalized, "output_locale": output_locale, "valid_response_shapes": valid_response_shapes}, ensure_ascii=False)},
    ]


def build_creator_discovery_repair_messages(
    context: str,
    invalid_content: str,
    failure_reason: str,
    output_locale: str = "zh-CN",
) -> list[dict]:
    """Give the same model one bounded chance to repair the complete output contract."""
    messages = build_creator_discovery_messages(context, output_locale)
    messages.append({"role": "assistant", "content": str(invalid_content or "")[:12_000]})
    messages.append({
        "role": "user",
        "content": (
            f"The previous response was rejected because: {str(failure_reason or 'invalid output')[:300]} "
            f"Return the complete JSON object again with the same meaning, one exact valid_response_shapes structure, and every user-facing field in {output_locale}. "
            "Do not add a clarification or a needs_confirmation question merely to make a list non-empty. Return JSON only."
        ),
    })
    return messages


def parse_creator_discovery(content: str, output_locale: str = "zh-CN") -> dict:
    """Validate the AI decision before it becomes selectable Creator work."""
    try:
        payload: Any = json.loads(str(content or ""))
    except json.JSONDecodeError as exc:
        raise CreatorDiscoveryError("AI discovery response must be JSON.") from exc
    if not isinstance(payload, dict) or set(payload) != _DISCOVERY_KEYS:
        raise CreatorDiscoveryError("AI discovery response shape is invalid.")
    mode = payload.get("mode")
    clarification = payload.get("clarification")
    possibilities = payload.get("possibilities")
    if mode == "clarify":
        if not isinstance(clarification, dict) or set(clarification) != _CLARIFICATION_KEYS or possibilities != []:
            raise CreatorDiscoveryError("AI clarification response shape is invalid.")
        answers = clarification.get("suggested_answers")
        if not isinstance(answers, list) or not 2 <= len(answers) <= 4:
            raise CreatorDiscoveryError("AI clarification needs two to four suggested answers.")
        return {
            "mode": "clarify",
            "clarification": {
                "question": _localized_text(clarification.get("question"), "clarification question", 240, output_locale),
                "why_it_matters": _localized_text(clarification.get("why_it_matters"), "clarification reason", 300, output_locale),
                "suggested_answers": [_localized_text(item, "suggested answer", 120, output_locale) for item in answers],
            },
            "possibilities": [],
        }
    if mode != "propose" or clarification is not None or not isinstance(possibilities, list) or not 2 <= len(possibilities) <= 4:
        raise CreatorDiscoveryError("AI proposal response needs two to four possibilities.")
    normalized = [_normalize_possibility(item, output_locale) for item in possibilities]
    if len({item["id"] for item in normalized}) != len(normalized):
        raise CreatorDiscoveryError("AI discovery possibility ids must be unique.")
    return {"mode": "propose", "clarification": None, "possibilities": normalized}


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


def _normalize_possibility(value: Any, output_locale: str) -> dict:
    if not isinstance(value, dict) or set(value) != _POSSIBILITY_KEYS:
        raise CreatorDiscoveryError("AI discovery possibility shape is invalid.")
    recipe = value["recipe"]
    if not isinstance(recipe, dict) or set(recipe) != _RECIPE_KEYS:
        raise CreatorDiscoveryError("AI discovery recipe shape is invalid.")
    identifier = _identifier(value["id"], "possibility")
    confirmations = value["needs_confirmation"]
    if not isinstance(confirmations, list) or len(confirmations) > 4:
        raise CreatorDiscoveryError("AI discovery confirmations are invalid.")
    steps = recipe["steps"]
    if not isinstance(steps, list) or not 2 <= len(steps) <= 5:
        raise CreatorDiscoveryError("AI discovery recipes need two to five steps.")
    result_steps = [_normalize_step(item, output_locale) for item in steps]
    if len({item["id"] for item in result_steps}) != len(result_steps):
        raise CreatorDiscoveryError("AI discovery step ids must be unique.")
    return {"id": identifier, "title": _localized_text(value["title"], "title", 100, output_locale), "outcome": _localized_text(value["outcome"], "outcome", 300, output_locale), "why_it_fits": _localized_text(value["why_it_fits"], "why_it_fits", 300, output_locale), "first_week_output": _localized_text(value["first_week_output"], "first_week_output", 300, output_locale), "needs_confirmation": [_localized_text(item, "confirmation", 120, output_locale) for item in confirmations], "recipe": {"intent": _localized_text(recipe["intent"], "recipe intent", 300, output_locale), "steps": result_steps}}


def _normalize_step(value: Any, output_locale: str | None = None) -> dict:
    if not isinstance(value, dict) or set(value) != _STEP_KEYS or value["inputs"] != [] or value["outputs"] != []:
        raise CreatorDiscoveryError("AI discovery step shape is invalid.")
    intent = _text(value["intent"], "step intent", 300)
    if output_locale:
        intent = _require_locale(intent, "step intent", output_locale)
    return {"id": _identifier(value["id"], "step"), "intent": intent, "inputs": [], "outputs": []}


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


def _localized_text(value: Any, field: str, limit: int, output_locale: str) -> str:
    return _require_locale(_text(value, field, limit), field, output_locale)


def _require_locale(text: str, field: str, output_locale: str) -> str:
    if output_locale == "zh-CN":
        han_count = len(_HAN.findall(text))
        latin_words = _LATIN_WORD.findall(text)
        latin_character_count = sum(len(word) for word in latin_words if word.lower() not in {"ai", "fps", "rag"})
        if not han_count or latin_character_count > max(8, han_count * 2):
            raise CreatorDiscoveryLanguageError(f"AI discovery {field} must be written in Simplified Chinese.")
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
