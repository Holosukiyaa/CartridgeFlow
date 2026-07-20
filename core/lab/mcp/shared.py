from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
from pathlib import Path


def workspace_rel(registry, path: Path) -> str:
    try:
        return path.resolve().relative_to(registry._workspace_root.resolve()).as_posix()
    except (OSError, ValueError):
        return str(path).replace("\\", "/")


def coerce_json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def load_manifest_from_params(registry, params: dict, path_key: str, content_key: str) -> dict:
    content = params.get(content_key)
    if isinstance(content, dict):
        return content
    if isinstance(content, str) and content.strip():
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError(f"{content_key} must be a JSON object")
        return parsed
    path_value = str(params.get(path_key) or params.get("manifest") or "").strip()
    if not path_value:
        raise ValueError(f"missing {path_key}")
    if path_value.startswith("{"):
        parsed = json.loads(path_value)
        if not isinstance(parsed, dict):
            raise ValueError(f"{path_key} JSON must be an object")
        return parsed
    parsed = json.loads(registry._safe_path(path_value).read_text(encoding="utf-8", errors="replace"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path_key} must point to a JSON object")
    return parsed


def image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        pass
    try:
        data = path.read_bytes()[:32]
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            return struct.unpack(">II", data[16:24])
    except OSError:
        pass
    return None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def safe_slug(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "._-" else "_" for character in str(value).strip())
    safe = "_".join(part for part in safe.split("_") if part)
    return safe[:64] or "artifact"


def find_ffmpeg_binary(anchor_path: Path | None = None) -> str | None:
    configured = os.environ.get("FFMPEG_BIN", "").strip()
    candidates = [configured] if configured else []
    roots = []
    if anchor_path:
        current = Path(anchor_path).resolve()
        roots.extend([current.parent if current.is_file() else current, *(current.parents)])
    roots.append(Path.cwd().resolve())
    executable = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for root in roots:
        candidates.append(str(root / ".tools" / "ffmpeg" / "bin" / executable))
    candidates.append("ffmpeg")
    return _first_executable(candidates)


def find_godot_binary() -> str | None:
    configured = os.environ.get("GODOT_BIN", "").strip()
    candidates = [configured] if configured else []
    roots = [Path.cwd() / ".data" / "mcp_runtime" / "godot", Path.cwd() / ".tools" / "godot"]
    for root in roots:
        marker = root / "GODOT_BIN.txt"
        if marker.is_file():
            candidates.append(marker.read_text(encoding="utf-8").strip())
        if root.is_dir():
            candidates.extend(str(path) for path in sorted(root.rglob("Godot*_win64*.exe")))
            candidates.extend(str(path) for path in sorted(root.rglob("godot*.exe")))
    candidates.extend(["godot", "godot4"])
    return _first_executable(candidates)


def first_comfyui_image(outputs: dict) -> dict | None:
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        for image in output.get("images") or []:
            if isinstance(image, dict) and image.get("filename"):
                return image
    return None


def _first_executable(candidates: list[str]) -> str | None:
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if path.is_file():
            return str(path)
        found = shutil.which(candidate)
        if found:
            return found
    return None
