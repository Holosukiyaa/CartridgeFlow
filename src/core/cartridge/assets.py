from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


ASSET_SCHEMA = "cartridgeflow.asset_registry.v1"
COMPONENT_SCHEMA = "cartridgeflow.interaction_components.v1"
ASSET_KINDS = {
    "flow",
    "model_recipe",
    "prompt",
    "schema",
    "motion_template",
    "interaction_template",
    "style",
    "media",
    "fixture",
}
COMPONENT_MODES = {"display", "collect", "review"}
EXECUTABLE_SUFFIXES = {
    ".bat", ".cjs", ".cmd", ".com", ".dll", ".exe", ".js", ".mjs",
    ".msi", ".ps1", ".py", ".pyd", ".sh", ".so", ".wasm",
}
TEXT_MEDIA_PREFIXES = ("text/", "application/json", "application/schema+json")


class CartridgeAssetError(ValueError):
    def __init__(self, message: str, code: str = "CARTRIDGE_ASSET_INVALID"):
        self.code = code
        super().__init__(message)


class _PassiveHtmlParser(HTMLParser):
    FORBIDDEN_TAGS = {
        "applet", "base", "button", "embed", "form", "iframe", "input",
        "link", "object", "portal", "script", "select", "svg", "textarea",
    }
    URL_ATTRIBUTES = {"action", "formaction", "href", "poster", "src", "srcset"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self._style_depth = 0

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in self.FORBIDDEN_TAGS:
            self.errors.append(f"forbidden active HTML tag: <{tag}>")
        if tag in {"a", "area"} and any(str(name).lower() == "href" for name, _ in attrs):
            self.errors.append(f"passive HTML cannot contain navigable <{tag}> elements")
        if tag == "meta":
            values = {str(name).lower(): str(value or "") for name, value in attrs}
            if values.get("http-equiv", "").lower() == "refresh":
                self.errors.append("passive HTML cannot contain meta refresh")
        if tag == "style":
            self._style_depth += 1
        for name, value in attrs:
            key = str(name).lower()
            text = str(value or "").strip()
            if key.startswith("on"):
                self.errors.append(f"forbidden event attribute: {key}")
            if key in {"action", "formaction"}:
                self.errors.append(f"forbidden form navigation attribute: {key}")
            if key in self.URL_ATTRIBUTES and self._unsafe_url(text):
                self.errors.append(f"forbidden external or executable URL in {key}")
            if key == "style":
                self.errors.extend(_validate_passive_css(text))

    def handle_startendtag(self, tag: str, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() == "style" and self._style_depth:
            self._style_depth -= 1

    def handle_endtag(self, tag: str):
        if tag.lower() == "style" and self._style_depth:
            self._style_depth -= 1

    def handle_data(self, data: str):
        if self._style_depth:
            self.errors.extend(_validate_passive_css(data))

    @staticmethod
    def _unsafe_url(value: str) -> bool:
        lowered = value.lower().strip()
        if not lowered:
            return False
        if re.fullmatch(r"asset:[a-z0-9._-]+", lowered):
            return False
        if lowered.startswith(("javascript:", "vbscript:", "data:text/html", "//")):
            return True
        parsed = urlparse(lowered)
        if parsed.scheme and not lowered.startswith(("data:image/", "blob:")):
            return True
        normalized = lowered.replace("\\", "/")
        return any(part == ".." for part in normalized.split("/"))


def _validate_passive_css(css: str) -> list[str]:
    lowered = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL).lower()
    errors = []
    for token in ("@import", "expression(", "javascript:", "-moz-binding", "behavior:"):
        if token in lowered:
            errors.append(f"forbidden active CSS token: {token}")
    for match in re.finditer(r"url\(\s*(['\"]?)(.*?)\1\s*\)", lowered, flags=re.DOTALL):
        value = match.group(2).strip()
        if _PassiveHtmlParser._unsafe_url(value):
            errors.append("passive CSS URL must stay in the package asset scope")
    return errors


def validate_passive_html(content: str) -> None:
    parser = _PassiveHtmlParser()
    try:
        parser.feed(content)
        parser.close()
    except Exception as exc:
        raise CartridgeAssetError(f"passive HTML parsing failed: {exc}", "PASSIVE_HTML_PARSE_FAILED") from exc
    if parser.errors:
        raise CartridgeAssetError("; ".join(dict.fromkeys(parser.errors)), "PASSIVE_HTML_ACTIVE_CONTENT")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def materialize_passive_html(content: str, bundle: dict) -> str:
    """Resolve stable package asset references to network-free data URLs."""
    assets = bundle.get("asset_by_id") or {}
    result = content
    for asset_id in set(re.findall(r"asset:([a-zA-Z0-9._-]+)", content)):
        asset = assets.get(asset_id)
        if not asset:
            raise CartridgeAssetError(f"passive HTML references an unknown asset: {asset_id}", "ASSET_REFERENCE_MISSING")
        media_type = str(asset.get("media_type") or "application/octet-stream")
        encoded = asset.get("content")
        encoding = asset.get("encoding")
        if encoding == "utf-8":
            encoded = base64.b64encode(str(encoded or "").encode("utf-8")).decode("ascii")
        if not encoded:
            raise CartridgeAssetError(f"asset content was not loaded for HTML materialization: {asset_id}")
        result = result.replace(f"asset:{asset_id}", f"data:{media_type};base64,{encoded}")
    return result


def resolve_package_path(package_root: str | Path, relative: str, field: str) -> Path:
    root = Path(package_root).resolve()
    value = str(relative or "").strip().replace("\\", "/")
    if not value or Path(value).is_absolute() or re.match(r"^[a-zA-Z]:", value):
        raise CartridgeAssetError(f"{field} must be a package-relative path")
    target = (root / value).resolve()
    if target == root or root not in target.parents:
        raise CartridgeAssetError(f"{field} points outside the cartridge package")
    return target


def _read_json(path: Path, label: str) -> dict:
    if not path.is_file():
        raise CartridgeAssetError(f"{label} not found: {path.name}", "ASSET_REGISTRY_MISSING")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CartridgeAssetError(f"{label} is invalid JSON: {exc.msg}", "ASSET_REGISTRY_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise CartridgeAssetError(f"{label} must be an object")
    return value


def load_asset_bundle(package_root: str | Path, manifest: dict, *, include_content: bool = False) -> dict:
    root = Path(package_root).resolve()
    registry_path = resolve_package_path(root, manifest.get("asset_registry"), "manifest.asset_registry")
    registry = _read_json(registry_path, "asset registry")
    if registry.get("schema") != ASSET_SCHEMA or not isinstance(registry.get("assets"), list):
        raise CartridgeAssetError(f"asset registry must use {ASSET_SCHEMA} with an assets array")

    assets = []
    by_id = {}
    asset_paths = set()
    interaction_html: dict[str, str] = {}
    for index, raw in enumerate(registry["assets"]):
        if not isinstance(raw, dict):
            raise CartridgeAssetError(f"asset registry assets[{index}] must be an object")
        item = dict(raw)
        asset_id = str(item.get("id") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if not asset_id or asset_id in by_id:
            raise CartridgeAssetError(f"asset id is missing or duplicated: {asset_id or index}")
        if kind not in ASSET_KINDS:
            raise CartridgeAssetError(f"asset {asset_id} has unsupported kind: {kind}")
        target = resolve_package_path(root, item.get("path"), f"asset {asset_id}.path")
        normalized_path = target.as_posix().lower()
        if normalized_path in asset_paths:
            raise CartridgeAssetError(f"multiple asset ids reference the same path: {item.get('path')}")
        asset_paths.add(normalized_path)
        if not target.is_file():
            raise CartridgeAssetError(f"asset file not found: {asset_id}", "ASSET_FILE_MISSING")
        if target.suffix.lower() in EXECUTABLE_SUFFIXES or item.get("executable") is not False:
            raise CartridgeAssetError(f"asset {asset_id} is executable and cannot be a package asset", "ASSET_EXECUTABLE_FORBIDDEN")
        content = target.read_bytes()
        actual_hash = sha256_bytes(content)
        actual_size = len(content)
        if str(item.get("sha256") or "").lower() != actual_hash or item.get("size") != actual_size:
            raise CartridgeAssetError(f"asset integrity mismatch: {asset_id}", "ASSET_INTEGRITY_MISMATCH")
        media_type = str(item.get("media_type") or "").strip().lower()
        guessed = (mimetypes.guess_type(target.name)[0] or "application/octet-stream").lower()
        if not media_type:
            raise CartridgeAssetError(f"asset {asset_id}.media_type is required")
        if kind == "interaction_template":
            if media_type != "text/html":
                raise CartridgeAssetError(f"interaction template {asset_id} must use text/html")
            html = content.decode("utf-8")
            validate_passive_html(html)
            interaction_html[asset_id] = html
        item["actual_media_type"] = guessed
        if include_content:
            if media_type.startswith(TEXT_MEDIA_PREFIXES):
                item["content"] = content.decode("utf-8")
                item["encoding"] = "utf-8"
            else:
                item["content"] = base64.b64encode(content).decode("ascii")
                item["encoding"] = "base64"
        assets.append(item)
        by_id[asset_id] = item

    for asset_id, html in interaction_html.items():
        for referenced_id in set(re.findall(r"asset:([a-zA-Z0-9._-]+)", html)):
            if referenced_id not in by_id:
                raise CartridgeAssetError(
                    f"interaction template {asset_id} references unknown asset: {referenced_id}",
                    "ASSET_REFERENCE_MISSING",
                )

    component_ref = manifest.get("interaction_components")
    components_doc = {"schema": COMPONENT_SCHEMA, "components": []}
    if component_ref:
        components_path = resolve_package_path(root, component_ref, "manifest.interaction_components")
        components_doc = _read_json(components_path, "interaction component registry")
    if components_doc.get("schema") != COMPONENT_SCHEMA or not isinstance(components_doc.get("components"), list):
        raise CartridgeAssetError(f"interaction components must use {COMPONENT_SCHEMA} with a components array")

    components = []
    component_by_id = {}
    for index, raw in enumerate(components_doc["components"]):
        if not isinstance(raw, dict):
            raise CartridgeAssetError(f"interaction components[{index}] must be an object")
        item = dict(raw)
        component_id = str(item.get("id") or "").strip()
        version = str(item.get("version") or "").strip()
        runtime = str(item.get("runtime") or "").strip()
        if not component_id or component_id in component_by_id or not version:
            raise CartridgeAssetError(f"component id/version is missing or duplicated: {component_id or index}")
        entry = item.get("entry") if isinstance(item.get("entry"), dict) else {}
        asset_id = ""
        if runtime == "passive":
            entry_ref = str(entry.get("ref") or "")
            asset_id = entry_ref.removeprefix("asset:") if entry.get("type") == "asset" else ""
            if not asset_id or asset_id not in by_id or by_id[asset_id].get("kind") != "interaction_template":
                raise CartridgeAssetError(f"component {component_id} must reference an interaction_template asset")
            item["entry_sha256"] = by_id[asset_id].get("sha256")
        elif runtime == "sandboxed":
            if entry.get("type") != "dlc_frontend" or not entry.get("ref"):
                raise CartridgeAssetError(f"sandboxed component {component_id} must reference a dlc_frontend entry")
            try:
                from core.extensions.descriptor import load_portable_dlc_descriptor
                descriptor = load_portable_dlc_descriptor(root, manifest)
            except Exception as exc:
                raise CartridgeAssetError(
                    f"sandboxed component {component_id} has an invalid descriptor v2: {exc}",
                    "SANDBOXED_INTERACTION_DESCRIPTOR_INVALID",
                ) from exc
            frontend_components = {
                str(value.get("id")): value
                for value in ((descriptor.get("frontend") or {}).get("components") or [])
                if isinstance(value, dict)
            }
            frontend_component = frontend_components.get(str(entry.get("ref")))
            if not frontend_component:
                raise CartridgeAssetError(f"sandboxed component frontend entry is missing: {entry.get('ref')}")
            entry_path = str(frontend_component.get("entry") or "").replace("\\", "/")
            entry_file = next(
                (value for value in descriptor.get("files") or [] if isinstance(value, dict) and value.get("path") == entry_path),
                None,
            )
            if not entry_file:
                raise CartridgeAssetError(f"sandboxed component entry file is not declared: {entry_path}")
            item["dlc_frontend_ref"] = str(entry.get("ref"))
            item["dlc_entry_path"] = entry_path
            item["entry_sha256"] = entry_file.get("sha256")
            item["descriptor_sha256"] = descriptor.get("_descriptor_sha256")
        else:
            raise CartridgeAssetError(f"component {component_id}.runtime must be passive or sandboxed")
        modes = item.get("supported_modes")
        if not isinstance(modes, list) or not modes or any(mode not in COMPONENT_MODES for mode in modes):
            raise CartridgeAssetError(f"component {component_id}.supported_modes is invalid")
        actions = item.get("actions")
        if not isinstance(actions, list):
            raise CartridgeAssetError(f"component {component_id}.actions must be an array")
        if any(mode in {"collect", "review"} for mode in modes) and not actions:
            raise CartridgeAssetError(f"component {component_id} requires actions for collect/review modes")
        _validate_schema_reference(item.get("input_schema"), by_id, f"component {component_id}.input_schema")
        action_ids = set()
        for action in actions:
            action_id = str(action.get("id") or "").strip() if isinstance(action, dict) else ""
            if not action_id or action_id in action_ids:
                raise CartridgeAssetError(f"component {component_id} has an invalid or duplicate action")
            action_ids.add(action_id)
            _validate_schema_reference(action.get("payload_schema"), by_id, f"component {component_id} action {action_id}.payload_schema")
        item["entry_asset_id"] = asset_id
        components.append(item)
        component_by_id[component_id] = item

    return {
        "registry": registry,
        "components_registry": components_doc,
        "assets": assets,
        "components": components,
        "asset_by_id": by_id,
        "component_by_id": component_by_id,
    }


def _validate_schema_reference(value, assets: dict, field: str) -> None:
    if isinstance(value, dict):
        return
    reference = str(value or "").strip()
    if not reference.startswith("asset:"):
        raise CartridgeAssetError(f"{field} must be an inline schema or asset reference")
    asset = assets.get(reference.removeprefix("asset:"))
    if not asset or asset.get("kind") != "schema":
        raise CartridgeAssetError(f"{field} must reference a schema asset")


def validate_interaction_nodes(root_flow: dict, bundle: dict) -> list[dict]:
    findings = []
    states = root_flow.get("states") if isinstance(root_flow, dict) else {}
    states = states if isinstance(states, dict) else {}
    components = bundle.get("component_by_id") or {}
    for node_id, node in states.items():
        if not isinstance(node, dict) or node.get("type") != "process" or node.get("kind") != "interaction":
            continue
        display_name = node.get("display_name")
        if display_name is not None and (not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 120):
            findings.append(_finding("blocker", "v07_display_name_invalid", node_id, "display_name must be 1-120 characters"))
        component_ref = str(node.get("component_ref") or "").strip()
        component = components.get(component_ref)
        if not component:
            findings.append(_finding("blocker", "v07_interaction_component_missing", node_id, f"unknown component_ref: {component_ref}"))
            continue
        mode = str(node.get("interaction_mode") or "").strip()
        if mode not in COMPONENT_MODES or mode not in component.get("supported_modes", []):
            findings.append(_finding("blocker", "v07_interaction_mode_invalid", node_id, f"unsupported interaction_mode: {mode}"))
        executor = str(node.get("executor") or "")
        effect = str(node.get("effect") or "")
        if mode == "display" and (executor != "deterministic" or effect != "none"):
            findings.append(_finding("blocker", "v07_display_contract_invalid", node_id, "display requires executor=deterministic and effect=none"))
        if mode in {"collect", "review"}:
            if executor not in {"user", "human"} or effect != "writes_store" or not node.get("output"):
                findings.append(_finding("blocker", "v07_interaction_contract_invalid", node_id, "collect/review requires user|human, writes_store and output"))
            routes = node.get("action_routes")
            if not isinstance(routes, dict) or not routes:
                findings.append(_finding("blocker", "v07_action_routes_missing", node_id, "collect/review requires action_routes"))
            else:
                component_actions = {str(item.get("id")) for item in component.get("actions") or [] if isinstance(item, dict)}
                for action_id, target in routes.items():
                    if action_id not in component_actions:
                        findings.append(_finding("blocker", "v07_action_unknown", node_id, f"action is not declared by component: {action_id}"))
                    if target not in states:
                        findings.append(_finding("blocker", "v07_action_target_missing", node_id, f"action target does not exist: {target}"))
        bindings = node.get("input_binding", {})
        if not isinstance(bindings, dict) or any(not str(value).startswith(("store:", "artifact:")) for value in bindings.values()):
            findings.append(_finding("blocker", "v07_input_binding_invalid", node_id, "input_binding values must use store: or artifact: references"))
    return findings


def _finding(severity: str, code: str, node_id: str, message: str) -> dict:
    return {"severity": severity, "code": code, "node": str(node_id), "message": message}


def write_asset(
    package_root: str | Path,
    manifest: dict,
    *,
    asset_id: str,
    kind: str,
    relative_path: str,
    media_type: str,
    content: str,
    encoding: str = "utf-8",
) -> dict:
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", asset_id or ""):
        raise CartridgeAssetError("asset id may only contain letters, numbers, dot, underscore and hyphen")
    if kind not in ASSET_KINDS:
        raise CartridgeAssetError(f"unsupported asset kind: {kind}")
    root = Path(package_root).resolve()
    target = resolve_package_path(root, relative_path, "asset.path")
    assets_root = (root / "assets").resolve()
    if assets_root not in target.parents:
        raise CartridgeAssetError("asset.path must be inside assets/")
    if target.suffix.lower() in EXECUTABLE_SUFFIXES:
        raise CartridgeAssetError("executable files cannot be stored as package assets", "ASSET_EXECUTABLE_FORBIDDEN")
    try:
        raw = base64.b64decode(content, validate=True) if encoding == "base64" else content.encode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise CartridgeAssetError(f"asset content encoding is invalid: {encoding}") from exc
    if kind == "interaction_template":
        if media_type != "text/html" or encoding != "utf-8":
            raise CartridgeAssetError("interaction_template requires UTF-8 text/html")
        validate_passive_html(content)
    target.parent.mkdir(parents=True, exist_ok=True)
    target_existed = target.is_file()
    previous_target = target.read_bytes() if target_existed else b""
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_bytes(raw)
    temp.replace(target)

    registry_path = resolve_package_path(root, manifest.get("asset_registry"), "manifest.asset_registry")
    previous_registry = registry_path.read_bytes()
    registry = _read_json(registry_path, "asset registry")
    items = registry.setdefault("assets", [])
    next_item = {
        "id": asset_id,
        "kind": kind,
        "path": target.relative_to(root).as_posix(),
        "media_type": media_type,
        "sha256": sha256_bytes(raw),
        "size": len(raw),
        "executable": False,
    }
    replaced = False
    old_target = None
    for index, item in enumerate(items):
        if isinstance(item, dict) and item.get("id") == asset_id:
            old_path = str(item.get("path") or "")
            if old_path and old_path != next_item["path"]:
                old_target = resolve_package_path(root, old_path, "old asset.path")
            items[index] = next_item
            replaced = True
            break
    if not replaced:
        items.append(next_item)
    _write_json_atomic(registry_path, registry)
    try:
        load_asset_bundle(root, manifest)
    except Exception:
        registry_path.write_bytes(previous_registry)
        if target_existed:
            target.write_bytes(previous_target)
        elif target.is_file():
            target.unlink()
        raise
    if old_target and old_target.is_file():
        old_target.unlink()
    return next_item


def write_component(package_root: str | Path, manifest: dict, component: dict) -> dict:
    root = Path(package_root).resolve()
    component_id = str(component.get("id") or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", component_id):
        raise CartridgeAssetError("component id is invalid")
    runtime = str(component.get("runtime") or "passive")
    if runtime not in {"passive", "sandboxed"}:
        raise CartridgeAssetError("component runtime must be passive or sandboxed")
    path = resolve_package_path(root, manifest.get("interaction_components"), "manifest.interaction_components")
    previous_document = path.read_bytes()
    document = _read_json(path, "interaction component registry")
    items = document.setdefault("components", [])
    normalized = {
        "id": component_id,
        "version": str(component.get("version") or "1.0.0"),
        "runtime": runtime,
        "entry": component.get("entry"),
        "supported_modes": component.get("supported_modes") or ["display"],
        "input_schema": component.get("input_schema") or {"type": "object"},
        "actions": component.get("actions") or [],
        "host_capabilities": component.get("host_capabilities") or [],
    }
    for index, item in enumerate(items):
        if isinstance(item, dict) and item.get("id") == component_id:
            items[index] = normalized
            break
    else:
        items.append(normalized)
    _write_json_atomic(path, document)
    try:
        load_asset_bundle(root, manifest)
    except Exception:
        path.write_bytes(previous_document)
        raise
    return normalized


def delete_asset(package_root: str | Path, manifest: dict, root_flow: dict, asset_id: str) -> None:
    root = Path(package_root).resolve()
    bundle = load_asset_bundle(root, manifest)
    item = bundle["asset_by_id"].get(asset_id)
    if not item:
        raise CartridgeAssetError(f"asset not found: {asset_id}", "ASSET_NOT_FOUND")
    needle = f"asset:{asset_id}"
    refs = _find_scalar_references(root_flow, needle) + _find_scalar_references(bundle["components_registry"], needle)
    if refs:
        raise CartridgeAssetError(f"asset is still referenced: {', '.join(refs[:8])}", "ASSET_IN_USE")
    path = resolve_package_path(root, item.get("path"), "asset.path")
    registry_path = resolve_package_path(root, manifest.get("asset_registry"), "manifest.asset_registry")
    registry = bundle["registry"]
    registry["assets"] = [entry for entry in registry["assets"] if entry.get("id") != asset_id]
    _write_json_atomic(registry_path, registry)
    if path.is_file():
        path.unlink()


def delete_component(package_root: str | Path, manifest: dict, root_flow: dict, component_id: str) -> None:
    root = Path(package_root).resolve()
    bundle = load_asset_bundle(root, manifest)
    if component_id not in bundle["component_by_id"]:
        raise CartridgeAssetError(f"component not found: {component_id}", "COMPONENT_NOT_FOUND")
    refs = _find_scalar_references(root_flow, component_id)
    if refs:
        raise CartridgeAssetError(f"component is still referenced: {', '.join(refs[:8])}", "COMPONENT_IN_USE")
    path = resolve_package_path(root, manifest.get("interaction_components"), "manifest.interaction_components")
    document = bundle["components_registry"]
    document["components"] = [
        item for item in document["components"]
        if not isinstance(item, dict) or item.get("id") != component_id
    ]
    _write_json_atomic(path, document)


def _find_scalar_references(value, needle: str, path: str = "$") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(_find_scalar_references(item, needle, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_scalar_references(item, needle, f"{path}[{index}]"))
    elif value == needle:
        found.append(path)
    return found


def _write_json_atomic(path: Path, value: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
