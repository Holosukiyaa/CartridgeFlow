"""Read-only validators for the CF-CRCP v0.1 artifact contracts.

This module deliberately has no registry hooks and never writes artifacts. The
runtime can use it as an input gate once the base declares CRCP capabilities.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


CONTROL_BUNDLE_SCHEMA = "cartridgeflow.shot_control_bundle.v1"
CREATIVE_SPEC_SCHEMA = "cartridgeflow.creative_spec.v1"
CREATIVE_MODES = {"conservative", "character_replace", "creative_recast", "exploration"}
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def validate_shot_control_bundle(
    bundle: dict,
    workspace_root: str | Path | None = None,
    *,
    check_files: bool = False,
) -> dict:
    """Validate a Shot Control Bundle manifest without mutating the workspace."""
    findings: list[dict] = []
    if not isinstance(bundle, dict):
        return _result(findings, "control_bundle_invalid", "Shot Control Bundle must be an object")

    if bundle.get("schema") != CONTROL_BUNDLE_SCHEMA:
        _block(findings, "control_bundle_schema", f"schema must be {CONTROL_BUNDLE_SCHEMA}")
    _required_string(bundle, "bundle_id", findings, "control_bundle_identity")
    _required_string(bundle, "shot_id", findings, "control_bundle_identity")
    _positive_int(bundle, "revision", findings, "control_bundle_revision")
    _positive_int(bundle, "fps", findings, "control_bundle_timing")
    _positive_int(bundle, "frame_count", findings, "control_bundle_timing")
    _positive_int(bundle, "width", findings, "control_bundle_dimensions")
    _positive_int(bundle, "height", findings, "control_bundle_dimensions")

    source = bundle.get("source")
    if not isinstance(source, dict):
        _block(findings, "control_bundle_source", "source must be an object")
        source = {}
    _required_string(source, "engine", findings, "control_bundle_source")
    _required_string(source, "preview", findings, "control_bundle_source")

    controls = bundle.get("controls")
    if not isinstance(controls, dict):
        _block(findings, "control_bundle_controls", "controls must be an object")
        controls = {}
    for field in ["character_mask", "depth", "pose"]:
        _required_string(controls, field, findings, "control_bundle_controls")
    background_edges = controls.get("background_edges")
    if background_edges is not None and not isinstance(background_edges, str):
        _block(findings, "control_bundle_controls", "controls.background_edges must be a path string")

    mask_convention = bundle.get("mask_convention")
    if not isinstance(mask_convention, dict):
        _block(findings, "control_bundle_mask_convention", "mask_convention must be an object")
    else:
        if mask_convention.get("white") != "generate_or_replace":
            _block(findings, "control_bundle_mask_convention", "mask_convention.white must be generate_or_replace")
        if mask_convention.get("black") != "preserve_control_input":
            _block(findings, "control_bundle_mask_convention", "mask_convention.black must be preserve_control_input")

    hashes = bundle.get("sha256")
    if not isinstance(hashes, dict):
        _block(findings, "control_bundle_hashes", "sha256 must be an object")
        hashes = {}
    artifact_paths = [source.get("preview"), *[controls.get(field) for field in ["character_mask", "depth", "pose", "background_edges"]]]
    artifact_paths = [path for path in artifact_paths if isinstance(path, str) and path.strip()]
    root = Path(workspace_root).resolve() if workspace_root else None
    for relative_path in artifact_paths:
        target = _safe_artifact_path(root, relative_path, findings) if check_files else None
        digest = hashes.get(relative_path)
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            _block(findings, "control_bundle_hashes", f"sha256 entry is missing or invalid: {relative_path}")
            continue
        if check_files:
            if target is None:
                continue
            if not target.is_file():
                _block(findings, "control_bundle_file_missing", f"artifact file does not exist: {relative_path}")
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual.lower() != digest.lower():
                _block(findings, "control_bundle_hash_mismatch", f"sha256 mismatch: {relative_path}")

    status = bundle.get("status")
    if status not in {"draft", "validated", "rejected"}:
        _block(findings, "control_bundle_status", "status must be draft, validated, or rejected")
    return _result(findings, "control_bundle_valid", "Shot Control Bundle is valid")


def validate_creative_spec(spec: dict, *, deliverable: bool = True) -> dict:
    """Validate CreativeSpec boundaries and user approval metadata."""
    findings: list[dict] = []
    if not isinstance(spec, dict):
        return _result(findings, "creative_spec_invalid", "CreativeSpec must be an object")
    if spec.get("schema") != CREATIVE_SPEC_SCHEMA:
        _block(findings, "creative_spec_schema", f"schema must be {CREATIVE_SPEC_SCHEMA}")
    _required_string(spec, "spec_id", findings, "creative_spec_identity")
    _positive_int(spec, "revision", findings, "creative_spec_revision")

    mode = spec.get("mode")
    if mode not in CREATIVE_MODES:
        _block(findings, "creative_spec_mode", f"mode must be one of: {', '.join(sorted(CREATIVE_MODES))}")

    locked = _string_array(spec, "locked", findings)
    free = _string_array(spec, "free", findings)
    overlap = sorted(set(locked) & set(free))
    if overlap:
        _block(findings, "creative_spec_overlap", f"locked and free overlap: {', '.join(overlap)}")
    bounds = spec.get("bounds")
    if not isinstance(bounds, dict):
        _block(findings, "creative_spec_bounds", "bounds must be an object")
        bounds = {}
    missing_bounds = [field for field in free if field not in bounds]
    if missing_bounds and not (mode == "exploration" and not deliverable):
        _block(findings, "creative_spec_bounds", f"free fields missing bounds: {', '.join(missing_bounds)}")

    anchors = _string_array(spec, "anchors", findings)
    if not anchors:
        _block(findings, "creative_spec_anchors", "anchors must contain at least one reference")
    for field in ["cast_pack", "world_pack", "style_pack"]:
        _required_string(spec, field, findings, "creative_spec_packs")
    allowed_workflows = _string_array(spec, "allowed_workflows", findings)
    if not allowed_workflows:
        _block(findings, "creative_spec_allowlist", "allowed_workflows must contain at least one workflow")

    approval = spec.get("approval")
    if not isinstance(approval, dict):
        _block(findings, "creative_spec_approval", "approval must be an object")
    else:
        if approval.get("status") != "approved":
            _block(findings, "creative_spec_approval", "approval.status must be approved")
        if approval.get("approved_by") != "user":
            _block(findings, "creative_spec_approval", "approval.approved_by must be user")
        approved_revision = approval.get("approved_revision")
        if isinstance(approved_revision, bool) or not isinstance(approved_revision, int) or approved_revision <= 0:
            _block(findings, "creative_spec_approval", "approval.approved_revision must be a positive integer")
        elif approved_revision != spec.get("revision"):
            _block(findings, "creative_spec_approval", "approval.approved_revision must equal revision")

    return _result(findings, "creative_spec_valid", "CreativeSpec is valid")


def _result(findings: list[dict], ok_code: str, ok_message: str) -> dict:
    blockers = [item for item in findings if item.get("severity") == "blocker"]
    if not blockers:
        findings.append({"severity": "info", "code": ok_code, "message": ok_message})
    return {"ok": not blockers, "findings": findings}


def _block(findings: list[dict], code: str, message: str) -> None:
    findings.append({"severity": "blocker", "code": code, "message": message})


def _required_string(value: dict, field: str, findings: list[dict], code: str) -> None:
    if not isinstance(value.get(field), str) or not value.get(field).strip():
        _block(findings, code, f"{field} is required")


def _positive_int(value: dict, field: str, findings: list[dict], code: str) -> None:
    number = value.get(field)
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        _block(findings, code, f"{field} must be a positive integer")


def _string_array(value: dict, field: str, findings: list[dict]) -> list[str]:
    raw = value.get(field)
    if not isinstance(raw, list):
        _block(findings, "creative_spec_fields", f"{field} must be an array")
        return []
    result = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            _block(findings, "creative_spec_fields", f"{field}[{index}] must be a non-empty string")
            continue
        result.append(item.strip())
    return result


def _safe_artifact_path(root: Path | None, relative_path: str, findings: list[dict]) -> Path | None:
    if root is None:
        _block(findings, "control_bundle_file_check", "workspace_root is required when check_files is true")
        return None
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        _block(findings, "control_bundle_path_escape", f"artifact path escapes workspace: {relative_path}")
        return None
    return target
