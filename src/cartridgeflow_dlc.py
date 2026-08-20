"""Restricted runtime SDK for transparent package-owned DLC tools.

Business logic stays inside the cartridge. This module supplies only the
generic declared-graph runner and brokered host capabilities that Base owns.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ipaddress
import socket
import ssl
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener


class McpRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, *, operation_id: str = ""):
        self.code = code
        self.operation_id = operation_id
        super().__init__(message)


def mcp_operation(operation_id: str):
    """Mark one callable as the implementation of a declared operation."""

    def decorate(function: Callable):
        function._mcp_operation_id = str(operation_id)  # type: ignore[attr-defined]
        return function

    return decorate


def _validate_public_https_url(url: str) -> tuple[str, int]:
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise McpRuntimeError("network_url_denied", "network.fetch accepts public HTTPS URLs only")
    if parsed.username or parsed.password or parsed.fragment:
        raise McpRuntimeError("network_url_denied", "network.fetch URL contains forbidden authority or fragment data")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise McpRuntimeError("network_url_denied", "network.fetch URL has an invalid port") from exc
    try:
        addresses = {
            item[4][0].split("%", 1)[0]
            for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise McpRuntimeError("network_dns_failed", f"could not resolve public feed host: {parsed.hostname}") from exc
    if not addresses:
        raise McpRuntimeError("network_dns_failed", f"could not resolve public feed host: {parsed.hostname}")
    for address in addresses:
        try:
            public = ipaddress.ip_address(address).is_global
        except ValueError as exc:
            raise McpRuntimeError("network_url_denied", "network.fetch resolved an invalid address") from exc
        if not public:
            raise McpRuntimeError("network_url_denied", "network.fetch cannot access private or reserved addresses")
    return parsed.hostname, port


class _ValidatedRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        _validate_public_https_url(new_url)
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


@dataclass(frozen=True)
class _Operation:
    operation_id: str
    kind: str
    capability: str


class _NetworkBroker:
    MAX_URLS = 8
    MAX_RESPONSE_BYTES = 2 * 1024 * 1024
    TIMEOUT_SECONDS = 20

    def __init__(self, context: "McpContext"):
        self._context = context

    def fetch_many(self, urls: list[str]) -> list[dict]:
        operation = self._context._active_operation
        if operation is None or operation.kind != "network" or operation.capability != "network.fetch":
            raise McpRuntimeError(
                "network_capability_denied",
                "network.fetch was called outside its declared broker operation",
                operation_id=operation.operation_id if operation else "",
            )
        if not isinstance(urls, list) or not 1 <= len(urls) <= self.MAX_URLS:
            raise McpRuntimeError(
                "network_request_invalid",
                f"network.fetch_many requires one to {self.MAX_URLS} URLs",
                operation_id=operation.operation_id,
            )
        return [self._fetch(str(url), operation.operation_id) for url in urls]

    def _fetch(self, url: str, operation_id: str) -> dict:
        _validate_public_https_url(url)
        opener = build_opener(
            ProxyHandler({}),
            HTTPSHandler(context=ssl.create_default_context()),
            _ValidatedRedirectHandler(),
        )
        request = Request(
            url,
            headers={
                "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.1",
                "User-Agent": "CartridgeFlow-DLC-Broker/1.0",
            },
            method="GET",
        )
        try:
            with opener.open(request, timeout=self.TIMEOUT_SECONDS) as response:
                final_url = str(response.geturl())
                _validate_public_https_url(final_url)
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
                if len(raw) > self.MAX_RESPONSE_BYTES:
                    raise McpRuntimeError(
                        "network_response_too_large",
                        f"network response exceeds {self.MAX_RESPONSE_BYTES} bytes",
                        operation_id=operation_id,
                    )
                charset = response.headers.get_content_charset() or "utf-8"
                try:
                    content = raw.decode(charset)
                except (LookupError, UnicodeDecodeError):
                    content = raw.decode("utf-8", errors="replace")
                return {
                    "url": final_url,
                    "status": int(getattr(response, "status", 200)),
                    "content_type": str(response.headers.get("Content-Type") or ""),
                    "content": content,
                    "bytes": len(raw),
                }
        except McpRuntimeError:
            raise
        except HTTPError as exc:
            raise McpRuntimeError(
                "network_http_failed",
                f"network.fetch returned HTTP {exc.code}",
                operation_id=operation_id,
            ) from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise McpRuntimeError(
                "network_transport_failed",
                f"network.fetch failed: {exc}",
                operation_id=operation_id,
            ) from exc


class McpContext:
    """Execution context passed to a transparent MCP source module."""

    def __init__(self, *, request: dict | None = None, tool: dict | None = None):
        self.request = dict(request or {})
        self.tool = dict(tool or {})
        self._active_operation: _Operation | None = None
        self.network = _NetworkBroker(self)

    def run_declared_graph(self, node: dict, operations: dict[str, Callable], inputs: dict) -> dict:
        declared = node.get("operations") if isinstance(node, dict) else None
        edges = node.get("edges") if isinstance(node, dict) else None
        if node.get("schema") != "cartridgeflow.mcp_python.v1" or not isinstance(declared, list):
            raise McpRuntimeError("dlc_graph_invalid", "MCP_NODE is not a declared operation graph")
        declared_by_id = {
            str(item.get("id") or ""): _Operation(
                str(item.get("id") or ""),
                str(item.get("kind") or ""),
                str(item.get("capability") or ""),
            )
            for item in declared
            if isinstance(item, dict) and str(item.get("id") or "")
        }
        if not declared_by_id or set(operations) != set(declared_by_id):
            raise McpRuntimeError("dlc_graph_invalid", "declared operations and implementation registry do not match")
        for operation_id, function in operations.items():
            if getattr(function, "_mcp_operation_id", None) != operation_id:
                raise McpRuntimeError("dlc_graph_invalid", f"operation decorator does not match: {operation_id}")

        indegree = {operation_id: 0 for operation_id in declared_by_id}
        outgoing = {operation_id: [] for operation_id in declared_by_id}
        for edge in edges or []:
            source = str((edge or {}).get("from") or "") if isinstance(edge, dict) else ""
            target = str((edge or {}).get("to") or "") if isinstance(edge, dict) else ""
            if (edge or {}).get("kind") != "control" or source not in outgoing or target not in indegree:
                raise McpRuntimeError("dlc_graph_invalid", "declared operation graph contains an invalid edge")
            outgoing[source].append(target)
            indegree[target] += 1
        declared_order = list(declared_by_id)
        ready = [operation_id for operation_id in declared_order if indegree[operation_id] == 0]
        execution_order: list[str] = []
        while ready:
            operation_id = ready.pop(0)
            execution_order.append(operation_id)
            for target in outgoing[operation_id]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
            ready.sort(key=declared_order.index)
        if len(execution_order) != len(declared_by_id):
            raise McpRuntimeError("dlc_graph_invalid", "declared operation graph contains a cycle")

        data = dict(inputs or {})
        trace = []
        try:
            for operation_id in execution_order:
                operation = declared_by_id[operation_id]
                self._active_operation = operation
                result = operations[operation_id](self, data)
                if not isinstance(result, dict):
                    raise McpRuntimeError(
                        "dlc_operation_invalid_response",
                        f"operation must return an object: {operation_id}",
                        operation_id=operation_id,
                    )
                data = result
                trace.append({"operation_id": operation_id, "kind": operation.kind, "status": "completed"})
        except McpRuntimeError:
            raise
        except Exception as exc:
            active = self._active_operation.operation_id if self._active_operation else ""
            raise McpRuntimeError(
                "dlc_operation_failed",
                f"{type(exc).__name__}: {exc}",
                operation_id=active,
            ) from exc
        finally:
            self._active_operation = None

        expected_outputs = node.get("outputs") if isinstance(node.get("outputs"), dict) else {}
        missing = [key for key in expected_outputs if key not in data]
        if missing:
            raise McpRuntimeError("dlc_output_missing", f"declared outputs are missing: {', '.join(missing)}")
        content = data[next(iter(expected_outputs))] if len(expected_outputs) == 1 else data
        return {"ok": True, "content": content, "outputs": data, "operation_trace": trace}


def fetch_public_https_url(url: str, *, operation_id: str = "creator.source.fetch") -> dict:
    """SSRF-safe public HTTPS GET used by Creator source review and trial runs."""
    context = McpContext()
    context._active_operation = _Operation(operation_id, "network", "network.fetch")
    try:
        return context.network._fetch(str(url), operation_id)
    finally:
        context._active_operation = None


def inspect_public_https_url(url: str) -> dict:
    """Use the same SSRF-safe network broker for a read-only Creator source review."""
    result = fetch_public_https_url(url, operation_id="creator.source.inspect")
    content = str(result.pop("content", ""))
    result["content_digest"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    result["sample"] = " ".join(content[:12000].split())[:1000]
    return result
