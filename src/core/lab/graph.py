from .mcp_slots import get_tool_summary, normalize_tools


ROOT_LIFECYCLE_STATES = {
    "start",
    "complete",
}


class FlowGraphBuilder:
    def build(self, cartridge: dict) -> dict:
        root_flow = cartridge.get("root_flow") or {}
        states = root_flow.get("states") or {}
        nodes = []
        edges = []
        order = self._ordered_states(root_flow)
        for index, state_id in enumerate(order):
            state = states.get(state_id) or {}
            tools = normalize_tools(state.get("tools"))
            scope = state.get("scope") or ("root" if state_id in ROOT_LIFECYCLE_STATES else "sub_flow")
            nodes.append({
                "id": state_id,
                "title": state.get("title", state_id),
                "type": state.get("type", "system"),
                "action": state.get("action"),
                "next": state.get("next"),
                "kind": state.get("kind"),
                "executor": state.get("executor"),
                "effect": state.get("effect"),
                "display_name": state.get("display_name"),
                "component_ref": state.get("component_ref"),
                "interaction_mode": state.get("interaction_mode"),
                "input_binding": state.get("input_binding"),
                "action_routes": state.get("action_routes"),
                "output": state.get("output"),
                "display": state.get("display") or {},
                "input_kind": state.get("input_kind"),
                "source": state.get("source"),
                "input_schema": state.get("input_schema"),
                "output_contract": state.get("output_contract"),
                "decision_contract": state.get("decision_contract"),
                "decision_test_mode": state.get("decision_test_mode"),
                "mock_decision_envelope": state.get("mock_decision_envelope"),
                "primary_output": state.get("primary_output"),
                "tool_binding": state.get("tool_binding"),
                "allowed_tools": state.get("allowed_tools"),
                "mcp_binding": state.get("mcp_binding"),
                "failure_policy": state.get("failure_policy"),
                "permission": state.get("permission"),
                "audit_log": state.get("audit_log"),
                "endpoint": state.get("endpoint"),
                "timeout_ms": state.get("timeout_ms"),
                "x": state.get("layout", {}).get("x", 80 + index * 190),
                "y": state.get("layout", {}).get("y", 120),
                "scope": scope,
                "locked": bool(state.get("locked", scope == "root")),
                "entry_kind": state.get("entry_kind") or ("root_flow" if scope == "root" else "sub_flow"),
                "template_id": state.get("template_id"),
                "agent": state.get("agent"),
                "tools": tools,
                "tool_summary": get_tool_summary(tools),
                "params": state.get("params") or {},
                "model_role": state.get("model_role"),
                "data": state,
            })
            if state.get("next"):
                edges.append({"from": state_id, "to": state.get("next"), "scope": "root"})
            edges.extend(self._answer_route_edges(state_id, state))
        for edge in root_flow.get("edges") or []:
            source = edge.get("from") or edge.get("source")
            target = edge.get("to") or edge.get("target")
            scope = edge.get("scope", "root")
            if source and target and not any(item.get("from") == source and item.get("to") == target and item.get("scope", "root") == scope for item in edges):
                edges.append({"from": source, "to": target, "scope": scope, "label": edge.get("label")})
        return {
            "id": root_flow.get("id"),
            "name": root_flow.get("name"),
            "mode": root_flow.get("mode", "lifecycle"),
            "cartridge_id": cartridge.get("id"),
            "nodes": nodes,
            "edges": edges,
            "sub_flows": [],
        }

    def _answer_route_edges(self, state_id: str, state: dict) -> list[dict]:
        named_routes = state.get("action_routes") if isinstance(state.get("action_routes"), dict) else {}
        if named_routes:
            return [
                {"from": state_id, "to": target, "scope": "branch", "label": action_id}
                for action_id, target in named_routes.items()
                if target and target != state_id
            ]
        decision_contract = state.get("decision_contract") if isinstance(state.get("decision_contract"), dict) else {}
        interaction = decision_contract.get("interaction") if isinstance(decision_contract.get("interaction"), dict) else {}
        routes = interaction.get("answer_routes")
        if not isinstance(routes, list):
            return []

        edges: list[dict] = []
        seen_targets = set()
        for route in routes:
            if not isinstance(route, dict):
                continue
            target = str(route.get("target_node") or "").strip()
            if not target or target == state_id or target in seen_targets:
                continue
            seen_targets.add(target)
            edge = {"from": state_id, "to": target, "scope": "branch", "label": "回跳"}
            edges.append(edge)
        return edges

    def _ordered_states(self, root_flow: dict) -> list[str]:
        states = root_flow.get("states") or {}
        current = root_flow.get("start")
        visited = []
        seen = set()
        while current and current in states and current not in seen:
            visited.append(current)
            seen.add(current)
            current = (states.get(current) or {}).get("next")
        for state_id in states:
            if state_id not in seen:
                visited.append(state_id)
        return visited
