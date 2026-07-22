import os
import tempfile
import unittest
from pathlib import Path

from core.studio.environment import delete_credential, environment_snapshot, upsert_credential
from core.studio.release import build_binding_descriptor, resource_preflight
from core.studio.resource_resolver import LocalResourceBindingError, resolve_cartridge_resources, resolve_runtime_tool_binding


class StudioEnvironmentTests(unittest.TestCase):
    def test_credential_values_are_masked_and_applied(self):
        key = "CF_TEST_LOCAL_SECRET"
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "credentials.json"
            public = upsert_credential({"key": key, "label": "Test", "value": "secret-value"}, path=target)
            snapshot = environment_snapshot(path=target)

            self.assertNotIn("value", public)
            self.assertEqual(public["preview"], "...alue")
            self.assertEqual(os.environ.get(key), "secret-value")
            self.assertEqual(snapshot["credentials"][0]["key"], key)
            self.assertTrue(delete_credential(key, target))
            self.assertNotIn(key, os.environ)

    def test_package_binding_descriptor_never_contains_credential_value(self):
        manifest = {
            "id": "demo",
            "resource_requirements": [{"role": "document_lookup", "kinds": ["remote_api"], "required": True}],
        }
        resources = {
            "tools": [{"id": "search", "name": "Search", "kind": "remote_api", "endpoint": "https://example.test/search", "auth_env": "SEARCH_KEY", "package_mode": "descriptor"}],
            "bindings": {"roles": {"demo": {"document_lookup": "search"}}, "tools": {}},
        }
        descriptor = build_binding_descriptor(manifest, resources, set())
        report = resource_preflight(manifest, resources, set())

        self.assertFalse(descriptor["contains_secrets"])
        self.assertNotIn("credential-value", str(descriptor))
        self.assertNotIn("example.test", str(descriptor))
        self.assertEqual(report["status"], "blocked")
        self.assertEqual({item["status"] for item in report["items"]}, {"blocked"})

    def test_resource_preflight_blocks_incomplete_bound_resources(self):
        manifest = {
            "id": "demo",
            "resource_requirements": [
                {"role": "mcp_role", "kinds": ["mcp"], "required": True},
                {"role": "api_role", "kinds": ["remote_api"], "required": True},
                {"role": "plugin_role", "kinds": ["plugin"], "required": True},
                {"role": "docs_role", "kinds": ["web"], "required": True},
            ],
        }
        resources = {
            "tools": [
                {"id": "mcp", "kind": "mcp"},
                {"id": "api", "kind": "remote_api"},
                {"id": "plugin", "kind": "plugin"},
                {"id": "docs", "kind": "remote_api"},
            ],
            "bindings": {
                "roles": {"demo": {"mcp_role": "mcp", "api_role": "api", "plugin_role": "plugin", "docs_role": "docs"}},
                "tools": {},
            },
        }

        report = resource_preflight(manifest, resources, set())

        self.assertEqual(report["status"], "blocked")
        self.assertEqual([item["status"] for item in report["items"]], ["blocked"] * 4)
        self.assertEqual(
            {item["message"] for item in report["items"]},
            {
                "MCP 服务缺少 Endpoint 或启动命令",
                "远程 API 缺少 Endpoint 或 OpenAPI URL",
                "底座插件缺少入口地址或启动命令",
            },
        )

    def test_runtime_tool_binding_uses_role_snapshot_and_rejects_changes(self):
        manifest = {
            "id": "demo",
            "resource_requirements": [{"role": "document_lookup", "kinds": ["remote_api"], "required": True}],
            "mcp_tools": [{"id": "lookup", "type": "remote", "server": "docs", "tool": "search", "resource_role": "document_lookup"}],
        }
        resources = {
            "tools": [{"id": "search-a", "kind": "remote_api", "endpoint": "https://example.test/search", "enabled": True}],
            "bindings": {"roles": {"demo": {"document_lookup": "search-a"}}, "tools": {}},
        }
        report = resolve_cartridge_resources(manifest, resources, set())
        run = {
            "cartridge_id": "demo",
            "resource_requirements": manifest["resource_requirements"],
            "mcp_tools": manifest["mcp_tools"],
            "local_resources": report["descriptor"],
        }

        resolved = resolve_runtime_tool_binding(run, "lookup", resources, set())
        self.assertEqual("search-a", resolved["resource_id"])
        self.assertEqual("https://example.test/search", resolved["connection"]["endpoint"])

        changed = {**resources, "bindings": {"roles": {"demo": {"document_lookup": "search-b"}}, "tools": {}}}
        with self.assertRaises(LocalResourceBindingError):
            resolve_runtime_tool_binding(run, "lookup", changed, set())


if __name__ == "__main__":
    unittest.main()
