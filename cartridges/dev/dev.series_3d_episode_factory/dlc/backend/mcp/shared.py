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

DLC_ID = "core.shared"
DLC_PROTOCOL = "CF-FARP@0.4"

def _workspace_rel(registry: BuiltinMcpRegistry, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")

def _coerce_json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}

def _load_manifest_from_params(registry: BuiltinMcpRegistry, params: dict, path_key: str, content_key: str) -> dict:
    content = params.get(content_key)
    if isinstance(content, dict):
        return content
    if isinstance(content, str) and content.strip():
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError(f"{content_key} must be a JSON object")
        return data
    path_str = str(params.get(path_key) or params.get("manifest") or "").strip()
    if not path_str:
        raise ValueError(f"missing {path_key}")
    if path_str.startswith("{"):
        data = json.loads(path_str)
        if not isinstance(data, dict):
            raise ValueError(f"{path_key} JSON must be an object")
        return data
    target = registry._safe_path(path_str)
    data = json.loads(target.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise ValueError(f"{path_key} must point to a JSON object")
    return data

def _image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        pass
    try:
        data = path.read_bytes()[:32]
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            width = struct.unpack(">I", data[16:20])[0]
            height = struct.unpack(">I", data[20:24])[0]
            return width, height
        if data.startswith(b"\xff\xd8"):
            with path.open("rb") as fh:
                fh.read(2)
                while True:
                    marker_start = fh.read(1)
                    if not marker_start:
                        break
                    if marker_start != b"\xff":
                        continue
                    marker = fh.read(1)
                    if marker in {b"\xc0", b"\xc2"}:
                        length = struct.unpack(">H", fh.read(2))[0]
                        precision = fh.read(1)
                        height = struct.unpack(">H", fh.read(2))[0]
                        width = struct.unpack(">H", fh.read(2))[0]
                        return width, height
                    if marker in {b"\xd8", b"\xd9"}:
                        continue
                    length_bytes = fh.read(2)
                    if len(length_bytes) < 2:
                        break
                    length = struct.unpack(">H", length_bytes)[0]
                    fh.seek(max(0, length - 2), 1)
    except Exception:
        return None
    return None

def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _safe_int(value, default: int, min_value: int, max_value: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    return max(min_value, min(max_value, number))

def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)

def _safe_slug(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value.strip())
    safe = "_".join(part for part in safe.split("_") if part)
    return safe[:48] or "short_video"

def _maybe_convert_episode_mp4(mp4_path: Path, source_video: Path, provider: str) -> Path | None:
    if provider in {"off", "local", "none"}:
        return None
    ffmpeg = _find_ffmpeg_binary(source_video)
    if not ffmpeg:
        return None
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source_video),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(mp4_path),
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    except Exception:
        return None
    return mp4_path if mp4_path.exists() else None

def _find_ffmpeg_binary(anchor_path: Path | None = None) -> str | None:
    configured = os.environ.get("FFMPEG_BIN", "").strip()
    if configured:
        configured_path = Path(configured)
        if configured_path.is_file():
            return str(configured_path)
        found = shutil.which(configured)
        if found:
            return found

    roots = []
    if anchor_path:
        try:
            current = Path(anchor_path).resolve()
            if current.is_file():
                current = current.parent
            roots.extend([current, *current.parents])
        except OSError:
            pass
    try:
        roots.append(Path.cwd().resolve())
    except OSError:
        pass

    seen = set()
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for root in roots:
        root_key = str(root)
        if root_key in seen:
            continue
        seen.add(root_key)
        tools_dir = root / ".tools"
        candidates = [tools_dir / "ffmpeg" / "bin" / exe_name]
        if tools_dir.exists():
            candidates.extend(tools_dir.glob(f"*/bin/{exe_name}"))
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return shutil.which("ffmpeg")

def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

def _mix(a: tuple[int, int, int], b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(int(a[i] * (1 - amount) + b[i] * amount) for i in range(3))
