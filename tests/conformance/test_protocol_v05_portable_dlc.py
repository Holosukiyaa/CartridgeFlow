import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.cartridge.registry import CartridgeRegistry
from core.cartridge.runner import CartridgeRunner
from core.extensions import load_portable_dlc_descriptor
from core.lab.builtin_mcp import BuiltinMcpRegistry
from core.lab.node_executor import LabNodeExecutor
from core.llm.config import ModelConfig
from core.protocol import ProtocolRegistry, load_base_implementation


ROOT = Path(__file__).resolve().parents[2]
CARTRIDGE_ID = "dev.series_3d_episode_factory"


class ProtocolV05PortableDlcTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = CartridgeRegistry(ROOT)
        cls.cartridge = cls.registry.get_cartridge(CARTRIDGE_ID)

    def test_v05_is_standalone_and_registered(self):
        protocol = json.loads((ROOT / "protocol" / "CF-FARP-0.5.json").read_text(encoding="utf-8"))
        self.assertTrue(protocol["standalone"])
        self.assertTrue(ProtocolRegistry(ROOT).supports_protocol("CF-FARP", "0.5"))
        text = (ROOT / protocol["document"]).read_text(encoding="utf-8")
        self.assertNotIn("CF-FARP@0.4", text)
        self.assertNotIn("CF-CRCP", text)
        self.assertIn("Portable DLC", text)

    def test_base_claims_portable_dlc_runtime(self):
        base = load_base_implementation(ROOT)
        self.assertIn("portable_dlc_runtime", base["profiles"])
        required = {
            "portable_dlc_descriptor",
            "cartridge_scoped_tool_registry",
            "isolated_dlc_worker",
            "frontend_dlc_sandbox",
            "dlc_uninstall_cleanup",
        }
        self.assertTrue(required <= set(base["capabilities"]))

    def test_cartridge_descriptor_is_valid_and_core_stays_clean(self):
        descriptor = load_portable_dlc_descriptor(self.cartridge["package_path"], self.cartridge["manifest"])
        self.assertEqual(CARTRIDGE_ID, descriptor["owner_cartridge"])
        self.assertNotIn("build_storyboard_project", BuiltinMcpRegistry(ROOT).list_tools()["media"])
        scoped = BuiltinMcpRegistry.for_manifest(
            ROOT,
            self.cartridge["manifest"],
            package_path=self.cartridge["package_path"],
        )
        self.assertIn("build_storyboard_project", scoped.list_tools()["media"])

    def test_storyboard_flow_closes_in_mock_mode(self):
        runner = CartridgeRunner(ROOT, self.registry)
        report = runner.build_cartridge_compatibility_report(CARTRIDGE_ID)
        self.assertTrue(report["ok"], report["findings"])
        run = runner.create_run(
            CARTRIDGE_ID,
            {"episode_brief": "A boy hears a second footstep on an empty street."},
            test_mode={"decision": "mock_resolved", "tool": "dry_run"},
        )
        self.assertEqual("completed", run["status"])
        self.assertEqual("complete", run["current_state"])
        self.assertTrue(run["data_chain"]["passed"])
        names = {item["name"] for item in run["artifacts"]}
        self.assertIn("video_shot_package.json", names)
        self.assertIn("shot_01.png", names)

    def test_human_gate_requires_submit_before_resume(self):
        executor = LabNodeExecutor(ROOT)
        node = {"type": "process", "kind": "human_gate", "executor": "human", "effect": "none", "action": "confirm_checkpoint", "params": {"output": "review", "interaction": {"store_key": "reply", "ui_extension": "portable_dlc", "input_schema": {"type": "object"}}}}
        state_doc = {"context": {"store": {}}}
        run = {"run_id": "test", "test_mode": {"decision": "live_collaboration"}}
        paused = executor.execute("director", node, state_doc, run, ROOT)
        self.assertTrue(paused["paused"])
        self.assertEqual("portable_dlc", paused["pending_interaction"]["ui_extension"])
        state_doc["context"]["store"]["reply"] = {"approval": "approve_all"}
        resumed = executor.execute("director", node, state_doc, run, ROOT)
        self.assertTrue(resumed["approved"])

    def test_top_level_abort_on_failed_stops_before_downstream_nodes(self):
        runner = CartridgeRunner(ROOT, self.registry)
        run = runner.create_run(
            CARTRIDGE_ID,
            {"episode_brief": "Abort this decision."},
            test_mode={"decision": "mock_blocked"},
        )
        self.assertEqual("failed", run["status"])
        events = runner.get_events(run["run_id"])
        entered = [event["state"] for event in events if event["type"] == "state_entered"]
        self.assertIn("write_script", entered)
        self.assertNotIn("plan_shots", entered)
        failed = [event for event in events if event["type"] == "lab_node_failed"]
        self.assertEqual("write_script", failed[-1]["state"])

    def test_approved_storyboard_draft_resumes_without_a_second_shot_generation(self):
        script_question = {
            "schema": "decision_envelope.v1",
            "status": "needs_user_input",
            "summary": "Confirm the story proposal.",
            "payload": {},
            "question": {"prompt": "Approve?", "input_schema": {"type": "object"}, "store_key": "script_reply"},
            "resume": {"policy": "resume_same_node"},
        }
        script_resolved = {
            "schema": "decision_envelope.v1",
            "status": "resolved",
            "summary": "Story ready.",
            "payload": {"episode_script": {"episode_id": "approval-regression", "title": "Exact draft"}},
        }
        approved_draft = {
            "schema": "shot_list.v1",
            "shots": [{
                "id": "exact-approved-shot",
                "title": "Approved composition",
                "description": "The exact proposal the user approved.",
                "scene_design": {"location": "city park", "landmarks": ["bench"]},
                "camera": {"template": "slow_push_in", "position": [0, -8, 2], "target": [0, 0, 1], "focal_length_mm": 42},
                "actor_blocking": [{"actor_id": "hero", "position": [0, 1, 0], "action": "idle_hold", "pose_time": 0.4}],
                "characters": ["hero"],
                "action_tags": ["idle_hold"],
                "duration": 3,
            }],
        }
        shot_question = {
            "schema": "decision_envelope.v1",
            "status": "needs_user_input",
            "summary": "Confirm the storyboard proposal.",
            "payload": {"draft_shot_list": approved_draft},
            "question": {"prompt": "Approve shots?", "input_schema": {"type": "object"}, "store_key": "shot_reply"},
            "resume": {"policy": "resume_next_node"},
        }
        responses = [
            {"content": json.dumps(script_question), "meta": {"finish_reason": "stop"}},
            {"content": json.dumps(script_resolved), "meta": {"finish_reason": "stop"}},
            {"content": json.dumps(shot_question), "meta": {"finish_reason": "stop"}},
        ]
        chat_mock = AsyncMock(side_effect=responses)
        config = ModelConfig(provider_id="test", model="test-model", api_key="test-key")
        runner = CartridgeRunner(ROOT, self.registry)
        with patch("core.llm.config_manager.resolve_model", return_value=config), patch("core.llm.chat", new=chat_mock):
            run = runner.create_run(CARTRIDGE_ID, {"episode_brief": "A park scene."}, test_mode={"decision": "live_collaboration"})
            self.assertEqual("write_script", run["current_state"])
            run = runner.answer_pending_interaction(run["run_id"], {"approval": "approve"})
            self.assertEqual("plan_shots", run["current_state"])
            run = runner.answer_pending_interaction(run["run_id"], {"approval": "approve"})

        self.assertEqual(3, chat_mock.await_count)
        self.assertEqual("paused_waiting_user", run["status"])
        self.assertEqual("review_storyboard", run["current_state"])
        state = runner._read_json(runner.runs_dir / run["run_id"] / "root_flow_state.json")
        shot_list = json.loads(state["context"]["store"]["shot_list"])
        self.assertEqual("exact-approved-shot", shot_list["shots"][0]["id"])
        self.assertFalse([event for event in runner.get_events(run["run_id"]) if event["type"] == "lab_node_failed"])


if __name__ == "__main__":
    unittest.main()
