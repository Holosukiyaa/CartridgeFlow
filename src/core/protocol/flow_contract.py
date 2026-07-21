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
        if protocol_version != "0.6":
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
    protocol = root_flow.get("protocol")
    if isinstance(protocol, str):
        return protocol.strip() in {f"CF-FARP@{version}", f"CF-FARP-{version}"}
    if isinstance(protocol, dict):
        return str(protocol.get("id") or "") == "CF-FARP" and str(protocol.get("version") or "") == version
    return str(root_flow.get("protocol_id") or "") == "CF-FARP" and str(root_flow.get("protocol_version") or "") == version


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
