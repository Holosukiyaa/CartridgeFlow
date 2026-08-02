import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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

    def test_missing_input_tracking_is_isolated_between_concurrent_nodes(self):
        executor = LabNodeExecutor()
        barrier = Barrier(2)

        def custom_action(params, _store, _run, _run_dir):
            barrier.wait(timeout=2)
            executor._record_missing(params["input"])
            return {"action": "custom_action"}

        executor._custom_action = custom_action

        def execute(key, optional):
            state = {
                "action": "custom_action",
                "params": {"input": key, "optional_input": key if optional else ""},
            }
            return executor.execute(key, state, {"context": {"store": {}}}, {"inputs": {}}, ".")

        with ThreadPoolExecutor(max_workers=2) as pool:
            optional_result = pool.submit(execute, "optional_key", True)
            required_result = pool.submit(execute, "required_key", False)
            optional_missing = optional_result.result(timeout=3)["missing_inputs"]
            required_missing = required_result.result(timeout=3)["missing_inputs"]

        self.assertEqual(["optional_key"], [item["key"] for item in optional_missing])
        self.assertFalse(optional_missing[0]["required"])
        self.assertEqual(["required_key"], [item["key"] for item in required_missing])
        self.assertTrue(required_missing[0]["required"])


if __name__ == "__main__":
    unittest.main()
