import json
import unittest

from core.lab.ai_steward import build_messages, parse_response


class AIFlowStewardTests(unittest.TestCase):
    def test_build_messages_marks_selected_nodes_and_limits_deep_context(self):
        graph = {
            "nodes": [
                {"id": "a", "title": "开始", "input_binding": {"query": "store:query"}, "output": "request"},
                {"id": "b", "title": "处理", "input_binding": {"request": "store:request"}, "output": "result"},
            ],
            "edges": [{"from": "a", "to": "b"}],
        }
        messages = build_messages(
            "解释这里",
            "guided",
            "engineering",
            "abc123",
            {"node_ids": ["b"], "edge_ids": [], "field_paths": []},
            graph,
        )
        payload = json.loads(messages[1]["content"])
        self.assertFalse(payload["current_graph"]["nodes"][0]["selected"])
        self.assertIsNone(payload["current_graph"]["nodes"][0]["input_binding"])
        self.assertTrue(payload["current_graph"]["nodes"][1]["selected"])
        self.assertEqual(payload["current_graph"]["nodes"][1]["input_binding"], {"request": "store:request"})

    def test_parse_response_preserves_revision_scope_and_requires_medium_risk_confirmation(self):
        response = parse_response(
            """```json
            {"understanding":"调整选区", "answer":"这段流程负责整理输入。", "operations":[{"op":"update_node", "target":"states.b", "description":"补齐输出"}], "risk":"medium", "confirmation_required":false, "next_step":"先检查输出契约"}
            ```""",
            mode="delegated",
            revision="rev-42",
            selection={"node_ids": ["b"], "edge_ids": [], "field_paths": []},
        )
        self.assertEqual(response["selection_revision"], "rev-42")
        self.assertEqual(response["scope"]["node_ids"], ["b"])
        self.assertTrue(response["confirmation_required"])
        self.assertEqual(response["operations"][0]["op"], "update_node")


if __name__ == "__main__":
    unittest.main()
