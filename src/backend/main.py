import os
import sys
import threading
import uuid
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
from pydantic import BaseModel, Field

from core.cartridge import CartridgeRegistry, CartridgeRunner
from core.data_paths import (
    CARTRIDGE_DATA_DIR,
    CONFORMANCE_REPORT,
    ERROR_REPORTS_DIR,
    IMPORTS_DIR,
    INSTALLED_CARTRIDGES_DIR,
    LOGS_DIR,
    PACKAGES_DIR,
    UPLOADS_DIR,
    ensure_data_layout,
)
from core.extensions import PortableDlcValidationError, load_portable_dlc_descriptor
from core.cartridge.artifacts import ArtifactManager
from core.lab import DevFlowManager, FlowGraphBuilder, FlowSteward
from core.lab.todo import parse_todo_markdown
from core.llm.config_manager import ensure_llm_config
from core.runtime.errors import RuntimeFailure, build_runtime_error, write_diagnostic
from core.studio.environment import ensure_local_credentials
from core.protocol import (
    BaseManifestError,
    CompatibilityBlockedError,
    apply_protocol_certification_label,
    build_compatibility_report,
    build_protocol_certification_report,
    load_base_implementation,
)

ensure_data_layout(ROOT)
PRODUCT_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip().removeprefix("CartridgeFlow-")


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(title="CartridgeFlow", version=PRODUCT_VERSION, default_response_class=UTF8JSONResponse)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _request_error_context(request: Request) -> dict:
    return {
        "run_id": str(request.path_params.get("run_id") or ""),
        "source": f"http.{request.method.lower()}.{request.url.path}",
    }


def _http_error_code(status_code: int) -> str:
    if status_code == 404:
        return "RESOURCE_NOT_FOUND"
    if status_code in {401, 403}:
        return "PERMISSION_DENIED"
    if status_code in {400, 409, 422}:
        return "REQUEST_INVALID"
    return "INTERNAL_UNEXPECTED"


@app.exception_handler(RuntimeFailure)
async def runtime_failure_handler(request: Request, exc: RuntimeFailure):
    return UTF8JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.envelope["message"], "error_envelope": exc.envelope},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    context = _request_error_context(request)
    envelope = build_runtime_error(
        "REQUEST_INVALID",
        run_id=context["run_id"],
        source=context["source"],
        cause_chain=[{"type": "RequestValidationError", "message": str(exc)}],
    )
    return UTF8JSONResponse(status_code=422, content={"detail": exc.errors(), "error_envelope": envelope})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    context = _request_error_context(request)
    envelope = build_runtime_error(
        _http_error_code(exc.status_code),
        run_id=context["run_id"],
        source=context["source"],
        cause_chain=[{"type": "HTTPException", "message": str(exc.detail)}],
        context={"status_code": exc.status_code},
    )
    return UTF8JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "error_envelope": envelope})


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
    return response

registry = CartridgeRegistry(ROOT)
runner = CartridgeRunner(ROOT, registry)
artifact_manager = ArtifactManager(ROOT)
flow_graph_builder = FlowGraphBuilder()
dev_flow_manager = DevFlowManager(ROOT)
flow_steward = FlowSteward()
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


class CartridgeRunCreate(BaseModel):
    cartridge_id: str
    inputs: dict = Field(default_factory=dict)
    test_mode: dict | None = None


class CartridgeRunControl(BaseModel):
    action: str
    target_node: str | None = None
    confirm_side_effect: bool = False
    feedback: dict = Field(default_factory=dict)


class PendingInteractionAnswerPayload(BaseModel):
    values: dict = Field(default_factory=dict)
    answer: str | None = None


class DevFlowCreate(BaseModel):
    flow_id: str
    name: str
    description: str = ""


class CartridgeCloneToDevPayload(BaseModel):
    new_id: str
    name: str = ""
    description: str = ""


class DevFlowFileSave(BaseModel):
    content: str


class DevFlowFilesPayload(BaseModel):
    files: dict = Field(default_factory=dict)


class FlowStewardSuggestPayload(BaseModel):
    intent: str
    files: dict = Field(default_factory=dict)
    selected_node: dict | None = None
    use_llm: bool = False


