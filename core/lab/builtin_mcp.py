"""Base-owned MCP registry and cartridge-scoped Portable DLC host."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path


FILESYSTEM_DESCRIPTIONS = {
    "read_file": {"description": "Read UTF-8 text from one or more workspace files.", "params": {"path": "Workspace-relative path, comma or newline separated."}},
    "write_file": {"description": "Write UTF-8 text to a workspace file.", "params": {"path": "Workspace-relative path.", "content": "Text content."}},
    "append_file": {"description": "Append UTF-8 text to a workspace file.", "params": {"path": "Workspace-relative path.", "content": "Text content."}},
    "list_dir": {"description": "List a workspace directory.", "params": {"path": "Workspace-relative directory."}},
    "exists": {"description": "Check whether a workspace path exists.", "params": {"path": "Workspace-relative path."}},
}

MEDIA_DESCRIPTIONS = {
    "media_probe": {
        "description": "Probe explicitly requested local media providers.",
        "params": {"providers": "Provider list.", "comfyui_url": "Optional ComfyUI URL.", "timeout": "Probe timeout in seconds."},
    },
    "extract_keyframes": {
        "description": "Extract reusable control keyframes from a rendered frame sequence.",
        "params": {"render_bundle": "Render bundle.", "frame_dir": "Source frames.", "output_dir": "Artifact directory."},
    },
    "style_keyframes": {
        "description": "Apply a configured image workflow to control keyframes.",
        "params": {"input_manifest": "Control manifest.", "provider": "Configured provider.", "workflow_path": "Workflow path.", "output_dir": "Artifact directory."},
    },
    "remote_upgrade_keyframes": {
        "description": "Extract, upgrade, and validate keyframes through one configured media channel.",
        "params": {"render_bundle": "Render bundle.", "provider": "Configured provider.", "workflow_path": "Workflow path.", "output_dir": "Artifact directory."},
    },
    "qc_outputs": {
        "description": "Validate a media output manifest and write a structured QC report.",
        "params": {"input_manifest": "Media manifest.", "output_path": "QC report path.", "min_outputs": "Required output count."},
    },
}


class BuiltinMcpRegistry:
    """Registry containing base tools plus one explicitly scoped cartridge DLC."""

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        *,
        package_path: str | Path | None = None,
        manifest: dict | None = None,
        protocol_extensions=None,
        capabilities=None,
        supported_protocols=None,
    ):
        self._workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self._package_path = Path(package_path).resolve() if package_path else None
        self._manifest = manifest if isinstance(manifest, dict) else {}
        self._protocol_extensions = protocol_extensions
        self._capabilities = capabilities
        self._supported_protocols = supported_protocols
        self._registry: dict[str, dict[str, callable]] = {}
        self._tool_dlc: dict[str, dict] = {}
        self._extension_tool_descriptions: dict[tuple[str, str], dict] = {}
        self._package_dlc_descriptor: dict | None = None
        self._dlc_report: list[dict] = []
        self._register_filesystem()
        self._register_media()
        self._register_package_dlc()

    @classmethod
    def for_manifest(
        cls,
        workspace_root: str | Path | None,
        manifest: dict,
        capabilities=None,
        supported_protocols=None,
        package_path: str | Path | None = None,
    ):
        manifest = manifest if isinstance(manifest, dict) else {}
        return cls(
            workspace_root,
            package_path=package_path,
            manifest=manifest,
            protocol_extensions=manifest.get("protocol_extensions") or [],
            capabilities=capabilities,
            supported_protocols=supported_protocols,
        )

    def _register_package_dlc(self) -> None:
        from core.extensions import register_package_dlc

        register_package_dlc(self, self._package_path, self._manifest)

    def _safe_path(self, path_str: str) -> Path:
        source = Path(str(path_str or ""))
        candidate = source.resolve() if source.is_absolute() else (self._workspace_root / source).resolve()
        if candidate != self._workspace_root and self._workspace_root not in candidate.parents:
            raise PermissionError(f"Path escapes workspace: {path_str}")
        return candidate

    def _register_filesystem(self) -> None:
        def read_file(params: dict) -> dict:
            raw = str(params.get("path") or "").strip()
            if not raw:
                return {"ok": False, "error": "path is required"}
            try:
                items = [item.strip() for item in raw.replace("\r", "\n").replace(",", "\n").split("\n") if item.strip()]
                chunks = []
                total = 0
                for item in items:
                    target = self._safe_path(item)
                    if not target.is_file():
                        return {"ok": False, "error": f"File not found: {item}"}
                    content = target.read_text(encoding="utf-8", errors="replace")
                    total += len(content)
                    chunks.append(content if len(items) == 1 else f"--- FILE: {item} ---\n{content}")
                return {"ok": True, "path": items[0] if len(items) == 1 else items, "content": "\n\n".join(chunks), "size": total, "count": len(items)}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        def write_file(params: dict) -> dict:
            raw = str(params.get("path") or "").strip()
            if not raw:
                return {"ok": False, "error": "path is required"}
            try:
                target = self._safe_path(raw)
                target.parent.mkdir(parents=True, exist_ok=True)
                content = str(params.get("content") or "")
                target.write_text(content, encoding="utf-8")
                return {"ok": True, "path": str(target), "written": len(content)}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        def append_file(params: dict) -> dict:
            raw = str(params.get("path") or "").strip()
            if not raw:
                return {"ok": False, "error": "path is required"}
            try:
                target = self._safe_path(raw)
                target.parent.mkdir(parents=True, exist_ok=True)
                content = str(params.get("content") or "")
                with target.open("a", encoding="utf-8") as handle:
                    handle.write(content)
                return {"ok": True, "path": str(target), "appended": len(content)}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        def list_dir(params: dict) -> dict:
            try:
                target = self._safe_path(str(params.get("path") or "."))
                if not target.is_dir():
                    return {"ok": False, "error": f"Directory not found: {target}"}
                entries = [{"name": item.name, "type": "dir" if item.is_dir() else "file", "size": item.stat().st_size if item.is_file() else None} for item in sorted(target.iterdir())]
                return {"ok": True, "path": str(target), "entries": entries, "count": len(entries)}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        def exists(params: dict) -> dict:
            raw = str(params.get("path") or "").strip()
            if not raw:
                return {"ok": False, "error": "path is required"}
            try:
                target = self._safe_path(raw)
                return {"ok": True, "path": str(target), "exists": target.exists(), "is_file": target.is_file(), "is_dir": target.is_dir()}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        self._registry["filesystem"] = {
            "read_file": read_file,
            "write_file": write_file,
            "append_file": append_file,
            "list_dir": list_dir,
            "exists": exists,
        }

    def _register_media(self) -> None:
        from .mcp.dlc import register_media_modules

        self._registry.setdefault("media", {})
        register_media_modules(
            self,
            protocol_extensions=self._protocol_extensions,
            capabilities=self._capabilities,
            supported_protocols=self._supported_protocols,
        )

    def call(self, server: str, tool: str, params: dict) -> dict:
        tools = self._registry.get(server)
        if not tools:
            return {"ok": False, "error": f"Unknown builtin server: {server}"}
        handler = tools.get(tool)
        if handler is None:
            return {"ok": False, "error": f"Unknown builtin tool: {server}/{tool}"}
        return handler(params if isinstance(params, dict) else {})

    def list_tools(self) -> dict:
        return {server: list(tools) for server, tools in self._registry.items()}

    def dlc_report(self) -> list[dict]:
        return deepcopy(self._dlc_report)

    def describe(self) -> list[dict]:
        descriptions = {"filesystem": FILESYSTEM_DESCRIPTIONS, "media": MEDIA_DESCRIPTIONS}
        result = []
        for server, tools in self._registry.items():
            for tool_name in tools:
                meta = descriptions.get(server, {}).get(tool_name, {}) or self._extension_tool_descriptions.get((server, tool_name), {})
                item = {"server": server, "tool": tool_name, "type": "builtin", "description": meta.get("description", ""), "params": meta.get("params", {})}
                if tool_name in self._tool_dlc:
                    item["dlc"] = self._tool_dlc[tool_name]
                result.append(item)
        return result
