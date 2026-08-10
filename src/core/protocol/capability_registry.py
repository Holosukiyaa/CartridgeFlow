from __future__ import annotations

import json
from pathlib import Path

from .artifact_store import ProtocolArtifactStore
from .release_catalog import ProtocolReleaseCatalog, load_protocol_release_catalog


class ProtocolRegistryError(ValueError):
    pass


class ProtocolRegistry:
    def __init__(self, root: str | Path, overlay_dirs: list[str | Path] | None = None):
        self.root = Path(root)
        self.artifacts = ProtocolArtifactStore(self.root)
        self.overlay_dirs = [Path(item) for item in (overlay_dirs or [])]
        self.release_catalog: ProtocolReleaseCatalog = load_protocol_release_catalog(self.root)
        self.protocols = self._load_protocols()
        self.protocol_history = self._load_protocol_history()
        self.profiles = self._load_catalog_id_set("profiles", "profiles")
        self.capabilities = self._load_catalog_id_set("capabilities", "capabilities")
        self.tool_packs = self._load_base_tool_packs()

    def validate_base(self, base: dict) -> list[dict]:
        findings: list[dict] = []
        for profile in base.get("profiles") or []:
            if profile not in self.profiles:
                findings.append(self._finding("blocker", "unknown_base_profile", f"Unknown base profile: {profile}"))
        for capability in base.get("capabilities") or []:
            if capability not in self.capabilities:
                findings.append(self._finding("blocker", "unknown_base_capability", f"Unknown base capability: {capability}"))
        for tool_pack in base.get("tool_packs") or []:
            if tool_pack not in self.tool_packs:
                findings.append(self._finding("blocker", "unknown_base_tool_pack", f"Unknown base tool pack: {tool_pack}"))
        return findings

    def supports_protocol(self, protocol_id: str, version: str) -> bool:
        if protocol_id == "CF-FARP":
            return self.release_catalog.published(protocol_id, version)
        if protocol_id == "CF-CRE":
            return self.release_catalog.release_envelope_published(protocol_id, version)
        return (protocol_id, version) in self.protocols

    def recognizes_protocol(self, protocol_id: str, version: str) -> bool:
        return self.release_catalog.recognizes(protocol_id, version) or self.release_catalog.get_release_envelope(protocol_id, version) is not None or (protocol_id, version) in self.protocols

    def protocol_lifecycle(self, protocol_id: str, version: str) -> dict | None:
        return self.release_catalog.lifecycle(protocol_id, version)

    def _load_protocols(self) -> set[tuple[str, str]]:
        result = {(item["id"], item["version"]) for item in self.release_catalog.releases}
        result.update((item["id"], item["version"]) for item in self.release_catalog.release_envelopes)
        result.update(
            (str(item["protocol_id"]), str(item["version"]))
            for item in self.artifacts.releases()
        )
        for protocol_dir in self.overlay_dirs:
            if not protocol_dir.is_dir():
                continue
            for path in protocol_dir.glob("*.json"):
                data = self._read_json(path)
                protocol_id = data.get("id")
                version = data.get("version")
                if protocol_id and version:
                    result.add((str(protocol_id), str(version)))
        return result

    def _load_protocol_history(self) -> dict[tuple[str, str], dict]:
        return {
            (item["id"], item["version"]): self.release_catalog.lifecycle(item["id"], item["version"])
            for item in self.release_catalog.releases
            if item["lifecycle"] == "recognized_legacy"
        }

    def _load_catalog_id_set(self, field: str, key: str) -> set[str]:
        """Merge vocabularies declared by the versioned release catalog."""
        result: set[str] = set()
        releases = [*self.release_catalog.releases, *self.release_catalog.release_envelopes]
        paths = sorted({str(release[field]) for release in releases})
        if not paths:
            raise ProtocolRegistryError(f"protocol catalog does not declare any {field} files")
        for path in paths:
            data = self._read_protocol_json(path)
            items = data.get(key)
            if not isinstance(items, list):
                raise ProtocolRegistryError(f"protocol/{path}.{key} must be an array")
            for index, item in enumerate(items):
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item.get("id").strip():
                    raise ProtocolRegistryError(f"protocol/{path}.{key}[{index}].id is required")
                result.add(item["id"])
        return result

    def _load_base_tool_packs(self) -> set[str]:
        base_contract = self.release_catalog.data["base_contract"]
        version = str(base_contract["version"])
        release_path = f"base/{version}/release.json"
        release = self._read_protocol_json(release_path)
        tool_packs_file = release.get("tool_packs_file")
        if not isinstance(tool_packs_file, str) or not tool_packs_file:
            raise ProtocolRegistryError(f"protocol/{release_path}.tool_packs_file is required")
        return self._load_protocol_id_set(tool_packs_file, "tool_packs")

    def _load_protocol_id_set(self, path: str, key: str) -> set[str]:
        data = self._read_protocol_json(path)
        items = data.get(key)
        if not isinstance(items, list):
            raise ProtocolRegistryError(f"protocol/{path}.{key} must be an array")
        result: set[str] = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item.get("id").strip():
                raise ProtocolRegistryError(f"protocol/{path}.{key}[{index}].id is required")
            result.add(item["id"])
        return result

    def _read_protocol_json(self, path: str) -> dict:
        try:
            return self.artifacts.read_json(path)
        except ValueError as exc:
            raise ProtocolRegistryError(str(exc)) from exc

    def _read_json(self, path: Path) -> dict:
        if not path.is_file():
            raise ProtocolRegistryError(f"protocol registry file not found: {path.name}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProtocolRegistryError(f"{path.name} is not valid JSON: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise ProtocolRegistryError(f"{path.name} must be an object")
        return data

    def _finding(self, severity: str, code: str, message: str) -> dict:
        return {"severity": severity, "code": code, "message": message}
