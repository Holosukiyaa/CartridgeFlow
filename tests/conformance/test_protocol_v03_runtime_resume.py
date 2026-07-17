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
            self.assertGreaterEqual(event_types.count("run_completed"), 2)


if __name__ == "__main__":
    unittest.main()
