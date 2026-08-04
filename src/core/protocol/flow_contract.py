from __future__ import annotations

import re

from .decision_envelope import RESUME_POLICIES
from .report import report_status, summarize_findings


PROCESS_KINDS = {
    "input",
    "transfer",
    "retrieval",
    "decision",
    "transform",
    "validation",
    "routing",
    "mcp_read",
    "mcp_execute",
    "remote_call",
    "gate",
    "ui",
    "human_gate",
    "interaction",
    "delivery",
}

EXECUTORS = {
    "user",
    "deterministic",
    "rules",
    "rag",
    "llm",
    "mcp",
    "remote",
    "human",
    "plugin",
}

EFFECTS = {
    "none",
    "read_only",
    "writes_store",
    "writes_artifacts",
    "writes_files",
    "mutates_state",
    "external_side_effect",
}

SIDE_EFFECT_EFFECTS = {
    "writes_artifacts",
    "writes_files",
    "mutates_state",
    "external_side_effect",
}

LIFECYCLE_TYPES = {"system", "terminal"}
READ_ONLY_TOOL_SIDE_EFFECTS = {"", "none", "read_only", "environment_probe"}
EXECUTION_PLAN_V1_ADAPTER = "cf-farp.execution-plan.v1"
TRUSTED_NODE_MAPPING_V1_ADAPTER = "cf-farp.trusted-node-mapping.v1"
STANDARD_FLOW_V06_ADAPTER = "cf-farp.standard-flow.v06"
STANDARD_FLOW_V07_ADAPTER = "cf-farp.standard-flow.v07"
TYPED_CONTROL_V08_ADAPTER = "cf-farp.typed-control.v08"
TYPED_CONTROL_V09_ADAPTER = "cf-farp.typed-control.v09"


def build_v02_flow_contract_report(root_flow: dict | None, manifest: dict | None = None) -> dict:
    findings = validate_v02_flow_contract(root_flow, manifest)
    counts = summarize_findings(findings)
    return {
        "ok": counts["blocker"] == 0,
        "status": report_status(findings),
        "protocol": "CF-FARP@0.2",
        "summary": counts,
        "findings": findings,
    }


def build_v03_flow_contract_report(root_flow: dict | None, manifest: dict | None = None) -> dict:
    findings = validate_v03_flow_contract(root_flow, manifest)
    counts = summarize_findings(findings)
    return {
        "ok": counts["blocker"] == 0,
        "status": report_status(findings),
        "protocol": "CF-FARP@0.3",
        "summary": counts,
        "findings": findings,
    }


def build_v04_flow_contract_report(root_flow: dict | None, manifest: dict | None = None) -> dict:
    findings = validate_v04_flow_contract(root_flow, manifest)
    counts = summarize_findings(findings)
    return {
        "ok": counts["blocker"] == 0,
        "status": report_status(findings),
        "protocol": "CF-FARP@0.4",
        "summary": counts,
        "findings": findings,
    }


def build_v05_flow_contract_report(root_flow: dict | None, manifest: dict | None = None) -> dict:
    findings = validate_v05_flow_contract(root_flow, manifest)
    counts = summarize_findings(findings)
    return {
        "ok": counts["blocker"] == 0,
        "status": report_status(findings),
        "protocol": "CF-FARP@0.5",
        "summary": counts,
        "findings": findings,
    }


def build_v06_flow_contract_report(root_flow: dict | None, manifest: dict | None = None) -> dict:
    findings = validate_v06_flow_contract(root_flow, manifest)
    counts = summarize_findings(findings)
    return {
        "ok": counts["blocker"] == 0,
        "status": report_status(findings),
        "protocol": "CF-FARP@0.6",
        "summary": counts,
        "findings": findings,
    }


def build_v07_flow_contract_report(root_flow: dict | None, manifest: dict | None = None) -> dict:
    findings = validate_v07_flow_contract(root_flow, manifest)
    counts = summarize_findings(findings)
    return {
        "ok": counts["blocker"] == 0,
        "status": report_status(findings),
        "protocol": "CF-FARP@0.7",
        "summary": counts,
        "findings": findings,
    }


def build_v08_flow_contract_report(
    root_flow: dict | None,
    manifest: dict | None = None,
    *,
    target: str = "dev",
    base: dict | None = None,
) -> dict:
    from core.lab.flow_analyzer import analyze_flow

    analysis = analyze_flow(root_flow, manifest, target=target, base=base)
    return {
        "ok": (analysis.get("summary") or {}).get("blockers", 0) == 0,
        "status": "compatible" if (analysis.get("summary") or {}).get("blockers", 0) == 0 else "blocked",
        "protocol": "CF-FARP@0.8",
        "summary": {
            "blocker": (analysis.get("summary") or {}).get("blockers", 0),
            "warning": (analysis.get("summary") or {}).get("warnings", 0),
            "info": (analysis.get("summary") or {}).get("infos", 0),
        },
        "findings": analysis.get("findings") or [],
        "analysis": analysis,
    }


def build_v09_flow_contract_report(
    root_flow: dict | None,
    manifest: dict | None = None,
    *,
    target: str = "dev",
    base: dict | None = None,
) -> dict:
    from core.lab.flow_analyzer import analyze_flow

    analysis = analyze_flow(root_flow, manifest, target=target, base=base)
    return {
        "ok": (analysis.get("summary") or {}).get("blockers", 0) == 0,
        "status": "compatible" if (analysis.get("summary") or {}).get("blockers", 0) == 0 else "blocked",
        "protocol": "CF-FARP@0.9",
        "summary": {
            "blocker": (analysis.get("summary") or {}).get("blockers", 0),
            "warning": (analysis.get("summary") or {}).get("warnings", 0),
            "info": (analysis.get("summary") or {}).get("infos", 0),
        },
        "findings": analysis.get("findings") or [],
        "analysis": analysis,
    }


def build_v10_flow_contract_report(root_flow: dict | None, manifest: dict | None = None) -> dict:
    """验证可执行的 CF-FARP@1.0 编排契约。"""
    return build_flow_contract_report_for_adapter(
        EXECUTION_PLAN_V1_ADAPTER,
        root_flow,
        manifest,
        protocol_id="CF-FARP",
        protocol_version="1.0",
    ) or {}


def build_flow_contract_report_for_adapter(
    runtime_adapter: str | None,
    root_flow: dict | None,
    manifest: dict | None = None,
    *,
    protocol_id: str,
    protocol_version: str,
    target: str = "dev",
    base: dict | None = None,
) -> dict | None:
    """Build a contract report for an implementation adapter, not a release number.

    A release can keep this adapter when its documentation-only revision changes.
    A new runtime semantic contract receives a new adapter id and handler here.
    """
    legacy_builders = {
        STANDARD_FLOW_V06_ADAPTER: lambda: build_v06_flow_contract_report(root_flow, manifest),
        STANDARD_FLOW_V07_ADAPTER: lambda: build_v07_flow_contract_report(root_flow, manifest),
        TYPED_CONTROL_V08_ADAPTER: lambda: build_v08_flow_contract_report(root_flow, manifest, target=target, base=base),
        TYPED_CONTROL_V09_ADAPTER: lambda: build_v09_flow_contract_report(root_flow, manifest, target=target, base=base),
    }
    if runtime_adapter in legacy_builders:
        return legacy_builders[runtime_adapter]()
    if runtime_adapter not in {EXECUTION_PLAN_V1_ADAPTER, TRUSTED_NODE_MAPPING_V1_ADAPTER}:
        return None
    findings = validate_execution_plan_v1_flow_contract(
        root_flow,
        manifest,
        protocol_id=protocol_id,
        protocol_version=protocol_version,
    )
    counts = summarize_findings(findings)
    return {
        "ok": counts["blocker"] == 0,
        "status": "compatible" if counts["blocker"] == 0 else "blocked",
        "protocol": f"{protocol_id}@{protocol_version}",
        "runtime_adapter": runtime_adapter,
        "implementation_status": "supported",
        "summary": counts,
        "findings": findings,
    }


