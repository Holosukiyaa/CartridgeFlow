"""Stable runtime error identities shared by runs, events, and HTTP responses."""

from __future__ import annotations

import json
import re
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ERROR_SCHEMA = "runtime_error_envelope.v1"


@dataclass(frozen=True)
class ErrorSpec:
    category: str
    message: str
    retryable: bool
    recoverable: bool
    recovery_actions: tuple[str, ...]
    http_status: int = 500


ERROR_CATALOG: dict[str, ErrorSpec] = {
    "INPUT_REQUIRED": ErrorSpec("input", "缺少继续运行所需的输入。", False, True, ("provide_input", "retry_node"), 400),
    "DECISION_ENVELOPE_INVALID": ErrorSpec("decision", "模型返回的决策格式不符合节点契约。", True, True, ("retry_node", "edit_node_contract"), 422),
    "DECISION_CONSUME_FAILED": ErrorSpec("decision", "决策已经生成，但下游需要的数据无法提取。", False, True, ("inspect_decision", "edit_consume_contract", "retry_node"), 422),
    "PROVIDER_CONFIGURATION_MISSING": ErrorSpec("provider", "当前模型配方还没有连接可用的本地模型配置。", False, True, ("configure_provider", "switch_provider"), 409),
    "PROVIDER_AUTH_FAILED": ErrorSpec("provider", "模型服务拒绝了当前凭据。", False, True, ("update_credentials", "switch_provider"), 401),
    "PROVIDER_RATE_LIMITED": ErrorSpec("provider", "模型服务当前请求过于频繁。", True, True, ("retry_node", "switch_provider"), 429),
    "PROVIDER_TIMEOUT": ErrorSpec("provider", "模型服务在限定时间内没有响应。", True, True, ("retry_node", "switch_provider"), 504),
    "PROVIDER_UNAVAILABLE": ErrorSpec("provider", "模型服务当前不可用。", True, True, ("retry_node", "switch_provider"), 503),
    "PROVIDER_EMPTY_RESPONSE": ErrorSpec("provider", "模型调用完成，但没有返回可用内容。", True, True, ("retry_node", "switch_provider"), 502),
    "TOOL_TIMEOUT": ErrorSpec("tool", "工具执行超过了允许时间。", True, True, ("retry_node", "inspect_tool"), 504),
    "TOOL_WORKER_CRASHED": ErrorSpec("tool", "卡带工具 Worker 意外退出。", True, True, ("retry_node", "inspect_worker_log"), 502),
    "TOOL_CANCELLED": ErrorSpec("tool", "工具调用已随运行取消。", False, False, (), 409),
    "TOOL_HOST_EXITED": ErrorSpec("tool", "宿主退出时终止了工具 Worker。", True, True, ("resume_checkpoint", "retry_node"), 503),
    "TOOL_EXECUTION_FAILED": ErrorSpec("tool", "工具没有完成当前节点要求的操作。", False, True, ("inspect_tool", "retry_node"), 422),
    "PERMISSION_DENIED": ErrorSpec("permission", "当前操作缺少必要权限。", False, True, ("review_permissions",), 403),
    "ARTIFACT_MISSING": ErrorSpec("artifact", "运行需要的产物不存在或已经失效。", False, True, ("rebuild_artifact", "retry_source_node"), 404),
    "DELIVERY_OUTPUT_MISSING": ErrorSpec("artifact", "流程结束时没有生成声明的主要交付结果。", False, True, ("inspect_source_node", "retry_source_node"), 422),
    "DEPENDENCY_UNAVAILABLE": ErrorSpec("dependency", "运行依赖的外部能力当前不可用。", True, True, ("check_dependency", "retry_node"), 503),
    "FLOW_CONTRACT_INVALID": ErrorSpec("flow", "流程或节点配置不符合当前运行契约。", False, True, ("edit_flow", "validate_flow"), 422),
    "REPLAY_CONFIRMATION_REQUIRED": ErrorSpec("recovery", "恢复路径包含不可安全重放的副作用，需要开发者明确确认。", False, True, ("confirm_replay", "choose_safe_checkpoint"), 409),
    "NODE_EXECUTION_FAILED": ErrorSpec("runtime", "节点执行失败。", False, True, ("inspect_node", "retry_node"), 422),
    "RESOURCE_NOT_FOUND": ErrorSpec("request", "请求的资源不存在。", False, False, (), 404),
    "REQUEST_INVALID": ErrorSpec("request", "请求内容不符合接口要求。", False, True, ("edit_request",), 400),
    "INTERNAL_UNEXPECTED": ErrorSpec("system", "底座发生了未预期的内部错误。", False, False, ("export_diagnostics",), 500),
}


