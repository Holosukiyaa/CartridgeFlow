"""Durable node checkpoints used for retry, resume, and rollback."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


CHECKPOINT_SCHEMA = "cartridgeflow.run_checkpoint.v1"
CHECKPOINT_INDEX_SCHEMA = "cartridgeflow.run_checkpoint_index.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class CheckpointManager:
    def save(
        self,
        run_dir: str | Path,
        run: dict,
        state_doc: dict,
        *,
        node_id: str,
        phase: str,
        outcome: str,
        replay: dict | None = None,
        event_snapshot: dict | None = None,
    ) -> dict:
        if phase not in {"before", "after"}:
            raise ValueError("Checkpoint phase must be before or after")
        root = Path(run_dir)
        directory = root / "checkpoints"
        directory.mkdir(parents=True, exist_ok=True)
        index_path = directory / "index.json"
        index = self._read_index(index_path)
        revision = int(index.get("revision") or 0) + 1
        checkpoint_id = f"cp_{revision:05d}_{uuid.uuid4().hex[:8]}"
        safe_node = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(node_id or "node"))[:80] or "node"
        filename = f"{revision:05d}-{safe_node}-{phase}.json"
        store = ((state_doc.get("context") or {}).get("store") or {}) if isinstance(state_doc, dict) else {}
        prior_items = [item for item in index.get("items") or [] if isinstance(item, dict)]
        state_snapshot = deepcopy(state_doc)
        if phase == "after":
            for item in reversed(state_snapshot.get("history") or []):
                if item.get("state") == node_id and item.get("completed_at") is None:
                    item["completed_at"] = utc_now()
                    item["status"] = outcome
                    break
            state_snapshot["current_state"] = node_id
            state_snapshot["status"] = outcome
            state_snapshot["updated_at"] = utc_now()
        checkpoint = {
            "schema": CHECKPOINT_SCHEMA,
            "checkpoint_id": checkpoint_id,
            "revision": revision,
            "run_id": run.get("run_id"),
            "node_id": node_id,
            "phase": phase,
            "outcome": outcome,
            "created_at": utc_now(),
            "store_sha256": _stable_hash(store),
            "input_summary": _summarize_store(store),
            "upstream_revisions": _upstream_revisions(state_doc, prior_items, node_id),
            "history_length": len(state_doc.get("history") or []),
            "artifact_ids": [str(item.get("artifact_id") or item.get("name") or "") for item in run.get("artifacts") or [] if isinstance(item, dict)],
            "replay": replay or {},
            "event_snapshot": deepcopy(event_snapshot) if isinstance(event_snapshot, dict) else None,
            "run_snapshot": deepcopy(run),
            "state_snapshot": state_snapshot,
        }
        self._write_json_atomic(directory / filename, checkpoint)
        summary = {
            "checkpoint_id": checkpoint_id,
            "revision": revision,
            "node_id": node_id,
            "phase": phase,
            "outcome": outcome,
            "created_at": checkpoint["created_at"],
            "path": f"checkpoints/{filename}",
            "replay": replay or {},
            "event_id": str((event_snapshot or {}).get("event_id") or ""),
        }
        items = prior_items
        items.append(summary)
        index = {
            "schema": CHECKPOINT_INDEX_SCHEMA,
            "run_id": run.get("run_id"),
            "revision": revision,
            "latest_checkpoint_id": checkpoint_id,
            "items": items,
        }
        self._write_json_atomic(index_path, index)
        return summary

    def list(self, run_dir: str | Path) -> list[dict]:
        index = self._read_index(Path(run_dir) / "checkpoints" / "index.json")
        return [dict(item) for item in index.get("items") or [] if isinstance(item, dict)]

    def load(self, run_dir: str | Path, checkpoint_id: str) -> dict:
        root = Path(run_dir)
        summary = next((item for item in self.list(root) if item.get("checkpoint_id") == checkpoint_id), None)
        if not summary:
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")
        target = (root / str(summary["path"])).resolve()
        if root.resolve() not in target.parents or not target.is_file():
            raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_id}")
        data = json.loads(target.read_text(encoding="utf-8"))
        if data.get("schema") != CHECKPOINT_SCHEMA:
            raise ValueError(f"Invalid checkpoint schema: {checkpoint_id}")
        return data

    def latest(self, run_dir: str | Path, *, phase: str | None = None, outcome: str | None = None, node_id: str | None = None) -> dict | None:
        items = self.list(run_dir)
        for item in reversed(items):
            if phase and item.get("phase") != phase:
                continue
            if outcome and item.get("outcome") != outcome:
                continue
            if node_id and item.get("node_id") != node_id:
                continue
            return item
        return None

    def _read_index(self, path: Path) -> dict:
        if not path.is_file():
            return {"schema": CHECKPOINT_INDEX_SCHEMA, "revision": 0, "items": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {"schema": CHECKPOINT_INDEX_SCHEMA, "revision": 0, "items": []}
        return data if data.get("schema") == CHECKPOINT_INDEX_SCHEMA else {"schema": CHECKPOINT_INDEX_SCHEMA, "revision": 0, "items": []}

    def _write_json_atomic(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)


def _stable_hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _summarize_store(store: dict) -> dict:
    summary = {}
    for key, value in store.items() if isinstance(store, dict) else []:
        try:
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            payload = str(value)
        summary[str(key)] = {
            "type": type(value).__name__,
            "size": len(payload.encode("utf-8")),
            "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }
    return summary


def _upstream_revisions(state_doc: dict, prior_items: list[dict], node_id: str) -> list[dict]:
    after_by_node = {}
    for item in prior_items:
        if item.get("phase") == "after" and item.get("node_id") and item.get("outcome") == "completed":
            after_by_node[str(item["node_id"])] = item
    revisions = []
    for history in state_doc.get("history") or []:
        if not isinstance(history, dict) or history.get("state") == node_id or history.get("status") != "completed":
            continue
        summary = after_by_node.get(str(history.get("state")))
        if summary:
            revisions.append({
                "node_id": str(history.get("state")),
                "checkpoint_id": summary.get("checkpoint_id"),
                "revision": summary.get("revision"),
                "event_id": summary.get("event_id", ""),
            })
    return revisions
