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
from core.protocol.base_manifest import supports_protocol_release, supports_subprotocol_release


def audit(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    catalog = load_protocol_release_catalog(root)
    protocol_dir = root / "protocol"
    root_files = sorted(path.name for path in protocol_dir.iterdir() if path.is_file() and path.name != "README.md")
    if root_files:
        errors.append(f"protocol root must only contain README.md and category directories: {root_files}")
    for directory in ("base", "catalog", "flow-authoring", "governance", "release-envelope", "tuning"):
        if not (protocol_dir / directory).is_dir():
            errors.append(f"protocol/{directory}/ directory is missing")

    known = {(item["id"], item["version"]) for item in catalog.releases}
    published = {
        (item["id"], item["version"])
        for item in catalog.releases
        if item["lifecycle"] in {"current", "supported_previous"}
    }
    published.update(
        (item["id"], item["version"])
        for item in catalog.release_envelopes
        if item.get("implementation_status") in {"partial", "supported"}
    )

    for release in catalog.releases:
        label = f"{release['id']}@{release['version']}"
        if release["lifecycle"] in {"current", "supported_previous"} and not release.get("runtime_adapter"):
            errors.append(f"{label}: published releases must declare a runtime_adapter")
        registry_path = protocol_dir / release["registry"]
        if not registry_path.is_file():
            errors.append(f"{label}: registry snapshot is missing: {release['registry']}")
            continue
        registry = _read_json(registry_path, errors)
        if registry and (str(registry.get("id")), str(registry.get("version"))) != (release["id"], release["version"]):
            errors.append(f"{label}: registry snapshot identity does not match release manifest")
        for field in ("runtime_adapter", "features"):
            if field in release and registry and registry.get(field) != release[field]:
                errors.append(f"{label}: release manifest {field} does not match registry {field}")
        for subprotocol in release.get("trusted_subprotocols") or []:
            registry_path = protocol_dir / str(subprotocol.get("registry") or "")
            sub_label = f"{subprotocol.get('id')}@{subprotocol.get('version')}"
            if not registry_path.is_file():
                errors.append(f"{label}: trusted subprotocol registry is missing: {subprotocol.get('registry')}")
                continue
            sub_registry = _read_json(registry_path, errors)
            if sub_registry and (str(sub_registry.get("id")), str(sub_registry.get("version"))) != (str(subprotocol.get("id")), str(subprotocol.get("version"))):
                errors.append(f"{label}: trusted subprotocol identity does not match {sub_label}")
            hosts = sub_registry.get("host_protocols") if sub_registry else []
            if not any(isinstance(host, dict) and str(host.get("id")) == release["id"] and str(host.get("version")) == release["version"] for host in hosts or []):
                errors.append(f"{label}: trusted subprotocol {sub_label} does not declare this host release")
        for field, registry_field in (("profiles", "profiles_file"), ("capabilities", "capabilities_file")):
            value = release.get(field)
            if not isinstance(value, str) or not (protocol_dir / value).is_file():
                errors.append(f"{label}: {field} snapshot is missing")
            elif registry and registry.get(registry_field) != value:
                errors.append(f"{label}: release manifest {field} does not match registry {registry_field}")
        document = release.get("document")
        if document and not (root / document).is_file():
            errors.append(f"{label}: protocol document is missing: {document}")
        elif document and Path(document).parent != Path("protocol/flow-authoring") / release["version"]:
            errors.append(f"{label}: protocol document must live under protocol/flow-authoring/{release['version']}/")

    envelope_known = {(item["id"], item["version"]) for item in catalog.release_envelopes}
    for release in catalog.release_envelopes:
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
        if not (root / document).is_file():
            errors.append(f"{label}: protocol document is missing: {document}")
        elif Path(document).parent != Path("protocol/release-envelope") / release["version"]:
            errors.append(f"{label}: protocol document must live under protocol/release-envelope/{release['version']}/")

    envelope_snapshot_keys = {
        (data.get("id"), str(data.get("version")))
        for release in catalog.release_envelopes
        for data in [_read_json(protocol_dir / release["registry"], errors)]
        if data
    }
    if envelope_snapshot_keys != envelope_known:
        errors.append(f"release envelope manifest and CF-CRE snapshots differ: manifest={sorted(envelope_known)}, snapshots={sorted(envelope_snapshot_keys)}")

    base_contract = catalog.data["base_contract"]
    base_version = str(base_contract["version"])
    base_registry = _read_json(protocol_dir / "base" / base_version / "release.json", errors)
    base_document = base_registry.get("document") if base_registry else None
    expected_base_document = f"protocol/base/{base_version}/specification.md"
    if base_document != expected_base_document:
        errors.append(f"{base_contract['id']}@{base_version} document must live under protocol/base/{base_version}/")
    elif not (root / base_document).is_file():
        errors.append(f"{base_contract['id']}@{base_version} document is missing")

    snapshot_keys = {
        (data.get("id"), str(data.get("version")))
        for release in catalog.releases
        for data in [_read_json(protocol_dir / release["registry"], errors)]
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
        errors.append(f"Base declares protocols that are not published by release manifest: {sorted(unknown_base)}")
    default = catalog.data["default_for_new_flows"]
    default_key = (str(default["id"]), str(default["version"]))
    default_release = catalog.get(*default_key)
    if not supports_protocol_release(base, default_release):
        errors.append(f"Base must support the default new-flow release through its adapter or legacy release declaration: {default_key[0]}@{default_key[1]}")
    for subprotocol in (default_release or {}).get("trusted_subprotocols") or []:
        if subprotocol.get("required") and not supports_subprotocol_release(
            base,
            str(subprotocol.get("id") or ""),
            str(subprotocol.get("version") or ""),
            default_key[0],
            default_key[1],
        ):
            errors.append(f"Base must support required trusted subprotocol {subprotocol.get('id')}@{subprotocol.get('version')} for {default_key[0]}@{default_key[1]}")

    _require_text(root / "src/core/protocol/capability_registry.py", "load_protocol_release_catalog", errors)
    _require_text(root / "src/core/lab/dev_flow.py", "self.default_protocol_version", errors)
    _require_text(root / "src/backend/main.py", "protocol_catalog", errors)
    _require_text(root / "src/frontend/src/pages/FlowWorkbench.tsx", "protocolCatalog", errors)
    _require_text(protocol_dir / "governance/GOVERNANCE.md", "release_manifest.json", errors)
    for document in [
        "AGENT.md",
        "protocol/README.md",
        "protocol/governance/GOVERNANCE.md",
    ]:
        _require_text(root / document, "release_manifest.json", errors)

    baseline_headers = {
        "protocol/governance/GOVERNANCE.md": "CF-FARP@1.1",
    }
    for document, marker in baseline_headers.items():
        header = "\n".join((root / document).read_text(encoding="utf-8").splitlines()[:24])
        if marker not in header:
            errors.append(f"{document} must present the v1.1 release baseline in its header")

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
