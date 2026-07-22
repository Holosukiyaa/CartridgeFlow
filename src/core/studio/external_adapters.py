"""Execute machine-owned HTTP, CLI, and MCP resource bindings."""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import re
import shlex
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import httpx


MAX_RESPONSE_BYTES = 4 * 1024 * 1024
DEFAULT_TIMEOUT_MS = 30_000
ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
HTTP_HEADER_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
SECRET_ENV_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|credential|authorization|auth[_-]?key|(?:^|[_-])key(?:$|[_-]))"
)
_NO_BODY = object()


class ExternalAdapterFailure(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False, status_code: int | None = None):
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        super().__init__(message)


class ExternalAdapterCancelled(RuntimeError):
    pass


class ExternalAdapterTimeout(TimeoutError):
    pass


@dataclass
class _ActiveCall:
    call_id: str
    run_id: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    process: subprocess.Popen | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def attach_process(self, process: subprocess.Popen) -> None:
        with self.lock:
            self.process = process
            if self.cancel_event.is_set() and process.poll() is None:
                process.terminate()

    def cancel(self) -> None:
        self.cancel_event.set()
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()


_ACTIVE_CALLS: dict[str, dict[str, _ActiveCall]] = {}
_ACTIVE_CALLS_LOCK = threading.Lock()


def execute_external_tool(
    binding: dict,
    server: str,
    tool_name: str,
    params: dict,
    contract: dict | None = None,
) -> dict:
    """Execute one external tool without exposing its connection to the cartridge."""
    connection = binding.get("connection") if isinstance(binding.get("connection"), dict) else {}
    kind = str(connection.get("kind") or "").strip()
    run_id = str(params.get("_runtime_run_id") or "").strip()
    public_params = {
        str(key): value
        for key, value in params.items()
        if not str(key).startswith("_runtime_") and str(key) != "_local_resource"
    }
    timeout_ms = _timeout_ms(contract)
    adapter = _adapter_name(kind, connection)
    active = _register_call(run_id)
    try:
        _require_credential(connection)
        if kind == "remote_api" or (kind == "plugin" and connection.get("endpoint") and not connection.get("command")):
            result = _run_async(_call_http(connection, server, tool_name, public_params, active, timeout_ms))
        elif kind == "plugin":
            result = _call_cli(connection, server, tool_name, public_params, active, timeout_ms)
        elif kind == "mcp":
            result = _run_async(_call_mcp(connection, tool_name, public_params, active, timeout_ms))
        else:
            raise ExternalAdapterFailure("dependency_unavailable", f"Unsupported external resource kind: {kind}")
        return {
            **result,
            "adapter": adapter,
            "call_id": active.call_id,
        }
    except ExternalAdapterCancelled:
        return _error_result("tool_cancelled", "External tool call was cancelled", retryable=False, adapter=adapter, call_id=active.call_id)
    except (ExternalAdapterTimeout, TimeoutError):
        return _error_result("tool_timeout", "External tool call exceeded its timeout", retryable=True, adapter=adapter, call_id=active.call_id)
    except ExternalAdapterFailure as exc:
        return _error_result(
            exc.code,
            _redact_message(str(exc), connection),
            retryable=exc.retryable,
            adapter=adapter,
            call_id=active.call_id,
            status_code=exc.status_code,
        )
    except (OSError, httpx.HTTPError) as exc:
        return _error_result(
            "dependency_unavailable",
            _redact_message(f"External resource transport failed: {exc}", connection),
            retryable=True,
            adapter=adapter,
            call_id=active.call_id,
        )
    except Exception as exc:
        return _error_result(
            "tool_failed",
            _redact_message(f"External tool call failed: {exc}", connection),
            retryable=False,
            adapter=adapter,
            call_id=active.call_id,
        )
    finally:
        _unregister_call(active)


