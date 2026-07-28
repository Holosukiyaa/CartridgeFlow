import unittest
from pathlib import Path
from unittest.mock import patch

from core.llm.config_manager import build_model_binding_report
from core.studio.resource_catalog import build_flow_resource_catalog


ROOT = Path(__file__).resolve().parents[3]


def manifest(tool_type="builtin"):
    return {
        "id": "dev.catalog-test",
        "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.8"},
        "portable_dlc": {"protocol": "CF-FARP@0.8", "descriptor": "dlc/descriptor.json"},
        "mcp_tools": [{
            "id": "fetch_news",
            "name": "Fetch news",
            "type": tool_type,
            "server": "media",
            "tool": "fetch_rss",
            "required": True,
            "enabled": True,
        }],
        "llm_recipe": {
            "schema": "cartridgeflow.llm_recipe.v1",
            "roles": [{
                "id": "runtime",
                "label": "Runtime",
                "api_type": "openai",
                "wire_api": "chat_completions",
                "capability": "text_generation",
                "model": "configured-locally",
                "required": True,
            }],
        },
    }


def flow():
    return {
        "states": {
            "fetch": {"type": "process", "kind": "mcp_read", "executor": "mcp", "allowed_tools": ["fetch_news"]},
            "decide": {"type": "process", "kind": "decision", "executor": "llm", "model_role": "runtime"},
        }
    }


class ResourceCatalogV08Tests(unittest.TestCase):
    @patch("core.studio.resource_catalog.load_resources", return_value={"version": 1, "tools": [], "bindings": {"roles": {}, "tools": {}}})
    @patch("core.studio.resource_catalog.load_portable_dlc_descriptor")
    def test_dlc_tool_keeps_cartridge_origin(self, descriptor, _resources):
        descriptor.return_value = {
            "id": "dlc.catalog-test",
            "tools": [{"server": "media", "tool": "fetch_rss", "description": "RSS", "effect": "read_only"}],
        }
        report = build_flow_resource_catalog(ROOT, manifest(), flow(), package_path=ROOT)
        item = next(item for item in report["tools"] if item["id"] == "fetch_news")
        self.assertEqual("cartridge_dlc", item["source"])
        self.assertEqual("ready", item["status"])
        self.assertEqual(["fetch"], item["node_references"])
        self.assertFalse(any(item["severity"] == "blocker" for item in report["findings"]))

    @patch("core.studio.resource_catalog.load_resources")
    def test_referenced_local_tool_without_flow_binding_is_blocked(self, resources):
        resources.return_value = {
            "version": 1,
            "tools": [{"id": "fetch_news", "name": "Local RSS", "kind": "mcp", "server": "media", "tool": "fetch_rss", "enabled": True}],
            "bindings": {"roles": {}, "tools": {}},
        }
        local_manifest = manifest("mcp")
        local_manifest.pop("portable_dlc")
        report = build_flow_resource_catalog(ROOT, local_manifest, flow())
        self.assertIn("NODE_TOOL_RESOURCE_NOT_BOUND", [item["code"] for item in report["findings"]])
        self.assertGreater(report["summary"]["blockers"], 0)

    @patch("core.llm.config_manager.list_providers")
    @patch("core.llm.config_manager.get_assignments")
    def test_decision_node_requires_explicit_binding_from_flow_pool(self, assignments, providers):
        providers.return_value = [{
            "id": "provider-1",
            "name": "Provider 1",
            "api_type": "openai",
            "wire_api": "chat_completions",
            "base_url": "https://example.invalid/v1",
            "api_key": "secret",
            "default_model": "model-1",
            "capabilities": ["text_reasoning"],
        }]
        assignments.return_value = {
            "version": 1,
            "defaults": {"mentor": {"provider_id": "provider-1", "model": "model-1"}},
            "cartridges": {"dev.catalog-test": {"runtime": {"provider_id": "provider-1", "model": "model-1"}}},
            "nodes": {},
        }
        blocked = build_model_binding_report(manifest(), flow())
        node = next(item for item in blocked["items"] if item["id"] == "node:decide")
        self.assertEqual("blocked", node["status"])

        assignments.return_value["nodes"] = {
            "dev.catalog-test/decide": {"runtime": {"provider_id": "provider-1", "model": "model-1"}}
        }
        ready = build_model_binding_report(manifest(), flow())
        node = next(item for item in ready["items"] if item["id"] == "node:decide")
        self.assertEqual("ok", node["status"])
        self.assertEqual("provider-1", node["provider_id"])

    @patch("core.llm.config_manager.list_providers", return_value=[])
    @patch("core.llm.config_manager.get_assignments", return_value={"version": 1, "defaults": {}, "cartridges": {}, "nodes": {}})
    def test_authoring_role_cannot_enter_cartridge_recipe(self, _assignments, _providers):
        item = manifest()
        item["llm_recipe"]["roles"] = [{"id": "mentor", "required": True}]
        report = build_model_binding_report(item, flow())
        self.assertEqual("blocked", report["status"])
        self.assertIn("must not be declared", report["items"][0]["message"])


if __name__ == "__main__":
    unittest.main()
