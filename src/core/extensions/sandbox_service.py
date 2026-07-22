"""Lifecycle manager for dedicated sandbox renderer processes."""

from __future__ import annotations

import secrets
import socket
import subprocess
import sys
import os
import time
import urllib.request
from pathlib import Path

from core.extensions.descriptor import load_portable_dlc_descriptor


class SandboxRendererError(RuntimeError):
    pass


class SandboxRendererManager:
    def __init__(self):
        self._processes: dict[str, dict] = {}

    def launch(self, package_path: str | Path, manifest: dict, component_ref: str, scope_key: str, host_origin: str) -> dict:
        self.cleanup()
        descriptor = load_portable_dlc_descriptor(package_path, manifest)
        component = next(
            (item for item in ((descriptor.get("frontend") or {}).get("components") or []) if item.get("id") == component_ref),
            None,
        )
        if not component:
            raise SandboxRendererError(f"sandbox frontend component is not declared: {component_ref}")
        self.revoke(scope_key)
        token = secrets.token_urlsafe(32)
        port = self._free_port()
        command = [
            sys.executable, str(Path(__file__).with_name("sandbox_renderer.py")),
            "--package", str(Path(package_path).resolve()),
            "--descriptor", str(descriptor["_descriptor_path"]),
            "--component", component_ref,
            "--token", token,
            "--port", str(port),
            "--host-origin", host_origin,
        ]
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **kwargs)
        health = f"http://127.0.0.1:{port}/health/{token}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise SandboxRendererError("sandbox renderer exited during startup")
            try:
                with opener.open(health, timeout=0.25) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        else:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
            raise SandboxRendererError("sandbox renderer startup timed out")
        entry = str(component.get("entry") or "").replace("\\", "/")
        self._processes[scope_key] = {"process": process, "started": time.monotonic(), "port": port}
        return {
            "url": f"http://localhost:{port}/component/{token}/{entry}",
            "origin": f"http://localhost:{port}",
            "entry_sha256": next(item.get("sha256") for item in descriptor.get("files") or [] if item.get("path") == entry),
            "descriptor_sha256": descriptor.get("_descriptor_sha256"),
            "policy": {
                "process": "dedicated",
                "memory_mb": None if os.name == "nt" else 160,
                "cpu_seconds": None if os.name == "nt" else 300,
                "lifetime_seconds": 600,
                "response_bytes": 4 * 1024 * 1024,
                "requests_per_minute": 240,
                "network": "denied_by_csp",
            },
        }

    def revoke(self, scope_key: str) -> None:
        item = self._processes.pop(scope_key, None)
        process = item.get("process") if item else None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()

    def revoke_run(self, run_id: str) -> None:
        for key in list(self._processes):
            if key.startswith(f"{run_id}:"):
                self.revoke(key)

    def cleanup(self) -> None:
        for key, item in list(self._processes.items()):
            process = item.get("process")
            if process.poll() is not None or time.monotonic() - item.get("started", 0) > 600:
                self.revoke(key)

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


sandbox_renderer_manager = SandboxRendererManager()
