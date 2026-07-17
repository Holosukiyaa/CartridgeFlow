import json
import os
import re


def import_opencode(data: dict) -> list[dict]:
    providers = []
    for name, cfg in (data.get("provider") or {}).items():
        options = cfg.get("options") or {}
        api_type = "anthropic" if "anthropic" in name.lower() or "anthropic" in str(cfg.get("npm", "")) else "openai"
        models = cfg.get("models") or {}
        first_model = next(iter(models.keys()), "")
        default_model = _clean_text(options.get("model") or first_model or ("claude-opus-4-5" if api_type == "anthropic" else "deepseek-chat"))
        wire_api = "messages" if api_type == "anthropic" else "chat_completions"
        providers.append({
            "id": f"opencode-{_slug(name)}",
            "name": f"OpenCode {name}",
            "api_type": api_type,
            "wire_api": wire_api,
            "base_url": _clean_text(options.get("baseURL") or options.get("baseUrl") or options.get("base_url") or ""),
            "api_key": _clean_text(options.get("apiKey") or options.get("api_key") or ""),
            "default_model": default_model,
            "enabled": True,
            "source": "opencode",
            "timeout": 120,
        })
    return providers


def import_claude_code(data: dict) -> list[dict]:
    env = data.get("env") or data
    base_url = env.get("ANTHROPIC_BASE_URL") or env.get("ANTHROPIC_BASE_URI") or "https://api.anthropic.com"
    api_key = env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY") or ""
    return [{
        "id": "claude-code-anthropic",
        "name": "Claude Code Anthropic",
        "api_type": "anthropic",
        "wire_api": "messages",
        "base_url": base_url,
        "api_key": api_key,
        "default_model": env.get("ANTHROPIC_MODEL") or env.get("CLAUDE_MODEL") or "claude-opus-4-5",
        "enabled": True,
        "source": "claude_code",
        "timeout": 120,
    }]


def import_claude_env_text(text: str) -> list[dict]:
    env = {}
    for line in text.splitlines():
        m = re.match(r"\s*(?:set\s+)?(ANTHROPIC_[A-Z_]+|CLAUDE_[A-Z_]+)\s*=\s*(.+?)\s*$", line, flags=re.I)
        if m:
            env[m.group(1).upper()] = m.group(2).strip().strip('"')
    return import_claude_code(env) if env else []


def import_codex(config_text: str, auth_data: dict | None = None) -> list[dict]:
    auth_data = auth_data or {}
    provider_name = _match_value(config_text, r'^model_provider\s*=\s*"([^"]+)"') or "OpenAI"
    model = _match_value(config_text, r'^model\s*=\s*"([^"]+)"') or "gpt-5.5"
    section = _extract_toml_section(config_text, f"model_providers.{provider_name}")
    base_url = _match_value(section, r'^base_url\s*=\s*"([^"]+)"') or "https://api.openai.com/v1"
    wire_api = _match_value(section, r'^wire_api\s*=\s*"([^"]+)"') or "responses"
    api_key = auth_data.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    return [{
        "id": f"codex-{_slug(provider_name)}",
        "name": f"Codex {provider_name}",
        "api_type": "openai",
        "wire_api": wire_api,
        "base_url": base_url,
        "api_key": api_key,
        "default_model": model,
        "enabled": True,
        "source": "codex",
        "timeout": 120,
    }]


def smart_import(text: str) -> list[dict]:
    """智能识别粘贴内容并导入 provider。"""
    providers: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for data in _extract_json_objects(text):
        if "providers" in data and "assignments" in data:
            providers.extend(data.get("providers", []))
        elif "provider" in data:
            providers.extend(import_opencode(data))
        elif "env" in data or "ANTHROPIC_AUTH_TOKEN" in data or "ANTHROPIC_API_KEY" in data:
            providers.extend(import_claude_code(data))
        elif "OPENAI_API_KEY" in data and "model_provider" in text:
            providers.extend(import_codex(text, data))

    if "model_provider" in text and "[model_providers." in text:
        auth = next((d for d in _extract_json_objects(text) if "OPENAI_API_KEY" in d), {})
        providers.extend(import_codex(text, auth))

    if "ANTHROPIC_AUTH_TOKEN" in text or "ANTHROPIC_API_KEY" in text:
        providers.extend(import_claude_env_text(text))

    result = []
    for p in providers:
        key = (p.get("api_type", ""), p.get("base_url", ""), p.get("api_key", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(p)
    return result


def parse_json_text(text: str) -> dict:
    return json.loads(text)


def _extract_json_objects(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    out = []
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                out.append(obj)
        except Exception:
            continue
    return out


def _clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = text.strip("` ").strip()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    return text.strip("` ").strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-") or "provider"


def _match_value(text: str, pattern: str) -> str:
    m = re.search(pattern, text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


def _extract_toml_section(text: str, section: str) -> str:
    marker = f"[{section}]"
    start = text.find(marker)
    if start < 0:
        return ""
    rest = text[start + len(marker):]
    next_section = re.search(r"^\[.+\]", rest, flags=re.MULTILINE)
    return rest[:next_section.start()] if next_section else rest
