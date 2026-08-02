import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.cartridge import artifacts as artifacts_module
from core.cartridge.artifacts import ArtifactManager
from core.cartridge.node_normalizer import normalize_runtime_node
from core.cartridge.runner import CartridgeRunner
from core.lab import builtin_mcp as builtin_mcp_module
from core.lab.builtin_mcp import BuiltinMcpRegistry
from core.lab.node_executor import LabNodeExecutor
from core.protocol import build_v06_flow_contract_report


ROOT = Path(__file__).resolve().parents[3]


def current_manifest():
    return {
        "id": "test.process.nodes",
        "version": "1.0.0",
        "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
        "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.6"},
        "mcp_tools": [
            {
                "id": "read_note",
                "type": "builtin",
                "server": "filesystem",
                "tool": "read_file",
                "contract": {"side_effect": "read_only"},
            }
        ],
    }


def current_flow(decision_patch=None, extra_states=None):
    decision = {
        "type": "process",
        "kind": "decision",
        "executor": "llm",
        "effect": "none",
        "input": "brief",
        "output": "decision",
        "output_contract": "decision_envelope.v1",
        "decision_contract": {
            "schema": "decision_envelope.v1",
            "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
            "on_needs_user_input": "pause",
            "interaction": {
                "store_key": "decision_reply",
                "input_schema": "decision_reply.v1",
                "resume_policy": "resume_same_node",
            },
            "consume": {
                "mode": "payload_path",
                "path": "payload.decision",
                "as": "decision_payload",
                "required": True,
                "on_missing": "fail_closed",
            },
        },
        "next": "deliver",
    }
    if decision_patch:
        decision.update(decision_patch)
    states = {
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
        "decide": decision,
        "deliver": {
            "type": "process",
            "kind": "delivery",
            "executor": "deterministic",
            "effect": "writes_store",
            "input": "decision_payload",
            "output": "delivery",
            "primary_output": "delivery",
            "next": "complete",
        },
        "complete": {"type": "terminal"},
    }
    if extra_states:
        states.update(extra_states)
    return {
        "schema_version": "1.0",
        "id": "test.process.nodes.root",
        "protocol": {"id": "CF-FARP", "version": "0.6"},
        "start": "start",
        "states": states,
    }


class ProcessNodeContractTests(unittest.TestCase):
    def test_current_process_contract_accepts_v06_flow(self):
        report = build_v06_flow_contract_report(current_flow(), current_manifest())
        self.assertTrue(report["ok"], report["findings"])

    def test_process_kind_is_required(self):
        flow = current_flow()
        flow["states"]["decide"].pop("kind")
        report = build_v06_flow_contract_report(flow, current_manifest())
        self.assertFalse(report["ok"])
        self.assertIn("v02_process_kind_missing", [item["code"] for item in report["findings"]])

    def test_transfer_rejects_tool_binding(self):
        flow = current_flow(extra_states={
            "unsafe_transfer": {
                "type": "process",
                "kind": "transfer",
                "executor": "deterministic",
                "effect": "writes_store",
                "input": "brief",
                "output": "brief_copy",
                "tools": [{"type": "builtin", "server": "filesystem", "tool": "read_file"}],
            }
        })
        report = build_v06_flow_contract_report(flow, current_manifest())
        self.assertFalse(report["ok"])
        self.assertIn("v02_transfer_has_side_capability", [item["code"] for item in report["findings"]])

    def test_resolved_decision_requires_consume_contract(self):
        flow = current_flow({
            "decision_contract": {
                "schema": "decision_envelope.v1",
                "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
                "on_needs_user_input": "pause",
                "interaction": {
                    "store_key": "decision_reply",
                    "input_schema": "decision_reply.v1",
                    "resume_policy": "resume_same_node",
                },
            }
        })
        report = build_v06_flow_contract_report(flow, current_manifest())
        self.assertFalse(report["ok"])
        self.assertIn("v04_decision_consume_missing", [item["code"] for item in report["findings"]])


