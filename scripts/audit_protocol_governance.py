from __future__ import annotations

import configparser
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import (
    DataContractError,
    ProtocolArtifactStore,
    ProtocolKnowledgeRegistry,
    ProtocolKnowledgeRegistryError,
    UNIFIED_PROTOCOLS,
    build_data_contract_support_report,
    build_unified_protocol_support_report,
    load_base_implementation,
    load_protocol_registry_lock,
    load_protocol_release_catalog,
    resolve_protocol_registry,
)
from core.protocol.base_manifest import supports_protocol_release, supports_subprotocol_release


def audit(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    root = Path(root).resolve()
    if (root / "protocol").exists():
        errors.append("product repository must consume the compiled registry instead of a protocol/ source directory")

    try:
        lock = load_protocol_registry_lock(root)
        registry_path = resolve_protocol_registry(root)
        artifacts = ProtocolArtifactStore(root)
        catalog = load_protocol_release_catalog(root)
    except (ProtocolKnowledgeRegistryError, ValueError) as exc:
        return [f"compiled protocol registry is unavailable: {exc}"]

    _audit_protocol_source_mount(root, lock, errors)
    _audit_registry_lock(registry_path, lock, errors)
    _audit_release_catalog(root, artifacts, catalog, errors)
    _audit_product_bindings(root, catalog, errors)
    try:
        support_report = build_data_contract_support_report(root)
    except (DataContractError, ProtocolKnowledgeRegistryError, OSError, ValueError) as exc:
        errors.append(f"data contract support cannot be audited: {exc}")
    else:
        errors.extend(
            f"data contract support {item['code']}: {item['message']}"
            for item in support_report["findings"]
        )
    try:
        unified_report = build_unified_protocol_support_report(root)
    except (DataContractError, ProtocolKnowledgeRegistryError, OSError, ValueError) as exc:
        errors.append(f"unified protocol support cannot be audited: {exc}")
    else:
        errors.extend(
            f"unified protocol support {item['code']}: {item['message']}"
            for item in unified_report["findings"]
        )
    return errors


def _audit_protocol_source_mount(root: Path, lock: dict, errors: list[str]) -> None:
    config_path = root / ".gitmodules"
    config = configparser.ConfigParser()
    try:
        if not config.read(config_path, encoding="utf-8"):
            errors.append("protocol source submodule configuration is missing")
            return
    except configparser.Error as exc:
        errors.append(f"protocol source submodule configuration is invalid: {exc}")
        return

    section = 'submodule "protocol-source"'
    expected_url = "https://github.com/Holosukiyaa/cartridgeflow-protocols.git"
    if not config.has_section(section):
        errors.append("protocol-source must be declared as a Git submodule")
        return
    if config.get(section, "path", fallback="") != "protocol-source":
        errors.append("protocol source submodule must be mounted at protocol-source/")
    if config.get(section, "url", fallback="") != expected_url:
        errors.append("protocol source submodule must use the authoritative GitHub repository")

    checkout = root / "protocol-source"
    source_database = checkout / "protocol-source.sqlite"
    if not source_database.is_file():
        errors.append(
            "protocol source submodule is not initialized; run 'git submodule update --init protocol-source'"
        )
        return
    source_lock = lock.get("source_database") if isinstance(lock.get("source_database"), dict) else {}
    actual_digest = hashlib.sha256(source_database.read_bytes()).hexdigest()
    if actual_digest != source_lock.get("database_sha256"):
        errors.append("embedded protocol source database SHA-256 does not match the product lock")

    try:
        result = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        errors.append(f"embedded protocol source commit cannot be inspected: {exc}")
        return
    repository = lock.get("repository") if isinstance(lock.get("repository"), dict) else {}
    if result.returncode:
        errors.append("embedded protocol source is not a valid Git checkout")
    elif result.stdout.strip() != repository.get("commit"):
        errors.append("embedded protocol source commit does not match the product lock")


def _audit_registry_lock(registry_path: Path, lock: dict, errors: list[str]) -> None:
    if lock.get("schema") != "cartridgeflow.product_protocol_registry_lock.v3":
        errors.append("protocol registry lock has an unknown schema")
    if lock.get("runtime_source_id") != "current":
        errors.append("protocol registry lock must keep current as the runtime source")
    repository = lock.get("repository") if isinstance(lock.get("repository"), dict) else {}
    source_database = (
        lock.get("source_database")
        if isinstance(lock.get("source_database"), dict)
        else {}
    )
    source_items = lock.get("sources") if isinstance(lock.get("sources"), list) else []
    source_locks = {
        str(item.get("source_id")): item
        for item in source_items
        if isinstance(item, dict) and item.get("source_id")
    }
    registry_lock = lock.get("registry") if isinstance(lock.get("registry"), dict) else {}
    if repository.get("url") != "https://github.com/Holosukiyaa/cartridgeflow-protocols.git":
        errors.append("protocol registry lock must name the authoritative source repository")
    if not re.fullmatch(r"[0-9a-f]{40}", str(repository.get("commit") or "")):
        errors.append("protocol registry lock requires a full Git commit SHA")
    if source_database.get("path") != "protocol-source.sqlite":
        errors.append("protocol registry lock must name the authoritative SQLite source")
    if not re.fullmatch(
        r"[0-9a-f]{64}", str(source_database.get("database_sha256") or "")
    ):
        errors.append("protocol registry lock requires the source database SHA-256")
    if not re.fullmatch(
        r"[0-9a-f]{64}", str(source_database.get("logical_digest") or "")
    ):
        errors.append("protocol registry lock requires the source database logical digest")
    expected_sources = {"current", "temp-runtime", "unified"}
    if set(source_locks) != expected_sources:
        errors.append("protocol registry lock must contain unified and both legacy sources")

    expected_database_digest = str(registry_lock.get("database_sha256") or "")
    actual_database_digest = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    if actual_database_digest != expected_database_digest:
        errors.append("compiled protocol registry SHA-256 does not match its lock")

    try:
        with ProtocolKnowledgeRegistry(registry_path) as registry:
            if registry.connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                errors.append("compiled protocol registry integrity check failed")
            if registry.connection.execute("PRAGMA foreign_key_check").fetchall():
                errors.append("compiled protocol registry contains foreign-key violations")
            summary = registry.summary()
            if summary.get("registry_role") != "product_snapshot":
                errors.append("compiled protocol registry must be a product snapshot")
            if summary.get("source_registry_digest") != source_database.get("logical_digest"):
                errors.append("compiled registry does not match its authoritative source digest")
            if summary.get("schema_version") != str(registry_lock.get("schema_version")):
                errors.append("compiled protocol registry schema version does not match its lock")
            if summary.get("registry_digest") != registry_lock.get("logical_digest"):
                errors.append("compiled protocol registry logical digest does not match its lock")
            sources = registry.connection.execute(
                "SELECT source_id, manifest_digest, source_digest FROM registry_source"
            ).fetchall()
            database_sources = {row["source_id"]: row for row in sources}
            if set(database_sources) != expected_sources:
                errors.append("product registry must contain unified and both legacy sources")
            for source_id in expected_sources:
                row = database_sources.get(source_id)
                source_lock = source_locks.get(source_id, {})
                if row is not None and (
                    row["manifest_digest"] != source_lock.get("manifest_digest")
                    or row["source_digest"] != source_lock.get("source_digest")
                ):
                    errors.append(f"compiled {source_id} source digests do not match the product lock")
            for finding in registry.findings(severity="blocker"):
                if finding["finding_type"] != "protocol_identity_collision":
                    errors.append(
                        f"compiled protocol registry {finding['finding_type']}: {finding['message']}"
                    )
    except (OSError, ProtocolKnowledgeRegistryError) as exc:
        errors.append(f"compiled protocol registry cannot be audited: {exc}")


def _audit_release_catalog(root: Path, artifacts: ProtocolArtifactStore, catalog, errors: list[str]) -> None:
    known = {(item["id"], item["version"]) for item in catalog.releases}
    published = {
        (item["id"], item["version"])
        for item in catalog.releases
        if item["lifecycle"] in {"current", "supported_previous"}
    }
    published.update(
        (item["id"], item["version"])
        for item in catalog.release_envelopes
        if item.get("implementation_status") in {"partial", "supported"}
    )
    published.update((protocol_id, version) for _layer, protocol_id, version, _adapter in UNIFIED_PROTOCOLS)

    for release in catalog.releases:
        label = f"{release['id']}@{release['version']}"
        if release["lifecycle"] in {"current", "supported_previous"} and not release.get("runtime_adapter"):
            errors.append(f"{label}: published releases must declare a runtime_adapter")
        registry = _artifact_json(artifacts, release["registry"], errors)
        if registry and (str(registry.get("id")), str(registry.get("version"))) != (release["id"], release["version"]):
            errors.append(f"{label}: registry snapshot identity does not match release manifest")
        for field in ("runtime_adapter", "features"):
            if field in release and registry and registry.get(field) != release[field]:
                errors.append(f"{label}: release manifest {field} does not match registry {field}")
        for subprotocol in release.get("trusted_subprotocols") or []:
            sub_label = f"{subprotocol.get('id')}@{subprotocol.get('version')}"
            sub_registry = _artifact_json(artifacts, str(subprotocol.get("registry") or ""), errors)
            hosts = sub_registry.get("host_protocols") if sub_registry else []
            if not any(
                isinstance(host, dict)
                and str(host.get("id")) == release["id"]
                and str(host.get("version")) == release["version"]
                for host in hosts or []
            ):
                errors.append(f"{label}: trusted subprotocol {sub_label} does not declare this host release")
        for field, registry_field in (("profiles", "profiles_file"), ("capabilities", "capabilities_file")):
            value = release.get(field)
            if not isinstance(value, str) or not artifacts.exists(value):
                errors.append(f"{label}: {field} snapshot is missing")
            elif registry and registry.get(registry_field) != value:
                errors.append(f"{label}: release manifest {field} does not match registry {registry_field}")
        document = release.get("document")
        if document and not artifacts.exists(document):
            errors.append(f"{label}: protocol document is missing: {document}")
        elif document and Path(document).parent != Path("protocol/flow-authoring") / release["version"]:
            errors.append(f"{label}: protocol document must live under protocol/flow-authoring/{release['version']}/")

    for release in catalog.release_envelopes:
        label = f"{release['id']}@{release['version']}"
        registry = _artifact_json(artifacts, release["registry"], errors)
        if registry and (str(registry.get("id")), str(registry.get("version"))) != (release["id"], release["version"]):
            errors.append(f"{label}: registry snapshot identity does not match release manifest")
        for field, registry_field in (("profiles", "profiles_file"), ("capabilities", "capabilities_file")):
            value = release.get(field)
            if not isinstance(value, str) or not artifacts.exists(value):
                errors.append(f"{label}: {field} snapshot is missing")
            elif registry and registry.get(registry_field) != value:
                errors.append(f"{label}: release manifest {field} does not match registry {registry_field}")
        if not artifacts.exists(release["document"]):
            errors.append(f"{label}: protocol document is missing: {release['document']}")

    history = _artifact_json(artifacts, "governance/protocol_history.json", errors)
    legacy = {
        (item["id"], item["version"]): item.get("migration_target")
        for item in catalog.releases
        if item["lifecycle"] == "recognized_legacy"
    }
    history_legacy = {
        (str(item.get("id")), str(item.get("version"))): item.get("migration_target")
        for item in (history or {}).get("protocols", [])
        if isinstance(item, dict)
    }
    if history_legacy != legacy:
        errors.append("governance protocol history must mirror recognized legacy catalog releases")

    base_contract = catalog.data["base_contract"]
    base_version = str(base_contract["version"])
    base_registry = _artifact_json(artifacts, f"base/{base_version}/release.json", errors)
    if base_registry and base_registry.get("document") != f"protocol/base/{base_version}/specification.md":
        errors.append(f"{base_contract['id']}@{base_version} has an invalid document path")

    base = load_base_implementation(root)
    base_supported = {(str(item.get("id")), str(item.get("version"))) for item in base.get("supported_protocols", [])}
    unknown_base = base_supported - published
    if unknown_base:
        errors.append(f"Base declares protocols that are not published by release manifest: {sorted(unknown_base)}")
    default = catalog.data["default_for_new_flows"]
    default_key = (str(default["id"]), str(default["version"]))
    default_release = catalog.get(*default_key)
    if not supports_protocol_release(base, default_release):
        errors.append(f"Base must support default release {default_key[0]}@{default_key[1]}")
    for subprotocol in (default_release or {}).get("trusted_subprotocols") or []:
        if subprotocol.get("required") and not supports_subprotocol_release(
            base,
            str(subprotocol.get("id") or ""),
            str(subprotocol.get("version") or ""),
            default_key[0],
            default_key[1],
        ):
            errors.append(
                f"Base must support required trusted subprotocol {subprotocol.get('id')}@{subprotocol.get('version')}"
            )

    header = "\n".join(artifacts.read_text("governance/GOVERNANCE.md").splitlines()[:24])
    if "CF-FARP@1.1" not in header:
        errors.append("governance snapshot must present the CF-FARP@1.1 baseline in its header")


def _audit_product_bindings(root: Path, catalog, errors: list[str]) -> None:
    _require_text(root / "src/core/protocol/capability_registry.py", "ProtocolArtifactStore", errors)
    _require_text(root / "src/core/lab/dev_flow.py", "self.default_protocol_version", errors)
    _require_text(root / "src/backend/main.py", "protocol_catalog", errors)
    _require_text(root / "src/core/studio/creator_runtime_bridge.py", 'CREATOR_PACKAGE_PROTOCOL = {"id": "CF-FARP", "version": "1.6"}', errors)
    _require_text(root / "src/intent-studio/src/pages/intent-studio/IntentStudio.tsx", "packageCreatorProject", errors)
    for document in ("AGENT.md", "README.md"):
        _require_text(root / document, "protocol-registry", errors)

    known = {(item["id"], item["version"]) for item in catalog.releases}
    for path in _project_text_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for version in re.findall(r"CF-FARP@(\d+\.\d+)", text):
            if ("CF-FARP", version) not in known:
                errors.append(f"{path.relative_to(root)} references unregistered CF-FARP@{version}")


def _artifact_json(store: ProtocolArtifactStore, path: str, errors: list[str]) -> dict:
    try:
        return store.read_json(path)
    except (ProtocolKnowledgeRegistryError, ValueError) as exc:
        errors.append(f"protocol artifact {path} is unavailable: {exc}")
        return {}


def _require_text(path: Path, expected: str, errors: list[str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path.relative_to(ROOT)} cannot be read: {exc}")
        return
    if expected not in text:
        errors.append(f"{path.relative_to(ROOT)} must reference {expected}")


def _project_text_files(root: Path):
    ignored = {".git", ".data", "node_modules", "dist", "__pycache__"}
    extensions = {".py", ".ts", ".tsx", ".json", ".md"}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in extensions or any(part in ignored for part in path.parts):
            continue
        yield path


def main() -> int:
    errors = audit()
    if errors:
        print("Protocol governance audit failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Protocol governance audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
