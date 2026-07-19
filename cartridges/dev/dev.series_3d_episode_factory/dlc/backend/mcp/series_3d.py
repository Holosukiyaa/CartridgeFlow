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

from . import spatial as _spatial

for _name in dir(_spatial):
    if _name.startswith("_"):
        globals()[_name] = getattr(_spatial, _name)

DLC_ID = 'dlc.series_3d_episode_factory'
DLC_PROTOCOL = 'CF-FARP@0.5'
TOOLS = ['match_series_assets', 'match_series_actions', 'forge_3d_series_episode']

def _load_series_asset_library(registry, path_value=None) -> dict:
    library_path = str(path_value or "").strip()
    path = registry._safe_path(library_path) if library_path else registry.package_path("assets/series_asset_library.json")
    if not path.is_file():
        raise FileNotFoundError(f"series asset library not found: {library_path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"series asset library is not valid JSON: {library_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"series asset library must be an object: {library_path}")
    return _normalize_series_library(data)

def _normalize_series_library(value: dict) -> dict:
    def items(key):
        raw = value.get(key) if isinstance(value, dict) else []
        if isinstance(raw, dict):
            raw = list(raw.values())
        return [item for item in raw if isinstance(item, dict)]

    return {
        "schema": "series_asset_library.v1",
        "characters": items("characters"),
        "scenes": items("scenes"),
        "props": items("props"),
        "actions": items("actions"),
        "camera_templates": items("camera_templates"),
    }

def _series_parse(value, fallback=None):
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return json.loads(text)
            except Exception:
                return fallback if fallback is not None else {"text": text}
        return fallback if fallback is not None else {}
    return value if isinstance(value, (dict, list)) else (fallback if fallback is not None else {})

def _series_episode_title(episode_script) -> str:
    data = _series_parse(episode_script, {})
    if isinstance(data, dict):
        return str(data.get("episode_id") or data.get("title") or "").strip()
    return ""

def _series_shots(shot_list) -> list[dict]:
    data = _series_parse(shot_list, {})
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        raw = data.get("shots") or data.get("shot_list") or []
    else:
        raw = []
    shots = []
    for index, item in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        shot_id = str(item.get("id") or item.get("shot_id") or f"shot_{index + 1:02d}").strip()
        shots.append({
            "id": shot_id,
            "index": index + 1,
            "title": str(item.get("title") or item.get("beat") or f"镜头 {index + 1}").strip(),
            "description": str(item.get("description") or item.get("visual") or item.get("summary") or "").strip(),
            "dialogue": item.get("dialogue") if isinstance(item.get("dialogue"), list) else [],
            "characters": _series_list(item.get("characters") or item.get("actors") or item.get("cast")),
            "props": _series_list(item.get("props") or item.get("objects")),
            "scene": str(item.get("scene") or item.get("location") or "").strip(),
            "camera": str(item.get("camera") or item.get("camera_template") or item.get("shot_type") or "").strip(),
            "action_tags": _series_list(item.get("action_tags") or item.get("actions")),
            "duration": _clamp_float(item.get("duration"), 1.0, 8.0, 4.0),
        })
    if not shots:
        shots = [
            {"id": "shot_01", "index": 1, "title": "空街建立", "description": "男性主角沿白天郊区街道向前走。", "dialogue": [], "characters": ["hero"], "props": [], "scene": "白天郊区街道", "camera": "slow_push_in", "action_tags": ["walk_slow"], "duration": 5.0},
            {"id": "shot_02", "index": 2, "title": "停下观察", "description": "主角停下脚步，观察空旷街道。", "dialogue": [], "characters": ["hero"], "props": [], "scene": "白天郊区街道", "camera": "close_up_reveal", "action_tags": ["idle_hold"], "duration": 5.0},
            {"id": "shot_03", "index": 3, "title": "做出反应", "description": "主角像是发现了什么，抬头做出反应。", "dialogue": [], "characters": ["hero"], "props": [], "scene": "白天郊区街道", "camera": "low_angle_hold", "action_tags": ["gesture_interact"], "duration": 5.0},
        ]
    return shots

def _series_list(value) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，、\n]+", value) if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []

def _match_series_assets(episode_script, shot_list, library: dict) -> dict:
    shots = _series_shots(shot_list)
    characters = library.get("characters") or []
    scenes = library.get("scenes") or []
    props = library.get("props") or []
    selected_characters = {}
    selected_scenes = {}
    selected_props = {}
    missing = []
    for shot in shots:
        text = " ".join([shot.get("title", ""), shot.get("description", ""), shot.get("scene", ""), " ".join(shot.get("characters") or []), " ".join(shot.get("props") or [])])
        scene = _series_best_match(
            text,
            scenes,
            "pilot_suburban_street_day" if not shot.get("scene") else "",
        )
        if scene:
            selected_scenes[scene["id"]] = scene
        else:
            missing.append({"type": "scene", "request": shot.get("scene") or text[:80], "shot_id": shot["id"]})
        requested_chars = shot.get("characters") or ["hero"]
        for requested in requested_chars:
            requested_text = str(requested).strip()
            fallback_character = "pilot_male_hero" if requested_text.lower() in {"", "hero", "主角", "男性", "男人"} else ""
            match = _series_best_match(requested_text, characters, fallback_character)
            if match:
                selected_characters[match["id"]] = match
            else:
                missing.append({"type": "character", "request": requested, "shot_id": shot["id"]})
        for requested in shot.get("props") or []:
            match = _series_best_match(requested + " " + text, props, "")
            if match:
                selected_props[match["id"]] = match
            elif requested:
                missing.append({"type": "prop", "request": requested, "shot_id": shot["id"]})
    return {
        "schema": "series_asset_plan.v1",
        "characters": list(selected_characters.values()),
        "scenes": list(selected_scenes.values()),
        "props": list(selected_props.values()),
        "missing": missing,
        "policy": "fixed_library_only",
        "notes": "No new visual assets were generated. Missing items must be supplied by the library later.",
    }

