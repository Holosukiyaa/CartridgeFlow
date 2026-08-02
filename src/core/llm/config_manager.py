import os
import re
from datetime import datetime, timezone
from pathlib import Path

from core.data_paths import LLM_ASSIGNMENTS_FILE, LLM_CONFIG_DIR, LLM_PROVIDERS_FILE, ensure_data_layout
from core.local_config import read_local_json, write_local_json

from .config import ModelConfig

ROOT = Path(__file__).resolve().parents[3]
DEFAULTS_DIR = ROOT / "config" / "defaults"
LLM_DIR = ROOT / LLM_CONFIG_DIR
PROVIDERS_PATH = ROOT / LLM_PROVIDERS_FILE
ASSIGNMENTS_PATH = ROOT / LLM_ASSIGNMENTS_FILE
RETRY_PATH = DEFAULTS_DIR / "llm_retry.json"

DEFAULT_ASSIGNMENT_ROLES = ("runtime", "mentor", "worker")
SUPPORTED_LLM_ROUTES = {
    ("openai", "chat_completions"),
    ("openai", "responses"),
}
PROVIDER_CONNECTION_FIELDS = ("api_type", "base_url", "api_key", "default_model", "wire_api", "timeout", "capabilities")
PROVIDER_ADAPTER_PROFILES = {
    "standard": {"label": "普通模型", "capabilities": ["text_reasoning"], "runtime_supported": True},
}

DEFAULT_DEEPSEEK_PROVIDER = {
    "id": "default-deepseek",
    "name": "Default DeepSeek",
    "api_type": "openai",
    "base_url": "https://api.deepseek.com",
    "api_key": "",
    "default_model": "deepseek-chat",
    "wire_api": "chat_completions",
    "capabilities": ["text_reasoning"],
    "adapter_profile": "standard",
    "enabled": True,
    "tested_ok": False,
    "source": "default",
    "timeout": 120,
}

def ensure_llm_config():
    ensure_data_layout(ROOT)
    env = _env_provider()
    active = env if env.get("api_key") and not provider_route_issue(env) else DEFAULT_DEEPSEEK_PROVIDER
    if not PROVIDERS_PATH.exists():
        write_local_json(PROVIDERS_PATH, {
            "version": 1,
            "providers": [
                {**DEFAULT_DEEPSEEK_PROVIDER, "enabled": active["id"] == DEFAULT_DEEPSEEK_PROVIDER["id"]},
                {**env, "enabled": active["id"] == env["id"]},
            ],
        })
    if not ASSIGNMENTS_PATH.exists():
        write_local_json(ASSIGNMENTS_PATH, {
            "version": 1,
            "defaults": {
                "runtime": {"provider_id": active["id"], "model": active["default_model"]},
                "mentor": {"provider_id": active["id"], "model": active["default_model"]},
                "worker": {"provider_id": active["id"], "model": active["default_model"]},
            },
            "cartridges": {},
            "nodes": {},
        })


def list_providers(include_disabled: bool = True) -> list[dict]:
    ensure_llm_config()
    data = read_local_json(
        PROVIDERS_PATH,
        {"version": 1, "providers": []},
        validator=lambda item: isinstance(item.get("providers"), list),
    )
    providers = [normalize_provider(_merge_env_provider(item)) for item in data.get("providers", [])]
    changed = providers != data.get("providers", [])
    repaired_active = None
    enabled = [item for item in providers if item.get("enabled", True)]
    if providers and len(enabled) != 1:
        active_id = (
            next((item.get("id") for item in providers if item.get("api_key") and not provider_route_issue(item)), None)
            or next((item.get("id") for item in providers if not provider_route_issue(item)), None)
            or providers[0].get("id")
        )
        providers = [{**item, "enabled": item.get("id") == active_id} for item in providers]
        repaired_active = next((item for item in providers if item.get("enabled")), None)
        changed = True
    if changed:
        save_providers(providers)
    if repaired_active:
        _set_default_assignments(repaired_active)
    if include_disabled:
        return providers
    return [item for item in providers if item.get("enabled", True)]