class FlowStewardApplyPayload(BaseModel):
    files: dict = Field(default_factory=dict)
    patches: list[dict] = Field(default_factory=list)
    selected_node: dict | None = None


class FlowAssistantPayload(BaseModel):
    message: str
    graph: dict = Field(default_factory=dict)
    files: dict = Field(default_factory=dict)


class LLMProviderPayload(BaseModel):
    id: str = ""
    name: str = ""
    api_type: str = "openai"
    base_url: str = ""
    api_key: str = ""
    default_model: str = ""
    wire_api: str = "chat_completions"
    enabled: bool = True
    timeout: int = 120


class LLMAssignmentsPayload(BaseModel):
    version: int = 1
    defaults: dict = Field(default_factory=dict)
    cartridges: dict = Field(default_factory=dict)
    nodes: dict = Field(default_factory=dict)


class LLMTestPayload(BaseModel):
    provider_id: str
    model: str = ""
    prompt: str = "OK"
    vision: bool = False


class LLMImportTextPayload(BaseModel):
    content: str


class LLMCodexImportPayload(BaseModel):
    config_toml: str
    auth_json: dict = Field(default_factory=dict)


class LLMSimpleProviderPayload(BaseModel):
    provider: str
    api_key: str
    base_url: str = ""
    model: str = ""


class StudioResourcesPayload(BaseModel):
    version: int = 1
    tools: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    bindings: dict = Field(default_factory=dict)


class StudioCredentialPayload(BaseModel):
    key: str = ""
    label: str = ""
    value: str = ""
    secret: bool = True


class NodeDeletePayload(BaseModel):
    files: dict = Field(default_factory=dict)


class NodeUpdatePayload(BaseModel):
    files: dict = Field(default_factory=dict)
    title: str | None = None
    type: str | None = None
    action: str | None = None
    next: str | None = None
    kind: str | None = None
    executor: str | None = None
    effect: str | None = None
    display: dict | None = None
    input_kind: str | None = None
    source: str | None = None
    input_schema: dict | str | None = None
    output_contract: str | None = None
    decision_contract: dict | None = None
    decision_test_mode: str | None = None
    mock_decision_envelope: dict | None = None
    primary_output: str | None = None
    tool_binding: str | None = None
    allowed_tools: list[str] | None = None
    mcp_binding: dict | None = None
    failure_policy: str | None = None
    permission: str | None = None
    audit_log: bool | None = None
    endpoint: str | None = None
    timeout_ms: int | None = None
    agent: str | None = None
    tools: list[dict] | None = None
    params: dict | None = None
    model_role: str | None = None
    layout: dict | None = None


class NodeCreatePayload(BaseModel):
    files: dict = Field(default_factory=dict)
    template_id: str
    node_id: str
    title: str | None = None
    after_node_id: str | None = None
    insert_mode: str = "insert"


class LayoutSavePayload(BaseModel):
    files: dict = Field(default_factory=dict)
    layout: dict = Field(default_factory=dict)  # {node_id: {"x": int, "y": int}}


class EdgeSavePayload(BaseModel):
    files: dict = Field(default_factory=dict)
    edges: list[dict] = Field(default_factory=list)  # [{"from": "a", "to": "b"}]


class McpToolPayload(BaseModel):
    id: str = ""
    name: str = ""
    type: str = "builtin"
    server: str = "filesystem"
    tool: str = ""
    description: str = ""
    default_params: dict = Field(default_factory=dict)
    params_schema: dict = Field(default_factory=dict)
    required: bool = False
    contract: dict = Field(default_factory=dict)
    enabled: bool = True


class UploadTextPayload(BaseModel):
    filename: str = "upload.txt"
    content: str = ""


class CartridgeImportPayload(BaseModel):
    filename: str = "cartridge.cartridge.zip"
    content_base64: str = ""
    install_mode: str = "keep_existing"


class CartridgePackagePayload(BaseModel):
    package_mode: str = "dev"


