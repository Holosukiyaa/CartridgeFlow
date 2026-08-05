"""Portable DLC worker entry; execution remains cartridge-scoped."""

from core.extensions.worker_sdk import DlcWorkerRegistry


def invoke(request: dict) -> dict:
    registry = DlcWorkerRegistry(request["workspace_root"], request["package_path"])
    return registry.call(request.get("server", ""), request.get("tool", ""), request.get("params") or {})
