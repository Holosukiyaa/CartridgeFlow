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
CAST_PACK_SCHEMA = "cartridgeflow.cast_pack.v1"
RUN_SNAPSHOT_SCHEMA = "cartridgeflow.run_snapshot.v1"
CREATIVE_MODES = {"conservative", "character_replace", "creative_recast", "exploration"}
CRCP_REQUIRED_PROFILES = ["creative_control_runtime"]
CRCP_REQUIRED_CAPABILITIES = [
    "control_bundle_v1",
    "control_bundle_validate",
    "creative_spec_v1",
    "creative_mode_policy",
    "creative_workflow_allowlist",
    "creative_change_proposal",
    "creative_approval_gate",
    "creative_run_snapshot",
    "creative_failure_record",
    "creative_quality_gates",
    "creative_artifact_audit",
]
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
        return _invalid(findings, "control_bundle_invalid", "Shot Control Bundle must be an object")

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
        return _invalid(findings, "creative_spec_invalid", "CreativeSpec must be an object")
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


def validate_cast_pack(
    pack: dict,
    workspace_root: str | Path | None = None,
    *,
    check_files: bool = False,
    deliverable: bool = True,
) -> dict:
    """Validate the approved identity references consumed by character replacement."""
    findings: list[dict] = []
    if not isinstance(pack, dict):
        return _invalid(findings, "cast_pack_invalid", "CastPack must be an object")
    if pack.get("schema") != CAST_PACK_SCHEMA:
        _block(findings, "cast_pack_schema", f"schema must be {CAST_PACK_SCHEMA}")
    for field in ["pack_id", "character_id", "display_name"]:
        _required_string(pack, field, findings, "cast_pack_identity")
    _positive_int(pack, "revision", findings, "cast_pack_revision")

    references = pack.get("references")
    if not isinstance(references, dict):
        _block(findings, "cast_pack_references", "references must be an object")
        references = {}
    _required_string(references, "primary", findings, "cast_pack_references")
    additional = references.get("additional", [])
    if not isinstance(additional, list) or any(not isinstance(item, str) or not item.strip() for item in additional):
        _block(findings, "cast_pack_references", "references.additional must be an array of non-empty paths")
        additional = []
    reference_paths = [references.get("primary"), *additional]
    reference_paths = [str(item).strip() for item in reference_paths if isinstance(item, str) and item.strip()]
    if len(reference_paths) != len(set(reference_paths)):
        _block(findings, "cast_pack_references", "reference image paths must be unique")

    appearance = pack.get("appearance")
    if not isinstance(appearance, dict):
        _block(findings, "cast_pack_appearance", "appearance must be an object")
        appearance = {}
    wardrobe = _nonempty_string_list(appearance, "wardrobe", findings, "cast_pack_appearance")
    if not wardrobe:
        _block(findings, "cast_pack_appearance", "appearance.wardrobe must contain at least one item")
    _required_string(appearance, "hair", findings, "cast_pack_appearance")
    immutable = _nonempty_string_list(appearance, "immutable_features", findings, "cast_pack_appearance")
    if not immutable:
        _block(findings, "cast_pack_appearance", "appearance.immutable_features must contain at least one item")
    fixed_colors = appearance.get("fixed_colors")
    if not isinstance(fixed_colors, dict) or not fixed_colors:
        _block(findings, "cast_pack_appearance", "appearance.fixed_colors must be a non-empty object")
    elif any(not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip() for key, value in fixed_colors.items()):
        _block(findings, "cast_pack_appearance", "appearance.fixed_colors keys and values must be non-empty strings")

    license_info = pack.get("license")
    if not isinstance(license_info, dict):
        _block(findings, "cast_pack_license", "license must be an object")
        license_info = {}
    for field in ["name", "source"]:
        _required_string(license_info, field, findings, "cast_pack_license")
    if not isinstance(license_info.get("public_delivery_allowed"), bool):
        _block(findings, "cast_pack_license", "license.public_delivery_allowed must be boolean")
    elif deliverable and not license_info["public_delivery_allowed"]:
        _block(findings, "cast_pack_license", "CastPack license does not allow public delivery")

    hashes = pack.get("sha256")
    if not isinstance(hashes, dict):
        _block(findings, "cast_pack_hashes", "sha256 must be an object")
        hashes = {}
    root = Path(workspace_root).resolve() if workspace_root else None
    for relative_path in reference_paths:
        digest = hashes.get(relative_path)
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            _block(findings, "cast_pack_hashes", f"sha256 entry is missing or invalid: {relative_path}")
            continue
        if check_files:
            target = _safe_artifact_path(root, relative_path, findings, "cast_pack")
            if target is None:
                continue
            if not target.is_file():
                _block(findings, "cast_pack_file_missing", f"reference image does not exist: {relative_path}")
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual.lower() != digest.lower():
                _block(findings, "cast_pack_hash_mismatch", f"sha256 mismatch: {relative_path}")

    status = pack.get("status")
    if status != "approved":
        _block(findings, "cast_pack_status", "status must be approved before character replacement")
    approval = pack.get("approval")
    if not isinstance(approval, dict):
        _block(findings, "cast_pack_approval", "approval must be an object")
    else:
        if approval.get("status") != "approved" or approval.get("approved_by") != "user":
            _block(findings, "cast_pack_approval", "approval must record explicit user approval")
        if approval.get("approved_revision") != pack.get("revision"):
            _block(findings, "cast_pack_approval", "approval.approved_revision must equal revision")
    return _result(findings, "cast_pack_valid", "CastPack is valid and approved")


