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

from . import media_core as _media_core

for _name in dir(_media_core):
    if _name.startswith("_"):
        globals()[_name] = getattr(_media_core, _name)

DLC_ID = 'dlc.pixel_episode'
DLC_PROTOCOL = 'CF-FARP@0.4'
TOOLS = ['generate_pixel_shot_plan', 'validate_pixel_shot_plan', 'update_pixel_world_state', 'check_pixel_assets', 'comfyui_generate_asset', 'forge_pixel_character_asset', 'forge_pixel_location_asset', 'forge_pixel_asset_batch', 'godot_render_pixel_episode', 'ffmpeg_mux_episode']

def _find_godot_binary() -> str | None:
    configured = os.environ.get("GODOT_BIN", "").strip()
    candidates = [configured] if configured else []
    repo_root = Path(__file__).resolve().parents[3]
    runtime_roots = [
        repo_root / ".data" / "mcp_runtime" / "godot",
        Path.cwd() / ".data" / "mcp_runtime" / "godot",
        repo_root / ".tools" / "godot",
    ]
    for runtime_root in runtime_roots:
        marker = runtime_root / "GODOT_BIN.txt"
        if marker.is_file():
            try:
                candidates.append(marker.read_text(encoding="utf-8").strip())
            except OSError:
                pass
        if runtime_root.is_dir():
            candidates.extend(str(path) for path in sorted(runtime_root.rglob("Godot*_win64*.exe")))
            candidates.extend(str(path) for path in sorted(runtime_root.rglob("godot*.exe")))
    candidates.extend([
        "godot",
        "godot4",
        "Godot_v4.3-stable_win64.exe",
        "Godot_v4.4-stable_win64.exe",
        "Godot_v4.5-stable_win64.exe",
        "Godot_v4.6-stable_win64.exe",
        "Godot_v4.7-stable_win64.exe",
        "Godot_v4.7.1-stable_win64.exe",
    ])
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if path.is_file():
            return str(path)
        found = shutil.which(candidate)
        if found:
            return found
    return None

def _maybe_render_pixel_episode_with_godot(
    registry: BuiltinMcpRegistry,
    avi_path: Path,
    plan: dict,
    shot_plan_path: str,
    shot_plan_content,
    target_dir: Path,
    stem: str,
) -> tuple[dict | None, str]:
    godot = _find_godot_binary()
    if not godot:
        return None, "godot binary not found; set GODOT_BIN or put godot/godot4 on PATH"

    project_dir = registry._safe_path("cartridges/dev/dev.pixel_episode_director/assets/pixel_stage/godot_project")
    if not project_dir.is_dir():
        return None, f"godot project not found: {_workspace_rel(registry, project_dir)}"
    cartridge_root = registry._safe_path("cartridges/dev/dev.pixel_episode_director")
    asset_manifest = cartridge_root / "assets" / "asset_manifest.json"

    try:
        source_plan = registry._safe_path(shot_plan_path)
    except PermissionError:
        source_plan = target_dir / f"{stem}.godot_shot_plan.json"
    if not source_plan.is_file() or str(shot_plan_content or "").strip():
        source_plan = target_dir / f"{stem}.godot_shot_plan.json"
        source_plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    width, height = _pixel_resolution(plan)
    fps = _safe_int((plan.get("style") or {}).get("fps"), 24, 1, 60)
    timeline = _pixel_timeline(plan)
    duration = max(1, int(math.ceil(timeline[-1]["end"])))
    frame_count = max(1, duration * fps)
    if avi_path.exists():
        try:
            avi_path.unlink()
        except OSError:
            pass

    cmd = [
        godot,
        "--path",
        str(project_dir),
        "--audio-driver",
        "Dummy",
        "--resolution",
        f"{width}x{height}",
        "--fixed-fps",
        str(fps),
        "--write-movie",
        str(avi_path),
        "--quit-after",
        str(frame_count),
        "--",
        "--shot-plan",
        str(source_plan),
        "--width",
        str(width),
        "--height",
        str(height),
        "--duration",
        str(duration),
        "--asset-manifest",
        str(asset_manifest),
        "--cartridge-root",
        str(cartridge_root),
    ]
    if _truthy(os.environ.get("GODOT_HEADLESS")):
        cmd.insert(1, "--headless")
    timeout_seconds = max(120, duration * 12)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_dir),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return None, f"godot execution failed: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-2000:]
        return None, f"godot exited with code {result.returncode}: {detail}"
    if not avi_path.is_file() or avi_path.stat().st_size <= 1024:
        detail = (result.stderr or result.stdout or "").strip()[-2000:]
        return None, f"godot did not produce a valid movie: {detail}"

    return {
        "renderer": "godot_movie_maker",
        "godot_binary": godot,
        "godot_project": _workspace_rel(registry, project_dir),
        "asset_manifest": _workspace_rel(registry, asset_manifest),
        "godot_shot_plan": _workspace_rel(registry, source_plan),
        "width": width,
        "height": height,
        "fps": fps,
        "duration_seconds": duration,
        "frame_count": frame_count,
        "frames_written": 0,
        "control_frames_written": 0,
        "shot_count": len(timeline),
        "movie_writer": "godot --write-movie",
    }, ""

def _pixel_asset_direction(value, draft_bundle=None) -> dict:
    specs = _coerce_json_dict(value)
    bundle = _coerce_json_dict(draft_bundle)
    assets = specs.get("assets") if isinstance(specs, dict) else None
    requested_assets = []
    if isinstance(assets, list):
        for item in assets:
            if not isinstance(item, dict):
                continue
            requested_assets.append({
                "id": str(item.get("id") or item.get("asset_id") or "").strip(),
                "kind": _normalize_pixel_asset_kind(str(item.get("kind") or item.get("asset_kind") or "")),
                "name": str(item.get("name") or item.get("display_name") or "").strip(),
                "visual_prompt": str(item.get("visual_prompt") or item.get("prompt") or item.get("description") or "").strip()[:240],
                "target_status": str(item.get("target_status") or item.get("register_mode") or "draft").strip(),
            })
    result = {}
    if requested_assets:
        result["schema"] = str(specs.get("schema") or "asset_spec_batch.v1")
        result["requested_assets"] = requested_assets
    if bundle:
        result["draft_bundle_status"] = str(bundle.get("status") or "")
        result["draft_asset_count"] = bundle.get("asset_count") or bundle.get("count") or 0
        result["requires_user_review"] = bool(bundle.get("requires_user_review"))
    return result

def _pixel_story_direction(value) -> dict:
    data = _coerce_json_dict(value)
    if not data:
        return {}
    raw_beats = data.get("beats") or data.get("story_beats") or data.get("items") or []
    if isinstance(raw_beats, dict):
        raw_beats = list(raw_beats.values())
    beats = []
    if isinstance(raw_beats, list):
        for index, item in enumerate(raw_beats, start=1):
            if isinstance(item, str):
                summary = item.strip()
                beat = {"id": f"beat_{index:02d}", "summary": summary[:240], "intent": ""}
            elif isinstance(item, dict):
                summary = str(item.get("summary") or item.get("goal") or item.get("description") or item.get("text") or "").strip()
                beat = {
                    "id": str(item.get("id") or f"beat_{index:02d}").strip(),
                    "summary": summary[:240],
                    "intent": str(item.get("intent") or item.get("type") or "").strip(),
                }
                for key in ("dialogue_hint", "shot_note", "emotion"):
                    value = item.get(key)
                    if value:
                        beat[key] = str(value).strip()[:180]
            else:
                continue
            if beat.get("summary") or beat.get("intent"):
                beats.append(beat)
    result = {
        "schema": str(data.get("schema") or "story_beats.v1"),
        "approved_by_user": bool(data.get("approved_by_user")),
        "beats": beats,
    }
    if data.get("summary"):
        result["summary"] = str(data.get("summary")).strip()[:240]
    return result if beats or result.get("summary") else {}

def _pixel_camera_direction(value, shot_presets: dict | None = None) -> dict:
    data = _coerce_json_dict(value)
    if not data:
        return {}
    presets = (shot_presets or {}).get("presets") or {}
    raw_items = data.get("shots") or data.get("camera_beats") or data.get("items") or []
    if isinstance(raw_items, dict):
        raw_items = list(raw_items.values())
    shots = []
    if isinstance(raw_items, list):
        for position, item in enumerate(raw_items, start=1):
            if isinstance(item, str):
                continue
            if not isinstance(item, dict):
                continue
            camera = item.get("camera") if isinstance(item.get("camera"), dict) else {}
            camera_type = str(
                item.get("camera_type")
                or item.get("preset")
                or item.get("type")
                or camera.get("type")
                or ""
            ).strip()
            if presets and camera_type not in presets:
                continue
            shot_index = _safe_int(item.get("shot_index") or item.get("index") or position, position, 1, 99)
            shots.append({
                "shot_index": shot_index,
                "camera_type": camera_type,
                "note": str(item.get("note") or item.get("description") or camera.get("note") or "").strip()[:240],
                "camera": camera,
            })
    result = {
        "schema": str(data.get("schema") or "camera_plan.v1"),
        "approved_by_user": bool(data.get("approved_by_user")),
        "global_style": str(data.get("global_style") or data.get("style") or "").strip()[:240],
        "shots": shots,
    }
    return result if shots or result.get("global_style") else {}

def _apply_pixel_story_direction(shots: list[dict], story_direction: dict | None) -> None:
    if not story_direction:
        return
    beats = story_direction.get("beats") if isinstance(story_direction.get("beats"), list) else []
    for index, beat in enumerate(beats):
        if index >= len(shots) or not isinstance(beat, dict):
            break
        shot = shots[index]
        summary = str(beat.get("summary") or "").strip()
        intent = str(beat.get("intent") or "").strip()
        shot["story_beat"] = {
            "id": str(beat.get("id") or f"beat_{index + 1:02d}").strip(),
            "summary": summary,
            "intent": intent,
        }
        dialogue_hint = str(beat.get("dialogue_hint") or "").strip()
        if dialogue_hint and not shot.get("dialogue"):
            shot["dialogue"] = [{"speaker": "hero", "text": dialogue_hint[:64]}]
        note = str(beat.get("shot_note") or summary or intent or "").strip()
        camera = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
        if note and isinstance(camera, dict):
            current = str(camera.get("note") or "").strip()
            if note not in current:
                camera["note"] = (current + " " + note).strip()[:420]
            shot["camera"] = camera

def _pixel_camera_payload_for_type(camera_type: str, base_camera: dict, shot_presets: dict | None) -> dict:
    payload = dict(base_camera or {})
    payload["type"] = camera_type
    preset = ((shot_presets or {}).get("presets") or {}).get(camera_type) or {}
    defaults = preset.get("defaults") if isinstance(preset.get("defaults"), dict) else {}
    for key, value in defaults.items():
        payload.setdefault(key, value)
    required = set(str(item) for item in (preset.get("required_params") or []))
    if "target" in required and not payload.get("target"):
        payload["target"] = str((base_camera or {}).get("target") or "hero")
    if "shoulder_actor" in required and not payload.get("shoulder_actor"):
        payload["shoulder_actor"] = str((base_camera or {}).get("shoulder_actor") or "vendor")
    if "from" in required and not payload.get("from"):
        payload["from"] = [2, 0]
    if "to" in required and not payload.get("to"):
        payload["to"] = [7, 0]
    return payload

def _apply_pixel_camera_direction(shots: list[dict], camera_direction: dict | None, shot_presets: dict | None) -> None:
    if not camera_direction:
        return
    directives = camera_direction.get("shots") if isinstance(camera_direction.get("shots"), list) else []
    for directive in directives:
        if not isinstance(directive, dict):
            continue
        shot_index = _safe_int(directive.get("shot_index"), 0, 1, 99) - 1
        if shot_index < 0 or shot_index >= len(shots):
            continue
        camera_type = str(directive.get("camera_type") or "").strip()
        if not camera_type:
            continue
        shot = shots[shot_index]
        base_camera = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
        camera = _pixel_camera_payload_for_type(camera_type, base_camera, shot_presets)
        raw_camera = directive.get("camera") if isinstance(directive.get("camera"), dict) else {}
        for key, value in raw_camera.items():
            if key != "type" and value not in (None, ""):
                camera[key] = value
        note = str(directive.get("note") or raw_camera.get("note") or "").strip()
        if note:
            current = str(camera.get("note") or "").strip()
            if note not in current:
                camera["note"] = (current + " " + note).strip()[:420]
        shot["camera"] = camera
        shot["camera_directive"] = {
            "source": "camera_plan.v1",
            "camera_type": camera_type,
            "note": note,
        }

def _pixel_episode_title(goal: str) -> str:
    text = _clean_spoken_text(goal)
    if not text:
        return "夜市小巷"
    for sep in ["，", "。", ",", ".", "；", ";", "并", "然后"]:
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    return text[:18] or "夜市小巷"

def _build_pixel_shot_plan(
    episode_id: str,
    episode_goal: str,
    style_notes: str,
    output_path: str,
    world_state: dict | None = None,
    shot_presets: dict | None = None,
    shot_count: int = 3,
    asset_direction: dict | None = None,
    story_direction: dict | None = None,
    camera_direction: dict | None = None,
) -> dict:
    profile = _pixel_goal_profile(episode_goal)
    world_state = world_state if isinstance(world_state, dict) else _default_pixel_world_state()
    shot_presets = shot_presets if isinstance(shot_presets, dict) else _default_pixel_shot_presets()
    shot_count = _safe_int(shot_count, 3, 3, 6)
    hero_state = ((world_state.get("characters") or {}).get("hero") or {}) if isinstance(world_state.get("characters"), dict) else {}
    vendor_state = ((world_state.get("characters") or {}).get("vendor") or {}) if isinstance(world_state.get("characters"), dict) else {}
    hero_start = _pixel_position(hero_state.get("position"), [4, 6, 1])
    vendor_pos = _pixel_position(vendor_state.get("position"), [11, 6, 1])
    final_camera = _pixel_goal_camera(episode_goal, str(profile.get("final_camera") or "push_in"))
    final_camera_payload = _pixel_final_camera(final_camera, shot_presets)
    shots = [
        {
            "id": "shot_001",
            "duration": 4,
            "location": "night_alley",
            "camera": {
                "type": "wide_establishing",
                "position": [0, 0],
                "zoom": 0.85,
                "note": f"建立夜市小巷空间，突出{profile['clue']}和前后景层次。",
            },
            "actors": [
                {"id": "hero", "position": hero_start, "animation": "idle", "emotion": profile["start_emotion"]}
            ],
            "dialogue": [],
        },
        {
            "id": "shot_002",
            "duration": 5,
            "location": "night_alley",
            "camera": {
                "type": "tracking_side",
                "target": "hero",
                "from": [2, 0],
                "to": [7, 0],
                "zoom": 1.0,
                "note": f"横向跟拍主角经过摊位，观察{profile['clue']}。",
            },
            "actors": [
                {"id": "hero", "position": [5, 6, 1], "move_to": [9, 6, 1], "animation": "walk_right", "emotion": "alert"},
                {"id": "vendor", "position": vendor_pos, "animation": "talk_idle", "emotion": "neutral"},
            ],
            "dialogue": [
                {"speaker": "vendor", "text": profile["vendor_line"]}
            ],
        },
    ]
    if shot_count >= 4:
        shots.append({
            "id": "shot_003",
            "duration": 3,
            "location": "night_alley",
            "camera": {
                "type": "close_up",
                "target": "hero",
                "zoom": 1.45,
                "note": f"插入线索特写，让{profile['clue']}成为镜头焦点。",
            },
            "actors": [
                {"id": "hero", "position": [8, 6, 1], "animation": "look_around", "emotion": "alert"}
            ],
            "dialogue": [],
        })
    if shot_count >= 5:
        shots.append({
            "id": "shot_004",
            "duration": 4,
            "location": "night_alley",
            "camera": {
                "type": "over_shoulder",
                "target": "hero",
                "shoulder_actor": "vendor",
                "from": [5, 0],
                "to": [7, 0],
                "zoom": 1.2,
                "note": "用摊主肩后视角制造被注视的压力。",
            },
            "actors": [
                {"id": "hero", "position": [8, 6, 1], "animation": "look_around", "emotion": "alert"},
                {"id": "vendor", "position": vendor_pos, "animation": "talk_idle", "emotion": "neutral"},
            ],
            "dialogue": [
                {"speaker": "vendor", "text": "别回头，灯影里有人。"}
            ],
        })
    shots.append({
        "id": f"shot_{len(shots) + 1:03d}",
        "duration": 4,
        "location": "night_alley",
        "camera": {**final_camera_payload, "note": profile["final_note"]},
        "actors": [
            {"id": "hero", "position": [9, 6, 1], "animation": "look_around", "emotion": profile["final_emotion"]}
        ],
        "dialogue": [
            {"speaker": "hero", "text": profile["hero_line"]}
        ],
    })
    if shot_count >= 6:
        shots.append({
            "id": f"shot_{len(shots) + 1:03d}",
            "duration": 4,
            "location": "night_alley",
            "camera": {
                "type": "wide_establishing",
                "position": [1, 0],
                "zoom": 0.9,
                "note": "拉回小巷全景，留下下一集继续追踪的空间。",
            },
            "actors": [
                {"id": "hero", "position": [10, 6, 1], "animation": "idle", "emotion": profile["final_emotion"]},
                {"id": "vendor", "position": vendor_pos, "animation": "idle", "emotion": "neutral"},
            ],
            "dialogue": [],
        })
    for index, shot in enumerate(shots, start=1):
        shot["id"] = f"shot_{index:03d}"
    _apply_pixel_story_direction(shots, story_direction)
    _apply_pixel_camera_direction(shots, camera_direction, shot_presets)
    plan = {
        "episode_id": episode_id,
        "title": _pixel_episode_title(episode_goal),
        "style": {
            "mode": "pixel_2_5d",
            "resolution": "1280x720",
            "fps": 24,
            "notes": style_notes or profile["style_notes"],
        },
        "source_goal": episode_goal,
        "continuity": {
            "world_state_version": world_state.get("version", 1),
            "previous_episode_id": world_state.get("last_episode_id", ""),
            "starting_location": world_state.get("current_location", "night_alley"),
            "open_threads": list(world_state.get("open_threads") or [])[:6],
            "hero_inventory": list(hero_state.get("inventory") or []),
        },
        "shots": shots,
        "validation_contract": {
            "characters": ["hero", "vendor"],
            "locations": ["night_alley"],
            "camera_presets": sorted((shot_presets.get("presets") or {}).keys()) or ["wide_establishing", "tracking_side", "push_in"],
        },
        "next_pipeline": {
            "godot_input": output_path.replace("\\", "/"),
            "expected_renderer": "Godot 2D Camera2D pixel stage",
        },
    }
    if asset_direction:
        plan["asset_direction"] = asset_direction
    if story_direction:
        plan["story_direction"] = story_direction
    if camera_direction:
        plan["camera_direction"] = camera_direction
    return plan

