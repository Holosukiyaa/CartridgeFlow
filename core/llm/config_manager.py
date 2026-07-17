import json
import os
import re
from copy import deepcopy
from pathlib import Path

from .config import ModelConfig

ROOT = Path(__file__).resolve().parents[2]
LLM_DIR = ROOT / "config" / "llm"
PROVIDERS_PATH = LLM_DIR / "providers.json"
ASSIGNMENTS_PATH = LLM_DIR / "assignments.json"
RETRY_PATH = LLM_DIR / "retry.json"

DEFAULT_DEEPSEEK_PROVIDER = {
    "id": "default-deepseek",
    "name": "Default DeepSeek",
    "api_type": "openai",
    "base_url": "https://api.deepseek.com",
    "api_key": "",
    "default_model": "deepseek-chat",
    "wire_api": "chat_completions",
    "enabled": True,
    "tested_ok": False,
    "source": "default",
    "timeout": 120,
}

DEFAULT_RETRY = {
    "max_retries": 3,
    "initial_delay": 1.0,
    "max_delay": 60.0,
    "exponential_base": 2,
    "retry_on_status": [429, 500, 502, 503, 504],
    "retry_on_errors": ["timeout", "connection"],
}


def ensure_llm_config():
    LLM_DIR.mkdir(parents=True, exist_ok=True)
    if not PROVIDERS_PATH.exists():
        _write_json(PROVIDERS_PATH, {"version": 1, "providers": [DEFAULT_DEEPSEEK_PROVIDER, _env_provider()]})
    if not ASSIGNMENTS_PATH.exists():
        env = _env_provider()
        _write_json(ASSIGNMENTS_PATH, {
            "version": 1,
            "defaults": {
                "steward": {"provider_id": env["id"], "model": env["default_model"]},
                "runtime": {"provider_id": env["id"], "model": env["default_model"]},
                "mentor": {"provider_id": env["id"], "model": env["default_model"]},
                "worker": {"provider_id": env["id"], "model": env["default_model"]},
            },
            "cartridges": {},
            "nodes": {},
        })
    if not RETRY_PATH.exists():
        _write_json(RETRY_PATH, DEFAULT_RETRY)


def list_providers(include_disabled: bool = True) -> list[dict]:
    ensure_llm_config()
    data = _read_json(PROVIDERS_PATH, {"version": 1, "providers": []})
    providers = [normalize_provider(_merge_env_provider(item)) for item in data.get("providers", [])]
    changed = providers != data.get("providers", [])
    if not any(item.get("id") == DEFAULT_DEEPSEEK_PROVIDER["id"] for item in providers):
        providers.insert(0, dict(DEFAULT_DEEPSEEK_PROVIDER))
        changed = True
    enabled = [item for item in providers if item.get("enabled", True)]
    if len(enabled) != 1:
        active_id = next((item.get("id") for item in providers if item.get("api_key")), None) or (providers[0].get("id") if providers else "")
        providers = [{**item, "enabled": item.get("id") == active_id} for item in providers]
        changed = True
    if changed:
        save_providers(providers)
    if include_disabled:
        return providers
    return [item for item in providers if item.get("enabled", True)]


def save_providers(providers: list[dict]):
    _write_json(PROVIDERS_PATH, {"version": 1, "providers": providers})


def get_provider(provider_id: str) -> dict | None:
    return next((item for item in list_providers() if item.get("id") == provider_id), None)


def upsert_provider(provider: dict) -> dict:
    providers = list_providers()
    item = normalize_provider(provider)
    if not item.get("id"):
        base = _slug(item.get("name") or item.get("api_type") or "provider")
        existing = {old.get("id") for old in providers}
        item["id"] = _next_id(base, existing)
    replaced = False
    for index, old in enumerate(providers):
        if old.get("id") == item.get("id"):
            if not item.get("api_key"):
                item["api_key"] = old.get("api_key", "")
            item["tested_ok"] = bool(item.get("tested_ok", old.get("tested_ok", False)))
            providers[index] = item
            replaced = True
            break
    if not replaced:
        providers.append(item)
    if item.get("enabled", True):
        providers = [{**old, "enabled": old.get("id") == item.get("id")} for old in providers]
    save_providers(providers)
    return item


def activate_provider(provider_id: str) -> dict | None:
    providers = list_providers()
    if not any(item.get("id") == provider_id for item in providers):
        return None
    providers = [{**item, "enabled": item.get("id") == provider_id} for item in providers]
    save_providers(providers)
    return next(item for item in providers if item.get("id") == provider_id)


def delete_provider(provider_id: str) -> bool:
    providers = list_providers()
    kept = [item for item in providers if item.get("id") != provider_id]
    if len(kept) == len(providers):
        return False
    save_providers(kept)
    return True


def mark_provider_tested(provider_id: str, ok: bool = True) -> dict | None:
    providers = list_providers()
    found = None
    for item in providers:
        if item.get("id") == provider_id:
            item["tested_ok"] = bool(ok)
            found = item
            break
    if found:
        save_providers(providers)
    return found


def get_assignments() -> dict:
    ensure_llm_config()
    return _read_json(ASSIGNMENTS_PATH, {"version": 1, "defaults": {}, "cartridges": {}, "nodes": {}})


