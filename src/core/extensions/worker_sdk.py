from __future__ import annotations

from pathlib import Path


class DlcWorkerRegistry:
    """Minimal stable SDK surface exposed inside an isolated DLC worker."""

    def __init__(self, workspace_root: str | Path, package_root: str | Path):
        self._workspace_root = Path(workspace_root).resolve()
        self._package_root = Path(package_root).resolve()
        self._registry: dict[str, dict[str, callable]] = {}

    def _safe_path(self, path_str: str) -> Path:
        path = Path(str(path_str or ""))
        candidate = path.resolve() if path.is_absolute() else (self._workspace_root / path).resolve()
        if candidate != self._workspace_root and self._workspace_root not in candidate.parents:
            raise PermissionError(f"path escapes workspace: {path_str}")
        return candidate

    def package_path(self, relative_path: str) -> Path:
        candidate = (self._package_root / str(relative_path or "")).resolve()
        if candidate != self._package_root and self._package_root not in candidate.parents:
            raise PermissionError(f"path escapes cartridge package: {relative_path}")
        return candidate

    def call(self, server: str, tool: str, params: dict) -> dict:
        handler = self._registry.get(server, {}).get(tool)
        if handler is None:
            return {"ok": False, "code": "dlc_tool_unavailable", "error": f"DLC tool not found: {server}/{tool}"}
        return handler(params)
