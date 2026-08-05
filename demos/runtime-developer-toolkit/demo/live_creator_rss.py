"""Run a signed Creator package against a live RSS source through Base.

This is an acceptance harness, not a mock runtime. It materializes the same
Creator handoff artifact, imports it through the public API, runs it, verifies
delivery and data-chain evidence, and also proves the invalid-source path.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol.capability_cartridges import build_flow_capability_release, create_semantic_recipe
from core.studio.authoring_service import AuthoringSessionStore
from core.studio.capability_cartridges import CapabilityCartridgeStore
from core.studio.creator_runtime_bridge import CreatorRuntimeBridge


DEMO = ROOT / "demos" / "capabilities" / "rss-reader"
DEFAULT_FEED = "https://github.blog/feed/"
DEFAULT_REPORT = ROOT / ".data" / "reports" / "creator-live-closure.json"


class AcceptanceError(RuntimeError):
    pass


def _api(base_url: str, method: str, path: str, payload: dict | None = None) -> object:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AcceptanceError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise AcceptanceError(f"cannot reach CartridgeFlow at {base_url}: {exc}") from exc
    value = json.loads(raw or "{}")
    return value


def _rss_release() -> dict:
    manifest = json.loads((DEMO / "manifest.json").read_text(encoding="utf-8"))
    root_flow = json.loads((DEMO / "root.flow.json").read_text(encoding="utf-8"))
    source_files = {
        path.relative_to(DEMO).as_posix(): path.read_text(encoding="utf-8")
        for path in DEMO.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and path.name not in {"manifest.json", "root.flow.json", "README.md"}
    }
    return build_flow_capability_release(
        capability_id="workspace.rss-reader",
        revision=1,
        trust_scope="workspace",
        label="Read reviewed RSS sources",
        description="Fetch reviewed public RSS or Atom feeds and return normalized entries.",
        match_terms=["RSS", "Atom", "news source", "daily briefing"],
        editable_fields=[
            {
                "id": "feed_urls",
                "label": "Reviewed feed URLs",
                "value_type": "string_list",
                "required": True,
                "default": [DEFAULT_FEED],
            },
            {
                "id": "max_items",
                "label": "Maximum entries",
                "value_type": "number",
                "required": True,
                "default": 5,
            },
        ],
        creator_bindings={
            "feed_urls": "states.fetch.params.tools.0.params.urls",
            "max_items": "states.fetch.params.tools.0.params.max_items",
        },
        public_inputs=[],
        public_outputs=[
            {
                "id": "items",
                "label": "Normalized feed entries",
                "required": True,
                "schema": {"type": "array"},
                "store_key": "items",
            }
        ],
        dependencies=[],
        source_flow_id=manifest["id"],
        manifest=manifest,
        root_flow=root_flow,
        source_files=source_files,
        evidence={
            "status": "passed",
            "checks": [
                {"id": "flow_contract", "status": "passed"},
                {"id": "portable_dlc", "status": "passed"},
            ],
        },
    )


def _build_package(temp: Path, feed_url: str, case_id: str) -> tuple[Path, dict]:
    capability_store = CapabilityCartridgeStore(temp / case_id / "capabilities")
    release = capability_store.put(_rss_release(), expected_revision=0)
    recipe, publications = create_semantic_recipe(
        f"recipe.{case_id}",
        "Collect current developer news from a reviewed source",
        {
            "nodes": [
                {
                    "id": "sources",
                    "label": "Collect current developer news",
                    "description": "Read the latest entries from a source reviewed on the Creator canvas.",
                    "needed_capability": "RSS news source retrieval",
                    "capability_id": release["id"],
                    "values": {"feed_urls": [feed_url], "max_items": 5},
                }
            ],
            "relations": [],
        },
        capability_store.list_active(),
    )
    sessions = AuthoringSessionStore(temp / case_id / "sessions")
    session_id = f"creator.{case_id}"
    sessions.create_from_semantic_recipe(session_id, f"project.{case_id}", recipe, publications)
    sessions.freeze(session_id, ["sources"], author="acceptance-user", summary="Reviewed source on Creator canvas")
    packages = temp / case_id / "packages"
    handoff = CreatorRuntimeBridge(ROOT, packages, capability_store).package(
        sessions,
        session_id,
        expected_revision=1,
    )
    return packages / handoff["filename"], handoff


def _import_and_run(
    base_url: str,
    archive: Path,
    cleanup: list[tuple[str, str]],
) -> tuple[str, dict, dict, list[dict]]:
    imported = _api(
        base_url,
        "POST",
        "/api/cartridges/import",
        {
            "filename": archive.name,
            "content_base64": base64.b64encode(archive.read_bytes()).decode("ascii"),
            "install_mode": "replace",
        },
    )
    if not isinstance(imported, dict):
        raise AcceptanceError(f"package import returned a non-object response: {imported}")
    cartridge_id = str((imported.get("cartridge") or {}).get("id") or "")
    if not imported.get("ok") or not cartridge_id:
        raise AcceptanceError(f"package import did not activate a cartridge: {imported}")
    cleanup.append(("cartridge", cartridge_id))
    run = _api(base_url, "POST", "/api/cartridge-runs", {"cartridge_id": cartridge_id, "inputs": {}})
    if not isinstance(run, dict):
        raise AcceptanceError(f"runtime returned a non-object response: {run}")
    run_id = str(run.get("run_id") or "")
    if not run_id:
        raise AcceptanceError(f"runtime did not return a run id: {run}")
    cleanup.insert(len(cleanup) - 1, ("run", run_id))
    raw_events = _api(base_url, "GET", f"/api/cartridge-runs/{run_id}/events")
    events = raw_events if isinstance(raw_events, list) else raw_events.get("items", raw_events.get("events", [])) if isinstance(raw_events, dict) else []
    delivery = {}
    if run.get("status") == "completed":
        raw_delivery = _api(base_url, "GET", f"/api/cartridge-runs/{run_id}/delivery")
        delivery = raw_delivery if isinstance(raw_delivery, dict) else {}
    return cartridge_id, run, delivery, events if isinstance(events, list) else []


def _data_chain_passed(run: dict) -> bool:
    data_chain = run.get("data_chain") if isinstance(run.get("data_chain"), dict) else {}
    return data_chain.get("passed") is True or data_chain.get("status") in {"passed", "complete", "completed"}


def _run_acceptance(base_url: str, feed_url: str) -> dict:
    cleanup: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="creator-live-acceptance-") as directory:
        temp = Path(directory)
        try:
            happy_archive, happy_handoff = _build_package(temp, feed_url, "live-rss-happy")
            happy_id, happy_run, happy_delivery, happy_events = _import_and_run(base_url, happy_archive, cleanup)
            items = happy_delivery.get("result")
            if happy_run.get("status") != "completed":
                failed_events = [event for event in happy_events if isinstance(event, dict) and event.get("type") == "lab_node_failed"]
                node_events = [
                    {"type": event.get("type"), "state": event.get("state"), "data": event.get("data")}
                    for event in happy_events
                    if isinstance(event, dict) and str(event.get("type") or "").startswith("lab_node_")
                ]
                detail = {
                    "failure": (failed_events[-1].get("data") if failed_events else None) or happy_run.get("errors") or happy_run.get("error"),
                    "node_events": node_events[-4:],
                }
                raise AcceptanceError(f"live run did not complete: {detail}")
            if not _data_chain_passed(happy_run):
                raise AcceptanceError(f"live run data chain did not pass: {happy_run.get('data_chain')}")
            if happy_delivery.get("status") != "delivered":
                raise AcceptanceError(f"live run was not delivered: {happy_delivery}")
            if not isinstance(items, list) or not items:
                raise AcceptanceError(f"live run produced no normalized feed entries: {items}")
            if not all(isinstance(item, dict) and item.get("title") and item.get("url") for item in items):
                raise AcceptanceError("live run returned entries without title and URL")

            failure_archive, failure_handoff = _build_package(temp, "http://127.0.0.1/private-feed.xml", "live-rss-failure")
            failure_id, failure_run, _, failure_events = _import_and_run(base_url, failure_archive, cleanup)
            if failure_run.get("status") != "failed":
                raise AcceptanceError(f"invalid source did not fail closed: {failure_run.get('status')}")
            errors = failure_run.get("errors") or []
            if not errors:
                raise AcceptanceError("invalid source failed without a runtime error envelope")

            return {
                "schema": "cartridgeflow.creator_live_closure_report.v1",
                "status": "passed",
                "base_url": base_url,
                "live_source": feed_url,
                "creator_handoff": {
                    "status": happy_handoff["status"],
                    "release_id": happy_handoff["release_id"],
                    "signature_verified": happy_handoff["signature"]["verified"],
                },
                "runtime": {
                    "cartridge_id": happy_id,
                    "run_id": happy_run["run_id"],
                    "status": happy_run["status"],
                    "current_state": happy_run.get("current_state"),
                    "data_chain": happy_run.get("data_chain"),
                    "delivery_status": happy_delivery.get("status"),
                    "item_count": len(items),
                    "samples": [
                        {
                            "title": item.get("title"),
                            "url": item.get("url"),
                            "published_at": item.get("published_at"),
                        }
                        for item in items[:3]
                    ],
                    "event_count": len(happy_events),
                },
                "failure_path": {
                    "creator_release_id": failure_handoff["release_id"],
                    "cartridge_id": failure_id,
                    "run_id": failure_run["run_id"],
                    "status": failure_run["status"],
                    "error_count": len(errors),
                    "error_code": str((errors[0] or {}).get("code") or (errors[0] or {}).get("error_code") or ""),
                    "event_count": len(failure_events),
                },
            }
        finally:
            for kind, identity in cleanup:
                if not identity:
                    continue
                try:
                    path = f"/api/cartridge-runs/{identity}" if kind == "run" else f"/api/cartridges/{identity}/installed"
                    _api(base_url, "DELETE", path)
                except AcceptanceError:
                    pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--feed", default=DEFAULT_FEED)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = _run_acceptance(args.base_url, args.feed)
    report_path = args.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    pending = report_path.with_suffix(report_path.suffix + ".tmp")
    pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(report_path)
    print(json.dumps({**report, "report_path": str(report_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
