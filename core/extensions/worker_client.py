from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_worker_call(
    workspace_root: str | Path,
    package_path: str | Path,
    descriptor: dict,
    request: dict,
    *,
    timeout_ms: int,
) -> dict:
    root = Path(workspace_root).resolve()
    package = Path(package_path).resolve()
    bootstrap = Path(__file__).with_name("worker_bootstrap.py").resolve()
    descriptor_path = Path(descriptor["_descriptor_path"]).resolve()
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
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
    try:
        completed = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            cwd=str(root),
            timeout=max(1.0, timeout_ms / 1000),
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "dlc_worker_timeout", "error": f"DLC worker exceeded {timeout_ms} ms"}
    stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
    stderr = (completed.stderr or b"").decode("utf-8", errors="replace")
    if completed.returncode != 0:
        detail = (stderr or stdout).strip()[-4000:]
        return {"ok": False, "code": "dlc_worker_failed", "error": detail or f"DLC worker exited {completed.returncode}"}
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        return {"ok": False, "code": "dlc_worker_invalid_response", "error": stdout[-2000:]}
    if not isinstance(result, dict):
        return {"ok": False, "code": "dlc_worker_invalid_response", "error": "DLC worker response must be an object"}
    if stderr.strip():
        result.setdefault("worker_log", stderr.strip()[-4000:])
    return result
