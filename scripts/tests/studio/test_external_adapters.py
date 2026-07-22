import json
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from core.lab.node_executor import LabNodeExecutor
from core.studio.external_adapters import (
    active_external_calls,
    cancel_external_calls_for_run,
    execute_external_tool,
)


class _AdapterHandler(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        if self.path == "/openapi.json":
            self._json({
                "openapi": "3.1.0",
                "paths": {
                    "/search/{scope}": {
                        "post": {
                            "operationId": "search",
                            "parameters": [
                                {"name": "scope", "in": "path", "required": True, "schema": {"type": "string"}},
                                {"name": "query", "in": "query", "required": True, "schema": {"type": "string"}},
                            ],
                            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                        }
                    }
                },
            })
            return
        if self.path.startswith("/slow"):
            time.sleep(0.5)
            self._json({"slow": True})
            return
        if self.path.startswith("/unauthorized"):
            self._json({"error": "unauthorized"}, status=401)
            return
        self._json({"method": "GET", "path": self.path})

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        record = {
            "path": self.path,
            "body": body,
            "auth": self.headers.get("X-API-Key") or self.headers.get("Authorization") or "",
        }
        type(self).requests.append(record)
        self._json({"received": body, "path": self.path, "authenticated": bool(record["auth"])})

    def log_message(self, _format, *_args):
        return

    def _json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


@contextmanager
def _http_fixture():
    _AdapterHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AdapterHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _binding(kind, **connection):
    return {
        "role": "fixture_role",
        "resource_id": "fixture-resource",
        "connection": {"id": "fixture-resource", "kind": kind, **connection},
    }


class ExternalAdapterTests(unittest.TestCase):
    def test_remote_http_executes_openapi_operation_with_local_auth(self):
        secret = "local-secret-value"
        with _http_fixture() as base_url, patch.dict(os.environ, {"CF_FIXTURE_API_KEY": secret}):
            result = execute_external_tool(
                _binding(
                    "remote_api",
                    endpoint=base_url,
                    openapi_url=f"{base_url}/openapi.json",
                    auth_env="CF_FIXTURE_API_KEY",
                    auth_header="X-API-Key",
                    auth_scheme="",
                ),
                "documents",
                "search",
                {"scope": "public", "query": "adapter", "limit": 2, "_runtime_run_id": "run_http"},
                {"timeout_ms": 2_000, "idempotent": True},
            )

        self.assertTrue(result["ok"])
        self.assertEqual("remote_http", result["adapter"])
        self.assertEqual("/search/public?query=adapter", result["content"]["path"])
        self.assertEqual({"limit": 2}, result["content"]["received"])
        self.assertTrue(result["content"]["authenticated"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(base_url, json.dumps(result))

    def test_remote_http_reports_auth_and_timeout_without_private_connection_details(self):
        with _http_fixture() as base_url:
            missing_auth = execute_external_tool(
                _binding("remote_api", endpoint=f"{base_url}/direct", auth_env="CF_MISSING_FIXTURE_KEY"),
                "fixture",
                "call",
                {},
                {"timeout_ms": 1_000},
            )
            timed_out = execute_external_tool(
                _binding("remote_api", endpoint=f"{base_url}/slow", http_method="GET"),
                "fixture",
                "slow",
                {},
                {"timeout_ms": 100},
            )

        self.assertEqual("permission_denied", missing_auth["code"])
        self.assertFalse(missing_auth["retryable"])
        self.assertNotIn(base_url, missing_auth["error"])
        self.assertEqual("tool_timeout", timed_out["code"])
        self.assertTrue(timed_out["retryable"])

    def test_cli_adapter_uses_json_stdio_and_local_environment(self):
        script = textwrap.dedent("""
            import json
            import os
            import sys

            request = json.loads(sys.stdin.read())
            print(json.dumps({
                "ok": True,
                "content": {
                    "tool": request["tool"],
                    "arguments": request["arguments"],
                    "credential_available": bool(os.environ.get("CF_CLI_SECRET")),
                    "unrelated_secret_available": bool(os.environ.get("CF_OTHER_SECRET")),
                },
            }))
        """)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"CF_CLI_SECRET": "cli-secret", "CF_OTHER_SECRET": "must-not-leak"},
        ):
            target = Path(temp_dir) / "cli_fixture.py"
            target.write_text(script, encoding="utf-8")
            result = execute_external_tool(
                _binding("plugin", command=sys.executable, args=json.dumps([str(target)]), auth_env="CF_CLI_SECRET"),
                "fixture",
                "summarize",
                {"text": "hello", "_runtime_run_id": "run_cli"},
                {"timeout_ms": 2_000},
            )

        self.assertTrue(result["ok"])
        self.assertEqual("cli_json_stdio", result["adapter"])
        self.assertEqual("summarize", result["content"]["tool"])
        self.assertEqual({"text": "hello"}, result["content"]["arguments"])
        self.assertTrue(result["content"]["credential_available"])
        self.assertFalse(result["content"]["unrelated_secret_available"])
        self.assertNotIn("cli-secret", json.dumps(result))
        self.assertNotIn("must-not-leak", json.dumps(result))

    def test_cli_adapter_is_terminated_when_run_is_cancelled(self):
        script = "import time; time.sleep(10)\n"
        result_holder = {}
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "slow_cli.py"
            target.write_text(script, encoding="utf-8")
            binding = _binding("plugin", command=sys.executable, args=json.dumps([str(target)]))
            thread = threading.Thread(
                target=lambda: result_holder.setdefault(
                    "result",
                    execute_external_tool(
                        binding,
                        "fixture",
                        "wait",
                        {"_runtime_run_id": "run_cancel_external"},
                        {"timeout_ms": 10_000},
                    ),
                )
            )
            thread.start()
            for _ in range(100):
                if active_external_calls("run_cancel_external"):
                    break
                time.sleep(0.02)
            cancelled = cancel_external_calls_for_run("run_cancel_external")
            thread.join(timeout=5)

        self.assertTrue(cancelled)
        self.assertFalse(thread.is_alive())
        self.assertEqual("tool_cancelled", result_holder["result"]["code"])

    def test_mcp_stdio_performs_real_initialize_and_tool_call(self):
        server_script = textwrap.dedent("""
            from mcp.server.fastmcp import FastMCP

            server = FastMCP("CartridgeFlow test server")

            @server.tool()
            def echo(text: str) -> dict:
                return {"echo": text}

            if __name__ == "__main__":
                server.run(transport="stdio")
        """)
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mcp_fixture.py"
            target.write_text(server_script, encoding="utf-8")
            result = execute_external_tool(
                _binding("mcp", command=sys.executable, args=json.dumps([str(target)])),
                "fixture",
                "echo",
                {"text": "hello MCP", "_runtime_run_id": "run_mcp"},
                {"timeout_ms": 5_000},
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual("mcp_stdio", result["adapter"])
        self.assertIn("hello MCP", json.dumps(result["content"]))

    def test_mcp_streamable_http_performs_real_tool_call(self):
        server_script = textwrap.dedent("""
            import sys
            from mcp.server.fastmcp import FastMCP

            server = FastMCP(
                "CartridgeFlow HTTP test server",
                host="127.0.0.1",
                port=int(sys.argv[1]),
                streamable_http_path="/mcp",
                stateless_http=True,
                json_response=True,
                log_level="ERROR",
            )

            @server.tool()
            def multiply(left: int, right: int) -> dict:
                return {"product": left * right}

            if __name__ == "__main__":
                server.run(transport="streamable-http")
        """)
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mcp_http_fixture.py"
            target.write_text(server_script, encoding="utf-8")
            port = _free_port()
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            process = subprocess.Popen(
                [sys.executable, str(target), str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            try:
                _wait_for_port(port)
                result = execute_external_tool(
                    _binding("mcp", endpoint=f"http://127.0.0.1:{port}/mcp"),
                    "fixture",
                    "multiply",
                    {"left": 6, "right": 7, "_runtime_run_id": "run_mcp_http"},
                    {"timeout_ms": 5_000},
                )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        self.assertTrue(result["ok"], result)
        self.assertEqual("mcp_streamable_http", result["adapter"])
        self.assertIn("42", json.dumps(result["content"]))

    def test_node_executor_uses_real_external_adapter_path(self):
        with _http_fixture() as base_url:
            binding = _binding("remote_api", endpoint=f"{base_url}/direct", http_method="POST")
            run = {
                "run_id": "run_node_http",
                "cartridge_id": "fixture.cartridge",
                "resource_requirements": [{"role": "fixture_role", "kinds": ["remote_api"], "required": True}],
                "local_resources": {"roles": {"fixture_role": {"resource_id": "fixture-resource", "ready": True}}},
                "mcp_tools": [{
                    "id": "remote_fixture",
                    "type": "remote",
                    "server": "fixture",
                    "tool": "send",
                    "resource_role": "fixture_role",
                    "contract": {"idempotent": True, "timeout_ms": 2_000},
                }],
            }
            state = {
                "action": "remote_call",
                "params": {"mcp_tool_id": "remote_fixture", "tool_params": {"message": "from node"}, "output": "result"},
            }
            with patch("core.studio.resource_resolver.resolve_runtime_tool_binding", return_value=binding):
                result = LabNodeExecutor().execute("remote", state, {"context": {"store": {}}}, run, ".")

        self.assertFalse(result["failed"], result)
        self.assertEqual("remote_http", result["tool_results"][0]["result"]["adapter"])


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(port):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"MCP fixture did not listen on port {port}")


if __name__ == "__main__":
    unittest.main()
