import unittest
from pathlib import Path

from core.lab.builtin_mcp import BASE_BUILTIN_TOOL_IDS, BuiltinMcpRegistry


ROOT = Path(__file__).resolve().parents[3]


class BuiltinMediaCoreTest(unittest.TestCase):
    def test_local_probe_executes_without_cartridge_helpers(self):
        result = BuiltinMcpRegistry(ROOT).call("media", "media_probe", {"providers": "local"})
        self.assertTrue(result["ok"], result)
        self.assertIn("local", result["providers"])

    def test_default_media_probe_contains_only_base_owned_providers(self):
        result = BuiltinMcpRegistry(ROOT).call("media", "media_probe", {})
        self.assertTrue(result["ok"], result)
        self.assertEqual({"local", "ffmpeg"}, set(result["providers"]))

    def test_external_provider_is_not_implemented_by_the_base(self):
        result = BuiltinMcpRegistry(ROOT).call("media", "media_probe", {"providers": "external_provider"})
        self.assertFalse(result["providers"]["external_provider"]["ok"])
        self.assertIn("unknown media provider", result["providers"]["external_provider"]["message"])

    def test_external_style_provider_requires_cartridge_dlc(self):
        result = BuiltinMcpRegistry(ROOT).call("media", "style_keyframes", {
            "manifest_content": {"keyframes": [{"image": "unused.png"}]},
            "provider": "external_provider",
        })
        self.assertFalse(result["ok"])
        self.assertIn("use a cartridge DLC", result["error"])

    def test_removed_remote_pipeline_is_not_registered(self):
        result = BuiltinMcpRegistry(ROOT).call("media", "remote_upgrade_keyframes", {})
        self.assertFalse(result["ok"])
        self.assertIn("Unknown builtin tool", result["error"])

    def test_default_registry_contains_only_base_media_tools(self):
        tools = BuiltinMcpRegistry(ROOT).list_tools()["media"]
        self.assertEqual(
            {"media_probe", "extract_keyframes", "style_keyframes", "qc_outputs"},
            set(tools),
        )

    def test_default_registry_matches_explicit_base_tool_allowlist(self):
        registry = BuiltinMcpRegistry(ROOT)
        actual = {f"{server}/{tool}" for server, tools in registry.list_tools().items() for tool in tools}
        self.assertEqual(BASE_BUILTIN_TOOL_IDS, actual)


if __name__ == "__main__":
    unittest.main()
