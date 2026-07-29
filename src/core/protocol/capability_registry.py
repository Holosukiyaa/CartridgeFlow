from __future__ import annotations

import json
from pathlib import Path

from .release_catalog import ProtocolReleaseCatalog, load_protocol_release_catalog


class ProtocolRegistryError(ValueError):
    pass


class ProtocolRegistry:
    def __init__(self, root: str | Path, overlay_dirs: list[str | Path] | None = None):
        self.root = Path(root)
        self.protocol_dir = self.root / "protocol"
        self.base_dir = self.protocol_dir / "base"
        self.vocabulary_dir = self.protocol_dir / "vocabulary"
        self.tooling_dir = self.protocol_dir / "tooling"
        self.overlay_dirs = [Path(item) for item in (overlay_dirs or [])]
        self.release_catalog: ProtocolReleaseCatalog = load_protocol_release_catalog(self.root)
        self.protocols = self._load_protocols()
        self.protocol_history = self._load_protocol_history()
        self.profiles = self._load_versioned_id_set("profiles", "profiles")
        self.capabilities = self._load_versioned_id_set("capabilities", "capabilities")
        self.tool_packs = self._load_id_set(self.tooling_dir / "tool_packs.json", "tool_packs")

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
        return (protocol_id, version) in self.protocols

    def recognizes_protocol(self, protocol_id: str, version: str) -> bool:
        return self.release_catalog.recognizes(protocol_id, version) or (protocol_id, version) in self.protocols

    def protocol_lifecycle(self, protocol_id: str, version: str) -> dict | None:
        return self.release_catalog.lifecycle(protocol_id, version)

    def _load_protocols(self) -> set[tuple[str, str]]:
        result = {(item["id"], item["version"]) for item in self.release_catalog.releases}
        for path in self.base_dir.glob("CARTRIDGEFLOW-BASE-*.json"):
            data = self._read_json(path)
            if data.get("id") and data.get("version"):
                result.add((str(data["id"]), str(data["version"])))
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

    def _load_id_set(self, path: Path, key: str) -> set[str]:
        data = self._read_json(path)
        items = data.get(key)
        if not isinstance(items, list):
            raise ProtocolRegistryError(f"{path.relative_to(self.root)}.{key} must be an array")
        result: set[str] = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item.get("id").strip():
                raise ProtocolRegistryError(f"protocol/{filename}.{key}[{index}].id is required")
            result.add(item["id"])
        return result

    def _load_versioned_id_set(self, stem: str, key: str) -> set[str]:
        """Merge the base vocabulary with protocol-version vocabulary snapshots."""
        result: set[str] = set()
        paths = sorted(self.vocabulary_dir.glob(f"{stem}*.json"))
        if not paths:
            raise ProtocolRegistryError(f"protocol vocabulary file not found: {stem}.json")
        for path in paths:
            data = self._read_json(path)
            items = data.get(key)
            if not isinstance(items, list):
                raise ProtocolRegistryError(f"protocol/{path.name}.{key} must be an array")
            for index, item in enumerate(items):
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item.get("id").strip():
                    raise ProtocolRegistryError(f"protocol/{path.name}.{key}[{index}].id is required")
                result.add(item["id"])
        return result

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