class ProcessNodeExecutionTests(unittest.TestCase):
    def test_builtin_filesystem_protects_private_data_and_reads_explicit_upload(self):
        with tempfile.TemporaryDirectory(prefix="cartridgeflow-workspace-") as workspace_dir, tempfile.TemporaryDirectory(
            prefix="cartridgeflow-data-",
        ) as data_dir:
            workspace = Path(workspace_dir)
            data_root = Path(data_dir)
            upload_root = data_root / "temp" / "uploads"
            secret = data_root / "user" / "config" / "llm" / "providers.json"
            legacy_secret = workspace / ".data" / "user" / "config" / "llm" / "providers.json"
            uploaded = upload_root / "upload-token.txt"
            secret.parent.mkdir(parents=True)
            legacy_secret.parent.mkdir(parents=True)
            upload_root.mkdir(parents=True)
            secret.write_text('{"api_key":"must-not-leak"}', encoding="utf-8")
            legacy_secret.write_text('{"api_key":"legacy-must-not-leak"}', encoding="utf-8")
            uploaded.write_text("explicit upload", encoding="utf-8")

            with patch.object(builtin_mcp_module, "DATA_ROOT", data_root), patch.object(
                builtin_mcp_module, "UPLOADS_DIR", upload_root,
            ):
                registry = BuiltinMcpRegistry(workspace)
                denied_read = registry.call("filesystem", "read_file", {"path": ".data/user/config/llm/providers.json"})
                denied_legacy_absolute = registry.call("filesystem", "read_file", {"path": str(legacy_secret)})
                denied_write = registry.call("filesystem", "write_file", {"path": ".data/user/config/overwrite.json", "content": "bad"})
                denied_list = registry.call("filesystem", "list_dir", {"path": ".data/temp/uploads"})
                allowed_read = registry.call("filesystem", "read_file", {"path": ".data/temp/uploads/upload-token.txt"})

            self.assertFalse(denied_read["ok"])
            self.assertFalse(denied_legacy_absolute["ok"])
            self.assertFalse(denied_write["ok"])
            self.assertFalse(denied_list["ok"])
            self.assertNotIn("must-not-leak", str(denied_read))
            self.assertTrue(allowed_read["ok"])
            self.assertEqual("explicit upload", allowed_read["content"])

    def test_artifacts_are_scoped_to_the_current_run_with_external_data_root(self):
        with tempfile.TemporaryDirectory(prefix="cartridgeflow-workspace-") as workspace_dir, tempfile.TemporaryDirectory(
            prefix="cartridgeflow-data-",
        ) as data_dir:
            workspace = Path(workspace_dir)
            runs_dir = Path(data_dir) / "runtime" / "runs"
            run = {"run_id": "run_scoped", "runtime": {"type": "none"}, "artifacts": []}
            run_dir = runs_dir / run["run_id"]
            manager = ArtifactManager(workspace)

            with patch.object(artifacts_module, "RUNS_DIR", runs_dir):
                artifact = manager.create_text_artifact(run, run_dir, "artifact_1", "result.txt", "safe")
                run["artifacts"] = [artifact]
                self.assertEqual("safe", manager.resolve_artifact_path(run, "result.txt").read_text(encoding="utf-8"))

                unrelated = workspace / "README.md"
                unrelated.write_text("private project content", encoding="utf-8")
                forged = {"name": "README.md", "path": str(unrelated)}
                with self.assertRaisesRegex(ValueError, "Invalid artifact path"):
                    manager.resolve_artifact_record_path(run, forged)
                with self.assertRaisesRegex(ValueError, "Invalid run id"):
                    manager.resolve_artifact_record_path({**run, "run_id": "run_scoped/../other"}, artifact)

    def test_top_level_llm_instructions_are_preserved_for_runtime(self):
        state = {
            "type": "process",
            "kind": "decision",
            "executor": "llm",
            "effect": "none",
            "system_prompt": "You are a narration editor.",
            "prompt": "Write the final narration into payload.script.",
            "params": {},
        }

        normalized = normalize_runtime_node(state)

        self.assertEqual("You are a narration editor.", normalized["params"]["system_prompt"])
        self.assertEqual("Write the final narration into payload.script.", normalized["params"]["prompt"])

    def test_unknown_action_fails_instead_of_reporting_a_skipped_success(self):
        state_doc = {"context": {"store": {}}}
        result = LabNodeExecutor().execute(
            "unsupported",
            {"type": "process", "action": "unsupported_action"},
            state_doc,
            {"inputs": {}},
            ".",
        )
        self.assertTrue(result["failed"])
        self.assertEqual("ACTION_EXECUTOR_MISSING", result["error_code"])
        self.assertNotIn("skipped", result)

    def test_input_process_collects_declared_inputs(self):
        state_doc = {"context": {"store": {}}}
        run = {"inputs": {"episode_id": "ep_001", "goal": "open with a chase"}}
        state = {
            "type": "process",
            "protocol_version": "0.6",
            "kind": "input",
            "executor": "user",
            "effect": "writes_store",
            "input_kind": "initial",
            "source": "user_form",
            "input_schema": {"fields": ["episode_id", "goal"]},
            "output": "brief",
        }
        result = LabNodeExecutor().execute("collect", state, state_doc, run, ".")
        self.assertEqual("collect_inputs", result["action"])
        self.assertEqual({"episode_id": "ep_001", "goal": "open with a chase"}, state_doc["context"]["store"]["brief"])

    def test_input_process_resolves_current_date_when_omitted(self):
        state_doc = {"context": {"store": {}}}
        state = {
            "type": "process",
            "kind": "input",
            "action": "collect_inputs",
            "params": {
                "output": "brief",
                "fields": ["edition_date"],
                "defaults": {"edition_date": {"type": "current_date", "timezone": "Asia/Shanghai"}},
            },
        }
        LabNodeExecutor().execute("collect", state, state_doc, {"inputs": {}}, ".")
        self.assertRegex(state_doc["context"]["store"]["brief"]["edition_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_legacy_generic_prompt_does_not_override_configured_ai_preset(self):
        state_doc = {"context": {"store": {"brief": "# Launch plan\nShip the guided builder."}}}
        state = {
            "type": "process",
            "kind": "decision",
            "executor": "llm",
            "effect": "none",
            "action": "llm_prompt",
            "params": {
                "input": "brief",
                "output": "generated",
                "prompt": "请根据用户输入完成任务。",
                "preset_config": {"target": "生成发布摘要", "format": "JSON"},
            },
        }

        with patch(
            "core.llm.config_manager.resolve_model",
            return_value=SimpleNamespace(api_key="", provider_id="", model="", timeout=30),
        ):
            result = LabNodeExecutor().execute("generate", state, state_doc, {"inputs": {}}, ".")

        self.assertEqual("llm_prompt", result["action"])
        self.assertEqual("missing_api_key", result["fallback"])
        self.assertIsInstance(state_doc["context"]["store"]["generated"], str)
        self.assertEqual("Launch plan", json.loads(state_doc["context"]["store"]["generated"])["title"])

    def test_delivery_process_collects_declared_outputs_and_artifacts(self):
        state_doc = {"context": {"store": {}}}
        state = {
            "type": "process", "kind": "delivery", "executor": "deterministic", "effect": "none",
            "action": "collect_artifacts",
            "inputs": {
                "brief": {"required": True, "binding": {"source": "constant", "value": {"script": "ready"}}},
                "approval": {"required": True, "binding": {"source": "constant", "value": {"status": "approved"}}},
            },
            "outputs": {"delivery": {"target": {"type": "store", "key": "delivery"}}},
        }
        result = LabNodeExecutor().execute("deliver", state, state_doc, {"artifacts": [{"name": "preview.mp4"}]}, ".")
        self.assertEqual("collect_artifacts", result["action"])
        self.assertEqual({"brief", "approval"}, set(state_doc["context"]["store"]["delivery"]["items"]))
        self.assertEqual([{"name": "preview.mp4"}], state_doc["context"]["store"]["delivery"]["artifacts"])

    def test_video_render_action_is_registered(self):
        result = LabNodeExecutor().execute(
            "render",
            {"type": "process", "action": "render_video_brief", "params": {"output": "video"}},
            {"context": {"store": {}}},
            {"run_id": "test_video", "artifacts": []},
            ".",
        )
        self.assertEqual("render_video_brief", result["action"])
        self.assertEqual("INPUT_REQUIRED", result["error_code"])

    def test_node_llm_options_are_preserved_for_runtime_budgeting(self):
        normalized = normalize_runtime_node({
            "type": "process",
            "kind": "decision",
            "llm_options": {"timeout_seconds": 45, "max_tokens": 1200},
        })
        self.assertEqual({"timeout_seconds": 45, "max_tokens": 1200}, normalized["params"]["llm_options"])

    def test_transfer_process_passes_result(self):
        state_doc = {"context": {"store": {"brief": {"episode_id": "ep_001"}}}}
        state = {
            "type": "process",
            "protocol_version": "0.6",
            "kind": "transfer",
            "executor": "deterministic",
            "effect": "writes_store",
            "input": "brief",
            "output": "brief_copy",
        }
        result = LabNodeExecutor().execute("transfer", state, state_doc, {"inputs": {}}, ".")
        self.assertEqual("pass_result", result["action"])
        self.assertEqual({"episode_id": "ep_001"}, state_doc["context"]["store"]["brief_copy"])

    def test_html_ui_uses_string_input_as_html(self):
        html = "<main><h1>Expanded result</h1></main>"
        state_doc = {"context": {"store": {"expanded_html": html}}}
        state = {
            "type": "process",
            "kind": "ui",
            "executor": "deterministic",
            "effect": "writes_store",
            "action": "show_ui",
            "input": "expanded_html",
            "output": "result_page",
            "params": {"ui_type": "html"},
        }

        result = LabNodeExecutor().execute("show_result", state, state_doc, {"inputs": {}}, ".")

        self.assertEqual("html", result["ui_type"])
        self.assertEqual(html, result["ui_html"])
        self.assertEqual("", result["ui_markdown"])
        self.assertEqual(html, state_doc["context"]["store"]["result_page"]["html"])

    def test_rules_decision_maps_to_custom_action(self):
        state_doc = {"context": {"store": {"brief": "episode brief"}}}
        state = {
            "type": "process",
            "protocol_version": "0.6",
            "kind": "decision",
            "executor": "rules",
            "effect": "none",
            "input": "brief",
            "output": "decision",
        }
        result = LabNodeExecutor().execute("decide", state, state_doc, {"inputs": {}}, ".")
        self.assertEqual("custom_action", result["action"])
        self.assertIn("episode brief", state_doc["context"]["store"]["decision"])

    def test_read_only_process_rejects_side_effecting_tool(self):
        state_doc = {"context": {"store": {}}}
        run = {
            "inputs": {},
            "mcp_tools": [{
                "id": "write_note",
                "type": "builtin",
                "server": "filesystem",
                "tool": "write_file",
                "contract": {"side_effect": "writes_files"},
            }],
        }
        state = {
            "type": "process",
            "protocol_version": "0.6",
            "kind": "mcp_read",
            "executor": "mcp",
            "effect": "read_only",
            "mcp_binding": {"mode": "read_only", "allowed_tools": ["write_note"]},
            "output": "read_result",
        }
        with self.assertRaisesRegex(RuntimeError, "side-effecting tool"):
            LabNodeExecutor(ROOT).execute("unsafe_read", state, state_doc, run, ".")

    def test_execute_process_consumes_tool_plan(self):
        with tempfile.TemporaryDirectory(prefix="cartridgeflow-tool-plan-") as temp_dir:
            workspace = Path(temp_dir)
            target = workspace / "tool_plan_runtime.txt"
            state_doc = {
                "context": {
                    "store": {
                        "plan": {
                            "schema": "tool_plan.v1",
                            "tool_id": "write_note",
                            "params": {"path": "tool_plan_runtime.txt", "content": "tool plan ok"},
                            "expected_output": "write_result",
                            "failure_policy": "fail_closed",
                        }
                    }
                }
            }
            run = {
                "inputs": {},
                "mcp_tools": [{
                    "id": "write_note",
                    "type": "builtin",
                    "server": "filesystem",
                    "tool": "write_file",
                    "required": True,
                    "contract": {"side_effect": "writes_files"},
                    "params_schema": {
                        "type": "object",
                        "required": ["path", "content"],
                        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    },
                }],
            }
            state = {
                "type": "process",
                "protocol_version": "0.6",
                "kind": "mcp_execute",
                "executor": "mcp",
                "effect": "writes_files",
                "tool_binding": "from_tool_plan",
                "allowed_tools": ["write_note"],
                "failure_policy": "fail_closed",
                "permission": "write_run_artifacts",
                "audit_log": True,
                "input": "plan",
                "output": "write_result",
            }
            result = LabNodeExecutor(workspace).execute("write_note", state, state_doc, run, workspace)
            self.assertEqual("tool_call", result["action"])
            self.assertTrue(target.is_file())
            self.assertEqual("tool plan ok", target.read_text(encoding="utf-8"))
            self.assertIn("write_result", state_doc["context"]["store"])

    def test_deterministic_cartridge_runs_input_decision_tool_delivery_and_artifact_history(self):
        manifest = {
            **current_manifest(),
            "id": "test.deterministic.chain",
            "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.8"},
            "inputs": [{"id": "request", "type": "text", "required": True}],
            "llm_recipe": {"schema": "cartridgeflow.llm_recipe.v1", "roles": []},
            "mcp_tools": [{
                "id": "write_artifact",
                "type": "builtin",
                "server": "filesystem",
                "tool": "write_file",
                "enabled": True,
                "contract": {
                    "idempotent": True,
                    "side_effect": "writes_run_artifacts",
                    "retry_policy": {"max_attempts": 1},
                },
            }],
            "delivery": {"type": "summary_with_artifacts", "primary_output": "delivery"},
        }
        decision_contract = {
            "schema": "decision_envelope.v1",
            "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
            "on_needs_user_input": "pause",
            "interaction": {
                "store_key": "decision_reply",
                "input_schema": {"type": "object"},
                "resume_policy": "resume_same_node",
            },
            "consume": {
                "mode": "payload_path",
                "path": "payload.decision",
                "as": "decision_payload",
                "required": True,
                "on_missing": "fail_closed",
            },
        }
        flow = {
            "schema_version": "1.0",
            "id": "test.deterministic.chain.root",
            "protocol": {"id": "CF-FARP", "version": "0.8"},
            "start": "start",
            "states": {
                "start": {"type": "system", "next": "collect"},
                "collect": {
                    "type": "process", "kind": "input", "executor": "user", "effect": "writes_store",
                    "input_kind": "initial", "source": "user_form", "input_schema": {"fields": ["request"]},
                    "output": "brief", "next": "prepare",
                },
                "prepare": {
                    "type": "process", "kind": "transfer", "executor": "deterministic", "effect": "writes_store",
                    "input": "brief", "output": "prepared", "next": "decide",
                },
                "decide": {
                    "type": "process", "kind": "decision", "executor": "llm", "effect": "none",
                    "input": "prepared", "output": "decision", "output_contract": "decision_envelope.v1",
                    "decision_test_mode": "mock_resolved", "decision_contract": decision_contract, "next": "write",
                },
                "write": {
                    "type": "process", "kind": "mcp_execute", "executor": "mcp", "effect": "writes_artifacts",
                    "action": "tool_call", "input": "decision_payload", "output": "write_result",
                    "tool_binding": "write_artifact", "allowed_tools": ["write_artifact"],
                    "mcp_binding": {"mode": "execute", "allowed_tools": ["write_artifact"]},
                    "failure_policy": "fail_closed", "permission": "write_run_artifacts", "audit_log": True,
                    "tools": [{
                        "type": "builtin", "server": "filesystem", "tool": "write_file",
                        "mcp_tool_id": "write_artifact", "output": "write_result",
                        "params": {"path": "outputs/final.json", "content": "store:decision_payload"},
                    }],
                    "next": "store_delivery",
                },
                "store_delivery": {
                    "type": "process", "kind": "delivery", "executor": "deterministic", "effect": "writes_store",
                    "input": "write_result", "output": "delivery", "primary_output": "delivery", "next": "delivery",
                },
                "delivery": {"type": "system", "next": "complete"},
                "complete": {"type": "terminal"},
            },
        }

        class Registry:
            def get_cartridge(self, cartridge_id):
                if cartridge_id != manifest["id"]:
                    raise FileNotFoundError(cartridge_id)
                return {
                    "id": manifest["id"],
                    "manifest": manifest,
                    "root_flow": flow,
                    "package_path": str(ROOT),
                }

        with tempfile.TemporaryDirectory(prefix="cartridgeflow-deterministic-chain-") as temp_dir:
            runner = CartridgeRunner(Path(temp_dir), Registry())
            runner.build_compatibility_report = lambda *args, **kwargs: {
                "ok": True, "status": "compatible", "legacy": False,
                "base": {}, "protocol": {}, "summary": {}, "findings": [],
            }

            with patch("core.cartridge.runner.build_model_binding_report", return_value={"status": "ok", "items": []}):
                run = runner.create_run(
                    manifest["id"],
                    {"request": "produce a deterministic artifact"},
                    run_id="run_deterministic_chain",
                    test_mode={"decision": "mock_resolved"},
                )

            self.assertEqual("completed", run["status"], run)
            self.assertEqual("complete", run["current_state"])
            self.assertEqual("mock_resolved", run["test_mode"]["decision"])
            self.assertEqual(1, len(run["artifacts"]))
            artifact = run["artifacts"][0]
            self.assertEqual("write", artifact["source"]["node_id"])
            artifact_path = runner.artifact_manager.resolve_artifact_path(run, artifact["name"])
            self.assertTrue(artifact_path.is_file())
            self.assertIn('"mock": true', artifact_path.read_text(encoding="utf-8"))
            self.assertEqual([artifact], run["delivery"]["artifacts"])
            self.assertEqual(artifact["url"], run["delivery"]["actions"][0]["url"])

            stored_run = runner.get_run(run["run_id"])
            self.assertEqual("completed", stored_run["status"])
            self.assertIn(run["run_id"], [item["run_id"] for item in runner.list_runs()])
            events = runner.get_events(run["run_id"])
            self.assertIn("run_completed", [event["type"] for event in events])
            tool_event = next(event for event in events if event["type"] == "lab_node_executed" and event["state"] == "write")
            self.assertEqual("tool_call", tool_event["data"]["action"])
            self.assertTrue(tool_event["data"]["tool_results"][0]["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