@app.post("/api/uploads/file")
def upload_file(payload: UploadTextPayload):
    import re as _re
    import uuid as _uuid

    upload_dir = ROOT / UPLOADS_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    original_name = Path(payload.filename or "upload.txt").name
    safe_name = _re.sub(r"[^a-zA-Z0-9._-]+", "_", original_name).strip("._-") or "upload.txt"
    suffix = Path(safe_name).suffix or ".txt"
    stem = Path(safe_name).stem or "upload"
    target_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{_uuid.uuid4().hex[:8]}_{stem}{suffix}"
    target = upload_dir / target_name
    text = payload.content or ""
    target.write_text(text, encoding="utf-8")
    return {
        "ok": True,
        "filename": original_name,
        "path": target.relative_to(ROOT).as_posix(),
        "size": len(text),
    }


@app.get("/api/health")
def health():
    return {"ok": True, "app": "CartridgeFlow", "version": PRODUCT_VERSION}


@app.get("/api/base")
def get_base_implementation():
    try:
        base = load_base_implementation(ROOT)
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
        return {"ok": True, "base": base}
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
            "command": ".tools/runtimes/python/python.exe scripts/run_conformance.py",
        }
    return {"available": True, "report": report}


@app.get("/api/studio/todo")
def get_studio_todo():
    todo_path = ROOT / "docs" / "planning" / "TODO.md"
    template_path = ROOT / "docs" / "planning" / "TODO_TEMPLATE.md"
    source_path = todo_path if todo_path.is_file() else template_path
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="TODO.md and TODO_TEMPLATE.md are missing")
    result = parse_todo_markdown(source_path.read_text(encoding="utf-8"))
    return {
        **result,
        "source": source_path.name,
        "file_url": "/api/studio/todo/file",
        "template_url": "/api/studio/todo/template",
    }


@app.get("/api/studio/todo/file")
def get_studio_todo_file():
    todo_path = ROOT / "docs" / "planning" / "TODO.md"
    if not todo_path.is_file():
        raise HTTPException(status_code=404, detail="TODO.md is missing")
    return FileResponse(todo_path, media_type="text/markdown; charset=utf-8")


@app.get("/api/studio/todo/template")
def get_studio_todo_template():
    template_path = ROOT / "docs" / "planning" / "TODO_TEMPLATE.md"
    if not template_path.is_file():
        raise HTTPException(status_code=404, detail="TODO_TEMPLATE.md is missing")
    return FileResponse(template_path, media_type="text/markdown; charset=utf-8")


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

    return {"ok": True, "resources": save_resources(payload.dict())}


@app.get("/api/studio/environment")
def get_studio_environment():
    from core.studio.environment import environment_snapshot
    from core.studio.resources import load_resources

    return environment_snapshot(load_resources())


@app.post("/api/studio/environment/credentials")
def create_studio_credential(payload: StudioCredentialPayload):
    from core.studio.environment import upsert_credential

    try:
        item = upsert_credential(payload.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "credential": item}


@app.put("/api/studio/environment/credentials/{credential_key}")
def update_studio_credential(credential_key: str, payload: StudioCredentialPayload):
    from core.studio.environment import upsert_credential

    try:
        item = upsert_credential(payload.dict(), credential_key)
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
    item = upsert_provider(payload.dict())
    return {"ok": True, "provider": public_provider(item)}


@app.put("/api/llm/providers/{provider_id}")
def update_llm_provider(provider_id: str, payload: LLMProviderPayload):
    from core.llm.config_manager import public_provider, upsert_provider
    data = payload.dict()
    data["id"] = provider_id
    item = upsert_provider(data)
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
    item = activate_provider(provider_id)
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
    save_assignments(payload.dict())
    return {"ok": True, "assignments": get_assignments()}


