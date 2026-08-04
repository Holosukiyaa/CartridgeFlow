"""Atomic developer-owned storage for trusted node preset revisions."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from threading import RLock

from core.protocol.trusted_node_recipes import creator_preset_projection, preset_digest, validate_preset
from core.protocol.tuning import TuningProtocolError, canonical_digest
from core.studio.authoring_service import AuthoringServiceError


class TrustedNodePresetStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def put(self, preset: dict, *, expected_revision: int | None = None) -> dict:
        try:
            item = validate_preset(preset)
        except TuningProtocolError as exc:
            raise AuthoringServiceError("TRUSTED_NODE_PRESET_INVALID", str(exc)) from exc
        with self._lock:
            path = self._path(item["id"])
            state = self._read(path) if path.exists() else None
            current = state["current"]["revision"] if state else 0
            if expected_revision is not None and expected_revision != current:
                raise AuthoringServiceError("TRUSTED_NODE_PRESET_REVISION_CONFLICT", "Trusted node preset revision is stale.", status=409)
            if item["revision"] != current + 1:
                raise AuthoringServiceError("TRUSTED_NODE_PRESET_REVISION_INVALID", "Trusted node preset revision must advance by one.", status=409)
            revision = {**deepcopy(item), "digest": preset_digest(item)}
            revisions = [*(state["revisions"] if state else []), revision]
            body = {"schema": "cartridgeflow.trusted_node_registry_entry.v1", "id": item["id"], "current": revision, "revisions": revisions}
            body["digest"] = canonical_digest(body)
            self._write(path, body)
            return deepcopy(revision)

    def list_developer(self) -> list[dict]:
        with self._lock:
            return [deepcopy(self._read(path)["current"]) for path in sorted(self.root.glob("*.json"))]

    def list_creator(self) -> list[dict]:
        return [creator_preset_projection(item) for item in self.list_developer()]

    def get(self, preset_id: str, revision: int | None = None) -> dict:
        with self._lock:
            path = self._path(preset_id)
            if not path.exists():
                raise AuthoringServiceError("TRUSTED_NODE_PRESET_UNKNOWN", "Trusted node preset was not found.", status=404)
            state = self._read(path)
            if revision is None:
                return deepcopy(state["current"])
            item = next((value for value in state["revisions"] if value["revision"] == revision), None)
            if item is None:
                raise AuthoringServiceError("TRUSTED_NODE_PRESET_REVISION_UNKNOWN", "Trusted node preset revision was not found.", status=404)
            return deepcopy(item)

    def _path(self, preset_id: str) -> Path:
        if not isinstance(preset_id, str) or not preset_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in preset_id):
            raise AuthoringServiceError("TRUSTED_NODE_PRESET_ID_INVALID", "Trusted node preset id is invalid.")
        return self.root / f"{preset_id}.json"

    @staticmethod
    def _read(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthoringServiceError("TRUSTED_NODE_PRESET_STORE_INVALID", "Trusted node preset storage is invalid.", status=500) from exc
        body = {key: value[key] for key in value if key != "digest"}
        if value.get("digest") != canonical_digest(body):
            raise AuthoringServiceError("TRUSTED_NODE_PRESET_STORE_INVALID", "Trusted node preset storage integrity check failed.", status=500)
        return value

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        pending = path.with_suffix(".tmp")
        pending.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        pending.replace(path)
