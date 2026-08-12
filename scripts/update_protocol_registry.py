from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import (
    CLEAN_GENERATION,
    RUNTIME_CATALOG_RELATIVE_PATH,
    ImplementationSource,
    ProtocolKnowledgeRegistry,
    build_clean_base_candidate,
    build_clean_protocol_support_report,
    load_runtime_protocol_catalog,
    publish_protocol_knowledge_registry,
)
from core.protocol.base_manifest import BASE_IMPLEMENTATION_PATH
from core.protocol.knowledge_registry import (
    EVIDENCE_RELATIVE_PATH,
    IMPLEMENTATION_KNOWLEDGE_RELATIVE_PATHS,
)


REPOSITORY_URL = "https://github.com/Holosukiyaa/cartridgeflow-protocols.git"
SOURCE_DATABASE_RELATIVE_PATH = Path("protocol-source.sqlite")
RUNTIME_SOURCE_ID = "cartridgeflow-authoritative"
DATABASE_PATH = ROOT / "config" / "protocol" / "protocol-registry.sqlite"
LOCK_PATH = ROOT / "config" / "protocol" / "protocol-registry.lock.json"
BASE_PATH = ROOT / BASE_IMPLEMENTATION_PATH
RUNTIME_CATALOG_PATH = ROOT / RUNTIME_CATALOG_RELATIVE_PATH


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the product protocol registry from a clean, pushed protocol commit."
    )
    parser.add_argument(
        "--protocol-repository",
        type=Path,
        required=True,
        help="Explicit checkout of the authoritative cartridgeflow-protocols repository.",
    )
    args = parser.parse_args()
    repository = args.protocol_repository.resolve()
    try:
        commit, remote = _validate_source_repository(repository)
        source_database = repository / SOURCE_DATABASE_RELATIVE_PATH
        if not source_database.is_file():
            raise RuntimeError(
                f"authoritative protocol database not found: {SOURCE_DATABASE_RELATIVE_PATH.as_posix()}"
            )
        source_database_digest = hashlib.sha256(source_database.read_bytes()).hexdigest()
        load_runtime_protocol_catalog(ROOT)
        runtime_catalog_digest = hashlib.sha256(RUNTIME_CATALOG_PATH.read_bytes()).hexdigest()
        clean_base = build_clean_base_candidate(ROOT)
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".protocol-registry-update-", dir=DATABASE_PATH.parent
        ) as temporary:
            staging_dir = Path(temporary)
            staged_database = staging_dir / DATABASE_PATH.name
            staged_base = staging_dir / BASE_PATH.name
            _write_json_atomic(staged_base, clean_base)
            implementation_root = staging_dir / "implementation"
            _stage_implementation_source(implementation_root, clean_base)
            report = publish_protocol_knowledge_registry(
                staged_database,
                source_database,
                implementation_sources=[ImplementationSource(RUNTIME_SOURCE_ID, implementation_root)],
            )
            with ProtocolKnowledgeRegistry(staged_database) as registry:
                product_summary = registry.summary()
                unexpected_blockers = registry.findings(severity="blocker")
                source_rows = [
                    dict(row)
                    for row in registry.connection.execute(
                        "SELECT source_id, manifest_digest, source_digest "
                        "FROM registry_source ORDER BY source_id"
                    )
                ]
            with ProtocolKnowledgeRegistry(source_database) as source_registry:
                source_summary = source_registry.summary()
            if unexpected_blockers:
                raise RuntimeError(
                    f"protocol sources contain unexpected blocker findings: "
                    f"{sorted({item['finding_type'] for item in unexpected_blockers})}"
                )
            database_digest = hashlib.sha256(staged_database.read_bytes()).hexdigest()
            base_digest = hashlib.sha256(staged_base.read_bytes()).hexdigest()
            lock = {
                "schema": "cartridgeflow.product_protocol_registry_lock.v4",
                "generation": CLEAN_GENERATION,
                "repository": {
                    "url": remote,
                    "commit": commit,
                },
                "source_database": {
                    "path": SOURCE_DATABASE_RELATIVE_PATH.as_posix(),
                    "database_sha256": source_database_digest,
                    "logical_digest": source_summary["registry_digest"],
                },
                "runtime_source_id": RUNTIME_SOURCE_ID,
                "runtime_catalog": {
                    "path": RUNTIME_CATALOG_RELATIVE_PATH.as_posix(),
                    "sha256": runtime_catalog_digest,
                },
                "base": {
                    "path": BASE_IMPLEMENTATION_PATH.as_posix(),
                    "manifest_sha256": base_digest,
                },
                "sources": [
                    {
                        "source_id": row["source_id"],
                        "manifest_digest": row["manifest_digest"],
                        "source_digest": row["source_digest"],
                    }
                    for row in source_rows
                ],
                "registry": {
                    "schema_version": product_summary["schema_version"],
                    "logical_digest": report.registry_digest,
                    "database_sha256": database_digest,
                    "path": DATABASE_PATH.relative_to(ROOT).as_posix(),
                },
            }
            support_report = build_clean_protocol_support_report(
                ROOT,
                base=clean_base,
                registry_path=staged_database,
            )
            if not support_report["ok"]:
                raise RuntimeError(
                    "staged clean-v1 bundle does not conform: "
                    + "; ".join(
                        f"{item['code']}: {item['message']}"
                        for item in support_report["findings"]
                    )
                )
            staged_lock = staging_dir / LOCK_PATH.name
            _write_json_atomic(staged_lock, lock)
            _replace_registry_bundle(staged_database, staged_lock, staged_base, staging_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Protocol registry update failed: {exc}", file=sys.stderr)
        return 1
    print(f"Protocol source database: {source_database}")
    print(f"Protocol repository: {remote}@{commit}")
    print(f"Protocol registry: {DATABASE_PATH}")
    print(f"Base generation: {CLEAN_GENERATION}")
    print(f"Database SHA-256: {database_digest}")
    return 0


def _validate_source_repository(repository: Path) -> tuple[str, str]:
    if not (repository / ".git").exists():
        raise RuntimeError(f"not an initialized Git protocol repository: {repository}")
    if _git(repository, "rev-parse", "--is-inside-work-tree").strip() != "true":
        raise RuntimeError(f"not a Git protocol repository: {repository}")
    status = _git(repository, "status", "--porcelain", "--untracked-files=all")
    if status.strip():
        raise RuntimeError("protocol repository has uncommitted changes")
    commit = _git(repository, "rev-parse", "HEAD").strip()
    remote = _git(repository, "remote", "get-url", "origin").strip()
    normalized_remote = remote.removesuffix("/")
    if normalized_remote not in {REPOSITORY_URL, REPOSITORY_URL.removesuffix(".git")}:
        raise RuntimeError(f"unexpected protocol source remote: {remote}")
    published_refs = _git(
        repository,
        "for-each-ref",
        f"--contains={commit}",
        "--format=%(refname)",
        "refs/remotes/origin",
        "refs/tags",
    ).splitlines()
    if not published_refs:
        remote_refs = _git(repository, "ls-remote", "origin")
        if not any(line.startswith(f"{commit}\t") for line in remote_refs.splitlines()):
            raise RuntimeError("protocol source HEAD is not published on origin")
    return commit, REPOSITORY_URL


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _stage_implementation_source(staged_root: Path, clean_base: dict) -> None:
    _write_json_atomic(staged_root / BASE_IMPLEMENTATION_PATH, clean_base)
    for relative in (EVIDENCE_RELATIVE_PATH, *IMPLEMENTATION_KNOWLEDGE_RELATIVE_PATHS):
        source = ROOT / relative
        if not source.is_file():
            continue
        target = staged_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _replace_registry_bundle(
    staged_database: Path,
    staged_lock: Path,
    staged_base: Path,
    staging_dir: Path,
) -> None:
    replacements = (
        (staged_database, DATABASE_PATH, staging_dir / "previous-registry.sqlite"),
        (staged_base, BASE_PATH, staging_dir / "previous-base.json"),
        (staged_lock, LOCK_PATH, staging_dir / "previous-registry.lock.json"),
    )
    for _staged, target, backup in replacements:
        if target.is_file():
            shutil.copy2(target, backup)
    completed: list[tuple[Path, Path, Path]] = []
    try:
        for staged, target, backup in replacements:
            os.replace(staged, target)
            completed.append((staged, target, backup))
    except OSError as exc:
        rollback_errors: list[str] = []
        for _staged, target, backup in reversed(completed):
            if backup.is_file():
                try:
                    os.replace(backup, target)
                except OSError as rollback_exc:
                    rollback_errors.append(f"{target}: {rollback_exc}")
            else:
                target.unlink(missing_ok=True)
        detail = (
            f"; rollback also failed for {rollback_errors}"
            if rollback_errors
            else ""
        )
        raise RuntimeError(
            "protocol bundle replacement failed; close processes reading the Registry "
            f"and retry: {exc}{detail}"
        ) from exc


if __name__ == "__main__":
    raise SystemExit(main())
