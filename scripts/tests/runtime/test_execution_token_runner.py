from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.cartridge.runner import CartridgeRunner
from core.runtime.errors import RuntimeFailure


class _Registry:
    def __init__(self, cartridge: dict):
        self.cartridge = cartridge

    def get_cartridge(self, cartridge_id: str) -> dict:
        if cartridge_id != self.cartridge["id"]:
            raise FileNotFoundError(cartridge_id)
        return self.cartridge


def _manifest(cartridge_id: str = "test.execution.tokens") -> dict:
    return {
        "id": cartridge_id,
        "version": "1.0.0",
        "inputs": [],
        "runtime": {"type": "none"},
        "mcp_tools": [],
    }


def _flow(states: dict, edges: list[dict], entry: str) -> dict:
    return {
        "id": "test.execution.tokens.root",
        "protocol": {"id": "CF-FARP", "version": "1.0"},
        "states": states,
        "execution_plan": {
            "schema": "cartridgeflow.execution_plan.v1",
            "entry": entry,
            "edges": edges,
        },
    }


def _runner(root: Path, root_flow: dict, manifest: dict | None = None) -> CartridgeRunner:
    manifest = manifest or _manifest()
    package = root / "package"
    package.mkdir(exist_ok=True)
    runner = CartridgeRunner(root, _Registry({
        "id": manifest["id"],
        "package_path": str(package),
        "manifest": manifest,
        "root_flow": root_flow,
    }))
    runner.build_compatibility_report = lambda *args, **kwargs: {
        "ok": True,
        "status": "compatible",
        "legacy": False,
        "base": {},
        "protocol": {},
        "summary": {},
        "findings": [],
    }
    return runner


