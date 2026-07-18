import shutil
import tempfile
import unittest
from pathlib import Path

from core.cartridge.runner import CartridgeRunner
from core.protocol import build_compatibility_report, load_base_implementation


ROOT = Path(__file__).resolve().parents[2]


def v03_manifest():
    return {
        "id": "test.v03.resume",
        "version": "0.0.1",
        "base_contract": {"id": "CF-FARP", "version": "0.3"},
        "runtime_contract": {
            "protocol": "CF-FARP",
            "protocol_version": "0.3",
            "required_profiles": ["runtime_core", "interactive_decision_runtime"],
            "recommended_profiles": [],
            "required_capabilities": [
                "root_flow_execution",
                "unified_process_node",
                "process_node_kind_parse",
                "process_executor_contract",
                "process_effect_contract",
                "decision_process",
                "decision_envelope_v1",
                "decision_envelope_validate",
                "runtime_user_input_request",
                "paused_waiting_user_status",
                "pending_interaction_record",
                "runtime_resume_after_user_input",
            ],
            "optional_capabilities": [],
            "required_tools": [],
            "optional_tools": [],
        },
        "delivery_readiness": {"level": "dev"},
        "branding": {"tags": []},
        "mcp_tools": [],
    }


def v03_flow():
    return {
        "schema_version": "1.0",
        "id": "test.v03.resume.root",
        "protocol": {"id": "CF-FARP", "version": "0.3"},
        "start": "start",
        "states": {
            "start": {"type": "system", "next": "collect"},
            "collect": {
                "type": "process",
                "kind": "input",
                "executor": "user",
                "effect": "writes_store",
                "input_kind": "initial",
                "source": "user_form",
                "input_schema": "brief.v1",
                "output": "brief",
                "next": "decide",
            },
            "decide": {
                "type": "process",
                "kind": "decision",
                "executor": "llm",
                "effect": "none",
                "input": "brief",
                "output": "story_decision",
                "output_contract": "decision_envelope.v1",
                "decision_test_mode": "mock",
                "decision_contract": {
                    "schema": "decision_envelope.v1",
                    "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
                    "on_needs_user_input": "pause",
                    "interaction": {
                        "store_key": "story_reply",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "answer": {"type": "string"},
                            },
                            "required": ["answer"],
                        },
                        "resume_policy": "resume_next_node",
                    },
                },
                "mock_decision_envelope": {
                    "schema": "decision_envelope.v1",
                    "status": "needs_user_input",
                    "summary": "Need a direct answer before delivery.",
                    "question": {
                        "id": "ask_story_answer",
                        "prompt": "What should happen next?",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "answer": {"type": "string"},
                            },
                            "required": ["answer"],
                        },
                        "store_key": "story_reply",
                    },
                    "resume": {"policy": "resume_next_node"},
                },
                "next": "deliver",
            },
            "deliver": {
                "type": "process",
                "kind": "transfer",
                "executor": "deterministic",
                "effect": "writes_store",
                "input": "story_decision",
                "output": "episode_delivery",
                "next": "complete",
            },
            "complete": {"type": "terminal"},
        },
    }


def v03_reroute_flow():
    flow = v03_flow()
    decision = flow["states"]["decide"]
    answer_routes = [
        {
            "match": {"field": "approval", "equals": "revise"},
            "policy": "resume_target_node",
            "target_node": "collect",
            "replay_from_target": True,
            "copy_answer_to": "failure_feedback",
            "clear_store_keys": ["story_reply", "story_decision", "episode_delivery"],
        }
    ]
    decision["decision_contract"]["interaction"] = {
        "store_key": "story_reply",
        "input_schema": {
            "type": "object",
            "properties": {
                "approval": {"type": "string", "enum": ["approve", "revise"]},
                "feedback": {"type": "string"},
            },
            "required": ["approval"],
        },
        "resume_policy": "resume_same_node",
        "answer_routes": answer_routes,
    }
    decision["mock_decision_envelope"]["question"]["input_schema"] = decision["decision_contract"]["interaction"]["input_schema"]
    decision["mock_decision_envelope"]["resume"] = {
        "policy": "resume_same_node",
        "answer_routes": answer_routes,
    }
    return flow


