import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient

from backend import main as backend_main
from backend.main import app
from core.studio.authoring_service import AuthoringServiceError, AuthoringSessionStore
from core.studio.creator_workspace import CreatorWorkspaceStore
from core.studio.trusted_node_presets import TrustedNodePresetStore, build_trusted_node_mapping
from core.studio.capability_cartridges import CapabilityCartridgeStore
from core.cartridge import CartridgeRegistry
from core.lab import DevFlowManager


PRESET = {
    "schema": "cartridgeflow.trusted_node_preset.v1", "protocol": {"id": "CF-TUNING", "version": "1.4"},
    "id": "rss-source", "revision": 1, "creator_label": "收集公开信息源",
    "creator_description": "按主题收集可供用户审核的公开信息源。", "match_terms": ["RSS", "日报"],
    "editable_fields": [{"id": "topics", "label": "关注主题", "value_type": "string_list", "required": True, "default": ["AI"]}],
    "developer_mapping_key": "source.rss.v1",
}
STATE = {
    "type": "process", "kind": "transfer", "executor": "deterministic", "effect": "writes_store",
    "action": "pass_result", "inputs": {}, "outputs": {},
    "params": {"preset_config": {"from": "seed", "to": "result", "topics": ["AI"]}},
}


def mapping(preset=PRESET):
    return build_trusted_node_mapping(
        preset, STATE, source_flow_id="dev.sources", source_node_id="rss",
        creator_bindings={"topics": "params.preset_config.topics"}, source_manifest={"permissions": []},
    )


class TrustedCreatorApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.root = root
        self.sessions = AuthoringSessionStore(root / "sessions")
        self.workspaces = CreatorWorkspaceStore(root / "workspaces")
        self.presets = TrustedNodePresetStore(root / "presets")
        self.capabilities = CapabilityCartridgeStore(root / "capabilities")
        self.registry = CartridgeRegistry(root)
        self.dev_flows = DevFlowManager(root)
        self.verifications = root / "capability_verifications"
        self.test_runs = root / "capability_test_runs"
        self.verifications.mkdir()
        self.test_runs.mkdir()
        self.desktop_runner = Mock()
        self.desktop_runner.status.return_value = {
            "schema": "cartridgeflow.desktop_runner_status.v1", "available": True,
            "url": "http://127.0.0.1:18990/", "version": "test", "busy": False, "cartridge": None,
        }
        self.desktop_runner.install.return_value = {
            "schema": "cartridgeflow.desktop_runner_delivery.v1", "status": "installed",
            "runner_url": "http://127.0.0.1:18990/", "cartridge": {"id": "creator-package"},
        }
        self.patches = [
            patch.object(backend_main, "authoring_sessions", self.sessions),
            patch.object(backend_main, "creator_workspaces", self.workspaces),
            patch.object(backend_main, "trusted_node_presets", self.presets),
            patch.object(backend_main, "capability_cartridges", self.capabilities),
            patch.object(backend_main, "registry", self.registry),
            patch.object(backend_main, "dev_flow_manager", self.dev_flows),
            patch.object(backend_main, "capability_verification_dir", self.verifications),
            patch.object(backend_main, "capability_test_run_dir", self.test_runs),
            patch.object(backend_main, "desktop_runner", self.desktop_runner),
        ]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def test_optional_project_lookup_returns_empty_creator(self):
        response = self.client.get("/api/creator/projects/project.missing?optional=true")
        self.assertEqual(200, response.status_code, response.text)
        self.assertIsNone(response.json()["creator"])

    def test_creator_workspace_saves_before_authoring_and_detects_conflicts(self):
        snapshot = {
            "version": 1, "goal": "Prepare a brief", "messages": [], "clarification": None,
            "possibilities": [], "selectedId": "", "middleView": "outline",
            "workspacePane": "collaboration", "packageResult": None, "packageRevision": None,
        }
        missing = self.client.get("/api/creator/projects/project.workspace/workspace")
        self.assertEqual(200, missing.status_code, missing.text)
        self.assertIsNone(missing.json()["workspace"])
        saved = self.client.put(
            "/api/creator/projects/project.workspace/workspace",
            json={"expected_revision": 0, "snapshot": snapshot},
        )
        self.assertEqual(200, saved.status_code, saved.text)
        self.assertEqual(1, saved.json()["workspace"]["revision"])
        conflict = self.client.put(
            "/api/creator/projects/project.workspace/workspace",
            json={"expected_revision": 0, "snapshot": snapshot},
        )
        self.assertEqual(409, conflict.status_code, conflict.text)
        self.assertEqual("CREATOR_WORKSPACE_REVISION_CONFLICT", conflict.json()["detail"]["code"])

    def test_creator_project_list_rename_and_delete(self):
        created = self.client.post("/api/creator/authoring-sessions", json={
            "session_id": "creator.projects", "project_id": "project.projects",
            "recipe_id": "recipe.projects", "intent": "Original project",
            "steps": [{"id": "draft", "intent": "Draft", "inputs": {}, "outputs": {}}],
            "source_references": [], "bindings": {},
        })
        self.assertEqual(200, created.status_code, created.text)
        listed = self.client.get("/api/creator/projects")
        self.assertEqual("project.projects", listed.json()["projects"][0]["project_id"])
        renamed = self.client.patch("/api/creator/projects/project.projects", json={"name": "Daily brief"})
        self.assertEqual("Daily brief", renamed.json()["creator"]["project_name"])
        deleted = self.client.delete("/api/creator/projects/project.projects")
        self.assertTrue(deleted.json()["deleted"])
        self.assertIsNone(self.client.get("/api/creator/projects/project.projects?optional=true").json()["creator"])

    def test_developer_node_delete_accepts_an_empty_delete_request(self):
        created = self.client.post("/api/lab/flows", json={
            "flow_id": "dev.delete-node", "name": "Delete node", "description": "test",
        })
        self.assertEqual(200, created.status_code, created.text)
        node = self.client.post("/api/lab/flows/dev.delete-node/nodes", json={
            "template_id": "runtime", "node_id": "temporary", "title": "Temporary",
            "after_node_id": "start",
        })
        self.assertEqual(200, node.status_code, node.text)
        deleted = self.client.request("DELETE", "/api/lab/flows/dev.delete-node/nodes/temporary")
        self.assertEqual(200, deleted.status_code, deleted.text)
        self.assertEqual("node_deleted", deleted.json()["status"])
        root = json.loads(self.client.get("/api/lab/flows/dev.delete-node/files").json()["files"]["root_flow"])
        self.assertNotIn("temporary", root["states"])
        self.assertNotIn("temporary_failed", root["states"])

    def test_developer_tool_node_inserted_after_start_has_a_sequence_edge(self):
        created = self.client.post("/api/lab/flows", json={
            "flow_id": "dev.insert-node", "name": "Insert node", "description": "test",
        })
        self.assertEqual(200, created.status_code, created.text)
        node = self.client.post("/api/lab/flows/dev.insert-node/nodes", json={
            "template_id": "tool_call", "node_id": "fetch", "title": "Fetch", "after_node_id": "start",
        })
        self.assertEqual(200, node.status_code, node.text)
        root = json.loads(self.client.get("/api/lab/flows/dev.insert-node/files").json()["files"]["root_flow"])
        self.assertIn({"id": "start_fetch", "kind": "sequence", "from": "start", "to": "fetch"}, root["execution_plan"]["edges"])
        self.assertIn("fetch_failed", root["states"])
        self.assertEqual("failed", root["states"]["fetch_failed"]["terminal_status"])

    def test_developer_can_scaffold_and_edit_package_owned_dlc(self):
        created = self.client.post("/api/lab/flows", json={
            "flow_id": "dev.custom-dlc", "name": "Custom DLC", "description": "Package-owned adapter",
        })
        self.assertEqual(200, created.status_code, created.text)
        scaffold = self.client.post("/api/developer/flows/dev.custom-dlc/portable-dlc", json={
            "node_id": "custom_adapter", "server": "custom_adapter", "tool": "run",
            "name": "Custom adapter", "description": "Protocol-owned blank adapter",
        })
        self.assertEqual(200, scaffold.status_code, scaffold.text)
        descriptor = self.client.get("/api/developer/flows/dev.custom-dlc/portable-dlc")
        self.assertEqual("custom_adapter", descriptor.json()["tools"][0]["node_id"])
        source = self.client.get("/api/lab/flows/dev.custom-dlc/mcp-nodes/custom_adapter/source")
        self.assertEqual(200, source.status_code, source.text)
        replaced = self.client.put("/api/lab/flows/dev.custom-dlc/mcp-nodes/custom_adapter/source", json={
            "expected_source_digest": source.json()["source_digest"], "source": source.json()["source"],
        })
        self.assertEqual(200, replaced.status_code, replaced.text)
        self.assertEqual("custom_adapter", replaced.json()["source_model"]["node_id"])

    def test_empty_registry_keeps_unresolved_semantic_nodes(self):
        model = type("Model", (), {"api_key": "test-key"})()
        output = json.dumps({
            "nodes": [{
                "id": "collect", "label": "收集公开信息", "description": "获取可审核的最新信息。",
                "needed_capability": "从公开信息源获取最新内容", "capability_id": None, "values": {},
            }],
            "relations": [],
        }, ensure_ascii=False)
        with patch("core.llm.config_manager.resolve_model", return_value=model), patch("core.llm.chat", new_callable=AsyncMock, return_value={"content": output}) as chat:
            result = self.client.post("/api/creator/compose-recipe", json={"session_id": "creator.empty", "project_id": "project.empty", "goal": "制作日报"})
        self.assertEqual(200, result.status_code)
        creator = result.json()["creator"]
        self.assertEqual("unresolved", creator["trusted_recipe"]["nodes"][0]["resolution"]["status"])
        self.assertEqual(1, creator["capability_resolution"]["unresolved"])
        self.assertFalse(creator["generation_readiness"]["ready"])
        chat.assert_awaited_once()

    def test_registry_composition_node_refinement_and_developer_confirmation(self):
        registered = self.client.put("/api/developer/trusted-node-presets/rss-source", json={"preset": PRESET, "mapping": mapping(), "expected_revision": 0})
        self.assertEqual(200, registered.status_code, registered.text)
        creator_registry = self.client.get("/api/creator/trusted-node-presets").json()
        self.assertNotIn("developer_mapping_key", json.dumps(creator_registry))

        flow_output = '{"recipe":{"nodes":[{"id":"sources","preset_id":"rss-source","values":{"topics":["AI"]}}],"relations":[]}}'
        model = type("Model", (), {"api_key": "test-key"})()
        with patch("core.llm.config_manager.resolve_model", return_value=model), patch("core.llm.chat", new_callable=AsyncMock, return_value={"content": flow_output}):
            composed = self.client.post("/api/creator/compose-recipe", json={"session_id": "creator.daily", "project_id": "project.daily", "goal": "制作 AI 日报"})
        self.assertEqual(200, composed.status_code, composed.text)
        creator = composed.json()["creator"]
        self.assertEqual("rss-source", creator["trusted_recipe"]["nodes"][0]["preset"]["id"])
        self.assertNotIn("source.rss.v1", json.dumps(creator))

        with patch("core.llm.config_manager.resolve_model", return_value=model), patch("core.llm.chat", new_callable=AsyncMock, return_value={"content": '{"values":{"topics":["AI","模型"]}}'}):
            proposal = self.client.post("/api/creator/authoring-sessions/creator.daily/nodes/sources/ai-proposals", json={"prompt": "增加模型主题", "expected_revision": 1})
        self.assertEqual(200, proposal.status_code, proposal.text)
        accepted = self.client.post(f"/api/creator/authoring-sessions/creator.daily/proposals/{proposal.json()['proposal']['proposal_id']}/accept", json={})
        self.assertEqual(["AI", "模型"], accepted.json()["creator"]["trusted_recipe"]["nodes"][0]["values"]["topics"])
        self.client.post("/api/creator/authoring-sessions/creator.daily/freeze", json={"step_ids": ["sources"], "summary": "Reviewed"})
        confirmed = self.client.post("/api/developer/authoring-sessions/creator.daily/confirm-materialization", json={"expected_revision": 2, "summary": "Mappings reviewed"})
        self.assertEqual(200, confirmed.status_code, confirmed.text)
        developer = confirmed.json()["developer"]
        self.assertEqual("source.rss.v1", developer["trusted_recipe"]["nodes"][0]["developer_mapping_key"])
        self.assertEqual(mapping()["digest"], developer["trusted_recipe"]["nodes"][0]["developer_mapping_digest"])

    def test_creator_package_is_the_only_creator_materialization_route(self):
        self.presets.put(PRESET, mapping(), expected_revision=0)
        model = type("Model", (), {"api_key": "test-key"})()
        flow_output = '{"recipe":{"nodes":[{"id":"sources","preset_id":"rss-source","values":{"topics":["AI"]}}],"relations":[]}}'
        with patch("core.llm.config_manager.resolve_model", return_value=model), patch("core.llm.chat", new_callable=AsyncMock, return_value={"content": flow_output}):
            composed = self.client.post("/api/creator/compose-recipe", json={"session_id": "creator.package", "project_id": "project.package", "goal": "制作 AI 日报"})
        self.assertEqual(200, composed.status_code, composed.text)
        self.client.post("/api/creator/authoring-sessions/creator.package/freeze", json={"step_ids": ["sources"], "summary": "Reviewed"})
        self.assertIn(self.client.post("/api/creator/authoring-sessions/creator.package/compile-candidate", json={"expected_revision": 1}).status_code, {404, 405})
        self.assertIn(self.client.post("/api/creator/authoring-sessions/creator.package/runtime-handoff", json={"expected_revision": 1, "compile_candidate": {}}).status_code, {404, 405})
        with patch.object(backend_main, "ROOT", self.root):
            packaged = self.client.post("/api/creator/authoring-sessions/creator.package/package", json={"expected_revision": 1})
        self.assertEqual(200, packaged.status_code, packaged.text)
        payload = packaged.json()
        self.assertEqual({"schema", "status", "filename", "url", "signature_verified"}, set(payload))
        self.assertEqual("ready", payload["status"])
        self.assertTrue(payload["signature_verified"])
        with patch.object(backend_main, "ROOT", self.root):
            delivered = self.client.post(
                "/api/creator/authoring-sessions/creator.package/desktop-runner",
                json={"expected_revision": 1},
            )
        self.assertEqual(200, delivered.status_code, delivered.text)
        self.assertEqual("installed", delivered.json()["status"])
        self.assertTrue(delivered.json()["package"]["signature_verified"])
        self.desktop_runner.install.assert_called_once()
        self.desktop_runner.install.reset_mock()
        self.desktop_runner.install.return_value = {
            "schema": "cartridgeflow.desktop_runner_delivery.v1", "status": "trust_required",
            "runner_url": "http://127.0.0.1:18990/?pending=" + "a" * 32,
            "approval_id": "a" * 32,
            "publisher": {"id": "creator", "key_id": "creator.development", "fingerprint": "0123456789abcdef"},
            "cartridge": {"id": "creator-package", "name": "Creator package", "version": "1.0.0"},
        }
        with patch.object(backend_main, "ROOT", self.root):
            awaiting_trust = self.client.post(
                "/api/creator/authoring-sessions/creator.package/desktop-runner",
                json={"expected_revision": 1},
            )
        self.assertEqual(200, awaiting_trust.status_code, awaiting_trust.text)
        self.assertEqual("trust_required", awaiting_trust.json()["status"])

    def test_overall_recompose_replaces_the_draft_and_resets_node_reviews(self):
        self.presets.put(PRESET, mapping(), expected_revision=0)
        model = type("Model", (), {"api_key": "configured"})()
        initial = '{"recipe":{"nodes":[{"id":"sources","preset_id":"rss-source","values":{"topics":["AI"]}}],"relations":[]}}'
        revised = '{"recipe":{"nodes":[{"id":"daily-sources","preset_id":"rss-source","values":{"topics":["AI","研究"]}}],"relations":[]}}'
        with patch("core.llm.config_manager.resolve_model", return_value=model), patch("core.llm.chat", new_callable=AsyncMock, return_value={"content": initial}):
            created = self.client.post("/api/creator/compose-recipe", json={"session_id": "creator.recompose", "project_id": "project.recompose", "goal": "制作 AI 日报"})
        self.assertEqual(200, created.status_code, created.text)
        self.client.post("/api/creator/authoring-sessions/creator.recompose/freeze", json={"step_ids": ["sources"], "summary": "Reviewed"})
        with patch("core.llm.config_manager.resolve_model", return_value=model), patch("core.llm.chat", new_callable=AsyncMock, return_value={"content": revised}):
            response = self.client.post("/api/creator/authoring-sessions/creator.recompose/recompose", json={"goal": "制作更偏研究的 AI 日报", "expected_revision": 1})
        self.assertEqual(200, response.status_code, response.text)
        creator = response.json()["creator"]
        self.assertEqual(2, creator["revision"])
        self.assertEqual(["daily-sources"], [node["id"] for node in creator["trusted_recipe"]["nodes"]])
        self.assertEqual([], creator["frozen_steps"])
        self.assertFalse(creator["generation_readiness"]["ready"])

    def test_developer_publishes_real_canvas_node(self):
        created = self.client.post("/api/lab/flows", json={"flow_id": "dev.trusted-source", "name": "Trusted source", "description": "test"})
        self.assertEqual(200, created.status_code, created.text)
        node = self.client.post("/api/lab/flows/dev.trusted-source/nodes", json={
            "template_id": "runtime", "node_id": "normalize", "title": "Normalize result",
            "node": {"params": {"preset_config": {"from": "seed", "to": "result", "topic": "AI"}}},
        })
        self.assertEqual(200, node.status_code, node.text)
        published = self.client.post("/api/developer/flows/dev.trusted-source/nodes/normalize/trusted-node-preset", json={
            "preset_id": "normalize-result", "creator_label": "Normalize result",
            "creator_description": "Normalize collected information into a reusable result.",
            "match_terms": ["normalize", "daily"],
            "editable_fields": [{"id": "topic", "label": "Topic", "value_type": "string", "required": True, "default": "AI"}],
            "creator_bindings": {"topic": "params.preset_config.topic"},
        })
        self.assertEqual(200, published.status_code, published.text)
        publication = published.json()["publication"]
        self.assertEqual("pass_result", publication["mapping"]["state_template"]["action"])
        self.assertNotIn("next", publication["mapping"]["state_template"])
        creator = self.client.get("/api/creator/trusted-node-presets").json()
        self.assertNotIn("state_template", json.dumps(creator))

    def test_developer_publishes_complete_flow_as_creator_safe_capability(self):
        created = self.client.post("/api/lab/flows", json={
            "flow_id": "dev.complete-capability", "name": "Complete capability", "description": "Reusable internal Flow",
        })
        self.assertEqual(200, created.status_code, created.text)
        node = self.client.post("/api/lab/flows/dev.complete-capability/nodes", json={
            "template_id": "runtime", "node_id": "normalize", "title": "Normalize content",
        })
        self.assertEqual(200, node.status_code, node.text)
        token = "verify_test_complete_capability"
        snapshot = backend_main._capability_flow_snapshot("dev.complete-capability")
        backend_main._atomic_json(self.verifications / f"{token}.json", {
            "schema": "cartridgeflow.capability_runtime_evidence.v1",
            "token": token,
            "flow_id": "dev.complete-capability",
            "source_digest": snapshot["source_digest"],
            "success_run": {"run_id": "run_success", "status": "completed"},
            "failure_run": {"run_id": "run_failure", "status": "failed", "error_code": "INPUT_REQUIRED"},
            "consumed": False,
        })
        published = self.client.post("/api/developer/flows/dev.complete-capability/capability-cartridges", json={
            "capability_id": "workspace.normalize-content",
            "label": "整理内容", "description": "把输入内容整理为可复用结果。",
            "match_terms": ["整理", "标准化"], "editable_fields": [], "creator_bindings": {},
            "public_inputs": [], "public_outputs": [], "dependencies": [], "trust_scope": "workspace",
            "verification_token": token,
        })
        self.assertEqual(200, published.status_code, published.text)
        release = published.json()["release"]
        self.assertEqual("flow", release["implementation"]["kind"])
        self.assertEqual("workspace", release["trust_scope"])
        creator = self.client.get("/api/creator/capability-cartridges")
        self.assertEqual(200, creator.status_code, creator.text)
        serialized = json.dumps(creator.json())
        self.assertIn("workspace.normalize-content", serialized)
        self.assertNotIn("root_flow", serialized)
        self.assertNotIn("implementation", serialized)

    def test_target_binding_is_validated_before_publication_and_evidence_consumption(self):
        created = self.client.post("/api/lab/flows", json={
            "flow_id": "dev.atomic-capability", "name": "Atomic capability", "description": "test",
        })
        self.assertEqual(200, created.status_code, created.text)
        node = self.client.post("/api/lab/flows/dev.atomic-capability/nodes", json={
            "template_id": "runtime", "node_id": "normalize", "title": "Normalize content",
        })
        self.assertEqual(200, node.status_code, node.text)
        token = "verify_test_atomic_capability"
        snapshot = backend_main._capability_flow_snapshot("dev.atomic-capability")
        evidence_path = self.verifications / f"{token}.json"
        backend_main._atomic_json(evidence_path, {
            "schema": "cartridgeflow.capability_runtime_evidence.v1",
            "token": token,
            "flow_id": "dev.atomic-capability",
            "source_digest": snapshot["source_digest"],
            "success_run": {"run_id": "run_success", "status": "completed"},
            "failure_run": {"run_id": "run_failure", "status": "failed", "error_code": "INPUT_REQUIRED"},
            "consumed": False,
        })
        with patch.object(
            self.sessions,
            "validate_capability_binding",
            side_effect=AuthoringServiceError(
                "AUTHORING_CAPABILITY_INTERFACE_INCOMPATIBLE",
                "The published capability does not satisfy the adjacent node data contracts.",
                status=409,
            ),
        ):
            response = self.client.post("/api/developer/flows/dev.atomic-capability/capability-cartridges", json={
                "capability_id": "workspace.atomic-capability",
                "label": "Atomic capability", "description": "Must not partially publish.",
                "match_terms": ["atomic"], "editable_fields": [], "creator_bindings": {},
                "public_inputs": [], "public_outputs": [], "dependencies": [], "trust_scope": "workspace",
                "verification_token": token,
                "target_project_id": "project.target", "target_node_id": "target",
            })
        self.assertEqual(409, response.status_code, response.text)
        self.assertEqual(0, self.capabilities.latest_revision("workspace.atomic-capability"))
        self.assertFalse(json.loads(evidence_path.read_text(encoding="utf-8"))["consumed"])

    def test_presentation_evidence_reports_typed_field_and_producer(self):
        created = self.client.post("/api/lab/flows", json={
            "flow_id": "dev.presentation-proof", "name": "Presentation proof", "description": "test",
        })
        self.assertEqual(200, created.status_code, created.text)
        display = self.client.post("/api/lab/flows/dev.presentation-proof/nodes", json={
            "template_id": "interaction", "node_id": "display", "title": "Display", "after_node_id": "start",
        })
        self.assertEqual(200, display.status_code, display.text)
        component = self.client.put("/api/lab/flows/dev.presentation-proof/display-components/topic.panel", json={
            "label": "Topic panel", "description": "Typed runtime data", "template_id": "summary",
            "target_node_id": "display",
            "fields": [{"id": "topic", "label": "Topic", "type": "text", "required": True, "source": "store:input_data.topic"}],
        })
        self.assertEqual(200, component.status_code, component.text)
        snapshot = backend_main._capability_flow_snapshot("dev.presentation-proof")
        snapshot["root_flow"]["states"]["collect"] = {
            "type": "process", "kind": "input", "executor": "user", "effect": "writes_store",
            "action": "collect_inputs", "inputs": {},
            "outputs": {"input_data": {"schema": {"type": "object"}, "target": {"type": "store", "key": "input_data"}}},
            "params": {"fields": ["topic"]},
        }
        event = {
            "state": "display",
            "data": {
                "action": "render_interaction",
                "presentation": {"component_id": "topic.panel", "component_version": "1.0.0", "entry_sha256": "a" * 64, "bindings": {"topic": 42}},
            },
        }
        with patch.object(backend_main.runner, "get_events", return_value=[event]):
            with self.assertRaises(AuthoringServiceError) as caught:
                backend_main._presentation_runtime_evidence("dev.presentation-proof", snapshot, {"run_id": "run_success"})
        self.assertEqual("CAPABILITY_EVIDENCE_PRESENTATION_TYPE_INVALID", caught.exception.code)
        self.assertIn("display", str(caught.exception))
        self.assertIn("collect", str(caught.exception))

        event["data"]["presentation"]["bindings"]["topic"] = "AI"
        with patch.object(backend_main.runner, "get_events", return_value=[event]):
            checks = backend_main._presentation_runtime_evidence("dev.presentation-proof", snapshot, {"run_id": "run_success"})
        self.assertEqual("collect", checks[0]["fields"][0]["producer_node_id"])

    def test_verified_production_release_requires_current_evidence_and_frozen_recipe(self):
        created = self.client.post("/api/lab/flows", json={
            "flow_id": "dev.verified-release", "name": "Verified release", "description": "test",
        })
        self.assertEqual(200, created.status_code, created.text)
        promoted = self.client.post("/api/developer/flows/dev.verified-release/production-candidate")
        self.assertEqual(200, promoted.status_code, promoted.text)
        snapshot = backend_main._capability_flow_snapshot("dev.verified-release")
        token = "verify_test_production_release"
        backend_main._atomic_json(self.verifications / f"{token}.json", {
            "schema": "cartridgeflow.capability_runtime_evidence.v2",
            "token": token,
            "flow_id": "dev.verified-release",
            "source_digest": snapshot["source_digest"],
            "success_run": {"run_id": "run_success", "status": "completed"},
            "failure_run": {"run_id": "run_failure", "status": "failed", "error_code": "INPUT_REQUIRED"},
            "presentation_checks": [],
            "consumed": False,
        })
        recipe = self.client.post("/api/lab/flows/dev.verified-release/tuning/releases", json={
            "author": "test", "message": "Freeze verified release",
        })
        self.assertEqual(200, recipe.status_code, recipe.text)
        with patch.object(backend_main, "package_cartridge", return_value={
            "ok": True, "protocol": "CF-CRE@2", "release_id": "release-test", "activation_allowed": True,
        }):
            packaged = self.client.post("/api/developer/flows/dev.verified-release/production-release", json={
                "verification_token": token,
            })
        self.assertEqual(200, packaged.status_code, packaged.text)
        self.assertEqual(token, packaged.json()["runtime_evidence"]["token"])
        self.assertEqual(recipe.json()["release"]["id"], packaged.json()["recipe_release"]["id"])

        files = self.dev_flows.read_files("dev.verified-release")
        manifest = json.loads(files["manifest"])
        manifest["description"] = "changed after evidence"
        self.dev_flows.save_file("dev.verified-release", "manifest", json.dumps(manifest))
        stale = self.client.post("/api/developer/flows/dev.verified-release/production-release", json={
            "verification_token": token,
        })
        self.assertEqual(409, stale.status_code, stale.text)
        self.assertEqual("CAPABILITY_RUNTIME_EVIDENCE_STALE", stale.json()["detail"]["code"])

    def test_developer_can_check_trusted_node_readiness_before_publish(self):
        created = self.client.post("/api/lab/flows", json={
            "flow_id": "dev.trusted-readiness", "name": "Trusted readiness", "description": "test",
        })
        self.assertEqual(200, created.status_code, created.text)
        process = self.client.post("/api/lab/flows/dev.trusted-readiness/nodes", json={
            "template_id": "runtime", "node_id": "normalize", "title": "Normalize result",
        })
        self.assertEqual(200, process.status_code, process.text)
        ready = self.client.get(
            "/api/developer/flows/dev.trusted-readiness/nodes/normalize/trusted-node-preset/readiness"
        )
        self.assertEqual(200, ready.status_code, ready.text)
        self.assertTrue(ready.json()["ready"])
        self.assertEqual("pass_result", ready.json()["action"])

        interaction = self.client.post("/api/lab/flows/dev.trusted-readiness/nodes", json={
            "template_id": "interaction", "node_id": "local_ui", "title": "Local UI",
        })
        self.assertEqual(200, interaction.status_code, interaction.text)
        blocked = self.client.get(
            "/api/developer/flows/dev.trusted-readiness/nodes/local_ui/trusted-node-preset/readiness"
        )
        self.assertEqual(200, blocked.status_code, blocked.text)
        self.assertFalse(blocked.json()["ready"])
        self.assertEqual("TRUSTED_NODE_MAPPING_RESOURCE_UNSUPPORTED", blocked.json()["blocker"]["code"])

    def test_publish_records_simulation_and_activation_controls_creator_registry(self):
        self.client.post("/api/lab/flows", json={"flow_id": "dev.lifecycle", "name": "Lifecycle", "description": "test"})
        self.client.post("/api/lab/flows/dev.lifecycle/nodes", json={
            "template_id": "runtime", "node_id": "normalize", "title": "Normalize result",
            "node": {"params": {"preset_config": {"from": "seed", "to": "result", "topic": "AI"}}},
        })
        payload = {
            "preset_id": "normalize-lifecycle", "creator_label": "Normalize result",
            "creator_description": "Normalize a result without external effects.",
            "match_terms": ["normalize"],
            "editable_fields": [{"id": "topic", "label": "Topic", "value_type": "string", "required": True, "default": "AI"}],
            "creator_bindings": {"topic": "params.preset_config.topic"},
        }
        simulated = self.client.post(
            "/api/developer/flows/dev.lifecycle/nodes/normalize/trusted-node-preset/simulate", json=payload,
        )
        self.assertEqual(200, simulated.status_code, simulated.text)
        self.assertEqual("passed", simulated.json()["status"])
        self.assertFalse(simulated.json()["executed_real_resources"])
        published = self.client.post(
            "/api/developer/flows/dev.lifecycle/nodes/normalize/trusted-node-preset", json=payload,
        )
        self.assertEqual(200, published.status_code, published.text)
        registry = self.client.get("/api/developer/trusted-node-presets").json()
        entry = registry["entries"][0]
        self.assertEqual("passed", entry["simulation_evidence"]["1"]["status"])
        stopped = self.client.patch(
            "/api/developer/trusted-node-presets/normalize-lifecycle/activation", json={"active": False},
        )
        self.assertEqual(200, stopped.status_code, stopped.text)
        self.assertEqual([], self.client.get("/api/creator/trusted-node-presets").json()["presets"])
        restored = self.client.patch(
            "/api/developer/trusted-node-presets/normalize-lifecycle/activation", json={"active": True, "revision": 1},
        )
        self.assertEqual("active", restored.json()["entry"]["status"])

    def test_simulation_distinguishes_safe_local_nodes_from_unbound_external_nodes(self):
        deterministic = backend_main._simulate_trusted_node_candidate(
            "dev.sim", "pass", {"manifest": {"id": "dev.sim"}, "root_flow": {"states": {"pass": STATE}}}, STATE, mapping(),
        )
        self.assertEqual("passed", deterministic["status"])

        ai_state = {
            "type": "process", "kind": "decision", "executor": "llm", "effect": "none", "action": "llm_prompt",
            "model_role": "runtime", "params": {"model_role": "runtime", "prompt": "Summarize", "output": "summary"},
        }
        ai_manifest = {"id": "dev.sim", "llm_recipe": {"schema": "cartridgeflow.llm_recipe.v1", "roles": [{
            "id": "runtime", "label": "Runtime", "capability": "text_generation", "api_type": "openai_compatible",
            "wire_api": "chat_completions", "model": "configured-locally", "required": True,
        }]}}
        ai_preset = {**PRESET, "id": "ai-summary", "editable_fields": [], "developer_mapping_key": "ai.summary"}
        ai_mapping = build_trusted_node_mapping(
            ai_preset, ai_state, source_flow_id="dev.sim", source_node_id="ai",
            creator_bindings={}, source_manifest=ai_manifest,
        )
        with patch("core.llm.config_manager.list_providers", return_value=[]), patch("core.llm.config_manager.get_assignments", return_value={"version": 1, "defaults": {}, "cartridges": {}, "nodes": {}}):
            ai = backend_main._simulate_trusted_node_candidate(
                "dev.sim", "ai", {"manifest": ai_manifest, "root_flow": {"states": {"ai": ai_state}}}, ai_state, ai_mapping,
            )
        self.assertEqual("blocked", ai["status"])
        self.assertEqual("TRUSTED_NODE_MODEL_BINDING_REQUIRED", next(item for item in ai["checks"] if item["status"] == "blocked")["code"])

        review_state = {
            "type": "process", "kind": "interaction", "executor": "human", "effect": "none", "action": "confirm_checkpoint",
            "params": {"interaction": {"prompt": "Review", "store_key": "answer", "resume_policy": "resume_same_node"}},
        }
        review_preset = {**PRESET, "id": "human-review", "editable_fields": [], "developer_mapping_key": "human.review"}
        review_mapping = build_trusted_node_mapping(
            review_preset, review_state, source_flow_id="dev.sim", source_node_id="review", creator_bindings={}, source_manifest={},
        )
        review = backend_main._simulate_trusted_node_candidate(
            "dev.sim", "review", {"manifest": {"id": "dev.sim"}, "root_flow": {"states": {"review": review_state}}}, review_state, review_mapping,
        )
        self.assertEqual("passed", review["status"])

        tool_state = {
            "type": "process", "kind": "mcp_read", "executor": "mcp", "effect": "read_only", "action": "tool_call",
            "allowed_tools": ["filesystem_read"],
            "tools": [{"type": "builtin", "server": "filesystem", "tool": "read_file", "mcp_tool_id": "filesystem_read"}],
            "params": {"tools": [{"type": "builtin", "server": "filesystem", "tool": "read_file", "mcp_tool_id": "filesystem_read"}]},
        }
        tool_manifest = {"id": "dev.sim", "mcp_tools": [{
            "id": "filesystem_read", "type": "builtin", "server": "filesystem", "tool": "read_file", "required": True,
        }]}
        tool_preset = {**PRESET, "id": "read-file", "editable_fields": [], "developer_mapping_key": "tool.read"}
        tool_mapping = build_trusted_node_mapping(
            tool_preset, tool_state, source_flow_id="dev.sim", source_node_id="tool", creator_bindings={}, source_manifest=tool_manifest,
        )
        tool = backend_main._simulate_trusted_node_candidate(
            "dev.sim", "tool", {"manifest": tool_manifest, "root_flow": {"states": {"tool": tool_state}}}, tool_state, tool_mapping,
        )
        self.assertEqual("passed", tool["status"])

        remote_state = {
            "type": "process", "kind": "remote_call", "executor": "remote", "effect": "external_side_effect", "action": "remote_call",
            "permission": "external_call", "params": {"preset": "remote_mcp_call", "preset_config": {"service": "remote"}},
        }
        remote_manifest = {"id": "dev.sim", "permissions": [{"id": "external_call"}]}
        remote_preset = {**PRESET, "id": "remote-call", "editable_fields": [], "developer_mapping_key": "remote.call"}
        remote_mapping = build_trusted_node_mapping(
            remote_preset, remote_state, source_flow_id="dev.sim", source_node_id="remote", creator_bindings={}, source_manifest=remote_manifest,
        )
        remote = backend_main._simulate_trusted_node_candidate(
            "dev.sim", "remote", {"manifest": remote_manifest, "root_flow": {"states": {"remote": remote_state}}}, remote_state, remote_mapping,
        )
        self.assertEqual("blocked", remote["status"])
        self.assertEqual("TRUSTED_NODE_TOOL_BINDING_REQUIRED", next(item for item in remote["checks"] if item["status"] == "blocked")["code"])

    def test_developer_cannot_expose_internal_runtime_parameters_to_creator(self):
        internal_preset = {
            **PRESET,
            "editable_fields": [{
                "id": "preset", "label": "Preset", "value_type": "string", "required": True, "default": "pass",
            }],
        }
        with self.assertRaisesRegex(ValueError, "existing params"):
            build_trusted_node_mapping(
                internal_preset,
                {**STATE, "params": {"preset": "pass"}},
                source_flow_id="dev.sources",
                source_node_id="runtime",
                creator_bindings={"preset": "params.preset"},
                source_manifest={},
            )


if __name__ == "__main__":
    unittest.main()
