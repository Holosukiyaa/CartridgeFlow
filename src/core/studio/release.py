"""Release helpers for local resource bindings and package history."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from core.data_paths import PACKAGES_DIR
from core.protocol.clean_distribution import CleanDistributionProjectionError, CleanDistributionProjector
from core.protocol.release_builder import ReleaseBuildError, build_release_archive, inspect_release_archive
from core.protocol.release_envelope import RELEASE_SCHEMA_V2, build_release_envelope_report
from core.protocol.release_signing import (
    ReleaseSigningIdentity,
    ensure_development_signing_identity,
    trusted_public_keys,
)
from core.studio.resource_resolver import resolve_cartridge_resources


class ProductionReleaseError(ValueError):
    """Raised when a production handoff cannot be published safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_PRESENTATION_PATHS = {
    "settings": Path("contracts/settings.contract.json"),
    "settings_bindings": Path("settings/bindings.json"),
    "ui": Path("contracts/ui.contract.json"),
}


def build_binding_descriptor(manifest: dict, resources: dict, configured_keys: set[str] | None = None) -> dict:
    return resolve_cartridge_resources(manifest, resources, configured_keys)["descriptor"]


def resource_preflight(manifest: dict, resources: dict, configured_keys: set[str]) -> dict:
    return resolve_cartridge_resources(manifest, resources, configured_keys)


def release_archive_inputs(manifest: dict) -> dict:
    """Derive public CF-CRE contracts from a cartridge without copying private runtime data."""
    source = manifest.get("release_envelope") if isinstance(manifest.get("release_envelope"), dict) else {}
    publisher = manifest.get("publisher") if isinstance(manifest.get("publisher"), dict) else {}
    publisher_id = str(source.get("publisher_id") or publisher.get("id") or "local")
    inputs = []
    for item in manifest.get("inputs") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        inputs.append({
            "id": str(item["id"]),
            "label": str(item.get("label") or item["id"]),
            "type": _public_input_type(item.get("type")),
            "required": item.get("required") is not False,
        })
    outputs = [item for item in (manifest.get("outputs") or []) if isinstance(item, dict) and item.get("id")]
    primary_output = str((manifest.get("delivery") or {}).get("primary_output") or "")
    primary = next((item for item in outputs if str(item.get("id")) == primary_output), outputs[0] if outputs else None)
    artifacts = [{
        "id": str(primary.get("id") or "delivery") if primary else "delivery",
        "label": str(primary.get("label") or primary.get("id") or "Delivery") if primary else "Delivery",
        "mime_types": [_public_mime_type(primary.get("type"))] if primary else ["application/octet-stream"],
    }]
    experience = {
        "schema": "cartridgeflow.cartridge_experience.v1",
        "product": {
            "name": str(manifest.get("name") or manifest.get("id") or "Cartridge"),
            "category": str(manifest.get("category") or manifest.get("kind") or "cartridge"),
        },
        "inputs": inputs,
        "stages": [
            {"id": "prepare", "label": "Prepare"},
            {"id": "deliver", "label": "Deliver"},
        ],
    }
    delivery = {
        "schema": "cartridgeflow.delivery_contract.v1",
        "primary_artifacts": artifacts,
        "attachments": [],
        "revision": {"mode": "new_run"},
        "delivery_states": ["produced", "delivered", "failed"],
    }
    return {
        "publisher_id": publisher_id,
        "experience": experience,
        "delivery": delivery,
        "placement": str(source.get("placement") or "local"),
        "required_capabilities": _stable_ids(source.get("required_capabilities")),
        "required_permissions": _stable_ids(source.get("required_permissions")),
    }


def load_release_presentation_contracts(package_path: str | Path) -> dict[str, dict]:
    """Load the three explicit CF-CRE@2 presentation contracts from a package."""
    root = Path(package_path).resolve()
    if not root.is_dir():
        raise ProductionReleaseError("release_package_missing", "Cartridge package path was not found.")
    result: dict[str, dict] = {}
    for name, relative in _PRESENTATION_PATHS.items():
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise ProductionReleaseError(
                "release_presentation_contract_missing",
                f"CF-CRE@2 requires {relative.as_posix()}.",
            )
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProductionReleaseError(
                "release_presentation_contract_invalid",
                f"{relative.as_posix()} must be a readable UTF-8 JSON object.",
            ) from exc
        if not isinstance(value, dict):
            raise ProductionReleaseError(
                "release_presentation_contract_invalid",
                f"{relative.as_posix()} must contain a JSON object.",
            )
        result[name] = value
    return result