class RuntimeFailure(Exception):
    def __init__(self, envelope: dict):
        self.envelope = envelope
        super().__init__(str(envelope.get("message") or envelope.get("code") or "Runtime failure"))

    @property
    def status_code(self) -> int:
        return int(self.envelope.get("http_status") or 500)


def build_runtime_error(
    code: str | None = None,
    *,
    exception: Exception | None = None,
    run_id: str | None = None,
    node_id: str | None = None,
    source: str = "runtime",
    missing_inputs=None,
    recovery_actions=None,
    cause_chain=None,
    context: dict | None = None,
) -> dict:
    stable_code = code if code in ERROR_CATALOG else classify_exception(exception, source)
    spec = ERROR_CATALOG.get(stable_code, ERROR_CATALOG["INTERNAL_UNEXPECTED"])
    normalized_missing = _normalize_missing_inputs(missing_inputs)
    causes = _normalize_cause_chain(cause_chain)
    if exception is not None:
        causes = [*_exception_chain(exception), *causes]
    actions = list(recovery_actions) if isinstance(recovery_actions, (list, tuple)) else list(spec.recovery_actions)
    envelope = {
        "schema": ERROR_SCHEMA,
        "error_id": f"err_{uuid.uuid4().hex[:16]}",
        "code": stable_code,
        "category": spec.category,
        "message": spec.message,
        "run_id": str(run_id or ""),
        "node_id": str(node_id or ""),
        "source": str(source or "runtime"),
        "missing_inputs": normalized_missing,
        "retryable": spec.retryable,
        "recoverable": spec.recoverable,
        "recovery_actions": actions,
        "cause_chain": causes,
        "http_status": spec.http_status,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    if context:
        envelope["context"] = _public_context(context)
    return envelope


def error_from_node_result(result: dict, *, run_id: str, node_id: str, source: str = "runtime.node") -> dict:
    missing = [item for item in result.get("missing_inputs") or [] if isinstance(item, dict) and item.get("required")]
    code = str(result.get("error_code") or "")
    if code not in ERROR_CATALOG:
        if missing:
            code = "INPUT_REQUIRED"
        elif (result.get("decision_consume") or {}).get("failed"):
            code = "DECISION_CONSUME_FAILED"
        elif str(result.get("fallback") or "") == "missing_api_key":
            code = "PROVIDER_CONFIGURATION_MISSING"
        elif str(result.get("fallback") or "").startswith("llm_error"):
            code = _provider_code(result.get("provider_error") or {})
        elif _decision_error_code(result):
            code = _decision_error_code(result)
        else:
            code = _tool_error_code(result) or "NODE_EXECUTION_FAILED"
    raw_cause = str(result.get("error") or result.get("reason") or "").strip()
    causes = [{"type": str(result.get("error_type") or "NodeResult"), "message": raw_cause}] if raw_cause else []
    return build_runtime_error(
        code,
        run_id=run_id,
        node_id=node_id,
        source=source,
        missing_inputs=missing,
        cause_chain=causes,
        context={
            "action": result.get("action"),
            "provider_id": result.get("provider_id"),
            "model": result.get("model"),
        },
    )


def classify_exception(exception: Exception | None, source: str = "runtime") -> str:
    if exception is None:
        return "INTERNAL_UNEXPECTED"
    status_code = getattr(exception, "status_code", None)
    lowered_source = str(source).lower()
    lowered = str(exception).lower()
    if isinstance(exception, PermissionError) or status_code == 403:
        return "PERMISSION_DENIED"
    if status_code == 401:
        return "PROVIDER_AUTH_FAILED" if "provider" in lowered_source or "llm" in lowered_source else "PERMISSION_DENIED"
    if status_code == 429:
        return "PROVIDER_RATE_LIMITED"
    if isinstance(exception, (TimeoutError,)) or "timed out" in lowered or "timeout" in lowered:
        return "PROVIDER_TIMEOUT" if "provider" in lowered_source or "llm" in lowered_source else "TOOL_TIMEOUT"
    if status_code in {500, 502, 503, 504} and ("provider" in lowered_source or "llm" in lowered_source):
        return "PROVIDER_UNAVAILABLE"
    if isinstance(exception, FileNotFoundError):
        return "ARTIFACT_MISSING" if "artifact" in lowered_source else "RESOURCE_NOT_FOUND"
    if isinstance(exception, ConnectionError):
        return "DEPENDENCY_UNAVAILABLE"
    return "INTERNAL_UNEXPECTED"


def write_diagnostic(
    directory: str | Path,
    envelope: dict,
    exception: Exception,
    context: dict | None = None,
    *,
    exact_directory: bool = False,
) -> Path:
    target_dir = Path(directory) if exact_directory else Path(directory) / "diagnostics"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{envelope['error_id']}.json"
    payload = {
        "schema": "cartridgeflow.runtime_diagnostic.v1",
        "error": envelope,
        "exception_type": exception.__class__.__name__,
        "exception_message": str(exception),
        "traceback": "".join(traceback.format_exception(type(exception), exception, exception.__traceback__)),
        "context": context or {},
    }
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)
    return target