def _match_series_actions(episode_script, shot_list, library: dict) -> dict:
    shots = _series_shots(shot_list)
    actions = library.get("actions") or []
    cameras = library.get("camera_templates") or []
    per_shot = []
    missing = []
    for shot in shots:
        action_tags = shot.get("action_tags") or []
        action_text = " ".join(action_tags) if action_tags else " ".join([shot.get("title", ""), shot.get("description", "")])
        camera_text = " ".join([shot.get("title", ""), shot.get("description", ""), shot.get("camera", "")])
        action = _series_best_match(action_text, actions, "")
        if not action and not shot.get("action_tags"):
            action = _series_best_match("idle_hold", actions, "idle_hold")
        camera = _series_best_match(camera_text, cameras, "slow_push_in")
        if not action:
            missing.append({"type": "action", "shot_id": shot["id"], "request": action_text[:80]})
        if not camera:
            missing.append({"type": "camera_template", "shot_id": shot["id"], "request": shot.get("camera")})
        per_shot.append({
            "shot_id": shot["id"],
            "duration": shot["duration"],
            "primary_action": action or {"id": "idle_hold", "name": "站立停留", "duration": shot["duration"]},
            "camera_template": camera or {"id": "slow_push_in", "name": "慢慢推进", "duration": shot["duration"]},
            "segments": [
                {
                    "actor": (shot.get("characters") or ["hero"])[0],
                    "action_id": (action or {}).get("id", "idle_hold"),
                    "start": 0,
                    "duration": shot["duration"],
                    "notes": "Matched from fixed action library.",
                }
            ],
        })
    return {
        "schema": "series_action_plan.v1",
        "shots": per_shot,
        "missing": missing,
        "policy": "fixed_action_tags_only",
        "notes": "LLM selected tags; deterministic matcher mapped them to library action IDs.",
    }

def _series_best_match(text: str, items: list[dict], fallback_id: str):
    text_l = str(text or "").lower()
    requested_ids = {token for token in re.split(r"[\s,，、；;]+", text_l) if token}
    for item in items:
        item_id = str(item.get("id") or "").lower()
        if item_id and item_id in requested_ids:
            return dict(item)
    best = None
    best_score = -1
    for item in items:
        hay = " ".join(str(part) for part in [item.get("id"), item.get("name"), " ".join(item.get("tags") or []), " ".join(item.get("roles") or [])]).lower()
        score = 0
        for token in re.split(r"[\s,，、;；]+", hay):
            if token and token in text_l:
                score += len(token)
        for tag in item.get("tags") or item.get("roles") or []:
            tag_text = str(tag).lower()
            if tag_text and tag_text in text_l:
                score += 12
        if score > best_score:
            best = item
            best_score = score
    if best and best_score > 0:
        return dict(best)
    if fallback_id:
        for item in items:
            if item.get("id") == fallback_id:
                return dict(item)
    return None

def _normalize_series_episode_package(episode_script, shot_list, asset_plan, action_plan) -> dict:
    script = _series_parse(episode_script, {})
    if not isinstance(script, dict):
        script = {"title": "未命名短剧", "logline": str(script)}
    shots = _series_shots(shot_list)
    assets = _series_parse(asset_plan, {})
    actions = _series_parse(action_plan, {})
    if isinstance(assets, dict) and isinstance(assets.get("asset_plan"), dict):
        assets = assets["asset_plan"]
    if isinstance(actions, dict) and isinstance(actions.get("action_plan"), dict):
        actions = actions["action_plan"]
    action_by_shot = {item.get("shot_id"): item for item in (actions.get("shots") or []) if isinstance(item, dict)} if isinstance(actions, dict) else {}
    normalized_shots = []
    current = 0.0
    for shot in shots:
        duration = shot.get("duration") or 4.0
        normalized_shots.append({
            **shot,
            "start": round(current, 2),
            "end": round(current + duration, 2),
            "action_plan": action_by_shot.get(shot["id"], {}),
        })
        current += duration
    return {
        "schema": "series_3d_episode_package.v1",
        "episode_script": script,
        "shots": normalized_shots,
        "asset_plan": assets if isinstance(assets, dict) else {},
        "action_plan": actions if isinstance(actions, dict) else {},
        "duration_seconds": round(current, 2),
        "render_target": "vertical_9_16",
    }