def validate_v08_flow_contract(root_flow: dict | None, manifest: dict | None = None) -> list[dict]:
    return build_v08_flow_contract_report(root_flow, manifest).get("findings") or []


def validate_v09_flow_contract(root_flow: dict | None, manifest: dict | None = None) -> list[dict]:
    return build_v09_flow_contract_report(root_flow, manifest).get("findings") or []


def validate_v10_flow_contract(root_flow: dict | None, manifest: dict | None = None) -> list[dict]:
    return validate_execution_plan_v1_flow_contract(
        root_flow,
        manifest,
        protocol_id="CF-FARP",
        protocol_version="1.0",
    )


def validate_execution_plan_v1_flow_contract(
    root_flow: dict | None,
    manifest: dict | None = None,
    *,
    protocol_id: str = "CF-FARP",
    protocol_version: str = "1.0",
) -> list[dict]:
    """Validate execution-plan-v1 authoring facts for a catalogued release.

    它只验证作者声明本身，不执行节点业务代码。编译器、运行器、分析器和
    认证层都必须消费同一份已验证的执行计划。
    """
    del manifest
    findings: list[dict] = []
    root_flow = root_flow if isinstance(root_flow, dict) else {}

    if not _root_flow_declares_protocol(root_flow, protocol_id, protocol_version):
        findings.append(_finding(
            "blocker",
            "v10_root_flow_protocol_missing",
            f"root flow must declare protocol {protocol_id}@{protocol_version}.",
        ))

    states = root_flow.get("states")
    if not isinstance(states, dict) or not states:
        return findings + [_finding("blocker", "v10_invalid_states", "root_flow.states must be a non-empty object.")]

    findings.extend(_validate_v10_legacy_topology(root_flow, states))
    execution_plan = root_flow.get("execution_plan")
    if not isinstance(execution_plan, dict):
        return findings + [_finding(
            "blocker",
            "v10_execution_plan_missing",
            f"{protocol_id}@{protocol_version} requires root_flow.execution_plan.",
        )]
    if execution_plan.get("schema") != "cartridgeflow.execution_plan.v1":
        findings.append(_finding(
            "blocker",
            "v10_execution_plan_schema_invalid",
            "execution_plan.schema must be cartridgeflow.execution_plan.v1.",
        ))

    entry = str(execution_plan.get("entry") or "").strip()
    if not entry or entry not in states:
        findings.append(_finding(
            "blocker",
            "v10_execution_plan_entry_invalid",
            "execution_plan.entry must name a declared state.",
        ))

    edges = execution_plan.get("edges")
    if not isinstance(edges, list):
        return findings + [_finding(
            "blocker",
            "v10_execution_plan_edges_invalid",
            "execution_plan.edges must be an array.",
        )]

    edge_ids: set[str] = set()
    parsed_edges: list[dict] = []
    for index, edge in enumerate(edges):
        parsed = _validate_v10_edge(edge, index, states, findings)
        if not parsed:
            continue
        edge_id = parsed["id"]
        if edge_id in edge_ids:
            findings.append(_edge_finding(
                "blocker",
                "v10_execution_edge_id_duplicate",
                edge_id,
                "execution plan edge ids must be unique.",
            ))
            continue
        edge_ids.add(edge_id)
        parsed_edges.append(parsed)

    findings.extend(_validate_v10_execution_topology(parsed_edges, states))
    return findings


def validate_v02_flow_contract(root_flow: dict | None, manifest: dict | None = None) -> list[dict]:
    findings: list[dict] = []
    root_flow = root_flow if isinstance(root_flow, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}

    if not _root_flow_declares_v02(root_flow):
        findings.append(_finding(
            "blocker",
            "v02_root_flow_protocol_missing",
            "root flow must declare protocol CF-FARP@0.2.",
        ))

    states = root_flow.get("states")
    if not isinstance(states, dict) or not states:
        findings.append(_finding("blocker", "v02_invalid_states", "root_flow.states must be a non-empty object."))
        return findings

    manifest_tools = {
        str(tool.get("id")): tool
        for tool in manifest.get("mcp_tools") or []
        if isinstance(tool, dict) and tool.get("id")
    }
    produced_keys = _produced_keys(states)

    for node_id, node in states.items():
        if not isinstance(node, dict):
            findings.append(_node_finding("blocker", "v02_node_not_object", str(node_id), "node must be an object."))
            continue
        findings.extend(_validate_v02_node(str(node_id), node, manifest_tools, produced_keys))

    return findings


def validate_v03_flow_contract(root_flow: dict | None, manifest: dict | None = None) -> list[dict]:
    findings: list[dict] = []
    root_flow = root_flow if isinstance(root_flow, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}

    if not _root_flow_declares_version(root_flow, "0.3"):
        findings.append(_finding(
            "blocker",
            "v03_root_flow_protocol_missing",
            "root flow must declare protocol CF-FARP@0.3.",
        ))

    states = root_flow.get("states")
    if not isinstance(states, dict) or not states:
        findings.append(_finding("blocker", "v03_invalid_states", "root_flow.states must be a non-empty object."))
        return findings

    manifest_tools = {
        str(tool.get("id")): tool
        for tool in manifest.get("mcp_tools") or []
        if isinstance(tool, dict) and tool.get("id")
    }
    produced_keys = _produced_keys(states)

    for node_id, node in states.items():
        if not isinstance(node, dict):
            findings.append(_node_finding("blocker", "v03_node_not_object", str(node_id), "node must be an object."))
            continue
        findings.extend(_validate_v02_node(str(node_id), node, manifest_tools, produced_keys))
        findings.extend(_validate_v03_node(str(node_id), node))

    return findings


def validate_v04_flow_contract(root_flow: dict | None, manifest: dict | None = None) -> list[dict]:
    findings: list[dict] = []
    root_flow = root_flow if isinstance(root_flow, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}

    if not _root_flow_declares_version(root_flow, "0.4"):
        findings.append(_finding(
            "blocker",
            "v04_root_flow_protocol_missing",
            "root flow must declare protocol CF-FARP@0.4.",
        ))

    states = root_flow.get("states")
    if not isinstance(states, dict) or not states:
        findings.append(_finding("blocker", "v04_invalid_states", "root_flow.states must be a non-empty object."))
        return findings

    manifest_tools = {
        str(tool.get("id")): tool
        for tool in manifest.get("mcp_tools") or []
        if isinstance(tool, dict) and tool.get("id")
    }
    produced_keys = _produced_keys(states, include_decision_consume=True)

    for node_id, node in states.items():
        if not isinstance(node, dict):
            findings.append(_node_finding("blocker", "v04_node_not_object", str(node_id), "node must be an object."))
            continue
        findings.extend(_validate_v02_node(str(node_id), node, manifest_tools, produced_keys))
        findings.extend(_validate_v03_node(str(node_id), node))
        findings.extend(_validate_v04_node(str(node_id), node))

    return findings


def validate_v05_flow_contract(root_flow: dict | None, manifest: dict | None = None) -> list[dict]:
    findings: list[dict] = []
    root_flow = root_flow if isinstance(root_flow, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}

    if not _root_flow_declares_version(root_flow, "0.5"):
        findings.append(_finding(
            "blocker",
            "v05_root_flow_protocol_missing",
            "root flow must declare protocol CF-FARP@0.5.",
        ))

    states = root_flow.get("states")
    if not isinstance(states, dict) or not states:
        findings.append(_finding("blocker", "v05_invalid_states", "root_flow.states must be a non-empty object."))
        return findings

    manifest_tools = {
        str(tool.get("id")): tool
        for tool in manifest.get("mcp_tools") or []
        if isinstance(tool, dict) and tool.get("id")
    }
    produced_keys = _produced_keys(states, include_decision_consume=True)

    for node_id, node in states.items():
        if not isinstance(node, dict):
            findings.append(_node_finding("blocker", "v05_node_not_object", str(node_id), "node must be an object."))
            continue
        findings.extend(_validate_v02_node(str(node_id), node, manifest_tools, produced_keys))
        findings.extend(_validate_v03_node(str(node_id), node))
        findings.extend(_validate_v04_node(str(node_id), node))

    return findings


