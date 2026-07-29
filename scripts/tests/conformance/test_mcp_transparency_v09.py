import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.extensions import load_portable_dlc_descriptor, parse_mcp_python_source
from core.extensions.descriptor import PortableDlcValidationError
from core.lab.node_executor import LabNodeExecutor
from core.protocol import build_compatibility_report, load_base_implementation
from core.studio.resource_catalog import build_flow_resource_catalog


ROOT = Path(__file__).resolve().parents[3]


VALID_SOURCE = '''"""Fetch and normalize test feeds."""

from cartridgeflow_dlc import McpContext, mcp_operation


MCP_NODE = {
    "schema": "cartridgeflow.mcp_python.v1",
    "node_id": "fetch_news",
    "server": "media",
    "tool": "fetch_rss",
    "effect": "read_only",
    "inputs": {"feed_set": {"type": "string"}},
    "outputs": {"candidates": {"type": "object"}},
    "operations": [
        {"id": "resolve_feeds", "kind": "transform"},
        {"id": "download_feeds", "kind": "network", "capability": "network.fetch"},
        {"id": "parse_feeds", "kind": "transform"}
    ],
    "edges": [
        {"from": "resolve_feeds", "to": "download_feeds", "kind": "control"},
        {"from": "download_feeds", "to": "parse_feeds", "kind": "control"}
    ],
    "fallbacks": [
        {"id": "download_transport_fallback", "from": "download_feeds", "on": ["network_transport_failed"], "mode": "explicit", "visible": True}
    ]
}


@mcp_operation("resolve_feeds")
def op_resolve_feeds(ctx: McpContext, data: dict) -> dict:
    return {"feeds": [data["feed_set"]]}


@mcp_operation("download_feeds")
def op_download_feeds(ctx: McpContext, data: dict) -> dict:
    return {"responses": ctx.network.fetch_many(data["feeds"])}


@mcp_operation("parse_feeds")
def op_parse_feeds(ctx: McpContext, data: dict) -> dict:
    return {"candidates": data["responses"]}


OPERATIONS = {
    "resolve_feeds": op_resolve_feeds,
    "download_feeds": op_download_feeds,
    "parse_feeds": op_parse_feeds
}


def run(ctx: McpContext, inputs: dict) -> dict:
    return ctx.run_declared_graph(MCP_NODE, OPERATIONS, inputs)
'''


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _RecordingTools:
    def __init__(self, result=None):
        self.calls = 0
        self.result = result or {"ok": True, "content": {"done": True}}

    def call(self, _server, _tool, _params):
        self.calls += 1
        return dict(self.result)


