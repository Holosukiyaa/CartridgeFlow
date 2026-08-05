import asyncio
import os
import json
import math
import re
import subprocess
import sys
import threading
import uuid
import hashlib
import hmac
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.api_models import (
    AIFlowSelection,
    AIFlowStewardPayload,
    AuthoringAcceptPayload,
    AuthoringAIProposalPayload,
    CreatorDiscoveryPayload,
    CreatorDefaultRecipePayload,
    CreatorComposeRecipePayload,
    CreatorRecomposeRecipePayload,
    CreatorRecomposeAcceptPayload,
    CreatorPackagePayload,
    CreatorNodeRefinementPayload,
    DeveloperMaterializationPayload,
    TrustedNodePresetPayload,
    TrustedNodeActivationPayload,
    CapabilityCartridgePublishPayload,
    CapabilityVerificationPayload,
    CreatorProjectRenamePayload,
    CreatorSourceInspectPayload,
    TrustedNodePublishFromFlowPayload,
    CreatorSourceDiscoveryPayload,
    AuthoringFreezePayload,
    CreatorHandoffPayload,
    AuthoringProposalPayload,
    AuthoringRejectPayload,
    AuthoringReversePayload,
    AuthoringReadinessPayload,
    AuthoringSessionCreatePayload,
    AnnotationSavePayload,
    AuthoringSimulationPayload,
    CartridgeAssetPayload,
    CartridgeCloneToDevPayload,
    CartridgeImportPayload,
    CartridgePackagePayload,
    CartridgeRunControl,
    CartridgeRunCreate,
    DevFlowCreate,
    DevFlowFileSave,
    DevFlowFilesPayload,
    EdgeSavePayload,
    FlowAnalysisPayload,
    InteractionComponentPayload,
    LLMAssignmentsPayload,
    LLMCodexImportPayload,
    LLMDetectPayload,
    LLMImportTextPayload,
    LLMProviderPayload,
    LLMSimpleProviderPayload,
    LLMTestPayload,
    LayoutSavePayload,
    McpOperationCreatePayload,
    McpSourcePatchPayload,
    McpSourceReplacePayload,
    McpToolPayload,
    NodeCreatePayload,
    NodeDeletePayload,
    NodeUpdatePayload,
    PendingInteractionAnswerPayload,
    PortableDlcScaffoldPayload,
    RecipeReleasePayload,
    SandboxHostRequestPayload,
    StudioCredentialPayload,
    StudioResourcesPayload,
    TuningRevisionPayload,
    UploadTextPayload,
)

from core.cartridge import CartridgeRegistry, CartridgeRunner
from core.studio.authoring_service import AuthoringServiceError, AuthoringSessionStore
from core.studio.creator_runtime_bridge import CreatorRuntimeBridge, CreatorRuntimeBridgeError
from core.studio.trusted_node_presets import TrustedNodePresetStore, build_trusted_node_mapping
from core.studio.capability_cartridges import CapabilityCartridgeStore
from core.protocol.capability_cartridges import (
    CapabilityCartridgeError,
    MAX_SOURCE_FILE_BYTES,
    build_flow_capability_release,
    creator_capability_projection,
    validate_flow_capability_boundary,
    legacy_node_capability,
)
from core.protocol.tuning import canonical_digest
from core.cartridge.validator import ManifestValidationError
from core.data_paths import (
    CARTRIDGE_DATA_DIR,
    CONFORMANCE_REPORT,
    DATA_ROOT,
    ERROR_REPORTS_DIR,
    IMPORTS_DIR,
    INSTALLED_CARTRIDGES_DIR,
    LOGS_DIR,
    PACKAGES_DIR,
    UPLOADS_DIR,
    ensure_data_layout,
)
from core.extensions import PortableDlcValidationError, load_portable_dlc_descriptor
from core.extensions.descriptor import resolve_package_file
from core.extensions.mcp_source_editor import McpSourceEditError, add_mcp_operation, edit_mcp_source_graph, update_descriptor_source_digest
from core.extensions.mcp_source_parser import parse_mcp_python_file, parse_mcp_python_source
from core.cartridge.artifacts import ArtifactManager
from core.cartridge.assets import (
    CartridgeAssetError,
    delete_asset,
    delete_component,
    load_asset_bundle,
    write_asset,
    write_component,
)
from core.lab import DevFlowManager, FlowGraphBuilder
from core.llm.config_manager import ensure_llm_config
from core.runtime.errors import RuntimeFailure, build_runtime_error, write_diagnostic
from core.studio.environment import ensure_local_credentials
from core.protocol import (
    BaseManifestError,
    CompatibilityBlockedError,
    ReleaseBuildError,
    apply_protocol_certification_label,
    build_compatibility_report,
    build_release_archive,
    build_protocol_certification_report,
    ensure_development_signing_identity,
    extract_release_payload,
    has_protocol_feature,
    inspect_release_archive,
    load_protocol_release_catalog,
    load_base_implementation,
    supports_protocol_release,
    trusted_public_keys,
)
from core.protocol.tuning import TuningConflictError, TuningProtocolError

ensure_data_layout(ROOT)
PRODUCT_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip().removeprefix("CartridgeFlow-")

MAX_UPLOAD_TEXT_BYTES = 16 * 1024 * 1024
MAX_CARTRIDGE_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_CARTRIDGE_ARCHIVE_MEMBERS = 4096
MAX_CARTRIDGE_MEMBER_BYTES = 256 * 1024 * 1024
MAX_CARTRIDGE_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def _public_data_path(path: str | Path) -> str:
    """Expose stable logical data paths without leaking a relocated host path."""
    data_root = (ROOT / DATA_ROOT).resolve()
    try:
        relative = Path(path).resolve().relative_to(data_root)
    except ValueError:
        return str(path)
    return (Path(".data") / relative).as_posix()


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


SERVER_API_TOKEN = str(os.environ.get("CARTRIDGEFLOW_API_TOKEN") or "").strip()
_configured_origins = [item.strip() for item in str(os.environ.get("CARTRIDGEFLOW_CORS_ORIGINS") or "").split(",") if item.strip()]
_configured_hosts = [item.strip() for item in str(os.environ.get("CARTRIDGEFLOW_TRUSTED_HOSTS") or "").split(",") if item.strip()]

app = FastAPI(title="CartridgeFlow", version=PRODUCT_VERSION, default_response_class=UTF8JSONResponse)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_configured_origins or [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5180",
        "http://localhost:5180",
        "http://127.0.0.1:5181",
        "http://localhost:5181",
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=_configured_hosts or ["127.0.0.1", "localhost", "[::1]", "testserver"],
)


@app.middleware("http")
async def require_server_api_token(request: Request, call_next):
    if SERVER_API_TOKEN and request.url.path.startswith("/api/"):
        supplied = str(request.headers.get("authorization") or "")
        expected = f"Bearer {SERVER_API_TOKEN}"
        if not hmac.compare_digest(supplied, expected):
            return UTF8JSONResponse(
                status_code=401,
                content={"detail": {"code": "SERVER_AUTH_REQUIRED", "message": "A valid workspace access token is required."}},
            )
    return await call_next(request)


def _request_error_context(request: Request) -> dict:
    return {
        "run_id": str(request.path_params.get("run_id") or ""),
        "source": f"http.{request.method.lower()}.{request.url.path}",
    }


def _http_error_code(status_code: int, path: str = "") -> str:
    if path == "/api/llm/test" and status_code == 404:
        return "PROVIDER_MODEL_UNAVAILABLE"
    if status_code == 404:
        return "RESOURCE_NOT_FOUND"
    if path.startswith("/api/llm/"):
        if status_code in {401, 403}:
            return "PROVIDER_AUTH_FAILED"
        if status_code == 429:
            return "PROVIDER_RATE_LIMITED"
        if status_code == 504:
            return "PROVIDER_TIMEOUT"
        if status_code in {500, 502, 503}:
            return "PROVIDER_UNAVAILABLE"
    if status_code in {401, 403}:
        return "PERMISSION_DENIED"
    if status_code in {400, 409, 422}:
        return "REQUEST_INVALID"
    return "INTERNAL_UNEXPECTED"


_DIAGNOSTIC_SECRET_KEYS = {
    "api_key", "apikey", "authorization", "auth", "token", "access_token",
    "refresh_token", "secret", "password", "credential", "credentials", "private_key",
}


def _redact_diagnostic_value(value, key: str = ""):
    """Keep diagnostic bundles useful to an AI without copying local secrets."""
    lowered = str(key or "").lower().replace("-", "_")
    if lowered in _DIAGNOSTIC_SECRET_KEYS or re.search(
        r"api_?key|authorization|password|secret|token|cookie|credential", lowered, re.IGNORECASE,
    ):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(child_key): _redact_diagnostic_value(child_value, str(child_key)) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_redact_diagnostic_value(item, key) for item in value]
    if isinstance(value, str):
        text = value[:5000]
        text = re.sub(r"(?i)(bearer\s+)[a-z0-9._~+/-]+", r"\1[redacted]", text)
        text = re.sub(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+", r"\1=[redacted]", text)
        return text
    return value


@app.exception_handler(RuntimeFailure)
async def runtime_failure_handler(request: Request, exc: RuntimeFailure):
    return UTF8JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.envelope["message"], "error_envelope": exc.envelope},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    context = _request_error_context(request)
    safe_errors = _redact_diagnostic_value(exc.errors())
    envelope = build_runtime_error(
        "REQUEST_INVALID",
        run_id=context["run_id"],
        source=context["source"],
        cause_chain=[{"type": "RequestValidationError", "message": "Request payload validation failed"}],
    )
    return UTF8JSONResponse(status_code=422, content={"detail": safe_errors, "error_envelope": envelope})


@app.exception_handler(ManifestValidationError)
async def manifest_validation_error_handler(request: Request, exc: ManifestValidationError):
    context = _request_error_context(request)
    safe_detail = _redact_diagnostic_value(str(exc))
    envelope = build_runtime_error(
        "FLOW_CONTRACT_INVALID",
        run_id=context["run_id"],
        source=context["source"],
        cause_chain=[{"type": "ManifestValidationError", "message": safe_detail}],
    )
    return UTF8JSONResponse(status_code=409, content={"detail": safe_detail, "error_envelope": envelope})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    context = _request_error_context(request)
    compatibility_blocked = isinstance(exc.detail, dict) and exc.detail.get("error") == "compatibility_blocked"
    safe_detail = _redact_diagnostic_value(exc.detail)
    declared_code = safe_detail.get("code") if isinstance(safe_detail, dict) else None
    envelope = build_runtime_error(
        str(declared_code) if declared_code else ("FLOW_CONTRACT_INVALID" if compatibility_blocked else _http_error_code(exc.status_code, request.url.path)),
        run_id=context["run_id"],
        source=context["source"],
        cause_chain=[{"type": "HTTPException", "message": str(safe_detail)}],
        context={"status_code": exc.status_code},
    )
    return UTF8JSONResponse(status_code=exc.status_code, content={"detail": safe_detail, "error_envelope": envelope})


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    context = _request_error_context(request)
    envelope = build_runtime_error(
        exception=exc,
        run_id=context["run_id"],
        source=context["source"],
    )
    write_diagnostic(
        ROOT / ERROR_REPORTS_DIR,
        envelope,
        exc,
        {"method": request.method, "path": request.url.path},
        exact_directory=True,
    )
    return UTF8JSONResponse(status_code=500, content={"detail": envelope["message"], "error_envelope": envelope})


@app.middleware("http")
async def add_utf8_charset(request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    lower_content_type = content_type.lower()
    needs_charset = (
        lower_content_type.startswith("application/json")
        or lower_content_type.startswith("text/html")
        or lower_content_type.startswith("text/css")
        or lower_content_type.startswith("text/javascript")
        or lower_content_type.startswith("application/javascript")
    )
    if needs_charset and "charset=" not in lower_content_type:
        response.headers["content-type"] = f"{content_type}; charset=utf-8"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), display-capture=(), payment=(), usb=(), serial=(), hid=()",
    )
    if lower_content_type.startswith("text/html"):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
            "frame-src 'self' http://127.0.0.1:* http://localhost:*; object-src 'none'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
    return response

registry = CartridgeRegistry(ROOT)
authoring_sessions = AuthoringSessionStore(ROOT / DATA_ROOT / "user" / "authoring_sessions")
trusted_node_presets = TrustedNodePresetStore(ROOT / DATA_ROOT / "user" / "trusted_node_presets")
capability_cartridges = CapabilityCartridgeStore(ROOT / DATA_ROOT / "user" / "capability_cartridges")
capability_verification_dir = ROOT / DATA_ROOT / "user" / "capability_verifications"
capability_test_run_dir = ROOT / DATA_ROOT / "user" / "capability_test_runs"
creator_recipe_proposal_dir = ROOT / DATA_ROOT / "user" / "creator_recipe_proposals"
capability_verification_dir.mkdir(parents=True, exist_ok=True)
capability_test_run_dir.mkdir(parents=True, exist_ok=True)
creator_recipe_proposal_dir.mkdir(parents=True, exist_ok=True)
runner = CartridgeRunner(ROOT, registry)
artifact_manager = ArtifactManager(ROOT)
flow_graph_builder = FlowGraphBuilder()
dev_flow_manager = DevFlowManager(ROOT)
ensure_llm_config()
ensure_local_credentials()


def write_flow_layout_log(cartridge_id: str, graph: dict, reason: str):
    import json as _json
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_points = {}
    for node in nodes:
        layout = node.get("layout") or (node.get("params") or {}).get("layout") or (node.get("data") or {}).get("layout") or {}
        node_points[node.get("id")] = {
            "title": node.get("title"),
            "x": int(layout.get("x", node.get("x", 0)) or 0),
            "y": int(layout.get("y", node.get("y", 0)) or 0),
        }
    edge_metrics = []
    for edge in edges:
        source = edge.get("from") or edge.get("source")
        target = edge.get("to") or edge.get("target")
        source_point = node_points.get(source)
        target_point = node_points.get(target)
        if not source_point or not target_point:
            continue
        dx = target_point["x"] - source_point["x"]
        dy = target_point["y"] - source_point["y"]
        edge_metrics.append({
            "from": source,
            "to": target,
            "label": edge.get("label") or "",
            "scope": edge.get("scope") or "root",
            "from_title": source_point.get("title"),
            "to_title": target_point.get("title"),
            "dx": dx,
            "dy": dy,
            "length": round((dx * dx + dy * dy) ** 0.5),
        })
    edge_metrics.sort(key=lambda item: item["length"], reverse=True)
    log_entry = {
        "time": datetime.utcnow().isoformat() + "Z",
        "cartridge_id": cartridge_id,
        "reason": reason,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "max_edge_length": edge_metrics[0]["length"] if edge_metrics else 0,
        "long_edges": [item for item in edge_metrics if item["length"] > 560][:20],
        "edges_top10": edge_metrics[:10],
        "nodes": node_points,
    }
    log_dir = ROOT / LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "flow_layout_debug.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps(log_entry, ensure_ascii=False) + "\n")


def _is_typed_root_flow(root_flow: dict) -> bool:
    protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
    return has_protocol_feature(
        str(protocol.get("id") or ""),
        str(protocol.get("version") or ""),
        "typed_control_edges",
        ROOT,
    )


def _is_execution_plan_root_flow(root_flow: dict) -> bool:
    protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
    return has_protocol_feature(
        str(protocol.get("id") or ""),
        str(protocol.get("version") or ""),
        "execution_plan",
        ROOT,
    )


def _edge_scope(edge: dict) -> str:
    if edge.get("scope"):
        return str(edge.get("scope") or "root")
    kind = str(edge.get("kind") or "control")
    return "root" if kind == "control" else kind


def _stored_flow_edge(root_flow: dict, source: str, target: str, scope: str = "root", label: str | None = None) -> dict:
    if _is_typed_root_flow(root_flow):
        kind = "control" if scope == "root" else scope
        item = {"kind": kind, "from": source, "to": target}
        if scope != "root":
            item["scope"] = scope
    else:
        item = {"from": source, "to": target, "scope": scope}
    if label:
        item["label"] = label
    return item


def _flow_edges(root_flow: dict) -> list[dict]:
    if _is_execution_plan_root_flow(root_flow):
        plan = root_flow.get("execution_plan") if isinstance(root_flow.get("execution_plan"), dict) else {}
        return [edge for edge in plan.get("edges") or [] if isinstance(edge, dict)]
    field = "control_edges" if _is_typed_root_flow(root_flow) else "edges"
    return [edge for edge in root_flow.get(field) or [] if isinstance(edge, dict)]


def _write_flow_edges(root_flow: dict, edges: list[dict]) -> None:
    if _is_execution_plan_root_flow(root_flow):
        plan = root_flow.setdefault("execution_plan", {"schema": "cartridgeflow.execution_plan.v1", "entry": root_flow.get("start")})
        previous = {
            (str(item.get("from") or ""), str(item.get("to") or "")): item
            for item in (plan.get("edges") or [])
            if isinstance(item, dict) and item.get("from") and item.get("to")
        }
        normalized = []
        seen = set()
        for edge in edges:
            source = str(edge.get("from") or edge.get("source") or "").strip()
            target = str(edge.get("to") or edge.get("target") or "").strip()
            if not source or not target or source == target:
                continue
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            prior = previous.get(key) or {}
            # The frontend sends edges without a `kind`; recover the author kind
            # from the previous facts or from the visual scope so failure edges
            # are never rewritten as sequence edges.
            kind = str(edge.get("kind") or prior.get("kind") or ("failure" if str(edge.get("scope") or "") == "failure" else "sequence"))
            item: dict = {
                "id": str(edge.get("id") or prior.get("id") or f"{source}_{target}"),
                "kind": kind,
                "from": source,
                "to": target,
            }
            failure_detail = edge.get("failure") if isinstance(edge.get("failure"), dict) else prior.get("failure")
            if kind == "failure" and isinstance(failure_detail, dict):
                item["failure"] = failure_detail
            normalized.append(item)
        plan["schema"] = "cartridgeflow.execution_plan.v1"
        plan["entry"] = str(plan.get("entry") or root_flow.get("start") or "")
        plan["edges"] = normalized
        root_flow.pop("edges", None)
        root_flow.pop("control_edges", None)
        return
    seen = set()
    normalized = []
    for edge in edges:
        source = str(edge.get("from") or edge.get("source") or "").strip()
        target = str(edge.get("to") or edge.get("target") or "").strip()
        if not source or not target or source == target:
            continue
        scope = _edge_scope(edge)
        key = (scope, source, target)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(_stored_flow_edge(root_flow, source, target, scope, edge.get("label")))
    if _is_typed_root_flow(root_flow):
        root_flow["control_edges"] = normalized
        root_flow.pop("edges", None)
    else:
        root_flow["edges"] = normalized


def _sync_flow_edges_from_next(root_flow: dict, extra_edges: list[dict] | None = None) -> None:
    states = root_flow.get("states") if isinstance(root_flow.get("states"), dict) else {}
    edges = []
    for source_id, source_state in states.items():
        if not isinstance(source_state, dict):
            continue
        target_id = source_state.get("next")
        if target_id in states:
            edges.append({"from": source_id, "to": target_id, "scope": "root"})
    for edge in extra_edges or []:
        source = edge.get("from") or edge.get("source")
        target = edge.get("to") or edge.get("target")
        if source in states and target in states and _edge_scope(edge) != "root":
            edges.append(edge)
    _write_flow_edges(root_flow, edges)


def _ensure_typed_node_contracts(root_flow: dict, state: dict) -> None:
    if _is_typed_root_flow(root_flow) and state.get("type") == "process":
        if not isinstance(state.get("inputs"), dict):
            state["inputs"] = {}
        if not isinstance(state.get("outputs"), dict):
            state["outputs"] = {}


def _validate_candidate_interaction_contracts(cartridge_id: str, files: dict, root_flow: dict) -> None:
    states = root_flow.get("states") if isinstance(root_flow.get("states"), dict) else {}
    if not any(isinstance(state, dict) and state.get("kind") == "interaction" for state in states.values()):
        return
    import json as _json
    from core.cartridge.assets import load_asset_bundle, validate_interaction_nodes

    manifest = _json.loads(files.get("manifest") or "{}")
    bundle = load_asset_bundle(dev_flow_manager._flow_path(cartridge_id), manifest)
    blockers = [item for item in validate_interaction_nodes(root_flow, bundle) if item.get("severity") == "blocker"]
    if blockers:
        finding = blockers[0]
        raise HTTPException(
            status_code=409,
            detail=f"{finding.get('code')}: {finding.get('node')}: {finding.get('message')}",
        )


def _validate_cartridge_archive_members(members, extract_dir: Path) -> None:
    import stat as _stat

    if len(members) > MAX_CARTRIDGE_ARCHIVE_MEMBERS:
        raise HTTPException(status_code=413, detail="Cartridge zip contains too many files")
    extract_root = extract_dir.resolve()
    total_size = 0
    seen_targets: set[str] = set()
    for member in members:
        member_name = (member.filename or "").replace("\\", "/")
        parts = member_name.split("/")
        if (
            not member_name
            or member_name.startswith("/")
            or ":" in member_name
            or any(part in {".", ".."} for part in parts)
        ):
            raise HTTPException(status_code=400, detail=f"Invalid zip path: {member.filename}")
        if member.flag_bits & 0x1:
            raise HTTPException(status_code=400, detail=f"Encrypted zip member is not supported: {member.filename}")
        file_type = (member.external_attr >> 16) & 0o170000
        if file_type == _stat.S_IFLNK:
            raise HTTPException(status_code=400, detail=f"Symbolic links are not allowed in cartridge packages: {member.filename}")
        target = (extract_dir / member_name).resolve()
        if target != extract_root and extract_root not in target.parents:
            raise HTTPException(status_code=400, detail=f"Unsafe zip path: {member.filename}")
        target_key = str(target).casefold()
        if target_key in seen_targets:
            raise HTTPException(status_code=400, detail=f"Duplicate zip path: {member.filename}")
        seen_targets.add(target_key)
        if member.is_dir():
            continue
        if member.file_size > MAX_CARTRIDGE_MEMBER_BYTES:
            raise HTTPException(status_code=413, detail=f"Cartridge zip member is too large: {member.filename}")
        total_size += max(0, int(member.file_size))
        if total_size > MAX_CARTRIDGE_TOTAL_UNCOMPRESSED_BYTES:
            raise HTTPException(status_code=413, detail="Cartridge zip expands beyond the allowed size")


@app.post("/api/uploads/file")
def upload_file(payload: UploadTextPayload):
    import re as _re
    import uuid as _uuid

    text = payload.content or ""
    encoded_size = len(text.encode("utf-8"))
    if encoded_size > MAX_UPLOAD_TEXT_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded text exceeds 16 MiB")
    upload_dir = ROOT / UPLOADS_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    original_name = Path(payload.filename or "upload.txt").name
    safe_name = _re.sub(r"[^a-zA-Z0-9._-]+", "_", original_name).strip("._-") or "upload.txt"
    suffix = Path(safe_name).suffix or ".txt"
    stem = Path(safe_name).stem or "upload"
    target_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{_uuid.uuid4().hex[:8]}_{stem}{suffix}"
    target = upload_dir / target_name
    target.write_text(text, encoding="utf-8")
    return {
        "ok": True,
        "filename": original_name,
        "path": _public_data_path(target),
        "size": encoded_size,
    }


@app.get("/api/health")
def health():
    return {"ok": True, "app": "CartridgeFlow", "version": PRODUCT_VERSION}


@app.get("/api/base")
def get_base_implementation():
    try:
        base = load_base_implementation(ROOT)
        protocol_catalog = load_protocol_release_catalog(ROOT).public_payload()
        from core.conformance import load_latest_report

        report = load_latest_report(ROOT)
        if report:
            base["conformance"] = {
                **(base.get("conformance") or {}),
                "latest_report": {
                    "status": report.get("status"),
                    "generated_at": report.get("generated_at"),
                    "tests": {key: report.get("tests", {}).get(key) for key in ("status", "total", "counts")},
                    "capabilities": {key: report.get("capabilities", {}).get(key) for key in ("status", "declared", "counts")},
                },
            }
        return {"ok": True, "base": base, "protocol_catalog": protocol_catalog}
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/studio/conformance")
def get_studio_conformance():
    from core.conformance import load_latest_report

    report = load_latest_report(ROOT)
    if report is None:
        return {
            "available": False,
            "report_path": CONFORMANCE_REPORT.as_posix(),
            "command": "python scripts/run_conformance.py",
        }
    return {"available": True, "report": report}


@app.get("/api/runtimes")
def list_runtimes():
    return {"items": runner.runtime_manager.list_runtime_types()}


@app.get("/api/studio/resources")
def get_studio_resources():
    from core.lab.builtin_mcp import BuiltinMcpRegistry
    from core.studio.resources import load_resources

    builtin_tools = []
    for item in BuiltinMcpRegistry(ROOT).describe():
        server = str(item.get("server") or "")
        tool = str(item.get("tool") or "")
        builtin_tools.append({
            "id": f"builtin:{server}/{tool}",
            "name": f"{server} / {tool}",
            "kind": "builtin",
            "description": item.get("description") or "",
            "server": server,
            "tool": tool,
            "package_mode": "base",
            "enabled": True,
            "locked": True,
        })
    return {**load_resources(), "builtin_tools": builtin_tools}


@app.put("/api/studio/resources")
def put_studio_resources(payload: StudioResourcesPayload):
    from core.studio.resources import save_resources

    return {"ok": True, "resources": save_resources(payload.model_dump())}


@app.get("/api/studio/environment")
def get_studio_environment():
    from core.studio.environment import environment_snapshot
    from core.studio.resources import load_resources

    return environment_snapshot(load_resources())


@app.post("/api/studio/environment/credentials")
def create_studio_credential(payload: StudioCredentialPayload):
    from core.studio.environment import upsert_credential

    try:
        item = upsert_credential(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "credential": item}


@app.put("/api/studio/environment/credentials/{credential_key}")
def update_studio_credential(credential_key: str, payload: StudioCredentialPayload):
    from core.studio.environment import upsert_credential

    try:
        item = upsert_credential(payload.model_dump(), credential_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "credential": item}