def _provider_code(provider_error: dict) -> str:
    status = provider_error.get("status_code")
    if status == 401 or status == 403:
        return "PROVIDER_AUTH_FAILED"
    if status == 429:
        return "PROVIDER_RATE_LIMITED"
    if status in {500, 502, 503, 504}:
        return "PROVIDER_UNAVAILABLE"
    message = str(provider_error.get("message") or "").lower()
    if "timeout" in message or "timed out" in message:
        return "PROVIDER_TIMEOUT"
    return "PROVIDER_UNAVAILABLE"


def _decision_error_code(result: dict) -> str:
    envelope = result.get("decision_envelope") if isinstance(result.get("decision_envelope"), dict) else {}
    issues = envelope.get("issues") if isinstance(envelope.get("issues"), list) else []
    issue_codes = {str(item.get("code") or "") for item in issues if isinstance(item, dict)}
    if "llm_empty_response" in issue_codes:
        return "PROVIDER_EMPTY_RESPONSE"
    if issue_codes & {"decision_envelope_parse_failed", "decision_envelope_validation_failed"}:
        return "DECISION_ENVELOPE_INVALID"
    if result.get("decision_validation_errors"):
        return "DECISION_ENVELOPE_INVALID"
    return ""


def _tool_error_code(result: dict) -> str:
    for item in result.get("tool_results") or []:
        if not isinstance(item, dict):
            continue
        tool_result = item.get("result") if isinstance(item.get("result"), dict) else item
        if tool_result.get("ok") is not False:
            continue
        tool_code = str(tool_result.get("code") or "").lower()
        if tool_code in {"dlc_worker_timeout", "tool_timeout"}:
            return "TOOL_TIMEOUT"
        if tool_code in {"dlc_worker_failed", "dlc_worker_invalid_response"}:
            return "TOOL_WORKER_CRASHED"
        if tool_code in {"dlc_worker_cancelled", "tool_cancelled"}:
            return "TOOL_CANCELLED"
        if tool_code == "dlc_worker_host_exited":
            return "TOOL_HOST_EXITED"
        if tool_code in {"permission_denied", "forbidden"}:
            return "PERMISSION_DENIED"
        if tool_code in {"extension_inactive", "dependency_unavailable"}:
            return "DEPENDENCY_UNAVAILABLE"
        return "TOOL_EXECUTION_FAILED"
    return ""


def _normalize_missing_inputs(items) -> list[str]:
    result = []
    for item in items if isinstance(items, list) else []:
        value = item.get("key") if isinstance(item, dict) else item
        value = str(value or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def _exception_chain(exception: Exception) -> list[dict]:
    result = []
    current = exception
    seen = set()
    while current is not None and id(current) not in seen and len(result) < 8:
        seen.add(id(current))
        result.append({"type": current.__class__.__name__, "message": _redact(str(current))})
        current = current.__cause__ or current.__context__
    return result


def _normalize_cause_chain(items) -> list[dict]:
    result = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            result.append({"type": str(item.get("type") or "Error"), "message": _redact(str(item.get("message") or ""))})
        elif item:
            result.append({"type": "Error", "message": _redact(str(item))})
    return result[:8]


def _public_context(context: dict) -> dict:
    allowed = {"action", "provider_id", "model", "tool", "server", "status_code"}
    return {key: context.get(key) for key in allowed if context.get(key) not in (None, "")}


def _redact(message: str) -> str:
    value = str(message or "")[:1000]
    value = re.sub(r"(?i)(api[_-]?key|authorization|token|secret)\s*[:=]\s*\S+", r"\1=[redacted]", value)
    value = re.sub(r"(?i)bearer\s+[a-z0-9._~+/-]+", "Bearer [redacted]", value)
    return value