class McpTransparencyV09Tests(unittest.TestCase):
    def test_parser_extracts_source_model_without_importing_dlc(self):
        model = parse_mcp_python_source(VALID_SOURCE, display_path="dlc/mcp_nodes/fetch_news.py")

        self.assertTrue(model["ok"], model["findings"])
        self.assertEqual("cartridgeflow.mcp_source_model.v1", model["schema"])
        self.assertEqual("fetch_news", model["node_id"])
        self.assertEqual("media/fetch_rss", model["tool_identity"])
        self.assertEqual("cartridgeflow.mcp_python.v1", model["format"])
        self.assertEqual(["network.fetch"], model["capabilities"])
        self.assertEqual({"resolve_feeds", "download_feeds", "parse_feeds"}, {item["id"] for item in model["operations"]})
        self.assertIn("operation:download_feeds", model["source_map"])
        self.assertTrue(model["source_digest"].startswith("sha256:"))

    def test_parser_rejects_direct_network_import_and_nonstandard_run(self):
        source = VALID_SOURCE.replace("from cartridgeflow_dlc import McpContext, mcp_operation", "import requests\nfrom cartridgeflow_dlc import McpContext, mcp_operation")
        source = source.replace("return ctx.run_declared_graph(MCP_NODE, OPERATIONS, inputs)", "return {'ok': True}")

        model = parse_mcp_python_source(source, display_path="dlc/mcp_nodes/fetch_news.py")

        self.assertFalse(model["ok"])
        codes = {item["code"] for item in model["findings"]}
        self.assertIn("MCP_DIRECT_CAPABILITY_IMPORT", codes)
        self.assertIn("MCP_RUN_NOT_STANDARD_GRAPH_RUNNER", codes)

    def test_parser_rejects_direct_filesystem_and_process_capabilities(self):
        source = VALID_SOURCE.replace(
            "from cartridgeflow_dlc import McpContext, mcp_operation",
            "import os\nfrom pathlib import Path\nfrom cartridgeflow_dlc import McpContext, mcp_operation",
        )
        source = source.replace(
            'return {"candidates": data["responses"]}',
            'Path("owned.txt").write_text("unexpected")\n    os.system("echo unexpected")\n    return {"candidates": data["responses"]}',
        )

        model = parse_mcp_python_source(source, display_path="dlc/mcp_nodes/fetch_news.py")

        self.assertFalse(model["ok"])
        codes = {item["code"] for item in model["findings"]}
        self.assertIn("MCP_DIRECT_CAPABILITY_IMPORT", codes)
        self.assertIn("MCP_DIRECT_CAPABILITY_CALL", codes)

    def test_descriptor_v3_validates_unique_source_entry_and_digest(self):
        with tempfile.TemporaryDirectory(prefix="cartridgeflow-v09-dlc-") as tmp:
            package = Path(tmp) / "dev.v09"
            source_path = package / "dlc" / "mcp_nodes" / "fetch_news.py"
            source_path.parent.mkdir(parents=True)
            source_path.write_text(VALID_SOURCE, encoding="utf-8")
            source_digest = f"sha256:{_sha256(source_path)}"

            manifest = {
                "schema_version": "1.0",
                "id": "dev.v09",
                "name": "v0.9 fixture",
                "version": "1.0.0",
                "kind": "runtime_cartridge",
                "category": "test",
                "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
                "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.9"},
                "mcp_tools": [{
                    "id": "fetch_news",
                    "node_id": "fetch_news",
                    "name": "Fetch news",
                    "type": "cartridge_dlc",
                    "server": "media",
                    "tool": "fetch_rss",
                    "enabled": True,
                    "required": True,
                    "contract": {"side_effect": "read_only", "timeout_ms": 30000}
                }],
                "portable_dlc": {"protocol": "CF-FARP@0.9", "descriptor": "dlc/descriptor.json"},
            }
            descriptor = {
                "schema": "cartridgeflow.portable_dlc.v3",
                "id": "dlc.v09",
                "version": "1.0.0",
                "owner_cartridge": "dev.v09",
                "scope": "cartridge",
                "tools": [{
                    "node_id": "fetch_news",
                    "server": "media",
                    "tool": "fetch_rss",
                    "handler": "run",
                    "effect": "read_only",
                    "timeout_ms": 30000,
                    "description": "Fetch news.",
                    "implementation": {
                        "language": "python",
                        "format": "cartridgeflow.mcp_python.v1",
                        "entry": "dlc/mcp_nodes/fetch_news.py"
                    },
                    "transparency": "declared_graph",
                    "source_digest": source_digest
                }],
                "protocols": [],
                "resources": [{"path": "dlc", "ownership": "package"}],
                "files": [{
                    "path": "dlc/mcp_nodes/fetch_news.py",
                    "sha256": _sha256(source_path),
                    "media_type": "text/x-python",
                    "role": "mcp_node_source"
                }]
            }
            (package / "dlc" / "descriptor.json").write_text(json.dumps(descriptor, indent=2), encoding="utf-8")

            loaded = load_portable_dlc_descriptor(package, manifest)

            self.assertEqual("cartridgeflow.portable_dlc.v3", loaded["schema"])
            self.assertEqual(source_digest, loaded["tools"][0]["source_digest"])

    def test_resource_catalog_v2_projects_transparent_tool_source_model(self):
        with tempfile.TemporaryDirectory(prefix="cartridgeflow-v09-dlc-") as tmp:
            package = Path(tmp) / "dev.v09"
            source_path = package / "dlc" / "mcp_nodes" / "fetch_news.py"
            source_path.parent.mkdir(parents=True)
            source_path.write_text(VALID_SOURCE, encoding="utf-8")
            source_digest = f"sha256:{_sha256(source_path)}"
            manifest = {
                "id": "dev.v09",
                "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.9"},
                "mcp_tools": [{
                    "id": "fetch_news",
                    "node_id": "fetch_news",
                    "type": "cartridge_dlc",
                    "server": "media",
                    "tool": "fetch_rss",
                    "enabled": True,
                    "required": True,
                    "transparency": "declared_graph"
                }],
                "portable_dlc": {"protocol": "CF-FARP@0.9", "descriptor": "dlc/descriptor.json"},
            }
            descriptor = {
                "schema": "cartridgeflow.portable_dlc.v3",
                "id": "dlc.v09",
                "version": "1.0.0",
                "owner_cartridge": "dev.v09",
                "scope": "cartridge",
                "tools": [{
                    "node_id": "fetch_news",
                    "server": "media",
                    "tool": "fetch_rss",
                    "handler": "run",
                    "effect": "read_only",
                    "timeout_ms": 30000,
                    "description": "Fetch news.",
                    "implementation": {"language": "python", "format": "cartridgeflow.mcp_python.v1", "entry": "dlc/mcp_nodes/fetch_news.py"},
                    "transparency": "declared_graph",
                    "source_digest": source_digest
                }],
                "protocols": [],
                "resources": [{"path": "dlc", "ownership": "package"}],
                "files": [{"path": "dlc/mcp_nodes/fetch_news.py", "sha256": _sha256(source_path), "media_type": "text/x-python", "role": "mcp_node_source"}]
            }
            (package / "dlc" / "descriptor.json").write_text(json.dumps(descriptor), encoding="utf-8")
            flow = {"states": {"fetch": {"type": "process", "kind": "mcp_read", "executor": "mcp", "allowed_tools": ["fetch_news"]}}}

            catalog = build_flow_resource_catalog(ROOT, manifest, flow, package_path=package)
            item = next(item for item in catalog["tools"] if item["id"] == "fetch_news")

            self.assertEqual("cartridgeflow.flow_resource_catalog.v2", catalog["schema"])
            self.assertEqual("declared_graph", item["transparency"])
            self.assertEqual("parsed", item["parse_status"])
            self.assertEqual(3, item["operation_count"])
            self.assertEqual(source_digest, item["source_digest"])
            self.assertEqual(["network.fetch"], item["broker_capabilities"])
            self.assertEqual(["resolve_feeds", "download_feeds", "parse_feeds"], [operation["id"] for operation in item["operation_graph"]["operations"]])

    def test_v09_operation_trace_uses_source_model_operation_identity(self):
        executor = LabNodeExecutor(ROOT)
        tools = _RecordingTools()
        executor._builtin_mcp = tools
        source_model = parse_mcp_python_source(VALID_SOURCE, display_path="dlc/mcp_nodes/fetch_news.py")
        run = {
            "run_id": "run_v09_trace",
            "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.9"},
            "mcp_tools": [{
                "id": "fetch_news",
                "type": "cartridge_dlc",
                "server": "media",
                "tool": "fetch_rss",
                "transparency": "declared_graph",
                "source_digest": source_model["source_digest"],
                "operation_graph": {
                    "operations": source_model["operations"],
                    "edges": source_model["edges"],
                    "fallbacks": source_model["fallbacks"],
                    "capabilities": source_model["capabilities"],
                },
                "broker_capabilities": ["network.fetch"],
                "contract": {"side_effect": "read_only"},
            }],
        }
        state = {
            "type": "process",
            "protocol_version": "0.9",
            "kind": "mcp_read",
            "executor": "mcp",
            "effect": "read_only",
            "allowed_tools": ["fetch_news"],
            "output": "result",
        }

        result = executor.execute("fetch", state, {"context": {"store": {}}}, run, ROOT)

        self.assertFalse(result["failed"])
        self.assertEqual(1, tools.calls)
        event_types = [item["type"] for item in result["operation_events"]]
        self.assertIn("tool_operation_started", event_types)
        self.assertIn("capability_dependency", event_types)
        self.assertIn("tool_operation_completed", event_types)
        self.assertIn("download_feeds", {item["operation_id"] for item in result["operation_events"]})

    def test_v09_broker_blocks_operation_without_declared_capability(self):
        executor = LabNodeExecutor(ROOT)
        tools = _RecordingTools()
        executor._builtin_mcp = tools
        run = {
            "run_id": "run_v09_broker",
            "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.9"},
            "mcp_tools": [{
                "id": "fetch_news",
                "type": "cartridge_dlc",
                "server": "media",
                "tool": "fetch_rss",
                "transparency": "declared_graph",
                "operation_graph": {"operations": [{"id": "download_feeds", "kind": "network"}]},
                "broker_capabilities": [],
                "contract": {"side_effect": "read_only"},
            }],
        }
        state = {
            "type": "process",
            "protocol_version": "0.9",
            "kind": "mcp_read",
            "executor": "mcp",
            "effect": "read_only",
            "allowed_tools": ["fetch_news"],
            "output": "result",
        }

        result = executor.execute("fetch", state, {"context": {"store": {}}}, run, ROOT)

        self.assertTrue(result["failed"])
        self.assertEqual(0, tools.calls)
        self.assertEqual("HOST_CAPABILITY_BROKER_DENIED", result["tool_results"][0]["result"]["code"])
        self.assertIn("MCP_OPERATION_CAPABILITY_MISSING", [item["code"] for item in result["tool_results"][0]["result"]["findings"]])
        self.assertIn("tool_operation_failed", [item["type"] for item in result["operation_events"]])

    def test_v09_compatibility_blocks_tool_without_transparency(self):
        base = load_base_implementation(ROOT)
        manifest = {
            "id": "dev.v09.bad-tool",
            "version": "1.0.0",
            "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
            "runtime_contract": {
                "protocol": "CF-FARP",
                "protocol_version": "0.9",
                "required_profiles": ["runtime_core", "flow_analysis", "tool_transparency"],
                "recommended_profiles": [],
                "required_capabilities": ["root_flow_execution", "flow_analysis_report_v1", "mcp_source_model_v1"],
                "optional_capabilities": [],
                "required_tools": [],
                "optional_tools": [],
            },
            "delivery_readiness": {"level": "dev"},
            "mcp_tools": [{"id": "fetch_news", "type": "cartridge_dlc", "server": "media", "tool": "fetch_rss", "enabled": True}],
        }
        flow = {
            "protocol": {"id": "CF-FARP", "version": "0.9"},
            "start": "start",
            "states": {"start": {"type": "system", "next": "complete"}, "complete": {"type": "terminal"}},
        }

        report = build_compatibility_report(base, manifest, flow, ROOT)

        self.assertFalse(report["ok"])
        self.assertIn("TOOL_TRANSPARENCY_MISSING", [item["code"] for item in report["findings"]])

    def test_descriptor_v3_rejects_stale_source_digest(self):
        with tempfile.TemporaryDirectory(prefix="cartridgeflow-v09-dlc-") as tmp:
            package = Path(tmp) / "dev.v09"
            source_path = package / "dlc" / "mcp_nodes" / "fetch_news.py"
            source_path.parent.mkdir(parents=True)
            source_path.write_text(VALID_SOURCE, encoding="utf-8")

            manifest = {
                "id": "dev.v09",
                "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.9"},
                "mcp_tools": [{"server": "media", "tool": "fetch_rss", "enabled": True}],
                "portable_dlc": {"protocol": "CF-FARP@0.9", "descriptor": "dlc/descriptor.json"},
            }
            descriptor = {
                "schema": "cartridgeflow.portable_dlc.v3",
                "id": "dlc.v09",
                "version": "1.0.0",
                "owner_cartridge": "dev.v09",
                "scope": "cartridge",
                "tools": [{
                    "node_id": "fetch_news",
                    "server": "media",
                    "tool": "fetch_rss",
                    "handler": "run",
                    "effect": "read_only",
                    "timeout_ms": 30000,
                    "description": "Fetch news.",
                    "implementation": {"language": "python", "format": "cartridgeflow.mcp_python.v1", "entry": "dlc/mcp_nodes/fetch_news.py"},
                    "transparency": "declared_graph",
                    "source_digest": "sha256:" + "0" * 64
                }],
                "protocols": [],
                "resources": [{"path": "dlc", "ownership": "package"}],
                "files": [{"path": "dlc/mcp_nodes/fetch_news.py", "sha256": _sha256(source_path), "media_type": "text/x-python", "role": "mcp_node_source"}]
            }
            (package / "dlc" / "descriptor.json").write_text(json.dumps(descriptor), encoding="utf-8")

            with self.assertRaisesRegex(PortableDlcValidationError, "source_digest"):
                load_portable_dlc_descriptor(package, manifest)


if __name__ == "__main__":
    unittest.main()
