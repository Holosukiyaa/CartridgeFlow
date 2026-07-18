from __future__ import annotations

import base64
import html
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
import zlib
from pathlib import Path

from . import shared as _shared

for _name in dir(_shared):
    if _name.startswith("_"):
        globals()[_name] = getattr(_shared, _name)

DLC_ID = 'dlc.spatial_blockout'
DLC_PROTOCOL = 'CF-FARP@0.4'
TOOLS = ['forge_spatial_blockout']

def _normalize_spatial_layer_name(value) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "front": "foreground",
        "foregrounds": "foreground",
        "foreground_layer": "foreground",
        "fg": "foreground",
        "mid": "midground",
        "middle": "midground",
        "middleground": "midground",
        "center": "midground",
        "bg": "background",
        "back": "background",
        "backgrounds": "background",
        "rear": "background",
    }
    if text in {"foreground", "midground", "background"}:
        return text
    return aliases.get(text, "")

def _normalize_spatial_blockout_spec(value, title: str) -> dict:
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                value = json.loads(text)
            except Exception:
                value = {"title": title, "prompt": text}
        else:
            value = {}
    if not isinstance(value, dict):
        value = {}
    if isinstance(value.get("scene_blockout"), dict):
        value = value["scene_blockout"]
    elif isinstance(value.get("payload"), dict) and isinstance(value["payload"].get("scene_blockout"), dict):
        value = value["payload"]["scene_blockout"]
    scene_title = str(value.get("title") or value.get("scene") or title or "Spatial Blockout").strip()
    raw_objects = value.get("objects") or value.get("assets") or value.get("elements") or []
    if isinstance(raw_objects, dict):
        raw_objects = list(raw_objects.values())
    objects = []
    for index, item in enumerate(raw_objects if isinstance(raw_objects, list) else []):
        if isinstance(item, dict):
            objects.extend(_expand_spatial_blockout_object(item, index))
    if not objects:
        objects = _default_spatial_blockout_objects(value)
    def _list_ids(raw_value) -> list[str]:
        if isinstance(raw_value, str):
            parts = re.split(r"[,\n、|]+", raw_value)
            return [piece.strip() for piece in parts if piece.strip()]
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        if isinstance(raw_value, dict):
            return [str(key).strip() for key, enabled in raw_value.items() if enabled and str(key).strip()]
        return []

    composition_raw = value.get("composition") if isinstance(value.get("composition"), dict) else {}
    foreground_ids = _list_ids(
        composition_raw.get("foreground")
        or composition_raw.get("foreground_ids")
        or composition_raw.get("front")
        or composition_raw.get("front_ids")
        or value.get("foreground")
    )
    midground_ids = _list_ids(
        composition_raw.get("midground")
        or composition_raw.get("midground_ids")
        or composition_raw.get("middle")
        or composition_raw.get("middle_ids")
        or value.get("midground")
    )
    background_ids = _list_ids(
        composition_raw.get("background")
        or composition_raw.get("background_ids")
        or composition_raw.get("back")
        or composition_raw.get("back_ids")
        or value.get("background")
    )
    focus_ids = _list_ids(
        composition_raw.get("focus")
        or composition_raw.get("focus_ids")
        or composition_raw.get("subject")
        or composition_raw.get("subject_ids")
        or value.get("focus")
    )
    composition = {
        "schema": "scene_composition.v1",
        "goal": str(composition_raw.get("goal") or value.get("composition_goal") or value.get("goal") or "").strip(),
        "foreground": foreground_ids,
        "midground": midground_ids,
        "background": background_ids,
        "focus": focus_ids,
        "subject_scale": str(composition_raw.get("subject_scale") or value.get("subject_scale") or "").strip(),
        "depth_rules": [str(item).strip() for item in (composition_raw.get("depth_rules") or composition_raw.get("rules") or []) if str(item).strip()] if isinstance(composition_raw.get("depth_rules") or composition_raw.get("rules") or [], list) else [],
        "notes": str(composition_raw.get("notes") or value.get("composition_notes") or "").strip(),
    }
    camera = value.get("camera") if isinstance(value.get("camera"), dict) else {}
    camera_spec = {
        "position": _vec3(camera.get("position"), [4.5, 4.0, 6.0]),
        "look_at": _vec3(camera.get("look_at"), [0.0, 0.8, 0.0]),
        "lens_mm": _clamp_float(camera.get("lens_mm") or camera.get("focal_length"), 18.0, 120.0, 35.0),
        "movement": str(camera.get("movement") or camera.get("motion") or "slow_push_in").strip(),
        "distance": str(camera.get("distance") or camera.get("framing") or "medium_close").strip(),
        "focus_target": str(camera.get("focus_target") or camera.get("focus") or _spatial_primary_object_id(objects, {"character", "hero", "person"}) or "").strip(),
    }
    timeline = _normalize_spatial_animation_timeline(value, objects, camera_spec)
    layer_order = {"background": 0, "midground": 1, "foreground": 2}
    layer_lookup = {}
    for item in objects:
        if not isinstance(item, dict):
            continue
        item_layer = _normalize_spatial_layer_name(item.get("layer") or item.get("depth_layer"))
        item_id = str(item.get("id") or "").strip()
        if item_id in foreground_ids:
            item_layer = "foreground"
        elif item_id in midground_ids:
            item_layer = "midground"
        elif item_id in background_ids:
            item_layer = "background"
        if not item_layer:
            raw_type = str(item.get("type") or "").strip().lower()
            if raw_type in {"ground", "floor", "plane"} or any(tag in raw_type for tag in {"background", "wall", "architecture", "building", "sky"}):
                item_layer = "background"
            elif any(tag in raw_type for tag in {"character", "person", "hero", "subject"}):
                item_layer = "foreground"
            else:
                item_layer = "midground"
        item["layer"] = item_layer
        try:
            depth_order = int(item.get("depth_order"))
        except Exception:
            depth_order = layer_order.get(item_layer, 1) * 100
        item["depth_order"] = depth_order
        if item_id:
            layer_lookup[item_id] = item_layer
    if not composition["foreground"]:
        composition["foreground"] = [item_id for item_id, layer in layer_lookup.items() if layer == "foreground"]
    if not composition["midground"]:
        composition["midground"] = [item_id for item_id, layer in layer_lookup.items() if layer == "midground"]
    if not composition["background"]:
        composition["background"] = [item_id for item_id, layer in layer_lookup.items() if layer == "background"]
    if not composition["focus"]:
        composition["focus"] = [item_id for item_id, layer in layer_lookup.items() if layer == "foreground"][:2]
    return {
        "schema": "scene_animation.v1",
        "title": scene_title,
        "unit": "meter",
        "style": str(value.get("style") or "low_poly_animation_previz"),
        "composition": composition,
        "objects": objects,
        "camera": camera_spec,
        "timeline": timeline,
        "notes": str(value.get("notes") or value.get("prompt") or "Local deterministic 3D animation preview."),
    }

