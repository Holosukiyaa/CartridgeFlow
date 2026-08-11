from __future__ import annotations

import json
import re
from pathlib import Path


class BaseManifestError(ValueError):
    pass


BASE_IMPLEMENTATION_PATH = Path("config/base/BASE_IMPLEMENTATION.json")
_ADAPTER_STATUSES = {"partial", "supported"}
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")


def load_base_implementation(root: str | Path) -> dict:
    root_path = Path(root)
    path = root_path / BASE_IMPLEMENTATION_PATH
    if not path.is_file():
        raise BaseManifestError(f"{BASE_IMPLEMENTATION_PATH.as_posix()} not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BaseManifestError(f"{BASE_IMPLEMENTATION_PATH.as_posix()} is not valid JSON: {exc.msg}") from exc
    validate_base_implementation(data)
    return data


def validate_base_implementation(data: dict) -> None:
    if not isinstance(data, dict):
        raise BaseManifestError("base implementation manifest must be an object")
    for field in ["schema_version", "implementation_id", "implementation_version", "environment"]:
        if not isinstance(data.get(field), str) or not data.get(field).strip():
            raise BaseManifestError(f"base.{field} is required")
    if data.get("environment") not in {"development", "production", "test"}:
        raise BaseManifestError("base.environment must be development, production, or test")
    if data.get("schema_version") in {"0.2", "0.3"}:
        base_contract = data.get("base_contract")
        if not isinstance(base_contract, dict):
            raise BaseManifestError("base.base_contract is required for schema 0.2")
        if not isinstance(base_contract.get("id"), str) or not base_contract.get("id").strip():
            raise BaseManifestError("base.base_contract.id is required")
        if not isinstance(base_contract.get("version"), str) or not base_contract.get("version").strip():
            raise BaseManifestError("base.base_contract.version is required")
    generation = data.get("protocol_generation")
    if data.get("schema_version") == "0.3":
        if not isinstance(generation, dict):
            raise BaseManifestError("base.protocol_generation is required")
        if generation.get("id") != "unified-v1" or generation.get("source_id") != "unified":
            raise BaseManifestError(
                "base.protocol_generation must select unified-v1 from source unified"
            )
        layers = generation.get("layers")
        if not isinstance(layers, list) or len(layers) != 4:
            raise BaseManifestError("base.protocol_generation.layers must contain four layers")
        expected_layers = {
            1: ("CF-FOUNDATION", "1.0.0", "cf.foundation.v1"),
            2: ("CF-AUTHORING", "1.0.0", "cf.authoring.v1"),
            3: ("CF-DISTRIBUTION", "1.0.0", "cf.distribution.v1"),
            4: ("CF-RUNTIME", "1.0.0", "cf.runtime.v1"),
        }
        actual_layers: dict[int, tuple[str, str, str]] = {}
        for index, layer in enumerate(layers):
            if not isinstance(layer, dict) or not isinstance(layer.get("layer"), int):
                raise BaseManifestError(
                    f"base.protocol_generation.layers[{index}] must declare an integer layer"
                )
            number = layer["layer"]
            identity = (
                str(layer.get("id") or ""),
                str(layer.get("version") or ""),
                str(layer.get("runtime_adapter") or ""),
            )
            if number in actual_layers:
                raise BaseManifestError(f"base.protocol_generation duplicates layer {number}")
            actual_layers[number] = identity
        if actual_layers != expected_layers:
            raise BaseManifestError(
                "base.protocol_generation.layers does not match the unified-v1 architecture"
            )
    supported_base_contracts = data.get("supported_base_contracts", [])
    if data.get("schema_version") == "0.3" and not isinstance(supported_base_contracts, list):
        raise BaseManifestError("base.supported_base_contracts must be an array")
    for index, item in enumerate(supported_base_contracts if isinstance(supported_base_contracts, list) else []):
        if not isinstance(item, dict) or not item.get("id") or not item.get("version"):
            raise BaseManifestError(f"base.supported_base_contracts[{index}] requires id and version")
        if item.get("status") not in {"current", "supported_previous"}:
            raise BaseManifestError(f"base.supported_base_contracts[{index}].status is invalid")
    data_contracts = data.get("supported_data_contracts", [])
    if data.get("schema_version") == "0.3" and not isinstance(data_contracts, list):
        raise BaseManifestError("base.supported_data_contracts must be an array")
    contract_identities: set[tuple[str, str]] = set()
    for index, item in enumerate(data_contracts if isinstance(data_contracts, list) else []):
        if not isinstance(item, dict):
            raise BaseManifestError(f"base.supported_data_contracts[{index}] must be an object")
        contract_id = str(item.get("id") or "")
        version = str(item.get("version") or "")
        identity = (contract_id, version)
        if not contract_id or not _SEMVER.fullmatch(version):
            raise BaseManifestError(
                f"base.supported_data_contracts[{index}] requires id and semantic version"
            )
        if identity in contract_identities:
            raise BaseManifestError(
                f"base.supported_data_contracts duplicates {contract_id}@{version}"
            )
        contract_identities.add(identity)
        if item.get("status") != "supported":
            raise BaseManifestError(
                f"base.supported_data_contracts[{index}].status must be supported"
            )
        if not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
            raise BaseManifestError(
                f"base.supported_data_contracts[{index}].evidence is required"
            )
    if not isinstance(data.get("supported_protocols"), list):
        raise BaseManifestError("base.supported_protocols must be an array")
    for index, item in enumerate(data.get("supported_protocols") or []):
        if not isinstance(item, dict):
            raise BaseManifestError(f"base.supported_protocols[{index}] must be an object")
        if not item.get("id") or not item.get("version"):
            raise BaseManifestError(f"base.supported_protocols[{index}] requires id and version")
        if item.get("status") not in _ADAPTER_STATUSES:
            raise BaseManifestError(f"base.supported_protocols[{index}].status is invalid")
    supported_subprotocols = data.get("supported_subprotocols", [])
    if data.get("schema_version") == "0.3" and not isinstance(supported_subprotocols, list):
        raise BaseManifestError("base.supported_subprotocols must be an array")
    for index, item in enumerate(supported_subprotocols if isinstance(supported_subprotocols, list) else []):
        if not isinstance(item, dict):
            raise BaseManifestError(f"base.supported_subprotocols[{index}] must be an object")
        if not item.get("id") or not item.get("version"):
            raise BaseManifestError(f"base.supported_subprotocols[{index}] requires id and version")
        if item.get("status") not in _ADAPTER_STATUSES:
            raise BaseManifestError(f"base.supported_subprotocols[{index}].status is invalid")
        if not isinstance(item.get("runtime_adapter"), str) or not item["runtime_adapter"].strip():
            raise BaseManifestError(f"base.supported_subprotocols[{index}].runtime_adapter is required")
        hosts = item.get("host_protocols")
        if not isinstance(hosts, list) or not hosts or any(not isinstance(host, dict) or not host.get("id") or not host.get("version") for host in hosts):
            raise BaseManifestError(f"base.supported_subprotocols[{index}].host_protocols requires protocol identities")
    adapters = data.get("supported_protocol_adapters", [])
    if not isinstance(adapters, list):
        raise BaseManifestError("base.supported_protocol_adapters must be an array")
    adapter_ids: set[str] = set()
    for index, item in enumerate(adapters):
        if not isinstance(item, dict):
            raise BaseManifestError(f"base.supported_protocol_adapters[{index}] must be an object")
        adapter_id = item.get("id")
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise BaseManifestError(f"base.supported_protocol_adapters[{index}].id is required")
        if adapter_id in adapter_ids:
            raise BaseManifestError(f"base.supported_protocol_adapters duplicates {adapter_id}")
        adapter_ids.add(adapter_id)
        if item.get("status") not in _ADAPTER_STATUSES:
            raise BaseManifestError(f"base.supported_protocol_adapters[{index}].status is invalid")
    for field in ["profiles", "capabilities", "tool_packs"]:
        if not isinstance(data.get(field), list):
            raise BaseManifestError(f"base.{field} must be an array")
        for index, value in enumerate(data.get(field) or []):
            if not isinstance(value, str) or not value.strip():
                raise BaseManifestError(f"base.{field}[{index}] must be a non-empty string")


def protocol_adapter_status(base: dict, adapter_id: str | None) -> str | None:
    if not adapter_id:
        return None
    for item in base.get("supported_protocol_adapters") or []:
        if isinstance(item, dict) and item.get("id") == adapter_id:
            status = item.get("status")
            return str(status) if status in _ADAPTER_STATUSES else None
    return None


def supports_protocol_release(base: dict, release: dict | None) -> bool:
    """Resolve Base support from an implementation adapter, then legacy exact versions."""
    if not isinstance(release, dict):
        return False
    if "status" in release and release.get("status") != "active":
        return False
    if "implementation_status" in release and release.get("implementation_status") != "supported":
        return False
    adapter = release.get("runtime_adapter")
    if protocol_adapter_status(base, str(adapter) if adapter else None):
        return True
    expected = (str(release.get("id") or ""), str(release.get("version") or ""))
    return any(
        isinstance(item, dict)
        and (str(item.get("id") or ""), str(item.get("version") or "")) == expected
        and item.get("status") in _ADAPTER_STATUSES
        for item in base.get("supported_protocols") or []
    )


def supports_base_contract(base: dict, contract_id: str, contract_version: str) -> bool:
    current = base.get("base_contract") if isinstance(base.get("base_contract"), dict) else {}
    if (str(current.get("id") or ""), str(current.get("version") or "")) == (str(contract_id), str(contract_version)):
        return True
    return any(
        isinstance(item, dict)
        and item.get("status") in {"current", "supported_previous"}
        and (str(item.get("id") or ""), str(item.get("version") or "")) == (str(contract_id), str(contract_version))
        for item in base.get("supported_base_contracts") or []
    )


def supports_subprotocol_release(
    base: dict,
    subprotocol_id: str,
    subprotocol_version: str,
    host_protocol_id: str,
    host_protocol_version: str,
) -> bool:
    for item in base.get("supported_subprotocols") or []:
        if not isinstance(item, dict) or item.get("status") != "supported":
            continue
        if str(item.get("id")) != str(subprotocol_id) or str(item.get("version")) != str(subprotocol_version):
            continue
        return any(
            isinstance(host, dict)
            and str(host.get("id")) == str(host_protocol_id)
            and str(host.get("version")) == str(host_protocol_version)
            for host in item.get("host_protocols") or []
        )
    return False
