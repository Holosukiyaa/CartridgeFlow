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
from backend.api_models import NodeCreatePayload, NodeUpdatePayload
from backend.main import app
from core.lab.dev_flow import DevFlowManager
from core.studio.authoring_service import AuthoringSessionStore


class ApiSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_and_base_routes_are_available(self):
        self.assertEqual(200, self.client.get("/api/health").status_code)
        self.assertEqual(200, self.client.get("/api/base").status_code)

    def test_creator_ai_proposal_uses_configured_dispatch_and_creator_projection(self):
        source = {"id": "source.brief", "kind": "source", "digest": "a" * 64}
        steps = [{"id": "draft", "intent": "Draft a brief.", "inputs": {}, "outputs": {}}]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AuthoringSessionStore(temp_dir)
            with patch.object(backend_main, "authoring_sessions", store), patch("core.llm.config_manager.resolve_model") as resolve_model, patch("core.llm.chat") as chat:
                model = type("Model", (), {"api_key": "configured"})()
                resolve_model.return_value = model
                async def fake_chat(*args, **kwargs):
                    return {"content": '{"changes":[{"id":"ai.draft","target_id":"draft","operation":"set_step_intent","value":"Draft a clearer brief."}]}' }
                chat.side_effect = fake_chat
                created = self.client.post("/api/creator/authoring-sessions", json={"session_id": "api.session", "recipe_id": "recipe.api", "intent": "Create brief", "steps": steps, "source_references": [source], "bindings": {}})
                self.assertEqual(200, created.status_code)
                proposal = self.client.post("/api/creator/authoring-sessions/api.session/ai-proposals", json={"prompt": "Clarify the draft", "expected_revision": 1})
                self.assertEqual(200, proposal.status_code)
                self.assertEqual("set_step_intent", proposal.json()["proposal"]["changes"][0]["operation"])
                preview = self.client.post(f"/api/creator/authoring-sessions/api.session/proposals/{proposal.json()['proposal']['proposal_id']}/preview", json={})
                self.assertEqual(200, preview.status_code)
                self.assertNotIn("developer", preview.json())

    def test_creator_ai_proposal_without_model_is_stable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AuthoringSessionStore(temp_dir)
            source = {"id": "source.brief", "kind": "source", "digest": "a" * 64}
            store.create("api.unbound", "recipe.api", "Create brief", [{"id": "draft", "intent": "Draft.", "inputs": {}, "outputs": {}}], [source], {})
            with patch.object(backend_main, "authoring_sessions", store), patch("core.llm.config_manager.resolve_model", side_effect=ValueError("unbound")):
                response = self.client.post("/api/creator/authoring-sessions/api.unbound/ai-proposals", json={"prompt": "Clarify", "expected_revision": 1})
        self.assertEqual(409, response.status_code)
        self.assertEqual("AI_AUTHORING_MODEL_UNBOUND", response.json()["detail"]["code"])

    def test_creator_ai_proposal_rejects_untrusted_capability_resolution_without_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AuthoringSessionStore(temp_dir)
            source = {"id": "source.brief", "kind": "source", "digest": "a" * 64}
            store.create("api.trust", "recipe.api", "Create brief", [{"id": "draft", "intent": "Draft.", "inputs": {}, "outputs": {}}], [source], {})
            with patch.object(backend_main, "authoring_sessions", store), patch("core.llm.config_manager.resolve_model", return_value=type("Model", (), {"api_key": "configured"})()), patch("core.studio.authoring_service.resolve_ai_authoring_capabilities", side_effect=backend_main.AuthoringServiceError("AI_AUTHORING_TRUST_UNAVAILABLE", "no trust", status=409)):
                response = self.client.post("/api/creator/authoring-sessions/api.trust/ai-proposals", json={"prompt": "Clarify", "expected_revision": 1})
            state = store.get("api.trust")
        self.assertEqual(409, response.status_code)
        self.assertEqual("AI_AUTHORING_TRUST_UNAVAILABLE", response.json()["detail"]["code"])
        self.assertEqual(1, state["head"]["revision"])
        self.assertEqual({}, state["proposals"])

    def test_creator_generation_candidate_is_gated_by_frozen_design(self):
        source = {"id": "source.brief", "kind": "source", "digest": "a" * 64, "role": "public brief"}
        steps = [{"id": "draft", "intent": "Draft a brief.", "inputs": {}, "outputs": {}}]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AuthoringSessionStore(temp_dir)
            with patch.object(backend_main, "authoring_sessions", store):
                created = self.client.post("/api/creator/authoring-sessions", json={"session_id": "api.gate", "recipe_id": "recipe.gate", "intent": "Create brief", "steps": steps, "source_references": [source], "bindings": {}})
                self.assertEqual(200, created.status_code)
                blocked = self.client.post("/api/creator/authoring-sessions/api.gate/compile-candidate", json={"expected_revision": 1})
                self.assertEqual(409, blocked.status_code)
                self.assertEqual("AUTHORING_GENERATION_BLOCKED", blocked.json()["detail"]["code"])
                frozen = self.client.post("/api/creator/authoring-sessions/api.gate/freeze", json={"step_ids": ["draft"], "summary": "Reviewed"})
                self.assertEqual(200, frozen.status_code)
                candidate = self.client.post("/api/creator/authoring-sessions/api.gate/compile-candidate", json={"expected_revision": 1})
                self.assertEqual(200, candidate.status_code)
                self.assertEqual("compile", candidate.json()["compile_candidate"]["kind"])
                self.assertNotIn("runtime", candidate.json())

    def test_creator_runtime_handoff_returns_only_signed_artifact_metadata(self):
        source = {"id": "source.brief", "kind": "source", "digest": "a" * 64, "role": "public brief"}
        steps = [{"id": "draft", "intent": "Draft a brief.", "inputs": {}, "outputs": {}}]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AuthoringSessionStore(temp_dir)
            with patch.object(backend_main, "authoring_sessions", store), patch.object(backend_main, "ROOT", Path(temp_dir)):
                self.assertEqual(200, self.client.post("/api/creator/authoring-sessions", json={"session_id": "api.handoff", "recipe_id": "recipe.handoff", "intent": "Create brief", "steps": steps, "source_references": [source], "bindings": {}}).status_code)
                self.assertEqual(200, self.client.post("/api/creator/authoring-sessions/api.handoff/freeze", json={"step_ids": ["draft"], "summary": "Reviewed"}).status_code)
                candidate = self.client.post("/api/creator/authoring-sessions/api.handoff/compile-candidate", json={"expected_revision": 1}).json()["compile_candidate"]
                response = self.client.post("/api/creator/authoring-sessions/api.handoff/runtime-handoff", json={"expected_revision": 1, "compile_candidate": candidate})
                self.assertEqual(200, response.status_code)
                payload = response.json()
                self.assertEqual("signed_handoff_ready", payload["status"])
                self.assertTrue(payload["signature"]["verified"])
                self.assertNotIn("archive", payload)
                self.assertNotIn("running", json.dumps(payload).lower())

    def test_creator_reverse_endpoint_handles_new_operation_without_server_error(self):
        source = {"id": "source.brief", "kind": "source", "digest": "a" * 64}
        steps = [{"id": "draft", "intent": "Draft a brief.", "inputs": {}, "outputs": {}}]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AuthoringSessionStore(temp_dir)
            with patch.object(backend_main, "authoring_sessions", store):
                self.assertEqual(200, self.client.post("/api/creator/authoring-sessions", json={"session_id": "api.reverse", "recipe_id": "recipe.reverse", "intent": "Create brief", "steps": steps, "source_references": [source], "bindings": {}}).status_code)
                proposal = self.client.post("/api/creator/authoring-sessions/api.reverse/proposals", json={"expected_revision": 1, "summary": "Add source", "changes": [{"id": "add", "target_id": "source.extra", "operation": "add_source", "value": {"id": "source.extra", "kind": "source", "digest": "b" * 64, "role": "extra"}}]}).json()["proposal"]
                accepted = self.client.post(f"/api/creator/authoring-sessions/api.reverse/proposals/{proposal['proposal_id']}/accept", json={}).json()
                response = self.client.post(f"/api/creator/authoring-sessions/api.reverse/revisions/{accepted['creator']['history'][-1]['id']}/reverse", json={"expected_revision": 2, "summary": "Undo source"})
                self.assertEqual(200, response.status_code)
                self.assertEqual(3, response.json()["reversal"]["revision"])

    def test_creator_reverse_endpoint_rejects_later_relation_dependency(self):
        source = {"id": "source.brief", "kind": "source", "digest": "a" * 64}
        steps = [{"id": "research", "intent": "Research.", "inputs": {}, "outputs": {}}, {"id": "draft", "intent": "Draft.", "inputs": {}, "outputs": {}}]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AuthoringSessionStore(temp_dir)
            with patch.object(backend_main, "authoring_sessions", store):
                self.client.post("/api/creator/authoring-sessions", json={"session_id": "api.ambiguous", "recipe_id": "recipe.ambiguous", "intent": "Create brief", "steps": steps, "source_references": [source], "bindings": {}})
                add = self.client.post("/api/creator/authoring-sessions/api.ambiguous/proposals", json={"expected_revision": 1, "summary": "Add review", "changes": [{"id": "add", "target_id": "review", "operation": "add_step", "value": {"id": "review", "intent": "Review.", "inputs": {}, "outputs": {}}}]}).json()["proposal"]
                added = self.client.post(f"/api/creator/authoring-sessions/api.ambiguous/proposals/{add['proposal_id']}/accept", json={}).json()
                connect = self.client.post("/api/creator/authoring-sessions/api.ambiguous/proposals", json={"expected_revision": 2, "summary": "Connect", "changes": [{"id": "connect", "target_id": "rel.draft.review", "operation": "connect_steps", "value": {"id": "rel.draft.review", "from_step_id": "draft", "to_step_id": "review", "relation": "informs"}}]}).json()["proposal"]
                self.client.post(f"/api/creator/authoring-sessions/api.ambiguous/proposals/{connect['proposal_id']}/accept", json={})
                response = self.client.post(f"/api/creator/authoring-sessions/api.ambiguous/revisions/{added['creator']['history'][-1]['id']}/reverse", json={"expected_revision": 3, "summary": "Undo review"})
                self.assertEqual(409, response.status_code)
                self.assertEqual("AUTHORING_REVERSAL_AMBIGUOUS", response.json()["detail"]["code"])
                self.assertEqual(3, store.get("api.ambiguous")["head"]["revision"])
                self.assertEqual("rel.draft.review", store.get("api.ambiguous")["head"]["blueprint"]["relations"][0]["id"])

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
        self.assertEqual("CF-FARP@1.1", catalog["default_for_new_flows"]["label"])
        self.assertEqual("supported_previous", next(item["lifecycle"] for item in catalog["releases"] if item["version"] == "1.0"))
        self.assertEqual("current", next(item["lifecycle"] for item in catalog["releases"] if item["version"] == "1.1"))

    def test_node_create_applies_complete_business_configuration_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DevFlowManager(Path(temp_dir))
            flow_id = "dev.atomic-authoring"
            manager.create_flow(flow_id, "Atomic authoring")
            payload = NodeCreatePayload(
                template_id="prompt",
                node_id="generate_summary",
                title="生成摘要",
                after_node_id="start",
                node=NodeUpdatePayload(
                    kind="decision",
                    executor="llm",
                    effect="none",
                    action="llm_prompt",
                    model_role="runtime",
                    params={
                        "node_category": "process",
                        "preset": "generate",
                        "preset_config": {
                            "target": "生成发布摘要",
                            "format": "Markdown",
                            "output_name": "release_summary",
                        },
                        "prompt": "生成发布摘要\n输出格式：Markdown",
                        "output": "release_summary",
                    },
                    manifest_model_roles=[{
                        "id": "runtime",
                        "label": "运行模型",
                        "capability": "text_generation",
                        "api_type": "openai_compatible",
                        "wire_api": "chat_completions",
                        "model": "configured-locally",
                        "required": True,
                    }],
                ),
            )
            input_payload = NodeCreatePayload(
                template_id="input",
                node_id="collect_brief",
                title="填写需求",
                after_node_id="start",
                node=NodeUpdatePayload(
                    kind="input",
                    executor="user",
                    effect="writes_store",
                    action="collect_inputs",
                    params={
                        "node_category": "input",
                        "preset": "user_form",
                        "preset_config": {"fields": "需求描述、目标", "output_name": "brief"},
                        "fields": ["input_1", "input_2"],
                        "output": "brief",
                    },
                    manifest_inputs=[
                        {"id": "input_1", "label": "需求描述", "type": "textarea", "required": True},
                        {"id": "input_2", "label": "目标", "type": "text", "required": True},
                    ],
                ),
            )
            other_input_payload = NodeCreatePayload(
                template_id="input",
                node_id="collect_audience",
                title="填写受众",
                after_node_id="collect_brief",
                node=NodeUpdatePayload(
                    kind="input",
                    executor="user",
                    effect="writes_store",
                    action="collect_inputs",
                    params={
                        "node_category": "input",
                        "preset": "user_form",
                        "preset_config": {"fields": "受众", "output_name": "audience"},
                        "fields": ["input_3"],
                        "output": "audience",
                    },
                    manifest_inputs=[
                        {"id": "input_3", "label": "受众", "type": "text", "required": True},
                    ],
                    manifest_model_roles=[{
                        "id": "reviewer",
                        "label": "审核模型",
                        "capability": "text_generation",
                        "api_type": "openai_compatible",
                        "wire_api": "chat_completions",
                        "model": "configured-locally",
                        "required": False,
                    }],
                ),
            )

            with patch.object(backend_main, "dev_flow_manager", manager), patch.object(
                backend_main.registry,
                "get_cartridge",
                return_value={"id": flow_id, "editable": True},
            ):
                result = backend_main.create_lab_flow_node(flow_id, payload)
                input_result = backend_main.create_lab_flow_node(flow_id, input_payload)
                other_input_result = backend_main.create_lab_flow_node(flow_id, other_input_payload)
                updated_input_result = backend_main.update_lab_flow_node(
                    flow_id,
                    "collect_brief",
                    NodeUpdatePayload(
                        params={
                            "node_category": "input",
                            "preset": "user_form",
                            "preset_config": {"fields": "需求描述", "output_name": "brief"},
                            "fields": ["input_1"],
                            "output": "brief",
                        },
                        manifest_inputs=[
                            {"id": "input_1", "label": "需求描述", "type": "textarea", "required": True},
                        ],
                    ),
                )

            root_flow = json.loads(result["files"]["root_flow"])
            node = root_flow["states"]["generate_summary"]
            self.assertEqual("生成发布摘要\n输出格式：Markdown", node["params"]["prompt"])
            self.assertEqual("release_summary", node["params"]["output"])
            self.assertEqual("runtime", node["model_role"])
            self.assertEqual(1, sum(
                edge.get("from") == "generate_summary" and edge.get("kind") == "failure"
                for edge in root_flow["execution_plan"]["edges"]
            ))
            manifest = json.loads(updated_input_result["files"]["manifest"])
            self.assertEqual(["input_3", "input_1"], [item["id"] for item in manifest["inputs"]])
            self.assertEqual(["runtime", "reviewer"], [item["id"] for item in manifest["llm_recipe"]["roles"]])
            input_root_flow = json.loads(input_result["files"]["root_flow"])
            self.assertEqual(["input_1", "input_2"], input_root_flow["states"]["collect_brief"]["params"]["fields"])

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