def validate_v06_flow_contract(root_flow: dict | None, manifest: dict | None = None) -> list[dict]:
    findings: list[dict] = []
    root_flow = root_flow if isinstance(root_flow, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}

    if not _root_flow_declares_version(root_flow, "0.6"):
        findings.append(_finding(
            "blocker",
            "v06_root_flow_protocol_missing",
            "root flow must declare protocol CF-FARP@0.6.",
        ))

    states = root_flow.get("states")
    if not isinstance(states, dict) or not states:
        findings.append(_finding("blocker", "v06_invalid_states", "root_flow.states must be a non-empty object."))
        return findings

    manifest_tools = {
        str(tool.get("id")): tool
        for tool in manifest.get("mcp_tools") or []
        if isinstance(tool, dict) and tool.get("id")
    }
    produced_keys = _produced_keys(states, include_decision_consume=True)

    for node_id, node in states.items():
        if not isinstance(node, dict):
            findings.append(_node_finding("blocker", "v06_node_not_object", str(node_id), "node must be an object."))
            continue
        findings.extend(_validate_v02_node(str(node_id), node, manifest_tools, produced_keys, protocol_version="0.6"))
        findings.extend(_validate_v03_node(str(node_id), node))
        findings.extend(_validate_v04_node(str(node_id), node))
        findings.extend(_validate_v06_node(str(node_id), node, manifest_tools))

    return findings


def validate_v07_flow_contract(root_flow: dict | None, manifest: dict | None = None) -> list[dict]:
    findings: list[dict] = []
    root_flow = root_flow if isinstance(root_flow, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}

    if not _root_flow_declares_version(root_flow, "0.7"):
        findings.append(_finding(
            "blocker",
            "v07_root_flow_protocol_missing",
            "root flow must declare protocol CF-FARP@0.7.",
        ))

    states = root_flow.get("states")
    if not isinstance(states, dict) or not states:
        findings.append(_finding("blocker", "v07_invalid_states", "root_flow.states must be a non-empty object."))
        return findings

    manifest_tools = {
        str(tool.get("id")): tool
        for tool in manifest.get("mcp_tools") or []
        if isinstance(tool, dict) and tool.get("id")
    }
    produced_keys = _produced_keys(states, include_decision_consume=True)

    for node_id, node in states.items():
        node_id = str(node_id)
        if not isinstance(node, dict):
            findings.append(_node_finding("blocker", "v07_node_not_object", node_id, "node must be an object."))
            continue
        findings.extend(_validate_v02_node(node_id, node, manifest_tools, produced_keys, protocol_version="0.7"))
        findings.extend(_validate_v03_node(node_id, node))
        findings.extend(_validate_v04_node(node_id, node))
        findings.extend(_validate_v06_node(node_id, node, manifest_tools))
        if str(node.get("type") or "") == "process" and _contract_field(node, "kind") == "ui":
            findings.append(_node_finding(
                "blocker",
                "v07_legacy_ui_kind_forbidden",
                node_id,
                "kind=ui was replaced by kind=interaction in CF-FARP@0.7.",
            ))

    return findings


def _validate_v02_node(
    node_id: str,
    node: dict,
    manifest_tools: dict[str, dict],
    produced_keys: set[str],
    protocol_version: str = "0.2",
) -> list[dict]:
    findings: list[dict] = []
    node_type = str(node.get("type") or "").strip()
    if node_type in LIFECYCLE_TYPES:
        return findings
    if node_type != "process":
        findings.append(_node_finding(
            "blocker",
            "v02_business_node_must_be_process",
            node_id,
            "v0.2 business nodes must use type=process; only system and terminal are lifecycle exceptions.",
        ))
        return findings

    kind = _contract_field(node, "kind")
    executor = _contract_field(node, "executor")
    effect = _contract_field(node, "effect")

    if not kind:
        findings.append(_node_finding("blocker", "v02_process_kind_missing", node_id, "process node must declare kind."))
    elif kind not in PROCESS_KINDS:
        findings.append(_node_finding("blocker", "v02_process_kind_unknown", node_id, f"unknown process kind: {kind}"))
    elif kind == "interaction" and protocol_version != "0.7":
        findings.append(_node_finding("blocker", "v07_interaction_kind_not_available", node_id, "kind=interaction requires CF-FARP@0.7."))

    if not executor:
        findings.append(_node_finding("blocker", "v02_process_executor_missing", node_id, "process node must declare executor."))
    elif executor not in EXECUTORS:
        findings.append(_node_finding("blocker", "v02_process_executor_unknown", node_id, f"unknown process executor: {executor}"))

    if not effect:
        findings.append(_node_finding("blocker", "v02_process_effect_missing", node_id, "process node must declare effect."))
    elif effect not in EFFECTS:
        findings.append(_node_finding("blocker", "v02_process_effect_unknown", node_id, f"unknown process effect: {effect}"))

    if not kind or kind not in PROCESS_KINDS:
        return findings

    if kind == "input":
        findings.extend(_validate_input_node(node_id, node, executor, effect))
    elif kind == "transfer":
        findings.extend(_validate_transfer_node(node_id, node, executor, effect))
    elif kind == "retrieval":
        findings.extend(_validate_retrieval_node(node_id, node, effect))
    elif kind == "decision":
        findings.extend(_validate_decision_node(node_id, node, effect))
    elif kind == "mcp_read":
        findings.extend(_validate_mcp_read_node(node_id, node, executor, effect, manifest_tools))
    elif kind == "mcp_execute":
        findings.extend(_validate_mcp_execute_node(node_id, node, executor, effect, manifest_tools))
    elif kind == "gate":
        findings.extend(_validate_gate_node(node_id, node))
    elif kind == "delivery":
        findings.extend(_validate_delivery_node(node_id, node, produced_keys))
    elif kind == "remote_call":
        if protocol_version not in {"0.6", "0.7"}:
            findings.extend(_validate_remote_call_node(node_id, node, executor))

    if effect in SIDE_EFFECT_EFFECTS:
        findings.extend(_validate_side_effect_policy(node_id, node))

    return findings


def _validate_v06_node(node_id: str, node: dict, manifest_tools: dict[str, dict]) -> list[dict]:
    if str(node.get("type") or "").strip() != "process":
        return []

    findings: list[dict] = []
    for path in _local_binding_paths(node):
        findings.append(_node_finding(
            "blocker",
            "v06_local_binding_forbidden",
            node_id,
            f"Root Flow must use a local resource role binding; remove local-only field: {path}",
        ))

    kind = _contract_field(node, "kind")
    if kind == "delivery":
        for field in ["input", "output", "primary_output"]:
            if not _contract_field(node, field):
                findings.append(_node_finding("blocker", f"v06_delivery_{field}_missing", node_id, f"kind=delivery must declare {field}."))
        return findings
    if kind != "remote_call":
        return findings

    executor = _contract_field(node, "executor")
    effect = _contract_field(node, "effect")
    if executor and executor != "remote":
        findings.append(_node_finding("blocker", "v06_remote_executor_invalid", node_id, "kind=remote_call must use executor=remote."))
    if not _contract_field(node, "resource_role"):
        findings.append(_node_finding("blocker", "v06_remote_resource_role_missing", node_id, "kind=remote_call must declare resource_role."))

    allowed_tools = _allowed_tools(node)
    if not allowed_tools:
        findings.append(_node_finding("blocker", "v06_remote_allowed_tools_missing", node_id, "kind=remote_call must declare allowed_tools."))
    findings.extend(_validate_allowed_tools(node_id, allowed_tools, manifest_tools))
    for field in ["timeout_ms", "failure_policy"]:
        if not _contract_field(node, field):
            findings.append(_node_finding("blocker", f"v06_remote_{field}_missing", node_id, f"kind=remote_call must declare {field}."))
    if effect in SIDE_EFFECT_EFFECTS and not _contract_field(node, "replay_policy"):
        findings.append(_node_finding("blocker", "v06_remote_replay_policy_missing", node_id, "side-effecting remote_call must declare replay_policy."))

    return findings


