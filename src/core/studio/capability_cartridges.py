"""Immutable trusted capability-cartridge registry."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from threading import RLock

from core.protocol.capability_cartridges import (
    CapabilityCartridgeError,
    creator_capability_projection,
    validate_capability_release,
)
from core.protocol.tuning import canonical_digest
from core.studio.authoring_service import AuthoringServiceError


class CapabilityCartridgeStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def put(self, release: dict, *, expected_revision: int | None = None) -> dict:
        try:
            item = validate_capability_release(release)
        except CapabilityCartridgeError as exc:
            raise AuthoringServiceError("CAPABILITY_RELEASE_INVALID", str(exc)) from exc
        with self._lock:
            path = self._path(item["id"])
            state = self._read(path) if path.exists() else None
            latest = max((entry["revision"] for entry in state["revisions"]), default=0) if state else 0
            if expected_revision is not None and expected_revision != latest:
                raise AuthoringServiceError("CAPABILITY_RELEASE_REVISION_CONFLICT", "Capability release revision is stale.", status=409)
            if item["revision"] != latest + 1:
                raise AuthoringServiceError("CAPABILITY_RELEASE_REVISION_INVALID", "Capability release revision must advance by one.", status=409)
            self._validate_dependencies(item)
            revisions = [*(state["revisions"] if state else []), deepcopy(item)]
            body = {
                "schema": "cartridgeflow.capability_cartridge_registry_entry.v1",
                "id": item["id"],
                "status": "active",
                "active_revision": item["revision"],
                "current": deepcopy(item),
                "revisions": revisions,
            }
            body["digest"] = canonical_digest(body)
            self._write(path, body)
            return deepcopy(item)

    def list_active(self) -> list[dict]:
        with self._lock:
            return [
                deepcopy(state["current"])
                for path in sorted(self.root.glob("*.json"))
                if (state := self._read(path)).get("status") == "active"
            ]

    def list_creator(self) -> list[dict]:
        return [creator_capability_projection(item) for item in self.list_active()]

    def list_entries(self) -> list[dict]:
        with self._lock:
            return [deepcopy(self._read(path)) for path in sorted(self.root.glob("*.json"))]

    def get(self, capability_id: str, revision: int | None = None) -> dict:
        with self._lock:
            path = self._path(capability_id)
            if not path.exists():
                raise AuthoringServiceError("CAPABILITY_RELEASE_UNKNOWN", "Capability release was not found.", status=404)
            state = self._read(path)
            if revision is None:
                return deepcopy(state["current"])
            release = next((item for item in state["revisions"] if item["revision"] == revision), None)
            if release is None:
                raise AuthoringServiceError("CAPABILITY_RELEASE_REVISION_UNKNOWN", "Capability release revision was not found.", status=404)
            return deepcopy(release)

    def latest_revision(self, capability_id: str) -> int:
        with self._lock:
            path = self._path(capability_id)
            if not path.exists():
                return 0
            return max(item["revision"] for item in self._read(path)["revisions"])

    def set_activation(self, capability_id: str, *, active: bool, revision: int | None = None) -> dict:
        with self._lock:
            path = self._path(capability_id)
            if not path.exists():
                raise AuthoringServiceError("CAPABILITY_RELEASE_UNKNOWN", "Capability release was not found.", status=404)
            state = self._read(path)
            if active:
                target_revision = revision or max(item["revision"] for item in state["revisions"])
                target = next((item for item in state["revisions"] if item["revision"] == target_revision), None)
                if target is None:
                    raise AuthoringServiceError("CAPABILITY_RELEASE_REVISION_UNKNOWN", "Capability release revision was not found.", status=404)
                state["current"] = deepcopy(target)
                state["active_revision"] = target_revision
                state["status"] = "active"
            else:
                state["status"] = "inactive"
            state["digest"] = canonical_digest({key: value for key, value in state.items() if key != "digest"})
            self._write(path, state)
            return deepcopy(state)

    def dependency_closure(self, roots: list[dict]) -> list[dict]:
        """Resolve exact immutable refs, rejecting missing releases and cycles."""
        result: dict[tuple[str, int], dict] = {}
        visiting: set[tuple[str, int]] = set()

        def visit(ref: dict) -> None:
            key = (str(ref.get("id") or ""), int(ref.get("revision") or 0))
            if key in visiting:
                raise AuthoringServiceError("CAPABILITY_DEPENDENCY_CYCLE", "Capability dependency graph contains a cycle.", status=409)
            if key in result:
                if result[key]["digest"] != ref.get("digest"):
                    raise AuthoringServiceError("CAPABILITY_DEPENDENCY_CONFLICT", "A capability revision was pinned with two digests.", status=409)
                return
            release = self.get(key[0], key[1])
            if release["digest"] != ref.get("digest"):
                raise AuthoringServiceError("CAPABILITY_DEPENDENCY_DIGEST_MISMATCH", "Capability dependency digest no longer matches its immutable release.", status=409)
            visiting.add(key)
            for dependency in release.get("dependencies") or []:
                visit(dependency)
            visiting.remove(key)
            result[key] = release

        for root in roots:
            visit(root)
        return [result[key] for key in sorted(result)]

    def _validate_dependencies(self, release: dict) -> None:
        for ref in release.get("dependencies") or []:
            dependency = self.get(ref["id"], ref["revision"])
            if dependency["digest"] != ref["digest"]:
                raise AuthoringServiceError("CAPABILITY_DEPENDENCY_DIGEST_MISMATCH", "Capability dependency digest is invalid.", status=409)
            if release["trust_scope"] == "system" and dependency["trust_scope"] != "system":
                raise AuthoringServiceError("CAPABILITY_DEPENDENCY_TRUST_INVALID", "System capabilities may only depend on system-trusted releases.", status=409)
            if release["trust_scope"] == "organization" and dependency["trust_scope"] == "workspace":
                raise AuthoringServiceError("CAPABILITY_DEPENDENCY_TRUST_INVALID", "Organization capabilities may not depend on workspace-only releases.", status=409)
        if release.get("dependencies"):
            self.dependency_closure(release["dependencies"])

    def _path(self, capability_id: str) -> Path:
        if not isinstance(capability_id, str) or not capability_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in capability_id):
            raise AuthoringServiceError("CAPABILITY_RELEASE_IDENTITY_INVALID", "Capability id is invalid.")
        return self.root / f"{capability_id}.json"

    @staticmethod
    def _read(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthoringServiceError("CAPABILITY_REGISTRY_INVALID", "Capability registry storage is invalid.", status=500) from exc
        body = {key: value[key] for key in value if key != "digest"}
        if value.get("schema") != "cartridgeflow.capability_cartridge_registry_entry.v1" or value.get("digest") != canonical_digest(body):
            raise AuthoringServiceError("CAPABILITY_REGISTRY_INVALID", "Capability registry integrity check failed.", status=500)
        for release in value.get("revisions") or []:
            try:
                validate_capability_release(release)
            except CapabilityCartridgeError as exc:
                raise AuthoringServiceError("CAPABILITY_REGISTRY_INVALID", str(exc), status=500) from exc
        return value

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        pending = path.with_suffix(".tmp")
        pending.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        pending.replace(path)
