import tempfile
import unittest
from pathlib import Path

from core.lab.builtin_mcp import BASE_BUILTIN_TOOL_IDS, BuiltinMcpRegistry


class BuiltinFilesystemTest(unittest.TestCase):
    def test_read_file_is_scoped_to_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.txt").write_text("hello", encoding="utf-8")
            result = BuiltinMcpRegistry(root).call("filesystem", "read_file", {"path": "note.txt"})
            self.assertTrue(result["ok"], result)
            self.assertEqual("hello", result["content"])

    def test_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = BuiltinMcpRegistry(directory).call("filesystem", "read_file", {"path": "../outside.txt"})
            self.assertFalse(result["ok"])
            self.assertIn("escapes workspace", result["error"])

    def test_default_registry_contains_only_filesystem_tools(self):
        registry = BuiltinMcpRegistry(Path.cwd())
        actual = {f"{server}/{tool}" for server, tools in registry.list_tools().items() for tool in tools}
        self.assertEqual(BASE_BUILTIN_TOOL_IDS, actual)
        self.assertEqual({"filesystem"}, set(registry.list_tools()))


if __name__ == "__main__":
    unittest.main()
