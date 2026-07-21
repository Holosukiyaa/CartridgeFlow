"""Flow 结构静态检查（只做图拓扑，不碰键解析）。

重要边界：本模块**不**重新实现 node_executor 的键解析逻辑。
"某个 input 键是否被上游生产"这类数据链问题，由执行器在运行时自己上报
（见 node_executor 的 missing_inputs / missing_store_refs），因为执行器才是
键解析的唯一事实来源。本模块只回答纯图论问题：

- 哪些节点从 start 不可达（孤立子图）？
- 其中哪些显式标了 params.isolated=true（故意隔离，预期行为）？
- 哪些没标却断链（可能是意外遗漏）？

这样静态层永远不会和执行器的键语义漂移——它压根不看键。
"""
from __future__ import annotations


def _build_adjacency(root_flow: dict) -> dict[str, list[str]]:
    states = root_flow.get("states") or {}
    outgoing: dict[str, list[str]] = {sid: [] for sid in states}
    for state_id, state in states.items():
        nxt = state.get("next")
        if nxt and nxt in states:
            outgoing[state_id].append(nxt)
    for edge in root_flow.get("edges") or []:
        source = edge.get("from") or edge.get("source")
        target = edge.get("to") or edge.get("target")
        if source in states and target in states and target not in outgoing[source]:
            outgoing[source].append(target)
    return outgoing


def _is_isolated_marked(state: dict) -> bool:
    params = state.get("params") or {}
    return bool(params.get("isolated") or (params.get("preset_config") or {}).get("isolated"))


def analyze_flow_structure(root_flow: dict) -> dict:
    """纯拓扑检查：找出从 start 不可达的节点，区分故意隔离 vs 意外断链。"""
    states = root_flow.get("states") or {}
    start = root_flow.get("start")
    outgoing = _build_adjacency(root_flow)

    reachable: set[str] = set()
    if start in states:
        stack = [start]
        while stack:
            node = stack.pop()
            if node in reachable:
                continue
            reachable.add(node)
            for nxt in outgoing.get(node, []):
                if nxt not in reachable:
                    stack.append(nxt)

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
            "detail": (
                "节点从 start 不可达，且已显式标记 params.isolated=true —— 故意隔离，符合预期。"
                if marked else
                "节点从 start 不可达且未标记 isolated；可能是意外断链。若为有意隔离，请加 params.isolated=true 以消除此告警。"
            ),
        })

    warnings = sum(1 for f in findings if f["severity"] == "warning")
    return {
        "findings": findings,
        "summary": {
            "isolated_total": len(findings),
            "isolated_intentional": sum(1 for f in findings if f.get("isolated")),
            "isolated_suspicious": warnings,
            "reachable_count": len(reachable),
            "node_count": len(states),
        },
    }
