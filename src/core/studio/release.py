"""Release helpers for local resource bindings and package history."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path

from core.data_paths import PACKAGES_DIR
from core.studio.resource_resolver import resolve_cartridge_resources


def build_binding_descriptor(manifest: dict, resources: dict, configured_keys: set[str] | None = None) -> dict:
    return resolve_cartridge_resources(manifest, resources, configured_keys)["descriptor"]


def resource_preflight(manifest: dict, resources: dict, configured_keys: set[str]) -> dict:
    return resolve_cartridge_resources(manifest, resources, configured_keys)


def package_history(root: str | Path) -> list[dict]:
    package_dir = Path(root) / PACKAGES_DIR
    if not package_dir.is_dir():
        return []
    result = []
    for path in package_dir.glob("*.cartridge.zip"):
        manifest = {}
        mode = "unknown"
        try:
            with zipfile.ZipFile(path) as archive:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                if "package.metadata.json" in archive.namelist():
                    metadata = json.loads(archive.read("package.metadata.json").decode("utf-8"))
                    mode = metadata.get("package_mode") or "unknown"
                elif "package.compatibility.json" in archive.namelist():
                    mode = "dev"
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
            manifest = {}
        modified = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        result.append({
            "filename": path.name,
            "url": f"/packages/{path.name}",
            "size": path.stat().st_size,
            "modified_at": modified,
            "cartridge_id": manifest.get("id") or "",
            "name": manifest.get("name") or path.stem,
            "version": manifest.get("version") or "",
            "package_mode": mode,
        })
    return sorted(result, key=lambda item: item["modified_at"], reverse=True)