def _validate_input_node(node_id: str, node: dict, executor: str, effect: str) -> list[dict]:
    findings: list[dict] = []
    if executor and executor not in {"user", "remote", "human", "plugin"}:
        findings.append(_node_finding("blocker", "v02_input_executor_invalid", node_id, "kind=input must use user, human, remote, or plugin executor."))
    if effect and effect != "writes_store":
        findings.append(_node_finding("blocker", "v02_input_effect_invalid", node_id, "kind=input must use effect=writes_store."))
    for field in ["input_kind", "source", "output"]:
        if not _contract_field(node, field):
            findings.append(_node_finding("blocker", f"v02_input_{field}_missing", node_id, f"kind=input must declare {field}."))
    if not (_contract_field(node, "input_schema") or _contract_field(node, "schema")):
        findings.append(_node_finding("blocker", "v02_input_schema_missing", node_id, "kind=input must declare input_schema or equivalent schema source."))
    return findings


def _validate_transfer_node(node_id: str, node: dict, executor: str, effect: str) -> list[dict]:
    findings: list[dict] = []
    if executor and executor != "deterministic":
        findings.append(_node_finding("blocker", "v02_transfer_executor_invalid", node_id, "kind=transfer must use executor=deterministic."))
    if effect and effect != "writes_store":
        findings.append(_node_finding("blocker", "v02_transfer_effect_invalid", node_id, "kind=transfer must use effect=writes_store."))
    if _has_tool_binding(node) or _action(node) in {"tool_call", "remote_call", "llm_prompt"}:
        findings.append(_node_finding("blocker", "v02_transfer_has_side_capability", node_id, "kind=transfer must not call LLM, MCP, remote service, or tools."))
    return findings


def _validate_retrieval_node(node_id: str, node: dict, effect: str) -> list[dict]:
    if effect and effect not in {"none", "read_only", "writes_store"}:
        return [_node_finding("blocker", "v02_retrieval_effect_invalid", node_id, "kind=retrieval may only use none, read_only, or writes_store.")]
    return []


def _validate_decision_node(node_id: str, node: dict, effect: str) -> list[dict]:
    findings: list[dict] = []
    if effect and effect != "none":
        findings.append(_node_finding("blocker", "v02_decision_effect_invalid", node_id, "kind=decision must use effect=none."))
    if _action(node) in {"tool_call", "remote_call"} or _has_tools(node):
        findings.append(_node_finding("blocker", "v02_decision_direct_side_effect", node_id, "kind=decision must not directly execute tools or remote side effects."))
    if _drives_tools(node) and _contract_field(node, "output_contract") not in {"tool_plan.v1", "decision_envelope.v1"}:
        findings.append(_node_finding("blocker", "v02_decision_tool_plan_missing", node_id, "kind=decision that drives tools must output tool_plan.v1 or protocol-equivalent decision_envelope.v1."))
    return findings


def _validate_v03_node(node_id: str, node: dict) -> list[dict]:
    findings: list[dict] = []
    node_type = str(node.get("type") or "").strip()
    if node_type in LIFECYCLE_TYPES or node_type != "process":
        return findings

    kind = _contract_field(node, "kind")
    executor = _contract_field(node, "executor")
    if kind == "decision" and executor == "llm":
        findings.extend(_validate_v03_llm_decision_node(node_id, node))
    return findings


def _validate_v04_node(node_id: str, node: dict) -> list[dict]:
    findings: list[dict] = []
    node_type = str(node.get("type") or "").strip()
    if node_type in LIFECYCLE_TYPES or node_type != "process":
        return findings

    kind = _contract_field(node, "kind")
    executor = _contract_field(node, "executor")
    if kind == "decision" and executor == "llm":
        findings.extend(_validate_v04_llm_decision_node(node_id, node))
    return findings


def _validate_v03_llm_decision_node(node_id: str, node: dict) -> list[dict]:
    findings: list[dict] = []
    output_contract = _contract_field(node, "output_contract")
    if output_contract != "decision_envelope.v1":
        findings.append(_node_finding(
            "blocker",
            "v03_decision_envelope_contract_missing",
            node_id,
            "kind=decision with executor=llm must declare output_contract=decision_envelope.v1.",
        ))

    decision_contract = _mapping_field(node, "decision_contract")
    if not decision_contract:
        findings.append(_node_finding(
            "blocker",
            "v03_decision_contract_missing",
            node_id,
            "kind=decision with executor=llm must declare decision_contract.",
        ))
        return findings

    schema = str(decision_contract.get("schema") or "").strip()
    if schema and schema != "decision_envelope.v1":
        findings.append(_node_finding(
            "blocker",
            "v03_decision_contract_schema_invalid",
            node_id,
            "decision_contract.schema must be decision_envelope.v1 when declared.",
        ))

    allowed_statuses = _string_list(decision_contract.get("allowed_statuses"))
    if not allowed_statuses:
        findings.append(_node_finding(
            "blocker",
            "v03_decision_allowed_statuses_missing",
            node_id,
            "decision_contract.allowed_statuses is required.",
        ))
    unknown_statuses = [item for item in allowed_statuses if item not in {"resolved", "needs_user_input", "blocked"}]
    for status in unknown_statuses:
        findings.append(_node_finding("blocker", "v03_decision_allowed_status_unknown", node_id, f"unknown decision status: {status}"))

    if "needs_user_input" in allowed_statuses or str(decision_contract.get("on_needs_user_input") or "").strip() == "pause":
        interaction = decision_contract.get("interaction") if isinstance(decision_contract.get("interaction"), dict) else {}
        if not interaction:
            findings.append(_node_finding(
                "blocker",
                "v03_decision_interaction_missing",
                node_id,
                "decision nodes that may request user input must declare decision_contract.interaction.",
            ))
        else:
            for field in ["store_key", "input_schema"]:
                if not interaction.get(field):
                    findings.append(_node_finding(
                        "blocker",
                        f"v03_decision_interaction_{field}_missing",
                        node_id,
                        f"decision_contract.interaction.{field} is required.",
                    ))
            resume_policy = str(interaction.get("resume_policy") or "").strip()
            if resume_policy and resume_policy not in RESUME_POLICIES:
                findings.append(_node_finding(
                    "blocker",
                    "v03_decision_interaction_resume_policy_invalid",
                    node_id,
                    "decision_contract.interaction.resume_policy is invalid.",
                ))
            if not resume_policy:
                findings.append(_node_finding(
                    "blocker",
                    "v03_decision_interaction_resume_policy_missing",
                    node_id,
                    "decision_contract.interaction.resume_policy is required.",
                ))
    return findings


