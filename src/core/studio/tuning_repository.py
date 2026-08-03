from __future__ import annotations

import json
import re
from pathlib import Path
from threading import RLock

from core.cartridge.validator import resolve_package_entry
from core.data_paths import DEV_CARTRIDGES_DIR, FLOW_TUNING_DIR
from core.protocol.tuning import (
    TUNING_RELEASE_SCHEMA,
    TuningProtocolError,
    activate_recipe_release,
    create_node_revision,
    create_tuning_repository,
    materialize_tuning,
    publish_recipe_release,
    validate_tuning_release,
    validate_tuning_repository,
)


class TuningRepositoryStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.directory = self.root / FLOW_TUNING_DIR
        self.dev_directory = self.root / DEV_CARTRIDGES_DIR
        self._write_lock = RLock()
        self.directory.mkdir(parents=True, exist_ok=True)

    def initialize(self, flow_id: str, root_flow: dict) -> dict:
        with self._write_lock:
            path = self._repository_path(flow_id)
            if path.is_file():
                return self.load(flow_id, root_flow)
            repository = create_tuning_repository(flow_id, root_flow)
            self._write(path, repository)
            return repository

    def load(self, flow_id: str, root_flow: dict | None = None) -> dict:
        path = self._repository_path(flow_id)
        if not path.is_file():
            if root_flow is None:
                root_flow = self._load_root_flow(flow_id)
            return self.initialize(flow_id, root_flow)
        repository = json.loads(path.read_text(encoding="utf-8"))
        return validate_tuning_repository(repository, root_flow)

    def create_revision(
        self,
        flow_id: str,
        node_id: str,
        patch: dict,
        *,
        expected_head: str | None,
        author: str,
        message: str,
    ) -> tuple[dict, dict, dict, dict]:
        with self._write_lock:
            root_flow = self._load_root_flow(flow_id)
            repository = self.load(flow_id, root_flow)
            updated, revision = create_node_revision(
                repository,
                root_flow,
                node_id,
                patch,
                expected_head=expected_head,
                author=author,
                message=message,
            )
            self._write(self._repository_path(flow_id), updated)
            materialized, context = materialize_tuning(root_flow, updated, draft=True)
            return updated, revision, materialized, context

    def publish(self, flow_id: str, *, author: str, message: str) -> tuple[dict, dict]:
        with self._write_lock:
            root_flow = self._load_root_flow(flow_id)
            repository = self.load(flow_id, root_flow)
            updated, release = publish_recipe_release(repository, root_flow, author=author, message=message, activate=True)
            self._write_release(flow_id, release)
            self._write(self._repository_path(flow_id), updated)
            return updated, release

    def activate(self, flow_id: str, release_id: str) -> tuple[dict, dict]:
        with self._write_lock:
            root_flow = self._load_root_flow(flow_id)
            repository = self.load(flow_id, root_flow)
            updated, release = activate_recipe_release(repository, release_id)
            validate_tuning_release(release, root_flow)
            self._write_release(flow_id, release)
            self._write(self._repository_path(flow_id), updated)
            return updated, release

    def materialize_draft(self, flow_id: str, root_flow: dict) -> tuple[dict, dict]:
        repository = self.load(flow_id, root_flow)
        return materialize_tuning(root_flow, repository, draft=True)

    def retire_node_head(self, flow_id: str, node_id: str) -> dict:
        with self._write_lock:
            root_flow = self._load_root_flow(flow_id)
            repository = self.load(flow_id)
            if node_id not in repository["node_heads"]:
                return repository
            updated = json.loads(json.dumps(repository))
            updated["repository_revision"] += 1
            updated["node_heads"].pop(node_id, None)
            validate_tuning_repository(updated, root_flow)
            self._write(self._repository_path(flow_id), updated)
            return updated

    def reconcile_node_heads(self, flow_id: str, root_flow: dict) -> dict:
        with self._write_lock:
            repository = self.load(flow_id)
            states = root_flow.get("states") if isinstance(root_flow.get("states"), dict) else {}
            missing = sorted(set(repository["node_heads"]) - set(states))
            if not missing:
                return repository
            updated = json.loads(json.dumps(repository))
            updated["repository_revision"] += 1
            for node_id in missing:
                updated["node_heads"].pop(node_id, None)
            validate_tuning_repository(updated, root_flow)
            self._write(self._repository_path(flow_id), updated)
            return updated

    def materialize_published(self, flow_id: str, root_flow: dict) -> tuple[dict, dict]:
        release_path = self._release_path(flow_id)
        if not release_path.is_file():
            raise TuningProtocolError("published recipe release is missing")
        release = json.loads(release_path.read_text(encoding="utf-8"))
        return materialize_tuning(root_flow, release, draft=False)

    def release_summary(self, repository: dict) -> dict:
        return {
            "schema": repository["schema"],
            "protocol": repository["protocol"],
            "flow_id": repository["flow_id"],
            "repository_revision": repository["repository_revision"],
            "node_heads": repository["node_heads"],
            "revisions": repository["revisions"],
            "releases": repository["releases"],
            "active_release_id": repository["active_release_id"],
        }

    def delete(self, flow_id: str) -> None:
        with self._write_lock:
            path = self._repository_path(flow_id)
            if path.is_file():
                path.unlink()
            if path.parent.is_dir() and not any(path.parent.iterdir()):
                path.parent.rmdir()

    def _load_root_flow(self, flow_id: str) -> dict:
        path = self._flow_path(flow_id) / "root.flow.json"
        if not path.is_file():
            raise FileNotFoundError(f"Root flow not found: {flow_id}")
        root_flow = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(root_flow, dict):
            raise TuningProtocolError("root flow must be an object")
        return root_flow

    def _release_path(self, flow_id: str) -> Path:
        package = self._flow_path(flow_id)
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        contract = manifest.get("tuning_contract") if isinstance(manifest.get("tuning_contract"), dict) else {}
        if contract.get("protocol") != "CF-TUNING" or str(contract.get("protocol_version")) != "1.0":
            raise TuningProtocolError("manifest tuning contract is missing or unsupported")
        entry = str(contract.get("release_entry") or "tuning/release.json")
        return resolve_package_entry(package, entry, "manifest.tuning_contract.release_entry")

    def _write_release(self, flow_id: str, release: dict) -> None:
        if release.get("schema") != TUNING_RELEASE_SCHEMA:
            raise TuningProtocolError("cannot write an unknown tuning release")
        self._write(self._release_path(flow_id), release)

    def _repository_path(self, flow_id: str) -> Path:
        normalized = self._normalize_id(flow_id)
        return self.directory / normalized / "repository.json"

    def _flow_path(self, flow_id: str) -> Path:
        normalized = self._normalize_id(flow_id)
        path = (self.dev_directory / normalized).resolve()
        root = self.dev_directory.resolve()
        if path == root or root not in path.parents or not path.is_dir():
            raise FileNotFoundError(f"Dev flow not found: {flow_id}")
        return path

    @staticmethod
    def _normalize_id(flow_id: str) -> str:
        value = str(flow_id or "").strip()
        if not value or not re.fullmatch(r"[a-zA-Z0-9._-]+", value):
            raise TuningProtocolError("invalid flow id")
        return value

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        target = path.with_suffix(path.suffix + ".tmp")
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        target.replace(path)