def validate_run_snapshot(snapshot: dict) -> dict:
    """Validate the immutable inputs captured for one CRCP run."""
    findings: list[dict] = []
    if not isinstance(snapshot, dict):
        return _invalid(findings, "run_snapshot_invalid", "RunSnapshot must be an object")
    if snapshot.get("schema") != RUN_SNAPSHOT_SCHEMA:
        _block(findings, "run_snapshot_schema", f"schema must be {RUN_SNAPSHOT_SCHEMA}")
    for field in ["snapshot_id", "run_id"]:
        _required_string(snapshot, field, findings, "run_snapshot_identity")
    _positive_int(snapshot, "revision", findings, "run_snapshot_revision")

    protocol = snapshot.get("protocol")
    if not isinstance(protocol, dict) or protocol.get("id") != "CF-CRCP" or protocol.get("version") != "0.1":
        _block(findings, "run_snapshot_protocol", "protocol must be CF-CRCP@0.1")

    _revision_ref(snapshot, "creative_spec", "spec_id", findings)
    _revision_ref(snapshot, "control_bundle", "bundle_id", findings)
    _hashed_ref(snapshot, "workflow", findings)
    _hashed_ref(snapshot, "model", findings)

    seed = snapshot.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, (int, str)) or (isinstance(seed, str) and not seed.strip()):
        _block(findings, "run_snapshot_seed", "seed must be a non-empty string or integer")
    if not isinstance(snapshot.get("parameters"), dict):
        _block(findings, "run_snapshot_parameters", "parameters must be an object")

    outputs = snapshot.get("outputs")
    if not isinstance(outputs, list):
        _block(findings, "run_snapshot_outputs", "outputs must be an array")
        outputs = []
    for index, output in enumerate(outputs):
        if not isinstance(output, dict) or not isinstance(output.get("path"), str) or not output.get("path").strip():
            _block(findings, "run_snapshot_outputs", f"outputs[{index}].path is required")
            continue
        digest = output.get("sha256")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            _block(findings, "run_snapshot_outputs", f"outputs[{index}].sha256 must be a SHA-256 digest")

    status = snapshot.get("status")
    valid_statuses = {"locked", "running", "review_required", "accepted", "rejected", "blocked"}
    if status not in valid_statuses:
        _block(findings, "run_snapshot_status", f"status must be one of: {', '.join(sorted(valid_statuses))}")
    if status in {"review_required", "accepted", "rejected", "blocked"} and not outputs:
        _block(findings, "run_snapshot_outputs", "a completed snapshot must record at least one output")

    approval = snapshot.get("approval")
    if not isinstance(approval, dict):
        _block(findings, "run_snapshot_approval", "approval must be an object")
    else:
        if approval.get("status") != "approved":
            _block(findings, "run_snapshot_approval", "approval.status must be approved")
        if approval.get("approved_by") != "user":
            _block(findings, "run_snapshot_approval", "approval.approved_by must be user")
        if approval.get("approved_revision") != snapshot.get("revision"):
            _block(findings, "run_snapshot_approval", "approval.approved_revision must equal revision")
    return _result(findings, "run_snapshot_valid", "RunSnapshot is valid")


