"""Clean-v1 Foundation projections for implementation and proof facts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .clean_protocol import CLEAN_CONTRACT_VERSION, CLEAN_SOURCE_ID, resolve_clean_protocol_adapter
from .data_contracts import DataContractError


FOUNDATION_ADAPTER_ID = "cartridgeflow.foundation.v1"


class CleanFoundationProjectionError(DataContractError):
    """Raised when implementation or publication proof is incomplete."""


class CleanFoundationProjector:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        registry_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else None
        self.registry_path = Path(registry_path).resolve() if registry_path is not None else None
        self.adapter = resolve_clean_protocol_adapter(FOUNDATION_ADAPTER_ID)

    def implementation(
        self,
        *,
        implementation_id: str,
        supported_targets: Iterable[str],
        validator_ref: str,
        revision: int = 1,
    ) -> list[dict]:
        common = {
            "revision": _revision(revision),
            "implementation_id": _text(implementation_id, "implementation id"),
            "supported_targets": _texts(supported_targets, "supported targets"),
            "validator_ref": _text(validator_ref, "validator reference"),
        }
        return [
            self._envelope(f"cartridgeflow.foundation.{kind}", {**common, "kind": kind})
            for kind in ("implementation", "support")
        ]

    def conformance(
        self,
        *,
        result: str,
        finding_codes: Iterable[str],
        evidence_refs: Iterable[str],
        revision: int = 1,
    ) -> list[dict]:
        common = {
            "revision": _revision(revision),
            "result": result,
            "finding_codes": _texts(finding_codes, "finding codes"),
            "evidence_refs": _texts(evidence_refs, "evidence references"),
        }
        return [
            self._envelope(f"cartridgeflow.foundation.{kind}", {**common, "kind": kind})
            for kind in ("conformance-report", "finding", "evidence")
        ]

    def publication_lock(self, lock: dict, *, revision: int = 1) -> list[dict]:
        lock = _mapping(lock, "product protocol lock")
        if lock.get("schema") != "cartridgeflow.product_protocol_registry_lock.v4":
            _projection_error(
                "clean_foundation_lock_generation_invalid",
                "clean-v1 publication proof requires a v4 product protocol lock",
            )
        if lock.get("runtime_source_id") != CLEAN_SOURCE_ID:
            _projection_error(
                "clean_foundation_lock_source_invalid",
                f"clean-v1 publication proof requires runtime source {CLEAN_SOURCE_ID}",
            )
        sources = lock.get("sources")
        if not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], dict):
            _projection_error(
                "clean_foundation_lock_source_invalid",
                "clean-v1 publication proof requires exactly one locked source",
            )
        source = sources[0]
        if source.get("source_id") != CLEAN_SOURCE_ID:
            _projection_error(
                "clean_foundation_lock_source_invalid",
                f"locked source must be {CLEAN_SOURCE_ID}",
            )
        repository = _mapping(lock.get("repository"), "protocol repository lock")
        source_database = _mapping(lock.get("source_database"), "source database lock")
        common = {
            "revision": _revision(revision),
            "source_commit": _text(repository.get("commit"), "protocol source commit"),
            "source_digest": _digest(source.get("source_digest"), "protocol source digest"),
            "database_digest": _digest(source_database.get("database_sha256"), "source database digest"),
        }
        return [
            self._envelope(f"cartridgeflow.governance.{kind}", {**common, "kind": kind})
            for kind in ("protocol-release", "registry-lock")
        ]

    def change(
        self,
        *,
        target_version: str,
        compatibility: str,
        impact: str,
        revision: int = 1,
    ) -> dict:
        return self._envelope(
            "cartridgeflow.governance.change",
            {
                "kind": "change",
                "revision": _revision(revision),
                "target_version": _semver(target_version),
                "compatibility": compatibility,
                "impact": _text(impact, "change impact"),
            },
        )

    def _envelope(self, contract_id: str, payload: dict) -> dict:
        envelope = {"contract_id": contract_id, "version": CLEAN_CONTRACT_VERSION, "payload": payload}
        self.adapter.validate(
            contract_id,
            envelope,
            root=self.root,
            registry_path=self.registry_path,
        )
        return envelope


def _mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        _projection_error("clean_foundation_source_invalid", f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        _projection_error("clean_foundation_source_invalid", f"{label} must not be empty")
    return text


def _texts(value: Iterable[str], label: str) -> list[str]:
    if isinstance(value, (str, bytes, dict)):
        _projection_error("clean_foundation_source_invalid", f"{label} must be an array")
    try:
        result = [_text(item, label) for item in value]
    except TypeError as exc:
        raise CleanFoundationProjectionError(
            "clean_foundation_source_invalid", f"{label} must be an array"
        ) from exc
    if not result:
        _projection_error("clean_foundation_source_invalid", f"{label} must not be empty")
    return result


def _revision(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        _projection_error("clean_foundation_revision_invalid", "revision must be a positive integer")
    return value


def _semver(value: Any) -> str:
    text = _text(value, "target version")
    parts = text.split(".")
    if len(parts) != 3 or any(not item.isdigit() for item in parts):
        _projection_error("clean_foundation_version_invalid", "target version must use x.y.z")
    return text


def _digest(value: Any, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        _projection_error("clean_foundation_digest_invalid", f"{label} must be a SHA-256 digest")
    return text


def _projection_error(code: str, message: str) -> None:
    raise CleanFoundationProjectionError(code, message)