def build_production_release_handoff(
    package_path: str | Path,
    output_file: str | Path,
    *,
    project_root: str | Path,
    requested_by: str = "local-workbench",
    target: str = "desktop-runner",
    rollback: str = "enabled",
    request_id: str | None = None,
    plan_id: str | None = None,
    requested_at: str | None = None,
    publisher_id: str | None = None,
    signing_identity: ReleaseSigningIdentity | None = None,
    trusted_keys: Mapping[str, str] | None = None,
) -> dict:
    """Build, verify, project, and atomically publish one production handoff."""
    source = Path(package_path).resolve()
    output = Path(output_file).resolve()
    root = Path(project_root).resolve()
    manifest_path = source / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionReleaseError(
            "release_manifest_invalid",
            "Production release requires a readable UTF-8 manifest.json object.",
        ) from exc
    if not isinstance(manifest, dict):
        raise ProductionReleaseError(
            "release_manifest_invalid",
            "Production release manifest.json must contain an object.",
        )
    presentation = load_release_presentation_contracts(source)
    inputs = release_archive_inputs(manifest)
    actual_publisher = str(publisher_id or inputs["publisher_id"]).strip()
    actual_requested_by = str(requested_by or "").strip()
    actual_target = str(target or "").strip()
    if not actual_publisher:
        raise ProductionReleaseError("release_signing_failed", "Release publisher must not be empty.")
    if not actual_requested_by:
        raise ProductionReleaseError("installation_request_invalid", "Installation requester must not be empty.")
    if not actual_target:
        raise ProductionReleaseError("installation_request_invalid", "Installation target must not be empty.")

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            prefix=f".{output.stem}-",
            suffix=".pending",
            dir=output.parent,
            delete=False,
        )
    except OSError as exc:
        raise ProductionReleaseError(
            "release_publish_failed",
            "Production release staging file could not be created.",
        ) from exc
    pending = Path(handle.name)
    handle.close()
    try:
        try:
            identity = signing_identity or ensure_development_signing_identity(root, actual_publisher)
        except (OSError, ValueError) as exc:
            raise ProductionReleaseError("release_signing_failed", str(exc)) from exc
        try:
            built = build_release_archive(
                source,
                pending,
                publisher_id=actual_publisher,
                experience=inputs["experience"],
                delivery=inputs["delivery"],
                settings=presentation["settings"],
                settings_bindings=presentation["settings_bindings"],
                ui=presentation["ui"],
                release_envelope_version=2,
                placement=inputs["placement"],
                required_capabilities=inputs["required_capabilities"],
                required_permissions=inputs["required_permissions"],
                signing_identity=identity,
            )
            trust = dict(trusted_keys) if trusted_keys is not None else trusted_public_keys(root)
            inspection = inspect_release_archive(pending, trusted_keys=trust)
        except (ReleaseBuildError, OSError, ValueError) as exc:
            raise ProductionReleaseError("release_build_failed", str(exc)) from exc
        protocol = str((inspection.get("report") or {}).get("protocol") or "")
        if protocol != "CF-CRE@2" or not inspection.get("activation_allowed"):
            raise ProductionReleaseError(
                "release_activation_blocked",
                "CF-CRE@2 package failed signature trust or integrity activation checks.",
            )
        try:
            archive_contracts = clean_release_contracts(
                pending,
                trusted_keys=trust,
                project_root=root,
            )
            projector = CleanDistributionProjector(root)
            installation_request, installation_plan = projector.installation_request(
                {
                    "revision": 1,
                    "package_id": str(manifest.get("id") or ""),
                    "target": actual_target,
                    "plan_id": str(plan_id or f"install-{uuid.uuid4().hex}"),
                    "rollback": rollback,
                    "request_id": str(request_id or f"request-{uuid.uuid4().hex}"),
                    "requested_at": requested_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "requested_by": actual_requested_by,
                }
            )
        except (CleanDistributionProjectionError, ValueError) as exc:
            raise ProductionReleaseError("clean_distribution_projection_failed", str(exc)) from exc
        try:
            os.replace(pending, output)
        except OSError as exc:
            raise ProductionReleaseError("release_publish_failed", "Verified release could not be published atomically.") from exc
        return {
            "archive": str(output),
            "release_id": built["release_id"],
            "protocol": protocol,
            "activation_allowed": True,
            "signature": inspection.get("signature"),
            "archive_contract_ids": [item["contract_id"] for item in archive_contracts],
            "installation_request": installation_request,
            "installation_plan": installation_plan,
        }
    finally:
        pending.unlink(missing_ok=True)