def save_assignments(data: dict):
    data.setdefault("version", 1)
    data.setdefault("defaults", {})
    data.setdefault("cartridges", {})
    data.setdefault("nodes", {})
    _write_json(ASSIGNMENTS_PATH, data)


def resolve_model(role: str = "runtime", cartridge_id: str | None = None, node_id: str | None = None) -> ModelConfig:
    ensure_llm_config()
    assignment = _assignment_for(role, cartridge_id, node_id)
    providers = list_providers(False)
    provider = None
    assignment_provider_found = False
    if assignment and assignment.get("provider_id"):
        provider = get_provider(assignment.get("provider_id"))
        assignment_provider_found = bool(provider)
    provider = provider or next((item for item in providers if item.get("api_key")), None) or next(iter(providers), None) or DEFAULT_DEEPSEEK_PROVIDER
    model = ((assignment or {}).get("model") if assignment_provider_found else None) or provider.get("default_model") or "deepseek-chat"
    base_url = provider.get("base_url") or ""
    if "deepseek" in base_url.lower() and not str(model).startswith("deepseek-"):
        model = provider.get("default_model") or "deepseek-chat"
    return ModelConfig(
        provider_id=provider.get("id", "env-openai"),
        api_type=provider.get("api_type", "openai"),
        wire_api=provider.get("wire_api", "chat_completions"),
        model=model,
        api_key=provider.get("api_key", ""),
        base_url=provider.get("base_url") or None,
        timeout=int(provider.get("timeout", 120) or 120),
    )


def public_provider(provider: dict) -> dict:
    item = dict(provider)
    key = item.pop("api_key", "") or ""
    item["has_key"] = bool(key)
    item["key_preview"] = f"...{key[-4:]}" if len(key) > 4 else ("****" if key else "")
    return item


def config_paths() -> dict[str, str]:
    ensure_llm_config()
    return {"llm_dir": str(LLM_DIR), "providers": str(PROVIDERS_PATH), "assignments": str(ASSIGNMENTS_PATH), "retry": str(RETRY_PATH)}


def normalize_provider(provider: dict) -> dict:
    api_type = _clean(provider.get("api_type") or provider.get("provider") or "openai")
    if api_type == "claude":
        api_type = "anthropic"
    wire_api = _clean(provider.get("wire_api") or ("messages" if api_type == "anthropic" else "chat_completions"))
    return {
        "id": _clean(provider.get("id", "")),
        "name": _clean(provider.get("name") or provider.get("id") or "Provider"),
        "api_type": api_type,
        "base_url": _clean(provider.get("base_url", "")),
        "api_key": _clean(provider.get("api_key", "")),
        "default_model": _clean(provider.get("default_model") or provider.get("model") or ("claude-opus-4-5" if api_type == "anthropic" else "deepseek-chat")),
        "wire_api": wire_api,
        "enabled": bool(provider.get("enabled", True)),
        "tested_ok": bool(provider.get("tested_ok", False)),
        "source": _clean(provider.get("source", "manual")),
        "timeout": int(provider.get("timeout", 120) or 120),
    }


def _assignment_for(role: str, cartridge_id: str | None = None, node_id: str | None = None) -> dict | None:
    data = get_assignments()
    if cartridge_id and node_id:
        item = data.get("nodes", {}).get(f"{cartridge_id}/{node_id}", {}).get(role)
        if item:
            return item
    if cartridge_id:
        item = data.get("cartridges", {}).get(cartridge_id, {}).get(role)
        if item:
            return item
    return data.get("defaults", {}).get(role)


def _env_provider() -> dict:
    if os.environ.get("AI_PROVIDER") == "claude":
        return {
            "id": "env-claude",
            "name": "Env Claude",
            "api_type": "anthropic",
            "base_url": os.environ.get("CLAUDE_BASE_URL", ""),
            "api_key": os.environ.get("CLAUDE_API_KEY", ""),
            "default_model": os.environ.get("CLAUDE_MODEL", "claude-opus-4-5"),
            "wire_api": "messages",
            "enabled": True,
            "source": "env",
            "timeout": 120,
        }
    return {
        "id": "env-openai",
        "name": "Env OpenAI Compatible",
        "api_type": "openai",
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com")),
        "api_key": os.environ.get("DEEPSEEK_API_KEY", os.environ.get("OPENAI_API_KEY", "")),
        "default_model": os.environ.get("OPENAI_MODEL", "deepseek-chat"),
        "wire_api": "chat_completions",
        "enabled": True,
        "source": "env",
        "timeout": 120,
    }


def _merge_env_provider(provider: dict) -> dict:
    if provider.get("source") != "env":
        return provider
    env = _env_provider()
    merged = dict(provider)
    for key in ["api_type", "base_url", "api_key", "default_model", "wire_api", "timeout"]:
        if env.get(key):
            merged[key] = env[key]
    return merged


def _read_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return deepcopy(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(fallback)


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or "provider"


def _next_id(base: str, existing: set[str]) -> str:
    if base not in existing:
        return base
    index = 2
    while f"{base}-{index}" in existing:
        index += 1
    return f"{base}-{index}"


def _clean(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().strip("` ").strip()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    return text.strip("` ").strip()
