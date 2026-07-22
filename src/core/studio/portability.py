"""Build an auditable cartridge portability report before packaging."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from core.cartridge.assets import CartridgeAssetError, load_asset_bundle
from core.studio.hygiene import scan_package_hygiene
from core.studio.resource_resolver import resolve_cartridge_resources


REPORT_SCHEMA = "cartridgeflow.portability_report.v1"
SENSITIVE_KEYS = {
    "api_key", "apikey", "key", "secret", "password", "token", "credential",
    "credentials", "base_url", "endpoint", "openapi_url", "auth_env",
}
TEXT_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".txt", ".md", ".html", ".css", ".js", ".mjs"}
WINDOWS_ABSOLUTE = re.compile(r"(?i)(?:^|[\"'\s])(?:[a-z]:[\\/]|\\\\[^\\/]+[\\/])")
POSIX_LOCAL = re.compile(r"(?:^|[\"'\s])/(?:home|users|private|var|tmp|opt|mnt)/[^\s\"']+")


def build_portability_report(
    package_path: str | Path,
    manifest: dict,
    root_flow: dict | None = None,
    *,
    resources: dict | None = None,
    configured_keys: set[str] | None = None,
) -> dict:
    root = Path(package_path).resolve()
    manifest = manifest if isinstance(manifest, dict) else {}
    root_flow = root_flow if isinstance(root_flow, dict) else {}
    portable: list[dict] = []
    local_rebind: list[dict] = []
    missing: list[dict] = []
    forbidden: list[dict] = []

    hygiene = scan_package_hygiene(root)
    for item in hygiene.get("items") or []:
        forbidden.append(_item(
            item.get("path") or ".",
            item.get("message") or "Prohibited package content.",
            path=item.get("path"),
            check=item.get("category"),
        ))

    if not root.is_dir():
        missing.append(_item("package", "Cartridge package directory does not exist.", path=str(root)))
        return _finish(portable, local_rebind, missing, forbidden, hygiene.get("scanned_files", 0))

    _record_core_file(root, "manifest.json", "manifest", portable, missing)
    root_value = manifest.get("root_flow")
    root_ref = str(root_value.get("entry") or "root_flow.json") if isinstance(root_value, dict) else str(root_value or "root_flow.json")
    _record_core_file(root, root_ref, "flow", portable, missing)

    protocol = manifest.get("runtime_contract") if isinstance(manifest.get("runtime_contract"), dict) else {}
    if protocol.get("protocol") == "CF-FARP" and str(protocol.get("protocol_version")) == "0.7":
        try:
            bundle = load_asset_bundle(root, manifest, include_content=False)
            for asset in bundle.get("assets") or []:
                portable.append(_item(
                    str(asset.get("id")),
                    f"{asset.get('kind')} asset is package-owned and integrity checked.",
                    path=asset.get("path"),
                    kind=asset.get("kind"),
                    sha256=asset.get("sha256"),
                    size=asset.get("size"),
                    media_type=asset.get("media_type"),
                ))
            for component in bundle.get("components") or []:
                portable.append(_item(
                    f"component:{component.get('id')}",
                    "Interaction component definition travels with the cartridge.",
                    kind="interaction_component",
                    runtime=component.get("runtime"),
                    version=component.get("version"),
                    entry_ref=(component.get("entry") or {}).get("ref"),
                    host_capabilities=component.get("host_capabilities") or [],
                ))
        except CartridgeAssetError as exc:
            missing.append(_item("asset_registry", str(exc), check=getattr(exc, "code", "ASSET_INVALID")))

    recipe = manifest.get("llm_recipe") if isinstance(manifest.get("llm_recipe"), dict) else {}
    for role in recipe.get("roles") or []:
        if not isinstance(role, dict) or not role.get("id"):
            continue
        local_rebind.append(_item(
            f"model:{role['id']}",
            "Model recipe travels with the cartridge; provider URL, model instance and key must be rebound locally.",
            kind="model",
            required=role.get("required", True) is not False,
            recipe={key: role.get(key) for key in ("id", "label", "api_type", "capabilities") if role.get(key) is not None},
        ))

    for requirement in manifest.get("resource_requirements") or []:
        if not isinstance(requirement, dict) or not requirement.get("role"):
            continue
        local_rebind.append(_item(
            f"tool:{requirement['role']}",
            "Tool capability declaration travels with the cartridge; the concrete MCP/API/plugin connection stays local.",
            kind="tool",
            required=requirement.get("required", True) is not False,
            kinds=requirement.get("kinds") or [],
            capabilities=requirement.get("capabilities") or [],
        ))

    permissions = manifest.get("permissions", [])
    if not isinstance(permissions, list):
        missing.append(_item("permissions", "Manifest permissions must be an array.", check="permission_schema"))
    else:
        for index, permission in enumerate(permissions):
            permission_id = str(permission.get("id") or "").strip() if isinstance(permission, dict) else ""
            level = str(permission.get("level") or "").strip() if isinstance(permission, dict) else ""
            if not permission_id or level not in {"safe", "sensitive", "dangerous"}:
                missing.append(_item(f"permission:{index}", "Permission requires a stable id and safe, sensitive or dangerous level.", check="permission_schema"))
                continue
            portable.append(_item(
                f"permission:{permission_id}",
                "Permission declaration travels with the cartridge; sensitive and dangerous grants remain Host-owned.",
                kind="permission",
                level=level,
            ))

    if resources is not None:
        binding_report = resolve_cartridge_resources(manifest, resources, configured_keys)
        for item in binding_report.get("items") or []:
            if item.get("status") == "blocked":
                missing.append(_item(
                    f"tool:{item.get('role') or item.get('id')}",
                    item.get("message") or "Required local tool binding is unavailable.",
                    check=item.get("state"),
                    resource_id=item.get("resource_id"),
                ))

    _scan_text_content(root, forbidden)
    return _finish(portable, local_rebind, missing, forbidden, hygiene.get("scanned_files", 0))


def _record_core_file(root: Path, relative: str, kind: str, portable: list[dict], missing: list[dict]) -> None:
    target = _safe_package_file(root, relative)
    if target is None or not target.is_file():
        missing.append(_item(kind, f"Required package file is missing or outside the cartridge: {relative}", path=relative))
        return
    content = target.read_bytes()
    portable.append(_item(
        kind,
        f"{kind} definition travels with the cartridge.",
        path=target.relative_to(root).as_posix(),
        kind=kind,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
    ))


def _scan_text_content(root: Path, forbidden: list[dict]) -> None:
    seen: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 2 * 1024 * 1024:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if WINDOWS_ABSOLUTE.search(text) or POSIX_LOCAL.search(text):
            _append_unique(forbidden, seen, _item(relative, "Package text contains an absolute local path.", path=relative, check="local_path"))
        if path.suffix.lower() == ".json":
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            for key_path, value in _walk_sensitive(value):
                if value not in (None, "", [], {}, False):
                    _append_unique(forbidden, seen, _item(
                        relative,
                        f"Package JSON contains machine-owned connection or credential field: {key_path}",
                        path=relative,
                        check="sensitive_field",
                        field=key_path,
                    ))


def _walk_sensitive(value, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).casefold() in SENSITIVE_KEYS:
                yield path, child
            yield from _walk_sensitive(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_sensitive(child, f"{prefix}[{index}]")


def _safe_package_file(root: Path, relative: str) -> Path | None:
    value = str(relative or "").strip().replace("\\", "/")
    if not value or Path(value).is_absolute() or re.match(r"^[a-zA-Z]:", value):
        return None
    target = (root / value).resolve()
    return target if target != root and root in target.parents else None


def _append_unique(items: list[dict], seen: set[tuple[str, str]], item: dict) -> None:
    key = (str(item.get("path") or item.get("id")), str(item.get("check")))
    if key not in seen:
        seen.add(key)
        items.append(item)


def _item(item_id: str, reason: str, **details) -> dict:
    return {"id": str(item_id), "reason": reason, **{key: value for key, value in details.items() if value not in (None, "")}}


def _finish(portable: list[dict], local_rebind: list[dict], missing: list[dict], forbidden: list[dict], scanned_files: int) -> dict:
    summary = {
        "portable": len(portable),
        "local_rebind": len(local_rebind),
        "missing_blockers": len(missing),
        "forbidden": len(forbidden),
        "scanned_files": int(scanned_files or 0),
    }
    return {
        "schema": REPORT_SCHEMA,
        "status": "blocked" if missing or forbidden else "ok",
        "summary": summary,
        "portable": portable,
        "local_rebind": local_rebind,
        "missing_blockers": missing,
        "forbidden": forbidden,
    }
