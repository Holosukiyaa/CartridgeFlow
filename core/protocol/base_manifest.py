from __future__ import annotations

import json
from pathlib import Path


class BaseManifestError(ValueError):
    pass


def load_base_implementation(root: str | Path) -> dict:
    root_path = Path(root)
    path = root_path / "BASE_IMPLEMENTATION.json"
    if not path.is_file():
        raise BaseManifestError("BASE_IMPLEMENTATION.json not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BaseManifestError(f"BASE_IMPLEMENTATION.json is not valid JSON: {exc.msg}") from exc
    validate_base_implementation(data)
    return data


def validate_base_implementation(data: dict) -> None:
    if not isinstance(data, dict):
        raise BaseManifestError("base implementation manifest must be an object")
    for field in ["schema_version", "implementation_id", "implementation_version", "environment"]:
        if not isinstance(data.get(field), str) or not data.get(field).strip():
            raise BaseManifestError(f"base.{field} is required")
    if data.get("environment") not in {"development", "production", "test"}:
        raise BaseManifestError("base.environment must be development, production, or test")
    if not isinstance(data.get("supported_protocols"), list):
        raise BaseManifestError("base.supported_protocols must be an array")
    for index, item in enumerate(data.get("supported_protocols") or []):
        if not isinstance(item, dict):
            raise BaseManifestError(f"base.supported_protocols[{index}] must be an object")
        if not item.get("id") or not item.get("version"):
            raise BaseManifestError(f"base.supported_protocols[{index}] requires id and version")
    for field in ["profiles", "capabilities", "tool_packs"]:
        if not isinstance(data.get(field), list):
            raise BaseManifestError(f"base.{field} must be an array")
        for index, value in enumerate(data.get(field) or []):
            if not isinstance(value, str) or not value.strip():
                raise BaseManifestError(f"base.{field}[{index}] must be a non-empty string")
