from datetime import datetime
import json
import re

from core.runtime.state_machine import assert_transition


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class RootFlowEngine:
    def __init__(self, root_flow: dict):
        self.root_flow = root_flow or {}
        self.states = self.root_flow.get("states") or {}

    def create_state(self, run_id: str, inputs: dict) -> dict:
        timestamp = now_iso()
        return {
            "run_id": run_id,
            "root_flow_id": self.root_flow.get("id"),
            "current_state": self.root_flow.get("start", "load"),
            "previous_state": None,
            "status": "created",
            "context": {
                "inputs": inputs,
                "artifacts": [],
            },
            "history": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def enter(self, state_doc: dict, state_name: str) -> dict:
        state = self.states.get(state_name, {})
        item = {
            "state": state_name,
            "type": state.get("type", "system"),
            "title": state.get("title", state_name),
            "action": state.get("action"),
            "entered_at": now_iso(),
            "completed_at": None,
            "status": "entered",
        }
        state_doc["previous_state"] = state_doc.get("current_state")
        state_doc["current_state"] = state_name
        state_doc["status"] = "running"
        state_doc["history"].append(item)
        state_doc["updated_at"] = item["entered_at"]
        return item

    def complete(self, state_doc: dict, state_name: str, status: str = "completed") -> dict:
        timestamp = now_iso()
        for item in reversed(state_doc.get("history", [])):
            if item.get("state") == state_name and item.get("completed_at") is None:
                assert_transition("node", item.get("status") or "entered", status)
                item["completed_at"] = timestamp
                item["status"] = status
                break
        state_doc["current_state"] = state_name
        state_doc["status"] = status
        state_doc["updated_at"] = timestamp
        return state_doc

    def next_state(self, state_name: str) -> str | None:
        return (self.states.get(state_name) or {}).get("next")

    def _uses_typed_control_edges(self) -> bool:
        protocol = self.root_flow.get("protocol") if isinstance(self.root_flow.get("protocol"), dict) else {}
        return protocol.get("id") == "CF-FARP" and str(protocol.get("version")) in {"0.8", "0.9"}

    def next_states(self, state_name: str, context: dict | None = None) -> list[str]:
        result = []
        next_state = self.next_state(state_name)
        if next_state:
            result.append(next_state)
        edge_field = "control_edges" if self._uses_typed_control_edges() else "edges"
        for edge in self.root_flow.get(edge_field) or []:
            if not isinstance(edge, dict):
                continue
            kind = str(edge.get("kind") or ("control" if not self._uses_typed_control_edges() else ""))
            if self._uses_typed_control_edges() and kind not in {"control", "branch"}:
                continue
            source = edge.get("from") or edge.get("source")
            target = edge.get("to") or edge.get("target")
            if source == state_name and target and (kind != "branch" or self._condition_matches(edge.get("condition"), context or {})):
                result.append(target)
        if self._uses_typed_control_edges():
            routes = (self.states.get(state_name) or {}).get("routes")
            if isinstance(routes, dict):
                for route in routes.values():
                    if not isinstance(route, dict):
                        continue
                    target = route.get("target")
                    if target and self._condition_matches(route.get("condition"), context or {}):
                        result.append(target)
        deduped = []
        seen = set()
        for item in result:
            if item in self.states and item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    def _condition_matches(self, condition, context: dict) -> bool:
        if isinstance(condition, dict):
            source = str(condition.get("source") or "")
            if source != "store":
                return False
            value = self._store_path(context, str(condition.get("key") or ""), str(condition.get("path") or ""))
            operator = str(condition.get("operator") or "eq")
            expected = condition.get("value")
            if operator == "eq":
                return value == expected
            if operator == "ne":
                return value != expected
            if operator == "in" and isinstance(expected, list):
                return value in expected
            return False
        if not isinstance(condition, str) or not condition.strip():
            return False
        match = re.fullmatch(r"store:([A-Za-z_][\w]*)(?:\.([A-Za-z_][\w.]*))?\s*(==|!=)\s*(.+)", condition.strip())
        if not match:
            return False
        key, path, operator, raw_expected = match.groups()
        try:
            expected = json.loads(raw_expected)
        except json.JSONDecodeError:
            expected = raw_expected.strip().strip("'\"")
        value = self._store_path(context, key, path or "")
        return value == expected if operator == "==" else value != expected

    def _store_path(self, context: dict, key: str, path: str):
        store = context.get("store") if isinstance(context.get("store"), dict) else context
        value = store.get(key) if isinstance(store, dict) else None
        for part in [item for item in path.split(".") if item]:
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        return value

    def _incoming_counts(self) -> dict[str, int]:
        incoming = {state_id: 0 for state_id in self.states}
        seen_edges = set()
        for source_id, state in self.states.items():
            target_id = state.get("next")
            if target_id in self.states:
                key = (source_id, target_id)
                if key not in seen_edges:
                    seen_edges.add(key)
                    incoming[target_id] = incoming.get(target_id, 0) + 1
        edge_field = "control_edges" if self._uses_typed_control_edges() else "edges"
        for edge in self.root_flow.get(edge_field) or []:
            if not isinstance(edge, dict):
                continue
            if self._uses_typed_control_edges() and edge.get("kind") not in {"control", "branch"}:
                continue
            source = edge.get("from") or edge.get("source")
            target = edge.get("to") or edge.get("target")
            if source in self.states and target in self.states:
                key = (source, target)
                if key not in seen_edges:
                    seen_edges.add(key)
                    incoming[target] = incoming.get(target, 0) + 1
        if self._uses_typed_control_edges():
            return {node_id: min(count, 1) for node_id, count in incoming.items()}
        return incoming

    def run_standard_flow(
        self,
        state_doc: dict,
        handlers: dict,
        start_state: str | None = None,
        visited: set[str] | list[str] | None = None,
        completed_parents: dict[str, set[str] | list[str]] | None = None,
        initial_queue: list[str] | None = None,
        edge_handler=None,
    ) -> dict:
        start_state = start_state or self.root_flow.get("start", "load")
        if initial_queue is not None:
            queue = [state for state in initial_queue if state in self.states]
        else:
            queue = [start_state] if start_state in self.states else []
        visited = set(visited or [])
        completed_parents = {
            key: set(value or [])
            for key, value in (completed_parents or {}).items()
        }
        incoming_counts = self._incoming_counts()

        while queue:
            state_name = queue.pop(0)
            if state_name in visited:
                continue
            waiting_for = incoming_counts.get(state_name, 0)
            if state_name != start_state and waiting_for > len(completed_parents.get(state_name, set())):
                continue
            visited.add(state_name)
            self.enter(state_doc, state_name)
            handler = handlers.get(state_name)
            if handler:
                handler(state_doc)
            pause = (state_doc.get("context") or {}).get("_pause_flow")
            if pause:
                pause_status = str((pause or {}).get("status") or "paused_waiting_user")
                self.complete(state_doc, state_name, pause_status)
                state_doc["status"] = pause_status
                state_doc["current_state"] = state_name
                state_doc["updated_at"] = now_iso()
                break
            if (state_doc.get("context") or {}).get("_cancel_flow"):
                self.complete(state_doc, state_name, "cancelled")
                state_doc["status"] = "cancelled"
                state_doc["current_state"] = state_name
                state_doc["updated_at"] = now_iso()
                break
            if (state_doc.get("context") or {}).get("_abort_flow"):
                self.complete(state_doc, state_name, "failed")
                state_doc["status"] = "failed"
                state_doc["current_state"] = state_name
                state_doc["updated_at"] = now_iso()
                break
            self.complete(state_doc, state_name, "completed")
            state = self.states.get(state_name) or {}
            next_states = [] if state.get("type") == "terminal" and state_name != start_state else self.next_states(state_name, state_doc.get("context") or {})
            if state.get("type") == "terminal" and (state_name == "complete" or not next_states):
                state_doc["status"] = "completed" if state_name == "complete" else state_name
                state_doc["current_state"] = state_name
                state_doc["updated_at"] = now_iso()
                if state_name == "complete":
                    break
            for target in next_states:
                completed_parents.setdefault(target, set()).add(state_name)
                if edge_handler:
                    edge_handler(state_name, target, state_doc)
                if target not in visited and target not in queue:
                    queue.append(target)
        return state_doc
