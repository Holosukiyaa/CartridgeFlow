"""Seed and execute the Lite workbench's deterministic node coverage cartridges.

Each run is started through the same /api/lab/flows/{id}/test-run endpoint used
by the workbench's Run button. The resulting records therefore remain visible
in the normal in-product history panel.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.lab.dev_flow import DevFlowManager  # noqa: E402


BASE_URL = "http://127.0.0.1:8765"


def process(title: str, *, kind: str, executor: str, effect: str, action: str, next_state: str, params: dict | None = None, **extra) -> dict:
    node_params = {"node_category": kind, **(params or {})}
    protocol_fields = {}
    if kind == "input":
        protocol_fields = {
            "input_kind": "initial",
            "source": "user_form",
            "input_schema": {"type": "object", "fields": ["title", "description"]},
        }
    return {
        "type": "process",
        "title": title,
        "display_name": title,
        "kind": kind,
        "executor": executor,
        "effect": effect,
        "action": action,
        **protocol_fields,
        **{key: node_params[key] for key in ("component_ref", "interaction_mode", "input_binding", "input_schema", "source", "input_kind", "allowed_tools", "mcp_binding", "tool_binding", "failure_policy", "permission", "audit_log", "primary_output", "resource_role", "timeout_ms", "replay_policy") if key in node_params},
        "params": node_params,
        "next": next_state,
        **extra,
    }


def terminal() -> dict:
    return {"type": "terminal", "title": "完成", "display_name": "完成", "locked": True}


def start(next_state: str) -> dict:
    return {"type": "system", "title": "开始", "display_name": "开始", "action": "start", "locked": True, "next": next_state}


def flow(flow_id: str, states: dict) -> dict:
    return {
        "schema_version": "1.0",
        "id": f"{flow_id}.root",
        "name": f"{flow_id} 节点覆盖流程",
        "mode": "lifecycle",
        "cartridge_id": flow_id,
        "protocol": {"id": "CF-FARP", "version": "0.7"},
        "start": "start",
        "states": states,
    }


def coverage_definitions() -> list[tuple[str, str, str, dict]]:
    return [
        (
            "dev.coverage-01-input-transfer",
            "01 输入与传递",
            "覆盖输入收集、字段映射和传递节点。",
            flow("dev.coverage-01-input-transfer", {
                "start": start("collect"),
                "collect": process("收集输入", kind="input", executor="user", effect="writes_store", action="collect_inputs", next_state="transfer", params={"output": "brief", "preset_config": {"fields": "title,description", "output_name": "brief"}}),
                "transfer": process("传递摘要", kind="transfer", executor="deterministic", effect="writes_store", action="pass_result", next_state="complete", params={"input": "brief", "output": "final", "preset_config": {"from": "brief", "to": "final"}}),
                "complete": terminal(),
            }),
        ),
        (
            "dev.coverage-02-interaction-display",
            "02 交互展示",
            "覆盖被动 HTML 交互组件、资产注册和展示节点。",
            flow("dev.coverage-02-interaction-display", {
                "start": start("show"),
                "show": process("展示欢迎界面", kind="interaction", executor="deterministic", effect="none", action="render_interaction", next_state="complete", params={"component_ref": "welcome.panel", "interaction_mode": "display", "input_binding": {}}),
                "complete": terminal(),
            }),
        ),
        (
            "dev.coverage-03-decision-rules",
            "03 决策与转换",
            "覆盖无需模型密钥的规则决策、转换和结果传递。",
            flow("dev.coverage-03-decision-rules", {
                "start": start("collect"),
                "collect": process("收集决策材料", kind="input", executor="user", effect="writes_store", action="collect_inputs", next_state="decision", params={"output": "source", "preset_config": {"fields": "title,description", "output_name": "source"}}),
                "decision": process("规则决策", kind="decision", executor="rules", effect="none", action="custom_action", next_state="transform", params={"input": "source", "output": "decision_result"}),
                "transform": process("转换决策结果", kind="transform", executor="deterministic", effect="writes_store", action="custom_action", next_state="complete", params={"input": "decision_result", "output": "transformed_result"}),
                "complete": terminal(),
            }),
        ),
        (
            "dev.coverage-04-retrieval-validation-routing",
            "04 检索校验与路由",
            "覆盖检索、校验、路由等规则型节点。",
            flow("dev.coverage-04-retrieval-validation-routing", {
                "start": start("collect"),
                "collect": process("收集内容", kind="input", executor="user", effect="writes_store", action="collect_inputs", next_state="retrieve", params={"output": "source", "preset_config": {"fields": "title,description", "output_name": "source"}}),
                "retrieve": process("检索上下文", kind="retrieval", executor="deterministic", effect="writes_store", action="custom_action", next_state="validate", params={"input": "source", "output": "retrieved"}),
                "validate": process("校验结果", kind="validation", executor="rules", effect="none", action="custom_action", next_state="route", params={"input": "retrieved", "output": "validated"}),
                "route": process("路由结果", kind="routing", executor="rules", effect="none", action="custom_action", next_state="complete", params={"input": "validated", "output": "route_result"}),
                "complete": terminal(),
            }),
        ),
        (
            "dev.coverage-05-gate-checkpoint",
            "05 自动门禁",
            "覆盖自动批准的门禁和检查点状态记录。",
            flow("dev.coverage-05-gate-checkpoint", {
                "start": start("gate"),
                "gate": process("自动门禁", kind="gate", executor="rules", effect="none", action="confirm_checkpoint", next_state="complete", params={"condition": "覆盖测试：自动批准", "output": "gate_result"}),
                "complete": terminal(),
            }),
        ),
        (
            "dev.coverage-06-context-delivery",
            "06 上下文与交付",
            "覆盖上下文保存、合并和交付主输出。",
            flow("dev.coverage-06-context-delivery", {
                "start": start("collect"),
                "collect": process("收集交付内容", kind="input", executor="user", effect="writes_store", action="collect_inputs", next_state="save", params={"output": "source", "preset_config": {"fields": "title,description", "output_name": "source"}}),
                "save": process("保存上下文", kind="delivery", executor="deterministic", effect="writes_store", action="save_context", next_state="deliver", params={"input": "source", "output": "delivery_context", "primary_output": "delivery_context", "preset_config": {"key": "delivery_context", "source": "source"}}),
                "deliver": process("交付输出", kind="delivery", executor="deterministic", effect="writes_store", action="pass_result", next_state="complete", params={"input": "delivery_context", "output": "html", "primary_output": "html", "preset_config": {"from": "delivery_context", "to": "html"}}),
                "complete": terminal(),
            }),
        ),
        (
            "dev.coverage-07-mcp-read-write",
            "07 MCP 文件读写",
            "覆盖真实的运行目录文件写入、读取、工具审计与产物收集。",
            flow("dev.coverage-07-mcp-read-write", {
                "start": start("collect"),
                "collect": process("收集文件内容", kind="input", executor="user", effect="writes_store", action="collect_inputs", next_state="write", params={"output": "payload", "preset_config": {"fields": "title,description", "output_name": "payload"}}),
                "write": process("MCP 写入文件", kind="mcp_execute", executor="mcp", effect="writes_files", action="tool_call", next_state="read", params={"output": "write_result", "tool_binding": "static_params", "allowed_tools": ["filesystem_write"], "failure_policy": "fail_closed", "permission": "write_run_artifacts", "audit_log": True, "preset_config": {"mcp_tool_id": "filesystem_write", "output_name": "write_result", "params": {"path": "coverage/result.txt", "content": "coverage-write-ok"}}}),
                "read": process("MCP 读取文件", kind="mcp_read", executor="mcp", effect="read_only", action="tool_call", next_state="complete", params={"output": "read_result", "allowed_tools": ["filesystem_read"], "mcp_binding": {"mode": "read_only", "allowed_tools": ["filesystem_read"]}, "preset_config": {"mcp_tool_id": "filesystem_read", "output_name": "read_result", "params": {"path": "coverage/result.txt"}}}),
                "complete": terminal(),
            }),
        ),
        (
            "dev.coverage-08-remote-adapter",
            "08 远程适配器调度",
            "覆盖远程执行节点的统一适配器调度；测试目标使用本机安全文件读取工具。",
            flow("dev.coverage-08-remote-adapter", {
                "start": start("remote"),
                "remote": process("远程适配器调用", kind="remote_call", executor="remote", effect="external_side_effect", action="remote_call", next_state="complete", params={"output": "remote_result", "remote_service": "coverage-local-adapter", "resource_role": "coverage_local_adapter", "allowed_tools": ["filesystem_read"], "timeout_ms": 10000, "failure_policy": "fail_closed", "replay_policy": "requires_confirmation", "permission": "external_service_call", "audit_log": True, "preset_config": {"preset": "remote_call", "server": "filesystem", "tool": "list_dir", "params": {"path": "."}, "output_name": "remote_result"}}),
                "complete": terminal(),
            }),
        ),
        (
            "dev.coverage-09-human-gate-resume",
            "09 人工门禁续跑",
            "覆盖真实暂停、提交答案、从检查点恢复和完成。",
            flow("dev.coverage-09-human-gate-resume", {
                "start": start("gate"),
                "gate": process("人工确认", kind="human_gate", executor="human", effect="writes_store", action="confirm_checkpoint", next_state="complete", params={"output": "approval", "interaction": {"id": "coverage_approval", "store_key": "coverage_answer", "prompt": "覆盖测试确认继续", "input_schema": {"type": "object", "properties": {"approval": {"type": "string"}}}, "resume_policy": "resume_same_node"}}),
                "complete": terminal(),
            }),
        ),
    ]


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def seed_flows() -> list[dict]:
    manager = DevFlowManager(ROOT)
    result = []
    for flow_id, name, description, root_flow in coverage_definitions():
        path = manager.dev_dir / flow_id
        if not path.exists():
            manager.create_flow(flow_id, name, description)
        manifest_path = path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({"name": name, "description": description})
        manifest["outputs"] = [{"id": "html", "label": "覆盖测试输出", "type": "json", "required": False}]
        manifest["delivery"] = {"type": "summary", "primary_output": "html", "show_artifacts": True}
        write_json(manifest_path, manifest)
        write_json(path / "root.flow.json", root_flow)
        result.append({"id": flow_id, "name": name, "description": description})
    return result


def request_json(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url}: {exc.code} {detail}") from exc


def wait_for_terminal(base_url: str, run_id: str, timeout_seconds: int = 45) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            run = request_json("GET", f"{base_url}/api/cartridge-runs/{run_id}")
        except RuntimeError as exc:
            if " 404 " not in str(exc):
                raise
            time.sleep(0.25)
            continue
        if run.get("status") not in {"created", "running", "recovering", "retrying", "rolling_back"}:
            return run
        time.sleep(0.25)
    raise TimeoutError(f"Run timed out: {run_id}")


def run_coverage(base_url: str, seeded: list[dict]) -> list[dict]:
    results = []
    for item in seeded:
        started = request_json("POST", f"{base_url}/api/lab/flows/{item['id']}/test-run", {"inputs": {"title": item["name"], "description": item["description"]}})
        run = wait_for_terminal(base_url, started["run"]["run_id"])
        if run.get("status") == "paused_waiting_user":
            request_json("POST", f"{base_url}/api/cartridge-runs/{run['run_id']}/pending-interaction/answer", {"values": {"approval": "approve"}})
            run = wait_for_terminal(base_url, run["run_id"])
        results.append({"id": item["id"], "run_id": run["run_id"], "status": run.get("status"), "state": run.get("current_state"), "errors": run.get("errors", [])})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args()
    seeded = seed_flows()
    if args.seed_only:
        print(json.dumps({"seeded": seeded}, ensure_ascii=False, indent=2))
        return 0
    results = run_coverage(args.base_url.rstrip("/"), seeded)
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    failed = [item for item in results if item["status"] != "completed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
