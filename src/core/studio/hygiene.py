"""Ownership and package-hygiene gates for the clean base distribution."""

from __future__ import annotations

import json
import re
from pathlib import Path


SOURCE_DIRS = ("src/core", "src/backend", "src/frontend/src")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html"}

# These release-tree shelves are legacy/prohibited locations, not runtime inputs.
# The active registry only reads the user-owned development and installed shelves.
LEGACY_RELEASE_CARTRIDGE_DIRS = ("cartridges/dev", "cartridges/builtin")
PACKAGE_DIRS = (
    *LEGACY_RELEASE_CARTRIDGE_DIRS,
    ".data/user/dev_cartridges",
    ".data/user/installed_cartridges",
)

_SHARED_MARKERS = {
    "builtin",
    "cartridge",
    "filesystem",
    "media",
    "filesystem_read",
    "filesystem_write",
    "filesystem_list",
    "read_file",
    "write_file",
    "append_file",
    "list_dir",
    "exists",
    "media_probe",
    "extract_keyframes",
    "style_keyframes",
    "qc_outputs",
}

_LITERAL_BRANCH_PATTERNS = (
    re.compile(r"(?:cartridge(?:_id|Id|\.id)|flow(?:_id|Id|\.id))\s*(?:={2,3}|!={1,2})\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"['\"]([^'\"]+)['\"]\s*(?:={2,3}|!={1,2})\s*(?:cartridge(?:_id|Id|\.id)|flow(?:_id|Id|\.id))"),
)

PROHIBITED_PACKAGE_DIRS = {
    ".data": "local_data",
    ".tools": "local_tools",
    ".cache": "cache",
    "__pycache__": "cache",
    ".pytest_cache": "cache",
    ".mypy_cache": "cache",
    ".ruff_cache": "cache",
    "cache": "cache",
    "logs": "logs",
    "runs": "runtime_artifact",
    "outputs": "runtime_artifact",
    "temp": "runtime_artifact",
    "tmp": "runtime_artifact",
    "models": "model",
    "checkpoints": "model",
    "weights": "model",
    "node_modules": "cache",
}
PROHIBITED_SECRET_NAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "secrets.json",
    "providers.json",
    "id_rsa",
    "id_ed25519",
}
PROHIBITED_SECRET_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".keystore"}
PROHIBITED_MODEL_SUFFIXES = {".safetensors", ".ckpt", ".pt", ".pth", ".onnx", ".gguf"}
PROHIBITED_RUNTIME_NAMES = {"run.json", "run_state.json", "root_flow_state.json", "events.jsonl"}


def release_tree_manifests(root: str | Path) -> list[Path]:
    base = Path(root)
    manifests = []
    for relative in LEGACY_RELEASE_CARTRIDGE_DIRS:
        directory = base / relative
        if directory.is_dir():
            manifests.extend(directory.glob("*/manifest.json"))
    return sorted(manifests)


