from __future__ import annotations

import json
from pathlib import Path


class ProtocolRegistryError(ValueError):
    pass


class ProtocolRegistry:
    def __init__(self, root: str | Path, overlay_dirs: list[str | Path] | None = None):
        self.root = Path(root)
        self.protocol_dir = self.root / "protocol"
        self.overlay_dirs = [Path(item) for item in (overlay_dirs or [])]
        self.protocols = self._load_protocols()
        self.profiles = self._load_id_set("profiles.json", "profiles")
        self.capabilities = self._load_id_set("capabilities.json", "capabilities")
        self.tool_packs = self._load_id_set("tool_packs.json", "tool_packs")

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
        return (protocol_id, version) in self.protocols

    def _load_protocols(self) -> set[tuple[str, str]]:
        result: set[tuple[str, str]] = set()
        for protocol_dir in [self.protocol_dir, *self.overlay_dirs]:
            if not protocol_dir.is_dir():
                continue
            for path in protocol_dir.glob("*.json"):
                if protocol_dir == self.protocol_dir and path.name in {"profiles.json", "capabilities.json", "tool_packs.json"}:
                    continue
                data = self._read_json(path)
                protocol_id = data.get("id")
                version = data.get("version")
                if protocol_id and version:
                    result.add((str(protocol_id), str(version)))
        return result

    def _load_id_set(self, filename: str, key: str) -> set[str]:
        path = self.protocol_dir / filename
        data = self._read_json(path)
        items = data.get(key)
        if not isinstance(items, list):
            raise ProtocolRegistryError(f"protocol/{filename}.{key} must be an array")
        result: set[str] = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item.get("id").strip():
                raise ProtocolRegistryError(f"protocol/{filename}.{key}[{index}].id is required")
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
