from datetime import datetime


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
                item["completed_at"] = timestamp
                item["status"] = status
                break
        state_doc["current_state"] = state_name
        state_doc["status"] = status
        state_doc["updated_at"] = timestamp
        return state_doc

    def next_state(self, state_name: str) -> str | None:
        return (self.states.get(state_name) or {}).get("next")

    def next_states(self, state_name: str) -> list[str]:
        result = []
        next_state = self.next_state(state_name)
        if next_state:
            result.append(next_state)
        for edge in self.root_flow.get("edges") or []:
            source = edge.get("from") or edge.get("source")
            target = edge.get("to") or edge.get("target")
            if source == state_name and target:
                result.append(target)
        deduped = []
        seen = set()
        for item in result:
            if item in self.states and item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

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
        for edge in self.root_flow.get("edges") or []:
            source = edge.get("from") or edge.get("source")
            target = edge.get("to") or edge.get("target")
            if source in self.states and target in self.states:
                key = (source, target)
                if key not in seen_edges:
                    seen_edges.add(key)
                    incoming[target] = incoming.get(target, 0) + 1
        return incoming

    def run_standard_flow(
        self,
        state_doc: dict,
        handlers: dict,
        start_state: str | None = None,
        visited: set[str] | list[str] | None = None,
        completed_parents: dict[str, set[str] | list[str]] | None = None,
        initial_queue: list[str] | None = None,
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
            if (state_doc.get("context") or {}).get("_pause_flow"):
                self.complete(state_doc, state_name, "paused_waiting_user")
                state_doc["status"] = "paused_waiting_user"
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
            next_states = [] if state.get("type") == "terminal" and state_name != start_state else self.next_states(state_name)
            if state.get("type") == "terminal" and (state_name == "complete" or not next_states):
                state_doc["status"] = "completed" if state_name == "complete" else state_name
                state_doc["current_state"] = state_name
                state_doc["updated_at"] = now_iso()
                if state_name == "complete":
                    break
            for target in next_states:
                completed_parents.setdefault(target, set()).add(state_name)
                if target not in visited and target not in queue:
                    queue.append(target)
        return state_doc
