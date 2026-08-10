from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL_REPOSITORY = ROOT.parent / "cartridgeflow-protocols"
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import (
    ImplementationSource,
    ProtocolKnowledgeRegistry,
    ProtocolKnowledgeRegistryError,
    ProtocolSource,
    build_protocol_knowledge_registry,
)


_SEVERITY = {"none": 99, "blocker": 2, "warning": 1, "info": 0}


def _source(value: str) -> ProtocolSource:
    source_id, separator, path = value.partition("=")
    if not separator or not source_id or not path:
        raise argparse.ArgumentTypeError("source must use ID=PATH")
    try:
        return ProtocolSource(source_id, Path(path))
    except ProtocolKnowledgeRegistryError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _implementation_source(value: str) -> ImplementationSource:
    source_id, separator, path = value.partition("=")
    if not separator or not source_id or not path:
        raise argparse.ArgumentTypeError("implementation source must use ID=PATH")
    try:
        return ImplementationSource(source_id, Path(path))
    except ProtocolKnowledgeRegistryError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile one or more Git-backed protocol trees into a read-only SQLite governance registry."
    )
    parser.add_argument(
        "--source",
        action="append",
        type=_source,
        help="Product-line source in ID=PATH form. Repeat to build a federated registry.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".data" / "protocol" / "protocol-registry.sqlite",
    )
    parser.add_argument(
        "--implementation-source",
        action="append",
        type=_implementation_source,
        help="Product implementation and evidence source in ID=PATH form.",
    )
    parser.add_argument(
        "--lock-dir",
        type=Path,
        default=ROOT / ".data" / "protocol" / "locks",
        help="Directory for deterministic per-line protocol lock files.",
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "blocker", "warning", "info"),
        default="none",
        help="Return a non-zero status when findings at this severity or higher exist.",
    )
    args = parser.parse_args()
    sources = args.source or [
        ProtocolSource("current", DEFAULT_PROTOCOL_REPOSITORY / "sources" / "current"),
        ProtocolSource(
            "temp-runtime", DEFAULT_PROTOCOL_REPOSITORY / "sources" / "temp-runtime"
        ),
    ]
    implementation_sources = args.implementation_source
    if implementation_sources is None and args.source is None:
        implementation_sources = [ImplementationSource("current", ROOT)]
    try:
        report = build_protocol_knowledge_registry(
            args.output,
            sources,
            implementation_sources=implementation_sources or [],
            lock_dir=args.lock_dir,
        )
    except (OSError, ProtocolKnowledgeRegistryError) as exc:
        print(f"Protocol registry build failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Protocol registry: {report.output_path}\n"
        f"Digest: {report.registry_digest}\n"
        f"Sources: {report.source_count}; releases: {report.release_count}; "
        f"artifacts: {report.artifact_count}; sections: {report.section_count}"
    )
    with ProtocolKnowledgeRegistry(report.output_path) as registry:
        findings = registry.findings()
    if findings:
        print("Governance findings:")
        for finding in findings:
            identity = ""
            if finding.get("protocol_id") and finding.get("version"):
                identity = f" {finding['protocol_id']}@{finding['version']}"
            print(f"- [{finding['severity']}] {finding['finding_type']}{identity}: {finding['message']}")
    else:
        print("Governance findings: none")
    for path in report.lock_paths:
        print(f"Protocol lock: {path}")

    threshold = _SEVERITY[args.fail_on]
    return int(
        threshold != _SEVERITY["none"]
        and any(_SEVERITY.get(item["severity"], 0) >= threshold for item in findings)
    )


if __name__ == "__main__":
    raise SystemExit(main())