def _pixel_goal_camera(goal: str, fallback: str = "push_in") -> str:
    text = _clean_spoken_text(goal)
    lower = text.lower()
    if any(keyword in text for keyword in ["跟踪", "跟蹤", "追", "盯", "尾随", "尾隨"]) or any(keyword in lower for keyword in ["follow", "trail", "stalk", "shadow"]):
        return "over_shoulder"
    if any(keyword in text for keyword in ["钥匙", "鑰匙", "门", "門", "锁", "鎖", "纸条", "紙條", "密码", "密碼"]) or any(keyword in lower for keyword in ["key", "door", "lock", "note", "password", "code"]):
        return "reveal"
    if any(keyword in text for keyword in ["灯", "燈", "闪", "閃", "电", "電", "信号", "信號"]) or any(keyword in lower for keyword in ["lamp", "light", "flicker", "signal", "electric"]):
        return "close_up"
    return fallback or "push_in"

def _pixel_final_camera(camera_type: str, shot_presets: dict) -> dict:
    presets = shot_presets.get("presets") or {}
    if camera_type not in presets:
        camera_type = "push_in"
    if camera_type == "close_up":
        return {"type": "close_up", "target": "hero", "zoom": 1.55}
    if camera_type == "over_shoulder":
        return {"type": "over_shoulder", "target": "hero", "shoulder_actor": "vendor", "zoom": 1.25, "from": [5, 0], "to": [7, 0]}
    if camera_type == "reveal":
        return {"type": "reveal", "target": "hero", "zoom_from": 1.05, "zoom_to": 1.35, "reveal_axis": "foreground_left"}
    return {"type": "push_in", "target": "hero", "zoom_from": 1.0, "zoom_to": 1.45}

def _pixel_position(value, fallback: list) -> list:
    if isinstance(value, list) and len(value) >= 2:
        result = [_pixel_float(value[0], fallback[0]), _pixel_float(value[1], fallback[1])]
        result.append(_pixel_float(value[2], fallback[2] if len(fallback) > 2 else 1) if len(value) > 2 else (fallback[2] if len(fallback) > 2 else 1))
        return result
    return list(fallback)

def _pixel_goal_profile(goal: str) -> dict:
    text = _clean_spoken_text(goal)
    profiles = [
        (["雨", "积水", "水"], {
            "clue": "积水里的反常倒影",
            "vendor_line": "这片积水没有风，却一直在晃。",
            "hero_line": "倒影里多了一个影子。",
            "start_emotion": "alert",
            "final_emotion": "suspicious",
            "final_note": "推近到主角特写，表现他从倒影里发现异常。",
            "style_notes": "低帧率像素风、潮湿地面反光、2.5D 视差、慢速推近。",
        }),
        (["钥匙", "门", "锁"], {
            "clue": "摊位下方露出的旧钥匙",
            "vendor_line": "那把钥匙不是卖的，是有人故意留下的。",
            "hero_line": "它在指向巷子尽头那扇门。",
            "start_emotion": "alert",
            "final_emotion": "suspicious",
            "final_note": "推近到主角特写，表现他意识到钥匙和远处门牌有关。",
            "style_notes": "低帧率像素风、暖色摊位灯、前景遮挡、简单推近。",
        }),
        (["跟踪", "追", "盯", "尾随"], {
            "clue": "忽明忽暗的路灯和背后脚步",
            "vendor_line": "你刚过去时，后面那个人也停了。",
            "hero_line": "有人在后面。",
            "start_emotion": "alert",
            "final_emotion": "suspicious",
            "final_note": "推近到主角特写，表现他意识到被跟踪。",
            "style_notes": "低帧率像素风、2.5D 视差、背后灯光闪烁、横移跟拍。",
        }),
        (["灯", "闪", "电"], {
            "clue": "异常闪烁的路灯",
            "vendor_line": "这盏灯今晚已经闪了三次。",
            "hero_line": "闪烁的节奏像是在发信号。",
            "start_emotion": "alert",
            "final_emotion": "suspicious",
            "final_note": "推近到主角特写，表现他读懂灯光节奏。",
            "style_notes": "低帧率像素风、闪烁路灯、2.5D 视差、简单推近和横移。",
        }),
        (["纸条", "信", "号码", "密码"], {
            "clue": "摊位边缘压着的红色纸条",
            "vendor_line": "刚才有人把纸条塞在灯箱下面。",
            "hero_line": "这不是地址，是一串密码。",
            "start_emotion": "alert",
            "final_emotion": "suspicious",
            "final_note": "推近到主角特写，表现他看懂纸条上的隐藏信息。",
            "style_notes": "低帧率像素风、红色纸条焦点、2.5D 视差、稳定角色动作。",
        }),
    ]
    for keywords, profile in profiles:
        if any(keyword in text for keyword in keywords):
            return profile
    return {
        "clue": "摊位之间出现的异常线索",
        "vendor_line": "这条巷子今晚有点不对劲。",
        "hero_line": "线索就在前面。",
        "start_emotion": "alert",
        "final_emotion": "suspicious",
        "final_note": "推近到主角特写，表现他确认下一步行动。",
        "style_notes": "低帧率像素风、2.5D 视差、简单运镜、稳定角色动作。",
    }

def _load_pixel_shot_plan(registry: BuiltinMcpRegistry, shot_plan_path: str, shot_plan_content) -> dict:
    text = str(shot_plan_content or "").strip()
    if not text:
        target = registry._safe_path(shot_plan_path or "test_output/pixel_episode/shot_plan.json")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"镜头表不存在：{shot_plan_path}")
        text = target.read_text(encoding="utf-8", errors="replace")
    plan = json.loads(text)
    if not isinstance(plan, dict):
        raise ValueError("shot_plan.json 必须是 JSON object")
    if not isinstance(plan.get("shots"), list) or not plan["shots"]:
        raise ValueError("shot_plan.json 缺少 shots 数组")
    return plan

def _load_pixel_world_state(registry: BuiltinMcpRegistry, world_state_path: str, world_state_content) -> dict:
    text = str(world_state_content or "").strip()
    if text:
        data = json.loads(text)
        return data if isinstance(data, dict) else _default_pixel_world_state()
    data, _path = _read_pixel_json_file(registry, world_state_path, _default_pixel_world_state())
    return data

def _load_pixel_shot_presets(registry: BuiltinMcpRegistry, shot_presets_path: str, shot_presets_content) -> dict:
    text = str(shot_presets_content or "").strip()
    if text:
        data = json.loads(text)
        return data if isinstance(data, dict) else _default_pixel_shot_presets()
    data, _path = _read_pixel_json_file(registry, shot_presets_path, _default_pixel_shot_presets())
    if not isinstance(data.get("presets"), dict):
        return _default_pixel_shot_presets()
    return data

def _validate_pixel_shot_plan(registry: BuiltinMcpRegistry, plan: dict, series_bible_path: str, asset_manifest_path: str, shot_presets_path: str | None = None, shot_presets_content=None) -> dict:
    series_bible, series_path = _read_pixel_json_file(registry, series_bible_path, _default_pixel_series_bible())
    asset_manifest, asset_path = _read_pixel_json_file(registry, asset_manifest_path, {"approved_assets": {}})
    shot_presets = _load_pixel_shot_presets(registry, shot_presets_path or "cartridges/dev/dev.pixel_episode_director/assets/shot_presets.json", shot_presets_content or "")
    issues = []
    repairs = []
    allowed_locations = {str(item.get("id")) for item in series_bible.get("locations") or [] if isinstance(item, dict) and item.get("id")}
    allowed_cameras = {str(item) for item in (shot_presets.get("presets") or {}).keys()}
    if not allowed_cameras:
        allowed_cameras = {str(item) for item in series_bible.get("camera_presets") or []}
    characters = {
        str(item.get("id")): set(str(action) for action in item.get("available_actions") or [])
        for item in series_bible.get("characters") or []
        if isinstance(item, dict) and item.get("id")
    }
    required_fields = list((series_bible.get("shot_contract") or {}).get("required_fields") or ["id", "duration", "location", "camera", "actors", "dialogue"])
    shots = plan.get("shots") or []
    seen_ids = set()
    used_characters = set()
    used_locations = set()
    used_cameras = set()
    total_duration = 0

    if len(shots) < 3:
        issues.append("shots 至少需要 3 个镜头。")
        repairs.append("补足 establishing / action / reaction 三段式镜头。")

    for index, shot in enumerate(shots):
        prefix = f"shots[{index}]"
        if not isinstance(shot, dict):
            issues.append(f"{prefix} 必须是 object。")
            repairs.append(f"把 {prefix} 改为包含 id、duration、location、camera、actors、dialogue 的 object。")
            continue
        for field in required_fields:
            if field not in shot:
                issues.append(f"{prefix} 缺少字段 {field}。")
                repairs.append(f"给 {prefix} 添加 {field} 字段。")
        shot_id = str(shot.get("id") or "").strip()
        if not shot_id:
            issues.append(f"{prefix} 缺少有效 id。")
            repairs.append(f"给 {prefix} 设置 shot_{index + 1:03d}。")
        elif shot_id in seen_ids:
            issues.append(f"{prefix} id 重复：{shot_id}。")
            repairs.append(f"重命名 {prefix}.id，确保每个镜头唯一。")
        seen_ids.add(shot_id)

        duration = _safe_int(shot.get("duration"), 0, 0, 999)
        total_duration += duration
        if duration < 1 or duration > 30:
            issues.append(f"{prefix}.duration 必须在 1-30 秒之间。")
            repairs.append(f"把 {prefix}.duration 调整为 3-8 秒。")

        location = str(shot.get("location") or "").strip()
        used_locations.add(location)
        if allowed_locations and location not in allowed_locations:
            issues.append(f"{prefix}.location 未在系列设定中登记：{location}。")
            repairs.append(f"把 {prefix}.location 改为 {sorted(allowed_locations)[0]} 或先补资产。")

        camera = shot.get("camera")
        if not isinstance(camera, dict):
            issues.append(f"{prefix}.camera 必须是 object。")
            repairs.append(f"给 {prefix}.camera 设置 type 和对应参数。")
        else:
            camera_type = str(camera.get("type") or "").strip()
            used_cameras.add(camera_type)
            if allowed_cameras and camera_type not in allowed_cameras:
                issues.append(f"{prefix}.camera.type 未在镜头库中登记：{camera_type}。")
                repairs.append(f"把 {prefix}.camera.type 改为 {', '.join(sorted(allowed_cameras))} 之一。")

        if isinstance(camera, dict):
            preset = (shot_presets.get("presets") or {}).get(str(camera.get("type") or "").strip()) or {}
            for param_name in preset.get("required_params") or []:
                if param_name not in camera:
                    issues.append(f"{prefix}.camera missing required preset param {param_name}.")
                    repairs.append(f"Add camera.{param_name} or choose another shot preset.")

        actors = shot.get("actors")
        if not isinstance(actors, list):
            issues.append(f"{prefix}.actors 必须是数组。")
            repairs.append(f"给 {prefix}.actors 添加至少一个已登记角色。")
            actors = []
        for actor_index, actor in enumerate(actors):
            actor_prefix = f"{prefix}.actors[{actor_index}]"
            if not isinstance(actor, dict):
                issues.append(f"{actor_prefix} 必须是 object。")
                repairs.append(f"把 {actor_prefix} 改为角色调度 object。")
                continue
            actor_id = str(actor.get("id") or "").strip()
            animation = str(actor.get("animation") or "").strip()
            used_characters.add(actor_id)
            if actor_id not in characters:
                issues.append(f"{actor_prefix}.id 未在角色库中登记：{actor_id}。")
                repairs.append(f"把 {actor_prefix}.id 改为 {', '.join(sorted(characters))} 之一，或先补角色资产。")
            elif animation and characters[actor_id] and animation not in characters[actor_id]:
                issues.append(f"{actor_prefix}.animation 不属于角色 {actor_id} 的动作库：{animation}。")
                repairs.append(f"把 {actor_prefix}.animation 改为 {', '.join(sorted(characters[actor_id]))} 之一。")
            position = actor.get("position")
            if not isinstance(position, list) or len(position) < 2:
                issues.append(f"{actor_prefix}.position 必须是至少包含 x/y 的数组。")
                repairs.append(f"给 {actor_prefix}.position 设置类似 [6, 6, 1] 的坐标。")

        dialogue = shot.get("dialogue")
        if not isinstance(dialogue, list):
            issues.append(f"{prefix}.dialogue 必须是数组。")
            repairs.append(f"没有对白时把 {prefix}.dialogue 设置为 []。")
            dialogue = []
        for line_index, line in enumerate(dialogue):
            line_prefix = f"{prefix}.dialogue[{line_index}]"
            if not isinstance(line, dict):
                issues.append(f"{line_prefix} 必须是 object。")
                repairs.append(f"把 {line_prefix} 改为包含 speaker/text 的 object。")
                continue
            speaker = str(line.get("speaker") or "").strip()
            if speaker and speaker not in characters:
                issues.append(f"{line_prefix}.speaker 未在角色库中登记：{speaker}。")
                repairs.append(f"把 {line_prefix}.speaker 改为 {', '.join(sorted(characters))} 之一。")
            if speaker:
                used_characters.add(speaker)
            if speaker and not str(line.get("text") or "").strip():
                issues.append(f"{line_prefix}.text 不能为空。")
                repairs.append(f"为 {line_prefix} 补一句短对白。")

    asset_check = _validate_pixel_assets(registry, asset_manifest, asset_path, characters, allowed_locations)
    issues.extend(asset_check["issues"])
    repairs.extend(asset_check["repairs"])
    valid = not issues
    return {
        "valid": valid,
        "issues": issues,
        "repairs": repairs,
        "stats": {
            "shot_count": len(shots),
            "duration_seconds": total_duration,
            "characters": sorted(item for item in used_characters if item),
            "locations": sorted(item for item in used_locations if item),
            "camera_presets": sorted(item for item in used_cameras if item),
        },
        "contract": {
            "series_bible_path": str(series_path) if series_path else "",
            "asset_manifest_path": str(asset_path) if asset_path else "",
            "shot_presets_path": shot_presets_path or "",
            "required_fields": required_fields,
            "allowed_characters": sorted(characters),
            "allowed_locations": sorted(allowed_locations),
            "allowed_camera_presets": sorted(allowed_cameras),
        },
        "asset_check": asset_check["summary"],
    }

def _read_pixel_json_file(registry: BuiltinMcpRegistry, path_str: str, fallback: dict) -> tuple[dict, Path | None]:
    candidates = [path_str]
    if path_str.startswith("assets/"):
        candidates.append(f"cartridges/dev/dev.pixel_episode_director/{path_str}")
    for candidate in candidates:
        try:
            target = registry._safe_path(candidate)
            if target.exists() and target.is_file():
                data = json.loads(target.read_text(encoding="utf-8", errors="replace"))
                return data if isinstance(data, dict) else fallback, target
        except Exception:
            continue
    return fallback, None

def _default_pixel_series_bible() -> dict:
    return {
        "locations": [{"id": "night_alley"}],
        "characters": [
            {"id": "hero", "available_actions": ["idle", "walk_right", "look_around", "talk_idle"]},
            {"id": "vendor", "available_actions": ["idle", "talk_idle"]},
        ],
        "camera_presets": ["wide_establishing", "push_in", "tracking_side", "close_up", "over_shoulder", "reveal"],
        "shot_contract": {"required_fields": ["id", "duration", "location", "camera", "actors", "dialogue"]},
    }

def _default_pixel_shot_presets() -> dict:
    return {
        "version": 1,
        "presets": {
            "wide_establishing": {"required_params": [], "defaults": {"zoom": 0.85}},
            "push_in": {"required_params": ["target"], "defaults": {"zoom_from": 1.0, "zoom_to": 1.45}},
            "tracking_side": {"required_params": ["target", "from", "to"], "defaults": {"zoom": 1.0}},
            "close_up": {"required_params": ["target"], "defaults": {"zoom": 1.55}},
            "over_shoulder": {"required_params": ["target", "shoulder_actor"], "defaults": {"zoom": 1.25}},
            "reveal": {"required_params": ["target"], "defaults": {"zoom_from": 1.05, "zoom_to": 1.35, "reveal_axis": "foreground_left"}},
        },
    }

def _default_pixel_world_state() -> dict:
    return {
        "series_id": "pixel_alley",
        "version": 1,
        "current_location": "night_alley",
        "last_episode_id": "",
        "characters": {
            "hero": {"location": "night_alley", "position": [4, 6, 1], "emotion": "alert", "inventory": [], "costume": "blue jacket"},
            "vendor": {"location": "night_alley", "position": [11, 6, 1], "emotion": "neutral", "inventory": [], "costume": "market apron"},
        },
        "props": {},
        "relationships": {"hero.vendor": "cautious"},
        "open_threads": [],
        "episode_history": [],
    }

