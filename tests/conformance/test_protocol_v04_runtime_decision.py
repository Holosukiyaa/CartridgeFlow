import unittest

from core.lab.node_executor import LabNodeExecutor


def decision_state(mock_envelope, consume=None):
    contract = {
        "schema": "decision_envelope.v1",
        "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
        "on_needs_user_input": "pause",
        "interaction": {
            "store_key": "decision_user_reply",
            "input_schema": "decision_reply.v1",
            "resume_policy": "resume_same_node",
        },
    }
    if consume is not None:
        contract["consume"] = consume
    return {
        "type": "process",
        "kind": "decision",
        "executor": "llm",
        "effect": "none",
        "input": "context_pack",
        "output": "decision",
        "output_contract": "decision_envelope.v1",
        "decision_test_mode": "mock",
        "decision_contract": contract,
        "mock_decision_envelope": mock_envelope,
    }


class ProtocolV04RuntimeDecisionTest(unittest.TestCase):
    def test_v04_resolved_decision_projects_explicit_consume_value(self):
        state_doc = {"context": {"store": {"context_pack": {"goal": "build short drama"}}}}
        run = {"inputs": {}, "run_id": "run_test", "cartridge_id": "test.v04"}
        envelope = {
            "schema": "decision_envelope.v1",
            "status": "resolved",
            "summary": "Ready.",
            "payload": {"decision": {"shot_count": 4}},
        }
        consume = {
            "mode": "payload_path",
            "path": "payload.decision",
            "as": "decision_payload",
            "required": True,
            "on_missing": "fail_closed",
        }
        result = LabNodeExecutor().execute("decide", decision_state(envelope, consume), state_doc, run, ".")

        self.assertEqual(envelope, state_doc["context"]["store"]["decision"])
        self.assertEqual({"shot_count": 4}, state_doc["context"]["store"]["decision_payload"])
        self.assertEqual("projected", result["decision_consume"]["status"])
        self.assertEqual("decision_payload", result["decision_consume_output"])

    def test_v04_needs_user_input_does_not_project_consume_value(self):
        state_doc = {"context": {"store": {"context_pack": {"goal": "build short drama"}}}}
        run = {"inputs": {}, "run_id": "run_test", "cartridge_id": "test.v04"}
        envelope = {
            "schema": "decision_envelope.v1",
            "status": "needs_user_input",
            "summary": "Need answer.",
            "question": {
                "id": "ask",
                "prompt": "Need info.",
                "input_schema": {"type": "object"},
                "store_key": "reply",
            },
            "resume": {"policy": "resume_same_node"},
        }
        consume = {"mode": "payload_path", "path": "payload.decision", "as": "decision_payload"}
        result = LabNodeExecutor().execute("decide", decision_state(envelope, consume), state_doc, run, ".")

        self.assertTrue(result["paused"])
        self.assertNotIn("decision_payload", state_doc["context"]["store"])
        self.assertEqual("skipped", result["decision_consume"]["status"])

    def test_v04_missing_consume_path_fails_closed(self):
        state_doc = {"context": {"store": {"context_pack": {"goal": "build short drama"}}}}
        run = {"inputs": {}, "run_id": "run_test", "cartridge_id": "test.v04"}
        envelope = {
            "schema": "decision_envelope.v1",
            "status": "resolved",
            "summary": "Ready.",
            "payload": {"note": "missing decision"},
        }
        consume = {"mode": "payload_path", "path": "payload.decision", "as": "decision_payload"}
        result = LabNodeExecutor().execute("decide", decision_state(envelope, consume), state_doc, run, ".")

        self.assertTrue(result["failed"])
        self.assertNotIn("decision_payload", state_doc["context"]["store"])
        self.assertEqual("failed", result["decision_consume"]["status"])


if __name__ == "__main__":
    unittest.main()
