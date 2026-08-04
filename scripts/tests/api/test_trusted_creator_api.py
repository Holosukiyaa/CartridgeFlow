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

    def test_registry_composition_node_refinement_and_developer_confirmation(self):
        registered = self.client.put("/api/developer/trusted-node-presets/rss-source", json={"preset": PRESET, "mapping": mapping(), "expected_revision": 0})
        self.assertEqual(200, registered.status_code, registered.text)
        creator_registry = self.client.get("/api/creator/trusted-node-presets").json()
        self.assertNotIn("developer_mapping_key", json.dumps(creator_registry))

        flow_output = '{"recipe":{"nodes":[{"id":"sources","preset_id":"rss-source","values":{"topics":["AI"]}}],"relations":[]}}'
        model = type("Model", (), {"api_key": "configured"})()
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
