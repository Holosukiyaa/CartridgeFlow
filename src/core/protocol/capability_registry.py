from __future__ import annotations

import json
from pathlib import Path

from .artifact_store import ProtocolArtifactStore
from .base_manifest import load_base_implementation
from .release_catalog import ProtocolReleaseCatalog, load_protocol_release_catalog
from .runtime_catalog import load_runtime_protocol_catalog


class ProtocolRegistryError(ValueError):
    pass


class ProtocolRegistry:
    def __init__(self, root: str | Path, overlay_dirs: list[str | Path] | None = None):
        self.root = Path(root)
        self.artifacts = ProtocolArtifactStore(self.root)
        self.overlay_dirs = [Path(item) for item in (overlay_dirs or [])]
        self.release_catalog: ProtocolReleaseCatalog = load_protocol_release_catalog(self.root)
        self.runtime_catalog = load_runtime_protocol_catalog(self.root)
        self.protocols = self._load_protocols()
        self.protocol_history = self._load_protocol_history()
        vocabularies = self.runtime_catalog["vocabularies"]
        self.profiles = set(vocabularies["profiles"])
        self.capabilities = set(vocabularies["capabilities"])
        self.tool_packs = set(vocabularies["tool_packs"])

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
        base = load_base_implementation(self.root)
        for field in ("supported_protocols", "supported_subprotocols"):
            result.update(
                (str(item["id"]), str(item["version"]))
                for item in base.get(field) or []
                if isinstance(item, dict) and item.get("id") and item.get("version")
            )
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

    @staticmethod
    def _read_json(path: Path) -> dict:
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
