import re
from pathlib import Path

from core.data_paths import RUNS_DIR


class ArtifactManager:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def create_text_artifact(
        self,
        run: dict,
        run_dir: Path,
        artifact_id: str,
        name: str,
        content: str,
        artifact_type: str = "text",
        mime_type: str = "text/plain",
    ) -> dict:
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_filename(name)
        path = artifacts_dir / safe_name
        path.write_text(content, encoding="utf-8")
        return self.make_artifact(run, artifact_id, safe_name, path, artifact_type, mime_type)

    def make_artifact(
        self,
        run: dict,
        artifact_id: str,
        name: str,
        path: Path,
        artifact_type: str,
        mime_type: str,
    ) -> dict:
        resolved = path.resolve()
        artifacts_root = self._run_artifacts_dir(run)
        if resolved != artifacts_root and artifacts_root not in resolved.parents:
            raise ValueError("Artifact path escapes the current run")
        return {
            "artifact_id": artifact_id,
            "run_id": run["run_id"],
            "type": artifact_type,
            "name": name,
            "path": str(resolved),
            "url": f"/artifacts/{run['run_id']}/{name}",
            "mime_type": mime_type,
            "visibility": "user",
            "source": {"runtime": (run.get("runtime") or {}).get("type", "none")},
        }

    def resolve_artifact_path(self, run: dict, filename: str) -> Path:
        for artifact in run.get("artifacts", []):
            if artifact.get("name") != filename:
                continue
            return self.resolve_artifact_record_path(run, artifact)
        raise FileNotFoundError("Artifact not found")

    def resolve_artifact_record_path(self, run: dict, artifact: dict) -> Path:
        path = Path(str(artifact.get("path") or ""))
        if not path.is_absolute():
            path = self.root / path
        resolved = path.resolve()
        artifacts_root = self._run_artifacts_dir(run)
        if resolved != artifacts_root and artifacts_root not in resolved.parents:
            raise ValueError("Invalid artifact path")
        if not resolved.is_file():
            raise FileNotFoundError("Artifact file not found")
        return resolved

    def _run_artifacts_dir(self, run: dict) -> Path:
        run_id = str(run.get("run_id") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id) or run_id in {".", ".."}:
            raise ValueError("Invalid run id")
        runs_root = (self.root / RUNS_DIR).resolve()
        target = (runs_root / run_id / "artifacts").resolve()
        if target == runs_root or runs_root not in target.parents:
            raise ValueError("Invalid run id")
        return target

    def _safe_filename(self, name: str) -> str:
        return "".join(ch for ch in name if ch.isalnum() or ch in "._-") or "artifact.txt"
