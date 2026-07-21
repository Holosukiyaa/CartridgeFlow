import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.cartridge.runner import CartridgeRunner
from core.lab.node_executor import LabNodeExecutor
from core.runtime.checkpoints import CHECKPOINT_SCHEMA, CheckpointManager
from core.runtime.errors import RuntimeFailure
from core.runtime.state_machine import TRANSITIONS, InvalidStateTransition, assert_transition


class _Registry:
    def __init__(self, cartridge):
        self.cartridge = cartridge

    def get_cartridge(self, cartridge_id):
        if cartridge_id != self.cartridge.get("id"):
            raise FileNotFoundError(cartridge_id)
        return self.cartridge


class _SequenceTools:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0
        self.last_params = None

    def call(self, server, tool, params):
        self.calls += 1
        self.last_params = dict(params)
        index = min(self.calls - 1, len(self.results) - 1)
        return dict(self.results[index])


def _runner(root: Path, root_flow: dict, manifest: dict | None = None):
    package = root / "package"
    package.mkdir(exist_ok=True)
    manifest = manifest or {"id": "test.recovery", "version": "1.0.0", "inputs": [], "runtime": {"type": "none"}}
    cartridge = {
        "id": manifest["id"],
        "package_path": str(package),
        "manifest": manifest,
        "root_flow": root_flow,
    }
    runner = CartridgeRunner(root, _Registry(cartridge))
    runner.build_compatibility_report = lambda *args, **kwargs: {
        "ok": True, "status": "compatible", "legacy": False, "base": {}, "protocol": {}, "summary": {}, "findings": [],
    }
    return runner


