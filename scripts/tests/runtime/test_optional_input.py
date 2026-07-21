import unittest

from core.lab.node_executor import LabNodeExecutor


class OptionalInputConformanceTest(unittest.TestCase):
    def test_optional_input_is_structured_info(self):
        state_doc = {"context": {"store": {}}}
        run = {"inputs": {}, "mcp_tools": []}
        state = {
            "action": "llm_prompt",
            "params": {
                "input": "required_key",
                "optional_input": "optional_key",
                "output": "out",
                "prompt": "test",
            },
        }
        result = LabNodeExecutor().execute("node_a", state, state_doc, run, ".")
        missing = result.get("missing_inputs") or []
        by_key = {item["key"]: item for item in missing}

        self.assertTrue(by_key["required_key"]["required"])
        self.assertEqual(by_key["required_key"]["severity"], "error")
        self.assertFalse(by_key["optional_key"]["required"])
        self.assertEqual(by_key["optional_key"]["severity"], "info")
        self.assertEqual(by_key["optional_key"]["source"], "optional_input")


if __name__ == "__main__":
    unittest.main()
