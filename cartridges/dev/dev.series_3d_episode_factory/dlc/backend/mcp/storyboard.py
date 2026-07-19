from __future__ import annotations

import json
import math
import re
import struct
import zlib
from copy import deepcopy
from pathlib import Path


DLC_ID = "dlc.series_3d_episode_factory"
DLC_PROTOCOL = "CF-FARP@0.5"
TOOLS = [
    "build_storyboard_project",
    "render_storyboard_frames",
    "apply_storyboard_adjustments",
    "prepare_video_shots",
]


def _object(value, fallback=None):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"shots": value}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"shots": parsed}
        except json.JSONDecodeError:
            pass
    return deepcopy(fallback if isinstance(fallback, dict) else {})


def _project(value) -> dict:
    data = _object(value)
    if isinstance(data.get("project"), dict):
        return deepcopy(data["project"])
    return data


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "storyboard")).strip("_") or "storyboard"


def _shots(value) -> list[dict]:
    data = _object(value)
    raw = data.get("shots") or data.get("shot_list") or []
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _workspace_rel(registry, path: Path) -> str:
    return path.resolve().relative_to(registry._workspace_root.resolve()).as_posix()


def _camera_for(index: int, shot: dict) -> dict:
    template = str(shot.get("camera") or "slow_push_in")
    presets = {
        "slow_push_in": {"position": [0.0, -8.0, 2.1], "target": [0.0, 0.0, 1.2], "focal_length_mm": 42},
        "close_up_reveal": {"position": [1.4, -3.8, 1.8], "target": [0.0, 0.0, 1.45], "focal_length_mm": 68},
        "over_shoulder": {"position": [-1.8, -4.8, 1.9], "target": [0.2, 0.5, 1.35], "focal_length_mm": 52},
        "low_angle_hold": {"position": [1.1, -5.5, 0.75], "target": [0.0, 0.5, 1.35], "focal_length_mm": 38},
    }
    camera = deepcopy(presets.get(template, presets["slow_push_in"]))
    camera.update({"template": template, "safe_frame": "9:16", "index": index})
    return camera


def _actor_for(shot: dict, action: str) -> dict:
    return {
        "id": "hero",
        "asset_id": "pilot_male_hero",
        "position": [0.0, 0.25, 0.0],
        "rotation_degrees": [0.0, 0.0, 0.0],
        "scale": 1.0,
        "action": action,
        "pose_time": 0.42,
        "gaze_target": [0.0, -4.0, 1.4],
        "locked_identity": True,
    }


def _build_project(params: dict) -> dict:
    script = _object(params.get("episode_script"))
    shot_list = _object(params.get("shot_list"))
    asset_plan = _object(params.get("asset_plan"))
    action_plan = _object(params.get("action_plan"))
    source_shots = _shots(shot_list)
    if not source_shots:
        raise ValueError("shot_list must contain at least one shot")
    project_id = _slug(params.get("project_id") or script.get("episode_id") or script.get("title") or "episode")
    actions = {
        str(item.get("shot_id") or item.get("id")): str(item.get("action_id") or item.get("action") or "idle_hold")
        for item in (action_plan.get("shots") or action_plan.get("assignments") or [])
        if isinstance(item, dict)
    }
    shots = []
    for index, source in enumerate(source_shots[:10]):
        shot_id = str(source.get("id") or f"shot_{index + 1:02d}")
        action = actions.get(shot_id) or str((source.get("action_tags") or ["idle_hold"])[0])
        shots.append({
            "id": shot_id,
            "order": index + 1,
            "title": str(source.get("title") or f"Shot {index + 1}"),
            "intent": str(source.get("description") or ""),
            "duration_seconds": float(source.get("duration") or 3.0),
            "scene": {"asset_id": "pilot_suburban_street_day", "time": "day", "weather": "clear"},
            "camera": _camera_for(index, source),
            "actors": [_actor_for(source, action)],
            "props": [],
            "lighting": {"key": "sun", "exposure": 0.1, "contrast": 1.0, "temperature_k": 5600},
            "prompt": {
                "content": str(source.get("description") or source.get("title") or ""),
                "style": str(params.get("style_prompt") or "cinematic anime, grounded 3D composition, consistent character"),
                "negative": "identity drift, extra limbs, camera jump, unreadable face, inconsistent costume",
            },
            "review": {"status": "draft", "revision": 1, "notes": ""},
        })
    return {
        "schema": "cartridgeflow.storyboard_project.v1",
        "protocol": "CF-FARP@0.5",
        "project_id": project_id,
        "title": str(script.get("title") or project_id),
        "source": {"script": script, "shot_list": shot_list, "asset_plan": asset_plan, "action_plan": action_plan},
        "shot_count": len(shots),
        "current_shot_id": shots[0]["id"],
        "shots": shots,
        "approval": {"status": "blocking", "approved_shots": 0, "required_shots": len(shots)},
    }