class RuntimeRecoveryTests(unittest.TestCase):
    def _safe_flow(self):
        return {
            "id": "checkpoint.root",
            "start": "collect",
            "states": {
                "collect": {"type": "process", "kind": "input", "executor": "user", "effect": "writes_store", "input_schema": {"fields": ["source"]}, "output": "brief", "next": "transfer"},
                "transfer": {"type": "process", "kind": "transfer", "executor": "deterministic", "effect": "writes_store", "input": "brief", "output": "result", "next": "deliver"},
                "deliver": {"type": "process", "kind": "delivery", "executor": "deterministic", "effect": "writes_store", "input": "result", "output": "final", "primary_output": "final", "next": "complete"},
                "complete": {"type": "terminal"},
            },
        }

    def _safe_manifest(self):
        return {"id": "test.recovery", "version": "1.0.0", "inputs": [{"id": "source", "required": True}], "runtime": {"type": "none"}}

    def test_illegal_state_transition_is_rejected(self):
        assert_transition("run", "running", "failed")
        with self.assertRaises(InvalidStateTransition):
            assert_transition("run", "completed", "running")

    def test_all_lifecycle_tables_accept_declared_edges_and_reject_unknown_edges(self):
        for entity, table in TRANSITIONS.items():
            for current, targets in table.items():
                for target in targets:
                    assert_transition(entity, current, target)
                with self.assertRaises(InvalidStateTransition):
                    assert_transition(entity, current, "not_a_real_state")

    def test_checkpoint_round_trip_preserves_run_and_store(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = CheckpointManager()
            run = {"run_id": "run_test", "status": "running", "artifacts": []}
            state = {"status": "running", "history": [{"state": "node", "status": "entered", "completed_at": None}], "context": {"store": {"brief": {"value": 1}}}}
            summary = manager.save(root, run, state, node_id="node", phase="after", outcome="completed", replay={"replay_safe": True})
            loaded = manager.load(root, summary["checkpoint_id"])

            self.assertEqual(CHECKPOINT_SCHEMA, loaded["schema"])
            self.assertEqual({"value": 1}, loaded["state_snapshot"]["context"]["store"]["brief"])
            self.assertEqual("completed", loaded["state_snapshot"]["history"][-1]["status"])
            self.assertEqual("dict", loaded["input_summary"]["brief"]["type"])

    def test_completed_flow_has_before_and_after_checkpoint_for_every_node(self):
        root_flow = self._safe_flow()
        manifest = self._safe_manifest()
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), root_flow, manifest)
            run = runner.create_run("test.recovery", {"source": "input"})
            checkpoints = runner.list_checkpoints(run["run_id"])

            self.assertEqual("completed", run["status"])
            for node_id in root_flow["states"]:
                self.assertEqual({"before", "after"}, {item["phase"] for item in checkpoints if item["node_id"] == node_id})
                after = next(item for item in checkpoints if item["node_id"] == node_id and item["phase"] == "after")
                committed = runner.checkpoint_manager.load(Path(temp_dir) / ".data" / "runtime" / "runs" / run["run_id"], after["checkpoint_id"])
                self.assertEqual(after["event_id"], committed["event_snapshot"]["event_id"])
            transfer_before = next(item for item in checkpoints if item["node_id"] == "transfer" and item["phase"] == "before")
            committed = runner.checkpoint_manager.load(Path(temp_dir) / ".data" / "runtime" / "runs" / run["run_id"], transfer_before["checkpoint_id"])
            self.assertEqual(["collect"], [item["node_id"] for item in committed["upstream_revisions"]])

    def test_resume_checkpoint_rollback_and_restart_are_distinct_actions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = _runner(root, self._safe_flow(), self._safe_manifest())
            original = runner.create_run("test.recovery", {"source": "input"})
            run_path = root / ".data" / "runtime" / "runs" / original["run_id"] / "run.json"
            interrupted = json.loads(run_path.read_text(encoding="utf-8"))
            interrupted["status"] = "interrupted"
            run_path.write_text(json.dumps(interrupted), encoding="utf-8")

            resumed = runner.recover_run(original["run_id"], "resume_checkpoint")
            resumed_path = root / ".data" / "runtime" / "runs" / original["run_id"] / "run.json"
            resumed_doc = json.loads(resumed_path.read_text(encoding="utf-8"))
            resumed_doc["artifacts"] = [{"artifact_id": "artifact_downstream", "name": "downstream.txt"}]
            resumed_doc["approvals"] = [{"approval_id": "approval_downstream", "node_id": "deliver"}]
            resumed_path.write_text(json.dumps(resumed_doc), encoding="utf-8")
            state_path = root / ".data" / "runtime" / "runs" / original["run_id"] / "root_flow_state.json"
            live_state = json.loads(state_path.read_text(encoding="utf-8"))
            live_state["context"]["cache"] = {"delivery_preview": {"ready": True}}
            state_path.write_text(json.dumps(live_state), encoding="utf-8")
            feedback = {"reason": "developer_adjustment", "changes": {"tone": "short"}}
            rolled_back = runner.recover_run(original["run_id"], "rollback_to_node", target_node="transfer", feedback=feedback)
            restarted = runner.recover_run(original["run_id"], "restart_run")

            self.assertEqual("completed", resumed["status"])
            self.assertEqual("resume_checkpoint", resumed["recovery_history"][-1]["action"])
            self.assertEqual("completed", rolled_back["status"])
            self.assertEqual("rollback_to_node", rolled_back["recovery_history"][-1]["action"])
            self.assertEqual(feedback, rolled_back["recovery_history"][-1]["feedback"])
            self.assertEqual({"final", "result"}, set(rolled_back["recovery_history"][-1]["invalidated_store_keys"]))
            self.assertEqual(["artifact_downstream"], rolled_back["recovery_history"][-1]["invalidated_artifact_ids"])
            self.assertEqual(["approval_downstream"], rolled_back["recovery_history"][-1]["invalidated_approval_ids"])
            self.assertEqual(["delivery_preview"], rolled_back["recovery_history"][-1]["invalidated_cache_keys"])
            self.assertNotEqual(original["run_id"], restarted["run_id"])
            self.assertEqual(original["run_id"], restarted["parent_run_id"])

    def test_missing_delivery_output_fails_closed(self):
        root_flow = {
            "id": "delivery.root",
            "start": "deliver",
            "states": {
                "deliver": {"type": "process", "kind": "delivery", "executor": "deterministic", "effect": "writes_store", "input": "missing", "output": "final", "primary_output": "final", "next": "complete"},
                "complete": {"type": "terminal"},
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), root_flow)
            run = runner.create_run("test.recovery")

            self.assertEqual("failed", run["status"])
            self.assertEqual("DELIVERY_OUTPUT_MISSING", run["error"]["code"])

    def test_required_local_resource_role_blocks_before_run(self):
        manifest = self._safe_manifest()
        manifest["id"] = "test.missing-resource-fixture"
        manifest["resource_requirements"] = [{"role": "required_fixture", "kinds": ["remote_api"], "required": True}]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = _runner(root, self._safe_flow(), manifest)

            with self.assertRaises(RuntimeFailure) as context:
                runner.create_run(manifest["id"], {"source": "input"}, run_id="run_missing_resource")

            self.assertEqual("DEPENDENCY_UNAVAILABLE", context.exception.envelope["code"])
            self.assertFalse((root / ".data" / "runtime" / "runs" / "run_missing_resource").exists())

    def test_idempotent_transient_tool_failure_retries_with_bounds(self):
        executor = LabNodeExecutor()
        tools = _SequenceTools([
            {"ok": False, "code": "dlc_worker_timeout", "error": "timeout"},
            {"ok": True, "content": "done"},
        ])
        executor._builtin_mcp = tools
        run = {"inputs": {}, "mcp_tools": [{
            "id": "flaky",
            "server": "fixture",
            "tool": "work",
            "contract": {"idempotent": True, "retry_policy": {"max_attempts": 2, "initial_delay_seconds": 0}},
        }]}
        state = {"action": "tool_call", "params": {"tools": [{"type": "builtin", "server": "fixture", "tool": "work", "mcp_tool_id": "flaky"}], "output": "result"}}

        result = executor.execute("work", state, {"context": {"store": {}}}, run, ".")

        self.assertFalse(result["failed"])
        self.assertEqual(2, tools.calls)
        self.assertEqual(["timed_out", "succeeded"], [item["status"] for item in result["tool_results"][0]["attempts"]])

    def test_non_idempotent_tool_never_retries_automatically(self):
        executor = LabNodeExecutor()
        tools = _SequenceTools([{"ok": False, "code": "dlc_worker_timeout", "error": "timeout"}])
        executor._builtin_mcp = tools
        run = {"inputs": {}, "mcp_tools": [{
            "id": "charge",
            "server": "fixture",
            "tool": "charge",
            "contract": {"idempotent": False, "retry_policy": {"max_attempts": 3, "initial_delay_seconds": 0}},
        }]}
        state = {"action": "tool_call", "params": {"tools": [{"type": "builtin", "server": "fixture", "tool": "charge", "mcp_tool_id": "charge"}], "output": "result"}}

        result = executor.execute("charge", state, {"context": {"store": {}}}, run, ".")

        self.assertTrue(result["failed"])
        self.assertEqual(1, tools.calls)
        self.assertTrue(result["retry_blocked"][0]["requires_confirmation"])

    def test_bound_external_tool_receives_private_connection_only_at_call_time(self):
        executor = LabNodeExecutor()
        tools = _SequenceTools([{"ok": True, "content": "found"}])
        executor._builtin_mcp = tools
        run = {
            "run_id": "run_resource",
            "cartridge_id": "test.resources",
            "resource_requirements": [{"role": "document_lookup", "kinds": ["remote_api"], "required": True}],
            "local_resources": {"roles": {"document_lookup": {"resource_id": "local-search", "ready": True}}},
            "mcp_tools": [{
                "id": "lookup",
                "type": "remote",
                "server": "docs",
                "tool": "search",
                "resource_role": "document_lookup",
                "contract": {"idempotent": True},
            }],
        }
        state = {"action": "remote_call", "params": {"mcp_tool_id": "lookup", "tool_params": {"query": "test"}, "output": "result"}}
        binding = {
            "role": "document_lookup",
            "resource_id": "local-search",
            "connection": {"id": "local-search", "kind": "remote_api", "endpoint": "https://example.test/search", "auth_env": "SEARCH_KEY"},
        }

        with patch("core.studio.resource_resolver.resolve_runtime_tool_binding", return_value=binding):
            result = executor.execute("lookup", state, {"context": {"store": {}}}, run, ".")

        self.assertFalse(result["failed"])
        self.assertEqual("https://example.test/search", tools.last_params["_local_resource"]["endpoint"])
        self.assertEqual("document_lookup", result["tool_results"][0]["resource_role"])
        self.assertEqual("local-search", result["tool_results"][0]["resource_id"])

    def test_tool_contract_metadata_is_recorded_for_replay_audit(self):
        executor = LabNodeExecutor()
        tools = _SequenceTools([{"ok": True, "content": "done"}])
        executor._builtin_mcp = tools
        run = {"inputs": {}, "mcp_tools": [{
            "id": "charge",
            "server": "fixture",
            "tool": "charge",
            "contract": {
                "idempotent": False,
                "deduplication_key": "store:charge_request_id",
                "compensation": {"tool": "refund", "required": True},
                "unreplayable_reason": "provider cannot guarantee exactly-once charge",
            },
        }]}
        state = {"action": "tool_call", "params": {"tools": [{"type": "builtin", "server": "fixture", "tool": "charge", "mcp_tool_id": "charge"}], "output": "result"}}

        result = executor.execute("charge", state, {"context": {"store": {}}}, run, ".")

        metadata = result["tool_results"][0]["contract"]
        self.assertEqual("store:charge_request_id", metadata["deduplication_key"])
        self.assertTrue(metadata["compensation"]["required"])
        self.assertIn("exactly-once", metadata["unreplayable_reason"])

    def test_retry_current_node_restores_before_checkpoint(self):
        root_flow = {
            "id": "retry.root",
            "start": "work",
            "states": {
                "work": {"type": "process", "kind": "mcp_read", "executor": "mcp", "effect": "read_only", "allowed_tools": ["flaky"], "output": "result", "next": "complete"},
                "complete": {"type": "terminal"},
            },
        }
        manifest = {
            "id": "test.recovery", "version": "1.0.0", "inputs": [], "runtime": {"type": "none"},
            "mcp_tools": [{"id": "flaky", "type": "builtin", "server": "fixture", "tool": "work", "enabled": True, "contract": {"idempotent": True, "side_effect": "read_only", "retry_policy": {"max_attempts": 1}}}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), root_flow, manifest)
            tools = _SequenceTools([
                {"ok": False, "code": "dependency_unavailable", "error": "temporary"},
                {"ok": True, "content": "recovered"},
            ])
            runner.lab_node_executor._builtin_mcp = tools
            failed = runner.create_run("test.recovery")
            recovered = runner.recover_run(failed["run_id"], "retry_current_node")

            self.assertEqual("failed", failed["status"])
            self.assertEqual("completed", recovered["status"])
            self.assertEqual("recovered", json.loads((Path(temp_dir) / ".data" / "runtime" / "runs" / failed["run_id"] / "root_flow_state.json").read_text(encoding="utf-8"))["context"]["store"]["result"])
            self.assertEqual("retry_current_node", recovered["recovery_history"][-1]["action"])
            self.assertEqual(failed["error"]["error_id"], recovered["recovery_history"][-1]["failure_experience"]["error_id"])

    def test_side_effect_retry_requires_explicit_confirmation(self):
        root_flow = {
            "id": "unsafe.root",
            "start": "charge",
            "states": {
                "charge": {"type": "process", "kind": "mcp_execute", "executor": "mcp", "effect": "external_side_effect", "allowed_tools": ["charge"], "output": "result", "next": "complete"},
                "complete": {"type": "terminal"},
            },
        }
        manifest = {
            "id": "test.recovery", "version": "1.0.0", "inputs": [], "runtime": {"type": "none"},
            "mcp_tools": [{"id": "charge", "type": "builtin", "server": "fixture", "tool": "charge", "enabled": True, "contract": {"idempotent": False, "side_effect": "external_side_effect", "retry_policy": {"max_attempts": 1}}}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), root_flow, manifest)
            runner.lab_node_executor._builtin_mcp = _SequenceTools([{"ok": False, "code": "dlc_worker_timeout", "error": "unknown side effect"}])
            failed = runner.create_run("test.recovery")

            with self.assertRaises(RuntimeFailure) as context:
                runner.recover_run(failed["run_id"], "retry_current_node")
            self.assertEqual("REPLAY_CONFIRMATION_REQUIRED", context.exception.envelope["code"])

    def test_running_snapshot_becomes_interrupted_on_base_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / ".data" / "runtime" / "runs" / "run_interrupted"
            run_dir.mkdir(parents=True)
            (run_dir / "run.json").write_text(json.dumps({
                "run_id": "run_interrupted", "cartridge_id": "test.recovery", "status": "running", "current_state": "work",
            }), encoding="utf-8")
            runner = CartridgeRunner(root, _Registry({"id": "test.recovery"}))

            interrupted = runner.get_run("run_interrupted")
            self.assertEqual("interrupted", interrupted["status"])
            self.assertEqual("run_interrupted", runner.get_events("run_interrupted")[-1]["type"])


if __name__ == "__main__":
    unittest.main()
