import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient

from backend import main as backend_main
from backend.main import app
from core.studio.authoring_service import AuthoringSessionStore
from core.studio.trusted_node_presets import TrustedNodePresetStore, build_trusted_node_mapping
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
        self.presets = TrustedNodePresetStore(root / "presets")
        self.registry = CartridgeRegistry(root)
        self.dev_flows = DevFlowManager(root)
        self.patches = [
            patch.object(backend_main, "authoring_sessions", self.sessions),
            patch.object(backend_main, "trusted_node_presets", self.presets),
            patch.object(backend_main, "registry", self.registry),
            patch.object(backend_main, "dev_flow_manager", self.dev_flows),
        ]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def test_optional_project_lookup_returns_empty_creator(self):
        response = self.client.get("/api/creator/projects/project.missing?optional=true")
        self.assertEqual(200, response.status_code, response.text)
        self.assertIsNone(response.json()["creator"])

    def test_empty_registry_returns_capability_gap_without_calling_model(self):
        with patch("core.llm.chat", new_callable=AsyncMock) as chat:
            result = self.client.post("/api/creator/compose-recipe", json={"session_id": "creator.empty", "project_id": "project.empty", "goal": "制作日报"})
        self.assertEqual(200, result.status_code)
        self.assertEqual("cartridgeflow.creator_capability_gap.v1", result.json()["capability_gap"]["schema"])
        chat.assert_not_called()

    def test_canvas_setup_publishes_one_simulated_base_owned_starter_capability(self):
        model = type("Model", (), {
            "api_key": "test-key",
            "provider_id": "creator-test-provider",
            "model": "creator-test-model",
        })()
        report = {"status": "ok", "items": [
            {"node_id": "ai-transform", "status": "ok"},
        ]}
        assignments = {"version": 1, "defaults": {}, "cartridges": {}, "nodes": {}}
        with (
            patch("core.llm.config_manager.resolve_model", return_value=model),
            patch("core.llm.config_manager.get_provider", return_value={"id": model.provider_id}),
            patch("core.llm.config_manager.get_assignments", return_value=assignments),
            patch("core.llm.config_manager.save_assignments") as save_assignments,
            patch("core.llm.config_manager.build_model_binding_report", return_value=report),
        ):
            created = self.client.post("/api/creator/starter-capabilities")
            repeated = self.client.post("/api/creator/starter-capabilities")
        self.assertEqual(200, created.status_code, created.text)
        self.assertEqual(200, repeated.status_code, repeated.text)
        self.assertTrue(created.json()["ready"])
        self.assertEqual("starter-ai-transform", created.json()["capability"]["id"])
        self.assertEqual(1, self.presets.latest_revision("starter-ai-transform"))
        publication = self.presets.get_publication("starter-ai-transform")
        self.assertEqual("llm_prompt", publication["mapping"]["state_template"]["action"])
        entry = self.presets.list_entries()[0]
        self.assertEqual("passed", entry["simulation_evidence"]["1"]["status"])
        creator_registry = self.client.get("/api/creator/trusted-node-presets").json()
        self.assertNotIn("state_template", json.dumps(creator_registry))
        save_assignments.assert_called_once()

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
