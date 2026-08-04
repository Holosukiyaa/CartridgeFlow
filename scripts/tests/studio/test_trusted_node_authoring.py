import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol.trusted_node_recipes import create_dynamic_recipe
from core.studio.authoring_service import AuthoringServiceError, AuthoringSessionStore
from core.studio.creator_runtime_bridge import CreatorRuntimeBridge, CreatorRuntimeBridgeError
from core.studio.trusted_node_presets import TrustedNodePresetStore


PRESET = {
    "schema": "cartridgeflow.trusted_node_preset.v1", "protocol": {"id": "CF-TUNING", "version": "1.4"},
    "id": "rss-source", "revision": 1, "creator_label": "收集公开信息源",
    "creator_description": "按主题收集可供用户审核的公开信息源。", "match_terms": ["RSS", "日报"],
    "editable_fields": [{"id": "topics", "label": "关注主题", "value_type": "string_list", "required": True, "default": ["AI"]}],
    "developer_mapping_key": "source.rss.v1",
}


class TrustedNodeAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sessions = AuthoringSessionStore(Path(self.temp.name) / "sessions")
        self.presets = TrustedNodePresetStore(Path(self.temp.name) / "presets")
        self.presets.put(PRESET, expected_revision=0)
        self.recipe = create_dynamic_recipe("recipe.daily", "制作 AI 日报", {"nodes": [{"id": "sources", "preset_id": "rss-source", "values": {}}], "relations": []}, self.presets.list_developer())

    def tearDown(self):
        self.temp.cleanup()

    def test_registry_is_empty_by_default_and_revisions_are_optimistic(self):
        empty = TrustedNodePresetStore(Path(self.temp.name) / "empty")
        self.assertEqual([], empty.list_creator())
        next_revision = {**PRESET, "revision": 2, "creator_description": "新的安全说明。"}
        with self.assertRaises(AuthoringServiceError): self.presets.put(next_revision, expected_revision=0)
        self.presets.put(next_revision, expected_revision=1)
        self.assertEqual(2, self.presets.get("rss-source")["revision"])

    def test_creator_projection_is_safe_and_topology_mutation_is_blocked(self):
        projection = self.sessions.create_from_recipe("creator.daily", "project.daily", self.recipe, self.presets.list_developer())
        self.assertEqual("rss-source", projection["trusted_recipe"]["nodes"][0]["preset"]["id"])
        self.assertNotIn("developer_mapping_key", str(projection))
        with self.assertRaises(AuthoringServiceError) as error:
            self.sessions.propose("creator.daily", [{"id": "invent", "target_id": "invented", "operation": "add_step", "value": {"id": "invented", "intent": "定义第一周输出", "inputs": {}, "outputs": {}}}], author="creator", summary="invent", expected_revision=1)
        self.assertEqual("AUTHORING_TRUSTED_RECIPE_CHANGE_FORBIDDEN", error.exception.code)

    def test_node_replacement_cannot_remove_required_preset_fields(self):
        self.sessions.create_from_recipe("creator.daily", "project.daily", self.recipe, self.presets.list_developer())
        with self.assertRaises(AuthoringServiceError) as error:
            self.sessions.propose(
                "creator.daily",
                [{"id": "clear", "target_id": "sources", "operation": "set_creator_binding", "value": {}}],
                author="creator",
                summary="clear required values",
                expected_revision=1,
            )
        self.assertEqual("AUTHORING_TRUSTED_NODE_FIELD_INVALID", error.exception.code)

    def test_developer_confirmation_is_required_before_signed_handoff(self):
        self.sessions.create_from_recipe("creator.daily", "project.daily", self.recipe, self.presets.list_developer())
        self.sessions.freeze("creator.daily", ["sources"], author="creator", summary="Reviewed")
        state = self.sessions.get("creator.daily")
        candidate = self.sessions.compile_candidate(state)
        bridge = CreatorRuntimeBridge(ROOT, Path(self.temp.name) / "packages")
        with self.assertRaises(CreatorRuntimeBridgeError) as error:
            bridge.materialize(self.sessions, "creator.daily", expected_revision=1, candidate=candidate)
        self.assertEqual("CREATOR_HANDOFF_DEVELOPER_CONFIRMATION_REQUIRED", error.exception.code)
        self.sessions.confirm_materialization("creator.daily", expected_revision=1, author="developer", summary="Mappings reviewed")
        handoff = bridge.materialize(self.sessions, "creator.daily", expected_revision=1, candidate=candidate)
        self.assertEqual({"id": "CF-FARP", "version": "1.5"}, handoff["root_flow"]["protocol"])
        self.assertTrue(handoff["signature"]["verified"])


if __name__ == "__main__":
    unittest.main()
