"""Clean-v1 distribution projections for verified CF-CRE release artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
import zipfile

from .clean_protocol import CLEAN_CONTRACT_VERSION, resolve_clean_protocol_adapter
from .data_contracts import DataContractError
from .release_builder import inspect_release_archive


DISTRIBUTION_ADAPTER_ID = "cartridgeflow.distribution.v1"
_PACKAGE_KINDS = ("manifest", "content-entry", "dependency-lock", "entrypoint")
_INTEGRITY_KINDS = ("manifest", "signature-payload", "verification")
_TRUST_KINDS = ("publisher", "signature", "decision")
_INSTALLATION_KINDS = ("request", "plan", "result")
_EXPOSURE_KINDS = ("experience", "delivery")


class CleanDistributionProjectionError(DataContractError):
    """Raised when a release or handoff fact cannot be projected faithfully."""


class CleanDistributionProjector:
    """Project release and installation facts without changing the CF-CRE archive."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        registry_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else None
        self.registry_path = Path(registry_path).resolve() if registry_path is not None else None
        self.adapter = resolve_clean_protocol_adapter(DISTRIBUTION_ADAPTER_ID)

    def archive(
        self,
        archive_file: str | Path,
        *,
        trusted_keys: Mapping[str, str] | None = None,
        scope: str = "workspace",
        delivery_mode: str = "download",
        revision: int = 1,
    ) -> list[dict]:
        """Project a statically valid archive; trust remains an explicit allow/deny fact."""
        archive_path = Path(archive_file).resolve()
        inspection = inspect_release_archive(archive_path, trusted_keys=trusted_keys)
        report = inspection.get("report") if isinstance(inspection.get("report"), dict) else {}
        if not report.get("ok"):
            codes = sorted(
                str(item.get("code") or "release-invalid")
                for item in report.get("findings") or []
                if isinstance(item, dict)
            )
            _projection_error(
                "clean_distribution_archive_invalid",
                f"release archive failed static validation: {', '.join(codes) or 'unknown'}",
            )
        release = _mapping(inspection.get("release"), "release manifest")
        identity = _mapping(release.get("release"), "release identity")
        package_id = _text(identity.get("cartridge_id"), "package id")
        package_version = _semver(identity.get("version"))
        release_id = _text(release.get("release_id"), "release id")
        payload = _mapping(release.get("payload"), "release payload descriptor")
        dependency_lock = _digest(payload.get("digest"), "payload digest")
        revision = _revision(revision)

        try:
            with zipfile.ZipFile(archive_path) as archive:
                hashes = json.loads(archive.read("hashes.json").decode("utf-8"))
                descriptor = next(
                    (
                        item
                        for item in release.get("signatures") or []
                        if isinstance(item, dict) and item.get("role") == "publisher"
                    ),
                    None,
                )
                descriptor = _mapping(descriptor, "publisher signature descriptor")
                signature_metadata = json.loads(
                    archive.read(_text(descriptor.get("path"), "publisher signature path")).decode("utf-8")
                )
        except (OSError, KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
            raise CleanDistributionProjectionError(
                "clean_distribution_control_file_invalid",
                "verified release control files could not be read",
            ) from exc

        hash_entries = _mapping_list(_mapping(hashes, "hash manifest").get("files"), "hash entries")
        member_digests = {
            _text(item.get("path"), "release member path"): _digest(item.get("sha256"), "release member digest")
            for item in hash_entries
        }
        members = sorted(member_digests)
        if not members:
            _projection_error("clean_distribution_members_missing", "release hash manifest has no members")
        entrypoint = "payload/root.flow.json"
        if entrypoint not in member_digests:
            _projection_error(
                "clean_distribution_entrypoint_missing",
                f"release hash manifest does not cover {entrypoint}",
            )

        result: list[dict] = []
        package_common = {
            "revision": revision,
            "package_id": package_id,
            "version": package_version,
            "members": members,
            "entrypoint": entrypoint,
            "dependency_lock": dependency_lock,
        }
        result.extend(
            self._envelope(f"cartridgeflow.package.{kind}", {**package_common, "kind": kind})
            for kind in _PACKAGE_KINDS
        )

        integrity_common = {
            "revision": revision,
            "package_id": package_id,
            "algorithm": "sha-256",
            "member_digests": member_digests,
            "signature_payload": release_id,
        }
        result.extend(
            self._envelope(f"cartridgeflow.integrity.{kind}", {**integrity_common, "kind": kind})
            for kind in _INTEGRITY_KINDS
        )

        signature_report = _mapping(inspection.get("signature"), "signature report")
        signature_value = _text(
            _mapping(signature_metadata, "signature metadata").get("signature"),
            "publisher signature",
        )
        trust_common = {
            "revision": revision,
            "publisher_id": _text(identity.get("publisher_id"), "publisher id"),
            "scope": scope,
            "signature": signature_value,
            "decision": "allow" if signature_report.get("ok") and signature_report.get("trusted") else "deny",
        }
        result.extend(
            self._envelope(f"cartridgeflow.trust.{kind}", {**trust_common, "kind": kind})
            for kind in _TRUST_KINDS
        )

        public_contracts = _mapping(inspection.get("public_contracts"), "public contracts")
        public_settings = _public_setting_ids(public_contracts)
        if not public_settings:
            _projection_error(
                "clean_distribution_public_settings_missing",
                "release exposes no public setting or input id for clean-v1",
            )
        exposure_common = {
            "revision": revision,
            "experience_id": package_id,
            "public_settings": public_settings,
            "delivery_mode": delivery_mode,
        }
        result.extend(
            self._envelope(f"cartridgeflow.exposure.{kind}", {**exposure_common, "kind": kind})
            for kind in _EXPOSURE_KINDS
        )
        return result

    def installation(self, fact: dict) -> list[dict]:
        """Build the explicit Workbench-to-DR install request, plan, and observed result."""
        fact = _mapping(fact, "installation fact")
        common = {
            "revision": _revision(fact.get("revision", 1)),
            "package_id": _text(fact.get("package_id"), "installation package id"),
            "target": _text(fact.get("target"), "installation target"),
            "plan_id": _text(fact.get("plan_id"), "installation plan id"),
            "rollback": str(fact.get("rollback") or ""),
        }
        result = []
        for kind in _INSTALLATION_KINDS:
            payload = {**common, "kind": kind}
            if kind == "request":
                payload.update(
                    {
                        "request_id": _text(fact.get("request_id"), "installation request id"),
                        "requested_at": _text(fact.get("requested_at"), "installation request time"),
                        "requested_by": _text(fact.get("requested_by"), "installation requester"),
                    }
                )
            elif kind == "result":
                payload.update(
                    {
                        "status": str(fact.get("status") or ""),
                        "message": _text(fact.get("message"), "installation result message"),
                    }
                )
            result.append(self._envelope(f"cartridgeflow.installation.{kind}", payload))
        return result

    def _envelope(self, contract_id: str, payload: dict) -> dict:
        envelope = {
            "contract_id": contract_id,
            "version": CLEAN_CONTRACT_VERSION,
            "payload": payload,
        }
        self.adapter.validate(
            contract_id,
            envelope,
            root=self.root,
            registry_path=self.registry_path,
        )
        return envelope


def _public_setting_ids(public_contracts: dict) -> list[str]:
    settings = public_contracts.get("settings")
    if isinstance(settings, dict):
        fields = settings.get("fields") if isinstance(settings.get("fields"), list) else []
        result = sorted(
            {
                _text(item.get("id"), "public setting id")
                for item in fields
                if isinstance(item, dict) and item.get("id")
            }
        )
        if result:
            return result
    experience = public_contracts.get("experience")
    if isinstance(experience, dict):
        inputs = experience.get("inputs") if isinstance(experience.get("inputs"), list) else []
        return sorted(
            {
                _text(item.get("id"), "public input id")
                for item in inputs
                if isinstance(item, dict) and item.get("id")
            }
        )
    return []


def _mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        _projection_error("clean_distribution_source_invalid", f"{label} must be an object")
    return value


def _mapping_list(value: Any, label: str) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        _projection_error("clean_distribution_source_invalid", f"{label} must contain only objects")
    return value


def _text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        _projection_error("clean_distribution_source_invalid", f"{label} must not be empty")
    return text


def _revision(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        _projection_error("clean_distribution_revision_invalid", "revision must be a positive integer")
    return value


def _semver(value: Any) -> str:
    text = _text(value, "package version")
    parts = text.split(".")
    if len(parts) != 3 or any(not item.isdigit() for item in parts):
        _projection_error("clean_distribution_version_invalid", "package version must use x.y.z")
    return text


def _digest(value: Any, label: str) -> str:
    text = _text(value, label)
    if text.startswith("sha256:"):
        text = text.removeprefix("sha256:")
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        _projection_error("clean_distribution_digest_invalid", f"{label} must be a SHA-256 digest")
    return text


def _projection_error(code: str, message: str) -> None:
    raise CleanDistributionProjectionError(code, message)
