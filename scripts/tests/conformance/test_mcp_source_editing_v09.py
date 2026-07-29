import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.extensions.mcp_source_editor import (
    McpSourceEditError,
    add_mcp_operation,
    edit_mcp_source_graph,
    update_descriptor_source_digest,
)
from core.extensions.mcp_source_parser import parse_mcp_python_source


SOURCE = '''from cartridgeflow_dlc import McpContext, mcp_operation

MCP_NODE = {
    "schema": "cartridgeflow.mcp_python.v1",
    "node_id": "demo_node",
    "server": "demo",
    "tool": "run",
    "operations": [{"id": "start", "kind": "transform"}],
    "edges": [],
    "fallbacks": []
}

@mcp_operation("start")
def op_start(ctx: McpContext, data: dict) -> dict:
    return data

OPERATIONS = {"start": op_start}

def run(ctx: McpContext, inputs: dict) -> dict:
    return ctx.run_declared_graph(MCP_NODE, OPERATIONS, inputs)
'''


class McpSourceEditingV09Tests(unittest.TestCase):
    def test_operation_graph_edit_preserves_static_source_contract(self):
        before = parse_mcp_python_source(SOURCE, display_path="dlc/mcp_nodes/demo_node.py")
        self.assertTrue(before["ok"], before["findings"])

        edited, after = edit_mcp_source_graph(
            SOURCE,
            expected_source_digest=before["source_digest"],
            graph={
                "edges": [{"from": "start", "to": "start", "kind": "control"}],
                "fallbacks": [{
                    "id": "visible_fallback",
                    "from": "start",
                    "on": ["failed"],
                    "mode": "explicit",
                    "visible": True,
                }],
            },
        )

        self.assertTrue(after["ok"], after["findings"])
        self.assertNotEqual(before["source_digest"], after["source_digest"])
        self.assertEqual("start", after["edges"][0]["from"])
        self.assertEqual("visible_fallback", after["fallbacks"][0]["id"])
        self.assertNotIn("import requests", edited)

    def test_add_operation_updates_node_decorator_and_registry(self):
        before = parse_mcp_python_source(SOURCE)
        edited, after = add_mcp_operation(
            SOURCE,
            expected_source_digest=before["source_digest"],
            operation={"id": "finish", "kind": "transform"},
        )

        self.assertTrue(after["ok"], after["findings"])
        self.assertIn('@mcp_operation("finish")', edited)
        self.assertIn('"finish": op_finish', edited)
        self.assertEqual({"start", "finish"}, {item["id"] for item in after["operations"]})

    def test_stale_digest_is_rejected(self):
        with self.assertRaises(McpSourceEditError) as context:
            edit_mcp_source_graph(
                SOURCE,
                expected_source_digest="sha256:" + "0" * 64,
                graph={"edges": []},
            )
        self.assertEqual("MCP_SOURCE_DIGEST_CONFLICT", context.exception.code)

    def test_descriptor_and_manifest_digests_follow_source_edit(self):
        with tempfile.TemporaryDirectory(prefix="cartridgeflow-v09-edit-") as temp_dir:
            package = Path(temp_dir)
            source_path = package / "dlc" / "mcp_nodes" / "demo_node.py"
            descriptor_path = package / "dlc" / "descriptor.json"
            source_path.parent.mkdir(parents=True)
            source_path.write_text(SOURCE, encoding="utf-8")
            descriptor = {
                "schema": "cartridgeflow.portable_dlc.v3",
                "id": "dlc.demo",
                "version": "1.0.0",
                "owner_cartridge": "dev.demo",
                "scope": "cartridge",
                "tools": [{
                    "node_id": "demo_node",
                    "server": "demo",
                    "tool": "run",
                    "implementation": {"entry": "dlc/mcp_nodes/demo_node.py"},
                }],
                "files": [{
                    "path": "dlc/mcp_nodes/demo_node.py",
                    "sha256": hashlib.sha256(SOURCE.encode("utf-8")).hexdigest(),
                }],
            }
            descriptor_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
            manifest = {
                "id": "dev.demo",
                "portable_dlc": {"descriptor": "dlc/descriptor.json"},
                "mcp_tools": [{"node_id": "demo_node", "server": "demo", "tool": "run"}],
            }

            edited, model = add_mcp_operation(
                SOURCE,
                expected_source_digest=parse_mcp_python_source(SOURCE)["source_digest"],
                operation={"id": "finish", "kind": "transform"},
            )
            source_path.write_bytes(edited.encode("utf-8"))
            result = update_descriptor_source_digest(package, manifest, node_id="demo_node", source_model=model)

            updated_descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
            self.assertEqual(model["source_digest"], result["source_digest"])
            self.assertEqual(model["source_digest"], updated_descriptor["tools"][0]["source_digest"])
            self.assertEqual(model["source_digest"], manifest["mcp_tools"][0]["source_digest"])
            self.assertEqual(
                hashlib.sha256(edited.encode("utf-8")).hexdigest(),
                updated_descriptor["files"][0]["sha256"],
            )

    def test_source_edit_rolls_back_every_file_when_manifest_write_fails(self):
        from backend import main

        with tempfile.TemporaryDirectory(prefix="cartridgeflow-v09-rollback-") as temp_dir:
            package = Path(temp_dir)
            source_path = package / "dlc" / "mcp_nodes" / "demo_node.py"
            descriptor_path = package / "dlc" / "descriptor.json"
            manifest_path = package / "manifest.json"
            source_path.parent.mkdir(parents=True)
            source_path.write_text(SOURCE, encoding="utf-8")
            descriptor = {
                "schema": "cartridgeflow.portable_dlc.v3",
                "id": "dlc.demo",
                "version": "1.0.0",
                "owner_cartridge": "dev.demo",
                "scope": "cartridge",
                "tools": [{
                    "node_id": "demo_node",
                    "server": "demo",
                    "tool": "run",
                    "implementation": {"entry": "dlc/mcp_nodes/demo_node.py"},
                }],
                "files": [{
                    "path": "dlc/mcp_nodes/demo_node.py",
                    "sha256": hashlib.sha256(SOURCE.encode("utf-8")).hexdigest(),
                }],
            }
            descriptor_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
            manifest = {
                "id": "dev.demo",
                "portable_dlc": {"descriptor": "dlc/descriptor.json"},
                "mcp_tools": [{"node_id": "demo_node", "server": "demo", "tool": "run"}],
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            before = {path: path.read_bytes() for path in (source_path, descriptor_path, manifest_path)}
            edited, model = add_mcp_operation(
                SOURCE,
                expected_source_digest=parse_mcp_python_source(SOURCE)["source_digest"],
                operation={"id": "finish", "kind": "transform"},
            )

            def fail_manifest_write(_cartridge_id, _files, _manifest):
                manifest_path.write_text('{"partially_written":', encoding="utf-8")
                raise OSError("simulated manifest failure")

            with patch.object(main.dev_flow_manager, "read_files", return_value={"manifest": before[manifest_path].decode("utf-8")}):
                with patch.object(main, "_write_manifest_tools", side_effect=fail_manifest_write):
                    with self.assertRaises(OSError):
                        main._persist_mcp_source_edit("dev.demo", "demo_node", manifest, package, source_path, edited, model)

            for path, content in before.items():
                self.assertEqual(content, path.read_bytes(), path.name)


if __name__ == "__main__":
    unittest.main()
