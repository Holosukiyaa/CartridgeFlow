import json
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from core.runtime.manager import RuntimeManager
from core.workspace.host import WorkspaceHostManager
from core.lab.node_executor import LabNodeExecutor
from core.protocol import CompatibilityBlockedError, build_compatibility_report, load_base_implementation
from .artifacts import ArtifactManager
from .dependencies import DependencyResolver
from .environment import EnvironmentChecker
from .permissions import PermissionManager
from .root_flow import RootFlowEngine


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class CartridgeRunner:
    def __init__(self, root: str | Path, registry):
        self.root = Path(root)
        self.registry = registry
        self.runtime_manager = RuntimeManager(self.root)
        self.workspace_host = WorkspaceHostManager()
        self.dependency_resolver = DependencyResolver()
        self.environment_checker = EnvironmentChecker()
        self.permission_manager = PermissionManager()
        self.lab_node_executor = LabNodeExecutor(self.root)
        self.artifact_manager = ArtifactManager(self.root)
        self.runs_dir = self.root / ".data" / "cartridge_runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def create_run(
        self,
        cartridge_id: str,
        inputs: dict | None = None,
        probe_range: dict | None = None,
        run_id: str | None = None,
        test_mode: dict | None = None,
    ) -> dict:
        cartridge = self.registry.get_cartridge(cartridge_id)
        manifest = cartridge["manifest"]
        source_root_flow = cartridge.get("root_flow") or {}
        compatibility = self.build_compatibility_report(manifest, source_root_flow)
        if not compatibility.get("ok"):
            raise CompatibilityBlockedError(compatibility)
        normalized_probe_range = self._normalize_probe_range(source_root_flow, probe_range)
        root_flow = self._build_probe_root_flow(source_root_flow, normalized_probe_range) if normalized_probe_range else source_root_flow
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        run_dir = self.runs_dir / run_id
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        created_at = now_iso()
        normalized_test_mode = self._normalize_test_mode(test_mode)
        run = {
            "run_id": run_id,
            "cartridge_id": cartridge_id,
            "cartridge_version": manifest.get("version"),
            "status": "created",
            "current_state": "created",
            "inputs": inputs or {},
            "test_mode": normalized_test_mode,
            "permissions": self.permission_manager.init_permission_state(manifest),
            "environment": self.environment_checker.init_environment_state(manifest),
            "dependencies": self.dependency_resolver.init_dependency_state(manifest),
            "runtime": manifest.get("runtime", {}),
            "base": compatibility.get("base", {}),
            "protocol": compatibility.get("protocol", {}),
            "compatibility": {
                "ok": compatibility.get("ok"),
                "status": compatibility.get("status"),
                "legacy": compatibility.get("legacy"),
                "summary": compatibility.get("summary", {}),
                "findings": compatibility.get("findings", []),
            },
            "workspace": manifest.get("workspace", {}),
            "mcp_tools": manifest.get("mcp_tools", []),
            "run_mode": "probe_range" if normalized_probe_range else "full_flow",
            "probe_range": normalized_probe_range,
            "package_path": cartridge.get("package_path"),
            "runtime_run_id": None,
            "workspace_state": {},
            "artifacts": [],
            "delivery": None,
            "created_at": created_at,
            "updated_at": created_at,
        }
        engine = RootFlowEngine(root_flow)
        state_doc = engine.create_state(run_id, inputs or {})
        if normalized_test_mode:
            state_doc["context"]["test_mode"] = normalized_test_mode
        if normalized_probe_range:
            state_doc["context"]["probe_range"] = normalized_probe_range
            self._seed_probe_driver_context(state_doc, root_flow, normalized_probe_range, inputs or {})
        self._write_json(run_dir / "run.json", run)
        self._write_json(run_dir / "root_flow_state.json", state_doc)
        self._append_event(run_id, cartridge_id, "compatibility_checked", "created", "Compatibility report generated", compatibility)
        self._append_event(run_id, cartridge_id, "run_created", "created", "CartridgeRun 已创建", {"inputs": inputs or {}, "test_mode": normalized_test_mode})

        # 运行前结构检查（纯拓扑）：针对完整流程图检测孤立节点，区分故意隔离与意外断链。
        # 用 source_root_flow 而非探针裁剪后的图，这样结论反映整张流程的真实结构。
        try:
            from core.lab.flow_analyzer import analyze_flow_structure
            structure = analyze_flow_structure(source_root_flow)
            self._append_event(
                run_id, cartridge_id, "structure_checked", "created",
                "流程结构检查完成", structure,
            )
        except Exception as exc:
            self._append_event(
                run_id, cartridge_id, "structure_checked", "created",
                f"流程结构检查跳过：{exc}", {"findings": [], "summary": {}},
            )

        if normalized_probe_range:
            self._append_event(
                run_id,
                cartridge_id,
                "probe_range_selected",
                normalized_probe_range["start_node_id"],
                "Test probe range selected",
                normalized_probe_range,
            )

        def sync_state(state_name: str):
            run["current_state"] = state_name
            run["updated_at"] = now_iso()
            self._write_json(run_dir / "run.json", run)
            self._write_json(run_dir / "root_flow_state.json", state_doc)

        def handle_run(_state_doc: dict):
            runtime_result = self._start_runtime(run, run_dir)
            run["runtime_run_id"] = runtime_result.get("runtime_run_id")
            run["artifacts"] = self._merge_artifacts(run.get("artifacts", []), runtime_result.get("artifacts", []))
            run["status"] = "completed" if runtime_result.get("status") == "completed" else "running"
            _state_doc["context"]["artifacts"] = run["artifacts"]
            self._append_event(run_id, cartridge_id, "runtime_completed", "run", "Runtime 执行完成", {"runtime": runtime_result})

        def handle_workspace(_state_doc: dict):
            run["workspace_state"] = self.workspace_host.open(run)
            self._append_event(run_id, cartridge_id, "workspace_opened", "workspace_open", "Workspace 状态已更新", run["workspace_state"])

        def handle_delivery(_state_doc: dict):
            delivery = self._create_initial_delivery(run, manifest)
            run["delivery"] = delivery
            run["status"] = "completed" if run.get("artifacts") else run.get("status", "created")
            self._write_json(run_dir / "delivery.json", delivery)
            self._append_event(run_id, cartridge_id, "delivery_ready", "delivery", "Delivery 已生成", delivery)

        def handle_permission(_state_doc: dict):
            perm_state = run.get("permissions", {})
            risk = self.permission_manager.get_risk_summary(perm_state)
            _state_doc["context"]["permission_risk"] = risk
            self._append_event(run_id, cartridge_id, "permission_checked", "permission", f"权限风险: {risk['label']}", risk)

        def handle_environment(_state_doc: dict):
            environment = self.environment_checker.check(manifest)
            run["environment"] = environment
            _state_doc["context"]["environment"] = environment
            self._append_event(run_id, cartridge_id, "environment_checked", "environment_check", environment["summary"], environment)

        def handle_dependencies(_state_doc: dict):
            dependencies = self.dependency_resolver.resolve(manifest, run.get("environment", {}))
            run["dependencies"] = dependencies
            _state_doc["context"]["dependencies"] = dependencies
            self._append_event(run_id, cartridge_id, "dependencies_resolved", "dependency_resolution", dependencies["summary"], dependencies)

        handlers = {
            "load": lambda _state_doc: self._append_event(run_id, cartridge_id, "state_load", "load", "卡带已加载", {}),
            "welcome": lambda _state_doc: self._append_event(run_id, cartridge_id, "state_welcome", "welcome", "Welcome 已准备", {}),
            "permission": handle_permission,
            "environment_check": handle_environment,
            "dependency_resolution": handle_dependencies,
            "input_collect": lambda _state_doc: self._append_event(run_id, cartridge_id, "input_collected", "input_collect", "输入已收集", {"inputs": inputs or {}}),
            "run": handle_run,
            "workspace_open": handle_workspace,
            "artifact_collect": lambda _state_doc: self._append_event(run_id, cartridge_id, "artifact_collected", "artifact_collect", "Artifact 已整理", {"artifacts": run.get("artifacts", [])}),
            "monitor": lambda _state_doc: self._append_event(run_id, cartridge_id, "state_monitor", "monitor", "Monitor 已完成", {}),
            "delivery": handle_delivery,
        }

        root_flow_states = root_flow.get("states") or {}
        lifecycle_states = set(handlers.keys()) | {"start", "complete"}
        lab_failed = False

        def make_lab_node_handler(state_name_: str):
            def _handle(_state_doc: dict):
                nonlocal lab_failed
                state_ = root_flow_states.get(state_name_) or {}
                store = _state_doc["context"].setdefault("store", {})
                params_ = state_.get("params") or {}
                preset_config_ = params_.get("preset_config") or {}
                abort_on_failed = bool(params_.get("abort_on_failed") or preset_config_.get("abort_on_failed"))
                input_key = params_.get("input") or preset_config_.get("from") or preset_config_.get("source") or preset_config_.get("items")

                def _truncate(val, limit=2000):
                    if val is None:
                        return None
                    import json as _json
                    text = val if isinstance(val, str) else _json.dumps(val, ensure_ascii=False)
                    return text[:limit] + "…(截断)" if len(text) > limit else text

                def _failure_reason(result_: dict) -> str:
                    for item in result_.get("tool_results") or []:
                        if not isinstance(item, dict):
                            continue
                        tool_result = item.get("result") or {}
                        if not isinstance(tool_result, dict):
                            continue
                        label = f"{item.get('server', '')}/{item.get('tool', '')}".strip("/")
                        if tool_result.get("ok") is False:
                            return f"{label}: {tool_result.get('error') or 'tool returned ok=false'}"
                        if tool_result.get("asset_ok") is False:
                            issues = tool_result.get("issues") or []
                            return f"{label}: asset_ok=false; {issues[:3]}"
                        if tool_result.get("validation_ok") is False:
                            issues = tool_result.get("issues") or []
                            return f"{label}: validation_ok=false; {issues[:3]}"
                    return str(result_.get("error") or "node failed")

                input_value = _truncate(store.get(input_key)) if input_key and input_key in store else None

                try:
                    if state_.get("action") == "tool_call" and not self._is_v02_mcp_process(state_) and not normalized_probe_range and not self._tool_has_process_parent(root_flow, state_name_):
                        raise RuntimeError("工具节点必须直接挂在 AI 处理节点之后；请把 MCP/filesystem 工具节点连接到 action=llm_prompt 的处理节点后面。")
                    result = self.lab_node_executor.execute(state_name_, state_, _state_doc, run, run_dir)
                    skipped = result.get("skipped", False)
                    output_key = result.get("output")
                    output_value = _truncate(store.get(output_key)) if output_key and output_key in store else None
                    if result.get("action") in {"tool_call", "remote_call"}:
                        tool_results = result.get("tool_results") or []
                        artifacts = self._collect_tool_artifacts(run, run_dir, state_name_, tool_results)
                        if artifacts:
                            run["artifacts"] = self._merge_artifacts(run.get("artifacts", []), artifacts)
                            _state_doc["context"]["artifacts"] = run["artifacts"]
                            result["artifacts"] = artifacts
                        output_value = _truncate(next((
                            (tr.get("result") or {}).get("content") or (tr.get("result") or {}).get("error")
                            for tr in tool_results if isinstance(tr, dict)
                        ), output_value))
                    if result.get("paused") and result.get("pause_status") == "paused_waiting_user":
                        pending = result.get("pending_interaction") if isinstance(result.get("pending_interaction"), dict) else {}
                        pending["node_id"] = state_name_
                        run["status"] = "paused_waiting_user"
                        run["current_state"] = state_name_
                        run["pending_interaction"] = pending
                        _state_doc["context"]["_pause_flow"] = {
                            "state": state_name_,
                            "status": "paused_waiting_user",
                            "pending_interaction": pending,
                        }
                        event_type = "lab_node_paused"
                        event_msg = f"节点 {state_name_} 暂停等待用户输入"
                    elif result.get("failed"):
                        lab_failed = True
                        if abort_on_failed:
                            _state_doc["context"]["_abort_flow"] = {
                                "state": state_name_,
                                "reason": _failure_reason(result),
                                "action": result.get("action"),
                            }
                        event_type = "lab_node_failed"
                        event_msg = f"节点 {state_name_} 执行失败：{result.get('action', '')}"
                    else:
                        event_type = "lab_node_skipped" if skipped else "lab_node_executed"
                        event_msg = f"节点 {state_name_} 已{'跳过' if skipped else '执行'}：{result.get('action', '')}"
                    result["input_key"] = input_key
                    result["input_value"] = input_value
                    result["output_value"] = output_value
                except Exception as exc:
                    lab_failed = True
                    if abort_on_failed:
                        _state_doc["context"]["_abort_flow"] = {
                            "state": state_name_,
                            "reason": str(exc),
                            "action": state_.get("action"),
                        }
                    result = {"action": state_.get("action"), "failed": True, "error": str(exc), "error_type": exc.__class__.__name__, "input_key": input_key, "input_value": input_value, "output_value": None}
                    event_type = "lab_node_failed"
                    event_msg = f"节点 {state_name_} 执行失败：{exc}"
                self._append_event(run_id, cartridge_id, event_type, state_name_, event_msg, result)
            return _handle

        for state_name_ in root_flow_states:
            if state_name_ not in lifecycle_states and state_name_ not in handlers:
                handlers[state_name_] = make_lab_node_handler(state_name_)

        original_enter = engine.enter
        def enter_and_sync(doc: dict, state_name: str):
            item = original_enter(doc, state_name)
            sync_state(state_name)
            self._append_event(run_id, cartridge_id, "state_entered", state_name, f"进入阶段：{item['title']}", item)
            return item
        engine.enter = enter_and_sync

        engine.run_standard_flow(state_doc, handlers)
        run["current_state"] = state_doc["current_state"]
        paused = (state_doc.get("context") or {}).get("_pause_flow")
        if paused:
            run["pending_interaction"] = paused.get("pending_interaction") or run.get("pending_interaction") or {}
        run["status"] = (
            "paused_waiting_user" if paused
            else "failed" if lab_failed
            else "completed" if normalized_probe_range or state_doc["current_state"] == "complete"
            else "completed"
        )
        run["updated_at"] = now_iso()
        state_doc["context"]["artifacts"] = run.get("artifacts", [])
        # 数据链体检：聚合各节点运行时如实上报的缺失 input 键（唯一依据执行器真实解析行为）。
        # 这是测试台"能检测到数据链断裂"的权威结论——之前这些 bug 在测试台完全隐形。
        data_chain = self._summarize_data_chain(run_id, state_doc, normalized_probe_range)
        run["data_chain"] = data_chain
        run_event_type = "run_paused" if paused else "run_failed" if lab_failed else "run_completed"
        run_event_message = "Root Flow 暂停等待用户输入" if paused else "Root Flow 执行失败" if lab_failed else "Root Flow 执行完成"
        self._append_event(
            run_id, cartridge_id, run_event_type, run["current_state"],
            run_event_message, {"status": run["status"], "data_chain": data_chain},
        )
        self._write_json(run_dir / "root_flow_state.json", state_doc)
        self._write_json(run_dir / "run.json", run)
        return run

    def build_compatibility_report(self, manifest: dict, root_flow: dict | None) -> dict:
        base = load_base_implementation(self.root)
        return build_compatibility_report(base, manifest, root_flow, self.root)

    def build_cartridge_compatibility_report(self, cartridge_id: str) -> dict:
        cartridge = self.registry.get_cartridge(cartridge_id)
        return self.build_compatibility_report(cartridge.get("manifest") or {}, cartridge.get("root_flow") or {})

    def validate_probe_range(self, root_flow: dict, probe_range: dict | None) -> dict:
        normalized = self._normalize_probe_range(root_flow, probe_range)
        if not normalized:
            raise ValueError("Probe range is required")
        return normalized

    def _node_kind(self, state: dict) -> str:
        params = state.get("params") or {}
        return str(state.get("kind") or params.get("kind") or "").strip()

    def _normalize_test_mode(self, test_mode: dict | None) -> dict:
        if not isinstance(test_mode, dict):
            return {}
        decision = str(test_mode.get("decision") or "").strip()
        tool = str(test_mode.get("tool") or "").strip()
        normalized: dict = {}
        if decision and decision != "live":
            if decision not in {"live_collaboration", "mock_resolved", "mock_interaction", "mock_blocked"}:
                raise ValueError(f"Unsupported decision test mode: {decision}")
            normalized["decision"] = decision
        if tool and tool != "real":
            if tool not in {"dry_run"}:
                raise ValueError(f"Unsupported tool test mode: {tool}")
            normalized["tool"] = tool
        return normalized

    def _is_v02_mcp_process(self, state: dict) -> bool:
        return state.get("type") == "process" and self._node_kind(state) in {"mcp_read", "mcp_execute", "remote_call"}

    def _is_probe_driver_process(self, state: dict) -> bool:
        kind = self._node_kind(state)
        category = (state.get("params") or {}).get("node_category")
        return state.get("action") == "llm_prompt" or category == "process" or kind in {
            "decision",
            "retrieval",
            "transform",
            "validation",
            "routing",
            "gate",
            "human_gate",
            "transfer",
        }

    def _seed_probe_driver_context(self, state_doc: dict, root_flow: dict, probe_range: dict, inputs: dict) -> None:
        store = state_doc["context"].setdefault("store", {})
        states = root_flow.get("states") or {}
        node_ids = probe_range.get("node_ids") or []
        driver_payload = {
            "mode": "probe_driver",
            "goal": "Drive the selected probe range with enough structured context for isolated node testing.",
            "inputs": inputs,
            "selected_nodes": [
                {
                    "id": node_id,
                    "title": (states.get(node_id) or {}).get("title") or node_id,
                    "action": (states.get(node_id) or {}).get("action"),
                }
                for node_id in node_ids
            ],
        }
        store["probe_driver_context"] = json.dumps(driver_payload, ensure_ascii=False, indent=2)
        # 记录探针替身填过哪些键。局部探针会为范围外未运行的上游节点补占位值，
        # 这是合法的隔离手段；但这些键并非真实数据流产出，测试台要如实标注，
        # 避免用户误以为"局部探针跑通 == 真实数据链完整"。
        seeded_keys: list[str] = []
        for node_id in node_ids:
            state = states.get(node_id) or {}
            params = state.get("params") or {}
            preset_config = params.get("preset_config") or {}
            category = params.get("node_category") or preset_config.get("node_category")
            if not self._is_probe_driver_process(state) and category != "process":
                continue
            raw_input = params.get("input") or preset_config.get("from") or preset_config.get("source") or preset_config.get("items")
            keys = [item.strip() for item in str(raw_input or "").replace("\r", "\n").replace(",", "\n").split("\n") if item.strip()]
            for key in keys:
                if key not in store:
                    store[key] = store["probe_driver_context"]
                    if key not in seeded_keys:
                        seeded_keys.append(key)
        state_doc["context"]["_probe_seeded_keys"] = seeded_keys

    def _summarize_data_chain(self, run_id: str, state_doc: dict, probe_range: dict | None) -> dict:
        """聚合本次运行的数据链体检结论。

        依据执行器在解析键时如实上报的 missing_inputs（写在各节点 lab 事件的 data 里），
        不另写一份键解析逻辑，因此永远与真实执行行为一致。

        - breaks：真实数据链断裂——某节点声明要读的 store 键，运行到它时在 store 里根本没有。
        - seeded：局部探针为范围外未运行的上游节点补的占位键（合法隔离手段，单独标注）。
          若本次是全流程运行（无探针裁剪），seeded 为空，breaks 即权威结论。
        """
        seeded = list((state_doc.get("context") or {}).get("_probe_seeded_keys") or [])
        breaks: list[dict] = []
        optional_missing: list[dict] = []
        seen: set[tuple[str, str, bool]] = set()
        for event in self.get_events(run_id):
            if not isinstance(event, dict):
                continue
            data = event.get("data") or {}
            missing = data.get("missing_inputs")
            if not missing:
                continue
            node_id = event.get("state") or data.get("state") or ""
            for item in missing:
                if isinstance(item, dict):
                    key = str(item.get("key") or "").strip()
                    required = bool(item.get("required", True))
                    source = item.get("source") or ("input" if required else "optional_input")
                else:
                    key = str(item or "").strip()
                    required = True
                    source = "input"
                if not key:
                    continue
                dedup = (node_id, key, required)
                if dedup in seen:
                    continue
                seen.add(dedup)
                entry = {
                    "node": node_id,
                    "key": key,
                    "required": required,
                    "source": source,
                    "severity": "error" if required else "info",
                    "seeded_by_probe": key in seeded,
                }
                if required:
                    breaks.append(entry)
                else:
                    optional_missing.append(entry)
        real_breaks = [item for item in breaks if not item["seeded_by_probe"]]
        return {
            "checked": True,
            "is_probe_run": bool(probe_range),
            "passed": len(real_breaks) == 0,
            "breaks": real_breaks,
            "missing_optional": optional_missing,
            "probe_seeded_keys": seeded,
            "summary": (
                f"数据链断裂 {len(real_breaks)} 处"
                if real_breaks
                else "数据链完整：所有节点声明的 input 键都由上游真实产出"
            ),
        }

    def _normalize_probe_range(self, root_flow: dict, probe_range: dict | None) -> dict | None:
        if not probe_range:
            return None
        states = root_flow.get("states") or {}
        if not states:
            raise ValueError("Cannot run probe range: root flow has no states")

        start_node_id = str(probe_range.get("start_node_id") or "").strip()
        end_node_id = str(probe_range.get("end_node_id") or "").strip()
        if start_node_id not in states:
            raise ValueError(f"Probe start node not found: {start_node_id}")
        if end_node_id not in states:
            raise ValueError(f"Probe end node not found: {end_node_id}")

        ordered_state_ids = list(states.keys())
        raw_node_ids = probe_range.get("node_ids") or []
        node_ids = [str(node_id).strip() for node_id in raw_node_ids if str(node_id).strip() in states]
        if not node_ids:
            start_index = ordered_state_ids.index(start_node_id)
            end_index = ordered_state_ids.index(end_node_id)
            if start_index > end_index:
                raise ValueError("Probe start node must be before probe end node")
            node_ids = ordered_state_ids[start_index:end_index + 1]

        if not node_ids or node_ids[0] != start_node_id or node_ids[-1] != end_node_id:
            raise ValueError("Probe node range must include start and end probes in execution order")

        seen_process = False
        for node_id in node_ids:
            state = states.get(node_id) or {}
            params = state.get("params") or {}
            category = params.get("node_category") or (params.get("preset_config") or {}).get("node_category")
            action = state.get("action")
            if self._is_probe_driver_process(state):
                seen_process = True
            if not self._is_v02_mcp_process(state) and (action in {"tool_call", "remote_call"} or category in {"tool", "remote"}):
                if not seen_process:
                    title = state.get("title") or node_id
                    raise ValueError(f"Probe range is invalid: tool/remote node '{title}' has no process node before it")

        return {
            "start_node_id": start_node_id,
            "end_node_id": end_node_id,
            "node_ids": node_ids,
            "node_count": len(node_ids),
        }

    def _build_probe_root_flow(self, root_flow: dict, probe_range: dict) -> dict:
        node_ids = probe_range.get("node_ids") or []
        node_id_set = set(node_ids)
        end_node_id = probe_range.get("end_node_id")
        filtered = deepcopy(root_flow)
        source_states = root_flow.get("states") or {}
        filtered_states = {
            node_id: deepcopy(source_states[node_id])
            for node_id in node_ids
            if node_id in source_states
        }

        # 保留原始子图拓扑：分支扇出必须全部保留，不能拍平成一条线。
        # 只保留两端都落在探针范围内的 next 与 edges；范围外的出边一律剪掉。
        probe_edges: list[dict] = []
        seen_edges: set[tuple[str, str]] = set()

        def _keep_edge(source: str, target: str) -> None:
            if source not in node_id_set or target not in node_id_set:
                return
            key = (source, target)
            if key in seen_edges:
                return
            seen_edges.add(key)
            probe_edges.append({"from": source, "to": target, "scope": "probe"})

        for node_id in node_ids:
            state = filtered_states.get(node_id)
            if not state:
                continue
            next_target = state.get("next")
            if node_id == end_node_id or next_target not in node_id_set:
                # 结束探针、或 next 指向范围外的节点：切断主边，避免跑出探针范围。
                state.pop("next", None)
            else:
                _keep_edge(node_id, next_target)

        for edge in root_flow.get("edges") or []:
            source = edge.get("from") or edge.get("source")
            target = edge.get("to") or edge.get("target")
            if source and target:
                _keep_edge(source, target)

        filtered["start"] = probe_range["start_node_id"]
        filtered["states"] = filtered_states
        filtered["edges"] = probe_edges
        filtered["_probe_range"] = probe_range
        return filtered

    def _tool_has_process_parent(self, root_flow: dict, node_id: str) -> bool:
        states = root_flow.get("states") or {}
        parents = []
        for state_id, state in states.items():
            if state.get("next") == node_id:
                parents.append(state_id)
        for edge in root_flow.get("edges") or []:
            source = edge.get("from") or edge.get("source")
            target = edge.get("to") or edge.get("target")
            if target == node_id and source:
                parents.append(source)
        if not parents:
            return False
        for parent_id in set(parents):
            parent = states.get(parent_id) or {}
            if self._is_probe_driver_process(parent):
                return True
        return False

    def _collect_tool_artifacts(self, run: dict, run_dir: Path, state_name: str, tool_results: list[dict]) -> list[dict]:
        artifacts = []
        for item in tool_results or []:
            if not isinstance(item, dict):
                continue
            if item.get("server") == "filesystem" and item.get("tool") not in {"write_file", "append_file"}:
                continue
            if item.get("server") not in {"filesystem", "media"}:
                continue
            result = item.get("result") or {}
            if not isinstance(result, dict) or not result.get("ok"):
                continue
            result_paths = self._artifact_paths_from_tool_result(result)
            if not result_paths:
                continue
            for result_path in result_paths:
                artifact = self._artifact_from_path(run, state_name, item, result_path, artifacts)
                if artifact:
                    artifacts.append(artifact)
        return artifacts

    def _artifact_paths_from_tool_result(self, result: dict) -> list[Path]:
        candidates = []
        for key in ["path", "video_path", "audio_path", "project_path", "preview_path"]:
            if result.get(key):
                candidates.append(result.get(key))
        for item in result.get("files") or []:
            if item:
                candidates.append(item)
        paths = []
        seen = set()
        for item in candidates:
            text = str(item)
            if text in seen:
                continue
            seen.add(text)
            paths.append(Path(text))
        return paths

    def _artifact_from_path(self, run: dict, state_name: str, tool_result: dict, path: Path, pending: list[dict]) -> dict | None:
        if not path.is_absolute():
            path = self.root / path
        try:
            resolved = path.resolve()
            root = self.root.resolve()
            if resolved != root and root not in resolved.parents:
                return None
            if not resolved.is_file():
                return None
            rel_path = resolved.relative_to(root).as_posix()
            name = self._unique_artifact_name(run.get("artifacts", []) + pending, resolved.name)
            artifact = self.artifact_manager.make_artifact(
                run,
                f"{state_name}_{len(run.get('artifacts', [])) + len(pending) + 1}",
                name,
                resolved,
                self._artifact_type_for_path(resolved),
                self._mime_type_for_path(resolved),
            )
            artifact["display_path"] = rel_path
            artifact["source"] = {
                **(artifact.get("source") or {}),
                "node_id": state_name,
                "tool": f"{tool_result.get('server')}/{tool_result.get('tool')}",
            }
        except Exception:
            return None
        return artifact

    def _merge_artifacts(self, current: list[dict], incoming: list[dict] | None) -> list[dict]:
        merged = list(current or [])
        seen_paths = {str(item.get("path") or "") for item in merged if isinstance(item, dict)}
        seen_names = {str(item.get("name") or "") for item in merged if isinstance(item, dict)}
        for artifact in incoming or []:
            if not isinstance(artifact, dict):
                continue
            path = str(artifact.get("path") or "")
            name = str(artifact.get("name") or "")
            if path and path in seen_paths:
                continue
            if name and name in seen_names and not path:
                continue
            merged.append(artifact)
            if path:
                seen_paths.add(path)
            if name:
                seen_names.add(name)
        return merged

    def _unique_artifact_name(self, artifacts: list[dict], filename: str) -> str:
        safe = self.artifact_manager._safe_filename(filename)
        names = {item.get("name") for item in artifacts if isinstance(item, dict)}
        if safe not in names:
            return safe
        stem = Path(safe).stem or "artifact"
        suffix = Path(safe).suffix
        index = 2
        while f"{stem}-{index}{suffix}" in names:
            index += 1
        return f"{stem}-{index}{suffix}"

    def _artifact_type_for_path(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".md", ".markdown"}:
            return "markdown"
        if suffix in {".html", ".htm"}:
            return "html"
        if suffix == ".json":
            return "json"
        if suffix == ".csv":
            return "csv"
        if suffix in {".mp4", ".mov", ".avi", ".webm"}:
            return "video"
        if suffix in {".wav", ".mp3", ".m4a", ".ogg"}:
            return "audio"
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            return "image"
        if suffix in {".glb", ".gltf", ".obj", ".fbx"}:
            return "model"
        return "text"

    def _mime_type_for_path(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".md", ".markdown"}:
            return "text/markdown"
        if suffix in {".html", ".htm"}:
            return "text/html"
        if suffix == ".json":
            return "application/json"
        if suffix == ".csv":
            return "text/csv"
        if suffix == ".mp4":
            return "video/mp4"
        if suffix == ".mov":
            return "video/quicktime"
        if suffix == ".avi":
            return "video/x-msvideo"
        if suffix == ".webm":
            return "video/webm"
        if suffix == ".wav":
            return "audio/wav"
        if suffix == ".mp3":
            return "audio/mpeg"
        if suffix == ".m4a":
            return "audio/mp4"
        if suffix == ".ogg":
            return "audio/ogg"
        if suffix == ".png":
            return "image/png"
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix == ".gif":
            return "image/gif"
        if suffix == ".webp":
            return "image/webp"
        if suffix == ".glb":
            return "model/gltf-binary"
        if suffix == ".gltf":
            return "model/gltf+json"
        if suffix == ".obj":
            return "model/obj"
        if suffix == ".fbx":
            return "application/octet-stream"
        return "text/plain"

    def list_runs(self) -> list[dict]:
        runs = []
        for run_path in self.runs_dir.glob("*/run.json"):
            run = self._read_json(run_path)
            run["_sort_mtime"] = run_path.stat().st_mtime
            runs.append(run)
        runs.sort(key=lambda item: (str(item.get("updated_at") or item.get("created_at") or ""), item.get("_sort_mtime") or 0), reverse=True)
        for run in runs:
            run.pop("_sort_mtime", None)
        return runs

    def get_run(self, run_id: str) -> dict:
        path = self.runs_dir / run_id / "run.json"
        if not path.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")
        return self._read_json(path)

    def get_events(self, run_id: str) -> list[dict]:
        path = self.runs_dir / run_id / "events.jsonl"
        if not path.exists():
            return []
        events = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def get_delivery(self, run_id: str) -> dict:
        path = self.runs_dir / run_id / "delivery.json"
        if not path.exists():
            raise FileNotFoundError(f"Delivery not found: {run_id}")
        return self._read_json(path)

    def answer_pending_interaction(self, run_id: str, values: dict | str | None = None) -> dict:
        run_dir = self.runs_dir / run_id
        run = self.get_run(run_id)
        pending = run.get("pending_interaction")
        if run.get("status") != "paused_waiting_user" or not isinstance(pending, dict):
            raise ValueError("Run is not waiting for a pending interaction answer")

        state_path = run_dir / "root_flow_state.json"
        if not state_path.exists():
            raise FileNotFoundError(f"Run state not found: {run_id}")
        state_doc = self._read_json(state_path)
        context = state_doc.setdefault("context", {})
        store = context.setdefault("store", {})
        question = pending.get("question") if isinstance(pending.get("question"), dict) else {}
        store_key = str(question.get("store_key") or "user_reply").strip() or "user_reply"
        answer_value = values if values is not None else {}
        store[store_key] = answer_value

        answered_at = now_iso()
        answer_record = {
            "interaction_id": pending.get("interaction_id"),
            "node_id": pending.get("node_id"),
            "store_key": store_key,
            "answered_at": answered_at,
        }
        run.setdefault("answered_interactions", []).append({**answer_record, "value": answer_value})
        resolved_resume = self._resolve_answer_resume(pending.get("resume"), answer_value)
        pending["resume"] = resolved_resume
        self._apply_resume_store_effects(resolved_resume, answer_value, store)
        run.pop("pending_interaction", None)
        run["status"] = "running"
        run["updated_at"] = answered_at
        context.pop("_pause_flow", None)
        store.pop("_pending_interaction", None)

        cartridge_id = run.get("cartridge_id")
        cartridge = self.registry.get_cartridge(cartridge_id)
        manifest = cartridge.get("manifest") or {}
        source_root_flow = cartridge.get("root_flow") or {}
        probe_range = run.get("probe_range")
        root_flow = self._build_probe_root_flow(source_root_flow, probe_range) if probe_range else source_root_flow
        start_state, include_paused_parent = self._resolve_resume_start(root_flow, pending, state_doc.get("current_state"))
        replay_exclusions = self._resume_replay_exclusions(root_flow, resolved_resume, start_state)

        completed_parents = self._completed_parent_map_from_history(
            root_flow,
            state_doc,
            include_paused_node=include_paused_parent,
            exclude_states=replay_exclusions,
        )
        visited = self._completed_visited_from_history(
            state_doc,
            exclude_state=start_state,
            include_paused_node=include_paused_parent,
            exclude_states=replay_exclusions,
        )
        initial_queue = self._resume_initial_queue(root_flow, start_state, visited, completed_parents)

        self._write_json(state_path, state_doc)
        self._write_json(run_dir / "run.json", run)
        self._append_event(
            run_id,
            cartridge_id,
            "pending_interaction_answered",
            pending.get("node_id") or state_doc.get("current_state") or start_state,
            "Pending interaction answered",
            answer_record,
        )
        self._append_event(
            run_id,
            cartridge_id,
            "run_resumed",
            start_state,
            "Run resumed from pending interaction",
            {
                "resume": pending.get("resume") or {},
                "start_state": start_state,
                "store_key": store_key,
            },
        )

        return self._continue_run(
            run=run,
            run_dir=run_dir,
            manifest=manifest,
            root_flow=root_flow,
            source_root_flow=source_root_flow,
            state_doc=state_doc,
            normalized_probe_range=probe_range,
            inputs=run.get("inputs") or {},
            start_state=start_state,
            visited=visited,
            completed_parents=completed_parents,
            initial_queue=initial_queue,
        )

    def _continue_run(
        self,
        run: dict,
        run_dir: Path,
        manifest: dict,
        root_flow: dict,
        source_root_flow: dict,
        state_doc: dict,
        normalized_probe_range: dict | None,
        inputs: dict,
        start_state: str,
        visited: set[str] | None = None,
        completed_parents: dict[str, set[str]] | None = None,
        initial_queue: list[str] | None = None,
    ) -> dict:
        run_id = run["run_id"]
        cartridge_id = run["cartridge_id"]
        engine = RootFlowEngine(root_flow)

        def sync_state(state_name: str):
            run["current_state"] = state_name
            run["updated_at"] = now_iso()
            self._write_json(run_dir / "run.json", run)
            self._write_json(run_dir / "root_flow_state.json", state_doc)

        def handle_run(_state_doc: dict):
            runtime_result = self._start_runtime(run, run_dir)
            run["runtime_run_id"] = runtime_result.get("runtime_run_id")
            run["artifacts"] = self._merge_artifacts(run.get("artifacts", []), runtime_result.get("artifacts", []))
            run["status"] = "completed" if runtime_result.get("status") == "completed" else "running"
            _state_doc["context"]["artifacts"] = run["artifacts"]
            self._append_event(run_id, cartridge_id, "runtime_completed", "run", "Runtime completed", {"runtime": runtime_result})

        def handle_workspace(_state_doc: dict):
            run["workspace_state"] = self.workspace_host.open(run)
            self._append_event(run_id, cartridge_id, "workspace_opened", "workspace_open", "Workspace state updated", run["workspace_state"])

        def handle_delivery(_state_doc: dict):
            delivery = self._create_initial_delivery(run, manifest)
            run["delivery"] = delivery
            run["status"] = "completed" if run.get("artifacts") else run.get("status", "created")
            self._write_json(run_dir / "delivery.json", delivery)
            self._append_event(run_id, cartridge_id, "delivery_ready", "delivery", "Delivery generated", delivery)

        def handle_permission(_state_doc: dict):
            perm_state = run.get("permissions", {})
            risk = self.permission_manager.get_risk_summary(perm_state)
            _state_doc["context"]["permission_risk"] = risk
            self._append_event(run_id, cartridge_id, "permission_checked", "permission", f"Permission risk: {risk['label']}", risk)

        def handle_environment(_state_doc: dict):
            environment = self.environment_checker.check(manifest)
            run["environment"] = environment
            _state_doc["context"]["environment"] = environment
            self._append_event(run_id, cartridge_id, "environment_checked", "environment_check", environment["summary"], environment)

        def handle_dependencies(_state_doc: dict):
            dependencies = self.dependency_resolver.resolve(manifest, run.get("environment", {}))
            run["dependencies"] = dependencies
            _state_doc["context"]["dependencies"] = dependencies
            self._append_event(run_id, cartridge_id, "dependencies_resolved", "dependency_resolution", dependencies["summary"], dependencies)

        handlers = {
            "load": lambda _state_doc: self._append_event(run_id, cartridge_id, "state_load", "load", "Cartridge loaded", {}),
            "welcome": lambda _state_doc: self._append_event(run_id, cartridge_id, "state_welcome", "welcome", "Welcome ready", {}),
            "permission": handle_permission,
            "environment_check": handle_environment,
            "dependency_resolution": handle_dependencies,
            "input_collect": lambda _state_doc: self._append_event(run_id, cartridge_id, "input_collected", "input_collect", "Inputs collected", {"inputs": inputs or {}}),
            "run": handle_run,
            "workspace_open": handle_workspace,
            "artifact_collect": lambda _state_doc: self._append_event(run_id, cartridge_id, "artifact_collected", "artifact_collect", "Artifacts collected", {"artifacts": run.get("artifacts", [])}),
            "monitor": lambda _state_doc: self._append_event(run_id, cartridge_id, "state_monitor", "monitor", "Monitor completed", {}),
            "delivery": handle_delivery,
        }

        root_flow_states = root_flow.get("states") or {}
        lifecycle_states = set(handlers.keys()) | {"start", "complete"}
        lab_failed = False

        def make_lab_node_handler(state_name_: str):
            def _handle(_state_doc: dict):
                nonlocal lab_failed
                state_ = root_flow_states.get(state_name_) or {}
                store = _state_doc["context"].setdefault("store", {})
                params_ = state_.get("params") or {}
                preset_config_ = params_.get("preset_config") or {}
                abort_on_failed = bool(params_.get("abort_on_failed") or preset_config_.get("abort_on_failed"))
                input_key = params_.get("input") or preset_config_.get("from") or preset_config_.get("source") or preset_config_.get("items")

                def _truncate(val, limit=2000):
                    if val is None:
                        return None
                    text = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
                    return text[:limit] + "...(truncated)" if len(text) > limit else text

                def _failure_reason(result_: dict) -> str:
                    for item in result_.get("tool_results") or []:
                        if not isinstance(item, dict):
                            continue
                        tool_result = item.get("result") or {}
                        if not isinstance(tool_result, dict):
                            continue
                        label = f"{item.get('server', '')}/{item.get('tool', '')}".strip("/")
                        if tool_result.get("ok") is False:
                            return f"{label}: {tool_result.get('error') or 'tool returned ok=false'}"
                        if tool_result.get("asset_ok") is False:
                            issues = tool_result.get("issues") or []
                            return f"{label}: asset_ok=false; {issues[:3]}"
                        if tool_result.get("validation_ok") is False:
                            issues = tool_result.get("issues") or []
                            return f"{label}: validation_ok=false; {issues[:3]}"
                    return str(result_.get("error") or "node failed")

                input_value = _truncate(store.get(input_key)) if input_key and input_key in store else None

                try:
                    if state_.get("action") == "tool_call" and not self._is_v02_mcp_process(state_) and not normalized_probe_range and not self._tool_has_process_parent(root_flow, state_name_):
                        raise RuntimeError("Tool nodes must be connected after a process node.")
                    result = self.lab_node_executor.execute(state_name_, state_, _state_doc, run, run_dir)
                    skipped = result.get("skipped", False)
                    output_key = result.get("output")
                    output_value = _truncate(store.get(output_key)) if output_key and output_key in store else None
                    if result.get("action") in {"tool_call", "remote_call"}:
                        tool_results = result.get("tool_results") or []
                        artifacts = self._collect_tool_artifacts(run, run_dir, state_name_, tool_results)
                        if artifacts:
                            run["artifacts"] = self._merge_artifacts(run.get("artifacts", []), artifacts)
                            _state_doc["context"]["artifacts"] = run["artifacts"]
                            result["artifacts"] = artifacts
                        output_value = _truncate(next((
                            (tr.get("result") or {}).get("content") or (tr.get("result") or {}).get("error")
                            for tr in tool_results if isinstance(tr, dict)
                        ), output_value))
                    if result.get("paused") and result.get("pause_status") == "paused_waiting_user":
                        pending = result.get("pending_interaction") if isinstance(result.get("pending_interaction"), dict) else {}
                        pending["node_id"] = state_name_
                        run["status"] = "paused_waiting_user"
                        run["current_state"] = state_name_
                        run["pending_interaction"] = pending
                        _state_doc["context"]["_pause_flow"] = {
                            "state": state_name_,
                            "status": "paused_waiting_user",
                            "pending_interaction": pending,
                        }
                        event_type = "lab_node_paused"
                        event_msg = f"Node {state_name_} paused waiting for user input"
                    elif result.get("failed"):
                        lab_failed = True
                        if abort_on_failed:
                            _state_doc["context"]["_abort_flow"] = {
                                "state": state_name_,
                                "reason": _failure_reason(result),
                                "action": result.get("action"),
                            }
                        event_type = "lab_node_failed"
                        event_msg = f"Node {state_name_} failed: {result.get('action', '')}"
                    else:
                        event_type = "lab_node_skipped" if skipped else "lab_node_executed"
                        event_msg = f"Node {state_name_} {'skipped' if skipped else 'executed'}: {result.get('action', '')}"
                    result["input_key"] = input_key
                    result["input_value"] = input_value
                    result["output_value"] = output_value
                except Exception as exc:
                    lab_failed = True
                    if abort_on_failed:
                        _state_doc["context"]["_abort_flow"] = {
                            "state": state_name_,
                            "reason": str(exc),
                            "action": state_.get("action"),
                        }
                    result = {"action": state_.get("action"), "failed": True, "error": str(exc), "error_type": exc.__class__.__name__, "input_key": input_key, "input_value": input_value, "output_value": None}
                    event_type = "lab_node_failed"
                    event_msg = f"Node {state_name_} failed: {exc}"
                self._append_event(run_id, cartridge_id, event_type, state_name_, event_msg, result)
            return _handle

        for state_name_ in root_flow_states:
            if state_name_ not in lifecycle_states and state_name_ not in handlers:
                handlers[state_name_] = make_lab_node_handler(state_name_)

        original_enter = engine.enter

        def enter_and_sync(doc: dict, state_name: str):
            item = original_enter(doc, state_name)
            sync_state(state_name)
            self._append_event(run_id, cartridge_id, "state_entered", state_name, f"Entered state: {item['title']}", item)
            return item

        engine.enter = enter_and_sync
        state_doc["status"] = "running"
        engine.run_standard_flow(
            state_doc,
            handlers,
            start_state=start_state,
            visited=visited,
            completed_parents=completed_parents,
            initial_queue=initial_queue,
        )

        run["current_state"] = state_doc["current_state"]
        paused = (state_doc.get("context") or {}).get("_pause_flow")
        if paused:
            run["pending_interaction"] = paused.get("pending_interaction") or run.get("pending_interaction") or {}
        else:
            run.pop("pending_interaction", None)
        run["status"] = (
            "paused_waiting_user" if paused
            else "failed" if lab_failed
            else "completed" if normalized_probe_range or state_doc["current_state"] == "complete"
            else "completed"
        )
        run["updated_at"] = now_iso()
        state_doc["context"]["artifacts"] = run.get("artifacts", [])
        data_chain = self._summarize_data_chain(run_id, state_doc, normalized_probe_range)
        run["data_chain"] = data_chain
        run_event_type = "run_paused" if paused else "run_failed" if lab_failed else "run_completed"
        run_event_message = "Root Flow paused waiting for user input" if paused else "Root Flow execution failed" if lab_failed else "Root Flow execution completed"
        self._append_event(
            run_id,
            cartridge_id,
            run_event_type,
            run["current_state"],
            run_event_message,
            {"status": run["status"], "data_chain": data_chain},
        )
        self._write_json(run_dir / "root_flow_state.json", state_doc)
        self._write_json(run_dir / "run.json", run)
        return run

    def _resolve_answer_resume(self, resume: dict | None, answer_value) -> dict:
        base_resume = dict(resume) if isinstance(resume, dict) else {}
        routes = base_resume.get("answer_routes")
        if not isinstance(routes, list):
            return base_resume
        for route in routes:
            if not isinstance(route, dict):
                continue
            matcher = route.get("match") if isinstance(route.get("match"), dict) else {}
            if not self._answer_route_matches(answer_value, matcher):
                continue
            resolved = dict(base_resume)
            resolved.pop("answer_routes", None)
            for key in (
                "policy",
                "target_node",
                "replay_from_target",
                "clear_downstream",
                "copy_answer_to",
                "clear_store_keys",
            ):
                if key in route:
                    resolved[key] = route[key]
            return resolved
        return base_resume

    def _answer_route_matches(self, answer_value, matcher: dict) -> bool:
        field = str(matcher.get("field") or "").strip()
        if field and isinstance(answer_value, dict):
            candidate = answer_value.get(field)
        else:
            candidate = answer_value
        text = self._answer_text(candidate)
        all_text = self._answer_text(answer_value)

        equals = matcher.get("equals")
        if equals is not None:
            values = equals if isinstance(equals, list) else [equals]
            lowered = text.strip().lower()
            if any(lowered == str(value).strip().lower() for value in values):
                return True

        contains = matcher.get("contains")
        if contains is not None and str(contains).strip().lower() in text.lower():
            return True

        contains_any = matcher.get("contains_any")
        if isinstance(contains_any, list):
            haystack = text.lower() if field else all_text.lower()
            if any(str(item).strip().lower() and str(item).strip().lower() in haystack for item in contains_any):
                return True

        return False

    def _answer_text(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, dict):
            return " ".join(self._answer_text(item) for item in value.values())
        if isinstance(value, list):
            return " ".join(self._answer_text(item) for item in value)
        return str(value)

    def _apply_resume_store_effects(self, resume: dict, answer_value, store: dict) -> None:
        if not isinstance(resume, dict):
            return
        copy_to = str(resume.get("copy_answer_to") or "").strip()
        if copy_to:
            store[copy_to] = answer_value
        clear_keys = resume.get("clear_store_keys")
        if isinstance(clear_keys, str):
            clear_keys = [item.strip() for item in clear_keys.replace("\r", "\n").replace(",", "\n").split("\n") if item.strip()]
        if isinstance(clear_keys, list):
            for key in clear_keys:
                key = str(key or "").strip()
                if key:
                    store.pop(key, None)

    def _resume_replay_exclusions(self, root_flow: dict, resume: dict, start_state: str) -> set[str]:
        if not isinstance(resume, dict):
            return set()
        if not (resume.get("replay_from_target") or resume.get("clear_downstream")):
            return set()
        return self._flow_descendants(root_flow, start_state, include_start=True)

    def _flow_descendants(self, root_flow: dict, start_state: str, include_start: bool = False) -> set[str]:
        states = root_flow.get("states") if isinstance(root_flow, dict) else {}
        if not start_state or start_state not in (states or {}):
            return set()
        engine = RootFlowEngine(root_flow)
        result = {start_state} if include_start else set()
        queue = list(engine.next_states(start_state))
        while queue:
            state_name = queue.pop(0)
            if state_name in result:
                continue
            result.add(state_name)
            for target in engine.next_states(state_name):
                if target not in result and target not in queue:
                    queue.append(target)
        return result

    def _resolve_resume_start(self, root_flow: dict, pending: dict, current_state: str | None) -> tuple[str, bool]:
        states = root_flow.get("states") or {}
        node_id = str(pending.get("node_id") or current_state or "").strip()
        if not node_id or node_id not in states:
            raise ValueError("Pending interaction node is not present in root flow")
        resume = pending.get("resume") if isinstance(pending.get("resume"), dict) else {}
        policy = str(resume.get("policy") or "resume_same_node").strip()
        if policy == "resume_same_node":
            return node_id, False
        if policy == "resume_next_node":
            engine = RootFlowEngine(root_flow)
            next_states = engine.next_states(node_id)
            if not next_states:
                raise ValueError("Cannot resume next node: paused node has no next state")
            return next_states[0], True
        if policy == "resume_target_node":
            target = str(resume.get("target_node") or "").strip()
            if not target or target not in states:
                raise ValueError("Cannot resume target node: resume.target_node is invalid")
            return target, True
        if policy == "restart_run_with_inputs":
            raise ValueError("restart_run_with_inputs is not supported by this base because it may replay side effects")
        if policy == "manual_only":
            raise ValueError("manual_only interactions cannot be resumed automatically")
        raise ValueError(f"Unsupported resume policy: {policy}")

    def _completed_parent_map_from_history(
        self,
        root_flow: dict,
        state_doc: dict,
        include_paused_node: bool = False,
        exclude_states: set[str] | None = None,
    ) -> dict[str, set[str]]:
        completed = self._completed_visited_from_history(
            state_doc,
            include_paused_node=include_paused_node,
            exclude_states=exclude_states,
        )
        states = root_flow.get("states") or {}
        result: dict[str, set[str]] = {}
        for source_id in completed:
            state = states.get(source_id) or {}
            target = state.get("next")
            if target in states:
                result.setdefault(target, set()).add(source_id)
        for edge in root_flow.get("edges") or []:
            source = edge.get("from") or edge.get("source")
            target = edge.get("to") or edge.get("target")
            if source in completed and target in states:
                result.setdefault(target, set()).add(source)
        return result

    def _resume_initial_queue(
        self,
        root_flow: dict,
        start_state: str,
        visited: set[str] | None,
        completed_parents: dict[str, set[str]] | None,
    ) -> list[str]:
        states = root_flow.get("states") or {}
        if start_state not in states:
            return []
        engine = RootFlowEngine(root_flow)
        incoming_counts = engine._incoming_counts()
        completed_parents = completed_parents or {}
        visited = visited or set()
        queue = [start_state]
        queued = {start_state}
        for state_id in states:
            if state_id in queued or state_id in visited:
                continue
            waiting_for = incoming_counts.get(state_id, 0)
            if waiting_for <= 0:
                continue
            if waiting_for <= len(completed_parents.get(state_id, set())):
                queue.append(state_id)
                queued.add(state_id)
        return queue

    def _completed_visited_from_history(
        self,
        state_doc: dict,
        exclude_state: str | None = None,
        include_paused_node: bool = False,
        exclude_states: set[str] | None = None,
    ) -> set[str]:
        completed: set[str] = set()
        excluded = set(exclude_states or set())
        if exclude_state:
            excluded.add(exclude_state)
        for item in state_doc.get("history") or []:
            state = str(item.get("state") or "").strip()
            if not state or state in excluded:
                continue
            status = item.get("status")
            if status == "completed" or (include_paused_node and status == "paused_waiting_user"):
                completed.add(state)
        return completed

    def control(self, run_id: str, action: str) -> dict:
        run = self.get_run(run_id)
        if action == "cancel":
            run["status"] = "cancelled"
            run["current_state"] = "cancelled"
        elif action == "pause":
            run["status"] = "paused"
            run["current_state"] = "paused"
        elif action == "resume":
            if run.get("status") == "paused_waiting_user":
                raise ValueError("Use pending-interaction/answer to resume a run waiting for user input")
            run["status"] = "created"
            run["current_state"] = "created"
        else:
            raise ValueError(f"Unsupported action: {action}")
        run["updated_at"] = now_iso()
        self._write_json(self.runs_dir / run_id / "run.json", run)
        self._append_event(run_id, run["cartridge_id"], f"run_{action}", run["current_state"], f"运行控制：{action}", {})
        return run

    def _start_runtime(self, run: dict, run_dir: Path) -> dict:
        return self.runtime_manager.start(run, run_dir)

    def _create_initial_delivery(self, run: dict, manifest: dict) -> dict:
        inputs = run.get("inputs") or {}
        title = inputs.get("title") or inputs.get("task_description") or "未命名任务"
        artifacts = run.get("artifacts", [])
        actions = []
        for artifact in artifacts:
            if artifact.get("url"):
                actions.append({
                    "id": f"open_{artifact.get('artifact_id')}",
                    "label": f"打开 {artifact.get('name')}",
                    "url": artifact.get("url"),
                })
        summary = f"卡带运行完成：{title}" if artifacts else f"卡带运行记录已创建：{title}"
        return {
            "run_id": run["run_id"],
            "type": manifest.get("delivery", {}).get("type", "summary_with_artifacts"),
            "summary": summary,
            "artifacts": artifacts,
            "actions": actions,
            "created_at": now_iso(),
        }

    def _append_event(self, run_id: str, cartridge_id: str, event_type: str, state: str, message: str, data: dict):
        event = {
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "cartridge_id": cartridge_id,
            "type": event_type,
            "state": state,
            "message": message,
            "data": data,
            "created_at": now_iso(),
        }
        path = self.runs_dir / run_id / "events.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _read_json(self, path: Path) -> dict:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