def release_contract_preview(manifest: dict) -> dict:
    """Validate the public CRE shape before the archive is generated."""
    inputs = release_archive_inputs(manifest)
    base_contract = manifest.get("base_contract") if isinstance(manifest.get("base_contract"), dict) else {}
    runtime_contract = manifest.get("runtime_contract") if isinstance(manifest.get("runtime_contract"), dict) else {}
    digest = "sha256:" + "0" * 64
    cartridge_id = str(manifest.get("id") or "")
    version = str(manifest.get("version") or "")
    release = {
        "schema": "cartridgeflow.release_envelope.v1",
        "release": {"publisher_id": inputs["publisher_id"], "cartridge_id": cartridge_id, "version": version},
        "release_id": f"{inputs['publisher_id']}:{cartridge_id}@{version}+{digest}",
        "runtime": {
            "base_contract": {"id": str(base_contract.get("id") or ""), "version": str(base_contract.get("version") or "")},
            "flow_contract": {"id": str(runtime_contract.get("protocol") or ""), "version": str(runtime_contract.get("protocol_version") or "")},
            "min_runner_version": "0.3.0",
        },
        "execution": {
            "placement": inputs["placement"],
            "required_capabilities": inputs["required_capabilities"],
            "required_permissions": inputs["required_permissions"],
        },
        "public_contracts": {
            "experience": {"path": "public/experience.json", "digest": digest},
            "delivery": {"path": "public/delivery.contract.json", "digest": digest},
        },
        "payload": {"path": "payload", "digest": digest},
        "integrity": {"hashes_path": "hashes.json", "content_digest": digest},
        "signatures": [{"role": "publisher", "key_id": f"{inputs['publisher_id']}.development", "algorithm": "ed25519", "path": "signatures/publisher.ed25519.json"}],
    }
    report = build_release_envelope_report(release, inputs["experience"], inputs["delivery"])
    return {"status": "ready" if report.get("ok") else "blocked", "inputs": inputs, "report": report}


def package_history(root: str | Path) -> list[dict]:
    package_dir = Path(root) / PACKAGES_DIR
    if not package_dir.is_dir():
        return []
    result = []
    for path in sorted([*package_dir.glob("*.cartridge.zip"), *package_dir.glob("*.cf-cre.zip")]):
        manifest = {}
        mode = "unknown"
        protocol = "legacy"
        release_id = ""
        try:
            with zipfile.ZipFile(path) as archive:
                if "release.manifest.json" in archive.namelist():
                    release = json.loads(archive.read("release.manifest.json").decode("utf-8"))
                    manifest = json.loads(archive.read("payload/manifest.json").decode("utf-8"))
                    protocol = "CF-CRE@2" if release.get("schema") == RELEASE_SCHEMA_V2 else "CF-CRE@1"
                    release_id = str(release.get("release_id") or "")
                    mode = "production"
                else:
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                if "package.metadata.json" in archive.namelist():
                    metadata = json.loads(archive.read("package.metadata.json").decode("utf-8"))
                    mode = metadata.get("package_mode") or "unknown"
                elif "package.compatibility.json" in archive.namelist():
                    mode = "dev"
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
            manifest = {}
        modified = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        result.append({
            "filename": path.name,
            "url": f"/packages/{path.name}",
            "size": path.stat().st_size,
            "modified_at": modified,
            "cartridge_id": manifest.get("id") or "",
            "name": manifest.get("name") or path.stem,
            "version": manifest.get("version") or "",
            "package_mode": mode,
            "protocol": protocol,
            "release_id": release_id,
        })
    return sorted(result, key=lambda item: item["modified_at"], reverse=True)


def clean_release_contracts(
    archive_file: str | Path,
    *,
    trusted_keys: Mapping[str, str] | None = None,
    scope: str = "workspace",
    delivery_mode: str = "download",
    registry_path: str | Path | None = None,
    project_root: str | Path | None = None,
) -> list[dict]:
    """Expose a built archive through the detachable clean-v1 Distribution adapter."""
    return CleanDistributionProjector(
        project_root,
        registry_path=registry_path,
    ).archive(
        archive_file,
        trusted_keys=trusted_keys,
        scope=scope,
        delivery_mode=delivery_mode,
    )


def _public_input_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return {
        "text": "string",
        "textarea": "string",
        "select": "enum",
        "checkbox": "boolean",
        "json": "object",
    }.get(normalized, normalized if normalized in {"string", "number", "boolean", "enum", "file", "object", "array"} else "string")


def _public_mime_type(value: object) -> str:
    return {
        "html": "text/html",
        "markdown": "text/markdown",
        "text": "text/plain",
        "json": "application/json",
    }.get(str(value or "").strip().lower(), "application/octet-stream")


def _stable_ids(value: object) -> list[str]:
    values = value if isinstance(value, list) else []
    return sorted({str(item).strip() for item in values if str(item).strip()})
