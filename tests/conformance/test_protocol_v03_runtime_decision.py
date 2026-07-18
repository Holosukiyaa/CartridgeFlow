import unittest

from core.lab.node_executor import LabNodeExecutor
from core.protocol import parse_decision_envelope, validate_decision_envelope


def decision_state(mock_envelope):
    return {
        "type": "process",
        "kind": "decision",
        "executor": "llm",
        "effect": "none",
        "input": "context_pack",
        "output": "decision",
        "output_contract": "decision_envelope.v1",
        "decision_test_mode": "mock",
        "decision_contract": {
            "schema": "decision_envelope.v1",
            "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
            "on_needs_user_input": "pause",
            "interaction": {
                "store_key": "decision_user_reply",
                "input_schema": "decision_reply.v1",
                "resume_policy": "resume_same_node",
            },
        },
        "mock_decision_envelope": mock_envelope,
    }


class ProtocolV03RuntimeDecisionTest(unittest.TestCase):
    def test_v03_mock_decision_writes_structured_envelope(self):
        state_doc = {"context": {"store": {"context_pack": {"goal": "build short drama"}}}}
        run = {"inputs": {}, "run_id": "run_test", "cartridge_id": "test.v03"}
        envelope = {
            "schema": "decision_envelope.v1",
            "status": "resolved",
            "summary": "Ready.",
            "payload": {"decision": {"shot_count": 4}},
        }
        result = LabNodeExecutor().execute("decide", decision_state(envelope), state_doc, run, ".")

        self.assertEqual("llm_prompt", result["action"])
        self.assertEqual("decision_envelope.v1", result["output_contract"])
        self.assertEqual("resolved", result["decision_status"])
        self.assertEqual(envelope, state_doc["context"]["store"]["decision"])

    def test_v03_needs_user_input_returns_pause_signal(self):
        state_doc = {"context": {"store": {"context_pack": {"goal": "build short drama"}}}}
        run = {"inputs": {}, "run_id": "run_test", "cartridge_id": "test.v03"}
        envelope = {
            "schema": "decision_envelope.v1",
            "status": "needs_user_input",
            "summary": "Need hero style.",
            "question": {
                "id": "ask_hero_style",
                "prompt": "主角是什么风格？",
                "input_schema": {"type": "object", "required": ["hero_style"]},
                "store_key": "hero_style_reply",
            },
            "resume": {"policy": "resume_same_node"},
        }
        result = LabNodeExecutor().execute("decide", decision_state(envelope), state_doc, run, ".")

        self.assertTrue(result["paused"])
        self.assertEqual("paused_waiting_user", result["pause_status"])
        pending = result["pending_interaction"]
        self.assertEqual("pending_interaction.v1", pending["schema"])
        self.assertEqual("hero_style_reply", pending["question"]["store_key"])
        self.assertEqual(pending, state_doc["context"]["store"]["_pending_interaction"])

    def test_v03_run_level_interaction_mock_requests_user_input(self):
        state_doc = {"context": {"store": {"context_pack": {"goal": "build short drama"}}}}
        run = {
            "inputs": {},
            "run_id": "run_test",
            "cartridge_id": "test.v03",
            "test_mode": {"decision": "mock_interaction"},
        }
        result = LabNodeExecutor().execute("decide", decision_state({
            "schema": "decision_envelope.v1",
            "status": "resolved",
            "summary": "Node mock would resolve.",
            "payload": {"decision": {"ignored_by_run_mode": True}},
        }), state_doc, run, ".")

        self.assertTrue(result["paused"])
        self.assertEqual("mock_interaction", result["decision_test_mode"])
        self.assertEqual("needs_user_input", result["decision_status"])
        self.assertEqual("decision_user_reply", result["pending_interaction"]["question"]["store_key"])

    def test_v03_run_level_blocked_mock_fails_decision(self):
        state_doc = {"context": {"store": {"context_pack": {"goal": "build short drama"}}}}
        run = {
            "inputs": {},
            "run_id": "run_test",
            "cartridge_id": "test.v03",
            "test_mode": {"decision": "mock_blocked"},
        }
        result = LabNodeExecutor().execute("decide", decision_state({
            "schema": "decision_envelope.v1",
            "status": "resolved",
            "summary": "Node mock would resolve.",
            "payload": {"decision": {"ignored_by_run_mode": True}},
        }), state_doc, run, ".")

        self.assertTrue(result["failed"])
        self.assertEqual("mock_blocked", result["decision_test_mode"])
        self.assertEqual("blocked", result["decision_status"])

    def test_v03_invalid_decision_output_blocks(self):
        state_doc = {"context": {"store": {"context_pack": {"goal": "build short drama"}}}}
        run = {"inputs": {}, "run_id": "run_test", "cartridge_id": "test.v03"}
        result = LabNodeExecutor().execute("decide", decision_state({"status": "resolved"}), state_doc, run, ".")

        self.assertTrue(result["failed"])
        self.assertEqual("blocked", result["decision_status"])
        self.assertEqual("decision_envelope.v1", state_doc["context"]["store"]["decision"]["schema"])

    def test_v03_live_decision_unwraps_common_outer_key(self):
        raw = """
        {
          "decision_envelope": {
            "status": "resolved",
            "payload": {
              "decision": "入料完整，可以进入工程链路。"
            }
          }
        }
        """
        envelope = LabNodeExecutor()._decision_envelope_from_result(
            raw,
            {"schema": "decision_envelope.v1", "allowed_statuses": ["resolved", "needs_user_input", "blocked"]},
            "",
        )

        self.assertEqual("decision_envelope.v1", envelope["schema"])
        self.assertEqual("resolved", envelope["status"])
        self.assertEqual("入料完整，可以进入工程链路。", envelope["summary"])

    def test_v03_parse_decision_envelope_accepts_smart_quotes(self):
        raw = """
        {
          "schema": "decision_envelope.v1",
          "status": "needs_user_input",
          "summary": "AI 决策：生成 3D 动画预演规格”,
          "question": {
            "id": "ask_scene_shape",
            "prompt": "是否按前景 / 中景 / 背景分层？",
            "input_schema": {"type": "object"},
            "store_key": "scene_shape_reply"
          },
          "resume": {"policy": "resume_same_node"}
        }
        """
        envelope = parse_decision_envelope(raw)

        self.assertIsInstance(envelope, dict)
        self.assertEqual("decision_envelope.v1", envelope["schema"])
        self.assertEqual("needs_user_input", envelope["status"])
        self.assertEqual("AI 决策：生成 3D 动画预演规格", envelope["summary"])

    def test_v03_live_needs_user_input_hoists_payload_question_and_uses_contract(self):
        raw = """
        {
          "schema": "decision_envelope.v1",
          "status": "needs_user_input",
          "summary": "Please review the proposed direction.",
          "payload": {
            "question": {
              "prompt": "Approve this plan?",
              "input_schema": {"type": "string"},
              "store_key": "model_chosen_key",
              "resume": {"policy": "resume_on_input"}
            }
          }
        }
        """
        state = decision_state({"status": "resolved"})
        contract = state["decision_contract"]
        executor = LabNodeExecutor()
        envelope = executor._decision_envelope_from_result(raw, contract, "")
        envelope = executor._apply_contract_interaction(envelope, contract, state, "decision")
        blockers = [item for item in validate_decision_envelope(envelope, contract) if item.get("severity") == "blocker"]

        self.assertEqual("needs_user_input", envelope["status"])
        self.assertEqual("Approve this plan?", envelope["question"]["prompt"])
        self.assertEqual("decision_user_reply", envelope["question"]["store_key"])
        self.assertEqual("decision_reply.v1", envelope["question"]["input_schema"])
        self.assertEqual("resume_same_node", envelope["resume"]["policy"])
        self.assertEqual([], blockers)

    def test_v03_run_level_resolved_mock_uses_offline_decision_sample(self):
        state_doc = {"context": {"store": {"context_pack": {"goal": "build short drama"}}}}
        run = {
            "inputs": {},
            "run_id": "run_test",
            "cartridge_id": "test.v03",
            "test_mode": {"decision": "mock_resolved"},
        }
        state = decision_state({
            "schema": "decision_envelope.v1",
            "status": "needs_user_input",
            "summary": "Node mock would ask.",
            "question": {
                "id": "ask",
                "prompt": "Need info.",
                "input_schema": {"type": "object"},
                "store_key": "reply",
            },
            "resume": {"policy": "resume_same_node"},
        })
        state["decision_contract"]["offline_decision"] = {
            "schema": "decision_envelope.v1",
            "status": "resolved",
            "summary": "离线样例：入料足够。",
            "payload": {"decision": {"approved": True}},
        }
        result = LabNodeExecutor().execute("decide", state, state_doc, run, ".")

        self.assertEqual("resolved", result["decision_status"])
        self.assertEqual("离线样例：入料足够。", state_doc["context"]["store"]["decision"]["summary"])


if __name__ == "__main__":
    unittest.main()
