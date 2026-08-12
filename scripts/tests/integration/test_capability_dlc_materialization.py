import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.extensions import load_portable_dlc_descriptor
from core.protocol.capability_cartridges import build_flow_capability_release, create_semantic_recipe
from core.studio.authoring_service import AuthoringSessionStore
from core.studio.capability_cartridges import CapabilityCartridgeStore
from core.studio.creator_runtime_bridge import CreatorRuntimeBridge


ROOT = Path(__file__).resolve().parents[3]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _capability_release() -> dict:
    backend = '''"""Package-scoped worker entry."""

from core.extensions.worker_sdk import DlcWorkerRegistry


def invoke(request: dict) -> dict:
    registry = DlcWorkerRegistry(request["workspace_root"], request["package_path"])
    return registry.call(request.get("server", ""), request.get("tool", ""), request.get("params") or {})
'''
    source = '''"""Normalize a generic value through a declared operation graph."""

from cartridgeflow_dlc import McpContext, mcp_operation


MCP_NODE = {
    "schema": "cartridgeflow.mcp_python.v1",
    "node_id": "value_normalizer",
    "server": "value_tools",
    "tool": "normalize",
    "effect": "read_only",
    "inputs": {"value": {"type": "string"}, "prefix": {"type": "string"}},
    "outputs": {"result": {"type": "string"}},
    "operations": [{"id": "normalize_value", "kind": "transform"}],
    "edges": [],
    "fallbacks": [],
}


@mcp_operation("normalize_value")
def op_normalize_value(ctx: McpContext, data: dict) -> dict:
    return {"result": str(data.get("prefix") or "") + str(data.get("value") or "").strip()}


OPERATIONS = {"normalize_value": op_normalize_value}


def run(ctx: McpContext, inputs: dict) -> dict:
    return ctx.run_declared_graph(MCP_NODE, OPERATIONS, inputs)
'''
    descriptor = {
        "schema": "cartridgeflow.portable_dlc.v3",
        "id": "dlc.value-normalizer",
        "version": "1.0.0",
        "owner_cartridge": "dev.value-normalizer",
        "scope": "cartridge",
        "backend": {"transport": "json_stdio_worker", "entry": "dlc/backend/entry.py"},
        "tools": [{
            "node_id": "value_normalizer", "server": "value_tools", "tool": "normalize",
            "handler": "run", "effect": "read_only", "timeout_ms": 30000,
            "description": "Normalize a generic input value.",
            "implementation": {
                "language": "python", "format": "cartridgeflow.mcp_python.v1",
                "entry": "dlc/mcp_nodes/value_normalizer.py",
            },
            "transparency": "declared_graph", "source_digest": f"sha256:{_sha256(source)}",
        }],
        "protocols": [],
        "resources": [{"path": "dlc", "ownership": "package"}],
        "files": [
            {
                "path": "dlc/backend/entry.py", "sha256": _sha256(backend),
                "media_type": "text/x-python", "role": "backend_entry",
            },
            {
                "path": "dlc/mcp_nodes/value_normalizer.py", "sha256": _sha256(source),
                "media_type": "text/x-python", "role": "mcp_node_source",
            },
        ],
    }
    manifest = {
        "schema_version": "1.0",
        "id": "dev.value-normalizer",
        "name": "Value normalizer",
        "version": "1.0.0",
        "kind": "runtime_cartridge",
        "category": "capability",
        "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.3"},
        "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "1.1"},
        "root_flow": {"entry": "root.flow.json", "mode": "lifecycle", "required": True},
        "runtime": {"type": "capability_flow"},
        "permissions": [],
        "mcp_tools": [{
            "id": "value_normalize", "node_id": "value_normalizer", "name": "Normalize value",
            "type": "cartridge_dlc", "server": "value_tools", "tool": "normalize",
            "required": True, "enabled": True, "transparency": "declared_graph",
            "contract": {"side_effect": "read_only", "timeout_ms": 30000},
        }],
        "portable_dlc": {"protocol": "CF-FARP@1.1", "descriptor": "dlc/descriptor.json"},
        "inputs": [],
        "outputs": [{"id": "result", "label": "Normalized value", "type": "string", "required": True}],
        "delivery": {"type": "structured", "primary_output": "result"},
    }
    root_flow = {
        "schema_version": "1.0",
        "id": "dev.value-normalizer.root",
        "mode": "lifecycle",
        "protocol": {"id": "CF-FARP", "version": "1.1"},
        "start": "start",
        "states": {
            "start": {"type": "control", "title": "Start", "locked": True},
            "normalize": {
                "type": "process", "kind": "mcp_read", "executor": "mcp", "effect": "read_only",
                "action": "tool_call", "title": "Normalize value", "allowed_tools": ["value_normalize"],
                "mcp_binding": {"mode": "read_only", "allowed_tools": ["value_normalize"]},
                "inputs": {},
                "outputs": {"result": {"schema": {"type": "string"}, "target": {"type": "store", "key": "result"}}},
                "params": {
                    "output": "result",
                    "tools": [{
                        "type": "cartridge_dlc", "server": "value_tools", "tool": "normalize",
                        "mcp_tool_id": "value_normalize", "params": {"value": "sample", "prefix": ""},
                        "output": "result", "enabled": True, "strict": True,
                    }],
                },
            },
            "complete": {"type": "terminal", "title": "Complete", "locked": True},
            "failed": {"type": "terminal", "title": "Failed", "locked": True},
        },
        "execution_plan": {
            "schema": "cartridgeflow.execution_plan.v1", "entry": "start",
            "edges": [
                {"id": "start_normalize", "kind": "sequence", "from": "start", "to": "normalize"},
                {"id": "normalize_complete", "kind": "sequence", "from": "normalize", "to": "complete"},
                {
                    "id": "normalize_failed", "kind": "failure", "from": "normalize", "to": "failed",
                    "failure": {"id": "normalize_failure", "causes": ["exception"]},
                },
            ],
        },
    }
    source_files = {
        "dlc/backend/entry.py": backend,
        "dlc/descriptor.json": json.dumps(descriptor, ensure_ascii=True, indent=2),
        "dlc/mcp_nodes/value_normalizer.py": source,
    }
    return build_flow_capability_release(
        capability_id="workspace.value-normalizer",
        revision=1,
        trust_scope="workspace",
        label="Normalize a value",
        description="Apply a user-selected prefix to a normalized value.",
        match_terms=["normalize", "prefix", "value"],
        editable_fields=[{
            "id": "prefix", "label": "Prefix", "value_type": "string", "required": True, "default": "",
        }],
        creator_bindings={"prefix": "states.normalize.params.tools.0.params.prefix"},
        public_inputs=[],
        public_outputs=[{
            "id": "result", "label": "Normalized value", "required": True,
            "schema": {"type": "string"}, "store_key": "result",
        }],
        dependencies=[],
        source_flow_id=manifest["id"],
        manifest=manifest,
        root_flow=root_flow,
        source_files=source_files,
        evidence={"status": "passed", "checks": [{"id": "flow_contract", "status": "passed"}]},
    )


