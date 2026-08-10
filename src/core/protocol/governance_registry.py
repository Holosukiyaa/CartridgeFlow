from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REGISTRY_SCHEMA_VERSION = "1"
REGISTRY_SCHEMA_NAME = "cartridgeflow.protocol_knowledge_registry.v1"
LOCK_SCHEMA_NAME = "cartridgeflow.protocol_line_lock.v1"
MANIFEST_RELATIVE_PATH = Path("protocol/catalog/release_manifest.json")
FAMILY_METADATA_RELATIVE_PATH = Path("protocol/governance/protocol_families.json")
IMPLEMENTATION_RELATIVE_PATH = Path("config/base/BASE_IMPLEMENTATION.json")
EVIDENCE_RELATIVE_PATH = Path("config/base/capability_evidence.json")
DEFAULT_SCHEMA_PATH = Path(__file__).with_name("knowledge_registry_schema.sql")
_SOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TEXT_SUFFIXES = {".json", ".md", ".sql", ".txt", ".yaml", ".yml"}


class ProtocolKnowledgeRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ProtocolSource:
    source_id: str
    root: Path

    def __post_init__(self) -> None:
        if not _SOURCE_ID_RE.fullmatch(self.source_id):
            raise ProtocolKnowledgeRegistryError(
                f"invalid protocol source id {self.source_id!r}; use lowercase letters, digits, '_' or '-'"
            )
        object.__setattr__(self, "root", Path(self.root).resolve())


@dataclass(frozen=True)
class ImplementationSource:
    source_id: str
    root: Path

    def __post_init__(self) -> None:
        if not _SOURCE_ID_RE.fullmatch(self.source_id):
            raise ProtocolKnowledgeRegistryError(
                f"invalid implementation source id {self.source_id!r}; use lowercase letters, digits, '_' or '-'"
            )
        object.__setattr__(self, "root", Path(self.root).resolve())


@dataclass(frozen=True)
class RegistryBuildReport:
    output_path: Path
    registry_digest: str
    source_count: int
    release_count: int
    artifact_count: int
    section_count: int
    finding_counts: dict[str, int]
    lock_paths: tuple[Path, ...]


@dataclass
class _Artifact:
    artifact_id: str
    source_id: str
    path: str
    kind: str
    media_type: str
    content: bytes
    text: str | None
    byte_size: int
    digest: str
    release_key: str | None = None


@dataclass
class _Section:
    section_key: str
    artifact_id: str
    release_key: str | None
    anchor: str
    heading: str
    level: int
    line_start: int
    line_end: int
    content: str


@dataclass
class _Release:
    release_key: str
    source_id: str
    protocol_id: str
    version: str
    name: str | None
    category: str
    lifecycle: str | None
    specification_status: str | None
    implementation_status: str | None
    runtime_adapter: str | None
    release_path: str
    release_digest: str
    bundle_digest: str
    manifest_entry: dict | None
    release_data: dict
    features: set[str] = field(default_factory=set)


@dataclass
class _SourceInventory:
    source: ProtocolSource
    manifest_digest: str
    source_digest: str
    implementation_digest: str | None
    families: dict[str, dict]
    releases: list[_Release]
    artifacts: list[_Artifact]
    sections: list[_Section]
    relations: list[dict]
    policies: list[dict]
    implementation: dict | None
    implementation_support: list[dict]
    implementation_evidence: list[dict]
    findings: list[dict]


