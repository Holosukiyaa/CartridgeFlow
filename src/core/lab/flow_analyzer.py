"""Deterministic CF-FARP flow analysis without executing cartridge code."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from copy import deepcopy

from core.orchestration import ExecutionPlanCompileError, compile_execution_plan


ANALYSIS_SCHEMA = "cartridgeflow.flow_analysis.v1"
ANALYSIS_VERSION = "flow-analysis.v1"
ANALYSIS_TARGETS = {"draft", "dev", "preview", "production", "package", "publish"}
CONTROL_KINDS = {"control", "branch", "action_route", "failure_route"}
SIDE_EFFECTS = {"writes_files", "mutates_state", "external_side_effect"}
SECRET_KEYS = {"api_key", "authorization", "credential", "headers", "key", "secret", "token"}
TRANSPARENCY_LEVELS = {"atomic", "declared_graph", "contract_only", "opaque", "legacy_opaque"}


def analyze_flow(
    root_flow: dict | None,
    manifest: dict | None = None,
    *,
    target: str = "dev",
    base: dict | None = None,
) -> dict:
    """Compile authoring facts into topology, relations, and stable findings."""
    root_flow = deepcopy(root_flow) if isinstance(root_flow, dict) else {}
    manifest = deepcopy(manifest) if isinstance(manifest, dict) else {}
    base = deepcopy(base) if isinstance(base, dict) else {}
    target = target if target in ANALYSIS_TARGETS else "dev"
    states = root_flow.get("states") if isinstance(root_flow.get("states"), dict) else {}
    findings: list[dict] = []
    relations: list[dict] = []

    def add(
        code: str,
        message: str,
        *,
        stage: str,
        node_id: str | None = None,
        path: str | None = None,
        severity: str = "blocker",
        **extra,
    ) -> None:
        identity = ":".join(item for item in [code, node_id or "flow", path or ""] if item)
        finding = {
            "id": f"finding:{identity}",
            "severity": severity,
            "code": code,
            "stage": stage,
            "message": message,
        }
        if node_id:
            finding["node_id"] = node_id
        if path:
            finding["path"] = path
        finding.update(extra)
        findings.append(finding)

    protocol = _protocol_identity(root_flow, manifest)
    if protocol == ("CF-FARP", "1.0"):
        return _analyze_v10_execution_plan(root_flow, manifest, target=target, base=base)
    if protocol[0] != "CF-FARP" or protocol[1] not in {"0.8", "0.9"}:
        add(
            "PROTOCOL_UNSUPPORTED",
            f"Flow Analyzer requires CF-FARP@0.8 or CF-FARP@0.9, got {protocol[0]}@{protocol[1]}.",
            stage="protocol_structure",
            path="protocol",
        )
    if not states:
        add("FLOW_STATES_MISSING", "root_flow.states must be a non-empty object.", stage="protocol_structure", path="states")
    start = str(root_flow.get("start") or "")
    if not start or start not in states:
        add("START_NODE_MISSING", "root_flow.start must point to an existing node.", stage="topology", path="start")

    edges = _collect_control_edges(root_flow, states, add)
    adjacency = {node_id: [] for node_id in states}
    predecessors = {node_id: [] for node_id in states}
    for edge in edges:
        source, target_node = edge["from"], edge["to"]
        if source in states and target_node in states:
            adjacency[source].append(target_node)
            predecessors[target_node].append(source)
        relations.append({
            "id": f"relation:{edge['id']}",
            "kind": edge["kind"],
            "from": {"type": "node", "node_id": source},
            "to": {"type": "node", "node_id": target_node},
            "derived_from": edge["derived_from"],
            "confidence": "deterministic",
            "runtime_effect": True,
        })

    reachable = _reachable(start, adjacency)
    for node_id, node in states.items():
        if node_id not in reachable and not _is_isolated_marked(node):
            add(
                "NODE_UNREACHABLE",
                f"Node {node_id} is not reachable from start.",
                stage="topology",
                node_id=node_id,
                path=f"states.{node_id}",
            )
        if node.get("type") == "terminal" and adjacency.get(node_id):
            add(
                "TERMINAL_HAS_SUCCESSOR",
                f"Terminal node {node_id} must not have a successor.",
                stage="topology",
                node_id=node_id,
                path=f"states.{node_id}",
            )
        if node.get("type") == "process" and node_id in reachable and not adjacency.get(node_id):
            add(
                "NODE_EXIT_MISSING",
                f"Process node {node_id} has no executable exit.",
                stage="topology",
                node_id=node_id,
                path=f"states.{node_id}",
            )
    for cycle in _uncontrolled_cycles(adjacency):
        add(
            "UNCONTROLLED_CYCLE",
            f"Control cycle has no declared iteration guard: {' -> '.join(cycle)}.",
            stage="topology",
            path="control_edges",
            evidence=cycle,
        )

    producer_by_store: dict[str, list[tuple[str, str, dict]]] = defaultdict(list)
    producer_by_artifact: dict[str, list[tuple[str, str, dict]]] = defaultdict(list)
    node_outputs: dict[tuple[str, str], dict] = {}
    consumers: list[tuple[str, str, dict, dict]] = []
    declared_tools = {
        str(item.get("id")): item
        for item in manifest.get("mcp_tools") or []
        if isinstance(item, dict) and item.get("id")
    }
    if protocol == ("CF-FARP", "0.9"):
        _validate_tool_transparency(manifest, declared_tools, add, protocol_version="0.9")
    roles = {
        str(item.get("id"))
        for item in ((manifest.get("llm_recipe") or {}).get("roles") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for reserved_role in sorted(roles & {"authoring", "mentor"}):
        add(
            "AUTHORING_MODEL_SCOPE_LEAK",
            f"Authoring role {reserved_role} must not be declared in cartridge llm_recipe.",
            stage="resources",
            path=f"manifest.llm_recipe.roles.{reserved_role}",
        )

    for node_id, node in states.items():
        if node.get("type") != "process":
            continue
        node_path = f"states.{node_id}"
        inputs = node.get("inputs")
        outputs = node.get("outputs")
        if not isinstance(inputs, dict):
            add("INPUT_CONTRACT_MISSING", f"Node {node_id} requires an inputs object.", stage="dataflow", node_id=node_id, path=f"{node_path}.inputs")
            inputs = {}
        if not isinstance(outputs, dict):
            add("OUTPUT_CONTRACT_MISSING", f"Node {node_id} requires an outputs object.", stage="dataflow", node_id=node_id, path=f"{node_path}.outputs")
            outputs = {}
        if any(key in node for key in ("input", "optional_input", "output")):
            add(
                "LEGACY_IO_CONTRACT",
                f"Node {node_id} still contains v0.7 input/output fields.",
                stage="dataflow",
                node_id=node_id,
                path=node_path,
                severity="warning" if target in {"draft", "dev"} else "blocker",
            )

        for output_name, contract in outputs.items():
            path = f"{node_path}.outputs.{output_name}"
            if not isinstance(contract, dict) or not _has_exactly_one_schema(contract):
                add("OUTPUT_CONTRACT_MISSING", f"Output {node_id}.{output_name} requires exactly one schema or schema_ref.", stage="dataflow", node_id=node_id, path=path)
                continue
            target_doc = contract.get("target") if isinstance(contract.get("target"), dict) else {}
            target_type = str(target_doc.get("type") or "")
            if target_type == "store" and target_doc.get("key"):
                producer_by_store[str(target_doc["key"])].append((node_id, str(output_name), contract))
            elif target_type == "artifact" and target_doc.get("artifact_id"):
                producer_by_artifact[str(target_doc["artifact_id"])].append((node_id, str(output_name), contract))
            else:
                add("OUTPUT_CONTRACT_MISSING", f"Output {node_id}.{output_name} has no valid store/artifact target.", stage="dataflow", node_id=node_id, path=f"{path}.target")
            node_outputs[(node_id, str(output_name))] = contract

        for input_name, contract in inputs.items():
            path = f"{node_path}.inputs.{input_name}"
            if not isinstance(contract, dict) or not _has_exactly_one_schema(contract) or not isinstance(contract.get("required"), bool):
                add("INPUT_CONTRACT_MISSING", f"Input {node_id}.{input_name} requires required and exactly one schema or schema_ref.", stage="dataflow", node_id=node_id, path=path)
                continue
            binding = contract.get("binding")
            if contract.get("required") and not isinstance(binding, dict):
                add("INPUT_SOURCE_MISSING", f"Required input {node_id}.{input_name} has no binding.", stage="dataflow", node_id=node_id, path=f"{path}.binding")
                continue
            if isinstance(binding, dict):
                consumers.append((node_id, str(input_name), contract, binding))

        model_role = str(node.get("model_role") or "")
        if model_role:
            relations.append(_resource_relation("model_dependency", node_id, "model_role", model_role, f"{node_path}.model_role"))
            if model_role not in roles:
                add("MODEL_ROLE_UNDECLARED", f"Node {node_id} references undeclared model role {model_role}.", stage="resources", node_id=node_id, path=f"{node_path}.model_role")
        allowed_tools = _string_list(node.get("allowed_tools"))
        for tool_id in allowed_tools:
            declared_tool = declared_tools.get(tool_id) or {}
            tool_kind = "mcp_dependency" if declared_tool.get("type") in {"mcp", "cartridge_dlc", "local_resource", "remote_mcp"} else "tool_dependency"
            relations.append(_resource_relation(tool_kind, node_id, "tool", tool_id, f"{node_path}.allowed_tools"))
            if protocol == ("CF-FARP", "0.9") and declared_tool:
                transparency = str(declared_tool.get("transparency") or "legacy_opaque").strip()
                relations.append(_resource_relation("tool_operation", node_id, "tool_transparency", transparency, f"manifest.mcp_tools.{tool_id}.transparency"))
            if tool_id not in declared_tools:
                add("TOOL_UNDECLARED", f"Node {node_id} references undeclared tool {tool_id}.", stage="resources", node_id=node_id, path=f"{node_path}.allowed_tools")
        component_ref = str(node.get("component_ref") or "")
        if component_ref:
            relations.append(_resource_relation("component_dependency", node_id, "component", component_ref, f"{node_path}.component_ref"))

        effect = str(node.get("effect") or "")
        if effect in SIDE_EFFECTS:
            required_policy_fields = ["permission", "failure_policy", "audit_log", "replay_policy"]
            missing_policy = [field for field in required_policy_fields if node.get(field) in (None, "", False)]
            if missing_policy:
                add(
                    "EFFECT_PERMISSION_MISMATCH" if "permission" in missing_policy else "REPLAY_POLICY_MISSING",
                    f"Side-effect node {node_id} is missing: {', '.join(missing_policy)}.",
                    stage="effects",
                    node_id=node_id,
                    path=node_path,
                    evidence=missing_policy,
                )

    for identity, producers in [*[(f"store:{key}", value) for key, value in producer_by_store.items()], *[(f"artifact:{key}", value) for key, value in producer_by_artifact.items()]]:
        if len(producers) > 1:
            add("OUTPUT_IDENTITY_CONFLICT", f"Output identity {identity} has multiple producers.", stage="dataflow", path="states", evidence=[item[0] for item in producers])

    dominators = _dominators(start, set(states), predecessors, reachable)
    for node_id, input_name, contract, binding in consumers:
        source = str(binding.get("source") or "")
        source_node = ""
        source_port = ""
        producer_contract = None
        if source == "node_output":
            source_node = str(binding.get("node_id") or "")
            source_port = str(binding.get("output") or "")
            producer_contract = node_outputs.get((source_node, source_port))
        elif source == "store":
            candidates = producer_by_store.get(str(binding.get("key") or ""), [])
            if len(candidates) == 1:
                source_node, source_port, producer_contract = candidates[0]
            elif len(candidates) > 1:
                add("INPUT_SOURCE_AMBIGUOUS", f"Input {node_id}.{input_name} resolves to multiple Store producers.", stage="dataflow", node_id=node_id, path=f"states.{node_id}.inputs.{input_name}.binding")
        elif source == "artifact":
            candidates = producer_by_artifact.get(str(binding.get("artifact_id") or ""), [])
            if len(candidates) == 1:
                source_node, source_port, producer_contract = candidates[0]
        elif source in {"run_input", "interaction_answer", "constant"}:
            producer_contract = contract
        else:
            add("INPUT_SOURCE_MISSING", f"Input {node_id}.{input_name} has an unsupported binding source.", stage="dataflow", node_id=node_id, path=f"states.{node_id}.inputs.{input_name}.binding")

        if producer_contract is None:
            add("INPUT_SOURCE_MISSING", f"Input {node_id}.{input_name} does not resolve to a producer.", stage="dataflow", node_id=node_id, path=f"states.{node_id}.inputs.{input_name}.binding")
            continue
        if source_node:
            relations.append({
                "id": f"relation:data:{source_node}:{source_port}:{node_id}:{input_name}",
                "kind": "artifact_dependency" if source == "artifact" else "data",
                "from": {"type": "node_output", "node_id": source_node, "port": source_port},
                "to": {"type": "node_input", "node_id": node_id, "port": input_name},
                "derived_from": [f"states.{source_node}.outputs.{source_port}", f"states.{node_id}.inputs.{input_name}.binding"],
                "confidence": "deterministic",
                "runtime_effect": False,
            })
            if source_node not in dominators.get(node_id, set()):
                add("INPUT_NOT_AVAILABLE_ON_ALL_PATHS", f"Input {node_id}.{input_name} is not produced on every reachable path.", stage="dataflow", node_id=node_id, path=f"states.{node_id}.inputs.{input_name}.binding", evidence=[source_node])
            projected_producer = _contract_at_binding_path(producer_contract, binding.get("path"))
            if not _schemas_compatible(projected_producer, contract):
                add("INPUT_SCHEMA_INCOMPATIBLE", f"Input {node_id}.{input_name} is incompatible with {source_node}.{source_port}.", stage="dataflow", node_id=node_id, path=f"states.{node_id}.inputs.{input_name}")

    source_digest = build_source_digest(manifest, root_flow, base)
    analysis_id = f"analysis:{source_digest.split(':', 1)[-1][:24]}"
    counts = {severity: sum(1 for item in findings if item["severity"] == severity) for severity in ("blocker", "warning", "info")}
    complete = bool(states) and not any(item["stage"] == "protocol_structure" and item["severity"] == "blocker" for item in findings)
    return {
        "schema": ANALYSIS_SCHEMA,
        "analysis_version": ANALYSIS_VERSION,
        "analysis_id": analysis_id,
        "analyzer": {"implementation_id": "cartridgeflow.reference.flow-analyzer", "implementation_version": "0.9.0"},
        "protocol": {"id": protocol[0], "version": protocol[1]},
        "target": target,
        "source_digest": source_digest,
        "normalized_topology": {"start": start, "control_edges": edges},
        "relations": _dedupe_by_id(relations),
        "findings": _dedupe_by_id(findings),
        "coverage": {
            "complete": complete,
            "stages": ["protocol_structure", "topology", "dataflow", "resources", "branches", "effects", "delivery"],
        },
        "summary": {
            "blockers": counts["blocker"],
            "warnings": counts["warning"],
            "infos": counts["info"],
            "runnable": complete and counts["blocker"] == 0,
            "packagable": complete and counts["blocker"] == 0 and target in {"package", "publish"},
            "publishable": complete and counts["blocker"] == 0 and counts["warning"] == 0 and target == "publish",
        },
    }


def _analyze_v10_execution_plan(root_flow: dict, manifest: dict, *, target: str, base: dict) -> dict:
    """Project only compiler-approved CF-FARP@1.0 transitions for consumers.

    The v1.0 contract deliberately makes ``execution_plan.edges`` the only
    source of executable topology.  Keeping this boundary here prevents the
    analyzer and every consumer of its relations from accidentally treating a
    legacy canvas relation as a runner transition.
    """
    source_digest = build_source_digest(manifest, root_flow, base)
    analysis_id = f"analysis:{source_digest.split(':', 1)[-1][:24]}"
    try:
        plan = compile_execution_plan(root_flow)
    except ExecutionPlanCompileError as error:
        findings = _v10_compile_findings(error.findings, root_flow)
        counts = _finding_counts(findings)
        return {
            "schema": ANALYSIS_SCHEMA,
            "analysis_version": ANALYSIS_VERSION,
            "analysis_id": analysis_id,
            "analyzer": {"implementation_id": "cartridgeflow.reference.flow-analyzer", "implementation_version": "1.0.0"},
            "protocol": {"id": "CF-FARP", "version": "1.0"},
            "target": target,
            "source_digest": source_digest,
            "normalized_topology": {"start": _v10_entry(root_flow), "control_edges": []},
            "relations": [],
            "findings": findings,
            "execution_plan": {
                "status": "rejected",
                "compiler": {"id": "cartridgeflow.execution-plan-compiler", "version": "1.0.0"},
                "diagnostic_code": error.code,
                "edge_count": 0,
            },
            "coverage": {"complete": False, "stages": ["protocol_structure", "execution_plan"]},
            "summary": {
                "blockers": counts["blocker"],
                "warnings": counts["warning"],
                "infos": counts["info"],
                "runnable": False,
                "packagable": False,
                "publishable": False,
            },
        }

    relations = _v10_plan_relations(plan, root_flow)
    topology = [
        {
            "id": relation["plan_edge_id"],
            "kind": relation["plan_edge_kind"],
            "from": relation["from"]["node_id"],
            "to": relation["to"]["node_id"],
            "derived_from": relation["derived_from"],
            "plan_transition": relation["plan_transition"],
        }
        for relation in relations
    ]
    runtime_supported = _v10_base_runtime_supported(base)
    findings = [] if runtime_supported else [_v10_runtime_unsupported_finding(base)]

    def add(code: str, message: str, *, stage: str, path: str | None = None, severity: str = "blocker", **extra) -> None:
        finding = {
            "id": f"finding:{code}:flow:{path or ''}",
            "severity": severity,
            "code": code,
            "stage": stage,
            "message": message,
            **extra,
        }
        if path:
            finding["path"] = path
        findings.append(finding)

    declared_tools = {
        str(tool.get("id")): tool
        for tool in manifest.get("mcp_tools") or []
        if isinstance(tool, dict) and str(tool.get("id") or "").strip()
    }
    _validate_tool_transparency(manifest, declared_tools, add, protocol_version="1.0")
    counts = _finding_counts(findings)
    return {
        "schema": ANALYSIS_SCHEMA,
        "analysis_version": ANALYSIS_VERSION,
        "analysis_id": analysis_id,
        "analyzer": {"implementation_id": "cartridgeflow.reference.flow-analyzer", "implementation_version": "1.0.0"},
        "protocol": {"id": "CF-FARP", "version": "1.0"},
        "target": target,
        "source_digest": source_digest,
        "normalized_topology": {"start": plan["entry"], "control_edges": topology},
        "relations": relations,
        "findings": findings,
        "execution_plan": {
            "status": "compiled",
            "runtime_status": "supported" if runtime_supported else "unsupported",
            "schema": plan["schema"],
            "plan_id": plan["plan_id"],
            "plan_digest": plan["plan_digest"],
            "source_digest": plan["source_digest"],
            "entry": plan["entry"],
            "edge_count": len(plan["edges"]),
        },
        "coverage": {"complete": runtime_supported, "stages": ["protocol_structure", "execution_plan", "runtime_support"]},
        "summary": {
            "blockers": counts["blocker"],
            "warnings": counts["warning"],
            "infos": counts["info"],
            "runnable": runtime_supported,
            "packagable": runtime_supported and target in {"package", "publish"},
            "publishable": runtime_supported and target == "publish",
        },
    }


def _v10_base_runtime_supported(base: dict) -> bool:
    """Base support is the only authority that can open v1.0 runtime gates."""
    supported = base.get("supported_protocols") if isinstance(base.get("supported_protocols"), list) else []
    return any(
        isinstance(item, dict)
        and item.get("id") == "CF-FARP"
        and str(item.get("version")) == "1.0"
        and item.get("status") in {"partial", "supported"}
        for item in supported
    )


def _v10_runtime_unsupported_finding(base: dict) -> dict:
    implementation_id = str(base.get("implementation_id") or "当前 Base")
    return {
        "id": "finding:v10_base_runtime_unsupported:flow:base.supported_protocols",
        "severity": "blocker",
        "code": "v10_base_runtime_unsupported",
        "stage": "runtime_support",
        "path": "base.supported_protocols",
        "message": f"{implementation_id} 尚未声明 CF-FARP@1.0 运行时支持；ExecutionPlan 仅可用于工程投影，不能运行、打包或发布。",
    }


def _v10_plan_relations(plan: dict, root_flow: dict) -> list[dict]:
    raw_edges = _v10_raw_edges(root_flow)
    raw_path_by_id = {
        str(edge.get("id") or "").strip(): f"execution_plan.edges.{index}"
        for index, edge in enumerate(raw_edges)
        if isinstance(edge, dict) and str(edge.get("id") or "").strip()
    }
    relations: list[dict] = []
    for edge in plan["edges"]:
        edge_id = edge["id"]
        derived_from = [raw_path_by_id.get(edge_id, "execution_plan.edges")]
        relations.append(_v10_plan_relation(
            edge,
            relation_id=f"relation:plan:{edge_id}",
            target=edge["to"],
            derived_from=derived_from,
        ))
        if edge["kind"] == "loop":
            exit_to = str((edge.get("loop") or {}).get("exit_to") or "").strip()
            if exit_to:
                relations.append(_v10_plan_relation(
                    edge,
                    relation_id=f"relation:plan:{edge_id}:exit",
                    target=exit_to,
                    derived_from=derived_from,
                    transition="loop_exit",
                ))
    return relations


def _v10_plan_relation(edge: dict, *, relation_id: str, target: str, derived_from: list[str], transition: str = "transition") -> dict:
    return {
        "id": relation_id,
        "kind": "execution_plan_edge",
        "from": {"type": "node", "node_id": edge["from"]},
        "to": {"type": "node", "node_id": target},
        "derived_from": derived_from,
        "confidence": "deterministic",
        "runtime_effect": True,
        "executable": True,
        "plan_edge_id": edge["id"],
        "plan_edge_kind": edge["kind"],
        "plan_transition": transition,
    }


def _v10_compile_findings(compiler_findings: tuple[dict, ...], root_flow: dict) -> list[dict]:
    findings: list[dict] = []
    for index, raw in enumerate(compiler_findings):
        finding = dict(raw)
        code = str(finding.get("code") or "execution_plan_contract_invalid")
        edge_id = str(finding.get("edge_id") or "").strip()
        node_id = str(finding.get("node_id") or "").strip()
        path = _v10_finding_path(root_flow, code, edge_id, index)
        if not node_id:
            node_id = _v10_finding_node(root_flow, code, edge_id)
        item = {
            "id": f"finding:{code}:{edge_id or node_id or 'flow'}:{path}",
            "severity": str(finding.get("severity") or "blocker"),
            "code": code,
            "stage": "execution_plan",
            "message": _v10_diagnostic_message(code, edge_id, node_id),
            "path": path,
        }
        if node_id:
            item["node_id"] = node_id
        if edge_id:
            item["edge_id"] = edge_id
        findings.append(item)
    if findings:
        return _dedupe_by_id(findings)
    return [{
        "id": "finding:execution_plan_contract_invalid:flow:execution_plan",
        "severity": "blocker",
        "code": "execution_plan_contract_invalid",
        "stage": "execution_plan",
        "message": "执行计划无法编译，未生成任何可执行路线。请补全 CF-FARP@1.0 的 execution_plan 声明后重新分析。",
        "path": "execution_plan",
    }]


def _v10_finding_path(root_flow: dict, code: str, edge_id: str, index: int) -> str:
    if edge_id:
        for edge_index, edge in enumerate(_v10_raw_edges(root_flow)):
            if isinstance(edge, dict) and str(edge.get("id") or "").strip() == edge_id:
                return f"execution_plan.edges.{edge_index}"
    if code == "v10_legacy_control_edges_forbidden":
        return "control_edges"
    if code == "v10_legacy_edges_forbidden":
        return "edges"
    if code in {"v10_legacy_action_route_forbidden", "v10_legacy_failure_route_forbidden", "v10_implicit_sequence_forbidden"}:
        return "states"
    if code == "v10_implicit_join_forbidden":
        return "execution_plan.edges"
    return "execution_plan" if index == 0 else f"execution_plan.findings.{index}"


def _v10_finding_node(root_flow: dict, code: str, edge_id: str) -> str:
    if edge_id:
        for edge in _v10_raw_edges(root_flow):
            if isinstance(edge, dict) and str(edge.get("id") or "").strip() == edge_id:
                return str(edge.get("from") or "").strip()
    states = root_flow.get("states") if isinstance(root_flow.get("states"), dict) else {}
    if code == "v10_implicit_join_forbidden":
        incoming: dict[str, int] = defaultdict(int)
        for edge in _v10_raw_edges(root_flow):
            if isinstance(edge, dict) and str(edge.get("kind") or "") != "failure":
                target = str(edge.get("to") or "").strip()
                if target:
                    incoming[target] += 1
        return next((node_id for node_id, count in sorted(incoming.items()) if count > 1), "")
    for node_id, node in states.items():
        if not isinstance(node, dict):
            continue
        if code == "v10_implicit_sequence_forbidden" and node.get("next"):
            return str(node_id)
        if code == "v10_legacy_action_route_forbidden" and (node.get("action_route") or node.get("action_routes")):
            return str(node_id)
        if code == "v10_legacy_failure_route_forbidden" and node.get("failure_route"):
            return str(node_id)
    return ""


def _v10_diagnostic_message(code: str, edge_id: str, node_id: str) -> str:
    edge = f"计划边“{edge_id}”" if edge_id else "该关系"
    node = f"节点“{node_id}”" if node_id else "该流程"
    if code == "v10_legacy_action_route_forbidden":
        return f"{node} 使用了旧 action_route/action_routes；它在 CF-FARP@1.0 中没有执行语义，已不作为运行路线。请改为 execution_plan.edges 中带稳定 id 的 sequence、fork 或其他受支持计划边。"
    if code == "v10_legacy_failure_route_forbidden":
        return f"{node} 使用了旧 failure_route；它在 CF-FARP@1.0 中没有执行语义，已不作为运行路线。请声明带 failure.id 与 causes 的 failure 计划边。"
    if code in {"v10_legacy_edges_forbidden", "v10_legacy_control_edges_forbidden"}:
        return "检测到旧版画布连线；它们不能驱动 CF-FARP@1.0 执行，已不作为运行路线。请将关系迁移到 execution_plan.edges，并为每条边声明稳定 id。"
    if code == "v10_implicit_sequence_forbidden":
        return f"{node} 使用 node.next 推导下一步；该隐式路线不可执行。请删除 next，并在 execution_plan.edges 中声明 sequence 计划边。"
    if code == "v10_visible_non_executable_edge":
        return f"{edge} 被标记为不可执行；CF-FARP@1.0 不允许把装饰线伪装成计划边。请删除该线，或声明完整且可执行的计划边。"
    if code == "v10_implicit_join_forbidden":
        return f"{node} 存在未声明的隐式合流；多个 token 不能靠画布位置自动合并。请为每条入边声明同一 join.id、完整 branches 和 join 模式。"
    if code in {"v10_execution_plan_missing", "v10_execution_plan_schema_invalid"}:
        return "缺少有效的 execution_plan；当前没有可执行路线。请声明 execution_plan.schema、entry 和 edges 后重新分析。"
    if code.startswith("v10_fork"):
        return f"{edge} 的 fork 声明不完整或不一致，无法编译。请使用同一 fork.id、同一来源及至少两个唯一 branch。"
    if code.startswith("v10_join") or code.startswith("v10_any_join") or code.startswith("v10_keyed_join"):
        return f"{edge} 的 join 声明不完整或不一致，无法编译。请补全统一的 join.id、mode、branches，并按模式声明 remaining 或 key_ref。"
    if code.startswith("v10_loop") or code == "v10_implicit_cycle_forbidden":
        return f"{edge} 的循环没有可验证的有界语义，无法执行。请声明正整数 max_iterations、continue_when 和有效 exit_to，并避免普通边闭环。"
    if code.startswith("v10_batch"):
        return f"{edge} 的批处理参数无法编译。请补全 batch.id、items_ref、size、max_concurrency 和 ordering。"
    if code.startswith("v10_wait"):
        return f"{edge} 的等待或超时失败出口不完整，无法执行。请补全 wait 配置，并声明包含 timeout cause 的 failure 计划边。"
    if code.startswith("v10_failure"):
        return f"{edge} 缺少可执行的失败处理。请声明带稳定 failure.id 和合法 causes 的 failure 计划边。"
    if code.startswith("v10_execution_edge"):
        return f"{edge} 的标识、种类或端点不符合执行计划要求，无法编译。请使用受支持 kind，并指向已声明的状态。"
    if code == "v10_ambiguous_successor_forbidden":
        return f"{node} 有多条未声明 fork 的成功路线，执行器无法猜测选择规则。请改为一个成功计划边，或使用完整 fork 组。"
    return f"{edge} 不符合 CF-FARP@1.0 执行计划约束，无法编译或执行。请根据诊断代码“{code}”补全显式计划语义。"


def _v10_raw_edges(root_flow: dict) -> list:
    plan = root_flow.get("execution_plan") if isinstance(root_flow.get("execution_plan"), dict) else {}
    edges = plan.get("edges")
    return edges if isinstance(edges, list) else []


def _v10_entry(root_flow: dict) -> str:
    plan = root_flow.get("execution_plan") if isinstance(root_flow.get("execution_plan"), dict) else {}
    return str(plan.get("entry") or "").strip()


def _finding_counts(findings: list[dict]) -> dict[str, int]:
    return {severity: sum(1 for item in findings if item.get("severity") == severity) for severity in ("blocker", "warning", "info")}


def build_source_digest(manifest: dict, root_flow: dict, base: dict | None = None) -> str:
    base = base if isinstance(base, dict) else {}
    payload = {
        "manifest": _redact_secrets(manifest),
        "root_flow": _without_layout(root_flow),
        "base": {
            "implementation_id": base.get("implementation_id"),
            "base_contract": base.get("base_contract"),
            "supported_protocols": base.get("supported_protocols") or [],
            "profiles": sorted(base.get("profiles") or []),
            "capabilities": sorted(base.get("capabilities") or []),
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _validate_tool_transparency(manifest: dict, declared_tools: dict[str, dict], add, *, protocol_version: str) -> None:
    runtime = manifest.get("runtime_contract") if isinstance(manifest.get("runtime_contract"), dict) else {}
    if "tool_transparency" not in (runtime.get("required_profiles") or []):
        add(
            "TOOL_TRANSPARENCY_PROFILE_MISSING",
            f"CF-FARP@{protocol_version} cartridges must require the tool_transparency profile.",
            stage="protocol_structure",
            path="manifest.runtime_contract.required_profiles",
        )
    portable = manifest.get("portable_dlc") if isinstance(manifest.get("portable_dlc"), dict) else {}
    if portable and portable.get("protocol") != f"CF-FARP@{protocol_version}":
        add(
            "PORTABLE_DLC_PROTOCOL_MISMATCH",
            f"CF-FARP@{protocol_version} portable DLC must declare protocol CF-FARP@{protocol_version}.",
            stage="resources",
            path="manifest.portable_dlc.protocol",
        )
    for tool_id, tool in declared_tools.items():
        tool_type = str(tool.get("type") or "builtin").strip()
        transparency = str(tool.get("transparency") or "").strip()
        if not transparency:
            add(
                "TOOL_TRANSPARENCY_MISSING",
                f"Tool {tool_id} must declare transparency for CF-FARP@{protocol_version}.",
                stage="resources",
                path=f"manifest.mcp_tools.{tool_id}.transparency",
            )
            continue
        if transparency not in TRANSPARENCY_LEVELS:
            add(
                "TOOL_TRANSPARENCY_INVALID",
                f"Tool {tool_id} declares unknown transparency level {transparency}.",
                stage="resources",
                path=f"manifest.mcp_tools.{tool_id}.transparency",
            )
            continue
        if tool_type == "cartridge_dlc":
            if not str(tool.get("node_id") or "").strip():
                add(
                    "MCP_NODE_ID_MISSING",
                    f"Cartridge DLC tool {tool_id} must declare node_id.",
                    stage="resources",
                    path=f"manifest.mcp_tools.{tool_id}.node_id",
                )
            if transparency == "legacy_opaque":
                add(
                    "LEGACY_OPAQUE_V09_TOOL",
                    f"Cartridge DLC tool {tool_id} cannot be legacy_opaque in a CF-FARP@{protocol_version} cartridge.",
                    stage="resources",
                    path=f"manifest.mcp_tools.{tool_id}.transparency",
                )
            if transparency == "declared_graph" and not manifest.get("portable_dlc"):
                add(
                    "PORTABLE_DLC_DESCRIPTOR_MISSING",
                    f"Declared graph tool {tool_id} requires manifest.portable_dlc.",
                    stage="resources",
                    path="manifest.portable_dlc",
                )
        if tool_type == "remote_mcp" and transparency not in {"contract_only", "opaque"}:
            add(
                "REMOTE_MCP_TRANSPARENCY_INVALID",
                f"Remote MCP tool {tool_id} must use contract_only or opaque transparency.",
                stage="resources",
                path=f"manifest.mcp_tools.{tool_id}.transparency",
            )


def analyze_flow_structure(root_flow: dict) -> dict:
    """Legacy topology-only adapter retained for v0.6/v0.7 callers."""
    states = root_flow.get("states") or {}
    start = root_flow.get("start")
    outgoing = {state_id: [] for state_id in states}
    for state_id, state in states.items():
        if state.get("next") in states:
            outgoing[state_id].append(state["next"])
    for edge in root_flow.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = edge.get("from") or edge.get("source")
        target = edge.get("to") or edge.get("target")
        if source in states and target in states and target not in outgoing[source]:
            outgoing[source].append(target)
    reachable = _reachable(start, outgoing)
    findings = []
    for state_id, state in states.items():
        if state_id == start or state_id in reachable:
            continue
        marked = _is_isolated_marked(state)
        findings.append({
            "type": "isolated_node",
            "severity": "info" if marked else "warning",
            "node": state_id,
            "title": state.get("title", state_id),
            "isolated": marked,
            "detail": "节点从 start 不可达，且已显式标记 params.isolated=true —— 故意隔离，符合预期。" if marked else "节点从 start 不可达且未标记 isolated；可能是意外断链。若为有意隔离，请加 params.isolated=true 以消除此告警。",
        })
    warnings = sum(1 for item in findings if item["severity"] == "warning")
    return {
        "findings": findings,
        "summary": {
            "isolated_total": len(findings),
            "isolated_intentional": sum(1 for item in findings if item.get("isolated")),
            "isolated_suspicious": warnings,
            "reachable_count": len(reachable),
            "node_count": len(states),
        },
    }


def _collect_control_edges(root_flow: dict, states: dict, add) -> list[dict]:
    result: list[dict] = []
    selectors: dict[tuple[str, str, str], str] = {}

    def append(kind: str, source: str, target: str, derived_from: str, selector: str = "") -> None:
        if kind not in CONTROL_KINDS:
            add("CONTROL_EDGE_KIND_INVALID", f"Unknown control edge kind: {kind}.", stage="topology", path=derived_from)
            return
        if source not in states or target not in states:
            add("CONTROL_TARGET_MISSING", f"Control relation {source} -> {target} references a missing node.", stage="topology", path=derived_from)
            return
        selector_key = (source, kind, selector)
        previous = selectors.get(selector_key)
        if previous and previous != target:
            add("CONTROL_EDGE_CONFLICT", f"Control selector {source}/{kind}/{selector or 'default'} has conflicting targets.", stage="topology", node_id=source, path=derived_from)
            return
        selectors[selector_key] = target
        edge_id = ":".join(item for item in [kind, source, selector, target] if item)
        for item in result:
            if item["id"] == edge_id:
                item["derived_from"] = sorted(set([*item["derived_from"], derived_from]))
                return
        edge = {"id": edge_id, "kind": kind, "from": source, "to": target, "derived_from": [derived_from]}
        if selector:
            edge["selector"] = selector
        result.append(edge)

    for node_id, node in states.items():
        if node.get("next"):
            append("control", node_id, str(node["next"]), f"states.{node_id}.next")
        for field, kind in (("routes", "branch"), ("action_routes", "action_route")):
            routes = node.get(field)
            if not isinstance(routes, dict):
                continue
            for selector, route in routes.items():
                target = route.get("target") if isinstance(route, dict) else route
                if target:
                    append(kind, node_id, str(target), f"states.{node_id}.{field}.{selector}", str(selector))
        failure_route = node.get("failure_route")
        if failure_route:
            target = failure_route.get("target") if isinstance(failure_route, dict) else failure_route
            selector = str(failure_route.get("selector") or "failure") if isinstance(failure_route, dict) else "failure"
            if target:
                append("failure_route", node_id, str(target), f"states.{node_id}.failure_route", selector)

    if root_flow.get("edges"):
        add("DERIVED_RELATION_IN_CONTROL_GRAPH", "v0.8/v0.9 do not permit legacy root_flow.edges; migrate executable facts to control_edges.", stage="topology", path="edges")
    raw_edges = root_flow.get("control_edges") or []
    if not isinstance(raw_edges, list):
        add("CONTROL_EDGE_KIND_INVALID", "root_flow.control_edges must be an array.", stage="topology", path="control_edges")
        return result
    for index, edge in enumerate(raw_edges):
        path = f"control_edges.{index}"
        if not isinstance(edge, dict):
            add("CONTROL_EDGE_KIND_INVALID", "Control edge must be an object.", stage="topology", path=path)
            continue
        append(str(edge.get("kind") or ""), str(edge.get("from") or ""), str(edge.get("to") or ""), path, str(edge.get("condition_id") or edge.get("action_id") or edge.get("selector") or ""))
    return result


def _protocol_identity(root_flow: dict, manifest: dict) -> tuple[str, str]:
    protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
    runtime = manifest.get("runtime_contract") if isinstance(manifest.get("runtime_contract"), dict) else {}
    return str(protocol.get("id") or runtime.get("protocol") or ""), str(protocol.get("version") or runtime.get("protocol_version") or "")


def _has_exactly_one_schema(contract: dict) -> bool:
    return sum(1 for key in ("schema", "schema_ref") if contract.get(key) not in (None, "")) == 1


def _schemas_compatible(producer: dict, consumer: dict) -> bool:
    producer_ref, consumer_ref = producer.get("schema_ref"), consumer.get("schema_ref")
    if producer_ref or consumer_ref:
        return bool(producer_ref and consumer_ref and producer_ref == consumer_ref)
    producer_schema = producer.get("schema") if isinstance(producer.get("schema"), dict) else {}
    consumer_schema = consumer.get("schema") if isinstance(consumer.get("schema"), dict) else {}
    producer_type, consumer_type = producer_schema.get("type"), consumer_schema.get("type")
    if producer_type and consumer_type and producer_type != consumer_type:
        return False
    producer_properties = producer_schema.get("properties") if isinstance(producer_schema.get("properties"), dict) else {}
    for required in consumer_schema.get("required") or []:
        if required not in producer_properties:
            return False
    return True


def _contract_at_binding_path(contract: dict, path: object) -> dict:
    if not isinstance(path, str) or not path.strip():
        return contract
    schema = contract.get("schema") if isinstance(contract.get("schema"), dict) else None
    if schema is None:
        return contract
    current = schema
    for segment in path.split("."):
        if not segment:
            continue
        if current.get("type") == "array" and segment.isdigit():
            current = current.get("items") if isinstance(current.get("items"), dict) else {}
            continue
        properties = current.get("properties") if isinstance(current.get("properties"), dict) else {}
        next_schema = properties.get(segment)
        if not isinstance(next_schema, dict):
            return contract
        current = next_schema
    return {"schema": current}


def _resource_relation(kind: str, node_id: str, target_type: str, target_id: str, path: str) -> dict:
    return {
        "id": f"relation:{kind}:{node_id}:{target_id}",
        "kind": kind,
        "from": {"type": "node", "node_id": node_id},
        "to": {"type": target_type, "id": target_id},
        "derived_from": [path],
        "confidence": "deterministic",
        "runtime_effect": False,
    }


def _reachable(start: str, adjacency: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = [start] if start in adjacency else []
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(target for target in adjacency.get(node, []) if target not in seen)
    return seen


def _dominators(start: str, nodes: set[str], predecessors: dict[str, list[str]], reachable: set[str]) -> dict[str, set[str]]:
    dom = {node: ({node} if node == start else set(reachable)) for node in reachable}
    changed = True
    while changed:
        changed = False
        for node in reachable - {start}:
            parents = [parent for parent in predecessors.get(node, []) if parent in reachable]
            new = {node} | (set.intersection(*(dom[parent] for parent in parents)) if parents else set())
            if new != dom[node]:
                dom[node] = new
                changed = True
    return dom


def _uncontrolled_cycles(adjacency: dict[str, list[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            cycle = visiting[visiting.index(node):] + [node]
            if cycle not in cycles:
                cycles.append(cycle)
            return
        if node in visited:
            return
        visiting.append(node)
        for target in adjacency.get(node, []):
            visit(target)
        visiting.pop()
        visited.add(node)

    for node in adjacency:
        visit(node)
    return cycles


def _is_isolated_marked(state: dict) -> bool:
    params = state.get("params") or {}
    return bool(state.get("isolated") or state.get("experimental") or params.get("isolated") or (params.get("preset_config") or {}).get("isolated"))


def _string_list(value) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,\r\n]+", value) if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe_by_id(items: list[dict]) -> list[dict]:
    result, seen = [], set()
    for item in items:
        identity = item.get("id")
        if identity in seen:
            continue
        seen.add(identity)
        result.append(item)
    return result


def _redact_secrets(value):
    if isinstance(value, dict):
        return {key: ("<redacted>" if key.lower() in SECRET_KEYS else _redact_secrets(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _without_layout(value):
    if isinstance(value, dict):
        return {key: _without_layout(item) for key, item in value.items() if key not in {"layout", "annotations"}}
    if isinstance(value, list):
        return [_without_layout(item) for item in value]
    return value
