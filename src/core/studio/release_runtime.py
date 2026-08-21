"""Studio-owned release runtime: pack a CF-CRE, unpack it, then execute it.

The customer Desktop Runner is a separate product. Studio never locates, starts, or
calls that process. Packing uses the shared CF-CRE builder. Unpacking uses
extract_release_payload. Execution uses CartridgeFlow's in-process CF-FARP runner so
the same signed archive can run in a cloud-hosted Studio.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile

from core.data_paths import INSTALLED_CARTRIDGES_DIR, PACKAGES_DIR
from core.protocol.release_builder import ReleaseBuildError, build_release_archive, extract_release_payload, inspect_release_archive
from core.protocol.release_signing import ensure_development_signing_identity, trusted_public_keys
from core.studio.rss_daily_trial import TrialRunError, extractive_digest, fetch_feeds


PUBLISHER_ID = "studio"
CARTRIDGE_ID = "studio.daily-brief"
VERSION = "0.1.0"

RUNTIME_CONTRACT = {
    "protocol": "CF-FARP",
    "protocol_version": "1.0",
    "required_profiles": [
        "runtime_core",
        "flow_analysis",
        "tool_transparency",
        "execution_plan_runtime",
        "interaction_runtime",
    ],
    "recommended_profiles": [],
    "required_capabilities": [
        "manifest_load",
        "manifest_validate",
        "runtime_contract_parse",
        "compatibility_report",
        "root_flow_execution",
        "structured_io_contract",
        "explicit_input_binding",
        "typed_control_edges",
        "executable_topology_filter",
        "flow_analysis_report_v1",
        "analysis_report_freshness_guard",
        "basic_node_execution",
        "unified_process_node",
        "process_node_kind_parse",
        "process_executor_contract",
        "process_effect_contract",
        "runtime_error_envelope_v1",
        "runtime_state_machine",
        "delivery_primary_output_guard",
        "mcp_source_model_v1",
        "tool_source_provenance",
        "explicit_fallback_policy",
        "opaque_tool_visibility_guard",
        "mcp_source_digest_guard",
        "portable_dlc_descriptor_v3",
        "tool_resource_catalog_v2",
        "execution_plan_v1_authoring",
        "execution_plan_static_conformance",
        "execution_plan_compile",
        "execution_plan_token_ledger",
        "execution_plan_join_runtime",
        "execution_plan_wait_resume",
        "execution_plan_cancellation",
        "execution_plan_source_digest_guard",
    ],
    "optional_capabilities": [],
    "required_tools": [],
    "optional_tools": [],
}

MANIFEST = {
    "schema_version": "1.0",
    "id": CARTRIDGE_ID,
    "name": "中文 AI 日报",
    "version": VERSION,
    "kind": "runtime_cartridge",
    "category": "content",
    "description": "把已审核的公开来源整理成今天的中文 AI 日报。",
    "publisher": {"id": PUBLISHER_ID, "name": "Studio", "type": "local", "verified": False},
    "asset_registry": "assets/registry.json",
    "root_flow": {"entry": "root.flow.json", "mode": "lifecycle", "required": True},
    "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
    "runtime_contract": RUNTIME_CONTRACT,
    "delivery_readiness": {"level": "dev", "certification_target": "CF-FARP@1.0", "notes": "studio-owned runtime"},
    "runtime": {"type": "none", "adapter": "builtin:root_flow"},
    "environment": {"os": ["windows", "macos", "linux"], "requires": []},
    "permissions": [],
    "dependencies": [],
    "mcp_tools": [],
    "llm_recipe": {
        "schema": "cartridgeflow.llm_recipe.v1",
        "roles": [{
            "id": "writer",
            "label": "日报写作",
            "description": "根据公开条目生成日报",
            "capability": "text_generation",
            "api_type": "openai",
            "wire_api": "chat_completions",
            "model": "configured-locally",
            "required": True,
        }],
    },
    "resource_requirements": [],
    "inputs": [
        {
            "id": "sources",
            "label": "公开来源",
            "type": "string",
            "required": True,
            "schema": {"type": "string", "minLength": 1},
        },
        {
            "id": "topic",
            "label": "主题",
            "type": "string",
            "required": False,
            "schema": {"type": "string"},
            "default": "今日 AI 日报",
        },
    ],
    "outputs": [
        {
            "id": "brief",
            "label": "日报",
            "type": "string",
            "required": True,
            "schema": {"type": "string", "minLength": 1},
            "target": {"type": "store", "key": "brief"},
        }
    ],
    "artifacts": {"store_policy": "run_scoped", "visibility_default": "user", "allowed_types": []},
    "delivery": {"type": "summary", "primary_output": "brief", "show_artifacts": False},
}

FLOW = {
    "schema_version": "1.0",
    "id": "studio.daily-brief.root",
    "name": "中文 AI 日报",
    "mode": "lifecycle",
    "cartridge_id": CARTRIDGE_ID,
    "protocol": {"id": "CF-FARP", "version": "1.0"},
    "start": "start",
    "states": {
        "start": {"type": "control", "title": "开始", "display_name": "开始", "locked": True},
        "collect_sources": {
            "type": "process",
            "kind": "input",
            "executor": "user",
            "effect": "writes_store",
            "action": "collect_inputs",
            "title": "采集公开来源",
            "display_name": "采集公开来源",
            "source": "user_form",
            "input_kind": "initial",
            "params": {"fields": ["sources", "topic"], "output": "input_data"},
            "failure_policy": "fail_closed",
        },
        "generate_brief": {
            "type": "process",
            "kind": "process",
            "executor": "llm",
            "effect": "writes_store",
            "action": "llm_prompt",
            "title": "整理成新闻日报",
            "display_name": "整理成新闻日报",
            "params": {
                "description": "根据公开来源调用写作模型生成日报。",
                "system_prompt": (
                    "你是中文 AI 日报编辑。只根据用户提供的公开条目写一份今天的新闻日报。"
                    "不要编造条目里没有的事实、数字或引语。不要输出 JSON。"
                    "用 Markdown，结构必须是：标题、今日要点（5到8条）、分条新闻（标题/来源/为何重要/链接）、一句话结语。"
                ),
                "prompt": "请根据以下公开来源整理今天的中文 AI 日报。",
                "input": "input_data",
                "output": "llm_result",
                "model_role": "writer",
            },
            "failure_policy": "fail_closed",
        },
        "publish_brief": {
            "type": "process",
            "kind": "delivery",
            "executor": "deterministic",
            "effect": "writes_store",
            "action": "pass_result",
            "title": "交付日报",
            "display_name": "交付日报",
            "primary_output": "brief",
            "params": {"input": "llm_result", "output": "brief", "from": "llm_result", "to": "brief"},
            "failure_policy": "fail_closed",
        },
        "delivery": {"type": "system", "title": "生成交付快照", "display_name": "生成交付快照", "locked": True},
        "complete": {"type": "terminal", "title": "完成", "display_name": "完成", "locked": True},
        "failed": {"type": "terminal", "title": "流程失败", "display_name": "流程失败", "locked": True, "terminal_status": "failed"},
    },
    "execution_plan": {
        "schema": "cartridgeflow.execution_plan.v1",
        "entry": "start",
        "edges": [
            {"id": "start_collect", "kind": "sequence", "from": "start", "to": "collect_sources"},
            {"id": "collect_generate", "kind": "sequence", "from": "collect_sources", "to": "generate_brief"},
            {"id": "generate_publish", "kind": "sequence", "from": "generate_brief", "to": "publish_brief"},
            {"id": "publish_delivery", "kind": "sequence", "from": "publish_brief", "to": "delivery"},
            {"id": "delivery_complete", "kind": "sequence", "from": "delivery", "to": "complete"},
            {"id": "collect_failed", "kind": "failure", "from": "collect_sources", "to": "failed", "failure": {"id": "collect_f", "causes": ["cancelled", "exception", "resource", "retry_exhausted", "timeout", "validation"]}},
            {"id": "generate_failed", "kind": "failure", "from": "generate_brief", "to": "failed", "failure": {"id": "generate_f", "causes": ["cancelled", "exception", "resource", "retry_exhausted", "timeout", "validation"]}},
            {"id": "publish_failed", "kind": "failure", "from": "publish_brief", "to": "failed", "failure": {"id": "publish_f", "causes": ["cancelled", "exception", "resource", "retry_exhausted", "timeout", "validation"]}},
        ],
    },
}

EXPERIENCE = {
    "schema": "cartridgeflow.cartridge_experience.v1",
    "product": {"name": "中文 AI 日报", "category": "content"},
    "inputs": [
        {"id": "sources", "label": "公开来源", "type": "string", "required": True, "sensitive": False},
        {"id": "topic", "label": "主题", "type": "string", "required": False, "sensitive": False},
    ],
    "stages": [{"id": "prepare", "label": "准备来源"}, {"id": "deliver", "label": "交付日报"}],
}

DELIVERY_CONTRACT = {
    "schema": "cartridgeflow.delivery_contract.v1",
    "primary_artifacts": [{"id": "brief", "label": "日报", "mime_types": ["text/markdown"]}],
    "attachments": [],
    "revision": {"mode": "new_run"},
    "delivery_states": ["produced", "delivered", "failed"],
}


class ReleaseRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int = 409):
        self.code, self.status = code, status
        super().__init__(message)

    def as_dict(self) -> dict:
        return {"schema": "cartridgeflow.release_runtime_error.v1", "code": self.code, "message": str(self)}


def format_sources(items: list[dict], *, topic: str = "今日 AI 日报") -> str:
    date_label = datetime.now().strftime("%Y年%m月%d日")
    lines = [f"主题：{topic}", f"日期：{date_label}", "公开条目："]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.get('title') or ''}")
        if item.get("source"):
            lines.append(f"   来源：{item['source']}")
        if item.get("published"):
            lines.append(f"   时间：{item['published']}")
        if item.get("summary"):
            lines.append(f"   摘要：{item['summary']}")
        if item.get("link"):
            lines.append(f"   链接：{item['link']}")
    return "\n".join(lines).strip()


def write_daily_brief_source(path: str | Path) -> Path:
    source = Path(path)
    (source / "assets").mkdir(parents=True, exist_ok=True)
    (source / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (source / "root.flow.json").write_text(json.dumps(FLOW, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (source / "assets" / "registry.json").write_text(
        json.dumps({"schema": "cartridgeflow.asset_registry.v1", "assets": [], "components": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return source


def package_daily_brief(root: str | Path, packages_dir: str | Path | None = None) -> dict:
    project = Path(root).resolve()
    output_dir = Path(packages_dir).resolve() if packages_dir else (project / PACKAGES_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    identity = ensure_development_signing_identity(project, PUBLISHER_ID)
    filename = f"{CARTRIDGE_ID}-{VERSION}.cf-cre.zip"
    archive = output_dir / filename
    with tempfile.TemporaryDirectory(prefix="studio-daily-brief-", dir=output_dir) as source_dir:
        write_daily_brief_source(source_dir)
        pending = output_dir / f".{filename}.pending"
        try:
            built = build_release_archive(
                source_dir,
                pending,
                publisher_id=PUBLISHER_ID,
                experience=EXPERIENCE,
                delivery=DELIVERY_CONTRACT,
                signing_identity=identity,
            )
            keys = trusted_public_keys(project)
            inspection = inspect_release_archive(pending, trusted_keys=keys)
            if not inspection.get("activation_allowed"):
                raise ReleaseRuntimeError("RELEASE_SIGNATURE_UNTRUSTED", "The signed CF-CRE could not be independently verified.")
            pending.replace(archive)
        except ReleaseRuntimeError:
            pending.unlink(missing_ok=True)
            raise
        except (ReleaseBuildError, OSError, ValueError) as exc:
            pending.unlink(missing_ok=True)
            raise ReleaseRuntimeError("RELEASE_PACKAGE_FAILED", f"Studio could not build a signed CF-CRE: {exc}") from exc
    staging = output_dir / f"{CARTRIDGE_ID}-{VERSION}.unpacked"
    if staging.exists():
        import shutil

        shutil.rmtree(staging)
    extracted = extract_release_payload(archive, staging, trusted_keys=trusted_public_keys(project))
    return {
        "schema": "cartridgeflow.studio_release_package.v1",
        "status": "ready",
        "filename": filename,
        "url": f"/packages/{filename}",
        "archive": str(archive),
        "release_id": built["release_id"],
        "signature_verified": True,
        "key_id": identity.key_id,
        "publisher_id": PUBLISHER_ID,
        "cartridge": {"id": CARTRIDGE_ID, "name": MANIFEST["name"], "version": VERSION},
        "unpack": {
            "consumer": "python.extract_release_payload",
            "payload_path": extracted["payload_path"],
            "activation_allowed": True,
            "status": inspection["status"],
        },
    }


def install_daily_brief(root: str | Path, packages_dir: str | Path | None = None) -> dict:
    """Activate the verified payload into Studio's installed-cartridge shelf."""
    package = package_daily_brief(root, packages_dir)
    payload = Path(package["unpack"]["payload_path"])
    target = Path(root).resolve() / INSTALLED_CARTRIDGES_DIR / CARTRIDGE_ID
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(payload, target)
    package.pop("archive", None)
    return {
        **package,
        "status": "installed",
        "installed_path": str(target),
        "cartridge": {"id": CARTRIDGE_ID, "name": MANIFEST["name"], "version": VERSION},
    }