def _validate_v04_llm_decision_node(node_id: str, node: dict) -> list[dict]:
    findings: list[dict] = []
    decision_contract = _mapping_field(node, "decision_contract")
    if not decision_contract:
        return findings

    allowed_statuses = _string_list(decision_contract.get("allowed_statuses"))
    if "resolved" not in allowed_statuses:
        return findings

    consume = decision_contract.get("consume") if isinstance(decision_contract.get("consume"), dict) else {}
    if not consume:
        findings.append(_node_finding(
            "blocker",
            "v04_decision_consume_missing",
            node_id,
            "decision nodes that allow resolved must declare decision_contract.consume.",
        ))
        return findings

    mode = str(consume.get("mode") or "").strip()
    if mode != "payload_path":
        findings.append(_node_finding(
            "blocker",
            "v04_decision_consume_mode_invalid",
            node_id,
            "decision_contract.consume.mode must be payload_path.",
        ))

    path = str(consume.get("path") or "").strip()
    if not path:
        findings.append(_node_finding(
            "blocker",
            "v04_decision_consume_path_missing",
            node_id,
            "decision_contract.consume.path is required.",
        ))
    elif path != "payload" and not path.startswith("payload."):
        findings.append(_node_finding(
            "blocker",
            "v04_decision_consume_path_invalid",
            node_id,
            "decision_contract.consume.path must point inside payload.",
        ))

    as_key = str(consume.get("as") or "").strip()
    output_key = str(_contract_field(node, "output") or "").strip()
    if not as_key:
        findings.append(_node_finding(
            "blocker",
            "v04_decision_consume_as_missing",
            node_id,
            "decision_contract.consume.as is required.",
        ))
    elif not _valid_store_key(as_key):
        findings.append(_node_finding(
            "blocker",
            "v04_decision_consume_as_invalid",
            node_id,
            "decision_contract.consume.as must be a simple store key.",
        ))
    elif output_key and as_key == output_key:
        findings.append(_node_finding(
            "blocker",
            "v04_decision_consume_as_overwrites_output",
            node_id,
            "decision_contract.consume.as must not overwrite the complete decision envelope output.",
        ))

    on_missing = str(consume.get("on_missing") or "fail_closed").strip()
    if on_missing not in {"fail_closed", "block_decision"}:
        findings.append(_node_finding(
            "blocker",
            "v04_decision_consume_on_missing_invalid",
            node_id,
            "decision_contract.consume.on_missing must be fail_closed or block_decision.",
        ))

    return findings


def _validate_mcp_read_node(node_id: str, node: dict, executor: str, effect: str, manifest_tools: dict[str, dict]) -> list[dict]:
    findings: list[dict] = []
    if executor and executor != "mcp":
        findings.append(_node_finding("blocker", "v02_mcp_read_executor_invalid", node_id, "kind=mcp_read must use executor=mcp."))
    if effect and effect != "read_only":
        findings.append(_node_finding("blocker", "v02_mcp_read_effect_invalid", node_id, "kind=mcp_read must use effect=read_only."))

    binding = _mapping_field(node, "mcp_binding")
    if binding.get("mode") != "read_only":
        findings.append(_node_finding("blocker", "v02_mcp_read_binding_missing", node_id, "kind=mcp_read must declare mcp_binding.mode=read_only."))

    allowed_tools = _allowed_tools(node, binding)
    if not allowed_tools:
        findings.append(_node_finding("blocker", "v02_mcp_read_allowed_tools_missing", node_id, "kind=mcp_read must declare allowed_tools."))
    findings.extend(_validate_allowed_tools(node_id, allowed_tools, manifest_tools))
    for tool_id in allowed_tools:
        tool = manifest_tools.get(tool_id)
        if not tool:
            continue
        side_effect = _tool_side_effect(tool)
        if side_effect not in READ_ONLY_TOOL_SIDE_EFFECTS:
            findings.append(_node_finding(
                "blocker",
                "v02_mcp_read_tool_has_side_effect",
                node_id,
                f"kind=mcp_read cannot bind side-effecting tool: {tool_id}",
            ))
    return findings


def _validate_mcp_execute_node(node_id: str, node: dict, executor: str, effect: str, manifest_tools: dict[str, dict]) -> list[dict]:
    findings: list[dict] = []
    if executor and executor != "mcp":
        findings.append(_node_finding("blocker", "v02_mcp_execute_executor_invalid", node_id, "kind=mcp_execute must use executor=mcp."))
    if effect and effect not in SIDE_EFFECT_EFFECTS:
        findings.append(_node_finding("blocker", "v02_mcp_execute_effect_invalid", node_id, "kind=mcp_execute must declare a side-effect effect."))
    if not _contract_field(node, "tool_binding"):
        findings.append(_node_finding("blocker", "v02_mcp_execute_tool_binding_missing", node_id, "kind=mcp_execute must declare tool_binding."))
    allowed_tools = _allowed_tools(node)
    if not allowed_tools:
        findings.append(_node_finding("blocker", "v02_mcp_execute_allowed_tools_missing", node_id, "kind=mcp_execute must declare allowed_tools."))
    findings.extend(_validate_allowed_tools(node_id, allowed_tools, manifest_tools))
    if not _contract_field(node, "failure_policy"):
        findings.append(_node_finding("blocker", "v02_mcp_execute_failure_policy_missing", node_id, "kind=mcp_execute must declare failure_policy."))
    return findings


def _validate_gate_node(node_id: str, node: dict) -> list[dict]:
    output_contract = _contract_field(node, "output_contract")
    if output_contract and output_contract != "gate_result.v1":
        return [_node_finding("warning", "v02_gate_output_contract_nonstandard", node_id, "kind=gate should output gate_result.v1 or an equivalent structured result.")]
    if not output_contract and not _contract_field(node, "gate_contract"):
        return [_node_finding("warning", "v02_gate_output_contract_missing", node_id, "kind=gate should declare output_contract=gate_result.v1 or gate_contract.")]
    return []


def _validate_delivery_node(node_id: str, node: dict, produced_keys: set[str]) -> list[dict]:
    findings: list[dict] = []
    primary_output = _contract_field(node, "primary_output") or _contract_field(node, "output")
    if not primary_output:
        findings.append(_node_finding("blocker", "v02_delivery_output_missing", node_id, "kind=delivery must declare output or primary_output."))
    for key in _split_keys(_contract_field(node, "input")):
        if key and key not in produced_keys:
            findings.append(_node_finding("blocker", "v02_delivery_input_missing", node_id, f"delivery input is not produced by the flow: {key}"))
    return findings


def _validate_remote_call_node(node_id: str, node: dict, executor: str) -> list[dict]:
    findings: list[dict] = []
    if executor and executor != "remote":
        findings.append(_node_finding("warning", "v02_remote_executor_nonstandard", node_id, "kind=remote_call should normally use executor=remote."))
    for field in ["endpoint", "timeout_ms", "failure_policy"]:
        if not _contract_field(node, field):
            findings.append(_node_finding("blocker", f"v02_remote_{field}_missing", node_id, f"kind=remote_call must declare {field}."))
    return findings


def _validate_side_effect_policy(node_id: str, node: dict) -> list[dict]:
    findings: list[dict] = []
    if not _contract_field(node, "permission"):
        findings.append(_node_finding("blocker", "v02_side_effect_permission_missing", node_id, "side-effecting process node must declare permission."))
    if not _contract_field(node, "failure_policy"):
        findings.append(_node_finding("blocker", "v02_side_effect_failure_policy_missing", node_id, "side-effecting process node must declare failure_policy."))
    if not _contract_field(node, "audit_log"):
        findings.append(_node_finding("blocker", "v02_side_effect_audit_log_missing", node_id, "side-effecting process node must declare audit_log."))
    return findings


def _validate_allowed_tools(node_id: str, allowed_tools: list[str], manifest_tools: dict[str, dict]) -> list[dict]:
    findings: list[dict] = []
    for tool_id in allowed_tools:
        if tool_id not in manifest_tools:
            findings.append(_node_finding("blocker", "v02_allowed_tool_not_declared", node_id, f"allowed tool is not declared in manifest.mcp_tools: {tool_id}"))
    return findings


def _root_flow_declares_v02(root_flow: dict) -> bool:
    return _root_flow_declares_version(root_flow, "0.2")


def _root_flow_declares_version(root_flow: dict, version: str) -> bool:
    return _root_flow_declares_protocol(root_flow, "CF-FARP", version)


