"""CF-CRE@1 archive construction and staged runtime-consumer validation.

This module deliberately stops before trust, installation, activation, or code
execution. It gives the development console and a future runtime one shared,
byte-oriented boundary for a release candidate.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

from core.studio.hygiene import scan_package_hygiene

from .release_envelope import build_release_envelope_report
from .release_catalog import load_protocol_release_catalog


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class ReleaseBuildError(ValueError):
    """Raised when a source package cannot become a CF-CRE candidate."""


def build_release_archive(
    source_package: str | Path,
    output_file: str | Path,
    *,
    publisher_id: str,
    experience: dict,
    delivery: dict,
    placement: str = "local",
    required_capabilities: list[str] | None = None,
    required_permissions: list[str] | None = None,
) -> dict:
    """Create a deterministic CF-CRE archive and verify its written bytes."""
    source = Path(source_package).resolve()
    output = Path(output_file).resolve()
    if not source.is_dir():
        raise ReleaseBuildError("source package directory does not exist")
    if output == source or source in output.parents:
        raise ReleaseBuildError("release archive must be written outside the source package")
    hygiene = scan_package_hygiene(source)
    if hygiene.get("status") != "ok":
        raise ReleaseBuildError("source package contains non-portable or sensitive files")
    manifest_path = source / "manifest.json"
    flow_path = source / "root.flow.json"
    if not manifest_path.is_file() or not flow_path.is_file():
        raise ReleaseBuildError("source package must contain manifest.json and root.flow.json")

    manifest = _read_object(manifest_path, "manifest.json")
    flow = _read_object(flow_path, "root.flow.json")
    cartridge_id = str(manifest.get("id") or "")
    version = str(manifest.get("version") or "")
    if not _ID.fullmatch(publisher_id) or not _ID.fullmatch(cartridge_id):
        raise ReleaseBuildError("publisher_id and cartridge id must be stable identifiers")
    if not _SEMVER.fullmatch(version):
        raise ReleaseBuildError("cartridge manifest version must be a semantic version")

    payload = _payload_files(source)
    payload_entries = _hash_entries(payload)
    payload_digest = _payload_digest(payload_entries)
    public = {
        "public/experience.json": _canonical_bytes(experience),
        "public/delivery.contract.json": _canonical_bytes(delivery),
    }
    bundle_content = {**payload, **public}
    hashes = {"schema": "cartridgeflow.release_hashes.v1", "files": _hash_entries(bundle_content)}
    hashes_bytes = _canonical_bytes(hashes)
    content_digest = _digest(hashes_bytes)
    flow_protocol = flow.get("protocol") if isinstance(flow.get("protocol"), dict) else {}
    base_contract = manifest.get("base_contract") if isinstance(manifest.get("base_contract"), dict) else {}
    catalog = load_protocol_release_catalog(Path(__file__).resolve().parents[3])
    default_flow_protocol = catalog.data["default_for_new_flows"]
    default_base_contract = catalog.data["base_contract"]
    release = {
        "schema": "cartridgeflow.release_envelope.v1",
        "release": {"publisher_id": publisher_id, "cartridge_id": cartridge_id, "version": version},
        "release_id": f"{publisher_id}:{cartridge_id}@{version}+{content_digest}",
        "runtime": {
            "base_contract": {"id": str(base_contract.get("id") or default_base_contract["id"]), "version": str(base_contract.get("version") or default_base_contract["version"])},
            "flow_contract": {"id": str(flow_protocol.get("id") or default_flow_protocol["id"]), "version": str(flow_protocol.get("version") or default_flow_protocol["version"])},
            "min_runner_version": "0.3.0",
        },
        "execution": {
            "placement": placement,
            "required_capabilities": sorted(set(required_capabilities or [])),
            "required_permissions": sorted(set(required_permissions or [])),
        },
        "public_contracts": {
            "experience": {"path": "public/experience.json", "digest": _digest(public["public/experience.json"])},
            "delivery": {"path": "public/delivery.contract.json", "digest": _digest(public["public/delivery.contract.json"])},
        },
        "payload": {"path": "payload", "digest": payload_digest},
        "integrity": {"hashes_path": "hashes.json", "content_digest": content_digest},
        "signatures": [{"role": "publisher", "key_id": f"{publisher_id}.demo", "algorithm": "ed25519", "path": "signatures/publisher.ed25519.json"}],
    }
    signature_metadata = {
        "schema": "cartridgeflow.release_signature_metadata.v1",
        "algorithm": "ed25519",
        "verification": "not_implemented",
        "purpose": "release-candidate-demo",
    }
    archive_files = {
        "release.manifest.json": _canonical_bytes(release),
        "hashes.json": hashes_bytes,
        "signatures/publisher.ed25519.json": _canonical_bytes(signature_metadata),
        **bundle_content,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_deterministic_zip(output, archive_files)
    inspection = inspect_release_archive(output)
    if not inspection["report"]["ok"]:
        raise ReleaseBuildError("written release archive did not pass static validation")
    return {
        "release_id": release["release_id"],
        "archive": str(output),
        "size": output.stat().st_size,
        "status": inspection["status"],
        "activation_allowed": False,
        "report": inspection["report"],
    }


def inspect_release_archive(archive_file: str | Path) -> dict:
    """Read one archive for runtime staging without extracting or activating it."""
    archive = Path(archive_file)
    findings: list[dict] = []
    try:
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            names = [info.filename for info in infos if not info.is_dir()]
            duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
            for name in duplicates:
                findings.append(_archive_finding("cre_archive_duplicate_path", "archive contains duplicate file paths", name))
            for name in names:
                if not _safe_archive_path(name):
                    findings.append(_archive_finding("cre_archive_path_invalid", "archive contains an unsafe file path", name))
            if findings:
                return _rejected_archive_report(findings)
            files = {name: zf.read(name) for name in names}
    except (OSError, zipfile.BadZipFile):
        return _rejected_archive_report([_archive_finding("cre_archive_invalid", "release archive is not a readable ZIP file", str(archive))])

    try:
        release = json.loads(files["release.manifest.json"].decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return _rejected_archive_report([_archive_finding("cre_release_manifest_file_invalid", "release.manifest.json must be a UTF-8 JSON object", "release.manifest.json")])
    experience = _load_public_json(files, "public/experience.json")
    delivery = _load_public_json(files, "public/delivery.contract.json")
    report = build_release_envelope_report(release, experience, delivery, bundle_files=files)
    return {
        "status": "validated_pending_install" if report["ok"] else "rejected",
        "activation_allowed": False,
        "report": report,
        "release": release if report["ok"] else None,
        "public_contracts": {"experience": experience, "delivery": delivery} if report["ok"] else None,
    }


def _payload_files(source: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(source.rglob("*")):
        if path.is_file():
            relative = path.relative_to(source).as_posix()
            if relative.startswith((".data/", "output/", ".playwright-cli/")):
                raise ReleaseBuildError(f"source package contains forbidden release content: {relative}")
            files[f"payload/{relative}"] = path.read_bytes()
    return files


def _hash_entries(files: dict[str, bytes]) -> list[dict]:
    return [{"path": path, "sha256": _digest(content), "size": len(content)} for path, content in sorted(files.items())]


def _payload_digest(entries: list[dict]) -> str:
    payload_entries = [entry for entry in entries if entry["path"].startswith("payload/")]
    return _digest(_canonical_bytes(payload_entries))


def _write_deterministic_zip(target: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in sorted(files.items()):
            info = zipfile.ZipInfo(path, date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, content)


def _read_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseBuildError(f"{label} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ReleaseBuildError(f"{label} must contain a JSON object")
    return value


def _load_public_json(files: dict[str, bytes], path: str) -> dict:
    try:
        value = json.loads(files[path].decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_archive_path(path: str) -> bool:
    candidate = PurePosixPath(path)
    return bool(path and not candidate.is_absolute() and ".." not in candidate.parts and not path.startswith("/") and "\\" not in path)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _archive_finding(code: str, message: str, path: str) -> dict:
    return {"severity": "blocker", "code": code, "message": message, "path": path}


def _rejected_archive_report(findings: list[dict]) -> dict:
    return {
        "status": "rejected",
        "activation_allowed": False,
        "report": {
            "schema": "cartridgeflow.release_envelope_report.v1",
            "protocol": "CF-CRE@1",
            "implementation_status": "partial",
            "ok": False,
            "status": "blocked",
            "summary": {"blocker": len(findings), "warning": 0, "info": 0},
            "findings": findings,
        },
        "release": None,
        "public_contracts": None,
    }
