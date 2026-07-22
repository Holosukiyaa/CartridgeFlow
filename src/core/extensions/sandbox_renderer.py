"""Single-component, short-lived HTTP renderer for untrusted cartridge UI."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_REQUESTS_PER_MINUTE = 240
DEFAULT_TTL_SECONDS = 10 * 60
PERMISSIONS_POLICY = (
    "camera=(), microphone=(), geolocation=(), display-capture=(), clipboard-read=(), "
    "clipboard-write=(), usb=(), serial=(), hid=(), payment=()"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _apply_process_limits() -> None:
    if os.name == "nt":
        # The parent supervisor owns termination on Windows. Nested Job Objects
        # are not reliable in every developer shell, so do not make startup
        # depend on one; browser site isolation and the dedicated server process
        # remain independent from the Base process.
        return
    else:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (160 * 1024 * 1024, 160 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
        except (ImportError, OSError, ValueError):
            pass


def _load_scope(package: Path, descriptor_path: Path, component_id: str) -> dict:
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    component = next(
        (item for item in ((descriptor.get("frontend") or {}).get("components") or []) if item.get("id") == component_id),
        None,
    )
    if not component:
        raise ValueError("frontend component is not declared")
    entry = str(component.get("entry") or "").replace("\\", "/")
    entry_root = Path(entry).parent
    files = {}
    for item in descriptor.get("files") or []:
        if not isinstance(item, dict):
            continue
        relative = str(item.get("path") or "").replace("\\", "/")
        role = str(item.get("role") or "")
        if role.startswith("frontend_") and (Path(relative) == Path(entry) or entry_root in Path(relative).parents):
            files[relative] = item
    if entry not in files:
        raise ValueError("frontend entry is outside the declared renderer scope")
    return {"entry": entry, "files": files}


def serve(package: Path, descriptor: Path, component: str, token: str, port: int, host_origin: str, ttl: int) -> None:
    _apply_process_limits()
    package = package.resolve()
    scope = _load_scope(package, descriptor.resolve(), component)
    started = time.monotonic()
    requests = deque()

    class Handler(BaseHTTPRequestHandler):
        server_version = "CartridgeFlowSandbox/1"

        def log_message(self, _format, *_args):
            return

        def do_GET(self):
            now = time.monotonic()
            if now - started > ttl:
                self.send_error(410, "Renderer expired")
                return
            while requests and now - requests[0] > 60:
                requests.popleft()
            if len(requests) >= MAX_REQUESTS_PER_MINUTE:
                self.send_error(429, "Renderer request limit exceeded")
                return
            requests.append(now)
            parsed = urlparse(self.path)
            if parsed.path == f"/health/{token}":
                self._headers(200, "application/json", 11)
                self.wfile.write(b'{"ok":true}')
                return
            prefix = f"/component/{token}/"
            if not parsed.path.startswith(prefix):
                self.send_error(404)
                return
            relative = unquote(parsed.path[len(prefix):]).replace("\\", "/")
            item = scope["files"].get(relative)
            target = (package / relative).resolve()
            if not item or target != package and package not in target.parents or not target.is_file():
                self.send_error(404)
                return
            size = target.stat().st_size
            if size > MAX_RESPONSE_BYTES or _sha256(target) != item.get("sha256"):
                self.send_error(409, "Renderer integrity check failed")
                return
            media_type = str(item.get("media_type") or mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self._headers(200, media_type, size, html=relative == scope["entry"])
            with target.open("rb") as handle:
                self.wfile.write(handle.read())

        def _headers(self, status: int, media_type: str, length: int, *, html: bool = False):
            self.send_response(status)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Permissions-Policy", PERMISSIONS_POLICY)
            if html:
                csp = (
                    "default-src 'none'; script-src 'self'; connect-src 'none'; "
                    "img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self'; "
                    "object-src 'none'; frame-src 'none'; worker-src 'none'; child-src 'none'; "
                    "media-src 'self' blob:; form-action 'none'; base-uri 'none'; navigate-to 'none'; "
                    f"frame-ancestors {host_origin}"
                )
                self.send_header("Content-Security-Policy", csp)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    while time.monotonic() - started <= ttl:
        server.handle_request()
    server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--descriptor", required=True)
    parser.add_argument("--component", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--host-origin", required=True)
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    args = parser.parse_args()
    serve(Path(args.package), Path(args.descriptor), args.component, args.token, args.port, args.host_origin, args.ttl)


if __name__ == "__main__":
    main()
