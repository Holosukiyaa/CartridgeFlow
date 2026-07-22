import json
import tempfile
import unittest
from pathlib import Path

from core.local_config import read_local_json, write_local_json
from core.studio.resources import load_resources, save_resources


class StudioResourcesTests(unittest.TestCase):
    def test_normalizes_resources_and_deduplicates_bindings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "resources.json"
            result = save_resources({
                "tools": [{
                    "id": " Remote Search ",
                    "name": "Remote Search",
                    "kind": "remote_api",
                    "openapi_url": " https://example.test/openapi.json ",
                    "auth_env": "SEARCH_API_KEY",
                }],
                "sources": [{
                    "id": " Product Docs ",
                    "name": "Product Docs",
                    "kind": "local_path",
                    "location": "docs",
                    "package_mode": "snapshot",
                }],
                "bindings": {
                    "roles": {"demo.flow": {"document_lookup": "remote-search"}},
                    "tools": {"demo.flow": ["remote-search", "remote-search", ""]},
                    "sources": {"demo.flow": ["product-docs"]},
                },
            }, target)

            self.assertEqual(result["tools"][0]["id"], "remote-search")
            self.assertEqual(result["tools"][0]["openapi_url"], "https://example.test/openapi.json")
            self.assertEqual([item["id"] for item in result["tools"]], ["remote-search", "product-docs"])
            self.assertEqual(result["tools"][1]["kind"], "plugin")
            self.assertEqual(result["tools"][1]["endpoint"], "docs")
            self.assertEqual(result["tools"][1]["package_mode"], "descriptor")
            self.assertNotIn("sources", result)
            self.assertEqual(result["bindings"]["roles"]["demo.flow"]["document_lookup"], "remote-search")
            self.assertEqual(result["bindings"]["tools"]["demo.flow"], ["remote-search", "product-docs"])
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), result)

    def test_creates_default_file_when_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "nested" / "resources.json"
            result = load_resources(target)

            self.assertEqual(result["version"], 1)
            self.assertEqual(result["bindings"], {"roles": {}, "tools": {}})
            self.assertTrue(target.is_file())

    def test_generates_stable_id_for_chinese_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "resources.json"
            result = save_resources({"sources": [{"name": "产品文档"}]}, target)

            self.assertRegex(result["tools"][0]["id"], r"^resource-[0-9a-f]{10}$")
            self.assertEqual(load_resources(target)["tools"][0]["id"], result["tools"][0]["id"])
            self.assertNotIn("sources", json.loads(target.read_text(encoding="utf-8")))

    def test_invalid_local_json_is_preserved_before_default_is_restored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "resources.json"
            target.write_text('{"tools": [', encoding="utf-8")

            fallback = {"version": 1, "tools": [], "sources": [], "bindings": {}}
            result = read_local_json(target, fallback)
            backups = list(target.parent.glob("resources.corrupt-*.json"))

            self.assertEqual(fallback, result)
            self.assertEqual(1, len(backups))
            self.assertEqual('{"tools": [', backups[0].read_text(encoding="utf-8"))
            self.assertEqual(fallback, json.loads(target.read_text(encoding="utf-8")))

    def test_local_json_write_replaces_file_without_leaving_temp_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "providers.json"
            target.write_text('{"version":0}', encoding="utf-8")

            write_local_json(target, {"version": 1, "providers": []})

            self.assertEqual(1, json.loads(target.read_text(encoding="utf-8"))["version"])
            self.assertEqual([], list(target.parent.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
