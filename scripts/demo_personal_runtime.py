"""Run a CF-CRE candidate in an isolated personal-runtime demonstration host.

This is an executable integration demo, not the CF-CRE production installer.
It deliberately has no signature trust store, marketplace, rollback, or
resource-binding wizard.  It proves the boundary from a release ZIP to an
independent local run without starting the development-console API.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core.cartridge.registry import CartridgeRegistry
from core.cartridge.runner import CartridgeRunner
from core.protocol import inspect_release_archive


class PersonalRuntimeDemoError(ValueError):
    """Raised when a release cannot enter the isolated demo host."""


def run_personal_runtime_demo(
    archive_file: str | Path,
    host_root: str | Path,
    *,
    inputs: dict,
) -> dict:
    """Install one validated candidate into an isolated host and execute it."""
    archive = Path(archive_file).resolve()
    host = Path(host_root).resolve()
    inspection = inspect_release_archive(archive)
    if inspection["status"] != "validated_pending_install" or not inspection["report"]["ok"]:
        raise PersonalRuntimeDemoError("CF-CRE candidate did not pass static archive validation")

    release = inspection["release"]
    identity = release["release"]
    publisher_id = _safe_identifier(identity["publisher_id"], "publisher_id")
    cartridge_id = _safe_identifier(identity["cartridge_id"], "cartridge_id")
    version = _safe_identifier(identity["version"], "version")
    digest = _safe_identifier(release["integrity"]["content_digest"].removeprefix("sha256:"), "content digest")
    immutable_package = host / "installed" / publisher_id / cartridge_id / version / digest / "payload"
    active_package = host / ".data" / "user" / "installed_cartridges" / cartridge_id

    _provision_host_contract(host)
    _extract_payload(archive, immutable_package)
    _activate_demo_package(immutable_package, active_package, release["release_id"])
    _write_json(
        host / "active" / publisher_id / f"{cartridge_id}.json",
        {
            "schema": "cartridgeflow.personal_runtime_demo.active_release.v1",
            "release_id": release["release_id"],
            "package": str(active_package.relative_to(host)).replace("\\", "/"),
            "status": "demo_active",
        },
    )

    registry = CartridgeRegistry(host)
    cartridge = registry.get_cartridge(cartridge_id)
    if cartridge.get("source") != "installed":
        raise PersonalRuntimeDemoError("demo host did not load the installed release payload")
    runner = CartridgeRunner(host, registry)
    run = runner.create_run(cartridge_id, inputs=inputs)
    artifacts = run.get("artifacts") or []
    if run.get("status") != "completed" or not artifacts:
        raise PersonalRuntimeDemoError("demo runtime did not produce a completed run with an artifact")
    return {
        "ok": True,
        "host_root": str(host),
        "release_id": release["release_id"],
        "installed_version": str(immutable_package.relative_to(host)).replace("\\", "/"),
        "active_release": str((host / "active" / publisher_id / f"{cartridge_id}.json").relative_to(host)).replace("\\", "/"),
        "run_id": run["run_id"],
        "status": run["status"],
        "artifacts": artifacts,
        "boundary": "demo only: no signature verification, rollback, marketplace, or external-resource binding",
    }


def _provision_host_contract(host: Path) -> None:
    """Copy only the base and compiled protocol snapshots required by the host."""
    for relative in (Path("config") / "base", Path("config") / "protocol"):
        source = PROJECT_ROOT / relative
        target = host / relative
        if target.exists():
            continue
        shutil.copytree(source, target)


def _extract_payload(archive: Path, destination: Path) -> None:
    if destination.exists():
        return
    staging = destination.with_name(f"{destination.name}.staging")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir() or not info.filename.startswith("payload/"):
                    continue
                relative = info.filename.removeprefix("payload/")
                if not _safe_relative_path(relative):
                    raise PersonalRuntimeDemoError("release payload contains an unsafe path")
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        if not (staging / "manifest.json").is_file() or not (staging / "root.flow.json").is_file():
            raise PersonalRuntimeDemoError("release payload is missing a runnable cartridge entry")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _activate_demo_package(immutable_package: Path, active_package: Path, release_id: str) -> None:
    marker = active_package / ".personal-runtime-demo-release.json"
    if active_package.exists():
        current = _read_json(marker)
        if current.get("release_id") != release_id:
            raise PersonalRuntimeDemoError("demo host already has another active release for this cartridge")
        return
    active_package.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(immutable_package, active_package)
    _write_json(marker, {"release_id": release_id})


def _safe_identifier(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for char in text):
        raise PersonalRuntimeDemoError(f"release {label} is not safe for a local path")
    return text


def _safe_relative_path(path: str) -> bool:
    candidate = PurePosixPath(path)
    return bool(path and not candidate.is_absolute() and ".." not in candidate.parts and "\\" not in path)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one CF-CRE candidate in an isolated personal-runtime demo host.")
    parser.add_argument("--archive", required=True, help="CF-CRE candidate ZIP")
    parser.add_argument("--host-root", required=True, help="empty or previously initialized demo host directory")
    parser.add_argument("--title", default="每日摘要", help="demo artifact title")
    parser.add_argument("--description", default="由独立个人运行台生成的本地交付。", help="demo artifact description")
    args = parser.parse_args()
    result = run_personal_runtime_demo(args.archive, args.host_root, inputs={"title": args.title, "description": args.description})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