def save_providers(providers: list[dict]):
    write_local_json(PROVIDERS_PATH, {"version": 1, "providers": providers})


def get_provider(provider_id: str) -> dict | None:
    return next((item for item in list_providers() if item.get("id") == provider_id), None)


def upsert_provider(provider: dict) -> dict:
    providers = list_providers()
    item = normalize_provider(provider)
    validate_provider_route(item, configuration=True)
    if not item.get("id"):
        base = _slug(item.get("name") or item.get("api_type") or "provider")
        existing = {old.get("id") for old in providers}
        item["id"] = _next_id(base, existing)
    replaced = False
    for index, old in enumerate(providers):
        if old.get("id") == item.get("id"):
            if not item.get("api_key"):
                item["api_key"] = old.get("api_key", "")
            connection_changed = any(item.get(field) != old.get(field) for field in PROVIDER_CONNECTION_FIELDS)
            item["tested_ok"] = False if connection_changed else bool(old.get("tested_ok", False))
            item["tested_at"] = "" if connection_changed else str(old.get("tested_at") or "")
            providers[index] = item
            replaced = True
            break
    if not replaced:
        item["tested_ok"] = False
        item["tested_at"] = ""
        providers.append(item)
    if item.get("enabled", True):
        providers = [{**old, "enabled": old.get("id") == item.get("id")} for old in providers]
    save_providers(providers)
    if item.get("enabled", True):
        _set_default_assignments(item)
    return item


def activate_provider(provider_id: str) -> dict | None:
    providers = list_providers()
    selected = next((item for item in providers if item.get("id") == provider_id), None)
    if selected is None:
        return None
    validate_provider_route(selected)
    if "text_reasoning" not in set(selected.get("capabilities") or []):
        raise ValueError("只有具备 text_reasoning 能力的模型连接可以设为底座默认")
    providers = [{**item, "enabled": item.get("id") == provider_id} for item in providers]
    save_providers(providers)
    selected = next(item for item in providers if item.get("id") == provider_id)
    _set_default_assignments(selected)
    return selected


def delete_provider(provider_id: str) -> bool:
    providers = list_providers()
    removed = next((item for item in providers if item.get("id") == provider_id), None)
    kept = [item for item in providers if item.get("id") != provider_id]
    if removed is None:
        return False
    replacement = next((item for item in kept if item.get("enabled")), None)
    if removed.get("enabled") and kept:
        replacement = (
            next((item for item in kept if item.get("api_key") and not provider_route_issue(item)), None)
            or next((item for item in kept if not provider_route_issue(item)), None)
            or kept[0]
        )
        kept = [{**item, "enabled": item.get("id") == replacement.get("id")} for item in kept]
    save_providers(kept)
    _remove_provider_assignments(provider_id, replacement)
    return True


def mark_provider_tested(provider_id: str, ok: bool = True) -> dict | None:
    providers = list_providers()
    found = None
    for item in providers:
        if item.get("id") == provider_id:
            item["tested_ok"] = bool(ok)
            item["tested_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds") if ok else ""
            found = item
            break
    if found:
        save_providers(providers)
    return found


def get_assignments() -> dict:
    ensure_llm_config()
    fallback = {"version": 1, "defaults": {}, "cartridges": {}, "nodes": {}}
    return read_local_json(
        ASSIGNMENTS_PATH,
        fallback,
        validator=lambda item: all(isinstance(item.get(key), dict) for key in ("defaults", "cartridges", "nodes")),
    )


def save_assignments(data: dict):
    write_local_json(ASSIGNMENTS_PATH, normalize_assignments(data))


