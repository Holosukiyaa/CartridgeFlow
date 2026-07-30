"""Pure, deterministic compiler for the CF-FARP@1.0 ExecutionPlan contract.

This module deliberately compiles only static authoring facts.  It does not
instantiate node handlers, resolve value references, inspect resources, or read
and write run state.  Those are token-runner responsibilities.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from core.protocol.flow_contract import validate_v10_flow_contract


COMPILED_PLAN_SCHEMA = "cartridgeflow.execution_plan.compiled.v1"
COMPILER_ID = "cartridgeflow.execution-plan-compiler"
COMPILER_VERSION = "1.0.0"
_PRESENTATION_FIELDS = {"annotations", "layout"}
_SIDE_EFFECT_EFFECTS = {
    "writes_artifacts",
    "writes_files",
    "mutates_state",
    "external_side_effect",
}


class ExecutionPlanCompileError(ValueError):
    """A stable, machine-readable rejection of ExecutionPlan authoring facts."""

    def __init__(self, code: str, message: str, findings: list[dict[str, Any]] | None = None):
        self.code = code
        self.findings = tuple(dict(item) for item in findings or [])
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "cartridgeflow.execution_plan.compile_error.v1",
            "code": self.code,
            "message": str(self),
            "findings": [dict(item) for item in self.findings],
        }


def compile_execution_plan(root_flow: dict | None) -> dict[str, Any]:
    """Compile validated CF-FARP@1.0 authoring facts into a token-runner input shape.

    The source object is only read.  Contract findings are sorted before being
    exposed so callers receive an identical machine-readable error for an
    identical invalid source.
    """
    findings = _stable_findings(validate_v10_flow_contract(root_flow))
    if findings:
        codes = ", ".join(sorted({item["code"] for item in findings}))
        raise ExecutionPlanCompileError(
            "execution_plan_contract_invalid",
            f"CF-FARP@1.0 authoring facts are invalid: {codes}.",
            findings,
        )

    source = root_flow if isinstance(root_flow, dict) else {}
    source_digest = build_execution_plan_source_digest(source)
    states = source["states"]
    author_plan = source["execution_plan"]
    edges = sorted((_compile_edge(edge) for edge in author_plan["edges"]), key=lambda edge: edge["id"])
    nodes = [_compile_node(node_id, states[node_id], str(author_plan["entry"])) for node_id in sorted(states)]

    plan = {
        "schema": COMPILED_PLAN_SCHEMA,
        "compiler": {"id": COMPILER_ID, "version": COMPILER_VERSION},
        "protocol": {"id": "CF-FARP", "version": "1.0"},
        "plan_id": f"execution-plan:{source_digest.removeprefix('sha256:')[:24]}",
        "source_digest": source_digest,
        "entry": str(author_plan["entry"]).strip(),
        "nodes": nodes,
        "edges": edges,
        "schedule": _compile_schedule(nodes, edges),
    }
    plan["plan_digest"] = _digest(plan)
    return plan


def build_execution_plan_source_digest(root_flow: dict | None) -> str:
    """Return the canonical digest for ExecutionPlan authoring facts.

    Presentation-only layout and annotation fields are intentionally excluded,
    matching the existing analyzer's source-digest boundary.  The compiler does
    not interpret any node input/output/store fields while producing this hash.
    """
    author_facts = _without_presentation(root_flow if isinstance(root_flow, dict) else {})
    execution_plan = author_facts.get("execution_plan")
    if isinstance(execution_plan, dict):
        edges = execution_plan.get("edges")
        if isinstance(edges, list):
            execution_plan["edges"] = sorted(
                (_canonicalize_edge_author_fact(edge) for edge in edges),
                key=_canonical_json,
            )
    try:
        return _digest(author_facts)
    except (TypeError, ValueError) as error:
        raise ExecutionPlanCompileError(
            "execution_plan_source_not_serializable",
            "CF-FARP@1.0 authoring facts must be JSON serializable.",
        ) from error


def _compile_node(node_id: str, node: dict[str, Any], entry: str) -> dict[str, Any]:
    return {
        "id": str(node_id),
        "type": _string(node.get("type")),
        "entry": str(node_id) == entry,
        "may_fail": _node_may_fail(node),
    }


def _compile_edge(edge: dict[str, Any]) -> dict[str, Any]:
    kind = _string(edge.get("kind"))
    compiled = {
        "id": _string(edge.get("id")),
        "kind": kind,
        "from": _string(edge.get("from")),
        "to": _string(edge.get("to")),
    }
    if kind == "fork":
        fork = _mapping(edge.get("fork"))
        compiled["fork"] = {"id": _string(fork.get("id")), "branch": _string(fork.get("branch"))}
    elif kind == "join":
        join = _mapping(edge.get("join"))
        compiled_join = {
            "id": _string(join.get("id")),
            "mode": _string(join.get("mode")),
            "branch": _string(join.get("branch")),
            "branches": sorted(_strings(join.get("branches"))),
        }
        if compiled_join["mode"] == "any":
            compiled_join["remaining"] = _string(join.get("remaining"))
        if compiled_join["mode"] == "keyed":
            compiled_join["key_ref"] = _string(join.get("key_ref"))
        compiled["join"] = compiled_join
    elif kind == "loop":
        loop = _mapping(edge.get("loop"))
        compiled["loop"] = {
            "id": _string(loop.get("id")),
            "max_iterations": loop.get("max_iterations"),
            "continue_when": _string(loop.get("continue_when")),
            "exit_to": _string(loop.get("exit_to")),
        }
    elif kind == "batch":
        batch = _mapping(edge.get("batch"))
        compiled["batch"] = {
            "id": _string(batch.get("id")),
            "items_ref": _string(batch.get("items_ref")),
            "size": batch.get("size"),
            "max_concurrency": batch.get("max_concurrency"),
            "ordering": _string(batch.get("ordering")),
        }
    elif kind == "wait":
        wait = _mapping(edge.get("wait"))
        compiled_wait = {
            "id": _string(wait.get("id")),
            "mode": _string(wait.get("mode")),
            "timeout_ms": wait.get("timeout_ms"),
            "resume_key": _string(wait.get("resume_key")),
        }
        if compiled_wait["mode"] == "duration":
            compiled_wait["duration_ms"] = wait.get("duration_ms")
        elif compiled_wait["mode"] == "signal":
            compiled_wait["signal"] = _string(wait.get("signal"))
        elif compiled_wait["mode"] == "condition":
            compiled_wait["condition_ref"] = _string(wait.get("condition_ref"))
        compiled["wait"] = compiled_wait
    elif kind == "failure":
        failure = _mapping(edge.get("failure"))
        compiled["failure"] = {
            "id": _string(failure.get("id")),
            "causes": sorted(_strings(failure.get("causes"))),
        }
    return compiled


def _compile_schedule(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    successful_by_source: dict[str, list[str]] = defaultdict(list)
    failures_by_source: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        destination = failures_by_source if edge["kind"] == "failure" else successful_by_source
        destination[edge["from"]].append(edge["id"])

    failure_edges = [edge for edge in edges if edge["kind"] == "failure"]
    schedule = {
        "node_transitions": [
            {
                "node_id": node["id"],
                "success_edge_ids": sorted(successful_by_source.get(node["id"], [])),
                "failure_edge_ids": sorted(failures_by_source.get(node["id"], [])),
            }
            for node in nodes
        ],
        "forks": _compile_forks(edges),
        "joins": _compile_joins(edges),
        "loops": [_edge_schedule(edge) for edge in edges if edge["kind"] == "loop"],
        "batches": [_edge_schedule(edge) for edge in edges if edge["kind"] == "batch"],
        "waits": _compile_waits(edges, failure_edges),
        "failures": [_edge_schedule(edge) for edge in failure_edges],
    }
    return schedule


def _compile_forks(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge["kind"] == "fork":
            groups[edge["fork"]["id"]].append(edge)
    return [
        {
            "id": fork_id,
            "from": group[0]["from"],
            "branches": [
                {"branch": edge["fork"]["branch"], "edge_id": edge["id"], "to": edge["to"]}
                for edge in sorted(group, key=lambda item: (item["fork"]["branch"], item["id"]))
            ],
        }
        for fork_id, group in sorted(groups.items())
    ]


def _compile_joins(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge["kind"] == "join":
            groups[edge["join"]["id"]].append(edge)
    joins: list[dict[str, Any]] = []
    for join_id, group in sorted(groups.items()):
        exemplar = group[0]
        join = exemplar["join"]
        item = {
            "id": join_id,
            "mode": join["mode"],
            "to": exemplar["to"],
            "branches": list(join["branches"]),
            "incoming": [
                {"branch": edge["join"]["branch"], "edge_id": edge["id"], "from": edge["from"]}
                for edge in sorted(group, key=lambda edge: (edge["join"]["branch"], edge["id"]))
            ],
        }
        if join["mode"] == "any":
            item["remaining"] = join["remaining"]
        if join["mode"] == "keyed":
            item["key_ref"] = join["key_ref"]
        joins.append(item)
    return joins


def _compile_waits(edges: list[dict[str, Any]], failure_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    waits = []
    for edge in edges:
        if edge["kind"] != "wait":
            continue
        timeouts = [
            failure["id"]
            for failure in failure_edges
            if failure["from"] == edge["from"] and "timeout" in failure["failure"]["causes"]
        ]
        item = _edge_schedule(edge)
        item["timeout_failure_edge_ids"] = sorted(timeouts)
        waits.append(item)
    return waits


def _edge_schedule(edge: dict[str, Any]) -> dict[str, Any]:
    item = {"edge_id": edge["id"], "from": edge["from"], "to": edge["to"], "kind": edge["kind"]}
    if edge["kind"] in {"loop", "batch", "wait", "failure"}:
        item[edge["kind"]] = dict(edge[edge["kind"]])
    return item


def _node_may_fail(node: dict[str, Any]) -> bool:
    execution = _mapping(node.get("execution"))
    if execution.get("may_fail") is True:
        return True
    if _string(node.get("type")) in {"action", "process"}:
        return True
    return _contract_effect(node) in _SIDE_EFFECT_EFFECTS


def _contract_effect(node: dict[str, Any]) -> str:
    if "effect" in node:
        return _string(node.get("effect"))
    params = _mapping(node.get("params"))
    protocol = _mapping(params.get("protocol"))
    preset_config = _mapping(params.get("preset_config"))
    for facts in (protocol, params, preset_config):
        if "effect" in facts:
            return _string(facts.get("effect"))
    return ""


def _without_presentation(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_presentation(item)
            for key, item in value.items()
            if key not in _PRESENTATION_FIELDS
        }
    if isinstance(value, list):
        return [_without_presentation(item) for item in value]
    return value


def _canonicalize_edge_author_fact(edge: Any) -> Any:
    if not isinstance(edge, dict):
        return edge
    normalized = dict(edge)
    join = normalized.get("join")
    if isinstance(join, dict) and isinstance(join.get("branches"), list):
        normalized["join"] = {**join, "branches": sorted(join["branches"], key=_canonical_json)}
    failure = normalized.get("failure")
    if isinstance(failure, dict) and isinstance(failure.get("causes"), list):
        normalized["failure"] = {**failure, "causes": sorted(failure["causes"], key=_canonical_json)}
    return normalized


def _stable_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(finding) for finding in sorted(findings, key=_canonical_json)]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> list[str]:
    return [_string(item) for item in value] if isinstance(value, list) else []


def _string(value: Any) -> str:
    return str(value or "").strip()


def _digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
