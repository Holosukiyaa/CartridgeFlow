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
    "confirm_storyboard_plan",
    "build_storyboard_project",
    "render_storyboard_frames",
    "apply_storyboard_adjustments",
    "prepare_video_shots",
]

_ACTION_ALIASES = {
    "sitting_reading": "sit_reading",
    "reading": "sit_reading",
    "read": "sit_reading",
    "hand_tracing_text": "page_turn",
    "turn_page": "page_turn",
    "turning_page": "page_turn",
    "look_up_thoughtfully": "look_up",
    "reading_then_looking_up": "sit_reading",
    "looking_up_smiling": "sit_reading",
    "tracking_butterfly_closing_book": "sit_reading",
    "closing_book": "page_turn",
    "watching_butterfly": "sit_reading",
    "return_to_reading_with_smile": "sit_reading",
    "walk_forward": "walk_slow",
    "walk_backward": "walk_slow",
    "talking": "idle_talk",
    "interact": "gesture_interact",
}


def _normalize_action_id(value: str, fallback: str = "idle_hold") -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _ACTION_ALIASES.get(raw, raw or fallback)


def _normalize_actor(actor: dict) -> dict:
    item = deepcopy(actor) if isinstance(actor, dict) else {}
    item["action"] = _normalize_action_id(item.get("action"))
    available = item.get("available_actions")
    if isinstance(available, list):
        item["available_actions"] = list(dict.fromkeys(_normalize_action_id(value) for value in available if value))
    if item["action"] not in item.get("available_actions", []):
        item.setdefault("available_actions", []).append(item["action"])
    return item


def _normalize_project_actions(project: dict) -> dict:
    normalized = deepcopy(project)
    for shot in normalized.get("shots") or []:
        if isinstance(shot, dict) and isinstance(shot.get("actors"), list):
            shot["actors"] = [_normalize_actor(actor) for actor in shot["actors"]]
    return normalized


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


def _vector(value, fallback: list[float], length: int = 3) -> list[float]:
    if isinstance(value, (list, tuple)) and len(value) >= length:
        try:
            return [float(value[index]) for index in range(length)]
        except (TypeError, ValueError):
            pass
    return deepcopy(fallback)


