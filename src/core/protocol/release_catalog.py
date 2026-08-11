from __future__ import annotations

from pathlib import Path

from .runtime_catalog import load_runtime_protocol_catalog


class ProtocolReleaseCatalogError(ValueError):
    pass


_LIFECYCLES = {"current", "supported_previous", "recognized_legacy"}
_RELEASE_ENVELOPE_LIFECYCLES = {"draft", "active", "supported_previous"}
_ADAPTER_STATUSES = {"partial", "supported"}
_FLOW_RELEASE_STATUSES = {"draft", "active"}


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
        if not item or item["lifecycle"] not in {"current", "supported_previous"}:
            return False
        # Historical releases predate explicit delivery state. Their lifecycle remains authoritative.
        if "status" in item and item.get("status") != "active":
            return False
        if "implementation_status" in item and item.get("implementation_status") != "supported":
            return False
        return True

    def runtime_adapter(self, protocol_id: str, version: str) -> str | None:
        item = self.get(protocol_id, version)
        adapter = item.get("runtime_adapter") if item else None
        return str(adapter) if isinstance(adapter, str) and adapter else None

    def features(self, protocol_id: str, version: str) -> frozenset[str]:
        item = self.get(protocol_id, version)
        return frozenset(str(feature) for feature in (item or {}).get("features") or [])

    def has_feature(self, protocol_id: str, version: str, feature: str) -> bool:
        return str(feature) in self.features(protocol_id, version)

    def trusted_subprotocols(self, protocol_id: str, version: str) -> tuple[dict, ...]:
        item = self.get(protocol_id, version) or {}
        return tuple(dict(entry) for entry in item.get("trusted_subprotocols") or [])

    def trusts_subprotocol(self, protocol_id: str, version: str, subprotocol_id: str, subprotocol_version: str) -> bool:
        return any(
            str(item.get("id")) == str(subprotocol_id)
            and str(item.get("version")) == str(subprotocol_version)
            for item in self.trusted_subprotocols(protocol_id, version)
        )

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

    def release_envelope_published(self, protocol_id: str, version: str) -> bool:
        item = self.get_release_envelope(protocol_id, version)
        return bool(
            item
            and item.get("lifecycle") in {"active", "supported_previous"}
            and item.get("implementation_status") == "supported"
        )

    def public_payload(self) -> dict:
        default = dict(self.data["default_for_new_flows"])
        return {
            "schema": self.data["schema"],
            "base_contract": dict(self.data["base_contract"]),
            "default_for_new_flows": {**default, "label": f"{default['id']}@{default['version']}"},
            "releases": [
                {
                    key: value
                    for key, value in item.items()
                    if key in {"id", "version", "lifecycle", "status", "implementation_status", "migration_target", "runtime_adapter", "features", "trusted_subprotocols"}
                }
                for item in self.releases
            ],
            "release_envelopes": {
                "default_for_new_releases": dict(self.data["release_envelopes"]["default_for_new_releases"]),
                "releases": [
                    {
                        key: value
                        for key, value in item.items()
                        if key in {"id", "version", "lifecycle", "implementation_status", "runtime_adapter", "features"}
                    }
                    for item in self.release_envelopes
                ],
            },
        }


def load_protocol_release_catalog(root: str | Path) -> ProtocolReleaseCatalog:
    return ProtocolReleaseCatalog(root)


def _load_release_manifest(root: Path) -> dict:
    try:
        data = load_runtime_protocol_catalog(root)["release_manifest"]
    except ValueError as exc:
        raise ProtocolReleaseCatalogError(str(exc)) from exc
    if not isinstance(data, dict) or data.get("schema") != "cartridgeflow.runtime_protocol_release_manifest.v1":
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
        if "status" in item and item.get("status") not in _FLOW_RELEASE_STATUSES:
            raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}].status is invalid")
        if "implementation_status" in item and item.get("implementation_status") not in _ADAPTER_STATUSES:
            raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}].implementation_status is invalid")
        adapter = item.get("runtime_adapter")
        if adapter is not None and (not isinstance(adapter, str) or not adapter.strip()):
            raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}].runtime_adapter must be a non-empty string")
        features = item.get("features", [])
        if not isinstance(features, list) or any(not isinstance(feature, str) or not feature.strip() for feature in features):
            raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}].features must be an array of non-empty strings")
        if len(set(features)) != len(features):
            raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}].features must not contain duplicates")
        trusted_subprotocols = item.get("trusted_subprotocols", [])
        if not isinstance(trusted_subprotocols, list):
            raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}].trusted_subprotocols must be an array")
        trusted_seen: set[tuple[str, str]] = set()
        for sub_index, subprotocol in enumerate(trusted_subprotocols):
            if not isinstance(subprotocol, dict) or not subprotocol.get("id") or not subprotocol.get("version"):
                raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}].trusted_subprotocols[{sub_index}] requires id and version")
            sub_key = (str(subprotocol["id"]), str(subprotocol["version"]))
            if sub_key in trusted_seen:
                raise ProtocolReleaseCatalogError(f"protocol release manifest releases[{index}] duplicates trusted subprotocol {sub_key[0]}@{sub_key[1]}")
            trusted_seen.add(sub_key)
            required = subprotocol.get("required")
            if required is not None and not isinstance(required, bool):
                raise ProtocolReleaseCatalogError(
                    f"protocol release manifest releases[{index}].trusted_subprotocols[{sub_index}].required must be boolean"
                )
        if item["lifecycle"] == "recognized_legacy":
            target = item.get("migration_target")
            if not isinstance(target, dict) or not target.get("id") or not target.get("version"):
                raise ProtocolReleaseCatalogError(f"legacy release {key[0]}@{key[1]} requires migration_target")
        if item["lifecycle"] in {"current", "supported_previous"} and not adapter:
            raise ProtocolReleaseCatalogError(f"published release {key[0]}@{key[1]} requires runtime_adapter")
        if item["lifecycle"] == "current":
            if not adapter:
                raise ProtocolReleaseCatalogError(f"current release {key[0]}@{key[1]} requires runtime_adapter")
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
        adapter = item.get("runtime_adapter")
        if adapter is not None and (not isinstance(adapter, str) or not adapter.strip()):
            raise ProtocolReleaseCatalogError(f"release_envelopes.releases[{index}].runtime_adapter must be a non-empty string")
        features = item.get("features", [])
        if not isinstance(features, list) or any(not isinstance(feature, str) or not feature.strip() for feature in features):
            raise ProtocolReleaseCatalogError(f"release_envelopes.releases[{index}].features must be an array of non-empty strings")
        if len(set(features)) != len(features):
            raise ProtocolReleaseCatalogError(f"release_envelopes.releases[{index}].features must not contain duplicates")
        if item.get("lifecycle") in {"active", "supported_previous"} and not adapter:
            raise ProtocolReleaseCatalogError(f"published release envelope {key[0]}@{key[1]} requires runtime_adapter")
    if (str(default["id"]), str(default["version"])) not in seen:
        raise ProtocolReleaseCatalogError("release_envelopes.default_for_new_releases must name a registered release")