def build_creative_recast_certification_report(base: dict, manifest: dict, artifacts: dict | None = None) -> dict:
    """Report whether a base and one cartridge meet the CRCP v0.1 boundary.

    This report is intentionally separate from the existing FARP certification
    label path. It cannot certify or mutate a manifest while the base does not
    declare CRCP support.
    """
    findings: list[dict] = []
    base = base if isinstance(base, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    supported_protocols = {
        (str(item.get("id")), str(item.get("version")))
        for item in base.get("supported_protocols") or []
        if isinstance(item, dict)
    }
    if ("CF-CRCP", "0.1") not in supported_protocols:
        _block(findings, "crcp_protocol_unsupported", "Base does not support CF-CRCP@0.1")
    extension = next((item for item in manifest.get("protocol_extensions") or [] if isinstance(item, dict) and item.get("id") == "CF-CRCP" and item.get("version") == "0.1"), None)
    if extension is None:
        _block(findings, "crcp_extension_missing", "Manifest must declare CF-CRCP@0.1 in protocol_extensions")

    base_profiles = set(base.get("profiles") or [])
    base_capabilities = set(base.get("capabilities") or [])
    required_profiles = list(CRCP_REQUIRED_PROFILES)
    required_capabilities = list(CRCP_REQUIRED_CAPABILITIES)
    if isinstance(extension, dict):
        required_profiles = _merge_required(required_profiles, extension.get("required_profiles"))
        required_capabilities = _merge_required(required_capabilities, extension.get("required_capabilities"))
    for profile in required_profiles:
        if profile not in base_profiles:
            _block(findings, "crcp_required_profile_missing", f"Base is missing CRCP profile: {profile}")
    for capability in required_capabilities:
        if capability not in base_capabilities:
            _block(findings, "crcp_required_capability_missing", f"Base is missing CRCP capability: {capability}")

    validators = {
        "cast_pack": validate_cast_pack,
        "creative_spec": validate_creative_spec,
        "shot_control_bundle": validate_shot_control_bundle,
        "run_snapshot": validate_run_snapshot,
    }
    for artifact_name, validator in validators.items():
        artifact = artifacts.get(artifact_name)
        if artifact is None:
            _block(findings, "crcp_artifact_missing", f"Missing required CRCP artifact: {artifact_name}")
            continue
        result = validator(artifact)
        for finding in result.get("findings") or []:
            if finding.get("severity") == "blocker":
                findings.append({
                    **finding,
                    "code": f"{artifact_name}_{finding.get('code')}",
                })

    blockers = [item for item in findings if item.get("severity") == "blocker"]
    return {
        "ok": not blockers,
        "status": "certified" if not blockers else "not_certified",
        "protocol": {"id": "CF-CRCP", "version": "0.1"},
        "summary": {"blocker": len(blockers), "total": len(findings)},
        "findings": findings,
    }


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


def _required_string(value: dict, field: str, findings: list[dict], code: str) -> None:
    if not isinstance(value.get(field), str) or not value.get(field).strip():
        _block(findings, code, f"{field} is required")


def _positive_int(value: dict, field: str, findings: list[dict], code: str) -> None:
    number = value.get(field)
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        _block(findings, code, f"{field} must be a positive integer")


def _revision_ref(value: dict, field: str, identity_field: str, findings: list[dict]) -> None:
    reference = value.get(field)
    if not isinstance(reference, dict):
        _block(findings, "run_snapshot_reference", f"{field} must be an object")
        return
    _required_string(reference, identity_field, findings, "run_snapshot_reference")
    _positive_int(reference, "revision", findings, "run_snapshot_reference")


def _hashed_ref(value: dict, field: str, findings: list[dict]) -> None:
    reference = value.get(field)
    if not isinstance(reference, dict):
        _block(findings, "run_snapshot_reference", f"{field} must be an object")
        return
    _required_string(reference, "id", findings, "run_snapshot_reference")
    digest = reference.get("sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        _block(findings, "run_snapshot_reference", f"{field}.sha256 must be a SHA-256 digest")


def _merge_required(defaults: list[str], declared) -> list[str]:
    values = list(defaults)
    if isinstance(declared, list):
        for item in declared:
            text = str(item).strip()
            if text and text not in values:
                values.append(text)
    return values


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


def _nonempty_string_list(value: dict, field: str, findings: list[dict], code: str) -> list[str]:
    raw = value.get(field)
    if not isinstance(raw, list):
        _block(findings, code, f"{field} must be an array")
        return []
    result = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            _block(findings, code, f"{field}[{index}] must be a non-empty string")
        else:
            result.append(item.strip())
    return result


def _safe_artifact_path(root: Path | None, relative_path: str, findings: list[dict], code_prefix: str = "control_bundle") -> Path | None:
    if root is None:
        _block(findings, f"{code_prefix}_file_check", "workspace_root is required when check_files is true")
        return None
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        _block(findings, f"{code_prefix}_path_escape", f"artifact path escapes workspace: {relative_path}")
        return None
    return target
