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
from core.studio.trusted_node_presets import TrustedNodePresetStore


PRESET = {
    "schema": "cartridgeflow.trusted_node_preset.v1", "protocol": {"id": "CF-TUNING", "version": "1.4"},
    "id": "rss-source", "revision": 1, "creator_label": "收集公开信息源",
    "creator_description": "按主题收集可供用户审核的公开信息源。", "match_terms": ["RSS", "日报"],
    "editable_fields": [{"id": "topics", "label": "关注主题", "value_type": "string_list", "required": True, "default": ["AI"]}],
    "developer_mapping_key": "source.rss.v1",
}


class TrustedCreatorApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.sessions = AuthoringSessionStore(root / "sessions")
        self.presets = TrustedNodePresetStore(root / "presets")
        self.patches = [
            patch.object(backend_main, "authoring_sessions", self.sessions),
            patch.object(backend_main, "trusted_node_presets", self.presets),
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
        registered = self.client.put("/api/developer/trusted-node-presets/rss-source", json={"preset": PRESET, "expected_revision": 0})
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


if __name__ == "__main__":
    unittest.main()
