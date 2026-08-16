"""Server-backed Creator UI drafts kept separate from immutable authoring facts."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock


class CreatorWorkspaceError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400):
        self.code, self.status = code, status
        super().__init__(message)

    def as_dict(self) -> dict:
        return {"schema": "cartridgeflow.creator_workspace_error.v1", "code": self.code, "message": str(self)}


class CreatorWorkspaceStore:
    """Atomic, bounded storage for recoverable UI state and conversation context."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def get(self, project_id: str) -> dict | None:
        path = self._path(project_id)
        with self._lock:
            if not path.is_file():
                return None
            return deepcopy(json.loads(path.read_text(encoding="utf-8")))

    def save(self, project_id: str, snapshot: dict, *, expected_revision: int) -> dict:
        if expected_revision < 0:
            raise CreatorWorkspaceError("CREATOR_WORKSPACE_REVISION_INVALID", "Workspace revision must be non-negative.")
        normalized = self._normalize_snapshot(snapshot)
        path = self._path(project_id)
        with self._lock:
            current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
            current_revision = int((current or {}).get("revision") or 0)
            if current_revision != expected_revision:
                raise CreatorWorkspaceError(
                    "CREATOR_WORKSPACE_REVISION_CONFLICT",
                    "Workspace changed in another tab. Reload before saving again.",
                    status=409,
                )
            value = {
                "schema": "cartridgeflow.creator_workspace.v1",
                "project_id": project_id,
                "revision": current_revision + 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "snapshot": normalized,
            }
            self._write(path, value)
            return deepcopy(value)

    def delete(self, project_id: str) -> bool:
        path = self._path(project_id)
        with self._lock:
            if not path.is_file():
                return False
            path.unlink()
            return True

    def _path(self, project_id: str) -> Path:
        if not isinstance(project_id, str) or not project_id or len(project_id) > 200 or any(item in project_id for item in ("/", "\\", "..")):
            raise CreatorWorkspaceError("CREATOR_WORKSPACE_PROJECT_ID_INVALID", "Workspace project id is invalid.")
        return self.root / f"{project_id}.json"

    @classmethod
    def _normalize_snapshot(cls, value: dict) -> dict:
        if not isinstance(value, dict) or value.get("version") != 1:
            raise CreatorWorkspaceError("CREATOR_WORKSPACE_INVALID", "Workspace snapshot version is invalid.")
        messages = []
        for item in list(value.get("messages") or [])[-80:]:
            if not isinstance(item, dict) or item.get("role") not in {"assistant", "user"}:
                continue
            message = {
                "id": cls._text(item.get("id"), 200),
                "role": item["role"],
                "text": cls._text(item.get("text"), 12_000),
            }
            clarification = cls._clarification(item.get("clarification"))
            if clarification:
                message["clarification"] = clarification
            messages.append(message)
        possibilities = [
            item for item in (cls._possibility(raw) for raw in list(value.get("possibilities") or [])[:6]) if item
        ]
        package = value.get("packageResult") if isinstance(value.get("packageResult"), dict) else None
        package_result = None if package is None else {
            "schema": cls._text(package.get("schema"), 100),
            "status": cls._text(package.get("status"), 40),
            "filename": cls._text(package.get("filename"), 260),
            "url": cls._text(package.get("url"), 500),
            "signature_verified": bool(package.get("signature_verified")),
        }
        return {
            "version": 1,
            "goal": cls._text(value.get("goal"), 12_000),
            "messages": messages,
            "clarification": cls._clarification(value.get("clarification")),
            "possibilities": possibilities,
            "selectedId": cls._text(value.get("selectedId"), 200),
            "middleView": "detail" if value.get("middleView") == "detail" else "outline",
            "workspacePane": value.get("workspacePane") if value.get("workspacePane") in {"collaboration", "outline", "canvas"} else "collaboration",
            "packageResult": package_result,
            "packageRevision": value.get("packageRevision") if isinstance(value.get("packageRevision"), int) else None,
        }

    @classmethod
    def _clarification(cls, value: object) -> dict | None:
        if not isinstance(value, dict) or not str(value.get("question") or "").strip():
            return None
        return {
            "question": cls._text(value.get("question"), 2_000),
            "why_it_matters": cls._text(value.get("why_it_matters"), 2_000),
            "suggested_answers": [cls._text(item, 1_000) for item in list(value.get("suggested_answers") or [])[:8]],
        }

    @classmethod
    def _possibility(cls, value: object) -> dict | None:
        if not isinstance(value, dict) or not str(value.get("id") or "").strip():
            return None
        recipe = value.get("recipe") if isinstance(value.get("recipe"), dict) else {}
        steps = []
        for step in list(recipe.get("steps") or [])[:12]:
            if isinstance(step, dict) and str(step.get("id") or "").strip():
                steps.append({
                    "id": cls._text(step.get("id"), 200),
                    "intent": cls._text(step.get("intent"), 2_000),
                    "inputs": [],
                    "outputs": [],
                })
        return {
            "id": cls._text(value.get("id"), 200),
            "title": cls._text(value.get("title"), 1_000),
            "outcome": cls._text(value.get("outcome"), 2_000),
            "why_it_fits": cls._text(value.get("why_it_fits"), 2_000),
            "first_week_output": cls._text(value.get("first_week_output"), 2_000),
            "needs_confirmation": [cls._text(item, 1_000) for item in list(value.get("needs_confirmation") or [])[:8]],
            "recipe": {"intent": cls._text(recipe.get("intent"), 4_000), "steps": steps},
        }

    @staticmethod
    def _text(value: object, limit: int) -> str:
        return str(value or "")[:limit]

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