def build_protocol_knowledge_registry(
    output_path: str | Path,
    sources: Iterable[ProtocolSource],
    *,
    implementation_sources: Iterable[ImplementationSource] = (),
    lock_dir: str | Path | None = None,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> RegistryBuildReport:
    source_list = list(sources)
    if not source_list:
        raise ProtocolKnowledgeRegistryError("at least one protocol source is required")
    source_ids = [item.source_id for item in source_list]
    if len(source_ids) != len(set(source_ids)):
        raise ProtocolKnowledgeRegistryError("protocol source ids must be unique")

    implementation_list = list(implementation_sources)
    implementation_by_id = {item.source_id: item for item in implementation_list}
    if len(implementation_by_id) != len(implementation_list):
        raise ProtocolKnowledgeRegistryError("implementation source ids must be unique")
    unknown_implementations = sorted(set(implementation_by_id) - set(source_ids))
    if unknown_implementations:
        raise ProtocolKnowledgeRegistryError(
            f"implementation sources require matching protocol sources: {unknown_implementations}"
        )

    inventories = [
        _inventory_source(source, implementation_by_id.get(source.source_id))
        for source in source_list
    ]
    findings = [finding for inventory in inventories for finding in inventory.findings]
    findings.extend(_identity_collision_findings(inventories))
    registry_digest = _sha256_json(
        {
            "schema": REGISTRY_SCHEMA_NAME,
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "sources": [
                {
                    "source_id": item.source.source_id,
                    "source_digest": item.source_digest,
                    "implementation_digest": item.implementation_digest,
                }
                for item in sorted(inventories, key=lambda value: value.source.source_id)
            ],
        }
    )

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    schema = Path(schema_path).read_text(encoding="utf-8")
    temporary = _temporary_database_path(output)
    try:
        _write_database(temporary, schema, inventories, findings, registry_digest)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    lock_paths: list[Path] = []
    if lock_dir is not None:
        target_dir = Path(lock_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        for inventory in inventories:
            target = target_dir / f"{inventory.source.source_id}.protocol-lock.json"
            _write_json_atomic(target, _build_lock(inventory))
            lock_paths.append(target)

    counts: dict[str, int] = {}
    for finding in findings:
        severity = finding["severity"]
        counts[severity] = counts.get(severity, 0) + 1
    return RegistryBuildReport(
        output_path=output,
        registry_digest=registry_digest,
        source_count=len(inventories),
        release_count=sum(len(item.releases) for item in inventories),
        artifact_count=sum(len(item.artifacts) for item in inventories),
        section_count=sum(len(item.sections) for item in inventories),
        finding_counts=counts,
        lock_paths=tuple(lock_paths),
    )


class ProtocolKnowledgeRegistry:
    """Read-only access to a generated protocol knowledge registry."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise ProtocolKnowledgeRegistryError(f"protocol registry not found: {self.path}")
        self.connection = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA query_only = ON")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ProtocolKnowledgeRegistry:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def summary(self) -> dict:
        metadata = dict(self.connection.execute("SELECT key, value FROM registry_metadata"))
        return {
            **metadata,
            "source_count": self.connection.execute("SELECT COUNT(*) FROM registry_source").fetchone()[0],
            "release_count": self.connection.execute("SELECT COUNT(*) FROM protocol_release").fetchone()[0],
            "artifact_count": self.connection.execute("SELECT COUNT(*) FROM artifact").fetchone()[0],
            "section_count": self.connection.execute("SELECT COUNT(*) FROM document_section").fetchone()[0],
            "finding_count": self.connection.execute("SELECT COUNT(*) FROM governance_finding").fetchone()[0],
            "implementation_count": self.connection.execute("SELECT COUNT(*) FROM implementation_manifest").fetchone()[0],
            "evidence_count": self.connection.execute("SELECT COUNT(*) FROM implementation_evidence").fetchone()[0],
        }

    def get_release(self, source_id: str, protocol_id: str, version: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT * FROM protocol_release
            WHERE source_id = ? AND protocol_id = ? AND version = ?
            """,
            (source_id, protocol_id, version),
        ).fetchone()
        return dict(row) if row else None

    def artifact_exists(self, source_id: str, artifact_path: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM artifact WHERE source_id = ? AND artifact_path = ?",
            (source_id, _logical_path(artifact_path)),
        ).fetchone() is not None

    def artifact_bytes(self, source_id: str, artifact_path: str) -> bytes:
        row = self.connection.execute(
            "SELECT content, media_type FROM artifact WHERE source_id = ? AND artifact_path = ?",
            (source_id, _logical_path(artifact_path)),
        ).fetchone()
        if row is None:
            raise ProtocolKnowledgeRegistryError(
                f"protocol artifact not found: {source_id}:{_logical_path(artifact_path)}"
            )
        return _decode_stored_content(bytes(row[0]), str(row[1]))

    def artifact_text(self, source_id: str, artifact_path: str) -> str:
        row = self.connection.execute(
            "SELECT text_content, content, media_type FROM artifact WHERE source_id = ? AND artifact_path = ?",
            (source_id, _logical_path(artifact_path)),
        ).fetchone()
        if row is None:
            raise ProtocolKnowledgeRegistryError(
                f"text protocol artifact not found: {source_id}:{_logical_path(artifact_path)}"
            )
        if row[0] is not None:
            return str(row[0])
        try:
            return _decode_stored_content(bytes(row[1]), str(row[2])).decode("utf-8")
        except (UnicodeDecodeError, zlib.error) as exc:
            raise ProtocolKnowledgeRegistryError(
                f"text protocol artifact cannot be decoded: {source_id}:{_logical_path(artifact_path)}"
            ) from exc

    def artifact_json(self, source_id: str, artifact_path: str) -> dict:
        try:
            value = json.loads(self.artifact_text(source_id, artifact_path))
        except json.JSONDecodeError as exc:
            raise ProtocolKnowledgeRegistryError(
                f"protocol artifact is not valid JSON: {source_id}:{_logical_path(artifact_path)}"
            ) from exc
        if not isinstance(value, dict):
            raise ProtocolKnowledgeRegistryError(
                f"protocol artifact must be a JSON object: {source_id}:{_logical_path(artifact_path)}"
            )
        return value

    def releases(self, source_id: str) -> list[dict]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM protocol_release WHERE source_id = ? ORDER BY protocol_id, version",
                (source_id,),
            )
        ]

    def findings(self, *, severity: str | None = None) -> list[dict]:
        if severity is None:
            rows = self.connection.execute(
                "SELECT * FROM governance_finding ORDER BY severity, finding_type, finding_id"
            )
        else:
            rows = self.connection.execute(
                "SELECT * FROM governance_finding WHERE severity = ? ORDER BY finding_type, finding_id",
                (severity,),
            )
        return [dict(row) for row in rows]

    def search(self, query: str, *, source_id: str | None = None, limit: int = 20) -> list[dict]:
        query = query.strip()
        if not query:
            return []
        engine = self.connection.execute(
            "SELECT value FROM registry_metadata WHERE key = 'search_engine'"
        ).fetchone()[0]
        source_filter = " AND source_id = ?" if source_id else ""
        parameters: list[object]
        if engine.startswith("fts5") and not _requires_like_search(query):
            expression = _fts_expression(query)
            sql = (
                "SELECT section_key, source_id, release_key, artifact_path, heading, "
                "line_start, line_end, snippet(section_fts, 7, '[', ']', '...', 24) AS excerpt "
                "FROM section_fts WHERE section_fts MATCH ?"
                f"{source_filter} ORDER BY rank LIMIT ?"
            )
            parameters = [expression]
        else:
            tokens = [token for token in re.split(r"\s+", query) if token]
            predicates = " AND ".join("content LIKE ?" for _ in tokens)
            sql = (
                "SELECT section_key, source_id, release_key, artifact_path, heading, "
                "line_start, line_end, substr(content, 1, 320) AS excerpt "
                f"FROM section_fts WHERE {predicates}"
                f"{source_filter} ORDER BY artifact_path, line_start LIMIT ?"
            )
            parameters = [f"%{token}%" for token in tokens]
        if source_id:
            parameters.append(source_id)
        parameters.append(max(1, min(int(limit), 100)))
        return [dict(row) for row in self.connection.execute(sql, parameters)]


