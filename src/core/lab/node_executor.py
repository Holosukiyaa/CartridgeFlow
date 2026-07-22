"""Lab 节点通用执行器。

按节点 action 分发执行，通过 context.store 实现节点间数据传递。

IO 约定：
- context.store            本次运行共享键值空间，所有节点可读写
- node.params.input        节点从 context.store 读取的 key，多个用英文逗号分隔
- node.params.output       节点把结果写入 context.store 的 key
- node.params.save_to      store 节点专用，等同 output
- node.params.tools        工具节点声明的工具槽，type=builtin 时调用内置 MCP 服务
- node.params.preset_config 字段在 input/output 未显式设置时作为 fallback
"""

from __future__ import annotations
import asyncio
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

from core.cartridge.node_normalizer import normalize_runtime_node
from core.cartridge.assets import load_asset_bundle, materialize_passive_html
from core.protocol import parse_decision_envelope, validate_decision_envelope, validate_tool_plan
from core.protocol.decision_envelope import make_blocked_decision_envelope, make_mock_decision_envelope
from core.runtime.state_machine import assert_transition


class LabNodeExecutor:

    def __init__(self, workspace_root: str | Path | None = None):
        from core.lab.builtin_mcp import BuiltinMcpRegistry
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self._builtin_mcp = BuiltinMcpRegistry(self.workspace_root)
        self._scoped_mcp_registries: dict[str, object] = {}

    def _registry_for_run(self, run: dict):
        """Use a manifest-scoped registry for protocol or portable-DLC extensions."""
        extensions = run.get("protocol_extensions") if isinstance(run, dict) else None
        portable_dlc = run.get("portable_dlc") if isinstance(run, dict) else None
        package_path = run.get("package_path") if isinstance(run, dict) else None
        if not extensions and not portable_dlc:
            return self._builtin_mcp

        from core.lab.builtin_mcp import BuiltinMcpRegistry
        from core.protocol import load_base_implementation

        capabilities = run.get("base_capabilities") if isinstance(run, dict) else None
        supported_protocols = run.get("base_supported_protocols") if isinstance(run, dict) else None
        if not capabilities or not supported_protocols:
            try:
                base = load_base_implementation(self.workspace_root)
                capabilities = capabilities or base.get("capabilities") or []
                supported_protocols = supported_protocols or base.get("supported_protocols") or []
            except Exception:
                capabilities = []
                supported_protocols = []
        cache_key = json.dumps(
            {
                "extensions": extensions,
                "portable_dlc": portable_dlc,
                "package_path": package_path,
                "capabilities": sorted(str(item) for item in capabilities),
                "supported_protocols": supported_protocols,
            },
            ensure_ascii=True,
            sort_keys=True,
            default=str,
        )
        registry = self._scoped_mcp_registries.get(cache_key)
        if registry is None:
            manifest = {
                "id": run.get("cartridge_id"),
                "version": run.get("cartridge_version"),
                "mcp_tools": run.get("mcp_tools") or [],
                "protocol_extensions": extensions or [],
                "portable_dlc": portable_dlc,
            }
            registry = BuiltinMcpRegistry.for_manifest(
                self.workspace_root,
                manifest,
                capabilities=capabilities,
                supported_protocols=supported_protocols,
                package_path=package_path,
            )
            self._scoped_mcp_registries[cache_key] = registry
        return registry

    def execute(self, state_name: str, state: dict, state_doc: dict, run: dict, run_dir) -> dict:
        state = normalize_runtime_node(state)
        store = state_doc["context"].setdefault("store", {})
        params = dict(state.get("params") or {})
        if state.get("tools") and not params.get("tools"):
            params["tools"] = state.get("tools")
        params = self._prepare_protocol_runtime(state, params, store, run)
        action = state.get("action") or ""
        preset_config = params.get("preset_config") or {}

        dispatch = {
            "collect_inputs": self._collect_inputs,
            "show_welcome": self._show_ui,
            "show_ui": self._show_ui,
            "render_ui": self._show_ui,
            "show_result": self._show_ui,
            "render_interaction": self._render_interaction,
            "llm_prompt": self._llm_prompt,
            "tool_call": self._tool_call,
            "remote_call": self._remote_call,
            "pass_result": self._pass_result,
            "save_context": self._save_context,
            "confirm_checkpoint": self._confirm_checkpoint,
            "custom_action": self._custom_action,
        }

        # per-node 缺失键收集：在执行器自己解析键的那一刻记录"要读但 store 里没有"的键。
        # 这样数据链断裂的判定唯一依据执行器的真实解析行为，不再另写一份静态解析（避免与引擎漂移）。
        self._pending_missing = []
        self._optional_input_keys = set(self._split_keys(params.get("optional_input") or preset_config.get("optional_input")))

        try:
            handler = dispatch.get(action)
            if handler:
                result = handler(params, store, run, run_dir)
            else:
                result = {"action": action, "skipped": True, "reason": f"action '{action}' 暂无执行器，节点已进入/完成但未实际执行"}

            if isinstance(result, dict) and self._pending_missing:
                # 去重保序
                seen = set()
                missing = []
                for item in self._pending_missing:
                    if not item:
                        continue
                    key = (item.get("key"), item.get("required"), item.get("source")) if isinstance(item, dict) else item
                    if key not in seen:
                        seen.add(key)
                        missing.append(item)
                result["missing_inputs"] = missing
                required_missing = [item for item in missing if isinstance(item, dict) and item.get("required")]
                if required_missing:
                    result["failed"] = True
                    result["error_code"] = "INPUT_REQUIRED"
                    result["error"] = "Required inputs are missing: " + ", ".join(str(item.get("key")) for item in required_missing)
            return result
        finally:
            self._pending_missing = []
            self._optional_input_keys = set()

    def _split_keys(self, raw_value) -> list[str]:
        if not raw_value:
            return []
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        return [
            item.strip()
            for item in str(raw_value).replace("\r", "\n").replace(",", "\n").split("\n")
            if item.strip()
        ]

    def _prepare_protocol_runtime(self, state: dict, params: dict, store: dict, run: dict) -> dict:
        runtime = state.get("_protocol_runtime") if isinstance(state.get("_protocol_runtime"), dict) else {}
        kind = runtime.get("kind")
        if kind in {"mcp_read", "mcp_execute"}:
            return self._prepare_v02_mcp_node(kind, runtime, params, store, run)
        return params

    def _prepare_v02_mcp_node(self, kind: str, runtime: dict, params: dict, store: dict, run: dict) -> dict:
        params = dict(params)
        preset_config = dict(params.get("preset_config") or {})
        mcp_binding = params.get("mcp_binding") if isinstance(params.get("mcp_binding"), dict) else {}
        allowed_tools = self._split_keys(params.get("allowed_tools")) or self._split_keys(mcp_binding.get("allowed_tools"))
        if not allowed_tools:
            raise RuntimeError(f"{kind} requires allowed_tools before execution")

        manifest_tools = {
            str(tool.get("id")): tool
            for tool in run.get("mcp_tools") or []
            if isinstance(tool, dict) and tool.get("id")
        }
        missing = [tool_id for tool_id in allowed_tools if tool_id not in manifest_tools]
        if missing:
            raise RuntimeError(f"{kind} references undeclared manifest tools: {', '.join(missing)}")

        if kind == "mcp_read":
            for tool_id in allowed_tools:
                side_effect = self._tool_side_effect(manifest_tools.get(tool_id) or {})
                if side_effect not in {"", "none", "read_only", "environment_probe"}:
                    raise RuntimeError(f"mcp_read cannot execute side-effecting tool: {tool_id}")

        effect = str(runtime.get("effect") or params.get("effect") or "").strip()
        tool_binding = str(params.get("tool_binding") or "").strip()
        if tool_binding in {"from_tool_plan", "hybrid_params"}:
            plan = self._read_tool_plan_from_store(params, store)
            findings = validate_tool_plan(
                plan,
                {"mcp_tools": run.get("mcp_tools") or []},
                {"effect": effect, "allowed_tools": allowed_tools},
            )
            blockers = [item for item in findings if item.get("severity") == "blocker"]
            if blockers:
                codes = ", ".join(item.get("code", "tool_plan_invalid") for item in blockers)
                raise RuntimeError(f"tool_plan.v1 validation failed: {codes}")
            preset_config["mcp_tool_id"] = plan.get("tool_id")
            params["tool_params"] = dict(plan.get("params") or {})
            if plan.get("expected_output") and not params.get("output"):
                params["output"] = plan.get("expected_output")
                preset_config["output_name"] = plan.get("expected_output")

        selected_tool_id = preset_config.get("mcp_tool_id") or params.get("mcp_tool_id")
        if selected_tool_id:
            selected_tool_id = str(selected_tool_id).strip()
            if selected_tool_id not in allowed_tools:
                raise RuntimeError(f"{kind} selected tool is not allowed: {selected_tool_id}")
        elif not params.get("tools") and allowed_tools:
            preset_config["mcp_tool_id"] = allowed_tools[0]

        tools = params.get("tools")
        if isinstance(tools, list):
            for tool in tools:
                if not isinstance(tool, dict) or tool.get("enabled", True) is False:
                    continue
                tool_id = self._tool_id_for_call(tool, manifest_tools)
                if not tool_id:
                    raise RuntimeError(f"{kind} tool calls must reference manifest tools by mcp_tool_id or matching server/tool")
                if tool_id not in allowed_tools:
                    raise RuntimeError(f"{kind} tool is not allowed: {tool_id}")

        params["preset_config"] = preset_config
        return params

    def _read_tool_plan_from_store(self, params: dict, store: dict) -> dict:
        preset_config = params.get("preset_config") or {}
        input_key = params.get("input") or preset_config.get("source") or preset_config.get("from")
        if not input_key:
            raise RuntimeError("from_tool_plan requires input key")
        value = store.get(input_key)
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"tool_plan input is not valid JSON: {input_key}") from exc
            if isinstance(parsed, dict):
                return parsed
        raise RuntimeError(f"tool_plan input is missing or not an object: {input_key}")

    def _tool_id_for_call(self, tool: dict, manifest_tools: dict[str, dict]) -> str:
        explicit = str(tool.get("mcp_tool_id") or tool.get("tool_id") or "").strip()
        if explicit:
            return explicit
        server = str(tool.get("server") or "").strip()
        tool_name = str(tool.get("tool") or "").strip()
        for tool_id, manifest_tool in manifest_tools.items():
            if str(manifest_tool.get("server") or "").strip() == server and str(manifest_tool.get("tool") or "").strip() == tool_name:
                return tool_id
        return ""

    def _tool_side_effect(self, tool: dict) -> str:
        contract = tool.get("contract") if isinstance(tool.get("contract"), dict) else {}
        return str(contract.get("side_effect") or "").strip().lower()

    def _record_missing(self, base_key: str, ref: str = "", required: bool | None = None, source: str = "input") -> None:
        tracker = getattr(self, "_pending_missing", None)
        if tracker is not None and base_key:
            optional_keys = getattr(self, "_optional_input_keys", set())
            is_required = (base_key not in optional_keys) if required is None else bool(required)
            tracker.append({
                "key": base_key,
                "required": is_required,
                "source": "optional_input" if not is_required else source,
                "severity": "error" if is_required else "info",
                **({"ref": ref} if ref else {}),
            })

    def _resolve_tool_params(self, raw_params: dict, store: dict) -> dict:
        resolved = {}
        for key, value in (raw_params or {}).items():
            if isinstance(value, str) and value.startswith("store:"):
                resolved[key] = self._resolve_store_ref(store, value)
            else:
                resolved[key] = value
        return resolved

    def _resolve_package_relative_path(self, path_str: str, run: dict) -> str:
        if not path_str or Path(path_str).is_absolute():
            return path_str
        path_items = [
            item.strip()
            for item in str(path_str).replace("\r", "\n").replace(",", "\n").split("\n")
            if item.strip()
        ]
        if len(path_items) > 1:
            return "\n".join(self._resolve_package_relative_path(item, run) for item in path_items)
        workspace_target = (self.workspace_root / path_str).resolve()
        if workspace_target.exists():
            return path_str
        package_path = run.get("package_path")
        if not package_path:
            return path_str
        try:
            package_root = Path(package_path).resolve()
            candidate = (package_root / path_str).resolve()
            workspace_root = self.workspace_root.resolve()
            if package_root in candidate.parents and workspace_root in candidate.parents and candidate.exists():
                return str(candidate)
        except OSError:
            return path_str
        return path_str

    def _resolve_store_ref(self, store: dict, ref: str):
        key = (ref or "").removeprefix("store:").strip()
        if not key:
            return ""
        segments = [piece for piece in re.split(r"[.\[\]]+", key) if piece]
        base_key = segments[0] if segments else ""
        if base_key and base_key not in store:
            # 运行时如实记录：这个 store 引用要读的键在 store 里根本不存在。
            # 由执行器自己在解析处记录，避免另写一份解析逻辑与本文件漂移。
            self._record_missing(base_key, ref)
        current = store
        for part in segments:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                if 0 <= index < len(current):
                    current = current[index]
                else:
                    return ""
            else:
                return ""
        if isinstance(current, (dict, list)):
            return json.dumps(current, ensure_ascii=False)
        return current

    def _tool_call(self, params: dict, store: dict, _run: dict, _run_dir) -> dict:
        preset_config = params.get("preset_config") or {}
        input_key = params.get("input") or preset_config.get("source") or preset_config.get("from")
        default_output = params.get("output") or preset_config.get("output_name") or "tool_result"
        tools = params.get("tools") or []
        if isinstance(tools, list):
            tools = [
                tool for tool in tools
                if isinstance(tool, dict) and (tool.get("server") or tool.get("tool") or tool.get("mcp_tool_id"))
            ]
        library_tool_id = preset_config.get("mcp_tool_id") or preset_config.get("tool_id") or params.get("mcp_tool_id")
        if library_tool_id and (not isinstance(tools, list) or not tools):
            library_tool = self._resolve_library_tool(_run, library_tool_id)
            if library_tool:
                tool_params = dict(library_tool.get("default_params") or {})
                explicit_params = params.get("tool_params") or preset_config.get("params") or {}
                if isinstance(explicit_params, dict):
                    tool_params.update(explicit_params)
                tools = [{
                    "type": library_tool.get("type") or "builtin",
                    "server": library_tool.get("server"),
                    "tool": library_tool.get("tool"),
                    "params": tool_params,
                    "enabled": library_tool.get("enabled", True),
                    "output": default_output,
                    "mcp_tool_id": library_tool_id,
                }]
        if not isinstance(tools, list) or not tools:
            tools = self._build_preset_tools(params, preset_config, store, input_key, default_output)

        tool_results: list[dict] = []
        strict_failed = False
        manifest_tools = {
            str(item.get("id")): item
            for item in _run.get("mcp_tools") or []
            if isinstance(item, dict) and item.get("id")
        }
        for tool in tools if isinstance(tools, list) else []:
            if not isinstance(tool, dict) or tool.get("enabled", True) is False:
                continue
            tool_type = str(tool.get("type") or "builtin").strip()
            if tool_type not in {"builtin", "mcp", "remote", "plugin"}:
                tool_results.append({"type": tool_type, "ok": False, "code": "dependency_unavailable", "error": "Unsupported tool adapter type"})
                continue
            server = tool.get("server") or ""
            tool_name = tool.get("tool") or ""
            tool_params = self._resolve_tool_params(tool.get("params") or {}, store)
            tool_params.setdefault("_runtime_run_id", str(_run.get("run_id") or ""))
            tool_id = self._tool_id_for_call(tool, manifest_tools)
            local_binding = None
            if tool_id:
                try:
                    from core.studio.resource_resolver import resolve_runtime_tool_binding
                    local_binding = resolve_runtime_tool_binding(_run, tool_id)
                except ConnectionError as exc:
                    tool_results.append({
                        "server": server,
                        "tool": tool_name,
                        "resource_role": str((manifest_tools.get(tool_id) or {}).get("resource_role") or ""),
                        "result": {"ok": False, "code": "dependency_unavailable", "error": str(exc)},
                        "attempts": [],
                        "retry_blocked": None,
                        "idempotent": False,
                        "contract": self._contract_metadata({}),
                    })
                    continue
            if params.get("include_runtime_test_mode"):
                tool_params["_runtime_test_mode"] = dict(_run.get("test_mode") or {})
            if server == "filesystem" and isinstance(tool_params.get("path"), str):
                tool_params["path"] = self._resolve_package_relative_path(tool_params["path"], _run)
            if server and tool_name:
                contract = self._tool_contract_for_call(_run, tool)
                result, attempts, retry_blocked = self._call_tool_with_retry(
                    self._registry_for_run(_run),
                    server,
                    tool_name,
                    tool_params,
                    contract,
                    external_binding=local_binding,
                )
                tool_results.append({
                    "server": server,
                    "tool": tool_name,
                    "resource_role": local_binding.get("role") if local_binding else "",
                    "resource_id": local_binding.get("resource_id") if local_binding else "",
                    "result": result,
                    "attempts": attempts,
                    "retry_blocked": retry_blocked,
                    "idempotent": contract.get("idempotent") is True,
                    "contract": self._contract_metadata(contract),
                })
                if tool.get("strict") and result.get("ok"):
                    if result.get("validation_ok") is False or result.get("asset_ok") is False:
                        strict_failed = True
                output_key = tool.get("output") or default_output or f"{server}_{tool_name}_result"
                if result.get("ok") and "content" in result:
                    store[output_key] = result["content"]
                else:
                    store[output_key] = result

        failed = any((item.get("result") or item).get("ok") is False for item in tool_results if isinstance(item, dict))
        failed = failed or strict_failed
        retry_blocked = [item.get("retry_blocked") for item in tool_results if isinstance(item, dict) and item.get("retry_blocked")]
        return {
            "action": "tool_call",
            "input": input_key,
            "output": default_output,
            "tool_results": tool_results,
            "failed": failed,
            **({"retry_blocked": retry_blocked} if retry_blocked else {}),
        }

    def _tool_contract_for_call(self, run: dict, tool: dict) -> dict:
        tool_id = str(tool.get("mcp_tool_id") or tool.get("id") or "").strip()
        for item in run.get("mcp_tools") or []:
            if not isinstance(item, dict):
                continue
            same_id = tool_id and str(item.get("id") or "") == tool_id
            same_call = str(item.get("server") or "") == str(tool.get("server") or "") and str(item.get("tool") or "") == str(tool.get("tool") or "")
            if same_id or same_call:
                return item.get("contract") if isinstance(item.get("contract"), dict) else {}
        return tool.get("contract") if isinstance(tool.get("contract"), dict) else {}

    def _contract_metadata(self, contract: dict) -> dict:
        contract = contract if isinstance(contract, dict) else {}
        deduplication_key = contract.get("deduplication_key") or contract.get("dedup_key")
        compensation = contract.get("compensation")
        return {
            "idempotent": contract.get("idempotent") is True,
            "idempotency_declared": "idempotent" in contract,
            "deduplication_key": str(deduplication_key or ""),
            "compensation": compensation if isinstance(compensation, (dict, str)) else None,
            "unreplayable_reason": str(contract.get("unreplayable_reason") or ""),
        }

    def _call_tool_with_retry(
        self,
        registry,
        server: str,
        tool_name: str,
        params: dict,
        contract: dict,
        *,
        external_binding: dict | None = None,
    ) -> tuple[dict, list[dict], dict | None]:
        retry_policy = contract.get("retry_policy") if isinstance(contract.get("retry_policy"), dict) else {}
        try:
            max_attempts = max(1, min(5, int(retry_policy.get("max_attempts") or 1)))
        except (TypeError, ValueError):
            max_attempts = 1
        try:
            initial_delay = max(0.0, min(30.0, float(retry_policy.get("initial_delay_seconds") or 0.25)))
            max_delay = max(initial_delay, min(60.0, float(retry_policy.get("max_delay_seconds") or 5.0)))
            total_timeout = max(0.1, min(600.0, float(retry_policy.get("total_timeout_seconds") or 120.0)))
        except (TypeError, ValueError):
            initial_delay, max_delay, total_timeout = 0.25, 5.0, 120.0
        idempotent = contract.get("idempotent") is True
        attempts = []
        started = time.monotonic()
        state = "queued"
        result: dict = {"ok": False, "code": "tool_not_called", "error": "Tool was not called"}
        retry_blocked = None
        for attempt in range(1, max_attempts + 1):
            assert_transition("tool", state, "running")
            state = "running"
            attempt_started = time.monotonic()
            if external_binding:
                from core.studio.external_adapters import execute_external_tool

                result = execute_external_tool(external_binding, server, tool_name, params, contract)
            else:
                result = registry.call(server, tool_name, params)
            result = result if isinstance(result, dict) else {"ok": False, "code": "tool_invalid_response", "error": "Tool response must be an object"}
            duration_ms = round((time.monotonic() - attempt_started) * 1000, 3)
            code = str(result.get("code") or "")
            target = (
                "succeeded"
                if result.get("ok") is not False
                else "timed_out"
                if code in {"dlc_worker_timeout", "tool_timeout"}
                else "cancelled"
                if code in {"dlc_worker_cancelled", "tool_cancelled"}
                else "failed"
            )
            assert_transition("tool", state, target)
            state = target
            attempts.append({
                "attempt": attempt,
                "status": target,
                "code": code,
                "duration_ms": duration_ms,
            })
            if target == "succeeded":
                break
            retryable = self._tool_result_retryable(result)
            has_attempt = attempt < max_attempts
            within_total = (time.monotonic() - started) < total_timeout
            if not retryable or not has_attempt or not within_total:
                break
            if not idempotent:
                retry_blocked = {
                    "reason": "tool_is_not_idempotent",
                    "requires_confirmation": True,
                    "attempts_allowed": max_attempts,
                }
                break
            assert_transition("tool", state, "retrying")
            state = "retrying"
            delay = min(initial_delay * (2 ** (attempt - 1)), max_delay)
            if time.monotonic() - started + delay > total_timeout:
                break
            if delay:
                time.sleep(delay)
        return result, attempts, retry_blocked

    def _tool_result_retryable(self, result: dict) -> bool:
        if isinstance(result.get("retryable"), bool):
            return result["retryable"]
        code = str(result.get("code") or "").lower()
        if code in {"dlc_worker_timeout", "dlc_worker_failed", "tool_timeout", "dependency_unavailable"}:
            return True
        message = str(result.get("error") or "").lower()
        return any(marker in message for marker in ("timeout", "timed out", "connection", "temporarily unavailable", "429", "502", "503", "504"))

    def _remote_call(self, params: dict, store: dict, run: dict, run_dir) -> dict:
        result = self._tool_call(params, store, run, run_dir)
        result["action"] = "remote_call"
        result["remote_service"] = (
            params.get("remote_service")
            or (params.get("preset_config") or {}).get("remote_service")
            or (params.get("preset_config") or {}).get("service")
            or "remote"
        )
        return result

    def _build_preset_tools(self, params: dict, preset_config: dict, store: dict, input_key: str | None, default_output: str) -> list[dict]:
        preset = params.get("preset") or preset_config.get("preset")
        path = preset_config.get("path") or params.get("path")
        source = preset_config.get("source") or params.get("source") or input_key
        if preset == "filesystem_read" and path:
            resolved_path = self._resolve_store_ref(store, path) if isinstance(path, str) and path.startswith("store:") else path
            return [{"type": "builtin", "server": "filesystem", "tool": "read_file", "params": {"path": resolved_path}, "enabled": True, "output": default_output}]
        if preset == "filesystem_write" and path:
            resolved_path = self._resolve_store_ref(store, path) if isinstance(path, str) and path.startswith("store:") else path
            content = self._resolve_store_ref(store, source) if isinstance(source, str) and source.startswith("store:") else store.get(source, source or "")
            return [{"type": "builtin", "server": "filesystem", "tool": "write_file", "params": {"path": resolved_path, "content": content}, "enabled": True, "output": default_output}]
        if preset == "filesystem_list" and path:
            resolved_path = self._resolve_store_ref(store, path) if isinstance(path, str) and path.startswith("store:") else path
            return [{"type": "builtin", "server": "filesystem", "tool": "list_dir", "params": {"path": resolved_path}, "enabled": True, "output": default_output}]
        if preset in {"mcp_call", "remote_call", "remote_mcp_call"}:
            server = preset_config.get("server") or params.get("server")
            tool_name = preset_config.get("tool") or params.get("tool")
            if server and tool_name:
                return [{"type": "builtin", "server": server, "tool": tool_name, "params": self._resolve_tool_params(params.get("tool_params") or {}, store), "enabled": True, "output": default_output}]
        return []

    def _resolve_library_tool(self, run: dict, tool_id: str) -> dict | None:
        for item in run.get("mcp_tools") or []:
            if isinstance(item, dict) and item.get("id") == tool_id:
                return item
        return None

    def _read_input(self, input_key: str, store: dict, required: bool = True) -> str:
        parts = [k.strip() for k in input_key.split(",") if k.strip()]
        chunks = []
        for key in parts:
            found = False
            val = None
            if key in store:
                found = True
                val = store[key]
            elif any(marker in key for marker in (".", "[")):
                base_key = key.split(".", 1)[0].split("[", 1)[0]
                if base_key in store:
                    resolved = self._resolve_store_ref(store, f"store:{key}")
                    if resolved != "":
                        found = True
                        val = resolved
            if found:
                if isinstance(val, dict):
                    import json
                    chunks.append(f"[{key}]\n{json.dumps(val, ensure_ascii=False, indent=2)}")
                else:
                    chunks.append(f"[{key}]\n{val}")
            else:
                # 声明要读、但 store 里根本没有 —— 数据链断裂的真实现场
                self._record_missing(key, required=required, source="input")
        return "\n\n".join(chunks)

    def _collect_inputs(self, params: dict, store: dict, run: dict, _run_dir) -> dict:
        fields = params.get("fields") or params.get("preset_config", {}).get("fields") or []
        output_key = (
            params.get("output") or
            params.get("output_name") or
            params.get("preset_config", {}).get("output_name") or
            "user_input"
        )
        inputs = run.get("inputs") or {}
        if isinstance(fields, str):
            fields = [f.strip() for f in fields.split(",") if f.strip()]
        if isinstance(fields, list) and fields:
            collected = {field: inputs.get(field, "") for field in fields if isinstance(field, str)}
        else:
            collected = dict(inputs)
        store[output_key] = collected
        return {"action": "collect_inputs", "output": output_key, "keys": list(collected.keys())}

    def _show_ui(self, params: dict, store: dict, run: dict, _run_dir) -> dict:
        preset_config = params.get("preset_config") or {}
        input_key = params.get("input") or preset_config.get("source") or preset_config.get("data_key")
        output_key = params.get("output") or preset_config.get("output_name") or "ui_view"
        ui_type = (params.get("ui_type") or preset_config.get("ui_type") or preset_config.get("format") or "html").lower()
        html = params.get("html") or preset_config.get("html") or ""
        markdown = params.get("markdown") or preset_config.get("markdown") or ""
        path = (
            params.get("path") or
            preset_config.get("path") or
            preset_config.get("html_path") or
            preset_config.get("markdown_path")
        )
        package_path = Path(run.get("package_path") or ".")

        if path and not html and not markdown:
            try:
                target = (package_path / str(path)).resolve()
                package_root = package_path.resolve()
                if (target == package_root or package_root in target.parents) and target.is_file():
                    content = target.read_text(encoding="utf-8", errors="replace")
                    if str(path).lower().endswith((".md", ".markdown")):
                        markdown = content
                        ui_type = "markdown"
                    else:
                        html = content
                        ui_type = "html"
            except OSError:
                pass

        data_value = store.get(input_key) if input_key else None
        if not html and not markdown and data_value is not None:
            if isinstance(data_value, str):
                markdown = data_value
            else:
                import json
                markdown = "```json\n" + json.dumps(data_value, ensure_ascii=False, indent=2) + "\n```"
            ui_type = "markdown"

        payload = {
            "type": ui_type,
            "html": html,
            "markdown": markdown,
            "path": path,
            "input": input_key,
        }
        store[output_key] = payload
        return {
            "action": "show_ui",
            "output": output_key,
            "ui_type": ui_type,
            "ui_html": html,
            "ui_markdown": markdown,
            "path": path,
        }

    def _render_interaction(self, params: dict, store: dict, run: dict, _run_dir) -> dict:
        package_path = run.get("package_path")
        if not package_path:
            raise RuntimeError("interaction node requires a cartridge package path")
        manifest = {
            "id": run.get("cartridge_id"),
            "version": run.get("cartridge_version"),
            "runtime_contract": run.get("runtime_contract") or {},
            "mcp_tools": run.get("mcp_tools") or [],
            "portable_dlc": run.get("portable_dlc"),
            "asset_registry": run.get("asset_registry"),
            "interaction_components": run.get("interaction_components"),
        }
        bundle = load_asset_bundle(package_path, manifest, include_content=True)
        component_id = str(params.get("component_ref") or "").strip()
        component = (bundle.get("component_by_id") or {}).get(component_id)
        if not component:
            raise RuntimeError(f"interaction component not found: {component_id}")
        mode = str(params.get("interaction_mode") or "display").strip()
        if mode not in component.get("supported_modes", []):
            raise RuntimeError(f"interaction mode is not supported by {component_id}: {mode}")
        asset = (bundle.get("asset_by_id") or {}).get(component.get("entry_asset_id")) or {}
        html = materialize_passive_html(str(asset.get("content") or ""), bundle) if component.get("runtime") == "passive" else ""
        bindings = self._resolve_interaction_bindings(params.get("input_binding"), store, run)
        presentation = {
            "component_id": component_id,
            "component_version": component.get("version"),
            "component_runtime": component.get("runtime"),
            "asset_id": asset.get("id"),
            "entry_sha256": component.get("entry_sha256") or asset.get("sha256"),
            "html": html,
            "bindings": bindings,
        }
        if component.get("runtime") == "sandboxed":
            presentation.update({
                "frontend_ref": component.get("dlc_frontend_ref"),
                "descriptor_sha256": component.get("descriptor_sha256"),
                "host_capabilities": component.get("host_capabilities") or [],
            })
        if mode == "display":
            return {
                "action": "render_interaction",
                "interaction_mode": mode,
                "presentation": presentation,
                "ui_type": "html",
                "ui_html": html,
            }

        action_routes = params.get("action_routes") if isinstance(params.get("action_routes"), dict) else {}
        declared_actions = {
            str(item.get("id")): item
            for item in component.get("actions") or []
            if isinstance(item, dict) and item.get("id") in action_routes
        }
        if not declared_actions:
            raise RuntimeError("collect/review interaction requires at least one routed component action")
        input_schema = self._interaction_schema(bundle, component.get("input_schema"))
        action_schemas = {
            action_id: self._interaction_schema(bundle, action.get("payload_schema"))
            for action_id, action in declared_actions.items()
        }
        revision_source = json.dumps(bindings, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        input_hash = hashlib.sha256(revision_source).hexdigest()
        input_revision = 1
        presentation["input_revision"] = input_revision
        import uuid
        pending = {
            "schema": "cartridgeflow.pending_interaction.v2",
            "interaction_id": f"pi_{uuid.uuid4().hex[:12]}",
            "run_id": run.get("run_id"),
            "status": "waiting_user",
            "mode": mode,
            "presentation": presentation,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "answered_at": None,
            "answer_revision": 0,
            "input_snapshot": {
                "bindings": bindings,
                "input_revision": input_revision,
                "input_hash": input_hash,
            },
            "question": {
                "id": f"{component_id}.{mode}",
                "prompt": str(params.get("prompt") or component.get("label") or params.get("display_name") or "Please review and continue."),
                "input_schema": input_schema,
                "store_key": str(params.get("output") or "interaction_result"),
            },
            "allowed_actions": list(declared_actions.keys()),
            "action_labels": {
                action_id: str(action.get("label") or action_id)
                for action_id, action in declared_actions.items()
            },
            "action_schemas": action_schemas,
            "resume": {
                "policy": "resume_by_action_route",
                "action_routes": dict(action_routes),
            },
        }
        store["_pending_interaction"] = pending
        return {
            "action": "render_interaction",
            "interaction_mode": mode,
            "paused": True,
            "pause_status": "paused_waiting_user",
            "pending_interaction": pending,
        }

    def _interaction_schema(self, bundle: dict, value) -> dict:
        if isinstance(value, dict):
            return value
        reference = str(value or "").strip()
        if not reference.startswith("asset:"):
            return {"type": "object"}
        asset = (bundle.get("asset_by_id") or {}).get(reference.removeprefix("asset:")) or {}
        try:
            parsed = json.loads(str(asset.get("content") or "{}"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"interaction schema asset is invalid JSON: {reference}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"interaction schema asset must contain an object: {reference}")
        return parsed

    def _resolve_interaction_bindings(self, raw, store: dict, run: dict) -> dict:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise RuntimeError("interaction input_binding must be an object")
        resolved = {}
        for name, reference in raw.items():
            reference = str(reference or "")
            if reference.startswith("store:"):
                path = reference.removeprefix("store:")
                found, value = self._resolve_mapping_path(store, path)
                resolved[str(name)] = value if found else None
            elif reference.startswith("artifact:"):
                artifact_id = reference.removeprefix("artifact:")
                resolved[str(name)] = next(
                    (item for item in run.get("artifacts") or [] if str(item.get("id") or item.get("artifact_id")) == artifact_id),
                    None,
                )
            else:
                raise RuntimeError(f"unsupported interaction binding: {reference}")
        return resolved

    def _llm_prompt(self, params: dict, store: dict, run: dict, _run_dir) -> dict:
        preset_config = params.get("preset_config") or {}
        input_key = (
            params.get("input") or
            params.get("from") or
            preset_config.get("from") or
            preset_config.get("source") or
            preset_config.get("items")
        )
        output_key = (
            params.get("output") or
            params.get("output_name") or
            preset_config.get("output_name") or
            preset_config.get("to") or
            "llm_result"
        )
        system_prompt = (
            params.get("system_prompt") or
            preset_config.get("goal") or
            preset_config.get("change_goal") or
            preset_config.get("focus") or
            "你是一个可靠的助手，请根据上下文完成任务。"
        )
        prompt_template = (
            params.get("prompt") or
            preset_config.get("target") or
            preset_config.get("format") or
            preset_config.get("from_to") or
            params.get("description") or
            ""
        )
        model_role = params.get("model_role") or run.get("inputs", {}).get("model_role") or "runtime"

        optional_input_key = params.get("optional_input") or preset_config.get("optional_input")
        context_parts = []
        if input_key:
            context_parts.append(self._read_input(input_key, store, required=True))
        if optional_input_key:
            optional_context = self._read_input(optional_input_key, store, required=False)
            if optional_context:
                context_parts.append(optional_context)
        context_text = "\n\n".join(item for item in context_parts if item)
        if not prompt_template:
            prompt_template = (
                run.get("inputs", {}).get("prompt") or
                run.get("inputs", {}).get("task_description") or
                "请根据上下文完成任务。"
            )
        final_prompt = f"{context_text}\n\n{prompt_template}".strip() if context_text else prompt_template

        used_llm = False
        fallback = ""
        provider_id = ""
        model = ""
        llm_response_meta = {}
        provider_error = {}
        raw_decision_contract = params.get("decision_contract")
        decision_contract = raw_decision_contract if isinstance(raw_decision_contract, dict) else {}
        output_contract = params.get("output_contract") or decision_contract.get("schema")
        if output_contract == "decision_envelope.v1":
            allowed_statuses = decision_contract.get("allowed_statuses") or ["resolved", "needs_user_input", "blocked"]
            consume = decision_contract.get("consume") if isinstance(decision_contract.get("consume"), dict) else {}
            force_live_confirmation = self._should_force_live_collaboration(
                decision_contract,
                params,
                optional_input_key,
                store,
                run,
            )
            final_prompt = (
                f"{final_prompt}\n\n"
                "你必须只返回一个 JSON 对象，不要使用 Markdown，不要添加解释文本，不要包在 decision_envelope 字段里。\n"
                "JSON 里的键和值必须只使用 ASCII 双引号，禁止使用中文引号、弯引号或单引号。\n"
                "JSON 根对象必须符合 decision_envelope.v1：\n"
                "{\n"
                '  "schema": "decision_envelope.v1",\n'
                '  "status": "resolved | needs_user_input | blocked",\n'
                '  "summary": "用一句话说明本次决策",\n'
                '  "payload": {"decision": "当 status=resolved 时写清楚具体决策、理由和下一步"}\n'
                "}\n"
                f"本节点允许的 status: {', '.join(map(str, allowed_statuses))}。\n"
                "当 status=needs_user_input 时必须提供 question.prompt、question.input_schema、question.store_key 和 resume.policy。\n"
                "当 status=blocked 时必须提供 issues 数组。"
            )
            if consume.get("path"):
                final_prompt = (
                    f"{final_prompt}\n"
                    f"当 status=resolved 时，必须提供可供后续节点消费的字段：{consume.get('path')}。"
                )
            if force_live_confirmation:
                final_prompt = (
                    f"{final_prompt}\n"
                    "当前测试台处于真实协作模式。本节点首次运行必须先提出方案并请求用户确认，"
                    "不要直接 resolved。请输出 status=needs_user_input，并把方案摘要写入 question.prompt；"
                    "question.input_schema、question.store_key 和 resume.policy 必须沿用节点交互契约。"
                )
        decision_test_mode = (
            self._run_decision_test_mode(run)
            or params.get("decision_test_mode")
            or preset_config.get("decision_test_mode")
            or (run.get("inputs") or {}).get("decision_test_mode")
            or ""
        )

        try:
            from core.llm import chat
            from core.llm.config_manager import resolve_model
            cfg = resolve_model(role=model_role, cartridge_id=run.get("cartridge_id"))
            provider_id = cfg.provider_id
            model = cfg.model
            if output_contract == "decision_envelope.v1" and str(decision_test_mode).strip() in {"mock", "mock_resolved", "mock_interaction", "mock_blocked"}:
                fallback = f"mock_decision:{decision_test_mode}"
                mock = params.get("mock_decision_envelope") or preset_config.get("mock_decision_envelope")
                envelope = self._mock_decision_envelope_for_mode(str(decision_test_mode).strip(), mock, decision_contract, params, output_key)
                result_text = json.dumps(envelope, ensure_ascii=False)
            elif not cfg.api_key:
                fallback = "missing_api_key"
                provider_error = {"type": "ProviderConfiguration", "message": "API key is not configured", "retryable": False}
                result_text = self._offline_llm_response(system_prompt, prompt_template, final_prompt)
            else:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": final_prompt},
                ]
                try:
                    response = asyncio.run(chat(cfg, messages, agent_name="lab_node", phase="flow_node"))
                except RuntimeError:
                    loop = asyncio.get_event_loop()
                    response = loop.run_until_complete(chat(cfg, messages, agent_name="lab_node", phase="flow_node"))
                result_text = response.get("content", "")
                llm_response_meta = response.get("meta") if isinstance(response.get("meta"), dict) else {}
                used_llm = True
        except Exception as exc:
            from core.llm.errors import classify_llm_error

            classified = classify_llm_error(exc)
            fallback = f"llm_error:{exc.__class__.__name__}"
            provider_error = {
                "type": exc.__class__.__name__,
                "message": str(classified),
                "status_code": classified.status_code,
                "retryable": classified.retryable,
            }
            result_text = self._offline_llm_response(system_prompt, prompt_template, final_prompt)

        if output_contract == "decision_envelope.v1":
            if used_llm and not str(result_text or "").strip():
                finish_reason = str(llm_response_meta.get("finish_reason") or "unknown")
                envelope = make_blocked_decision_envelope(
                    "llm_empty_response",
                    f"LLM returned empty assistant content (finish_reason={finish_reason}).",
                )
            else:
                envelope = self._decision_envelope_from_result(result_text, decision_contract, fallback)
            if force_live_confirmation and envelope.get("status") == "resolved":
                envelope = self._collaboration_confirmation_envelope(envelope, decision_contract, params, output_key)
            if envelope.get("status") == "needs_user_input":
                if str(fallback or "").startswith("mock"):
                    envelope = self._normalize_needs_user_input_shape(envelope)
                else:
                    envelope = self._apply_contract_interaction(envelope, decision_contract, params, output_key)
            validation_findings = validate_decision_envelope(envelope, decision_contract)
            blockers = [item for item in validation_findings if item.get("severity") == "blocker"]
            if blockers:
                envelope = self._blocked_envelope_from_validation(blockers, result_text)
                findings = validate_decision_envelope(envelope, decision_contract)
            else:
                findings = validation_findings
            store[output_key] = envelope
            consume_result = self._apply_decision_consume(decision_contract, envelope, store)
            result = {
                "action": "llm_prompt",
                "output": output_key,
                "length": len(json.dumps(envelope, ensure_ascii=False)),
                "used_llm": used_llm,
                "fallback": fallback,
                "provider_id": provider_id,
                "model": model,
                "provider_error": provider_error,
                "llm_response_meta": llm_response_meta,
                "test_mode": run.get("test_mode") or {},
                "decision_test_mode": decision_test_mode,
                "output_contract": "decision_envelope.v1",
                "decision_status": envelope.get("status"),
                "decision_envelope": envelope,
                "decision_findings": findings,
            }
            if validation_findings:
                result["decision_validation_errors"] = validation_findings
            if consume_result:
                result["decision_consume"] = consume_result
                if consume_result.get("output"):
                    result["decision_consume_output"] = consume_result.get("output")
                if consume_result.get("failed"):
                    result["failed"] = True
                    result["error_code"] = "DECISION_CONSUME_FAILED"
            if envelope.get("status") == "needs_user_input":
                pending = self._pending_interaction_from_decision(run, output_key, envelope)
                store["_pending_interaction"] = pending
                result["paused"] = True
                result["pause_status"] = "paused_waiting_user"
                result["pending_interaction"] = pending
            if envelope.get("status") == "blocked":
                result["failed"] = True
                if blockers:
                    result["error"] = self._format_decision_validation_error(blockers)
                else:
                    issues = envelope.get("issues") if isinstance(envelope.get("issues"), list) else []
                    result["error"] = "; ".join(
                        str(item.get("message") or item.get("code") or "Decision blocked")
                        for item in issues[:5]
                        if isinstance(item, dict)
                    ) or str(envelope.get("summary") or "Decision blocked")
            if fallback and not str(fallback).startswith("mock"):
                result["failed"] = True
                result["degraded"] = True
                result["error_code"] = "PROVIDER_CONFIGURATION_MISSING" if fallback == "missing_api_key" else "PROVIDER_UNAVAILABLE"
                result["error"] = "The configured model provider was unavailable; offline output is diagnostic only."
            return result

        store[output_key] = result_text
        result = {
            "action": "llm_prompt",
            "output": output_key,
            "length": len(result_text),
            "used_llm": used_llm,
            "fallback": fallback,
            "provider_id": provider_id,
            "model": model,
            "provider_error": provider_error,
        }
        if fallback and not str(fallback).startswith("mock"):
            result.update({
                "failed": True,
                "degraded": True,
                "error_code": "PROVIDER_CONFIGURATION_MISSING" if fallback == "missing_api_key" else "PROVIDER_UNAVAILABLE",
                "error": "The configured model provider was unavailable; offline output is diagnostic only.",
            })
        return result

    def _decision_envelope_from_result(self, result_text: str, decision_contract: dict, fallback: str) -> dict:
        if fallback and decision_contract.get("offline_decision") and not fallback.startswith("mock"):
            offline = decision_contract.get("offline_decision")
            if isinstance(offline, dict):
                return offline
        envelope = parse_decision_envelope(result_text)
        if envelope and not fallback.startswith("mock"):
            envelope = self._normalize_live_decision_envelope(envelope)
        if envelope:
            return envelope
        return make_blocked_decision_envelope(
            "decision_envelope_parse_failed",
            "AI decision output was not valid decision_envelope.v1 JSON.",
            result_text,
        )

    def _normalize_live_decision_envelope(self, envelope: dict) -> dict:
        if isinstance(envelope.get("decision_envelope"), dict):
            envelope = dict(envelope["decision_envelope"])
        else:
            envelope = dict(envelope)
        status = str(envelope.get("status") or "").strip()
        looks_like_decision = status in {"resolved", "needs_user_input", "blocked"} or any(
            key in envelope for key in ("summary", "payload", "question", "issues")
        )
        if not looks_like_decision:
            return envelope
        envelope.setdefault("schema", "decision_envelope.v1")
        if status not in {"resolved", "needs_user_input", "blocked"}:
            envelope["status"] = "resolved" if isinstance(envelope.get("payload"), dict) else "blocked"
            status = str(envelope.get("status") or "").strip()
        if not str(envelope.get("summary") or "").strip():
            envelope["summary"] = self._decision_summary_from_payload(envelope)
        if status == "needs_user_input":
            envelope = self._normalize_needs_user_input_shape(envelope)
        return envelope

    def _normalize_needs_user_input_shape(self, envelope: dict) -> dict:
        envelope = dict(envelope)
        payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
        question = envelope.get("question") if isinstance(envelope.get("question"), dict) else None
        if question is None and isinstance(payload.get("question"), dict):
            question = dict(payload["question"])
            envelope["question"] = question
        elif question is not None:
            question = dict(question)
            envelope["question"] = question

        resume = envelope.get("resume") if isinstance(envelope.get("resume"), dict) else None
        if resume is None and isinstance(payload.get("resume"), dict):
            resume = dict(payload["resume"])
        if resume is None and isinstance(question, dict) and isinstance(question.get("resume"), dict):
            resume = dict(question["resume"])
        if resume is not None:
            resume = dict(resume)
            resume["policy"] = self._normalize_resume_policy(resume.get("policy"))
            envelope["resume"] = resume

        return envelope

    def _decision_summary_from_payload(self, envelope: dict) -> str:
        status = str(envelope.get("status") or "").strip()
        payload = envelope.get("payload")
        if isinstance(payload, dict):
            decision = payload.get("decision")
            if isinstance(decision, str) and decision.strip():
                return decision.strip()
            if isinstance(decision, dict):
                for key in ("summary", "decision", "next_step", "recommendation", "reason"):
                    value = decision.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                return "AI decision resolved with structured payload."
        if status == "needs_user_input":
            question = envelope.get("question") if isinstance(envelope.get("question"), dict) else {}
            prompt = question.get("prompt")
            return str(prompt).strip() if prompt else "AI decision requires user input."
        if status == "blocked":
            issues = envelope.get("issues")
            if isinstance(issues, list) and issues:
                first = issues[0] if isinstance(issues[0], dict) else {}
                message = first.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
            return "AI decision blocked the flow."
        return "AI decision resolved."

    def _apply_decision_consume(self, decision_contract: dict, envelope: dict, store: dict) -> dict | None:
        consume = decision_contract.get("consume") if isinstance(decision_contract.get("consume"), dict) else {}
        if not consume:
            return None
        path = str(consume.get("path") or "").strip()
        output_key = str(consume.get("as") or "").strip()
        result = {
            "schema": "decision_consume.v1",
            "mode": str(consume.get("mode") or "payload_path").strip() or "payload_path",
            "path": path,
            "output": output_key,
            "status": "skipped",
        }
        status = str(envelope.get("status") or "").strip()
        if status != "resolved":
            result["reason"] = f"decision status is {status or 'unknown'}"
            return result
        found, value = self._resolve_mapping_path(envelope, path)
        if not found:
            result["status"] = "failed"
            result["failed"] = True
            result["reason"] = f"decision consume path missing: {path}"
            return result
        if not output_key:
            result["status"] = "failed"
            result["failed"] = True
            result["reason"] = "decision consume output key is missing"
            return result
        store[output_key] = value
        result["status"] = "projected"
        result["value"] = value
        return result

    def _resolve_mapping_path(self, data, path: str) -> tuple[bool, object | None]:
        current = data
        segments = [piece for piece in re.split(r"[.\[\]]+", str(path or "")) if piece]
        if not segments:
            return False, None
        for part in segments:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                if index < 0 or index >= len(current):
                    return False, None
                current = current[index]
            else:
                return False, None
        return True, current

    def _run_decision_test_mode(self, run: dict) -> str:
        test_mode = run.get("test_mode") if isinstance(run.get("test_mode"), dict) else {}
        decision = str(test_mode.get("decision") or "").strip()
        return decision if decision in {"live_collaboration", "mock_resolved", "mock_interaction", "mock_blocked"} else ""

    def _should_force_live_collaboration(
        self,
        decision_contract: dict,
        params: dict,
        optional_input_key,
        store: dict,
        run: dict,
    ) -> bool:
        test_mode = run.get("test_mode") if isinstance(run.get("test_mode"), dict) else {}
        if str(test_mode.get("decision") or "").strip() != "live_collaboration":
            return False
        if "needs_user_input" not in self._split_keys(decision_contract.get("allowed_statuses")):
            return False
        interaction = decision_contract.get("interaction") if isinstance(decision_contract.get("interaction"), dict) else {}
        if not interaction:
            return False
        enabled = (
            interaction.get("live_collaboration")
            or interaction.get("requires_user_confirmation")
            or decision_contract.get("live_collaboration")
            or params.get("live_collaboration")
        )
        if not enabled:
            return False
        return not self._has_any_optional_input(optional_input_key, store)

    def _has_any_optional_input(self, optional_input_key, store: dict) -> bool:
        for key in self._split_keys(optional_input_key):
            if key not in store:
                continue
            value = store.get(key)
            if value not in (None, "", {}, []):
                return True
        return False

    def _normalize_resume_policy(self, policy) -> str:
        value = str(policy or "").strip()
        aliases = {
            "": "resume_same_node",
            "same": "resume_same_node",
            "same_node": "resume_same_node",
            "resume": "resume_same_node",
            "resume_on_input": "resume_same_node",
            "continue_in_same_node": "resume_same_node",
            "user_input": "resume_same_node",
            "replace": "resume_same_node",
            "next": "resume_next_node",
            "continue": "resume_next_node",
            "resume_next": "resume_next_node",
            "target": "resume_target_node",
            "resume_to_target": "resume_target_node",
        }
        return aliases.get(value, value)

    def _apply_contract_interaction(self, envelope: dict, decision_contract: dict, params: dict, output_key: str) -> dict:
        if envelope.get("status") != "needs_user_input":
            return envelope
        envelope = self._normalize_needs_user_input_shape(envelope)
        interaction = decision_contract.get("interaction") if isinstance(decision_contract.get("interaction"), dict) else {}
        if not interaction:
            return envelope

        question = envelope.get("question") if isinstance(envelope.get("question"), dict) else {}
        question = dict(question)
        question.setdefault("id", f"live_collaboration_{output_key}_question")
        if not str(question.get("prompt") or "").strip():
            question["prompt"] = envelope.get("summary") or params.get("description") or "请补充该决策节点继续运行所需的信息。"
        if interaction.get("input_schema") is not None:
            question["input_schema"] = interaction.get("input_schema")
        else:
            question.setdefault("input_schema", {"type": "object", "properties": {"answer": {"type": "string"}}})
        if str(interaction.get("store_key") or "").strip():
            question["store_key"] = str(interaction.get("store_key")).strip()
        else:
            question.setdefault("store_key", "decision_user_reply")
        if str(interaction.get("ui_extension") or "").strip():
            question["ui_extension"] = str(interaction.get("ui_extension")).strip()
        envelope["question"] = question

        resume = envelope.get("resume") if isinstance(envelope.get("resume"), dict) else {}
        resume = dict(resume)
        if str(interaction.get("resume_policy") or "").strip():
            resume["policy"] = str(interaction.get("resume_policy")).strip()
        else:
            resume["policy"] = self._normalize_resume_policy(resume.get("policy"))
        if interaction.get("target_node"):
            resume["target_node"] = interaction.get("target_node")
        for field in ("answer_routes", "replay_from_target", "clear_downstream", "copy_answer_to", "clear_store_keys"):
            if field in interaction:
                resume[field] = interaction.get(field)
        envelope["resume"] = resume
        return envelope

    def _blocked_envelope_from_validation(self, blockers: list[dict], raw_output: str) -> dict:
        issues = []
        for item in blockers:
            if not isinstance(item, dict):
                continue
            issues.append({
                "severity": item.get("severity") or "blocker",
                "code": item.get("code") or "decision_envelope_validation_failed",
                "message": item.get("message") or "AI decision output failed decision_envelope.v1 validation.",
            })
        if not issues:
            issues = [{
                "severity": "blocker",
                "code": "decision_envelope_validation_failed",
                "message": "AI decision output failed decision_envelope.v1 validation.",
            }]
        envelope = {
            "schema": "decision_envelope.v1",
            "status": "blocked",
            "summary": "AI decision output failed decision_envelope.v1 validation.",
            "issues": issues,
        }
        if raw_output:
            envelope["raw_output"] = raw_output[:4000]
        return envelope

    def _format_decision_validation_error(self, blockers: list[dict]) -> str:
        parts = []
        for item in blockers[:5]:
            if not isinstance(item, dict):
                continue
            code = item.get("code") or "decision_envelope_validation_failed"
            message = item.get("message") or "AI decision output failed decision_envelope.v1 validation."
            parts.append(f"{code}: {message}")
        return "；".join(parts) if parts else "AI decision output failed decision_envelope.v1 validation."

    def _collaboration_confirmation_envelope(self, envelope: dict, decision_contract: dict, params: dict, output_key: str) -> dict:
        interaction = decision_contract.get("interaction") if isinstance(decision_contract.get("interaction"), dict) else {}
        input_schema = interaction.get("input_schema") or {
            "type": "object",
            "properties": {
                "review": {"type": "string", "title": "确认或修改意见"},
            },
            "required": ["review"],
        }
        store_key = str(interaction.get("store_key") or "decision_user_reply").strip() or "decision_user_reply"
        resume_policy = str(interaction.get("resume_policy") or "resume_same_node").strip() or "resume_same_node"
        summary = str(envelope.get("summary") or params.get("description") or "AI 已生成方案，等待用户确认。").strip()
        proposal = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
        proposal_text = json.dumps(proposal, ensure_ascii=False, indent=2)[:1600] if proposal else ""
        prompt = (
            f"{summary}\n\n"
            f"{proposal_text}\n\n"
            "请确认这个方案是否继续执行；如不满意，请写明修改意见。"
        ).strip()
        resume = {"policy": resume_policy}
        if interaction.get("target_node"):
            resume["target_node"] = interaction.get("target_node")
        for field in ("answer_routes", "replay_from_target", "clear_downstream", "copy_answer_to", "clear_store_keys"):
            if field in interaction:
                resume[field] = interaction.get(field)
        return {
            "schema": "decision_envelope.v1",
            "status": "needs_user_input",
            "summary": f"等待用户确认：{summary}",
            "question": {
                "id": f"live_collaboration_{output_key}_confirm",
                "prompt": prompt,
                "input_schema": input_schema,
                "store_key": store_key,
                **({"ui_extension": interaction.get("ui_extension")} if interaction.get("ui_extension") else {}),
            },
            "resume": resume,
            "proposal": envelope,
        }

    def _mock_decision_envelope_for_mode(self, mode: str, mock: dict | None, decision_contract: dict, params: dict, output_key: str) -> dict:
        if mode == "mock":
            return mock if isinstance(mock, dict) else make_mock_decision_envelope()
        if mode == "mock_resolved":
            offline = decision_contract.get("offline_decision") if isinstance(decision_contract, dict) else None
            if isinstance(offline, dict) and offline.get("status") == "resolved":
                return offline
            if isinstance(mock, dict) and mock.get("status") == "resolved":
                return mock
            return make_mock_decision_envelope(
                "resolved",
                params.get("mock_summary") or params.get("description") or "Mock resolved decision.",
                {
                    "decision": {
                        "mock": True,
                        "mode": mode,
                        "output": output_key,
                    }
                },
            )
        if mode == "mock_interaction":
            if isinstance(mock, dict) and mock.get("status") == "needs_user_input":
                return mock
            interaction = decision_contract.get("interaction") if isinstance(decision_contract.get("interaction"), dict) else {}
            store_key = str(interaction.get("store_key") or "decision_user_reply").strip() or "decision_user_reply"
            input_schema = interaction.get("input_schema") or {
                "type": "object",
                "properties": {
                    "answer": {"type": "string", "title": "补充信息"},
                },
                "required": ["answer"],
            }
            resume_policy = str(interaction.get("resume_policy") or "resume_same_node").strip() or "resume_same_node"
            envelope = {
                "schema": "decision_envelope.v1",
                "status": "needs_user_input",
                "summary": "Mock interaction requested user input.",
                "question": {
                    "id": f"mock_{output_key}_question",
                    "prompt": params.get("mock_question") or params.get("description") or "请补充这个决策节点继续运行所需的信息。",
                    "input_schema": input_schema,
                    "store_key": store_key,
                },
                "resume": {
                    "policy": resume_policy,
                },
            }
            if interaction.get("target_node"):
                envelope["resume"]["target_node"] = interaction.get("target_node")
            for field in ("answer_routes", "replay_from_target", "clear_downstream", "copy_answer_to", "clear_store_keys"):
                if field in interaction:
                    envelope["resume"][field] = interaction.get(field)
            return envelope
        if mode == "mock_blocked":
            return make_blocked_decision_envelope(
                "mock_decision_blocked",
                "Mock blocked decision.",
            )
        return make_mock_decision_envelope()

    def _pending_interaction_from_decision(self, run: dict, output_key: str, envelope: dict) -> dict:
        import uuid
        question = envelope.get("question") if isinstance(envelope.get("question"), dict) else {}
        resume = envelope.get("resume") if isinstance(envelope.get("resume"), dict) else {}
        interaction_id = question.get("id") or f"pi_{uuid.uuid4().hex[:12]}"
        pending_resume = {
            "policy": resume.get("policy") or "resume_same_node",
            **({"target_node": resume.get("target_node")} if resume.get("target_node") else {}),
        }
        for field in ("answer_routes", "replay_from_target", "clear_downstream", "copy_answer_to", "clear_store_keys"):
            if field in resume:
                pending_resume[field] = resume.get(field)
        return {
            "schema": "pending_interaction.v1",
            "interaction_id": interaction_id,
            "run_id": run.get("run_id"),
            "node_output": output_key,
            "status": "waiting_user",
            "question": {
                "prompt": question.get("prompt") or envelope.get("summary") or "请补充运行所需信息。",
                "input_schema": question.get("input_schema") or {},
                "store_key": question.get("store_key") or "user_reply",
            },
            "resume": pending_resume,
            **({"ui_extension": question.get("ui_extension")} if question.get("ui_extension") else {}),
        }

    def _offline_llm_response(self, system_prompt: str, prompt_template: str, context_text: str) -> str:
        source_match = re.search(r"\[[^\]]+\]\n(.*?)(?:\n\n\[[^\]]+\]\n|$)", context_text or "", flags=re.DOTALL)
        source_text = source_match.group(1).strip() if source_match else (context_text or "")
        if not source_text.strip():
            return "\u79bb\u7ebf\u515c\u5e95\uff1a\u6682\u65e0\u53ef\u603b\u7ed3\u5185\u5bb9\u3002"

        title = "\u6587\u4ef6\u603b\u7ed3"
        for line in source_text.splitlines():
            striped = line.strip()
            if striped.startswith("#"):
                title = striped.lstrip("#").strip() or title
                break

        path_matches = re.findall(r'"(file_path|output_path)"\s*:\s*"([^"]+)"', context_text or "")
        path_map = {key: value for key, value in path_matches}
        focus_match = re.search(r'"focus"\s*:\s*"([^"]+)"', context_text or "", flags=re.DOTALL)
        focus = (focus_match.group(1) if focus_match else "").strip()

        paragraph_lines = []
        for line in source_text.splitlines():
            striped = line.strip()
            if not striped or striped.startswith("[") or striped.startswith("#") or striped.startswith("{") or striped.startswith("}") or ":" in striped[:40]:
                continue
            paragraph_lines.append(striped)
        body = " ".join(paragraph_lines).strip()
        if len(body) > 220:
            body = body[:220].rstrip() + "..."

        key_points = []
        for chunk in re.split("[\\u3002\\uff01\\uff1f!?\\uff1b;\\n]", body):
            chunk = chunk.strip()
            if chunk and chunk not in key_points:
                key_points.append(chunk)
            if len(key_points) >= 3:
                break
        if not key_points and body:
            key_points = [body]

        want_json = "json" in f"{system_prompt}\n{prompt_template}".lower()
        if want_json:
            payload = {
                "title": title,
                "focus": focus,
                "summary": body or title,
                "key_points": key_points,
                "source_path": path_map.get("file_path", ""),
                "output_path": path_map.get("output_path", ""),
                "fallback": "offline",
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        lines = [f"# {title}", "", "## \u6838\u5fc3\u6458\u8981", body or f"\u8fd9\u662f\u5173\u4e8e\u300c{title}\u300d\u7684\u672c\u5730\u6587\u4ef6\u603b\u7ed3\u3002"]
        if focus:
            lines += ["", "## \u5173\u6ce8\u70b9", focus]
        if key_points:
            lines += ["", "## \u91cd\u70b9", *(f"- {item}" for item in key_points)]
        if path_map.get("output_path"):
            lines += ["", "## \u8f93\u51fa\u8def\u5f84", path_map["output_path"]]
        lines += ["", "_\u79bb\u7ebf\u515c\u5e95\u751f\u6210_"]
        return "\n".join(lines)

    def _pass_result(self, params: dict, store: dict, _run: dict, _run_dir) -> dict:
        preset_config = params.get("preset_config") or {}
        from_key = (
            params.get("input") or
            params.get("from") or
            preset_config.get("from") or
            preset_config.get("source")
        )
        to_key = (
            params.get("output") or
            params.get("to") or
            preset_config.get("to") or
            preset_config.get("output_name")
        )
        mapping_str = preset_config.get("mapping") or ""
        items_key = preset_config.get("items") or ""
        merge_output = preset_config.get("output_name") or to_key

        if mapping_str:
            for line in mapping_str.strip().splitlines():
                parts = [p.strip() for p in line.split("->")]
                if len(parts) == 2:
                    src, dst = parts
                    if src in store:
                        store[dst] = store[src]
            return {"action": "pass_result", "mapping": mapping_str}

        if items_key and merge_output:
            keys = [k.strip() for k in items_key.split(",") if k.strip()]
            merged: dict = {}
            for key in keys:
                if key in store:
                    val = store[key]
                    merged[key] = val if isinstance(val, (str, dict, list)) else str(val)
            store[merge_output] = merged
            return {"action": "pass_result", "merge": keys, "output": merge_output}

        if from_key and to_key:
            val = store.get(from_key)
            if val is not None:
                store[to_key] = val
            return {"action": "pass_result", "from": from_key, "to": to_key, "ok": val is not None}

        return {"action": "pass_result", "skipped": True, "reason": "未指定有效 from/to 或 mapping"}

    def _save_context(self, params: dict, store: dict, _run: dict, _run_dir) -> dict:
        preset_config = params.get("preset_config") or {}
        key = (
            params.get("save_to") or
            params.get("output") or
            preset_config.get("key") or
            preset_config.get("name") or
            preset_config.get("path")
        )
        source_key = (
            params.get("input") or
            preset_config.get("source") or
            preset_config.get("items")
        )
        if not key:
            return {"action": "save_context", "skipped": True, "reason": "未指定保存 key"}
        if source_key and source_key in store:
            store[key] = store[source_key]
        elif source_key:
            store[key] = source_key
        else:
            store[key] = None
        return {"action": "save_context", "key": key, "source": source_key}

    def _confirm_checkpoint(self, params: dict, store: dict, _run: dict, _run_dir) -> dict:
        preset_config = params.get("preset_config") or {}
        message = (
            params.get("condition") or
            preset_config.get("message") or
            "请确认是否继续执行。"
        )
        interaction = params.get("interaction") if isinstance(params.get("interaction"), dict) else preset_config.get("interaction")
        if isinstance(interaction, dict) and str(interaction.get("store_key") or "").strip():
            import uuid
            store_key = str(interaction.get("store_key")).strip()
            test_mode = str((_run.get("test_mode") or {}).get("decision") or "").strip()
            if store_key not in store and test_mode == "mock_resolved":
                store[store_key] = interaction.get("offline_answer") if isinstance(interaction.get("offline_answer"), dict) else {"approval": "approve"}
            if store_key not in store:
                pending = {
                    "schema": "pending_interaction.v1",
                    "interaction_id": str(interaction.get("id") or f"human_gate_{uuid.uuid4().hex[:12]}"),
                    "run_id": _run.get("run_id"),
                    "node_output": params.get("output") or "human_gate_result",
                    "status": "waiting_user",
                    "question": {
                        "prompt": str(interaction.get("prompt") or message),
                        "input_schema": interaction.get("input_schema") or {"type": "object", "properties": {"approval": {"type": "string"}}},
                        "store_key": store_key,
                    },
                    "resume": {"policy": str(interaction.get("resume_policy") or "resume_same_node")},
                }
                if interaction.get("ui_extension"):
                    pending["ui_extension"] = str(interaction.get("ui_extension"))
                store["_pending_interaction"] = pending
                return {"action": "confirm_checkpoint", "paused": True, "pause_status": "paused_waiting_user", "pending_interaction": pending, "message": message}
            output_key = str(params.get("output") or preset_config.get("output_name") or "human_gate_result")
            store[output_key] = store.get(store_key)
            store["_checkpoint_status"] = "approved"
            return {"action": "confirm_checkpoint", "output": output_key, "message": message, "approved": True}
        store["_checkpoint_message"] = message
        store["_checkpoint_status"] = "auto_approved"
        return {"action": "confirm_checkpoint", "message": message, "auto_approved": True}

    def _custom_action(self, params: dict, store: dict, _run: dict, _run_dir) -> dict:
        preset_config = params.get("preset_config") or {}
        input_key = params.get("input") or params.get("from") or preset_config.get("from")
        output_key = (
            params.get("output") or
            params.get("output_name") or
            preset_config.get("output_name") or
            "custom_result"
        )
        optional_input_key = params.get("optional_input") or preset_config.get("optional_input")
        context_parts = []
        if input_key:
            context_parts.append(self._read_input(input_key, store, required=True))
        if optional_input_key:
            optional_context = self._read_input(optional_input_key, store, required=False)
            if optional_context:
                context_parts.append(optional_context)
        context_text = "\n\n".join(item for item in context_parts if item)
        if context_text:
            store[output_key] = context_text
        return {"action": "custom_action", "output": output_key if context_text else None}
