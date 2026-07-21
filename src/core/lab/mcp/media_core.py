from __future__ import annotations

import base64
import html
import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import time
import wave
import zlib
from pathlib import Path

from .shared import (
    coerce_json_dict as _coerce_json_dict,
    file_sha256 as _file_sha256,
    find_ffmpeg_binary as _find_ffmpeg_binary,
    image_dimensions as _image_dimensions,
    load_manifest_from_params as _load_manifest_from_params,
    safe_int as _safe_int,
    safe_slug as _safe_slug,
    workspace_rel as _workspace_rel,
)

DLC_ID = 'core.media'
DLC_PROTOCOL = 'CF-FARP@0.4'
TOOLS = ['media_probe', 'extract_keyframes', 'style_keyframes', 'qc_outputs']

def _select_keyframes(frames: list[Path], shots: list[dict], fps: int, frames_per_shot: int, mode: str) -> list[dict]:
    if not shots:
        index = max(0, min(len(frames) - 1, len(frames) // 2))
        return [{"shot_id": "shot_001", "shot_index": 0, "label": "key", "frame_index": index, "source": frames[index]}]

    selected = []
    cursor = 0.0
    for shot_index, shot in enumerate(shots):
        duration = max(1.0, float(_safe_int(shot.get("duration"), 4, 1, 999)))
        shot_id = str(shot.get("id") or f"shot_{shot_index + 1:03d}")
        points = []
        if frames_per_shot >= 3:
            points = [("start", cursor), ("middle", cursor + duration * 0.5), ("end", cursor + max(0.0, duration - 1.0 / max(1, fps)))]
        elif frames_per_shot == 2:
            points = [("start", cursor), ("end", cursor + max(0.0, duration - 1.0 / max(1, fps)))]
        elif mode == "start":
            points = [("start", cursor)]
        elif mode == "end":
            points = [("end", cursor + max(0.0, duration - 1.0 / max(1, fps)))]
        else:
            points = [("key", cursor + duration * 0.5)]
        for label, second in points[:frames_per_shot]:
            frame_index = max(0, min(len(frames) - 1, int(round(second * max(1, fps)))))
            selected.append({
                "shot_id": shot_id,
                "shot_index": shot_index,
                "label": label,
                "frame_index": frame_index,
                "source": frames[frame_index],
            })
        cursor += duration
    return selected

def _preview_src(path_str: str) -> str:
    text = str(path_str or "").replace("\\", "/")
    for marker in ["/keyframes/", "/styled/", "keyframes/", "styled/"]:
        if marker in text:
            return text[text.index(marker.strip("/")):]
    return Path(text).name

def _cache_bust_src(src: str) -> str:
    if not src:
        return src
    separator = "&" if "?" in src else "?"
    return f"{src}{separator}v={int(time.time())}"

def _render_keyframe_preview_html(manifest: dict, title: str) -> str:
    cards = []
    for item in manifest.get("keyframes") or []:
        image = html.escape(_cache_bust_src(_preview_src(item.get("image", ""))))
        shot_id = html.escape(str(item.get("shot_id") or "shot"))
        label = html.escape(str(item.get("label") or "key"))
        cards.append(f"<figure><img src=\"{image}\" alt=\"{shot_id}\"/><figcaption>{shot_id} / {label}</figcaption></figure>")
    return _render_media_grid_html(title, cards, "Keyframes extracted from the source frame sequence.")

def _render_style_preview_html(manifest: dict, title: str) -> str:
    cards = []
    for item in manifest.get("outputs") or []:
        base = html.escape(_cache_bust_src(_preview_src(item.get("base", ""))))
        styled = html.escape(_cache_bust_src(_preview_src(item.get("styled", ""))))
        shot_id = html.escape(str(item.get("shot_id") or "shot"))
        cards.append(
            f"<figure><div class=\"pair\"><img src=\"{base}\" alt=\"{shot_id} base\"/><img src=\"{styled}\" alt=\"{shot_id} styled\"/></div>"
            f"<figcaption>{shot_id} / seed {html.escape(str(item.get('seed', '')))}</figcaption></figure>"
        )
    provider = html.escape(str(manifest.get("provider") or "media"))
    return _render_media_grid_html(title, cards, f"Provider: {provider}. Left is source, right is processed output.")

def _render_media_grid_html(title: str, cards: list[str], subtitle: str) -> str:
    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    body = "\n".join(cards) or "<p>No media outputs.</p>"
    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8" />
<title>{safe_title}</title>
<style>
body{{margin:0;background:#10141b;color:#edf2f7;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:24px;}}
main{{max-width:1180px;margin:0 auto;}}
h1{{font-size:24px;margin:0 0 8px;}}p{{color:#aeb8c5;line-height:1.7;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;margin-top:20px;}}
figure{{margin:0;background:#171d26;border:1px solid #2b3442;border-radius:8px;padding:10px;}}
img{{width:100%;height:auto;display:block;background:#05070a;border-radius:4px;image-rendering:auto;}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
figcaption{{font-size:12px;color:#cbd5e1;margin-top:8px;word-break:break-word;}}
</style>
<main>
  <h1>{safe_title}</h1>
  <p>{safe_subtitle}</p>
  <section class="grid">{body}</section>
</main>
</html>
"""

def _compose_upgrade_prompt(style_notes: str) -> str:
    base = (
        "cinematic animation keyframe, coherent composition, stable silhouettes, "
        "consistent character count, positions, scene geometry, and readable lighting"
    )
    notes = str(style_notes or "").strip()
    if not notes:
        return base
    lower = notes.lower()
    if "preserve original composition" in lower:
        return notes
    return f"{base}, scene notes: {notes}"


def _load_shot_plan(registry, path_value: str, content_value) -> dict:
    if isinstance(content_value, dict):
        return content_value
    if isinstance(content_value, str) and content_value.strip():
        parsed = json.loads(content_value)
        if not isinstance(parsed, dict):
            raise ValueError("shot_plan_content must be a JSON object")
        return parsed
    target = registry._safe_path(path_value)
    parsed = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("shot plan must be a JSON object")
    return parsed

def _style_image_locally(source: Path, target: Path, style_prompt: str, seed: int) -> None:
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        img = Image.open(source).convert("RGB")
        prompt_hash = int(hashlib.sha256(f"{style_prompt}|{seed}".encode("utf-8")).hexdigest()[:8], 16)
        overlay_color = [
            (64, 154, 194),
            (212, 112, 78),
            (143, 105, 210),
            (220, 180, 78),
            (81, 180, 132),
        ][prompt_hash % 5]
        img = ImageEnhance.Color(img).enhance(1.18)
        img = ImageEnhance.Contrast(img).enhance(1.12)
        overlay = Image.new("RGB", img.size, overlay_color)
        img = Image.blend(img, overlay, 0.12)
        img = ImageOps.posterize(img, 6)
        img = img.filter(ImageFilter.SHARPEN)
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target)
    except Exception:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

def _image_file_sequence_report(paths: list[Path], label: str) -> dict:
    items = []
    hashes = []
    perceptual_hashes = []
    for path in paths:
        try:
            file_hash = _file_sha256(path)
        except Exception as exc:
            items.append({"name": path.name, "error": str(exc)})
            continue
        perceptual_hash = _png_average_hash(path)
        item = {"name": path.name, "hash": file_hash[:16]}
        if perceptual_hash:
            item["perceptual_hash"] = perceptual_hash
            perceptual_hashes.append(perceptual_hash)
        items.append(item)
        hashes.append(file_hash)
    unique_perceptual_groups = _count_perceptual_groups(perceptual_hashes) if perceptual_hashes else len(hashes)
    return {
        "label": label,
        "count": len(paths),
        "checked": len(hashes),
        "unique_hashes": len(set(hashes)),
        "unique_perceptual_groups": unique_perceptual_groups,
        "perceptual_threshold": 4,
        "items": items,
    }

def _frame_sequence_motion_report(frames: list[bytes], max_samples: int = 12) -> dict:
    frame_count = len(frames)
    if frame_count <= 0:
        return {"frame_count": 0, "sample_count": 0, "unique_sampled_frames": 0, "sample_indices": [], "sample_hashes": []}
    sample_count = min(frame_count, max(1, max_samples))
    if sample_count == 1:
        indices = [0]
    else:
        indices = sorted({int(round(i * (frame_count - 1) / (sample_count - 1))) for i in range(sample_count)})
    hashes = [hashlib.sha256(frames[index]).hexdigest() for index in indices]
    transitions = sum(1 for index in range(1, len(hashes)) if hashes[index] != hashes[index - 1])
    return {
        "frame_count": frame_count,
        "sample_count": len(indices),
        "unique_sampled_frames": len(set(hashes)),
        "sample_indices": indices,
        "sample_hashes": [item[:16] for item in hashes],
        "sample_transitions": transitions,
        "static_sequence": len(set(hashes)) <= 1,
    }

def _png_average_hash(path: Path, size: int = 8) -> str | None:
    try:
        data = path.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return None
        width, height, color_type, rows, palette = _decode_png_rows(data)
        if width <= 0 or height <= 0 or not rows:
            return None
        samples = []
        for gy in range(size):
            y = min(height - 1, int((gy + 0.5) * height / size))
            row = rows[y]
            for gx in range(size):
                x = min(width - 1, int((gx + 0.5) * width / size))
                samples.append(_png_luma_at(row, x, color_type, palette))
        average = sum(samples) / max(1, len(samples))
        bits = ["1" if value >= average else "0" for value in samples]
        return f"{int(''.join(bits), 2):0{size * size // 4}x}"
    except Exception:
        return None

def _decode_png_rows(data: bytes) -> tuple[int, int, int, list[bytearray], list[tuple[int, int, int]]]:
    offset = 8
    width = 0
    height = 0
    bit_depth = 0
    color_type = 0
    palette: list[tuple[int, int, int]] = []
    idat = bytearray()
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", payload)
        elif chunk_type == b"PLTE":
            palette = [
                (payload[index], payload[index + 1], payload[index + 2])
                for index in range(0, len(payload) - 2, 3)
            ]
        elif chunk_type == b"IDAT":
            idat.extend(payload)
        elif chunk_type == b"IEND":
            break
    if bit_depth != 8 or color_type not in {0, 2, 3, 4, 6}:
        raise ValueError("unsupported PNG format for perceptual hash")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    row_size = width * channels
    raw = zlib.decompress(bytes(idat))
    rows = []
    previous = bytearray(row_size)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor:cursor + row_size])
        cursor += row_size
        _unfilter_png_row(row, previous, filter_type, channels)
        rows.append(row)
        previous = row
    return width, height, color_type, rows, palette

def _unfilter_png_row(row: bytearray, previous: bytearray, filter_type: int, bytes_per_pixel: int) -> None:
    if filter_type == 0:
        return
    for index in range(len(row)):
        left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        up = previous[index] if index < len(previous) else 0
        up_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel and index - bytes_per_pixel < len(previous) else 0
        if filter_type == 1:
            row[index] = (row[index] + left) & 0xFF
        elif filter_type == 2:
            row[index] = (row[index] + up) & 0xFF
        elif filter_type == 3:
            row[index] = (row[index] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            row[index] = (row[index] + _paeth_predictor(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"unsupported PNG filter: {filter_type}")

def _paeth_predictor(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_up_left = abs(estimate - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left

def _png_luma_at(row: bytearray, x: int, color_type: int, palette: list[tuple[int, int, int]]) -> int:
    if color_type == 0:
        return row[x]
    if color_type == 3:
        color = palette[row[x]] if row[x] < len(palette) else (0, 0, 0)
        r, g, b = color
    elif color_type == 4:
        r = g = b = row[x * 2]
    elif color_type == 6:
        offset = x * 4
        r, g, b = row[offset], row[offset + 1], row[offset + 2]
    else:
        offset = x * 3
        r, g, b = row[offset], row[offset + 1], row[offset + 2]
    return int(0.299 * r + 0.587 * g + 0.114 * b)

def _count_perceptual_groups(hashes: list[str], threshold: int = 4) -> int:
    groups: list[str] = []
    for item in hashes:
        if not any(_hex_hamming_distance(item, group) <= threshold for group in groups):
            groups.append(item)
    return len(groups)

def _hex_hamming_distance(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except Exception:
        return 9999


def register(registry):
    def media_probe(params: dict) -> dict:
        providers = params.get("providers") or ["local", "ffmpeg"]
        if isinstance(providers, str):
            providers = [item.strip() for item in providers.replace(",", "\n").splitlines() if item.strip()]
        result = {}
        for provider in providers:
            provider_name = str(provider or "").strip().lower()
            if provider_name in {"local", "local_python"}:
                result["local"] = {"ok": True, "provider": "local_python", "message": "local media helpers are available"}
            elif provider_name == "ffmpeg":
                ffmpeg = _find_ffmpeg_binary()
                result["ffmpeg"] = {"ok": bool(ffmpeg), "path": ffmpeg or "", "message": "ffmpeg found" if ffmpeg else "ffmpeg not found"}
            else:
                result[provider_name or "unknown"] = {"ok": False, "message": f"unknown media provider: {provider}"}
        return {
            "ok": True,
            "providers": result,
            "content": json.dumps(result, ensure_ascii=False, indent=2),
        }

    def extract_keyframes(params: dict) -> dict:
        render_bundle = _coerce_json_dict(params.get("render_bundle"))
        frame_dir = str(params.get("frame_dir") or render_bundle.get("control_frame_dir") or render_bundle.get("frame_dir") or "").strip()
        if not frame_dir:
            return {"ok": False, "error": "missing frame_dir or render_bundle.frame_dir"}
        shot_plan_path = str(params.get("shot_plan_path") or "test_output/media/shot_plan.json").strip()
        shot_plan_content = params.get("shot_plan_content") or params.get("shot_plan_json") or ""
        output_dir = str(params.get("output_dir") or "test_output/media_control_bundle").strip()
        frames_per_shot = _safe_int(params.get("frames_per_shot"), 1, 1, 3)
        mode = str(params.get("mode") or "middle").strip().lower()
        try:
            source_dir = registry._safe_path(frame_dir)
            if not source_dir.exists() or not source_dir.is_dir():
                return {"ok": False, "error": f"frame_dir not found: {frame_dir}"}
            plan = _load_shot_plan(registry, shot_plan_path, shot_plan_content)
            frames = sorted(source_dir.glob("*.png"))
            if not frames:
                return {"ok": False, "error": f"no PNG frames found in {frame_dir}"}
            target_root = registry._safe_path(output_dir)
            keyframe_dir = target_root / "keyframes"
            meta_dir = target_root / "meta"
            keyframe_dir.mkdir(parents=True, exist_ok=True)
            meta_dir.mkdir(parents=True, exist_ok=True)
            shots = [shot for shot in plan.get("shots") or [] if isinstance(shot, dict)]
            fps = _safe_int((plan.get("style") or {}).get("fps"), _safe_int(render_bundle.get("fps"), 12, 1, 60), 1, 60)
            selected = _select_keyframes(frames, shots, fps, frames_per_shot, mode)
            keyframes = []
            for item in selected:
                shot_id = _safe_slug(str(item["shot_id"] or f"shot_{item['shot_index'] + 1:03d}"))
                suffix = item["label"]
                target = keyframe_dir / f"{shot_id}_{suffix}.png"
                shutil.copy2(item["source"], target)
                keyframes.append({
                    "shot_id": shot_id,
                    "label": suffix,
                    "source_frame": _workspace_rel(registry, item["source"]),
                    "image": _workspace_rel(registry, target),
                    "frame_index": item["frame_index"],
                    "second": round(item["frame_index"] / max(1, fps), 3),
                })
            keyframe_check = _image_file_sequence_report([registry._safe_path(item["image"]) for item in keyframes], "keyframes")
            if len(keyframes) > 1 and keyframe_check["unique_hashes"] <= 1:
                return {
                    "ok": False,
                    "error": "selected keyframes are identical; source frame motion collapsed before downstream processing",
                    "keyframe_check": keyframe_check,
                }
            shot_plan_target = meta_dir / "shot_plan.json"
            shot_plan_target.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest = {
                "schema_version": 1,
                "kind": "media_control_bundle",
                "source": {
                    "frame_dir": _workspace_rel(registry, source_dir),
                    "shot_plan": _workspace_rel(registry, shot_plan_target),
                    "renderer": render_bundle.get("renderer", ""),
                },
                "fps": fps,
                "mode": mode,
                "frames_per_shot": frames_per_shot,
                "keyframe_check": keyframe_check,
                "keyframes": keyframes,
            }
            manifest_path = meta_dir / "keyframe_manifest.json"
            preview_path = target_root / "keyframes.preview.html"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            preview_path.write_text(_render_keyframe_preview_html(manifest, "Extracted keyframes"), encoding="utf-8")
            files = [_workspace_rel(registry, manifest_path), _workspace_rel(registry, preview_path), *[item["image"] for item in keyframes]]
            return {
                "ok": True,
                "path": _workspace_rel(registry, manifest_path),
                "manifest": _workspace_rel(registry, manifest_path),
                "preview_path": _workspace_rel(registry, preview_path),
                "files": files,
                "keyframe_count": len(keyframes),
                "keyframe_check": keyframe_check,
                "content": json.dumps(manifest, ensure_ascii=False, indent=2),
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"extract keyframes failed: {exc}"}

    def style_keyframes(params: dict) -> dict:
        manifest = _load_manifest_from_params(registry, params, "input_manifest", "manifest_content")
        keyframes = [item for item in manifest.get("keyframes") or [] if isinstance(item, dict)]
        if not keyframes:
            return {"ok": False, "error": "input manifest has no keyframes"}
        provider = str(params.get("provider") or "local").strip().lower()
        if provider == "auto":
            provider = "local"
        if provider not in {"local", "off", "none", "skip"}:
            return {"ok": False, "error": f"unsupported base media provider: {provider}; use a cartridge DLC for external providers"}
        style_prompt = _compose_upgrade_prompt(str(params.get("style_prompt") or "").strip())
        output_dir = str(params.get("output_dir") or "test_output/media_upgrade").strip()
        seed = _safe_int(params.get("seed"), 123456, 0, 2147483647)
        try:
            target_root = registry._safe_path(output_dir)
            image_dir = target_root / "styled"
            image_dir.mkdir(parents=True, exist_ok=True)
            outputs = []
            errors = []
            provider_used = "off" if provider in {"off", "none", "skip"} else "local"
            for index, item in enumerate(keyframes):
                source_rel = str(item.get("image") or item.get("path") or "").strip()
                if not source_rel:
                    errors.append({"shot_id": item.get("shot_id"), "error": "missing keyframe image"})
                    continue
                source = registry._safe_path(source_rel)
                if not source.is_file():
                    errors.append({"shot_id": item.get("shot_id"), "error": f"keyframe missing: {source_rel}"})
                    continue
                shot_id = _safe_slug(str(item.get("shot_id") or f"shot_{index + 1:03d}"))
                label = _safe_slug(str(item.get("label") or "key"))
                target = image_dir / f"{shot_id}_{label}_styled.png"
                item_seed = seed + index
                if provider_used == "off":
                    shutil.copy2(source, target)
                else:
                    _style_image_locally(source, target, style_prompt, item_seed)
                outputs.append({
                    "shot_id": shot_id,
                    "label": label,
                    "base": _workspace_rel(registry, source),
                    "styled": _workspace_rel(registry, target),
                    "seed": item_seed,
                    "prompt": style_prompt,
                    "status": "completed",
                })
            output_paths = [registry._safe_path(item["styled"]) for item in outputs]
            output_check = _image_file_sequence_report(output_paths, "styled_outputs")
            upgrade_manifest = {
                "schema_version": 1,
                "kind": "media_style_manifest",
                "provider": provider_used,
                "source_bundle": params.get("input_manifest") or "",
                "output_check": output_check,
                "outputs": outputs,
                "errors": errors,
            }
            manifest_path = target_root / "media_style_manifest.json"
            preview_path = target_root / "media_style.preview.html"
            manifest_path.write_text(json.dumps(upgrade_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            preview_path.write_text(_render_style_preview_html(upgrade_manifest, "Local media style pass"), encoding="utf-8")
            files = [_workspace_rel(registry, manifest_path), _workspace_rel(registry, preview_path), *[item["styled"] for item in outputs]]
            return {
                "ok": bool(outputs),
                "path": _workspace_rel(registry, manifest_path),
                "manifest": _workspace_rel(registry, manifest_path),
                "preview_path": _workspace_rel(registry, preview_path),
                "files": files,
                "provider": provider_used,
                "output_count": len(outputs),
                "output_check": output_check,
                "errors": errors,
                "content": json.dumps(upgrade_manifest, ensure_ascii=False, indent=2),
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"style keyframes failed: {exc}"}

    def qc_outputs(params: dict) -> dict:
        manifest = _load_manifest_from_params(registry, params, "input_manifest", "manifest_content")
        output_path = str(params.get("output_path") or "test_output/media_upgrade/qc_report.json").strip()
        min_outputs = _safe_int(params.get("min_outputs"), 1, 0, 9999)
        require_images = params.get("require_images", True) is not False
        try:
            outputs = [item for item in manifest.get("outputs") or manifest.get("keyframes") or [] if isinstance(item, dict)]
            issues = []
            checked = []
            for item in outputs:
                image_rel = str(item.get("styled") or item.get("image") or item.get("path") or "").strip()
                if not image_rel:
                    issues.append(f"{item.get('shot_id') or 'item'} missing image path")
                    continue
                try:
                    image_path = registry._safe_path(image_rel)
                except PermissionError as exc:
                    issues.append(str(exc))
                    continue
                if not image_path.is_file():
                    issues.append(f"missing image: {image_rel}")
                    continue
                meta = {"shot_id": item.get("shot_id"), "image": _workspace_rel(registry, image_path), "size": image_path.stat().st_size}
                if require_images:
                    dims = _image_dimensions(image_path)
                    if dims:
                        meta["width"], meta["height"] = dims
                    else:
                        issues.append(f"cannot read image dimensions: {image_rel}")
                file_hash = _file_sha256(image_path)
                meta["hash"] = file_hash[:16]
                perceptual_hash = _png_average_hash(image_path)
                if perceptual_hash:
                    meta["perceptual_hash"] = perceptual_hash
                checked.append(meta)
            if len(checked) < min_outputs:
                issues.append(f"expected at least {min_outputs} outputs, got {len(checked)}")
            output_paths = [registry._safe_path(item["image"]) for item in checked]
            output_check = _image_file_sequence_report(output_paths, "qc_outputs")
            if len(checked) > 1 and output_check["unique_hashes"] <= 1:
                issues.append("all checked output images have identical file hashes")
            if len(checked) > 1 and output_check.get("unique_perceptual_groups", 0) <= 1:
                issues.append("all checked output images are visually near-identical")
            report = {
                "ok": not issues,
                "passed": not issues,
                "issues": issues,
                "checked": checked,
                "output_check": output_check,
                "selected_outputs": checked,
                "fallback": params.get("fallback") or "source_media_bundle",
            }
            target = registry._safe_path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return {
                "ok": True,
                "passed": report["passed"],
                "path": _workspace_rel(registry, target),
                "files": [_workspace_rel(registry, target)],
                "issues": issues,
                "content": json.dumps(report, ensure_ascii=False, indent=2),
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"qc outputs failed: {exc}"}

    registry._registry["media"].update({
        'media_probe': media_probe,
        'extract_keyframes': extract_keyframes,
        'style_keyframes': style_keyframes,
        'qc_outputs': qc_outputs,
    })
