from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.data_paths import WORKERS_DIR


WORKER_STATE_SCHEMA = "cartridgeflow.dlc_worker_state.v1"
_ACTIVE_LOCK = threading.RLock()
_ACTIVE: dict[str, dict] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_state(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _terminate_process_domain(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


def _request_termination(entry: dict, reason: str) -> None:
    entry["terminal_reason"] = reason
    entry["cancel_event"].set()


def cancel_worker_calls_for_run(run_id: str) -> list[str]:
    cancelled = []
    with _ACTIVE_LOCK:
        for worker_id, entry in _ACTIVE.items():
            if str(entry["record"].get("run_id") or "") == str(run_id or ""):
                _request_termination(entry, "cancelled")
                cancelled.append(worker_id)
    return cancelled


def shutdown_active_workers(reason: str = "host_exited") -> list[str]:
    terminated = []
    with _ACTIVE_LOCK:
        entries = list(_ACTIVE.items())
        for worker_id, entry in entries:
            _request_termination(entry, reason)
            record = entry["record"]
            record.update({"status": reason, "finished_at": _utc_now(), "exit_code": None})
            _write_state(entry["journal_path"], record)
            _terminate_process_domain(entry["process"])
            terminated.append(worker_id)
    return terminated


atexit.register(shutdown_active_workers)


def run_worker_call(
    workspace_root: str | Path,
    package_path: str | Path,
    descriptor: dict,
    request: dict,
    *,
    timeout_ms: int,
    worker_call_id: str | None = None,
    cancel_event: threading.Event | None = None,
    journal_dir: str | Path | None = None,
) -> dict:
    root = Path(workspace_root).resolve()
    package = Path(package_path).resolve()
    bootstrap = Path(__file__).with_name("worker_bootstrap.py").resolve()
    descriptor_path = Path(descriptor["_descriptor_path"]).resolve()
    worker_id = str(worker_call_id or request.get("request_id") or f"worker_{uuid.uuid4().hex[:16]}")
    safe_worker_id = "".join(char if char.isalnum() or char in "._-" else "_" for char in worker_id)[:120]
    journal_root = Path(journal_dir).resolve() if journal_dir else root / WORKERS_DIR
    journal_path = journal_root / f"{safe_worker_id}.json"
    command = [
        sys.executable,
        "-I",
        str(bootstrap),
        "--workspace",
        str(root),
        "--package",
        str(package),
        "--descriptor",
        str(descriptor_path),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
    record = {
        "schema": WORKER_STATE_SCHEMA,
        "worker_call_id": worker_id,
        "run_id": str(request.get("run_id") or ""),
        "cartridge_id": str(request.get("cartridge_id") or ""),
        "server": str(request.get("server") or ""),
        "tool": str(request.get("tool") or ""),
        "status": "starting",
        "started_at": _utc_now(),
        "finished_at": None,
        "pid": None,
        "exit_code": None,
    }
    _write_state(journal_path, record)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(root),
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    except OSError as exc:
        record.update({"status": "failed", "finished_at": _utc_now(), "error": str(exc)})
        _write_state(journal_path, record)
        return {
            "ok": False,
            "code": "dlc_worker_start_failed",
            "error": str(exc),
            "worker_call_id": worker_id,
            "worker_state": "failed",
        }

    local_cancel = threading.Event()
    entry = {
        "process": process,
        "cancel_event": local_cancel,
        "external_cancel_event": cancel_event,
        "terminal_reason": "",
        "journal_path": journal_path,
        "record": record,
    }
    record.update({"status": "running", "pid": process.pid})
    _write_state(journal_path, record)
    with _ACTIVE_LOCK:
        _ACTIVE[worker_id] = entry

    terminal_state = ""
    stdout = b""
    stderr = b""
    io_result: dict[str, object] = {}

    def _communicate() -> None:
        try:
            io_result["output"] = process.communicate(input=payload)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            io_result["error"] = exc

    io_thread = threading.Thread(target=_communicate, name=f"cf-worker-io-{safe_worker_id}", daemon=True)
    try:
        io_thread.start()
        deadline = time.monotonic() + max(0.05, timeout_ms / 1000)
        while io_thread.is_alive():
            if local_cancel.is_set() or (cancel_event is not None and cancel_event.is_set()):
                terminal_state = str(entry.get("terminal_reason") or "cancelled")
                _terminate_process_domain(process)
                break
            if time.monotonic() >= deadline:
                terminal_state = "timed_out"
                _terminate_process_domain(process)
                break
            time.sleep(0.02)
        io_thread.join(timeout=5)
        output = io_result.get("output")
        if isinstance(output, tuple) and len(output) == 2:
            stdout, stderr = output
        if io_result.get("error") is not None:
            raise io_result["error"]
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        terminal_state = terminal_state or "failed"
        stderr = str(exc).encode("utf-8", errors="replace")
        _terminate_process_domain(process)
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.pop(worker_id, None)

    stdout_text = (stdout or b"").decode("utf-8", errors="replace")
    stderr_text = (stderr or b"").decode("utf-8", errors="replace")
    if not terminal_state and local_cancel.is_set():
        terminal_state = str(entry.get("terminal_reason") or "cancelled")
    if not terminal_state:
        terminal_state = "succeeded" if process.returncode == 0 else "failed"
    record.update({
        "status": terminal_state,
        "finished_at": _utc_now(),
        "exit_code": process.returncode,
    })
    if stderr_text.strip():
        record["worker_log_tail"] = stderr_text.strip()[-4000:]
    _write_state(journal_path, record)

    if terminal_state == "timed_out":
        return {
            "ok": False,
            "code": "dlc_worker_timeout",
            "error": f"DLC worker exceeded {timeout_ms} ms",
            "worker_call_id": worker_id,
            "worker_state": terminal_state,
        }
    if terminal_state in {"cancelled", "host_exited"}:
        return {
            "ok": False,
            "code": "dlc_worker_cancelled" if terminal_state == "cancelled" else "dlc_worker_host_exited",
            "error": "DLC worker was cancelled" if terminal_state == "cancelled" else "DLC worker stopped because the host exited",
            "worker_call_id": worker_id,
            "worker_state": terminal_state,
        }
    if process.returncode != 0:
        detail = (stderr_text or stdout_text).strip()[-4000:]
        return {
            "ok": False,
            "code": "dlc_worker_failed",
            "error": detail or f"DLC worker exited {process.returncode}",
            "worker_call_id": worker_id,
            "worker_state": terminal_state,
        }
    try:
        result = json.loads(stdout_text)
    except json.JSONDecodeError:
        record.update({"status": "failed", "error": "invalid_json_response"})
        _write_state(journal_path, record)
        return {
            "ok": False,
            "code": "dlc_worker_invalid_response",
            "error": stdout_text[-2000:],
            "worker_call_id": worker_id,
            "worker_state": "failed",
        }
    if not isinstance(result, dict):
        record.update({"status": "failed", "error": "non_object_response"})
        _write_state(journal_path, record)
        return {
            "ok": False,
            "code": "dlc_worker_invalid_response",
            "error": "DLC worker response must be an object",
            "worker_call_id": worker_id,
            "worker_state": "failed",
        }
    result.setdefault("worker_call_id", worker_id)
    result.setdefault("worker_state", terminal_state)
    if stderr_text.strip():
        result.setdefault("worker_log", stderr_text.strip()[-4000:])
    return result
