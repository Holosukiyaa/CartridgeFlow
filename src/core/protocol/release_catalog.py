from __future__ import annotations

import json
from pathlib import Path


class ProtocolReleaseCatalogError(ValueError):
    pass


RELEASE_MANIFEST_PATH = Path("protocol/catalog/release_manifest.json")
_LIFECYCLES = {"current", "supported_previous", "recognized_legacy"}
_RELEASE_ENVELOPE_LIFECYCLES = {"draft", "active", "supported_previous"}


class ProtocolReleaseCatalog:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.data = _load_release_manifest(self.root)
        self.releases = self.data["releases"]
        self.release_envelopes = self.data["release_envelopes"]["releases"]
        self._by_key = {(item["id"], item["version"]): item for item in self.releases}
        self._release_envelopes_by_key = {(item["id"], item["version"]): item for item in self.release_envelopes}

    def get(self, protocol_id: str, version: str) -> dict | None:
        return self._by_key.get((str(protocol_id), str(version)))

    def recognizes(self, protocol_id: str, version: str) -> bool:
        return self.get(protocol_id, version) is not None

    def published(self, protocol_id: str, version: str) -> bool:
        item = self.get(protocol_id, version)
        return bool(item and item["lifecycle"] in {"current", "supported_previous"})

    def lifecycle(self, protocol_id: str, version: str) -> dict | None:
        item = self.get(protocol_id, version)
        if not item or item["lifecycle"] != "recognized_legacy":
            return None
        return {
            "id": item["id"],
            "version": item["version"],
            "status": "recognized",
            "migration_target": item.get("migration_target"),
            "document": item.get("document"),
        }

    def get_release_envelope(self, protocol_id: str, version: str) -> dict | None:
        return self._release_envelopes_by_key.get((str(protocol_id), str(version)))

    def default_release_envelope(self) -> dict | None:
        default = self.data["release_envelopes"]["default_for_new_releases"]
        return self.get_release_envelope(str(default["id"]), str(default["version"]))

    def public_payload(self) -> dict:
        default = dict(self.data["default_for_new_flows"])
        return {
            "schema": self.data["schema"],
            "base_contract": dict(self.data["base_contract"]),
            "default_for_new_flows": {**default, "label": f"{default['id']}@{default['version']}"},
            "releases": [
                {key: value for key, value in item.items() if key in {"id", "version", "lifecycle", "migration_target"}}
                for item in self.releases
            ],
            "release_envelopes": {
                "default_for_new_releases": dict(self.data["release_envelopes"]["default_for_new_releases"]),
                "releases": [
                    {key: value for key, value in item.items() if key in {"id", "version", "lifecycle", "implementation_status"}}
                    for item in self.release_envelopes
                ],
            },
        }


def load_protocol_release_catalog(root: str | Path) -> ProtocolReleaseCatalog:
    return ProtocolReleaseCatalog(root)


def _load_release_manifest(root: Path) -> dict:
    path = root / RELEASE_MANIFEST_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProtocolReleaseCatalogError(f"{RELEASE_MANIFEST_PATH.as_posix()} not found") from exc
    except json.JSONDecodeError as exc:
        raise ProtocolReleaseCatalogError(f"{RELEASE_MANIFEST_PATH.as_posix()} is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict) or data.get("schema") != "cartridgeflow.protocol_release_manifest.v1":
        raise ProtocolReleaseCatalogError("protocol release manifest has an unknown schema")
    for field in ("base_contract", "default_for_new_flows"):
        value = data.get(field)
        if not isinstance(value, dict) or not value.get("id") or not value.get("version"):
            raise ProtocolReleaseCatalogError(f"protocol release manifest {field} requires id and version")
    releases = data.get("releases")
    if not isinstance(releases, list) or not releases:
        raise ProtocolReleaseCatalogError("protocol release manifest releases must be a non-empty array")
    seen: set[tuple[str, str]] = set()
    current = 0
    for index, item in enumerate(releases):
        if not isinstance(item, dict) or not item.get("id") or not item.get("version"):
            raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}] requires id and version")
        key = (str(item["id"]), str(item["version"]))
        if key in seen:
            raise ProtocolReleaseCatalogError(f"protocol release manifest duplicates {key[0]}@{key[1]}")
        seen.add(key)
        if item.get("lifecycle") not in _LIFECYCLES:
            raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}].lifecycle is invalid")
        if not isinstance(item.get("registry"), str) or not item["registry"]:
            raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}].registry is required")
        if item["lifecycle"] == "recognized_legacy":
            target = item.get("migration_target")
            if not isinstance(target, dict) or not target.get("id") or not target.get("version"):
                raise ProtocolReleaseCatalogError(f"legacy release {key[0]}@{key[1]} requires migration_target")
        if item["lifecycle"] == "current":
            current += 1
    default = (str(data["default_for_new_flows"]["id"]), str(data["default_for_new_flows"]["version"]))
    if current != 1 or default not in seen or next(item for item in releases if (item["id"], item["version"]) == default)["lifecycle"] != "current":
        raise ProtocolReleaseCatalogError("default_for_new_flows must be the only current release")
    _validate_release_envelopes(data)
    return data


def _validate_release_envelopes(data: dict) -> None:
    track = data.get("release_envelopes")
    if not isinstance(track, dict):
        raise ProtocolReleaseCatalogError("protocol release manifest release_envelopes is required")
    default = track.get("default_for_new_releases")
    if not isinstance(default, dict) or not default.get("id") or not default.get("version"):
        raise ProtocolReleaseCatalogError("release_envelopes.default_for_new_releases requires id and version")
    releases = track.get("releases")
    if not isinstance(releases, list) or not releases:
        raise ProtocolReleaseCatalogError("release_envelopes.releases must be a non-empty array")
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(releases):
        if not isinstance(item, dict) or not item.get("id") or not item.get("version"):
            raise ProtocolReleaseCatalogError(f"release_envelopes.releases[{index}] requires id and version")
        key = (str(item["id"]), str(item["version"]))
        if key in seen:
            raise ProtocolReleaseCatalogError(f"release_envelopes duplicates {key[0]}@{key[1]}")
        seen.add(key)
        if item.get("lifecycle") not in _RELEASE_ENVELOPE_LIFECYCLES:
            raise ProtocolReleaseCatalogError(f"release_envelopes.releases[{index}].lifecycle is invalid")
        if item.get("implementation_status") not in {"validation_only", "partial", "supported"}:
            raise ProtocolReleaseCatalogError(f"release_envelopes.releases[{index}].implementation_status is invalid")
        for field in ("registry", "profiles", "capabilities", "document"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise ProtocolReleaseCatalogError(f"release_envelopes.releases[{index}].{field} is required")
    if (str(default["id"]), str(default["version"])) not in seen:
        raise ProtocolReleaseCatalogError("release_envelopes.default_for_new_releases must name a registered release")
