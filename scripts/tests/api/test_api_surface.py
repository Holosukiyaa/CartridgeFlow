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
from backend.main import app


class ApiSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_and_base_routes_are_available(self):
        self.assertEqual(200, self.client.get("/api/health").status_code)
        self.assertEqual(200, self.client.get("/api/base").status_code)

    def test_resource_detail_is_redacted_and_unbound_connectivity_has_stable_error(self):
        secret = "workbench-resource-secret"
        endpoint = f"https://private.example.test/connector?token={secret}"
        manifest = {
            "id": "dev.example",
            "mcp_tools": [{
                "id": "external-news",
                "type": "remote",
                "server": "news-service",
                "tool": "fetch",
                "contract": {"timeout_ms": 3000, "idempotent": True, "permissions": ["network:read"]},
            }],
        }
        cartridge = {"manifest": manifest, "root_flow": {"states": {"fetch": {"allowed_tools": ["external-news"]}}}, "package_path": None}
        resources = {
            "version": 1,
            "tools": [{
                "id": "external-news",
                "kind": "remote_api",
                "server": "news-service",
                "tool": "fetch",
                "endpoint": endpoint,
                "auth_env": "WORKBENCH_RESOURCE_TOKEN",
                "auth_header": "Authorization",
                "enabled": True,
            }],
            "bindings": {"roles": {}, "tools": {"dev.example": []}},
        }
        with patch.object(backend_main.registry, "get_cartridge", return_value=cartridge), patch(
            "core.studio.resource_catalog.load_resources", return_value=resources,
        ):
            detail = self.client.get("/api/lab/flows/dev.example/resource-details/external-news")
            check = self.client.post("/api/lab/flows/dev.example/resource-connectivity/external-news")

        self.assertEqual(200, detail.status_code)
        self.assertEqual("external_connector", detail.json()["resource"]["presentation_mode"])
        self.assertEqual("local-resource:external-news#endpoint", detail.json()["resource"]["connector"]["endpoint"]["reference"])
        self.assertNotIn(secret, detail.text)
        self.assertNotIn(endpoint, detail.text)
        self.assertNotIn("Authorization", detail.text)
        self.assertEqual(409, check.status_code)
        self.assertEqual("EXTERNAL_CONNECTOR_UNBOUND", check.json()["detail"]["code"])

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
        self.assertEqual("CF-FARP@1.0", catalog["default_for_new_flows"]["label"])
        self.assertEqual("current", next(item["lifecycle"] for item in catalog["releases"] if item["version"] == "1.0"))

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


    def test_execution_plan_edge_save_preserves_failure_facts(self):
        """保存可视化连线不得把 failure 边改写成 sequence 边或丢失其详情。"""
        root_flow = {
            "id": "edges.root",
            "start": "start",
            "protocol": {"id": "CF-FARP", "version": "1.0"},
            "execution_plan": {
                "schema": "cartridgeflow.execution_plan.v1",
                "entry": "start",
                "edges": [
                    {"id": "start_run", "kind": "sequence", "from": "start", "to": "run"},
                    {"id": "run_failure", "kind": "failure", "from": "run", "to": "failed",
                     "failure": {"id": "run_error", "causes": ["exception", "timeout"]}},
                ],
            },
            "states": {
                "start": {"type": "control"},
                "run": {"type": "process", "action": "tool_call"},
                "failed": {"type": "terminal"},
            },
        }
        # 前端只传 from/to/scope，不携带 kind
        frontend_edges = [
            {"from": "start", "to": "run", "scope": "root"},
            {"from": "run", "to": "failed", "scope": "failure"},
        ]
        backend_main._write_flow_edges(root_flow, frontend_edges)
        saved = root_flow["execution_plan"]["edges"]
        by_pair = {(edge["from"], edge["to"]): edge for edge in saved}
        sequence = by_pair[("start", "run")]
        failure = by_pair[("run", "failed")]
        self.assertEqual("sequence", sequence["kind"])
        self.assertEqual("start_run", sequence["id"])
        self.assertEqual("failure", failure["kind"])
        self.assertEqual("run_failure", failure["id"])
        self.assertEqual({"id": "run_error", "causes": ["exception", "timeout"]}, failure["failure"])

    def test_execution_plan_edge_save_full_payload_keeps_failure_kinds(self):
        """全量保存（前端语义）时，传入的 failure 边保持 kind，不被改写为 sequence。"""
        root_flow = {
            "id": "edges.root",
            "start": "start",
            "protocol": {"id": "CF-FARP", "version": "1.0"},
            "execution_plan": {
                "schema": "cartridgeflow.execution_plan.v1",
                "entry": "start",
                "edges": [
                    {"id": "start_a", "kind": "sequence", "from": "start", "to": "a"},
                    {"id": "a_b", "kind": "sequence", "from": "a", "to": "b"},
                    {"id": "a_fail", "kind": "failure", "from": "a", "to": "fail",
                     "failure": {"id": "a_error", "causes": ["exception"]}},
                ],
            },
            "states": {
                "start": {"type": "control"},
                "a": {"type": "process", "action": "tool_call"},
                "b": {"type": "terminal"},
                "fail": {"type": "terminal"},
            },
        }
        frontend_edges = [
            {"from": "start", "to": "a", "scope": "root"},
            {"from": "a", "to": "b", "scope": "root"},
            {"from": "a", "to": "fail", "scope": "failure"},
        ]
        backend_main._write_flow_edges(root_flow, frontend_edges)
        saved = root_flow["execution_plan"]["edges"]
        by_pair = {(edge["from"], edge["to"]): edge for edge in saved}
        self.assertEqual({"start_a", "a_b", "a_fail"}, {edge["id"] for edge in saved})
        self.assertEqual("failure", by_pair[("a", "fail")]["kind"])
        self.assertEqual({"id": "a_error", "causes": ["exception"]}, by_pair[("a", "fail")]["failure"])
        self.assertEqual("sequence", by_pair[("a", "b")]["kind"])


if __name__ == "__main__":
    unittest.main()