def _canvas(width: int, height: int, color: tuple[int, int, int]) -> bytearray:
    return bytearray(color * (width * height))


def _rect(pixels: bytearray, width: int, height: int, x0: int, y0: int, x1: int, y1: int, color):
    x0, x1 = max(0, x0), min(width, x1)
    y0, y1 = max(0, y0), min(height, y1)
    for y in range(y0, y1):
        start = (y * width + x0) * 3
        pixels[start:start + (x1 - x0) * 3] = bytes(color) * (x1 - x0)


def _circle(pixels: bytearray, width: int, height: int, cx: int, cy: int, radius: int, color):
    radius2 = radius * radius
    for y in range(max(0, cy - radius), min(height, cy + radius + 1)):
        span = int(math.sqrt(max(0, radius2 - (y - cy) ** 2)))
        _rect(pixels, width, height, cx - span, y, cx + span + 1, y + 1, color)


def _write_png(path: Path, width: int, height: int, pixels: bytearray):
    raw = b"".join(b"\x00" + bytes(pixels[y * width * 3:(y + 1) * width * 3]) for y in range(height))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    payload = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.write_bytes(payload)


def _render_shot(path: Path, shot: dict):
    width, height = 540, 960
    pixels = _canvas(width, height, (207, 220, 218))
    _rect(pixels, width, height, 0, 0, width, 350, (137, 187, 214))
    _rect(pixels, width, height, 0, 350, width, height, (91, 102, 96))
    _rect(pixels, width, height, 0, 385, 155, 760, (183, 187, 174))
    _rect(pixels, width, height, 385, 385, width, 760, (170, 181, 170))
    _rect(pixels, width, height, 175, 350, 365, height, (63, 67, 66))
    actor = (shot.get("actors") or [{}])[0]
    ax = int(270 + float((actor.get("position") or [0])[0]) * 28)
    scale = 1.15 if int(shot.get("order") or 1) % 2 == 0 else 0.95
    _circle(pixels, width, height, ax, int(520 - 55 * scale), int(32 * scale), (215, 171, 132))
    _rect(pixels, width, height, ax - int(42 * scale), int(500), ax + int(42 * scale), int(695), (53, 78, 100))
    _rect(pixels, width, height, ax - int(35 * scale), int(690), ax - 3, int(840), (38, 42, 48))
    _rect(pixels, width, height, ax + 3, int(690), ax + int(35 * scale), int(840), (38, 42, 48))
    _rect(pixels, width, height, 20, 20, width - 20, 24, (238, 79, 65))
    _rect(pixels, width, height, 20, height - 24, width - 20, height - 20, (238, 79, 65))
    _write_png(path, width, height, pixels)


def _save_project(registry, project: dict, output_dir: str) -> tuple[Path, str]:
    target_dir = registry._safe_path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "storyboard_project.json"
    path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, _workspace_rel(registry, path)


