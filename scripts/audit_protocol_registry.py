from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import (
    CLEAN_GENERATION,
    CLEAN_SOURCE_ID,
    DataContractError,
    ProtocolArtifactStore,
    ProtocolKnowledgeRegistry,
    ProtocolKnowledgeRegistryError,
    UNIFIED_PROTOCOLS,
    build_clean_protocol_support_report,
    build_data_contract_support_report,
    build_unified_protocol_support_report,
    load_base_implementation,
    load_protocol_registry_lock,
    load_protocol_release_catalog,
    load_runtime_protocol_catalog,
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
        catalog = load_protocol_release_catalog(root)
    except (ProtocolKnowledgeRegistryError, ValueError) as exc:
        return [f"compiled protocol registry is unavailable: {exc}"]

    schema = lock.get("schema")
    if schema == "cartridgeflow.product_protocol_registry_lock.v3":
        artifacts = ProtocolArtifactStore(root)
        _audit_unified_registry_lock(registry_path, lock, errors)
        _audit_release_catalog(root, artifacts, catalog, errors)
        _audit_product_bindings(root, catalog, errors, clean=False)
        _audit_support_report(
            "data contract",
            lambda: build_data_contract_support_report(root),
            errors,
        )
        _audit_support_report(
            "unified protocol",
            lambda: build_unified_protocol_support_report(root),
            errors,
        )
    elif schema == "cartridgeflow.product_protocol_registry_lock.v4":
        _audit_clean_registry_lock(root, registry_path, lock, errors)
        _audit_runtime_catalog(root, catalog, errors)
        _audit_product_bindings(root, catalog, errors, clean=True)
        _audit_support_report(
            "clean protocol",
            lambda: build_clean_protocol_support_report(root),
            errors,
        )
    else:
        errors.append("protocol registry lock has an unknown schema")
    return errors


def _audit_support_report(label: str, build, errors: list[str]) -> None:
    try:
        report = build()
    except (DataContractError, ProtocolKnowledgeRegistryError, OSError, ValueError) as exc:
        errors.append(f"{label} support cannot be audited: {exc}")
        return
    errors.extend(
        f"{label} support {item['code']}: {item['message']}"
        for item in report["findings"]
    )


def _audit_unified_registry_lock(registry_path: Path, lock: dict, errors: list[str]) -> None:
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


def _audit_clean_registry_lock(
    root: Path,
    registry_path: Path,
    lock: dict,
    errors: list[str],
) -> None:
    if lock.get("generation") != CLEAN_GENERATION:
        errors.append("clean protocol registry lock must select clean-v1")
    if lock.get("runtime_source_id") != CLEAN_SOURCE_ID:
        errors.append(f"clean protocol registry lock must select {CLEAN_SOURCE_ID}")
    repository = lock.get("repository") if isinstance(lock.get("repository"), dict) else {}
    if repository.get("url") != "https://github.com/Holosukiyaa/cartridgeflow-protocols.git":
        errors.append("protocol registry lock must name the authoritative source repository")
    if not re.fullmatch(r"[0-9a-f]{40}", str(repository.get("commit") or "")):
        errors.append("protocol registry lock requires a full Git commit SHA")

    source_database = lock.get("source_database") if isinstance(lock.get("source_database"), dict) else {}
    if source_database.get("path") != "protocol-source.sqlite":
        errors.append("protocol registry lock must name the authoritative SQLite source")
    for field in ("database_sha256", "logical_digest"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(source_database.get(field) or "")):
            errors.append(f"protocol registry lock requires source database {field}")

    source_items = lock.get("sources") if isinstance(lock.get("sources"), list) else []
    if (
        len(source_items) != 1
        or not isinstance(source_items[0], dict)
        or source_items[0].get("source_id") != CLEAN_SOURCE_ID
    ):
        errors.append(f"clean protocol registry lock must contain only {CLEAN_SOURCE_ID}")
        source_lock = {}
    else:
        source_lock = source_items[0]

    _audit_locked_file(
        root,
        lock.get("runtime_catalog"),
        "config/protocol/runtime-compatibility.json",
        "sha256",
        errors,
    )
    _audit_locked_file(
        root,
        lock.get("base"),
        "config/base/BASE_IMPLEMENTATION.json",
        "manifest_sha256",
        errors,
    )

    registry_lock = lock.get("registry") if isinstance(lock.get("registry"), dict) else {}
    if registry_lock.get("path") != "config/protocol/protocol-registry.sqlite":
        errors.append("clean protocol registry lock has an invalid registry path")
    if hashlib.sha256(registry_path.read_bytes()).hexdigest() != registry_lock.get("database_sha256"):
        errors.append("compiled protocol registry SHA-256 does not match its lock")
    try:
        with ProtocolKnowledgeRegistry(registry_path) as registry:
            if registry.connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                errors.append("compiled protocol registry integrity check failed")
            if registry.connection.execute("PRAGMA foreign_key_check").fetchall():
                errors.append("compiled protocol registry contains foreign-key violations")
            summary = registry.summary()
            expected_summary = {
                "registry_role": "product_snapshot",
                "generation": CLEAN_GENERATION,
                "source_id": CLEAN_SOURCE_ID,
                "schema_version": str(registry_lock.get("schema_version") or ""),
                "registry_digest": registry_lock.get("logical_digest"),
                "source_registry_digest": source_database.get("logical_digest"),
            }
            for field, expected in expected_summary.items():
                if summary.get(field) != expected:
                    errors.append(f"compiled clean protocol registry {field} does not match its lock")
            rows = registry.connection.execute(
                "SELECT source_id, manifest_digest, source_digest FROM registry_source"
            ).fetchall()
            if len(rows) != 1 or rows[0]["source_id"] != CLEAN_SOURCE_ID:
                errors.append(f"compiled clean registry must contain only {CLEAN_SOURCE_ID}")
            elif (
                rows[0]["manifest_digest"] != source_lock.get("manifest_digest")
                or rows[0]["source_digest"] != source_lock.get("source_digest")
            ):
                errors.append("compiled clean source digests do not match the product lock")
            for finding in registry.findings(severity="blocker"):
                errors.append(
                    f"compiled protocol registry {finding['finding_type']}: {finding['message']}"
                )
    except (OSError, ProtocolKnowledgeRegistryError) as exc:
        errors.append(f"compiled protocol registry cannot be audited: {exc}")


def _audit_locked_file(
    root: Path,
    value,
    expected_path: str,
    digest_field: str,
    errors: list[str],
) -> None:
    item = value if isinstance(value, dict) else {}
    if item.get("path") != expected_path:
        errors.append(f"protocol registry lock must bind {expected_path}")
        return
    path = root / expected_path
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        errors.append(f"locked file {expected_path} cannot be read: {exc}")
        return
    if digest != item.get(digest_field):
        errors.append(f"locked file {expected_path} SHA-256 does not match")


def _audit_release_catalog(root: Path, artifacts: ProtocolArtifactStore, catalog, errors: list[str]) -> None:
    try:
        governance_manifest = artifacts.read_json("protocol/catalog/release_manifest.json")
    except (ProtocolKnowledgeRegistryError, ValueError) as exc:
        errors.append(f"protocol release governance manifest is unavailable: {exc}")
        return
    governance_releases = {
        (str(item.get("id")), str(item.get("version"))): item
        for item in governance_manifest.get("releases") or []
        if isinstance(item, dict)
    }
    governance_envelopes = {
        (str(item.get("id")), str(item.get("version"))): item
        for item in (governance_manifest.get("release_envelopes") or {}).get("releases") or []
        if isinstance(item, dict)
    }
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
        governed = governance_releases.get((release["id"], release["version"]), {})
        if release["lifecycle"] in {"current", "supported_previous"} and not release.get("runtime_adapter"):
            errors.append(f"{label}: published releases must declare a runtime_adapter")
        registry = _artifact_json(artifacts, str(governed.get("registry") or ""), errors)
        if registry and (str(registry.get("id")), str(registry.get("version"))) != (release["id"], release["version"]):
            errors.append(f"{label}: registry snapshot identity does not match release manifest")
        for field in ("runtime_adapter", "features"):
            if field in release and registry and registry.get(field) != release[field]:
                errors.append(f"{label}: release manifest {field} does not match registry {field}")
        for subprotocol in governed.get("trusted_subprotocols") or []:
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
            value = governed.get(field)
            if not isinstance(value, str) or not artifacts.exists(value):
                errors.append(f"{label}: {field} snapshot is missing")
            elif registry and registry.get(registry_field) != value:
                errors.append(f"{label}: release manifest {field} does not match registry {registry_field}")
        document = governed.get("document")
        if document and not artifacts.exists(document):
            errors.append(f"{label}: protocol document is missing: {document}")
        elif document and Path(document).parent != Path("protocol/flow-authoring") / release["version"]:
            errors.append(f"{label}: protocol document must live under protocol/flow-authoring/{release['version']}/")

    for release in catalog.release_envelopes:
        label = f"{release['id']}@{release['version']}"
        governed = governance_envelopes.get((release["id"], release["version"]), {})
        registry = _artifact_json(artifacts, str(governed.get("registry") or ""), errors)
        if registry and (str(registry.get("id")), str(registry.get("version"))) != (release["id"], release["version"]):
            errors.append(f"{label}: registry snapshot identity does not match release manifest")
        for field, registry_field in (("profiles", "profiles_file"), ("capabilities", "capabilities_file")):
            value = governed.get(field)
            if not isinstance(value, str) or not artifacts.exists(value):
                errors.append(f"{label}: {field} snapshot is missing")
            elif registry and registry.get(registry_field) != value:
                errors.append(f"{label}: release manifest {field} does not match registry {registry_field}")
        document = str(governed.get("document") or "")
        if not artifacts.exists(document):
            errors.append(f"{label}: protocol document is missing: {document}")

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


def _audit_runtime_catalog(root: Path, catalog, errors: list[str]) -> None:
    try:
        runtime_catalog = load_runtime_protocol_catalog(root)
        base = load_base_implementation(root)
    except ValueError as exc:
        errors.append(f"runtime compatibility catalog cannot be audited: {exc}")
        return
    forbidden_fields = {"registry", "profiles", "capabilities", "document"}
    found_forbidden: set[str] = set()

    def visit(value) -> None:
        if isinstance(value, dict):
            found_forbidden.update(forbidden_fields.intersection(value))
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(runtime_catalog["release_manifest"])
    if found_forbidden:
        errors.append(
            "runtime compatibility catalog must not retain governance artifact references: "
            f"{sorted(found_forbidden)}"
        )
    vocabularies = runtime_catalog["vocabularies"]
    for field in ("profiles", "capabilities", "tool_packs"):
        unknown = sorted(set(base.get(field) or []) - set(vocabularies[field]))
        if unknown:
            errors.append(f"Base declares unknown runtime {field}: {unknown}")
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


def _audit_product_bindings(root: Path, catalog, errors: list[str], *, clean: bool) -> None:
    expected_binding = "load_runtime_protocol_catalog" if clean else "ProtocolArtifactStore"
    _require_text(root / "src/core/protocol/capability_registry.py", expected_binding, errors)
    _require_text(root / "src/core/lab/dev_flow.py", "self.default_protocol_version", errors)
    _require_text(root / "src/backend/main.py", "protocol_catalog", errors)
    _require_text(root / "src/core/studio/creator_runtime_bridge.py", 'CREATOR_PACKAGE_PROTOCOL = {"id": "CF-FARP", "version": "1.6"}', errors)
    _require_text(root / "src/studio/src/api/client.ts", "packageCreatorProject", errors)
    _require_text(root / "README.md", "protocol-registry", errors)

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
        print("Protocol registry audit failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Protocol registry audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
