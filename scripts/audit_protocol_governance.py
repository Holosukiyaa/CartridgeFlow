from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import load_base_implementation, load_protocol_release_catalog


def audit(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    catalog = load_protocol_release_catalog(root)
    protocol_dir = root / "protocol"
    root_files = sorted(path.name for path in protocol_dir.iterdir() if path.is_file() and path.name != "README.md")
    if root_files:
        errors.append(f"protocol root must only contain README.md and category directories: {root_files}")
    for directory in ("base", "catalog", "governance", "releases", "tooling", "vocabulary"):
        if not (protocol_dir / directory).is_dir():
            errors.append(f"protocol/{directory}/ directory is missing")

    protocol_docs = root / "docs" / "protocol"
    flat_documents = [path.name for path in protocol_docs.glob("*.md") if path.name != "README.md"]
    if flat_documents:
        errors.append(f"docs/protocol must not contain flat release documents: {sorted(flat_documents)}")
    _require_text(protocol_docs / "README.md", "release_manifest.json", errors)

    known = {(item["id"], item["version"]) for item in catalog.releases}
    published = {
        (item["id"], item["version"])
        for item in catalog.releases
        if item["lifecycle"] in {"current", "supported_previous"}
    }

    for release in catalog.releases:
        label = f"{release['id']}@{release['version']}"
        registry_path = protocol_dir / release["registry"]
        if not registry_path.is_file():
            errors.append(f"{label}: registry snapshot is missing: {release['registry']}")
            continue
        registry = _read_json(registry_path, errors)
        if registry and (str(registry.get("id")), str(registry.get("version"))) != (release["id"], release["version"]):
            errors.append(f"{label}: registry snapshot identity does not match release manifest")
        for field, registry_field in (("profiles", "profiles_file"), ("capabilities", "capabilities_file")):
            value = release.get(field)
            if not isinstance(value, str) or not (protocol_dir / value).is_file():
                errors.append(f"{label}: {field} snapshot is missing")
            elif registry and registry.get(registry_field) != value:
                errors.append(f"{label}: release manifest {field} does not match registry {registry_field}")
        document = release.get("document")
        if document and not (root / document).is_file():
            errors.append(f"{label}: protocol document is missing: {document}")
        elif document and Path(document).parent != Path("docs/protocol/flow-authoring"):
            errors.append(f"{label}: protocol document must live under docs/protocol/flow-authoring/")

    base_registry = _read_json(protocol_dir / "base" / "CARTRIDGEFLOW-BASE-0.2.json", errors)
    base_document = base_registry.get("document") if base_registry else None
    if base_document != "docs/protocol/base-contract/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md":
        errors.append("CARTRIDGEFLOW-BASE-0.2 document must live under docs/protocol/base-contract/")
    elif not (root / base_document).is_file():
        errors.append("CARTRIDGEFLOW-BASE-0.2 document is missing")

    snapshot_keys = {
        (data.get("id"), str(data.get("version")))
        for path in (protocol_dir / "releases").glob("CF-FARP-*.json")
        for data in [_read_json(path, errors)]
        if data
    }
    if snapshot_keys != known:
        errors.append(f"release manifest and CF-FARP snapshots differ: manifest={sorted(known)}, snapshots={sorted(snapshot_keys)}")

    history = _read_json(protocol_dir / "governance" / "protocol_history.json", errors)
    legacy = {
        (item["id"], item["version"]): item.get("migration_target")
        for item in catalog.releases
        if item["lifecycle"] == "recognized_legacy"
    }
    history_items = history.get("protocols", []) if history else []
    history_legacy = {
        (str(item.get("id")), str(item.get("version"))): item.get("migration_target")
        for item in history_items if isinstance(item, dict)
    }
    if history_legacy != legacy:
        errors.append("governance/protocol_history.json must mirror release_manifest.json recognized_legacy releases and migration targets")
    if (protocol_dir / "protocol_history.json").exists():
        errors.append("protocol_history.json must live under protocol/governance/")
    _require_text(protocol_dir / "governance" / "README.md", "release_manifest.json", errors)

    base = load_base_implementation(root)
    base_supported = {(str(item.get("id")), str(item.get("version"))) for item in base.get("supported_protocols", [])}
    unknown_base = base_supported - published
    if unknown_base:
        errors.append(f"Base declares releases that are not published by release manifest: {sorted(unknown_base)}")
    default = catalog.data["default_for_new_flows"]
    default_key = (str(default["id"]), str(default["version"]))
    if default_key not in base_supported:
        errors.append(f"Base must declare the default new-flow release: {default_key[0]}@{default_key[1]}")

    _require_text(root / "src/core/protocol/capability_registry.py", "load_protocol_release_catalog", errors)
    _require_text(root / "src/core/lab/dev_flow.py", "self.default_protocol_version", errors)
    _require_text(root / "src/backend/main.py", "protocol_catalog", errors)
    _require_text(root / "src/frontend/src/pages/FlowWorkbench.tsx", "protocolCatalog", errors)
    _require_text(root / "docs/protocol/governance/GOVERNANCE.md", "release_manifest.json", errors)
    for document in [
        "AGENT.md",
        "docs/README.md",
        "protocol/README.md",
        "docs/protocol/governance/GOVERNANCE.md",
        "docs/planning/ROADMAP.md",
        "docs/architecture/FLOW_AUTHORING_ANALYSIS_CONTRACT.md",
        "docs/architecture/PORTABLE_DLC_ARCHITECTURE.md",
    ]:
        _require_text(root / document, "release_manifest.json", errors)

    baseline_headers = {
        "docs/README.md": "CF-FARP 0.9",
        "docs/protocol/governance/GOVERNANCE.md": "CF-FARP@0.9",
        "docs/planning/ROADMAP.md": "CF-FARP@0.9",
        "docs/architecture/FLOW_AUTHORING_ANALYSIS_CONTRACT.md": "CF-FARP@0.9",
        "docs/architecture/PORTABLE_DLC_ARCHITECTURE.md": "CF-FARP@0.9",
    }
    for document, marker in baseline_headers.items():
        header = "\n".join((root / document).read_text(encoding="utf-8").splitlines()[:24])
        if marker not in header:
            errors.append(f"{document} must present the v0.9 release baseline in its header")

    stale_phrases = ("最新 FARP v0.8", "v0.7 是最新目标规范", "目标协议基线：`CARTRIDGEFLOW-BASE@0.2`、`CF-FARP@0.8`")
    for path in (root / "docs").rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for phrase in stale_phrases:
            if phrase in text:
                errors.append(f"{path.relative_to(root)} still presents a stale protocol baseline: {phrase}")

    for path in _project_text_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for version in re.findall(r"CF-FARP@(\d+\.\d+)", text):
            if ("CF-FARP", version) not in known:
                errors.append(f"{path.relative_to(root)} references unregistered CF-FARP@{version}")
    return errors


def _read_json(path: Path, errors: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.relative_to(ROOT)} is not valid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.relative_to(ROOT)} must be a JSON object")
        return {}
    return value


def _require_text(path: Path, expected: str, errors: list[str]) -> None:
    if expected not in path.read_text(encoding="utf-8"):
        errors.append(f"{path.relative_to(ROOT)} must reference {expected}")


def _project_text_files(root: Path):
    ignored = {".git", ".data", "node_modules", "dist", "__pycache__"}
    extensions = {".py", ".ts", ".tsx", ".json", ".md"}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in extensions or any(part in ignored for part in path.parts):
            continue
        yield path


def main() -> int:
    errors = audit()
    if errors:
        print("Protocol governance audit failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Protocol governance audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
