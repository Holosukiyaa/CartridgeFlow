from __future__ import annotations

import json
from pathlib import Path

from .governance_registry import ProtocolKnowledgeRegistry, ProtocolKnowledgeRegistryError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_RELATIVE_PATH = Path("config/protocol/protocol-registry.sqlite")
REGISTRY_LOCK_RELATIVE_PATH = Path("config/protocol/protocol-registry.lock.json")
DEFAULT_SOURCE_ID = "current"


def resolve_protocol_registry(root: str | Path | None = None) -> Path:
    candidate_root = Path(root).resolve() if root is not None else PROJECT_ROOT
    candidate = candidate_root / REGISTRY_RELATIVE_PATH
    if candidate.is_file():
        return candidate
    fallback = PROJECT_ROOT / REGISTRY_RELATIVE_PATH
    if fallback.is_file():
        return fallback
    raise ProtocolKnowledgeRegistryError(
        f"compiled protocol registry not found: {REGISTRY_RELATIVE_PATH.as_posix()}"
    )


class ProtocolArtifactStore:
    def __init__(self, root: str | Path | None = None, source_id: str | None = None):
        self.path = resolve_protocol_registry(root)
        self.source_id = source_id or _locked_runtime_source_id(root)

    def exists(self, artifact_path: str | Path) -> bool:
        with ProtocolKnowledgeRegistry(self.path) as registry:
            return registry.artifact_exists(self.source_id, _artifact_path(artifact_path))

    def read_bytes(self, artifact_path: str | Path) -> bytes:
        with ProtocolKnowledgeRegistry(self.path) as registry:
            return registry.artifact_bytes(self.source_id, _artifact_path(artifact_path))

    def read_text(self, artifact_path: str | Path) -> str:
        with ProtocolKnowledgeRegistry(self.path) as registry:
            return registry.artifact_text(self.source_id, _artifact_path(artifact_path))

    def read_json(self, artifact_path: str | Path) -> dict:
        with ProtocolKnowledgeRegistry(self.path) as registry:
            return registry.artifact_json(self.source_id, _artifact_path(artifact_path))

    def releases(self) -> list[dict]:
        with ProtocolKnowledgeRegistry(self.path) as registry:
            return registry.releases(self.source_id)


def load_protocol_artifact_text(
    artifact_path: str | Path,
    root: str | Path | None = None,
    source_id: str | None = None,
) -> str:
    return ProtocolArtifactStore(root, source_id).read_text(artifact_path)


def load_protocol_artifact_json(
    artifact_path: str | Path,
    root: str | Path | None = None,
    source_id: str | None = None,
) -> dict:
    return ProtocolArtifactStore(root, source_id).read_json(artifact_path)


def load_protocol_registry_lock(root: str | Path | None = None) -> dict:
    candidate_root = Path(root).resolve() if root is not None else PROJECT_ROOT
    path = candidate_root / REGISTRY_LOCK_RELATIVE_PATH
    if not path.is_file():
        path = PROJECT_ROOT / REGISTRY_LOCK_RELATIVE_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolKnowledgeRegistryError(
            f"protocol registry lock is missing or invalid: {REGISTRY_LOCK_RELATIVE_PATH.as_posix()}"
        ) from exc
    if not isinstance(value, dict):
        raise ProtocolKnowledgeRegistryError("protocol registry lock must be a JSON object")
    return value


def _locked_runtime_source_id(root: str | Path | None = None) -> str:
    value = load_protocol_registry_lock(root).get("runtime_source_id")
    if not isinstance(value, str) or not value.strip():
        raise ProtocolKnowledgeRegistryError(
            "protocol registry lock must declare runtime_source_id"
        )
    return value


def _artifact_path(value: str | Path) -> str:
    path = Path(value).as_posix().lstrip("./")
    return path if path.startswith("protocol/") or path.startswith("config/") else f"protocol/{path}"