def _update_pixel_world_state(world_state: dict, plan: dict, episode_id: str, episode_goal: str) -> tuple[dict, dict]:
    updated = json.loads(json.dumps(world_state if isinstance(world_state, dict) else _default_pixel_world_state(), ensure_ascii=False))
    updated.setdefault("series_id", "pixel_alley")
    updated["version"] = _safe_int(updated.get("version"), 1, 1, 999999) + 1
    episode_id = episode_id or str(plan.get("episode_id") or "ep001")
    shots = [shot for shot in (plan.get("shots") or []) if isinstance(shot, dict)]
    final_location = str(shots[-1].get("location") or updated.get("current_location") or "night_alley") if shots else str(updated.get("current_location") or "night_alley")
    updated["current_location"] = final_location
    updated["last_episode_id"] = episode_id
    characters = updated.setdefault("characters", {})
    changed_characters = []
    for shot in shots:
        location = str(shot.get("location") or final_location)
        for actor in shot.get("actors") or []:
            if not isinstance(actor, dict) or not actor.get("id"):
                continue
            actor_id = str(actor.get("id"))
            item = characters.setdefault(actor_id, {})
            final_position = actor.get("move_to") if isinstance(actor.get("move_to"), list) else actor.get("position")
            if isinstance(final_position, list) and len(final_position) >= 2:
                item["position"] = _pixel_position(final_position, item.get("position") or [6, 6, 1])
            item["location"] = location
            if actor.get("emotion"):
                item["emotion"] = actor.get("emotion")
            if actor.get("animation"):
                item["last_animation"] = actor.get("animation")
            changed_characters.append(actor_id)
    open_threads = list(updated.get("open_threads") or [])
    new_thread = _pixel_world_thread(episode_goal, plan)
    if new_thread and new_thread not in open_threads:
        open_threads.append(new_thread)
    updated["open_threads"] = open_threads[-12:]
    history = list(updated.get("episode_history") or [])
    history.append({
        "episode_id": episode_id,
        "title": plan.get("title") or episode_id,
        "goal": episode_goal or plan.get("source_goal") or "",
        "final_location": final_location,
        "final_camera": ((shots[-1].get("camera") or {}).get("type") if shots else ""),
        "open_thread": new_thread,
        "characters": sorted(set(changed_characters)),
    })
    updated["episode_history"] = history[-20:]
    report = {
        "episode_id": episode_id,
        "world_state_version": updated["version"],
        "current_location": updated["current_location"],
        "updated_characters": sorted(set(changed_characters)),
        "open_threads": updated["open_threads"],
        "last_episode": updated["episode_history"][-1] if updated["episode_history"] else {},
    }
    return updated, report

def _pixel_world_thread(episode_goal: str, plan: dict) -> str:
    text = _clean_spoken_text(episode_goal or plan.get("source_goal") or "")
    lower = text.lower()
    if any(keyword in text for keyword in ["跟踪", "跟蹤", "尾随", "尾隨", "盯"]) or any(keyword in lower for keyword in ["follow", "trail", "stalk", "shadow"]):
        return "someone_is_following_hero"
    if any(keyword in text for keyword in ["灯", "燈", "闪", "閃", "信号", "信號"]) or any(keyword in lower for keyword in ["lamp", "light", "flicker", "signal"]):
        return "flickering_lamp_signal"
    if any(keyword in text for keyword in ["钥匙", "鑰匙", "门", "門", "锁", "鎖"]) or any(keyword in lower for keyword in ["key", "door", "lock"]):
        return "locked_door_key"
    if any(keyword in text for keyword in ["纸条", "紙條", "密码", "密碼"]) or any(keyword in lower for keyword in ["note", "password", "code"]):
        return "coded_note"
    return "unresolved_alley_clue"