class CapabilityDlcMaterializationTests(unittest.TestCase):
    def test_semantic_mapping_recursively_packages_capability_owned_dlc(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            registry = CapabilityCartridgeStore(temp / "registry")
            release = registry.put(_capability_release(), expected_revision=0)
            recipe, publications = create_semantic_recipe(
                "recipe.normalize",
                "Normalize a labeled value",
                {
                    "nodes": [{
                        "id": "transform", "label": "Normalize", "description": "Normalize one value.",
                        "needed_capability": "value normalization", "capability_id": release["id"],
                        "values": {"prefix": "tag:"},
                    }],
                    "relations": [],
                },
                registry.list_active(),
            )
            sessions = AuthoringSessionStore(temp / "sessions")
            sessions.create_from_semantic_recipe("creator.normalize", "project.normalize", recipe, publications)
            sessions.freeze("creator.normalize", ["transform"], author="creator", summary="Reviewed mapping")

            result = CreatorRuntimeBridge(ROOT, temp / "packages", registry).package(
                sessions, "creator.normalize", expected_revision=1,
            )
            extracted = temp / "extracted"
            with zipfile.ZipFile(temp / "packages" / result["filename"]) as bundle:
                bundle.extractall(extracted)

            manifest_path = next(extracted.rglob("manifest.json"))
            package_root = manifest_path.parent
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            root_flow = json.loads((package_root / "root.flow.json").read_text(encoding="utf-8"))
            normalize = root_flow["states"]["cap.transform.normalize"]
            self.assertEqual("tag:", normalize["params"]["tools"][0]["params"]["prefix"])
            self.assertEqual("cap.transform.result", normalize["params"]["output"])
            self.assertEqual(release["digest"], normalize["capability_release"]["digest"])

            descriptor = load_portable_dlc_descriptor(package_root, manifest)
            implementation_entry = descriptor["tools"][0]["implementation"]["entry"]
            self.assertEqual(
                "dlc/mcp_nodes/workspace.value-normalizer.1/value_normalizer.py",
                implementation_entry,
            )
            self.assertTrue((package_root / implementation_entry).is_file())
            self.assertEqual(
                release["digest"],
                manifest["creator_lineage"]["capability_dependency_closure"][0]["digest"],
            )


if __name__ == "__main__":
    unittest.main()
