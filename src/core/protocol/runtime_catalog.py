from __future__ import annotations

import hashlib
import json
from pathlib import Path


RUNTIME_CATALOG_RELATIVE_PATH = Path("config/protocol/runtime-compatibility.json")
RUNTIME_CATALOG_SCHEMA = "cartridgeflow.runtime_protocol_catalog.v1"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class RuntimeProtocolCatalogError(ValueError):
    pass


def load_runtime_protocol_catalog(root: str | Path) -> dict:
    path = _resolve_runtime_catalog_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeProtocolCatalogError(
            f"runtime protocol catalog is missing or invalid: {RUNTIME_CATALOG_RELATIVE_PATH.as_posix()}"
        ) from exc
    if not isinstance(data, dict) or data.get("schema") != RUNTIME_CATALOG_SCHEMA:
        raise RuntimeProtocolCatalogError("runtime protocol catalog has an unknown schema")
    manifest = data.get("release_manifest")
    if not isinstance(manifest, dict):
        raise RuntimeProtocolCatalogError("runtime protocol catalog requires release_manifest")
    releases = manifest.get("releases")
    if not isinstance(releases, list) or not releases:
        raise RuntimeProtocolCatalogError("runtime protocol catalog requires release_manifest.releases")
    for release_index, release in enumerate(releases):
        if not isinstance(release, dict):
            raise RuntimeProtocolCatalogError(
                f"runtime protocol catalog release_manifest.releases[{release_index}] must be an object"
            )
        for binding_index, binding in enumerate(release.get("trusted_subprotocols") or []):
            if (
                not isinstance(binding, dict)
                or not all(isinstance(binding.get(field), str) and binding[field].strip() for field in ("id", "version", "binding"))
                or not isinstance(binding.get("required"), bool)
            ):
                raise RuntimeProtocolCatalogError(
                    "runtime protocol catalog trusted subprotocol bindings require id, version, binding, and required"
                )
    vocabularies = data.get("vocabularies")
    if not isinstance(vocabularies, dict):
        raise RuntimeProtocolCatalogError("runtime protocol catalog requires vocabularies")
    for field in ("profiles", "capabilities", "tool_packs"):
        values = vocabularies.get(field)
        if (
            not isinstance(values, list)
            or any(not isinstance(value, str) or not value.strip() for value in values)
            or len(values) != len(set(values))
        ):
            raise RuntimeProtocolCatalogError(
                f"runtime protocol catalog vocabularies.{field} must contain unique non-empty strings"
            )
    contracts = data.get("data_contracts")
    if not isinstance(contracts, list) or not contracts:
        raise RuntimeProtocolCatalogError("runtime protocol catalog requires data_contracts")
    identities: set[tuple[str, str]] = set()
    for index, item in enumerate(contracts):
        if not isinstance(item, dict):
            raise RuntimeProtocolCatalogError(
                f"runtime protocol catalog data_contracts[{index}] must be an object"
            )
        identity = (str(item.get("id") or ""), str(item.get("version") or ""))
        if not all(identity) or identity in identities:
            raise RuntimeProtocolCatalogError(
                f"runtime protocol catalog data_contracts[{index}] has an invalid or duplicate identity"
            )
        identities.add(identity)
        if item.get("definition_kind") not in {"json_schema", "machine_contract"}:
            raise RuntimeProtocolCatalogError(
                f"runtime protocol catalog data_contracts[{index}] has an invalid definition_kind"
            )
        if not isinstance(item.get("definition"), dict):
            raise RuntimeProtocolCatalogError(
                f"runtime protocol catalog data_contracts[{index}] requires an object definition"
            )
        examples = item.get("examples", {})
        if (
            not isinstance(examples, dict)
            or not set(examples).issubset({"valid", "invalid"})
        ):
            raise RuntimeProtocolCatalogError(
                f"runtime protocol catalog data_contracts[{index}] examples are invalid"
            )
    return data


def find_runtime_data_contract(
    root: str | Path,
    contract_id: str,
    version: str,
) -> dict | None:
    for item in load_runtime_protocol_catalog(root)["data_contracts"]:
        if (str(item["id"]), str(item["version"])) == (
            str(contract_id),
            str(version),
        ):
            return item
    return None


def runtime_protocol_catalog_digest(root: str | Path) -> str:
    path = _resolve_runtime_catalog_path(root)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise RuntimeProtocolCatalogError(
            f"runtime protocol catalog is unavailable: {RUNTIME_CATALOG_RELATIVE_PATH.as_posix()}"
        ) from exc


def _resolve_runtime_catalog_path(root: str | Path) -> Path:
    candidate = Path(root).resolve() / RUNTIME_CATALOG_RELATIVE_PATH
    if candidate.is_file():
        return candidate
    fallback = PROJECT_ROOT / RUNTIME_CATALOG_RELATIVE_PATH
    return fallback if fallback.is_file() else candidate
