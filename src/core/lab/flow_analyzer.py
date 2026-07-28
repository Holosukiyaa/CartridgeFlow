"""Deterministic CF-FARP flow analysis without executing cartridge code."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from copy import deepcopy


ANALYSIS_SCHEMA = "cartridgeflow.flow_analysis.v1"
ANALYSIS_VERSION = "flow-analysis.v1"
ANALYSIS_TARGETS = {"draft", "dev", "preview", "production", "package", "publish"}
CONTROL_KINDS = {"control", "branch", "action_route", "failure_route"}
SIDE_EFFECTS = {"writes_files", "mutates_state", "external_side_effect"}
SECRET_KEYS = {"api_key", "authorization", "credential", "headers", "key", "secret", "token"}


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
    if protocol != ("CF-FARP", "0.8"):
        add(
            "PROTOCOL_UNSUPPORTED",
            f"Flow Analyzer v0.8 requires CF-FARP@0.8, got {protocol[0]}@{protocol[1]}.",
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
            tool_kind = "mcp_dependency" if (declared_tools.get(tool_id) or {}).get("type") == "mcp" else "tool_dependency"
            relations.append(_resource_relation(tool_kind, node_id, "tool", tool_id, f"{node_path}.allowed_tools"))
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
        "analyzer": {"implementation_id": "cartridgeflow.reference.flow-analyzer", "implementation_version": "0.8.0"},
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
        add("DERIVED_RELATION_IN_CONTROL_GRAPH", "v0.8 does not permit legacy root_flow.edges; migrate executable facts to control_edges.", stage="topology", path="edges")
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
