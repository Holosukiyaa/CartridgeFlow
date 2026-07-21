from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path


class PortableDlcValidationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_package_file(package_root: Path, relative_path: str, field: str) -> Path:
    value = str(relative_path or "").strip().replace("\\", "/")
    if not value or Path(value).is_absolute():
        raise PortableDlcValidationError(f"{field} must be a package-relative path")
    candidate = (package_root / value).resolve()
    root = package_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise PortableDlcValidationError(f"{field} escapes the cartridge package")
    return candidate


def load_portable_dlc_descriptor(package_path: str | Path, manifest: dict, *, verify_hashes: bool = True) -> dict:
    package_root = Path(package_path).resolve()
    portable = manifest.get("portable_dlc") if isinstance(manifest, dict) else None
    if not isinstance(portable, dict):
        raise PortableDlcValidationError("manifest.portable_dlc must be an object")
    runtime_contract = manifest.get("runtime_contract") if isinstance(manifest.get("runtime_contract"), dict) else {}
    runtime_version = str(runtime_contract.get("protocol_version") or "")
    if runtime_contract.get("protocol") != "CF-FARP" or runtime_version != "0.6":
        raise PortableDlcValidationError("portable DLC activation requires CF-FARP@0.6")
    expected_protocol = f"CF-FARP@{runtime_version}"
    if portable.get("protocol") != expected_protocol:
        raise PortableDlcValidationError(f"manifest.portable_dlc.protocol must match {expected_protocol}")

    descriptor_path = resolve_package_file(package_root, portable.get("descriptor"), "manifest.portable_dlc.descriptor")
    if not descriptor_path.is_file():
        raise PortableDlcValidationError("portable DLC descriptor not found")
    try:
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PortableDlcValidationError(f"portable DLC descriptor is invalid JSON: {exc.msg}") from exc
    if not isinstance(descriptor, dict):
        raise PortableDlcValidationError("portable DLC descriptor must be an object")

    _validate_identity(descriptor, manifest)
    _validate_entries(package_root, descriptor)
    _validate_tools(descriptor, manifest)
    _validate_protocols(package_root, descriptor)
    _validate_resources(descriptor)
    _validate_files(package_root, descriptor, verify_hashes=verify_hashes)

    result = deepcopy(descriptor)
    result["_package_path"] = str(package_root)
    result["_descriptor_path"] = str(descriptor_path)
    result["_descriptor_sha256"] = sha256_file(descriptor_path)
    result["_protocol"] = expected_protocol
    return result


def _validate_identity(descriptor: dict, manifest: dict) -> None:
    if descriptor.get("schema") != "cartridgeflow.portable_dlc.v1":
        raise PortableDlcValidationError("descriptor.schema must be cartridgeflow.portable_dlc.v1")
    for field in ["id", "version", "owner_cartridge"]:
        if not isinstance(descriptor.get(field), str) or not descriptor.get(field).strip():
            raise PortableDlcValidationError(f"descriptor.{field} is required")
    if descriptor.get("owner_cartridge") != manifest.get("id"):
        raise PortableDlcValidationError("descriptor.owner_cartridge must match manifest.id")
    if descriptor.get("scope") != "cartridge":
        raise PortableDlcValidationError("descriptor.scope must be cartridge")


def _validate_entries(package_root: Path, descriptor: dict) -> None:
    backend = descriptor.get("backend")
    if not isinstance(backend, dict):
        raise PortableDlcValidationError("descriptor.backend must be an object")
    if backend.get("transport") != "json_stdio_worker":
        raise PortableDlcValidationError("descriptor.backend.transport must be json_stdio_worker")
    backend_entry = resolve_package_file(package_root, backend.get("entry"), "descriptor.backend.entry")
    if not backend_entry.is_file():
        raise PortableDlcValidationError("descriptor.backend.entry not found")

    frontend = descriptor.get("frontend")
    if frontend is not None:
        if not isinstance(frontend, dict):
            raise PortableDlcValidationError("descriptor.frontend must be an object")
        if frontend.get("sandbox") != "isolated_iframe":
            raise PortableDlcValidationError("descriptor.frontend.sandbox must be isolated_iframe")
        frontend_entry = resolve_package_file(package_root, frontend.get("entry"), "descriptor.frontend.entry")
        if not frontend_entry.is_file():
            raise PortableDlcValidationError("descriptor.frontend.entry not found")