def _normalize_spatial_animation_timeline(value: dict, objects: list[dict], camera: dict) -> dict:
    raw = value.get("timeline") or value.get("animation") or value.get("motion") or {}
    if not isinstance(raw, dict):
        raw = {}
    try:
        duration = float(raw.get("duration_seconds") or raw.get("duration") or value.get("duration_seconds") or 6.0)
    except Exception:
        duration = 6.0
    duration = max(2.0, min(30.0, duration))
    tracks = raw.get("tracks") if isinstance(raw.get("tracks"), list) else []
    normalized_tracks = []
    for item in tracks:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or item.get("id") or "").strip()
        prop = str(item.get("property") or item.get("prop") or "position").strip()
        frames = item.get("keyframes") if isinstance(item.get("keyframes"), list) else []
        keyframes = []
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            keyframes.append({
                "time": _clamp_float(frame.get("time"), 0.0, duration, 0.0),
                "value": _timeline_value(frame.get("value")),
            })
        if target and keyframes:
            normalized_tracks.append({"target": target, "property": prop, "keyframes": keyframes})
    if not normalized_tracks:
        normalized_tracks = _default_spatial_animation_tracks(objects, duration)

    camera_track = raw.get("camera") if isinstance(raw.get("camera"), list) else []
    normalized_camera = []
    for frame in camera_track:
        if not isinstance(frame, dict):
            continue
        normalized_camera.append({
            "time": _clamp_float(frame.get("time"), 0.0, duration, 0.0),
            "position": _vec3(frame.get("position"), camera.get("position") or [4.5, 4.0, 6.0]),
            "look_at": _vec3(frame.get("look_at"), camera.get("look_at") or [0.0, 0.8, 0.0]),
        })
    if not normalized_camera:
        normalized_camera = [
            {"time": 0.0, "position": camera.get("position") or [4.5, 4.0, 6.0], "look_at": camera.get("look_at") or [0.0, 0.8, 0.0]},
            {"time": duration, "position": [3.2, 2.8, 4.2], "look_at": [0.0, 0.9, 0.2]},
        ]

    events = raw.get("events") if isinstance(raw.get("events"), list) else []
    normalized_events = []
    for event in events:
        if not isinstance(event, dict):
            continue
        normalized_events.append({
            "time": _clamp_float(event.get("time"), 0.0, duration, 0.0),
            "type": str(event.get("type") or "beat").strip(),
            "target": str(event.get("target") or "").strip(),
            "label": str(event.get("label") or event.get("name") or "").strip(),
        })
    if not normalized_events:
        hero_id = _spatial_primary_object_id(objects, {"character", "hero", "person"}) or "hero"
        normalized_events = [
            {"time": duration * 0.34, "type": "gesture", "target": hero_id, "label": "抬手"},
            {"time": duration * 0.56, "type": "smoke_puff", "target": hero_id, "label": "烟雾"},
            {"time": duration * 0.78, "type": "warning_light", "target": "warning_light", "label": "警示灯闪烁"},
        ]

    return {
        "duration_seconds": duration,
        "fps": int(raw.get("fps") or 24),
        "tracks": normalized_tracks,
        "camera": normalized_camera,
        "events": normalized_events,
    }

