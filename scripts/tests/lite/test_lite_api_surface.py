import base64
import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main as backend_main
from backend.lite_main import app, is_lite_api_allowed


class LiteApiSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_workbench_routes_are_available(self):
        allowed = [
            "/api/health",
            "/api/base",
            "/api/lab/flows",
            "/api/lab/flows/dev.example/nodes",
            "/api/lab/flows/dev.example/test-run",
            "/api/llm/providers",
            "/api/studio/resources",
            "/api/studio/packages",
            "/api/studio/release/dev.example/preflight",
            "/api/studio/environment/credentials/IMAGE_API_KEY",
            "/api/cartridge-runs/run_123/events",
            "/api/cartridges/dev.example/clone-to-dev",
            "/api/cartridges/dev.example/package",
        ]
        for path in allowed:
            with self.subTest(path=path):
                self.assertTrue(is_lite_api_allowed(path))

    def test_global_and_removed_routes_are_blocked(self):
        blocked = [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/studio/conformance",
            "/api/studio/todo",
            "/api/settings",
            "/api/cartridge-runs",
            "/api/lab/flows/dev.example/assistant",
            "/api/lab/flows/dev.example/steward/suggest",
            "/api/lab/flows/dev.example/certification",
        ]
        for path in blocked:
            with self.subTest(path=path):
                self.assertFalse(is_lite_api_allowed(path))

    def test_framework_docs_return_lite_not_available(self):
        for path in ["/docs", "/redoc", "/openapi.json"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(404, response.status_code)
                self.assertEqual("LITE_CAPABILITY_NOT_AVAILABLE", response.json()["detail"]["code"])

    def test_untrusted_host_is_rejected(self):
        response = self.client.get("/api/health", headers={"Host": "attacker.example"})
        self.assertEqual(400, response.status_code)

    def test_cors_only_allows_local_workbench_origins(self):
        preflight_headers = {"Access-Control-Request-Method": "GET"}
        rejected = self.client.options(
            "/api/health",
            headers={"Origin": "https://attacker.example", **preflight_headers},
        )
        self.assertEqual(400, rejected.status_code)
        self.assertNotIn("access-control-allow-origin", rejected.headers)

        allowed = self.client.options(
            "/api/health",
            headers={"Origin": "http://127.0.0.1:5173", **preflight_headers},
        )
        self.assertEqual(200, allowed.status_code)
        self.assertEqual("http://127.0.0.1:5173", allowed.headers["access-control-allow-origin"])

    def test_api_responses_include_security_headers(self):
        response = self.client.get("/api/health")
        self.assertEqual(200, response.status_code)
        self.assertEqual("nosniff", response.headers["x-content-type-options"])
        self.assertEqual("no-referrer", response.headers["referrer-policy"])
        self.assertIn("camera=()", response.headers["permissions-policy"])

    def test_base_endpoint_distributes_protocol_release_catalog(self):
        response = self.client.get("/api/base")
        self.assertEqual(200, response.status_code)
        catalog = response.json()["protocol_catalog"]
        self.assertEqual("CF-FARP@0.9", catalog["default_for_new_flows"]["label"])
        self.assertEqual("current", next(item["lifecycle"] for item in catalog["releases"] if item["version"] == "0.9"))

    def test_validation_errors_do_not_echo_api_keys(self):
        secret = "sk-security-regression-secret"
        response = self.client.post(
            "/api/llm/providers",
            json={"name": "invalid", "api_key": {"secret": secret}},
        )
        self.assertEqual(422, response.status_code)
        self.assertNotIn(secret, response.text)

    def test_upload_rejects_oversized_text_before_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(backend_main, "ROOT", Path(temp_dir)), patch.object(
            backend_main, "MAX_UPLOAD_TEXT_BYTES", 4,
        ):
            response = self.client.post("/api/uploads/file", json={"filename": "large.txt", "content": "12345"})
        self.assertEqual(413, response.status_code)

    def test_upload_uses_logical_data_path_when_data_root_is_external(self):
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as data_dir:
            workspace = Path(workspace_dir)
            data_root = Path(data_dir)
            upload_root = data_root / "temp" / "uploads"
            with patch.object(backend_main, "ROOT", workspace), patch.object(
                backend_main, "DATA_ROOT", data_root,
            ), patch.object(backend_main, "UPLOADS_DIR", upload_root):
                response = self.client.post(
                    "/api/uploads/file",
                    json={"filename": "sample.txt", "content": "isolated upload"},
                )

            self.assertEqual(200, response.status_code)
            self.assertRegex(response.json()["path"], r"^\.data/temp/uploads/[^/]+_sample\.txt$")
            self.assertEqual("isolated upload", next(upload_root.iterdir()).read_text(encoding="utf-8"))

    def test_cartridge_zip_rejects_parent_segments_symlinks_and_oversized_members(self):
        extract_dir = Path(tempfile.gettempdir()) / "cf-archive-validation-only"

        parent = zipfile.ZipInfo("assets/../manifest.json")
        with self.assertRaisesRegex(Exception, "Invalid zip path"):
            backend_main._validate_cartridge_archive_members([parent], extract_dir)

        symlink = zipfile.ZipInfo("assets/link")
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(Exception, "Symbolic links"):
            backend_main._validate_cartridge_archive_members([symlink], extract_dir)

        oversized = zipfile.ZipInfo("assets/large.bin")
        oversized.file_size = 5
        with patch.object(backend_main, "MAX_CARTRIDGE_MEMBER_BYTES", 4), self.assertRaisesRegex(Exception, "too large"):
            backend_main._validate_cartridge_archive_members([oversized], extract_dir)

    def test_valid_cartridge_archive_reaches_installation(self):
        archive = io.BytesIO()
        manifest = {"id": "test.safe-import", "root_flow": {"entry": "root.flow.json"}}
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("root.flow.json", "{}")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            dev_dir = temp_root / "cartridges" / "dev"
            builtin_dir = temp_root / "cartridges" / "builtin"
            with patch.object(backend_main, "ROOT", temp_root), patch.object(
                backend_main.registry, "dev_dir", dev_dir,
            ), patch.object(backend_main.registry, "builtin_dir", builtin_dir), patch.object(
                backend_main.registry.validator, "validate_package",
            ), patch.object(
                backend_main.registry, "get_cartridge", return_value={"id": manifest["id"]},
            ):
                response = self.client.post(
                    "/api/cartridges/import",
                    json={"content_base64": base64.b64encode(archive.getvalue()).decode("ascii")},
                )
                installed = temp_root / backend_main.INSTALLED_CARTRIDGES_DIR / manifest["id"]
                self.assertTrue(installed.is_dir())

        self.assertEqual(200, response.status_code)
        self.assertFalse(Path(response.json()["installed_path"]).is_absolute())

    def test_external_data_root_import_does_not_leak_an_absolute_path(self):
        archive = io.BytesIO()
        manifest = {"id": "test.external-data-import", "root_flow": {"entry": "root.flow.json"}}
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("root.flow.json", "{}")

        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as data_dir:
            workspace = Path(workspace_dir)
            data_root = Path(data_dir)
            imports_root = data_root / "temp" / "imports"
            installed_root = data_root / "user" / "installed_cartridges"
            with patch.object(backend_main, "ROOT", workspace), patch.object(
                backend_main, "DATA_ROOT", data_root,
            ), patch.object(backend_main, "IMPORTS_DIR", imports_root), patch.object(
                backend_main, "INSTALLED_CARTRIDGES_DIR", installed_root,
            ), patch.object(backend_main.registry, "dev_dir", workspace / "dev"), patch.object(
                backend_main.registry, "builtin_dir", workspace / "builtin",
            ), patch.object(backend_main.registry.validator, "validate_package"), patch.object(
                backend_main.registry, "get_cartridge", return_value={"id": manifest["id"]},
            ):
                response = self.client.post(
                    "/api/cartridges/import",
                    json={"content_base64": base64.b64encode(archive.getvalue()).decode("ascii")},
                )

            self.assertEqual(200, response.status_code)
            self.assertEqual(".data/user/installed_cartridges/test.external-data-import", response.json()["installed_path"])
            self.assertTrue((installed_root / manifest["id"] / "manifest.json").is_file())

    def test_active_artifact_is_served_with_scriptless_sandbox(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = Path(temp_dir) / "report.html"
            artifact_path.write_text("<script>document.body.textContent='unsafe'</script>", encoding="utf-8")
            run = {"run_id": "run_security", "artifacts": [{"name": "report.html", "mime_type": "text/html"}]}
            with patch.object(backend_main.runner, "get_run", return_value=run), patch.object(
                backend_main.artifact_manager, "resolve_artifact_path", return_value=artifact_path,
            ):
                response = self.client.get("/artifacts/run_security/report.html")
        self.assertEqual(200, response.status_code)
        self.assertIn("sandbox", response.headers["content-security-policy"])
        self.assertIn("script-src 'none'", response.headers["content-security-policy"])
        self.assertEqual("no-store", response.headers["cache-control"])


if __name__ == "__main__":
    unittest.main()
