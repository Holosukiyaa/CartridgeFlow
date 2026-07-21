"""Generate evidence-linked reports from an actual unittest run."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.data_paths import CONFORMANCE_REPORT


REPORT_SCHEMA = "cartridgeflow.conformance_report.v1"
EVIDENCE_SCHEMA = "cartridgeflow.capability_evidence.v1"
DEFAULT_BASE_IMPLEMENTATION_PATH = Path("config/base/BASE_IMPLEMENTATION.json")
DEFAULT_EVIDENCE_PATH = Path("config/base/capability_evidence.json")
DEFAULT_REPORT_PATH = CONFORMANCE_REPORT


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class RecordingTestResult(unittest.TextTestResult):
    """Text result that also retains stable case IDs and durations."""

    def startTestRun(self):
        super().startTestRun()
        self.run_started_at = utc_now()
        self._case_started: dict[str, float] = {}
        self.case_results: list[dict] = []

    def startTest(self, test):
        self._case_started[test.id()] = time.perf_counter()
        super().startTest(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "passed")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "failed", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "skipped", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record(test, "expected_failure", self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, "unexpected_success")

    def _record(self, test, status: str, detail: str = "") -> None:
        case_id = test.id()
        started = self._case_started.pop(case_id, time.perf_counter())
        self.case_results.append({
            "id": case_id,
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            **({"detail": str(detail)[-12000:]} if detail else {}),
        })


def build_conformance_report(
    root: str | Path,
    cases: list[dict],
    *,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> dict:
    base_root = Path(root)
    base_path = base_root / DEFAULT_BASE_IMPLEMENTATION_PATH
    evidence_path = base_root / DEFAULT_EVIDENCE_PATH
    base = _read_json(base_path)
    evidence = _read_json(evidence_path)
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError(f"Unsupported capability evidence schema: {evidence.get('schema')}")

    declared = [str(item) for item in base.get("capabilities") or []]
    mappings = evidence.get("capabilities") if isinstance(evidence.get("capabilities"), dict) else {}
    evidence_sets = evidence.get("evidence_sets") if isinstance(evidence.get("evidence_sets"), dict) else {}
    case_index = {str(item.get("id")): item for item in cases if item.get("id")}
    capability_items = []
    for capability in declared:
        set_id = str(mappings.get(capability) or "")
        record = evidence_sets.get(set_id) if set_id else None
        capability_items.append(_capability_result(base_root, capability, set_id, record, case_index))

    undeclared_evidence = sorted(set(mappings) - set(declared))
    counts = {"verified": 0, "partial": 0, "unverified": 0, "failing": 0}
    for item in capability_items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1

    case_counts: dict[str, int] = {}
    duration_ms = 0.0
    for case in cases:
        status = str(case.get("status") or "unknown")
        case_counts[status] = case_counts.get(status, 0) + 1
        duration_ms += float(case.get("duration_ms") or 0)
    failed_count = sum(case_counts.get(name, 0) for name in ("failed", "error", "unexpected_success"))
    finished = finished_at or utc_now()
    report = {
        "schema": REPORT_SCHEMA,
        "generated_at": finished,
        "implementation": {
            "id": base.get("implementation_id"),
            "version": base.get("implementation_version"),
            "base_manifest_sha256": _sha256(base_path),
            "evidence_sha256": _sha256(evidence_path),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "executable": str(Path(sys.executable).resolve()),
        },
        "run": {
            "started_at": started_at or finished,
            "finished_at": finished,
            "duration_ms": round(duration_ms, 3),
            "command": ".tools/runtimes/python/python.exe scripts/run_conformance.py",
        },
        "tests": {
            "status": "failed" if failed_count else "passed",
            "total": len(cases),
            "counts": case_counts,
            "cases": sorted(cases, key=lambda item: str(item.get("id") or "")),
        },
        "capabilities": {
            "status": "failing" if counts["failing"] else "partial" if counts["partial"] or counts["unverified"] else "verified",
            "declared": len(declared),
            "counts": counts,
            "items": capability_items,
            "configuration_errors": [
                *([f"Evidence references undeclared capability: {item}" for item in undeclared_evidence]),
                *([f"Declared capability has no evidence mapping: {item['id']}" for item in capability_items if not item.get("evidence_set")]),
            ],
        },
    }
    report["status"] = "failed" if failed_count or counts["failing"] else "partial" if report["capabilities"]["status"] != "verified" else "passed"
    return report


def write_conformance_report(root: str | Path, report: dict, output: str | Path | None = None) -> Path:
    base_root = Path(root)
    target = Path(output) if output else base_root / DEFAULT_REPORT_PATH
    if not target.is_absolute():
        target = base_root / target
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)
    return target


def load_latest_report(root: str | Path, path: str | Path | None = None) -> dict | None:
    base_root = Path(root)
    target = Path(path) if path else base_root / DEFAULT_REPORT_PATH
    if not target.is_absolute():
        target = base_root / target
    if not target.is_file():
        return None
    try:
        report = _read_json(target)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return report if report.get("schema") == REPORT_SCHEMA else None


def _capability_result(root: Path, capability: str, set_id: str, record, cases: dict[str, dict]) -> dict:
    if not isinstance(record, dict):
        return {
            "id": capability,
            "evidence_set": set_id or None,
            "status": "unverified",
            "verification": "unmapped",
            "gaps": ["No capability evidence record."],
            "implementation": [],
            "positive_tests": [],
            "failure_tests": [],
            "ui": {"status": "unknown", "entries": []},
        }
    implementation = _path_evidence(root, record.get("implementation") or [])
    ui = record.get("ui") if isinstance(record.get("ui"), dict) else {"status": "unknown", "entries": []}
    ui_entries = _path_evidence(root, ui.get("entries") or [])
    positive = _test_evidence(record.get("positive_tests") or [], cases)
    negative = _test_evidence(record.get("failure_tests") or [], cases)
    gaps = []
    if not implementation:
        gaps.append("Implementation entry is missing.")
    elif any(not item["exists"] for item in implementation):
        gaps.append("One or more implementation entries do not exist.")
    if not positive:
        gaps.append("Positive test evidence is missing.")
    if not negative:
        gaps.append("Failure-path test evidence is missing.")
    if str(ui.get("status") or "unknown") != "not_applicable" and not ui_entries:
        gaps.append("UI visibility is not mapped.")
    elif any(not item["exists"] for item in ui_entries):
        gaps.append("One or more UI entries do not exist.")
    tests = positive + negative
    failing = any(item["status"] in {"failed", "error", "unexpected_success"} for item in tests)
    missing_tests = any(item["status"] in {"missing", "skipped"} for item in tests)
    verification = str(record.get("verification") or "unverified")
    if failing:
        status = "failing"
    elif verification == "verified" and not gaps and not missing_tests:
        status = "verified"
    elif implementation or positive:
        status = "partial"
    else:
        status = "unverified"
    return {
        "id": capability,
        "evidence_set": set_id,
        "status": status,
        "verification": verification,
        "notes": str(record.get("notes") or ""),
        "gaps": gaps,
        "implementation": implementation,
        "positive_tests": positive,
        "failure_tests": negative,
        "ui": {"status": str(ui.get("status") or "unknown"), "entries": ui_entries},
    }


def _path_evidence(root: Path, entries) -> list[dict]:
    result = []
    for entry in entries if isinstance(entries, list) else []:
        reference = str(entry or "").strip()
        if not reference:
            continue
        path_text = reference.split("#", 1)[0]
        result.append({"ref": reference, "exists": (root / path_text).is_file()})
    return result


def _test_evidence(selectors, cases: dict[str, dict]) -> list[dict]:
    result = []
    for selector in selectors if isinstance(selectors, list) else []:
        selector = str(selector or "").strip()
        if not selector:
            continue
        matches = [item for case_id, item in cases.items() if case_id == selector or case_id.endswith(selector)]
        if not matches:
            result.append({"id": selector, "status": "missing"})
        else:
            result.extend({"id": item["id"], "status": item.get("status"), "duration_ms": item.get("duration_ms", 0)} for item in matches)
    return result


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
