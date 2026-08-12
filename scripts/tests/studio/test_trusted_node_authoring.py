import sys
import tempfile
import unittest
import json
import zipfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol import inspect_release_archive, trusted_public_keys
from core.protocol.trusted_node_recipes import create_dynamic_recipe
from core.studio.authoring_service import AuthoringServiceError, AuthoringSessionStore
from core.studio.creator_runtime_bridge import CreatorRuntimeBridge, CreatorRuntimeBridgeError
from core.studio.trusted_node_presets import TrustedNodePresetStore, build_trusted_node_mapping
from core.lab.node_executor import LabNodeExecutor
from core.protocol.tuning import canonical_digest


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


class TrustedNodeAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sessions = AuthoringSessionStore(Path(self.temp.name) / "sessions")
        self.presets = TrustedNodePresetStore(Path(self.temp.name) / "presets")
        self.presets.put(PRESET, mapping(), expected_revision=0)
        self.recipe = create_dynamic_recipe("recipe.daily", "制作 AI 日报", {"nodes": [{"id": "sources", "preset_id": "rss-source", "values": {}}], "relations": []}, self.presets.list_developer())

    def tearDown(self):
        self.temp.cleanup()

    def test_registry_is_empty_by_default_and_revisions_are_optimistic(self):
        empty = TrustedNodePresetStore(Path(self.temp.name) / "empty")
        self.assertEqual([], empty.list_creator())
        next_revision = {**PRESET, "revision": 2, "creator_description": "新的安全说明。"}
        with self.assertRaises(AuthoringServiceError): self.presets.put(next_revision, mapping(next_revision), expected_revision=0)
        self.presets.put(next_revision, mapping(next_revision), expected_revision=1)
        self.assertEqual(2, self.presets.get("rss-source")["revision"])

    def test_registry_activation_moves_pointer_without_rewriting_history(self):
        second = {**PRESET, "revision": 2, "creator_description": "第二个不可变版本。"}
        evidence = {
            "schema": "cartridgeflow.trusted_node_simulation.v1",
            "flow_id": "dev.sources",
            "node_id": "rss",
            "status": "passed",
            "mapping_digest": mapping(second)["digest"],
            "mode": "isolated_dry_run",
            "executed_real_resources": False,
            "created_at": "2026-08-04T00:00:00+08:00",
            "checks": [{"id": "portable_snapshot", "status": "passed", "message": "ok"}],
        }
        evidence["digest"] = canonical_digest(evidence)
        self.presets.put(second, mapping(second), expected_revision=1, simulation_evidence=evidence)
        self.presets.set_activation("rss-source", active=False)
        self.assertEqual([], self.presets.list_creator())
        rolled_back = self.presets.set_activation("rss-source", active=True, revision=1)
        self.assertEqual(1, rolled_back["active_revision"])
        self.assertEqual(2, rolled_back["latest_revision"])
        self.assertEqual([1, 2], [item["preset"]["revision"] for item in rolled_back["revisions"]])
        third = {**PRESET, "revision": 3, "creator_description": "回滚后发布的新版本。"}
        self.presets.put(third, mapping(third), expected_revision=2)
        self.assertEqual(3, self.presets.latest_revision("rss-source"))

    def test_registry_reports_creator_project_usage(self):
        self.sessions.create_from_recipe(
            "creator.daily", "project.daily", self.recipe, self.presets.list_developer(),
            mappings=self.presets.mappings_for_recipe(self.recipe),
        )
        usage = self.sessions.trusted_preset_usage("rss-source")
        self.assertEqual("project.daily", usage[0]["project_id"])
        self.assertEqual({"node_id": "sources", "revision": 1}, usage[0]["nodes"][0])

    def test_creator_projection_is_safe_and_topology_mutation_is_blocked(self):
        projection = self.sessions.create_from_recipe("creator.daily", "project.daily", self.recipe, self.presets.list_developer(), mappings=self.presets.mappings_for_recipe(self.recipe))
        self.assertEqual("rss-source", projection["trusted_recipe"]["nodes"][0]["preset"]["id"])
        self.assertNotIn("developer_mapping_key", str(projection))
        with self.assertRaises(AuthoringServiceError) as error:
            self.sessions.propose("creator.daily", [{"id": "invent", "target_id": "invented", "operation": "add_step", "value": {"id": "invented", "intent": "定义第一周输出", "inputs": {}, "outputs": {}}}], author="creator", summary="invent", expected_revision=1)
        self.assertEqual("AUTHORING_TRUSTED_RECIPE_CHANGE_FORBIDDEN", error.exception.code)

    def test_node_replacement_cannot_remove_required_preset_fields(self):
        self.sessions.create_from_recipe("creator.daily", "project.daily", self.recipe, self.presets.list_developer(), mappings=self.presets.mappings_for_recipe(self.recipe))
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
        self.sessions.create_from_recipe("creator.daily", "project.daily", self.recipe, self.presets.list_developer(), mappings=self.presets.mappings_for_recipe(self.recipe))
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
        with zipfile.ZipFile(Path(self.temp.name) / "packages" / handoff["filename"]) as archive:
            root_flow = json.loads(archive.read("payload/root.flow.json"))
        state = root_flow["states"]["step.sources"]
        self.assertEqual("process", state["type"])
        self.assertEqual("pass_result", state["action"])
        self.assertEqual(["AI"], state["params"]["preset_config"]["topics"])
        self.assertIn("handoff.failure.000", {edge["id"] for edge in root_flow["execution_plan"]["edges"]})
        runtime_state = {"context": {"store": {"seed": "ready"}}}
        result = LabNodeExecutor(ROOT).execute("step.sources", state, runtime_state, {}, Path(self.temp.name))
        self.assertTrue(result["ok"])
        self.assertEqual("ready", runtime_state["context"]["store"]["result"])

    def test_creator_package_boundary_builds_signed_archive_without_project_confirmation(self):
        self.sessions.create_from_recipe(
            "creator.package", "project.package", self.recipe, self.presets.list_developer(),
            mappings=self.presets.mappings_for_recipe(self.recipe),
        )
        self.sessions.freeze("creator.package", ["sources"], author="creator", summary="Reviewed")
        bridge = CreatorRuntimeBridge(Path(self.temp.name), Path(self.temp.name) / "packages-v16")
        package = bridge.package(self.sessions, "creator.package", expected_revision=1)
        self.assertEqual({"id": "CF-FARP", "version": "1.6"}, package["root_flow"]["protocol"])
        self.assertTrue(package["signature"]["verified"])
        self.assertNotIn("developer_confirmation", package["lineage"])
        self.assertEqual(
            self.sessions.compile_candidate(self.sessions.get("creator.package"))["mapping_digest"],
            package["lineage"]["mapping_snapshot_digest"],
        )
        with zipfile.ZipFile(Path(self.temp.name) / "packages-v16" / package["filename"]) as archive:
            root_flow = json.loads(archive.read("payload/root.flow.json"))
        self.assertEqual("1.6", root_flow["protocol"]["version"])
        verified = inspect_release_archive(
            Path(self.temp.name) / "packages-v16" / package["filename"],
            trusted_keys=trusted_public_keys(Path(self.temp.name)),
        )
        self.assertTrue(verified["activation_allowed"], verified["report"])

    def test_registry_rejects_preset_without_executable_mapping(self):
        empty = TrustedNodePresetStore(Path(self.temp.name) / "strict")
        with self.assertRaises(TypeError):
            empty.put(PRESET, expected_revision=0)

    def test_mapping_rejects_unknown_actions_and_external_topology(self):
        unknown = {**STATE, "action": "invented_action"}
        with self.assertRaises(AuthoringServiceError):
            build_trusted_node_mapping(PRESET, unknown, source_flow_id="dev.sources", source_node_id="rss", creator_bindings={"topics": "params.preset_config.topics"})
        routed = {**STATE, "action_routes": {"approved": "another_node"}}
        with self.assertRaises(AuthoringServiceError):
            build_trusted_node_mapping(PRESET, routed, source_flow_id="dev.sources", source_node_id="rss", creator_bindings={"topics": "params.preset_config.topics"})
        nested_route = deepcopy(STATE)
        nested_route["params"]["interaction"] = {"resume_policy": "resume_target_node", "target_node": "another_node"}
        with self.assertRaises(AuthoringServiceError):
            build_trusted_node_mapping(PRESET, nested_route, source_flow_id="dev.sources", source_node_id="rss", creator_bindings={"topics": "params.preset_config.topics"})

    def test_mapping_rejects_sensitive_or_type_mismatched_creator_paths(self):
        sensitive = deepcopy(STATE)
        sensitive["params"]["api_key"] = ["not-a-real-key"]
        with self.assertRaises(AuthoringServiceError):
            build_trusted_node_mapping(PRESET, sensitive, source_flow_id="dev.sources", source_node_id="rss", creator_bindings={"topics": "params.api_key"})
        wrong_type = deepcopy(STATE)
        wrong_type["params"]["preset_config"]["topics"] = "AI"
        with self.assertRaises(AuthoringServiceError):
            build_trusted_node_mapping(PRESET, wrong_type, source_flow_id="dev.sources", source_node_id="rss", creator_bindings={"topics": "params.preset_config.topics"})

    def test_mapping_carries_only_referenced_tools_and_rejects_local_dlc(self):
        tool_state = {
            **deepcopy(STATE), "kind": "mcp_read", "executor": "mcp", "action": "tool_call",
            "allowed_tools": ["fetch_news"],
            "tools": [{"type": "builtin", "server": "news", "tool": "fetch", "mcp_tool_id": "fetch_news"}],
        }
        manifest = {"mcp_tools": [
            {"id": "fetch_news", "type": "builtin", "server": "news", "tool": "fetch"},
            {"id": "unused_local", "type": "cartridge_dlc", "server": "local", "tool": "read"},
        ]}
        portable = build_trusted_node_mapping(PRESET, tool_state, source_flow_id="dev.sources", source_node_id="rss", creator_bindings={"topics": "params.preset_config.topics"}, source_manifest=manifest)
        self.assertEqual(["fetch_news"], [item["id"] for item in portable["requirements"]["mcp_tools"]])
        tool_state["allowed_tools"] = ["unused_local"]
        tool_state["tools"][0]["mcp_tool_id"] = "unused_local"
        with self.assertRaises(AuthoringServiceError):
            build_trusted_node_mapping(PRESET, tool_state, source_flow_id="dev.sources", source_node_id="rss", creator_bindings={"topics": "params.preset_config.topics"}, source_manifest=manifest)


if __name__ == "__main__":
    unittest.main()