@app.delete("/api/studio/environment/credentials/{credential_key}")
def remove_studio_credential(credential_key: str):
    from core.studio.environment import delete_credential

    if not delete_credential(credential_key):
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"ok": True}


@app.get("/api/studio/packages")
def get_studio_packages():
    from core.studio.release import package_history

    return {"items": package_history(ROOT)}


@app.get("/api/llm/providers")
def list_llm_providers():
    from core.llm.config_manager import config_paths, list_providers, public_provider
    return {"providers": [public_provider(item) for item in list_providers()], "paths": config_paths()}


@app.post("/api/llm/providers")
def create_llm_provider(payload: LLMProviderPayload):
    from core.llm.config_manager import public_provider, upsert_provider
    try:
        item = upsert_provider(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "provider": public_provider(item)}


@app.put("/api/llm/providers/{provider_id}")
def update_llm_provider(provider_id: str, payload: LLMProviderPayload):
    from core.llm.config_manager import public_provider, upsert_provider
    data = payload.model_dump()
    data["id"] = provider_id
    try:
        item = upsert_provider(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "provider": public_provider(item)}


@app.delete("/api/llm/providers/{provider_id}")
def delete_llm_provider(provider_id: str):
    from core.llm.config_manager import delete_provider
    if not delete_provider(provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"ok": True}


@app.post("/api/llm/providers/{provider_id}/activate")
def activate_llm_provider(provider_id: str):
    from core.llm.config_manager import activate_provider, public_provider
    try:
        item = activate_provider(provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"ok": True, "provider": public_provider(item)}


@app.get("/api/llm/assignments")
def get_llm_assignments():
    from core.llm.config_manager import get_assignments
    return get_assignments()


@app.put("/api/llm/assignments")
def set_llm_assignments(payload: LLMAssignmentsPayload):
    from core.llm.config_manager import get_assignments, save_assignments
    save_assignments(payload.model_dump())
    return {"ok": True, "assignments": get_assignments()}


@app.post("/api/llm/detect")
async def detect_llm_provider(payload: LLMDetectPayload):
    from core.llm.config_manager import get_provider
    from core.llm.detection import LLMDetectionError, detect_model_connection

    stored = get_provider(payload.provider_id) if payload.provider_id else None
    base_url = str(payload.base_url or (stored or {}).get("base_url") or "").strip()
    api_key = str(payload.api_key or (stored or {}).get("api_key") or "").strip()
    preferred_model = str(payload.preferred_model or (stored or {}).get("default_model") or "").strip()
    try:
        result = await detect_model_connection(
            base_url=base_url,
            api_key=api_key,
            preferred_model=preferred_model,
        )
    except LLMDetectionError as exc:
        message = str(exc)
        if api_key:
            message = message.replace(api_key, "***")
        raise HTTPException(status_code=exc.status_code, detail=message) from exc
    result["used_stored_key"] = bool(stored and not payload.api_key and api_key)
    return result


@app.post("/api/llm/test")
async def test_llm_provider(payload: LLMTestPayload):
    from core.llm import ModelConfig, chat
    from core.llm.config_manager import get_provider, mark_provider_tested, provider_route_issue
    provider = get_provider(payload.provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    model = str(payload.model or provider.get("default_model") or "").strip()
    route_issue = provider_route_issue(provider)
    if route_issue:
        mark_provider_tested(payload.provider_id, False)
        raise HTTPException(status_code=400, detail=route_issue)
    missing = []
    if not str(provider.get("base_url") or "").strip():
        missing.append("URL")
    if not str(provider.get("api_key") or "").strip():
        missing.append("Key")
    if not model:
        missing.append("默认模型")
    if missing:
        mark_provider_tested(payload.provider_id, False)
        raise HTTPException(status_code=400, detail=f"连接信息不完整：请填写{'、'.join(missing)}")
    cfg = ModelConfig(
        provider_id=provider.get("id", ""),
        api_type=provider.get("api_type", "openai"),
        wire_api=provider.get("wire_api", "chat_completions"),
        model=model,
        api_key=provider.get("api_key", ""),
        base_url=provider.get("base_url") or None,
        max_tokens=64,
        timeout=int(provider.get("timeout", 120) or 120),
        capabilities=list(provider.get("capabilities") or []),
        adapter_profile=str(provider.get("adapter_profile") or "standard"),
    )
    try:
        if payload.vision:
            test_image = (
                "data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
            content = [
                {"type": "text", "text": payload.prompt or "Inspect this image and reply with OK."},
                {"type": "image_url", "image_url": {"url": test_image, "detail": "low"}},
            ]
        else:
            content = payload.prompt or "OK"
        response = await chat(
            cfg,
            [{"role": "user", "content": content}],
            agent_name="llm_test",
            phase="vision_test" if payload.vision else "test",
        )
        mark_provider_tested(payload.provider_id, True)
        return {
            "ok": True,
            "provider_id": payload.provider_id,
            "model": model,
            "content": response.get("content", "")[:500],
            "capability": "vision" if payload.vision else "text",
            "adapter_profile": provider.get("adapter_profile", "standard"),
            "tested_scope": "vision_input" if payload.vision else "text_protocol",
            "media_capability_tested": False,
            "meta": response.get("meta", {}),
        }
    except Exception as e:
        from core.llm.errors import classify_llm_error
        error = classify_llm_error(e)
        mark_provider_tested(payload.provider_id, False)
        message = str(error)
        api_key = str(provider.get("api_key") or "")
        if api_key:
            message = message.replace(api_key, "***")
        status_code = error.status_code or (504 if "timeout" in message.lower() else 502)
        raise HTTPException(status_code=status_code, detail=f"连接测试失败：{message[:500]}") from e


@app.post("/api/llm/import/opencode")
async def llm_import_opencode(payload: LLMImportTextPayload):
    from core.llm.importers import import_opencode, parse_json_text
    from core.llm.config_manager import public_provider, upsert_provider
    from core.llm.detection import LLMDetectionError, detect_model_connection

    try:
        drafts = import_opencode(parse_json_text(payload.content))
        if not drafts:
            raise ValueError("OpenCode 配置中没有可导入的 provider")
        prepared = []
        detections = []
        for draft in drafts:
            api_key = str(draft.get("api_key") or "")
            try:
                detected = await detect_model_connection(
                    base_url=str(draft.get("base_url") or ""),
                    api_key=api_key,
                    preferred_model=str(draft.get("default_model") or ""),
                )
            except LLMDetectionError as exc:
                message = str(exc).replace(api_key, "***") if api_key else str(exc)
                raise HTTPException(status_code=exc.status_code, detail=f"{draft.get('name') or 'OpenCode provider'}：{message}") from exc
            detected_provider = detected["provider"]
            prepared.append({
                **draft,
                **detected_provider,
                "id": draft.get("id", ""),
                "name": detected_provider.get("name") or draft.get("name", ""),
                "api_key": api_key,
                "available_models": list(dict.fromkeys([
                    *(draft.get("available_models") or []),
                    *(detected["detection"].get("models") or []),
                ])),
                "enabled": True,
                "source": "opencode",
            })
            detections.append(detected["detection"])
        providers = [upsert_provider(item) for item in prepared]
    except HTTPException:
        raise
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "providers": [public_provider(p) for p in providers], "detections": detections}


@app.post("/api/llm/import/claude-code")
def llm_import_claude_code(payload: LLMImportTextPayload):
    from core.llm.importers import import_claude_code, parse_json_text
    from core.llm.config_manager import public_provider, upsert_provider
    try:
        providers = [upsert_provider(p) for p in import_claude_code(parse_json_text(payload.content))]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "providers": [public_provider(p) for p in providers]}


@app.post("/api/llm/import/codex")
def llm_import_codex(payload: LLMCodexImportPayload):
    from core.llm.importers import import_codex
    from core.llm.config_manager import public_provider, upsert_provider
    try:
        providers = [upsert_provider(p) for p in import_codex(payload.config_toml, payload.auth_json)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "providers": [public_provider(p) for p in providers]}


@app.post("/api/llm/import/smart")
def llm_import_smart(payload: LLMImportTextPayload):
    from core.llm.importers import parse_json_text, smart_import
    from core.llm.config_manager import public_provider, save_assignments, upsert_provider
    providers = []
    data = None
    try:
        data = parse_json_text(payload.content)
    except ValueError:
        data = None
    if isinstance(data, dict) and "providers" in data and "assignments" in data:
        try:
            providers = [upsert_provider(p) for p in data.get("providers", [])]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_assignments(data.get("assignments") or {})
        return {"ok": True, "providers": [public_provider(p) for p in providers], "assignments_imported": True}
    try:
        providers = [upsert_provider(p) for p in smart_import(payload.content)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "providers": [public_provider(p) for p in providers], "assignments_imported": False}


@app.get("/api/llm/config/export")
def llm_export_config():
    from core.llm.config_manager import get_assignments, list_providers, public_provider
    # Exports are safe to download or attach to a ticket; local secrets never leave this API.
    return {"version": 1, "providers": [public_provider(item) for item in list_providers()], "assignments": get_assignments()}


@app.post("/api/llm/config/import")
def llm_import_config(payload: LLMImportTextPayload):
    from core.llm.importers import parse_json_text
    from core.llm.config_manager import public_provider, save_assignments, upsert_provider
    try:
        data = parse_json_text(payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="导入内容不是有效 JSON") from exc
    try:
        providers = [upsert_provider(p) for p in data.get("providers", [])]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if data.get("assignments"):
        save_assignments(data["assignments"])
    return {"ok": True, "providers": [public_provider(p) for p in providers], "assignments_imported": bool(data.get("assignments"))}


@app.get("/api/settings")
def get_settings():
    from core.llm.config_manager import list_providers
    providers = list_providers()
    active = next((p for p in providers if p.get("enabled", True)), None)
    if active:
        key = active.get("api_key", "")
        return {
            "provider": active.get("name") or active.get("id"),
            "has_key": bool(key),
            "key_preview": f"...{key[-4:]}" if len(key) > 4 else ("****" if key else ""),
            "base_url": active.get("base_url", ""),
            "model": active.get("default_model", ""),
        }
    return {
        "provider": "未选择",
        "has_key": False,
        "key_preview": "",
        "base_url": "",
        "model": "",
    }