def collect_cartridge_markers(root: str | Path) -> set[str]:
    """Collect package-owned identifiers that must not be hardcoded in base source."""
    base = Path(root)
    markers: set[str] = set()
    for relative in PACKAGE_DIRS:
        directory = base / relative
        if not directory.is_dir():
            continue
        for manifest_path in directory.glob("*/manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            _add_marker(markers, manifest.get("id"), allow_simple=True)
            for tool in manifest.get("mcp_tools") or []:
                if not isinstance(tool, dict):
                    continue
                for key in ("id", "server", "tool"):
                    _add_marker(markers, tool.get(key))
            portable = manifest.get("portable_dlc") if isinstance(manifest.get("portable_dlc"), dict) else {}
            descriptor_entry = portable.get("descriptor")
            if isinstance(descriptor_entry, str):
                descriptor_path = (manifest_path.parent / descriptor_entry).resolve()
                try:
                    package_root = manifest_path.parent.resolve()
                    if package_root in descriptor_path.parents and descriptor_path.is_file():
                        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
                        for key in ("id", "owner_cartridge"):
                            _add_marker(markers, descriptor.get(key), allow_simple=True)
                        for tool in descriptor.get("tools") or []:
                            if isinstance(tool, dict):
                                _add_marker(markers, tool.get("server"))
                                _add_marker(markers, tool.get("tool"))
                except (OSError, ValueError, json.JSONDecodeError):
                    pass
    return markers


def scan_source_ownership(root: str | Path, markers: set[str] | None = None) -> list[dict]:
    """Find cartridge identifiers, domain tools, and literal cartridge UI branches in base source."""
    base = Path(root)
    owned_markers = collect_cartridge_markers(base) if markers is None else set(markers)
    findings: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    for relative in SOURCE_DIRS:
        source_root = base / relative
        if not source_root.is_dir():
            continue
        for path in source_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES or "__pycache__" in path.parts:
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, 1):
                for marker in owned_markers:
                    if marker in line:
                        _append_source_finding(findings, seen, base, path, line_number, "package_marker", marker)
                for pattern in _LITERAL_BRANCH_PATTERNS:
                    for match in pattern.finditer(line):
                        literal = match.group(1).strip()
                        if "." in literal or literal.startswith(("dev-", "flow-", "cartridge-")):
                            _append_source_finding(findings, seen, base, path, line_number, "literal_branch", literal)
    return findings


def scan_package_hygiene(package_path: str | Path) -> dict:
    """Reject local state, secrets, caches, models, logs, and run artifacts from a package."""
    root = Path(package_path)
    items: list[dict] = []
    scanned_files = 0
    if not root.is_dir():
        return {
            "status": "blocked",
            "items": [{"path": ".", "category": "missing_package", "message": "Package directory does not exist."}],
            "scanned_files": 0,
        }
    blocked_dirs: set[Path] = set()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        if path.is_symlink():
            items.append({"path": relative_text, "category": "symlink", "message": "Symbolic links are not portable package content."})
            if path.is_dir():
                blocked_dirs.add(path)
            continue
        if path.is_dir():
            category = PROHIBITED_PACKAGE_DIRS.get(path.name.lower())
            if category:
                items.append({"path": relative_text, "category": category, "message": f"Prohibited package directory: {path.name}"})
                blocked_dirs.add(path)
            continue
        if any(parent in blocked_dirs for parent in path.parents):
            continue
        scanned_files += 1
        lower_name = path.name.lower()
        category = None
        message = None
        if lower_name in PROHIBITED_SECRET_NAMES or lower_name.startswith(".env.") or path.suffix.lower() in PROHIBITED_SECRET_SUFFIXES:
            category, message = "secret", "Credential or secret file is local-only."
        elif path.suffix.lower() in PROHIBITED_MODEL_SUFFIXES:
            category, message = "model", "Model weights must not be embedded in a cartridge package."
        elif lower_name.endswith(".log"):
            category, message = "logs", "Log files are runtime-local artifacts."
        elif lower_name in PROHIBITED_RUNTIME_NAMES or lower_name.endswith((".tmp", ".bak", ".swp")):
            category, message = "runtime_artifact", "Generated runtime files must not be published."
        if category:
            items.append({"path": relative_text, "category": category, "message": message})
    return {"status": "blocked" if items else "ok", "items": items, "scanned_files": scanned_files}


def _add_marker(markers: set[str], value, *, allow_simple: bool = False) -> None:
    marker = str(value or "").strip()
    is_domain_specific = any(separator in marker for separator in (".", "_", "-")) or len(marker) >= 16
    if len(marker) >= 4 and marker.lower() not in _SHARED_MARKERS and (allow_simple or is_domain_specific):
        markers.add(marker)


def _append_source_finding(findings, seen, root, path, line_number, kind, marker) -> None:
    relative = path.relative_to(root).as_posix()
    key = (relative, line_number, marker)
    if key in seen:
        return
    seen.add(key)
    findings.append({"path": relative, "line": line_number, "kind": kind, "marker": marker})
