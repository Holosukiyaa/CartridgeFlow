from __future__ import annotations

import json
from pathlib import Path


class BaseManifestError(ValueError):
    pass


BASE_IMPLEMENTATION_PATH = Path("config/base/BASE_IMPLEMENTATION.json")
_ADAPTER_STATUSES = {"partial", "supported"}


def load_base_implementation(root: str | Path) -> dict:
    root_path = Path(root)
    path = root_path / BASE_IMPLEMENTATION_PATH
    if not path.is_file():
        raise BaseManifestError(f"{BASE_IMPLEMENTATION_PATH.as_posix()} not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BaseManifestError(f"{BASE_IMPLEMENTATION_PATH.as_posix()} is not valid JSON: {exc.msg}") from exc
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
    if data.get("schema_version") == "0.2":
        base_contract = data.get("base_contract")
        if not isinstance(base_contract, dict):
            raise BaseManifestError("base.base_contract is required for schema 0.2")
        if not isinstance(base_contract.get("id"), str) or not base_contract.get("id").strip():
            raise BaseManifestError("base.base_contract.id is required")
        if not isinstance(base_contract.get("version"), str) or not base_contract.get("version").strip():
            raise BaseManifestError("base.base_contract.version is required")
    if not isinstance(data.get("supported_protocols"), list):
        raise BaseManifestError("base.supported_protocols must be an array")
    for index, item in enumerate(data.get("supported_protocols") or []):
        if not isinstance(item, dict):
            raise BaseManifestError(f"base.supported_protocols[{index}] must be an object")
        if not item.get("id") or not item.get("version"):
            raise BaseManifestError(f"base.supported_protocols[{index}] requires id and version")
        if item.get("status") not in _ADAPTER_STATUSES:
            raise BaseManifestError(f"base.supported_protocols[{index}].status is invalid")
    adapters = data.get("supported_protocol_adapters", [])
    if not isinstance(adapters, list):
        raise BaseManifestError("base.supported_protocol_adapters must be an array")
    adapter_ids: set[str] = set()
    for index, item in enumerate(adapters):
        if not isinstance(item, dict):
            raise BaseManifestError(f"base.supported_protocol_adapters[{index}] must be an object")
        adapter_id = item.get("id")
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise BaseManifestError(f"base.supported_protocol_adapters[{index}].id is required")
        if adapter_id in adapter_ids:
            raise BaseManifestError(f"base.supported_protocol_adapters duplicates {adapter_id}")
        adapter_ids.add(adapter_id)
        if item.get("status") not in _ADAPTER_STATUSES:
            raise BaseManifestError(f"base.supported_protocol_adapters[{index}].status is invalid")
    for field in ["profiles", "capabilities", "tool_packs"]:
        if not isinstance(data.get(field), list):
            raise BaseManifestError(f"base.{field} must be an array")
        for index, value in enumerate(data.get(field) or []):
            if not isinstance(value, str) or not value.strip():
                raise BaseManifestError(f"base.{field}[{index}] must be a non-empty string")


def protocol_adapter_status(base: dict, adapter_id: str | None) -> str | None:
    if not adapter_id:
        return None
    for item in base.get("supported_protocol_adapters") or []:
        if isinstance(item, dict) and item.get("id") == adapter_id:
            status = item.get("status")
            return str(status) if status in _ADAPTER_STATUSES else None
    return None


def supports_protocol_release(base: dict, release: dict | None) -> bool:
    """Resolve Base support from an implementation adapter, then legacy exact versions."""
    if not isinstance(release, dict):
        return False
    if "status" in release and release.get("status") != "active":
        return False
    if "implementation_status" in release and release.get("implementation_status") != "supported":
        return False
    adapter = release.get("runtime_adapter")
    if protocol_adapter_status(base, str(adapter) if adapter else None):
        return True
    expected = (str(release.get("id") or ""), str(release.get("version") or ""))
    return any(
        isinstance(item, dict)
        and (str(item.get("id") or ""), str(item.get("version") or "")) == expected
        and item.get("status") in _ADAPTER_STATUSES
        for item in base.get("supported_protocols") or []
    )