def _scene_for(index: int, shot: dict) -> dict:
    raw = shot.get("scene_design") or shot.get("scene") or {}
    design = raw if isinstance(raw, dict) else {"location": str(raw)}
    requested_location = str(design.get("location") or design.get("name") or shot.get("location") or "").strip()
    text = " ".join([
        requested_location,
        str(shot.get("title") or ""),
        str(shot.get("description") or ""),
    ]).lower()
    archetypes = [
        (("bedroom", "卧室", "房间", "室内"), "bedroom"),
        (("classroom", "教室", "学校"), "classroom"),
        (("cafe", "咖啡", "餐厅"), "cafe"),
        (("roof", "天台", "屋顶"), "rooftop"),
        (("forest", "树林", "森林", "公园"), "forest"),
        (("alley", "巷", "拐角"), "alley"),
        (("street", "街", "道路", "路口", "人行道", "住宅"), "street"),
    ]
    archetype = next((name for words, name in archetypes if any(word in text for word in words)), "studio")
    location = requested_location or {
        "bedroom": "卧室",
        "classroom": "教室",
        "cafe": "咖啡店",
        "rooftop": "建筑天台",
        "forest": "公园林地",
        "alley": "城市巷道",
        "street": "城市街道",
        "studio": "抽象预演场",
    }[archetype]
    palette_by_archetype = {
        "bedroom": {"sky": "#707b8d", "ground": "#765f53", "accent": "#e2ad69"},
        "classroom": {"sky": "#a7c6cf", "ground": "#6d745e", "accent": "#d3b45f"},
        "cafe": {"sky": "#765e54", "ground": "#4d4540", "accent": "#d78e58"},
        "rooftop": {"sky": "#789cb4", "ground": "#626a6d", "accent": "#db6554"},
        "forest": {"sky": "#71908a", "ground": "#465747", "accent": "#d7b85d"},
        "alley": {"sky": "#657381", "ground": "#4c5052", "accent": "#ca6657"},
        "street": {"sky": "#82afc4", "ground": "#5b625e", "accent": "#d45f50"},
        "studio": {"sky": "#747e85", "ground": "#505557", "accent": "#d29a50"},
    }
    palette = deepcopy(palette_by_archetype[archetype])
    if isinstance(design.get("palette"), dict):
        palette.update({key: value for key, value in design["palette"].items() if key in palette})
    layouts = {
        "street": [
            {"kind": "building", "position": [-4.8, 2.2, 1.6], "scale": [3.0, 2.2, 3.2], "color": "#a8afa7"},
            {"kind": "building", "position": [4.6, 4.2, 2.2], "scale": [2.5, 2.4, 4.4], "color": "#8fa29a"},
            {"kind": "tree", "position": [-2.8, 0.2, 0.0], "scale": [1.0, 1.0, 1.0], "color": "#607a61"},
        ],
        "alley": [
            {"kind": "wall", "position": [-3.5, 1.0, 1.8], "scale": [1.0, 7.0, 3.6], "color": "#777a78"},
            {"kind": "wall", "position": [3.5, 1.8, 2.1], "scale": [1.0, 7.0, 4.2], "color": "#666e70"},
            {"kind": "lamp", "position": [2.8, -0.5, 0.0], "scale": [1.0, 1.0, 1.0], "color": "#d7a755"},
        ],
        "bedroom": [
            {"kind": "wall", "position": [0.0, 3.8, 1.7], "scale": [8.0, 0.4, 3.4], "color": "#8b8585"},
            {"kind": "bed", "position": [-2.0, 1.2, 0.35], "scale": [2.8, 4.0, 0.7], "color": "#596b7c"},
            {"kind": "window", "position": [2.0, 3.45, 1.8], "scale": [1.7, 0.2, 1.8], "color": "#9dc2cb"},
        ],
        "classroom": [
            {"kind": "wall", "position": [0.0, 4.5, 1.8], "scale": [9.0, 0.4, 3.6], "color": "#a7aaa1"},
            {"kind": "board", "position": [0.0, 4.2, 1.9], "scale": [4.5, 0.2, 1.8], "color": "#355b50"},
            {"kind": "desk", "position": [-2.2, 0.7, 0.45], "scale": [2.0, 1.2, 0.9], "color": "#96704e"},
            {"kind": "desk", "position": [2.0, 1.8, 0.45], "scale": [2.0, 1.2, 0.9], "color": "#96704e"},
        ],
        "cafe": [
            {"kind": "counter", "position": [2.8, 2.8, 0.65], "scale": [2.2, 4.0, 1.3], "color": "#76523e"},
            {"kind": "table", "position": [-1.5, 0.8, 0.5], "scale": [1.5, 1.5, 1.0], "color": "#9a704c"},
            {"kind": "lamp", "position": [-1.5, 0.8, 2.5], "scale": [1.0, 1.0, 1.0], "color": "#d69252"},
        ],
        "rooftop": [
            {"kind": "wall", "position": [0.0, 5.0, 0.55], "scale": [10.0, 0.5, 1.1], "color": "#858c8d"},
            {"kind": "vent", "position": [-2.7, 2.0, 0.7], "scale": [1.4, 1.4, 1.4], "color": "#71797c"},
            {"kind": "building", "position": [5.5, 8.0, 2.5], "scale": [3.0, 2.0, 5.0], "color": "#78868b"},
        ],
        "forest": [
            {"kind": "tree", "position": [-3.2, 1.0, 0.0], "scale": [1.2, 1.2, 1.2], "color": "#49654d"},
            {"kind": "tree", "position": [3.5, 3.0, 0.0], "scale": [1.4, 1.4, 1.4], "color": "#3f5d48"},
            {"kind": "rock", "position": [1.8, 0.0, 0.45], "scale": [1.7, 1.2, 0.9], "color": "#777d76"},
        ],
        "studio": [
            {"kind": "wall", "position": [0.0, 4.5, 1.8], "scale": [9.0, 0.4, 3.6], "color": "#777f82"},
            {"kind": "platform", "position": [0.0, 0.8, 0.15], "scale": [4.0, 4.0, 0.3], "color": "#686e70"},
        ],
    }
    objects = deepcopy(layouts[archetype])
    provided = design.get("landmarks") or design.get("objects")
    if isinstance(provided, list):
        for item_index, item in enumerate(provided[:6]):
            if isinstance(item, dict):
                objects.append({
                    "kind": str(item.get("kind") or item.get("type") or "prop"),
                    "position": _vector(item.get("position"), [float(item_index - 2), 2.5, 0.5]),
                    "scale": _vector(item.get("scale"), [1.0, 1.0, 1.0]),
                    "color": str(item.get("color") or palette["accent"]),
                })
            elif item:
                objects.append({"kind": str(item), "position": [float(item_index - 2), 2.5, 0.5], "scale": [1.0, 1.0, 1.0], "color": palette["accent"]})
    return {
        "asset_id": str(design.get("asset_id") or f"blocking_{archetype}"),
        "label": location,
        "location": location,
        "archetype": archetype,
        "time": str(design.get("time") or shot.get("time") or "day"),
        "weather": str(design.get("weather") or shot.get("weather") or "clear"),
        "palette": palette,
        "environment": objects,
        "blocking_notes": str(design.get("blocking_notes") or shot.get("composition") or shot.get("description") or ""),
        "variation": index,
    }


