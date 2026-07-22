import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.cartridge.runner import CartridgeRunner
from core.lab.node_executor import LabNodeExecutor
from core.llm.config import ModelConfig
from core.runtime.errors import ERROR_CATALOG, ERROR_SCHEMA, RuntimeFailure, build_runtime_error, error_from_node_result, write_diagnostic


REQUIRED_FIELDS = {
    "code", "category", "message", "run_id", "node_id", "source", "missing_inputs",
    "retryable", "recoverable", "recovery_actions", "cause_chain",
}


class _Registry:
    def __init__(self, cartridge):
        self.cartridge = cartridge

    def get_cartridge(self, cartridge_id):
        if cartridge_id != self.cartridge["id"]:
            raise FileNotFoundError(cartridge_id)
        return self.cartridge


class RuntimeErrorEnvelopeTests(unittest.TestCase):
    def test_catalog_covers_required_failure_classes(self):
        required_codes = {
            "INPUT_REQUIRED", "DECISION_ENVELOPE_INVALID", "DECISION_CONSUME_FAILED",
            "PROVIDER_CONFIGURATION_MISSING", "PROVIDER_AUTH_FAILED", "PROVIDER_RATE_LIMITED",
            "PROVIDER_TIMEOUT", "PROVIDER_UNAVAILABLE", "TOOL_TIMEOUT", "TOOL_WORKER_CRASHED",
            "PERMISSION_DENIED", "ARTIFACT_MISSING", "DEPENDENCY_UNAVAILABLE", "INTERNAL_UNEXPECTED",
        }
        self.assertTrue(required_codes <= set(ERROR_CATALOG))

    def test_public_envelope_is_complete_and_redacts_secret_causes(self):
        error = build_runtime_error(
            "PROVIDER_AUTH_FAILED",
            run_id="run_test",
            node_id="writer",
            source="runtime.node.llm_prompt",
            cause_chain=[{"type": "LLMError", "message": "api_key=super-secret"}],
        )

        self.assertEqual(ERROR_SCHEMA, error["schema"])
        self.assertTrue(REQUIRED_FIELDS <= set(error))
        self.assertNotIn("super-secret", json.dumps(error))
        self.assertEqual(["update_credentials", "switch_provider"], error["recovery_actions"])

    def test_full_traceback_is_local_diagnostic_not_public_envelope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                raise RuntimeError("developer-only trace")
            except RuntimeError as exc:
                error = build_runtime_error(exception=exc, run_id="run_test", source="runtime.node")
                target = write_diagnostic(temp_dir, error, exc)

            diagnostic = json.loads(target.read_text(encoding="utf-8"))
            self.assertIn("developer-only trace", diagnostic["traceback"])
            self.assertNotIn("traceback", error)

    def test_missing_required_input_fails_with_stable_code(self):
        executor = LabNodeExecutor()
        state = {"action": "llm_prompt", "params": {"input": "brief", "output": "result", "prompt": "test"}}
        config = ModelConfig(provider_id="local", model="offline", api_key="")
        with patch("core.llm.config_manager.resolve_model", return_value=config):
            result = executor.execute("writer", state, {"context": {"store": {}}}, {"inputs": {}}, ".")

        self.assertTrue(result["failed"])
        self.assertEqual("INPUT_REQUIRED", result["error_code"])
        envelope = error_from_node_result(result, run_id="run_test", node_id="writer")
        self.assertEqual("INPUT_REQUIRED", envelope["code"])
        self.assertEqual(["brief"], envelope["missing_inputs"])

    def test_missing_provider_configuration_is_not_normal_success(self):
        executor = LabNodeExecutor()
        state = {"action": "llm_prompt", "params": {"output": "result", "prompt": "test"}}
        config = ModelConfig(provider_id="local", model="offline", api_key="")
        with patch("core.llm.config_manager.resolve_model", return_value=config):
            result = executor.execute("writer", state, {"context": {"store": {}}}, {"inputs": {}}, ".")

        self.assertTrue(result["failed"])
        self.assertTrue(result["degraded"])
        self.assertEqual("PROVIDER_CONFIGURATION_MISSING", result["error_code"])

    def test_tool_worker_failures_have_distinct_stable_codes(self):
        timeout = error_from_node_result({
            "action": "tool_call",
            "failed": True,
            "tool_results": [{"result": {"ok": False, "code": "dlc_worker_timeout", "error": "timeout"}}],
        }, run_id="run_test", node_id="render")
        crashed = error_from_node_result({
            "action": "tool_call",
            "failed": True,
            "tool_results": [{"result": {"ok": False, "code": "dlc_worker_failed", "error": "exit 1"}}],
        }, run_id="run_test", node_id="render")
        cancelled = error_from_node_result({
            "action": "tool_call",
            "failed": True,
            "tool_results": [{"result": {"ok": False, "code": "tool_cancelled", "error": "cancelled"}}],
        }, run_id="run_test", node_id="render")

        self.assertEqual("TOOL_TIMEOUT", timeout["code"])
        self.assertEqual("TOOL_WORKER_CRASHED", crashed["code"])
        self.assertEqual("TOOL_CANCELLED", cancelled["code"])

    def test_run_snapshot_and_events_share_one_error_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "package"
            package.mkdir()
            cartridge = {
                "id": "test.failure",
                "package_path": str(package),
                "manifest": {"id": "test.failure", "version": "1.0.0", "inputs": [], "runtime": {"type": "none"}},
                "root_flow": {
                    "id": "failure.root",
                    "start": "decide",
                    "states": {
                        "decide": {
                            "type": "process",
                            "kind": "decision",
                            "executor": "llm",
                            "effect": "none",
                            "output": "decision",
                            "output_contract": "decision_envelope.v1",
                            "decision_contract": {"schema": "decision_envelope.v1", "allowed_statuses": ["blocked"]},
                            "next": "complete",
                        },
                        "complete": {"type": "terminal"},
                    },
                },
            }
            runner = CartridgeRunner(root, _Registry(cartridge))
            runner.build_compatibility_report = lambda *args, **kwargs: {
                "ok": True, "status": "compatible", "legacy": False, "base": {}, "protocol": {}, "summary": {}, "findings": [],
            }
            run = runner.create_run("test.failure", test_mode={"decision": "mock_blocked"})
            failed_event = next(item for item in runner.get_events(run["run_id"]) if item["type"] == "lab_node_failed")
            final_event = next(item for item in runner.get_events(run["run_id"]) if item["type"] == "run_failed")

            self.assertEqual("failed", run["status"])
            self.assertEqual(run["error"]["error_id"], failed_event["data"]["error_envelope"]["error_id"])
            self.assertEqual(run["error"]["error_id"], final_event["data"]["error_envelope"]["error_id"])

    def test_http_error_handler_preserves_structured_error_identity(self):
        from fastapi.testclient import TestClient
        from starlette.requests import Request
        from backend.main import app, runtime_failure_handler

        response = TestClient(app).get("/api/cartridge-runs/run_does_not_exist")
        payload = response.json()

        self.assertEqual(404, response.status_code)
        self.assertEqual("RESOURCE_NOT_FOUND", payload["error_envelope"]["code"])
        self.assertEqual("run_does_not_exist", payload["error_envelope"]["run_id"])
        self.assertTrue(payload["error_envelope"]["error_id"].startswith("err_"))

        original = build_runtime_error("TOOL_TIMEOUT", run_id="run_same", node_id="render")
        request = Request({"type": "http", "method": "POST", "path": "/api/cartridge-runs/run_same/control", "headers": [], "query_string": b"", "server": ("test", 80), "client": ("test", 1), "scheme": "http"})
        handler_response = asyncio.run(runtime_failure_handler(request, RuntimeFailure(original)))
        handler_payload = json.loads(handler_response.body)
        self.assertEqual(original["error_id"], handler_payload["error_envelope"]["error_id"])
        self.assertEqual(original["code"], handler_payload["error_envelope"]["code"])

    def test_diagnostic_bundle_aggregates_run_evidence_and_redacts_secrets(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        class DiagnosticRunner:
            def get_run(self, run_id):
                return {
                    "run_id": run_id,
                    "cartridge_id": "test.diagnostic",
                    "status": "failed",
                    "current_state": "writer",
                    "inputs": {"api_key": "must-not-leak", "topic": "safe"},
                    "error": build_runtime_error("PROVIDER_AUTH_FAILED", run_id=run_id, node_id="writer"),
                    "artifacts": [],
                }

            def get_events(self, run_id):
                return [{"type": "run_failed", "message": "Authorization: Bearer secret-value", "created_at": "2026-01-01T00:00:00"}]

            def list_checkpoints(self, run_id):
                return [{"checkpoint_id": "cp_1", "node_id": "writer", "phase": "before", "outcome": "entered"}]

        with patch("backend.main.runner", DiagnosticRunner()):
            response = TestClient(app).get("/api/cartridge-runs/run_ai/diagnostics")
        payload = response.json()
        serialized = json.dumps(payload)

        self.assertEqual(200, response.status_code)
        self.assertEqual("cartridgeflow.diagnostic_bundle.v1", payload["schema"])
        self.assertEqual("PROVIDER_AUTH_FAILED", payload["summary"]["error_code"])
        self.assertEqual(1, payload["summary"]["event_count"])
        self.assertEqual(1, payload["summary"]["checkpoint_count"])
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("secret-value", serialized)


if __name__ == "__main__":
    unittest.main()
