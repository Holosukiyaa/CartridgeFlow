import unittest
from pathlib import Path

from core.lab.builtin_mcp import BuiltinMcpRegistry


ROOT = Path(__file__).resolve().parents[2]


class BuiltinMediaCoreTest(unittest.TestCase):
    def test_local_probe_executes_without_cartridge_helpers(self):
        result = BuiltinMcpRegistry(ROOT).call("media", "media_probe", {"providers": "local"})
        self.assertTrue(result["ok"], result)
        self.assertIn("local", result["providers"])

    def test_default_registry_contains_only_base_media_tools(self):
        tools = BuiltinMcpRegistry(ROOT).list_tools()["media"]
        self.assertEqual(
            {"media_probe", "extract_keyframes", "style_keyframes", "qc_outputs", "remote_upgrade_keyframes"},
            set(tools),
        )


if __name__ == "__main__":
    unittest.main()
