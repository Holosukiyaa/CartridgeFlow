from __future__ import annotations

from core.extensions.worker_sdk import DlcWorkerRegistry

from .mcp import series_3d, storyboard


def invoke(request: dict) -> dict:
    registry = DlcWorkerRegistry(request["workspace_root"], request["package_path"])
    registry._registry.setdefault("media", {})
    series_3d.register(registry)
    storyboard.register(registry)
    return registry.call(
        str(request.get("server") or ""),
        str(request.get("tool") or ""),
        request.get("params") if isinstance(request.get("params"), dict) else {},
    )
