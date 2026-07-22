from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from html.parser import HTMLParser
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
    if runtime_contract.get("protocol") != "CF-FARP" or runtime_version not in {"0.6", "0.7"}:
        raise PortableDlcValidationError("portable DLC activation requires CF-FARP@0.6 or CF-FARP@0.7")
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

    expected_schema = "cartridgeflow.portable_dlc.v2" if runtime_version == "0.7" else "cartridgeflow.portable_dlc.v1"
    _validate_identity(descriptor, manifest, expected_schema)
    _validate_entries(package_root, descriptor, runtime_version)
    _validate_tools(descriptor, manifest)
    _validate_protocols(package_root, descriptor)
    _validate_resources(descriptor)
    _validate_files(package_root, descriptor, verify_hashes=verify_hashes)
    if runtime_version == "0.7":
        _validate_v2_frontend_closure(package_root, descriptor, manifest)

    result = deepcopy(descriptor)
    result["_package_path"] = str(package_root)
    result["_descriptor_path"] = str(descriptor_path)
    result["_descriptor_sha256"] = sha256_file(descriptor_path)
    result["_protocol"] = expected_protocol
    return result


def _validate_identity(descriptor: dict, manifest: dict, expected_schema: str) -> None:
    if descriptor.get("schema") != expected_schema:
        raise PortableDlcValidationError(f"descriptor.schema must be {expected_schema}")
    for field in ["id", "version", "owner_cartridge"]:
        if not isinstance(descriptor.get(field), str) or not descriptor.get(field).strip():
            raise PortableDlcValidationError(f"descriptor.{field} is required")
    if descriptor.get("owner_cartridge") != manifest.get("id"):
        raise PortableDlcValidationError("descriptor.owner_cartridge must match manifest.id")
    if descriptor.get("scope") != "cartridge":
        raise PortableDlcValidationError("descriptor.scope must be cartridge")


def _validate_entries(package_root: Path, descriptor: dict, runtime_version: str) -> None:
    backend = descriptor.get("backend")
    if backend is None and runtime_version == "0.7":
        backend = None
    elif not isinstance(backend, dict):
        raise PortableDlcValidationError("descriptor.backend must be an object")
    if backend is not None and backend.get("transport") != "json_stdio_worker":
        raise PortableDlcValidationError("descriptor.backend.transport must be json_stdio_worker")
    if backend is not None:
        backend_entry = resolve_package_file(package_root, backend.get("entry"), "descriptor.backend.entry")
        if not backend_entry.is_file():
            raise PortableDlcValidationError("descriptor.backend.entry not found")

    frontend = descriptor.get("frontend")
    if frontend is not None:
        if not isinstance(frontend, dict):
            raise PortableDlcValidationError("descriptor.frontend must be an object")
        if frontend.get("sandbox") != "isolated_iframe":
            raise PortableDlcValidationError("descriptor.frontend.sandbox must be isolated_iframe")
        if runtime_version == "0.6":
            frontend_entry = resolve_package_file(package_root, frontend.get("entry"), "descriptor.frontend.entry")
            if not frontend_entry.is_file():
                raise PortableDlcValidationError("descriptor.frontend.entry not found")
        else:
            components = frontend.get("components")
            if not isinstance(components, list) or not components:
                raise PortableDlcValidationError("descriptor.frontend.components must be a non-empty array")
            seen = set()
            for index, component in enumerate(components):
                component_id = str(component.get("id") or "").strip() if isinstance(component, dict) else ""
                if not component_id or component_id in seen:
                    raise PortableDlcValidationError(f"descriptor.frontend.components[{index}].id is missing or duplicated")
                seen.add(component_id)
                entry = resolve_package_file(package_root, component.get("entry"), f"descriptor.frontend.components[{index}].entry")
                if not entry.is_file():
                    raise PortableDlcValidationError(f"frontend component entry not found: {component_id}")
                if component.get("script_policy") != "external_hashed_only":
                    raise PortableDlcValidationError(f"frontend component {component_id}.script_policy must be external_hashed_only")
                capabilities = component.get("host_capabilities", [])
                if not isinstance(capabilities, list) or any(not isinstance(item, str) for item in capabilities):
                    raise PortableDlcValidationError(f"frontend component {component_id}.host_capabilities must be an array")


def _validate_tools(descriptor: dict, manifest: dict) -> None:
    tools = descriptor.get("tools")
    if not isinstance(tools, list) or (descriptor.get("schema") == "cartridgeflow.portable_dlc.v1" and not tools):
        raise PortableDlcValidationError("descriptor.tools must be an array (non-empty for descriptor v1)")
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
        if descriptor.get("schema") == "cartridgeflow.portable_dlc.v2":
            media_type = str(item.get("media_type") or "").strip().lower()
            role = str(item.get("role") or "").strip()
            if not media_type or not role:
                raise PortableDlcValidationError(f"descriptor.files[{index}] requires media_type and role in v2")


class _FrontendHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str]] = []
        self.errors: list[str] = []
        self._script_without_src = 0

    def handle_starttag(self, tag: str, attrs):
        values = {str(name).lower(): str(value or "").strip() for name, value in attrs}
        if any(name.startswith("on") for name in values):
            self.errors.append("inline event handlers are forbidden")
        if tag.lower() == "script":
            if not values.get("src"):
                self._script_without_src += 1
                self.errors.append("inline script is forbidden")
            else:
                self.references.append(("script", values["src"]))
        for name in ("src", "href", "poster"):
            if values.get(name) and tag.lower() != "script":
                self.references.append((tag.lower(), values[name]))

    def handle_startendtag(self, tag: str, attrs):
        self.handle_starttag(tag, attrs)