def cancel_external_calls_for_run(run_id: str) -> list[str]:
    run_id = str(run_id or "").strip()
    with _ACTIVE_CALLS_LOCK:
        calls = list((_ACTIVE_CALLS.get(run_id) or {}).values())
    for call in calls:
        call.cancel()
    return [call.call_id for call in calls]


def shutdown_active_external_calls() -> list[str]:
    with _ACTIVE_CALLS_LOCK:
        calls = [call for group in _ACTIVE_CALLS.values() for call in group.values()]
    for call in calls:
        call.cancel()
    return [call.call_id for call in calls]


def active_external_calls(run_id: str | None = None) -> list[dict]:
    with _ACTIVE_CALLS_LOCK:
        if run_id is None:
            calls = [call for group in _ACTIVE_CALLS.values() for call in group.values()]
        else:
            calls = list((_ACTIVE_CALLS.get(str(run_id)) or {}).values())
    return [{"call_id": call.call_id, "run_id": call.run_id} for call in calls]


async def _call_http(
    connection: dict,
    server: str,
    tool_name: str,
    params: dict,
    active: _ActiveCall,
    timeout_ms: int,
) -> dict:
    async def operation() -> dict:
        headers = _auth_headers(connection)
        async with httpx.AsyncClient(headers=headers, timeout=None, follow_redirects=False) as client:
            method, url, query, request_headers, body = await _http_request(
                client,
                connection,
                server,
                tool_name,
                params,
            )
            response = await client.request(
                method,
                url,
                params=query or None,
                headers=request_headers or None,
                json=None if body is _NO_BODY else body,
            )
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ExternalAdapterFailure("tool_output_too_large", "Remote HTTP response exceeded 4 MiB")
            if response.status_code >= 400:
                code = "permission_denied" if response.status_code in {401, 403} else "remote_http_error"
                retryable = response.status_code in {408, 425, 429} or response.status_code >= 500
                raise ExternalAdapterFailure(
                    code,
                    f"Remote HTTP returned status {response.status_code}",
                    retryable=retryable,
                    status_code=response.status_code,
                )
            content_type = str(response.headers.get("content-type") or "").lower()
            if "json" in content_type:
                try:
                    content = response.json()
                except ValueError as exc:
                    raise ExternalAdapterFailure("tool_invalid_response", "Remote HTTP returned invalid JSON") from exc
            else:
                content = response.text
            return {
                "ok": True,
                "content": content,
                "status_code": response.status_code,
                "content_type": content_type.split(";", 1)[0],
            }

    return await _await_controlled(operation(), active, timeout_ms)


async def _http_request(
    client: httpx.AsyncClient,
    connection: dict,
    server: str,
    tool_name: str,
    params: dict,
) -> tuple[str, str, dict, dict, object]:
    openapi_url = str(connection.get("openapi_url") or "").strip()
    endpoint = str(connection.get("endpoint") or "").strip()
    if not openapi_url:
        if not endpoint:
            raise ExternalAdapterFailure("dependency_unavailable", "Remote HTTP endpoint is not configured")
        method = _http_method(connection.get("http_method"))
        body = _NO_BODY if method in {"GET", "DELETE"} else params
        query = params if body is _NO_BODY else {}
        return method, endpoint, query, {}, body

    response = await client.get(openapi_url)
    if response.status_code >= 400:
        raise ExternalAdapterFailure(
            "dependency_unavailable",
            f"OpenAPI document returned status {response.status_code}",
            retryable=response.status_code in {408, 425, 429} or response.status_code >= 500,
            status_code=response.status_code,
        )
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ExternalAdapterFailure("tool_output_too_large", "OpenAPI document exceeded 4 MiB")
    try:
        document = response.json()
    except ValueError as exc:
        raise ExternalAdapterFailure("tool_invalid_response", "OpenAPI document is not valid JSON") from exc
    operation = _find_openapi_operation(document, server, tool_name)
    if operation is None:
        raise ExternalAdapterFailure("tool_not_found", f"OpenAPI operation is not available: {server}/{tool_name}")
    method, path, details = operation
    base_url = endpoint or _openapi_base_url(document, openapi_url)
    return _build_openapi_request(method, base_url, path, details, params, connection)