class StubRegistry:
    def __init__(self, cartridge: dict):
        self.cartridge = cartridge

    def get_cartridge(self, cartridge_id: str):
        if cartridge_id != self.cartridge["id"]:
            raise FileNotFoundError(cartridge_id)
        return self.cartridge


class ProtocolV03RuntimeResumeTest(unittest.TestCase):
    def test_pending_interaction_answer_resumes_run(self):
        cartridge = {
            "id": "test.v03.resume",
            "manifest": v03_manifest(),
            "root_flow": v03_flow(),
            "package_path": str(ROOT),
            "editable": False,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            shutil.copy2(ROOT / "BASE_IMPLEMENTATION.json", tmp_root / "BASE_IMPLEMENTATION.json")
            shutil.copytree(ROOT / "protocol", tmp_root / "protocol")

            runner = CartridgeRunner(tmp_root, StubRegistry(cartridge))
            compatibility = build_compatibility_report(load_base_implementation(ROOT), cartridge["manifest"], cartridge["root_flow"], ROOT)
            self.assertTrue(compatibility["ok"], compatibility["findings"])

            run = runner.create_run(cartridge["id"], {"topic": "story"})
            self.assertEqual("paused_waiting_user", run["status"])
            self.assertIn("pending_interaction", run)
            self.assertEqual("resume_next_node", run["pending_interaction"]["resume"]["policy"])

            resumed = runner.answer_pending_interaction(run["run_id"], {"answer": "make the ending hopeful"})
            self.assertEqual("completed", resumed["status"])
            self.assertEqual("complete", resumed["current_state"])
            self.assertEqual("make the ending hopeful", resumed["answered_interactions"][-1]["value"]["answer"])
            state_doc = runner._read_json(tmp_root / ".data" / "cartridge_runs" / run["run_id"] / "root_flow_state.json")
            self.assertEqual("make the ending hopeful", state_doc["context"]["store"]["story_reply"]["answer"])
            self.assertNotIn("pending_interaction", resumed)

            event_types = [event["type"] for event in runner.get_events(run["run_id"])]
            self.assertIn("pending_interaction_answered", event_types)
            self.assertEqual(1, event_types.count("run_completed"))
            traversed = [
                (event["data"].get("from"), event["data"].get("to"))
                for event in runner.get_events(run["run_id"])
                if event["type"] == "flow_edge_traversed"
            ]
            self.assertEqual(
                [("start", "collect"), ("collect", "decide"), ("decide", "deliver"), ("deliver", "complete")],
                traversed,
            )

    def test_reject_route_replays_previous_node_with_feedback(self):
        cartridge = {
            "id": "test.v03.resume",
            "manifest": v03_manifest(),
            "root_flow": v03_reroute_flow(),
            "package_path": str(ROOT),
            "editable": False,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            shutil.copy2(ROOT / "BASE_IMPLEMENTATION.json", tmp_root / "BASE_IMPLEMENTATION.json")
            shutil.copytree(ROOT / "protocol", tmp_root / "protocol")

            runner = CartridgeRunner(tmp_root, StubRegistry(cartridge))
            run = runner.create_run(cartridge["id"], {"topic": "story"})
            self.assertEqual("paused_waiting_user", run["status"])

            answer = {"approval": "revise", "feedback": "The first draft was too slow."}
            resumed = runner.answer_pending_interaction(run["run_id"], answer)
            self.assertEqual("paused_waiting_user", resumed["status"])
            self.assertEqual("decide", resumed["current_state"])

            state_doc = runner._read_json(tmp_root / ".data" / "cartridge_runs" / run["run_id"] / "root_flow_state.json")
            self.assertEqual(answer, state_doc["context"]["store"]["failure_feedback"])
            self.assertEqual(2, [item["state"] for item in state_doc["history"]].count("collect"))
            route_events = [
                event for event in runner.get_events(run["run_id"])
                if event["type"] == "flow_edge_traversed" and event["data"].get("reason") == "resume_route"
            ]
            self.assertEqual(("decide", "collect"), (route_events[-1]["data"]["from"], route_events[-1]["data"]["to"]))


if __name__ == "__main__":
    unittest.main()
