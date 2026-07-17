from __future__ import annotations

import json
import re
from typing import Any


DECISION_ENVELOPE_SCHEMA = "decision_envelope.v1"
DECISION_STATUSES = {"resolved", "needs_user_input", "blocked"}
RESUME_POLICIES = {
    "resume_same_node",
    "resume_next_node",
    "resume_target_node",
    "restart_run_with_inputs",
    "manual_only",
}


def parse_decision_envelope(value: Any) -> dict | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def validate_decision_envelope(envelope: Any, decision_contract: dict | None = None) -> list[dict]:
    findings: list[dict] = []
    if not isinstance(envelope, dict):
        return [_finding("blocker", "decision_envelope_not_object", "decision_envelope.v1 output must be an object.")]

    schema = envelope.get("schema")
    if schema != DECISION_ENVELOPE_SCHEMA:
        findings.append(_finding("blocker", "decision_envelope_schema_invalid", "decision envelope schema must be decision_envelope.v1."))

    status = str(envelope.get("status") or "").strip()
    if status not in DECISION_STATUSES:
        findings.append(_finding("blocker", "decision_envelope_status_invalid", "decision envelope status must be resolved, needs_user_input, or blocked."))

    summary = envelope.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        findings.append(_finding("blocker", "decision_envelope_summary_missing", "decision envelope must include a non-empty summary."))

    contract = decision_contract if isinstance(decision_contract, dict) else {}
    allowed_statuses = _string_list(contract.get("allowed_statuses"))
    if allowed_statuses and status and status not in allowed_statuses:
        findings.append(_finding("blocker", "decision_envelope_status_not_allowed", f"decision status is not allowed by node contract: {status}"))

    if status == "resolved":
        payload = envelope.get("payload")
        if payload is not None and not isinstance(payload, dict):
            findings.append(_finding("blocker", "decision_envelope_payload_invalid", "resolved decision payload must be an object when present."))

    if status == "needs_user_input":
        findings.extend(_validate_question(envelope.get("question")))
        findings.extend(_validate_resume(envelope.get("resume")))

    if status == "blocked":
        issues = envelope.get("issues")
        if issues is not None and not isinstance(issues, list):
            findings.append(_finding("blocker", "decision_envelope_issues_invalid", "blocked decision issues must be an array when present."))

    return findings


def make_blocked_decision_envelope(code: str, message: str, raw_output: str = "") -> dict:
    envelope = {
        "schema": DECISION_ENVELOPE_SCHEMA,
        "status": "blocked",
        "summary": message,
        "issues": [
            {
                "severity": "blocker",
                "code": code,
                "message": message,
            }
        ],
    }
    if raw_output:
        envelope["raw_output"] = raw_output[:4000]
    return envelope


def make_mock_decision_envelope(status: str = "resolved", summary: str = "Mock decision resolved.", payload: dict | None = None) -> dict:
    status = status if status in DECISION_STATUSES else "resolved"
    envelope = {
        "schema": DECISION_ENVELOPE_SCHEMA,
        "status": status,
        "summary": summary,
    }
    if status == "resolved":
        envelope["payload"] = payload if isinstance(payload, dict) else {"decision": {"mock": True}}
    elif status == "needs_user_input":
        envelope["question"] = {
            "id": "mock_question",
            "prompt": "请补充运行所需信息。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                },
            },
            "store_key": "mock_user_reply",
        }
        envelope["resume"] = {
            "policy": "resume_same_node",
        }
    else:
        envelope["issues"] = [{"severity": "blocker", "code": "mock_blocked", "message": summary}]
    return envelope


def _validate_question(question: Any) -> list[dict]:
    findings: list[dict] = []
    if not isinstance(question, dict):
        return [_finding("blocker", "decision_question_missing", "needs_user_input decision must include question.")]
    for field in ["prompt", "store_key"]:
        value = question.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(_finding("blocker", f"decision_question_{field}_missing", f"question.{field} is required."))
    if "input_schema" not in question:
        findings.append(_finding("blocker", "decision_question_input_schema_missing", "question.input_schema is required."))
    return findings


def _validate_resume(resume: Any) -> list[dict]:
    findings: list[dict] = []
    if not isinstance(resume, dict):
        return [_finding("blocker", "decision_resume_missing", "needs_user_input decision must include resume policy.")]
    policy = str(resume.get("policy") or "").strip()
    if policy not in RESUME_POLICIES:
        findings.append(_finding("blocker", "decision_resume_policy_invalid", "resume.policy is invalid."))
    if policy == "resume_target_node" and not str(resume.get("target_node") or "").strip():
        findings.append(_finding("blocker", "decision_resume_target_missing", "resume_target_node requires resume.target_node."))
    return findings


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.replace("\r", "\n").replace(",", "\n").split("\n") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _finding(severity: str, code: str, message: str) -> dict:
    return {"severity": severity, "code": code, "message": message}
