import json
import re
import unittest
from pathlib import Path

from core.protocol import ProtocolRegistry, build_compatibility_report, load_base_implementation
from core.lab.graph import FlowGraphBuilder


ROOT = Path(__file__).resolve().parents[3]
DOCUMENT = ROOT / "docs/protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.9.md"


class ProtocolV09SpecificationTests(unittest.TestCase):
    def test_registry_and_base_publish_v09_partial_support(self):
        registry_data = json.loads((ROOT / "protocol/releases/CF-FARP-0.9.json").read_text(encoding="utf-8"))
        self.assertEqual("0.9", registry_data["version"])
        self.assertEqual({"id": "CF-FARP", "version": "0.8"}, registry_data["supersedes"])
        self.assertEqual("vocabulary/capabilities-0.9.json", registry_data["capabilities_file"])
        self.assertEqual("vocabulary/profiles-0.9.json", registry_data["profiles_file"])
        self.assertEqual(DOCUMENT, ROOT / registry_data["document"])

        registry = ProtocolRegistry(ROOT)
        self.assertTrue(registry.recognizes_protocol("CF-FARP", "0.9"))
        self.assertTrue(registry.supports_protocol("CF-FARP", "0.9"))

        base = load_base_implementation(ROOT)
        supported = {(item["id"], item["version"]) for item in base["supported_protocols"]}
        self.assertIn(("CF-FARP", "0.9"), supported)
        self.assertIn("tool_transparency", base["profiles"])
        self.assertIn("mcp_source_model_v1", base["capabilities"])
        self.assertIn("portable_dlc_descriptor_v3", base["capabilities"])

        report = build_compatibility_report(
            base,
            {
                "id": "test.v09.partial-supported",
                "version": "0.0.1",
                "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
                "runtime_contract": {
                    "protocol": "CF-FARP",
                    "protocol_version": "0.9",
                    "required_profiles": ["runtime_core", "flow_analysis", "tool_transparency"],
                    "recommended_profiles": [],
                    "required_capabilities": [
                        "root_flow_execution",
                        "flow_analysis_report_v1",
                        "mcp_source_model_v1",
                    ],
                    "optional_capabilities": [],
                    "required_tools": [],
                    "optional_tools": [],
                },
                "asset_registry": "assets/registry.json",
                "delivery_readiness": {"level": "dev"},
                "mcp_tools": [],
            },
            {
                "protocol": {"id": "CF-FARP", "version": "0.9"},
                "start": "start",
                "states": {
                    "start": {"type": "system", "next": "complete"},
                    "complete": {"type": "terminal"},
                },
            },
            ROOT,
        )
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual("supported", report["protocol"]["lifecycle"])
        self.assertEqual("CF-FARP@0.9", report["flow_contract"]["protocol"])

    def test_v09_document_is_standalone_mcp_transparency_spec(self):
        text = DOCUMENT.read_text(encoding="utf-8")
        self.assertIn("协议编号：`CF-FARP-0.9`", text)
        for term in [
            "tool_transparency",
            "legacy_opaque",
            "cartridgeflow.portable_dlc.v3",
            "cartridgeflow.mcp_python.v1",
            "cartridgeflow.mcp_source_model.v1",
            "ctx.run_declared_graph",
            "host_capability_broker",
            "tool_operation_started",
            "resource_access_requested",
            "MCP_SOURCE_OPAQUE_CONTROL_FLOW",
        ]:
            self.assertIn(term, text)

        headings = re.findall(r"^## (.+)$", text, re.MULTILINE)

        def anchor(title):
            value = re.sub(r"[^\w\- ]", "", title.strip().lower(), flags=re.UNICODE)
            return re.sub(r" +", "-", value)

        heading_anchors = {anchor(item) for item in headings}
        first_section = re.search(r"^## 1\..+$", text, re.MULTILINE)
        self.assertIsNotNone(first_section)
        toc = text[text.index("## 目录"):first_section.start()]
        targets = re.findall(r"\]\(#([^\)]+)\)", toc)
        self.assertEqual(22, len(targets))
        self.assertEqual([], [target for target in targets if target not in heading_anchors])

    def test_v09_tool_transparency_vocabulary_is_registered(self):
        capabilities = json.loads((ROOT / "protocol/vocabulary/capabilities-0.9.json").read_text(encoding="utf-8"))
        profiles = json.loads((ROOT / "protocol/vocabulary/profiles-0.9.json").read_text(encoding="utf-8"))
        registered = {item["id"] for item in capabilities["capabilities"]}
        profile_ids = {item["id"] for item in profiles["profiles"]}

        self.assertIn("tool_transparency", profile_ids)
        self.assertEqual([], [item["profile"] for item in capabilities["capabilities"] if item["profile"] not in profile_ids])
        for capability in [
            "mcp_node_source_format_v1",
            "mcp_node_file_identity",
            "mcp_source_static_parse",
            "mcp_source_model_v1",
            "compound_tool_operation_graph",
            "tool_stage_trace_v1",
            "tool_source_provenance",
            "explicit_fallback_policy",
            "host_capability_broker",
            "opaque_tool_visibility_guard",
            "mcp_graph_authoring_operations",
            "mcp_source_digest_guard",
            "portable_dlc_descriptor_v3",
            "tool_resource_catalog_v2",
        ]:
            self.assertIn(capability, registered)

    def test_v09_authoring_helpers_keep_nodes_and_edges_typed(self):
        from backend.main import _ensure_typed_node_contracts, _sync_flow_edges_from_next

        root_flow = {
            "protocol": {"id": "CF-FARP", "version": "0.9"},
            "start": "start",
            "states": {
                "start": {"type": "system", "next": "work"},
                "work": {"type": "process", "kind": "transfer", "next": "complete"},
                "complete": {"type": "terminal"},
            },
            "edges": [{"from": "start", "to": "complete", "scope": "root"}],
        }

        _ensure_typed_node_contracts(root_flow, root_flow["states"]["work"])
        _sync_flow_edges_from_next(root_flow)

        self.assertEqual({}, root_flow["states"]["work"]["inputs"])
        self.assertEqual({}, root_flow["states"]["work"]["outputs"])
        self.assertNotIn("edges", root_flow)
        self.assertEqual(
            [
                {"kind": "control", "from": "start", "to": "work"},
                {"kind": "control", "from": "work", "to": "complete"},
            ],
            root_flow["control_edges"],
        )

    def test_graph_preflight_matches_dev_runtime_and_allows_outputless_terminal(self):
        manifest = {
            "id": "test.v09.outputless-terminal",
            "version": "0.0.1",
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
            "asset_registry": "assets/registry.json",
            "delivery_readiness": {"level": "dev"},
            "mcp_tools": [],
        }
        root_flow = {
            "protocol": {"id": "CF-FARP", "version": "0.9"},
            "start": "start",
            "states": {
                "start": {"type": "system", "next": "complete"},
                "complete": {"type": "terminal"},
            },
        }
        graph = FlowGraphBuilder().build({**manifest, "root_flow": root_flow})
        base = load_base_implementation(ROOT)
        runtime = build_compatibility_report(base, manifest, root_flow, ROOT, analysis_target="dev")

        self.assertEqual("dev", graph["analysis"]["target"])
        self.assertTrue(graph["analysis"]["summary"]["runnable"], graph["analysis"]["findings"])
        self.assertTrue(runtime["ok"], runtime["findings"])
        self.assertEqual(
            graph["analysis"]["findings"],
            runtime["flow_contract"]["analysis"]["findings"],
        )


if __name__ == "__main__":
    unittest.main()