class ExecutionTokenRunnerTests(unittest.TestCase):
    def test_loop_is_reentrant_and_checkpoints_capture_token_identity(self):
        flow = _flow(
            {
                "gate": {"type": "control"},
                "body": {"type": "control"},
                "complete": {"type": "terminal"},
            },
            [
                {"id": "gate_body", "kind": "loop", "from": "gate", "to": "body", "loop": {"id": "retry", "max_iterations": 3, "continue_when": "$gate.retry", "exit_to": "complete"}},
                {"id": "body_gate", "kind": "sequence", "from": "body", "to": "gate"},
            ],
            "gate",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), flow)
            calls: list[str] = []

            def execute(node_id, _state, state_doc, _run, _run_dir):
                calls.append(node_id)
                if node_id == "gate":
                    gate = state_doc["context"].setdefault("store", {}).setdefault("gate", {})
                    gate["retry"] = calls.count("gate") == 1
                return {"action": "noop"}

            runner.lab_node_executor.execute = execute
            run = runner.create_run("test.execution.tokens", run_id="run_loop")

            self.assertEqual("completed", run["status"])
            self.assertEqual(["gate", "body", "gate"], calls)
            state = runner._read_json(Path(temp_dir) / ".data" / "runtime" / "runs" / "run_loop" / "root_flow_state.json")
            self.assertEqual(2, [item["state"] for item in state["history"]].count("gate"))
            tokens = state["execution"]["tokens"]
            self.assertGreaterEqual(len([token for token in tokens if token["node_id"] == "gate"]), 2)
            checkpoints = runner.list_checkpoints("run_loop")
            self.assertTrue(all(item["token_id"] and item["token_attempt"] for item in checkpoints))
            committed = runner.checkpoint_manager.load(
                Path(temp_dir) / ".data" / "runtime" / "runs" / "run_loop",
                checkpoints[0]["checkpoint_id"],
            )
            self.assertEqual("cartridgeflow.execution_tokens.v1", committed["execution_snapshot"]["schema"])
            self.assertEqual("run_loop", committed["token"]["run_id"])

    def test_fork_all_join_emits_exactly_one_aggregate_token(self):
        flow = _flow(
            {
                "start": {"type": "control"},
                "left": {"type": "control"},
                "right": {"type": "control"},
                "joined": {"type": "control"},
                "complete": {"type": "terminal"},
            },
            [
                {"id": "start_left", "kind": "fork", "from": "start", "to": "left", "fork": {"id": "split", "branch": "left"}},
                {"id": "start_right", "kind": "fork", "from": "start", "to": "right", "fork": {"id": "split", "branch": "right"}},
                {"id": "left_join", "kind": "join", "from": "left", "to": "joined", "join": {"id": "all_work", "mode": "all", "branch": "left", "branches": ["left", "right"]}},
                {"id": "right_join", "kind": "join", "from": "right", "to": "joined", "join": {"id": "all_work", "mode": "all", "branch": "right", "branches": ["left", "right"]}},
                {"id": "joined_complete", "kind": "sequence", "from": "joined", "to": "complete"},
            ],
            "start",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), flow)
            calls: list[str] = []
            runner.lab_node_executor.execute = lambda node_id, *_args: calls.append(node_id) or {"action": "noop"}

            run = runner.create_run("test.execution.tokens", run_id="run_join")

            self.assertEqual("completed", run["status"])
            self.assertEqual(["left", "right", "joined"], calls)
            events = runner.get_events("run_join")
            joined_edges = [
                event for event in events
                if event["type"] == "flow_edge_traversed" and event["data"].get("reason") == "join"
            ]
            self.assertEqual(1, len(joined_edges))
            self.assertEqual("joined", joined_edges[0]["data"]["to"])
            state = runner._read_json(Path(temp_dir) / ".data" / "runtime" / "runs" / "run_join" / "root_flow_state.json")
            join_tokens = [token for token in state["execution"]["tokens"] if token["node_id"] == "joined"]
            self.assertEqual(1, len(join_tokens))
            self.assertEqual(2, len(join_tokens[0]["parent_token_ids"]))

    def test_batch_tokens_are_bounded_and_preserve_source_item_references(self):
        flow = _flow(
            {
                "files": {"type": "control"},
                "render": {"type": "control"},
                "complete": {"type": "terminal"},
            },
            [
                {"id": "files_render", "kind": "batch", "from": "files", "to": "render", "batch": {"id": "render_files", "items_ref": "$files.items", "size": 2, "max_concurrency": 1, "ordering": "preserve"}},
                {"id": "render_complete", "kind": "sequence", "from": "render", "to": "complete"},
            ],
            "files",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), flow)
            batch_sizes: list[int] = []

            def execute(node_id, _state, state_doc, _run, _run_dir):
                if node_id == "files":
                    state_doc["context"].setdefault("store", {})["files"] = {"items": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
                if node_id == "render":
                    token = state_doc["context"]["_execution_token"]
                    batch_sizes.append(len([ref for ref in token["input_refs"] if ref["kind"] == "batch_item"]))
                return {"action": "noop"}

            runner.lab_node_executor.execute = execute
            run = runner.create_run("test.execution.tokens", run_id="run_batch")

            self.assertEqual("completed", run["status"])
            self.assertEqual([2, 1], batch_sizes)
            state = runner._read_json(Path(temp_dir) / ".data" / "runtime" / "runs" / "run_batch" / "root_flow_state.json")
            render_tokens = [token for token in state["execution"]["tokens"] if token["node_id"] == "render"]
            self.assertEqual([0, 1], [token["lineage"]["batches"][-1]["index"] for token in render_tokens])
            self.assertTrue(all(token["lineage"]["batches"][-1]["max_concurrency"] == 1 for token in render_tokens))

    def test_any_join_cancels_unstarted_sibling_and_emits_once(self):
        flow = _flow(
            {
                "start": {"type": "control"},
                "left": {"type": "control"},
                "right": {"type": "control"},
                "winner": {"type": "control"},
                "complete": {"type": "terminal"},
            },
            [
                {"id": "start_left", "kind": "fork", "from": "start", "to": "left", "fork": {"id": "race", "branch": "left"}},
                {"id": "start_right", "kind": "fork", "from": "start", "to": "right", "fork": {"id": "race", "branch": "right"}},
                {"id": "left_winner", "kind": "join", "from": "left", "to": "winner", "join": {"id": "first", "mode": "any", "branch": "left", "branches": ["left", "right"], "remaining": "cancel"}},
                {"id": "right_winner", "kind": "join", "from": "right", "to": "winner", "join": {"id": "first", "mode": "any", "branch": "right", "branches": ["left", "right"], "remaining": "cancel"}},
                {"id": "winner_complete", "kind": "sequence", "from": "winner", "to": "complete"},
            ],
            "start",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), flow)
            calls: list[str] = []
            runner.lab_node_executor.execute = lambda node_id, *_args: calls.append(node_id) or {"action": "noop"}

            run = runner.create_run("test.execution.tokens", run_id="run_any")

            self.assertEqual("completed", run["status"])
            self.assertEqual(["left", "winner"], calls)
            state = runner._read_json(Path(temp_dir) / ".data" / "runtime" / "runs" / "run_any" / "root_flow_state.json")
            right = next(token for token in state["execution"]["tokens"] if token["node_id"] == "right")
            self.assertEqual("cancelled", right["status"])
            winner_tokens = [token for token in state["execution"]["tokens"] if token["node_id"] == "winner"]
            self.assertEqual(1, len(winner_tokens))

    def test_wait_resume_keeps_the_source_token_and_trace_deterministic(self):
        flow = _flow(
            {
                "request": {"type": "control"},
                "complete": {"type": "terminal"},
                "timed_out": {"type": "terminal"},
            },
            [
                {"id": "wait_approval", "kind": "wait", "from": "request", "to": "complete", "wait": {"id": "approval", "mode": "signal", "signal": "approval.done", "timeout_ms": 60000, "resume_key": "approval"}},
                {"id": "wait_timeout", "kind": "failure", "from": "request", "to": "timed_out", "failure": {"id": "approval_timeout", "causes": ["timeout"]}},
            ],
            "request",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), flow)
            calls: list[str] = []
            runner.lab_node_executor.execute = lambda node_id, *_args: calls.append(node_id) or {"action": "noop"}

            paused = runner.create_run("test.execution.tokens", run_id="run_wait")
            self.assertEqual("paused_waiting_user", paused["status"])
            before = runner._read_json(Path(temp_dir) / ".data" / "runtime" / "runs" / "run_wait" / "root_flow_state.json")
            waiting = next(token for token in before["execution"]["tokens"] if token["status"] == "waiting")
            wait_checkpoint = next(item for item in runner.list_checkpoints("run_wait") if item["outcome"] == "paused_waiting_user")
            committed = runner.checkpoint_manager.load(Path(temp_dir) / ".data" / "runtime" / "runs" / "run_wait", wait_checkpoint["checkpoint_id"])
            self.assertEqual("waiting", committed["token"]["status"])
            interrupted = runner.get_run("run_wait")
            interrupted["status"] = "interrupted"
            runner._write_json(Path(temp_dir) / ".data" / "runtime" / "runs" / "run_wait" / "run.json", interrupted)
            restored = runner.recover_run("run_wait", "resume_checkpoint")
            self.assertEqual("paused_waiting_user", restored["status"])
            resumed = runner.resume_execution_wait("run_wait", "approval", {"approved": True})

            self.assertEqual("completed", resumed["status"])
            self.assertEqual(["request"], calls)
            after = runner._read_json(Path(temp_dir) / ".data" / "runtime" / "runs" / "run_wait" / "root_flow_state.json")
            self.assertEqual("completed", next(token for token in after["execution"]["tokens"] if token["token_id"] == waiting["token_id"])["status"])
            trace = [event["type"] for event in runner.get_events("run_wait")]
            self.assertLess(trace.index("execution_token_waiting"), trace.index("execution_wait_resume_requested"))
            self.assertIn("execution_token_wait_resumed", trace)

    def test_duration_wait_rejects_resume_before_the_declared_boundary(self):
        flow = _flow(
            {
                "sleep": {"type": "control"},
                "complete": {"type": "terminal"},
                "timed_out": {"type": "terminal"},
            },
            [
                {"id": "wait_duration", "kind": "wait", "from": "sleep", "to": "complete", "wait": {"id": "short_delay", "mode": "duration", "duration_ms": 60000, "timeout_ms": 120000, "resume_key": "delay_elapsed"}},
                {"id": "wait_timeout", "kind": "failure", "from": "sleep", "to": "timed_out", "failure": {"id": "delay_timeout", "causes": ["timeout"]}},
            ],
            "sleep",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), flow)
            runner.lab_node_executor.execute = lambda *_args: {"action": "noop"}
            paused = runner.create_run("test.execution.tokens", run_id="run_duration")

            with self.assertRaisesRegex(ValueError, "declared resume boundary"):
                runner.resume_execution_wait("run_duration", "delay_elapsed")

            self.assertEqual("paused_waiting_user", paused["status"])
            self.assertEqual("paused_waiting_user", runner.get_run("run_duration")["status"])

    def test_pending_interaction_resumes_the_paused_token_through_declared_plan_edge(self):
        flow = _flow(
            {
                "decide": {"type": "control"},
                "deliver": {"type": "control"},
                "complete": {"type": "terminal"},
            },
            [
                {"id": "decide_deliver", "kind": "sequence", "from": "decide", "to": "deliver"},
                {"id": "deliver_complete", "kind": "sequence", "from": "deliver", "to": "complete"},
            ],
            "decide",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), flow)
            calls: list[str] = []

            def execute(node_id, *_args):
                calls.append(node_id)
                if node_id == "decide":
                    return {
                        "action": "decision",
                        "paused": True,
                        "pause_status": "paused_waiting_user",
                        "pending_interaction": {
                            "interaction_id": "review",
                            "status": "waiting_user",
                            "question": {"store_key": "decision_reply"},
                            "resume": {"policy": "resume_next_node"},
                        },
                    }
                return {"action": "noop"}

            runner.lab_node_executor.execute = execute
            paused = runner.create_run("test.execution.tokens", run_id="run_interaction")
            resumed = runner.answer_pending_interaction("run_interaction", {"approved": True})

            self.assertEqual("paused_waiting_user", paused["status"])
            self.assertEqual("completed", resumed["status"])
            self.assertEqual(["decide", "deliver"], calls)
            state = runner._read_json(Path(temp_dir) / ".data" / "runtime" / "runs" / "run_interaction" / "root_flow_state.json")
            decide = next(token for token in state["execution"]["tokens"] if token["node_id"] == "decide")
            self.assertEqual("completed", decide["status"])
            self.assertEqual({"approved": True}, state["context"]["store"]["decision_reply"])

    def test_side_effect_token_recovery_requires_confirmation_without_replay(self):
        flow = _flow(
            {
                "charge": {"type": "process", "effect": "external_side_effect"},
                "complete": {"type": "terminal"},
                "failed": {"type": "terminal"},
            },
            [
                {"id": "charge_complete", "kind": "sequence", "from": "charge", "to": "complete"},
                {"id": "charge_failed", "kind": "failure", "from": "charge", "to": "failed", "failure": {"id": "charge_exception", "causes": ["exception"]}},
            ],
            "charge",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = _runner(Path(temp_dir), flow)
            calls: list[str] = []
            def execute(node_id, *_args):
                calls.append(node_id)
                if node_id == "charge":
                    return {"action": "tool_call", "failed": True, "error": "provider outcome is unknown"}
                return {"action": "noop"}

            runner.lab_node_executor.execute = execute

            failed = runner.create_run("test.execution.tokens", run_id="run_effect")
            self.assertEqual("failed", failed["status"])
            with self.assertRaises(RuntimeFailure) as caught:
                runner.recover_run("run_effect", "retry_current_node")

            self.assertEqual("REPLAY_CONFIRMATION_REQUIRED", caught.exception.envelope["code"])
            self.assertEqual(["charge", "failed"], calls)
            events = runner.get_events("run_effect")
            self.assertNotIn("run_recovery_started", [event["type"] for event in events])


if __name__ == "__main__":
    unittest.main()
