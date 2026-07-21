from pathlib import Path


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
        root = self.root.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError("Artifact path escapes project root")
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
            path = Path(artifact.get("path", ""))
            if not path.is_absolute():
                path = self.root / path
            resolved = path.resolve()
            root = self.root.resolve()
            if resolved != root and root not in resolved.parents:
                raise ValueError("Invalid artifact path")
            if not resolved.is_file():
                raise FileNotFoundError("Artifact file not found")
            return resolved
        raise FileNotFoundError("Artifact not found")

    def _safe_filename(self, name: str) -> str:
        return "".join(ch for ch in name if ch.isalnum() or ch in "._-") or "artifact.txt"