def _camera_for(index: int, shot: dict) -> dict:
    raw = shot.get("camera")
    raw_camera = raw if isinstance(raw, dict) else {}
    template = str(raw_camera.get("template") or raw or shot.get("camera_movement") or "slow_push_in")
    presets = {
        "slow_push_in": {"position": [0.0, -8.0, 2.1], "target": [0.0, 0.0, 1.2], "focal_length_mm": 42},
        "close_up_reveal": {"position": [1.4, -3.8, 1.8], "target": [0.0, 0.0, 1.45], "focal_length_mm": 68},
        "over_shoulder": {"position": [-1.8, -4.8, 1.9], "target": [0.2, 0.5, 1.35], "focal_length_mm": 52},
        "low_angle_hold": {"position": [1.1, -5.5, 0.75], "target": [0.0, 0.5, 1.35], "focal_length_mm": 38},
    }
    fallback_names = list(presets)
    if template not in presets:
        template = fallback_names[index % len(fallback_names)]
    camera = deepcopy(presets[template])
    camera["position"] = _vector(raw_camera.get("position"), camera["position"])
    camera["target"] = _vector(raw_camera.get("target"), camera["target"])
    if raw_camera.get("focal_length_mm") is not None:
        camera["focal_length_mm"] = float(raw_camera["focal_length_mm"])
    camera.update({"template": template, "safe_frame": "9:16", "index": index, "view_mode": "shot_camera"})
    return camera


