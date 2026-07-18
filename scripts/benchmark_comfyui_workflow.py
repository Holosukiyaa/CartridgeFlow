import argparse
import json
import subprocess
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def request_json(base_url: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ComfyUI returned HTTP {exc.code}: {detail}") from exc


def gpu_used_bytes(stats: dict) -> int:
    devices = stats.get("devices") or []
    if not devices:
        return 0
    device = devices[0]
    return max(0, int(device.get("vram_total") or 0) - int(device.get("vram_free") or 0))


def driver_gpu_used_bytes() -> int:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        return int(float(output.splitlines()[0].strip())) * 1024 * 1024
    except (FileNotFoundError, OSError, subprocess.SubprocessError, ValueError, IndexError):
        return 0


def apply_overrides(workflow: dict, overrides: list[str]) -> dict:
    applied = {}
    for item in overrides:
        key, separator, raw_value = item.partition("=")
        if not separator or "." not in key:
            raise ValueError(f"invalid --set value {item!r}; expected NODE.INPUT=VALUE")
        node_id, input_name = key.split(".", 1)
        if node_id not in workflow:
            raise KeyError(f"workflow has no node {node_id!r}")
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = raw_value
        workflow[node_id].setdefault("inputs", {})[input_name] = value
        applied[key] = value
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a ComfyUI API workflow and record a local benchmark report.")
    parser.add_argument("workflow", type=Path)
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    parser.add_argument("--report", type=Path, default=ROOT / "test_output/comfyui/workflow_benchmark.json")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--set", action="append", default=[], metavar="NODE.INPUT=VALUE")
    args = parser.parse_args()

    workflow_path = args.workflow if args.workflow.is_absolute() else ROOT / args.workflow
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    overrides = apply_overrides(workflow, args.set)
    client_id = f"cartridgeflow-{uuid.uuid4().hex}"
    baseline_comfy = gpu_used_bytes(request_json(args.server, "/system_stats"))
    baseline_driver = driver_gpu_used_bytes()
    queued = request_json(args.server, "/prompt", {"prompt": workflow, "client_id": client_id})
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return prompt_id: {queued}")

    started = time.monotonic()
    peak_comfy = baseline_comfy
    peak_driver = baseline_driver
    history_entry = None
    while time.monotonic() - started < args.timeout:
        stats = request_json(args.server, "/system_stats")
        peak_comfy = max(peak_comfy, gpu_used_bytes(stats))
        peak_driver = max(peak_driver, driver_gpu_used_bytes())
        history = request_json(args.server, f"/history/{prompt_id}")
        history_entry = history.get(prompt_id)
        if history_entry:
            status = history_entry.get("status") or {}
            if status.get("completed") or status.get("status_str") in {"error", "success"}:
                break
        time.sleep(1)
    else:
        raise TimeoutError(f"ComfyUI workflow did not finish within {args.timeout} seconds")

    elapsed = round(time.monotonic() - started, 3)
    status = (history_entry or {}).get("status") or {}
    report = {
        "schema": "cartridgeflow.comfyui_benchmark.v1",
        "workflow": workflow_path.resolve().relative_to(ROOT).as_posix(),
        "server": args.server,
        "prompt_id": prompt_id,
        "overrides": overrides,
        "status": status.get("status_str"),
        "completed": bool(status.get("completed")),
        "elapsed_seconds": elapsed,
        "baseline_comfy_vram_gb": round(baseline_comfy / (1024**3), 3),
        "peak_comfy_vram_gb": round(peak_comfy / (1024**3), 3),
        "baseline_driver_vram_gb": round(baseline_driver / (1024**3), 3),
        "peak_driver_vram_gb": round(peak_driver / (1024**3), 3),
        "outputs": (history_entry or {}).get("outputs") or {},
        "messages": status.get("messages") or [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    report_path = args.report if args.report.is_absolute() else ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["completed"] and report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