def register(registry):
    def build_storyboard_project(params: dict) -> dict:
        try:
            project = _build_project(params)
            output_dir = str(params.get("output_dir") or f"test_output/storyboards/{project['project_id']}")
            path, relative = _save_project(registry, project, output_dir)
            return {"ok": True, "content": json.dumps(project, ensure_ascii=False), "project": project, "path": relative, "files": [relative]}
        except Exception as exc:
            return {"ok": False, "error": f"storyboard project failed: {exc}"}

    def render_storyboard_frames(params: dict) -> dict:
        try:
            project = _project(params.get("storyboard_project") or params.get("project"))
            if project.get("schema") != "cartridgeflow.storyboard_project.v1":
                raise ValueError("storyboard_project.v1 is required")
            output_dir = str(params.get("output_dir") or f"test_output/storyboards/{_slug(project.get('project_id'))}")
            target = registry._safe_path(output_dir)
            target.mkdir(parents=True, exist_ok=True)
            frames = []
            for shot in project.get("shots") or []:
                frame = target / f"{_slug(shot.get('id'))}.png"
                _render_shot(frame, shot)
                relative = _workspace_rel(registry, frame)
                shot["preview_frame"] = relative
                frames.append(relative)
            project_path, project_relative = _save_project(registry, project, output_dir)
            bundle = {"schema": "cartridgeflow.storyboard_frame_bundle.v1", "project": project, "frames": frames, "project_path": project_relative}
            return {"ok": True, "content": json.dumps(bundle, ensure_ascii=False), "bundle": bundle, "path": frames[0] if frames else project_relative, "files": [project_relative, *frames]}
        except Exception as exc:
            return {"ok": False, "error": f"storyboard render failed: {exc}"}

    def apply_storyboard_adjustments(params: dict) -> dict:
        try:
            project = _project(params.get("storyboard_project") or params.get("project"))
            review = _object(params.get("review") or params.get("director_reply") or params.get("adjustments"))
            shots = project.get("shots") or []
            by_id = {str(item.get("id")): item for item in shots if isinstance(item, dict)}
            for change in review.get("shot_changes") or review.get("changes") or []:
                if not isinstance(change, dict) or str(change.get("shot_id")) not in by_id:
                    continue
                shot = by_id[str(change["shot_id"])]
                for field in ["camera", "actors", "props", "lighting", "prompt", "duration_seconds"]:
                    if field in change:
                        shot[field] = deepcopy(change[field])
                shot["review"] = {"status": "draft", "revision": int((shot.get("review") or {}).get("revision") or 1) + 1, "notes": str(change.get("notes") or "")}
            approved_ids = {str(item) for item in (review.get("approved_shot_ids") or review.get("approved_shots") or [])}
            if review.get("approval") in {"approve", "approve_all"} or review.get("status") == "approved":
                if approved_ids:
                    approved_ids &= set(by_id)
                else:
                    approved_ids = set(by_id)
            for shot_id in approved_ids:
                if shot_id in by_id:
                    by_id[shot_id].setdefault("review", {})["status"] = "approved"
            approved = sum(1 for shot in shots if (shot.get("review") or {}).get("status") == "approved")
            project["approval"] = {"status": "approved" if approved == len(shots) and shots else "blocking", "approved_shots": approved, "required_shots": len(shots)}
            output_dir = str(params.get("output_dir") or f"test_output/storyboards/{_slug(project.get('project_id'))}")
            _, relative = _save_project(registry, project, output_dir)
            return {"ok": True, "content": json.dumps(project, ensure_ascii=False), "project": project, "path": relative, "approval": project["approval"], "files": [relative]}
        except Exception as exc:
            return {"ok": False, "error": f"storyboard adjustment failed: {exc}"}

    def prepare_video_shots(params: dict) -> dict:
        try:
            project = _project(params.get("storyboard_project") or params.get("project"))
            shots = project.get("shots") or []
            pending = [str(shot.get("id")) for shot in shots if (shot.get("review") or {}).get("status") != "approved"]
            if pending:
                return {"ok": False, "code": "storyboard_approval_required", "error": "Every storyboard shot must be approved before video generation", "pending_shots": pending}
            package = {
                "schema": "cartridgeflow.video_shot_package.v1",
                "project_id": project.get("project_id"),
                "status": "ready_for_image_reference_generation",
                "shots": [{
                    "id": shot.get("id"),
                    "duration_seconds": shot.get("duration_seconds"),
                    "reference_frame": shot.get("preview_frame"),
                    "camera": shot.get("camera"),
                    "actors": shot.get("actors"),
                    "prompt": shot.get("prompt"),
                } for shot in shots],
                "handoff": {"image_reference": "gpt-image-2_or_configured_provider", "video": "wan2.2", "policy": "one_approved_shot_per_generation_unit"},
            }
            output_dir = str(params.get("output_dir") or f"test_output/storyboards/{_slug(project.get('project_id'))}")
            path = registry._safe_path(output_dir) / "video_shot_package.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
            relative = _workspace_rel(registry, path)
            return {"ok": True, "content": json.dumps(package, ensure_ascii=False), "package": package, "path": relative, "files": [relative]}
        except Exception as exc:
            return {"ok": False, "error": f"video shot preparation failed: {exc}"}

    registry._registry["media"].update({
        "build_storyboard_project": build_storyboard_project,
        "render_storyboard_frames": render_storyboard_frames,
        "apply_storyboard_adjustments": apply_storyboard_adjustments,
        "prepare_video_shots": prepare_video_shots,
    })