def bind_studio_runtime_models(cartridge_id: str, *, node_id: str = "generate_brief", role: str = "writer", registry=None) -> dict:
    """Bind Studio's local model connection to cartridge roles. Keys stay on the host."""
    from core.llm.config_manager import get_assignments, list_providers, save_assignments

    providers = [item for item in list_providers() if item.get("enabled") and str(item.get("api_key") or "").strip()]
    if not providers:
        raise ReleaseRuntimeError("STUDIO_RUNTIME_MODEL_UNBOUND", "Studio 还没有连接可用的模型。", status=409)
    provider = providers[0]
    assignments = get_assignments()
    defaults = assignments.get("defaults") if isinstance(assignments.get("defaults"), dict) else {}
    source = defaults.get("runtime") or defaults.get("mentor") or {}
    binding = {
        "provider_id": str(source.get("provider_id") or provider["id"]),
        "model": str(source.get("model") or provider.get("default_model") or ""),
    }
    roles = {role}
    node_roles: list[tuple[str, str]] = [(node_id, role)]
    if registry is not None:
        try:
            cartridge = registry.get_cartridge(cartridge_id)
        except FileNotFoundError:
            cartridge = None
        if cartridge:
            recipe = (cartridge.get("manifest") or {}).get("llm_recipe") if isinstance(cartridge.get("manifest"), dict) else {}
            for item in (recipe or {}).get("roles") or []:
                if isinstance(item, dict) and item.get("id"):
                    roles.add(str(item["id"]))
            states = (cartridge.get("root_flow") or {}).get("states") if isinstance(cartridge.get("root_flow"), dict) else {}
            for state_id, state in (states or {}).items():
                if not isinstance(state, dict):
                    continue
                params = state.get("params") if isinstance(state.get("params"), dict) else {}
                if state.get("action") == "llm_prompt" or state.get("executor") == "llm":
                    node_role = str(params.get("model_role") or state.get("model_role") or role)
                    roles.add(node_role)
                    node_roles.append((str(state_id), node_role))
    cartridges = assignments.setdefault("cartridges", {})
    if not isinstance(cartridges, dict):
        cartridges = {}
        assignments["cartridges"] = cartridges
    cartridge_bindings = cartridges.setdefault(cartridge_id, {})
    for role_id in roles:
        cartridge_bindings[role_id] = dict(binding)
    nodes = assignments.setdefault("nodes", {})
    if not isinstance(nodes, dict):
        nodes = {}
        assignments["nodes"] = nodes
    for state_id, node_role in node_roles:
        nodes.setdefault(f"{cartridge_id}/{state_id}", {})[node_role] = dict(binding)
    save_assignments(assignments)
    return {"provider_id": binding["provider_id"], "model": binding["model"], "roles": sorted(roles), "nodes": [item[0] for item in node_roles]}


