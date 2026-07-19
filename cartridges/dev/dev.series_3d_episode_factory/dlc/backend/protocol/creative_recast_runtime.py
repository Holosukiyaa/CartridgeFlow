"""Pure CRCP v0.1 run-state and failure-record guards.

No function in this module writes state or starts a provider. The cartridge
runner can persist the returned transition only after the surrounding FARP
runtime has accepted it.
"""

from __future__ import annotations

from .creative_recast import CRCP_FAILURE_LABELS, validate_candidate_review, validate_run_snapshot


CRCP_STATES = (
    "draft",
    "awaiting_user_approval",
    "approved",
    "control_ready",
    "running_blender",
    "running_comfy",
    "review_required",
    "accepted",
    "rejected",
    "blocked",
)

FAILURE_LABELS = CRCP_FAILURE_LABELS

ALLOWED_TRANSITIONS = {
    "draft": {"awaiting_user_approval", "blocked"},
    "awaiting_user_approval": {"approved", "rejected", "blocked"},
    "approved": {"control_ready", "blocked"},
    "control_ready": {"running_blender", "blocked"},
    "running_blender": {"running_comfy", "rejected", "blocked"},
    "running_comfy": {"review_required", "rejected", "blocked"},
    "review_required": {"accepted", "rejected", "blocked"},
    "rejected": {"awaiting_user_approval", "blocked"},
    "accepted": set(),
    "blocked": set(),
}


def validate_failure_record(record: dict) -> dict:
    findings: list[dict] = []
    if not isinstance(record, dict):
        return _invalid(findings, "failure_record_invalid", "FailureRecord must be an object")
    if record.get("schema") != "cartridgeflow.failure_record.v1":
        _block(findings, "failure_record_schema", "schema must be cartridgeflow.failure_record.v1")
    for field in ["failure_id", "shot_id", "user_feedback", "actual_change", "output_location", "rollback_target", "recommendation"]:
        if not isinstance(record.get(field), str) or not record.get(field).strip():
            _block(findings, "failure_record_fields", f"{field} is required")
    run_revision = record.get("run_revision")
    if isinstance(run_revision, bool) or not isinstance(run_revision, int) or run_revision <= 0:
        _block(findings, "failure_record_revision", "run_revision must be a positive integer")
    if record.get("label") not in FAILURE_LABELS:
        _block(findings, "failure_record_label", "label is not a recognized CRCP failure label")
    retry_index = record.get("retry_index")
    if isinstance(retry_index, bool) or not isinstance(retry_index, int) or retry_index < 0:
        _block(findings, "failure_record_retry", "retry_index must be a non-negative integer")
    changed_fields = record.get("changed_fields")
    if not isinstance(changed_fields, list) or any(not isinstance(item, str) or not item.strip() for item in changed_fields):
        _block(findings, "failure_record_changed_fields", "changed_fields must be an array of non-empty strings")
    return _result(findings, "failure_record_valid", "FailureRecord is valid")


def transition_crcp_run(current_state: str, next_state: str, context: dict | None = None) -> dict:
    """Validate one explicit CRCP state transition and its prerequisites."""
    context = context if isinstance(context, dict) else {}
    findings: list[dict] = []
    current_state = str(current_state or "").strip()
    next_state = str(next_state or "").strip()
    if current_state not in CRCP_STATES:
        _block(findings, "run_state_invalid", f"unknown current state: {current_state}")
    if next_state not in CRCP_STATES:
        _block(findings, "run_state_invalid", f"unknown next state: {next_state}")
    if not findings and next_state not in ALLOWED_TRANSITIONS[current_state]:
        _block(findings, "run_transition_invalid", f"transition is not allowed: {current_state} -> {next_state}")

    if not findings:
        if next_state == "approved":
            _require_approved(context.get("approval"), findings)
        elif next_state == "control_ready":
            _require_valid(context.get("creative_spec"), context.get("shot_control_bundle"), findings)
        elif next_state == "running_blender":
            _require_locked_snapshot(context.get("run_snapshot"), findings)
        elif next_state == "running_comfy":
            if context.get("blender_ok") is not True:
                _block(findings, "run_prerequisite_missing", "Blender control render must pass before ComfyUI")
        elif next_state == "review_required":
            if not context.get("outputs"):
                _block(findings, "run_prerequisite_missing", "ComfyUI transition requires output artifacts")
        elif next_state == "accepted":
            workspace_root = context.get("workspace_root")
            review = validate_candidate_review(
                context.get("candidate_review"),
                workspace_root,
                check_files=bool(workspace_root),
            )
            if not workspace_root:
                _block(findings, "run_artifact_audit", "accepted requires workspace_root for artifact hash checks")
            if not review.get("ok") or (context.get("candidate_review") or {}).get("status") != "accepted":
                _block(findings, "run_review_required", "accepted requires a valid accepted CandidateReview")
        elif next_state == "rejected":
            failure = validate_failure_record(context.get("failure_record"))
            if not failure.get("ok"):
                findings.extend(failure.get("findings") or [])
        elif current_state == "rejected" and next_state == "awaiting_user_approval":
            if context.get("retry") is not True:
                _block(findings, "run_retry_confirmation", "retry must be explicitly requested")
            failure = validate_failure_record(context.get("failure_record"))
            if not failure.get("ok"):
                findings.extend(failure.get("findings") or [])

    blockers = [item for item in findings if item.get("severity") == "blocker"]
    return {
        "ok": not blockers,
        "from": current_state,
        "to": next_state,
        "state": next_state if not blockers else current_state,
        "findings": findings,
    }


def _require_approved(approval: dict, findings: list[dict]) -> None:
    if not isinstance(approval, dict) or approval.get("status") != "approved" or approval.get("approved_by") != "user":
        _block(findings, "run_approval_required", "approved requires explicit user approval")


def _require_valid(creative_spec: dict, shot_control_bundle: dict, findings: list[dict]) -> None:
    if not isinstance(creative_spec, dict) or not isinstance(shot_control_bundle, dict):
        _block(findings, "run_prerequisite_missing", "control_ready requires CreativeSpec and Shot Control Bundle")
        return
    if creative_spec.get("ok") is not True or shot_control_bundle.get("ok") is not True:
        _block(findings, "run_prerequisite_invalid", "CreativeSpec and Shot Control Bundle must pass validation")


def _require_locked_snapshot(snapshot: dict, findings: list[dict]) -> None:
    if not isinstance(snapshot, dict):
        _block(findings, "run_snapshot_required", "running_blender requires a RunSnapshot")
        return
    result = validate_run_snapshot(snapshot)
    if not result.get("ok") or snapshot.get("status") != "locked":
        _block(findings, "run_snapshot_not_locked", "running_blender requires a valid locked RunSnapshot")


def _result(findings: list[dict], ok_code: str, ok_message: str) -> dict:
    blockers = [item for item in findings if item.get("severity") == "blocker"]
    if not blockers:
        findings.append({"severity": "info", "code": ok_code, "message": ok_message})
    return {"ok": not blockers, "findings": findings}


def _invalid(findings: list[dict], code: str, message: str) -> dict:
    _block(findings, code, message)
    return _result(findings, code, message)


def _block(findings: list[dict], code: str, message: str) -> None:
    findings.append({"severity": "blocker", "code": code, "message": message})