def resolve_model(
    role: str = "runtime",
    cartridge_id: str | None = None,
    node_id: str | None = None,
    *,
    provider_id: str | None = None,
    model: str | None = None,
) -> ModelConfig:
    ensure_llm_config()
    assignment = _assignment_for(role, cartridge_id, node_id, include_defaults=not bool(cartridge_id))
    providers = list_providers(False)
    provider = None
    assignment_provider_found = False
    if cartridge_id and not assignment:
        raise ValueError(f"Cartridge {cartridge_id} has no explicit model binding for role {role}")
    selected_provider_id = _clean(provider_id) or _clean((assignment or {}).get("provider_id"))
    if selected_provider_id:
        provider = get_provider(selected_provider_id)
        assignment_provider_found = bool(provider)
        if cartridge_id and not provider:
            raise ValueError(f"Cartridge model binding references an unavailable provider: {selected_provider_id}")
    if not cartridge_id:
        provider = provider or next((item for item in providers if item.get("api_key")), None) or next(iter(providers), None) or DEFAULT_DEEPSEEK_PROVIDER
    if provider is None:
        raise ValueError(f"Cartridge {cartridge_id} has no available provider for role {role}")
    validate_provider_route(provider)
    resolved_model = _clean(model) or (((assignment or {}).get("model") if assignment_provider_found else None) or provider.get("default_model") or "")
    base_url = provider.get("base_url") or ""
    if "deepseek" in base_url.lower() and not str(resolved_model).startswith("deepseek-"):
        resolved_model = provider.get("default_model") or "deepseek-chat"
    return ModelConfig(
        provider_id=provider.get("id", "env-openai"),
        api_type=provider.get("api_type", "openai"),
        wire_api=provider.get("wire_api", "chat_completions"),
        model=resolved_model,
        api_key=provider.get("api_key", ""),
        base_url=provider.get("base_url") or None,
        timeout=int(provider.get("timeout", 120) or 120),
        capabilities=list(provider.get("capabilities") or []),
        adapter_profile="standard",
    )


def public_provider(provider: dict) -> dict:
    item = dict(provider)
    key = item.pop("api_key", "") or ""
    item["has_key"] = bool(key)
    item["key_preview"] = f"...{key[-4:]}" if len(key) > 4 else ("****" if key else "")
    issue = provider_route_issue(item)
    item["runtime_supported"] = not bool(issue)
    item["runtime_issue"] = issue
    item["adapter_supported"] = True
    item["adapter_label"] = PROVIDER_ADAPTER_PROFILES["standard"]["label"]
    return item


def config_paths() -> dict[str, str]:
    ensure_llm_config()
    return {
        "llm_dir": LLM_CONFIG_DIR.as_posix(),
        "providers": LLM_PROVIDERS_FILE.as_posix(),
        "assignments": LLM_ASSIGNMENTS_FILE.as_posix(),
        "retry": "config/defaults/llm_retry.json",
    }


def normalize_provider(provider: dict) -> dict:
    api_type = normalize_api_type(provider.get("api_type") or provider.get("provider") or "openai")
    wire_api = normalize_wire_api(provider.get("wire_api"), api_type)
    # 图片/视频逆向适配器已撤下。旧配置统一迁移为普通文本连接，
    # 避免历史配置在启动时重新进入不可控的媒体执行链路。
    if wire_api == "images":
        wire_api = "chat_completions"
    return {
        "id": _clean(provider.get("id", "")),
        "name": _clean(provider.get("name") or provider.get("id") or "Provider"),
        "api_type": api_type,
        "base_url": _clean(provider.get("base_url", "")),
        "api_key": _clean(provider.get("api_key", "")),
        "default_model": _clean(provider.get("default_model") or provider.get("model") or ""),
        "wire_api": wire_api,
        "capabilities": ["text_reasoning"],
        "available_models": _normalize_model_list(provider.get("available_models")),
        "adapter_profile": "standard",
        "enabled": bool(provider.get("enabled", True)),
        "tested_ok": bool(provider.get("tested_ok", False)),
        "tested_at": _clean(provider.get("tested_at", "")),
        "source": _clean(provider.get("source", "manual")),
        "timeout": _safe_timeout(provider.get("timeout", 120)),
    }