def _root_flow_declares_protocol(root_flow: dict, protocol_id: str, version: str) -> bool:
    protocol = root_flow.get("protocol")
    if isinstance(protocol, str):
        return protocol.strip() in {f"{protocol_id}@{version}", f"{protocol_id}-{version}"}
    if isinstance(protocol, dict):
        return str(protocol.get("id") or "") == protocol_id and str(protocol.get("version") or "") == version
    return str(root_flow.get("protocol_id") or "") == protocol_id and str(root_flow.get("protocol_version") or "") == version


def _local_binding_paths(value, path: str = "node") -> list[str]:
    forbidden = {"api_key", "authorization", "base_url", "endpoint", "headers", "secret", "token", "url"}
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if str(key).strip().lower() in forbidden:
                paths.append(item_path)
            paths.extend(_local_binding_paths(item, item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_local_binding_paths(item, f"{path}[{index}]"))
    return paths


def _produced_keys(states: dict, include_decision_consume: bool = False) -> set[str]:
    produced: set[str] = set()
    for node in states.values():
        if isinstance(node, dict):
            for key in _split_keys(_contract_field(node, "output")):
                produced.add(key)
            if include_decision_consume:
                consume_key = _decision_consume_as(node)
                if consume_key:
                    produced.add(consume_key)
            for key in _split_keys(_contract_field(node, "primary_output")):
                produced.add(key)
    return produced


def _decision_consume_as(node: dict) -> str:
    if _contract_field(node, "output_contract") != "decision_envelope.v1":
        return ""
    decision_contract = _mapping_field(node, "decision_contract")
    consume = decision_contract.get("consume") if isinstance(decision_contract.get("consume"), dict) else {}
    return str(consume.get("as") or "").strip()


def _contract_field(node: dict, key: str):
    if key in node:
        return node.get(key)
    params = node.get("params") if isinstance(node.get("params"), dict) else {}
    protocol = params.get("protocol") if isinstance(params.get("protocol"), dict) else {}
    preset_config = params.get("preset_config") if isinstance(params.get("preset_config"), dict) else {}
    if key in protocol:
        return protocol.get(key)
    if key in params:
        return params.get(key)
    return preset_config.get(key)


def _mapping_field(node: dict, key: str) -> dict:
    value = _contract_field(node, key)
    return value if isinstance(value, dict) else {}


def _allowed_tools(node: dict, binding: dict | None = None) -> list[str]:
    binding = binding if isinstance(binding, dict) else {}
    raw = _contract_field(node, "allowed_tools")
    if raw is None:
        raw = binding.get("allowed_tools")
    if isinstance(raw, str):
        return _split_keys(raw)
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _action(node: dict) -> str:
    return str(node.get("action") or _contract_field(node, "action") or "").strip()


def _has_tools(node: dict) -> bool:
    tools = node.get("tools")
    if isinstance(tools, list) and tools:
        return True
    params = node.get("params") if isinstance(node.get("params"), dict) else {}
    return isinstance(params.get("tools"), list) and bool(params.get("tools"))


def _has_tool_binding(node: dict) -> bool:
    return bool(_has_tools(node) or _contract_field(node, "tool_binding") or _allowed_tools(node) or _contract_field(node, "mcp_binding"))


def _drives_tools(node: dict) -> bool:
    return bool(_contract_field(node, "tool_binding") or _allowed_tools(node) or _contract_field(node, "emits_tool_plan"))


def _tool_side_effect(tool: dict) -> str:
    contract = tool.get("contract") if isinstance(tool.get("contract"), dict) else {}
    value = str(contract.get("side_effect") or "").strip().lower()
    if any(token in value for token in ["write", "mutate", "artifact", "file", "state", "publish", "external", "remote"]):
        return value
    return value if value in READ_ONLY_TOOL_SIDE_EFFECTS else value


def _split_keys(value) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).replace("\r", "\n").replace(",", "\n").split("\n") if item.strip()]


def _string_list(value) -> list[str]:
    if isinstance(value, str):
        return _split_keys(value)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _valid_store_key(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(value or "")))


def _finding(severity: str, code: str, message: str) -> dict:
    return {"severity": severity, "code": code, "message": message}


def _node_finding(severity: str, code: str, node_id: str, message: str) -> dict:
    return {"severity": severity, "code": code, "node_id": node_id, "message": message}


V10_EXECUTION_EDGE_KINDS = {"sequence", "fork", "join", "loop", "batch", "wait", "failure"}
V10_JOIN_MODES = {"all", "any", "keyed"}
V10_WAIT_MODES = {"duration", "signal", "condition"}
V10_FAILURE_CAUSES = {"cancelled", "exception", "resource", "retry_exhausted", "timeout", "validation"}


def _validate_v10_legacy_topology(root_flow: dict, states: dict) -> list[dict]:
    findings: list[dict] = []
    control_edges = root_flow.get("control_edges")
    if control_edges:
        findings.append(_finding(
            "blocker",
            "v10_legacy_control_edges_forbidden",
            "CF-FARP@1.0 requires executable edges in execution_plan.edges, not control_edges.",
        ))
        findings.extend(_validate_v10_legacy_edge_kinds(control_edges))
    for edge in root_flow.get("edges") or []:
        if isinstance(edge, dict) and edge.get("kind") == "action_route":
            findings.append(_finding(
                "blocker",
                "v10_legacy_action_route_forbidden",
                "legacy action_route edges must be expressed as explicit ExecutionPlan edges.",
            ))
        elif isinstance(edge, dict) and edge.get("kind") == "failure_route":
            findings.append(_finding(
                "blocker",
                "v10_legacy_failure_route_forbidden",
                "legacy failure_route edges must be expressed as explicit failure edges.",
            ))
        elif isinstance(edge, dict) and edge.get("executable") is False:
            findings.append(_finding(
                "blocker",
                "v10_visible_non_executable_edge",
                "A visible edge marked executable=false cannot appear in a CF-FARP@1.0 flow.",
            ))
        else:
            findings.append(_finding(
                "blocker",
                "v10_legacy_edges_forbidden",
                "CF-FARP@1.0 requires executable edges in execution_plan.edges, not root_flow.edges.",
            ))
    for node_id, node in states.items():
        if not isinstance(node, dict):
            findings.append(_node_finding("blocker", "v10_node_not_object", str(node_id), "node must be an object."))
            continue
        if node.get("next"):
            findings.append(_node_finding(
                "blocker",
                "v10_implicit_sequence_forbidden",
                str(node_id),
                "node.next is not an executable CF-FARP@1.0 sequence edge.",
            ))
        if node.get("action_route") or node.get("action_routes"):
            findings.append(_node_finding(
                "blocker",
                "v10_legacy_action_route_forbidden",
                str(node_id),
                "legacy action_route/action_routes must be expressed as explicit ExecutionPlan edges.",
            ))
        if node.get("failure_route"):
            findings.append(_node_finding(
                "blocker",
                "v10_legacy_failure_route_forbidden",
                str(node_id),
                "legacy failure_route must be expressed as an explicit failure edge.",
            ))
    return findings


def _validate_v10_legacy_edge_kinds(edges) -> list[dict]:
    if not isinstance(edges, list):
        return []
    findings: list[dict] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if edge.get("kind") == "action_route":
            findings.append(_finding(
                "blocker",
                "v10_legacy_action_route_forbidden",
                "legacy action_route edges must be expressed as explicit ExecutionPlan edges.",
            ))
        elif edge.get("kind") == "failure_route":
            findings.append(_finding(
                "blocker",
                "v10_legacy_failure_route_forbidden",
                "legacy failure_route edges must be expressed as explicit failure edges.",
            ))
        elif edge.get("executable") is False:
            findings.append(_finding(
                "blocker",
                "v10_visible_non_executable_edge",
                "A visible edge marked executable=false cannot appear in a CF-FARP@1.0 flow.",
            ))
    return findings