def _default_spatial_animation_tracks(objects: list[dict], duration: float) -> list[dict]:
    hero_id = _spatial_primary_object_id(objects, {"character", "hero", "person"}) or "hero"
    light_id = _spatial_primary_object_id(objects, {"warning_light", "light", "lamp"}) or "warning_light"
    hero_obj = next((item for item in objects if str(item.get("id")) == hero_id), None) or {}
    start = _vec3(hero_obj.get("position"), [0.0, 0.85, 0.0])
    return [
        {
            "target": hero_id,
            "property": "offset",
            "keyframes": [
                {"time": 0.0, "value": [-0.65, 0.0, 0.35]},
                {"time": duration * 0.45, "value": [0.0, 0.0, 0.0]},
                {"time": duration, "value": [0.18, 0.0, -0.08]},
            ],
        },
        {
            "target": hero_id,
            "property": "pose",
            "keyframes": [
                {"time": 0.0, "value": "walk"},
                {"time": duration * 0.46, "value": "smoke"},
                {"time": duration, "value": "idle"},
            ],
        },
        {
            "target": light_id,
            "property": "pulse",
            "keyframes": [
                {"time": 0.0, "value": 0.2},
                {"time": duration * 0.5, "value": 1.0},
                {"time": duration, "value": 0.35},
            ],
        },
    ]

def _spatial_primary_object_id(objects: list[dict], type_hints: set[str]) -> str:
    for item in objects:
        raw = f"{item.get('id', '')} {item.get('type', '')} {item.get('name', '')}".lower()
        if any(hint in raw for hint in type_hints):
            return str(item.get("id") or "").strip()
    return ""

def _timeline_value(value):
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _timeline_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_timeline_value(item) for item in value]
    return value

