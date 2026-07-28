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

    def test_unbound_manifest_tools_do_not_enter_runtime(self):
        merged = merge_flow_tools(
            "dev.example",
            [{"id": "manifest-tool", "type": "builtin", "server": "filesystem", "tool": "exists"}],
            self.resources(),
        )
        self.assertEqual({item["id"] for item in merged}, {
            "docs-search",
            "builtin:filesystem/read_file",
        })

    def test_bound_builtin_satisfies_legacy_manifest_alias(self):
        merged = merge_flow_tools(
            "dev.example",
            [{"id": "filesystem_read", "type": "builtin", "server": "filesystem", "tool": "read_file"}],
            self.resources(),
        )
        self.assertEqual({item["id"] for item in merged}, {"docs-search", "filesystem_read"})
        alias = next(item for item in merged if item["id"] == "filesystem_read")
        self.assertEqual(alias["server"], "filesystem")
        self.assertEqual(alias["tool"], "read_file")

    def test_manifest_tools_are_empty_when_flow_has_no_bindings(self):
        resources = self.resources()
        resources["bindings"]["tools"] = {}
        merged = merge_flow_tools(
            "dev.example",
            [{"id": "filesystem_read", "type": "builtin", "server": "filesystem", "tool": "read_file"}],
            resources,
        )
        self.assertEqual(merged, [])

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