def _find_openapi_operation(document: dict, server: str, tool_name: str) -> tuple[str, str, dict] | None:
    targets = {str(tool_name or "").strip(), f"{server}.{tool_name}".strip(".")}
    for path, path_item in (document.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in ALLOWED_HTTP_METHODS:
            details = path_item.get(method.lower())
            if not isinstance(details, dict):
                continue
            operation_id = str(details.get("operationId") or "").strip()
            if operation_id in targets:
                merged = {**details, "_path_parameters": path_item.get("parameters") or []}
                return method, str(path), merged
    return None


def _build_openapi_request(
    method: str,
    base_url: str,
    path: str,
    operation: dict,
    params: dict,
    connection: dict,
) -> tuple[str, str, dict, dict, object]:
    remaining = dict(params)
    query: dict = {}
    headers: dict = {}
    auth_header = str(connection.get("auth_header") or "Authorization").casefold()
    parameter_items = [*(operation.get("_path_parameters") or []), *(operation.get("parameters") or [])]
    for item in parameter_items:
        if not isinstance(item, dict) or "$ref" in item:
            continue
        name = str(item.get("name") or "").strip()
        location = str(item.get("in") or "").strip()
        if not name or name not in remaining:
            continue
        value = remaining.pop(name)
        if location == "path":
            path = path.replace("{" + name + "}", quote(str(value), safe=""))
        elif location == "query":
            query[name] = value
        elif location == "header" and name.casefold() != auth_header:
            headers[name] = str(value)
    if re.search(r"\{[^{}]+\}", path):
        raise ExternalAdapterFailure("request_invalid", "OpenAPI path parameters are incomplete")
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    body: object = _NO_BODY
    if "body" in remaining:
        body = remaining.pop("body")
    elif operation.get("requestBody") is not None or method not in {"GET", "DELETE"}:
        body = remaining
        remaining = {}
    query.update(remaining)
    return method, url, query, headers, body


def _openapi_base_url(document: dict, openapi_url: str) -> str:
    servers = document.get("servers") if isinstance(document.get("servers"), list) else []
    if servers and isinstance(servers[0], dict) and servers[0].get("url"):
        return urljoin(openapi_url, str(servers[0]["url"]))
    parsed = urlsplit(openapi_url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _call_cli(
    connection: dict,
    server: str,
    tool_name: str,
    params: dict,
    active: _ActiveCall,
    timeout_ms: int,
) -> dict:
    command = _command_parts(connection.get("command"))
    if not command:
        raise ExternalAdapterFailure("dependency_unavailable", "CLI command is not configured")
    command.extend(_argument_parts(connection.get("args")))
    request = json.dumps(
        {
            "schema": "cartridgeflow.cli_tool_request.v1",
            "server": str(server or ""),
            "tool": str(tool_name or ""),
            "arguments": params,
        },
        ensure_ascii=False,
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_child_environment(connection),
        creationflags=creation_flags,
    )
    active.attach_process(process)
    try:
        stdout, _stderr = process.communicate(request, timeout=timeout_ms / 1000)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate()
        raise ExternalAdapterTimeout() from exc
    if active.cancel_event.is_set():
        raise ExternalAdapterCancelled()
    if process.returncode != 0:
        raise ExternalAdapterFailure("tool_failed", f"CLI process exited with code {process.returncode}")
    if len(stdout.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ExternalAdapterFailure("tool_output_too_large", "CLI response exceeded 4 MiB")
    output = stdout.strip()
    if not output:
        content: object = ""
    else:
        try:
            content = json.loads(output)
        except json.JSONDecodeError:
            content = output
    if isinstance(content, dict) and content.get("ok") is False:
        return {
            **content,
            "code": str(content.get("code") or "tool_failed"),
            "error": _redact_message(str(content.get("error") or "CLI tool reported failure"), connection),
        }
    if isinstance(content, dict) and content.get("ok") is True:
        return content
    return {"ok": True, "content": content}


async def _call_mcp(
    connection: dict,
    tool_name: str,
    params: dict,
    active: _ActiveCall,
    timeout_ms: int,
) -> dict:
    async def operation() -> dict:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:
            raise ExternalAdapterFailure("dependency_unavailable", "The MCP Python SDK is not installed") from exc

        read_timeout = timedelta(milliseconds=timeout_ms)
        endpoint = str(connection.get("endpoint") or "").strip()
        if endpoint:
            async with httpx.AsyncClient(headers=_auth_headers(connection), timeout=None, follow_redirects=False) as client:
                async with streamable_http_client(endpoint, http_client=client) as (read_stream, write_stream, _session_id):
                    async with ClientSession(read_stream, write_stream, read_timeout_seconds=read_timeout) as session:
                        await session.initialize()
                        return _mcp_result(await session.call_tool(tool_name, arguments=params, read_timeout_seconds=read_timeout), connection)

        command = _command_parts(connection.get("command"))
        if not command:
            raise ExternalAdapterFailure("dependency_unavailable", "MCP command or endpoint is not configured")
        command.extend(_argument_parts(connection.get("args")))
        server = StdioServerParameters(
            command=command[0],
            args=command[1:],
            env=_child_environment(connection),
            encoding="utf-8",
        )
        with open(os.devnull, "w", encoding="utf-8") as errlog:
            async with stdio_client(server, errlog=errlog) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream, read_timeout_seconds=read_timeout) as session:
                    await session.initialize()
                    return _mcp_result(await session.call_tool(tool_name, arguments=params, read_timeout_seconds=read_timeout), connection)

    return await _await_controlled(operation(), active, timeout_ms)


def _mcp_result(result, connection: dict) -> dict:
    payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    is_error = payload.get("isError") is True
    structured = payload.get("structuredContent")
    content_items = payload.get("content") or []
    if structured is not None:
        content: object = structured
    elif len(content_items) == 1 and isinstance(content_items[0], dict) and content_items[0].get("type") == "text":
        content = content_items[0].get("text") or ""
    else:
        content = content_items
    if is_error:
        message = content if isinstance(content, str) else "MCP tool reported an error"
        return {"ok": False, "code": "tool_failed", "error": _redact_message(str(message), connection), "content": content_items}
    return {"ok": True, "content": content, "mcp_content": content_items}


async def _await_controlled(awaitable, active: _ActiveCall, timeout_ms: int):
    operation = asyncio.create_task(awaitable)
    cancellation = asyncio.create_task(_wait_for_cancel(active.cancel_event))
    done, _pending = await asyncio.wait(
        {operation, cancellation},
        timeout=timeout_ms / 1000,
        return_when=asyncio.FIRST_COMPLETED,
    )
    if operation in done:
        cancellation.cancel()
        await asyncio.gather(cancellation, return_exceptions=True)
        return await operation
    operation.cancel()
    await asyncio.gather(operation, return_exceptions=True)
    cancellation.cancel()
    await asyncio.gather(cancellation, return_exceptions=True)
    if active.cancel_event.is_set():
        raise ExternalAdapterCancelled()
    raise ExternalAdapterTimeout()


async def _wait_for_cancel(event: threading.Event) -> None:
    while not event.is_set():
        await asyncio.sleep(0.05)


def _run_async(awaitable):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    result: dict = {}

    def run() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=run, name="cartridgeflow-external-adapter", daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _auth_headers(connection: dict) -> dict[str, str]:
    key = str(connection.get("auth_env") or "").strip().upper()
    if not key:
        return {"Accept": "application/json"}
    secret = os.environ.get(key, "")
    if not secret:
        raise ExternalAdapterFailure("permission_denied", f"Required local credential is not configured: {key}")
    header = str(connection.get("auth_header") or "Authorization").strip()
    if not HTTP_HEADER_PATTERN.fullmatch(header):
        raise ExternalAdapterFailure("request_invalid", "Configured authentication header name is invalid")
    scheme = str(connection.get("auth_scheme") or ("Bearer" if header.casefold() == "authorization" else "")).strip()
    value = f"{scheme} {secret}".strip()
    return {"Accept": "application/json", header: value}


def _require_credential(connection: dict) -> None:
    key = str(connection.get("auth_env") or "").strip().upper()
    if key and not os.environ.get(key):
        raise ExternalAdapterFailure("permission_denied", f"Required local credential is not configured: {key}")


def _child_environment(connection: dict) -> dict[str, str]:
    selected_key = str(connection.get("auth_env") or "").strip().upper()
    return {
        str(key): str(value)
        for key, value in os.environ.items()
        if str(key).upper() == selected_key or not SECRET_ENV_PATTERN.search(str(key))
    }


def _timeout_ms(contract: dict | None) -> int:
    contract = contract if isinstance(contract, dict) else {}
    try:
        return max(100, min(600_000, int(contract.get("timeout_ms") or DEFAULT_TIMEOUT_MS)))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_MS


def _http_method(value) -> str:
    method = str(value or "POST").strip().upper()
    if method not in ALLOWED_HTTP_METHODS:
        raise ExternalAdapterFailure("request_invalid", f"Unsupported HTTP method: {method}")
    return method


def _command_parts(value) -> list[str]:
    text = str(value or "").strip()
    if text and Path(text).is_file():
        return [text]
    return _argument_parts(value)


def _argument_parts(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item)]
        except json.JSONDecodeError:
            pass
    parts = shlex.split(text, posix=os.name != "nt")
    return [part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"} else part for part in parts]


def _register_call(run_id: str) -> _ActiveCall:
    active = _ActiveCall(call_id=f"external_{uuid.uuid4().hex[:16]}", run_id=run_id)
    with _ACTIVE_CALLS_LOCK:
        _ACTIVE_CALLS.setdefault(run_id, {})[active.call_id] = active
    return active


def _unregister_call(active: _ActiveCall) -> None:
    with _ACTIVE_CALLS_LOCK:
        group = _ACTIVE_CALLS.get(active.run_id)
        if group is None:
            return
        group.pop(active.call_id, None)
        if not group:
            _ACTIVE_CALLS.pop(active.run_id, None)


def _adapter_name(kind: str, connection: dict) -> str:
    if kind == "mcp":
        return "mcp_streamable_http" if connection.get("endpoint") else "mcp_stdio"
    if kind == "plugin":
        return "remote_http" if connection.get("endpoint") and not connection.get("command") else "cli_json_stdio"
    return "remote_http" if kind == "remote_api" else kind or "unknown"


def _error_result(
    code: str,
    error: str,
    *,
    retryable: bool,
    adapter: str,
    call_id: str,
    status_code: int | None = None,
) -> dict:
    return {
        "ok": False,
        "code": code,
        "error": error,
        "retryable": retryable,
        "adapter": adapter,
        "call_id": call_id,
        **({"status_code": status_code} if status_code is not None else {}),
    }


def _redact_message(message: str, connection: dict) -> str:
    value = str(message or "")[:500]
    sensitive_values = [
        os.environ.get(str(connection.get("auth_env") or "").strip().upper(), ""),
        connection.get("endpoint"),
        connection.get("openapi_url"),
        connection.get("command"),
        connection.get("args"),
        connection.get("location"),
    ]
    for sensitive in sensitive_values:
        text = str(sensitive or "")
        if text:
            value = value.replace(text, "[redacted]")
    value = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", value)
    return value


atexit.register(shutdown_active_external_calls)
