"""execution_plan 路径下 resume_target_node 的 ready-token 调度测试（博客驳回循环）"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.cartridge.runner import CartridgeRunner
from core.llm.config import ModelConfig
from core.protocol import build_compatibility_report, load_base_implementation

ROOT = Path(__file__).resolve().parents[3]


def plan_manifest():
    return {
        "id": "test.runtime.resume-target-token",
        "version": "0.0.1",
        "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
        "runtime_contract": {
            "protocol": "CF-FARP",
            "protocol_version": "1.0",
            "required_profiles": ["runtime_core", "execution_plan_runtime", "interaction_runtime"],
            "recommended_profiles": [],
            "required_capabilities": [
                "manifest_load",
                "manifest_validate",
                "root_flow_execution",
                "unified_process_node",
                "execution_plan_v1_authoring",
                "execution_plan_compile",
                "execution_plan_sequence_contract",
                "execution_plan_failure_contract",
                "decision_process",
                "decision_envelope_v1",
                "runtime_state_machine",
                "checkpoint_persistence",
                "runtime_error_envelope_v1",
            ],
            "optional_capabilities": [],
            "required_tools": [],
            "optional_tools": [],
        },
        "delivery_readiness": {"level": "dev"},
        "branding": {"tags": []},
        "mcp_tools": [],
        "inputs": [{"id": "topic", "type": "textarea", "required": True}],
        "outputs": [{"id": "article", "type": "document", "required": True}],
        "delivery": {"type": "summary_with_artifacts", "primary_output": "article", "show_artifacts": True},
    }


def plan_flow():
    return {
        "schema_version": "1.0",
        "id": "test.runtime.resume-target-token.root",
        "protocol": {"id": "CF-FARP", "version": "1.0"},
        "start": "start",
        "states": {
            "start": {"type": "control", "title": "start", "locked": True},
            "collect": {
                "type": "process", "kind": "input", "executor": "user", "effect": "writes_store",
                "action": "collect_inputs",
                "params": {"output": "topic", "fields": ["topic"]},
                "outputs": {"topic": {"schema": {"type": "object"}, "target": {"type": "store", "key": "topic"}}},
            },
            "draft": {
                "type": "process", "kind": "decision", "executor": "llm", "effect": "none",
                "action": "llm_prompt", "model_role": "writer", "output": "draft_out",
                "output_contract": "decision_envelope.v1",
                "decision_contract": {
                    "schema": "decision_envelope.v1",
                    "allowed_statuses": ["resolved"],
                    "consume": {"mode": "payload_path", "path": "payload.draft", "as": "draft_text", "required": True, "on_missing": "fail_closed"},
                    "offline_decision": {"schema": "decision_envelope.v1", "status": "resolved", "summary": "mock", "payload": {"draft": "DRAFT"}},
                },
                "inputs": {"topic": {"required": True, "schema": {"type": "object"}, "binding": {"source": "store", "key": "topic"}}},
                "outputs": {"draft_out": {"schema": {"type": "object"}, "target": {"type": "store", "key": "draft_text"}}},
                "llm_options": {"max_tokens": 20000, "timeout_seconds": 30},
                "retry_policy": {"max_attempts": 3, "initial_delay_seconds": 0, "max_delay_seconds": 0},
                "params": {"description": "draft the article"},
            },
            "review": {
                "type": "process", "kind": "human_gate", "executor": "human", "effect": "writes_store",
                "action": "confirm_checkpoint",
                "params": {
                    "output": "approval",
                    "interaction": {
                        "store_key": "approval",
                        "input_schema": {"type": "object", "properties": {"approval": {"type": "string"}, "feedback": {"type": "string"}}, "required": ["approval"]},
                        "prompt": "review",
                        "answer_routes": [
                            {"match": {"field": "approval", "equals": "rejected"}, "policy": "resume_target_node", "target_node": "revise", "clear_store_keys": "approval", "copy_answer_to": "review_feedback"},
                            {"match": {"field": "approval", "equals": "approved"}, "policy": "resume_same_node"},
                        ],
                    },
                    "description": "review the draft",
                },
                "inputs": {"article": {"required": True, "schema": {"type": "object"}, "binding": {"source": "store", "key": "draft_text"}}},
                "outputs": {"approval": {"schema": {"type": "object"}, "target": {"type": "store", "key": "approval"}}},
            },
            "revise": {
                "type": "process", "kind": "decision", "executor": "llm", "effect": "none",
                "action": "llm_prompt", "model_role": "writer", "output": "revise_out",
                "output_contract": "decision_envelope.v1",
                "decision_contract": {
                    "schema": "decision_envelope.v1",
                    "allowed_statuses": ["resolved"],
                    "consume": {"mode": "payload_path", "path": "payload.rev", "as": "draft_text", "required": True, "on_missing": "fail_closed"},
                    "offline_decision": {"schema": "decision_envelope.v1", "status": "resolved", "summary": "mock", "payload": {"rev": "REVISED"}},
                },
                "inputs": {
                    "draft": {"required": True, "schema": {"type": "object"}, "binding": {"source": "store", "key": "draft_text"}},
                    "feedback": {"required": True, "schema": {"type": "object"}, "binding": {"source": "store", "key": "review_feedback"}},
                },
                "outputs": {"revise_out": {"schema": {"type": "object"}, "target": {"type": "store", "key": "draft_text"}}},
                "llm_options": {"max_tokens": 20000, "timeout_seconds": 30},
                "params": {"description": "revise the draft"},
            },
            "package": {
                "type": "process", "kind": "transform", "executor": "deterministic", "effect": "writes_artifacts",
                "action": "pass_result", "output": "article", "permission": "write_run_artifacts", "failure_policy": "fail_closed", "audit_log": True, "replay_policy": "new_revision",
                "inputs": {"article": {"required": True, "schema": {"type": "string", "minLength": 1}, "binding": {"source": "store", "key": "draft_text"}}},
                "outputs": {"article": {"schema": {"type": "object"}, "target": {"type": "artifact", "artifact_id": "article", "type_name": "markdown", "mime_type": "text/markdown", "name": "article.md"}}},
                "params": {"description": "package the article"},
            },
            "complete": {"type": "terminal", "title": "complete", "kind": "terminal", "locked": True},
            "flow_failed": {"type": "terminal", "title": "flow_failed", "kind": "terminal"},
        },
        "execution_plan": {
            "schema": "cartridgeflow.execution_plan.v1",
            "entry": "start",
            "edges": [
                {"id": "start_collect", "kind": "sequence", "from": "start", "to": "collect"},
                {"id": "collect_draft", "kind": "sequence", "from": "collect", "to": "draft"},
                {"id": "collect_failure", "kind": "failure", "from": "collect", "to": "flow_failed", "failure": {"id": "e1", "causes": ["exception", "validation"]}},
                {"id": "draft_review", "kind": "sequence", "from": "draft", "to": "review"},
                {"id": "draft_failure", "kind": "failure", "from": "draft", "to": "flow_failed", "failure": {"id": "e2", "causes": ["exception", "resource", "timeout", "validation"]}},
                {"id": "review_loop", "kind": "loop", "from": "review", "to": "revise", "loop": {"id": "revision_loop", "max_iterations": 3, "continue_when": "$approval.feedback", "exit_to": "package"}},
                {"id": "review_failure", "kind": "failure", "from": "review", "to": "flow_failed", "failure": {"id": "e3", "causes": ["exception", "validation"]}},
                {"id": "revise_review", "kind": "sequence", "from": "revise", "to": "review"},
                {"id": "revise_failure", "kind": "failure", "from": "revise", "to": "flow_failed", "failure": {"id": "e4", "causes": ["exception", "resource", "timeout", "validation"]}},
                {"id": "package_complete", "kind": "sequence", "from": "package", "to": "complete"},
                {"id": "package_failure", "kind": "failure", "from": "package", "to": "flow_failed", "failure": {"id": "e5", "causes": ["exception", "validation"]}},
            ],
        },
    }


class _Registry:
    def __init__(self, temp_dir, manifest, flow):
        self._temp_dir = temp_dir
        self._manifest = manifest
        self._flow = flow

    def get_cartridge(self, cartridge_id):
        return {
            "id": cartridge_id,
            "package_path": str(self._temp_dir),
            "manifest": self._manifest,
            "root_flow": self._flow,
        }


class ResumeTargetTokenTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._tmp.name)
        self._model_binding_patch = mock.patch(
            "core.cartridge.runner.build_model_binding_report",
            return_value={"status": "ok", "items": []},
        )
        self._model_binding_patch.start()
        self.manifest = plan_manifest()
        self.flow = plan_flow()
        self.runner = CartridgeRunner(self.temp_dir, _Registry(self.temp_dir, self.manifest, self.flow))
        base = load_base_implementation(ROOT)
        self.runner.build_compatibility_report = lambda manifest, root_flow=None, package_path=None, analysis_target="dev", base=base: build_compatibility_report(base, manifest, root_flow or self.flow)
        self.runner.mcp_executor = None

    def tearDown(self):
        self._model_binding_patch.stop()
        self._tmp.cleanup()

    def _mock_llm(self):
        """Stub the LLM provider: draft/revise return resolved envelopes while
        the human review gate really pauses. Must stay active across answer
        calls (the revise node calls chat after resume)."""
        import core.llm
        import core.llm.config_manager
        assert hasattr(core.llm, "chat"), "core.llm.chat must stay patchable (function-local import)"
        assert hasattr(core.llm.config_manager, "resolve_model"), "resolve_model must stay patchable"
        cfg = ModelConfig(
            provider_id="test-provider",
            model="test-model",
            api_key="test-key",
            base_url="https://example.test",
            timeout=30,
            max_tokens=20000,
        )

        async def fake_chat(_cfg, _messages, **kwargs):
            payload = {"draft": "DRAFT"}
            if _messages and "revise" in str(_messages[-1].get("content") or "").lower():
                payload = {"rev": "REVISED"}
            return {
                "content": json.dumps({
                    "schema": "decision_envelope.v1",
                    "status": "resolved",
                    "summary": "mock",
                    "payload": payload,
                }),
                "meta": {"finish_reason": "stop"},
            }

        return mock.patch("core.llm.config_manager.resolve_model", return_value=cfg), mock.patch(
            "core.llm.chat", side_effect=fake_chat
        )

    def test_reject_routes_to_revise_via_ready_token(self):
        p1, p2 = self._mock_llm()
        with p1, p2:
            run = self.runner.create_run("test.runtime.resume-target-token", {"topic": "T"})
            self.assertEqual(run["status"], "paused_waiting_user")
            self.assertEqual(run["current_state"], "review")

            # 驳回：resume_target_node=revise + clear approval + copy feedback
            run = self.runner.answer_pending_interaction(
                run["run_id"],
                {"approval": "rejected", "feedback": "压缩开头"},
            )
            self.assertEqual(run["status"], "paused_waiting_user")
            self.assertEqual(run["current_state"], "review")
            state_doc = self.runner._read_json(self.runner.runs_dir / run["run_id"] / "root_flow_state.json")
            store = state_doc["context"]["store"]
            self.assertNotIn("approval", store)  # clear_store_keys 生效
            self.assertIn("review_feedback", store)  # copy_answer_to 生效
            tokens = state_doc["execution"]["tokens"]
            revise_tokens = [t for t in tokens if t.get("node_id") == "revise"]
            self.assertEqual(len(revise_tokens), 1, "resume target must schedule a ready token for revise")
            self.assertEqual(revise_tokens[0]["status"], "completed", "revise already ran (offline decision) and completed")
            # review token completed 且无 transition_pending（不走成功出边绕过）
            review_token = max((t for t in tokens if t.get("node_id") == "review"), key=lambda t: int(t.get("created_sequence") or 0))
            self.assertNotIn("transition_pending", review_token)
            # 血缘：resume token 继承 parent（首次暂停的 review token）/via_edge，并发出 created 事件
            first_review = min((t for t in tokens if t.get("node_id") == "review"), key=lambda t: int(t.get("created_sequence") or 0))
            self.assertEqual(revise_tokens[0]["parent_token_ids"], [first_review["token_id"]])
            self.assertEqual(revise_tokens[0]["via_edge_id"], "review_loop")
            created = [
                e for e in self.runner.get_events(run["run_id"])
                if e.get("type") == "execution_token_created" and (e.get("data") or {}).get("node_id") == "revise"
            ]
            self.assertEqual(len(created), 1, "resume token must emit an execution_token_created event")

            # 第二轮批准：approval 保留 -> loop exit -> package -> complete
            run = self.runner.answer_pending_interaction(
                run["run_id"],
                {"approval": "approved"},
            )
            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["current_state"], "complete")
            self.assertIn("article", {a.get("artifact_id") for a in (run.get("artifacts") or [])})

    def test_approve_route_exits_loop(self):
        p1, p2 = self._mock_llm()
        with p1, p2:
            run = self.runner.create_run("test.runtime.resume-target-token", {"topic": "T"})
            self.assertEqual(run["status"], "paused_waiting_user")
            run = self.runner.answer_pending_interaction(run["run_id"], {"approval": "approved"})
            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["current_state"], "complete")
            state_doc = self.runner._read_json(self.runner.runs_dir / run["run_id"] / "root_flow_state.json")
            tokens = [t for t in state_doc["execution"]["tokens"] if t.get("node_id") == "revise"]
            self.assertEqual(tokens, [], "approve path must not schedule revise")


    def test_node_retry_policy_retries_failed_llm_node(self):
        """A node-level retry_policy re-schedules a failed LLM node: first call
        returns empty content (PROVIDER_EMPTY_RESPONSE), the retry succeeds."""
        calls = {"n": 0}

        async def flaky_chat(_cfg, _messages, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"content": "", "meta": {"finish_reason": "length"}}
            return {
                "content": json.dumps({
                    "schema": "decision_envelope.v1",
                    "status": "resolved",
                    "summary": "mock",
                    "payload": {"draft": "DRAFT"},
                }),
                "meta": {"finish_reason": "stop"},
            }

        cfg = ModelConfig(
            provider_id="test-provider", model="test-model", api_key="test-key",
            base_url="https://example.test", timeout=30, max_tokens=20000,
        )
        with mock.patch("core.llm.config_manager.resolve_model", return_value=cfg), \
                mock.patch("core.llm.chat", side_effect=flaky_chat):
            run = self.runner.create_run("test.runtime.resume-target-token", {"topic": "T"})
        self.assertEqual(run["status"], "paused_waiting_user")
        self.assertEqual(calls["n"], 2, "node-level retry must re-invoke the LLM")
        state_doc = self.runner._read_json(self.runner.runs_dir / run["run_id"] / "root_flow_state.json")
        draft_token = next(
            (t for t in state_doc["execution"]["tokens"] if t.get("node_id") == "draft"),
            None,
        )
        self.assertIsNotNone(draft_token)
        self.assertEqual(draft_token["attempt"], 2, "retried token must record attempt 2")
        self.assertNotEqual(draft_token["status"], "failed")

    def test_node_retry_policy_exhausts_into_failure_edge(self):
        """After max_attempts the node fails for real and follows the failure edge."""
        calls = {"n": 0}

        async def always_empty(_cfg, _messages, **kwargs):
            calls["n"] += 1
            return {"content": "", "meta": {"finish_reason": "length"}}

        cfg = ModelConfig(
            provider_id="test-provider", model="test-model", api_key="test-key",
            base_url="https://example.test", timeout=30, max_tokens=20000,
        )
        with mock.patch("core.llm.config_manager.resolve_model", return_value=cfg), \
                mock.patch("core.llm.chat", side_effect=always_empty):
            run = self.runner.create_run("test.runtime.resume-target-token", {"topic": "T"})
        self.assertEqual(run["status"], "failed")
        self.assertEqual(calls["n"], 3, "retry_policy max_attempts=3 must bound the attempts")
        err = run.get("error") or {}
        self.assertEqual(err.get("code"), "PROVIDER_EMPTY_RESPONSE")
        self.assertEqual(err.get("node_id"), "draft")


    def test_route_max_attempts_bounds_reject_loop(self):
        """answer_routes rejected route with max_attempts=2: the third rejection
        falls through to the default resume (approve-like exit to package)."""
        flow = plan_flow()
        routes = flow["states"]["review"]["params"]["interaction"]["answer_routes"]
        routes[0]["max_attempts"] = 2
        tmp2 = tempfile.TemporaryDirectory()
        registry = _Registry(Path(tmp2.name), plan_manifest(), flow)
        runner = CartridgeRunner(Path(tmp2.name), registry)
        base = load_base_implementation(ROOT)
        runner.build_compatibility_report = lambda manifest, root_flow=None, package_path=None, analysis_target="dev", base=base: build_compatibility_report(base, manifest, root_flow or flow)

        cfg = ModelConfig(
            provider_id="test-provider", model="test-model", api_key="test-key",
            base_url="https://example.test", timeout=30, max_tokens=20000,
        )

        async def fake_chat(_cfg, _messages, **kwargs):
            payload = {"draft": "DRAFT"}
            if _messages and "revise" in str(_messages[-1].get("content") or "").lower():
                payload = {"rev": "REVISED"}
            return {
                "content": json.dumps({"schema": "decision_envelope.v1", "status": "resolved", "summary": "m", "payload": payload}),
                "meta": {"finish_reason": "stop"},
            }

        with mock.patch("core.llm.config_manager.resolve_model", return_value=cfg), \
                mock.patch("core.llm.chat", side_effect=fake_chat):
            run = runner.create_run("test.runtime.resume-target-token", {"topic": "T"})
            self.assertEqual(run["status"], "paused_waiting_user")
            # 驳回 1
            run = runner.answer_pending_interaction(run["run_id"], {"approval": "rejected", "feedback": "f1"})
            self.assertEqual(run["status"], "paused_waiting_user", "first rejection resumes to revise and re-pauses")
            # 驳回 2（max_attempts 内）
            run = runner.answer_pending_interaction(run["run_id"], {"approval": "rejected", "feedback": "f2"})
            self.assertEqual(run["status"], "paused_waiting_user", "second rejection still within max_attempts")
            # 驳回 3（超限 -> 走默认 resume_same_node -> approval 保留 -> loop exit -> package）
            run = runner.answer_pending_interaction(run["run_id"], {"approval": "rejected", "feedback": "f3"})
            self.assertEqual(run["status"], "completed", "route exhausted: fall through to exit")
            self.assertEqual(run["current_state"], "complete")
        tmp2.cleanup()


    def test_llm_retry_appends_corrective_prompt(self):
        """On parse failure the automatic retry sends an extra corrective
        user message instead of repeating the identical prompt."""
        prompts = []

        async def drift_chat(_cfg, _messages, **kwargs):
            prompts.append(str(_messages[-1].get("content") or ""))
            if len(prompts) == 1:
                # malformed JSON: valid object followed by 60 chars of garbage
                # (beyond the 40-char tail-trim tolerance)
                return {
                    "content": '{"schema":"decision_envelope.v1","status":"resolved","summary":"m","payload":{"draft":"DRAFT"}}' + "x" * 60,
                    "meta": {"finish_reason": "stop"},
                }
            return {
                "content": json.dumps({"schema": "decision_envelope.v1", "status": "resolved", "summary": "m", "payload": {"draft": "DRAFT"}}),
                "meta": {"finish_reason": "stop"},
            }

        cfg = ModelConfig(
            provider_id="test-provider", model="test-model", api_key="test-key",
            base_url="https://example.test", timeout=30, max_tokens=20000,
        )
        with mock.patch("core.llm.config_manager.resolve_model", return_value=cfg), \
                mock.patch("core.llm.chat", side_effect=drift_chat):
            run = self.runner.create_run("test.runtime.resume-target-token", {"topic": "T"})
        self.assertEqual(run["status"], "paused_waiting_user", "retry recovered from malformed JSON")
        self.assertEqual(len(prompts), 2)
        self.assertIn("合法 JSON", prompts[1], "second attempt must carry a corrective hint")
        self.assertNotEqual(prompts[0], prompts[1])


    def test_paused_run_cancels_to_cancelled_status(self):
        """A paused review run can be cancelled through control_with_options."""
        p1, p2 = self._mock_llm()
        with p1, p2:
            run = self.runner.create_run("test.runtime.resume-target-token", {"topic": "T"})
            self.assertEqual(run["status"], "paused_waiting_user")
            cancelled = self.runner.control_with_options(run["run_id"], "cancel")
            self.assertEqual(cancelled["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
