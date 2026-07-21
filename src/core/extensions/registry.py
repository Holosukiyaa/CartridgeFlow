from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import uuid

from .descriptor import load_portable_dlc_descriptor
from .worker_client import run_worker_call


class PortableDlcToolProxy:
    def __init__(self, registry, descriptor: dict, tool: dict):
        self.registry = registry
        self.descriptor = descriptor
        self.tool = tool

    def __call__(self, params: dict) -> dict:
        package = Path(self.descriptor["_package_path"])
        if not package.is_dir():
            return {"ok": False, "code": "extension_inactive", "error": "Cartridge DLC package is unavailable"}
        request = {
            "schema": "cartridgeflow.dlc_worker_request.v1",
            "request_id": f"worker_{uuid.uuid4().hex[:16]}",
            "run_id": str(params.get("_runtime_run_id") or "") if isinstance(params, dict) else "",
            "cartridge_id": self.descriptor.get("owner_cartridge"),
            "dlc_id": self.descriptor.get("id"),
            "dlc_version": self.descriptor.get("version"),
            "server": self.tool["server"],
            "tool": self.tool["tool"],
            "params": params if isinstance(params, dict) else {},
        }
        return run_worker_call(
            self.registry._workspace_root,
            package,
            self.descriptor,
            request,
            timeout_ms=int(self.tool["timeout_ms"]),
            worker_call_id=request["request_id"],
            journal_dir=self.registry._worker_journal_dir,
        )


def register_package_dlc(registry, package_path: str | Path | None, manifest: dict | None) -> dict | None:
    manifest = manifest if isinstance(manifest, dict) else {}
    if not package_path or not manifest.get("portable_dlc"):
        return None
    descriptor = load_portable_dlc_descriptor(package_path, manifest)
    registered = []
    for tool in descriptor.get("tools") or []:
        server = tool["server"]
        name = tool["tool"]
        server_tools = registry._registry.setdefault(server, {})
        if name in server_tools:
            raise ValueError(f"portable DLC tool conflicts with existing tool: {server}/{name}")
        server_tools[name] = PortableDlcToolProxy(registry, descriptor, tool)
        registry._extension_tool_descriptions[(server, name)] = {
            "description": tool.get("description", ""),
            "params": deepcopy(tool.get("params") or {}),
        }
        registry._tool_dlc[name] = {
            "id": descriptor.get("id"),
            "kind": "dlc",
            "protocol": descriptor.get("_protocol"),
            "owner_cartridge": descriptor.get("owner_cartridge"),
            "scope": "cartridge",
            "isolated_worker": True,
        }
        registered.append(f"{server}/{name}")

    report = {
        "id": descriptor.get("id"),
        "version": descriptor.get("version"),
        "owner_cartridge": descriptor.get("owner_cartridge"),
        "kind": "dlc",
        "protocol": descriptor.get("_protocol"),
        "load_status": "enabled",
        "scope": "cartridge",
        "descriptor_sha256": descriptor.get("_descriptor_sha256"),
        "isolated_worker": True,
        "frontend_sandbox": (descriptor.get("frontend") or {}).get("sandbox"),
        "tools": registered,
    }
    registry._dlc_report.append(report)
    registry._package_dlc_descriptor = descriptor
    return report
