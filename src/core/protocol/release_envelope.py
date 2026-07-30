"""Static validation for the draft CF-CRE@1 release envelope.

This module intentionally validates declarations and supplied bytes only. It does
not load a cartridge, verify an Ed25519 signature, or contact a market service.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

from .report import report_status, summarize_findings


RELEASE_SCHEMA = "cartridgeflow.release_envelope.v1"
HASHES_SCHEMA = "cartridgeflow.release_hashes.v1"
EXPERIENCE_SCHEMA = "cartridgeflow.cartridge_experience.v1"
DELIVERY_SCHEMA = "cartridgeflow.delivery_contract.v1"
REPORT_SCHEMA = "cartridgeflow.release_envelope_report.v1"

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_PUBLIC_FORBIDDEN_KEYS = {
    "api_key",
    "args",
    "authorization",
    "checkpoint",
    "command",
    "context",
    "credential",
    "credentials",
    "endpoint",
    "execution_plan",
    "node_id",
    "openapi_url",
    "prompt",
    "root_flow",
    "root_flow_path",
    "secret",
    "states",
    "store",
    "system_prompt",
    "token",
    "tool_parameters",
}
_INPUT_TYPES = {"string", "number", "boolean", "enum", "file", "object", "array"}
_PLACEMENTS = {"local", "cloud", "either"}
_CONTROL_FILES = {"release.manifest.json", "hashes.json"}


def validate_release_envelope(
    release: dict | None,
    experience: dict | None,
    delivery: dict | None,
    *,
    bundle_files: Mapping[str, bytes | str] | None = None,
) -> list[dict]:
    """Return deterministic findings for one CF-CRE@1 release candidate."""
    findings: list[dict] = []
    release = release if isinstance(release, dict) else {}
    supplied_experience = experience if isinstance(experience, dict) else None
    supplied_delivery = delivery if isinstance(delivery, dict) else None

    if release.get("schema") != RELEASE_SCHEMA:
        findings.append(_finding("cre_release_schema_invalid", "release.schema must be cartridgeflow.release_envelope.v1.", path="release.manifest.json"))

    identity = release.get("release") if isinstance(release.get("release"), dict) else {}
    publisher_id = _require_id(identity.get("publisher_id"), "publisher_id", findings, "release.release")
    cartridge_id = _require_id(identity.get("cartridge_id"), "cartridge_id", findings, "release.release")
    version = str(identity.get("version") or "")
    if not _SEMVER.fullmatch(version):
        findings.append(_finding("cre_release_version_invalid", "release.release.version must be a semantic version.", path="release.release.version"))

    integrity = release.get("integrity") if isinstance(release.get("integrity"), dict) else {}
    content_digest = _require_digest(integrity.get("content_digest"), "release.integrity.content_digest", findings)
    if integrity.get("hashes_path") != "hashes.json":
        findings.append(_finding("cre_hashes_path_invalid", "release.integrity.hashes_path must be hashes.json.", path="release.integrity.hashes_path"))

    release_id = str(release.get("release_id") or "")
    if publisher_id and cartridge_id and _SEMVER.fullmatch(version) and content_digest:
        expected_release_id = f"{publisher_id}:{cartridge_id}@{version}+{content_digest}"
        if release_id != expected_release_id:
            findings.append(_finding("cre_release_id_mismatch", "release_id must bind publisher, cartridge, version, and content_digest.", path="release.release_id"))
    elif not release_id:
        findings.append(_finding("cre_release_id_missing", "release_id is required.", path="release.release_id"))

    _validate_runtime(release.get("runtime"), findings)
    _validate_execution(release.get("execution"), findings)
    _validate_public_refs(release.get("public_contracts"), findings)
    _validate_payload(release.get("payload"), findings)
    signature_paths = _validate_signatures(release.get("signatures"), findings)
    if bundle_files is not None:
        public_contracts = _validate_bundle_files(release, bundle_files, signature_paths, findings)
        _validate_bound_public_contracts(
            public_contracts,
            supplied_experience,
            supplied_delivery,
            findings,
        )
    else:
        _validate_experience(supplied_experience or {}, findings)
        _validate_delivery(supplied_delivery or {}, findings)
    return findings


def build_release_envelope_report(
    release: dict | None,
    experience: dict | None,
    delivery: dict | None,
    *,
    bundle_files: Mapping[str, bytes | str] | None = None,
) -> dict:
    findings = validate_release_envelope(release, experience, delivery, bundle_files=bundle_files)
    counts = summarize_findings(findings)
    return {
        "schema": REPORT_SCHEMA,
        "protocol": "CF-CRE@1",
        "implementation_status": "partial",
        "ok": counts["blocker"] == 0,
        "status": report_status(findings),
        "summary": counts,
        "findings": findings,
    }


def _validate_runtime(value, findings: list[dict]) -> None:
    runtime = value if isinstance(value, dict) else {}
    for field in ("base_contract", "flow_contract"):
        contract = runtime.get(field) if isinstance(runtime.get(field), dict) else {}
        if not _valid_contract(contract):
            findings.append(_finding("cre_runtime_contract_invalid", f"release.runtime.{field} requires non-empty id and version.", path=f"release.runtime.{field}"))
    min_runner_version = str(runtime.get("min_runner_version") or "")
    if not _SEMVER.fullmatch(min_runner_version):
        findings.append(_finding("cre_min_runner_version_invalid", "release.runtime.min_runner_version must be a semantic version.", path="release.runtime.min_runner_version"))


def _validate_execution(value, findings: list[dict]) -> None:
    execution = value if isinstance(value, dict) else {}
    if execution.get("placement") not in _PLACEMENTS:
        findings.append(_finding("cre_execution_placement_invalid", "release.execution.placement must be local, cloud, or either.", path="release.execution.placement"))
    for field in ("required_capabilities", "required_permissions"):
        values = execution.get(field)
        if not _unique_ids(values):
            findings.append(_finding("cre_execution_requirements_invalid", f"release.execution.{field} must be a unique array of stable identifiers.", path=f"release.execution.{field}"))


def _validate_public_refs(value, findings: list[dict]) -> None:
    contracts = value if isinstance(value, dict) else {}
    expected = {"experience": "public/experience.json", "delivery": "public/delivery.contract.json"}
    for name, expected_path in expected.items():
        item = contracts.get(name) if isinstance(contracts.get(name), dict) else {}
        if item.get("path") != expected_path:
            findings.append(_finding("cre_public_contract_path_invalid", f"release.public_contracts.{name}.path must be {expected_path}.", path=f"release.public_contracts.{name}.path"))
        _require_digest(item.get("digest"), f"release.public_contracts.{name}.digest", findings)


def _validate_payload(value, findings: list[dict]) -> None:
    payload = value if isinstance(value, dict) else {}
    if payload.get("path") != "payload":
        findings.append(_finding("cre_payload_path_invalid", "release.payload.path must be payload.", path="release.payload.path"))
    _require_digest(payload.get("digest"), "release.payload.digest", findings)


def _validate_signatures(value, findings: list[dict]) -> set[str]:
    paths: set[str] = set()
    signatures = value if isinstance(value, list) else []
    if not signatures:
        findings.append(_finding("cre_signature_missing", "release.signatures must contain a publisher Ed25519 signature descriptor.", path="release.signatures"))
        return paths
    publisher_signature = False
    for index, item in enumerate(signatures):
        path = f"release.signatures[{index}]"
        if not isinstance(item, dict):
            findings.append(_finding("cre_signature_invalid", "signature descriptor must be an object.", path=path))
            continue
        key_id = str(item.get("key_id") or "")
        file_path = str(item.get("path") or "")
        if not _ID.fullmatch(key_id) or item.get("algorithm") != "ed25519" or not _safe_path(file_path) or not file_path.startswith("signatures/"):
            findings.append(_finding("cre_signature_invalid", "signature requires key_id, algorithm=ed25519, and a safe signatures/ path.", path=path))
            continue
        if file_path in paths:
            findings.append(_finding("cre_signature_duplicate", "signature paths must be unique.", path=f"{path}.path"))
            continue
        paths.add(file_path)
        publisher_signature = publisher_signature or item.get("role") == "publisher"
    if not publisher_signature:
        findings.append(_finding("cre_publisher_signature_missing", "release.signatures must contain one descriptor with role=publisher.", path="release.signatures"))
    return paths


def _validate_experience(value: dict, findings: list[dict]) -> None:
    if value.get("schema") != EXPERIENCE_SCHEMA:
        findings.append(_finding("cre_experience_schema_invalid", "experience.schema must be cartridgeflow.cartridge_experience.v1.", path="public/experience.json"))
    product = value.get("product") if isinstance(value.get("product"), dict) else {}
    if not _nonempty(product.get("name")) or not _nonempty(product.get("category")):
        findings.append(_finding("cre_experience_product_invalid", "experience.product requires name and category.", path="public/experience.json.product"))
    for field in ("inputs", "stages"):
        items = value.get(field)
        if not isinstance(items, list):
            findings.append(_finding("cre_experience_items_invalid", f"experience.{field} must be an array.", path=f"public/experience.json.{field}"))
            continue
        seen: set[str] = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not _ID.fullmatch(str(item.get("id") or "")) or not _nonempty(item.get("label")):
                findings.append(_finding("cre_experience_item_invalid", f"experience.{field}[{index}] requires id and label.", path=f"public/experience.json.{field}[{index}]"))
                continue
            if item["id"] in seen:
                findings.append(_finding("cre_experience_item_duplicate", f"experience.{field} ids must be unique.", path=f"public/experience.json.{field}[{index}].id"))
            seen.add(item["id"])
            if field == "inputs" and item.get("type") not in _INPUT_TYPES:
                findings.append(_finding("cre_experience_input_type_invalid", "experience input type is not supported.", path=f"public/experience.json.inputs[{index}].type"))
    if not value.get("stages"):
        findings.append(_finding("cre_experience_stage_missing", "experience.stages must contain at least one public stage.", path="public/experience.json.stages"))
    _find_public_leaks(value, "public/experience.json", findings)


def _validate_delivery(value: dict, findings: list[dict]) -> None:
    if value.get("schema") != DELIVERY_SCHEMA:
        findings.append(_finding("cre_delivery_schema_invalid", "delivery.schema must be cartridgeflow.delivery_contract.v1.", path="public/delivery.contract.json"))
    primary = value.get("primary_artifacts")
    if not isinstance(primary, list) or not primary:
        findings.append(_finding("cre_delivery_primary_missing", "delivery.primary_artifacts must contain at least one declared primary artifact.", path="public/delivery.contract.json.primary_artifacts"))
    else:
        seen: set[str] = set()
        for index, item in enumerate(primary):
            path = f"public/delivery.contract.json.primary_artifacts[{index}]"
            if not isinstance(item, dict) or not _ID.fullmatch(str(item.get("id") or "")) or not _nonempty(item.get("label")) or not _string_list(item.get("mime_types")):
                findings.append(_finding("cre_delivery_primary_invalid", "primary artifact requires id, label, and mime_types.", path=path))
                continue
            if item["id"] in seen:
                findings.append(_finding("cre_delivery_primary_duplicate", "primary artifact ids must be unique.", path=f"{path}.id"))
            seen.add(item["id"])
    revision = value.get("revision") if isinstance(value.get("revision"), dict) else {}
    if revision.get("mode") != "new_run":
        findings.append(_finding("cre_delivery_revision_invalid", "delivery.revision.mode must be new_run; a new production cannot overwrite a prior delivery.", path="public/delivery.contract.json.revision.mode"))
    states = _string_list(value.get("delivery_states"))
    if not {"produced", "delivered", "failed"}.issubset(set(states)):
        findings.append(_finding("cre_delivery_states_invalid", "delivery.delivery_states must include produced, delivered, and failed.", path="public/delivery.contract.json.delivery_states"))
    _find_public_leaks(value, "public/delivery.contract.json", findings)


def _validate_bundle_files(
    release: dict,
    bundle_files: Mapping[str, bytes | str],
    signature_paths: set[str],
    findings: list[dict],
) -> dict[str, dict]:
    normalized: dict[str, bytes] = {}
    for raw_path, raw_content in bundle_files.items():
        path = str(raw_path).replace("\\", "/")
        if not _safe_path(path):
            findings.append(_finding("cre_bundle_path_invalid", "bundle contains an unsafe path.", path=path))
            continue
        if path in normalized:
            findings.append(_finding("cre_bundle_path_duplicate", "bundle contains a duplicate path.", path=path))
            continue
        normalized[path] = raw_content.encode("utf-8") if isinstance(raw_content, str) else bytes(raw_content)

    public_contracts = _read_bundle_public_contracts(normalized, findings)

    hashes_bytes = normalized.get("hashes.json")
    integrity = release.get("integrity") if isinstance(release.get("integrity"), dict) else {}
    if hashes_bytes is None:
        findings.append(_finding("cre_hashes_file_missing", "bundle must contain hashes.json.", path="hashes.json"))
        return public_contracts
    actual_content_digest = _digest(hashes_bytes)
    if actual_content_digest != integrity.get("content_digest"):
        findings.append(_finding("cre_content_digest_mismatch", "hashes.json does not match release.integrity.content_digest.", path="hashes.json"))
    try:
        hashes = json.loads(hashes_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        findings.append(_finding("cre_hashes_file_invalid", "hashes.json must be valid UTF-8 JSON.", path="hashes.json"))
        return public_contracts
    if not isinstance(hashes, dict) or hashes.get("schema") != HASHES_SCHEMA or not isinstance(hashes.get("files"), list):
        findings.append(_finding("cre_hashes_file_invalid", "hashes.json must use cartridgeflow.release_hashes.v1 with a files array.", path="hashes.json"))
        return public_contracts

    entries: dict[str, dict] = {}
    for index, item in enumerate(hashes["files"]):
        path = f"hashes.json.files[{index}]"
        if not isinstance(item, dict):
            findings.append(_finding("cre_hash_entry_invalid", "hash entry must be an object.", path=path))
            continue
        file_path = str(item.get("path") or "")
        if not _safe_path(file_path) or file_path in _CONTROL_FILES or file_path.startswith("signatures/"):
            findings.append(_finding("cre_hash_entry_path_invalid", "hash entry path must be a safe non-control file path.", path=f"{path}.path"))
            continue
        if file_path in entries:
            findings.append(_finding("cre_hash_entry_duplicate", "hash entry paths must be unique.", path=f"{path}.path"))
            continue
        if not _SHA256.fullmatch(str(item.get("sha256") or "")) or not isinstance(item.get("size"), int) or item["size"] < 0:
            findings.append(_finding("cre_hash_entry_invalid", "hash entry requires sha256 and non-negative size.", path=path))
            continue
        entries[file_path] = item

    expected_public = release.get("public_contracts") if isinstance(release.get("public_contracts"), dict) else {}
    for name in ("experience", "delivery"):
        item = expected_public.get(name) if isinstance(expected_public.get(name), dict) else {}
        file_path = item.get("path")
        entry = entries.get(file_path)
        if not entry:
            findings.append(_finding("cre_public_contract_unlisted", f"public {name} contract must be listed in hashes.json.", path=str(file_path or "public")))
        elif entry.get("sha256") != item.get("digest"):
            findings.append(_finding("cre_public_contract_digest_mismatch", f"public {name} digest must match hashes.json.", path=str(file_path)))

    for file_path, entry in entries.items():
        content = normalized.get(file_path)
        if content is None:
            findings.append(_finding("cre_hashed_file_missing", "hashes.json references a missing bundle file.", path=file_path))
            continue
        if entry["size"] != len(content) or entry["sha256"] != _digest(content):
            findings.append(_finding("cre_hashed_file_mismatch", "bundle file does not match declared size or SHA-256.", path=file_path))

    payload_entries = [item for path, item in entries.items() if path.startswith("payload/")]
    if not payload_entries or "payload/manifest.json" not in entries:
        findings.append(_finding("cre_payload_files_missing", "hashes.json must cover payload/manifest.json and payload content.", path="payload"))
    else:
        payload = release.get("payload") if isinstance(release.get("payload"), dict) else {}
        if payload.get("digest") != _payload_digest(payload_entries):
            findings.append(_finding("cre_payload_digest_mismatch", "release.payload.digest must match the canonical payload file list.", path="release.payload.digest"))

    allowed = _CONTROL_FILES | signature_paths | set(entries)
    for file_path in normalized:
        if file_path not in allowed:
            findings.append(_finding("cre_bundle_file_unlisted", "bundle contains a file that is not covered by hashes.json or a control file.", path=file_path))
    for signature_path in signature_paths:
        if signature_path not in normalized:
            findings.append(_finding("cre_signature_file_missing", "declared signature file is absent from the bundle.", path=signature_path))
    return public_contracts


def _read_bundle_public_contracts(normalized: Mapping[str, bytes], findings: list[dict]) -> dict[str, dict]:
    contracts: dict[str, dict] = {}
    for name, path in {
        "experience": "public/experience.json",
        "delivery": "public/delivery.contract.json",
    }.items():
        raw = normalized.get(path)
        if raw is None:
            findings.append(_finding("cre_public_contract_file_missing", "bundle is missing a required public contract file.", path=path))
            continue
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            findings.append(_finding("cre_public_contract_file_invalid", "public contract file must be a UTF-8 JSON object.", path=path))
            continue
        if not isinstance(value, dict):
            findings.append(_finding("cre_public_contract_file_invalid", "public contract file must be a JSON object.", path=path))
            continue
        contracts[name] = value
    return contracts


def _validate_bound_public_contracts(
    bundle_contracts: Mapping[str, dict],
    supplied_experience: dict | None,
    supplied_delivery: dict | None,
    findings: list[dict],
) -> None:
    for name, validator, supplied in (
        ("experience", _validate_experience, supplied_experience),
        ("delivery", _validate_delivery, supplied_delivery),
    ):
        actual = bundle_contracts.get(name)
        validator(actual or {}, findings)
        if supplied is not None and actual is not None and supplied != actual:
            findings.append(_finding(
                "cre_public_contract_object_mismatch",
                "caller-supplied public contract does not match the contract bytes in the bundle.",
                path=f"public/{'experience.json' if name == 'experience' else 'delivery.contract.json'}",
            ))


def _find_public_leaks(value, path: str, findings: list[dict]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).casefold() in _PUBLIC_FORBIDDEN_KEYS:
                findings.append(_finding("cre_public_contract_leaks_internal", "public contract contains an internal execution or connection field.", path=child_path))
            _find_public_leaks(child, child_path, findings)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _find_public_leaks(child, f"{path}[{index}]", findings)


def _require_id(value, field: str, findings: list[dict], parent: str) -> str:
    text = str(value or "")
    if not _ID.fullmatch(text):
        findings.append(_finding("cre_release_identity_invalid", f"{parent}.{field} must be a stable identifier.", path=f"{parent}.{field}"))
        return ""
    return text


def _require_digest(value, path: str, findings: list[dict]) -> str:
    text = str(value or "")
    if not _SHA256.fullmatch(text):
        findings.append(_finding("cre_digest_invalid", f"{path} must use sha256:<64 lowercase hex>.", path=path))
        return ""
    return text


def _valid_contract(value: dict) -> bool:
    return _nonempty(value.get("id")) and _nonempty(value.get("version"))


def _safe_path(value: str) -> bool:
    return bool(_SAFE_PATH.fullmatch(value) and not value.startswith("/") and "//" not in value and "/../" not in f"/{value}/" and not value.endswith("/.."))


def _unique_ids(value) -> bool:
    values = _string_list(value)
    return isinstance(value, list) and len(values) == len(value) and len(set(values)) == len(values) and all(_ID.fullmatch(item) for item in values)


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _payload_digest(entries: list[dict]) -> str:
    canonical = [
        {"path": item["path"], "sha256": item["sha256"], "size": item["size"]}
        for item in sorted(entries, key=lambda item: item["path"])
    ]
    encoded = json.dumps(canonical, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _digest(encoded)


def _finding(code: str, message: str, *, path: str) -> dict:
    return {"severity": "blocker", "code": code, "message": message, "path": path}
