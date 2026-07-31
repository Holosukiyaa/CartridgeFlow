from datetime import datetime
from copy import deepcopy
import hashlib
import json
import re

from core.runtime.state_machine import assert_transition
from core.protocol.features import has_protocol_feature


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
        return has_protocol_feature(
            str(protocol.get("id") or ""),
            str(protocol.get("version") or ""),
            "typed_control_edges",
        )

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

    def create_execution_tokens(self, run_id: str, plan: dict, inputs: dict | None = None) -> dict:
        """Create the durable token ledger for one compiled ExecutionPlan run."""
        if not isinstance(plan, dict) or plan.get("schema") != "cartridgeflow.execution_plan.compiled.v1":
            raise ValueError("A compiled ExecutionPlan v1 is required for token execution")
        input_refs = [
            {
                "kind": "run_input",
                "key": str(key),
                "sha256": _value_digest(value),
            }
            for key, value in sorted((inputs or {}).items(), key=lambda item: str(item[0]))
        ]
        initial = {
            "token_id": "tok_000001",
            "run_id": run_id,
            "node_id": plan["entry"],
            "attempt": 1,
            "status": "ready",
            "created_sequence": 1,
            "input_refs": input_refs,
            "lineage": {"forks": [], "loops": {}, "batches": []},
            "parent_token_ids": [],
            "checkpoints": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        return {
            "schema": "cartridgeflow.execution_tokens.v1",
            "run_id": run_id,
            "plan_id": plan.get("plan_id"),
            "plan_digest": plan.get("plan_digest"),
            "source_digest": plan.get("source_digest"),
            "next_sequence": 2,
            "tokens": [initial],
            "joins": {},
            "trace_revision": 0,
        }

    def prepare_execution_recovery(self, state_doc: dict, *, node_id: str, phase: str, outcome: str) -> None:
        """Turn a checkpointed active token back into a deterministic runnable state."""
        execution = self._execution_state(state_doc)
        candidates = [
            token for token in execution["tokens"]
            if token.get("node_id") == node_id and token.get("status") in {"running", "waiting", "paused"}
        ]
        if not candidates:
            raise ValueError(f"Checkpoint has no active execution token for node: {node_id}")
        token = max(candidates, key=lambda item: int(item.get("created_sequence") or 0))
        if phase == "after" and outcome == "completed":
            token["status"] = "completed"
            token["transition_pending"] = True
        elif phase == "after" and outcome == "failed":
            token["status"] = "failed"
            token["failure_pending"] = True
        else:
            token["status"] = "ready"
            token.pop("transition_pending", None)
            token.pop("failure_pending", None)
        token["updated_at"] = now_iso()
        state_doc.setdefault("context", {}).pop("_execution_token", None)

    def run_execution_plan(
        self,
        state_doc: dict,
        plan: dict,
        handlers: dict,
        *,
        edge_handler=None,
        token_handler=None,
    ) -> dict:
        """Execute a CF-FARP@1.0 plan from durable tokens, never a visited set.

        The caller owns persistence.  ``token_handler`` is invoked after every
        state transition so a runner can atomically expose the same ledger in
        its run trace and snapshots.
        """
        if not isinstance(plan, dict) or plan.get("schema") != "cartridgeflow.execution_plan.compiled.v1":
            raise ValueError("A compiled ExecutionPlan v1 is required for token execution")
        execution = self._execution_state(state_doc)
        if execution.get("plan_digest") != plan.get("plan_digest"):
            raise ValueError("Execution token ledger does not match the compiled plan")

        nodes = {str(node.get("id")): node for node in plan.get("nodes") or [] if isinstance(node, dict)}
        edges = [dict(edge) for edge in plan.get("edges") or [] if isinstance(edge, dict)]
        success_by_source: dict[str, list[dict]] = {}
        failure_by_source: dict[str, list[dict]] = {}
        for edge in edges:
            destination = failure_by_source if edge.get("kind") == "failure" else success_by_source
            destination.setdefault(str(edge.get("from")), []).append(edge)
        for collection in (success_by_source, failure_by_source):
            for source in collection:
                collection[source].sort(key=lambda item: str(item.get("id")))

        def emit(event_type: str, token: dict, **data) -> None:
            token["updated_at"] = now_iso()
            execution["trace_revision"] = int(execution.get("trace_revision") or 0) + 1
            if token_handler:
                token_handler({
                    "type": event_type,
                    "token": deepcopy(token),
                    "trace_revision": execution["trace_revision"],
                    **data,
                })

        def add_token(
            node_id: str,
            parent: dict,
            *,
            edge: dict,
            lineage: dict | None = None,
            input_refs: list[dict] | None = None,
            parents: list[str] | None = None,
        ) -> dict:
            sequence = int(execution.get("next_sequence") or 1)
            execution["next_sequence"] = sequence + 1
            token_lineage = deepcopy(lineage if lineage is not None else parent.get("lineage") or {})
            token = {
                "token_id": f"tok_{sequence:06d}",
                "run_id": execution.get("run_id") or state_doc.get("run_id"),
                "node_id": node_id,
                "attempt": self._next_token_attempt(execution, node_id, token_lineage),
                "status": "ready",
                "created_sequence": sequence,
                "input_refs": deepcopy(input_refs if input_refs is not None else parent.get("input_refs") or []),
                "lineage": token_lineage,
                "parent_token_ids": list(parents if parents is not None else [parent["token_id"]]),
                "via_edge_id": edge.get("id"),
                "checkpoints": [],
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            execution["tokens"].append(token)
            emit("created", token, edge_id=edge.get("id"), relation=edge.get("kind"))
            return token

        def traverse(source_token: dict, edge: dict, target: str, *, reason: str, lineage=None, input_refs=None, parents=None) -> dict:
            emitted = add_token(target, source_token, edge=edge, lineage=lineage, input_refs=input_refs, parents=parents)
            if edge_handler:
                edge_handler(
                    str(edge.get("from")),
                    target,
                    state_doc,
                    {
                        "edge_id": edge.get("id"),
                        "relation": edge.get("kind"),
                        "reason": reason,
                        "token_id": emitted["token_id"],
                        "parent_token_ids": emitted["parent_token_ids"],
                    },
                )
            return emitted

        def route_failure(token: dict, cause: str) -> bool:
            choices = [
                edge for edge in failure_by_source.get(str(token.get("node_id")), [])
                if cause in ((edge.get("failure") or {}).get("causes") or [])
            ]
            if not choices:
                token["status"] = "failed"
                token["failure_cause"] = cause
                emit("failed", token, cause=cause, fatal=True)
                state_doc.setdefault("context", {})["_execution_fatal"] = {
                    "token_id": token["token_id"], "node_id": token["node_id"], "cause": cause,
                }
                state_doc["status"] = "failed"
                return False
            token["status"] = "failed"
            token["failure_cause"] = cause
            emit("failed", token, cause=cause, fatal=False)
            for edge in choices:
                traverse(token, edge, str(edge.get("to")), reason="failure")
            return True

        def route_join(token: dict, edge: dict) -> None:
            join = edge.get("join") or {}
            join_id = str(join.get("id"))
            branch = str(join.get("branch"))
            base_lineage = self._join_base_lineage(token.get("lineage") or {})
            key_value = None
            if join.get("mode") == "keyed":
                key_value = self._resolve_value_ref(str(join.get("key_ref") or ""), state_doc, token)
                if key_value is None:
                    token["status"] = "failed"
                    emit("failed", token, cause="validation", fatal=True)
                    state_doc.setdefault("context", {})["_execution_fatal"] = {
                        "token_id": token["token_id"], "node_id": token["node_id"], "cause": "validation",
                    }
                    return
            group_key = _stable_key({"lineage": base_lineage, "key": key_value})
            ledger_key = f"{join_id}:{group_key}"
            joins = execution.setdefault("joins", {})
            group = joins.setdefault(ledger_key, {
                "join_id": join_id,
                "mode": join.get("mode"),
                "branches": list(join.get("branches") or []),
                "lineage": deepcopy(base_lineage),
                "key": deepcopy(key_value),
                "arrivals": {},
                "emitted": False,
            })
            if group.get("emitted"):
                remaining = str(join.get("remaining") or "")
                token["status"] = "cancelled" if remaining == "cancel" else "observed"
                emit("cancelled" if remaining == "cancel" else "observed", token, join_id=join_id, reason="join_already_emitted")
                return
            if branch in group["arrivals"]:
                token["status"] = "failed"
                emit("failed", token, cause="validation", fatal=True)
                state_doc.setdefault("context", {})["_execution_fatal"] = {
                    "token_id": token["token_id"], "node_id": token["node_id"], "cause": "validation",
                }
                return
            token["status"] = "held"
            token["join"] = {"id": join_id, "branch": branch, "key": deepcopy(key_value), "group_key": group_key}
            group["arrivals"][branch] = token["token_id"]
            emit("join_held", token, join_id=join_id, branch=branch, key=deepcopy(key_value))
            expected = list(group.get("branches") or [])
            eligible = bool(expected) and all(name in group["arrivals"] for name in expected)
            if join.get("mode") == "any":
                eligible = True
            if not eligible:
                return
            arrival_tokens = [
                next(item for item in execution["tokens"] if item.get("token_id") == group["arrivals"][name])
                for name in expected if name in group["arrivals"]
            ]
            group["emitted"] = True
            for item in arrival_tokens:
                item["status"] = "completed"
                emit("join_consumed", item, join_id=join_id)
            aggregate_refs = []
            for item in arrival_tokens:
                aggregate_refs.extend(deepcopy(item.get("input_refs") or []))
            aggregate = traverse(
                token,
                edge,
                str(edge.get("to")),
                reason="join",
                lineage=base_lineage,
                input_refs=aggregate_refs,
                parents=[item["token_id"] for item in arrival_tokens],
            )
            aggregate["join"] = {"id": join_id, "mode": join.get("mode"), "key": deepcopy(key_value)}
            if join.get("mode") == "any" and str(join.get("remaining")) == "cancel":
                self._cancel_remaining_join_tokens(
                    execution,
                    join_id,
                    _stable_key(base_lineage),
                    {str(item.get("from")) for item in edges if item.get("kind") == "join" and (item.get("join") or {}).get("id") == join_id},
                    token["token_id"],
                    emit,
                )

        def route_success(token: dict) -> None:
            outgoing = success_by_source.get(str(token.get("node_id")), [])
            for edge in outgoing:
                kind = str(edge.get("kind"))
                if kind == "sequence":
                    traverse(token, edge, str(edge.get("to")), reason="sequence")
                elif kind == "fork":
                    lineage = deepcopy(token.get("lineage") or {})
                    lineage.setdefault("forks", []).append({
                        "id": (edge.get("fork") or {}).get("id"),
                        "branch": (edge.get("fork") or {}).get("branch"),
                    })
                    traverse(token, edge, str(edge.get("to")), reason="fork", lineage=lineage)
                elif kind == "join":
                    route_join(token, edge)
                elif kind == "loop":
                    loop = edge.get("loop") or {}
                    loops = deepcopy((token.get("lineage") or {}).get("loops") or {})
                    loop_id = str(loop.get("id"))
                    continue_loop = bool(self._resolve_value_ref(str(loop.get("continue_when") or ""), state_doc, token))
                    if continue_loop:
                        iteration = int(loops.get(loop_id) or 0) + 1
                        if iteration > int(loop.get("max_iterations") or 0):
                            route_failure(token, "retry_exhausted")
                            return
                        loops[loop_id] = iteration
                        lineage = deepcopy(token.get("lineage") or {})
                        lineage["loops"] = loops
                        traverse(token, edge, str(edge.get("to")), reason="loop", lineage=lineage)
                    else:
                        traverse(token, edge, str(loop.get("exit_to")), reason="loop_exit")
                elif kind == "batch":
                    batch = edge.get("batch") or {}
                    items = self._resolve_value_ref(str(batch.get("items_ref") or ""), state_doc, token)
                    if not isinstance(items, list):
                        route_failure(token, "validation")
                        return
                    size = int(batch.get("size") or 0)
                    for batch_index, offset in enumerate(range(0, len(items), size)):
                        batch_items = deepcopy(items[offset:offset + size])
                        lineage = deepcopy(token.get("lineage") or {})
                        lineage.setdefault("batches", []).append({
                            "id": batch.get("id"),
                            "index": batch_index,
                            "offset": offset,
                            "size": len(batch_items),
                            "max_concurrency": batch.get("max_concurrency"),
                            "ordering": batch.get("ordering"),
                            "items": deepcopy(batch_items),
                        })
                        refs = [*deepcopy(token.get("input_refs") or []), *[
                            {
                                "kind": "batch_item",
                                "batch_id": batch.get("id"),
                                "batch_index": batch_index,
                                "item_index": offset + index,
                                "source_ref": f"{batch.get('items_ref')}[{offset + index}]",
                                "sha256": _value_digest(item),
                                "value": deepcopy(item),
                            }
                            for index, item in enumerate(batch_items)
                        ]]
                        traverse(token, edge, str(edge.get("to")), reason="batch", lineage=lineage, input_refs=refs)
                elif kind == "wait":
                    wait = deepcopy(edge.get("wait") or {})
                    token["status"] = "waiting"
                    token["wait"] = {
                        **wait,
                        "edge_id": edge.get("id"),
                        "target": edge.get("to"),
                        "started_at": now_iso(),
                    }
                    state_doc.setdefault("context", {})["_pause_flow"] = {
                        "state": token.get("node_id"),
                        "status": "paused_waiting_user",
                        "execution_wait": deepcopy(token["wait"]),
                        "token_id": token.get("token_id"),
                    }
                    self.complete(state_doc, str(token.get("node_id")), "paused_waiting_user")
                    emit("waiting", token, wait_id=wait.get("id"))

        def advance_checkpointed_tokens() -> bool:
            advanced = False
            for token in sorted(execution["tokens"], key=lambda item: int(item.get("created_sequence") or 0)):
                if token.get("transition_pending"):
                    token.pop("transition_pending", None)
                    route_success(token)
                    emit("recovered_completed", token)
                    advanced = True
                elif token.get("failure_pending"):
                    token.pop("failure_pending", None)
                    route_failure(token, str(token.get("failure_cause") or "exception"))
                    advanced = True
            return advanced

        def advance_waiting_tokens() -> bool:
            advanced = False
            now = datetime.now()
            for token in sorted(execution["tokens"], key=lambda item: int(item.get("created_sequence") or 0)):
                if token.get("status") != "waiting":
                    continue
                wait = token.get("wait") if isinstance(token.get("wait"), dict) else {}
                started = _parse_timestamp(wait.get("started_at"))
                elapsed_ms = int((now - started).total_seconds() * 1000) if started else 0
                if elapsed_ms >= int(wait.get("timeout_ms") or 0):
                    token["status"] = "failed"
                    route_failure(token, "timeout")
                    advanced = True
                    continue
                mode = str(wait.get("mode") or "")
                ready = bool(wait.get("resumed"))
                if mode == "duration":
                    ready = elapsed_ms >= int(wait.get("duration_ms") or 0)
                elif mode == "condition":
                    ready = bool(self._resolve_value_ref(str(wait.get("condition_ref") or ""), state_doc, token))
                if not ready:
                    continue
                token["status"] = "completed"
                token["wait_resumed_at"] = now_iso()
                token.pop("wait", None)
                synthetic = {"id": wait.get("edge_id"), "kind": "wait", "from": token.get("node_id"), "to": wait.get("target")}
                traverse(token, synthetic, str(synthetic.get("to")), reason="wait_resumed")
                emit("wait_resumed", token, wait_id=wait.get("id"))
                advanced = True
            return advanced

        while True:
            if state_doc.setdefault("context", {}).get("_execution_fatal"):
                break
            if advance_checkpointed_tokens() or advance_waiting_tokens():
                continue
            ready = sorted(
                (token for token in execution["tokens"] if token.get("status") == "ready"),
                key=lambda item: int(item.get("created_sequence") or 0),
            )
            if not ready:
                waiting = [token for token in execution["tokens"] if token.get("status") == "waiting"]
                held = [token for token in execution["tokens"] if token.get("status") == "held"]
                if waiting:
                    state_doc["status"] = "paused_waiting_user"
                elif held:
                    state_doc.setdefault("context", {})["_execution_fatal"] = {
                        "cause": "validation", "message": "A declared join cannot receive every required branch.",
                    }
                    state_doc["status"] = "failed"
                else:
                    state_doc["status"] = "completed"
                break

            token = ready[0]
            node_id = str(token.get("node_id"))
            if node_id not in nodes:
                token["status"] = "failed"
                emit("failed", token, cause="validation", fatal=True)
                state_doc.setdefault("context", {})["_execution_fatal"] = {"token_id": token["token_id"], "cause": "validation"}
                break
            token["status"] = "running"
            state_doc.setdefault("context", {})["_execution_token"] = token
            emit("started", token)
            self.enter(state_doc, node_id)
            handler = handlers.get(node_id)
            if handler:
                handler(state_doc)
            context = state_doc.setdefault("context", {})
            pause = context.get("_pause_flow")
            cancelled = context.get("_cancel_flow")
            aborted = context.get("_abort_flow")
            if pause:
                token["status"] = "paused"
                emit("paused", token, pause=deepcopy(pause))
                self.complete(state_doc, node_id, str(pause.get("status") or "paused_waiting_user"))
                state_doc["status"] = str(pause.get("status") or "paused_waiting_user")
                break
            if cancelled:
                token["status"] = "cancelled"
                emit("cancelled", token, reason=cancelled.get("reason"))
                self.complete(state_doc, node_id, "cancelled")
                state_doc["status"] = "cancelled"
                break
            if aborted:
                context.pop("_abort_flow", None)
                self.complete(state_doc, node_id, "failed")
                cause = _failure_cause(aborted)
                if not route_failure(token, cause):
                    break
                continue
            self.complete(state_doc, node_id, "completed")
            token["status"] = "completed"
            emit("completed", token)
            if str(nodes[node_id].get("type")) == "terminal":
                continue
            route_success(token)

        state_doc.setdefault("context", {}).pop("_execution_token", None)
        return state_doc

    def _execution_state(self, state_doc: dict) -> dict:
        execution = state_doc.get("execution")
        if not isinstance(execution, dict) or execution.get("schema") != "cartridgeflow.execution_tokens.v1":
            raise ValueError("Root flow state has no ExecutionPlan token ledger")
        tokens = execution.get("tokens")
        if not isinstance(tokens, list):
            raise ValueError("ExecutionPlan token ledger is malformed")
        return execution

    def _next_token_attempt(self, execution: dict, node_id: str, lineage: dict) -> int:
        lineage_key = _stable_key(lineage)
        attempts = [
            int(token.get("attempt") or 0)
            for token in execution.get("tokens") or []
            if token.get("node_id") == node_id and _stable_key(token.get("lineage") or {}) == lineage_key
        ]
        return (max(attempts) if attempts else 0) + 1

    def _join_base_lineage(self, lineage: dict) -> dict:
        result = deepcopy(lineage if isinstance(lineage, dict) else {})
        forks = list(result.get("forks") or [])
        if forks:
            forks.pop()
        result["forks"] = forks
        return result

    def _cancel_remaining_join_tokens(
        self,
        execution: dict,
        join_id: str,
        lineage_key: str,
        join_sources: set[str],
        winner_id: str,
        emit,
    ) -> None:
        for token in execution.get("tokens") or []:
            if token.get("token_id") == winner_id or token.get("status") not in {"ready", "held"}:
                continue
            if str(token.get("node_id") or "") not in join_sources:
                continue
            if _stable_key(self._join_base_lineage(token.get("lineage") or {})) != lineage_key:
                continue
            token["status"] = "cancelled"
            token["cancel_reason"] = f"join:{join_id}:remaining_cancelled"
            emit("cancelled", token, join_id=join_id, reason="any_join_remaining_cancelled")

    def _resolve_value_ref(self, reference: str, state_doc: dict, token: dict | None = None):
        if not reference or not reference.startswith("$"):
            return None
        parts = [part for part in reference[1:].split(".") if part]
        if not parts:
            return None
        context = state_doc.get("context") if isinstance(state_doc.get("context"), dict) else {}
        store = context.get("store") if isinstance(context.get("store"), dict) else {}
        value = None
        if parts[0] == "item" and token:
            for ref in token.get("input_refs") or []:
                if isinstance(ref, dict) and ref.get("kind") == "batch_item":
                    value = ref.get("value")
                    break
        elif parts[0] in store:
            value = store.get(parts[0])
        elif parts[0] in context:
            value = context.get(parts[0])
        else:
            return None
        for part in parts[1:]:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
                value = value[int(part)]
            else:
                return None
        return value


def _stable_key(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _value_digest(value) -> str:
    return "sha256:" + hashlib.sha256(_stable_key(value).encode("utf-8")).hexdigest()


def _parse_timestamp(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _failure_cause(aborted: dict) -> str:
    text = " ".join(str(aborted.get(key) or "") for key in ("reason", "action", "error_id")).lower()
    if "timeout" in text:
        return "timeout"
    if "resource" in text or "dependency" in text:
        return "resource"
    if "validation" in text or "input" in text:
        return "validation"
    return "exception"