@app.post("/api/settings/provider")
def set_simple_provider(payload: LLMSimpleProviderPayload):
    """兼容旧版快速设置：根据 provider/api_key/base_url/model 创建或激活一个 provider。"""
    from core.llm.config_manager import activate_provider, public_provider, upsert_provider
    provider_name = payload.provider.strip()
    api_key = payload.api_key.strip()
    base_url = payload.base_url.strip()
    model = payload.model.strip()
    is_claude = "claude" in provider_name.lower() or "anthropic" in provider_name.lower()
    api_type = "anthropic" if is_claude else "openai"
    wire_api = "messages" if is_claude else "chat_completions"
    default_model = model or ("claude-opus-4-5" if is_claude else "deepseek-chat")
    if not is_claude and api_key and not api_key.startswith("sk-"):
        api_key = f"sk-{api_key}"
    if not base_url:
        base_url = "https://api.anthropic.com" if is_claude else "https://api.deepseek.com"
    try:
        item = upsert_provider({
            "id": f"quick-{_slug(provider_name) or 'provider'}",
            "name": provider_name or "Quick Provider",
            "api_type": api_type,
            "wire_api": wire_api,
            "base_url": base_url,
            "api_key": api_key,
            "default_model": default_model,
            "enabled": True,
            "source": "quick",
            "timeout": 120,
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    activate_provider(item["id"])
    return {"ok": True, "provider": public_provider(item)}


def _slug(value: str) -> str:
    import re
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or "provider"


def _flow_manifest_files(cartridge_id: str, incoming_files: dict | None = None) -> tuple[dict, dict]:
    import json as _json
    files = dev_flow_manager.read_files(cartridge_id)
    files.update(incoming_files or {})
    manifest = _json.loads(files.get("manifest") or "{}")
    return manifest, files


def _compatibility_for_manifest(manifest: dict, root_flow: dict | None, analysis_target: str = "dev") -> dict:
    base = load_base_implementation(ROOT)
    return build_compatibility_report(base, manifest, root_flow or {}, ROOT, analysis_target=analysis_target)


def _compatibility_for_cartridge(cartridge: dict, analysis_target: str = "dev") -> dict:
    manifest = {**(cartridge.get("manifest") or {}), "_tuning_context": cartridge.get("tuning_context")}
    overlay_dirs = []
    if manifest.get("portable_dlc") and cartridge.get("package_path"):
        overlay_dirs.append(Path(cartridge["package_path"]) / "dlc" / "protocols")
    base = load_base_implementation(ROOT)
    return build_compatibility_report(
        base,
        manifest,
        cartridge.get("root_flow") or {},
        ROOT,
        protocol_overlay_dirs=overlay_dirs,
        analysis_target=analysis_target,
    )


def _compatibility_for_files(cartridge_id: str, incoming_files: dict | None = None) -> dict:
    import json as _json
    files = dev_flow_manager.read_files(cartridge_id)
    files.update(incoming_files or {})
    manifest = _json.loads(files.get("manifest") or "{}")
    root_flow = _json.loads(files.get("root_flow") or "{}")
    return _compatibility_for_manifest(manifest, root_flow)


def _certification_for_manifest(manifest: dict, root_flow: dict | None) -> dict:
    base = load_base_implementation(ROOT)
    return build_protocol_certification_report(base, manifest, root_flow or {}, ROOT)


def _certification_for_cartridge(cartridge: dict) -> dict:
    manifest = {**(cartridge.get("manifest") or {}), "_tuning_context": cartridge.get("tuning_context")}
    overlay_dirs = []
    if manifest.get("portable_dlc") and cartridge.get("package_path"):
        overlay_dirs.append(Path(cartridge["package_path"]) / "dlc" / "protocols")
    base = load_base_implementation(ROOT)
    return build_protocol_certification_report(
        base,
        manifest,
        cartridge.get("root_flow") or {},
        ROOT,
        protocol_overlay_dirs=overlay_dirs,
    )


def _certification_for_files(cartridge_id: str, incoming_files: dict | None = None) -> tuple[dict, dict, dict]:
    import json as _json
    files = dev_flow_manager.read_files(cartridge_id)
    files.update(incoming_files or {})
    manifest = _json.loads(files.get("manifest") or "{}")
    root_flow = _json.loads(files.get("root_flow") or "{}")
    return _certification_for_manifest(manifest, root_flow), manifest, files


def _release_preflight_for_cartridge(cartridge: dict) -> dict:
    from core.cartridge.dependencies import DependencyResolver
    from core.cartridge.environment import EnvironmentChecker
    from core.llm.config_manager import build_model_binding_report
    from core.studio.environment import environment_snapshot
    from core.studio.hygiene import scan_package_hygiene
    from core.studio.portability import build_portability_report
    from core.studio.release import release_contract_preview, resource_preflight
    from core.studio.resources import load_resources

    manifest = cartridge.get("manifest") or {}
    compatibility = _compatibility_for_cartridge(cartridge, analysis_target="publish")
    certification = _certification_for_cartridge(cartridge)
    environment = EnvironmentChecker().check(manifest)
    dependencies = DependencyResolver().resolve(manifest, environment)
    resources = load_resources()
    local_environment = environment_snapshot(resources)
    configured_keys = {item.get("key") for item in local_environment.get("credentials") or [] if item.get("has_value")}
    resource_report = resource_preflight(manifest, resources, configured_keys)
    package_path_value = cartridge.get("package_path")
    package_report = scan_package_hygiene(package_path_value) if package_path_value else {
        "status": "blocked",
        "items": [{"path": ".", "category": "missing_package", "message": "Package directory does not exist."}],
        "scanned_files": 0,
    }
    portability_report = build_portability_report(
        package_path_value or "",
        manifest,
        cartridge.get("root_flow") or {},
        resources=resources,
        configured_keys=configured_keys,
    )

    model_report = build_model_binding_report(manifest, cartridge.get("root_flow") or {})
    model_items = model_report.get("items") or []
    release_preview = release_contract_preview(manifest)
    release_catalog = load_protocol_release_catalog(ROOT)
    release_protocol = release_catalog.default_release_envelope()
    release_protocol_supported = bool(
        release_protocol
        and release_catalog.release_envelope_published(str(release_protocol.get("id") or ""), str(release_protocol.get("version") or ""))
        and supports_protocol_release(load_base_implementation(ROOT), release_protocol)
    )

    issues = []
    for finding in compatibility.get("findings") or []:
        if finding.get("severity") in {"blocker", "warning"}:
            issues.append({"area": "compatibility", "severity": finding.get("severity"), "message": finding.get("message") or finding.get("code")})
    for item in environment.get("items") or []:
        if item.get("status") != "ok":
            issues.append({"area": "environment", "severity": "blocker" if item.get("status") == "blocked" else "warning", "message": item.get("message")})
    for item in dependencies.get("items") or []:
        if item.get("status") not in {"ok", "confirmed", "skipped"}:
            issues.append({"area": "dependencies", "severity": "blocker" if item.get("required") else "warning", "message": f"{item.get('id')}: {item.get('message')}"})
    for item in model_items:
        if item.get("status") != "ok":
            issues.append({"area": "models", "severity": "blocker" if item.get("status") == "blocked" else "warning", "message": f"{item.get('label')}: {item.get('message')}"})
    for item in resource_report.get("items") or []:
        if item.get("status") != "ok":
            issues.append({"area": "resources", "severity": "blocker" if item.get("status") == "blocked" else "warning", "message": f"{item.get('name')}: {item.get('message')}"})
    for item in package_report.get("items") or []:
        issues.append({"area": "package_hygiene", "severity": "blocker", "message": f"{item.get('path')}: {item.get('message')}"})
    for item in portability_report.get("missing_blockers") or []:
        issues.append({"area": "portability", "severity": "blocker", "message": item.get("reason") or item.get("id")})
    for item in portability_report.get("forbidden") or []:
        issues.append({"area": "portability", "severity": "blocker", "message": item.get("reason") or item.get("id")})
    if release_preview.get("status") != "ready":
        for finding in (release_preview.get("report") or {}).get("findings") or []:
            issues.append({"area": "release_envelope", "severity": finding.get("severity") or "blocker", "message": finding.get("message") or finding.get("code")})
    if not release_protocol_supported:
        issues.append({"area": "release_envelope", "severity": "blocker", "message": "CF-CRE@1 is not active and supported by this Base"})

    delivery_level = (compatibility.get("delivery_readiness") or {}).get("level")
    if compatibility.get("legacy"):
        issues.append({"area": "compatibility", "severity": "blocker", "message": "Legacy 卡带不能生成生产包"})
    if delivery_level != "production":
        issues.append({"area": "compatibility", "severity": "blocker", "message": "delivery_readiness.level 必须为 production"})
    production_ready = bool(
        compatibility.get("ok")
        and not compatibility.get("legacy")
        and delivery_level == "production"
        and environment.get("status") != "blocked"
        and dependencies.get("status") != "blocked"
        and model_report.get("status") != "blocked"
        and resource_report.get("status") in {"ok", "warning"}
        and package_report.get("status") == "ok"
        and portability_report.get("status") == "ok"
        and release_preview.get("status") == "ready"
        and release_protocol_supported
    )
    return {
        "cartridge": {key: cartridge.get(key) for key in ("id", "name", "version", "source", "editable")},
        "compatibility": compatibility,
        "certification": certification,
        "environment": environment,
        "dependencies": dependencies,
        "models": model_report,
        "resources": resource_report,
        "package_hygiene": package_report,
        "portability": portability_report,
        "release_envelope": {
            "protocol": f"{(release_protocol or {}).get('id') or 'CF-CRE'}@{(release_protocol or {}).get('version') or '1'}",
            "status": release_preview.get("status"),
            "base_supported": release_protocol_supported,
            "report": release_preview.get("report"),
        },
        "issues": issues,
        "dev_ready": bool(cartridge.get("package_path") and Path(cartridge.get("package_path")).is_dir() and package_report.get("status") == "ok" and portability_report.get("status") == "ok"),
        "production_ready": production_ready,
    }


def _normalize_mcp_tool(raw: dict) -> dict:
    import re as _re
    tool_id = _re.sub(r"[^a-zA-Z0-9_-]+", "_", (raw.get("id") or raw.get("name") or raw.get("tool") or "tool").strip()).strip("_").lower()
    if not tool_id:
        tool_id = "tool"
    item = {
        "id": tool_id,
        "name": raw.get("name") or tool_id,
        "type": raw.get("type") or "builtin",
        "server": raw.get("server") or "filesystem",
        "tool": raw.get("tool") or "",
        "description": raw.get("description") or "",
        "default_params": raw.get("default_params") or {},
        "params_schema": raw.get("params_schema") or {},
        "required": bool(raw.get("required", False)),
        "contract": raw.get("contract") or {},
        "enabled": raw.get("enabled", True),
    }
    return _enrich_mcp_tool_schema(item)


_MCP_SCHEMA_CACHE: dict[tuple[str, str], dict] | None = None


def _mcp_schema_catalog() -> dict[tuple[str, str], dict]:
    global _MCP_SCHEMA_CACHE
    if _MCP_SCHEMA_CACHE is not None:
        return _MCP_SCHEMA_CACHE
    from core.lab.builtin_mcp import BuiltinMcpRegistry

    catalog: dict[tuple[str, str], dict] = {}
    registry_ = BuiltinMcpRegistry(ROOT)
    for item in registry_.describe():
        server = str(item.get("server") or "")
        tool = str(item.get("tool") or "")
        if not server or not tool:
            continue
        properties = {}
        for name, description in (item.get("params") or {}).items():
            properties[str(name)] = _schema_property_from_hint(str(name), str(description or ""))
        catalog[(server, tool)] = {
            "description": item.get("description") or "",
            "params_schema": {
                "type": "object",
                "properties": properties,
            },
        }
    _MCP_SCHEMA_CACHE = catalog
    return catalog


def _schema_property_from_hint(name: str, description: str) -> dict:
    lower = f"{name} {description}".lower()
    field_type = "string"
    if name.startswith(("require_", "enable_", "use_")) or "whether " in lower or "true/false" in lower:
        field_type = "boolean"
    elif any(token in lower for token in ["timeout", "seed", "count", "frames_per_shot", "duration", "fps", "min_outputs"]):
        field_type = "integer"
    elif any(token in lower for token in ["denoise", "strength", "parallax", "zoom"]):
        field_type = "number"
    prop = {"type": field_type, "description": description}
    enum_map = {
        "local/off": ["local", "off"],
        "auto/ffmpeg/local/off": ["auto", "ffmpeg", "local", "off"],
        "start/middle/end": ["start", "middle", "end"],
        "draft or approved": ["draft", "approved"],
        "background/prop/character/location": ["background", "prop", "character", "location"],
    }
    for marker, values in enum_map.items():
        if marker in lower:
            prop["enum"] = values
            break
    return prop


def _enrich_mcp_tool_schema(tool: dict) -> dict:
    item = dict(tool)
    meta = _mcp_schema_catalog().get((str(item.get("server") or ""), str(item.get("tool") or "")), {})
    if not item.get("description") and meta.get("description"):
        item["description"] = meta["description"]
    if not item.get("params_schema") and meta.get("params_schema"):
        item["params_schema"] = meta["params_schema"]
    return item


def _enrich_mcp_tools(tools: list[dict]) -> list[dict]:
    return [_enrich_mcp_tool_schema(item) if isinstance(item, dict) else item for item in tools]


def _write_manifest_tools(cartridge_id: str, files: dict, manifest: dict) -> dict:
    import json as _json
    files["manifest"] = _json.dumps(manifest, ensure_ascii=False, indent=2)
    dev_flow_manager.save_file(cartridge_id, "manifest", files["manifest"])
    return {"files": files, "mcp_tools": _enrich_mcp_tools(manifest.get("mcp_tools", []))}


@app.get("/api/cartridges")
def list_cartridges():
    return {"items": registry.list_cartridges()}


@app.post("/api/cartridges/import")
def import_cartridge(payload: CartridgeImportPayload):
    import base64 as _base64
    import binascii as _binascii
    import io as _io
    import json as _json
    import re as _re
    import shutil as _shutil
    import uuid as _uuid
    import zipfile as _zipfile

    install_mode = payload.install_mode or "keep_existing"
    if install_mode not in {"keep_existing", "replace"}:
        raise HTTPException(status_code=400, detail="install_mode must be keep_existing or replace")

    encoded_archive = payload.content_base64 or ""
    max_base64_chars = ((MAX_CARTRIDGE_ARCHIVE_BYTES + 2) // 3) * 4
    if len(encoded_archive) > max_base64_chars:
        raise HTTPException(status_code=413, detail="Cartridge package exceeds 128 MiB")
    try:
        archive_bytes = _base64.b64decode(encoded_archive, validate=True)
    except (_binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 cartridge content")
    if not archive_bytes:
        raise HTTPException(status_code=400, detail="Cartridge package is empty")
    if len(archive_bytes) > MAX_CARTRIDGE_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="Cartridge package exceeds 128 MiB")

    tmp_root = ROOT / IMPORTS_DIR
    tmp_dir = tmp_root / f"import_{_uuid.uuid4().hex}"
    extract_dir = tmp_dir / "package"
    installed_root = ROOT / INSTALLED_CARTRIDGES_DIR
    extract_root_resolved = extract_dir.resolve()
    release_install = None
    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            with _zipfile.ZipFile(_io.BytesIO(archive_bytes)) as zf:
                bad_member = zf.testzip()
                if bad_member:
                    raise HTTPException(status_code=400, detail=f"Invalid cartridge zip member: {bad_member}")
                members = zf.infolist()
                if not members:
                    raise HTTPException(status_code=400, detail="Cartridge zip is empty")
                is_cre_archive = "release.manifest.json" in {member.filename for member in members}
                if is_cre_archive:
                    archive_path = tmp_dir / "release.cf-cre.zip"
                    archive_path.write_bytes(archive_bytes)
                    try:
                        release_install = extract_release_payload(
                            archive_path,
                            extract_dir,
                            trusted_keys=trusted_public_keys(ROOT),
                        )
                    except ReleaseBuildError as exc:
                        raise HTTPException(status_code=400, detail=f"CF-CRE release cannot be activated: {exc}") from exc
                else:
                    _validate_cartridge_archive_members(members, extract_dir)
                    zf.extractall(extract_dir)
        except _zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid cartridge zip")

        manifest_path = extract_dir / "manifest.json"
        if not manifest_path.is_file():
            raise HTTPException(status_code=400, detail="Cartridge package must contain manifest.json at the zip root")
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        except _json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"manifest.json is not valid JSON: {e.msg}")

        cartridge_id = str(manifest.get("id") or "").strip()
        if not _re.fullmatch(r"[A-Za-z0-9._-]+", cartridge_id):
            raise HTTPException(status_code=400, detail="manifest.id may only contain letters, numbers, dot, underscore, and hyphen")

        root_flow = {}
        try:
            root_entry = manifest.get("root_flow", {}).get("entry", "root.flow.json")
            root_flow_path = (extract_dir / root_entry).resolve()
            if root_flow_path != extract_root_resolved and extract_root_resolved not in root_flow_path.parents:
                raise HTTPException(status_code=400, detail="root_flow entry points outside the cartridge package")
            registry.validator.validate_package(extract_dir, manifest)
            if root_flow_path.is_file():
                root_flow = _json.loads(root_flow_path.read_text(encoding="utf-8"))
            if release_install:
                compatibility = _compatibility_for_manifest(manifest, root_flow, analysis_target="production")
                if not compatibility.get("ok"):
                    raise HTTPException(status_code=400, detail={
                        "error": "release_payload_incompatible",
                        "message": "CF-CRE payload does not meet this Base's production compatibility contract.",
                        "report": compatibility,
                    })
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(status_code=400, detail=str(e))

        dev_path = registry.dev_dir / cartridge_id
        builtin_path = registry.builtin_dir / cartridge_id
        if dev_path.exists() or builtin_path.exists():
            raise HTTPException(status_code=409, detail="A dev or builtin cartridge with this id already exists")

        installed_root.mkdir(parents=True, exist_ok=True)
        target_dir = installed_root / cartridge_id
        replaced = target_dir.exists()
        if replaced and install_mode != "replace":
            raise HTTPException(status_code=409, detail="Cartridge is already installed")
        if replaced:
            _shutil.rmtree(target_dir)
        _shutil.move(str(extract_dir), str(target_dir))
        cartridge = registry.get_cartridge(cartridge_id)
        activation = None
        if release_install:
            preflight = _release_preflight_for_cartridge(cartridge)
            activation = {
                "status": "active" if preflight.get("production_ready") else "installed_pending_rebind",
                "allowed": bool(preflight.get("production_ready")),
                "release_id": ((release_install.get("inspection") or {}).get("release") or {}).get("release_id"),
                "signature": (release_install.get("inspection") or {}).get("signature"),
            }
        return {
            "ok": True,
            "cartridge": cartridge,
            "installed_path": _public_data_path(target_dir),
            "replaced": replaced,
            "activation": activation,
        }
    finally:
        _shutil.rmtree(tmp_dir, ignore_errors=True)


@app.get("/api/cartridges/{cartridge_id}")
def get_cartridge(cartridge_id: str):
    try:
        return registry.get_cartridge(cartridge_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/cartridges/{cartridge_id}/compatibility")
def get_cartridge_compatibility(cartridge_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        return _compatibility_for_cartridge(cartridge)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cartridges/{cartridge_id}/certification")
def get_cartridge_certification(cartridge_id: str):
    try:
        cartridge = registry.get_packaging_cartridge(cartridge_id)
        return _certification_for_cartridge(cartridge)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except (OSError, json.JSONDecodeError, TuningProtocolError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/studio/release/{cartridge_id}/preflight")
def get_studio_release_preflight(cartridge_id: str):
    try:
        return _release_preflight_for_cartridge(registry.get_packaging_cartridge(cartridge_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except BaseManifestError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except (OSError, json.JSONDecodeError, TuningProtocolError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/cartridges/{cartridge_id}/portability")
def get_cartridge_portability(cartridge_id: str):
    try:
        return _release_preflight_for_cartridge(registry.get_packaging_cartridge(cartridge_id))["portability"]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except BaseManifestError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except (OSError, json.JSONDecodeError, TuningProtocolError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/cartridges/{cartridge_id}/package")
def package_cartridge(cartridge_id: str, payload: CartridgePackagePayload | None = None):
    try:
        cartridge = registry.get_packaging_cartridge(cartridge_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (OSError, json.JSONDecodeError, TuningProtocolError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={
            "error": "recipe_release_required",
            "message": str(exc),
        }) from exc
    try:
        compatibility = _compatibility_for_cartridge(cartridge, analysis_target="package")
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))
    package_mode = (payload.package_mode if payload else "dev") or "dev"
    if package_mode not in {"dev", "production"}:
        raise HTTPException(status_code=400, detail="package_mode must be dev or production")
    import re as _re
    import json as _json
    import zipfile as _zipfile
    package_path = Path(cartridge.get("package_path") or "")
    if not package_path.is_dir():
        raise HTTPException(status_code=404, detail="Cartridge package path not found")
    tuning_contract = cartridge.get("tuning_contract") if isinstance(cartridge.get("tuning_contract"), dict) else None
    if tuning_contract and not compatibility.get("ok"):
        raise HTTPException(status_code=400, detail={
            "error": "recipe_release_incompatible",
            "message": "当前配方发布未通过打包兼容性检查",
            "report": compatibility,
        })
    from core.studio.hygiene import scan_package_hygiene
    package_hygiene = scan_package_hygiene(package_path)
    if package_hygiene.get("status") != "ok":
        raise HTTPException(status_code=400, detail={
            "error": "package_hygiene_failed",
            "message": "Package contains local, secret, model, cache, log, or runtime artifacts.",
            "report": package_hygiene,
        })
    release_preflight = _release_preflight_for_cartridge(cartridge)
    portability = release_preflight["portability"]
    if portability.get("status") != "ok":
        raise HTTPException(status_code=400, detail={
            "error": "portability_preflight_failed",
            "message": "Package portability report contains blocking items.",
            "report": portability,
        })
    if package_mode == "production":
        if not release_preflight.get("production_ready"):
            raise HTTPException(status_code=400, detail={
                "error": "production_preflight_failed",
                "message": "Production package preflight contains blocking items.",
                "report": release_preflight,
            })
    safe_id = _re.sub(r"[^a-zA-Z0-9._-]+", "_", cartridge_id)
    version = _re.sub(r"[^a-zA-Z0-9._-]+", "_", str(cartridge.get("version") or "0.0.0"))
    out_dir = ROOT / PACKAGES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    if package_mode == "production":
        from core.studio.release import release_archive_inputs

        release_inputs = release_archive_inputs(cartridge.get("manifest") or {})
        safe_publisher = _re.sub(r"[^a-zA-Z0-9._-]+", "_", str(release_inputs["publisher_id"]))
        signing_identity = ensure_development_signing_identity(ROOT, safe_publisher)
        out_file = out_dir / f"{safe_id}-{version}.cf-cre.zip"
        try:
            built = build_release_archive(
                package_path,
                out_file,
                publisher_id=safe_publisher,
                experience=release_inputs["experience"],
                delivery=release_inputs["delivery"],
                placement=release_inputs["placement"],
                required_capabilities=release_inputs["required_capabilities"],
                required_permissions=release_inputs["required_permissions"],
                signing_identity=signing_identity,
            )
            inspection = inspect_release_archive(out_file, trusted_keys=trusted_public_keys(ROOT))
        except ReleaseBuildError as exc:
            raise HTTPException(status_code=400, detail={"error": "release_build_failed", "message": str(exc)}) from exc
        if not inspection.get("activation_allowed"):
            raise HTTPException(status_code=400, detail={
                "error": "release_activation_blocked",
                "message": "CF-CRE package failed signature trust or integrity activation checks.",
                "report": inspection,
            })
        return {
            "ok": True,
            "cartridge_id": cartridge_id,
            "filename": out_file.name,
            "package_mode": package_mode,
            "protocol": "CF-CRE@1",
            "release_id": built["release_id"],
            "activation_allowed": inspection["activation_allowed"],
            "signature": inspection.get("signature"),
            "url": f"/packages/{out_file.name}",
            "size": out_file.stat().st_size,
            "portability": portability,
            "mcp_tool_count": len(cartridge.get("mcp_tools") or []),
            "compatibility": {
                "ok": compatibility.get("ok"),
                "status": compatibility.get("status"),
                "legacy": compatibility.get("legacy"),
                "summary": compatibility.get("summary", {}),
            },
        }
    out_file = out_dir / f"{safe_id}-{version}.cartridge.zip"
    root = package_path.resolve()
    from core.studio.release import build_binding_descriptor
    from core.studio.resources import load_resources
    binding_descriptor = build_binding_descriptor(cartridge.get("manifest") or {}, load_resources())
    with _zipfile.ZipFile(out_file, "w", compression=_zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(root.rglob("*")):
            if item.is_file():
                zf.write(item, item.relative_to(root).as_posix())
        zf.writestr("package.compatibility.json", _json.dumps(compatibility, ensure_ascii=False, indent=2))
        flow_analysis = (compatibility.get("flow_contract") or {}).get("analysis")
        if isinstance(flow_analysis, dict):
            zf.writestr("package.flow-analysis.json", _json.dumps(flow_analysis, ensure_ascii=False, indent=2))
        zf.writestr("package.local-bindings.json", _json.dumps(binding_descriptor, ensure_ascii=False, indent=2))
        zf.writestr("package.portability.json", _json.dumps(portability, ensure_ascii=False, indent=2))
        zf.writestr("package.metadata.json", _json.dumps({
            "schema": "cartridgeflow.package_metadata.v1",
            "package_mode": package_mode,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2))
    return {
        "ok": True,
        "cartridge_id": cartridge_id,
        "filename": out_file.name,
        "package_mode": package_mode,
        "url": f"/packages/{out_file.name}",
        "size": out_file.stat().st_size,
        "portability": portability,
        "mcp_tool_count": len(cartridge.get("mcp_tools") or []),
        "compatibility": {
            "ok": compatibility.get("ok"),
            "status": compatibility.get("status"),
            "legacy": compatibility.get("legacy"),
            "summary": compatibility.get("summary", {}),
        },
    }


@app.post("/api/cartridges/{cartridge_id}/load")
def load_cartridge(cartridge_id: str):
    try:
        return registry.get_cartridge(cartridge_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/cartridges/{cartridge_id}/dlc/frontend")
def serve_cartridge_dlc_frontend(cartridge_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        descriptor = load_portable_dlc_descriptor(cartridge["package_path"], cartridge["manifest"])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PortableDlcValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    entry = (descriptor.get("frontend") or {}).get("entry")
    if not entry:
        raise HTTPException(status_code=404, detail="Cartridge has no frontend DLC")
    target = (Path(cartridge["package_path"]) / entry).resolve()
    response = FileResponse(target, media_type="text/html")
    # GLTF/VRM loaders materialize embedded textures as blob URLs inside the isolated iframe.
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
        "img-src 'self' data: blob:; connect-src 'self' blob:; object-src 'none'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/cartridges/{cartridge_id}/dlc/assets/{asset_path:path}")
def serve_cartridge_dlc_asset(cartridge_id: str, asset_path: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        descriptor = load_portable_dlc_descriptor(cartridge["package_path"], cartridge["manifest"])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PortableDlcValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    entry = str((descriptor.get("frontend") or {}).get("entry") or "")
    if not entry:
        raise HTTPException(status_code=404, detail="Cartridge has no frontend DLC")
    package_root = Path(cartridge["package_path"]).resolve()
    frontend_root = (package_root / entry).resolve().parent
    target = (frontend_root / asset_path).resolve()
    if target != frontend_root and frontend_root not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid DLC asset path")
    relative = target.relative_to(package_root).as_posix()
    declared = {str(item.get("path") or "").replace("\\", "/") for item in descriptor.get("files") or [] if isinstance(item, dict)}
    if relative not in declared or not target.is_file():
        raise HTTPException(status_code=404, detail="DLC asset is not declared")
    response = FileResponse(target)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/cartridge-runs/{run_id}/dlc-context")
def get_cartridge_run_dlc_context(run_id: str):
    try:
        run = runner.get_run(run_id)
        cartridge = registry.get_cartridge(run["cartridge_id"])
        descriptor = load_portable_dlc_descriptor(cartridge["package_path"], cartridge["manifest"])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PortableDlcValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    state_path = runner.runs_dir / run_id / "root_flow_state.json"
    state = runner._read_json(state_path) if state_path.is_file() else {}
    store = ((state.get("context") or {}).get("store") or {}) if isinstance(state, dict) else {}
    context = {}
    for key in (descriptor.get("frontend") or {}).get("context_keys") or []:
        value = store.get(key)
        if isinstance(value, str):
            try:
                value = __import__("json").loads(value)
            except ValueError:
                pass
        context[str(key)] = value
    artifacts = []
    for item in run.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        artifacts.append({
            "name": item.get("name"),
            "type": item.get("type"),
            "mime_type": item.get("mime_type"),
            "path": source.get("original_path") or item.get("display_path") or item.get("path"),
            "preview_url": item.get("url"),
            "source_node_id": source.get("node_id"),
        })
    return {
        "schema": "cartridgeflow.dlc_ui_host.v1",
        "run_id": run_id,
        "cartridge_id": run["cartridge_id"],
        "frontend_url": f"/api/cartridges/{run['cartridge_id']}/dlc/frontend",
        "pending_interaction": run.get("pending_interaction"),
        "context": context,
        "artifacts": artifacts,
    }


@app.delete("/api/cartridges/{cartridge_id}/installed")
def uninstall_cartridge(cartridge_id: str):
    import shutil as _shutil
    import stat as _stat

    try:
        cartridge = registry.get_cartridge(cartridge_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if cartridge.get("source") != "installed":
        raise HTTPException(status_code=403, detail="Only installed cartridges can be uninstalled")
    package_path = Path(cartridge.get("package_path") or "")
    installed_root = (ROOT / INSTALLED_CARTRIDGES_DIR).resolve()
    try:
        package_path = package_path.resolve()
        if package_path == installed_root or installed_root not in package_path.parents:
            raise HTTPException(status_code=400, detail="Invalid installed cartridge path")
    except OSError as e:
        raise HTTPException(status_code=404, detail=str(e))
    for item in package_path.rglob("*"):
        try:
            item.chmod(_stat.S_IWRITE)
        except OSError:
            pass
    _shutil.rmtree(package_path)
    dlc_data_root = (ROOT / CARTRIDGE_DATA_DIR).resolve()
    private_root = (dlc_data_root / cartridge_id).resolve()
    if private_root != dlc_data_root and dlc_data_root in private_root.parents and private_root.is_dir():
        _shutil.rmtree(private_root)
    runner.lab_node_executor._scoped_mcp_registries.clear()
    return {
        "ok": not package_path.exists(),
        "cartridge_id": cartridge_id,
        "package_removed": not package_path.exists(),
        "private_data_removed": not private_root.exists(),
        "user_artifacts_preserved": True,
    }


@app.post("/api/cartridges/{cartridge_id}/clone-to-dev")
def clone_cartridge_to_dev(cartridge_id: str, payload: CartridgeCloneToDevPayload):
    import json as _json
    import re as _re
    import shutil as _shutil

    try:
        source = registry.get_cartridge(cartridge_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if source.get("source") == "dev" or source.get("editable"):
        raise HTTPException(status_code=400, detail="Dev cartridges are already editable")

    new_id = _re.sub(r"[^a-zA-Z0-9._-]+", ".", (payload.new_id or "").strip()).strip(".").lower()
    if not new_id:
        raise HTTPException(status_code=400, detail="new_id is required")
    if not new_id.startswith("dev."):
        new_id = f"dev.{new_id}"
    if not _re.fullmatch(r"[a-zA-Z0-9._-]+", new_id):
        raise HTTPException(status_code=400, detail="new_id may only contain letters, numbers, dot, underscore, and hyphen")
    target = (registry.dev_dir / new_id).resolve()
    dev_root = registry.dev_dir.resolve()
    try:
        if target == dev_root or dev_root not in target.parents:
            raise HTTPException(status_code=400, detail="Invalid dev flow id")
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if target.exists():
        raise HTTPException(status_code=409, detail=f"Dev flow already exists: {new_id}")

    source_path = Path(source.get("package_path") or "")
    if not source_path.is_dir():
        raise HTTPException(status_code=404, detail="Source cartridge package path not found")
    registry.dev_dir.mkdir(parents=True, exist_ok=True)
    try:
        _shutil.copytree(source_path, target)
        manifest_path = target / "manifest.json"
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["id"] = new_id
        manifest["name"] = payload.name.strip() or f"{source.get('name') or cartridge_id} Copy"
        manifest["description"] = payload.description.strip() or manifest.get("description", "")
        manifest["category"] = "dev_flow"
        manifest_path.write_text(_json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        portable_dlc = manifest.get("portable_dlc") if isinstance(manifest.get("portable_dlc"), dict) else None
        if portable_dlc and portable_dlc.get("descriptor"):
            descriptor_path = (target / str(portable_dlc["descriptor"])).resolve()
            if target.resolve() not in descriptor_path.parents or not descriptor_path.is_file():
                raise HTTPException(status_code=400, detail="Invalid portable DLC descriptor path")
            descriptor = _json.loads(descriptor_path.read_text(encoding="utf-8"))
            descriptor["owner_cartridge"] = new_id
            descriptor_path.write_text(_json.dumps(descriptor, ensure_ascii=False, indent=2), encoding="utf-8")

        root_entry = manifest.get("root_flow", {}).get("entry", "root.flow.json")
        root_flow_path = target / root_entry
        if root_flow_path.is_file():
            root_flow = _json.loads(root_flow_path.read_text(encoding="utf-8"))
            root_flow["cartridge_id"] = new_id
            root_flow["id"] = f"{new_id}.root"
            if root_flow.get("name"):
                root_flow["name"] = f"{manifest['name']} Root Flow"
            root_flow_path.write_text(_json.dumps(root_flow, ensure_ascii=False, indent=2), encoding="utf-8")

        cartridge = registry.get_cartridge(new_id)
        return {"ok": True, "cartridge": cartridge, "id": new_id, "path": str(target)}
    except Exception as e:
        _shutil.rmtree(target, ignore_errors=True)
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/lab/flows")
def list_lab_flows():
    items = []
    for cartridge in registry.list_cartridges():
        items.append({
            **cartridge,
            "source": cartridge.get("source", "builtin"),
            "editable": cartridge.get("editable", False),
            "flow_kind": "root_flow",
        })
    return {"items": items}


@app.post("/api/lab/flows")
def create_lab_flow(payload: DevFlowCreate):
    try:
        result = dev_flow_manager.create_flow(payload.flow_id, payload.name, payload.description)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.post("/api/lab/flows/simulations/authoring")
def simulate_lab_flow_authoring(payload: AuthoringSimulationPayload = AuthoringSimulationPayload()):
    """Exercise the same create/edit/validate services used by the workbench without user data."""
    cartridge_id = f"dev.authoring-simulation-{uuid.uuid4().hex[:10]}"
    steps: list[dict] = []
    created = False
    try:
        create_lab_flow(DevFlowCreate(
            flow_id=cartridge_id,
            name="流程创作仿真",
            description="由创作技能发起的隔离工作台仿真。",
        ))
        created = True
        steps.append({"action": "创建开发卡带", "ok": True})

        node_result = create_lab_flow_node(cartridge_id, NodeCreatePayload(
            template_id="runtime",
            node_id="organize_result",
            title="整理结果",
            after_node_id="start",
        ))
        steps.append({"action": "在画布创建业务节点", "ok": node_result.get("status") == "node_created"})

        layout_result = save_lab_flow_layout(cartridge_id, LayoutSavePayload(layout={
            "organize_result": {"x": 860, "y": 120},
        }))
        steps.append({"action": "保存画布布局", "ok": layout_result.get("status") == "layout_saved"})

        validation = validate_lab_flow(cartridge_id, DevFlowFilesPayload())
        steps.append({"action": "流程验证", "ok": bool(validation.get("valid")), "errors": validation.get("errors") or []})

        compatibility = get_lab_flow_compatibility(cartridge_id, DevFlowFilesPayload())
        steps.append({"action": "运行兼容性检查", "ok": bool(compatibility.get("ok")), "findings": compatibility.get("findings") or []})

        catalog = get_lab_flow_resource_catalog(cartridge_id)
        steps.append({"action": "读取资源目录", "ok": isinstance(catalog.get("tools"), list), "findings": catalog.get("findings") or []})
    except HTTPException as exc:
        steps.append({"action": "工作台服务调用", "ok": False, "error": exc.detail})
    except Exception as exc:  # Preserve unexpected implementation failures for the skill caller.
        steps.append({"action": "工作台服务调用", "ok": False, "error": str(exc)})
    finally:
        if created and not payload.keep_temporary_cartridge:
            try:
                delete_lab_flow(cartridge_id)
                steps.append({"action": "清理临时卡带", "ok": True})
            except Exception as exc:
                steps.append({"action": "清理临时卡带", "ok": False, "error": str(exc)})

    return {
        "ok": bool(steps) and all(step.get("ok") for step in steps),
        "simulation_id": cartridge_id,
        "temporary_cartridge_retained": bool(created and payload.keep_temporary_cartridge),
        "steps": steps,
    }


def _open_directory(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    command = ["open", str(path)] if sys.platform == "darwin" else ["xdg-open", str(path)]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


@app.post("/api/lab/flows/{cartridge_id}/open-directory")
def open_lab_flow_directory(cartridge_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    raw_path = str(cartridge.get("package_path") or "").strip()
    if not raw_path:
        raise HTTPException(status_code=404, detail="Cartridge directory is not registered")
    candidate = Path(raw_path)
    path = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    root = ROOT.resolve()
    if not path.is_dir() or (path != root and root not in path.parents):
        raise HTTPException(status_code=403, detail="Cartridge directory is outside the Studio workspace")
    try:
        _open_directory(path)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to open cartridge directory: {exc}")
    return {"ok": True, "id": cartridge_id, "path": str(path.relative_to(root))}


@app.delete("/api/lab/flows/{cartridge_id}")
def delete_lab_flow(cartridge_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        return dev_flow_manager.delete_flow(cartridge_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/lab/flows/{cartridge_id}")
def get_lab_flow(cartridge_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    graph = flow_graph_builder.build(cartridge)
    runs = [run for run in runner.list_runs() if run.get("cartridge_id") == cartridge_id]
    latest_run = runs[0] if runs else None
    try:
        compatibility = _compatibility_for_cartridge(cartridge)
    except Exception as exc:
        compatibility = {
            "ok": False,
            "status": "blocked",
            "findings": [{"severity": "blocker", "code": "compatibility_error", "message": str(exc)}],
            "summary": {"blocker": 1, "warning": 0, "info": 0},
        }
    return {
        "cartridge": cartridge,
        "graph": graph,
        "runs": runs[:5],
        "latest_run_events": runner.get_events(latest_run["run_id"]) if latest_run else [],
        "compatibility": compatibility,
    }


@app.get("/api/lab/flows/{cartridge_id}/files")
def get_lab_flow_files(cartridge_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        return {"cartridge_id": cartridge_id, "files": dev_flow_manager.read_files(cartridge_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/lab/flows/{cartridge_id}/tuning")
def get_lab_flow_tuning(cartridge_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows expose tuning history")
        raw_flow = json.loads(dev_flow_manager.read_files(cartridge_id)["root_flow"] or "{}")
        repository = dev_flow_manager.tuning.load(cartridge_id, raw_flow)
        return {
            "repository": dev_flow_manager.tuning.release_summary(repository),
            "tuning_context": cartridge.get("tuning_context"),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TuningProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/lab/flows/{cartridge_id}/tuning/nodes/{node_id}/revisions")
def create_lab_flow_tuning_revision(cartridge_id: str, node_id: str, payload: TuningRevisionPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows can create tuning revisions")
        repository, revision, root_flow, context = dev_flow_manager.tuning.create_revision(
            cartridge_id,
            node_id,
            payload.patch,
            expected_head=payload.expected_head,
            author=payload.author,
            message=payload.message,
        )
        files = dev_flow_manager.read_files(cartridge_id)
        manifest = json.loads(files["manifest"] or "{}")
        graph = flow_graph_builder.build({**manifest, "root_flow": root_flow, "tuning_context": context})
        return {
            "status": "tuning_revision_created",
            "node_id": node_id,
            "revision": revision,
            "repository": dev_flow_manager.tuning.release_summary(repository),
            "tuning_context": context,
            "files": files,
            "graph": graph,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TuningConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except TuningProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/lab/flows/{cartridge_id}/tuning/releases")
def publish_lab_flow_recipe_release(cartridge_id: str, payload: RecipeReleasePayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows can publish recipe releases")
        repository, release = dev_flow_manager.tuning.publish(
            cartridge_id,
            author=payload.author,
            message=payload.message,
        )
        return {
            "status": "recipe_release_published",
            "release": release,
            "repository": dev_flow_manager.tuning.release_summary(repository),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TuningProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/lab/flows/{cartridge_id}/tuning/releases/{release_id}/activate")
def activate_lab_flow_recipe_release(cartridge_id: str, release_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows can activate recipe releases")
        repository, release = dev_flow_manager.tuning.activate(cartridge_id, release_id)
        return {
            "status": "recipe_release_activated",
            "release": release,
            "repository": dev_flow_manager.tuning.release_summary(repository),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TuningProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _authoring_error(exc: AuthoringServiceError):
    raise HTTPException(status_code=exc.status, detail=exc.as_dict())


def _creator_ai_timeout(model) -> int:
    try:
        configured = int(getattr(model, "timeout", 120) or 120)
    except (TypeError, ValueError):
        configured = 120
    return min(120, max(30, configured))


@app.post("/api/creator/possibilities")
async def discover_creator_possibilities_endpoint(payload: CreatorDiscoveryPayload):
    from core.llm import chat
    from core.llm.config_manager import resolve_model
    from core.llm.creator_discovery import CreatorDiscoveryError, build_creator_discovery_messages, parse_creator_discovery
    try:
        model = resolve_model("mentor")
        if not str(model.api_key or "").strip():
            raise AuthoringServiceError("AI_CREATOR_DISCOVERY_MODEL_UNBOUND", "No configured discovery model is available.", status=409)
        messages = build_creator_discovery_messages(payload.context)
        try:
            response = await asyncio.wait_for(
                chat(model, messages, agent_name="creator_discovery", phase="possibility_discovery"),
                timeout=_creator_ai_timeout(model),
            )
        except TimeoutError as exc:
            raise AuthoringServiceError("AI_CREATOR_DISCOVERY_TIMEOUT", "The AI discovery service did not respond in time.", status=504) from exc
        try:
            possibilities = parse_creator_discovery(str(response.get("content") or ""))
        except CreatorDiscoveryError as exc:
            raise AuthoringServiceError("AI_CREATOR_DISCOVERY_OUTPUT_INVALID", str(exc), status=502) from exc
        return {"schema": "cartridgeflow.creator_possibilities.v1", "context": " ".join(payload.context.split()), "possibilities": possibilities}
    except AuthoringServiceError as exc:
        _authoring_error(exc)
    except ValueError as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_DISCOVERY_MODEL_UNBOUND", str(exc), status=409))
    except Exception as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_DISCOVERY_FAILED", str(exc), status=502))


@app.post("/api/creator/default-recipe")
async def create_creator_default_recipe(payload: CreatorDefaultRecipePayload):
    from core.llm import chat
    from core.llm.config_manager import resolve_model
    from core.llm.creator_discovery import CreatorDiscoveryError, build_default_recipe_messages, parse_default_recipe
    try:
        model = resolve_model("mentor")
        if not str(model.api_key or "").strip():
            raise AuthoringServiceError("AI_CREATOR_DEFAULT_RECIPE_MODEL_UNBOUND", "No configured default recipe model is available.", status=409)
        try:
            response = await asyncio.wait_for(
                chat(model, build_default_recipe_messages(payload.context), agent_name="creator_default_recipe", phase="default_recipe"),
                timeout=_creator_ai_timeout(model),
            )
        except TimeoutError as exc:
            raise AuthoringServiceError("AI_CREATOR_DEFAULT_RECIPE_TIMEOUT", "The AI default recipe service did not respond in time.", status=504) from exc
        try:
            recipe = parse_default_recipe(str(response.get("content") or ""))
        except CreatorDiscoveryError as exc:
            raise AuthoringServiceError("AI_CREATOR_DEFAULT_RECIPE_OUTPUT_INVALID", str(exc), status=502) from exc
        return {"schema": "cartridgeflow.creator_default_recipe.v1", "recipe": recipe}
    except AuthoringServiceError as exc:
        _authoring_error(exc)
    except ValueError as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_DEFAULT_RECIPE_MODEL_UNBOUND", str(exc), status=409))
    except Exception as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_DEFAULT_RECIPE_FAILED", str(exc), status=502))


def _all_capability_releases() -> list[dict]:
    """Combine recursive Flow releases with compatible single-node publications."""
    releases: dict[str, dict] = {}
    for entry in trusted_node_presets.list_entries():
        if entry.get("status") != "active":
            continue
        try:
            release = legacy_node_capability(entry["current"])
        except (CapabilityCartridgeError, KeyError) as exc:
            raise AuthoringServiceError("CAPABILITY_REGISTRY_INVALID", str(exc), status=500) from exc
        releases[release["id"]] = release
    for release in capability_cartridges.list_active():
        releases[release["id"]] = release
    return [releases[key] for key in sorted(releases)]


def _capability_flow_snapshot(flow_id: str) -> dict:
    cartridge = registry.get_cartridge(flow_id)
    manifest = cartridge.get("manifest") if isinstance(cartridge.get("manifest"), dict) else {}
    root_flow = cartridge.get("root_flow") if isinstance(cartridge.get("root_flow"), dict) else {}
    source_path = dev_flow_manager._flow_path(flow_id)
    source_files: dict[str, str] = {}
    for path in sorted(source_path.rglob("*")):
        if not path.is_file() or path.name in {"manifest.json", "root.flow.json"} or ".tuning" in path.parts:
            continue
        relative = path.relative_to(source_path).as_posix()
        if path.is_symlink():
            raise AuthoringServiceError(
                "CAPABILITY_SOURCE_FILE_UNSUPPORTED",
                f"Capability file must not be a symbolic link: {relative}",
                status=409,
            )
        if path.stat().st_size > MAX_SOURCE_FILE_BYTES:
            raise AuthoringServiceError(
                "CAPABILITY_SOURCE_FILE_UNSUPPORTED",
                f"Capability file exceeds the 4 MiB limit: {relative}",
                status=409,
            )
        try:
            source_files[relative] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise AuthoringServiceError(
                "CAPABILITY_SOURCE_FILE_UNSUPPORTED",
                f"Capability file must be UTF-8 text: {relative}",
                status=409,
            ) from exc
    digest = canonical_digest({"manifest": manifest, "root_flow": root_flow, "files": source_files})
    return {
        "manifest": manifest,
        "root_flow": root_flow,
        "source_files": source_files,
        "source_digest": digest,
    }


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _safe_evidence_path(root: Path, value: str) -> Path:
    normalized = str(value or "").strip()
    if not normalized or Path(normalized).name != normalized or not re.fullmatch(r"[A-Za-z0-9_.-]+", normalized):
        raise AuthoringServiceError("CAPABILITY_EVIDENCE_ID_INVALID", "Capability evidence id is invalid.")
    return root / f"{normalized}.json"


@app.post("/api/developer/flows/{flow_id}/capability-verifications")
def verify_developer_flow_capability(flow_id: str, payload: CapabilityVerificationPayload):
    """Bind one real success and one real safe-failure run to the current Flow source."""
    try:
        if payload.success_run_id == payload.failure_run_id:
            raise AuthoringServiceError(
                "CAPABILITY_EVIDENCE_RUNS_NOT_DISTINCT",
                "Success and failure evidence must come from different runs.",
                status=409,
            )
        snapshot = _capability_flow_snapshot(flow_id)
        success = runner.get_run(payload.success_run_id)
        failure = runner.get_run(payload.failure_run_id)
        for run, expected, label in ((success, "completed", "success"), (failure, "failed", "failure")):
            if run.get("cartridge_id") != flow_id:
                raise AuthoringServiceError(
                    "CAPABILITY_EVIDENCE_FLOW_MISMATCH",
                    f"The {label} run belongs to a different Flow.",
                    status=409,
                )
            record_path = _safe_evidence_path(capability_test_run_dir, str(run.get("run_id") or ""))
            if not record_path.is_file():
                raise AuthoringServiceError(
                    "CAPABILITY_EVIDENCE_SOURCE_UNKNOWN",
                    f"The {label} run was not started as a capability verification run.",
                    status=409,
                )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("source_digest") != snapshot["source_digest"]:
                raise AuthoringServiceError(
                    "CAPABILITY_EVIDENCE_SOURCE_STALE",
                    f"The Flow changed after the {label} run. Run both checks again.",
                    status=409,
                )
            if run.get("status") != expected:
                raise AuthoringServiceError(
                    "CAPABILITY_EVIDENCE_OUTCOME_INVALID",
                    f"The {label} run must finish with status {expected}; current status is {run.get('status')}.",
                    status=409,
                )
        delivery = success.get("delivery") if isinstance(success.get("delivery"), dict) else {}
        if delivery.get("status") not in {"ready", "completed", "delivered"}:
            raise AuthoringServiceError(
                "CAPABILITY_EVIDENCE_DELIVERY_MISSING",
                "The successful run did not produce a ready delivery.",
                status=409,
            )
        state_path = runner.runs_dir / str(success.get("run_id") or "") / "root_flow_state.json"
        state_document = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
        store = ((state_document.get("context") or {}).get("store") or {}) if isinstance(state_document, dict) else {}
        observed_store_keys = sorted(
            str(key) for key, value in store.items()
            if key != "local_resources" and value not in (None, "", [], {})
        ) if isinstance(store, dict) else []
        if not isinstance(failure.get("error"), dict) or not failure["error"].get("code"):
            raise AuthoringServiceError(
                "CAPABILITY_EVIDENCE_FAILURE_UNSTRUCTURED",
                "The failure run did not produce a structured runtime error.",
                status=409,
            )
        token = f"verify_{uuid.uuid4().hex}"
        evidence = {
            "schema": "cartridgeflow.capability_runtime_evidence.v1",
            "token": token,
            "flow_id": flow_id,
            "source_digest": snapshot["source_digest"],
            "success_run": {"run_id": success["run_id"], "status": success["status"]},
            "failure_run": {
                "run_id": failure["run_id"],
                "status": failure["status"],
                "error_code": failure["error"]["code"],
            },
            "observed_store_keys": observed_store_keys,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "consumed": False,
        }
        _atomic_json(_safe_evidence_path(capability_verification_dir, token), evidence)
        return {"verification": evidence}
    except FileNotFoundError as exc:
        _authoring_error(AuthoringServiceError("CAPABILITY_EVIDENCE_RUN_UNKNOWN", str(exc), status=404))
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.get("/api/creator/capability-cartridges")
def list_creator_capability_cartridges():
    return {
        "schema": "cartridgeflow.creator_capability_registry.v1",
        "capabilities": [creator_capability_projection(item) for item in _all_capability_releases()],
    }


@app.get("/api/developer/capability-cartridges")
def list_developer_capability_cartridges():
    entries = capability_cartridges.list_entries()
    for entry in entries:
        entry["usage"] = authoring_sessions.capability_usage(str(entry.get("id") or ""))
    return {
        "schema": "cartridgeflow.developer_capability_registry.v1",
        "capabilities": capability_cartridges.list_active(),
        "entries": entries,
    }


@app.get("/api/developer/flows/{flow_id}/capability-readiness")
def get_developer_flow_capability_readiness(flow_id: str):
    try:
        cartridge = registry.get_cartridge(flow_id)
        if not cartridge.get("editable"):
            raise AuthoringServiceError("CAPABILITY_SOURCE_FLOW_READ_ONLY", "Only editable Developer flows can publish capabilities.", status=403)
        validation = dev_flow_manager.validate_files(flow_id)
        findings = [
            {"code": "CAPABILITY_SOURCE_VALIDATION_BLOCKED", "message": message}
            for message in validation.get("errors") or []
        ]
        try:
            validate_flow_capability_boundary(cartridge.get("root_flow") or {}, cartridge.get("manifest") or {})
        except CapabilityCartridgeError as exc:
            findings.append({"code": exc.code, "message": str(exc)})
        return {
            "schema": "cartridgeflow.capability_publish_readiness.v1",
            "valid": not findings,
            "findings": findings,
        }
    except FileNotFoundError as exc:
        _authoring_error(AuthoringServiceError("CAPABILITY_SOURCE_FLOW_UNKNOWN", str(exc), status=404))
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/developer/flows/{flow_id}/capability-cartridges")
def publish_developer_flow_capability(flow_id: str, payload: CapabilityCartridgePublishPayload):
    """Publish one complete editable Root Flow as an immutable workspace capability."""
    try:
        if payload.trust_scope != "workspace":
            raise AuthoringServiceError(
                "CAPABILITY_RELEASE_TRUST_SCOPE_FORBIDDEN",
                "This local Developer workspace may publish only workspace-trusted capabilities.",
                status=403,
            )
        cartridge = registry.get_cartridge(flow_id)
        if not cartridge.get("editable"):
            raise AuthoringServiceError("CAPABILITY_SOURCE_FLOW_READ_ONLY", "Only editable Developer flows can publish capabilities.", status=403)
        snapshot = _capability_flow_snapshot(flow_id)
        manifest = snapshot["manifest"]
        root_flow = snapshot["root_flow"]
        validate_flow_capability_boundary(root_flow, manifest)
        validation = dev_flow_manager.validate_files(flow_id)
        if not validation.get("valid"):
            raise AuthoringServiceError("CAPABILITY_SOURCE_VALIDATION_BLOCKED", "; ".join(validation.get("errors") or ["Developer Flow validation failed."]), status=409)
        evidence_path = _safe_evidence_path(capability_verification_dir, payload.verification_token)
        if not evidence_path.is_file():
            raise AuthoringServiceError(
                "CAPABILITY_RUNTIME_EVIDENCE_REQUIRED",
                "Run and register one successful test and one safe failure test before publishing.",
                status=409,
            )
        runtime_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if runtime_evidence.get("consumed"):
            raise AuthoringServiceError("CAPABILITY_RUNTIME_EVIDENCE_CONSUMED", "This runtime evidence was already used.", status=409)
        if runtime_evidence.get("flow_id") != flow_id or runtime_evidence.get("source_digest") != snapshot["source_digest"]:
            raise AuthoringServiceError(
                "CAPABILITY_RUNTIME_EVIDENCE_STALE",
                "The verified Flow source does not match the current publishing source.",
                status=409,
            )
        missing_observed_outputs = sorted(
            str(item.get("store_key") or "")
            for item in payload.public_outputs
            if isinstance(item, dict)
            and str(item.get("store_key") or "") not in set(runtime_evidence.get("observed_store_keys") or [])
        )
        if missing_observed_outputs:
            raise AuthoringServiceError(
                "CAPABILITY_RUNTIME_OUTPUT_UNOBSERVED",
                "The successful verification run did not produce public outputs: " + ", ".join(missing_observed_outputs),
                status=409,
            )
        latest = capability_cartridges.latest_revision(payload.capability_id)
        expected = latest if payload.expected_revision is None else payload.expected_revision
        release = build_flow_capability_release(
            capability_id=payload.capability_id,
            revision=latest + 1,
            trust_scope=payload.trust_scope,
            label=payload.label,
            description=payload.description,
            match_terms=payload.match_terms,
            editable_fields=payload.editable_fields,
            creator_bindings=payload.creator_bindings,
            public_inputs=payload.public_inputs,
            public_outputs=payload.public_outputs,
            dependencies=payload.dependencies,
            source_flow_id=flow_id,
            manifest=manifest,
            root_flow=root_flow,
            source_files=snapshot["source_files"],
            evidence={
                "status": "passed",
                "checks": [
                    {"id": "developer_flow_validation", "status": "passed"},
                    {"id": "immutable_source_snapshot", "status": "passed"},
                    {"id": "workspace_trust_boundary", "status": "passed"},
                    {"id": "runtime_success", "status": "passed", "run_id": runtime_evidence["success_run"]["run_id"]},
                    {
                        "id": "runtime_safe_failure",
                        "status": "passed",
                        "run_id": runtime_evidence["failure_run"]["run_id"],
                        "error_code": runtime_evidence["failure_run"]["error_code"],
                    },
                ],
            },
        )
        if payload.target_project_id and payload.target_node_id:
            authoring_sessions.validate_capability_binding(
                payload.target_project_id,
                payload.target_node_id,
                release,
            )
        publication = capability_cartridges.put(release, expected_revision=expected)
        runtime_evidence["consumed"] = True
        runtime_evidence["published"] = {
            "id": publication["id"], "revision": publication["revision"], "digest": publication["digest"],
        }
        _atomic_json(evidence_path, runtime_evidence)
        if payload.target_project_id and payload.target_node_id:
            authoring_sessions.bind_capability(
                payload.target_project_id,
                payload.target_node_id,
                publication,
            )
        return {"release": publication, "creator": creator_capability_projection(publication)}
    except FileNotFoundError as exc:
        _authoring_error(AuthoringServiceError("CAPABILITY_SOURCE_FLOW_UNKNOWN", str(exc), status=404))
    except CapabilityCartridgeError as exc:
        _authoring_error(AuthoringServiceError("CAPABILITY_RELEASE_INVALID", str(exc)))
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.patch("/api/developer/capability-cartridges/{capability_id}/activation")
def set_capability_cartridge_activation(capability_id: str, payload: TrustedNodeActivationPayload):
    try:
        return {"entry": capability_cartridges.set_activation(capability_id, active=payload.active, revision=payload.revision)}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.get("/api/creator/trusted-node-presets")
def list_creator_trusted_node_presets():
    return {"schema": "cartridgeflow.creator_trusted_node_registry.v1", "presets": trusted_node_presets.list_creator()}


@app.get("/api/developer/trusted-node-presets")
def list_developer_trusted_node_presets():
    entries = trusted_node_presets.list_entries()
    for entry in entries:
        entry["usage"] = authoring_sessions.trusted_preset_usage(entry["id"])
    return {
        "schema": "cartridgeflow.developer_trusted_node_registry.v3",
        "presets": trusted_node_presets.list_developer(),
        "publications": trusted_node_presets.list_published(),
        "entries": entries,
    }


@app.patch("/api/developer/trusted-node-presets/{preset_id}/activation")
def set_developer_trusted_node_activation(preset_id: str, payload: TrustedNodeActivationPayload):
    try:
        entry = trusted_node_presets.set_activation(preset_id, active=payload.active, revision=payload.revision)
        entry["usage"] = authoring_sessions.trusted_preset_usage(preset_id)
        return {"entry": entry}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.put("/api/developer/trusted-node-presets/{preset_id}")
def put_developer_trusted_node_preset(preset_id: str, payload: TrustedNodePresetPayload):
    try:
        if payload.preset.get("id") != preset_id:
            raise AuthoringServiceError("TRUSTED_NODE_PRESET_ID_MISMATCH", "Route and preset identities differ.")
        publication = trusted_node_presets.put(payload.preset, payload.mapping, expected_revision=payload.expected_revision)
        return {"preset": publication["preset"], "publication": publication}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/developer/flows/{flow_id}/nodes/{node_id}/trusted-node-preset")
def publish_developer_flow_node(flow_id: str, node_id: str, payload: TrustedNodePublishFromFlowPayload):
    """Publish the selected real canvas node as one immutable trusted capability."""
    try:
        cartridge = registry.get_cartridge(flow_id)
        if not cartridge.get("editable"):
            raise AuthoringServiceError("TRUSTED_NODE_SOURCE_FLOW_READ_ONLY", "Only editable Developer flows can publish trusted nodes.", status=403)
        root_flow = cartridge.get("root_flow") if isinstance(cartridge.get("root_flow"), dict) else {}
        manifest = cartridge.get("manifest") if isinstance(cartridge.get("manifest"), dict) else {}
        state = (root_flow.get("states") or {}).get(node_id)
        if not isinstance(state, dict):
            raise AuthoringServiceError("TRUSTED_NODE_SOURCE_UNKNOWN", "The selected Developer node was not found.", status=404)

        current_revision = trusted_node_presets.latest_revision(payload.preset_id)
        expected_revision = current_revision if payload.expected_revision is None else payload.expected_revision
        mapping_key = str(payload.developer_mapping_key or f"{flow_id}.{node_id}").strip().lower()
        mapping_key = re.sub(r"[^a-z0-9_.-]+", ".", mapping_key).strip(".")
        preset = {
            "schema": "cartridgeflow.trusted_node_preset.v1",
            "protocol": {"id": "CF-TUNING", "version": "1.4"},
            "id": payload.preset_id,
            "revision": current_revision + 1,
            "creator_label": payload.creator_label,
            "creator_description": payload.creator_description,
            "match_terms": payload.match_terms,
            "editable_fields": payload.editable_fields,
            "developer_mapping_key": mapping_key,
        }
        mapping = build_trusted_node_mapping(
            preset,
            state,
            source_flow_id=flow_id,
            source_node_id=node_id,
            creator_bindings=payload.creator_bindings,
            source_manifest=manifest,
        )
        simulation = _simulate_trusted_node_candidate(flow_id, node_id, cartridge, state, mapping)
        if simulation["status"] != "passed":
            blocker = next((item for item in simulation["checks"] if item["status"] == "blocked"), None) or {}
            raise AuthoringServiceError(
                str(blocker.get("code") or "TRUSTED_NODE_SIMULATION_BLOCKED"),
                str(blocker.get("message") or "Trusted node simulation is blocked."),
                status=409,
            )
        publication = trusted_node_presets.put(
            preset,
            mapping,
            expected_revision=expected_revision,
            simulation_evidence=simulation,
        )
        return {"preset": publication["preset"], "publication": publication}
    except FileNotFoundError as exc:
        _authoring_error(AuthoringServiceError("TRUSTED_NODE_SOURCE_UNKNOWN", str(exc), status=404))
    except (json.JSONDecodeError, ValueError) as exc:
        _authoring_error(AuthoringServiceError("TRUSTED_NODE_SOURCE_INVALID", str(exc)))
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/developer/flows/{flow_id}/nodes/{node_id}/trusted-node-preset/simulate")
def simulate_developer_flow_node(flow_id: str, node_id: str, payload: TrustedNodePublishFromFlowPayload):
    """Validate one exact publish candidate without invoking real external resources."""
    try:
        cartridge = registry.get_cartridge(flow_id)
        if not cartridge.get("editable"):
            raise AuthoringServiceError("TRUSTED_NODE_SOURCE_FLOW_READ_ONLY", "Only editable Developer flows can simulate trusted nodes.", status=403)
        root_flow = cartridge.get("root_flow") if isinstance(cartridge.get("root_flow"), dict) else {}
        manifest = cartridge.get("manifest") if isinstance(cartridge.get("manifest"), dict) else {}
        state = (root_flow.get("states") or {}).get(node_id)
        if not isinstance(state, dict):
            raise AuthoringServiceError("TRUSTED_NODE_SOURCE_UNKNOWN", "The selected Developer node was not found.", status=404)
        revision = trusted_node_presets.latest_revision(payload.preset_id) + 1
        mapping_key = str(payload.developer_mapping_key or f"{flow_id}.{node_id}").strip().lower()
        mapping_key = re.sub(r"[^a-z0-9_.-]+", ".", mapping_key).strip(".")
        preset = {
            "schema": "cartridgeflow.trusted_node_preset.v1",
            "protocol": {"id": "CF-TUNING", "version": "1.4"},
            "id": payload.preset_id,
            "revision": revision,
            "creator_label": payload.creator_label,
            "creator_description": payload.creator_description,
            "match_terms": payload.match_terms,
            "editable_fields": payload.editable_fields,
            "developer_mapping_key": mapping_key,
        }
        mapping = build_trusted_node_mapping(
            preset,
            state,
            source_flow_id=flow_id,
            source_node_id=node_id,
            creator_bindings=payload.creator_bindings,
            source_manifest=manifest,
        )
        return _simulate_trusted_node_candidate(flow_id, node_id, cartridge, state, mapping)
    except FileNotFoundError as exc:
        _authoring_error(AuthoringServiceError("TRUSTED_NODE_SOURCE_UNKNOWN", str(exc), status=404))
    except AuthoringServiceError as exc:
        _authoring_error(exc)


def _simulate_trusted_node_candidate(flow_id: str, node_id: str, cartridge: dict, state: dict, mapping: dict) -> dict:
    """Produce integrity-bound dry-run evidence for mapping and local resource readiness."""
    from core.llm.config_manager import build_model_binding_report
    from core.studio.resource_catalog import build_flow_resource_catalog

    manifest = cartridge.get("manifest") if isinstance(cartridge.get("manifest"), dict) else {}
    root_flow = cartridge.get("root_flow") if isinstance(cartridge.get("root_flow"), dict) else {}
    checks = [
        {
            "id": "portable_snapshot",
            "status": "passed",
            "message": "节点已形成不含外部拓扑的可移植执行快照。",
        },
        {
            "id": "base_runtime_action",
            "status": "passed",
            "message": f"Base 已声明支持动作 {state.get('action')}。",
        },
    ]

    action = str(state.get("action") or "")
    requirements = mapping.get("requirements") if isinstance(mapping.get("requirements"), dict) else {}
    if action == "llm_prompt":
        report = build_model_binding_report(manifest, root_flow)
        relevant = [item for item in report.get("items") or [] if item.get("node_id") == node_id]
        blocked = next((item for item in relevant if item.get("status") != "ok"), None)
        checks.append({
            "id": "model_binding",
            "status": "blocked" if blocked or not relevant else "passed",
            "code": "TRUSTED_NODE_MODEL_BINDING_REQUIRED" if blocked or not relevant else "",
            "message": str((blocked or {}).get("message") or ("模型连接已绑定。" if relevant else "AI 节点尚未绑定可用的运行模型。")),
            "action": {"panel": "models"} if blocked or not relevant else None,
        })

    if action in {"tool_call", "remote_call"}:
        catalog = build_flow_resource_catalog(
            ROOT,
            manifest,
            root_flow,
            package_path=cartridge.get("package_path"),
        )
        required_tool_ids = {
            str(item.get("id") or "")
            for item in requirements.get("mcp_tools") or []
            if isinstance(item, dict) and item.get("id")
        }
        template_tools = list(state.get("tools") or [])
        params = state.get("params") if isinstance(state.get("params"), dict) else {}
        template_tools.extend(params.get("tools") or [])
        required_pairs = {
            (str(item.get("server") or ""), str(item.get("tool") or ""))
            for item in template_tools
            if isinstance(item, dict) and item.get("server") and item.get("tool")
        }
        relevant_tools = [
            item for item in catalog.get("tools") or []
            if node_id in (item.get("node_references") or [])
            or str(item.get("id") or "") in required_tool_ids
            or (str(item.get("server") or ""), str(item.get("tool") or "")) in required_pairs
        ]
        blocked_tool = next((item for item in relevant_tools if item.get("status") != "ready"), None)
        no_portable_tool = action == "remote_call" and not (requirements.get("mcp_tools") or [])
        checks.append({
            "id": "tool_binding",
            "status": "blocked" if blocked_tool or not relevant_tools or no_portable_tool else "passed",
            "code": "TRUSTED_NODE_TOOL_BINDING_REQUIRED" if blocked_tool or not relevant_tools or no_portable_tool else "",
            "message": str(
                (blocked_tool or {}).get("message")
                or ("工具已声明并完成本机绑定。" if relevant_tools and not no_portable_tool else "节点尚未绑定可移植的工具资源。")
            ),
            "action": {"panel": "tools"} if blocked_tool or not relevant_tools or no_portable_tool else None,
        })

    checks.append({
        "id": "external_execution_boundary",
        "status": "passed",
        "message": "隔离仿真未调用真实模型、远端服务，也未执行外部副作用；真实运行结果需在流程测试台确认。",
        "executed_real_resources": False,
    })
    status = "blocked" if any(item["status"] == "blocked" for item in checks) else "passed"
    evidence = {
        "schema": "cartridgeflow.trusted_node_simulation.v1",
        "flow_id": flow_id,
        "node_id": node_id,
        "status": status,
        "mapping_digest": mapping["digest"],
        "mode": "isolated_dry_run",
        "executed_real_resources": False,
        "created_at": datetime.now().astimezone().isoformat(),
        "checks": checks,
    }
    evidence["digest"] = canonical_digest(evidence)
    return evidence


@app.get("/api/developer/flows/{flow_id}/nodes/{node_id}/trusted-node-preset/readiness")
def get_developer_flow_node_trusted_readiness(flow_id: str, node_id: str):
    """Check whether one Developer node can produce a portable trusted snapshot."""
    try:
        cartridge = registry.get_cartridge(flow_id)
        if not cartridge.get("editable"):
            return {
                "schema": "cartridgeflow.developer_trusted_node_readiness.v1",
                "flow_id": flow_id,
                "node_id": node_id,
                "ready": False,
                "blocker": {
                    "code": "TRUSTED_NODE_SOURCE_FLOW_READ_ONLY",
                    "message": "Only editable Developer flows can publish trusted nodes.",
                },
            }
        root_flow = cartridge.get("root_flow") if isinstance(cartridge.get("root_flow"), dict) else {}
        manifest = cartridge.get("manifest") if isinstance(cartridge.get("manifest"), dict) else {}
        state = (root_flow.get("states") or {}).get(node_id)
        if not isinstance(state, dict):
            return {
                "schema": "cartridgeflow.developer_trusted_node_readiness.v1",
                "flow_id": flow_id,
                "node_id": node_id,
                "ready": False,
                "blocker": {
                    "code": "TRUSTED_NODE_SOURCE_UNKNOWN",
                    "message": "The selected Developer node was not found.",
                },
            }
        title = str(state.get("display_name") or state.get("title") or node_id).strip()
        preview_preset = {
            "schema": "cartridgeflow.trusted_node_preset.v1",
            "protocol": {"id": "CF-TUNING", "version": "1.4"},
            "id": "trusted-node-readiness",
            "revision": 1,
            "creator_label": title,
            "creator_description": f"Reusable Developer capability: {title}",
            "match_terms": [title],
            "editable_fields": [],
            "developer_mapping_key": "trusted-node-readiness",
        }
        mapping = build_trusted_node_mapping(
            preview_preset,
            state,
            source_flow_id=flow_id,
            source_node_id=node_id,
            creator_bindings={},
            source_manifest=manifest,
        )
        return {
            "schema": "cartridgeflow.developer_trusted_node_readiness.v1",
            "flow_id": flow_id,
            "node_id": node_id,
            "ready": True,
            "action": state.get("action"),
            "executor": state.get("executor"),
            "effect": state.get("effect"),
            "mapping_digest": mapping["digest"],
            "blocker": None,
        }
    except FileNotFoundError as exc:
        _authoring_error(AuthoringServiceError("TRUSTED_NODE_SOURCE_UNKNOWN", str(exc), status=404))
    except AuthoringServiceError as exc:
        return {
            "schema": "cartridgeflow.developer_trusted_node_readiness.v1",
            "flow_id": flow_id,
            "node_id": node_id,
            "ready": False,
            "blocker": {"code": exc.code, "message": str(exc)},
        }


async def _compose_trusted_creator_recipe(goal: str, recipe_id: str) -> tuple[dict, dict[str, dict]]:
    """Return a complete semantic recipe plus any resolved capability releases."""
    from core.llm import chat
    from core.llm.config_manager import resolve_model
    from core.llm.creator_flow_skill import CreatorFlowSkillError, build_creator_flow_messages, parse_creator_flow_result
    capabilities = _all_capability_releases()
    model = resolve_model("mentor")
    if not str(model.api_key or "").strip():
        raise AuthoringServiceError("AI_CREATOR_FLOW_MODEL_UNBOUND", "No configured whole-flow model is available.", status=409)
    try:
        response = await asyncio.wait_for(
            chat(model, build_creator_flow_messages(goal, capabilities), agent_name="creator_flow_skill", phase="semantic_recipe_composition"),
            timeout=_creator_ai_timeout(model),
        )
    except TimeoutError as exc:
        raise AuthoringServiceError("AI_CREATOR_FLOW_TIMEOUT", "The whole-flow AI service did not respond in time.", status=504) from exc
    try:
        recipe, publications = parse_creator_flow_result(str(response.get("content") or ""), goal, recipe_id, capabilities)
    except CreatorFlowSkillError as exc:
        raise AuthoringServiceError("AI_CREATOR_FLOW_OUTPUT_INVALID", str(exc), status=502) from exc
    return recipe, publications


@app.post("/api/creator/compose-recipe")
async def compose_creator_recipe(payload: CreatorComposeRecipePayload):
    """Run the whole-flow skill and atomically create a mapped Creator session."""
    try:
        result, publications = await _compose_trusted_creator_recipe(payload.goal, f"recipe.{payload.session_id}")
        if result.get("schema") == "cartridgeflow.dynamic_creator_recipe.v1":
            presets = [item["implementation"]["preset"] for item in publications.values()]
            mappings = {
                node["id"]: publications[node["preset"]["id"]]["implementation"]["mapping"]
                for node in result["nodes"]
            }
            creator = authoring_sessions.create_from_recipe(payload.session_id, payload.project_id, result, presets, mappings=mappings)
        else:
            creator = authoring_sessions.create_from_semantic_recipe(payload.session_id, payload.project_id, result, publications)
        return {"creator": creator}
    except AuthoringServiceError as exc:
        _authoring_error(exc)
    except ValueError as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_FLOW_MODEL_UNBOUND", str(exc), status=409))
    except Exception as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_FLOW_FAILED", str(exc), status=502))


@app.post("/api/creator/authoring-sessions/{session_id}/recompose")
async def recompose_creator_recipe(session_id: str, payload: CreatorRecomposeRecipePayload):
    """Replace the whole current draft; no engineering topology is accepted from the caller."""
    try:
        current = authoring_sessions.get(session_id)
        authoring_sessions._require_revision(current, payload.expected_revision)
        result, publications = await _compose_trusted_creator_recipe(
            payload.goal,
            f"recipe.{session_id}.{payload.expected_revision + 1}",
        )
        if result.get("schema") == "cartridgeflow.dynamic_creator_recipe.v1":
            presets = [item["implementation"]["preset"] for item in publications.values()]
            mappings = {
                node["id"]: publications[node["preset"]["id"]]["implementation"]["mapping"]
                for node in result["nodes"]
            }
            creator = authoring_sessions.replace_from_recipe(session_id, result, presets, mappings=mappings, expected_revision=payload.expected_revision)
        else:
            creator = authoring_sessions.replace_from_semantic_recipe(session_id, result, publications, expected_revision=payload.expected_revision)
        return {"creator": creator}
    except AuthoringServiceError as exc:
        _authoring_error(exc)
    except ValueError as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_FLOW_MODEL_UNBOUND", str(exc), status=409))
    except Exception as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_FLOW_FAILED", str(exc), status=502))


@app.post("/api/creator/authoring-sessions/{session_id}/recompose-preview")
async def preview_recompose_creator_recipe(session_id: str, payload: CreatorRecomposeRecipePayload):
    """Generate a whole-recipe candidate without replacing the current canvas."""
    try:
        current = authoring_sessions.get(session_id)
        authoring_sessions._require_revision(current, payload.expected_revision)
        recipe, publications = await _compose_trusted_creator_recipe(
            payload.goal,
            f"recipe.{session_id}.{payload.expected_revision + 1}",
        )
        proposal_id = f"recipe_{uuid.uuid4().hex}"
        proposal = {
            "schema": "cartridgeflow.creator_recipe_proposal.v1",
            "id": proposal_id,
            "session_id": session_id,
            "base_revision": payload.expected_revision,
            "goal": payload.goal,
            "recipe": recipe,
            "publications": publications,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        proposal["digest"] = canonical_digest(proposal)
        _atomic_json(_safe_evidence_path(creator_recipe_proposal_dir, proposal_id), proposal)
        preview_nodes = []
        for node in recipe.get("nodes") or []:
            preview_nodes.append({
                "id": node.get("id"),
                "label": node.get("creator_label") or node.get("label") or node.get("id"),
                "description": node.get("creator_description") or node.get("description") or "",
                "resolution": "resolved" if node.get("capability") or node.get("preset") else "unresolved",
            })
        current_ids = {
            item.get("id") for item in ((current.get("semantic_recipe") or current.get("trusted_recipe") or {}).get("nodes") or [])
        }
        next_ids = {item.get("id") for item in recipe.get("nodes") or []}
        return {
            "schema": "cartridgeflow.creator_recipe_preview.v1",
            "proposal_id": proposal_id,
            "goal": payload.goal,
            "nodes": preview_nodes,
            "relations": recipe.get("relations") or [],
            "impact": {
                "added_node_ids": sorted(next_ids - current_ids),
                "removed_node_ids": sorted(current_ids - next_ids),
                "retained_node_ids": sorted(current_ids & next_ids),
            },
        }
    except AuthoringServiceError as exc:
        _authoring_error(exc)
    except ValueError as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_FLOW_MODEL_UNBOUND", str(exc), status=409))
    except Exception as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_FLOW_FAILED", str(exc), status=502))


@app.post("/api/creator/authoring-sessions/{session_id}/recompose-proposals/{proposal_id}/accept")
def accept_recompose_creator_recipe(session_id: str, proposal_id: str, payload: CreatorRecomposeAcceptPayload):
    try:
        if proposal_id != payload.proposal_id:
            raise AuthoringServiceError("AUTHORING_RECIPE_PROPOSAL_INVALID", "Recipe proposal identity does not match.")
        path = _safe_evidence_path(creator_recipe_proposal_dir, proposal_id)
        if not path.is_file():
            raise AuthoringServiceError("AUTHORING_RECIPE_PROPOSAL_UNKNOWN", "Recipe proposal was not found.", status=404)
        proposal = json.loads(path.read_text(encoding="utf-8"))
        body = {key: value for key, value in proposal.items() if key != "digest"}
        if proposal.get("digest") != canonical_digest(body) or proposal.get("session_id") != session_id:
            raise AuthoringServiceError("AUTHORING_RECIPE_PROPOSAL_INVALID", "Recipe proposal integrity check failed.", status=409)
        if proposal.get("base_revision") != payload.expected_revision:
            raise AuthoringServiceError("AUTHORING_REVISION_CONFLICT", "The canvas changed after this preview.", status=409)
        result = proposal["recipe"]
        publications = proposal["publications"]
        if result.get("schema") == "cartridgeflow.dynamic_creator_recipe.v1":
            presets = [item["implementation"]["preset"] for item in publications.values()]
            mappings = {
                node["id"]: publications[node["preset"]["id"]]["implementation"]["mapping"]
                for node in result["nodes"]
            }
            creator = authoring_sessions.replace_from_recipe(
                session_id, result, presets, mappings=mappings, expected_revision=payload.expected_revision,
            )
        else:
            creator = authoring_sessions.replace_from_semantic_recipe(
                session_id, result, publications, expected_revision=payload.expected_revision,
            )
        path.unlink(missing_ok=True)
        return {"creator": creator}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/resolve-capabilities")
def resolve_creator_capabilities(session_id: str, payload: AuthoringReadinessPayload):
    try:
        creator, resolved = authoring_sessions.resolve_capabilities(
            session_id,
            _all_capability_releases(),
            expected_revision=payload.expected_revision,
        )
        return {"creator": creator, "resolved_node_ids": resolved}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/nodes/{node_id}/reject-capability")
def reject_creator_capability(session_id: str, node_id: str, payload: AuthoringReadinessPayload):
    try:
        return {"creator": authoring_sessions.reject_capability(session_id, node_id, expected_revision=payload.expected_revision)}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/source-candidates")
async def discover_creator_source_candidates(session_id: str, payload: CreatorSourceDiscoveryPayload):
    from core.llm import chat
    from core.llm.config_manager import resolve_model
    from core.llm.creator_discovery import CreatorDiscoveryError, build_source_discovery_messages, parse_source_discovery
    try:
        state = authoring_sessions.get(session_id)
        model = resolve_model("mentor")
        if not str(model.api_key or "").strip():
            raise AuthoringServiceError("AI_CREATOR_SOURCE_DISCOVERY_MODEL_UNBOUND", "No configured source discovery model is available.", status=409)
        blueprint = state["head"]["blueprint"]
        messages = build_source_discovery_messages(blueprint["intent"], blueprint["steps"], payload.request)
        try:
            response = await asyncio.wait_for(
                chat(model, messages, agent_name="creator_source_discovery", phase="source_discovery"),
                timeout=_creator_ai_timeout(model),
            )
        except TimeoutError as exc:
            raise AuthoringServiceError("AI_CREATOR_SOURCE_DISCOVERY_TIMEOUT", "The AI source discovery service did not respond in time.", status=504) from exc
        try:
            candidates = parse_source_discovery(str(response.get("content") or ""))
        except CreatorDiscoveryError as exc:
            raise AuthoringServiceError("AI_CREATOR_SOURCE_DISCOVERY_OUTPUT_INVALID", str(exc), status=502) from exc
        return {"schema": "cartridgeflow.creator_source_candidates.v1", "request": " ".join(payload.request.split()), "candidates": candidates}
    except AuthoringServiceError as exc:
        _authoring_error(exc)
    except ValueError as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_SOURCE_DISCOVERY_MODEL_UNBOUND", str(exc), status=409))
    except Exception as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_SOURCE_DISCOVERY_FAILED", str(exc), status=502))


@app.post("/api/creator/source-inspections")
def inspect_creator_source(payload: CreatorSourceInspectPayload):
    from cartridgeflow_dlc import McpRuntimeError, inspect_public_https_url
    try:
        result = inspect_public_https_url(payload.url)
        return {
            "schema": "cartridgeflow.creator_source_inspection.v1",
            "status": "reachable",
            **result,
        }
    except McpRuntimeError as exc:
        raise HTTPException(
            status_code=400 if exc.code in {"network_url_denied", "network_request_invalid"} else 502,
            detail={"code": exc.code.upper(), "message": str(exc)},
        )


@app.post("/api/creator/authoring-sessions")
def create_authoring_session(payload: AuthoringSessionCreatePayload):
    try:
        return {"creator": authoring_sessions.create(payload.session_id, payload.recipe_id, payload.intent, payload.steps, payload.source_references, payload.bindings, payload.project_id)}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.get("/api/creator/authoring-sessions/{session_id}")
def get_creator_authoring_session(session_id: str):
    try:
        return {"creator": authoring_sessions.creator_projection(authoring_sessions.get(session_id))}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.get("/api/creator/projects")
def list_creator_projects():
    return {"schema": "cartridgeflow.creator_project_list.v1", "projects": authoring_sessions.list_projects()}


@app.get("/api/creator/projects/{project_id}")
def get_creator_project(project_id: str, optional: bool = False):
    try:
        return {"creator": authoring_sessions.creator_projection(authoring_sessions.get_by_project_id(project_id))}
    except AuthoringServiceError as exc:
        if optional and exc.code == "AUTHORING_PROJECT_UNKNOWN":
            return {"creator": None}
        _authoring_error(exc)


@app.patch("/api/creator/projects/{project_id}")
def rename_creator_project(project_id: str, payload: CreatorProjectRenamePayload):
    try:
        return {"creator": authoring_sessions.rename_project(project_id, payload.name)}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.delete("/api/creator/projects/{project_id}")
def delete_creator_project(project_id: str):
    try:
        return authoring_sessions.delete_project(project_id)
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.get("/api/developer/authoring-sessions/{session_id}")
def get_developer_authoring_session(session_id: str):
    try:
        return {"developer": authoring_sessions.developer_projection(authoring_sessions.get(session_id))}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.get("/api/developer/projects/{project_id}")
def get_developer_project(project_id: str):
    try:
        return {"developer": authoring_sessions.developer_projection(authoring_sessions.get_by_project_id(project_id))}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/nodes/{node_id}/ai-proposals")
async def create_trusted_node_ai_proposal(session_id: str, node_id: str, payload: CreatorNodeRefinementPayload):
    from core.llm import chat
    from core.llm.config_manager import resolve_model
    from core.llm.creator_node_skill import CreatorNodeSkillError, build_creator_node_messages, parse_creator_node_result
    try:
        state = authoring_sessions.get(session_id)
        authoring_sessions._require_revision(state, payload.expected_revision)
        semantic_recipe = state.get("semantic_recipe")
        if isinstance(semantic_recipe, dict):
            node = next((item for item in semantic_recipe["nodes"] if item["id"] == node_id), None)
            if node is None:
                raise AuthoringServiceError("AUTHORING_STEP_UNKNOWN", "Semantic recipe node was not found.", status=404)
            projected = next(item for item in authoring_sessions.creator_projection(state)["trusted_recipe"]["nodes"] if item["id"] == node_id)
            preset = {
                "schema": "cartridgeflow.trusted_node_preset.v1",
                "protocol": {"id": "CF-TUNING", "version": "1.4"},
                "id": "semantic-node",
                "revision": 1,
                "creator_label": node["creator_label"],
                "creator_description": node["creator_description"],
                "match_terms": [node["needed_capability"]],
                "editable_fields": projected["editable_fields"],
                "developer_mapping_key": "semantic.node.refinement",
            }
            current_node = {**node, "values": state["head"]["bindings"].get(node_id, {})}
        else:
            recipe = state.get("trusted_recipe")
            if not isinstance(recipe, dict):
                raise AuthoringServiceError("AI_CREATOR_NODE_RECIPE_REQUIRED", "Node refinement requires a semantic recipe.", status=409)
            node = next((item for item in recipe["nodes"] if item["id"] == node_id), None)
            if node is None:
                raise AuthoringServiceError("AUTHORING_STEP_UNKNOWN", "Trusted recipe node was not found.", status=404)
            preset = next(item for item in state["trusted_presets"] if item["id"] == node["preset"]["id"] and item["revision"] == node["preset"]["revision"])
            current_node = {**node, "values": state["head"]["bindings"].get(node_id, {})}
        model = resolve_model("mentor")
        if not str(model.api_key or "").strip():
            raise AuthoringServiceError("AI_CREATOR_NODE_MODEL_UNBOUND", "No configured node-refinement model is available.", status=409)
        try:
            response = await asyncio.wait_for(
                chat(model, build_creator_node_messages(current_node, preset, payload.prompt), agent_name="creator_node_skill", phase="trusted_node_refinement"),
                timeout=_creator_ai_timeout(model),
            )
        except TimeoutError as exc:
            raise AuthoringServiceError("AI_CREATOR_NODE_TIMEOUT", "The node-refinement AI service did not respond in time.", status=504) from exc
        try:
            values = parse_creator_node_result(str(response.get("content") or ""), preset)
        except CreatorNodeSkillError as exc:
            raise AuthoringServiceError("AI_CREATOR_NODE_OUTPUT_INVALID", str(exc), status=502) from exc
        merged = {**state["head"]["bindings"].get(node_id, {}), **values}
        change = {"id": f"refine.{node_id}.{payload.expected_revision}", "target_id": node_id, "operation": "set_creator_binding", "value": merged}
        return {"proposal": authoring_sessions.propose(session_id, [change], author=payload.author, summary=payload.summary, expected_revision=payload.expected_revision)}
    except AuthoringServiceError as exc:
        _authoring_error(exc)
    except ValueError as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_NODE_MODEL_UNBOUND", str(exc), status=409))
    except Exception as exc:
        _authoring_error(AuthoringServiceError("AI_CREATOR_NODE_FAILED", str(exc), status=502))


@app.post("/api/creator/authoring-sessions/{session_id}/ai-proposals")
async def create_ai_authoring_proposal(session_id: str, payload: AuthoringAIProposalPayload):
    from core.llm import chat
    from core.llm.config_manager import resolve_model
    try:
        model = resolve_model("mentor")
        if not str(model.api_key or "").strip():
            raise AuthoringServiceError("AI_AUTHORING_MODEL_UNBOUND", "No configured authoring model is available.", status=409)
        async def model_call(messages):
            response = await chat(model, messages, agent_name="creator_authoring", phase="authoring_proposal")
            return str(response.get("content") or "")
        try:
            proposal = await asyncio.wait_for(
                authoring_sessions.propose_ai(session_id, prompt=payload.prompt, author=payload.author, summary=payload.summary, expected_revision=payload.expected_revision, model_call=model_call),
                timeout=_creator_ai_timeout(model),
            )
        except TimeoutError as exc:
            raise AuthoringServiceError("AI_AUTHORING_MODEL_TIMEOUT", "The AI authoring service did not respond in time.", status=504) from exc
        return {"proposal": proposal}
    except AuthoringServiceError as exc:
        _authoring_error(exc)
    except ValueError as exc:
        _authoring_error(AuthoringServiceError("AI_AUTHORING_MODEL_UNBOUND", str(exc), status=409))
    except Exception as exc:
        _authoring_error(AuthoringServiceError("AI_AUTHORING_MODEL_FAILED", str(exc), status=502))


@app.post("/api/creator/authoring-sessions/{session_id}/proposals")
def create_authoring_proposal(session_id: str, payload: AuthoringProposalPayload):
    try:
        return {"proposal": authoring_sessions.propose(session_id, payload.changes, author=payload.author, summary=payload.summary, expected_revision=payload.expected_revision)}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/proposals/{proposal_id}/preview")
def preview_authoring_proposal(session_id: str, proposal_id: str, payload: AuthoringAcceptPayload):
    try:
        result = authoring_sessions.preview(session_id, proposal_id, payload.selected_change_ids, freeze_revision=payload.freeze_revision)
        return {key: value for key, value in result.items() if key != "developer"}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/proposals/{proposal_id}/accept")
def accept_authoring_proposal(session_id: str, proposal_id: str, payload: AuthoringAcceptPayload):
    try:
        result = authoring_sessions.accept(session_id, proposal_id, payload.selected_change_ids, freeze_revision=payload.freeze_revision)
        return {"creator": result["creator"], "impact": result["impact"], "accepted_change_ids": result["acceptance"]["accepted_change_ids"], "freeze_revision": result["freeze_revision"]}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/proposals/{proposal_id}/reject")
def reject_authoring_proposal(session_id: str, proposal_id: str, payload: AuthoringRejectPayload):
    try:
        return {"creator": authoring_sessions.reject(session_id, proposal_id, reason=payload.reason)}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/revisions/{acceptance_id}/reverse")
def reverse_authoring_revision(session_id: str, acceptance_id: str, payload: AuthoringReversePayload):
    try:
        result = authoring_sessions.reverse(session_id, acceptance_id, author=payload.author, summary=payload.summary, expected_revision=payload.expected_revision, freeze_revision=payload.freeze_revision)
        return {"creator": result["creator"], "impact": result["impact"], "reversal": result["reversal"]}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/freeze")
def freeze_authoring_steps(session_id: str, payload: AuthoringFreezePayload):
    try:
        return {"freeze": authoring_sessions.freeze(session_id, payload.step_ids, author=payload.author, summary=payload.summary)}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.get("/api/creator/authoring-sessions/{session_id}/design-checks")
def get_creator_design_checks(session_id: str):
    try:
        return {"design_checks": authoring_sessions.design_checks(authoring_sessions.get(session_id))}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/generation-readiness")
def get_creator_generation_readiness(session_id: str, payload: AuthoringReadinessPayload):
    try:
        state = authoring_sessions.get(session_id)
        authoring_sessions._require_revision(state, payload.expected_revision)
        return {"generation_readiness": authoring_sessions.generation_readiness(state)}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/creator/authoring-sessions/{session_id}/package")
def package_creator_project(session_id: str, payload: CreatorPackagePayload):
    """The sole Creator boundary that maps reviewed design facts into a signed package."""
    try:
        bridge = CreatorRuntimeBridge(ROOT, ROOT / PACKAGES_DIR, capability_cartridges)
        result = bridge.package(authoring_sessions, session_id, expected_revision=payload.expected_revision)
        return {
            "schema": "cartridgeflow.creator_package.v1",
            "status": "ready",
            "filename": result["filename"],
            "url": f"/packages/{result['filename']}",
            "signature_verified": bool((result.get("signature") or {}).get("verified")),
        }
    except CreatorRuntimeBridgeError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.as_dict()) from exc
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/developer/authoring-sessions/{session_id}/confirm-materialization")
def confirm_developer_materialization(session_id: str, payload: DeveloperMaterializationPayload):
    try:
        confirmation = authoring_sessions.confirm_materialization(
            session_id,
            expected_revision=payload.expected_revision,
            author=payload.author,
            summary=payload.summary,
        )
        return {"confirmation": confirmation, "developer": authoring_sessions.developer_projection(authoring_sessions.get(session_id))}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/developer/authoring-sessions/{session_id}/runtime-handoff")
def create_developer_runtime_handoff(session_id: str, payload: CreatorHandoffPayload):
    try:
        bridge = CreatorRuntimeBridge(ROOT, ROOT / PACKAGES_DIR, capability_cartridges)
        result = bridge.materialize(authoring_sessions, session_id, expected_revision=payload.expected_revision, candidate=payload.compile_candidate)
        return {**result, "url": f"/packages/{result['filename']}"}
    except CreatorRuntimeBridgeError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.as_dict()) from exc
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/developer/projects/{project_id}/confirm-materialization")
def confirm_developer_project_materialization(project_id: str, payload: DeveloperMaterializationPayload):
    try:
        state = authoring_sessions.get_by_project_id(project_id)
        confirmation = authoring_sessions.confirm_materialization(state["id"], expected_revision=payload.expected_revision, author=payload.author, summary=payload.summary)
        return {"confirmation": confirmation, "developer": authoring_sessions.developer_projection(authoring_sessions.get(state["id"]))}
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/developer/projects/{project_id}/runtime-handoff")
def create_developer_project_runtime_handoff(project_id: str, payload: CreatorHandoffPayload):
    try:
        state = authoring_sessions.get_by_project_id(project_id)
        bridge = CreatorRuntimeBridge(ROOT, ROOT / PACKAGES_DIR, capability_cartridges)
        result = bridge.materialize(authoring_sessions, state["id"], expected_revision=payload.expected_revision, candidate=payload.compile_candidate)
        return {**result, "url": f"/packages/{result['filename']}"}
    except CreatorRuntimeBridgeError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.as_dict()) from exc
    except AuthoringServiceError as exc:
        _authoring_error(exc)


@app.post("/api/lab/flows/{cartridge_id}/ai-steward")
async def ask_lab_flow_ai_steward(cartridge_id: str, payload: AIFlowStewardPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows can use the AI steward")
        files = dev_flow_manager.read_files(cartridge_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    mode = str(payload.mode or "guided").strip().lower()
    view = str(payload.view or "engineering").strip().lower()
    tool = str(payload.tool or "none").strip().lower()
    if mode not in {"guided", "delegated"}:
        raise HTTPException(status_code=400, detail="AI steward mode must be guided or delegated")
    if view not in {"engineering", "outcome"}:
        raise HTTPException(status_code=400, detail="AI steward view must be engineering or outcome")
    if tool not in {"none", "pointer", "lasso"}:
        raise HTTPException(status_code=400, detail="Unknown AI steward selection tool")
    message = str(payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="请输入要交给 AI 管家的问题或目标")

    root_flow_text = str(files.get("root_flow") or "")
    revision = hashlib.sha256(root_flow_text.encode("utf-8")).hexdigest()[:16]
    if payload.revision and payload.revision != revision:
        raise HTTPException(status_code=409, detail={
            "message": "Flow 已在选择后发生变化，请重新指向或框选后再继续。",
            "expected_revision": revision,
            "selection_revision": payload.revision,
        })

    graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
    node_ids = {str(node.get("id") or "") for node in graph.get("nodes") or []}
    edge_ids = {
        f"{edge.get('from') or edge.get('source')}->{edge.get('to') or edge.get('target')}"
        for edge in graph.get("edges") or []
    }
    selection = payload.selection.model_dump()
    unknown_nodes = sorted(set(selection["node_ids"]) - node_ids)
    unknown_edges = sorted(set(selection["edge_ids"]) - edge_ids)
    invalid_fields = sorted(path for path in selection["field_paths"] if not any(
        path == f"states.{node_id}" or path.startswith(f"states.{node_id}.")
        for node_id in node_ids
    ))
    if unknown_nodes or unknown_edges or invalid_fields:
        raise HTTPException(status_code=409, detail={
            "message": "选区包含已经失效的工程引用，请重新选择。",
            "unknown_nodes": unknown_nodes,
            "unknown_edges": unknown_edges,
            "invalid_field_paths": invalid_fields,
        })

    from core.lab.ai_steward import build_messages, parse_response
    from core.llm import chat
    from core.llm.config_manager import resolve_model

    try:
        steward_model = resolve_model("mentor", cartridge_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "AI_STEWARD_MODEL_UNBOUND",
            "message": "当前 Flow 尚未绑定 AI 管家模型，请先在模型管理中为“AI 管家”分配模型 API。",
            "role": "mentor",
        }) from exc

    try:
        response = await chat(
            steward_model,
            build_messages(message, mode, view, revision, selection, graph),
            agent_name="ai_steward",
            phase="flow_guidance" if mode == "guided" else "flow_delegation",
        )
        result = parse_response(
            response.get("content", ""),
            mode=mode,
            revision=revision,
            selection=selection,
        )
        return {"ok": True, "message": result, "meta": response.get("meta", {})}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        from core.llm.errors import classify_llm_error
        error = classify_llm_error(exc)
        raise HTTPException(status_code=error.status_code, detail=str(error))


@app.put("/api/lab/flows/{cartridge_id}/files/{file_type}")
def save_lab_flow_file(cartridge_id: str, file_type: str, payload: DevFlowFileSave):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        return dev_flow_manager.save_file(cartridge_id, file_type, payload.content)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/lab/flows/{cartridge_id}/assets")
def get_lab_flow_assets(cartridge_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        bundle = load_asset_bundle(cartridge.get("package_path"), cartridge.get("manifest") or {}, include_content=True)
        return {
            "cartridge_id": cartridge_id,
            "assets": bundle["assets"],
            "components": bundle["components"],
            "files": dev_flow_manager.read_files(cartridge_id),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CartridgeAssetError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@app.put("/api/lab/flows/{cartridge_id}/assets/{asset_id}")
def put_lab_flow_asset(cartridge_id: str, asset_id: str, payload: CartridgeAssetPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        if payload.id != asset_id:
            raise HTTPException(status_code=400, detail="asset id cannot be changed by the route payload")
        item = write_asset(
            cartridge.get("package_path"),
            cartridge.get("manifest") or {},
            asset_id=asset_id,
            kind=payload.kind,
            relative_path=payload.path,
            media_type=payload.media_type,
            content=payload.content,
            encoding=payload.encoding,
        )
        return {"status": "asset_saved", "asset": item, "files": dev_flow_manager.read_files(cartridge_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CartridgeAssetError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@app.delete("/api/lab/flows/{cartridge_id}/assets/{asset_id}")
def delete_lab_flow_asset(cartridge_id: str, asset_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        delete_asset(cartridge.get("package_path"), cartridge.get("manifest") or {}, cartridge.get("root_flow") or {}, asset_id)
        return {"status": "asset_deleted", "asset_id": asset_id, "files": dev_flow_manager.read_files(cartridge_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CartridgeAssetError as exc:
        raise HTTPException(status_code=409 if exc.code == "ASSET_IN_USE" else 400, detail={"code": exc.code, "message": str(exc)})


@app.put("/api/lab/flows/{cartridge_id}/interaction-components/{component_id}")
def put_lab_flow_interaction_component(cartridge_id: str, component_id: str, payload: InteractionComponentPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        component = dict(payload.component)
        if component.get("id") not in {None, "", component_id}:
            raise HTTPException(status_code=400, detail="component id cannot be changed by the route payload")
        component["id"] = component_id
        item = write_component(cartridge.get("package_path"), cartridge.get("manifest") or {}, component)
        return {"status": "component_saved", "component": item, "files": dev_flow_manager.read_files(cartridge_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CartridgeAssetError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@app.delete("/api/lab/flows/{cartridge_id}/interaction-components/{component_id}")
def delete_lab_flow_interaction_component(cartridge_id: str, component_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        delete_component(cartridge.get("package_path"), cartridge.get("manifest") or {}, cartridge.get("root_flow") or {}, component_id)
        return {"status": "component_deleted", "component_id": component_id, "files": dev_flow_manager.read_files(cartridge_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CartridgeAssetError as exc:
        raise HTTPException(status_code=409 if exc.code == "COMPONENT_IN_USE" else 400, detail={"code": exc.code, "message": str(exc)})


@app.get("/api/lab/flows/{cartridge_id}/mcp-tools")
def list_lab_flow_mcp_tools(cartridge_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        manifest, files = _flow_manifest_files(cartridge_id)
        return {"cartridge_id": cartridge_id, "mcp_tools": _enrich_mcp_tools(manifest.get("mcp_tools", [])), "files": files}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/developer/flows/{cartridge_id}/portable-dlc")
def get_developer_portable_dlc(cartridge_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        manifest = cartridge.get("manifest") or {}
        if not manifest.get("portable_dlc"):
            return {"portable_dlc": None, "tools": []}
        descriptor = load_portable_dlc_descriptor(cartridge.get("package_path"), manifest)
        return {
            "portable_dlc": {key: descriptor.get(key) for key in ("id", "version", "scope")},
            "tools": [{
                "node_id": item.get("node_id"), "server": item.get("server"), "tool": item.get("tool"),
                "effect": item.get("effect"), "description": item.get("description"),
                "source_digest": item.get("source_digest"),
            } for item in descriptor.get("tools") or [] if isinstance(item, dict)],
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PortableDlcValidationError as exc:
        raise HTTPException(status_code=409, detail={"code": "DLC_DESCRIPTOR_INVALID", "message": str(exc)})


@app.post("/api/developer/flows/{cartridge_id}/portable-dlc")
def scaffold_developer_portable_dlc(cartridge_id: str, payload: PortableDlcScaffoldPayload):
    """Create a protocol-owned blank DLC skeleton; business behavior remains package-owned source."""
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise AuthoringServiceError("DLC_SOURCE_FLOW_READ_ONLY", "Only editable Developer flows can own a DLC.", status=403)
        manifest, files = _flow_manifest_files(cartridge_id)
        if manifest.get("portable_dlc"):
            raise AuthoringServiceError("DLC_ALREADY_EXISTS", "This Flow already owns a Portable DLC.", status=409)
        identifier = re.sub(r"[^A-Za-z0-9_]+", "_", payload.node_id).strip("_")
        if not identifier or identifier[0].isdigit():
            raise AuthoringServiceError("DLC_NODE_ID_INVALID", "DLC node id must be a valid Python identifier.")
        server = re.sub(r"[^A-Za-z0-9_.-]+", "_", payload.server).strip("_")
        tool = re.sub(r"[^A-Za-z0-9_.-]+", "_", payload.tool).strip("_")
        package_root = dev_flow_manager._flow_path(cartridge_id)
        source_relative = f"dlc/mcp_nodes/{identifier}.py"
        backend_relative = "dlc/backend/entry.py"
        descriptor_relative = "dlc/descriptor.json"
        source = f'''"""Package-owned custom capability implementation."""\n\nfrom cartridgeflow_dlc import McpContext, mcp_operation\n\n\nMCP_NODE = {{\n    "schema": "cartridgeflow.mcp_python.v1",\n    "node_id": "{identifier}",\n    "server": "{server}",\n    "tool": "{tool}",\n    "effect": "read_only",\n    "inputs": {{"input": {{"type": "object"}}}},\n    "outputs": {{"result": {{"type": "object"}}}},\n    "operations": [{{"id": "transform", "kind": "transform"}}],\n    "edges": [],\n    "fallbacks": [],\n}}\n\n\n@mcp_operation("transform")\ndef op_transform(ctx: McpContext, data: dict) -> dict:\n    return {{"result": data.get("input", data)}}\n\n\nOPERATIONS = {{"transform": op_transform}}\n\n\ndef run(ctx: McpContext, inputs: dict) -> dict:\n    return ctx.run_declared_graph(MCP_NODE, OPERATIONS, inputs)\n'''
        source_model = parse_mcp_python_source(source, display_path=source_relative)
        if not source_model.get("ok"):
            raise AuthoringServiceError("DLC_SCAFFOLD_INVALID", "Generated DLC source did not pass static validation.", status=500)
        backend = '''"""Portable DLC worker entry."""\n\nfrom core.extensions.worker_sdk import DlcWorkerRegistry\n\n\ndef invoke(request: dict) -> dict:\n    registry = DlcWorkerRegistry(request["workspace_root"], request["package_path"])\n    return registry.call(request.get("server", ""), request.get("tool", ""), request.get("params") or {{}})\n'''
        source_bytes = source.encode("utf-8")
        backend_bytes = backend.encode("utf-8")
        descriptor = {
            "schema": "cartridgeflow.portable_dlc.v3",
            "id": f"dlc.{cartridge_id.removeprefix('dev.').replace('.', '-')}",
            "version": str(manifest.get("version") or "0.0.1"),
            "owner_cartridge": cartridge_id,
            "scope": "cartridge",
            "backend": {"transport": "json_stdio_worker", "entry": backend_relative},
            "tools": [{
                "node_id": identifier, "server": server, "tool": tool, "handler": "run",
                "effect": "read_only", "timeout_ms": 45000, "description": payload.description,
                "implementation": {"language": "python", "format": "cartridgeflow.mcp_python.v1", "entry": source_relative},
                "transparency": "declared_graph", "source_digest": source_model["source_digest"],
            }],
            "protocols": [],
            "resources": [{"path": "dlc", "ownership": "package"}],
            "files": [
                {"path": backend_relative, "sha256": hashlib.sha256(backend_bytes).hexdigest(), "media_type": "text/x-python", "role": "backend_entry"},
                {"path": source_relative, "sha256": hashlib.sha256(source_bytes).hexdigest(), "media_type": "text/x-python", "role": "mcp_node_source"},
            ],
        }
        created = [package_root / source_relative, package_root / backend_relative, package_root / descriptor_relative]
        try:
            for path in created:
                path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_bytes(created[0], source_bytes)
            _atomic_write_bytes(created[1], backend_bytes)
            _atomic_write_bytes(created[2], (json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            manifest["portable_dlc"] = {"protocol": "CF-FARP@1.1", "descriptor": descriptor_relative}
            manifest["mcp_tools"] = [{
                "id": identifier, "name": payload.name, "type": "cartridge_dlc", "server": server, "tool": tool,
                "required": True, "enabled": True, "transparency": "declared_graph", "description": payload.description,
                "contract": {"side_effect": "read_only", "idempotent": True, "timeout_ms": 45000},
            }]
            result = _write_manifest_tools(cartridge_id, files, manifest)
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        return {"status": "portable_dlc_created", "node_id": identifier, "source_model": source_model, **result}
    except FileNotFoundError as exc:
        _authoring_error(AuthoringServiceError("DLC_SOURCE_FLOW_UNKNOWN", str(exc), status=404))
    except AuthoringServiceError as exc:
        _authoring_error(exc)


def _editable_mcp_source_context(cartridge_id: str, node_id: str) -> tuple[dict, dict, dict, Path, str, dict]:
    try:
        cartridge = registry.get_cartridge(cartridge_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not cartridge.get("editable"):
        raise HTTPException(status_code=403, detail="Only dev flows can edit MCP source")
    package_path = cartridge.get("package_path")
    if not package_path:
        raise HTTPException(status_code=409, detail={"code": "MCP_SOURCE_PACKAGE_REQUIRED", "message": "MCP source editing requires a package-backed dev flow"})
    manifest, _files = _flow_manifest_files(cartridge_id)
    if not isinstance(manifest.get("portable_dlc"), dict):
        raise HTTPException(status_code=409, detail={"code": "MCP_DESCRIPTOR_REQUIRED", "message": "MCP source editing requires a declared Portable DLC descriptor"})
    try:
        descriptor = load_portable_dlc_descriptor(package_path, manifest)
    except PortableDlcValidationError as exc:
        raise HTTPException(status_code=409, detail={"code": "MCP_DESCRIPTOR_INVALID", "message": str(exc)})
    tool = next(
        (
            item for item in descriptor.get("tools") or []
            if isinstance(item, dict) and str(item.get("node_id") or "") == node_id
        ),
        None,
    )
    if not isinstance(tool, dict):
        raise HTTPException(status_code=404, detail=f"MCP source node not found: {node_id}")
    entry = str((tool.get("implementation") or {}).get("entry") or "").replace("\\", "/")
    source_path = (Path(package_path).resolve() / entry).resolve()
    package_root = Path(package_path).resolve()
    if (source_path != package_root and package_root not in source_path.parents) or not source_path.is_file():
        raise HTTPException(status_code=404, detail=f"MCP source file not found: {entry}")
    source = source_path.read_text(encoding="utf-8")
    source_model = parse_mcp_python_file(source_path, display_path=entry)
    if not source_model.get("ok"):
        raise HTTPException(status_code=409, detail={"code": "MCP_SOURCE_INVALID", "message": "MCP source does not pass the protocol static parser", "findings": source_model.get("findings") or []})
    if source_model.get("node_id") != node_id:
        raise HTTPException(status_code=409, detail={"code": "MCP_NODE_ID_MISMATCH", "message": "MCP source node_id does not match the requested node"})
    return cartridge, manifest, descriptor, source_path, source, source_model


def _persist_mcp_source_edit(
    cartridge_id: str,
    node_id: str,
    manifest: dict,
    package_path: str | Path,
    source_path: Path,
    source: str,
    source_model: dict,
) -> dict:
    package_root = Path(package_path).resolve()
    descriptor_ref = str((manifest.get("portable_dlc") or {}).get("descriptor") or "")
    descriptor_path = resolve_package_file(package_root, descriptor_ref, "manifest.portable_dlc.descriptor")
    manifest_path = package_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("MCP source editing requires a package manifest")

    files = dev_flow_manager.read_files(cartridge_id)
    previous_files = {
        source_path: source_path.read_bytes(),
        descriptor_path: descriptor_path.read_bytes(),
        manifest_path: manifest_path.read_bytes(),
    }
    try:
        _atomic_write_bytes(source_path, source.encode("utf-8"))
        update_descriptor_source_digest(
            package_path,
            manifest,
            node_id=node_id,
            source_model=source_model,
        )
        result = _write_manifest_tools(cartridge_id, files, manifest)
    except Exception:
        rollback_errors = []
        for path, content in previous_files.items():
            try:
                _atomic_write_bytes(path, content)
            except OSError as rollback_error:
                rollback_errors.append(f"{path.name}: {rollback_error}")
        if rollback_errors:
            raise RuntimeError("MCP source edit failed and rollback was incomplete: " + "; ".join(rollback_errors))
        raise
    return {
        "status": "mcp_source_updated",
        "source": source,
        "source_model": source_model,
        "source_digest": source_model.get("source_digest"),
        **result,
    }


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


@app.get("/api/lab/flows/{cartridge_id}/mcp-nodes/{node_id}/source-model")
def get_lab_mcp_source_model(cartridge_id: str, node_id: str):
    _cartridge, _manifest, _descriptor, _source_path, _source, source_model = _editable_mcp_source_context(cartridge_id, node_id)
    return source_model


@app.get("/api/lab/flows/{cartridge_id}/mcp-nodes/{node_id}/source")
def get_lab_mcp_source(cartridge_id: str, node_id: str):
    _cartridge, _manifest, _descriptor, source_path, source, source_model = _editable_mcp_source_context(cartridge_id, node_id)
    return {
        "node_id": node_id,
        "path": (source_model.get("source") or {}).get("path") or source_path.name,
        "source": source,
        "source_digest": source_model.get("source_digest"),
        "source_model": source_model,
    }


@app.put("/api/lab/flows/{cartridge_id}/mcp-nodes/{node_id}/source")
def replace_lab_mcp_source(cartridge_id: str, node_id: str, payload: McpSourceReplacePayload):
    cartridge, manifest, _descriptor, source_path, _source, current_model = _editable_mcp_source_context(cartridge_id, node_id)
    if str(payload.expected_source_digest or "").strip().lower() != str(current_model.get("source_digest") or "").strip().lower():
        raise HTTPException(status_code=409, detail={"code": "MCP_SOURCE_DIGEST_CONFLICT", "message": "MCP source changed since the editor loaded it"})
    source = str(payload.source or "")
    source_model = parse_mcp_python_source(source, display_path=str((current_model.get("source") or {}).get("path") or source_path.name))
    if not source_model.get("ok"):
        raise HTTPException(status_code=400, detail={"code": "MCP_SOURCE_EDIT_INVALID", "message": "Edited MCP source did not pass static validation", "findings": source_model.get("findings") or []})
    if source_model.get("node_id") != node_id:
        raise HTTPException(status_code=400, detail={"code": "MCP_NODE_ID_MISMATCH", "message": "Edited source must retain the MCP node identity"})
    return _persist_mcp_source_edit(cartridge_id, node_id, manifest, cartridge.get("package_path"), source_path, source, source_model)


@app.patch("/api/lab/flows/{cartridge_id}/mcp-nodes/{node_id}/operation-graph")
def patch_lab_mcp_operation_graph(cartridge_id: str, node_id: str, payload: McpSourcePatchPayload):
    cartridge, manifest, _descriptor, source_path, source, _source_model = _editable_mcp_source_context(cartridge_id, node_id)
    try:
        next_source, next_model = edit_mcp_source_graph(
            source,
            expected_source_digest=payload.expected_source_digest,
            graph=payload.graph,
        )
        return _persist_mcp_source_edit(cartridge_id, node_id, manifest, cartridge.get("package_path"), source_path, next_source, next_model)
    except McpSourceEditError as exc:
        status = 409 if exc.code == "MCP_SOURCE_DIGEST_CONFLICT" else 400
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)})


@app.post("/api/lab/flows/{cartridge_id}/mcp-nodes/{node_id}/operations")
def add_lab_mcp_operation(cartridge_id: str, node_id: str, payload: McpOperationCreatePayload):
    cartridge, manifest, _descriptor, source_path, source, _source_model = _editable_mcp_source_context(cartridge_id, node_id)
    try:
        next_source, next_model = add_mcp_operation(
            source,
            expected_source_digest=payload.expected_source_digest,
            operation=payload.operation,
        )
        return _persist_mcp_source_edit(cartridge_id, node_id, manifest, cartridge.get("package_path"), source_path, next_source, next_model)
    except McpSourceEditError as exc:
        status = 409 if exc.code in {"MCP_SOURCE_DIGEST_CONFLICT", "MCP_OPERATION_EXISTS"} else 400
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)})


@app.get("/api/lab/flows/{cartridge_id}/resource-catalog")
def get_lab_flow_resource_catalog(cartridge_id: str):
    from core.studio.resource_catalog import build_flow_resource_catalog

    try:
        cartridge = registry.get_cartridge(cartridge_id)
        return build_flow_resource_catalog(
            ROOT,
            cartridge.get("manifest") or {},
            cartridge.get("root_flow") or {},
            package_path=cartridge.get("package_path"),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _resource_catalog_http_error(exc) -> HTTPException:
    detail = {"code": exc.code, "message": str(exc)}
    if exc.health is not None:
        detail["connection_health"] = exc.health
    return HTTPException(status_code=exc.status_code, detail=detail)


@app.get("/api/lab/flows/{cartridge_id}/resource-details/{resource_id:path}")
def get_lab_flow_resource_detail(cartridge_id: str, resource_id: str):
    from core.studio.resource_catalog import ResourceCatalogError, get_flow_resource_detail

    try:
        cartridge = registry.get_cartridge(cartridge_id)
        return get_flow_resource_detail(
            ROOT,
            cartridge.get("manifest") or {},
            cartridge.get("root_flow") or {},
            resource_id,
            package_path=cartridge.get("package_path"),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CARTRIDGE_NOT_FOUND", "message": str(exc)})
    except ResourceCatalogError as exc:
        raise _resource_catalog_http_error(exc)


@app.post("/api/lab/flows/{cartridge_id}/resource-connectivity/{resource_id:path}")
def check_lab_flow_resource_connectivity(cartridge_id: str, resource_id: str):
    from core.studio.resource_catalog import ResourceCatalogError, check_flow_resource_connectivity

    try:
        cartridge = registry.get_cartridge(cartridge_id)
        return check_flow_resource_connectivity(
            ROOT,
            cartridge.get("manifest") or {},
            cartridge.get("root_flow") or {},
            resource_id,
            package_path=cartridge.get("package_path"),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CARTRIDGE_NOT_FOUND", "message": str(exc)})
    except ResourceCatalogError as exc:
        raise _resource_catalog_http_error(exc)


def _ensure_manifest_tool_editor_allowed(manifest: dict) -> None:
    if manifest.get("portable_dlc"):
        raise HTTPException(
            status_code=409,
            detail="Portable DLC tools are owned by dlc/descriptor.json and cannot be edited independently.",
        )


@app.post("/api/lab/flows/{cartridge_id}/mcp-tools")
def create_lab_flow_mcp_tool(cartridge_id: str, payload: McpToolPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        manifest, files = _flow_manifest_files(cartridge_id)
        _ensure_manifest_tool_editor_allowed(manifest)
        tools = manifest.setdefault("mcp_tools", [])
        tool = _normalize_mcp_tool(payload.model_dump())
        existing_ids = {item.get("id") for item in tools if isinstance(item, dict)}
        base_id = tool["id"]
        index = 2
        while tool["id"] in existing_ids:
            tool["id"] = f"{base_id}_{index}"
            index += 1
        tools.append(tool)
        result = _write_manifest_tools(cartridge_id, files, manifest)
        return {"status": "mcp_tool_created", "tool": tool, **result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/lab/flows/{cartridge_id}/mcp-tools/{tool_id}")
def update_lab_flow_mcp_tool(cartridge_id: str, tool_id: str, payload: McpToolPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        manifest, files = _flow_manifest_files(cartridge_id)
        _ensure_manifest_tool_editor_allowed(manifest)
        tools = manifest.setdefault("mcp_tools", [])
        for index, item in enumerate(tools):
            if isinstance(item, dict) and item.get("id") == tool_id:
                data = payload.model_dump()
                data["id"] = tool_id
                tools[index] = _normalize_mcp_tool(data)
                result = _write_manifest_tools(cartridge_id, files, manifest)
                return {"status": "mcp_tool_updated", "tool": tools[index], **result}
        raise HTTPException(status_code=404, detail=f"MCP tool not found: {tool_id}")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/lab/flows/{cartridge_id}/mcp-tools/{tool_id}")
def delete_lab_flow_mcp_tool(cartridge_id: str, tool_id: str):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        manifest, files = _flow_manifest_files(cartridge_id)
        _ensure_manifest_tool_editor_allowed(manifest)
        tools = manifest.setdefault("mcp_tools", [])
        next_tools = [item for item in tools if not (isinstance(item, dict) and item.get("id") == tool_id)]
        if len(next_tools) == len(tools):
            raise HTTPException(status_code=404, detail=f"MCP tool not found: {tool_id}")
        manifest["mcp_tools"] = next_tools
        result = _write_manifest_tools(cartridge_id, files, manifest)
        return {"status": "mcp_tool_deleted", "tool_id": tool_id, **result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/lab/flows/{cartridge_id}/validate")
def validate_lab_flow(cartridge_id: str, payload: DevFlowFilesPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        return dev_flow_manager.validate_files(cartridge_id, payload.files)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/lab/flows/{cartridge_id}/compatibility")
def get_lab_flow_compatibility(cartridge_id: str, payload: DevFlowFilesPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        return _compatibility_for_files(cartridge_id, payload.files)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/lab/flows/{cartridge_id}/certification")
def get_lab_flow_certification(cartridge_id: str, payload: DevFlowFilesPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        report, _manifest, _files = _certification_for_files(cartridge_id, payload.files)
        return report
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/lab/flows/{cartridge_id}/certification/apply")
def apply_lab_flow_certification(cartridge_id: str, payload: DevFlowFilesPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        report, manifest, files = _certification_for_files(cartridge_id, payload.files)
        if not report.get("ok"):
            raise HTTPException(status_code=400, detail={
                "error": "protocol_certification_failed",
                "message": "Protocol certification checks must pass before applying the certification label.",
                "report": report,
            })
        import json as _json
        next_manifest = apply_protocol_certification_label(manifest, report)
        files["manifest"] = _json.dumps(next_manifest, ensure_ascii=False, indent=2)
        dev_flow_manager.save_file(cartridge_id, "manifest", files["manifest"])
        return {
            "ok": True,
            "cartridge_id": cartridge_id,
            "label": report.get("label"),
            "report": report,
            "files": files,
            "manifest": next_manifest,
        }
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/lab/flows/{cartridge_id}/preview-graph")
def preview_lab_flow_graph(cartridge_id: str, payload: DevFlowFilesPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        preview_cartridge = dev_flow_manager.preview_graph(cartridge_id, payload.files)
        return {"graph": flow_graph_builder.build(preview_cartridge)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/lab/flows/{cartridge_id}/analyze")
def analyze_lab_flow(cartridge_id: str, payload: FlowAnalysisPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are analyzable from the authoring API")
        preview = dev_flow_manager.preview_graph(cartridge_id, payload.files)
        from core.lab.flow_analyzer import ANALYSIS_TARGETS, analyze_flow
        if payload.target not in ANALYSIS_TARGETS:
            raise HTTPException(status_code=400, detail="target must be draft, dev, preview, production, package, or publish")
        root_flow = preview.get("root_flow") or {}
        protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
        catalog = load_protocol_release_catalog(ROOT)
        return analyze_flow(
            root_flow,
            preview,
            target=payload.target,
            base=load_base_implementation(ROOT),
            runtime_adapter=catalog.runtime_adapter(str(protocol.get("id") or ""), str(protocol.get("version") or "")),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/lab/flows/{cartridge_id}/readiness")
def get_lab_flow_readiness(cartridge_id: str, payload: DevFlowFilesPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        files = payload.files if cartridge.get("editable") else {}
        preview = dev_flow_manager.preview_graph(cartridge_id, files) if cartridge.get("editable") else cartridge
        root_flow = preview.get("root_flow") or {}
        protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
        catalog = load_protocol_release_catalog(ROOT)
        from core.lab.flow_analyzer import analyze_flow, build_authoring_readiness
        analysis = analyze_flow(
            root_flow,
            preview,
            target="dev",
            base=load_base_implementation(ROOT),
            runtime_adapter=catalog.runtime_adapter(str(protocol.get("id") or ""), str(protocol.get("version") or "")),
        )
        manifest = preview.get("manifest") if isinstance(preview.get("manifest"), dict) else preview
        from core.studio.resource_catalog import build_flow_resource_catalog
        resource_catalog = build_flow_resource_catalog(
            ROOT,
            manifest,
            root_flow,
            package_path=cartridge.get("package_path"),
        )
        return build_authoring_readiness(manifest, root_flow, analysis, resource_catalog)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


_NODE_UPDATE_FIELDS = (
    "title", "type", "action", "next", "kind", "executor", "effect",
    "display_name", "experience", "component_ref", "interaction_mode", "input_binding",
    "action_routes", "output", "display", "input_kind", "source",
    "input_schema", "output_contract", "decision_contract", "decision_test_mode",
    "mock_decision_envelope", "primary_output", "tool_binding", "allowed_tools",
    "mcp_binding", "failure_policy", "permission", "audit_log", "endpoint",
    "timeout_ms", "agent", "tools", "params", "model_role", "layout", "inputs",
    "outputs",
)


def _apply_node_update_payload(state: dict, payload: NodeUpdatePayload) -> None:
    """Apply the same typed node patch during create and update operations."""
    provided_fields = payload.model_fields_set
    for key in _NODE_UPDATE_FIELDS:
        if key not in provided_fields:
            continue
        value = getattr(payload, key)
        if value is None:
            state.pop(key, None)
        else:
            state[key] = value


def _apply_manifest_contracts(
    files: dict,
    payload: NodeUpdatePayload | None,
    previous_state: dict | None = None,
    preserve_existing_inputs: bool = True,
) -> bool:
    if payload is None:
        return False
    updates_inputs = "manifest_inputs" in payload.model_fields_set
    updates_roles = "manifest_model_roles" in payload.model_fields_set
    updates_permissions = "manifest_permissions" in payload.model_fields_set
    if not updates_inputs and not updates_roles and not updates_permissions:
        return False
    import json as _json
    manifest = _json.loads(files.get("manifest") or "{}")
    if updates_inputs:
        previous_params = previous_state.get("params") if isinstance(previous_state, dict) and isinstance(previous_state.get("params"), dict) else {}
        previous_input_ids = {
            str(item).strip()
            for item in previous_params.get("fields") or []
            if str(item).strip()
        }
        incoming_inputs = [item for item in payload.manifest_inputs or [] if isinstance(item, dict)]
        incoming_ids = {str(item.get("id") or "").strip() for item in incoming_inputs}
        preserved_inputs = [
            item for item in manifest.get("inputs") or []
            if isinstance(item, dict)
            and str(item.get("id") or "").strip() not in previous_input_ids
            and str(item.get("id") or "").strip() not in incoming_ids
        ] if preserve_existing_inputs else []
        manifest["inputs"] = [*preserved_inputs, *incoming_inputs]
    if updates_roles:
        recipe = manifest.get("llm_recipe") if isinstance(manifest.get("llm_recipe"), dict) else {}
        incoming_roles = [item for item in payload.manifest_model_roles or [] if isinstance(item, dict)]
        incoming_role_ids = {str(item.get("id") or "").strip() for item in incoming_roles}
        preserved_roles = [
            item for item in recipe.get("roles") or []
            if isinstance(item, dict) and str(item.get("id") or "").strip() not in incoming_role_ids
        ]
        manifest["llm_recipe"] = {
            **recipe,
            "schema": "cartridgeflow.llm_recipe.v1",
            "roles": [*preserved_roles, *incoming_roles],
        }
    if updates_permissions:
        incoming_permissions = [item for item in payload.manifest_permissions or [] if isinstance(item, dict)]
        incoming_permission_ids = {str(item.get("id") or "").strip() for item in incoming_permissions}
        previous_permission_id = str(
            previous_state.get("permission") or ""
        ).strip() if isinstance(previous_state, dict) else ""
        preserved_permissions = [
            item for item in manifest.get("permissions") or []
            if isinstance(item, dict)
            and str(item.get("id") or "").strip() != previous_permission_id
            and str(item.get("id") or "").strip() not in incoming_permission_ids
        ]
        manifest["permissions"] = [*preserved_permissions, *incoming_permissions]
    files["manifest"] = _json.dumps(manifest, ensure_ascii=False, indent=2)
    return True


@app.post("/api/lab/flows/{cartridge_id}/nodes")
def create_lab_flow_node(cartridge_id: str, payload: NodeCreatePayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    import json as _json
    import re as _re
    files = dev_flow_manager.read_files(cartridge_id)
    files.update(payload.files)
    root_flow = _json.loads(files.get("root_flow") or "{}")
    states = root_flow.setdefault("states", {})
    node_id = _re.sub(r"[^a-zA-Z0-9_-]+", "_", payload.node_id.strip()).strip("_").lower()
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required")
    if node_id in states:
        raise HTTPException(status_code=409, detail=f"Node already exists: {node_id}")
    templates = {
        "interaction": {
            "type": "process",
            "kind": "interaction",
            "executor": "deterministic",
            "effect": "none",
            "display_name": "交互展示",
            "title": "交互节点",
            "action": "render_interaction",
            "component_ref": "welcome.panel",
            "interaction_mode": "display",
            "input_binding": {},
            "action_routes": {},
            "inputs": {},
            "outputs": {},
            "params": {"node_category": "interaction"},
        },
        "welcome": {
            "type": "process",
            "kind": "ui",
            "executor": "deterministic",
            "effect": "writes_store",
            "display": {"suffix": "展示", "label": "处理节点-展示"},
            "title": "UI 展示节点",
            "action": "show_ui",
            "inputs": {},
            "outputs": {},
            "params": {"node_category": "ui", "preset": "welcome", "preset_config": {"path": "assets/welcome.html", "format": "html", "output_name": "welcome_ui"}, "description": "展示欢迎页、结果页或 HTML/Markdown 界面。", "output": "welcome_ui"},
        },
        "prompt": {
            "type": "process",
            "kind": "decision",
            "executor": "llm",
            "effect": "none",
            "display": {"suffix": "AI决策", "label": "处理节点-AI决策"},
            "title": "AI 决策节点",
            "action": "llm_prompt",
            "inputs": {},
            "outputs": {},
            "params": {"system_prompt": "你是一个可靠的助手。", "prompt": "请根据用户输入完成任务。"},
        },
        "input": {
            "type": "process",
            "kind": "input",
            "executor": "user",
            "effect": "writes_store",
            "display": {"suffix": "输入", "label": "处理节点-输入"},
            "title": "收集输入",
            "action": "collect_inputs",
            "input_kind": "initial",
            "source": "user_form",
            "input_schema": "input.v1",
            "inputs": {},
            "outputs": {},
            "params": {"fields": [], "node_category": "input"},
        },
        "checkpoint": {
            "type": "process",
            "kind": "human_gate",
            "executor": "human",
            "effect": "writes_store",
            "display": {"suffix": "人工确认", "label": "处理节点-人工确认"},
            "title": "人工确认",
            "action": "confirm_checkpoint",
            "output_contract": "gate_result.v1",
            "inputs": {},
            "outputs": {
                "review_result": {
                    "schema": {"type": "object"},
                    "target": {"type": "store", "key": "review_result"},
                },
            },
            "params": {
                "condition": "请审核当前结果，并选择批准或填写修改意见。",
                "output": "review_result",
                "node_category": "control",
                "interaction": {
                    "id": "capability_review",
                    "store_key": "review_response",
                    "prompt": "请审核当前结果，并选择批准或填写修改意见。",
                    "resume_policy": "resume_same_node",
                    "input_schema": {
                        "type": "object",
                        "required": ["approval"],
                        "properties": {
                            "approval": {"type": "string", "enum": ["approved", "rejected"]},
                            "feedback": {"type": "string"},
                        },
                    },
                    "offline_answer": {"approval": "approved", "feedback": ""},
                },
            },
        },
        "runtime": {
            "type": "process",
            "kind": "transfer",
            "executor": "deterministic",
            "effect": "writes_store",
            "display": {"suffix": "传递", "label": "处理节点-传递"},
            "title": "运行处理",
            "action": "pass_result",
            "inputs": {},
            "outputs": {
                "result": {
                    "schema": {"type": "object"},
                    "target": {"type": "store", "key": "result"},
                },
            },
            "params": {"node_category": "transfer", "input": "input", "output": "result"},
        },
        "tool_call": {
            "type": "process",
            "kind": "mcp_read",
            "executor": "mcp",
            "effect": "read_only",
            "display": {"suffix": "工具调用", "label": "处理节点-工具调用"},
            "title": "调用工具",
            "action": "tool_call",
            "tool_binding": "static_params",
            "failure_policy": "fail_closed",
            "audit_log": True,
            "allowed_tools": [],
            "mcp_binding": {"mode": "read_only", "allowed_tools": []},
            "inputs": {},
            "outputs": {
                "result": {
                    "schema": {"type": "object"},
                    "target": {"type": "store", "key": "result"},
                },
            },
            "params": {"node_category": "tool", "output": "result", "tool_params": {}},
        },
        "remote_call": {
            "type": "process",
            "kind": "remote_call",
            "executor": "remote",
            "effect": "external_side_effect",
            "display": {"suffix": "远程执行", "label": "处理节点-远程执行"},
            "title": "处理节点-远程执行",
            "action": "remote_call",
            "tool_binding": "static_params",
            "failure_policy": "fail_closed",
            "permission": "external_service_call",
            "audit_log": True,
            "endpoint": "remote://pending",
            "timeout_ms": 120000,
            "inputs": {},
            "outputs": {},
            "params": {"node_category": "remote"},
        },
    }
    template = templates.get(payload.template_id)
    if not template:
        raise HTTPException(status_code=400, detail=f"Unsupported template_id: {payload.template_id}")
    new_state = _json.loads(_json.dumps(template, ensure_ascii=False))
    new_state["scope"] = "sub_flow"
    new_state["entry_kind"] = "sub_flow"
    new_state["template_id"] = payload.template_id
    new_state["locked"] = False
    if payload.title:
        new_state["title"] = payload.title
    if payload.node is not None:
        _apply_node_update_payload(new_state, payload.node)
    has_existing_user_form = any(
        isinstance(item, dict)
        and isinstance(item.get("params"), dict)
        and str(item.get("action") or item["params"].get("action") or "") == "collect_inputs"
        and (
            str(item["params"].get("preset") or "") == "user_form"
            or str(item.get("input_kind") or "") == "initial"
        )
        for item in states.values()
    )
    manifest_changed = _apply_manifest_contracts(
        files,
        payload.node,
        preserve_existing_inputs=has_existing_user_form,
    )
    _ensure_typed_node_contracts(root_flow, new_state)
    after_node_id = payload.after_node_id or root_flow.get("start")
    if _is_execution_plan_root_flow(root_flow):
        plan = root_flow.setdefault("execution_plan", {
            "schema": "cartridgeflow.execution_plan.v1",
            "entry": root_flow.get("start"),
            "edges": [],
        })
        edges = [edge for edge in plan.get("edges") or [] if isinstance(edge, dict)]
        if after_node_id and after_node_id in states:
            source_layout = states[after_node_id].get("layout") or {}
            new_state["layout"] = {"x": int(source_layout.get("x", 80)) + 300, "y": int(source_layout.get("y", 120))}
            successor = next((edge for edge in edges if edge.get("kind") == "sequence" and edge.get("from") == after_node_id), None)
            if successor:
                edges.remove(successor)
                successor_target = str(successor.get("to") or "")
                edges.append({"id": f"{after_node_id}_{node_id}", "kind": "sequence", "from": after_node_id, "to": node_id})
                if successor_target:
                    edges.append({"id": f"{node_id}_{successor_target}", "kind": "sequence", "from": node_id, "to": successor_target})
            else:
                edges.append({"id": f"{after_node_id}_{node_id}", "kind": "sequence", "from": after_node_id, "to": node_id})
        elif not root_flow.get("start"):
            root_flow["start"] = node_id
            plan["entry"] = node_id
        states[node_id] = new_state
        if new_state.get("type") == "process":
            failed_id = f"{node_id}_failed"
            if failed_id not in states:
                states[failed_id] = {"type": "terminal", "title": f"{new_state.get('title') or node_id}失败结束", "display_name": "失败结束", "locked": True}
            edges.append({
                "id": f"{node_id}_failure",
                "kind": "failure",
                "from": node_id,
                "to": failed_id,
                "failure": {"id": f"{node_id}_exception", "causes": ["exception"]},
            })
        plan["schema"] = "cartridgeflow.execution_plan.v1"
        plan["entry"] = str(plan.get("entry") or root_flow.get("start") or "")
        plan["edges"] = edges
        root_flow.pop("edges", None)
        root_flow.pop("control_edges", None)
        files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
        _validate_candidate_interaction_contracts(cartridge_id, files, root_flow)
        validation = dev_flow_manager.validate_files(cartridge_id, files)
        graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
        dev_flow_manager.save_file(cartridge_id, "root_flow", files["root_flow"])
        if manifest_changed:
            dev_flow_manager.save_file(cartridge_id, "manifest", files["manifest"])
        return {"status": "node_created", "node_id": node_id, "files": files, "validation": validation, "graph": graph}
    current_edges = _flow_edges(root_flow)
    branch_edges = [edge for edge in current_edges if _edge_scope(edge) != "root"]
    if after_node_id and after_node_id in states:
        source_layout = states[after_node_id].get("layout") or {}
        source_x = int(source_layout.get("x", 80))
        source_y = int(source_layout.get("y", 120))
        if payload.insert_mode == "branch":
            branch_count = sum(1 for edge in branch_edges if (edge.get("from") or edge.get("source")) == after_node_id and _edge_scope(edge) == "branch")
            direction = 1 if branch_count % 2 == 0 else -1
            lane = branch_count // 2 + 1
            new_state["layout"] = {"x": source_x + 300, "y": source_y + direction * lane * 150}
            branch_edges.append({"from": after_node_id, "to": node_id, "scope": "branch", "label": payload.title or "新分支"})
        else:
            new_state.setdefault("layout", {"x": source_x + 300, "y": source_y})
            previous_next = states[after_node_id].get("next")
            new_state["next"] = previous_next
            states[after_node_id]["next"] = node_id
    elif not root_flow.get("start"):
        root_flow["start"] = node_id
    states[node_id] = new_state
    _sync_flow_edges_from_next(root_flow, branch_edges)
    files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
    _validate_candidate_interaction_contracts(cartridge_id, files, root_flow)
    validation = dev_flow_manager.validate_files(cartridge_id, files)
    graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
    dev_flow_manager.save_file(cartridge_id, "root_flow", files["root_flow"])
    if manifest_changed:
        dev_flow_manager.save_file(cartridge_id, "manifest", files["manifest"])
    return {"status": "node_created", "node_id": node_id, "files": files, "validation": validation, "graph": graph}


@app.delete("/api/lab/flows/{cartridge_id}/nodes/{node_id}")
def delete_lab_flow_node(cartridge_id: str, node_id: str, payload: NodeDeletePayload | None = None):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    import json as _json
    files = dev_flow_manager.read_files(cartridge_id)
    files.update(payload.files if payload else {})
    root_flow = _json.loads(files.get("root_flow") or "{}")
    states = root_flow.get("states") or {}
    if node_id not in states:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    state = states[node_id]
    if state.get("locked") or node_id == root_flow.get("start"):
        raise HTTPException(status_code=400, detail="Locked or start node cannot be deleted")

    deleted_next = state.get("next")
    original_edges = _flow_edges(root_flow)
    branch_edges = []
    for edge in original_edges:
        source = edge.get("from") or edge.get("source")
        target = edge.get("to") or edge.get("target")
        scope = _edge_scope(edge)
        if source == node_id or target == node_id:
            continue
        if scope != "root" and source in states and target in states:
            branch_edge = {"from": source, "to": target, "scope": scope}
            if edge.get("label"):
                branch_edge["label"] = edge.get("label")
            branch_edges.append(branch_edge)

    for source_id, source_state in states.items():
        if source_id == node_id:
            continue
        if source_state.get("next") == node_id:
            if deleted_next and deleted_next in states and deleted_next != node_id:
                source_state["next"] = deleted_next
            else:
                source_state.pop("next", None)
    states.pop(node_id, None)
    failure_id = f"{node_id}_failed"
    if failure_id in states and states[failure_id].get("locked"):
        states.pop(failure_id, None)

    for annotation in root_flow.get("annotations") or []:
        if not isinstance(annotation, dict):
            continue
        anchor = annotation.get("anchor")
        if isinstance(anchor, dict) and anchor.get("type") == "node" and anchor.get("id") == node_id:
            annotation.pop("anchor", None)

    _sync_flow_edges_from_next(root_flow, branch_edges)

    files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
    dev_flow_manager.save_file(cartridge_id, "root_flow", files["root_flow"])
    flow_protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
    if has_protocol_feature(str(flow_protocol.get("id") or ""), str(flow_protocol.get("version") or ""), "recipe_versioning"):
        dev_flow_manager.tuning.retire_node_head(cartridge_id, node_id)
    validation = dev_flow_manager.validate_files(cartridge_id, files)
    graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
    return {"status": "node_deleted", "node_id": node_id, "files": files, "validation": validation, "graph": graph}


@app.put("/api/lab/flows/{cartridge_id}/nodes/{node_id}")
def update_lab_flow_node(cartridge_id: str, node_id: str, payload: NodeUpdatePayload):
    """表单编辑节点：更新 root_flow.states[node_id] 的字段。"""
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    files = dev_flow_manager.read_files(cartridge_id)
    files.update(payload.files)

    import json as _json
    try:
        root_flow = _json.loads(files.get("root_flow") or "{}")
    except _json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"root.flow.json 不是合法 JSON: {e.msg}")
    states = root_flow.get("states") or {}
    if node_id not in states:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

    state = states[node_id]
    manifest_changed = _apply_manifest_contracts(files, payload, state)
    _apply_node_update_payload(state, payload)
    _ensure_typed_node_contracts(root_flow, state)
    if _is_typed_root_flow(root_flow):
        branch_edges = [edge for edge in _flow_edges(root_flow) if _edge_scope(edge) != "root"]
        _sync_flow_edges_from_next(root_flow, branch_edges)

    files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
    _validate_candidate_interaction_contracts(cartridge_id, files, root_flow)
    validation = dev_flow_manager.validate_files(cartridge_id, files)
    graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
    if validation.get("valid"):
        dev_flow_manager.save_file(cartridge_id, "root_flow", files["root_flow"])
        if manifest_changed:
            dev_flow_manager.save_file(cartridge_id, "manifest", files["manifest"])
    return {
        "status": "node_updated",
        "node_id": node_id,
        "files": files,
        "validation": validation,
        "graph": graph,
    }


@app.put("/api/lab/flows/{cartridge_id}/layout")
def save_lab_flow_layout(cartridge_id: str, payload: LayoutSavePayload):
    """批量保存节点坐标（拖拽布局元数据）。"""
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    files = dev_flow_manager.read_files(cartridge_id)

    import json as _json
    try:
        root_flow = _json.loads(files.get("root_flow") or "{}")
    except _json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"root.flow.json 不是合法 JSON: {e.msg}")
    states = root_flow.get("states") or {}
    for node_id, coords in (payload.layout or {}).items():
        if node_id in states:
            state = states[node_id]
            layout = state.setdefault("layout", {})
            if isinstance(coords, dict):
                if "x" in coords:
                    layout["x"] = int(coords["x"])
                if "y" in coords:
                    layout["y"] = int(coords["y"])

    files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
    dev_flow_manager.save_file(cartridge_id, "root_flow", files["root_flow"])
    graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
    write_flow_layout_log(cartridge_id, graph, "layout_saved")
    return {"status": "layout_saved", "files": files, "graph": graph}


@app.put("/api/lab/flows/{cartridge_id}/edges")
def save_lab_flow_edges(cartridge_id: str, payload: EdgeSavePayload):
    """保存可视化连线；允许节点多入多出，states.next 仅同步第一条 root 出边。"""
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    files = dev_flow_manager.read_files(cartridge_id)

    import json as _json
    root_flow = _json.loads(files.get("root_flow") or "{}")
    states = root_flow.get("states") or {}
    start_state = root_flow.get("start")
    normalized_edges = []
    next_by_source = {}
    seen_pairs = set()
    for edge in payload.edges or []:
        source = edge.get("from") or edge.get("source")
        target = edge.get("to") or edge.get("target")
        if not source or not target or source == target:
            continue
        if source not in states or target not in states:
            continue
        if target == start_state:
            continue
        if (states.get(source) or {}).get("type") == "terminal" and source != start_state:
            continue
        scope = edge.get("scope") or "root"
        edge_key = (scope, source, target)
        if edge_key in seen_pairs:
            continue
        if scope == "root" and source not in next_by_source:
            next_by_source[source] = target
        seen_pairs.add(edge_key)
        normalized_edge = {"from": source, "to": target, "scope": scope}
        if edge.get("label"):
            normalized_edge["label"] = edge.get("label")
        normalized_edges.append(normalized_edge)

    for state_id, state in states.items():
        if state_id in next_by_source:
            state["next"] = next_by_source[state_id]
        elif state.get("next") and state.get("next") in states:
            state.pop("next", None)
        _ensure_typed_node_contracts(root_flow, state)
    _write_flow_edges(root_flow, normalized_edges)

    files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
    dev_flow_manager.save_file(cartridge_id, "root_flow", files["root_flow"])
    validation = dev_flow_manager.validate_files(cartridge_id, files)
    graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
    return {"status": "edges_saved", "files": files, "validation": validation, "graph": graph}


@app.put("/api/lab/flows/{cartridge_id}/annotations")
def save_lab_flow_annotations(cartridge_id: str, payload: AnnotationSavePayload):
    """Save design-only canvas annotations without changing runtime node semantics."""
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if len(payload.annotations) > 200:
        raise HTTPException(status_code=400, detail="A flow can contain at most 200 annotations")

    files = dev_flow_manager.read_files(cartridge_id)
    import json as _json
    try:
        root_flow = _json.loads(files.get("root_flow") or "{}")
    except _json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"root.flow.json is not valid JSON: {e.msg}")

    states = root_flow.get("states") or {}
    normalized = []
    seen_ids = set()
    for index, item in enumerate(payload.annotations):
        def annotation_number(key: str, default: float) -> float:
            try:
                value = float(item.get(key, default))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"Invalid annotation {key} at index {index}")
            if not math.isfinite(value):
                raise HTTPException(status_code=400, detail=f"Invalid annotation {key} at index {index}")
            return value

        annotation_id = str(item.get("id") or "").strip()
        if not annotation_id or len(annotation_id) > 96:
            raise HTTPException(status_code=400, detail=f"Invalid annotation id at index {index}")
        if annotation_id in seen_ids:
            raise HTTPException(status_code=400, detail=f"Duplicate annotation id: {annotation_id}")
        seen_ids.add(annotation_id)
        tone = str(item.get("tone") or "neutral")
        if tone not in {"neutral", "warning"}:
            tone = "neutral"
        annotation = {
            "id": annotation_id,
            "title": str(item.get("title") or "新注释")[:160],
            "body": str(item.get("body") or "")[:10000],
            "x": int(round(annotation_number("x", 0))),
            "y": int(round(annotation_number("y", 0))),
            "width": max(240, min(640, int(round(annotation_number("width", 320))))),
            "height": max(120, min(520, int(round(annotation_number("height", 180))))),
            "tone": tone,
            "collapsed": bool(item.get("collapsed")),
        }
        anchor = item.get("anchor")
        if isinstance(anchor, dict) and anchor.get("type") == "node" and anchor.get("id") in states:
            annotation["anchor"] = {"type": "node", "id": anchor["id"]}
        normalized.append(annotation)

    root_flow["annotations"] = normalized
    files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
    dev_flow_manager.save_file(cartridge_id, "root_flow", files["root_flow"])
    graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
    return {"status": "annotations_saved", "files": files, "graph": graph}


@app.get("/api/lab/flows/{cartridge_id}/runs")
def get_lab_flow_runs(cartridge_id: str):
    runs = [run for run in runner.list_runs() if run.get("cartridge_id") == cartridge_id]
    latest_run = runs[0] if runs else None
    return {
        "cartridge_id": cartridge_id,
        "items": runs[:10],
        "latest_run_events": runner.get_events(latest_run["run_id"]) if latest_run else [],
    }


class LabTestRunCreate(BaseModel):
    inputs: dict[str, str] | None = None
    probe_range: dict | None = None


def _compatibility_blocked_detail(report: dict) -> dict:
    blockers = [
        item for item in report.get("findings") or []
        if isinstance(item, dict) and item.get("severity") == "blocker"
    ]
    first = blockers[0] if blockers else {}
    location = f"节点 {first.get('node_id')}：" if first.get("node_id") else ""
    reason = str(first.get("message") or "当前流程不符合运行契约")
    count = len(blockers) or int((report.get("summary") or {}).get("blocker") or 0)
    return {
        "error": "compatibility_blocked",
        "message": f"运行前检查发现 {count} 个阻断项。{location}{reason}",
        "report": report,
    }


@app.post("/api/lab/flows/{cartridge_id}/test-run")
def create_lab_flow_test_run(cartridge_id: str, payload: LabTestRunCreate | None = None):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    probe_range = payload.probe_range if payload else None
    test_mode = {"decision": "live_collaboration"}
    if probe_range:
        try:
            runner.validate_probe_range(cartridge.get("root_flow") or {}, probe_range)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    try:
        compatibility = runner.build_cartridge_compatibility_report(cartridge_id, use_draft=True)
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not compatibility.get("ok"):
        raise HTTPException(status_code=400, detail=_compatibility_blocked_detail(compatibility))
    user_inputs = (payload.inputs if payload and payload.inputs else None) or {}
    inputs = {}
    for item in cartridge.get("inputs", []):
        input_id = item.get("id")
        if not input_id:
            continue
        if input_id in user_inputs:
            inputs[input_id] = user_inputs[input_id]
        elif item.get("default") not in (None, ""):
            inputs[input_id] = str(item.get("default"))
        elif item.get("type") == "select":
            options = item.get("options") or [{"value": "feature"}]
            inputs[input_id] = options[0].get("value", "feature") if options else "feature"
        elif item.get("type") == "textarea":
            inputs[input_id] = f"Developer Lab smoke test for {cartridge_id}"
        else:
            inputs[input_id] = f"Lab {input_id}"
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    capability_source = _capability_flow_snapshot(cartridge_id)
    _atomic_json(
        _safe_evidence_path(capability_test_run_dir, run_id),
        {
            "schema": "cartridgeflow.capability_test_source.v1",
            "run_id": run_id,
            "flow_id": cartridge_id,
            "source_digest": capability_source["source_digest"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    run = runner.create_queued_run(
        cartridge_id,
        inputs,
        run_id=run_id,
        probe_range=probe_range,
        test_mode=test_mode,
        compatibility=compatibility,
    )

    def _run_test():
        try:
            runner.create_run(cartridge_id, inputs, probe_range=probe_range, run_id=run_id, test_mode=test_mode)
        except CompatibilityBlockedError as exc:
            envelope = build_runtime_error(
                "FLOW_CONTRACT_INVALID",
                run_id=run_id,
                source="runtime.async.compatibility",
                cause_chain=[{"type": exc.__class__.__name__, "message": str(exc)}],
            )
            runner.fail_queued_run(run_id, cartridge_id, envelope)
        except RuntimeFailure as exc:
            runner.fail_queued_run(run_id, cartridge_id, exc.envelope)
        except Exception as exc:
            envelope = build_runtime_error(
                exception=exc,
                run_id=run_id,
                source="runtime.async.test_run",
            )
            write_diagnostic(runner.runs_dir / run_id, envelope, exc, {"cartridge_id": cartridge_id})
            runner.fail_queued_run(run_id, cartridge_id, envelope)

    threading.Thread(target=_run_test, daemon=True).start()
    return {"run": run, "events": []}


@app.post("/api/cartridge-runs")
def create_cartridge_run(payload: CartridgeRunCreate):
    try:
        return runner.create_run(payload.cartridge_id, payload.inputs, test_mode=payload.test_mode)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CompatibilityBlockedError as e:
        raise HTTPException(status_code=400, detail=_compatibility_blocked_detail(e.report))
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/cartridge-runs")
def list_cartridge_runs():
    return {"items": runner.list_runs()}


@app.get("/api/cartridge-runs/{run_id}")
def get_cartridge_run(run_id: str):
    try:
        return runner.get_run(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/cartridge-runs/{run_id}")
def delete_cartridge_run(run_id: str):
    try:
        return runner.delete_run(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/cartridge-runs/{run_id}/diagnostics")
def get_cartridge_run_diagnostics(run_id: str):
    """Return one stable, redacted evidence bundle for humans and AI tools."""
    try:
        run = runner.get_run(run_id)
        events = runner.get_events(run_id)
        checkpoints = runner.list_checkpoints(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    redacted_run = _redact_diagnostic_value(run)
    redacted_events = _redact_diagnostic_value(events)
    redacted_checkpoints = _redact_diagnostic_value(checkpoints)
    error = redacted_run.get("error") if isinstance(redacted_run, dict) else None
    artifacts = []
    if isinstance(redacted_run, dict):
        artifacts = [*(redacted_run.get("artifacts") or []), *((redacted_run.get("delivery") or {}).get("artifacts") or [])]
    return {
        "schema": "cartridgeflow.diagnostic_bundle.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
        "cartridge_id": run.get("cartridge_id"),
        "summary": {
            "status": run.get("status"),
            "current_state": run.get("current_state"),
            "error_code": error.get("code") if isinstance(error, dict) else None,
            "error_category": error.get("category") if isinstance(error, dict) else None,
            "event_count": len(redacted_events),
            "checkpoint_count": len(redacted_checkpoints),
            "artifact_count": len(artifacts),
        },
        "run": redacted_run,
        "events": redacted_events,
        "checkpoints": redacted_checkpoints,
    }


@app.post("/api/cartridge-runs/{run_id}/control")
def control_cartridge_run(run_id: str, payload: CartridgeRunControl):
    try:
        result = runner.control_with_options(
            run_id,
            payload.action,
            target_node=payload.target_node,
            confirm_side_effect=payload.confirm_side_effect,
            feedback=payload.feedback,
        )
        if payload.action in {"cancel", "restart", "rollback"}:
            from core.extensions.sandbox_service import sandbox_renderer_manager
            sandbox_renderer_manager.revoke_run(run_id)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/cartridge-runs/{run_id}/checkpoints")
def get_cartridge_run_checkpoints(run_id: str):
    try:
        return {"run_id": run_id, "items": runner.list_checkpoints(run_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/cartridge-runs/{run_id}/pending-interaction/answer")
def answer_pending_interaction(run_id: str, payload: PendingInteractionAnswerPayload):
    try:
        current = runner.get_run(run_id)
        interaction_id = ((current.get("pending_interaction") or {}).get("interaction_id") or "")
        values = payload.values if payload.values else payload.answer
        run = runner.answer_pending_interaction(
            run_id,
            values,
            action_id=payload.action_id,
            input_revision=payload.input_revision,
            idempotency_key=payload.idempotency_key,
            draft_hash=payload.draft_hash,
        )
        from core.extensions.sandbox_service import sandbox_renderer_manager
        if interaction_id:
            sandbox_renderer_manager.revoke(f"{run_id}:{interaction_id}")
        return {"run": run, "events": runner.get_events(run_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _sandbox_origin(request: Request) -> str:
    from urllib.parse import urlparse
    origin = str(request.headers.get("origin") or "").strip().rstrip("/")
    if not origin:
        referer = urlparse(str(request.headers.get("referer") or ""))
        if referer.scheme and referer.netloc:
            origin = f"{referer.scheme}://{referer.netloc}"
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Sandbox renderer requires a trusted local Base UI origin")
    return origin


def _write_sandbox_audit(event: dict) -> None:
    from core.data_paths import REPORTS_DATA_ROOT
    target = ROOT / REPORTS_DATA_ROOT / "security" / "sandbox-audit.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), **event}, ensure_ascii=False) + "\n")


@app.get("/api/cartridge-runs/{run_id}/interaction/{interaction_id}/sandbox")
def get_interaction_sandbox(run_id: str, interaction_id: str, request: Request):
    from core.extensions.sandbox_service import SandboxRendererError, sandbox_renderer_manager
    try:
        run = runner.get_run(run_id)
        pending = run.get("pending_interaction") if isinstance(run.get("pending_interaction"), dict) else {}
        presentation = pending.get("presentation") if isinstance(pending.get("presentation"), dict) else {}
        if pending.get("interaction_id") != interaction_id or presentation.get("component_runtime") != "sandboxed":
            raise HTTPException(status_code=409, detail="Run is not waiting for this sandboxed interaction")
        supported = {"run.read_declared", "artifact.read", "draft.read", "draft.write", "interaction.propose", "notification.request"}
        requested = set(presentation.get("host_capabilities") or [])
        unsupported = sorted(requested - supported)
        if unsupported:
            raise HTTPException(status_code=400, detail=f"Unsupported sandbox host capabilities: {', '.join(unsupported)}")
        cartridge = registry.get_cartridge(run["cartridge_id"])
        channel_id = f"channel_{uuid.uuid4().hex}"
        nonce = uuid.uuid4().hex + uuid.uuid4().hex
        scope_key = f"{run_id}:{interaction_id}"
        renderer = sandbox_renderer_manager.launch(
            cartridge["package_path"],
            cartridge["manifest"],
            str(presentation.get("frontend_ref") or ""),
            scope_key,
            _sandbox_origin(request),
        )
        presentation["host_channel"] = {
            "channel_id": channel_id,
            "nonce": nonce,
            "status": "issued",
            "messages": 0,
            "max_messages": 120,
            "max_message_bytes": 65536,
        }
        runner._write_json(runner.runs_dir / run_id / "run.json", run)
        _write_sandbox_audit({"event": "renderer_started", "run_id": run_id, "interaction_id": interaction_id, "component_id": presentation.get("component_id"), "policy": renderer["policy"]})
        return {
            "schema": "cartridgeflow.interaction_sandbox_session.v1",
            "run_id": run_id,
            "cartridge_id": run["cartridge_id"],
            "node_id": pending.get("node_id"),
            "component_id": presentation.get("component_id"),
            "interaction_id": interaction_id,
            "channel_id": channel_id,
            "nonce": nonce,
            "url": renderer["url"],
            "origin": renderer["origin"],
            "host_capabilities": sorted(requested),
            "input_revision": (pending.get("input_snapshot") or {}).get("input_revision"),
            "input": (pending.get("input_snapshot") or {}).get("bindings") or {},
            "policy": renderer["policy"],
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SandboxRendererError as exc:
        _write_sandbox_audit({"event": "renderer_failed", "run_id": run_id, "interaction_id": interaction_id, "message": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/cartridge-runs/{run_id}/interaction/{interaction_id}/sandbox")
def delete_interaction_sandbox(run_id: str, interaction_id: str):
    from core.extensions.sandbox_service import sandbox_renderer_manager
    sandbox_renderer_manager.revoke(f"{run_id}:{interaction_id}")
    _write_sandbox_audit({"event": "renderer_revoked", "run_id": run_id, "interaction_id": interaction_id})
    return {"ok": True}


@app.post("/api/cartridge-runs/{run_id}/interaction/{interaction_id}/host-request")
def handle_interaction_host_request(run_id: str, interaction_id: str, payload: SandboxHostRequestPayload):
    import hashlib as _hashlib
    try:
        raw_size = len(json.dumps(payload.model_dump(by_alias=True), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if raw_size > 65536:
            raise HTTPException(status_code=413, detail="Sandbox host message exceeds 64 KiB")
        run = runner.get_run(run_id)
        pending = run.get("pending_interaction") if isinstance(run.get("pending_interaction"), dict) else {}
        presentation = pending.get("presentation") if isinstance(pending.get("presentation"), dict) else {}
        channel = presentation.get("host_channel") if isinstance(presentation.get("host_channel"), dict) else {}
        expected = {
            "run_id": run_id,
            "cartridge_id": run.get("cartridge_id"),
            "node_id": pending.get("node_id"),
            "component_id": presentation.get("component_id"),
            "interaction_id": interaction_id,
            "channel_id": channel.get("channel_id"),
            "nonce": channel.get("nonce"),
        }
        actual = {key: getattr(payload, key) for key in expected}
        if payload.schema_ != "cartridgeflow.interaction_component_message.v1" or actual != expected:
            raise HTTPException(status_code=403, detail="Sandbox host message scope is invalid")
        if int(channel.get("messages") or 0) >= int(channel.get("max_messages") or 120):
            raise HTTPException(status_code=429, detail="Sandbox host message limit exceeded")
        capability = payload.type
        granted = set(presentation.get("host_capabilities") or [])
        if capability not in granted:
            raise HTTPException(status_code=403, detail=f"Sandbox host capability was not granted: {capability}")
        response_payload: dict = {}
        if capability == "draft.write":
            value = payload.payload.get("value")
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            if len(encoded) > 128 * 1024:
                raise HTTPException(status_code=413, detail="Sandbox draft exceeds 128 KiB")
            draft = {
                "value": value,
                "revision": int((pending.get("draft") or {}).get("revision") or 0) + 1,
                "sha256": _hashlib.sha256(encoded).hexdigest(),
            }
            pending["draft"] = draft
            response_payload = {"revision": draft["revision"], "draft_hash": draft["sha256"]}
        elif capability == "draft.read":
            response_payload = pending.get("draft") or {"value": None, "revision": 0, "sha256": None}
        elif capability == "interaction.propose":
            action_id = str(payload.payload.get("action_id") or "")
            if action_id not in {str(item) for item in pending.get("allowed_actions") or []}:
                raise HTTPException(status_code=400, detail="Proposed action is not in the interaction allowlist")
            response_payload = {"action_id": action_id, "accepted": True, "requires_host_click": True}
        elif capability == "run.read_declared":
            response_payload = {"input": (pending.get("input_snapshot") or {}).get("bindings") or {}, "input_revision": (pending.get("input_snapshot") or {}).get("input_revision")}
        elif capability == "artifact.read":
            response_payload = {"artifacts": [{key: item.get(key) for key in ("name", "type", "mime_type", "url")} for item in run.get("artifacts") or [] if isinstance(item, dict)]}
        elif capability == "notification.request":
            response_payload = {"accepted": True}
        else:
            raise HTTPException(status_code=400, detail="Sandbox host capability is not implemented")
        channel["messages"] = int(channel.get("messages") or 0) + 1
        channel["status"] = "ready"
        runner._write_json(runner.runs_dir / run_id / "run.json", run)
        _write_sandbox_audit({"event": "host_capability", "run_id": run_id, "interaction_id": interaction_id, "component_id": presentation.get("component_id"), "capability": capability, "request_id": payload.request_id, "ok": True})
        return {
            "schema": "cartridgeflow.interaction_host_message.v1",
            "type": f"{capability}.result",
            "request_id": payload.request_id,
            "channel_id": payload.channel_id,
            "run_id": run_id,
            "cartridge_id": payload.cartridge_id,
            "node_id": payload.node_id,
            "component_id": payload.component_id,
            "interaction_id": interaction_id,
            "ok": True,
            "payload": response_payload,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/cartridge-runs/{run_id}/events")
def get_cartridge_run_events(run_id: str):
    return {"items": runner.get_events(run_id)}


@app.get("/api/cartridge-runs/{run_id}/artifacts")
def get_cartridge_run_artifacts(run_id: str):
    run = runner.get_run(run_id)
    return {"items": run.get("artifacts", [])}


@app.post("/api/cartridge-runs/{run_id}/artifacts/open-directory")
def open_cartridge_run_artifacts_directory(run_id: str):
    normalized_id = str(run_id or "").strip()
    if not normalized_id or Path(normalized_id).name != normalized_id:
        raise HTTPException(status_code=400, detail="Invalid run id")
    try:
        runner.get_run(normalized_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    runs_root = runner.runs_dir.resolve()
    run_directory = (runs_root / normalized_id).resolve()
    if run_directory.parent != runs_root:
        raise HTTPException(status_code=403, detail="Run directory is outside the runtime workspace")
    artifacts_directory = (run_directory / "artifacts").resolve()
    if artifacts_directory.parent != run_directory:
        raise HTTPException(status_code=403, detail="Artifact directory is outside the run workspace")
    if not artifacts_directory.is_dir():
        raise HTTPException(status_code=404, detail="Artifact directory not found")
    try:
        _open_directory(artifacts_directory)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to open artifact directory: {exc}")
    return {
        "ok": True,
        "run_id": normalized_id,
        "path": f".data/runtime/runs/{normalized_id}/artifacts",
    }


@app.get("/api/cartridge-runs/{run_id}/artifacts/{artifact_path:path}/preview")
def preview_cartridge_run_artifact(run_id: str, artifact_path: str):
    try:
        run = runner.get_run(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    artifact = None
    for item in run.get("artifacts", []):
        if isinstance(item, dict):
            candidates = [
                item.get("id"),
                item.get("name"),
                item.get("path"),
                item.get("file"),
                item.get("filename"),
                item.get("preview_path"),
            ]
            if artifact_path in {str(value) for value in candidates if value}:
                artifact = item
                break
        elif str(item) == artifact_path:
            artifact = {"path": str(item)}
            break

    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    raw_path = artifact.get("preview_path") or artifact.get("path") or artifact.get("file") or artifact.get("filename")
    if not raw_path:
        raise HTTPException(status_code=404, detail="Artifact file not found")

    try:
        artifact_file = artifact_manager.resolve_artifact_record_path(run, artifact)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    except (FileNotFoundError, OSError) as e:
        raise HTTPException(status_code=404, detail=str(e))

    response = FileResponse(artifact_file)
    response.headers["Content-Security-Policy"] = (
        "sandbox; default-src 'none'; script-src 'none'; connect-src 'none'; "
        "img-src 'self' data: blob:; style-src 'unsafe-inline'; font-src 'self' data:; "
        "object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/cartridge-runs/{run_id}/delivery")
def get_cartridge_run_delivery(run_id: str):
    try:
        return runner.get_delivery(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/cartridge-runs/{run_id}/permissions")
def get_cartridge_run_permissions(run_id: str):
    try:
        run = runner.get_run(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    perm_state = run.get("permissions", {})
    risk = runner.permission_manager.get_risk_summary(perm_state)
    return {"run_id": run_id, "permissions": perm_state, "risk": risk}


@app.get("/api/cartridge-runs/{run_id}/environment")
def get_cartridge_run_environment(run_id: str):
    try:
        run = runner.get_run(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"run_id": run_id, "environment": run.get("environment", {})}


@app.get("/api/cartridge-runs/{run_id}/dependencies")
def get_cartridge_run_dependencies(run_id: str):
    try:
        run = runner.get_run(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"run_id": run_id, "dependencies": run.get("dependencies", {})}


@app.post("/api/cartridge-runs/{run_id}/dependencies/{dependency_id}/confirm")
def confirm_dependency(run_id: str, dependency_id: str):
    try:
        run = runner.get_run(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        runner.dependency_resolver.confirm(run, dependency_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    run["updated_at"] = datetime.now().isoformat(timespec="seconds")
    runner._write_json(runner.runs_dir / run_id / "run.json", run)
    runner._append_event(run_id, run["cartridge_id"], "dependency_confirmed", run["current_state"], f"依赖已确认: {dependency_id}", {"dependency_id": dependency_id})
    return {"run_id": run_id, "dependency_id": dependency_id, "status": "confirmed"}


@app.post("/api/cartridge-runs/{run_id}/dependencies/{dependency_id}/skip")
def skip_dependency(run_id: str, dependency_id: str):
    try:
        run = runner.get_run(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        runner.dependency_resolver.skip(run, dependency_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    run["updated_at"] = datetime.now().isoformat(timespec="seconds")
    runner._write_json(runner.runs_dir / run_id / "run.json", run)
    runner._append_event(run_id, run["cartridge_id"], "dependency_skipped", run["current_state"], f"依赖已跳过: {dependency_id}", {"dependency_id": dependency_id})
    return {"run_id": run_id, "dependency_id": dependency_id, "status": "skipped"}


class PermissionGrant(BaseModel):
    auth_mode: str | None = None


@app.post("/api/cartridge-runs/{run_id}/permissions/{permission_id}/grant")
def grant_permission(run_id: str, permission_id: str, payload: PermissionGrant = PermissionGrant()):
    try:
        run = runner.get_run(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        runner.permission_manager.grant(run, permission_id, payload.auth_mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    run["updated_at"] = datetime.now().isoformat(timespec="seconds")
    runner._write_json(runner.runs_dir / run_id / "run.json", run)
    runner._append_event(run_id, run["cartridge_id"], "permission_granted", run["current_state"], f"权限已授权: {permission_id}", {"permission_id": permission_id})
    return {"run_id": run_id, "permission_id": permission_id, "status": "granted"}


@app.post("/api/cartridge-runs/{run_id}/permissions/{permission_id}/deny")
def deny_permission(run_id: str, permission_id: str):
    try:
        run = runner.get_run(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        runner.permission_manager.deny(run, permission_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    run["updated_at"] = datetime.now().isoformat(timespec="seconds")
    runner._write_json(runner.runs_dir / run_id / "run.json", run)
    runner._append_event(run_id, run["cartridge_id"], "permission_denied", run["current_state"], f"权限已拒绝: {permission_id}", {"permission_id": permission_id})
    return {"run_id": run_id, "permission_id": permission_id, "status": "denied"}


@app.get("/artifacts/{run_id}/{filename}")
def serve_artifact_file(run_id: str, filename: str):
    try:
        run = runner.get_run(run_id)
        path = artifact_manager.resolve_artifact_path(run, filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    mime_type = None
    for artifact in run.get("artifacts", []):
        if artifact.get("name") == filename:
            mime_type = artifact.get("mime_type")
            break
    response = FileResponse(path, media_type=mime_type)
    response.headers["Content-Security-Policy"] = (
        "sandbox; default-src 'none'; script-src 'none'; connect-src 'none'; "
        "img-src 'self' data: blob:; style-src 'unsafe-inline'; font-src 'self' data:; "
        "object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/packages/{filename}")
def serve_package_file(filename: str):
    package_dir = (ROOT / PACKAGES_DIR).resolve()
    target = (package_dir / filename).resolve()
    try:
        if target != package_dir and package_dir not in target.parents:
            raise HTTPException(status_code=400, detail="Invalid package path")
    except OSError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Package not found")
    return FileResponse(target, media_type="application/zip", filename=target.name)


static_dir = ROOT / "src" / "intent-studio" / "dist"
capability_static_dir = ROOT / "src" / "capability-workshop" / "dist"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


def _frontend_index() -> Path | None:
    index = static_dir / "index.html"
    return index if index.is_file() else None


def _spa_file(static_root: Path, relative_path: str) -> FileResponse | None:
    """Serve a static asset or the app shell without allowing path traversal."""
    index = static_root / "index.html"
    if not index.is_file():
        return None
    candidate = (static_root / relative_path).resolve()
    try:
        candidate.relative_to(static_root.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid frontend asset path")
    if relative_path and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(index, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/studio")
@app.get("/studio/{full_path:path}")
@app.get("/creator")
@app.get("/creator/{full_path:path}")
def serve_intent_studio(full_path: str = ""):
    response = _spa_file(static_dir, full_path)
    if response is None:
        raise HTTPException(status_code=404, detail="Intent Studio has not been built")
    return response


@app.get("/projects/{project_id}/studio")
@app.get("/projects/{project_id}/creator")
def serve_intent_project(project_id: str):
    return serve_intent_studio()


@app.get("/capabilities")
@app.get("/capabilities/{full_path:path}")
@app.get("/developer")
@app.get("/developer/{full_path:path}")
def serve_capability_workshop(full_path: str = ""):
    response = _spa_file(capability_static_dir, full_path)
    if response is None:
        raise HTTPException(status_code=404, detail="Capability Workshop has not been built")
    return response


@app.get("/projects/{project_id}/capabilities")
@app.get("/projects/{project_id}/developer")
def serve_capability_project(project_id: str):
    return serve_capability_workshop()


@app.get("/")
def service_root():
    index = _frontend_index()
    if index is not None:
        return FileResponse(index, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {
        "service": "CartridgeFlow API",
        "docs": "/docs",
        "health": "/api/health",
        "intent_studio": "Build src/intent-studio or run the Intent Studio development server.",
    }


@app.get("/{full_path:path}")
def serve_console(full_path: str):
    index = _frontend_index()
    if index is None:
        raise HTTPException(status_code=404, detail="No bundled frontend is available at this path")
    return FileResponse(index, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