def studio_runtime_status(registry) -> dict:
    try:
        cartridge = registry.get_cartridge(CARTRIDGE_ID)
    except FileNotFoundError:
        return {
            "schema": "cartridgeflow.studio_runtime_status.v1",
            "available": True,
            "runtime": "studio",
            "cartridge": None,
            "inputs": [],
        }
    manifest = cartridge.get("manifest") if isinstance(cartridge.get("manifest"), dict) else {}
    return {
        "schema": "cartridgeflow.studio_runtime_status.v1",
        "available": True,
        "runtime": "studio",
        "cartridge": {
            "id": str(cartridge.get("id") or CARTRIDGE_ID),
            "name": str(cartridge.get("name") or MANIFEST["name"]),
            "version": str(cartridge.get("version") or VERSION),
        },
        "inputs": manifest.get("inputs") or MANIFEST["inputs"],
        "package_url": f"/packages/{CARTRIDGE_ID}-{VERSION}.cf-cre.zip",
    }


def run_daily_brief_release(root: str | Path, runner, *, feed_url: str | None = None) -> dict:
    steps: list[dict] = []
    project = Path(root).resolve()

    def mark(step_id: str, label: str, status: str, detail: str = "") -> None:
        steps.append({"id": step_id, "label": label, "status": status, "detail": detail})

    try:
        package = install_daily_brief(project)
    except ReleaseRuntimeError as exc:
        mark("pack", "打包签发 CF-CRE", "error", str(exc))
        raise
    mark("pack", "打包签发 CF-CRE", "ok", package["filename"])
    mark("unpack", "按协议拆包验签", "ok", package["unpack"]["consumer"])
    mark("install", "装载到 Studio 运行核", "ok", package["cartridge"]["id"])
    try:
        bind_studio_runtime_models(CARTRIDGE_ID)
    except ReleaseRuntimeError as exc:
        mark("bind", "绑定本机模型", "error", str(exc))
        raise

    try:
        fetched = fetch_feeds(feed_url)
    except TrialRunError as exc:
        mark("fetch", "获取已审核来源的最新内容", "error", str(exc))
        raise ReleaseRuntimeError(exc.code, str(exc), status=exc.status) from exc
    items = fetched["items"]
    mark("fetch", "获取已审核来源的最新内容", "ok", f"{len(items)} 条")

    sources = format_sources(items)
    date_label = datetime.now().strftime("%Y年%m月%d日")
    digest = {
        "date": date_label,
        "headline": f"{date_label} 中文 AI 日报",
        "body": "",
        "used_model": False,
        "model": "",
        "item_count": len(items),
        "runtime": "studio",
    }
    run_result: dict | None = None
    try:
        run_result = runner.create_run(CARTRIDGE_ID, {"sources": sources, "topic": "今日 AI 日报"})
        body = _delivery_text(run_result.get("delivery") if isinstance(run_result, dict) else None)
        if isinstance(run_result, dict) and run_result.get("status") == "completed" and body:
            digest["body"] = body
            digest["used_model"] = True
            digest["model"] = "studio / writer"
            mark("run", "Studio 运行核执行并交付", "ok", str(run_result.get("run_id") or "completed"))
        else:
            error = run_result.get("error") if isinstance(run_result, dict) and isinstance(run_result.get("error"), dict) else {}
            detail = str(error.get("message") or (run_result or {}).get("status") or "run failed")
            digest["body"] = extractive_digest(items, date_label=date_label)
            mark("run", "Studio 运行核执行并交付", "fallback", detail)
    except Exception as exc:
        digest["body"] = extractive_digest(items, date_label=date_label)
        mark("run", "Studio 运行核执行并交付", "fallback", str(exc))

    return {
        "schema": "cartridgeflow.studio_release_run.v1",
        "steps": steps,
        "package": {key: value for key, value in package.items() if key not in {"archive", "installed_path"}},
        "runtime": {
            "id": "studio",
            "cartridge": package.get("cartridge"),
        },
        "fetch": {key: fetched[key] for key in ("fetched_at", "feeds", "warnings")},
        "items": items,
        "digest": digest,
        "run": {
            "run_id": (run_result or {}).get("run_id"),
            "status": (run_result or {}).get("status"),
            "error": (run_result or {}).get("error"),
        },
    }


