"""Crash-safe JSON storage for machine-owned configuration."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Callable


class LocalConfigError(RuntimeError):
    pass


def read_local_json(
    path: str | Path,
    fallback: dict,
    validator: Callable[[dict], bool] | None = None,
) -> dict:
    target = Path(path)
    if not target.exists():
        return deepcopy(fallback)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _recover_invalid_file(target, fallback)
    except OSError as exc:
        raise LocalConfigError(f"Cannot read local configuration: {target}") from exc
    if not isinstance(data, dict) or (validator is not None and not validator(data)):
        return _recover_invalid_file(target, fallback)
    return data


def write_local_json(path: str | Path, data: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    except OSError as exc:
        raise LocalConfigError(f"Cannot write local configuration: {target}") from exc
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _recover_invalid_file(path: Path, fallback: dict) -> dict:
    backup = _next_corrupt_backup(path)
    try:
        path.replace(backup)
    except OSError as exc:
        raise LocalConfigError(f"Cannot preserve invalid local configuration: {path}") from exc
    restored = deepcopy(fallback)
    write_local_json(path, restored)
    return restored


def _next_corrupt_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.stem}.corrupt-{stamp}{path.suffix}")
    index = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}.corrupt-{stamp}-{index}{path.suffix}")
        index += 1
    return candidate
