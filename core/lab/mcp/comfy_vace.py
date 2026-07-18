"""Strict local ComfyUI adapter for the CRCP VACE character-replacement workflow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from copy import deepcopy
from pathlib import Path

from core.protocol.creative_recast import (
    validate_creative_spec,
    validate_run_snapshot,
    validate_shot_control_bundle,
)


WORKFLOW_ID = "wan21_vace_1_3b_character_replace"
WORKFLOW_PATH = "config/comfyui/workflows/wan21_vace_1_3b_character_replace.api.json"
MODEL_ID = "wan2.1-vace-1.3b"
MODEL_FILENAME = "wan2.1_vace_1.3B_fp16.safetensors"

_NODE_TYPES = {
    "1": "UNETLoader",
    "4": "CLIPTextEncode",
    "5": "CLIPTextEncode",
    "6": "LoadVideo",
    "7": "GetVideoComponents",
    "8": "LoadImage",
    "9": "WanVaceToVideo",
    "11": "KSampler",
    "14": "CreateVideo",
    "15": "SaveVideo",
    "16": "LoadVideo",
    "17": "GetVideoComponents",
    "18": "ImageToMask",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(value, field: str) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"{field} must be a JSON object")


def _safe_token(value: str, fallback: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return token[:80] or fallback


def _require_file(registry, value: str, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    path = registry._safe_path(value)
    if not path.is_file():
        raise FileNotFoundError(f"{field} does not exist: {value}")
    return path


def _request_json(base_url: str, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ComfyUI returned HTTP {exc.code}: {detail}") from exc


def _gpu_used_bytes(stats: dict) -> int:
    devices = stats.get("devices") or []
    if not devices:
        return 0
    device = devices[0]
    return max(0, int(device.get("vram_total") or 0) - int(device.get("vram_free") or 0))


def _validate_workflow(workflow: dict) -> None:
    if not isinstance(workflow, dict):
        raise ValueError("ComfyUI workflow must be an API-format JSON object")
    for node_id, class_type in _NODE_TYPES.items():
        node = workflow.get(node_id)
        if not isinstance(node, dict) or node.get("class_type") != class_type:
            raise ValueError(f"workflow node {node_id} must be {class_type}")
    vace_inputs = workflow["9"].get("inputs") or {}
    if vace_inputs.get("control_video") != ["7", 0]:
        raise ValueError("VACE control_video must consume the Blender preview")
    if vace_inputs.get("control_masks") != ["18", 0]:
        raise ValueError("VACE control_masks must consume the CRCP character mask")
    if workflow["18"].get("inputs", {}).get("channel") != "red":
        raise ValueError("CRCP character mask must use its red grayscale channel")


def _prepare_workflow(
    workflow: dict,
    *,
    preview_name: str,
    mask_name: str,
    reference_name: str,
    positive_prompt: str,
    negative_prompt: str,
    parameters: dict,
    output_prefix: str,
) -> dict:
    _validate_workflow(workflow)
    width = int(parameters.get("width") or 288)
    height = int(parameters.get("height") or 512)
    length = int(parameters.get("length") or parameters.get("frame_count") or 0)
    fps = float(parameters.get("fps") or 12)
    if width <= 0 or height <= 0 or width % 16 or height % 16:
        raise ValueError("VACE width and height must be positive multiples of 16")
    if length <= 0 or (length - 1) % 4:
        raise ValueError("VACE frame count must use the 4n+1 temporal layout")
    workflow["4"]["inputs"]["text"] = positive_prompt
    workflow["5"]["inputs"]["text"] = negative_prompt
    workflow["6"]["inputs"]["file"] = preview_name
    workflow["8"]["inputs"]["image"] = reference_name
    workflow["16"]["inputs"]["file"] = mask_name
    workflow["9"]["inputs"].update({
        "width": width,
        "height": height,
        "length": length,
        "batch_size": 1,
        "strength": float(parameters.get("strength") or 1.0),
    })
    workflow["11"]["inputs"].update({
        "seed": int(parameters.get("seed") or 0),
        "steps": int(parameters.get("steps") or 8),
        "cfg": float(parameters.get("cfg") or 6.0),
        "sampler_name": str(parameters.get("sampler_name") or "uni_pc"),
        "scheduler": str(parameters.get("scheduler") or "simple"),
        "denoise": float(parameters.get("denoise") or 1.0),
    })
    workflow["14"]["inputs"]["fps"] = fps
    workflow["15"]["inputs"]["filename_prefix"] = output_prefix
    return workflow


def _copy_comfy_input(source: Path, input_root: Path, relative_name: str) -> str:
    target = (input_root / Path(relative_name)).resolve()
    if input_root.resolve() not in target.parents:
        raise PermissionError("ComfyUI input path escaped its input directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return Path(relative_name).as_posix()


def _first_video(outputs: dict) -> dict | None:
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        for key in ("videos", "images", "files"):
            for item in output.get(key) or []:
                if isinstance(item, dict) and Path(str(item.get("filename") or "")).suffix.lower() in {".mp4", ".webm", ".mov"}:
                    return item
    return None


def _download_output(base_url: str, metadata: dict, target: Path) -> None:
    query = urllib.parse.urlencode({
        "filename": metadata.get("filename"),
        "subfolder": metadata.get("subfolder") or "",
        "type": metadata.get("type") or "output",
    })
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"{base_url.rstrip('/')}/view?{query}", timeout=120) as response:
        target.write_bytes(response.read())
    if target.stat().st_size < 1024:
        raise RuntimeError("ComfyUI returned an empty or truncated video")


def _find_ffprobe(params: dict) -> str | None:
    candidates = [
        params.get("ffprobe_path"),
        os.environ.get("FFPROBE_PATH"),
        shutil.which("ffprobe"),
        r"C:\ffmpeg\bin\ffprobe.exe",
    ]
    return next((str(item) for item in candidates if item and Path(item).is_file()), None)


def _probe_video(path: Path, params: dict) -> dict:
    ffprobe = _find_ffprobe(params)
    if not ffprobe:
        return {"ok": False, "error": "ffprobe is required for the CRCP technical gate"}
    completed = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-count_frames",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames:format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        return {"ok": False, "error": completed.stderr.strip() or "ffprobe failed"}
    data = json.loads(completed.stdout)
    stream = (data.get("streams") or [{}])[0]
    rate = str(stream.get("avg_frame_rate") or "0/1").split("/", 1)
    fps = float(rate[0]) / float(rate[1]) if len(rate) == 2 and float(rate[1]) else 0.0
    return {
        "ok": True,
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "frame_count": int(stream.get("nb_read_frames") or 0),
        "fps": round(fps, 6),
        "duration": float((data.get("format") or {}).get("duration") or 0),
    }


def _technical_gate(probe: dict, parameters: dict) -> dict:
    findings = []
    expected = {
        "width": int(parameters["width"]),
        "height": int(parameters["height"]),
        "frame_count": int(parameters["length"]),
    }
    if not probe.get("ok"):
        findings.append({"severity": "blocker", "code": "candidate_unplayable", "message": probe.get("error") or "video probe failed"})
    else:
        for field, value in expected.items():
            if probe.get(field) != value:
                findings.append({"severity": "blocker", "code": f"candidate_{field}_mismatch", "message": f"expected {field}={value}, got {probe.get(field)}"})
        if abs(float(probe.get("fps") or 0) - float(parameters["fps"])) > 0.01:
            findings.append({"severity": "blocker", "code": "candidate_fps_mismatch", "message": f"expected fps={parameters['fps']}, got {probe.get('fps')}"})
    return {"ok": not findings, "findings": findings}


def _cached_nodes(status: dict) -> list[str]:
    for message in status.get("messages") or []:
        if isinstance(message, list) and len(message) == 2 and message[0] == "execution_cached":
            payload = message[1] if isinstance(message[1], dict) else {}
            return [str(item) for item in payload.get("nodes") or []]
    return []


def _review_snapshot(snapshot: dict, output_path: str, output_hash: str, technical_gate_ok: bool) -> dict:
    result = deepcopy(snapshot)
    result["status"] = "review_required" if technical_gate_ok else "rejected"
    result["outputs"] = [{"path": output_path, "sha256": output_hash}]
    return result


def _snapshot_parameters(snapshot: dict, spec: dict, bundle: dict) -> dict:
    if snapshot.get("status") != "locked":
        raise ValueError("RunSnapshot must be locked before ComfyUI execution")
    spec_ref = snapshot.get("creative_spec") or {}
    if spec_ref.get("spec_id") != spec.get("spec_id") or spec_ref.get("revision") != spec.get("revision"):
        raise ValueError("RunSnapshot creative_spec reference does not match the approved CreativeSpec")
    bundle_ref = snapshot.get("control_bundle") or {}
    if bundle_ref.get("bundle_id") != bundle.get("bundle_id") or bundle_ref.get("revision") != bundle.get("revision"):
        raise ValueError("RunSnapshot control_bundle reference does not match the validated Shot Control Bundle")
    parameters = dict(snapshot.get("parameters") or {})
    required = ["width", "height", "length", "fps", "steps", "cfg", "sampler_name", "scheduler", "strength", "denoise"]
    missing = [field for field in required if field not in parameters]
    if missing:
        raise ValueError(f"RunSnapshot parameters are missing: {', '.join(missing)}")
    parameters["seed"] = int(snapshot.get("seed"))
    if int(parameters["length"]) != int(bundle["frame_count"]):
        raise ValueError("RunSnapshot length must equal the Shot Control Bundle frame count")
    if abs(float(parameters["fps"]) - float(bundle["fps"])) > 0.01:
        raise ValueError("RunSnapshot fps must equal the Shot Control Bundle fps")
    return parameters


def run_vace_character_replace(registry, params: dict) -> dict:
    """Execute the one allowlisted VACE workflow and preserve a reproducible report."""
    try:
        spec = _json_object(params.get("creative_spec"), "creative_spec")
        bundle = _json_object(params.get("control_bundle"), "control_bundle")
        snapshot = _json_object(params.get("run_snapshot"), "run_snapshot")
        spec_check = validate_creative_spec(spec)
        bundle_check = validate_shot_control_bundle(bundle, registry._workspace_root, check_files=True)
        snapshot_check = validate_run_snapshot(snapshot)
        if not spec_check.get("ok") or not bundle_check.get("ok") or not snapshot_check.get("ok"):
            return {
                "ok": False,
                "stage": "validation",
                "error": "CRCP artifacts failed VACE preflight validation",
                "creative_spec": spec_check,
                "control_bundle": bundle_check,
                "run_snapshot": snapshot_check,
            }
        if spec.get("mode") != "character_replace":
            raise ValueError("the allowlisted VACE adapter only supports character_replace mode")
        if WORKFLOW_ID not in (spec.get("allowed_workflows") or []):
            raise ValueError(f"CreativeSpec does not allow workflow {WORKFLOW_ID}")
        workflow_ref = snapshot.get("workflow") or {}
        model_ref = snapshot.get("model") or {}
        if workflow_ref.get("id") != WORKFLOW_ID:
            raise ValueError(f"RunSnapshot workflow must be {WORKFLOW_ID}")
        if model_ref.get("id") != MODEL_ID:
            raise ValueError(f"RunSnapshot model must be {MODEL_ID}")

        workflow_path = registry._safe_path(WORKFLOW_PATH)
        workflow_hash = _sha256(workflow_path)
        if workflow_ref.get("sha256") != workflow_hash:
            raise ValueError("RunSnapshot workflow hash does not match the allowlisted workflow")
        comfy_root = Path(params.get("comfyui_root") or os.environ.get("COMFYUI_ROOT") or r"C:\ComfyUI_windows_portable").resolve()
        input_root = comfy_root / "ComfyUI" / "input"
        model_path = comfy_root / "ComfyUI" / "models" / "diffusion_models" / MODEL_FILENAME
        if not input_root.is_dir() or not model_path.is_file():
            raise FileNotFoundError("the configured ComfyUI portable root is missing its input directory or VACE model")
        model_hash = _sha256(model_path)
        if model_ref.get("sha256") != model_hash:
            raise ValueError("RunSnapshot model hash does not match the installed VACE model")

        source = bundle["source"]
        controls = bundle["controls"]
        preview_path = _require_file(registry, source["preview"], "control_bundle.source.preview")
        mask_path = _require_file(registry, controls["character_mask"], "control_bundle.controls.character_mask")
        reference_path = _require_file(registry, params.get("reference_image"), "reference_image")
        parameters = _snapshot_parameters(snapshot, spec, bundle)

        run_token = _safe_token(params.get("run_id") or snapshot.get("run_id"), uuid.uuid4().hex[:12])
        input_subdir = f"CartridgeFlow/crcp/{run_token}"
        preview_name = _copy_comfy_input(preview_path, input_root, f"{input_subdir}/preview.mp4")
        mask_name = _copy_comfy_input(mask_path, input_root, f"{input_subdir}/character_mask.mp4")
        reference_name = _copy_comfy_input(reference_path, input_root, f"{input_subdir}/character_reference{reference_path.suffix.lower()}")
        prompt_fields = params.get("prompt_fields") or {}
        positive_prompt = ", ".join(
            str(prompt_fields.get(field) or "").strip()
            for field in ("content_prompt", "identity_prompt", "style_prompt", "continuity_prompt")
            if str(prompt_fields.get(field) or "").strip()
        )
        negative_prompt = str(prompt_fields.get("negative_prompt") or "").strip()
        if not positive_prompt or not negative_prompt:
            raise ValueError("prompt_fields must include positive prompt layers and negative_prompt")

        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        output_prefix = f"CartridgeFlow/crcp/{run_token}/candidate"
        _prepare_workflow(
            workflow,
            preview_name=preview_name,
            mask_name=mask_name,
            reference_name=reference_name,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            parameters=parameters,
            output_prefix=output_prefix,
        )

        base_url = str(params.get("comfyui_url") or "http://127.0.0.1:8188").rstrip("/")
        timeout = max(30, min(int(params.get("timeout_seconds") or 1800), 7200))
        baseline_vram = _gpu_used_bytes(_request_json(base_url, "/system_stats"))
        peak_vram = baseline_vram
        queued = _request_json(base_url, "/prompt", {"prompt": workflow, "client_id": f"cartridgeflow-{uuid.uuid4().hex}"})
        prompt_id = queued.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return prompt_id: {queued}")
        started = time.monotonic()
        history_entry = None
        while time.monotonic() - started < timeout:
            peak_vram = max(peak_vram, _gpu_used_bytes(_request_json(base_url, "/system_stats")))
            history = _request_json(base_url, f"/history/{urllib.parse.quote(str(prompt_id))}")
            history_entry = history.get(str(prompt_id)) or history.get(prompt_id)
            if history_entry:
                status = history_entry.get("status") or {}
                if status.get("completed") or status.get("status_str") in {"error", "success"}:
                    break
            time.sleep(1.0)
        else:
            raise TimeoutError(f"ComfyUI workflow did not finish within {timeout} seconds")
        status = (history_entry or {}).get("status") or {}
        if status.get("status_str") != "success" or not status.get("completed"):
            raise RuntimeError(f"ComfyUI workflow failed: {status.get('messages') or status}")
        video_meta = _first_video((history_entry or {}).get("outputs") or {})
        if not video_meta:
            raise RuntimeError("ComfyUI history did not include a video output")

        output_dir = registry._safe_path(str(params.get("output_dir") or f"test_output/creative_recast/{run_token}"))
        prompt_token = _safe_token(str(prompt_id), "unknown_prompt")
        output_path = output_dir / f"candidate.{prompt_token}.mp4"
        _download_output(base_url, video_meta, output_path)
        probe = _probe_video(output_path, params)
        technical_gate = _technical_gate(probe, parameters)
        elapsed = round(time.monotonic() - started, 3)
        cached_nodes = _cached_nodes(status)
        relative_output = output_path.resolve().relative_to(registry._workspace_root.resolve()).as_posix()
        output_hash = _sha256(output_path)
        review_snapshot = _review_snapshot(snapshot, relative_output, output_hash, technical_gate["ok"])
        snapshot_path = output_dir / f"run_snapshot.review.{prompt_token}.json"
        snapshot_path.write_text(json.dumps(review_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        report = {
            "schema": "cartridgeflow.comfyui_run_report.v1",
            "run_id": run_token,
            "prompt_id": prompt_id,
            "workflow": {"id": WORKFLOW_ID, "path": WORKFLOW_PATH, "sha256": workflow_hash},
            "model": {"id": MODEL_ID, "filename": MODEL_FILENAME, "sha256": model_hash},
            "parameters": parameters,
            "prompt_fields": prompt_fields,
            "inputs": {
                "preview": {"path": source["preview"], "sha256": _sha256(preview_path)},
                "character_mask": {"path": controls["character_mask"], "sha256": _sha256(mask_path)},
                "depth": {"path": controls["depth"], "sha256": bundle["sha256"][controls["depth"]]},
                "pose": {"path": controls["pose"], "sha256": bundle["sha256"][controls["pose"]]},
                "character_reference": {"path": str(params.get("reference_image")), "sha256": _sha256(reference_path)},
            },
            "control_usage": {
                "preview": "consumed_by_vace_control_video",
                "character_mask": "consumed_by_vace_control_masks_white_generate_black_preserve",
                "character_reference": "consumed_by_vace_reference_image",
                "depth": "validated_but_not_consumed_by_this_allowlisted_workflow",
                "pose": "validated_but_not_consumed_by_this_allowlisted_workflow",
            },
            "output": {"path": relative_output, "sha256": output_hash},
            "review_snapshot": snapshot_path.resolve().relative_to(registry._workspace_root.resolve()).as_posix(),
            "probe": probe,
            "technical_gate": technical_gate,
            "elapsed_seconds": elapsed,
            "cache_hit": bool(cached_nodes),
            "cached_nodes": cached_nodes,
            "baseline_vram_gb": round(baseline_vram / (1024**3), 3),
            "peak_vram_gb": round(peak_vram / (1024**3), 3),
            "status": "candidate" if technical_gate["ok"] else "rejected",
        }
        report_path = output_dir / f"comfyui_run_report.{prompt_token}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        relative_report = report_path.resolve().relative_to(registry._workspace_root.resolve()).as_posix()
        relative_snapshot = snapshot_path.resolve().relative_to(registry._workspace_root.resolve()).as_posix()
        return {
            "ok": technical_gate["ok"],
            "path": relative_output,
            "files": [relative_output, relative_report, relative_snapshot],
            "report_path": relative_report,
            "run_snapshot_path": relative_snapshot,
            "run_snapshot": review_snapshot,
            "report": report,
            "technical_gate": technical_gate,
            "error": "ComfyUI output failed the CRCP technical gate" if not technical_gate["ok"] else "",
        }
    except Exception as exc:
        return {"ok": False, "stage": "comfyui", "error": f"VACE character replacement failed: {exc}", "files": []}