def _delivery_text(delivery: dict | None) -> str:
    if not isinstance(delivery, dict):
        return ""
    for key in ("result", "value", "brief", "text", "content", "body", "summary"):
        item = delivery.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            for nested_key in ("brief", "result", "text", "content", "body"):
                nested = item.get(nested_key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return ""


def package_studio_project(root: str | Path, state: dict, packages_dir: str | Path | None = None) -> dict:
    """Sign the current Creator project as a Studio-runnable CF-CRE."""
    from core.studio.authoring_service import _short_project_name
    from core.studio.studio_layer2 import gaps_cleared, normalize_layer2, project_runtime_protocol

    if not gaps_cleared(state):
        raise ReleaseRuntimeError("STUDIO_PACKAGE_GAPS", "还有步骤待补齐，暂时不能签发。")
    project = Path(root).resolve()
    output_dir = Path(packages_dir).resolve() if packages_dir else (project / PACKAGES_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    recipe = state.get("semantic_recipe") or state.get("trusted_recipe") or {}
    nodes = [node for node in (recipe.get("nodes") or []) if isinstance(node, dict) and node.get("id")]
    stored = state.get("studio_layer2") or {}
    layers = {
        str(node["id"]): normalize_layer2(str(node["id"]), str(node.get("creator_label") or node.get("label") or node["id"]), stored.get(node["id"]))
        for node in nodes
    }
    protocol = project_runtime_protocol(layers)
    project_id = str(state.get("project_id") or state.get("id") or "project")
    cartridge_id = f"studio.{project_id}".replace(" ", "-")[:120]
    short_name = _short_project_name(str(state.get("project_name") or (state.get("head") or {}).get("blueprint", {}).get("intent") or cartridge_id))
    revision = int((state.get("head") or {}).get("revision") or 1)
    version = f"0.1.{max(1, revision)}"
    inputs = []
    for item in protocol["params"]:
        list_type = str(item.get("value_type") or "") == "string_list"
        inputs.append({
            "id": item["id"],
            "label": item["label"],
            "type": "string",
            "required": bool(item.get("required")),
            "schema": {"type": "array", "items": {"type": "string"}} if list_type else {"type": "string"},
            **({"default": item["default"]} if item.get("default") not in (None, "", []) else {}),
        })
    states = {
        "start": {"type": "control", "title": "开始", "display_name": "开始", "locked": True},
        "delivery": {"type": "system", "title": "生成交付快照", "display_name": "生成交付快照", "locked": True},
        "complete": {"type": "terminal", "title": "完成", "display_name": "完成", "locked": True},
        "failed": {"type": "terminal", "title": "流程失败", "display_name": "流程失败", "locked": True, "terminal_status": "failed"},
    }
    process_ids = []
    for index, node in enumerate(nodes):
        node_id = str(node["id"])
        label = str(layers[node_id].get("step_name") or node.get("creator_label") or node.get("label") or node_id)
        state_id = f"step.{node_id}"
        process_ids.append(state_id)
        if index == 0:
            states[state_id] = {
                "type": "process",
                "kind": "input",
                "executor": "user",
                "effect": "writes_store",
                "action": "collect_inputs",
                "title": label,
                "display_name": label,
                "params": {"fields": [item["id"] for item in protocol["params"]], "output": "input_data"},
                "failure_policy": "fail_closed",
            }
        elif index == len(nodes) - 1:
            states[state_id] = {
                "type": "process",
                "kind": "delivery",
                "executor": "deterministic",
                "effect": "writes_store",
                "action": "pass_result",
                "title": label,
                "display_name": label,
                "primary_output": "brief",
                "params": {"input": "llm_result", "output": "brief"},
                "failure_policy": "fail_closed",
            }
        else:
            states[state_id] = {
                "type": "process",
                "kind": "process",
                "executor": "deterministic",
                "effect": "writes_store",
                "action": "pass_result",
                "title": label,
                "display_name": label,
                "params": {"input": "input_data", "output": "llm_result"},
                "failure_policy": "fail_closed",
            }
    route = ["start", *process_ids, "delivery", "complete"]
    edges = [{"id": f"seq.{index:03d}", "kind": "sequence", "from": route[index], "to": route[index + 1]} for index in range(len(route) - 1)]
    for index, state_id in enumerate(process_ids):
        edges.append({
            "id": f"fail.{index:03d}",
            "kind": "failure",
            "from": state_id,
            "to": "failed",
            "failure": {"id": f"{state_id}.failure", "causes": ["cancelled", "exception", "resource", "retry_exhausted", "timeout", "validation"]},
        })
    manifest = {
        **MANIFEST,
        "id": cartridge_id,
        "name": short_name,
        "version": version,
        "description": str((state.get("head") or {}).get("blueprint", {}).get("intent") or short_name)[:400],
        "runtime": {"type": "none", "adapter": "builtin:studio_protocol"},
        "inputs": inputs,
        "studio_protocol": {
            "project_id": project_id,
            "session_id": str(state.get("id") or ""),
            "nodes": [{"id": node["id"], "label": layers[str(node["id"])].get("step_name") or node.get("creator_label") or node.get("label")} for node in nodes],
            "fields": protocol["fields"],
        },
    }
    flow = {
        "schema_version": "1.0",
        "id": f"{cartridge_id}.root",
        "name": short_name,
        "mode": "lifecycle",
        "cartridge_id": cartridge_id,
        "protocol": {"id": "CF-FARP", "version": "1.0"},
        "start": "start",
        "states": states,
        "execution_plan": {"schema": "cartridgeflow.execution_plan.v1", "entry": "start", "edges": edges},
    }
    experience = {
        "schema": "cartridgeflow.cartridge_experience.v1",
        "product": {"name": short_name, "category": "content"},
        "inputs": [{"id": item["id"], "label": item["label"], "type": "string", "required": bool(item.get("required")), "sensitive": False} for item in inputs],
        "stages": [{"id": "prepare", "label": "准备"}, {"id": "deliver", "label": "交付"}],
    }
    identity = ensure_development_signing_identity(project, PUBLISHER_ID)
    filename = f"{cartridge_id}-{version}.cf-cre.zip"
    archive = output_dir / filename
    with tempfile.TemporaryDirectory(prefix="studio-project-", dir=output_dir) as source_dir:
        source = Path(source_dir)
        (source / "assets").mkdir(parents=True, exist_ok=True)
        (source / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (source / "root.flow.json").write_text(json.dumps(flow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (source / "assets" / "registry.json").write_text(
            json.dumps({"schema": "cartridgeflow.asset_registry.v1", "assets": [], "components": []}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        pending = output_dir / f".{filename}.pending"
        try:
            built = build_release_archive(
                source,
                pending,
                publisher_id=PUBLISHER_ID,
                experience=experience,
                delivery=DELIVERY_CONTRACT,
                signing_identity=identity,
            )
            keys = trusted_public_keys(project)
            inspection = inspect_release_archive(pending, trusted_keys=keys)
            if not inspection.get("activation_allowed"):
                raise ReleaseRuntimeError("RELEASE_SIGNATURE_UNTRUSTED", "The signed CF-CRE could not be independently verified.")
            pending.replace(archive)
        except ReleaseRuntimeError:
            pending.unlink(missing_ok=True)
            raise
        except (ReleaseBuildError, OSError, ValueError) as exc:
            pending.unlink(missing_ok=True)
            raise ReleaseRuntimeError("RELEASE_PACKAGE_FAILED", f"Studio could not build a signed CF-CRE: {exc}") from exc
    fingerprint = str(built.get("release_id") or archive.name)
    if "+" in fingerprint:
        fingerprint = fingerprint.split("+")[-1]
    fingerprint = fingerprint[-12:]
    return {
        "schema": "cartridgeflow.creator_package.v1",
        "status": "ready",
        "filename": filename,
        "url": f"/packages/{filename}",
        "signature_verified": True,
        "fingerprint": fingerprint,
        "issued_at": datetime.now().strftime("%Y-%m-%d"),
        "release_id": built.get("release_id"),
        "cartridge": {"id": cartridge_id, "name": short_name, "version": version},
    }
