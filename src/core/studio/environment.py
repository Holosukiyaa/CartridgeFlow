"""Local-only environment variables and base dependency diagnostics."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from core.data_paths import DATA_ROOT, PACKAGES_DIR, STUDIO_CREDENTIALS_FILE, ensure_data_layout
from core.local_config import read_local_json, write_local_json


ROOT = Path(__file__).resolve().parents[3]
CREDENTIAL_PATH = ROOT / STUDIO_CREDENTIALS_FILE
_INHERITED_ENV = dict(os.environ)
_KEY_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")

STANDARD_REFERENCES = [
    ("OPENAI_API_KEY", "OpenAI API Key", "模型环境连接"),
    ("OPENAI_BASE_URL", "OpenAI Base URL", "模型环境连接"),
    ("OPENAI_MODEL", "OpenAI Model", "模型环境连接"),
    ("DEEPSEEK_API_KEY", "DeepSeek API Key", "模型环境连接"),
    ("DEEPSEEK_BASE_URL", "DeepSeek Base URL", "模型环境连接"),
    ("CLAUDE_API_KEY", "Claude API Key", "模型环境连接"),
    ("CLAUDE_BASE_URL", "Claude Base URL", "模型环境连接"),
    ("CLAUDE_MODEL", "Claude Model", "模型环境连接"),
    ("HTTP_PROXY", "HTTP Proxy", "底座网络"),
    ("HTTPS_PROXY", "HTTPS Proxy", "底座网络"),
    ("NO_PROXY", "No Proxy", "底座网络"),
]


def ensure_local_credentials(path: str | Path | None = None) -> dict:
    if path is None:
        ensure_data_layout(ROOT)
    target = Path(path) if path else CREDENTIAL_PATH
    if not target.is_file():
        data = {"version": 1, "items": []}
        write_local_json(target, data)
        return data
    data = _read_json(target)
    _apply_items(data.get("items") or [])
    return data


def list_credentials(path: str | Path | None = None) -> list[dict]:
    return ensure_local_credentials(path).get("items") or []


def upsert_credential(payload: dict, key: str = "", path: str | Path | None = None) -> dict:
    target = Path(path) if path else CREDENTIAL_PATH
    data = ensure_local_credentials(target)
    normalized_key = str(key or payload.get("key") or "").strip().upper()
    if not _KEY_PATTERN.fullmatch(normalized_key):
        raise ValueError("Credential key must use uppercase letters, numbers, and underscores")
    items = list(data.get("items") or [])
    old = next((item for item in items if item.get("key") == normalized_key), None)
    value = str(payload.get("value") or "")
    if not value and old:
        value = str(old.get("value") or "")
    if not value:
        raise ValueError("Credential value is required")
    item = {
        "key": normalized_key,
        "label": str(payload.get("label") or (old or {}).get("label") or normalized_key).strip(),
        "value": value,
        "secret": payload.get("secret", (old or {}).get("secret", True)) is not False,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    items = [current for current in items if current.get("key") != normalized_key]
    items.append(item)
    items.sort(key=lambda current: current.get("key") or "")
    write_local_json(target, {"version": 1, "items": items})
    os.environ[normalized_key] = value
    return _public_credential(item, "local")


def delete_credential(key: str, path: str | Path | None = None) -> bool:
    target = Path(path) if path else CREDENTIAL_PATH
    normalized_key = str(key or "").strip().upper()
    data = ensure_local_credentials(target)
    items = data.get("items") or []
    kept = [item for item in items if item.get("key") != normalized_key]
    if len(kept) == len(items):
        return False
    write_local_json(target, {"version": 1, "items": kept})
    if normalized_key in _INHERITED_ENV:
        os.environ[normalized_key] = _INHERITED_ENV[normalized_key]
    else:
        os.environ.pop(normalized_key, None)
    return True


def environment_snapshot(resources: dict | None = None, path: str | Path | None = None) -> dict:
    local_items = list_credentials(path)
    local_by_key = {item.get("key"): item for item in local_items}
    references = _build_references(resources or {})
    keys = set(local_by_key)
    keys.update(reference["key"] for reference in references)
    credentials = []
    for key in sorted(keys):
        local = local_by_key.get(key)
        if local:
            credentials.append(_public_credential(local, "local"))
            continue
        inherited = os.environ.get(key, "")
        if inherited:
            credentials.append(_public_credential({"key": key, "label": key, "value": inherited, "secret": True}, "process"))
    status_by_key = {item["key"]: item for item in credentials}
    for reference in references:
        reference["configured"] = bool(status_by_key.get(reference["key"], {}).get("has_value"))
    return {
        "credentials": credentials,
        "references": references,
        "checks": system_checks(),
        "paths": {
            "workspace": str(ROOT),
            "credentials": str(Path(path) if path else CREDENTIAL_PATH),
            "data": str(ROOT / DATA_ROOT),
            "packages": str(ROOT / PACKAGES_DIR),
        },
    }


def system_checks() -> list[dict]:
    checks = [{
        "id": "python",
        "label": "Python",
        "status": "ok",
        "version": platform.python_version(),
        "path": sys.executable,
    }]
    node = ROOT / ".tools" / "runtimes" / "node" / ("node.exe" if os.name == "nt" else "node")
    checks.append(_command_check("node", "Node.js", str(node) if node.is_file() else shutil.which("node"), ["--version"]))
    checks.append(_command_check("ffmpeg", "FFmpeg", shutil.which("ffmpeg"), ["-version"]))
    checks.append(_command_check("git", "Git", shutil.which("git"), ["--version"]))
    checks.append({
        "id": "workspace",
        "label": "工作区写入",
        "status": "ok" if os.access(ROOT, os.W_OK) else "blocked",
        "version": "可写" if os.access(ROOT, os.W_OK) else "只读",
        "path": str(ROOT),
    })
    return checks


def _build_references(resources: dict) -> list[dict]:
    grouped: dict[str, dict] = {}
    for key, label, owner in STANDARD_REFERENCES:
        grouped[key] = {"key": key, "label": label, "owners": [owner], "configured": False}
    for kind in ("tools", "sources"):
        owner_label = "工具配置" if kind == "tools" else "数据来源"
        for item in resources.get(kind) or []:
            key = str(item.get("auth_env") or "").strip().upper()
            if not key:
                continue
            entry = grouped.setdefault(key, {"key": key, "label": key, "owners": [], "configured": False})
            owner = f"{owner_label} / {item.get('name') or item.get('id')}"
            if owner not in entry["owners"]:
                entry["owners"].append(owner)
    return list(grouped.values())


def _command_check(check_id: str, label: str, command: str | None, args: list[str]) -> dict:
    if not command:
        return {"id": check_id, "label": label, "status": "missing", "version": "未检测到", "path": ""}
    try:
        result = subprocess.run([command, *args], capture_output=True, text=True, errors="replace", timeout=5)
        output = (result.stdout or result.stderr or "").splitlines()
        version = output[0].strip()[:120] if output else "已检测到"
        return {"id": check_id, "label": label, "status": "ok" if result.returncode == 0 else "warning", "version": version, "path": command}
    except (OSError, subprocess.SubprocessError):
        return {"id": check_id, "label": label, "status": "missing", "version": "检测失败", "path": command}


def _public_credential(item: dict, source: str) -> dict:
    value = str(item.get("value") or "")
    return {
        "key": item.get("key") or "",
        "label": item.get("label") or item.get("key") or "",
        "secret": item.get("secret", True) is not False,
        "source": source,
        "has_value": bool(value),
        "preview": f"...{value[-4:]}" if len(value) > 4 else ("****" if value else ""),
        "updated_at": item.get("updated_at"),
    }


def _apply_items(items: list[dict]) -> None:
    for item in items:
        key = str(item.get("key") or "").strip().upper()
        value = str(item.get("value") or "")
        if _KEY_PATTERN.fullmatch(key) and value:
            os.environ[key] = value


def _read_json(path: Path) -> dict:
    data = read_local_json(
        path,
        {"version": 1, "items": []},
        validator=lambda item: isinstance(item.get("items"), list),
    )
    items = data.get("items") if isinstance(data, dict) else []
    return {"version": 1, "items": [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []}