def _validate_v10_edge(edge, index: int, states: dict, findings: list[dict]) -> dict | None:
    if not isinstance(edge, dict):
        findings.append(_finding("blocker", "v10_execution_edge_not_object", f"execution_plan.edges[{index}] must be an object."))
        return None

    edge_id = str(edge.get("id") or "").strip()
    if not edge_id:
        findings.append(_finding("blocker", "v10_execution_edge_id_missing", f"execution_plan.edges[{index}].id is required."))
        return None
    kind = str(edge.get("kind") or "").strip()
    if kind not in V10_EXECUTION_EDGE_KINDS:
        findings.append(_edge_finding(
            "blocker",
            "v10_execution_edge_kind_invalid",
            edge_id,
            f"execution edge kind must be one of {sorted(V10_EXECUTION_EDGE_KINDS)}.",
        ))
        return None
    if edge.get("executable") is False:
        findings.append(_edge_finding(
            "blocker",
            "v10_visible_non_executable_edge",
            edge_id,
            "ExecutionPlan edges are executable declarations and cannot be marked executable=false.",
        ))

    source = str(edge.get("from") or "").strip()
    target = str(edge.get("to") or "").strip()
    if not source or not target:
        findings.append(_edge_finding(
            "blocker",
            "v10_execution_edge_endpoint_missing",
            edge_id,
            "execution edge must declare non-empty from and to state ids.",
        ))
    elif source not in states or target not in states:
        findings.append(_edge_finding(
            "blocker",
            "v10_execution_edge_endpoint_unknown",
            edge_id,
            "execution edge endpoints must name declared states.",
        ))

    parsed = {"id": edge_id, "kind": kind, "from": source, "to": target, "raw": edge}
    if kind == "fork":
        _validate_v10_fork_edge(parsed, findings)
    elif kind == "join":
        _validate_v10_join_edge(parsed, findings)
    elif kind == "loop":
        _validate_v10_loop_edge(parsed, states, findings)
    elif kind == "batch":
        _validate_v10_batch_edge(parsed, findings)
    elif kind == "wait":
        _validate_v10_wait_edge(parsed, findings)
    elif kind == "failure":
        _validate_v10_failure_edge(parsed, findings)
    return parsed


def _validate_v10_fork_edge(edge: dict, findings: list[dict]) -> None:
    fork = _v10_mapping(edge["raw"].get("fork"))
    fork_id = _v10_string(fork.get("id"))
    branch = _v10_string(fork.get("branch"))
    edge["fork_id"] = fork_id
    edge["branch"] = branch
    if not fork_id or not branch:
        findings.append(_edge_finding(
            "blocker",
            "v10_fork_contract_invalid",
            edge["id"],
            "fork edges require fork.id and fork.branch.",
        ))


def _validate_v10_join_edge(edge: dict, findings: list[dict]) -> None:
    join = _v10_mapping(edge["raw"].get("join"))
    join_id = _v10_string(join.get("id"))
    mode = _v10_string(join.get("mode"))
    branch = _v10_string(join.get("branch"))
    branches = _v10_string_list(join.get("branches"))
    edge.update({
        "join_id": join_id,
        "join_mode": mode,
        "branch": branch,
        "join_branches": branches,
        "key_ref": _v10_string(join.get("key_ref")),
        "remaining": _v10_string(join.get("remaining")),
    })
    if not join_id or mode not in V10_JOIN_MODES or not branch:
        findings.append(_edge_finding(
            "blocker",
            "v10_join_contract_invalid",
            edge["id"],
            "join edges require join.id, join.mode=all|any|keyed, and join.branch.",
        ))
    if not branches:
        findings.append(_edge_finding(
            "blocker",
            "v10_join_branches_missing",
            edge["id"],
            "join.edges must declare the complete finite join.branches set.",
        ))
    if mode == "keyed" and not edge["key_ref"]:
        findings.append(_edge_finding(
            "blocker",
            "v10_keyed_join_key_missing",
            edge["id"],
            "keyed joins require a non-empty join.key_ref value reference.",
        ))
    if mode == "any" and edge["remaining"] not in {"cancel", "drain"}:
        findings.append(_edge_finding(
            "blocker",
            "v10_any_join_remaining_policy_missing",
            edge["id"],
            "any joins require join.remaining=cancel|drain.",
        ))
    if mode != "any" and edge["remaining"]:
        findings.append(_edge_finding(
            "blocker",
            "v10_join_remaining_policy_invalid",
            edge["id"],
            "join.remaining is only valid for mode=any.",
        ))


def _validate_v10_loop_edge(edge: dict, states: dict, findings: list[dict]) -> None:
    loop = _v10_mapping(edge["raw"].get("loop"))
    loop_id = _v10_string(loop.get("id"))
    maximum = loop.get("max_iterations")
    condition = _v10_string(loop.get("continue_when"))
    exit_to = _v10_string(loop.get("exit_to"))
    edge["loop_id"] = loop_id
    if not loop_id or not _v10_positive_int(maximum) or not condition or not exit_to:
        findings.append(_edge_finding(
            "blocker",
            "v10_loop_contract_invalid",
            edge["id"],
            "loop edges require loop.id, a positive integer max_iterations, continue_when, and exit_to.",
        ))
    if exit_to and exit_to not in states:
        findings.append(_edge_finding(
            "blocker",
            "v10_loop_exit_unknown",
            edge["id"],
            "loop.exit_to must name a declared state.",
        ))


def _validate_v10_batch_edge(edge: dict, findings: list[dict]) -> None:
    batch = _v10_mapping(edge["raw"].get("batch"))
    batch_id = _v10_string(batch.get("id"))
    items_ref = _v10_string(batch.get("items_ref"))
    size = batch.get("size")
    concurrency = batch.get("max_concurrency")
    ordering = _v10_string(batch.get("ordering"))
    if not batch_id or not items_ref or not _v10_positive_int(size) or not _v10_positive_int(concurrency) or ordering not in {"preserve", "unordered"}:
        findings.append(_edge_finding(
            "blocker",
            "v10_batch_contract_invalid",
            edge["id"],
            "batch edges require id, items_ref, positive size, positive max_concurrency, and ordering=preserve|unordered.",
        ))
    elif concurrency > size:
        findings.append(_edge_finding(
            "blocker",
            "v10_batch_concurrency_invalid",
            edge["id"],
            "batch.max_concurrency cannot exceed batch.size.",
        ))


def _validate_v10_wait_edge(edge: dict, findings: list[dict]) -> None:
    wait = _v10_mapping(edge["raw"].get("wait"))
    wait_id = _v10_string(wait.get("id"))
    mode = _v10_string(wait.get("mode"))
    timeout_ms = wait.get("timeout_ms")
    resume_key = _v10_string(wait.get("resume_key"))
    edge["wait_mode"] = mode
    if not wait_id or mode not in V10_WAIT_MODES or not _v10_positive_int(timeout_ms) or not _valid_store_key(resume_key):
        findings.append(_edge_finding(
            "blocker",
            "v10_wait_contract_invalid",
            edge["id"],
            "wait edges require id, mode, positive timeout_ms, and a valid resume_key.",
        ))
    if mode == "duration" and not _v10_positive_int(wait.get("duration_ms")):
        findings.append(_edge_finding("blocker", "v10_wait_duration_missing", edge["id"], "duration waits require positive duration_ms."))
    if mode == "signal" and not _v10_string(wait.get("signal")):
        findings.append(_edge_finding("blocker", "v10_wait_signal_missing", edge["id"], "signal waits require signal."))
    if mode == "condition" and not _v10_string(wait.get("condition_ref")):
        findings.append(_edge_finding("blocker", "v10_wait_condition_missing", edge["id"], "condition waits require condition_ref."))


