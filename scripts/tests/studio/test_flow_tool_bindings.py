import unittest

from core.studio.resource_resolver import LocalResourceBindingError, resolve_runtime_tool_binding
from core.studio.resources import merge_flow_tools, resolve_flow_tools


class FlowToolBindingTests(unittest.TestCase):
    def resources(self):
        return {
            "version": 1,
            "tools": [{
                "id": "docs-search",
                "name": "Docs search",
                "kind": "remote_api",
                "server": "docs",
                "tool": "search",
                "endpoint": "https://example.test/search",
                "auth_env": "DOCS_API_KEY",
                "enabled": True,
            }],
            "bindings": {
                "roles": {},
                "tools": {"dev.example": ["docs-search", "builtin:filesystem/read_file"]},
            },
        }

    def test_flow_descriptors_do_not_expose_private_connection_fields(self):
        tools = resolve_flow_tools("dev.example", self.resources())
        external = next(item for item in tools if item["id"] == "docs-search")
        self.assertEqual(external["local_resource_id"], "docs-search")
        self.assertEqual(external["server"], "docs")
        self.assertNotIn("endpoint", external)
        self.assertNotIn("auth_env", external)

    def test_selected_tools_are_merged_without_removing_manifest_tools(self):
        merged = merge_flow_tools(
            "dev.example",
            [{"id": "manifest-tool", "type": "builtin", "server": "filesystem", "tool": "exists"}],
            self.resources(),
        )
        self.assertEqual({item["id"] for item in merged}, {
            "manifest-tool",
            "docs-search",
            "builtin:filesystem/read_file",
        })

    def test_runtime_resolves_private_connection_only_for_selected_flow(self):
        run = {
            "cartridge_id": "dev.example",
            "mcp_tools": resolve_flow_tools("dev.example", self.resources()),
        }
        binding = resolve_runtime_tool_binding(run, "docs-search", self.resources())
        self.assertEqual(binding["resource_id"], "docs-search")
        self.assertEqual(binding["connection"]["endpoint"], "https://example.test/search")
        self.assertEqual(binding["connection"]["auth_env"], "DOCS_API_KEY")

        removed = self.resources()
        removed["bindings"]["tools"]["dev.example"] = []
        with self.assertRaises(LocalResourceBindingError):
            resolve_runtime_tool_binding(run, "docs-search", removed)


if __name__ == "__main__":
    unittest.main()