def _clamp_float(value, minimum: float, maximum: float, fallback: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = fallback
    return max(minimum, min(maximum, number))

def _default_spatial_blockout_objects(value: dict) -> list[dict]:
    accent = _spatial_color(value.get("accent_color") or "red")
    return [
        {"id": "ground", "type": "ground", "name": "Ground plane", "position": [0, -0.04, 0], "size": [7.0, 0.08, 5.0], "color": [0.46, 0.44, 0.40, 1.0], "layer": "background", "depth_order": 0},
        {"id": "hero", "type": "character", "name": "Hero blockout", "position": [0, 0.85, 0], "size": [0.55, 1.7, 0.38], "color": _spatial_color("blue"), "layer": "foreground", "depth_order": 200},
        {"id": "entrance", "type": "architecture", "name": "Entrance mass", "position": [0, 1.25, 1.8], "size": [2.8, 2.5, 0.28], "color": [0.32, 0.34, 0.36, 1.0], "layer": "midground", "depth_order": 100},
        {"id": "warning_light", "type": "prop", "name": "Warning light", "position": [2.2, 1.5, -0.8], "size": [0.32, 0.32, 0.32], "color": accent, "layer": "background", "depth_order": 20},
    ]

def _expand_spatial_blockout_object(item: dict, index: int) -> list[dict]:
    raw_type = str(item.get("type") or item.get("kind") or "box").strip().lower()
    name = str(item.get("name") or item.get("id") or f"object_{index + 1}").strip()
    obj_id = _safe_slug(str(item.get("id") or name or f"object_{index + 1}"))
    position = _vec3(item.get("position"), [0.0, 0.0, 0.0])
    size = _spatial_size(raw_type, item)
    color = _spatial_color(item.get("color") or item.get("material") or raw_type)
    layer = _normalize_spatial_layer_name(item.get("layer") or item.get("depth_layer"))
    try:
        depth_order = int(item.get("depth_order"))
    except Exception:
        depth_order = None
    if raw_type in {"ground", "floor", "plane"}:
        position[1] = -abs(size[1]) / 2
    elif abs(position[1]) < 0.0001:
        position[1] = abs(size[1]) / 2
    if "stair" in raw_type:
        return [
            {
                "id": f"{obj_id}_step_{step + 1}",
                "type": "stair_step",
                "name": f"{name} step {step + 1}",
                "position": [position[0], 0.08 + step * 0.16, position[2] + step * 0.34],
                "size": [size[0], 0.16, 0.34],
                "color": color,
                "layer": layer or "midground",
                "depth_order": (depth_order if depth_order is not None else 100) + step,
            }
            for step in range(5)
        ]
    if raw_type in {"door", "doorway", "entrance", "portal"}:
        return [
            {"id": f"{obj_id}_left", "type": "architecture", "name": f"{name} left", "position": [position[0] - size[0] * 0.42, size[1] / 2, position[2]], "size": [size[0] * 0.16, size[1], size[2]], "color": color, "layer": layer or "midground", "depth_order": (depth_order if depth_order is not None else 100)},
            {"id": f"{obj_id}_right", "type": "architecture", "name": f"{name} right", "position": [position[0] + size[0] * 0.42, size[1] / 2, position[2]], "size": [size[0] * 0.16, size[1], size[2]], "color": color, "layer": layer or "midground", "depth_order": (depth_order if depth_order is not None else 100)},
            {"id": f"{obj_id}_top", "type": "architecture", "name": f"{name} lintel", "position": [position[0], size[1] * 0.92, position[2]], "size": [size[0], size[1] * 0.16, size[2]], "color": color, "layer": layer or "midground", "depth_order": (depth_order if depth_order is not None else 100)},
        ]
    if not layer:
        if raw_type in {"ground", "floor", "plane"} or any(tag in raw_type for tag in {"background", "wall", "architecture", "building", "sky"}):
            layer = "background"
        elif any(tag in raw_type for tag in {"character", "person", "hero", "subject"}):
            layer = "foreground"
        else:
            layer = "midground"
    if depth_order is None:
        depth_order = {"background": 0, "midground": 100, "foreground": 200}.get(layer, 100) + index
    return [{"id": obj_id, "type": raw_type, "name": name, "position": position, "size": size, "color": color, "layer": layer, "depth_order": depth_order}]

def _spatial_size(raw_type: str, item: dict) -> list[float]:
    default = [0.8, 0.8, 0.8]
    if "character" in raw_type or "person" in raw_type or "hero" in raw_type:
        default = [0.55, 1.7, 0.38]
    elif "wall" in raw_type:
        default = [3.0, 2.2, 0.2]
    elif raw_type in {"ground", "floor", "plane"}:
        default = [6.0, 0.08, 4.0]
    elif "light" in raw_type:
        default = [0.32, 0.32, 0.32]
    elif "prop" in raw_type:
        default = [0.6, 0.6, 0.6]
    result = _vec3(item.get("size") or item.get("scale") or item.get("dimensions"), default)
    return [max(0.04, abs(float(part))) for part in result]

def _vec3(value, default: list[float]) -> list[float]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = [piece.strip() for piece in value.replace(",", " ").split() if piece.strip()]
    if isinstance(value, dict):
        value = [value.get("x"), value.get("y"), value.get("z")]
    if isinstance(value, (list, tuple)):
        out = []
        for index in range(3):
            try:
                out.append(float(value[index]))
            except Exception:
                out.append(float(default[index]))
        return out
    return [float(default[0]), float(default[1]), float(default[2])]

def _spatial_color(value) -> list[float]:
    named = {
        "blue": "#2f65d9", "red": "#d94a38", "green": "#4f9b63", "yellow": "#d7a437",
        "orange": "#c46f35", "purple": "#7e5cc8", "black": "#26221f", "white": "#f2eee7",
        "gray": "#77736c", "grey": "#77736c", "ground": "#747067", "wall": "#5a6066",
        "architecture": "#5a6066", "character": "#2f65d9", "prop": "#9a7757", "light": "#d94a38",
    }
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        vals = []
        for item in value[:4]:
            try:
                vals.append(float(item))
            except Exception:
                vals.append(1.0)
        if max(vals[:3]) > 1:
            vals[:3] = [item / 255 for item in vals[:3]]
        while len(vals) < 4:
            vals.append(1.0)
        return [min(1.0, max(0.0, item)) for item in vals[:4]]
    text = str(value or "").strip().lower()
    hex_value = named.get(text, text)
    if not hex_value.startswith("#") or len(hex_value) not in {4, 7}:
        digest = hashlib.sha1(text.encode("utf-8")).digest()
        return [0.25 + digest[0] / 255 * 0.45, 0.25 + digest[1] / 255 * 0.45, 0.25 + digest[2] / 255 * 0.45, 1.0]
    if len(hex_value) == 4:
        hex_value = "#" + "".join(ch * 2 for ch in hex_value[1:])
    rgb = _hex_to_rgb(hex_value)
    return [rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1.0]

def _write_spatial_blockout_glb(path: Path, spec: dict):
    buffer = bytearray()
    buffer_views = []
    accessors = []
    materials = []
    meshes = []
    nodes = []

    def add_view(payload: bytes, target: int) -> int:
        while len(buffer) % 4:
            buffer.append(0)
        offset = len(buffer)
        buffer.extend(payload)
        buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(payload), "target": target})
        return len(buffer_views) - 1

    def add_accessor(view: int, component_type: int, count: int, type_name: str, min_val=None, max_val=None) -> int:
        item = {"bufferView": view, "componentType": component_type, "count": count, "type": type_name}
        if min_val is not None:
            item["min"] = min_val
        if max_val is not None:
            item["max"] = max_val
        accessors.append(item)
        return len(accessors) - 1

    for index, obj in enumerate(spec.get("objects") or []):
        position = _vec3(obj.get("position"), [0, 0, 0])
        size = _vec3(obj.get("size"), [1, 1, 1])
        vertices, indices = _spatial_box_geometry(position, size)
        vertex_bytes = b"".join(struct.pack("<fff", *vertex) for vertex in vertices)
        index_bytes = b"".join(struct.pack("<H", item) for item in indices)
        pos_view = add_view(vertex_bytes, 34962)
        idx_view = add_view(index_bytes, 34963)
        mins = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
        maxs = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
        pos_accessor = add_accessor(pos_view, 5126, len(vertices), "VEC3", mins, maxs)
        idx_accessor = add_accessor(idx_view, 5123, len(indices), "SCALAR")
        materials.append({
            "name": str(obj.get("type") or "material"),
            "pbrMetallicRoughness": {"baseColorFactor": _spatial_color(obj.get("color")), "metallicFactor": 0.0, "roughnessFactor": 0.86},
            "doubleSided": True,
        })
        meshes.append({
            "name": str(obj.get("name") or obj.get("id") or f"object_{index + 1}"),
            "primitives": [{"attributes": {"POSITION": pos_accessor}, "indices": idx_accessor, "material": len(materials) - 1}],
        })
        nodes.append({"name": str(obj.get("name") or obj.get("id") or f"object_{index + 1}"), "mesh": len(meshes) - 1})

    if not nodes:
        vertices, indices = _spatial_box_geometry([0, 0.5, 0], [1, 1, 1])
        vertex_bytes = b"".join(struct.pack("<fff", *vertex) for vertex in vertices)
        index_bytes = b"".join(struct.pack("<H", item) for item in indices)
        pos_accessor = add_accessor(add_view(vertex_bytes, 34962), 5126, len(vertices), "VEC3", [-0.5, 0, -0.5], [0.5, 1, 0.5])
        idx_accessor = add_accessor(add_view(index_bytes, 34963), 5123, len(indices), "SCALAR")
        materials.append({"pbrMetallicRoughness": {"baseColorFactor": [0.3, 0.45, 0.8, 1], "metallicFactor": 0, "roughnessFactor": 0.9}})
        meshes.append({"primitives": [{"attributes": {"POSITION": pos_accessor}, "indices": idx_accessor, "material": 0}]})
        nodes.append({"name": "fallback_box", "mesh": 0})

    doc = {
        "asset": {"version": "2.0", "generator": "CartridgeFlow local_spatial_blockout"},
        "scene": 0,
        "scenes": [{"name": str(spec.get("title") or "Spatial Blockout"), "nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "buffers": [{"byteLength": len(buffer)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    json_chunk = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    bin_chunk = bytes(buffer)
    bin_chunk += b"\x00" * ((4 - len(bin_chunk) % 4) % 4)
    total_length = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    with path.open("wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total_length))
        fh.write(struct.pack("<I4s", len(json_chunk), b"JSON"))
        fh.write(json_chunk)
        fh.write(struct.pack("<I4s", len(bin_chunk), b"BIN\x00"))
        fh.write(bin_chunk)

def _spatial_box_geometry(position: list[float], size: list[float]) -> tuple[list[list[float]], list[int]]:
    x, y, z = position
    sx, sy, sz = [max(0.04, abs(float(item))) / 2 for item in size]
    vertices = [
        [x - sx, y - sy, z - sz], [x + sx, y - sy, z - sz], [x + sx, y + sy, z - sz], [x - sx, y + sy, z - sz],
        [x - sx, y - sy, z + sz], [x + sx, y - sy, z + sz], [x + sx, y + sy, z + sz], [x - sx, y + sy, z + sz],
    ]
    indices = [
        0, 1, 2, 0, 2, 3, 1, 5, 6, 1, 6, 2, 5, 4, 7, 5, 7, 6,
        4, 0, 3, 4, 3, 7, 3, 2, 6, 3, 6, 7, 4, 5, 1, 4, 1, 0,
    ]
    return vertices, indices

def _render_spatial_blockout_preview_html(spec: dict, glb_path: str) -> str:
    data = html.escape(json.dumps(spec, ensure_ascii=False), quote=False)
    title = html.escape(str(spec.get("title") or "Spatial Animation Previz"))
    glb = html.escape(glb_path)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
  <style>
    *{{box-sizing:border-box}}
    body{{margin:0;background:#f7f3ec;color:#332b24;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;}}
    main{{height:100vh;display:grid;grid-template-rows:auto minmax(0,1fr) auto;}}
    header,footer{{padding:12px 16px;border-bottom:1px solid #dfd2c4;background:#fffaf4;}}
    footer{{border-top:1px solid #dfd2c4;border-bottom:0;font-size:12px;color:#786b60;display:grid;grid-template-columns:auto minmax(180px,1fr) auto auto;gap:10px;align-items:center;}}
    h1{{margin:0;font-size:16px;}} p{{margin:4px 0 0;color:#786b60;font-size:12px;}}
    canvas{{width:100%;height:100%;display:block;background:linear-gradient(#fffaf4,#eee5d9);}}
    a{{color:#9a4e2f;text-decoration:none;font-weight:700;}}
    button{{border:1px solid #d5bba6;background:#fff7ed;color:#8d472b;border-radius:6px;padding:6px 10px;font-weight:700;cursor:pointer;}}
    input[type=range]{{width:100%;accent-color:#c46f35;}}
    code{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;color:#8d472b;}}
  </style>
</head>
<body>
<main>
  <header><h1>{title}</h1><p>3D 动画预演。GLB 代理文件：<a href="{glb}" target="_blank" rel="noreferrer">{glb}</a></p></header>
  <canvas id="view"></canvas>
  <footer>
    <button id="play" type="button">暂停</button>
    <input id="scrub" type="range" min="0" max="1000" value="0" />
    <code id="time">0.00s</code>
    <span id="stats"></span>
  </footer>
</main>
<script id="scene-data" type="application/json">{data}</script>
<script>
const spec = JSON.parse(document.getElementById('scene-data').textContent);
const canvas = document.getElementById('view');
const ctx = canvas.getContext('2d');
const timeline = spec.timeline || {{}};
const duration = Math.max(2, Number(timeline.duration_seconds || 6));
const tracks = Array.isArray(timeline.tracks) ? timeline.tracks : [];
const events = Array.isArray(timeline.events) ? timeline.events : [];
const composition = spec.composition || {{}};
const playButton = document.getElementById('play');
const scrub = document.getElementById('scrub');
const timeLabel = document.getElementById('time');
let angle = -0.78, zoom = 72, dragging = false, lastX = 0, manualCamera = false;
let playing = true, startMs = performance.now(), pausedAt = 0;
function nowTime(){{ return playing ? ((performance.now() - startMs) / 1000) % duration : pausedAt; }}
function setTime(t){{ pausedAt = Math.max(0, Math.min(duration, t)); startMs = performance.now() - pausedAt * 1000; }}
function resize(){{ const dpr = window.devicePixelRatio || 1; canvas.width = canvas.clientWidth*dpr; canvas.height = canvas.clientHeight*dpr; ctx.setTransform(dpr,0,0,dpr,0,0); draw(); }}
function color(c){{ if(!Array.isArray(c)) return '#77736c'; const r=Math.round((c[0]||0)*255),g=Math.round((c[1]||0)*255),b=Math.round((c[2]||0)*255); return 'rgb('+r+','+g+','+b+')'; }}
function shade(fill, k){{ const m=fill.match(/\\d+/g)||[120,120,120]; return 'rgb('+Math.max(0,Math.min(255,Math.round(m[0]*k)))+','+Math.max(0,Math.min(255,Math.round(m[1]*k)))+','+Math.max(0,Math.min(255,Math.round(m[2]*k)))+')'; }}
function cameraAngle(t){{ if(manualCamera) return angle; const p=t/duration; return -0.92 + p*.45 + Math.sin(p*Math.PI)*.12; }}
function cameraZoom(t){{ return zoom + Math.sin((t/duration)*Math.PI)*8; }}
function project(p,t){{ const a=cameraAngle(t), z=cameraZoom(t), ca=Math.cos(a), sa=Math.sin(a); const x=p[0]*ca-p[2]*sa; const depth=p[0]*sa+p[2]*ca; return [canvas.clientWidth/2+x*z, canvas.clientHeight*.64+depth*z*.38-p[1]*z]; }}
function boxCorners(o){{ const p=o.position||[0,0,0], s=o.size||[1,1,1]; const hx=s[0]/2, hy=s[1]/2, hz=s[2]/2; return [[p[0]-hx,p[1]-hy,p[2]-hz],[p[0]+hx,p[1]-hy,p[2]-hz],[p[0]+hx,p[1]+hy,p[2]-hz],[p[0]-hx,p[1]+hy,p[2]-hz],[p[0]-hx,p[1]-hy,p[2]+hz],[p[0]+hx,p[1]-hy,p[2]+hz],[p[0]+hx,p[1]+hy,p[2]+hz],[p[0]-hx,p[1]+hy,p[2]+hz]]; }}
function face(points, fill, t){{ ctx.beginPath(); points.forEach((p,i)=>{{ const q=project(p,t); if(i)ctx.lineTo(q[0],q[1]); else ctx.moveTo(q[0],q[1]); }}); ctx.closePath(); ctx.fillStyle=fill; ctx.fill(); ctx.strokeStyle='rgba(65,52,42,.35)'; ctx.stroke(); }}
function faceDepth(points,t){{ const a=cameraAngle(t), ca=Math.cos(a), sa=Math.sin(a); return points.reduce((sum,p)=>sum+p[0]*sa+p[2]*ca,0)/points.length; }}
function mix(a,b,p){{ if(Array.isArray(a)&&Array.isArray(b)) return a.map((v,i)=>Number(v)+(Number(b[i]||0)-Number(v))*p); if(typeof a==='number'&&typeof b==='number') return a+(b-a)*p; return p < .5 ? a : b; }}
function keyValue(frames,t){{ const ks=[...frames].sort((a,b)=>Number(a.time||0)-Number(b.time||0)); if(!ks.length) return null; if(t<=Number(ks[0].time||0)) return ks[0].value; for(let i=0;i<ks.length-1;i++){{ const a=ks[i], b=ks[i+1], ta=Number(a.time||0), tb=Number(b.time||ta); if(t>=ta&&t<=tb){{ const p=tb===ta?1:(t-ta)/(tb-ta); return mix(a.value,b.value,p); }} }} return ks[ks.length-1].value; }}
function trackValue(id, prop, t){{ const track = tracks.find(item => String(item.target||'')===String(id) && String(item.property||'')===prop); return track ? keyValue(track.keyframes||[],t) : null; }}
function listValues(value){{ if(Array.isArray(value)) return value.map(v=>String(v||'').trim()).filter(Boolean); if(value&&typeof value==='object') return Object.entries(value).filter(([,enabled])=>Boolean(enabled)).map(([key])=>String(key).trim()).filter(Boolean); if(typeof value==='string') return value.split(/[,\\n、|]+/).map(v=>v.trim()).filter(Boolean); return []; }}
const layerSets = {{
  foreground: new Set([...(listValues(composition.foreground)), ...(listValues(composition.foreground_ids))]),
  midground: new Set([...(listValues(composition.midground)), ...(listValues(composition.midground_ids))]),
  background: new Set([...(listValues(composition.background)), ...(listValues(composition.background_ids))]),
}};
function normalizeLayer(value){{ const text=String(value||'').trim().toLowerCase(); if(['foreground','midground','background'].includes(text)) return text; const aliases={{front:'foreground',fg:'foreground',middle:'midground',mid:'midground',middleground:'midground',back:'background',bg:'background',rear:'background'}}; return aliases[text] || ''; }}
function inferLayer(o){{ const explicit = normalizeLayer(o.layer || o.depth_layer || o.stage_layer); if(explicit) return explicit; const id=String(o.id||''); if(layerSets.foreground.has(id)) return 'foreground'; if(layerSets.midground.has(id)) return 'midground'; if(layerSets.background.has(id)) return 'background'; const text=`${{o.id||''}} ${{o.type||''}} ${{o.name||''}}`.toLowerCase(); if(/hero|character|person|subject/.test(text)) return 'foreground'; if(/ground|floor|background|wall|architecture|building|sky/.test(text)) return 'background'; return 'midground'; }}
function layerBias(layer){{ return {{background:-2, midground:0, foreground:2}}[layer] || 0; }}
function animatedObject(o,t){{ const next={{...o, position:[...(o.position||[0,0,0])], size:[...(o.size||[1,1,1])]}}; const offset=trackValue(o.id,'offset',t); const pos=trackValue(o.id,'position',t); if(Array.isArray(pos)) next.position=pos; if(Array.isArray(offset)) next.position=next.position.map((v,i)=>v+Number(offset[i]||0)); next.pose=trackValue(o.id,'pose',t)||''; next.pulse=Number(trackValue(o.id,'pulse',t)||0); next.layer=inferLayer(o); next.depth_order=Number(o.depth_order||0); return next; }}
function objectDepth(o,t){{ const p=o.position||[0,0,0], a=cameraAngle(t), ca=Math.cos(a), sa=Math.sin(a); const base=p[0]*sa+p[2]*ca; return base + layerBias(o.layer)*10 + Number(o.depth_order||0)*0.01; }}
function drawBox(o,t,label=true){{ const c=boxCorners(o), base=color(o.color); const pulse=Number(o.pulse||0); const lit=pulse>0?shade(base,1+.7*Math.abs(Math.sin(t*7))*pulse):base; const faces=[
  {{points:[c[0],c[1],c[2],c[3]], light:.72}},
  {{points:[c[4],c[5],c[6],c[7]], light:.94}},
  {{points:[c[0],c[4],c[7],c[3]], light:.82}},
  {{points:[c[1],c[5],c[6],c[2]], light:.78}},
  {{points:[c[3],c[2],c[6],c[7]], light:1.08}},
  {{points:[c[0],c[1],c[5],c[4]], light:.62}},
]; faces.sort((a,b)=>faceDepth(a.points,t)-faceDepth(b.points,t)).forEach(f=>face(f.points, shade(lit,f.light),t)); if(label) drawLabel(o,t); }}
function drawLabel(o,t){{ const p=o.position||[0,0,0], s=o.size||[1,1,1]; const q=project([p[0],p[1]+s[1]/2+.18,p[2]],t); ctx.fillStyle='rgba(255,250,244,.82)'; ctx.fillRect(q[0]-44,q[1]-15,88,18); ctx.fillStyle='#4a4038'; ctx.font='11px monospace'; ctx.textAlign='center'; ctx.fillText(o.name||o.id||o.type,q[0],q[1]-2); }}
function drawCharacter(o,t){{ const p=o.position||[0,0,0], base=o.size||[.55,1.7,.38], c=o.color||[.2,.38,.85,1]; const sway=Math.sin(t*7)*.08; const smokePose=String(o.pose||'').includes('smoke'); const parts=[
  {{id:o.id+'_body', position:[p[0],p[1]+base[1]*.48,p[2]], size:[base[0]*.62,base[1]*.42,base[2]*.78], color:c}},
  {{id:o.id+'_head', position:[p[0],p[1]+base[1]*.82,p[2]], size:[base[0]*.42,base[0]*.42,base[0]*.42], color:[.88,.72,.56,1]}},
  {{id:o.id+'_leg_l', position:[p[0]-base[0]*.16,p[1]+base[1]*.19,p[2]+sway], size:[base[0]*.18,base[1]*.38,base[2]*.28], color:[.18,.18,.2,1]}},
  {{id:o.id+'_leg_r', position:[p[0]+base[0]*.16,p[1]+base[1]*.19,p[2]-sway], size:[base[0]*.18,base[1]*.38,base[2]*.28], color:[.18,.18,.2,1]}},
  {{id:o.id+'_arm_l', position:[p[0]-base[0]*.42,p[1]+base[1]*.52,p[2]], size:[base[0]*.14,base[1]*.38,base[2]*.22], color:c}},
  {{id:o.id+'_arm_r', position:[p[0]+base[0]*.42,p[1]+base[1]*(smokePose ? .66 : .52),p[2]-base[2]*(smokePose ? .42 : 0)], size:[base[0]*.14,base[1]*(smokePose ? .26 : .38),base[2]*.22], color:c}},
]; parts.forEach(part=>drawBox(part,t,false)); if(smokePose) drawSmoke([p[0]+base[0]*.52,p[1]+base[1]*.78,p[2]-base[2]*.46],t); drawLabel(o,t); }}
function drawSmoke(origin,t){{ for(let i=0;i<4;i++){{ const age=((t*1.1+i*.22)%1); const q=project([origin[0]+age*.22,origin[1]+age*.48,origin[2]-age*.16],t); ctx.beginPath(); ctx.arc(q[0],q[1],6+age*11,0,Math.PI*2); ctx.fillStyle='rgba(190,180,168,'+(0.22*(1-age))+')'; ctx.fill(); }} }}
function drawEvents(t){{ events.forEach(ev=>{{ const dt=Math.abs(t-Number(ev.time||0)); if(dt>.45) return; if(String(ev.type||'').includes('smoke')){{ const hero=(spec.objects||[]).find(o=>String(o.id||'').includes(String(ev.target||'hero'))) || (spec.objects||[]).find(o=>String(o.type||'').includes('character')); if(hero) drawSmoke([(hero.position||[0,0,0])[0]+.35,(hero.position||[0,.8,0])[1]+1.25,(hero.position||[0,0,0])[2]-.2],t); }} }}); }}
function draw(){{ const t=nowTime(); ctx.clearRect(0,0,canvas.clientWidth,canvas.clientHeight); const objs=(spec.objects||[]).map(o=>animatedObject(o,t)).sort((a,b)=>objectDepth(a,t)-objectDepth(b,t)); const layerCounts={{foreground:0, midground:0, background:0}}; objs.forEach(o=>{{ layerCounts[o.layer] = (layerCounts[o.layer]||0) + 1; const type=String(o.type||'').toLowerCase(); if(type.includes('character')||type.includes('person')||type.includes('hero')) drawCharacter(o,t); else drawBox(o,t,true); }}); drawEvents(t); scrub.value=String(Math.round(t/duration*1000)); timeLabel.textContent=t.toFixed(2)+'s / '+duration.toFixed(1)+'s'; document.getElementById('stats').textContent='对象 '+objs.length+' 个 · 前景 '+(layerCounts.foreground||0)+' · 中景 '+(layerCounts.midground||0)+' · 背景 '+(layerCounts.background||0)+' · 拖拽旋转，滚轮缩放'; }}
function loop(){{ draw(); requestAnimationFrame(loop); }}
playButton.addEventListener('click',()=>{{ if(playing){{ pausedAt=nowTime(); playing=false; playButton.textContent='播放'; }} else {{ startMs=performance.now()-pausedAt*1000; playing=true; playButton.textContent='暂停'; }} }});
scrub.addEventListener('input',()=>{{ setTime(Number(scrub.value)/1000*duration); if(playing){{ playing=false; playButton.textContent='播放'; }} draw(); }});
canvas.addEventListener('mousedown',e=>{{dragging=true;lastX=e.clientX;manualCamera=true;}});
window.addEventListener('mouseup',()=>dragging=false);
window.addEventListener('mousemove',e=>{{ if(!dragging)return; angle+=(e.clientX-lastX)*.01; lastX=e.clientX; draw(); }});
canvas.addEventListener('wheel',e=>{{ e.preventDefault(); zoom=Math.max(32,Math.min(160,zoom-e.deltaY*.08)); manualCamera=true; draw(); }},{{passive:false}});
window.addEventListener('resize',resize); resize(); loop();
</script>
</body>
</html>"""


def register(registry):
    def forge_spatial_blockout(params: dict) -> dict:
        scene_spec = params.get("scene_spec") or params.get("scene_blockout") or params.get("spec") or {}
        title = str(params.get("title") or "").strip()
        output_dir = str(params.get("output_dir") or "test_output/spatial_blockout").strip()
        filename_prefix = _safe_slug(str(params.get("filename_prefix") or params.get("scene_id") or title or "spatial_blockout"))
        try:
            spec = _normalize_spatial_blockout_spec(scene_spec, title or filename_prefix)
            target_dir = registry._safe_path(output_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            scene_path = target_dir / f"{filename_prefix}.scene_animation.json"
            glb_path = target_dir / f"{filename_prefix}.glb"
            preview_path = target_dir / f"{filename_prefix}.preview.html"
            manifest_path = target_dir / f"{filename_prefix}.manifest.json"

            scene_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            _write_spatial_blockout_glb(glb_path, spec)
            rel_scene = _workspace_rel(registry, scene_path)
            rel_glb = _workspace_rel(registry, glb_path)
            preview_path.write_text(_render_spatial_blockout_preview_html(spec, rel_glb), encoding="utf-8")
            rel_preview = _workspace_rel(registry, preview_path)
            manifest = {
                "schema": "spatial_animation_manifest.v1",
                "status": "animation_preview_created",
                "title": spec.get("title"),
                "provider": "local_spatial_animation_previz",
                "scene_animation": rel_scene,
                "glb": rel_glb,
                "preview": rel_preview,
                "duration_seconds": (spec.get("timeline") or {}).get("duration_seconds"),
                "object_count": len(spec.get("objects") or []),
                "quality_gate": "animated_proxy_preview_visible",
                "notes": "Deterministic proxy animation preview. Use to judge timing, staging, camera and spatial blocking, not final model quality.",
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            rel_manifest = _workspace_rel(registry, manifest_path)
            return {
                "ok": True,
                "path": rel_glb,
                "project_path": rel_scene,
                "preview_path": rel_preview,
                "manifest_path": rel_manifest,
                "files": [rel_glb, rel_scene, rel_preview, rel_manifest],
                "content": json.dumps(manifest, ensure_ascii=False, indent=2),
                "scene_blockout_ok": True,
                "animation_preview_ok": True,
                "provider": "local_spatial_animation_previz",
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"spatial blockout forge failed: {exc}"}

    registry._registry["media"].update({
        'forge_spatial_blockout': forge_spatial_blockout,
    })
