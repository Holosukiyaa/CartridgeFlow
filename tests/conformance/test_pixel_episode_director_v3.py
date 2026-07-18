import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.cartridge.registry import CartridgeRegistry
from core.cartridge.runner import CartridgeRunner
from core.cartridge.validator import ManifestValidator
from core.lab import FlowGraphBuilder
from core.lab.builtin_mcp import BuiltinMcpRegistry
from core.lab.flow_analyzer import analyze_flow_structure
from core.lab.node_executor import LabNodeExecutor
from core.protocol import build_protocol_certification_report, load_base_implementation


ROOT = Path(__file__).resolve().parents[2]
CART = ROOT / "cartridges" / "dev" / "dev.pixel_episode_director_v3"


class PixelEpisodeDirectorV3Test(unittest.TestCase):
    def _load(self):
        manifest = json.loads((CART / "manifest.json").read_text(encoding="utf-8"))
        root_flow = json.loads((CART / "root.flow.json").read_text(encoding="utf-8"))
        return manifest, root_flow

    def test_manifest_is_protocol_certified(self):
        manifest, root_flow = self._load()
        ManifestValidator().validate_package(CART, manifest)
        report = build_protocol_certification_report(load_base_implementation(ROOT), manifest, root_flow, ROOT)
        self.assertTrue(report["ok"], report.get("findings"))
        self.assertEqual("certified", report["status"])
        self.assertEqual("cf-farp-0-4-certified", report["label"])

    def test_parallel_collaboration_lanes_are_explicit(self):
        _, root_flow = self._load()
        structure = analyze_flow_structure(root_flow)
        self.assertEqual([], structure["findings"])

        edges = {(edge.get("from"), edge.get("to")) for edge in root_flow.get("edges") or []}
        self.assertIn(("planning_fork", "plan_story_beats"), edges)
        self.assertIn(("planning_fork", "plan_asset_specs"), edges)
        self.assertIn(("planning_fork", "plan_camera_language"), edges)
        self.assertIn(("plan_story_beats", "assemble_creation_packet"), edges)
        self.assertIn(("forge_draft_assets", "review_draft_assets"), edges)
        self.assertIn(("review_draft_assets", "review_draft_assets_external_tool_mroweam2_0"), edges)
        self.assertIn(("review_draft_assets_external_tool_mroweam2_0", "assemble_creation_packet"), edges)
        self.assertIn(("plan_camera_language", "assemble_creation_packet"), edges)

        for node_id, consume_key in {
            "plan_story_beats": "story_beats_payload",
            "plan_asset_specs": "asset_specs_payload",
            "plan_camera_language": "camera_plan_payload",
        }.items():
            node = root_flow["states"][node_id]
            contract = node["decision_contract"]
            self.assertEqual("resume_same_node", contract["interaction"]["resume_policy"])
            self.assertEqual(consume_key, contract["consume"]["as"])

        review = root_flow["states"]["review_draft_assets"]["decision_contract"]
        self.assertEqual("asset_review_payload", review["consume"]["as"])
        routes = review["interaction"]["answer_routes"]
        self.assertEqual("resume_target_node", routes[0]["policy"])
        self.assertEqual("plan_asset_specs", routes[0]["target_node"])
        self.assertTrue(routes[0]["replay_from_target"])
        self.assertEqual("asset_rework_feedback", routes[0]["copy_answer_to"])

    def test_review_answer_route_is_rendered_as_branch_edge(self):
        _, root_flow = self._load()
        graph = FlowGraphBuilder().build({
            "id": "dev.pixel_episode_director_v3",
            "root_flow": root_flow,
        })

        branch_edges = {
            (edge.get("from"), edge.get("to"), edge.get("scope"), edge.get("label"))
            for edge in graph.get("edges") or []
            if edge.get("scope") == "branch"
        }
        self.assertIn(("review_draft_assets", "plan_asset_specs", "branch", "回跳"), branch_edges)

    def test_asset_review_revise_route_replays_asset_lane(self):
        _, root_flow = self._load()
        runner = CartridgeRunner(ROOT, CartridgeRegistry(ROOT))
        review = root_flow["states"]["review_draft_assets"]["decision_contract"]
        resume = {
            "policy": "resume_same_node",
            "answer_routes": review["interaction"]["answer_routes"],
        }
        resolved = runner._resolve_answer_resume(resume, {
            "approval": "revise",
            "feedback": "蓝色衬衫太亮，重新生成深蓝版本。",
        })
        self.assertEqual("resume_target_node", resolved["policy"])
        self.assertEqual("plan_asset_specs", resolved["target_node"])
        self.assertTrue(resolved["replay_from_target"])

        replay = runner._resume_replay_exclusions(root_flow, resolved, resolved["target_node"])
        self.assertIn("plan_asset_specs", replay)
        self.assertIn("forge_draft_assets", replay)
        self.assertIn("review_draft_assets", replay)
        self.assertIn("assemble_creation_packet", replay)

        state_doc = {
            "history": [
                {"state": "plan_story_beats", "status": "completed"},
                {"state": "plan_camera_language", "status": "completed"},
                {"state": "plan_asset_specs", "status": "completed"},
                {"state": "forge_draft_assets", "status": "completed"},
                {"state": "review_draft_assets", "status": "paused_waiting_user"},
            ]
        }
        visited = runner._completed_visited_from_history(
            state_doc,
            include_paused_node=True,
            exclude_states=replay,
        )
        self.assertIn("plan_story_beats", visited)
        self.assertIn("plan_camera_language", visited)
        self.assertNotIn("plan_asset_specs", visited)
        self.assertNotIn("forge_draft_assets", visited)
        self.assertNotIn("review_draft_assets", visited)

    def test_live_collaboration_forces_first_pass_user_confirmation(self):
        _, root_flow = self._load()
        node = root_flow["states"]["plan_asset_specs"]
        state_doc = {"context": {"store": {"planning_context": {"episode_brief": {"asset_requests": "蓝色衬衫人物"}}}}}
        run = {
            "run_id": "run_test_live_collaboration",
            "cartridge_id": "dev.pixel_episode_director_v3",
            "test_mode": {"decision": "live_collaboration"},
            "inputs": {},
        }
        with patch("core.llm.config_manager.resolve_model", return_value=SimpleNamespace(api_key="", provider_id="", model="offline")):
            result = LabNodeExecutor(ROOT).execute("plan_asset_specs", node, state_doc, run, ".")

        self.assertEqual("live_collaboration", result["decision_test_mode"])
        self.assertEqual("needs_user_input", result["decision_status"])
        self.assertTrue(result["paused"])
        self.assertEqual("asset_specs_reply", result["pending_interaction"]["question"]["store_key"])
        self.assertNotIn("asset_specs_payload", state_doc["context"]["store"])

    def test_live_collaboration_allows_resolved_after_user_reply(self):
        _, root_flow = self._load()
        node = root_flow["states"]["plan_asset_specs"]
        state_doc = {
            "context": {
                "store": {
                    "planning_context": {"episode_brief": {"asset_requests": "蓝色衬衫人物"}},
                    "asset_specs_reply": {"review": "approve"},
                }
            }
        }
        run = {
            "run_id": "run_test_live_collaboration_answered",
            "cartridge_id": "dev.pixel_episode_director_v3",
            "test_mode": {"decision": "live_collaboration"},
            "inputs": {},
        }
        with patch("core.llm.config_manager.resolve_model", return_value=SimpleNamespace(api_key="", provider_id="", model="offline")):
            result = LabNodeExecutor(ROOT).execute("plan_asset_specs", node, state_doc, run, ".")

        self.assertEqual("resolved", result["decision_status"])
        self.assertIn("asset_specs_payload", state_doc["context"]["store"])

    def test_shot_plan_tool_consumes_story_and_camera_direction(self):
        registry = BuiltinMcpRegistry(ROOT)
        result = registry.call("media", "generate_pixel_shot_plan", {
            "episode_id": "ep_v3_contract",
            "episode_goal": "主角在夜市小巷发现异常闪灯，结尾留下追踪者线索。",
            "style_notes": "低机位、轻微视差、像素霓虹。",
            "shot_count": "4",
            "output_path": "test_output/pixel_episode_v3/conformance_shot_plan.json",
            "world_state_path": "cartridges/dev/dev.pixel_episode_director_v3/assets/world_state.json",
            "shot_presets_path": "cartridges/dev/dev.pixel_episode_director_v3/assets/shot_presets.json",
            "story_beats": {
                "schema": "story_beats.v1",
                "approved_by_user": True,
                "beats": [
                    {"id": "beat_01", "summary": "建立异常闪灯。", "intent": "establish"},
                    {"id": "beat_02", "summary": "主角靠近线索。", "intent": "investigate"},
                ],
            },
            "camera_plan": {
                "schema": "camera_plan.v1",
                "approved_by_user": True,
                "shots": [
                    {"shot_index": 1, "camera_type": "wide_establishing", "note": "建立空间。"},
                    {"shot_index": 2, "camera_type": "tracking_side", "note": "跟拍靠近。"},
                    {"shot_index": 3, "camera_type": "close_up", "note": "线索特写。"},
                    {"shot_index": 4, "camera_type": "reveal", "note": "揭示钩子。"},
                ],
            },
        })
        self.assertTrue(result["ok"], result)
        plan = json.loads(result["content"])
        self.assertIn("story_direction", plan)
        self.assertIn("camera_direction", plan)
        self.assertEqual("建立异常闪灯。", plan["shots"][0]["story_beat"]["summary"])
        self.assertEqual(["wide_establishing", "tracking_side", "close_up", "reveal"], [
            shot["camera"]["type"] for shot in plan["shots"]
        ])


if __name__ == "__main__":
    unittest.main()
