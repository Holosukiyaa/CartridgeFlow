import json
import tempfile
import unittest
from pathlib import Path

from core.lab.dev_flow import DevFlowManager
from core.studio.portability import build_portability_report


class PortabilityReportTests(unittest.TestCase):
    def test_reports_packaged_assets_and_local_rebinds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            created = DevFlowManager(temp_dir).create_flow("demo.portable", "Portable")
            package = Path(created["path"])
            manifest = created["manifest"]
            manifest["llm_recipe"] = {
                "schema": "cartridgeflow.llm_recipe.v1",
                "roles": [{"id": "writer", "label": "Writer", "required": True, "api_type": "openai"}],
            }
            (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            report = build_portability_report(package, manifest, created["root_flow"], resources={"tools": [], "bindings": {"roles": {}, "tools": {}}})

            self.assertEqual("ok", report["status"])
            self.assertGreaterEqual(report["summary"]["portable"], 4)
            self.assertEqual(1, report["summary"]["local_rebind"])
            self.assertEqual([], report["forbidden"])
            self.assertTrue(all(item.get("sha256") and item.get("size") is not None for item in report["portable"] if item.get("path")))

    def test_missing_binding_and_secret_file_block_packaging(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            created = DevFlowManager(temp_dir).create_flow("demo.blocked", "Blocked")
            package = Path(created["path"])
            manifest = created["manifest"]
            manifest["resource_requirements"] = [{"role": "search", "kinds": ["remote_api"], "required": True}]
            (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            (package / ".env").write_text("SECRET=value", encoding="utf-8")

            report = build_portability_report(package, manifest, created["root_flow"], resources={"tools": [], "bindings": {"roles": {}, "tools": {}}})

            self.assertEqual("blocked", report["status"])
            self.assertEqual("missing_binding", report["missing_blockers"][0]["check"])
            self.assertTrue(any(item.get("path") == ".env" for item in report["forbidden"]))

    def test_sensitive_connection_fields_and_absolute_paths_are_forbidden(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            created = DevFlowManager(temp_dir).create_flow("demo.secret", "Secret")
            package = Path(created["path"])
            (package / "assets" / "unsafe.json").write_text(json.dumps({"endpoint": "https://private.example", "path": "C:\\Users\\demo\\file"}), encoding="utf-8")

            report = build_portability_report(package, created["manifest"], created["root_flow"])

            checks = {item.get("check") for item in report["forbidden"]}
            self.assertIn("sensitive_field", checks)
            self.assertIn("local_path", checks)

    def test_permission_declarations_are_audited(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            created = DevFlowManager(temp_dir).create_flow("demo.permissions", "Permissions")
            package = Path(created["path"])
            manifest = created["manifest"]
            manifest["permissions"] = [{"id": "publish", "level": "dangerous", "reason": "Publish output"}]
            (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            report = build_portability_report(package, manifest, created["root_flow"])

            permission = next(item for item in report["portable"] if item["id"] == "permission:publish")
            self.assertEqual("dangerous", permission["level"])

            manifest["permissions"] = {"publish": True}
            blocked = build_portability_report(package, manifest, created["root_flow"])
            self.assertTrue(any(item.get("check") == "permission_schema" for item in blocked["missing_blockers"]))


if __name__ == "__main__":
    unittest.main()