def _validate_v10_failure_edge(edge: dict, findings: list[dict]) -> None:
    failure = _v10_mapping(edge["raw"].get("failure"))
    failure_id = _v10_string(failure.get("id"))
    causes = _v10_string_list(failure.get("causes"))
    edge["failure_causes"] = causes
    if not failure_id or not causes or len(causes) != len(set(causes)) or any(cause not in V10_FAILURE_CAUSES for cause in causes):
        findings.append(_edge_finding(
            "blocker",
            "v10_failure_contract_invalid",
            edge["id"],
            "failure edges require id and unique causes from the CF-FARP@1.0 failure vocabulary.",
        ))


def _validate_v10_execution_topology(edges: list[dict], states: dict) -> list[dict]:
    findings: list[dict] = []
    successful = [edge for edge in edges if edge["kind"] != "failure" and edge["from"] and edge["to"]]
    by_source: dict[str, list[dict]] = {}
    incoming: dict[str, list[dict]] = {}
    for edge in successful:
        by_source.setdefault(edge["from"], []).append(edge)
        incoming.setdefault(edge["to"], []).append(edge)

    for source, outgoing in by_source.items():
        kinds = {edge["kind"] for edge in outgoing}
        if "fork" in kinds and kinds != {"fork"}:
            findings.append(_finding(
                "blocker",
                "v10_fork_mixed_outgoing_forbidden",
                f"state {source} must use only fork edges for a fork transition.",
            ))
        elif "fork" not in kinds and len(outgoing) > 1:
            findings.append(_finding(
                "blocker",
                "v10_ambiguous_successor_forbidden",
                f"state {source} has multiple non-fork executable successors.",
            ))

    loop_sources = {edge["from"] for edge in successful if edge["kind"] == "loop"}
    for target, target_edges in incoming.items():
        if target in loop_sources:
            continue
        if len(target_edges) > 1 and any(edge["kind"] != "join" for edge in target_edges):
            findings.append(_finding(
                "blocker",
                "v10_implicit_join_forbidden",
                f"state {target} has multiple incoming tokens without one explicit join declaration.",
            ))

    findings.extend(_validate_v10_fork_groups([edge for edge in edges if edge["kind"] == "fork"]))
    findings.extend(_validate_v10_join_groups([edge for edge in edges if edge["kind"] == "join"]))
    findings.extend(_validate_v10_failure_exits(edges, states))
    if _v10_has_cycle(successful):
        findings.append(_finding(
            "blocker",
            "v10_implicit_cycle_forbidden",
            "every execution-plan cycle must contain an explicit bounded loop edge.",
        ))
    return findings


def _validate_v10_fork_groups(edges: list[dict]) -> list[dict]:
    findings: list[dict] = []
    groups: dict[str, list[dict]] = {}
    for edge in edges:
        groups.setdefault(edge.get("fork_id") or f"__invalid__:{edge['id']}", []).append(edge)
    for fork_id, group in groups.items():
        sources = {edge["from"] for edge in group}
        branches = [edge.get("branch") for edge in group]
        if not fork_id or fork_id.startswith("__invalid__") or len(group) < 2 or len(sources) != 1 or not all(branches) or len(set(branches)) != len(branches):
            findings.append(_finding(
                "blocker",
                "v10_fork_group_invalid",
                f"fork {fork_id} must have at least two uniquely named branches from one state.",
            ))
    return findings


def _validate_v10_join_groups(edges: list[dict]) -> list[dict]:
    findings: list[dict] = []
    groups: dict[tuple[str, str], list[dict]] = {}
    id_targets: dict[str, set[str]] = {}
    for edge in edges:
        join_id = edge.get("join_id") or f"__invalid__:{edge['id']}"
        groups.setdefault((edge["to"], join_id), []).append(edge)
        id_targets.setdefault(join_id, set()).add(edge["to"])
    for join_id, targets in id_targets.items():
        if not join_id.startswith("__invalid__") and len(targets) != 1:
            findings.append(_finding(
                "blocker",
                "v10_join_target_ambiguous",
                f"join {join_id} must have exactly one output state.",
            ))
    for (target, join_id), group in groups.items():
        modes = {edge.get("join_mode") for edge in group}
        branches = [edge.get("branch") for edge in group]
        declared_branch_sets = {tuple(edge.get("join_branches") or []) for edge in group}
        valid_branches = all(branches) and len(set(branches)) == len(branches)
        actual_branches = set(branches)
        declared_matches = (
            len(declared_branch_sets) == 1
            and bool(declared_branch_sets)
            and set(next(iter(declared_branch_sets))) == actual_branches
            and len(next(iter(declared_branch_sets))) == len(actual_branches)
        )
        if len(group) < 2 or len(modes) != 1 or not valid_branches or not declared_matches:
            findings.append(_finding(
                "blocker",
                "v10_join_group_invalid",
                f"join {join_id} into {target} must have two or more unique branches matching one complete join.branches set.",
            ))
            continue
        mode = next(iter(modes))
        if mode == "keyed" and len({edge.get("key_ref") for edge in group}) != 1:
            findings.append(_finding(
                "blocker",
                "v10_keyed_join_key_inconsistent",
                f"keyed join {join_id} must use one key_ref for every branch.",
            ))
        if mode == "any" and len({edge.get("remaining") for edge in group}) != 1:
            findings.append(_finding(
                "blocker",
                "v10_any_join_remaining_policy_inconsistent",
                f"any join {join_id} must use one remaining policy for every branch.",
            ))
    return findings


def _validate_v10_failure_exits(edges: list[dict], states: dict) -> list[dict]:
    findings: list[dict] = []
    causes_by_source: dict[str, set[str]] = {}
    for edge in edges:
        if edge["kind"] != "failure" or not edge["from"]:
            continue
        causes = set(edge.get("failure_causes") or [])
        existing = causes_by_source.setdefault(edge["from"], set())
        overlap = existing & causes
        if overlap:
            findings.append(_edge_finding(
                "blocker",
                "v10_failure_cause_ambiguous",
                edge["id"],
                f"failure causes already have an exit from {edge['from']}: {sorted(overlap)}.",
            ))
        existing.update(causes)
    for node_id, node in states.items():
        if _v10_node_may_fail(node) and not causes_by_source.get(str(node_id)):
            findings.append(_node_finding(
                "blocker",
                "v10_failure_exit_missing",
                str(node_id),
                "executable action nodes require at least one declared failure edge.",
            ))
    for edge in edges:
        if edge["kind"] == "wait" and "timeout" not in causes_by_source.get(edge["from"], set()):
            findings.append(_edge_finding(
                "blocker",
                "v10_wait_timeout_failure_missing",
                edge["id"],
                "wait.timeout_ms requires an explicit failure edge for cause=timeout from the wait source.",
            ))
    return findings


def _v10_node_may_fail(node) -> bool:
    if not isinstance(node, dict):
        return False
    execution = _v10_mapping(node.get("execution"))
    if execution.get("may_fail") is True:
        return True
    if str(node.get("type") or "") in {"action", "process"}:
        return True
    return str(_contract_field(node, "effect") or "") in SIDE_EFFECT_EFFECTS


def _v10_has_cycle(edges: list[dict]) -> bool:
    """A loop edge is the only sanctioned way to close a cycle."""
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        if edge["kind"] == "loop":
            continue
        adjacency.setdefault(edge["from"], []).append(edge["to"])
    active: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in active:
            return True
        if node_id in visited:
            return False
        visited.add(node_id)
        active.add(node_id)
        if any(visit(target) for target in adjacency.get(node_id, [])):
            return True
        active.remove(node_id)
        return False

    return any(visit(node_id) for node_id in adjacency)


def _v10_mapping(value) -> dict:
    return value if isinstance(value, dict) else {}


def _v10_string(value) -> str:
    return str(value or "").strip()


def _v10_string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _v10_positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _edge_finding(severity: str, code: str, edge_id: str, message: str) -> dict:
    return {"severity": severity, "code": code, "edge_id": edge_id, "message": message}
