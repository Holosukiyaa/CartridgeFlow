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
    ImplementationSource,
    ProtocolKnowledgeRegistry,
    ProtocolSource,
    build_protocol_knowledge_registry,
)


REPOSITORY_URL = "https://github.com/Holosukiyaa/cartridgeflow-protocols.git"
SOURCE_SUBDIRECTORIES = {
    "current": Path("sources/current"),
    "temp-runtime": Path("sources/temp-runtime"),
}
RUNTIME_SOURCE_ID = "current"
DATABASE_PATH = ROOT / "config" / "protocol" / "protocol-registry.sqlite"
LOCK_PATH = ROOT / "config" / "protocol" / "protocol-registry.lock.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the product protocol registry from a clean, pushed protocol commit."
    )
    parser.add_argument(
        "--protocol-repository",
        type=Path,
        default=ROOT.parent / "cartridgeflow-protocols",
    )
    args = parser.parse_args()
    repository = args.protocol_repository.resolve()
    try:
        commit, remote = _validate_source_repository(repository)
        schema_path = repository / "registry" / "schema.sql"
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".protocol-registry-update-", dir=DATABASE_PATH.parent
        ) as temporary:
            staging_dir = Path(temporary)
            staged_database = staging_dir / DATABASE_PATH.name
            lock_dir = staging_dir / "line-locks"
            report = build_protocol_knowledge_registry(
                staged_database,
                [
                    ProtocolSource(source_id, repository / source_path)
                    for source_id, source_path in SOURCE_SUBDIRECTORIES.items()
                ],
                implementation_sources=[ImplementationSource("current", ROOT)],
                lock_dir=lock_dir,
                schema_path=schema_path,
            )
            with ProtocolKnowledgeRegistry(staged_database) as registry:
                unexpected_blockers = [
                    item
                    for item in registry.findings(severity="blocker")
                    if item["finding_type"] != "protocol_identity_collision"
                ]
            if unexpected_blockers:
                raise RuntimeError(
                    f"protocol sources contain unexpected blocker findings: "
                    f"{sorted({item['finding_type'] for item in unexpected_blockers})}"
                )
            line_locks = {
                source_id: json.loads(
                    (lock_dir / f"{source_id}.protocol-lock.json").read_text(encoding="utf-8")
                )
                for source_id in SOURCE_SUBDIRECTORIES
            }
            database_digest = hashlib.sha256(staged_database.read_bytes()).hexdigest()
            lock = {
                "schema": "cartridgeflow.product_protocol_registry_lock.v2",
                "repository": {
                    "url": remote,
                    "commit": commit,
                },
                "runtime_source_id": RUNTIME_SOURCE_ID,
                "sources": [
                    {
                        "source_id": source_id,
                        "path": source_path.as_posix(),
                        "manifest_digest": line_locks[source_id]["manifest_digest"],
                        "source_digest": line_locks[source_id]["source_digest"],
                    }
                    for source_id, source_path in SOURCE_SUBDIRECTORIES.items()
                ],
                "registry": {
                    "schema_version": "1",
                    "logical_digest": report.registry_digest,
                    "database_sha256": database_digest,
                    "path": DATABASE_PATH.relative_to(ROOT).as_posix(),
                },
            }
            staged_lock = staging_dir / LOCK_PATH.name
            _write_json_atomic(staged_lock, lock)
            _replace_registry_bundle(staged_database, staged_lock, staging_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Protocol registry update failed: {exc}", file=sys.stderr)
        return 1
    print(f"Protocol sources: {', '.join(SOURCE_SUBDIRECTORIES)}")
    print(f"Protocol repository: {remote}@{commit}")
    print(f"Protocol registry: {DATABASE_PATH}")
    print(f"Database SHA-256: {database_digest}")
    return 0


def _validate_source_repository(repository: Path) -> tuple[str, str]:
    if not (repository / ".git").is_dir():
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


def _replace_registry_bundle(staged_database: Path, staged_lock: Path, staging_dir: Path) -> None:
    database_backup = staging_dir / "previous-registry.sqlite"
    lock_backup = staging_dir / "previous-registry.lock.json"
    if DATABASE_PATH.is_file():
        shutil.copy2(DATABASE_PATH, database_backup)
    if LOCK_PATH.is_file():
        shutil.copy2(LOCK_PATH, lock_backup)
    try:
        os.replace(staged_database, DATABASE_PATH)
        os.replace(staged_lock, LOCK_PATH)
    except OSError:
        if database_backup.is_file():
            os.replace(database_backup, DATABASE_PATH)
        else:
            DATABASE_PATH.unlink(missing_ok=True)
        if lock_backup.is_file():
            os.replace(lock_backup, LOCK_PATH)
        else:
            LOCK_PATH.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