def _actor_for(index: int, shot: dict, action: str, actor_index: int, actor_id: str) -> dict:
    raw_blocking = shot.get("actor_blocking") or shot.get("blocking") or {}
    candidates = raw_blocking if isinstance(raw_blocking, list) else raw_blocking.get("actors", []) if isinstance(raw_blocking, dict) and isinstance(raw_blocking.get("actors"), list) else []
    blocking = next((item for item in candidates if isinstance(item, dict) and str(item.get("actor_id") or item.get("id") or "") == actor_id), None)
    if blocking is None and actor_index < len(candidates) and isinstance(candidates[actor_index], dict):
        blocking = candidates[actor_index]
    if blocking is None:
        blocking = raw_blocking if actor_index == 0 and isinstance(raw_blocking, dict) else {}
    default_positions = [[0.0, 0.2, 0.0], [-0.9, 0.8, 0.0], [0.8, 1.4, 0.0], [0.0, 2.0, 0.0]]
    base_position = deepcopy(default_positions[(index + actor_index) % len(default_positions)])
    if actor_index:
        base_position[0] += 1.6 * actor_index
    return {
        "id": actor_id,
        "asset_id": "pilot_male_hero",
        "cast_character_id": "pilot_vroid_boy_01",
        "asset_format": "gltf",
        "director_asset_path": "dlc/frontend/models/boy1.vrm",
        "director_asset_format": "vrm",
        "rig_profile": "vrm1_humanoid_54",
        "position": _vector(blocking.get("position"), base_position),
        "rotation_degrees": _vector(blocking.get("rotation_degrees"), [0.0, 0.0, float((index % 3 - 1) * 18)]),
        "scale": 1.0,
        "action": _normalize_action_id(blocking.get("action") or (action if actor_index == 0 else "idle_talk")),
        "pose_time": float(blocking.get("pose_time") or (0.22 + (index % 4) * 0.19)),
        "available_actions": ["idle_hold", "walk_slow", "idle_talk", "gesture_interact", "look_back", "run_short", "sit_idle", "sit_reading", "page_turn", "look_up", "point_forward", "pick_up"],
        "gaze_target": [0.0, -4.0, 1.4],
        "expression": str(blocking.get("expression") or "auto"),
        "expression_weight": float(blocking.get("expression_weight") if blocking.get("expression_weight") is not None else 0.65),
        "gaze_yaw_degrees": float(blocking.get("gaze_yaw_degrees") or 0.0),
        "gaze_pitch_degrees": float(blocking.get("gaze_pitch_degrees") or 0.0),
        "head_pitch_degrees": float(blocking.get("head_pitch_degrees") or 0.0),
        "head_yaw_degrees": float(blocking.get("head_yaw_degrees") or 0.0),
        "left_arm_raise_degrees": float(blocking.get("left_arm_raise_degrees") or 0.0),
        "right_arm_raise_degrees": float(blocking.get("right_arm_raise_degrees") or 0.0),
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
    action_items = {
        str(item.get("shot_id") or item.get("id")): item
        for item in (action_plan.get("shots") or action_plan.get("assignments") or [])
        if isinstance(item, dict)
    }
    shots = []
    for index, source in enumerate(source_shots[:10]):
        shot_id = str(source.get("id") or f"shot_{index + 1:02d}")
        action_item = action_items.get(shot_id) or {}
        primary_action = action_item.get("primary_action") if isinstance(action_item.get("primary_action"), dict) else {}
        action = _normalize_action_id(primary_action.get("id") or action_item.get("action_id") or action_item.get("action") or (source.get("action_tags") or ["idle_hold"])[0])
        planned_source = deepcopy(source)
        planned_camera = action_item.get("camera_template") if isinstance(action_item.get("camera_template"), dict) else {}
        if not isinstance(source.get("camera"), dict) and planned_camera.get("id"):
            planned_source["camera"] = str(planned_camera["id"])
        scene = _scene_for(index, source)
        source_props = source.get("props") if isinstance(source.get("props"), list) else []
        actor_ids = source.get("characters") or source.get("actors") or source.get("cast") or ["hero"]
        if not isinstance(actor_ids, list):
            actor_ids = [actor_ids]
        actor_ids = [str(value or f"actor_{actor_index + 1}") for actor_index, value in enumerate(actor_ids[:3])]
        shots.append({
            "id": shot_id,
            "order": index + 1,
            "title": str(source.get("title") or f"Shot {index + 1}"),
            "intent": str(source.get("description") or ""),
            "duration_seconds": float(source.get("duration") or 3.0),
            "scene": scene,
            "camera": _camera_for(index, planned_source),
            "actors": [_actor_for(index, source, action, actor_index, actor_id) for actor_index, actor_id in enumerate(actor_ids)],
            "props": [{"id": str(item), "position": [float(pos - 1), 1.8, 0.35]} for pos, item in enumerate(source_props[:4])],
            "lighting": {
                "key": str((source.get("lighting") or {}).get("key") if isinstance(source.get("lighting"), dict) else source.get("lighting") or "sun"),
                "exposure": float((source.get("lighting") or {}).get("exposure", 0.1) if isinstance(source.get("lighting"), dict) else 0.1),
                "contrast": 1.0,
                "temperature_k": 5600 if scene["time"] in {"day", "morning", "白天", "早晨"} else 3900,
            },
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


def _line(pixels: bytearray, width: int, height: int, x0: int, y0: int, x1: int, y1: int, thickness: int, color):
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for step in range(steps + 1):
        amount = step / steps
        x = int(x0 + (x1 - x0) * amount)
        y = int(y0 + (y1 - y0) * amount)
        _circle(pixels, width, height, x, y, thickness, color)


def _rgb(value, fallback=(128, 128, 128)):
    text = str(value or "").lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    try:
        return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4)) if len(text) == 6 else fallback
    except ValueError:
        return fallback


def _write_png(path: Path, width: int, height: int, pixels: bytearray):
    raw = b"".join(b"\x00" + bytes(pixels[y * width * 3:(y + 1) * width * 3]) for y in range(height))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    payload = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.write_bytes(payload)


def _render_shot(path: Path, shot: dict):
    width, height = 540, 960
    scene = shot.get("scene") if isinstance(shot.get("scene"), dict) else {}
    palette = scene.get("palette") if isinstance(scene.get("palette"), dict) else {}
    sky = _rgb(palette.get("sky"), (137, 187, 214))
    ground = _rgb(palette.get("ground"), (91, 102, 96))
    accent = _rgb(palette.get("accent"), (212, 95, 80))
    time_name = str(scene.get("time") or "day").lower()
    if time_name in {"night", "evening", "夜晚", "晚上", "黄昏"}:
        sky = tuple(max(12, int(channel * 0.48)) for channel in sky)
        ground = tuple(max(12, int(channel * 0.58)) for channel in ground)
    pixels = _canvas(width, height, sky)
    horizon = 365
    _rect(pixels, width, height, 0, horizon, width, height, ground)
    camera = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
    camera_position = _vector(camera.get("position"), [0.0, -8.0, 2.1])
    camera_target = _vector(camera.get("target"), [0.0, 0.0, 1.2])
    focal = max(18.0, min(120.0, float(camera.get("focal_length_mm") or 42.0)))
    view_scale = 0.72 + focal / 120.0
    camera_pan = camera_position[0] * 18.0 - camera_target[0] * 12.0
    for item in scene.get("environment") or []:
        if not isinstance(item, dict):
            continue
        position = _vector(item.get("position"), [0.0, 2.0, 0.0])
        scale = _vector(item.get("scale"), [1.0, 1.0, 1.0])
        depth = max(0.5, position[1] - camera_position[1])
        perspective = max(0.35, min(1.8, 9.5 / depth)) * view_scale
        cx = int(width / 2 + position[0] * 43 * perspective - camera_pan)
        floor_y = int(horizon + 250 / max(0.75, depth * 0.16))
        object_width = max(12, int(scale[0] * 42 * perspective))
        object_height = max(18, int(scale[2] * 82 * perspective))
        color = _rgb(item.get("color"), accent)
        kind = str(item.get("kind") or "prop")
        if kind in {"tree"}:
            _rect(pixels, width, height, cx - 7, floor_y - object_height // 2, cx + 7, floor_y, (83, 66, 48))
            _circle(pixels, width, height, cx, floor_y - object_height, max(16, object_width // 2), color)
        elif kind in {"lamp"}:
            _rect(pixels, width, height, cx - 3, floor_y - object_height, cx + 3, floor_y, (61, 64, 65))
            _circle(pixels, width, height, cx, floor_y - object_height, max(8, object_width // 4), color)
        else:
            _rect(pixels, width, height, cx - object_width // 2, floor_y - object_height, cx + object_width // 2, floor_y, color)
    wardrobe = [(53, 78, 100), (123, 78, 91), (77, 102, 80)]
    for actor_index, actor in enumerate(shot.get("actors") or [{}]):
        actor_position = _vector(actor.get("position"), [0.0, 0.0, 0.0])
        depth = max(1.0, actor_position[1] - camera_position[1])
        scale = max(0.48, min(1.65, 9.0 / depth)) * view_scale
        ax = int(width / 2 + actor_position[0] * 44 * scale - camera_pan)
        feet_y = int(horizon + 470 / max(0.82, depth * 0.13))
        body_top = int(feet_y - 205 * scale)
        head_y = int(body_top - 34 * scale)
        body_color = wardrobe[actor_index % len(wardrobe)]
        _circle(pixels, width, height, ax, head_y, max(12, int(29 * scale)), (215, 171, 132))
        _rect(pixels, width, height, ax - int(35 * scale), body_top, ax + int(35 * scale), int(body_top + 135 * scale), body_color)
        phase = float(actor.get("pose_time") or 0.0) * math.tau
        action = str(actor.get("action") or "idle_hold")
        stride = math.sin(phase) * (38 if action in {"walk_slow", "run_short"} else 8) * scale
        gesture = math.sin(phase * 0.5) * 45 * scale if action in {"gesture_interact", "idle_talk", "look_back"} else 8 * scale
        hip_y = int(body_top + 125 * scale)
        _line(pixels, width, height, ax - int(16 * scale), hip_y, ax - int(18 * scale + stride), feet_y, max(4, int(8 * scale)), (38, 42, 48))
        _line(pixels, width, height, ax + int(16 * scale), hip_y, ax + int(18 * scale + stride), feet_y, max(4, int(8 * scale)), (38, 42, 48))
        shoulder_y = int(body_top + 35 * scale)
        _line(pixels, width, height, ax - int(30 * scale), shoulder_y, ax - int(42 * scale + gesture), int(body_top + 115 * scale), max(3, int(7 * scale)), body_color)
        _line(pixels, width, height, ax + int(30 * scale), shoulder_y, ax + int(42 * scale + gesture), int(body_top + 105 * scale - gesture), max(3, int(7 * scale)), body_color)
    _rect(pixels, width, height, 20, 20, width - 20, 24, accent)
    _rect(pixels, width, height, 20, height - 24, width - 20, height - 20, accent)
    _write_png(path, width, height, pixels)


def _save_project(registry, project: dict, output_dir: str) -> tuple[Path, str]:
    target_dir = registry._safe_path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "storyboard_project.json"
    path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, _workspace_rel(registry, path)


def register(registry):
    def confirm_storyboard_plan(params: dict) -> dict:
        try:
            decision = _object(params.get("shot_list_decision") or params.get("decision"))
            reply = _object(params.get("shot_reply") or params.get("reply"))
            status = str(decision.get("status") or "").strip()
            approval = str(reply.get("approval") or "").strip()
            if status == "needs_user_input" and approval not in {"approve", "approve_all"}:
                raise ValueError("approved shot_reply is required for a pending storyboard proposal")
            payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
            shot_list = payload.get("shot_list") or payload.get("draft_shot_list") or decision.get("shot_list") or decision.get("draft_shot_list")
            if isinstance(shot_list, list):
                shot_list = {"schema": "shot_list.v1", "shots": shot_list}
            if not isinstance(shot_list, dict) or not _shots(shot_list):
                raise ValueError("decision does not contain payload.shot_list or payload.draft_shot_list")
            shot_list = deepcopy(shot_list)
            shot_list.setdefault("schema", "shot_list.v1")
            return {
                "ok": True,
                "content": json.dumps(shot_list, ensure_ascii=False),
                "shot_list": shot_list,
                "source_status": status,
                "approval": approval or "implicit_resolved",
            }
        except Exception as exc:
            return {"ok": False, "error": f"storyboard plan confirmation failed: {exc}"}

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
            project = _normalize_project_actions(_project(params.get("storyboard_project") or params.get("project")))
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
            project = _normalize_project_actions(_project(params.get("storyboard_project") or params.get("project")))
            review = _object(params.get("review") or params.get("director_reply") or params.get("adjustments"))
            shots = project.get("shots") or []
            by_id = {str(item.get("id")): item for item in shots if isinstance(item, dict)}
            for change in review.get("shot_changes") or review.get("changes") or []:
                if not isinstance(change, dict) or str(change.get("shot_id")) not in by_id:
                    continue
                shot = by_id[str(change["shot_id"])]
                for field in ["camera", "actors", "props", "lighting", "prompt", "duration_seconds"]:
                    if field in change:
                        shot[field] = [_normalize_actor(actor) for actor in change[field]] if field == "actors" and isinstance(change[field], list) else deepcopy(change[field])
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
            project = _normalize_project_actions(_project(params.get("storyboard_project") or params.get("project")))
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
                    "scene": shot.get("scene"),
                    "camera": shot.get("camera"),
                    "actors": shot.get("actors"),
                    "props": shot.get("props"),
                    "lighting": shot.get("lighting"),
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
        "confirm_storyboard_plan": confirm_storyboard_plan,
        "build_storyboard_project": build_storyboard_project,
        "render_storyboard_frames": render_storyboard_frames,
        "apply_storyboard_adjustments": apply_storyboard_adjustments,
        "prepare_video_shots": prepare_video_shots,
    })