def _validate_tools(descriptor: dict, manifest: dict) -> None:
    tools = descriptor.get("tools")
    if not isinstance(tools, list) or not tools:
        raise PortableDlcValidationError("descriptor.tools must be a non-empty array")
    descriptor_pairs: set[tuple[str, str]] = set()
    for index, tool in enumerate(tools):
        if not isinstance(tool, dict):
            raise PortableDlcValidationError(f"descriptor.tools[{index}] must be an object")
        for field in ["server", "tool", "handler", "effect", "description"]:
            if not isinstance(tool.get(field), str) or not tool.get(field).strip():
                raise PortableDlcValidationError(f"descriptor.tools[{index}].{field} is required")
        timeout_ms = tool.get("timeout_ms")
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
            raise PortableDlcValidationError(f"descriptor.tools[{index}].timeout_ms must be a positive integer")
        pair = (tool["server"], tool["tool"])
        if pair in descriptor_pairs:
            raise PortableDlcValidationError(f"duplicate descriptor tool: {pair[0]}/{pair[1]}")
        descriptor_pairs.add(pair)

    manifest_pairs = {
        (str(item.get("server") or ""), str(item.get("tool") or ""))
        for item in manifest.get("mcp_tools") or []
        if isinstance(item, dict) and item.get("enabled", True)
    }
    if descriptor_pairs != manifest_pairs:
        missing = sorted(manifest_pairs - descriptor_pairs)
        extra = sorted(descriptor_pairs - manifest_pairs)
        raise PortableDlcValidationError(f"descriptor tools must exactly match manifest tools; missing={missing}, extra={extra}")


def _validate_protocols(package_root: Path, descriptor: dict) -> None:
    protocols = descriptor.get("protocols", [])
    if not isinstance(protocols, list):
        raise PortableDlcValidationError("descriptor.protocols must be an array")
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(protocols):
        if not isinstance(item, dict):
            raise PortableDlcValidationError(f"descriptor.protocols[{index}] must be an object")
        protocol_id = str(item.get("id") or "").strip()
        version = str(item.get("version") or "").strip()
        if not protocol_id or not version:
            raise PortableDlcValidationError(f"descriptor.protocols[{index}] requires id and version")
        key = (protocol_id, version)
        if key in seen:
            raise PortableDlcValidationError(f"duplicate descriptor protocol: {protocol_id}@{version}")
        seen.add(key)
        registry_path = resolve_package_file(package_root, item.get("registry"), f"descriptor.protocols[{index}].registry")
        if not registry_path.is_file():
            raise PortableDlcValidationError(f"descriptor protocol registry not found: {protocol_id}@{version}")
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        if data.get("id") != protocol_id or str(data.get("version")) != version:
            raise PortableDlcValidationError(f"descriptor protocol identity mismatch: {protocol_id}@{version}")


def _validate_resources(descriptor: dict) -> None:
    resources = descriptor.get("resources", [])
    if not isinstance(resources, list):
        raise PortableDlcValidationError("descriptor.resources must be an array")
    allowed = {"package", "private_data", "shared_dependency", "user_artifact"}
    for index, item in enumerate(resources):
        if not isinstance(item, dict) or item.get("ownership") not in allowed:
            raise PortableDlcValidationError(f"descriptor.resources[{index}].ownership is invalid")


def _validate_files(package_root: Path, descriptor: dict, *, verify_hashes: bool) -> None:
    files = descriptor.get("files")
    if not isinstance(files, list) or not files:
        raise PortableDlcValidationError("descriptor.files must be a non-empty array")
    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise PortableDlcValidationError(f"descriptor.files[{index}] must be an object")
        relative = str(item.get("path") or "").strip().replace("\\", "/")
        expected = str(item.get("sha256") or "").strip().lower()
        if not relative or len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
            raise PortableDlcValidationError(f"descriptor.files[{index}] requires path and SHA-256")
        if relative in seen:
            raise PortableDlcValidationError(f"duplicate descriptor file: {relative}")
        seen.add(relative)
        target = resolve_package_file(package_root, relative, f"descriptor.files[{index}].path")
        if not target.is_file():
            raise PortableDlcValidationError(f"descriptor file not found: {relative}")
        if verify_hashes and sha256_file(target) != expected:
            raise PortableDlcValidationError(f"descriptor file hash mismatch: {relative}")
