"""Local tool and data-source registry used by the Studio base."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from core.data_paths import STUDIO_RESOURCES_FILE, ensure_data_layout
from core.local_config import read_local_json, write_local_json


ROOT = Path(__file__).resolve().parents[3]
RESOURCE_PATH = ROOT / STUDIO_RESOURCES_FILE

TOOL_KINDS = {"mcp", "remote_api", "plugin"}
SOURCE_KINDS = {"local_path", "web", "structured"}
TOOL_PACKAGE_MODES = {"descriptor", "external"}
SOURCE_PACKAGE_MODES = {"reference", "snapshot", "external"}


def default_resources() -> dict:
    return {
        "version": 1,
        "tools": [],
        "sources": [],
        "bindings": {"roles": {}, "tools": {}, "sources": {}},
    }


def load_resources(path: str | Path | None = None) -> dict:
    if path is None:
        ensure_data_layout(ROOT)
    target = Path(path) if path else RESOURCE_PATH
    if not target.is_file():
        data = default_resources()
        write_local_json(target, data)
        return data
    raw = read_local_json(
        target,
        default_resources(),
        validator=lambda item: all(key in item for key in ("tools", "sources", "bindings")),
    )
    return normalize_resources(raw)


def save_resources(data: dict, path: str | Path | None = None) -> dict:
    if path is None:
        ensure_data_layout(ROOT)
    target = Path(path) if path else RESOURCE_PATH
    normalized = normalize_resources(data)
    write_local_json(target, normalized)
    return normalized


def normalize_resources(data: dict | None) -> dict:
    source = data if isinstance(data, dict) else {}
    tools = _unique_items(source.get("tools"), _normalize_tool)
    sources = _unique_items(source.get("sources"), _normalize_source)
    bindings = source.get("bindings") if isinstance(source.get("bindings"), dict) else {}
    return {
        "version": 1,
        "tools": tools,
        "sources": sources,
        "bindings": {
            "roles": _normalize_role_bindings(bindings.get("roles")),
            "tools": _normalize_bindings(bindings.get("tools")),
            "sources": _normalize_bindings(bindings.get("sources")),
        },
    }


def _normalize_tool(raw: dict) -> dict | None:
    item_id = _resource_id(raw.get("id") or raw.get("name"))
    if not item_id:
        return None
    kind = _choice(raw.get("kind"), TOOL_KINDS, "mcp")
    package_mode = _choice(raw.get("package_mode"), TOOL_PACKAGE_MODES, "descriptor")
    return {
        "id": item_id,
        "name": _clean(raw.get("name")) or item_id,
        "kind": kind,
        "description": _clean(raw.get("description")),
        "endpoint": _clean(raw.get("endpoint")),
        "command": _clean(raw.get("command")),
        "args": _clean(raw.get("args")),
        "openapi_url": _clean(raw.get("openapi_url")),
        "auth_env": _clean(raw.get("auth_env")),
        "capabilities": _string_list(raw.get("capabilities")),
        "read_only": raw.get("read_only") is True,
        "package_mode": package_mode,
        "enabled": raw.get("enabled") is not False,
    }


def _normalize_source(raw: dict) -> dict | None:
    item_id = _resource_id(raw.get("id") or raw.get("name"))
    if not item_id:
        return None
    kind = _choice(raw.get("kind"), SOURCE_KINDS, "local_path")
    package_mode = _choice(raw.get("package_mode"), SOURCE_PACKAGE_MODES, "reference")
    return {
        "id": item_id,
        "name": _clean(raw.get("name")) or item_id,
        "kind": kind,
        "description": _clean(raw.get("description")),
        "location": _clean(raw.get("location")),
        "format": _clean(raw.get("format")) or "auto",
        "auth_env": _clean(raw.get("auth_env")),
        "capabilities": _string_list(raw.get("capabilities")),
        "read_only": raw.get("read_only", True) is not False,
        "refresh_mode": _choice(raw.get("refresh_mode"), {"manual", "run", "scheduled"}, "manual"),
        "package_mode": package_mode,
        "enabled": raw.get("enabled") is not False,
    }


def _unique_items(raw_items, normalizer) -> list[dict]:
    result = []
    seen = set()
    for raw in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw, dict):
            continue
        item = normalizer(raw)
        if not item or item["id"] in seen:
            continue
        seen.add(item["id"])
        result.append(item)
    return result


def _normalize_bindings(raw) -> dict[str, list[str]]:
    result = {}
    if not isinstance(raw, dict):
        return result
    for cartridge_id, resource_ids in raw.items():
        cartridge = _clean(cartridge_id)
        if not cartridge or not isinstance(resource_ids, list):
            continue
        unique = []
        for resource_id in resource_ids:
            value = _clean(resource_id)
            if value and value not in unique:
                unique.append(value)
        if unique:
            result[cartridge] = unique
    return result


def _normalize_role_bindings(raw) -> dict[str, dict[str, str]]:
    result = {}
    if not isinstance(raw, dict):
        return result
    for cartridge_id, roles in raw.items():
        cartridge = _clean(cartridge_id)
        if not cartridge or not isinstance(roles, dict):
            continue
        normalized_roles = {}
        for role, resource_id in roles.items():
            role_id = _clean(role)
            resource = _clean(resource_id)
            if role_id and resource:
                normalized_roles[role_id] = resource
        if normalized_roles:
            result[cartridge] = normalized_roles
    return result


def _resource_id(value) -> str:
    raw = _clean(value)
    slug = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", raw).strip("-.").lower()
    if slug:
        return slug
    return f"resource-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}" if raw else ""


def _choice(value, allowed: set[str], fallback: str) -> str:
    candidate = _clean(value)
    return candidate if candidate in allowed else fallback


def _clean(value) -> str:
    return str(value or "").strip()


def _string_list(value) -> list[str]:
    if isinstance(value, str):
        values = value.replace("\r", "\n").replace(",", "\n").split("\n")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    result = []
    for item in values:
        text = _clean(item)
        if text and text not in result:
            result.append(text)
    return result