@app.post("/api/llm/test")
async def test_llm_provider(payload: LLMTestPayload):
    from core.llm import ModelConfig, chat
    from core.llm.config_manager import get_provider, mark_provider_tested
    provider = get_provider(payload.provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    cfg = ModelConfig(
        provider_id=provider.get("id", ""),
        api_type=provider.get("api_type", "openai"),
        wire_api=provider.get("wire_api", "chat_completions"),
        model=payload.model or provider.get("default_model", ""),
        api_key=provider.get("api_key", ""),
        base_url=provider.get("base_url") or None,
        max_tokens=64,
        timeout=int(provider.get("timeout", 120) or 120),
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
            "content": response.get("content", "")[:500],
            "capability": "vision" if payload.vision else "text",
            "meta": response.get("meta", {}),
        }
    except Exception as e:
        from core.llm.errors import classify_llm_error
        error = classify_llm_error(e)
        return {"ok": False, "error": str(error)[:500], "status_code": error.status_code, "retryable": error.retryable}


@app.post("/api/llm/import/opencode")
def llm_import_opencode(payload: LLMImportTextPayload):
    from core.llm.importers import import_opencode, parse_json_text
    from core.llm.config_manager import public_provider, upsert_provider
    providers = [upsert_provider(p) for p in import_opencode(parse_json_text(payload.content))]
    return {"ok": True, "providers": [public_provider(p) for p in providers]}


@app.post("/api/llm/import/claude-code")
def llm_import_claude_code(payload: LLMImportTextPayload):
    from core.llm.importers import import_claude_code, parse_json_text
    from core.llm.config_manager import public_provider, upsert_provider
    providers = [upsert_provider(p) for p in import_claude_code(parse_json_text(payload.content))]
    return {"ok": True, "providers": [public_provider(p) for p in providers]}


@app.post("/api/llm/import/codex")
def llm_import_codex(payload: LLMCodexImportPayload):
    from core.llm.importers import import_codex
    from core.llm.config_manager import public_provider, upsert_provider
    providers = [upsert_provider(p) for p in import_codex(payload.config_toml, payload.auth_json)]
    return {"ok": True, "providers": [public_provider(p) for p in providers]}


@app.post("/api/llm/import/smart")
def llm_import_smart(payload: LLMImportTextPayload):
    from core.llm.importers import parse_json_text, smart_import
    from core.llm.config_manager import public_provider, save_assignments, upsert_provider
    providers = []
    try:
        data = parse_json_text(payload.content)
        if "providers" in data and "assignments" in data:
            providers = [upsert_provider(p) for p in data.get("providers", [])]
            save_assignments(data.get("assignments") or {})
            return {"ok": True, "providers": [public_provider(p) for p in providers], "assignments_imported": True}
    except Exception:
        pass
    providers = [upsert_provider(p) for p in smart_import(payload.content)]
    return {"ok": True, "providers": [public_provider(p) for p in providers], "assignments_imported": False}


@app.get("/api/llm/config/export")
def llm_export_config():
    from core.llm.config_manager import get_assignments, list_providers
    return {"version": 1, "providers": list_providers(), "assignments": get_assignments()}


@app.post("/api/llm/config/import")
def llm_import_config(payload: LLMImportTextPayload):
    from core.llm.importers import parse_json_text
    from core.llm.config_manager import public_provider, save_assignments, upsert_provider
    data = parse_json_text(payload.content)
    providers = [upsert_provider(p) for p in data.get("providers", [])]
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


def _compatibility_for_manifest(manifest: dict, root_flow: dict | None) -> dict:
    base = load_base_implementation(ROOT)
    return build_compatibility_report(base, manifest, root_flow or {}, ROOT)


def _compatibility_for_cartridge(cartridge: dict) -> dict:
    manifest = cartridge.get("manifest") or {}
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
    manifest = cartridge.get("manifest") or {}
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
    from core.llm.config_manager import get_assignments, list_providers
    from core.studio.environment import environment_snapshot
    from core.studio.hygiene import scan_package_hygiene
    from core.studio.release import resource_preflight
    from core.studio.resources import load_resources

    manifest = cartridge.get("manifest") or {}
    compatibility = _compatibility_for_cartridge(cartridge)
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

    providers = {item.get("id"): item for item in list_providers()}
    assignments = get_assignments()
    recipe = manifest.get("llm_recipe") if isinstance(manifest.get("llm_recipe"), dict) else {}
    roles = recipe.get("roles") if recipe.get("schema") == "cartridgeflow.llm_recipe.v1" else []
    model_items = []
    for role in roles if isinstance(roles, list) else []:
        if not isinstance(role, dict):
            continue
        role_id = str(role.get("id") or "").strip()
        if not role_id:
            continue
        binding = ((assignments.get("cartridges") or {}).get(cartridge.get("id") or "") or {}).get(role_id) or {}
        provider = providers.get(binding.get("provider_id"))
        status = "ok"
        message = f"已连接 {provider.get('name')}" if provider else "未绑定本机模型连接"
        if not provider:
            status = "blocked" if role.get("required", True) else "warning"
        elif not provider.get("base_url") or not provider.get("api_key"):
            missing = [name for name, value in (("URL", provider.get("base_url")), ("Key", provider.get("api_key"))) if not value]
            status = "blocked" if role.get("required", True) else "warning"
            message = f"本机连接缺少 {' / '.join(missing)}"
        elif role.get("api_type") and provider.get("api_type") != role.get("api_type"):
            status = "blocked" if role.get("required", True) else "warning"
            message = f"接口类型需要 {role.get('api_type')}"
        model_items.append({
            "id": role_id,
            "label": role.get("label") or role_id,
            "required": role.get("required", True),
            "status": status,
            "provider_id": binding.get("provider_id"),
            "message": message,
        })
    model_statuses = {item.get("status") for item in model_items}
    model_report = {"status": "blocked" if "blocked" in model_statuses else "warning" if "warning" in model_statuses else "ok", "items": model_items}

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
        and resource_report.get("status") == "ok"
        and package_report.get("status") == "ok"
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
        "issues": issues,
        "dev_ready": bool(cartridge.get("package_path") and Path(cartridge.get("package_path")).is_dir() and package_report.get("status") == "ok"),
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

    try:
        archive_bytes = _base64.b64decode(payload.content_base64 or "", validate=True)
    except (_binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 cartridge content")
    if not archive_bytes:
        raise HTTPException(status_code=400, detail="Cartridge package is empty")

    tmp_root = ROOT / IMPORTS_DIR
    tmp_dir = tmp_root / f"import_{_uuid.uuid4().hex}"
    extract_dir = tmp_dir / "package"
    installed_root = ROOT / INSTALLED_CARTRIDGES_DIR
    extract_root_resolved = extract_dir.resolve()

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
                for member in members:
                    member_name = (member.filename or "").replace("\\", "/")
                    if not member_name or member_name.startswith("/") or ":" in member_name:
                        raise HTTPException(status_code=400, detail=f"Invalid zip path: {member.filename}")
                    target = (extract_dir / member_name).resolve()
                    if target != extract_root_resolved and extract_root_resolved not in target.parents:
                        raise HTTPException(status_code=400, detail=f"Unsafe zip path: {member.filename}")
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

        try:
            root_entry = manifest.get("root_flow", {}).get("entry", "root.flow.json")
            root_flow_path = (extract_dir / root_entry).resolve()
            if root_flow_path != extract_root_resolved and extract_root_resolved not in root_flow_path.parents:
                raise HTTPException(status_code=400, detail="root_flow entry points outside the cartridge package")
            registry.validator.validate_package(extract_dir, manifest)
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
        return {
            "ok": True,
            "cartridge": cartridge,
            "installed_path": str(target_dir),
            "replaced": replaced,
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
        cartridge = registry.get_cartridge(cartridge_id)
        return _certification_for_cartridge(cartridge)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/studio/release/{cartridge_id}/preflight")
def get_studio_release_preflight(cartridge_id: str):
    try:
        return _release_preflight_for_cartridge(registry.get_cartridge(cartridge_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except BaseManifestError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/cartridges/{cartridge_id}/package")
def package_cartridge(cartridge_id: str, payload: CartridgePackagePayload | None = None):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        compatibility = _compatibility_for_cartridge(cartridge)
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
    from core.studio.hygiene import scan_package_hygiene
    package_hygiene = scan_package_hygiene(package_path)
    if package_hygiene.get("status") != "ok":
        raise HTTPException(status_code=400, detail={
            "error": "package_hygiene_failed",
            "message": "Package contains local, secret, model, cache, log, or runtime artifacts.",
            "report": package_hygiene,
        })
    if package_mode == "production":
        release_preflight = _release_preflight_for_cartridge(cartridge)
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
        zf.writestr("package.local-bindings.json", _json.dumps(binding_descriptor, ensure_ascii=False, indent=2))
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
    response.headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' blob:;"
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
        "steward": {
            "status": "skeleton",
            "role": "Flow 管家",
            "message": "第一版只读取当前 Flow 上下文，后续接入 AI 后可根据开发者意图修改链路图。",
            "context_keys": ["manifest", "root_flow", "graph", "selected_node", "runs", "events", "permissions", "environment", "dependencies"],
        },
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
        tool = _normalize_mcp_tool(payload.dict())
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
                data = payload.dict()
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


@app.post("/api/lab/flows/{cartridge_id}/steward/suggest")
async def suggest_lab_flow_changes(cartridge_id: str, payload: FlowStewardSuggestPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        files = dev_flow_manager.read_files(cartridge_id)
        files.update(payload.files)
        if payload.use_llm:
            return await flow_steward.suggest_with_llm(payload.intent, files, payload.selected_node)
        return flow_steward.suggest(payload.intent, files, payload.selected_node)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/lab/flows/{cartridge_id}/steward/suggest-llm")
async def suggest_lab_flow_changes_llm(cartridge_id: str, payload: FlowStewardSuggestPayload):
    """显式的 LLM 建议端点，等价于 use_llm=True。"""
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        files = dev_flow_manager.read_files(cartridge_id)
        files.update(payload.files)
        return await flow_steward.suggest_with_llm(payload.intent, files, payload.selected_node)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/lab/flows/{cartridge_id}/assistant")
@app.post("/api/lab/flows/{cartridge_id}/assistant/")
async def flow_assistant_chat(cartridge_id: str, payload: FlowAssistantPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        files = dev_flow_manager.read_files(cartridge_id)
        files.update(payload.files)
        graph = payload.graph or flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
        from core.lab.flow_assistant_llm import build_intent_fallback, build_messages, parse_response
        fallback = build_intent_fallback(payload.message, graph, files)
        if fallback:
            return {"ok": True, "message": fallback, "meta": {"source": "intent_fallback"}}

        from core.llm import chat
        from core.llm.config_manager import resolve_model
        cfg = resolve_model("steward", cartridge_id=cartridge_id)

        response = await chat(
            cfg,
            build_messages(payload.message, graph, files),
            agent_name="flow_assistant",
            phase="flow_design",
        )
        message = parse_response(response.get("content", ""))
        if message.get("type") == "clarify":
            fallback = build_intent_fallback(payload.message, graph, files)
            if fallback:
                message = fallback
        return {"ok": True, "message": message, "meta": response.get("meta", {})}
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/lab/flows/{cartridge_id}/steward/apply")
def apply_lab_flow_steward_patches(cartridge_id: str, payload: FlowStewardApplyPayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
        files = dev_flow_manager.read_files(cartridge_id)
        files.update(payload.files)
        result = flow_steward.apply(files, payload.patches, payload.selected_node)
        validation = dev_flow_manager.validate_files(cartridge_id, result.get("files", {}))
        graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, result.get("files", {})))
        return {**result, "validation": validation, "graph": graph}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
        "welcome": {
            "type": "process",
            "kind": "ui",
            "executor": "deterministic",
            "effect": "writes_store",
            "display": {"suffix": "展示", "label": "处理节点-展示"},
            "title": "UI 展示节点",
            "action": "show_ui",
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
            "model_role": "runtime",
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
            "params": {"message": "请确认是否继续。", "node_category": "control"},
        },
        "runtime": {
            "type": "process",
            "kind": "transfer",
            "executor": "deterministic",
            "effect": "writes_store",
            "display": {"suffix": "传递", "label": "处理节点-传递"},
            "title": "运行处理",
            "action": "pass_result",
            "params": {"node_category": "transfer"},
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
    after_node_id = payload.after_node_id or root_flow.get("start")
    edges = root_flow.setdefault("edges", [])
    if after_node_id and after_node_id in states:
        source_layout = states[after_node_id].get("layout") or {}
        source_x = int(source_layout.get("x", 80))
        source_y = int(source_layout.get("y", 120))
        if payload.insert_mode == "branch":
            branch_count = sum(1 for edge in edges if (edge.get("from") or edge.get("source")) == after_node_id and (edge.get("scope") or "root") == "branch")
            direction = 1 if branch_count % 2 == 0 else -1
            lane = branch_count // 2 + 1
            new_state["layout"] = {"x": source_x + 300, "y": source_y + direction * lane * 150}
            edges.append({"from": after_node_id, "to": node_id, "scope": "branch", "label": payload.title or "新分支"})
        else:
            new_state.setdefault("layout", {"x": source_x + 300, "y": source_y})
            previous_next = states[after_node_id].get("next")
            new_state["next"] = previous_next
            states[after_node_id]["next"] = node_id
            edges[:] = [edge for edge in edges if not ((edge.get("from") or edge.get("source")) == after_node_id and (edge.get("scope") or "root") == "root")]
            edges.append({"from": after_node_id, "to": node_id, "scope": "root"})
            if previous_next:
                edges.append({"from": node_id, "to": previous_next, "scope": "root"})
    elif not root_flow.get("start"):
        root_flow["start"] = node_id
    states[node_id] = new_state
    files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
    dev_flow_manager.save_file(cartridge_id, "root_flow", files["root_flow"])
    validation = dev_flow_manager.validate_files(cartridge_id, files)
    graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
    return {"status": "node_created", "node_id": node_id, "files": files, "validation": validation, "graph": graph}


@app.delete("/api/lab/flows/{cartridge_id}/nodes/{node_id}")
def delete_lab_flow_node(cartridge_id: str, node_id: str, payload: NodeDeletePayload):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
        if not cartridge.get("editable"):
            raise HTTPException(status_code=403, detail="Only dev flows are editable")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    import json as _json
    files = dev_flow_manager.read_files(cartridge_id)
    files.update(payload.files)
    root_flow = _json.loads(files.get("root_flow") or "{}")
    states = root_flow.get("states") or {}
    if node_id not in states:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    state = states[node_id]
    if state.get("locked") or node_id == root_flow.get("start"):
        raise HTTPException(status_code=400, detail="Locked or start node cannot be deleted")

    deleted_next = state.get("next")
    original_edges = root_flow.get("edges") or []
    branch_edges = []
    for edge in original_edges:
        source = edge.get("from") or edge.get("source")
        target = edge.get("to") or edge.get("target")
        scope = edge.get("scope") or "root"
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

    cleaned_edges = []
    seen = set()
    for source_id, source_state in states.items():
        target_id = source_state.get("next")
        if target_id not in states:
            continue
        key = (source_id, target_id, "root")
        if key in seen:
            continue
        seen.add(key)
        cleaned_edges.append({"from": source_id, "to": target_id, "scope": "root"})
    for edge in branch_edges:
        key = (edge["from"], edge["to"], edge["scope"])
        if key in seen:
            continue
        seen.add(key)
        cleaned_edges.append(edge)
    root_flow["edges"] = cleaned_edges

    files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
    dev_flow_manager.save_file(cartridge_id, "root_flow", files["root_flow"])
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
    updates = {
        "title": payload.title,
        "type": payload.type,
        "action": payload.action,
        "next": payload.next,
        "kind": payload.kind,
        "executor": payload.executor,
        "effect": payload.effect,
        "display": payload.display,
        "input_kind": payload.input_kind,
        "source": payload.source,
        "input_schema": payload.input_schema,
        "output_contract": payload.output_contract,
        "decision_contract": payload.decision_contract,
        "decision_test_mode": payload.decision_test_mode,
        "mock_decision_envelope": payload.mock_decision_envelope,
        "primary_output": payload.primary_output,
        "tool_binding": payload.tool_binding,
        "allowed_tools": payload.allowed_tools,
        "mcp_binding": payload.mcp_binding,
        "failure_policy": payload.failure_policy,
        "permission": payload.permission,
        "audit_log": payload.audit_log,
        "endpoint": payload.endpoint,
        "timeout_ms": payload.timeout_ms,
        "agent": payload.agent,
        "tools": payload.tools,
        "params": payload.params,
        "model_role": payload.model_role,
        "layout": payload.layout,
    }
    for key, value in updates.items():
        if value is not None:
            state[key] = value

    files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
    validation = dev_flow_manager.validate_files(cartridge_id, files)
    graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
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

    root_flow["edges"] = normalized_edges
    for state_id, state in states.items():
        if state_id in next_by_source:
            state["next"] = next_by_source[state_id]
        elif state.get("next") and state.get("next") in states:
            state.pop("next", None)

    files["root_flow"] = _json.dumps(root_flow, ensure_ascii=False, indent=2)
    dev_flow_manager.save_file(cartridge_id, "root_flow", files["root_flow"])
    validation = dev_flow_manager.validate_files(cartridge_id, files)
    graph = flow_graph_builder.build(dev_flow_manager.preview_graph(cartridge_id, files))
    return {"status": "edges_saved", "files": files, "validation": validation, "graph": graph}


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
    test_mode: dict | None = None


@app.post("/api/lab/flows/{cartridge_id}/test-run")
def create_lab_flow_test_run(cartridge_id: str, payload: LabTestRunCreate | None = None):
    try:
        cartridge = registry.get_cartridge(cartridge_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    probe_range = payload.probe_range if payload else None
    test_mode = payload.test_mode if payload else None
    if test_mode:
        try:
            runner._normalize_test_mode(test_mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if probe_range:
        try:
            runner.validate_probe_range(cartridge.get("root_flow") or {}, probe_range)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    try:
        compatibility = runner.build_cartridge_compatibility_report(cartridge_id)
    except BaseManifestError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not compatibility.get("ok"):
        raise HTTPException(status_code=400, detail={
            "error": "compatibility_blocked",
            "message": "Cartridge is not compatible with current base.",
            "report": compatibility,
        })
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

    def _run_test():
        try:
            runner.create_run(cartridge_id, inputs, probe_range=probe_range, run_id=run_id, test_mode=test_mode)
        except CompatibilityBlockedError as exc:
            try:
                runner._append_event(run_id, cartridge_id, "run_blocked", "created", "测试运行被兼容性检查阻断", {"report": exc.report})
            except Exception:
                pass
        except Exception as exc:
            try:
                runner._append_event(run_id, cartridge_id, "run_failed", "created", f"测试运行失败：{exc}", {"error": str(exc)})
            except Exception:
                pass

    threading.Thread(target=_run_test, daemon=True).start()
    run = {
        "run_id": run_id,
        "cartridge_id": cartridge_id,
        "status": "running",
        "current_state": "queued",
        "inputs": inputs,
        "run_mode": "probe_range" if probe_range else "full_flow",
        "probe_range": probe_range,
        "test_mode": test_mode or {},
        "compatibility": {
            "ok": compatibility.get("ok"),
            "status": compatibility.get("status"),
            "legacy": compatibility.get("legacy"),
            "summary": compatibility.get("summary", {}),
            "findings": compatibility.get("findings", []),
        },
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    return {"run": run, "events": []}


@app.post("/api/cartridge-runs")
def create_cartridge_run(payload: CartridgeRunCreate):
    try:
        return runner.create_run(payload.cartridge_id, payload.inputs, test_mode=payload.test_mode)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CompatibilityBlockedError as e:
        raise HTTPException(status_code=400, detail={
            "error": "compatibility_blocked",
            "message": "Cartridge is not compatible with current base.",
            "report": e.report,
        })
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


@app.post("/api/cartridge-runs/{run_id}/control")
def control_cartridge_run(run_id: str, payload: CartridgeRunControl):
    try:
        return runner.control_with_options(
            run_id,
            payload.action,
            target_node=payload.target_node,
            confirm_side_effect=payload.confirm_side_effect,
            feedback=payload.feedback,
        )
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
        values = payload.values if payload.values else payload.answer
        run = runner.answer_pending_interaction(run_id, values)
        return {"run": run, "events": runner.get_events(run_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/cartridge-runs/{run_id}/events")
def get_cartridge_run_events(run_id: str):
    return {"items": runner.get_events(run_id)}


@app.get("/api/cartridge-runs/{run_id}/artifacts")
def get_cartridge_run_artifacts(run_id: str):
    run = runner.get_run(run_id)
    return {"items": run.get("artifacts", [])}


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

    artifact_file = Path(raw_path)
    if not artifact_file.is_absolute():
        artifact_file = ROOT / artifact_file

    try:
        artifact_file = artifact_file.resolve()
        root = ROOT.resolve()
        if artifact_file != root and root not in artifact_file.parents:
            raise HTTPException(status_code=400, detail="Invalid artifact path")
    except OSError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not artifact_file.is_file():
        raise HTTPException(status_code=404, detail="Artifact file not found")

    return FileResponse(artifact_file)


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
    return FileResponse(path, media_type=mime_type)


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


static_dir = ROOT / "src" / "frontend" / "dist"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/{full_path:path}")
def serve_console(full_path: str):
    return FileResponse(
        static_dir / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