def _inventory_source(
    source: ProtocolSource,
    implementation_source: ImplementationSource | None = None,
) -> _SourceInventory:
    protocol_root = source.root / "protocol"
    manifest_path = source.root / MANIFEST_RELATIVE_PATH
    if not protocol_root.is_dir():
        raise ProtocolKnowledgeRegistryError(f"{source.source_id}: protocol directory not found")
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except FileNotFoundError as exc:
        raise ProtocolKnowledgeRegistryError(
            f"{source.source_id}: {MANIFEST_RELATIVE_PATH.as_posix()} not found"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolKnowledgeRegistryError(
            f"{source.source_id}: release manifest is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise ProtocolKnowledgeRegistryError(f"{source.source_id}: release manifest must be an object")

    if implementation_source is None:
        implementation, implementation_support, implementation_evidence, implementation_paths = None, [], [], set()
    else:
        implementation, implementation_support, implementation_evidence, implementation_paths = _load_implementation_governance(
            implementation_source
        )

    manifest_entries = _manifest_release_entries(manifest)
    manifest_by_key: dict[tuple[str, str], dict] = {}
    findings: list[dict] = []
    for entry in manifest_entries:
        key = (str(entry["id"]), str(entry["version"]))
        if key in manifest_by_key:
            findings.append(
                _finding(
                    "blocker",
                    "duplicate_manifest_identity",
                    source.source_id,
                    key[0],
                    key[1],
                    f"release manifest contains duplicate identity {key[0]}@{key[1]}",
                )
            )
        else:
            manifest_by_key[key] = entry

    release_records: list[_Release] = []
    release_dirs: dict[Path, str] = {}
    seen: set[tuple[str, str]] = set()
    for release_file in sorted(protocol_root.rglob("release.json")):
        relative = release_file.relative_to(source.root).as_posix()
        try:
            raw = release_file.read_bytes()
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolKnowledgeRegistryError(
                f"{source.source_id}:{relative} is not valid UTF-8 JSON: {exc}"
            ) from exc
        if not isinstance(data, dict) or not data.get("id") or data.get("version") is None:
            raise ProtocolKnowledgeRegistryError(
                f"{source.source_id}:{relative} requires id and version"
            )
        protocol_id, version = str(data["id"]), str(data["version"])
        identity = (protocol_id, version)
        if identity in seen:
            raise ProtocolKnowledgeRegistryError(
                f"{source.source_id} contains duplicate release {protocol_id}@{version}"
            )
        seen.add(identity)
        manifest_entry = manifest_by_key.get(identity)
        release_key = f"{source.source_id}:{protocol_id}@{version}"
        release_records.append(
            _Release(
                release_key=release_key,
                source_id=source.source_id,
                protocol_id=protocol_id,
                version=version,
                name=_optional_string(data.get("name")),
                category=release_file.relative_to(protocol_root).parts[0],
                lifecycle=_optional_string((manifest_entry or {}).get("lifecycle") or data.get("lifecycle")),
                specification_status=_optional_string(data.get("status") or (manifest_entry or {}).get("status")),
                implementation_status=_optional_string(
                    data.get("implementation_status") or (manifest_entry or {}).get("implementation_status")
                ),
                runtime_adapter=_optional_string(
                    data.get("runtime_adapter") or (manifest_entry or {}).get("runtime_adapter")
                ),
                release_path=relative,
                release_digest=_sha256(raw),
                bundle_digest="",
                manifest_entry=manifest_entry,
                release_data=data,
                features={str(item) for item in [*data.get("features", []), *(manifest_entry or {}).get("features", [])]},
            )
        )
        release_dirs[release_file.parent] = release_key

    protocol_artifact_paths = {item for item in protocol_root.rglob("*") if item.is_file()}
    artifact_paths = {
        item.relative_to(source.root).as_posix(): item
        for item in protocol_artifact_paths
    }
    if implementation_source is not None:
        artifact_paths.update(
            {
                item.relative_to(implementation_source.root).as_posix(): item
                for item in implementation_paths
            }
        )
    artifacts: list[_Artifact] = []
    for relative, path in sorted(artifact_paths.items()):
        logical_content = path.read_bytes()
        logical_text = _decode_text(path, logical_content)
        if path.suffix.lower() == ".json" and logical_text is not None:
            try:
                json.loads(logical_text)
            except json.JSONDecodeError as exc:
                findings.append(
                    _finding(
                        "blocker",
                        "invalid_json_artifact",
                        source.source_id,
                        None,
                        None,
                        f"{relative} is not valid JSON: {exc.msg}",
                        {"artifact_path": relative, "line": exc.lineno},
                    )
                )
        release_key = _owning_release(path, release_dirs)
        media_type = _media_type(path)
        content = logical_content
        text = logical_text
        if relative == EVIDENCE_RELATIVE_PATH.as_posix():
            content = zlib.compress(logical_content, level=9)
            text = None
            media_type = f"{media_type}+zlib"
        artifacts.append(
            _Artifact(
                artifact_id=f"{source.source_id}:{relative}",
                source_id=source.source_id,
                path=relative,
                kind=_artifact_kind(path, release_key),
                media_type=media_type,
                content=content,
                text=text,
                byte_size=len(logical_content),
                digest=_sha256(logical_content),
                release_key=release_key,
            )
        )

    artifacts_by_release: dict[str, list[_Artifact]] = {}
    for artifact in artifacts:
        if artifact.release_key:
            artifacts_by_release.setdefault(artifact.release_key, []).append(artifact)
    for release in release_records:
        release.bundle_digest = _bundle_digest(artifacts_by_release.get(release.release_key, []), release.release_path)

    releases_by_identity = {(item.protocol_id, item.version): item for item in release_records}
    for identity, entry in manifest_by_key.items():
        release = releases_by_identity.get(identity)
        if release is None:
            findings.append(
                _finding(
                    "blocker",
                    "manifest_release_missing",
                    source.source_id,
                    identity[0],
                    identity[1],
                    f"manifest release {identity[0]}@{identity[1]} has no release.json snapshot",
                    {"registry": entry.get("registry")},
                )
            )
        elif entry.get("registry") and f"protocol/{entry['registry']}" != release.release_path:
            findings.append(
                _finding(
                    "blocker",
                    "manifest_registry_mismatch",
                    source.source_id,
                    identity[0],
                    identity[1],
                    f"manifest registry path does not match the release snapshot for {identity[0]}@{identity[1]}",
                    {"manifest": entry.get("registry"), "actual": release.release_path},
                    release.release_key,
                )
            )

    families = _load_family_metadata(source.root)
    for release in release_records:
        families.setdefault(
            release.protocol_id,
            {"id": release.protocol_id, "name": release.name, "owner": None, "responsibility_boundary": None, "exclusions": []},
        )

    relations = _release_relations(release_records, releases_by_identity)
    for relation in relations:
        target = (relation["target_protocol_id"], relation["target_version"])
        if target not in releases_by_identity:
            findings.append(
                _finding(
                    "warning",
                    "unresolved_relation_target",
                    source.source_id,
                    target[0],
                    target[1],
                    f"{relation['source_release_key']} {relation['relation_type']} target is not present in this product line: {target[0]}@{target[1]}",
                    {"relation_type": relation["relation_type"]},
                    relation["source_release_key"],
                )
            )

    sections = [
        section
        for artifact in artifacts
        if artifact.text is not None and artifact.path.lower().endswith(".md")
        for section in _markdown_sections(artifact)
    ]
    policies = _manifest_policies(manifest, source.source_id)
    source_digest = _sha256_json(
        {
            "manifest_digest": _sha256(manifest_bytes),
            "artifacts": [
                {"path": item.path, "digest": item.digest}
                for item in artifacts
                if item.path.startswith("protocol/")
            ],
        }
    )
    implementation_digest = (
        _sha256_json(
            [
                {"path": item.path, "digest": item.digest}
                for item in artifacts
                if not item.path.startswith("protocol/")
            ]
        )
        if implementation is not None
        else None
    )
    return _SourceInventory(
        source=source,
        manifest_digest=_sha256(manifest_bytes),
        source_digest=source_digest,
        implementation_digest=implementation_digest,
        families=families,
        releases=release_records,
        artifacts=artifacts,
        sections=sections,
        relations=relations,
        policies=policies,
        implementation=implementation,
        implementation_support=implementation_support,
        implementation_evidence=implementation_evidence,
        findings=findings,
    )


def _write_database(
    path: Path,
    schema: str,
    inventories: list[_SourceInventory],
    findings: list[dict],
    registry_digest: str,
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.executescript(schema)
        search_engine = _create_search_tables(connection)
        connection.executemany(
            "INSERT INTO registry_metadata(key, value) VALUES (?, ?)",
            [
                ("schema", REGISTRY_SCHEMA_NAME),
                ("schema_version", REGISTRY_SCHEMA_VERSION),
                ("registry_digest", registry_digest),
                ("search_engine", search_engine),
                ("evidence_test_reference_format", "python_unittest_owner_case.v1"),
            ],
        )
        for inventory in inventories:
            source_id = inventory.source.source_id
            connection.execute(
                "INSERT INTO registry_source VALUES (?, ?, ?, ?)",
                (source_id, MANIFEST_RELATIVE_PATH.as_posix(), inventory.manifest_digest, inventory.source_digest),
            )
            for protocol_id, family in sorted(inventory.families.items()):
                connection.execute(
                    "INSERT INTO protocol_family VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        source_id,
                        protocol_id,
                        family.get("name"),
                        family.get("owner"),
                        family.get("responsibility_boundary"),
                        _canonical_json(family.get("exclusions") or []),
                    ),
                )
            for release in inventory.releases:
                connection.execute(
                    "INSERT INTO protocol_release VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        release.release_key,
                        release.source_id,
                        release.protocol_id,
                        release.version,
                        release.name,
                        release.category,
                        release.lifecycle,
                        release.specification_status,
                        release.implementation_status,
                        release.runtime_adapter,
                        release.release_path,
                        release.release_digest,
                        release.bundle_digest,
                        _canonical_json(release.manifest_entry) if release.manifest_entry else None,
                        _canonical_json(release.release_data),
                    ),
                )
                connection.executemany(
                    "INSERT INTO release_feature VALUES (?, ?)",
                    [(release.release_key, feature) for feature in sorted(release.features)],
                )
            for artifact in inventory.artifacts:
                connection.execute(
                    "INSERT INTO artifact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        artifact.artifact_id,
                        artifact.source_id,
                        artifact.release_key,
                        artifact.path,
                        artifact.kind,
                        artifact.media_type,
                        artifact.byte_size,
                        artifact.digest,
                        artifact.content,
                        artifact.text,
                    ),
                )
                if artifact.text:
                    connection.execute(
                        "INSERT INTO artifact_fts VALUES (?, ?, ?, ?, ?)",
                        (artifact.artifact_id, artifact.source_id, artifact.release_key, artifact.path, artifact.text),
                    )
            for section in inventory.sections:
                artifact_path = section.artifact_id.split(":", 1)[1]
                connection.execute(
                    "INSERT INTO document_section VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        section.section_key,
                        section.artifact_id,
                        section.release_key,
                        section.anchor,
                        section.heading,
                        section.level,
                        section.line_start,
                        section.line_end,
                        section.content,
                    ),
                )
                connection.execute(
                    "INSERT INTO section_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        section.section_key,
                        source_id,
                        section.release_key,
                        artifact_path,
                        section.heading,
                        section.line_start,
                        section.line_end,
                        section.content,
                    ),
                )
            for relation in inventory.relations:
                connection.execute(
                    """
                    INSERT INTO release_relation(
                        source_release_key, relation_type, target_source_id,
                        target_protocol_id, target_version, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        relation["source_release_key"],
                        relation["relation_type"],
                        relation["target_source_id"],
                        relation["target_protocol_id"],
                        relation["target_version"],
                        _canonical_json(relation["metadata"]),
                    ),
                )
            for policy in inventory.policies:
                connection.execute(
                    "INSERT INTO source_policy VALUES (?, ?, ?, ?, ?)",
                    (
                        source_id,
                        policy["policy_key"],
                        policy["target_protocol_id"],
                        policy["target_version"],
                        _canonical_json(policy["metadata"]),
                    ),
                )
            if inventory.implementation:
                implementation = inventory.implementation
                connection.execute(
                    "INSERT INTO implementation_manifest VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        implementation["implementation_key"],
                        source_id,
                        implementation["implementation_id"],
                        implementation.get("implementation_name"),
                        implementation["implementation_version"],
                        implementation.get("environment"),
                        implementation.get("base_protocol_id"),
                        implementation.get("base_protocol_version"),
                        implementation["artifact_id"],
                        implementation["manifest_digest"],
                    ),
                )
                for support in inventory.implementation_support:
                    connection.execute(
                        """
                        INSERT INTO implementation_support(
                            implementation_key, support_kind, target_id, target_version,
                            support_status, runtime_adapter, metadata_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            implementation["implementation_key"],
                            support["support_kind"],
                            support["target_id"],
                            support["target_version"],
                            support["support_status"],
                            support.get("runtime_adapter"),
                            _canonical_json(support.get("metadata") or {}),
                        ),
                    )
                for evidence in inventory.implementation_evidence:
                    connection.execute(
                        "INSERT INTO implementation_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            evidence["evidence_key"],
                            implementation["implementation_key"],
                            evidence["evidence_id"],
                            evidence["verification"],
                            _canonical_json(evidence["implementation"]),
                            _canonical_json(evidence["positive_tests"]),
                            _canonical_json(evidence["failure_tests"]),
                            _canonical_json(evidence["details"]),
                            evidence["artifact_id"],
                        ),
                    )
        for finding in findings:
            connection.execute(
                """
                INSERT INTO governance_finding(
                    severity, finding_type, source_id, release_key, protocol_id,
                    version, message, details_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding["severity"],
                    finding["finding_type"],
                    finding.get("source_id"),
                    finding.get("release_key"),
                    finding.get("protocol_id"),
                    finding.get("version"),
                    finding["message"],
                    _canonical_json(finding.get("details") or {}),
                    finding.get("status", "open"),
                ),
            )
        connection.commit()
        connection.execute("PRAGMA optimize")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _create_search_tables(connection: sqlite3.Connection) -> str:
    # Keep the distributable registry independent of optional FTS extensions.
    # A separate AI search index can be built from these portable text tables.
    connection.execute(
        "CREATE TABLE artifact_fts(artifact_id TEXT, source_id TEXT, release_key TEXT, artifact_path TEXT, content TEXT)"
    )
    connection.execute(
        "CREATE TABLE section_fts(section_key TEXT, source_id TEXT, release_key TEXT, artifact_path TEXT, heading TEXT, line_start INTEGER, line_end INTEGER, content TEXT)"
    )
    connection.execute("CREATE INDEX artifact_search_source_idx ON artifact_fts(source_id, artifact_path)")
    connection.execute("CREATE INDEX section_search_source_idx ON section_fts(source_id, artifact_path, line_start)")
    return "like"


def _identity_collision_findings(inventories: list[_SourceInventory]) -> list[dict]:
    identities: dict[tuple[str, str], list[_Release]] = {}
    for inventory in inventories:
        for release in inventory.releases:
            identities.setdefault((release.protocol_id, release.version), []).append(release)
    findings: list[dict] = []
    for (protocol_id, version), releases in sorted(identities.items()):
        digests = {item.bundle_digest for item in releases}
        if len(releases) < 2 or len(digests) == 1:
            continue
        origins = [
            {"source_id": item.source_id, "bundle_digest": item.bundle_digest, "release_path": item.release_path}
            for item in sorted(releases, key=lambda value: value.source_id)
        ]
        findings.append(
            _finding(
                "blocker",
                "protocol_identity_collision",
                None,
                protocol_id,
                version,
                f"{protocol_id}@{version} has different release content across product lines",
                {"origins": origins},
            )
        )
    return findings


def _release_relations(
    releases: list[_Release], releases_by_identity: dict[tuple[str, str], _Release]
) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    def add(release: _Release, relation_type: str, target: object, metadata: dict | None = None) -> None:
        if not isinstance(target, dict) or not target.get("id") or target.get("version") is None:
            return
        protocol_id, version = str(target["id"]), str(target["version"])
        metadata = metadata or {}
        signature = (release.release_key, relation_type, protocol_id, version, _canonical_json(metadata))
        if signature in seen:
            return
        seen.add(signature)
        result.append(
            {
                "source_release_key": release.release_key,
                "relation_type": relation_type,
                "target_source_id": release.source_id if (protocol_id, version) in releases_by_identity else None,
                "target_protocol_id": protocol_id,
                "target_version": version,
                "metadata": metadata,
            }
        )

    for release in releases:
        data = release.release_data
        add(release, "requires", data.get("base_contract"), {"role": "base_contract"})
        add(release, "supersedes", data.get("supersedes"))
        for host in data.get("host_protocols") or []:
            add(release, "hosted_by", host)
        for child in data.get("trusted_subprotocols") or []:
            add(
                release,
                "trusts",
                child,
                {key: child[key] for key in ("binding", "required") if key in child},
            )
        entry = release.manifest_entry or {}
        add(release, "migrates_to", entry.get("migration_target"))
        for child in entry.get("trusted_subprotocols") or []:
            add(
                release,
                "trusts",
                child,
                {key: child[key] for key in ("binding", "required") if key in child},
            )
    return result


def _manifest_release_entries(value: object) -> list[dict]:
    result: list[dict] = []

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "releases" and isinstance(child, list):
                    result.extend(
                        entry
                        for entry in child
                        if isinstance(entry, dict)
                        and entry.get("id")
                        and entry.get("version") is not None
                        and isinstance(entry.get("registry"), str)
                    )
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return result


def _manifest_policies(manifest: dict, source_id: str) -> list[dict]:
    policy_names = {
        "base_contract",
        "default_for_new_flows",
        "default_for_new_releases",
        "default_for_desktop_runner",
    }
    result: list[dict] = []

    def visit(item: object, path: tuple[str, ...]) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = (*path, key)
                if key in policy_names and isinstance(child, dict) and child.get("id") and child.get("version") is not None:
                    result.append(
                        {
                            "source_id": source_id,
                            "policy_key": ".".join(child_path),
                            "target_protocol_id": str(child["id"]),
                            "target_version": str(child["version"]),
                            "metadata": {k: v for k, v in child.items() if k not in {"id", "version"}},
                        }
                    )
                visit(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, (*path, str(index)))

    visit(manifest, ())
    return result


def _load_family_metadata(root: Path) -> dict[str, dict]:
    path = root / FAMILY_METADATA_RELATIVE_PATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolKnowledgeRegistryError(f"{FAMILY_METADATA_RELATIVE_PATH.as_posix()} is invalid: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != "cartridgeflow.protocol_families.v1":
        raise ProtocolKnowledgeRegistryError(f"{FAMILY_METADATA_RELATIVE_PATH.as_posix()} has an unknown schema")
    families = data.get("families")
    if not isinstance(families, list):
        raise ProtocolKnowledgeRegistryError(f"{FAMILY_METADATA_RELATIVE_PATH.as_posix()}.families must be an array")
    result: dict[str, dict] = {}
    for index, family in enumerate(families):
        if not isinstance(family, dict) or not isinstance(family.get("id"), str) or not family["id"]:
            raise ProtocolKnowledgeRegistryError(f"protocol_families.json families[{index}].id is required")
        if family["id"] in result:
            raise ProtocolKnowledgeRegistryError(f"protocol_families.json duplicates {family['id']}")
        result[family["id"]] = family
    return result


def _load_implementation_governance(
    source: ImplementationSource,
) -> tuple[dict | None, list[dict], list[dict], set[Path]]:
    manifest_path = source.root / IMPLEMENTATION_RELATIVE_PATH
    if not manifest_path.is_file():
        return None, [], [], set()
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolKnowledgeRegistryError(
            f"{source.source_id}:{IMPLEMENTATION_RELATIVE_PATH.as_posix()} is invalid: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise ProtocolKnowledgeRegistryError(
            f"{source.source_id}:{IMPLEMENTATION_RELATIVE_PATH.as_posix()} must be an object"
        )
    implementation_id = manifest.get("implementation_id")
    implementation_version = manifest.get("implementation_version")
    if not implementation_id or implementation_version is None:
        raise ProtocolKnowledgeRegistryError(
            f"{source.source_id}:{IMPLEMENTATION_RELATIVE_PATH.as_posix()} requires implementation_id and implementation_version"
        )
    implementation_key = f"{source.source_id}:{implementation_id}@{implementation_version}"
    base_contract = manifest.get("base_contract") if isinstance(manifest.get("base_contract"), dict) else {}
    implementation = {
        "implementation_key": implementation_key,
        "implementation_id": str(implementation_id),
        "implementation_name": _optional_string(manifest.get("implementation_name")),
        "implementation_version": str(implementation_version),
        "environment": _optional_string(manifest.get("environment")),
        "base_protocol_id": _optional_string(base_contract.get("id")),
        "base_protocol_version": _optional_string(base_contract.get("version")),
        "artifact_id": f"{source.source_id}:{IMPLEMENTATION_RELATIVE_PATH.as_posix()}",
        "manifest_digest": _sha256(manifest_bytes),
    }

    support: list[dict] = []
    base_items = manifest.get("supported_base_contracts")
    if not isinstance(base_items, list):
        base_items = [{**base_contract, "status": "current"}] if base_contract else []
    for support_kind, items in (
        ("base_contract", base_items),
        ("protocol", manifest.get("supported_protocols") or []),
        ("subprotocol", manifest.get("supported_subprotocols") or []),
        ("adapter", manifest.get("supported_protocol_adapters") or []),
    ):
        if not isinstance(items, list):
            raise ProtocolKnowledgeRegistryError(
                f"{source.source_id}:{IMPLEMENTATION_RELATIVE_PATH.as_posix()} {support_kind} support must be an array"
            )
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not item.get("id") or not item.get("status"):
                raise ProtocolKnowledgeRegistryError(
                    f"{source.source_id}:{IMPLEMENTATION_RELATIVE_PATH.as_posix()} {support_kind}[{index}] requires id and status"
                )
            support.append(
                {
                    "support_kind": support_kind,
                    "target_id": str(item["id"]),
                    "target_version": str(item.get("version") or ""),
                    "support_status": str(item["status"]),
                    "runtime_adapter": _optional_string(item.get("runtime_adapter")),
                    "metadata": {
                        key: value
                        for key, value in item.items()
                        if key not in {"id", "version", "status", "runtime_adapter"}
                    },
                }
            )

    paths = {manifest_path}
    evidence: list[dict] = []
    conformance = manifest.get("conformance") if isinstance(manifest.get("conformance"), dict) else {}
    evidence_relative = conformance.get("evidence_manifest")
    if evidence_relative:
        evidence_path = (source.root / str(evidence_relative)).resolve()
        if not evidence_path.is_relative_to(source.root):
            raise ProtocolKnowledgeRegistryError(
                f"{source.source_id}: evidence manifest escapes the product-line root"
            )
        if not evidence_path.is_file():
            raise ProtocolKnowledgeRegistryError(
                f"{source.source_id}: evidence manifest not found: {evidence_relative}"
            )
        paths.add(evidence_path)
        try:
            evidence_data = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolKnowledgeRegistryError(
                f"{source.source_id}:{evidence_relative} is invalid: {exc}"
            ) from exc
        evidence_sets = evidence_data.get("evidence_sets") if isinstance(evidence_data, dict) else None
        if not isinstance(evidence_sets, dict):
            raise ProtocolKnowledgeRegistryError(
                f"{source.source_id}:{evidence_relative}.evidence_sets must be an object"
            )
        artifact_id = f"{source.source_id}:{evidence_path.relative_to(source.root).as_posix()}"
        for evidence_id, item in sorted(evidence_sets.items()):
            if not isinstance(item, dict) or not item.get("verification"):
                raise ProtocolKnowledgeRegistryError(
                    f"{source.source_id}:{evidence_relative} evidence {evidence_id} requires verification"
                )
            evidence.append(
                {
                    "evidence_key": f"{implementation_key}:{evidence_id}",
                    "evidence_id": str(evidence_id),
                    "verification": str(item["verification"]),
                    "implementation": item.get("implementation") or [],
                    "positive_tests": _structured_test_references(
                        item.get("positive_tests") or [],
                        f"{source.source_id}:{evidence_relative} evidence {evidence_id}.positive_tests",
                    ),
                    "failure_tests": _structured_test_references(
                        item.get("failure_tests") or [],
                        f"{source.source_id}:{evidence_relative} evidence {evidence_id}.failure_tests",
                    ),
                    "details": {
                        key: value
                        for key, value in item.items()
                        if key not in {"verification", "implementation", "positive_tests", "failure_tests"}
                    },
                    "artifact_id": artifact_id,
                }
            )
    return implementation, support, evidence, paths


def _structured_test_references(value: object, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ProtocolKnowledgeRegistryError(f"{label} must be an array")
    result: list[dict[str, str]] = []
    for index, reference in enumerate(value):
        if not isinstance(reference, str):
            raise ProtocolKnowledgeRegistryError(f"{label}[{index}] must be a string")
        owner, separator, method = reference.rpartition(".")
        if not separator or not owner or not method.startswith("test_") or len(method) == 5:
            raise ProtocolKnowledgeRegistryError(
                f"{label}[{index}] must name a Python unittest test_* method"
            )
        result.append({"owner": owner, "case": method.removeprefix("test_")})
    return result


def _markdown_sections(artifact: _Artifact) -> list[_Section]:
    assert artifact.text is not None
    lines = artifact.text.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    if not headings:
        return []
    result: list[_Section] = []
    anchor_counts: dict[str, int] = {}
    for offset, (start, level, heading) in enumerate(headings):
        end = headings[offset + 1][0] if offset + 1 < len(headings) else len(lines)
        base_anchor = _heading_anchor(heading) or f"section-{offset + 1}"
        anchor_counts[base_anchor] = anchor_counts.get(base_anchor, 0) + 1
        anchor = base_anchor if anchor_counts[base_anchor] == 1 else f"{base_anchor}-{anchor_counts[base_anchor]}"
        result.append(
            _Section(
                section_key=f"{artifact.artifact_id}#{anchor}",
                artifact_id=artifact.artifact_id,
                release_key=artifact.release_key,
                anchor=anchor,
                heading=heading,
                level=level,
                line_start=start + 1,
                line_end=end,
                content="\n".join(lines[start:end]),
            )
        )
    return result


def _build_lock(inventory: _SourceInventory) -> dict:
    payload = {
        "schema": LOCK_SCHEMA_NAME,
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "product_line": inventory.source.source_id,
        "manifest_digest": inventory.manifest_digest,
        "source_digest": inventory.source_digest,
        "policies": [
            {
                "key": item["policy_key"],
                "target": {"id": item["target_protocol_id"], "version": item["target_version"]},
                "metadata": item["metadata"],
            }
            for item in sorted(inventory.policies, key=lambda value: value["policy_key"])
        ],
        "releases": [
            {
                "id": item.protocol_id,
                "version": item.version,
                "lifecycle": item.lifecycle,
                "implementation_status": item.implementation_status,
                "release_path": item.release_path,
                "release_digest": item.release_digest,
                "bundle_digest": item.bundle_digest,
            }
            for item in sorted(inventory.releases, key=lambda value: (value.protocol_id, value.version))
        ],
    }
    return {**payload, "lock_digest": _sha256_json(payload)}


def _bundle_digest(artifacts: list[_Artifact], release_path: str) -> str:
    release_directory = Path(release_path).parent.as_posix().rstrip("/") + "/"
    members = [
        {"path": item.path.removeprefix(release_directory), "digest": item.digest}
        for item in sorted(artifacts, key=lambda value: value.path)
    ]
    return _sha256_json(members)


def _owning_release(path: Path, release_dirs: dict[Path, str]) -> str | None:
    candidates = [(directory, key) for directory, key in release_dirs.items() if path == directory or directory in path.parents]
    if not candidates:
        return None
    return max(candidates, key=lambda item: len(item[0].parts))[1]


def _artifact_kind(path: Path, release_key: str | None) -> str:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    if name == "release_manifest.json":
        return "catalog"
    if name == "base_implementation.json":
        return "implementation_manifest"
    if name == "capability_evidence.json":
        return "implementation_evidence"
    if "governance" in parts:
        return "governance"
    if name == "release.json":
        return "release_manifest"
    if name.endswith(".schema.json") or "schema" in name:
        return "schema"
    if name == "profiles.json" or name == "profile.json":
        return "profile"
    if name in {"capabilities.json", "tool_packs.json"}:
        return "vocabulary"
    if any(token in name for token in ("test", "fixture", "conformance", "example")):
        return "evidence"
    if path.suffix.lower() == ".md":
        return "specification" if release_key else "documentation"
    return "release_artifact" if release_key else "governance"


def _media_type(path: Path) -> str:
    return {
        ".json": "application/json",
        ".md": "text/markdown",
        ".sql": "application/sql",
        ".txt": "text/plain",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
    }.get(path.suffix.lower(), "application/octet-stream")


def _decode_text(path: Path, content: bytes) -> str | None:
    if path.suffix.lower() not in _TEXT_SUFFIXES:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolKnowledgeRegistryError(f"{path} is not valid UTF-8 text") from exc


def _decode_stored_content(content: bytes, media_type: str) -> bytes:
    return zlib.decompress(content) if media_type.endswith("+zlib") else content


def _heading_anchor(heading: str) -> str:
    value = heading.strip().lower()
    value = re.sub(r"[`*_~]", "", value)
    value = re.sub(r"[^\w\-\u4e00-\u9fff ]+", "", value, flags=re.UNICODE)
    return re.sub(r"[\s_]+", "-", value).strip("-")


def _finding(
    severity: str,
    finding_type: str,
    source_id: str | None,
    protocol_id: str | None,
    version: str | None,
    message: str,
    details: dict | None = None,
    release_key: str | None = None,
) -> dict:
    return {
        "severity": severity,
        "finding_type": finding_type,
        "source_id": source_id,
        "release_key": release_key,
        "protocol_id": protocol_id,
        "version": version,
        "message": message,
        "details": details or {},
        "status": "open",
    }


def _temporary_database_path(output: Path) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(name)
    temporary.unlink()
    return temporary


def _write_json_atomic(path: Path, value: dict) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _fts_expression(query: str) -> str:
    tokens = [token for token in re.split(r"\s+", query) if token]
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)


def _requires_like_search(query: str) -> bool:
    tokens = [token for token in re.split(r"\s+", query) if token]
    return any(len(token) < 3 for token in tokens)


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None and str(value) else None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256(_canonical_json(value).encode("utf-8"))


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _logical_path(value: str | Path) -> str:
    return Path(value).as_posix().lstrip("./")
