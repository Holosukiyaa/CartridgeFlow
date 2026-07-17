from __future__ import annotations


def summarize_findings(findings: list[dict]) -> dict:
    counts = {"blocker": 0, "warning": 0, "info": 0}
    for finding in findings:
        severity = finding.get("severity")
        if severity in counts:
            counts[severity] += 1
    return counts


def report_status(findings: list[dict]) -> str:
    counts = summarize_findings(findings)
    if counts["blocker"]:
        return "blocked"
    if counts["warning"]:
        return "compatible_with_warnings"
    return "compatible"
