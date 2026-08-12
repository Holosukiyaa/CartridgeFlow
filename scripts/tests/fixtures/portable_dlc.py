from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PortableDlcFixture:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cartridgeflow-dlc-")
        self.root = Path(self.temp.name)
        self.package = self.root / "dev.fixture"
        self.worker_journal_dir = self.root / ".data" / "runtime" / "workers"
        backend = self.package / "dlc" / "backend" / "entry.py"
        frontend = self.package / "dlc" / "frontend" / "index.html"
        backend.parent.mkdir(parents=True)
        frontend.parent.mkdir(parents=True)
        backend.write_text(
            """from __future__ import annotations
import json
from core.extensions.worker_sdk import DlcWorkerRegistry

def invoke(request: dict) -> dict:
    registry = DlcWorkerRegistry(request["workspace_root"], request["package_path"])
    registry._registry.setdefault("fixture", {})["echo"] = lambda params: {
        "ok": True,
        "content": json.dumps({"value": params.get("value")}, ensure_ascii=False),
    }
    return registry.call(request.get("server", ""), request.get("tool", ""), request.get("params") or {})
""",
            encoding="utf-8",
        )
        frontend.write_text("<!doctype html><title>Fixture DLC</title>", encoding="utf-8")
        self.manifest = {
            "schema_version": "1.0",
            "id": "dev.fixture",
            "name": "Fixture",
            "version": "1.0.0",
            "kind": "runtime_cartridge",
            "category": "test",
            "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
            "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.6"},
            "mcp_tools": [{
                "id": "fixture_echo",
                "name": "Fixture echo",
                "type": "builtin",
                "server": "fixture",
                "tool": "echo",
                "enabled": True,
                "required": True,
                "contract": {"side_effect": "read_only", "timeout_ms": 30000},
            }],
            "portable_dlc": {"protocol": "CF-FARP@0.6", "descriptor": "dlc/descriptor.json"},
        }
        descriptor = {
            "schema": "cartridgeflow.portable_dlc.v1",
            "id": "dlc.fixture",
            "version": "1.0.0",
            "owner_cartridge": "dev.fixture",
            "scope": "cartridge",
            "backend": {"transport": "json_stdio_worker", "entry": "dlc/backend/entry.py"},
            "frontend": {"sandbox": "isolated_iframe", "entry": "dlc/frontend/index.html", "context_keys": ["fixture_project"]},
            "tools": [{
                "server": "fixture",
                "tool": "echo",
                "handler": "backend.entry:invoke",
                "effect": "read_only",
                "timeout_ms": 30000,
                "description": "Return a UTF-8 test value.",
                "params": {},
            }],
            "protocols": [],
            "resources": [
                {"path": "dlc", "ownership": "package"},
                {"path": ".data/user/cartridge_data/dev.fixture", "ownership": "private_data"},
                {"path": "test_output", "ownership": "user_artifact"},
            ],
            "files": [
                {"path": "dlc/backend/entry.py", "sha256": _sha256(backend)},
                {"path": "dlc/frontend/index.html", "sha256": _sha256(frontend)},
            ],
        }
        descriptor_path = self.package / "dlc" / "descriptor.json"
        descriptor_path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2), encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.temp.cleanup()


class TransparentDlcFixture:
    """Business-neutral CF-FARP@1.1 declared-graph DLC fixture."""

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cartridgeflow-transparent-dlc-")
        self.root = Path(self.temp.name)
        self.package = self.root / "dev.transparent-fixture"
        self.worker_journal_dir = self.root / "workers"
        backend = self.package / "dlc" / "backend" / "entry.py"
        source = self.package / "dlc" / "mcp_nodes" / "value_gate.py"
        backend.parent.mkdir(parents=True)
        source.parent.mkdir(parents=True)
        backend.write_text(
            '''"""Package-scoped worker entry."""

from core.extensions.worker_sdk import DlcWorkerRegistry


def invoke(request: dict) -> dict:
    registry = DlcWorkerRegistry(request["workspace_root"], request["package_path"])
    return registry.call(request.get("server", ""), request.get("tool", ""), request.get("params") or {})
''',
            encoding="utf-8",
        )
        source.write_text(
            '''"""Declared-graph validation fixture."""

from cartridgeflow_dlc import McpContext, mcp_operation


MCP_NODE = {
    "schema": "cartridgeflow.mcp_python.v1",
    "node_id": "value_gate",
    "server": "fixture_graph",
    "tool": "validate",
    "effect": "read_only",
    "inputs": {"value": {"type": "string"}},
    "outputs": {"value": {"type": "string"}},
    "operations": [{"id": "validate_value", "kind": "transform"}],
    "edges": [],
    "fallbacks": [],
}


@mcp_operation("validate_value")
def op_validate_value(ctx: McpContext, data: dict) -> dict:
    value = data.get("value")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("value must be a non-empty string")
    return {"value": value.strip()}


OPERATIONS = {"validate_value": op_validate_value}


def run(ctx: McpContext, inputs: dict) -> dict:
    return ctx.run_declared_graph(MCP_NODE, OPERATIONS, inputs)
''',
            encoding="utf-8",
        )
        self.manifest = {
            "schema_version": "1.0",
            "id": "dev.transparent-fixture",
            "name": "Transparent DLC fixture",
            "version": "1.0.0",
            "kind": "runtime_cartridge",
            "category": "test",
            "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.3"},
            "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "1.1"},
            "mcp_tools": [{
                "id": "fixture_validate",
                "node_id": "value_gate",
                "name": "Validate value",
                "type": "cartridge_dlc",
                "server": "fixture_graph",
                "tool": "validate",
                "enabled": True,
                "required": True,
                "transparency": "declared_graph",
                "contract": {"side_effect": "read_only", "timeout_ms": 30000},
            }],
            "portable_dlc": {"protocol": "CF-FARP@1.1", "descriptor": "dlc/descriptor.json"},
        }
        descriptor = {
            "schema": "cartridgeflow.portable_dlc.v3",
            "id": "dlc.transparent-fixture",
            "version": "1.0.0",
            "owner_cartridge": "dev.transparent-fixture",
            "scope": "cartridge",
            "backend": {"transport": "json_stdio_worker", "entry": "dlc/backend/entry.py"},
            "tools": [{
                "node_id": "value_gate",
                "server": "fixture_graph",
                "tool": "validate",
                "handler": "run",
                "effect": "read_only",
                "timeout_ms": 30000,
                "description": "Validate a generic test value.",
                "implementation": {
                    "language": "python",
                    "format": "cartridgeflow.mcp_python.v1",
                    "entry": "dlc/mcp_nodes/value_gate.py",
                },
                "transparency": "declared_graph",
                "source_digest": f"sha256:{_sha256(source)}",
            }],
            "protocols": [],
            "resources": [{"path": "dlc", "ownership": "package"}],
            "files": [
                {
                    "path": "dlc/backend/entry.py",
                    "sha256": _sha256(backend),
                    "media_type": "text/x-python",
                    "role": "backend_entry",
                },
                {
                    "path": "dlc/mcp_nodes/value_gate.py",
                    "sha256": _sha256(source),
                    "media_type": "text/x-python",
                    "role": "mcp_node_source",
                },
            ],
        }
        descriptor_path = self.package / "dlc" / "descriptor.json"
        descriptor_path.write_text(json.dumps(descriptor, ensure_ascii=True, indent=2), encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.temp.cleanup()
