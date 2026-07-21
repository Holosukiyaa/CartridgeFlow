"""Machine-readable conformance reporting for the declared base surface."""

from .reporting import (
    RecordingTestResult,
    build_conformance_report,
    load_latest_report,
    write_conformance_report,
)

__all__ = [
    "RecordingTestResult",
    "build_conformance_report",
    "load_latest_report",
    "write_conformance_report",
]