def _render_series_real_preview_html(package: dict, blender_script_path: str, video_path: str, still_path: str) -> str:
    title = html.escape(str((package.get("episode_script") or {}).get("title") or "3D Series Episode"))
    blender_name = html.escape(Path(blender_script_path).name)
    video_name = html.escape(Path(video_path).name)
    still_name = html.escape(Path(still_path).name)
    shot_count = len(package.get("shots") or [])
    duration = float(package.get("duration_seconds") or 0.0)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
  <style>
    *{{box-sizing:border-box}}
    body{{margin:0;background:#171817;color:#f2f4f1;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}}
    main{{min-height:100vh;display:grid;grid-template-columns:minmax(240px,340px) minmax(0,1fr)}}
    aside{{padding:24px;border-right:1px solid #353a36;background:#202320}}
    h1{{margin:0 0 14px;font-size:22px;line-height:1.3}}
    p{{margin:0 0 12px;color:#b9c1ba;line-height:1.6;font-size:14px}}
    code{{color:#e9b872;word-break:break-all}}
    .stage{{display:grid;place-items:center;padding:20px;background:#101210}}
    video{{display:block;width:min(56vh,420px);max-width:100%;max-height:calc(100vh - 40px);aspect-ratio:9/16;background:#000;object-fit:contain}}
    .status{{display:inline-block;margin-bottom:16px;padding:5px 8px;border:1px solid #5e8f68;color:#a9d9b1;font-size:12px}}
    @media(max-width:760px){{main{{grid-template-columns:1fr}}aside{{border-right:0;border-bottom:1px solid #353a36}}video{{max-height:70vh}}}}
  </style>
</head>
<body>
<main>
  <aside>
    <span class="status">真实 Blender 完整成片</span>
    <h1>{title}</h1>
    <p><b>{shot_count} 个镜头 · {duration:.1f} 秒</b></p>
    <p>全部分镜已按连续时间线渲染，每镜使用匹配的动作与摄影机模板。</p>
    <p>编排脚本：<code>{blender_name}</code></p>
  </aside>
  <section class="stage">
    <video controls autoplay loop muted playsinline poster="{still_name}" src="{video_name}"></video>
  </section>
</main>
</body>
</html>"""

def _render_series_episode_preview_html(
    package: dict,
    blender_script_path: str,
    video_path: str = "",
    still_path: str = "",
) -> str:
    if video_path and still_path:
        return _render_series_real_preview_html(package, blender_script_path, video_path, still_path)
    data = html.escape(json.dumps(package, ensure_ascii=False), quote=False)
    title = html.escape(str((package.get("episode_script") or {}).get("title") or "3D Series Episode"))
    blender_path = html.escape(blender_script_path)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
  <style>
    *{{box-sizing:border-box}}
    body{{margin:0;background:#15120f;color:#f3ede6;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;}}
    main{{height:100vh;display:grid;grid-template-columns:minmax(280px,420px) minmax(0,1fr);}}
    aside{{border-right:1px solid #3a2d24;background:#211a15;padding:18px;overflow:auto;}}
    h1{{margin:0 0 8px;font-size:20px;line-height:1.25}}
    p{{margin:0 0 12px;color:#c7b7a7;line-height:1.6;font-size:13px}}
    .stage{{display:grid;place-items:center;background:radial-gradient(circle at 50% 20%,#403229,#15120f 60%);}}
    .phone{{width:min(44vh,360px);height:min(78vh,640px);border:1px solid #5b4637;border-radius:18px;background:#0f0d0b;position:relative;overflow:hidden;box-shadow:0 24px 80px rgba(0,0,0,.45)}}
    .shot{{position:absolute;inset:0;padding:22px;display:grid;grid-template-rows:auto 1fr auto;opacity:0;transition:opacity .25s ease;background:linear-gradient(180deg,#2d302f,#15120f)}}
    .shot.active{{opacity:1}}
    .badge{{display:inline-flex;width:max-content;padding:4px 8px;border:1px solid #c46f35;border-radius:999px;color:#ffb27e;font-size:12px}}
    .visual{{display:grid;place-items:center;position:relative}}
    .actor{{width:54px;height:128px;background:#2f65d9;border-radius:16px 16px 8px 8px;position:absolute;left:42%;bottom:28%;animation:sway 1.2s infinite ease-in-out}}
    .actor:before{{content:"";position:absolute;left:12px;top:-34px;width:30px;height:30px;border-radius:50%;background:#d8b58d}}
    .prop{{position:absolute;right:18%;top:34%;width:40px;height:40px;border-radius:50%;background:#d94a38;box-shadow:0 0 30px #d94a38;animation:pulse .8s infinite alternate}}
    .observer{{position:absolute;right:28%;bottom:36%;width:30px;height:90px;background:#151515;border-radius:12px;opacity:.75}}
    .caption{{padding:12px;border:1px solid rgba(255,255,255,.12);background:rgba(0,0,0,.32);border-radius:10px;font-size:14px;line-height:1.45}}
    .timeline{{display:grid;gap:8px;margin-top:16px}}
    button{{border:1px solid #c46f35;background:#2b211b;color:#ffd2b7;border-radius:8px;padding:8px 10px;font-weight:700;cursor:pointer}}
    .row{{padding:10px;border:1px solid #3a2d24;border-radius:8px;margin:8px 0;background:#19130f;color:#d8c8b8;font-size:12px}}
    code{{color:#ffb27e}}
    @keyframes sway{{from{{transform:translateX(-8px)}}to{{transform:translateX(8px)}}}}
    @keyframes pulse{{from{{opacity:.45;transform:scale(.8)}}to{{opacity:1;transform:scale(1.12)}}}}
  </style>
</head>
<body>
<main>
  <aside>
    <h1>{title}</h1>
    <p id="logline"></p>
    <p>Blender 编排脚本：<code>{blender_path}</code></p>
    <button id="play" type="button">暂停</button>
    <div class="timeline" id="timeline"></div>
  </aside>
  <section class="stage"><div class="phone" id="phone"></div></section>
</main>
<script id="episode-data" type="application/json">{data}</script>
<script>
const pkg = JSON.parse(document.getElementById('episode-data').textContent);
const shots = pkg.shots || [];
const phone = document.getElementById('phone');
const timeline = document.getElementById('timeline');
document.getElementById('logline').textContent = pkg.episode_script?.logline || pkg.episode_script?.hook || '短剧预演';
let active = 0, playing = true, started = performance.now();
shots.forEach((shot, index) => {{
  const el = document.createElement('article');
  el.className = 'shot' + (index === 0 ? ' active' : '');
  el.innerHTML = '<span class="badge">'+shot.id+' · '+(shot.action_plan?.camera_template?.name || shot.camera || '镜头')+'</span><div class="visual"><div class="actor"></div><div class="prop"></div>'+(JSON.stringify(shot).includes('observer') || JSON.stringify(shot).includes('追踪') ? '<div class="observer"></div>' : '')+'</div><div class="caption"><b>'+shot.title+'</b><br>'+shot.description+'</div>';
  phone.appendChild(el);
  const row = document.createElement('div');
  row.className = 'row';
  row.textContent = shot.start.toFixed(1)+'s-'+shot.end.toFixed(1)+'s · '+shot.title+' · '+(shot.action_plan?.primary_action?.name || '');
  timeline.appendChild(row);
}});
function setActive(index) {{
  active = index % Math.max(1, shots.length);
  [...phone.children].forEach((item, i) => item.classList.toggle('active', i === active));
}}
function tick(now) {{
  if (playing && shots.length) {{
    const t = ((now - started) / 1000) % Math.max(1, pkg.duration_seconds || 12);
    const idx = Math.max(0, shots.findIndex(s => t >= s.start && t < s.end));
    setActive(idx < 0 ? shots.length - 1 : idx);
  }}
  requestAnimationFrame(tick);
}}
document.getElementById('play').addEventListener('click', (event) => {{
  playing = !playing;
  event.currentTarget.textContent = playing ? '暂停' : '播放';
  started = performance.now() - ((shots[active]?.start || 0) * 1000);
}});
requestAnimationFrame(tick);
</script>
</body>
</html>"""

def _find_blender_binary(configured=None) -> str | None:
    repo_root = Path(__file__).resolve().parents[3]
    candidates = []
    if configured:
        candidates.append(str(configured).strip())
    if os.environ.get("BLENDER_BIN"):
        candidates.append(os.environ["BLENDER_BIN"].strip())
    tools_root = repo_root / ".tools"
    if tools_root.is_dir():
        candidates.extend(str(path) for path in sorted(tools_root.glob("blender-*/blender.exe"), reverse=True))
        candidates.extend(str(path) for path in sorted(tools_root.glob("blender/blender.exe"), reverse=True))
    candidates.extend(["blender", "blender.exe"])
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if not path.is_absolute():
            local_path = (repo_root / path).resolve()
            if local_path.is_file():
                return str(local_path)
        if path.is_file():
            return str(path.resolve())
        found = shutil.which(candidate)
        if found:
            return found
    return None

def _render_series_blender_script(package: dict) -> str:
    payload = repr(json.dumps(package, ensure_ascii=False))
    return """# Blender Python script generated by CartridgeFlow.
# Run from the CartridgeFlow workspace with Blender in background mode.
import json
import hashlib
import math
import os
from pathlib import Path

import bpy
import mathutils

DATA = json.loads(""" + payload + """)
WORKSPACE = Path(os.environ.get("CF_WORKSPACE_ROOT") or Path.cwd()).resolve()
OUTPUT_DIR = Path(__file__).resolve().parent


def resolve_asset(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("asset path is empty")
    path = (WORKSPACE / text).resolve()
    if path != WORKSPACE and WORKSPACE not in path.parents:
        raise ValueError(f"asset path leaves workspace: {text}")
    if not path.is_file():
        raise FileNotFoundError(f"asset not found: {text}")
    return path


def import_asset(path):
    before = set(bpy.data.objects)
    suffix = path.suffix.lower()
    if suffix in {".gltf", ".glb"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        raise ValueError(f"unsupported 3D asset format: {path}")
    return [obj for obj in bpy.data.objects if obj not in before]


def append_material(profile):
    path = resolve_asset(profile.get("path"))
    name = str(profile.get("name") or "").strip()
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        if name not in source.materials:
            raise ValueError(f"material {name!r} not found in {path}")
        target.materials = [name]
    material = bpy.data.materials.get(name)
    if material is None:
        raise RuntimeError(f"material {name!r} was not appended")
    return material


def add_plane(name, location, scale, material):
    bpy.ops.mesh.primitive_plane_add(size=2, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(material)
    return obj


def point_at(obj, target):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def configure_world(hdri_path):
    world = bpy.data.worlds.new("pilot_world")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = 0.65
    environment = nodes.new("ShaderNodeTexEnvironment")
    environment.image = bpy.data.images.load(str(hdri_path), check_existing=True)
    links.new(environment.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    bpy.context.scene.world = world


def first_item(key):
    items = (DATA.get("asset_plan") or {}).get(key) or []
    if not items:
        raise ValueError(f"asset plan has no {key}")
    return items[0]


def camera_pose(template_id, actor_start_y, actor_end_y, forward_y_sign):
    subject_start = (0.0, actor_start_y, 1.25)
    subject_end = (0.0, actor_end_y, 1.25)
    if template_id == "over_shoulder":
        return (
            (1.7, actor_start_y + (2.8 * forward_y_sign), 2.05),
            (1.7, actor_end_y + (2.8 * forward_y_sign), 2.05),
            subject_start,
            subject_end,
            62.0,
            62.0,
        )
    if template_id == "low_angle_hold":
        midpoint = (actor_start_y + actor_end_y) / 2.0
        return (
            (3.4, midpoint + (4.2 * forward_y_sign), 0.72),
            (3.4, midpoint + (4.2 * forward_y_sign), 0.72),
            (0.0, midpoint, 1.15),
            (0.0, midpoint, 1.15),
            44.0,
            44.0,
        )
    if template_id == "close_up_reveal":
        return (
            (2.6, actor_start_y + (4.2 * forward_y_sign), 2.0),
            (1.25, actor_end_y + (2.2 * forward_y_sign), 1.8),
            subject_start,
            (0.0, actor_end_y, 1.45),
            68.0,
            82.0,
        )
    return (
        (5.6, actor_start_y + (5.0 * forward_y_sign), 2.8),
        (3.8, actor_end_y + (3.8 * forward_y_sign), 2.35),
        subject_start,
        subject_end,
        52.0,
        58.0,
    )


def add_shot_camera(scene, shot, index, start_frame, end_frame, actor_start_y, actor_end_y, forward_y_sign):
    camera_template = (shot.get("action_plan") or {}).get("camera_template") or {}
    template_id = str(camera_template.get("id") or shot.get("camera") or "slow_push_in")
    start_location, end_location, start_target, end_target, start_lens, end_lens = camera_pose(
        template_id,
        actor_start_y,
        actor_end_y,
        forward_y_sign,
    )
    bpy.ops.object.camera_add(location=start_location)
    camera = bpy.context.object
    camera.name = f"shot_{index:02d}_{template_id}"
    camera.data.lens = start_lens
    point_at(camera, start_target)
    camera.keyframe_insert(data_path="location", frame=start_frame)
    camera.keyframe_insert(data_path="rotation_euler", frame=start_frame)
    camera.data.keyframe_insert(data_path="lens", frame=start_frame)
    camera.location = end_location
    camera.data.lens = end_lens
    point_at(camera, end_target)
    camera.keyframe_insert(data_path="location", frame=end_frame)
    camera.keyframe_insert(data_path="rotation_euler", frame=end_frame)
    camera.data.keyframe_insert(data_path="lens", frame=end_frame)
    marker = scene.timeline_markers.new(f"shot_{index:02d}_{shot.get('id')}", frame=start_frame)
    marker.camera = camera
    return camera, template_id


def _is_character_object(obj, character):
    current = obj
    while current is not None:
        if current == character:
            return True
        current = current.parent
    return False


def _configure_video_output(scene, path):
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(path)


def _make_mask_material():
    material = bpy.data.materials.new("CF_CRCP_CHARACTER_MASK")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _render_character_mask(scene, character, output_path):
    saved_visibility = [(obj, obj.hide_render) for obj in scene.objects]
    saved_materials = []
    original_world_color = tuple(scene.world.color) if scene.world else None
    original_film_transparent = scene.render.film_transparent
    mask_material = _make_mask_material()
    try:
        for obj in scene.objects:
            obj.hide_render = not (obj.type == "CAMERA" or _is_character_object(obj, character))
            if obj.type == "MESH" and _is_character_object(obj, character):
                saved_materials.append((obj, list(obj.data.materials)))
                obj.data.materials.clear()
                obj.data.materials.append(mask_material)
        if scene.world:
            scene.world.color = (0.0, 0.0, 0.0)
        scene.render.film_transparent = True
        _configure_video_output(scene, output_path)
        bpy.ops.render.render(animation=True)
    finally:
        for obj, hidden in saved_visibility:
            obj.hide_render = hidden
        for obj, materials in saved_materials:
            obj.data.materials.clear()
            for material in materials:
                obj.data.materials.append(material)
        if scene.world and original_world_color is not None:
            scene.world.color = original_world_color
        scene.render.film_transparent = original_film_transparent
        if mask_material.users == 0:
            bpy.data.materials.remove(mask_material)


def _render_depth(scene, output_path):
    original_use_nodes = scene.use_nodes
    view_layer = scene.view_layers[0]
    original_use_pass_z = view_layer.use_pass_z
    view_layer.use_pass_z = True
    scene.use_nodes = True
    nodes = scene.node_tree.nodes
    links = scene.node_tree.links
    nodes.clear()
    render_layers = nodes.new("CompositorNodeRLayers")
    normalize = nodes.new("CompositorNodeNormalize")
    composite = nodes.new("CompositorNodeComposite")
    links.new(render_layers.outputs["Depth"], normalize.inputs[0])
    links.new(normalize.outputs[0], composite.inputs["Image"])
    try:
        _configure_video_output(scene, output_path)
        bpy.ops.render.render(animation=True)
    finally:
        view_layer.use_pass_z = original_use_pass_z
        scene.use_nodes = original_use_nodes


def _write_pose_data(scene, character, frame_end, output_path):
    frames = []
    for frame in range(1, frame_end + 1):
        scene.frame_set(frame)
        location = character.matrix_world.translation
        rotation = character.matrix_world.to_euler()
        frames.append({
            "frame": frame,
            "location": [round(float(value), 6) for value in location],
            "rotation_euler": [round(float(value), 6) for value in rotation],
        })
    output_path.write_text(json.dumps({"schema": "cartridgeflow.pose_data.v1", "frames": frames}, indent=2), encoding="utf-8")


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace_relative(path):
    try:
        return path.resolve().relative_to(WORKSPACE).as_posix()
    except ValueError:
        return path.name


def _render_control_bundle(scene, character, frame_end, fps, preview_path, stem):
    mask_path = OUTPUT_DIR / f"{stem}.character_mask.mp4"
    depth_path = OUTPUT_DIR / f"{stem}.depth.mp4"
    pose_path = OUTPUT_DIR / f"{stem}.pose.json"
    bundle_path = OUTPUT_DIR / f"{stem}.control_bundle.json"
    _render_character_mask(scene, character, mask_path)
    _render_depth(scene, depth_path)
    _write_pose_data(scene, character, frame_end, pose_path)
    preview_ref = _workspace_relative(preview_path)
    mask_ref = _workspace_relative(mask_path)
    depth_ref = _workspace_relative(depth_path)
    pose_ref = _workspace_relative(pose_path)
    paths = {preview_ref: preview_path, mask_ref: mask_path, depth_ref: depth_path, pose_ref: pose_path}
    manifest = {
        "schema": "cartridgeflow.shot_control_bundle.v1",
        "bundle_id": f"{stem}.bundle",
        "revision": 1,
        "shot_id": stem,
        "fps": fps,
        "frame_count": frame_end,
        "width": scene.render.resolution_x,
        "height": scene.render.resolution_y,
        "source": {"engine": "blender", "preview": preview_ref},
        "controls": {
            "character_mask": mask_ref,
            "depth": depth_ref,
            "pose": pose_ref,
        },
        "mask_convention": {"white": "generate_or_replace", "black": "preserve_control_input"},
        "sha256": {name: _sha256(path) for name, path in paths.items()},
        "status": "validated",
    }
    bundle_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return bundle_path, manifest


def main():
    shots = DATA.get("shots") or []
    if not shots:
        raise ValueError("episode package has no shots")
    character_profile = first_item("characters")
    scene_profile = first_item("scenes")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    scene = bpy.context.scene
    settings = DATA.get("render_settings") or {}
    fps = int(settings.get("fps") or 24)
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = int(settings.get("width") or 360)
    scene.render.resolution_y = int(settings.get("height") or 640)
    scene.render.resolution_percentage = 100
    scene.render.fps = fps
    scene.frame_start = 1
    scene.eevee.taa_render_samples = int(settings.get("samples") or 8)
    scene.eevee.volumetric_samples = min(16, int(settings.get("samples") or 8))

    asphalt = append_material(scene_profile.get("road_material") or {})
    pavement = append_material(scene_profile.get("pavement_material") or {})
    add_plane("pilot_road", (0, 0, 0), (3.2, 10.0, 1.0), asphalt)
    add_plane("pilot_sidewalk_left", (-4.2, 0, 0.03), (1.0, 10.0, 1.0), pavement)
    add_plane("pilot_sidewalk_right", (4.2, 0, 0.03), (1.0, 10.0, 1.0), pavement)

    for component in scene_profile.get("components") or []:
        objects = import_asset(resolve_asset(component.get("path")))
        location = tuple(float(value) for value in (component.get("location") or [0, 0, 0]))
        scale = float(component.get("scale") or 1.0)
        rotation = math.radians(float(component.get("rotation_z_degrees") or 0.0))
        for obj in objects:
            if obj.type != "MESH":
                continue
            obj.name = str(component.get("id") or obj.name)
            obj.location = location
            obj.scale = (scale, scale, scale)
            obj.rotation_euler.z = rotation

    character_objects = import_asset(resolve_asset(character_profile.get("asset_path")))
    character = next((obj for obj in character_objects if obj.type == "ARMATURE"), None)
    if character is None:
        raise RuntimeError("character asset has no armature")
    character.name = str(character_profile.get("id") or "pilot_character")
    world_transform = character_profile.get("world_transform") or {}
    forward_axis = str(world_transform.get("forward_axis") or "-Y").strip().upper()
    if forward_axis not in {"+Y", "-Y"}:
        raise ValueError(f"unsupported character forward_axis: {forward_axis}")
    forward_y_sign = -1.0 if forward_axis == "-Y" else 1.0
    actor_start_y = float(world_transform.get("start_y", -3.5 * forward_y_sign))
    character.location = (0.0, actor_start_y, 0.02)
    character.rotation_euler.z = math.radians(float(world_transform.get("rotation_z_degrees") or 0.0))

    imported_motion_paths = set()
    motion_objects = []
    for shot in shots:
        action_profile = (shot.get("action_plan") or {}).get("primary_action") or {}
        motion_path = resolve_asset(action_profile.get("motion_path"))
        if motion_path in imported_motion_paths:
            continue
        imported_motion_paths.add(motion_path)
        motion_objects.extend(import_asset(motion_path))
    for obj in motion_objects:
        bpy.data.objects.remove(obj, do_unlink=True)

    character.animation_data_create()
    track = character.animation_data.nla_tracks.new()
    track.name = "episode_actions"
    shot_reports = []
    frame_cursor = 1
    actor_y = actor_start_y
    first_camera = None
    for index, shot in enumerate(shots, start=1):
        duration = max(1.0, min(8.0, float(shot.get("duration") or 3.0)))
        frame_count = max(1, int(round(duration * fps)))
        start_frame = frame_cursor
        end_frame = start_frame + frame_count - 1
        action_profile = (shot.get("action_plan") or {}).get("primary_action") or {}
        clip_name = str(action_profile.get("clip_name") or "").strip()
        if not clip_name:
            raise ValueError(f"shot {shot.get('id')} has no matched clip_name")
        action = bpy.data.actions.get(clip_name)
        if action is None:
            raise RuntimeError(f"animation clip not found: {clip_name}")
        strip = track.strips.new(f"{index:02d}_{clip_name}", start_frame, action)
        strip.frame_end = end_frame

        distance = float(action_profile.get("translation_meters") or 0.0)
        actor_start_y = actor_y
        actor_end_y = actor_start_y + (distance * forward_y_sign)
        character.location = (0.0, actor_start_y, 0.02)
        character.keyframe_insert(data_path="location", frame=start_frame)
        character.location = (0.0, actor_end_y, 0.02)
        character.keyframe_insert(data_path="location", frame=end_frame)
        camera, camera_template_id = add_shot_camera(
            scene,
            shot,
            index,
            start_frame,
            end_frame,
            actor_start_y,
            actor_end_y,
            forward_y_sign,
        )
        if first_camera is None:
            first_camera = camera
        shot_reports.append({
            "shot_id": shot.get("id"),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "duration_seconds": duration,
            "action_id": action_profile.get("id"),
            "clip_name": clip_name,
            "camera_template_id": camera_template_id,
            "start_y": actor_start_y,
            "end_y": actor_end_y,
        })
        actor_y = actor_end_y
        frame_cursor = end_frame + 1
    frame_end = frame_cursor - 1
    scene.frame_end = frame_end
    scene.camera = first_camera

    bpy.ops.object.light_add(type="AREA", location=(-1.5, -1.0, 6.0))
    key = bpy.context.object
    key.name = "pilot_soft_key"
    key.data.energy = 700
    key.data.shape = "DISK"
    key.data.size = 5.0
    point_at(key, (0.0, 0.0, 1.0))

    bpy.ops.object.light_add(type="POINT", location=(2.8, 0.5, 3.2))
    lamp = bpy.context.object
    lamp.name = "pilot_streetlight_glow"
    lamp.data.energy = 180
    lamp.data.color = (1.0, 0.72, 0.42)
    lamp.data.shadow_soft_size = 0.35

    configure_world(resolve_asset(scene_profile.get("hdri_path")))
    # glTF animation imports can overwrite the scene FPS with the source clip rate.
    scene.render.fps = fps
    scene.render.fps_base = 1.0

    stem = str(DATA.get("output_stem") or "series_episode")
    blend_path = OUTPUT_DIR / f"{stem}.blend"
    still_path = OUTPUT_DIR / f"{stem}.poster.png"
    video_path = OUTPUT_DIR / f"{stem}.final.mp4"
    report_path = OUTPUT_DIR / f"{stem}.render.json"
    preview_frame = max(1, frame_end // 2)
    scene.frame_set(preview_frame)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(still_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.render.render(write_still=True)

    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(video_path)
    bpy.ops.render.render(animation=True)

    control_bundle_path = None
    control_bundle = None
    if (DATA.get("render_settings") or {}).get("render_control_passes"):
        control_bundle_path, control_bundle = _render_control_bundle(
            scene,
            character,
            frame_end,
            fps,
            video_path,
            stem,
        )

    report = {
        "schema": "series_blender_render.v1",
        "status": "rendered",
        "scope": "full_episode",
        "shots": shot_reports,
        "shot_count": len(shot_reports),
        "character_id": character_profile.get("id"),
        "scene_id": scene_profile.get("id"),
        "character_forward_axis": forward_axis,
        "duration_seconds": frame_end / fps,
        "fps": fps,
        "frame_count": frame_end,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "blend": blend_path.name,
        "still": still_path.name,
        "video": video_path.name,
        "control_bundle": control_bundle,
        "control_bundle_manifest": control_bundle_path.name if control_bundle_path else "",
        "blender_version": bpy.app.version_string,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("CF_SERIES_RENDER=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
"""


def register(registry):
    def match_series_assets(params: dict) -> dict:
        try:
            episode_script = params.get("episode_script") or {}
            shot_list = params.get("shot_list") or {}
            library = _load_series_asset_library(registry, params.get("asset_library_path"))
            asset_plan = _match_series_assets(episode_script, shot_list, library)
            return {
                "ok": True,
                "path": "",
                "content": json.dumps(asset_plan, ensure_ascii=False, indent=2),
                "asset_plan": asset_plan,
            }
        except Exception as exc:
            return {"ok": False, "error": f"series asset match failed: {exc}"}

    def match_series_actions(params: dict) -> dict:
        try:
            episode_script = params.get("episode_script") or {}
            shot_list = params.get("shot_list") or {}
            library = _load_series_asset_library(registry, params.get("asset_library_path"))
            action_plan = _match_series_actions(episode_script, shot_list, library)
            return {
                "ok": True,
                "path": "",
                "content": json.dumps(action_plan, ensure_ascii=False, indent=2),
                "action_plan": action_plan,
            }
        except Exception as exc:
            return {"ok": False, "error": f"series action match failed: {exc}"}

    def forge_3d_series_episode(params: dict) -> dict:
        try:
            episode_script = params.get("episode_script") or {}
            shot_list = params.get("shot_list") or {}
            asset_plan = params.get("asset_plan") or {}
            action_plan = params.get("action_plan") or {}
            output_dir = str(params.get("output_dir") or "test_output/series_3d_episode").strip()
            episode_id = _safe_slug(str(params.get("episode_id") or _series_episode_title(episode_script) or "series_episode"))
            package = _normalize_series_episode_package(episode_script, shot_list, asset_plan, action_plan)
            missing_assets = (package.get("asset_plan") or {}).get("missing") or []
            missing_actions = (package.get("action_plan") or {}).get("missing") or []
            if missing_assets or missing_actions:
                return {
                    "ok": False,
                    "error": "real Blender render is blocked by unresolved asset or action requirements",
                    "missing_assets": missing_assets,
                    "missing_actions": missing_actions,
                }
            package["output_stem"] = episode_id
            package["render_settings"] = {
                "width": _safe_int(params.get("render_width"), 360, 180, 1080),
                "height": _safe_int(params.get("render_height"), 640, 320, 1920),
                "fps": _safe_int(params.get("render_fps"), 24, 12, 60),
                "samples": _safe_int(params.get("render_samples"), 8, 1, 64),
                "render_control_passes": _truthy(params.get("render_control_passes", False)),
            }
            target_dir = registry._safe_path(output_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            plan_path = target_dir / f"{episode_id}.episode_plan.json"
            blender_path = target_dir / f"{episode_id}.blender_scene.py"
            preview_path = target_dir / f"{episode_id}.preview.html"
            manifest_path = target_dir / f"{episode_id}.manifest.json"
            blend_path = target_dir / f"{episode_id}.blend"
            still_path = target_dir / f"{episode_id}.poster.png"
            video_path = target_dir / f"{episode_id}.final.mp4"
            render_report_path = target_dir / f"{episode_id}.render.json"
            control_bundle_path = target_dir / f"{episode_id}.control_bundle.json"

            plan_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
            blender_path.write_text(_render_series_blender_script(package), encoding="utf-8")
            rel_plan = _workspace_rel(registry, plan_path)
            rel_blender = _workspace_rel(registry, blender_path)

            execute_blender = _truthy(params.get("execute_blender", True))
            blender_binary = ""
            blender_seconds = 0.0
            rendered = False
            blender_log = ""
            if execute_blender:
                blender_binary = _find_blender_binary(params.get("blender_path")) or ""
                if not blender_binary:
                    return {
                        "ok": False,
                        "error": "Blender executable not found; set BLENDER_BIN or install the portable runtime under .tools",
                        "files": [rel_plan, rel_blender],
                    }
                started = time.monotonic()
                env = dict(os.environ)
                env["CF_WORKSPACE_ROOT"] = str(registry._workspace_root.resolve())
                timeout_seconds = _safe_int(params.get("blender_timeout_seconds"), 300, 30, 1800)
                result = subprocess.run(
                    [
                        blender_binary,
                        "--background",
                        "--factory-startup",
                        "--python",
                        str(blender_path),
                    ],
                    cwd=str(registry._workspace_root.resolve()),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
                blender_seconds = round(time.monotonic() - started, 3)
                blender_log = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()[-6000:]
                if result.returncode != 0:
                    return {
                        "ok": False,
                        "error": f"Blender exited with code {result.returncode}: {blender_log}",
                        "files": [rel_plan, rel_blender],
                    }
                expected_outputs = {
                    blend_path: 1024,
                    still_path: 1024,
                    video_path: 1024,
                    render_report_path: 64,
                }
                if package["render_settings"].get("render_control_passes"):
                    expected_outputs[control_bundle_path] = 128
                missing_outputs = [
                    path.name
                    for path, minimum_size in expected_outputs.items()
                    if not path.is_file() or path.stat().st_size <= minimum_size
                ]
                if missing_outputs:
                    return {
                        "ok": False,
                        "error": f"Blender did not create valid outputs: {missing_outputs}: {blender_log}",
                        "files": [rel_plan, rel_blender],
                    }
                rendered = True

            rel_blend = _workspace_rel(registry, blend_path) if rendered else ""
            rel_still = _workspace_rel(registry, still_path) if rendered else ""
            rel_video = _workspace_rel(registry, video_path) if rendered else ""
            rel_render_report = _workspace_rel(registry, render_report_path) if rendered else ""
            rel_control_bundle = _workspace_rel(registry, control_bundle_path) if rendered and package["render_settings"].get("render_control_passes") else ""
            control_bundle = {}
            if rel_control_bundle:
                control_bundle = json.loads(control_bundle_path.read_text(encoding="utf-8"))
            preview_path.write_text(
                _render_series_episode_preview_html(package, rel_blender, rel_video, rel_still),
                encoding="utf-8",
            )
            rel_preview = _workspace_rel(registry, preview_path)
            manifest = {
                "schema": "series_3d_episode_manifest.v1",
                "status": "full_episode_rendered" if rendered else "blender_script_created",
                "title": package["episode_script"].get("title"),
                "provider": "local_blender_3d" if rendered else "blender_script_only",
                "episode_plan": rel_plan,
                "blender_script": rel_blender,
                "preview": rel_preview,
                "blend_project": rel_blend,
                "still": rel_still,
                "video": rel_video,
                "render_report": rel_render_report,
                "control_bundle": rel_control_bundle,
                "control_bundle_content": control_bundle,
                "blender_binary": blender_binary,
                "render_seconds": blender_seconds,
                "render_scope": "full_episode",
                "duration_seconds": package.get("duration_seconds"),
                "shot_count": len(package.get("shots") or []),
                "quality_gate": "real_multi_shot_episode_rendered" if rendered else "script_only_not_rendered",
                "notes": (
                    "Pure Blender production renders every planned shot on one timeline. It uses the selected character, "
                    "per-shot motion clips and cameras, scene components, PBR materials, and HDRI."
                ),
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            rel_manifest = _workspace_rel(registry, manifest_path)
            files = [rel_plan, rel_blender, rel_preview, rel_manifest]
            if rendered:
                files.extend([rel_blend, rel_still, rel_video, rel_render_report])
                if rel_control_bundle:
                    files.append(rel_control_bundle)
            return {
                "ok": True,
                "path": rel_video or rel_preview,
                "project_path": rel_blend or rel_plan,
                "video_path": rel_video,
                "preview_path": rel_preview,
                "manifest_path": rel_manifest,
                "control_bundle_path": rel_control_bundle,
                "control_bundle": control_bundle,
                "files": files,
                "content": json.dumps(manifest, ensure_ascii=False, indent=2),
                "series_episode_ok": rendered,
                "provider": manifest["provider"],
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"series episode forge failed: {exc}"}

    registry._registry["media"].update({
        'match_series_assets': match_series_assets,
        'match_series_actions': match_series_actions,
        'forge_3d_series_episode': forge_3d_series_episode,
    })