def _validate_v2_frontend_closure(package_root: Path, descriptor: dict, manifest: dict) -> None:
    frontend = descriptor.get("frontend") if isinstance(descriptor.get("frontend"), dict) else {}
    descriptor_components = {
        str(item.get("id")): item for item in frontend.get("components") or [] if isinstance(item, dict)
    }
    registry_path = resolve_package_file(package_root, manifest.get("interaction_components"), "manifest.interaction_components")
    if not registry_path.is_file():
        raise PortableDlcValidationError("interaction component registry not found for descriptor v2")
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PortableDlcValidationError(f"interaction component registry is invalid JSON: {exc.msg}") from exc
    registry_components = {}
    for item in registry.get("components") or []:
        if not isinstance(item, dict) or item.get("runtime") != "sandboxed":
            continue
        entry = item.get("entry") if isinstance(item.get("entry"), dict) else {}
        if entry.get("type") != "dlc_frontend" or not entry.get("ref"):
            raise PortableDlcValidationError(f"sandboxed component {item.get('id')} must reference a dlc_frontend entry")
        registry_components[str(entry["ref"])] = item
    if set(registry_components) != set(descriptor_components):
        raise PortableDlcValidationError("descriptor frontend components must exactly match sandboxed interaction component refs")

    allowed_capabilities = {
        "run.read_declared", "artifact.read", "upload.create", "draft.read", "draft.write",
        "interaction.propose", "download.request", "notification.request",
    }
    files = {
        str(item.get("path") or "").replace("\\", "/"): item
        for item in descriptor.get("files") or [] if isinstance(item, dict)
    }
    for component_id, frontend_component in descriptor_components.items():
        registry_component = registry_components[component_id]
        declared = set(frontend_component.get("host_capabilities") or [])
        required = set(registry_component.get("host_capabilities") or [])
        if not declared.issubset(allowed_capabilities) or declared != required:
            raise PortableDlcValidationError(f"frontend component {component_id} host capabilities do not match the registry")
        entry_relative = str(frontend_component.get("entry") or "").replace("\\", "/")
        entry_file = files.get(entry_relative)
        if not entry_file or entry_file.get("role") != "frontend_entry" or entry_file.get("media_type") != "text/html":
            raise PortableDlcValidationError(f"frontend component {component_id} entry must be a declared text/html frontend_entry")
        entry_path = resolve_package_file(package_root, entry_relative, f"frontend component {component_id}.entry")
        parser = _FrontendHtmlParser()
        parser.feed(entry_path.read_text(encoding="utf-8"))
        parser.close()
        if parser.errors:
            raise PortableDlcValidationError(f"frontend component {component_id}: {'; '.join(dict.fromkeys(parser.errors))}")
        base_dir = Path(entry_relative).parent
        for tag, reference in parser.references:
            declared_path = _normalize_frontend_reference(base_dir, reference, component_id)
            file_item = files.get(declared_path)
            if not file_item:
                raise PortableDlcValidationError(f"frontend component {component_id} references undeclared file: {reference}")
            if tag == "script":
                if file_item.get("role") != "frontend_script" or file_item.get("media_type") not in {"text/javascript", "application/javascript"}:
                    raise PortableDlcValidationError(f"frontend script has invalid role or media type: {declared_path}")
                _validate_frontend_script(package_root, declared_path, files, component_id)


def _normalize_frontend_reference(base_dir: Path, reference: str, component_id: str) -> str:
    value = str(reference or "").strip().replace("\\", "/")
    if not value or value.startswith(("http:", "https:", "//", "data:", "blob:", "javascript:", "/")):
        raise PortableDlcValidationError(f"frontend component {component_id} contains a non-package URL: {value}")
    normalized = (base_dir / value.split("?", 1)[0].split("#", 1)[0]).as_posix()
    if ".." in Path(normalized).parts:
        raise PortableDlcValidationError(f"frontend component {component_id} reference escapes its package scope")
    return normalized


def _validate_frontend_script(package_root: Path, relative: str, files: dict, component_id: str) -> None:
    content = resolve_package_file(package_root, relative, "frontend script").read_text(encoding="utf-8")
    forbidden_patterns = {
        r"\beval\s*\(": "eval",
        r"\bnew\s+Function\b": "new Function",
        r"\bWebAssembly\b": "WebAssembly",
        r"\b(?:SharedWorker|Worker|ServiceWorker|Worklet)\b": "worker API",
        r"\bimport\s*\(": "dynamic import",
        r"\bset(?:Timeout|Interval)\s*\(\s*['\"]": "string timer",
    }
    for pattern, label in forbidden_patterns.items():
        if re.search(pattern, content):
            raise PortableDlcValidationError(f"frontend component {component_id} script uses forbidden {label}: {relative}")
    base_dir = Path(relative).parent
    imports = re.findall(r"(?:\bimport\s+(?:[^'\"]+?\s+from\s+)?|\bexport\s+[^'\"]+?\s+from\s+)['\"]([^'\"]+)['\"]", content)
    for reference in imports:
        declared_path = _normalize_frontend_reference(base_dir, reference, component_id)
        item = files.get(declared_path)
        if not item or item.get("role") != "frontend_script":
            raise PortableDlcValidationError(f"frontend component {component_id} imports undeclared script: {reference}")