def _normalize_capabilities(value) -> list[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return list(dict.fromkeys(_normalize_capability_name(item) for item in values if _normalize_capability_name(item)))


def _normalize_model_list(value) -> list[str]:
    values = value if isinstance(value, list) else []
    return list(dict.fromkeys(_clean(item) for item in values if _clean(item)))


def _normalize_capability_name(value) -> str:
    normalized = _clean(value).lower().replace("-", "_")
    return {"text_generation": "text_reasoning", "image_generation_tool": "image_generation"}.get(normalized, normalized)


def normalize_api_type(value) -> str:
    normalized = _clean(value or "openai").lower().replace("-", "_")
    if normalized in {"openai_compatible", "openai_api"}:
        return "openai"
    if normalized == "claude":
        return "anthropic"
    return normalized


def normalize_wire_api(value, api_type: str = "openai") -> str:
    default = "messages" if normalize_api_type(api_type) == "anthropic" else "chat_completions"
    normalized = _clean(value or default).lower().replace("-", "_").replace(".", "_")
    if normalized in {"chat_completion", "chatcompletions"}:
        return "chat_completions"
    if normalized in {"image", "image_generation", "images_api", "images_generations"}:
        return "images"
    return normalized


def provider_route_issue(provider: dict, *, configuration: bool = False) -> str:
    api_type = normalize_api_type(provider.get("api_type"))
    wire_api = normalize_wire_api(provider.get("wire_api"), api_type)
    if (api_type, wire_api) in SUPPORTED_LLM_ROUTES:
        return ""
    if api_type != "openai":
        return f"当前底座尚未实现 {api_type or 'unknown'} 模型适配器"
    return f"当前底座尚未实现 OpenAI {wire_api or 'unknown'} 调用协议"


def validate_provider_route(provider: dict, *, configuration: bool = False) -> None:
    issue = provider_route_issue(provider, configuration=configuration)
    if issue:
        raise ValueError(issue)


def normalize_assignments(data: dict | None) -> dict:
    source = data if isinstance(data, dict) else {}
    return {
        "version": int(source.get("version", 1) or 1),
        "defaults": _normalize_role_bindings(source.get("defaults")),
        "cartridges": _normalize_scoped_bindings(source.get("cartridges")),
        "nodes": _normalize_scoped_bindings(source.get("nodes")),
    }


def build_model_binding_report(manifest: dict, root_flow: dict | None = None) -> dict:
    recipe = manifest.get("llm_recipe") if isinstance(manifest.get("llm_recipe"), dict) else {}
    roles = recipe.get("roles") if recipe.get("schema") == "cartridgeflow.llm_recipe.v1" else []
    if not isinstance(roles, list):
        roles = []
    providers = {item.get("id"): item for item in list_providers()}
    assignments = get_assignments()
    cartridge_id = str(manifest.get("id") or "")
    flow_assignments = (assignments.get("cartridges") or {}).get(cartridge_id) or {}
    flow_provider_ids = {
        _clean(binding.get("provider_id"))
        for binding in flow_assignments.values()
        if isinstance(binding, dict) and _clean(binding.get("provider_id"))
    }
    items = []
    for role in roles:
        if not isinstance(role, dict):
            continue
        role_id = _clean(role.get("id"))
        if not role_id:
            continue
        required = role.get("required", True) is not False
        if role_id in {"authoring", "mentor"}:
            items.append({
                "id": role_id,
                "label": _clean(role.get("label")) or role_id,
                "required": True,
                "status": "blocked",
                "provider_id": "",
                "provider_name": "",
                "model": "",
                "message": f"Authoring role {role_id} must not be declared in cartridge llm_recipe",
            })
            continue
        binding = _assignment_for(role_id, cartridge_id, include_defaults=False) or {}
        provider = providers.get(binding.get("provider_id"))
        status = "ok"
        issue = ""
        if not binding.get("provider_id"):
            issue = f"当前卡带尚未显式绑定模型角色：{role_id}"
        elif provider is None:
            issue = "未绑定本机模型连接"
        elif provider_route_issue(provider):
            issue = provider_route_issue(provider)
        elif not provider.get("base_url") or not provider.get("api_key"):
            missing = [label for label, value in (("URL", provider.get("base_url")), ("Key", provider.get("api_key"))) if not value]
            issue = f"本机连接缺少 {' / '.join(missing)}"
        elif normalize_api_type(role.get("api_type")) != normalize_api_type(provider.get("api_type")):
            issue = f"接口类型需要 {role.get('api_type')}"
        elif normalize_wire_api(role.get("wire_api"), role.get("api_type")) != normalize_wire_api(provider.get("wire_api"), provider.get("api_type")):
            issue = f"调用协议需要 {role.get('wire_api')}"
        elif _normalize_capability_name(role.get("capability")) and provider.get("capabilities") and _normalize_capability_name(role.get("capability")) not in set(provider.get("capabilities") or []):
            issue = f"能力需要 {role.get('capability')}"
        else:
            role_model = _clean(role.get("model"))
            binding_model = _clean(binding.get("model"))
            effective_model = (role_model if role_model != "configured-locally" else "") or binding_model or _clean(provider.get("default_model"))
            if role_model and role_model != "configured-locally" and binding_model and binding_model != role_model:
                issue = f"模型需要 {role_model}"
            elif not effective_model:
                issue = "没有可用的模型标识"
        if issue:
            status = "blocked" if required else "warning"
        items.append({
            "id": role_id,
            "label": _clean(role.get("label")) or role_id,
            "required": required,
            "status": status,
            "provider_id": _clean(provider.get("id")) if provider else "",
            "provider_name": _clean(provider.get("name")) if provider else "",
            "model": effective_model if provider and not issue else "",
            "message": issue or f"已连接 {provider.get('name')}",
        })
    role_items = {item.get("id"): item for item in items}
    states = root_flow.get("states") if isinstance(root_flow, dict) else {}
    for node_id, state in (states.items() if isinstance(states, dict) else []):
        if not isinstance(state, dict):
            continue
        params = state.get("params") if isinstance(state.get("params"), dict) else {}
        kind = _clean(state.get("kind") or params.get("kind"))
        executor = _clean(state.get("executor") or params.get("executor"))
        action = _clean(state.get("action"))
        if not ((kind == "decision" and executor == "llm") or action == "llm_prompt"):
            continue
        model_role = _clean(state.get("model_role") or params.get("model_role"))
        issue = ""
        if not model_role:
            issue = "AI 决策节点未选择模型角色"
        elif model_role not in role_items:
            issue = f"模型角色未在卡带配方中声明：{model_role}"
        elif role_items[model_role].get("status") != "ok":
            issue = f"模型角色 {model_role} 尚未就绪：{role_items[model_role].get('message')}"
        node_binding = ((assignments.get("nodes") or {}).get(f"{cartridge_id}/{node_id}") or {}).get(model_role) if model_role else None
        node_provider = providers.get((node_binding or {}).get("provider_id")) if isinstance(node_binding, dict) else None
        if not issue and not isinstance(node_binding, dict):
            issue = f"AI decision node {node_id} has no explicit model connection binding"
        elif not issue and not node_binding.get("provider_id"):
            issue = f"AI decision node {node_id} has no explicit model connection binding"
        elif not issue and node_binding.get("provider_id") not in flow_provider_ids:
            issue = f"Node model connection {node_binding.get('provider_id')} is not bound to Flow {cartridge_id}"
        elif not issue and node_provider is None:
            issue = f"Node model connection is unavailable: {node_binding.get('provider_id')}"
        elif not issue and provider_route_issue(node_provider):
            issue = provider_route_issue(node_provider)
        elif not issue and (not node_provider.get("base_url") or not node_provider.get("api_key")):
            issue = f"Node model connection is incomplete: {node_binding.get('provider_id')}"
        node_model = ""
        if node_provider and not issue:
            node_model = _clean((node_binding or {}).get("model")) or _clean(node_provider.get("default_model"))
            if not node_model:
                issue = f"Node model connection has no model: {node_binding.get('provider_id')}"
        items.append({
            "id": f"node:{node_id}",
            "label": _clean(state.get("display_name") or state.get("title")) or node_id,
            "node_id": node_id,
            "model_role": model_role,
            "required": True,
            "status": "blocked" if issue else "ok",
            "provider_id": _clean(node_provider.get("id")) if node_provider and not issue else "",
            "provider_name": _clean(node_provider.get("name")) if node_provider and not issue else "",
            "model": node_model if not issue else "",
            "message": issue or f"使用模型角色 {model_role}",
        })
    statuses = {item.get("status") for item in items}
    return {
        "status": "blocked" if "blocked" in statuses else "warning" if "warning" in statuses else "ok",
        "items": items,
    }


def _assignment_for(
    role: str,
    cartridge_id: str | None = None,
    node_id: str | None = None,
    *,
    include_defaults: bool = True,
) -> dict | None:
    data = get_assignments()
    if cartridge_id and node_id:
        item = data.get("nodes", {}).get(f"{cartridge_id}/{node_id}", {}).get(role)
        if item:
            return item
    if cartridge_id:
        item = data.get("cartridges", {}).get(cartridge_id, {}).get(role)
        if item:
            return item
    return data.get("defaults", {}).get(role) if include_defaults else None


def _set_default_assignments(provider: dict) -> None:
    data = get_assignments()
    defaults = data.setdefault("defaults", {})
    role_ids = set(DEFAULT_ASSIGNMENT_ROLES) | set(defaults)
    for role_id in role_ids:
        defaults[role_id] = {
            "provider_id": provider.get("id", ""),
            "model": provider.get("default_model", ""),
        }
    save_assignments(data)


def _remove_provider_assignments(provider_id: str, replacement: dict | None) -> None:
    data = get_assignments()
    defaults = data.setdefault("defaults", {})
    for role_id, binding in list(defaults.items()):
        if not isinstance(binding, dict) or binding.get("provider_id") != provider_id:
            continue
        if replacement:
            defaults[role_id] = {
                "provider_id": replacement.get("id", ""),
                "model": replacement.get("default_model", ""),
            }
        else:
            defaults.pop(role_id, None)

    for scope_name in ("cartridges", "nodes"):
        scope = data.setdefault(scope_name, {})
        for owner_id, bindings in list(scope.items()):
            if not isinstance(bindings, dict):
                scope.pop(owner_id, None)
                continue
            filtered = {
                role_id: binding
                for role_id, binding in bindings.items()
                if not isinstance(binding, dict) or binding.get("provider_id") != provider_id
            }
            if filtered:
                scope[owner_id] = filtered
            else:
                scope.pop(owner_id, None)
    save_assignments(data)


def _normalize_role_bindings(value) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for role_id, raw_binding in value.items():
        normalized_role = _clean(role_id)
        binding = _normalize_assignment(raw_binding)
        if normalized_role and binding:
            result[normalized_role] = binding
    return result


def _normalize_scoped_bindings(value) -> dict[str, dict[str, dict[str, str]]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, dict[str, str]]] = {}
    for owner_id, raw_bindings in value.items():
        normalized_owner = _clean(owner_id)
        bindings = _normalize_role_bindings(raw_bindings)
        if normalized_owner and bindings:
            result[normalized_owner] = bindings
    return result


def _normalize_assignment(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    provider_id = _clean(value.get("provider_id", ""))
    model = _clean(value.get("model", ""))
    if not provider_id:
        return {}
    return {"provider_id": provider_id, "model": model}


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


def _safe_timeout(value) -> int:
    try:
        timeout = int(value or 120)
    except (TypeError, ValueError):
        timeout = 120
    return min(900, max(1, timeout))


def _clean(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().strip("` ").strip()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    return text.strip("` ").strip()
