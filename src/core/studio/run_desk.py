"""Studio 运行台: enqueue cartridge runs, project progress, install signed packages."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import threading
import time

from core.data_paths import INSTALLED_CARTRIDGES_DIR, PACKAGES_DIR
from core.protocol.release_builder import ReleaseBuildError, extract_release_payload, inspect_release_archive
from core.protocol.release_signing import trusted_public_keys
from core.runtime.errors import RuntimeFailure, build_runtime_error
from core.studio.release_runtime import ReleaseRuntimeError, bind_studio_runtime_models
from core.studio.rss_daily_trial import TrialRunError, extractive_digest, fetch_feeds


_ACTIVE_THREADS: dict[str, threading.Thread] = {}
_LOCK = threading.Lock()
MAX_PARALLEL = 2


def install_signed_package(root: str | Path, filename: str) -> dict:
    project = Path(root).resolve()
    package_root = (project / PACKAGES_DIR).resolve()
    archive = (package_root / Path(filename).name).resolve()
    if archive.parent != package_root or not archive.is_file():
        raise ReleaseRuntimeError("STUDIO_PACKAGE_MISSING", "The signed package is not available.", status=404)
    keys = trusted_public_keys(project)
    inspection = inspect_release_archive(archive, trusted_keys=keys)
    if not inspection.get("activation_allowed"):
        raise ReleaseRuntimeError("RELEASE_SIGNATURE_UNTRUSTED", "The signed CF-CRE could not be independently verified.")
    with tempfile.TemporaryDirectory(prefix="studio-install-") as staging:
        extracted = extract_release_payload(archive, staging, trusted_keys=keys)
        payload = Path(extracted["payload_path"])
        manifest = json.loads((payload / "manifest.json").read_text(encoding="utf-8"))
        cartridge_id = str(manifest.get("id") or "").strip()
        if not cartridge_id:
            raise ReleaseRuntimeError("STUDIO_PACKAGE_INVALID", "The signed package has no cartridge id.")
        target = project / INSTALLED_CARTRIDGES_DIR / cartridge_id
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(payload, target)
    return {
        "schema": "cartridgeflow.studio_runtime_install.v1",
        "status": "installed",
        "filename": archive.name,
        "url": f"/packages/{archive.name}",
        "signature_verified": True,
        "cartridge": {
            "id": cartridge_id,
            "name": str(manifest.get("name") or cartridge_id),
            "version": str(manifest.get("version") or ""),
        },
        "inputs": manifest.get("inputs") or [],
        "unpack": {"consumer": "python.extract_release_payload", "activation_allowed": True},
    }


def desk_snapshot(registry, runner, *, project_id: str = "", cartridge_id: str = "") -> dict:
    filter_cartridge = str(cartridge_id or "")
    items = []
    for item in registry.list_cartridges():
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        try:
            cartridge = registry.get_cartridge(item_id)
        except FileNotFoundError:
            continue
        manifest = cartridge.get("manifest") if isinstance(cartridge.get("manifest"), dict) else {}
        source = str(cartridge.get("source") or item.get("source") or "")
        if source == "dev":
            continue
        items.append({
            "id": item_id,
            "name": str(cartridge.get("name") or item_id),
            "version": str(cartridge.get("version") or ""),
            "source": source,
            "inputs": manifest.get("inputs") or [],
        })
    names = {item["id"]: item["name"] for item in items}
    jobs = []
    for run in runner.list_runs():
        run_project = str(run.get("project_id") or "")
        run_cartridge = str(run.get("cartridge_id") or "")
        status = str(run.get("status") or "")
        is_active = status in {"created", "running", "queued", "paused", "paused_waiting_user"}
        if filter_cartridge:
            if run_cartridge != filter_cartridge:
                continue
        elif is_active and str(run.get("source") or "") == "studio":
            pass
        elif project_id:
            if run_project != project_id:
                continue
        elif str(run.get("source") or "") != "studio" and run_cartridge not in names:
            continue
        view = _job_view(runner, run)
        if view["label"] in {"", view["cartridge_id"]}:
            view["label"] = names.get(view["cartridge_id"], view["label"])
        jobs.append(view)
        if len(jobs) >= 80:
            break
    return {
        "schema": "cartridgeflow.studio_run_desk.v1",
        "available": True,
        "runtime": "studio",
        "cartridges": items,
        "jobs": jobs,
    }


def enqueue_run(runner, registry, cartridge_id: str, inputs: dict | None = None, *, label: str = "", project_id: str = "") -> dict:
    cartridge = registry.get_cartridge(cartridge_id)
    queued = runner.create_queued_run(cartridge_id, inputs or {})
    queued["label"] = label or str(cartridge.get("name") or cartridge_id)
    queued["source"] = "studio"
    queued["cartridge_version"] = str(cartridge.get("version") or "")
    if project_id:
        queued["project_id"] = project_id
    run_dir = runner.runs_dir / queued["run_id"]
    runner._write_json(run_dir / "run.json", queued)
    flow = cartridge.get("root_flow") if isinstance(cartridge.get("root_flow"), dict) else {}
    if flow:
        runner._write_json(run_dir / "root_flow.snapshot.json", flow)
    with _LOCK:
        busy = len(_ACTIVE_THREADS)
    if busy >= MAX_PARALLEL:
        return _job_view(runner, queued)
    _start_worker(runner, registry, queued["run_id"], cartridge_id, inputs or {}, cartridge)
    return _job_view(runner, queued)


def _start_worker(runner, registry, run_id: str, cartridge_id: str, inputs: dict, cartridge: dict) -> None:
    manifest = cartridge.get("manifest") if isinstance(cartridge.get("manifest"), dict) else {}
    studio_protocol = bool(manifest.get("studio_protocol") or ((manifest.get("runtime") or {}).get("adapter") == "builtin:studio_protocol"))

    def worker() -> None:
        try:
            if studio_protocol:
                execute_studio_protocol(runner, run_id, cartridge, inputs)
                return
            bind_studio_runtime_models(cartridge_id, registry=registry)
            runner.create_run(cartridge_id, inputs, run_id=run_id)
        except FileNotFoundError as exc:
            runner.fail_queued_run(run_id, cartridge_id, build_runtime_error(
                "RESOURCE_NOT_FOUND", run_id=run_id, source="studio.run_desk",
                cause_chain=[{"type": "FileNotFoundError", "message": str(exc)}],
            ))
        except RuntimeFailure as exc:
            runner.fail_queued_run(run_id, cartridge_id, exc.envelope)
        except ReleaseRuntimeError as exc:
            runner.fail_queued_run(run_id, cartridge_id, build_runtime_error(
                "INPUT_REQUIRED" if "必填" in str(exc) else "TOOL_EXECUTION_FAILED",
                run_id=run_id, source="studio.run_desk",
                cause_chain=[{"type": "ReleaseRuntimeError", "message": str(exc)}],
            ))
        except Exception as exc:
            runner.fail_queued_run(run_id, cartridge_id, build_runtime_error(
                exception=exc, run_id=run_id, source="studio.run_desk",
            ))
        finally:
            with _LOCK:
                _ACTIVE_THREADS.pop(run_id, None)
            _kick_waiters(runner, registry)

    thread = threading.Thread(target=worker, name=f"studio-run-{run_id}", daemon=True)
    with _LOCK:
        _ACTIVE_THREADS[run_id] = thread
    thread.start()


def _kick_waiters(runner, registry) -> None:
    with _LOCK:
        if len(_ACTIVE_THREADS) >= MAX_PARALLEL:
            return
    for run in runner.list_runs():
        run_id = str(run.get("run_id") or "")
        if str(run.get("source") or "") != "studio":
            continue
        if str(run.get("status") or "") not in {"created", "queued"}:
            continue
        if run_id in _ACTIVE_THREADS:
            continue
        cartridge_id = str(run.get("cartridge_id") or "")
        try:
            cartridge = registry.get_cartridge(cartridge_id)
        except FileNotFoundError:
            continue
        inputs = run.get("inputs") if isinstance(run.get("inputs"), dict) else {}
        _start_worker(runner, registry, run_id, cartridge_id, inputs, cartridge)
        return


def execute_studio_protocol(runner, run_id: str, cartridge: dict, inputs: dict) -> dict:
    from core.cartridge.runner import now_iso

    run = runner.get_run(run_id)
    run_dir = runner.runs_dir / run_id
    flow = cartridge.get("root_flow") if isinstance(cartridge.get("root_flow"), dict) else {}
    runner._write_json(run_dir / "root_flow.snapshot.json", flow)
    steps = _process_steps(flow)
    manifest = cartridge.get("manifest") if isinstance(cartridge.get("manifest"), dict) else {}
    required = [item for item in (manifest.get("inputs") or []) if isinstance(item, dict) and item.get("required") and item.get("id")]
    missing = []
    for item in required:
        value = inputs.get(item["id"])
        if value in (None, "", [], {}):
            missing.append(str(item.get("label") or item["id"]))
    runner._set_run_status(run, "running", "studio_protocol_start")
    run["updated_at"] = now_iso()
    runner._write_json(run_dir / "run.json", run)

    def enter(step: dict, status: str) -> None:
        run["current_state"] = step["id"]
        run["updated_at"] = now_iso()
        runner._write_json(run_dir / "run.json", run)
        runner._append_event(run_id, run["cartridge_id"], "state_entered", step["id"], step["label"], {"status": status})
        if status in {"done", "error"}:
            event = "lab_node_completed" if status == "done" else "lab_node_failed"
            runner._append_event(run_id, run["cartridge_id"], event, step["id"], step["label"], {"status": status})
        time.sleep(0.25)

    if missing:
        if steps:
            enter(steps[0], "error")
        runner.fail_queued_run(run_id, run["cartridge_id"], build_runtime_error(
            "INPUT_REQUIRED",
            run_id=run_id,
            source="studio.run_desk",
            cause_chain=[{"type": "ValidationError", "message": f"缺少必填 已停住 · 没写半份日报（{ '、'.join(missing) }）"}],
        ))
        return runner.get_run(run_id)

    sources = inputs.get("sources") or inputs.get("来源列表") or []
    if isinstance(sources, str):
        sources = [line.strip() for line in sources.splitlines() if line.strip()]
    if not isinstance(sources, list):
        sources = [sources]
    sources = [str(item).strip() for item in sources if str(item).strip()]
    date = str(inputs.get("date") or inputs.get("运行日期") or "")
    if not date:
        from datetime import datetime, timezone
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    items: list[dict] = []
    warning = ""
    for index, step in enumerate(steps):
        enter(step, "running")
        if index == 0 and sources:
            try:
                fetched = fetch_feeds(sources[0])
                items = list(fetched.get("items") or [])
            except TrialRunError as exc:
                warning = str(exc)
                items = [{"title": url, "link": url, "summary": "来源已登记，条目待拉取"} for url in sources]
        enter(step, "done")

    if not items:
        items = [{"title": url, "link": url} for url in sources] or [{"title": "可展示的日报草稿", "summary": warning or "已按当前输入完成"}]
    digest = extractive_digest(items, date_label=date)
    if warning:
        digest = f"{digest}\n\n（来源拉取提示：{warning}）"
    delivery = {
        "result": digest,
        "value": digest,
        "summary": digest,
        "date": date,
        "result_items": [
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("link") or item.get("url") or ""),
                "summary": str(item.get("summary") or ""),
            }
            for item in items[:12]
        ],
        "source_url": [str(item.get("link") or item.get("url") or "") for item in items if item.get("link") or item.get("url")],
        "approved": False,
    }
    run = runner.get_run(run_id)
    run["delivery"] = delivery
    runner._write_json(run_dir / "delivery.json", delivery)
    runner._append_event(run_id, run["cartridge_id"], "terminal", "complete", "运行完成", {"delivery": True})
    runner._set_run_status(run, "completed", "studio_protocol_complete")
    run["current_state"] = "complete"
    run["updated_at"] = now_iso()
    runner._write_json(run_dir / "run.json", run)
    return run


def job_status(runner, run_id: str) -> dict:
    return _job_view(runner, runner.get_run(run_id))


def approve_run(runner, run_id: str, approved: bool = True) -> dict:
    run = runner.get_run(run_id)
    delivery = run.get("delivery") if isinstance(run.get("delivery"), dict) else {}
    delivery["approved"] = bool(approved)
    run["delivery"] = delivery
    runner._write_json(runner.runs_dir / run_id / "run.json", run)
    return _job_view(runner, run)


def _job_view(runner, run: dict) -> dict:
    run_id = str(run.get("run_id") or "")
    flow = {}
    snapshot = runner.runs_dir / run_id / "root_flow.snapshot.json"
    if snapshot.is_file():
        try:
            flow = json.loads(snapshot.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            flow = {}
    events = runner.get_events(run_id) if run_id else []
    return {
        "schema": "cartridgeflow.studio_run_job.v1",
        "run_id": run_id,
        "cartridge_id": str(run.get("cartridge_id") or ""),
        "label": str(run.get("label") or run.get("cartridge_id") or ""),
        "project_id": str(run.get("project_id") or ""),
        "cartridge_version": str(run.get("cartridge_version") or ""),
        "approved": bool((run.get("delivery") or {}).get("approved")) if isinstance(run.get("delivery"), dict) else False,
        "status": str(run.get("status") or "created"),
        "current_state": str(run.get("current_state") or ""),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "inputs": run.get("inputs") if isinstance(run.get("inputs"), dict) else {},
        "delivery": run.get("delivery") if isinstance(run.get("delivery"), dict) else None,
        "error": run.get("error") if isinstance(run.get("error"), dict) else None,
        "progress": project_run_progress(run, flow, events, waiting=str(run.get("status") or "") in {"created", "queued"} and run_id not in _ACTIVE_THREADS),
        "active": run_id in _ACTIVE_THREADS or str(run.get("status") or "") in {"created", "running", "queued"},
    }


def project_run_progress(run: dict, flow: dict, events: list[dict], *, waiting: bool = False) -> dict:
    steps = _process_steps(flow)
    current = str(run.get("current_state") or "")
    status = str(run.get("status") or "created")
    seen = {str(item.get("state") or "") for item in events if item.get("type") in {"state_entered", "lab_node_llm_started", "node_start"}}
    finished_types = {"lab_node_completed", "lab_node_failed", "lab_node_cancelled", "terminal"}
    finished = {str(item.get("state") or "") for item in events if item.get("type") in finished_types}
    projected = []
    for step in steps:
        step_status = "pending"
        if step["id"] in finished or (status in {"completed", "failed", "cancelled"} and step["id"] in seen):
            step_status = "error" if status == "failed" and step["id"] == current else "done"
        elif step["id"] == current or step["id"] in seen or status == "running" and not finished:
            if step["id"] == current or (step["id"] in seen and step["id"] not in finished):
                step_status = "running"
        projected.append({**step, "status": step_status})
    if waiting or status in {"created", "queued"} and str(run.get("run_id") or "") not in _ACTIVE_THREADS:
        for item in projected:
            item["status"] = "pending"
        return {
            "status": status,
            "percent": 0,
            "current_label": "排队中",
            "steps": projected,
        }
    if status == "created":
        for item in projected:
            item["status"] = "pending"
        if projected:
            projected[0]["status"] = "running"
    if status == "completed":
        for item in projected:
            item["status"] = "done"
    done = sum(1 for item in projected if item["status"] == "done")
    total = max(1, len(projected))
    running = next((item for item in projected if item["status"] == "running"), None)
    percent = 100 if status == "completed" else int(100 * done / total)
    if running and percent > 95:
        percent = 95
    return {
        "status": status,
        "percent": percent,
        "current_label": (running or {}).get("label") or ("完成" if status == "completed" else current or "排队中"),
        "steps": projected,
    }


def _process_steps(flow: dict) -> list[dict]:
    states = flow.get("states") if isinstance(flow.get("states"), dict) else {}
    plan = flow.get("execution_plan") if isinstance(flow.get("execution_plan"), dict) else {}
    edges = [edge for edge in (plan.get("edges") or []) if isinstance(edge, dict) and edge.get("kind") == "sequence"]
    order: list[str] = []
    current = str(plan.get("entry") or flow.get("start") or "start")
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        state = states.get(current) if isinstance(states.get(current), dict) else {}
        if state.get("type") == "process":
            order.append(current)
        nxt = next((str(edge.get("to") or "") for edge in edges if str(edge.get("from") or "") == current), "")
        current = nxt
    if not order:
        order = [key for key, state in states.items() if isinstance(state, dict) and state.get("type") == "process"]
    steps = []
    for node_id in order:
        state = states.get(node_id) or {}
        steps.append({
            "id": node_id,
            "label": str(state.get("display_name") or state.get("title") or node_id),
        })
    return steps