def _validate_pixel_assets(registry: BuiltinMcpRegistry, asset_manifest: dict, asset_manifest_path: Path | None, characters: dict, locations: set[str]) -> dict:
    issues = []
    repairs = []
    approved = asset_manifest.get("approved_assets") or {}
    character_assets = approved.get("characters") or {}
    location_assets = approved.get("locations") or {}
    missing_profiles = []
    profile_contracts = []

    for character_id in sorted(characters):
        item = character_assets.get(character_id) or {}
        profile = item.get("profile")
        resolved = _resolve_pixel_asset_profile(registry, asset_manifest_path, profile)
        if not profile or not resolved or not resolved.exists():
            missing_profiles.append(character_id)
            issues.append(f"角色资产缺少 profile：{character_id}。")
            repairs.append(f"补充 assets/pixel_stage/characters/{character_id}/profile.json，并在 asset_manifest.json 登记。")

    for location_id in sorted(locations):
        item = location_assets.get(location_id) or {}
        profile = item.get("profile")
        resolved = _resolve_pixel_asset_profile(registry, asset_manifest_path, profile)
        if not profile or not resolved or not resolved.exists():
            missing_profiles.append(location_id)
            issues.append(f"地点资产缺少 profile：{location_id}。")
            repairs.append(f"补充 assets/pixel_stage/locations/{location_id}/profile.json，并在 asset_manifest.json 登记。")

    for character_id in sorted(characters):
        item = character_assets.get(character_id) or {}
        profile = item.get("profile")
        resolved = _resolve_pixel_asset_profile(registry, asset_manifest_path, profile)
        if not profile or not resolved or not resolved.exists():
            continue
        try:
            profile_data = json.loads(resolved.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            issues.append(f"character_profile_invalid_json:{character_id}:{exc}")
            repairs.append(f"rewrite {profile} as valid JSON before rendering")
            continue
        actions = {str(action) for action in profile_data.get("actions") or []}
        missing_actions = sorted(str(action) for action in characters.get(character_id, set()) if str(action) not in actions)
        if missing_actions:
            issues.append(f"character_profile_missing_actions:{character_id}:{','.join(missing_actions)}")
            repairs.append(f"add missing actions to {profile}: {', '.join(missing_actions)}")
        asset_info = profile_data.get("asset") if isinstance(profile_data.get("asset"), dict) else {}
        for asset_key in ["spritesheet", "metadata"]:
            asset_path = str(asset_info.get(asset_key) or item.get(asset_key) or "").strip()
            resolved_asset = _resolve_pixel_asset_profile(registry, asset_manifest_path, asset_path)
            if not asset_path or not resolved_asset or not resolved_asset.exists():
                issues.append(f"character_asset_missing_{asset_key}:{character_id}")
                repairs.append(f"add a valid {asset_key} path for {character_id} in {profile} or asset_manifest.json")
        render_contract = profile_data.get("render_contract") if isinstance(profile_data.get("render_contract"), dict) else {}
        min_height = _safe_int(render_contract.get("min_screen_height_px"), 0, 0, 9999)
        min_frames = _safe_int(render_contract.get("animation_min_frames"), 0, 0, 9999)
        if min_height < 128:
            issues.append(f"character_profile_min_height_too_low:{character_id}:{min_height}")
            repairs.append(f"set {profile}.render_contract.min_screen_height_px to at least 128")
        if min_frames < 4:
            issues.append(f"character_profile_animation_frames_too_low:{character_id}:{min_frames}")
            repairs.append(f"set {profile}.render_contract.animation_min_frames to at least 4")
        profile_contracts.append({
            "id": character_id,
            "kind": "character",
            "profile": profile,
            "min_screen_height_px": min_height,
            "animation_min_frames": min_frames,
            "actions": sorted(actions),
        })

    for location_id in sorted(locations):
        item = location_assets.get(location_id) or {}
        profile = item.get("profile")
        resolved = _resolve_pixel_asset_profile(registry, asset_manifest_path, profile)
        if not profile or not resolved or not resolved.exists():
            continue
        try:
            profile_data = json.loads(resolved.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            issues.append(f"location_profile_invalid_json:{location_id}:{exc}")
            repairs.append(f"rewrite {profile} as valid JSON before rendering")
            continue
        layers = profile_data.get("layers") if isinstance(profile_data.get("layers"), list) else []
        render_contract = profile_data.get("render_contract") if isinstance(profile_data.get("render_contract"), dict) else {}
        min_layers = _safe_int(render_contract.get("min_layers"), 0, 0, 99)
        expected_layers = max(4, min_layers)
        layer_images = []
        if min_layers < 4:
            issues.append(f"location_profile_min_layers_too_low:{location_id}:{min_layers}")
            repairs.append(f"set {profile}.render_contract.min_layers to at least 4")
        if len(layers) < expected_layers:
            issues.append(f"location_profile_missing_layers:{location_id}:{len(layers)}")
            repairs.append(f"add at least {expected_layers} parallax layers to {profile}")
        for layer_index, layer in enumerate(layers):
            if not isinstance(layer, dict):
                issues.append(f"location_profile_invalid_layer:{location_id}:{layer_index}")
                repairs.append(f"rewrite {profile}.layers[{layer_index}] as an object with id/image/parallax")
                continue
            image_path = str(layer.get("image") or layer.get("path") or "").strip()
            resolved_image = _resolve_pixel_asset_profile(registry, asset_manifest_path, image_path)
            if not image_path or not resolved_image or not resolved_image.exists():
                issues.append(f"location_profile_missing_layer_image:{location_id}:{layer.get('id', layer_index)}")
                repairs.append(f"add a valid PNG image path to {profile}.layers[{layer_index}].image")
            else:
                layer_images.append(image_path)
        if len(layer_images) < expected_layers:
            issues.append(f"location_profile_layer_images_too_few:{location_id}:{len(layer_images)}")
            repairs.append(f"provide at least {expected_layers} rendered PNG layer images for {profile}")
        profile_contracts.append({
            "id": location_id,
            "kind": "location",
            "profile": profile,
            "layer_count": len(layers),
            "min_layers": min_layers,
            "layer_images": layer_images,
        })

    return {
        "issues": issues,
        "repairs": repairs,
        "summary": {
            "approved_characters": sorted(character_assets),
            "approved_locations": sorted(location_assets),
            "missing_profiles": missing_profiles,
            "profile_contracts": profile_contracts,
        },
    }

def _resolve_pixel_asset_profile(registry: BuiltinMcpRegistry, asset_manifest_path: Path | None, profile_path: str | None) -> Path | None:
    if not profile_path:
        return None
    profile_text = str(profile_path).replace("\\", "/")
    candidates = [profile_text]
    if asset_manifest_path and profile_text.startswith("assets/"):
        candidates.append(str(asset_manifest_path.parent / profile_text.removeprefix("assets/")))
    for candidate in candidates:
        try:
            target = registry._safe_path(candidate)
            if target.exists():
                return target
        except Exception:
            target = Path(candidate)
            if target.exists():
                return target
    return None

def _normalize_pixel_asset_kind(kind: str) -> str:
    text = (kind or "background").strip().lower().replace("_", "-")
    aliases = {
        "bg": "background",
        "backgrounds": "background",
        "prop": "prop",
        "props": "prop",
        "character": "character",
        "characters": "character",
        "location": "location",
        "locations": "location",
        "scene": "background",
        "set": "location",
    }
    return aliases.get(text, text if text in {"background", "prop", "character", "location"} else "background")

def _pixel_asset_kind_bucket(kind: str) -> str:
    return {
        "background": "backgrounds",
        "prop": "props",
        "character": "characters",
        "location": "locations",
    }.get(_normalize_pixel_asset_kind(kind), "backgrounds")

def _pixel_asset_prompt(asset_id: str, asset_kind: str, prompt: str, style_notes: str) -> str:
    kind = _normalize_pixel_asset_kind(asset_kind)
    base = [
        f"asset id: {asset_id}",
        f"asset kind: {kind}",
        "pixel art, 2.5D stage reference, crisp silhouette, low frame animation friendly",
        "no text, no watermark, no logo, clean separated subject",
        prompt.strip(),
    ]
    if style_notes.strip():
        base.append(style_notes.strip())
    return "\n".join(item for item in base if item)

def _comfyui_generate_image_bytes(registry: BuiltinMcpRegistry, comfyui_url: str, workflow_path: str, prompt: str) -> bytes:
    if not workflow_path:
        raise RuntimeError("workflow_path is required for ComfyUI generation")
    workflow_target = registry._safe_path(workflow_path)
    if not workflow_target.exists() or not workflow_target.is_file():
        raise FileNotFoundError(f"ComfyUI workflow not found: {workflow_path}")
    workflow = json.loads(workflow_target.read_text(encoding="utf-8", errors="replace"))
    _inject_comfyui_prompt(workflow, prompt)
    base_url = comfyui_url.rstrip("/")
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        queued = json.loads(response.read().decode("utf-8", errors="replace"))
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI response missing prompt_id: {queued}")
    deadline = time.time() + _safe_int(os.environ.get("COMFYUI_TIMEOUT_SECONDS"), 120, 10, 900)
    history = None
    while time.time() < deadline:
        with urllib.request.urlopen(f"{base_url}/history/{urllib.parse.quote(str(prompt_id))}", timeout=20) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        history = data.get(str(prompt_id)) or data.get(prompt_id)
        if history and history.get("outputs"):
            break
        time.sleep(1.0)
    if not history or not history.get("outputs"):
        raise RuntimeError("ComfyUI generation timed out before producing an image")
    image_meta = _first_comfyui_image(history.get("outputs") or {})
    if not image_meta:
        raise RuntimeError("ComfyUI history did not include an image output")
    query = urllib.parse.urlencode({
        "filename": image_meta.get("filename"),
        "subfolder": image_meta.get("subfolder") or "",
        "type": image_meta.get("type") or "output",
    })
    with urllib.request.urlopen(f"{base_url}/view?{query}", timeout=60) as response:
        return response.read()

def _inject_comfyui_prompt(workflow, prompt: str) -> None:
    injected = False
    if isinstance(workflow, dict):
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if isinstance(inputs, dict) and isinstance(inputs.get("text"), str):
                class_type = str(node.get("class_type") or "").lower()
                if "cliptextencode" in class_type or not injected:
                    inputs["text"] = prompt
                    injected = True
    if not injected:
        raise RuntimeError("ComfyUI workflow has no text input to inject prompt")

def _first_comfyui_image(outputs: dict) -> dict | None:
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        for image in output.get("images") or []:
            if isinstance(image, dict) and image.get("filename"):
                return image
    return None

def _record_draft_pixel_asset(
    registry: BuiltinMcpRegistry,
    asset_manifest_path: str,
    asset_id: str,
    asset_kind: str,
    profile_path: str,
    image_path: str,
    provider: str,
) -> str:
    target = registry._safe_path(asset_manifest_path)
    if target.exists() and target.is_file():
        manifest = json.loads(target.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(manifest, dict):
            manifest = {}
    else:
        manifest = {}
    manifest.setdefault("version", 1)
    manifest.setdefault("approved_assets", {})
    drafts = manifest.setdefault("draft_assets", {})
    bucket = _pixel_asset_kind_bucket(asset_kind)
    bucket_items = drafts.setdefault(bucket, {})
    bucket_items[asset_id] = {
        "profile": _asset_manifest_local_path(profile_path),
        "image": _asset_manifest_local_path(image_path),
        "status": "draft",
        "provider": provider,
        "requires_approval": True,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")

def _asset_manifest_local_path(path_str: str) -> str:
    text = str(path_str or "").replace("\\", "/")
    prefix = "cartridges/dev/dev.pixel_episode_director/"
    if text.startswith(prefix):
        return text[len(prefix):]
    return text

def _pixel_character_actions(value) -> list[str]:
    if isinstance(value, list):
        actions = [str(item).strip() for item in value if str(item).strip()]
    else:
        text = str(value or "").replace(",", "\n")
        actions = [item.strip() for item in text.splitlines() if item.strip()]
    return actions or ["idle", "walk_right", "look_around", "talk_idle"]

def _pixel_character_palette(value, character_id: str) -> dict[str, str]:
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            value = json.loads(value)
        except Exception:
            value = {}
    palette = value if isinstance(value, dict) else {}
    defaults = {
        "body": "#4992dc" if character_id == "hero" else "#d67c3c",
        "skin": "#e8b586",
        "shadow": "#191c24",
        "trim": "#77bdf0" if character_id == "hero" else "#f4b24a",
        "hair": "#201818" if character_id == "hero" else "#36261b",
    }
    return {key: str(palette.get(key) or default) for key, default in defaults.items()}

def _pixel_frame_size(value, default: tuple[int, int] = (96, 128)) -> tuple[int, int]:
    raw = str(value or "").lower().strip()
    match = re.match(r"^\s*(\d+)\s*x\s*(\d+)\s*$", raw)
    if match:
        return _safe_int(match.group(1), default[0], 32, 256), _safe_int(match.group(2), default[1], 64, 256)
    return default

def _rgba(hex_value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    try:
        rgb = _hex_to_rgb(str(hex_value))
    except Exception:
        rgb = (255, 0, 255)
    return rgb[0], rgb[1], rgb[2], alpha

def _write_pixel_character_spritesheet(
    path: Path,
    character_id: str,
    actions: list[str],
    palette: dict[str, str],
    frame_width: int,
    frame_height: int,
    frames_per_action: int,
) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError("Pillow is required for local pixel character spritesheet generation") from exc

    sheet = Image.new("RGBA", (frame_width * frames_per_action, frame_height * len(actions)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet, "RGBA")
    for row, action in enumerate(actions):
        for frame_index in range(frames_per_action):
            ox = frame_index * frame_width
            oy = row * frame_height
            _draw_pixel_character_sprite(draw, ox, oy, frame_width, frame_height, character_id, action, frame_index, frames_per_action, palette)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)

def _draw_pixel_character_sprite(draw, ox: int, oy: int, width: int, height: int, character_id: str, action: str, frame_index: int, frame_count: int, palette: dict[str, str]) -> None:
    phase = (frame_index / max(1, frame_count)) * math.tau
    walking = "walk" in action
    talking = "talk" in action
    looking = "look" in action
    unit = max(1.0, height / 128.0)
    cx = ox + width // 2
    foot_y = oy + height - int(8 * unit)
    bob = int(math.sin(phase) * 2 * unit) if walking else 0
    swing = int(math.sin(phase) * 5 * unit) if walking else 0
    look_shift = int(math.sin(phase) * 2 * unit) if looking else 0
    body = _rgba(palette.get("body", "#4992dc"))
    skin = _rgba(palette.get("skin", "#e8b586"))
    shadow = _rgba(palette.get("shadow", "#191c24"))
    trim = _rgba(palette.get("trim", "#77bdf0"))
    hair = _rgba(palette.get("hair", "#201818"))
    outline = (5, 7, 11, 255)

    def rect(x0: float, y0: float, x1: float, y1: float, color: tuple[int, int, int, int]) -> None:
        draw.rectangle((int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))), fill=color)

    scale = 7.5 * unit
    head_top = foot_y - scale * 11 + bob
    head_bottom = head_top + scale * 2.5
    body_top = head_bottom + scale * 0.8
    body_bottom = body_top + scale * 4.7
    torso_left = cx - scale * 2.4
    torso_right = cx + scale * 2.4

    rect(cx - scale * 1.35 + look_shift, head_top - 2, cx + scale * 1.35 + look_shift, head_bottom + 2, outline)
    rect(cx - scale * 1.12 + look_shift, head_top, cx + scale * 1.12 + look_shift, head_bottom, skin)
    rect(cx - scale * 1.18 + look_shift, head_top, cx + scale * 1.18 + look_shift, head_top + scale * 0.72, hair)
    rect(cx - scale * 1.26 + look_shift, head_top + scale * 0.55, cx - scale * 0.55 + look_shift, head_bottom, hair)
    rect(cx - scale * 0.46 + look_shift, head_top + scale * 1.15, cx - scale * 0.24 + look_shift, head_top + scale * 1.35, outline)
    rect(cx + scale * 0.48 + look_shift, head_top + scale * 1.15, cx + scale * 0.70 + look_shift, head_top + scale * 1.35, outline)
    if talking and frame_index % 2:
        rect(cx - scale * 0.24 + look_shift, head_top + scale * 1.75, cx + scale * 0.30 + look_shift, head_top + scale * 1.93, outline)

    rect(cx - scale * 0.45, body_top - scale * 0.62, cx + scale * 0.45, body_top + scale * 0.2, skin)
    rect(torso_left - 2, body_top - 2, torso_right + 2, body_bottom + 2, outline)
    rect(torso_left, body_top, torso_right, body_bottom, body)
    rect(torso_left, body_top, torso_right, body_top + scale * 0.75, trim)
    rect(cx - 1, body_top + scale * 0.75, cx + 1, body_bottom, _rgba(palette.get("shadow", "#191c24"), 210))

    left_arm = torso_left - scale * 1.0
    right_arm = torso_right + scale * 0.15
    arm_shift = swing * 0.45
    rect(left_arm - 2, body_top + scale * 0.8 - arm_shift, left_arm + scale * 0.7, body_bottom - scale * 0.3 - arm_shift, outline)
    rect(right_arm, body_top + scale * 0.8 + arm_shift, right_arm + scale * 0.7, body_bottom - scale * 0.3 + arm_shift, outline)
    rect(left_arm, body_top + scale * 0.95 - arm_shift, left_arm + scale * 0.45, body_bottom - scale * 0.45 - arm_shift, body)
    rect(right_arm + scale * 0.15, body_top + scale * 0.95 + arm_shift, right_arm + scale * 0.6, body_bottom - scale * 0.45 + arm_shift, body)
    rect(left_arm - 1, body_bottom - scale * 0.35 - arm_shift, left_arm + scale * 0.45, body_bottom + scale * 0.15 - arm_shift, skin)
    rect(right_arm + scale * 0.15, body_bottom - scale * 0.35 + arm_shift, right_arm + scale * 0.62, body_bottom + scale * 0.15 + arm_shift, skin)

    hip_y = body_bottom + 1
    rect(cx - scale * 1.35, hip_y - 1, cx - scale * 0.35, foot_y + scale * 1.5 + swing, outline)
    rect(cx + scale * 0.35, hip_y - 1, cx + scale * 1.35, foot_y + scale * 1.5 - swing, outline)
    rect(cx - scale * 1.15, hip_y, cx - scale * 0.52, foot_y + scale * 1.36 + swing, shadow)
    rect(cx + scale * 0.52, hip_y, cx + scale * 1.15, foot_y + scale * 1.36 - swing, shadow)
    rect(cx - scale * 1.45, foot_y + scale * 1.42 + swing, cx - scale * 0.20, foot_y + scale * 1.75 + swing, outline)
    rect(cx + scale * 0.20, foot_y + scale * 1.42 - swing, cx + scale * 1.45, foot_y + scale * 1.75 - swing, outline)

    if "alert" in action or "look" in action:
        rect(cx + scale * 1.4, head_top - scale * 0.75, cx + scale * 1.65, head_top + scale * 0.25, (255, 232, 146, 255))
        rect(cx + scale * 1.3, head_top + scale * 0.55, cx + scale * 1.75, head_top + scale * 0.85, (255, 232, 146, 255))

def _pixel_character_metadata(character_id: str, sheet_rel: str, actions: list[str], frame_width: int, frame_height: int, frames_per_action: int, fps: int, profile_rel: str | None = None) -> dict:
    animations = {}
    for row, action in enumerate(actions):
        frames = []
        for frame_index in range(frames_per_action):
            frames.append({
                "x": frame_index * frame_width,
                "y": row * frame_height,
                "w": frame_width,
                "h": frame_height,
                "duration": round(1.0 / max(1, fps), 4),
            })
        animations[action] = {
            "loop": True,
            "fps": fps,
            "frames": frames,
        }
    return {
        "schema_version": 1,
        "kind": "pixel_character_spritesheet",
        "character_id": character_id,
        "image": _asset_manifest_local_path(sheet_rel),
        "profile": _asset_manifest_local_path(profile_rel or ""),
        "frame_size": [frame_width, frame_height],
        "frames_per_action": frames_per_action,
        "pivot": [frame_width // 2, frame_height - 8],
        "animations": animations,
    }

def _record_pixel_character_asset(
    registry: BuiltinMcpRegistry,
    asset_manifest_path: str,
    character_id: str,
    rel_profile: str,
    rel_sheet: str,
    rel_metadata: str,
    provider: str,
    register_mode: str,
) -> str:
    target = registry._safe_path(asset_manifest_path)
    try:
        manifest = json.loads(target.read_text(encoding="utf-8", errors="replace")) if target.exists() else {}
    except Exception:
        manifest = {}
    approved = manifest.setdefault("approved_assets", {})
    drafts = manifest.setdefault("draft_assets", {})
    payload = {
        "profile": _asset_manifest_local_path(rel_profile),
        "spritesheet": _asset_manifest_local_path(rel_sheet),
        "metadata": _asset_manifest_local_path(rel_metadata),
        "provider": provider,
    }
    if register_mode == "approved":
        payload["status"] = "approved"
        approved.setdefault("characters", {})[character_id] = payload
    else:
        payload["status"] = "draft"
        payload["requires_approval"] = True
        drafts.setdefault("characters", {})[character_id] = payload
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return _workspace_rel(registry, target)

def _parse_pixel_resolution_text(value, default: tuple[int, int] = (1280, 720)) -> tuple[int, int]:
    raw = str(value or "").lower().strip()
    match = re.match(r"^\s*(\d+)\s*x\s*(\d+)\s*$", raw)
    if match:
        return _safe_int(match.group(1), default[0], 160, 3840), _safe_int(match.group(2), default[1], 120, 2160)
    return default

def _pixel_location_layer_specs(value) -> list[dict]:
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            value = json.loads(value)
        except Exception:
            value = None
    defaults = [
        {"id": "background_buildings", "parallax": 0.25, "z_index": 0},
        {"id": "market_stalls", "parallax": 0.55, "z_index": 10},
        {"id": "walkable_ground", "parallax": 1.0, "z_index": 20},
        {"id": "foreground_lamps", "parallax": 1.25, "z_index": 30},
    ]
    raw_layers = value if isinstance(value, list) and value else defaults
    layers = []
    for index, raw in enumerate(raw_layers):
        item = raw if isinstance(raw, dict) else {}
        fallback = defaults[index] if index < len(defaults) else {"id": f"layer_{index + 1:02d}", "parallax": 1.0, "z_index": index * 10}
        layer_id = _safe_slug(str(item.get("id") or fallback["id"]))
        layers.append({
            "id": layer_id,
            "parallax": float(item.get("parallax", fallback["parallax"])),
            "z_index": _safe_int(item.get("z_index"), fallback["z_index"], -100, 100),
        })
    if len(layers) < 4:
        seen = {layer["id"] for layer in layers}
        for fallback in defaults:
            if fallback["id"] not in seen:
                layers.append(dict(fallback))
            if len(layers) >= 4:
                break
    return layers

def _write_pixel_location_layers(layers_dir: Path, specs: list[dict], width: int, height: int) -> dict[str, Path]:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError("Pillow is required for local pixel location layer generation") from exc

    layers_dir.mkdir(parents=True, exist_ok=True)
    low_w = max(320, width // 4)
    low_h = max(180, height // 4)
    scale_x = low_w / 320.0
    scale_y = low_h / 180.0
    written: dict[str, Path] = {}
    nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    for spec in specs:
        layer_id = spec["id"]
        img = Image.new("RGBA", (low_w, low_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        _draw_pixel_location_layer(draw, layer_id, low_w, low_h, scale_x, scale_y)
        target = img.resize((width, height), resample=nearest)
        path = layers_dir / f"{layer_id}.png"
        target.save(path)
        written[layer_id] = path
    return written

def _draw_pixel_location_layer(draw, layer_id: str, width: int, height: int, scale_x: float, scale_y: float) -> None:
    def rect(x0, y0, x1, y1, color):
        draw.rectangle((int(x0 * scale_x), int(y0 * scale_y), int(x1 * scale_x), int(y1 * scale_y)), fill=color)

    def ellipse(x0, y0, x1, y1, color):
        draw.ellipse((int(x0 * scale_x), int(y0 * scale_y), int(x1 * scale_x), int(y1 * scale_y)), fill=color)

    if layer_id == "background_buildings":
        for y in range(180):
            amount = y / 179.0
            color = (12 + int(amount * 18), 18 + int(amount * 10), 34 + int(amount * 24), 255)
            rect(0, y, 320, y + 1, color)
        for i in range(18):
            x = (i * 23 + 7) % 330 - 8
            w = 15 + (i * 7) % 19
            h = 44 + (i * 13) % 58
            base = 116 + (i % 3) * 5
            tone = (22 + (i % 2) * 7, 28 + (i % 3) * 5, 45 + (i % 4) * 4, 255)
            rect(x, base - h, x + w, base, tone)
            for wy in range(base - h + 8, base - 8, 10):
                for wx in range(x + 4, x + w - 2, 7):
                    lit = (i + wx + wy) % 5 == 0
                    rect(wx, wy, wx + 2, wy + 3, (240, 177, 76, 185 if lit else 38))
        for i in range(28):
            sx = (i * 37 + 11) % 320
            sy = (i * 19 + 7) % 58
            rect(sx, sy, sx + 1, sy + 1, (180, 205, 225, 90))
    elif layer_id == "market_stalls":
        for i in range(7):
            x = -18 + i * 54
            y = 106 + (i % 2) * 4
            body = (52, 48 + (i % 2) * 18, 62 + (i % 3) * 8, 245)
            awning = (184, 70, 72, 255) if i % 2 else (204, 139, 55, 255)
            rect(x, y + 12, x + 44, y + 48, body)
            rect(x - 4, y, x + 49, y + 12, awning)
            for stripe in range(0, 54, 10):
                rect(x - 3 + stripe, y, x + 1 + stripe, y + 12, (242, 194, 98, 255))
            rect(x + 8, y + 23, x + 35, y + 37, (99, 78, 64, 255))
            rect(x + 14, y + 17, x + 23, y + 27, (232, 169, 70, 255))
            if i % 2 == 0:
                rect(x + 12, y - 18, x + 38, y - 7, (12, 19, 29, 255))
                rect(x + 14, y - 16, x + 36, y - 10, (207, 77, 93, 255))
    elif layer_id == "walkable_ground":
        rect(0, 128, 320, 180, (35, 32, 42, 255))
        for i in range(-4, 12):
            x = i * 39
            draw.line((int(x * scale_x), int(138 * scale_y), int((x + 86) * scale_x), int(180 * scale_y)), fill=(67, 57, 75, 255), width=max(1, int(1.3 * scale_y)))
        for i in range(9):
            x = 14 + i * 38
            rect(x, 146 + (i % 3) * 5, x + 28, 148 + (i % 3) * 5, (232, 140, 69, 66))
            rect(x + 7, 162 - (i % 2) * 4, x + 48, 164 - (i % 2) * 4, (72, 149, 212, 52))
    elif layer_id == "foreground_lamps":
        for i in range(5):
            x = 10 + i * 76
            top = 64 + (i % 2) * 7
            rect(x, top, x + 2, 180, (20, 22, 30, 255))
            ellipse(x - 16, top - 18, x + 18, top + 16, (240, 167, 65, 42))
            rect(x - 5, top - 6, x + 9, top + 3, (241, 171, 66, 255))
            rect(x - 2, top - 3, x + 6, top + 1, (255, 226, 138, 255))
            for j in range(3):
                lx = x + 24 + j * 13
                ly = top + 13 + ((i + j) % 2) * 7
                rect(lx, ly, lx + 6, ly + 9, (201, 59, 58, 245))
                rect(lx + 2, ly + 2, lx + 4, ly + 7, (255, 199, 91, 230))

def _record_pixel_location_asset(
    registry: BuiltinMcpRegistry,
    asset_manifest_path: str,
    location_id: str,
    rel_profile: str,
    layers: list[dict],
    provider: str,
    register_mode: str,
) -> str:
    target = registry._safe_path(asset_manifest_path)
    try:
        manifest = json.loads(target.read_text(encoding="utf-8", errors="replace")) if target.exists() else {}
    except Exception:
        manifest = {}
    approved = manifest.setdefault("approved_assets", {})
    drafts = manifest.setdefault("draft_assets", {})
    payload = {
        "profile": _asset_manifest_local_path(rel_profile),
        "layers": layers,
        "provider": provider,
    }
    if register_mode == "approved":
        payload["status"] = "approved"
        approved.setdefault("locations", {})[location_id] = payload
    else:
        payload["status"] = "draft"
        payload["requires_approval"] = True
        drafts.setdefault("locations", {})[location_id] = payload
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return _workspace_rel(registry, target)

def _render_pixel_location_preview_html(location_id: str, layers: list[dict], profile: dict) -> str:
    image_tags = []
    for layer in layers:
        src = "layers/" + Path(str(layer.get("image") or "")).name
        image_tags.append(
            f'<img src="{html.escape(src)}" alt="{html.escape(str(layer.get("id", "layer")))}" />'
        )
    layer_items = "\n".join(
        f"<li><b>{html.escape(str(layer.get('id')))}</b> parallax {html.escape(str(layer.get('parallax')))}</li>"
        for layer in layers
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8" />
<title>{html.escape(location_id)} pixel location asset</title>
<style>
body{{margin:0;background:#12151d;color:#f5efe6;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}}
main{{max-width:1120px;margin:0 auto;padding:24px;}}
.stage{{position:relative;aspect-ratio:16/9;background:#070a10;border:1px solid #313843;overflow:hidden;image-rendering:pixelated;}}
.stage img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;image-rendering:pixelated;}}
code{{color:#8ecdf6;}}
</style>
<main>
  <h1>{html.escape(location_id)} location asset</h1>
  <p>Resolution <code>{html.escape(str(profile.get("resolution", "")))}</code>, {len(layers)} Godot parallax layers.</p>
  <div class="stage">{''.join(image_tags)}</div>
  <ul>{layer_items}</ul>
</main>
</html>"""

def _render_pixel_character_preview_html(character_id: str, sheet_rel: str, metadata: dict, profile: dict) -> str:
    image_src = _cache_bust_src(Path(sheet_rel).name)
    action_items = "\n".join(
        f"<li><b>{html.escape(action)}</b> {len((payload.get('frames') or []))} frames</li>"
        for action, payload in (metadata.get("animations") or {}).items()
        if isinstance(payload, dict)
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8" />
<title>{html.escape(character_id)} pixel character asset</title>
<style>
body{{margin:0;background:#141821;color:#f5efe6;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}}
main{{max-width:960px;margin:0 auto;padding:28px;display:grid;grid-template-columns:minmax(320px,1fr) 260px;gap:24px;}}
img{{width:100%;image-rendering:pixelated;background:#0b0f16;border:1px solid #313843;}}
h1{{font-size:24px;margin:0 0 10px;}} p,li{{color:#d7d0c5;line-height:1.6;}}
code{{color:#ffd28a;}}
@media(max-width:760px){{main{{grid-template-columns:1fr;}}}}
</style>
<main>
  <section>
    <h1>{html.escape(character_id)}</h1>
    <img src="{html.escape(image_src)}" alt="{html.escape(character_id)} spritesheet" />
  </section>
  <section>
    <p><code>{html.escape(str(metadata.get("frame_size")))}</code></p>
    <p>{html.escape(str(profile.get("stage_notes") or ""))}</p>
    <ul>{action_items}</ul>
  </section>
</main>
</html>
"""

def _write_local_pixel_asset_image(path: Path, asset_id: str, asset_kind: str, prompt: str) -> None:
    width, height = 160, 90
    seed = int(hashlib.sha256(f"{asset_id}|{asset_kind}|{prompt}".encode("utf-8")).hexdigest()[:12], 16)
    palettes = [
        ((19, 24, 31), (46, 89, 113), (225, 149, 72), (232, 220, 177)),
        ((22, 20, 34), (72, 55, 108), (63, 160, 149), (241, 205, 111)),
        ((18, 28, 26), (41, 97, 82), (199, 83, 80), (232, 230, 205)),
        ((25, 26, 28), (91, 84, 70), (216, 187, 92), (120, 184, 184)),
    ]
    bg, mid, accent, light = palettes[seed % len(palettes)]
    try:
        from PIL import Image, ImageDraw
    except Exception:
        _write_basic_pixel_asset_image(path, width, height, seed, bg, mid, accent, light, asset_kind)
        return

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    for y in range(height):
        amount = y / max(1, height - 1)
        color = _mix(bg, mid, 0.18 + 0.22 * amount)
        draw.line((0, y, width, y), fill=color)
    for x in range(0, width, 4):
        shade = _mix(bg, mid, 0.35 + ((x + seed) % 19) / 90)
        draw.line((x, 0, x, height), fill=shade)

    kind = _normalize_pixel_asset_kind(asset_kind)
    if kind == "character":
        cx = width // 2
        draw.rectangle((cx - 10, 28, cx + 10, 66), fill=accent)
        draw.rectangle((cx - 7, 16, cx + 7, 29), fill=light)
        draw.rectangle((cx - 13, 35, cx - 10, 58), fill=mid)
        draw.rectangle((cx + 10, 35, cx + 13, 58), fill=mid)
        draw.rectangle((cx - 8, 66, cx - 2, 78), fill=(8, 10, 12))
        draw.rectangle((cx + 2, 66, cx + 8, 78), fill=(8, 10, 12))
    elif kind == "prop":
        cx, cy = width // 2, height // 2 + 8
        draw.rectangle((cx - 20, cy - 14, cx + 20, cy + 10), fill=accent)
        draw.rectangle((cx - 14, cy - 22, cx + 12, cy - 14), fill=light)
        draw.rectangle((cx - 24, cy + 10, cx + 24, cy + 14), fill=(7, 10, 11))
        draw.line((cx - 18, cy - 14, cx + 14, cy + 10), fill=bg, width=2)
    elif kind == "location":
        for i in range(6):
            x0 = i * 28 - 8
            h = 24 + ((seed >> i) % 28)
            draw.rectangle((x0, 50 - h, x0 + 24, 72), fill=_mix(mid, bg, 0.18))
            for wy in range(50 - h + 5, 66, 9):
                draw.rectangle((x0 + 5, wy, x0 + 8, wy + 3), fill=light if (wy + i) % 2 else accent)
        draw.polygon([(0, 72), (160, 65), (160, 90), (0, 90)], fill=(14, 15, 16))
    else:
        for i in range(8):
            x0 = i * 24 - 12
            h = 16 + ((seed >> (i % 8)) % 36)
            draw.rectangle((x0, 54 - h, x0 + 22, 70), fill=_mix(mid, bg, 0.12 + i / 28))
        draw.rectangle((0, 67, 160, 90), fill=(13, 15, 17))
        for i in range(5):
            x = 12 + i * 32 + ((seed >> i) % 9)
            draw.line((x, 28, x, 70), fill=(48, 40, 33), width=2)
            draw.ellipse((x - 4, 24, x + 4, 32), fill=accent)
            draw.ellipse((x - 8, 21, x + 8, 37), outline=_mix(accent, light, 0.45))
        draw.rectangle((22, 58, 64, 74), fill=_mix(accent, mid, 0.32))
        draw.rectangle((92, 56, 136, 74), fill=_mix(light, accent, 0.38))

    for i in range(18):
        x = (seed * (i + 5) + i * 23) % width
        y = (seed * (i + 11) + i * 17) % height
        draw.point((x, y), fill=light)
    resampling = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    img = img.resize((640, 360), resample=resampling)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)

def _write_basic_pixel_asset_image(path: Path, width: int, height: int, seed: int, bg: tuple[int, int, int], mid: tuple[int, int, int], accent: tuple[int, int, int], light: tuple[int, int, int], asset_kind: str) -> None:
    scale = 4
    out_w, out_h = width * scale, height * scale
    rows = []
    kind = _normalize_pixel_asset_kind(asset_kind)
    for y in range(out_h - 1, -1, -1):
        row = bytearray()
        low_y = y // scale
        for x in range(out_w):
            low_x = x // scale
            amount = low_y / max(1, height - 1)
            color = _mix(bg, mid, 0.18 + 0.22 * amount)
            if (low_x + seed) % 17 < 2:
                color = _mix(color, mid, 0.35)
            if kind == "character":
                cx = width // 2
                if cx - 10 <= low_x <= cx + 10 and 28 <= low_y <= 66:
                    color = accent
                if cx - 7 <= low_x <= cx + 7 and 16 <= low_y <= 29:
                    color = light
            elif kind == "prop":
                cx, cy = width // 2, height // 2 + 8
                if cx - 20 <= low_x <= cx + 20 and cy - 14 <= low_y <= cy + 10:
                    color = accent
                if cx - 14 <= low_x <= cx + 12 and cy - 22 <= low_y <= cy - 14:
                    color = light
            else:
                if low_y > 67:
                    color = (13, 15, 17)
                for i in range(6):
                    x0 = i * 28 - 8
                    h = 24 + ((seed >> i) % 28)
                    if x0 <= low_x <= x0 + 24 and 50 - h <= low_y <= 72:
                        color = _mix(mid, bg, 0.18)
                lamp = ((low_x + seed) % 32) < 3 and 24 <= low_y <= 70
                if lamp:
                    color = accent if low_y < 34 else _mix(accent, mid, 0.45)
            row.extend((color[2], color[1], color[0]))
        while len(row) % 4:
            row.append(0)
        rows.append(bytes(row))
    _write_png_from_bgr_frame(path, out_w, out_h, b"".join(rows))

def _write_pixel_episode_avi(avi_path: Path, plan: dict, frames_dir: Path | None = None, control_frames_dir: Path | None = None) -> dict:
    width, height = _pixel_resolution(plan)
    fps = _safe_int((plan.get("style") or {}).get("fps"), 12, 1, 30)
    timeline = _pixel_timeline(plan)
    duration = max(1, int(math.ceil(timeline[-1]["end"])))
    frame_count = max(1, duration * fps)
    frames = []
    frames_written = 0
    control_frames_written = 0
    pillow_available = True
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        pillow_available = False

    if frames_dir:
        frames_dir.mkdir(parents=True, exist_ok=True)
        for item in frames_dir.glob("*.png"):
            try:
                item.unlink()
            except OSError:
                pass
    if control_frames_dir:
        control_frames_dir.mkdir(parents=True, exist_ok=True)
        for item in control_frames_dir.glob("*.png"):
            try:
                item.unlink()
            except OSError:
                pass

    for frame_index in range(frame_count):
        second = frame_index / fps
        item = _pixel_timeline_item(timeline, second)
        shot = item["shot"]
        progress = (second - item["start"]) / max(0.001, item["end"] - item["start"])
        progress = max(0.0, min(1.0, progress))
        if pillow_available:
            try:
                img = _render_pixel_episode_image(width, height, plan, shot, progress, second, duration)
                frame = _image_to_avi_frame(img)
                frames.append(frame)
                if frames_dir:
                    img.save(frames_dir / f"frame_{frame_index:04d}.png")
                    frames_written += 1
                if control_frames_dir:
                    clean_img = _render_pixel_episode_image(width, height, plan, shot, progress, second, duration, include_overlays=False)
                    clean_img.save(control_frames_dir / f"frame_{frame_index:04d}.png")
                    control_frames_written += 1
                continue
            except Exception:
                pillow_available = False
        frame = _render_pixel_basic_frame(width, height, plan, shot, progress, second, duration)
        frames.append(frame)
        if frames_dir:
            _write_png_from_bgr_frame(frames_dir / f"frame_{frame_index:04d}.png", width, height, frame)
            frames_written += 1
        if control_frames_dir:
            clean_frame = _render_pixel_basic_frame(width, height, plan, shot, progress, second, duration, include_overlays=False)
            _write_png_from_bgr_frame(control_frames_dir / f"frame_{frame_index:04d}.png", width, height, clean_frame)
            control_frames_written += 1

    motion_check = _frame_sequence_motion_report(frames)
    if frame_count > 1 and motion_check["static_sequence"]:
        raise RuntimeError("pixel episode renderer produced a static frame sequence; refusing to continue with repeated-frame video")
    _write_avi_frames(avi_path, width, height, fps, frames)
    return {
        "width": width,
        "height": height,
        "fps": fps,
        "duration_seconds": duration,
        "frame_count": frame_count,
        "frames_written": frames_written,
        "control_frames_written": control_frames_written,
        "shot_count": len(timeline),
        "motion_check": motion_check,
    }

def _pixel_resolution(plan: dict) -> tuple[int, int]:
    raw = str((plan.get("style") or {}).get("resolution") or "").lower()
    match = re.match(r"^\s*(\d+)\s*x\s*(\d+)\s*$", raw)
    if match:
        return _safe_int(match.group(1), 1280, 160, 1920), _safe_int(match.group(2), 720, 120, 1080)
    return 1280, 720

def _pixel_timeline(plan: dict) -> list[dict]:
    timeline = []
    cursor = 0.0
    for index, shot in enumerate(plan.get("shots") or []):
        duration = _safe_int(shot.get("duration"), 4, 1, 30)
        timeline.append({"index": index, "start": cursor, "end": cursor + duration, "shot": shot})
        cursor += duration
    if not timeline:
        timeline.append({"index": 0, "start": 0.0, "end": 4.0, "shot": {"id": "shot_001", "duration": 4, "actors": []}})
    return timeline

def _pixel_timeline_item(timeline: list[dict], second: float) -> dict:
    for item in timeline:
        if item["start"] <= second < item["end"]:
            return item
    return timeline[-1]

def _render_pixel_episode_image(width: int, height: int, plan: dict, shot: dict, progress: float, second: float, total_duration: int, include_overlays: bool = True):
    from PIL import Image, ImageDraw

    low_w, low_h = max(160, width // 2), max(90, height // 2)
    img = Image.new("RGB", (low_w, low_h), (18, 22, 28))
    draw = ImageDraw.Draw(img, "RGBA")
    camera = shot.get("camera") or {}
    cam_x, zoom = _pixel_camera(camera, progress)

    for y in range(low_h):
        mix = y / max(1, low_h - 1)
        color = _mix((13, 18, 27), (37, 31, 48), mix)
        draw.line((0, y, low_w, y), fill=color)

    _draw_pixel_buildings(draw, low_w, low_h, cam_x, 0.25)
    _draw_pixel_market(draw, low_w, low_h, cam_x, 0.55)
    ground_y = int(low_h * 0.72)
    draw.rectangle((0, ground_y, low_w, low_h), fill=(34, 32, 39, 255))
    for x in range(-40, low_w + 40, 18):
        sx = int(x - cam_x * 3) % (low_w + 40) - 20
        draw.line((sx, ground_y + 8, sx + 36, low_h), fill=(54, 48, 58, 160), width=1)

    for actor in sorted(shot.get("actors") or [], key=lambda item: (item.get("position") or [0, 0, 0])[-1] if isinstance(item, dict) else 0):
        if isinstance(actor, dict):
            _draw_pixel_actor(draw, low_w, low_h, actor, progress, cam_x, zoom)

    _draw_pixel_camera_effect(draw, low_w, low_h, camera, progress)
    _draw_pixel_foreground(draw, low_w, low_h, cam_x, second)
    nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    img = img.resize((width, height), nearest)
    if include_overlays:
        overlay = ImageDraw.Draw(img, "RGBA")
        _draw_pixel_titles(overlay, width, height, plan, shot, second, total_duration)
    return img

def _pixel_camera(camera: dict, progress: float) -> tuple[float, float]:
    camera_type = str(camera.get("type") or "").strip()
    zoom = _pixel_float(camera.get("zoom"), 1.0)
    cam_x = 0.0
    if camera_type == "tracking_side":
        start = camera.get("from") or [0, 0]
        end = camera.get("to") or [0, 0]
        cam_x = _pixel_float(start[0] if start else 0, 0) + (_pixel_float(end[0] if end else 0, 0) - _pixel_float(start[0] if start else 0, 0)) * progress
    elif camera_type == "push_in":
        zoom = _pixel_float(camera.get("zoom_from"), 1.0) + (_pixel_float(camera.get("zoom_to"), 1.35) - _pixel_float(camera.get("zoom_from"), 1.0)) * progress
        cam_x = 2.5 * progress
    elif camera_type == "wide_establishing":
        position = camera.get("position") or [0, 0]
        cam_x = _pixel_float(position[0] if position else 0, 0)
        zoom = _pixel_float(camera.get("zoom"), 0.85)
    elif camera_type == "close_up":
        zoom = _pixel_float(camera.get("zoom"), 1.55)
        cam_x = 3.8
    elif camera_type == "over_shoulder":
        start = camera.get("from") or [5, 0]
        end = camera.get("to") or [7, 0]
        cam_x = _pixel_float(start[0] if start else 5, 5) + (_pixel_float(end[0] if end else 7, 7) - _pixel_float(start[0] if start else 5, 5)) * progress
        zoom = _pixel_float(camera.get("zoom"), 1.25)
    elif camera_type == "reveal":
        zoom = _pixel_float(camera.get("zoom_from"), 1.05) + (_pixel_float(camera.get("zoom_to"), 1.35) - _pixel_float(camera.get("zoom_from"), 1.05)) * progress
        cam_x = 1.5 + 3.0 * progress
    return cam_x, max(0.7, min(1.8, zoom))

def _pixel_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default

def _draw_pixel_buildings(draw, width: int, height: int, cam_x: float, parallax: float):
    base_y = int(height * 0.56)
    for i in range(8):
        x = int(i * 54 - (cam_x * 9 * parallax)) % (width + 80) - 40
        h = 42 + (i % 4) * 12
        draw.rectangle((x, base_y - h, x + 34, base_y), fill=(24, 29, 40, 255))
        for wy in range(base_y - h + 8, base_y - 8, 13):
            for wx in range(x + 6, x + 28, 13):
                lit = (i + wx + wy) % 3 == 0
                draw.rectangle((wx, wy, wx + 4, wy + 5), fill=(242, 180, 76, 180 if lit else 50))

def _draw_pixel_market(draw, width: int, height: int, cam_x: float, parallax: float):
    base_y = int(height * 0.72)
    for i in range(5):
        x = int(26 + i * 70 - (cam_x * 15 * parallax)) % (width + 90) - 45
        draw.rectangle((x, base_y - 34, x + 50, base_y), fill=(64, 42, 43, 255))
        draw.rectangle((x - 4, base_y - 45, x + 54, base_y - 32), fill=(154, 64, 54, 255))
        for sx in range(x, x + 54, 12):
            draw.rectangle((sx, base_y - 45, sx + 6, base_y - 32), fill=(236, 184, 90, 230))
        draw.rectangle((x + 8, base_y - 24, x + 42, base_y - 10), fill=(90, 74, 62, 255))

def _draw_pixel_camera_effect(draw, width: int, height: int, camera: dict, progress: float):
    camera_type = str(camera.get("type") or "").strip()
    if camera_type == "over_shoulder":
        shoulder_w = int(width * 0.22)
        draw.rectangle((0, int(height * 0.46), shoulder_w, height), fill=(22, 20, 24, 230))
        draw.ellipse((-shoulder_w // 2, int(height * 0.22), shoulder_w, int(height * 0.62)), fill=(30, 26, 31, 235))
        draw.rectangle((shoulder_w - 4, int(height * 0.50), shoulder_w + 2, height), fill=(238, 175, 74, 85))
    elif camera_type == "reveal":
        cover = int(width * max(0.0, 0.42 * (1.0 - progress)))
        if cover > 0:
            draw.rectangle((0, 0, cover, height), fill=(8, 9, 12, 235))
            draw.rectangle((cover - 4, 0, cover, height), fill=(236, 184, 90, 170))

def _draw_pixel_foreground(draw, width: int, height: int, cam_x: float, second: float):
    ground_y = int(height * 0.72)
    for i in range(4):
        x = int(38 + i * 84 - cam_x * 22) % (width + 80) - 40
        flicker = 130 + int(80 * (0.5 + 0.5 * math.sin(second * 8 + i)))
        draw.rectangle((x, ground_y - 58, x + 3, ground_y + 8), fill=(23, 24, 28, 230))
        draw.rectangle((x - 4, ground_y - 66, x + 8, ground_y - 56), fill=(244, 179, 68, 255))
        draw.rectangle((x - 10, ground_y - 72, x + 14, ground_y - 50), fill=(244, 179, 68, flicker))

def _draw_pixel_actor(draw, width: int, height: int, actor: dict, progress: float, cam_x: float, zoom: float):
    pos = actor.get("position") or [6, 6, 1]
    move_to = actor.get("move_to")
    x = _pixel_float(pos[0] if len(pos) > 0 else 6, 6)
    y = _pixel_float(pos[1] if len(pos) > 1 else 6, 6)
    if isinstance(move_to, list) and len(move_to) >= 2:
        x += (_pixel_float(move_to[0], x) - x) * progress
        y += (_pixel_float(move_to[1], y) - y) * progress
    screen_x = int(width * 0.38 + (x - 5.5 - cam_x) * 22 * zoom)
    foot_y = int(height * 0.47 + y * 7)
    bob = int(math.sin(progress * math.pi * 6) * 2) if "walk" in str(actor.get("animation") or "") else 0
    scale = max(1, int(zoom * 8))
    color = (73, 146, 220, 255) if actor.get("id") == "hero" else (214, 124, 60, 255)
    skin = (232, 181, 134, 255)
    dark = (25, 28, 36, 255)
    draw.rectangle((screen_x - scale, foot_y - scale * 4 + bob, screen_x + scale, foot_y - scale * 2 + bob), fill=skin)
    draw.rectangle((screen_x - scale * 2, foot_y - scale * 2 + bob, screen_x + scale * 2, foot_y + scale * 2 + bob), fill=color)
    draw.rectangle((screen_x - scale * 2, foot_y + scale * 2 + bob, screen_x - 2, foot_y + scale * 4 + bob), fill=dark)
    draw.rectangle((screen_x + 2, foot_y + scale * 2 + bob, screen_x + scale * 2, foot_y + scale * 4 + bob), fill=dark)
    if actor.get("emotion") in {"suspicious", "alert"}:
        draw.rectangle((screen_x + scale, foot_y - scale * 3 + bob, screen_x + scale + 2, foot_y - scale * 3 + 1 + bob), fill=(255, 255, 255, 255))

def _draw_pixel_titles(draw, width: int, height: int, plan: dict, shot: dict, second: float, total_duration: int):
    title_font = _font(18, bold=True)
    body_font = _font(17)
    small_font = _font(13)
    draw.rectangle((14, 14, min(width - 14, 420), 82), fill=(9, 13, 18, 180), outline=(240, 165, 72, 200))
    draw.text((26, 24), str(plan.get("title") or plan.get("episode_id") or "像素短剧"), font=title_font, fill=(255, 241, 214, 255))
    camera_type = (shot.get("camera") or {}).get("type") or "camera"
    draw.text((26, 52), f"{shot.get('id', 'shot')} · {camera_type} · {int(second):02d}/{total_duration:02d}s", font=small_font, fill=(209, 213, 219, 255))
    dialogue = _pixel_dialogue_text(shot)
    if dialogue:
        lines = _wrap_text(dialogue, body_font, width - 76, max_lines=2)
        box_h = 34 + len(lines) * 23
        top = height - box_h - 24
        draw.rectangle((24, top, width - 24, height - 24), fill=(8, 10, 14, 205), outline=(244, 179, 68, 180))
        y = top + 17
        for line in lines:
            draw.text((38, y), line, font=body_font, fill=(255, 255, 255, 255))
            y += 23

def _pixel_dialogue_text(shot: dict) -> str:
    parts = []
    for item in shot.get("dialogue") or []:
        if isinstance(item, dict) and item.get("text"):
            speaker = item.get("speaker") or ""
            prefix = f"{speaker}: " if speaker else ""
            parts.append(prefix + str(item["text"]))
    return " / ".join(parts)

def _render_pixel_basic_frame(width: int, height: int, plan: dict, shot: dict, progress: float, second: float, total_duration: int, include_overlays: bool = True) -> bytes:
    camera = shot.get("camera") or {}
    cam_x, zoom = _pixel_camera(camera, progress)
    ground_y = int(height * 0.72)
    pixels: list[list[tuple[int, int, int]]] = []
    sky_top = (8, 12, 22)
    sky_bottom = (39, 30, 50)
    road_top = (42, 37, 48)
    road_bottom = (21, 22, 28)
    for y in range(height):
        row = []
        for x in range(width):
            if y < ground_y:
                amount = y / max(1, ground_y)
                color = _mix(sky_top, sky_bottom, amount)
                if ((x // 9) + (y // 7) + int(second * 2)) % 31 == 0:
                    color = _mix(color, (242, 180, 76), 0.24)
            else:
                amount = (y - ground_y) / max(1, height - ground_y)
                color = _mix(road_top, road_bottom, amount)
                if ((x // 10) + (y // 10)) % 6 == 0:
                    color = _mix(color, (86, 71, 71), 0.18)
            row.append(color)
        pixels.append(row)

    def rect(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        for py in range(max(0, y0), min(height, y1 + 1)):
            for px in range(max(0, x0), min(width, x1 + 1)):
                pixels[py][px] = color

    def blend_rect(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], amount: float) -> None:
        for py in range(max(0, y0), min(height, y1 + 1)):
            for px in range(max(0, x0), min(width, x1 + 1)):
                pixels[py][px] = _mix(pixels[py][px], color, amount)

    def line(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], thickness: int = 1) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            rect(x - thickness, y - thickness, x + thickness, y + thickness, color)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    # Far city skyline.
    for layer, (base_y, parallax, tone) in enumerate([
        (int(height * 0.52), 0.18, (18, 24, 36)),
        (int(height * 0.61), 0.36, (25, 30, 42)),
    ]):
        spacing = 58 - layer * 8
        for i in range(12):
            x = int(i * spacing - cam_x * 18 * parallax) % (width + 100) - 60
            building_w = 28 + ((i * 7 + layer * 5) % 24)
            building_h = 54 + ((i * 17 + layer * 11) % 82)
            rect(x, base_y - building_h, x + building_w, base_y, tone)
            if i % 3 == 0:
                rect(x + 5, base_y - building_h - 8, x + building_w - 6, base_y - building_h, _mix(tone, (68, 76, 92), 0.35))
            for wy in range(base_y - building_h + 10, base_y - 8, 16):
                for wx in range(x + 6, x + building_w - 5, 13):
                    lit = ((i * 11 + wx + wy + int(second * 3)) % 4) == 0
                    rect(wx, wy, wx + 4, wy + 5, (238, 178, 72) if lit else _mix(tone, (84, 92, 110), 0.35))

    # Storefronts and night-market stalls.
    for i in range(6):
        x = int(22 + i * 116 - cam_x * 34) % (width + 150) - 75
        stall_y = ground_y - 68 + (i % 2) * 5
        body = (69, 45, 48) if i % 2 else (47, 55, 65)
        awning = (180, 64, 56) if i % 2 else (214, 140, 52)
        rect(x, stall_y + 18, x + 82, ground_y + 8, body)
        rect(x - 6, stall_y, x + 88, stall_y + 20, awning)
        for sx in range(x - 4, x + 86, 16):
            rect(sx, stall_y, sx + 7, stall_y + 20, (240, 188, 92))
        rect(x + 12, stall_y + 34, x + 70, stall_y + 50, (101, 82, 69))
        rect(x + 18, stall_y + 26, x + 32, stall_y + 38, (239, 180, 78))
        rect(x + 44, stall_y + 25, x + 62, stall_y + 39, (98, 153, 176))
        if i % 2 == 0:
            sign_x = x + 20
            rect(sign_x, stall_y - 30, sign_x + 46, stall_y - 10, (17, 21, 28))
            rect(sign_x + 3, stall_y - 27, sign_x + 43, stall_y - 13, (204, 79, 93))
            for dot in range(4):
                rect(sign_x + 8 + dot * 9, stall_y - 22, sign_x + 12 + dot * 9, stall_y - 18, (255, 219, 138))

    # Road perspective markings and wet neon reflections.
    for i in range(-4, 12):
        start_x = int(i * 78 - cam_x * 18)
        line(start_x, ground_y + 18, start_x + 165, height + 8, (69, 61, 75), 2)
    for i in range(5):
        rx = int(38 + i * 124 - cam_x * 24) % (width + 120) - 60
        blend_rect(rx, ground_y + 28, rx + 46, ground_y + 36, (240, 145, 62), 0.36)
        blend_rect(rx + 18, ground_y + 72, rx + 86, ground_y + 82, (72, 146, 214), 0.22)

    # Foreground lamps and hanging lanterns.
    for i in range(4):
        x = int(46 + i * 176 - cam_x * 52) % (width + 180) - 90
        pole_top = ground_y - 122
        rect(x, pole_top, x + 4, ground_y + 12, (20, 22, 27))
        flicker = 0.45 + 0.25 * (0.5 + 0.5 * math.sin(second * 8 + i))
        blend_rect(x - 24, pole_top - 16, x + 30, pole_top + 38, (244, 177, 69), flicker * 0.22)
        rect(x - 7, pole_top - 8, x + 12, pole_top + 7, (245, 174, 66))
        rect(x - 3, pole_top - 4, x + 8, pole_top + 3, (255, 226, 137))
        for j in range(3):
            lx = x + 38 + j * 23
            ly = pole_top + 18 + ((i + j) % 2) * 8
            rect(lx, ly, lx + 10, ly + 14, (202, 60, 58))
            rect(lx + 3, ly + 3, lx + 7, ly + 11, (255, 199, 91))

    for actor in sorted(shot.get("actors") or [], key=lambda item: (item.get("position") or [0, 0, 0])[-1] if isinstance(item, dict) else 0):
        if isinstance(actor, dict):
            _paint_basic_pixel_actor(pixels, width, height, actor, progress, cam_x, zoom)

    camera_type = str(camera.get("type") or "").strip()
    if camera_type == "over_shoulder":
        shoulder_w = int(width * 0.22)
        blend_rect(0, int(height * 0.42), shoulder_w, height, (8, 9, 12), 0.78)
        rect(shoulder_w - 8, int(height * 0.46), shoulder_w - 2, height, (71, 51, 43))
    elif camera_type == "reveal":
        cover = int(width * max(0.0, 0.42 * (1.0 - progress)))
        if cover > 0:
            blend_rect(0, 0, cover, height, (4, 5, 8), 0.88)
            rect(cover - 5, 0, cover, height, (228, 151, 55))

    if include_overlays:
        # HUD and dialogue box. The fallback cannot rasterize CJK text, but it keeps
        # the dialogue beat visible in the local render while clean control frames
        # stay free of UI for ComfyUI.
        rect(14, 14, min(width - 14, 388), 72, (8, 11, 16))
        rect(14, 14, min(width - 14, 388), 17, (234, 160, 67))
        _paint_basic_ascii(pixels, width, height, str(shot.get("id") or "SHOT").upper(), 26, 31, (255, 233, 188), scale=2)
        _paint_basic_ascii(pixels, width, height, str(camera_type or "CAMERA").upper()[:14], 26, 53, (185, 197, 210), scale=1)

        dialogue = _pixel_dialogue_text(shot)
        if dialogue:
            top = height - 84
            rect(24, top, width - 24, height - 24, (7, 9, 13))
            rect(24, top, width - 24, top + 4, (240, 171, 72))
            speaker = "VOICE"
            for item in shot.get("dialogue") or []:
                if isinstance(item, dict) and item.get("speaker"):
                    speaker = str(item.get("speaker")).upper()
                    break
            _paint_basic_ascii(pixels, width, height, speaker[:10], 40, top + 18, (255, 221, 145), scale=2)
            text_seed = int(hashlib.sha256(dialogue.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
            for line_index in range(2):
                y = top + 45 + line_index * 16
                cursor = 40
                for segment in range(14):
                    length = 10 + ((text_seed >> (segment % 12)) & 15)
                    if cursor + length > width - 52:
                        break
                    shade = (224, 232, 240) if segment % 3 else (179, 196, 210)
                    rect(cursor, y, cursor + length, y + 5, shade)
                    cursor += length + 8
    rows = []
    for y in range(height - 1, -1, -1):
        row = bytearray()
        for color in pixels[y]:
            row.extend(bytes((color[2], color[1], color[0])))
        while len(row) % 4:
            row.append(0)
        rows.append(bytes(row))
    return b"".join(rows)

def _paint_basic_ascii(
    pixels: list[list[tuple[int, int, int]]],
    width: int,
    height: int,
    text: str,
    x: int,
    y: int,
    color: tuple[int, int, int],
    scale: int = 1,
) -> None:
    font = {
        "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
        "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
        "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
        "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
        "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
        "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
        "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
        "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
        "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
        "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
        "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
        "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
        "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
        "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
        "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
        "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
        "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
        "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
        "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
        "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
        "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
        "V": ["10001", "10001", "10001", "10001", "01010", "01010", "00100"],
        "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
        "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
        "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
        "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
        "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
        "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
        "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
        "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
        "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
        "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
        "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
        "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
        "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
        "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
        "_": ["00000", "00000", "00000", "00000", "00000", "00000", "11111"],
        "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
        ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
        " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    }
    cursor = x
    for char in str(text or "").upper():
        pattern = font.get(char)
        if not pattern:
            cursor += 4 * scale
            continue
        for row_index, row in enumerate(pattern):
            for col_index, bit in enumerate(row):
                if bit != "1":
                    continue
                x0 = cursor + col_index * scale
                y0 = y + row_index * scale
                for py in range(max(0, y0), min(height, y0 + scale)):
                    for px in range(max(0, x0), min(width, x0 + scale)):
                        pixels[py][px] = color
        cursor += 6 * scale

def _paint_basic_pixel_actor(pixels: list[list[tuple[int, int, int]]], width: int, height: int, actor: dict, progress: float, cam_x: float, zoom: float) -> None:
    pos = actor.get("position") or [6, 6, 1]
    move_to = actor.get("move_to")
    x = _pixel_float(pos[0] if len(pos) > 0 else 6, 6)
    y = _pixel_float(pos[1] if len(pos) > 1 else 6, 6)
    if isinstance(move_to, list) and len(move_to) >= 2:
        x += (_pixel_float(move_to[0], x) - x) * progress
        y += (_pixel_float(move_to[1], y) - y) * progress
    screen_x = int(width * 0.38 + (x - 5.5 - cam_x) * 44 * zoom)
    foot_y = int(height * 0.47 + y * 14)
    walking = "walk" in str(actor.get("animation") or "")
    bob = int(math.sin(progress * math.pi * 6) * 3) if walking else 0
    leg_swing = int(math.sin(progress * math.pi * 6) * 4) if walking else 0
    scale = max(5, int(zoom * 10))
    actor_id = str(actor.get("id") or "")
    body = (63, 138, 214) if actor_id == "hero" else (214, 119, 48)
    trim = (119, 189, 238) if actor_id == "hero" else (244, 178, 74)
    pants = (19, 24, 35) if actor_id == "hero" else (40, 34, 31)
    skin = (232, 181, 134)
    hair = (32, 24, 24) if actor_id == "hero" else (54, 38, 27)
    outline = (5, 7, 11)

    def rect(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        for py in range(max(0, y0), min(height, y1 + 1)):
            for px in range(max(0, x0), min(width, x1 + 1)):
                pixels[py][px] = color

    head_top = foot_y - scale * 6 + bob
    head_bottom = head_top + scale * 2
    neck_top = head_bottom + 1
    body_top = neck_top + scale // 2
    body_bottom = foot_y - scale + bob
    torso_left = screen_x - scale * 2
    torso_right = screen_x + scale * 2

    # Hair and face.
    rect(screen_x - scale - 2, head_top - 2, screen_x + scale + 2, head_bottom + 2, outline)
    rect(screen_x - scale, head_top, screen_x + scale, head_bottom, skin)
    rect(screen_x - scale, head_top, screen_x + scale, head_top + scale // 2, hair)
    rect(screen_x - scale - 1, head_top + scale // 2, screen_x - scale // 2, head_bottom, hair)
    eye_y = head_top + scale
    rect(screen_x - scale // 2, eye_y, screen_x - scale // 2 + 1, eye_y + 1, outline)
    rect(screen_x + scale // 2, eye_y, screen_x + scale // 2 + 1, eye_y + 1, outline)

    # Neck, torso, trim, and shoulders.
    rect(screen_x - scale // 2, neck_top, screen_x + scale // 2, body_top + 2, skin)
    rect(torso_left - 2, body_top - 2, torso_right + 2, body_bottom + 2, outline)
    rect(torso_left, body_top, torso_right, body_bottom, body)
    rect(torso_left, body_top, torso_right, body_top + scale // 2, trim)
    rect(screen_x - 1, body_top + scale // 2, screen_x + 1, body_bottom, _mix(body, outline, 0.35))
    rect(torso_left - scale, body_top + scale // 2, torso_left - 1, body_bottom - scale // 2, outline)
    rect(torso_right + 1, body_top + scale // 2, torso_right + scale, body_bottom - scale // 2, outline)
    rect(torso_left - scale + 2, body_top + scale // 2, torso_left - 2, body_bottom - scale // 2, body)
    rect(torso_right + 2, body_top + scale // 2, torso_right + scale - 2, body_bottom - scale // 2, body)
    rect(torso_left - scale, body_bottom - scale // 2, torso_left - scale + 3, body_bottom + scale // 2, skin)
    rect(torso_right + scale - 3, body_bottom - scale // 2, torso_right + scale, body_bottom + scale // 2, skin)

    # Legs and shoes, with a small walk cycle offset.
    hip_y = body_bottom + 1
    left_leg_x = screen_x - scale - 2
    right_leg_x = screen_x + 2
    rect(left_leg_x - 1, hip_y - 1, left_leg_x + scale, foot_y + scale * 2 + bob + leg_swing, outline)
    rect(right_leg_x - 1, hip_y - 1, right_leg_x + scale, foot_y + scale * 2 + bob - leg_swing, outline)
    rect(left_leg_x, hip_y, left_leg_x + scale - 2, foot_y + scale * 2 + bob + leg_swing, pants)
    rect(right_leg_x, hip_y, right_leg_x + scale - 2, foot_y + scale * 2 + bob - leg_swing, pants)
    rect(left_leg_x - 3, foot_y + scale * 2 + bob + leg_swing, left_leg_x + scale + 2, foot_y + scale * 2 + bob + leg_swing + 4, outline)
    rect(right_leg_x - 3, foot_y + scale * 2 + bob - leg_swing, right_leg_x + scale + 2, foot_y + scale * 2 + bob - leg_swing + 4, outline)
    if actor.get("emotion") in {"suspicious", "alert"}:
        rect(screen_x + scale + 3, head_top - 5, screen_x + scale + 5, head_top + 4, (255, 232, 146))
        rect(screen_x + scale + 2, head_top + 8, screen_x + scale + 6, head_top + 11, (255, 232, 146))

def _render_pixel_episode_preview_html(plan: dict, video_name: str, status: str) -> str:
    video_src = _cache_bust_src(video_name)
    shots = []
    for shot in plan.get("shots") or []:
        camera = shot.get("camera") or {}
        dialogue = _pixel_dialogue_text(shot)
        shots.append(
            f"<li><b>{html.escape(str(shot.get('id') or 'shot'))}</b> "
            f"{html.escape(str(camera.get('type') or 'camera'))} · {html.escape(str(shot.get('duration') or ''))}s"
            f"<p>{html.escape(dialogue or camera.get('note') or '')}</p></li>"
        )
    shot_html = "\n".join(shots)
    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8" />
<title>{html.escape(str(plan.get('title') or '像素短剧'))}</title>
<style>
body{{margin:0;background:#15171b;color:#f4f0e8;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}}
main{{max-width:1040px;margin:0 auto;padding:28px;display:grid;grid-template-columns:minmax(320px,640px) 1fr;gap:24px;}}
video{{width:100%;aspect-ratio:16/9;background:#000;border:1px solid #313843;}}
section{{border-left:3px solid #e09045;padding-left:18px;}}
h1{{font-size:24px;margin:0 0 8px;}} p{{line-height:1.7;color:#d7d0c5;}} li{{margin:0 0 14px;}} a{{color:#ffd28a;}}
.status{{color:#ffd28a;}}
@media (max-width: 820px){{main{{grid-template-columns:1fr;}}}}
</style>
<main>
  <video src="{html.escape(video_src)}" controls loop></video>
  <section>
    <h1>{html.escape(str(plan.get('title') or '像素短剧'))}</h1>
    <p class="status">{html.escape(status)}</p>
    <p>{html.escape(str((plan.get('style') or {}).get('notes') or '像素 2.5D 分层片场。'))}</p>
    <p><a href="{html.escape(video_src)}">下载视频文件</a></p>
    <ol>{shot_html}</ol>
  </section>
</main>
</html>
"""


def register(registry):
    def generate_pixel_shot_plan(params: dict) -> dict:
        episode_id = str(params.get("episode_id") or "ep001").strip() or "ep001"
        episode_goal = str(params.get("episode_goal") or params.get("goal") or "").strip()
        style_notes = str(params.get("style_notes") or params.get("style") or "").strip()
        shot_count = _safe_int(params.get("shot_count"), 3, 3, 6)
        output_path = str(params.get("output_path") or "test_output/pixel_episode/shot_plan.json").strip()
        world_state_path = str(params.get("world_state_path") or "cartridges/dev/dev.pixel_episode_director/assets/world_state.json").strip()
        world_state_content = params.get("world_state_content") or ""
        shot_presets_path = str(params.get("shot_presets_path") or "cartridges/dev/dev.pixel_episode_director/assets/shot_presets.json").strip()
        shot_presets_content = params.get("shot_presets_content") or ""
        asset_direction = _pixel_asset_direction(
            params.get("asset_specs") or params.get("asset_specs_content") or params.get("asset_spec_batch"),
            params.get("draft_asset_bundle") or params.get("draft_asset_bundle_content"),
        )
        story_direction_raw = params.get("story_beats") or params.get("story_beats_payload") or params.get("story_plan")
        camera_direction_raw = params.get("camera_plan") or params.get("camera_plan_payload") or params.get("camera_language")
        if not episode_goal:
            episode_goal = "主角在夜市小巷发现异常线索。"

        try:
            target = registry._safe_path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            world_state = _load_pixel_world_state(registry, world_state_path, world_state_content)
            shot_presets = _load_pixel_shot_presets(registry, shot_presets_path, shot_presets_content)
            story_direction = _pixel_story_direction(story_direction_raw)
            camera_direction = _pixel_camera_direction(camera_direction_raw, shot_presets)
            plan = _build_pixel_shot_plan(
                episode_id,
                episode_goal,
                style_notes,
                output_path,
                world_state,
                shot_presets,
                shot_count,
                asset_direction,
                story_direction,
                camera_direction,
            )
            content = json.dumps(plan, ensure_ascii=False, indent=2)
            target.write_text(content, encoding="utf-8")
            rel_path = str(target.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            return {
                "ok": True,
                "path": rel_path,
                "content": content,
                "episode_id": episode_id,
                "shot_count": len(plan["shots"]),
                "written": len(content),
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"pixel shot plan generation failed: {exc}"}

    def validate_pixel_shot_plan(params: dict) -> dict:
        shot_plan_path = str(params.get("shot_plan_path") or "test_output/pixel_episode/shot_plan.json").strip()
        shot_plan_content = params.get("shot_plan_content") or params.get("shot_plan_json") or ""
        series_bible_path = str(params.get("series_bible_path") or "cartridges/dev/dev.pixel_episode_director/assets/series_bible.json").strip()
        asset_manifest_path = str(params.get("asset_manifest_path") or "cartridges/dev/dev.pixel_episode_director/assets/asset_manifest.json").strip()
        shot_presets_path = str(params.get("shot_presets_path") or "cartridges/dev/dev.pixel_episode_director/assets/shot_presets.json").strip()
        shot_presets_content = params.get("shot_presets_content") or ""
        output_path = str(params.get("output_path") or "test_output/pixel_episode/validation.json").strip()
        try:
            plan = _load_pixel_shot_plan(registry, shot_plan_path, shot_plan_content)
            report = _validate_pixel_shot_plan(registry, plan, series_bible_path, asset_manifest_path, shot_presets_path, shot_presets_content)
            content = json.dumps(report, ensure_ascii=False, indent=2)
            target = registry._safe_path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            rel_path = str(target.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            return {
                "ok": True,
                "path": rel_path,
                "content": content,
                "validation_ok": report["valid"],
                "issues": report["issues"],
                "repairs": report["repairs"],
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"pixel shot plan validation failed: {exc}"}

    def update_pixel_world_state(params: dict) -> dict:
        world_state_path = str(params.get("world_state_path") or "cartridges/dev/dev.pixel_episode_director/assets/world_state.json").strip()
        world_state_content = params.get("world_state_content") or ""
        shot_plan_path = str(params.get("shot_plan_path") or "test_output/pixel_episode/shot_plan.json").strip()
        shot_plan_content = params.get("shot_plan_content") or params.get("shot_plan_json") or ""
        episode_id = str(params.get("episode_id") or "").strip()
        episode_goal = str(params.get("episode_goal") or params.get("goal") or "").strip()
        output_path = str(params.get("output_path") or "test_output/pixel_episode/world_state_update.json").strip()
        continuity_policy = str(params.get("continuity_policy") or params.get("policy") or "read_and_write").strip().lower()
        try:
            plan = _load_pixel_shot_plan(registry, shot_plan_path, shot_plan_content)
            world_state = _load_pixel_world_state(registry, world_state_path, world_state_content)
            if continuity_policy in {"off", "read_only", "readonly", "none", "skip"}:
                report = {
                    "valid": True,
                    "skipped": True,
                    "policy": continuity_policy,
                    "episode_id": episode_id or plan.get("episode_id") or "",
                    "message": "world_state write skipped by continuity_policy",
                }
                content = json.dumps(report, ensure_ascii=False, indent=2)
                report_target = registry._safe_path(output_path)
                report_target.parent.mkdir(parents=True, exist_ok=True)
                report_target.write_text(content, encoding="utf-8")
                rel_report = str(report_target.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
                return {
                    "ok": True,
                    "path": rel_report,
                    "files": [rel_report],
                    "content": content,
                    "world_state_ok": True,
                    "skipped": True,
                    "policy": continuity_policy,
                }
            updated, report = _update_pixel_world_state(world_state, plan, episode_id, episode_goal)
            state_target = registry._safe_path(world_state_path)
            state_target.parent.mkdir(parents=True, exist_ok=True)
            state_target.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
            report_target = registry._safe_path(output_path)
            report_target.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(report, ensure_ascii=False, indent=2)
            report_target.write_text(content, encoding="utf-8")
            rel_state = str(state_target.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            rel_report = str(report_target.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            return {
                "ok": True,
                "path": rel_report,
                "project_path": rel_state,
                "files": [rel_report, rel_state],
                "content": content,
                "world_state_ok": True,
                "episode_id": report.get("episode_id"),
                "open_threads": report.get("open_threads", []),
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"pixel world state update failed: {exc}"}

    def check_pixel_assets(params: dict) -> dict:
        series_bible_path = str(params.get("series_bible_path") or "cartridges/dev/dev.pixel_episode_director/assets/series_bible.json").strip()
        asset_manifest_path = str(params.get("asset_manifest_path") or "cartridges/dev/dev.pixel_episode_director/assets/asset_manifest.json").strip()
        series_bible_content = params.get("series_bible_content") or ""
        asset_manifest_content = params.get("asset_manifest_content") or ""
        output_path = str(params.get("output_path") or "test_output/pixel_episode/asset_check.json").strip()
        try:
            if str(series_bible_content).strip():
                series_bible = json.loads(str(series_bible_content))
                series_path = registry._safe_path(series_bible_path) if series_bible_path else None
                if not isinstance(series_bible, dict):
                    raise ValueError("series_bible_content must be a JSON object")
            else:
                series_bible, series_path = _read_pixel_json_file(registry, series_bible_path, _default_pixel_series_bible())

            if str(asset_manifest_content).strip():
                asset_manifest = json.loads(str(asset_manifest_content))
                asset_path = registry._safe_path(asset_manifest_path) if asset_manifest_path else None
                if not isinstance(asset_manifest, dict):
                    raise ValueError("asset_manifest_content must be a JSON object")
            else:
                asset_manifest, asset_path = _read_pixel_json_file(registry, asset_manifest_path, {"approved_assets": {}})

            characters = {
                str(item.get("id")): set(str(action) for action in item.get("available_actions") or [])
                for item in series_bible.get("characters") or []
                if isinstance(item, dict) and item.get("id")
            }
            locations = {
                str(item.get("id"))
                for item in series_bible.get("locations") or []
                if isinstance(item, dict) and item.get("id")
            }
            asset_check = _validate_pixel_assets(registry, asset_manifest, asset_path, characters, locations)
            report = {
                "valid": not asset_check["issues"],
                "issues": asset_check["issues"],
                "repairs": asset_check["repairs"],
                "summary": asset_check["summary"],
                "contract": {
                    "series_bible_path": str(series_path) if series_path else "",
                    "asset_manifest_path": str(asset_path) if asset_path else "",
                    "required_characters": sorted(characters),
                    "required_locations": sorted(locations),
                },
            }
            content = json.dumps(report, ensure_ascii=False, indent=2)
            target = registry._safe_path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            rel_path = str(target.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            return {
                "ok": True,
                "path": rel_path,
                "content": content,
                "asset_ok": report["valid"],
                "issues": report["issues"],
                "repairs": report["repairs"],
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"pixel asset check failed: {exc}"}

    def comfyui_generate_asset(params: dict) -> dict:
        asset_id = _safe_slug(str(params.get("asset_id") or params.get("id") or "night_market_bg"))
        asset_kind = _normalize_pixel_asset_kind(str(params.get("asset_kind") or params.get("kind") or "background"))
        prompt = str(params.get("prompt") or params.get("asset_prompt") or params.get("episode_goal") or "").strip()
        style_notes = str(params.get("style_notes") or "").strip()
        provider = str(params.get("provider") or params.get("draft_asset_provider") or "auto").strip().lower()
        asset_policy = str(params.get("asset_policy") or "").strip().lower()
        if asset_policy == "approved_only":
            provider = "off"
        output_dir = str(params.get("output_dir") or "cartridges/dev/dev.pixel_episode_director/assets/pixel_stage/drafts").strip()
        asset_manifest_path = str(params.get("asset_manifest_path") or "cartridges/dev/dev.pixel_episode_director/assets/asset_manifest.json").strip()
        report_path = str(params.get("report_path") or params.get("output_path") or "test_output/pixel_episode/draft_asset.json").strip()
        comfyui_url = str(params.get("comfyui_url") or os.environ.get("COMFYUI_URL") or "http://127.0.0.1:8188").strip()
        workflow_path = str(params.get("workflow_path") or os.environ.get("COMFYUI_WORKFLOW_PATH") or "").strip()
        if not prompt:
            prompt = "pixel art 2.5D night market alley background, clean silhouettes, readable layers"
        full_prompt = _pixel_asset_prompt(asset_id, asset_kind, prompt, style_notes)
        try:
            report_target = registry._safe_path(report_path)
            report_target.parent.mkdir(parents=True, exist_ok=True)
            if provider in {"off", "none", "skip"}:
                report = {
                    "status": "skipped",
                    "asset_id": asset_id,
                    "asset_kind": asset_kind,
                    "provider": "off",
                    "message": "draft asset generation skipped by input",
                }
                content = json.dumps(report, ensure_ascii=False, indent=2)
                report_target.write_text(content, encoding="utf-8")
                rel_report = str(report_target.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
                return {"ok": True, "path": rel_report, "content": content, "draft_asset_ok": True, "files": [rel_report]}

            draft_dir = registry._safe_path(output_dir) / _pixel_asset_kind_bucket(asset_kind) / asset_id
            draft_dir.mkdir(parents=True, exist_ok=True)
            image_path = draft_dir / f"{asset_id}.png"
            profile_path = draft_dir / "profile.json"
            errors = []
            image_bytes = None
            provider_used = "local"
            if provider in {"auto", "comfyui", "comfy"}:
                try:
                    image_bytes = _comfyui_generate_image_bytes(registry, comfyui_url, workflow_path, full_prompt)
                    provider_used = "comfyui"
                except Exception as exc:
                    errors.append(f"comfyui: {exc}")
                    if provider in {"comfyui", "comfy"}:
                        report = {
                            "status": "failed",
                            "asset_id": asset_id,
                            "asset_kind": asset_kind,
                            "provider": "comfyui",
                            "errors": errors,
                        }
                        content = json.dumps(report, ensure_ascii=False, indent=2)
                        report_target.write_text(content, encoding="utf-8")
                        rel_report = str(report_target.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
                        return {"ok": False, "path": rel_report, "content": content, "error": errors[-1], "files": [rel_report]}
            if image_bytes:
                image_path.write_bytes(image_bytes)
            else:
                _write_local_pixel_asset_image(image_path, asset_id, asset_kind, full_prompt)
                provider_used = "local"

            rel_image = str(image_path.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            rel_profile = str(profile_path.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            profile = {
                "id": asset_id,
                "kind": asset_kind,
                "status": "draft",
                "provider": provider_used,
                "image": _asset_manifest_local_path(rel_image),
                "prompt": full_prompt,
                "requires_approval": True,
                "usage": "Candidate reference only. It is not used by formal rendering until moved into approved_assets.",
            }
            profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest_rel = _record_draft_pixel_asset(registry, asset_manifest_path, asset_id, asset_kind, rel_profile, rel_image, provider_used)
            report = {
                "status": "draft_created",
                "asset_id": asset_id,
                "asset_kind": asset_kind,
                "provider": provider_used,
                "image_path": rel_image,
                "profile_path": rel_profile,
                "asset_manifest_path": manifest_rel,
                "draft_only": True,
                "errors": errors[:4],
            }
            content = json.dumps(report, ensure_ascii=False, indent=2)
            report_target.write_text(content, encoding="utf-8")
            rel_report = str(report_target.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            return {
                "ok": True,
                "path": rel_image,
                "image_path": rel_image,
                "project_path": rel_profile,
                "preview_path": rel_report,
                "files": [rel_image, rel_profile, rel_report],
                "content": content,
                "draft_asset_ok": True,
                "provider": provider_used,
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"pixel draft asset generation failed: {exc}"}

    def forge_pixel_character_asset(params: dict) -> dict:
        character_id = _safe_slug(str(params.get("character_id") or params.get("asset_id") or params.get("id") or "hero"))
        display_name = str(params.get("display_name") or params.get("name") or character_id).strip()
        role = str(params.get("role") or "character").strip()
        actions = _pixel_character_actions(params.get("actions"))
        palette = _pixel_character_palette(params.get("palette"), character_id)
        frame_width, frame_height = _pixel_frame_size(params.get("frame_size") or params.get("preferred_frame_size"), (128, 192))
        frame_width = max(128, frame_width)
        frame_height = max(192, frame_height)
        frames_per_action = _safe_int(params.get("frames_per_action"), 6, 4, 12)
        fps = _safe_int(params.get("animation_fps"), 12, 1, 24)
        output_root = str(params.get("output_dir") or "cartridges/dev/dev.pixel_episode_director/assets/pixel_stage").strip()
        asset_manifest_path = str(params.get("asset_manifest_path") or "cartridges/dev/dev.pixel_episode_director/assets/asset_manifest.json").strip()
        report_path = str(params.get("report_path") or params.get("output_path") or f"test_output/pixel_episode/{character_id}_asset_forge.json").strip()
        register_mode = str(params.get("register_mode") or "draft").strip().lower()
        if register_mode not in {"approved", "draft"}:
            register_mode = "draft"
        provider = str(params.get("provider") or "local_pixel_forge").strip() or "local_pixel_forge"
        try:
            root_dir = registry._safe_path(output_root)
            asset_dir = root_dir / ("characters" if register_mode == "approved" else "drafts/characters") / character_id
            asset_dir.mkdir(parents=True, exist_ok=True)
            sheet_path = asset_dir / f"{character_id}.spritesheet.png"
            metadata_path = asset_dir / f"{character_id}.spritesheet.json"
            profile_path = asset_dir / "profile.json"
            preview_path = asset_dir / f"{character_id}.preview.html"

            _write_pixel_character_spritesheet(sheet_path, character_id, actions, palette, frame_width, frame_height, frames_per_action)
            rel_sheet = _workspace_rel(registry, sheet_path)
            rel_profile = _workspace_rel(registry, profile_path)
            metadata = _pixel_character_metadata(character_id, rel_sheet, actions, frame_width, frame_height, frames_per_action, fps, rel_profile)
            rel_metadata = _workspace_rel(registry, metadata_path)
            metadata["profile"] = _asset_manifest_local_path(rel_profile)
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

            profile = {
                "id": character_id,
                "name": display_name,
                "role": role,
                "status": register_mode,
                "provider": provider,
                "palette": palette,
                "actions": actions,
                "asset": {
                    "spritesheet": _asset_manifest_local_path(rel_sheet),
                    "metadata": _asset_manifest_local_path(rel_metadata),
                },
                "render_contract": {
                    "min_screen_height_px": 128,
                    "preferred_frame_size": f"{frame_width}x{frame_height}",
                    "animation_min_frames": frames_per_action,
                    "format": "spritesheet_json",
                },
                "stage_notes": str(params.get("stage_notes") or "Locally forged pixel character spritesheet for Godot native animation."),
            }
            profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            preview_path.write_text(_render_pixel_character_preview_html(character_id, rel_sheet, metadata, profile), encoding="utf-8")
            manifest_rel = _record_pixel_character_asset(
                registry,
                asset_manifest_path,
                character_id,
                rel_profile,
                rel_sheet,
                rel_metadata,
                provider,
                register_mode,
            )
            report = {
                "status": "character_asset_forged",
                "character_id": character_id,
                "register_mode": register_mode,
                "provider": provider,
                "spritesheet": rel_sheet,
                "metadata": rel_metadata,
                "profile": rel_profile,
                "preview": _workspace_rel(registry, preview_path),
                "asset_manifest_path": manifest_rel,
                "frame_size": [frame_width, frame_height],
                "min_character_screen_height_px": 128,
                "quality_gate": "frame_size>=128x192",
                "frames_per_action": frames_per_action,
                "actions": actions,
            }
            report_target = registry._safe_path(report_path)
            report_target.parent.mkdir(parents=True, exist_ok=True)
            report_target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            rel_report = _workspace_rel(registry, report_target)
            files = [rel_sheet, rel_metadata, rel_profile, _workspace_rel(registry, preview_path), rel_report]
            return {
                "ok": True,
                "path": rel_sheet,
                "spritesheet_path": rel_sheet,
                "metadata_path": rel_metadata,
                "profile_path": rel_profile,
                "preview_path": _workspace_rel(registry, preview_path),
                "report_path": rel_report,
                "files": files,
                "content": json.dumps(report, ensure_ascii=False, indent=2),
                "asset_forge_ok": True,
                "register_mode": register_mode,
                "provider": provider,
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"pixel character asset forge failed: {exc}"}

    def forge_pixel_location_asset(params: dict) -> dict:
        location_id = _safe_slug(str(params.get("location_id") or params.get("asset_id") or params.get("id") or "night_alley"))
        display_name = str(params.get("display_name") or params.get("name") or location_id).strip()
        resolution = str(params.get("resolution") or params.get("target_resolution") or "1280x720").strip()
        width, height = _parse_pixel_resolution_text(resolution, (1280, 720))
        output_root = str(params.get("output_dir") or "cartridges/dev/dev.pixel_episode_director/assets/pixel_stage").strip()
        asset_manifest_path = str(params.get("asset_manifest_path") or "cartridges/dev/dev.pixel_episode_director/assets/asset_manifest.json").strip()
        report_path = str(params.get("report_path") or params.get("output_path") or f"test_output/pixel_episode/{location_id}_location_forge.json").strip()
        register_mode = str(params.get("register_mode") or "approved").strip().lower()
        if register_mode not in {"approved", "draft"}:
            register_mode = "approved"
        provider = str(params.get("provider") or "local_pixel_forge").strip() or "local_pixel_forge"
        layer_specs = _pixel_location_layer_specs(params.get("layers"))
        try:
            root_dir = registry._safe_path(output_root)
            asset_dir = root_dir / ("locations" if register_mode == "approved" else "drafts/locations") / location_id
            layers_dir = asset_dir / "layers"
            profile_path = asset_dir / "profile.json"
            preview_path = asset_dir / f"{location_id}.preview.html"
            written_layers = _write_pixel_location_layers(layers_dir, layer_specs, width, height)
            layers = []
            for spec in layer_specs:
                layer_id = spec["id"]
                rel_image = _workspace_rel(registry, written_layers[layer_id])
                layers.append({
                    "id": layer_id,
                    "image": _asset_manifest_local_path(rel_image),
                    "parallax": spec["parallax"],
                    "z_index": spec["z_index"],
                })
            rel_profile = _workspace_rel(registry, profile_path)
            profile = {
                "id": location_id,
                "name": display_name,
                "status": register_mode,
                "provider": provider,
                "resolution": f"{width}x{height}",
                "layers": layers,
                "render_contract": {
                    "min_layers": max(4, len(layers)),
                    "target_resolution": f"{width}x{height}",
                    "format": "godot_2d_layers",
                    "requires_layer_images": True,
                },
                "walkable_y": _safe_int(params.get("walkable_y"), 6, 0, 20),
                "stage_notes": str(params.get("stage_notes") or "Forged parallax pixel stage layers for Godot native rendering."),
            }
            profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            preview_path.write_text(_render_pixel_location_preview_html(location_id, layers, profile), encoding="utf-8")
            manifest_rel = _record_pixel_location_asset(
                registry,
                asset_manifest_path,
                location_id,
                rel_profile,
                layers,
                provider,
                register_mode,
            )
            report = {
                "status": "location_asset_forged",
                "location_id": location_id,
                "register_mode": register_mode,
                "provider": provider,
                "profile": rel_profile,
                "preview": _workspace_rel(registry, preview_path),
                "asset_manifest_path": manifest_rel,
                "resolution": [width, height],
                "layers": layers,
            }
            report_target = registry._safe_path(report_path)
            report_target.parent.mkdir(parents=True, exist_ok=True)
            report_target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            rel_report = _workspace_rel(registry, report_target)
            files = [_workspace_rel(registry, path) for path in written_layers.values()]
            files.extend([rel_profile, _workspace_rel(registry, preview_path), rel_report])
            return {
                "ok": True,
                "path": rel_profile,
                "profile_path": rel_profile,
                "preview_path": _workspace_rel(registry, preview_path),
                "report_path": rel_report,
                "files": files,
                "content": json.dumps(report, ensure_ascii=False, indent=2),
                "asset_forge_ok": True,
                "register_mode": register_mode,
                "provider": provider,
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"pixel location asset forge failed: {exc}"}

    def forge_pixel_asset_batch(params: dict) -> dict:
        specs = _coerce_json_dict(
            params.get("asset_specs")
            or params.get("asset_spec_batch")
            or params.get("specs")
            or params.get("content")
        )
        spec_path = str(params.get("asset_specs_path") or "").strip()
        if not specs and spec_path:
            try:
                specs = json.loads(registry._safe_path(spec_path).read_text(encoding="utf-8", errors="replace"))
            except Exception:
                specs = {}
        assets = specs.get("assets") if isinstance(specs, dict) else None
        if not isinstance(assets, list) or not assets:
            return {"ok": False, "error": "asset_spec_batch.v1 requires a non-empty assets array"}
        spec_policy = specs.get("policy") if isinstance(specs.get("policy"), dict) else {}
        if isinstance(specs.get("policy"), str):
            spec_policy = {"asset_policy": specs.get("policy")}

        output_root = str(params.get("output_dir") or "cartridges/dev/dev.pixel_episode_director/assets/pixel_stage").strip()
        draft_output_dir = str(params.get("draft_output_dir") or (output_root.rstrip("/\\") + "/drafts")).strip()
        asset_manifest_path = str(params.get("asset_manifest_path") or "cartridges/dev/dev.pixel_episode_director/assets/asset_manifest.json").strip()
        report_path = str(params.get("report_path") or params.get("output_path") or "test_output/pixel_episode_v2/asset_forge_batch.json").strip()
        asset_policy = str(params.get("asset_policy") or spec_policy.get("asset_policy") or "").strip().lower()
        provider = str(params.get("provider") or spec_policy.get("provider") or "local_pixel_forge").strip()
        image_provider = str(params.get("image_provider") or spec_policy.get("image_provider") or "auto").strip()
        register_mode_default = str(params.get("register_mode") or spec_policy.get("register_mode") or "draft").strip().lower()
        if register_mode_default not in {"approved", "draft"}:
            register_mode_default = "draft"
        style_notes = str(params.get("style_notes") or specs.get("style_notes") or "").strip()

        items = []
        files = []
        failures = []
        for index, raw_item in enumerate(assets, start=1):
            if not isinstance(raw_item, dict):
                failures.append({"index": index, "error": "asset item must be an object"})
                continue
            kind = _normalize_pixel_asset_kind(str(raw_item.get("kind") or raw_item.get("asset_kind") or "background"))
            asset_id = _safe_slug(str(raw_item.get("id") or raw_item.get("asset_id") or raw_item.get("name") or f"{kind}_{index:02d}"))
            requirements = raw_item.get("requirements") if isinstance(raw_item.get("requirements"), dict) else {}
            register_mode = str(raw_item.get("register_mode") or raw_item.get("target_status") or register_mode_default).strip().lower()
            if register_mode not in {"approved", "draft"}:
                register_mode = "draft"
            report_item_path = f"test_output/pixel_episode_v2/assets/{asset_id}.json"
            prompt = str(
                raw_item.get("visual_prompt")
                or raw_item.get("prompt")
                or raw_item.get("description")
                or requirements.get("prompt")
                or asset_id
            ).strip()

            if asset_policy == "approved_only":
                result = {
                    "ok": True,
                    "status": "skipped_by_policy",
                    "asset_id": asset_id,
                    "asset_kind": kind,
                    "asset_policy": asset_policy,
                    "message": "approved_only policy skips draft asset forging",
                }
            elif kind == "character":
                result = forge_pixel_character_asset({
                    "character_id": asset_id,
                    "display_name": raw_item.get("name") or raw_item.get("display_name") or asset_id,
                    "role": raw_item.get("role") or requirements.get("role") or "character",
                    "actions": raw_item.get("actions") or requirements.get("actions") or ["idle", "walk_right", "talk_idle", "look_around"],
                    "palette": raw_item.get("palette") or requirements.get("palette"),
                    "frame_size": raw_item.get("frame_size") or requirements.get("frame_size") or "128x192",
                    "frames_per_action": raw_item.get("frames_per_action") or requirements.get("frames_per_action") or 6,
                    "animation_fps": raw_item.get("animation_fps") or requirements.get("animation_fps") or 12,
                    "register_mode": register_mode,
                    "provider": provider,
                    "output_dir": output_root,
                    "asset_manifest_path": asset_manifest_path,
                    "report_path": report_item_path,
                    "stage_notes": prompt,
                })
            elif kind == "location":
                result = forge_pixel_location_asset({
                    "location_id": asset_id,
                    "display_name": raw_item.get("name") or raw_item.get("display_name") or asset_id,
                    "resolution": raw_item.get("resolution") or requirements.get("resolution") or "1280x720",
                    "layers": raw_item.get("layers") or requirements.get("layers"),
                    "register_mode": register_mode,
                    "provider": provider,
                    "output_dir": output_root,
                    "asset_manifest_path": asset_manifest_path,
                    "report_path": report_item_path,
                    "stage_notes": prompt,
                })
            else:
                result = comfyui_generate_asset({
                    "asset_id": asset_id,
                    "asset_kind": kind,
                    "prompt": prompt,
                    "style_notes": style_notes or raw_item.get("style_notes") or "",
                    "asset_policy": "draft_allowed",
                    "provider": raw_item.get("provider") or image_provider,
                    "comfyui_url": params.get("comfyui_url"),
                    "workflow_path": params.get("workflow_path"),
                    "output_dir": draft_output_dir,
                    "asset_manifest_path": asset_manifest_path,
                    "report_path": report_item_path,
                })

            item_report = {
                "id": asset_id,
                "kind": kind,
                "name": raw_item.get("name") or raw_item.get("display_name") or asset_id,
                "source_spec": raw_item,
                "result": result,
                "ok": bool(result.get("ok")),
            }
            if not result.get("ok"):
                failures.append({"id": asset_id, "kind": kind, "error": result.get("error") or "asset forge failed"})
            for path in result.get("files") or []:
                if path not in files:
                    files.append(path)
            items.append(item_report)

        report = {
            "schema": "asset_forge_batch_result.v1",
            "source_schema": specs.get("schema") if isinstance(specs, dict) else "",
            "status": "completed" if not failures else "completed_with_errors",
            "asset_policy": asset_policy or "draft_allowed",
            "register_mode_default": register_mode_default,
            "count": len(items),
            "failed_count": len(failures),
            "assets": items,
            "failures": failures,
            "requires_user_review": True,
        }
        try:
            target = registry._safe_path(report_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(report, ensure_ascii=False, indent=2)
            target.write_text(content, encoding="utf-8")
            rel_report = _workspace_rel(registry, target)
            if rel_report not in files:
                files.append(rel_report)
            return {
                "ok": not failures,
                "path": rel_report,
                "report_path": rel_report,
                "files": files,
                "content": content,
                "asset_forge_batch_ok": not failures,
                "asset_count": len(items),
                "failed_count": len(failures),
                "requires_user_review": True,
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc), "failures": failures}
        except Exception as exc:
            return {"ok": False, "error": f"pixel asset batch forge failed: {exc}", "failures": failures}

    def godot_render_pixel_episode(params: dict) -> dict:
        shot_plan_path = str(params.get("shot_plan_path") or "test_output/pixel_episode/shot_plan.json").strip()
        shot_plan_content = params.get("shot_plan_content") or params.get("shot_plan_json") or ""
        output_dir = str(params.get("output_dir") or "test_output/pixel_episode").strip()
        filename_prefix = str(params.get("filename_prefix") or params.get("episode_id") or "").strip()
        require_godot_native = _truthy(
            params.get("require_godot_native")
            or params.get("require_native_godot")
            or params.get("require_godot")
        )
        try:
            plan = _load_pixel_shot_plan(registry, shot_plan_path, shot_plan_content)
            episode_id = str(plan.get("episode_id") or filename_prefix or "ep001").strip() or "ep001"
            stem = _safe_slug(filename_prefix or episode_id or "episode")
            target_dir = registry._safe_path(output_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            frames_dir = target_dir / f"{stem}_frames"
            control_frames_dir = target_dir / f"{stem}_control_frames"
            avi_path = target_dir / f"{stem}.avi"
            project_path = target_dir / f"{stem}.pixel_stage.json"
            preview_path = target_dir / f"{stem}.render.preview.html"
            for frame_dir in [frames_dir, control_frames_dir]:
                frame_dir.mkdir(parents=True, exist_ok=True)
                for item in frame_dir.glob("*.png"):
                    try:
                        item.unlink()
                    except OSError:
                        pass
            render_meta, godot_error = _maybe_render_pixel_episode_with_godot(
                registry,
                avi_path,
                plan,
                shot_plan_path,
                shot_plan_content,
                target_dir,
                stem,
            )
            status_text = "Godot Movie Maker has rendered the native pixel stage AVI; the next node will try to mux MP4 with FFmpeg."
            if not render_meta:
                if require_godot_native:
                    return {
                        "ok": False,
                        "renderer": "godot_movie_maker",
                        "godot_required": True,
                        "godot_error": godot_error,
                        "error": godot_error or "Godot native renderer is required but did not produce a valid movie.",
                        "repair": "Install Godot 4 and set GODOT_BIN to the executable path, or put godot/godot4 on PATH.",
                    }
                render_meta = _write_pixel_episode_avi(avi_path, plan, frames_dir, control_frames_dir)
                render_meta["renderer"] = "local_python_pixel_stage"
                render_meta["godot_error"] = godot_error
                status_text = "Godot was unavailable or failed, so the local Python pixel-stage fallback rendered AVI; the next node will try to mux MP4 with FFmpeg."
            project = {
                "renderer": render_meta.get("renderer", "local_python_pixel_stage"),
                "godot_project": "cartridges/dev/dev.pixel_episode_director/assets/pixel_stage/godot_project",
                "shot_plan": shot_plan_path.replace("\\", "/"),
                "video": avi_path.name,
                "frames": frames_dir.name,
                "control_frames": control_frames_dir.name,
                "episode_id": episode_id,
                **render_meta,
            }
            project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
            preview_path.write_text(
                _render_pixel_episode_preview_html(plan, avi_path.name, status_text),
                encoding="utf-8",
            )
            files = [avi_path, project_path, preview_path]
            return {
                "ok": True,
                "path": str(avi_path),
                "video_path": str(avi_path),
                "avi_path": str(avi_path),
                "project_path": str(project_path),
                "preview_path": str(preview_path),
                "frame_dir": str(frames_dir.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/"),
                "control_frame_dir": str(control_frames_dir.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/"),
                "files": [str(item.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/") for item in files if item.exists()],
                "renderer": project["renderer"],
                **render_meta,
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"pixel episode render failed: {exc}"}

    def ffmpeg_mux_episode(params: dict) -> dict:
        video_path = str(params.get("video_path") or params.get("avi_path") or params.get("path") or "").strip()
        if not video_path:
            return {"ok": False, "error": "缺少 video_path 参数"}
        shot_plan_path = str(params.get("shot_plan_path") or "test_output/pixel_episode/shot_plan.json").strip()
        shot_plan_content = params.get("shot_plan_content") or ""
        output_path = str(params.get("output_path") or "test_output/pixel_episode/episode.mp4").strip()
        preview_path_param = str(params.get("preview_path") or "test_output/pixel_episode/episode.preview.html").strip()
        provider = str(params.get("compose_provider") or "auto").strip().lower()
        target_product = str(params.get("target_product") or "mp4").strip().lower()
        try:
            source = registry._safe_path(video_path)
            if not source.exists() or not source.is_file():
                return {"ok": False, "error": f"视频文件不存在：{video_path}"}
            target = registry._safe_path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            plan = _load_pixel_shot_plan(registry, shot_plan_path, shot_plan_content)
            want_mp4 = target_product == "mp4" and provider not in {"off", "none", "skip", "local", "avi", "render_bundle"}
            muxed = _maybe_convert_episode_mp4(target, source, provider) if want_mp4 else None
            final_video = muxed or source
            status = "ok" if muxed else "fallback"
            provider_name = "ffmpeg" if muxed else ("render_bundle" if target_product == "render_bundle" else "local_avi")
            if muxed:
                status_text = "FFmpeg 已输出 MP4。"
            elif target_product == "render_bundle":
                status_text = "目标产物为渲染包，跳过 MP4 合成并保留渲染源视频。"
            else:
                status_text = "当前环境未检测到 FFmpeg、合成被关闭或合成失败，保留 AVI 作为最终视频产物。"
            preview_path = registry._safe_path(preview_path_param)
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            preview_path.write_text(
                _render_pixel_episode_preview_html(plan, final_video.name, status_text),
                encoding="utf-8",
            )
            rel_video = str(final_video.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            rel_source = str(source.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            rel_preview = str(preview_path.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
            files = [rel_video, rel_preview]
            if rel_source not in files:
                files.append(rel_source)
            return {
                "ok": True,
                "path": str(final_video),
                "video_path": str(final_video),
                "preview_path": str(preview_path),
                "files": files,
                "content": json.dumps({
                    "episode_id": plan.get("episode_id"),
                    "title": plan.get("title"),
                    "video": rel_video,
                    "preview": rel_preview,
                    "source_video": rel_source,
                    "provider": provider_name,
                    "target_product": target_product,
                    "status": status,
                    "shots": len(plan.get("shots") or []),
                }, ensure_ascii=False, indent=2),
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"pixel episode mux failed: {exc}"}

    registry._registry["media"].update({
        'generate_pixel_shot_plan': generate_pixel_shot_plan,
        'validate_pixel_shot_plan': validate_pixel_shot_plan,
        'update_pixel_world_state': update_pixel_world_state,
        'check_pixel_assets': check_pixel_assets,
        'comfyui_generate_asset': comfyui_generate_asset,
        'forge_pixel_character_asset': forge_pixel_character_asset,
        'forge_pixel_location_asset': forge_pixel_location_asset,
        'forge_pixel_asset_batch': forge_pixel_asset_batch,
        'godot_render_pixel_episode': godot_render_pixel_episode,
        'ffmpeg_mux_episode': ffmpeg_mux_episode,
    })
