"""Bounded loopback client for handing signed Creator packages to Desktop Runner."""
from __future__ import annotations

import json
from pathlib import Path
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class DesktopRunnerError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int = 503):
        self.code, self.status = code, status
        super().__init__(message)

    def as_dict(self) -> dict:
        return {"schema": "cartridgeflow.desktop_runner_error.v1", "code": self.code, "message": str(self)}


class DesktopRunnerClient:
    def __init__(self, base_url: str = "http://127.0.0.1:18990", *, timeout: float = 2.0):
        self.base_url = base_url.rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Desktop Runner URL must use loopback HTTP")
        self.timeout = max(0.2, min(float(timeout), 10.0))

    def status(self) -> dict:
        try:
            payload = self._json_request(Request(f"{self.base_url}/api/status", method="GET"))
            cartridge = payload.get("cartridge") if isinstance(payload.get("cartridge"), dict) else {}
            cartridge_active = cartridge.get("active") is True and bool(cartridge.get("cartridge_id"))
            return {
                "schema": "cartridgeflow.desktop_runner_status.v1",
                "available": payload.get("ok") is True and payload.get("runtime") == "runtime-shell",
                "url": f"{self.base_url}/",
                "version": str(payload.get("version") or ""),
                "busy": bool(payload.get("busy")),
                "cartridge": {
                    "id": str(cartridge.get("cartridge_id") or ""),
                    "name": str(cartridge.get("name") or ""),
                    "version": str(cartridge.get("version") or ""),
                } if cartridge_active else None,
            }
        except DesktopRunnerError as exc:
            return {
                "schema": "cartridgeflow.desktop_runner_status.v1",
                "available": False,
                "url": f"{self.base_url}/",
                "version": "",
                "busy": False,
                "cartridge": None,
                "message": str(exc),
            }

    def install(self, archive: str | Path) -> dict:
        archive_path = Path(archive)
        if not archive_path.is_file():
            raise DesktopRunnerError("DESKTOP_RUNNER_PACKAGE_MISSING", "The signed trial package is no longer available.", status=404)
        if archive_path.stat().st_size > 128 * 1024 * 1024:
            raise DesktopRunnerError("DESKTOP_RUNNER_PACKAGE_TOO_LARGE", "The trial package exceeds the Runner upload limit.", status=413)
        boundary = f"cartridgeflow-{uuid.uuid4().hex}"
        filename = archive_path.name.replace('"', "")
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="archive"; filename="{filename}"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode("utf-8") + archive_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("ascii")
        payload = self._json_request(Request(
            f"{self.base_url}/api/install",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
        ), timeout=max(self.timeout, 10.0))
        if payload.get("ok") is True and payload.get("status") == "trust_required":
            pending_id = str(payload.get("id") or "")
            if not re.fullmatch(r"[0-9a-f]{32}", pending_id):
                raise DesktopRunnerError("DESKTOP_RUNNER_RESPONSE_INVALID", "Desktop Runner returned an invalid approval request.")
            publisher = payload.get("publisher") if isinstance(payload.get("publisher"), dict) else {}
            cartridge = payload.get("cartridge") if isinstance(payload.get("cartridge"), dict) else {}
            return {
                "schema": "cartridgeflow.desktop_runner_delivery.v1",
                "status": "trust_required",
                "runner_url": f"{self.base_url}/?pending={pending_id}",
                "approval_id": pending_id,
                "publisher": {
                    "id": str(publisher.get("id") or ""),
                    "key_id": str(publisher.get("key_id") or ""),
                    "fingerprint": str(publisher.get("fingerprint") or ""),
                },
                "cartridge": {
                    "id": str(cartridge.get("id") or ""),
                    "name": str(cartridge.get("name") or ""),
                    "version": str(cartridge.get("version") or ""),
                },
            }
        if payload.get("ok") is not True:
            raise DesktopRunnerError("DESKTOP_RUNNER_INSTALL_REJECTED", str(payload.get("error") or "Desktop Runner rejected the package."), status=409)
        cartridge = payload.get("cartridge") if isinstance(payload.get("cartridge"), dict) else {}
        return {
            "schema": "cartridgeflow.desktop_runner_delivery.v1",
            "status": "installed",
            "runner_url": f"{self.base_url}/",
            "cartridge": {
                "id": str(cartridge.get("cartridge_id") or cartridge.get("id") or ""),
                "name": str(cartridge.get("name") or ""),
                "version": str(cartridge.get("version") or ""),
            },
        }

    def _json_request(self, request: Request, *, timeout: float | None = None) -> dict:
        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                content = response.read(2 * 1024 * 1024 + 1)
                if len(content) > 2 * 1024 * 1024:
                    raise DesktopRunnerError("DESKTOP_RUNNER_RESPONSE_TOO_LARGE", "Desktop Runner response exceeded the safe limit.")
                payload = json.loads(content.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("response is not an object")
                return payload
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read(64 * 1024).decode("utf-8"))
                message = str(detail.get("error") or detail.get("message") or detail.get("detail") or "")
            except (UnicodeError, ValueError, AttributeError):
                message = ""
            raise DesktopRunnerError(
                "DESKTOP_RUNNER_REQUEST_REJECTED",
                message or f"Desktop Runner returned HTTP {exc.code}.",
                status=409 if exc.code < 500 else 503,
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise DesktopRunnerError("DESKTOP_RUNNER_UNAVAILABLE", "Desktop Runner is not reachable on this machine.") from exc
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise DesktopRunnerError("DESKTOP_RUNNER_RESPONSE_INVALID", "Desktop Runner returned an invalid response.") from exc
