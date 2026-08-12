import json
import re
import shutil
import tempfile
from html import escape
from pathlib import Path

from core.cartridge.assets import ASSET_SCHEMA, COMPONENT_SCHEMA, sha256_bytes
from core.cartridge.presentation import default_settings_bindings, default_settings_contract, default_ui_contract
from core.cartridge.validator import ManifestValidator
from core.cartridge.validator import ManifestValidationError
from core.data_paths import DEV_CARTRIDGES_DIR
from core.protocol import DataContractError, load_protocol_release_catalog, validate_cartridge_presentation_contracts
from core.studio.tuning_repository import TuningRepositoryStore


class DevFlowManager:
    FILES = {
        "manifest": "manifest.json",
        "root_flow": "root.flow.json",
        "welcome": "assets/welcome.md",
        "asset_registry": "assets/registry.json",
        "interaction_components": "assets/components.json",
        "settings_contract": "contracts/settings.contract.json",
        "settings_bindings": "settings/bindings.json",
        "ui_contract": "contracts/ui.contract.json",
    }

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.release_catalog = load_protocol_release_catalog(self.root)
        self.default_protocol = self.release_catalog.data["default_for_new_flows"]
        self.default_protocol_id = str(self.default_protocol["id"])
        self.default_protocol_version = str(self.default_protocol["version"])
        self.default_runtime_adapter = self.release_catalog.runtime_adapter(self.default_protocol_id, self.default_protocol_version)
        self.base_contract = self.release_catalog.data["base_contract"]
        self.dev_dir = self.root / DEV_CARTRIDGES_DIR
        self.validator = ManifestValidator()
        self.tuning = TuningRepositoryStore(self.root)
        self.dev_dir.mkdir(parents=True, exist_ok=True)

    def create_flow(self, flow_id: str, name: str, description: str = "") -> dict:
        flow_id = self._normalize_id(flow_id)
        path = self.dev_dir / flow_id
        if path.exists():
            raise FileExistsError(f"Dev flow already exists: {flow_id}")
        (path / "assets").mkdir(parents=True, exist_ok=True)
        (path / "contracts").mkdir(parents=True, exist_ok=True)
        (path / "settings").mkdir(parents=True, exist_ok=True)
        welcome_markdown = f"# {name}\n\n这是一个开发中的 Flow。"
        welcome_html = (
            "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            f"<title>{escape(name)}</title><style>body{{font-family:system-ui;padding:24px;color:#2f2923}}"
            "main{max-width:720px;margin:auto}h1{color:#b84b24;font-size:26px;line-height:1.25;overflow-wrap:anywhere}</style></head>"
            f"<body><main><h1>{escape(name)}</h1><p>{escape(description or '这是一个开发中的 Flow。')}</p></main></body></html>"
        )
        (path / "assets" / "welcome.md").write_bytes(welcome_markdown.encode("utf-8"))
        (path / "assets" / "welcome.html").write_bytes(welcome_html.encode("utf-8"))
        self._write_json(path / "assets" / "registry.json", {
            "schema": ASSET_SCHEMA,
            "assets": [
                self._asset_entry("ui.welcome", "interaction_template", "assets/welcome.html", "text/html", welcome_html.encode("utf-8")),
                self._asset_entry("copy.welcome", "prompt", "assets/welcome.md", "text/markdown", welcome_markdown.encode("utf-8")),
            ],
        })
        self._write_json(path / "assets" / "components.json", {
            "schema": COMPONENT_SCHEMA,
            "components": [{
                "id": "welcome.panel",
                "version": "1.0.0",
                "runtime": "passive",
                "entry": {"type": "asset", "ref": "asset:ui.welcome"},
                "supported_modes": ["display"],
                "input_schema": {"type": "object"},
                "actions": [],
                "host_capabilities": [],
            }],
        })
        self._write_json(path / "contracts" / "settings.contract.json", default_settings_contract())
        self._write_json(path / "settings" / "bindings.json", default_settings_bindings())
        self._write_json(path / "contracts" / "ui.contract.json", default_ui_contract())
        manifest = self._manifest_template(flow_id, name, description)
        root_flow = self._root_flow_template(flow_id, name)
        self._write_json(path / "manifest.json", manifest)
        self._write_json(path / "root.flow.json", root_flow)
        if self._has_feature(root_flow["protocol"], "recipe_versioning"):
            self.tuning.initialize(flow_id, root_flow)
        return {"id": flow_id, "path": str(path), "manifest": manifest, "root_flow": root_flow}

    def read_files(self, flow_id: str) -> dict:
        path = self._flow_path(flow_id)
        return {
            key: (path / rel_path).read_text(encoding="utf-8") if (path / rel_path).exists() else ""
            for key, rel_path in self.FILES.items()
        }

    def delete_flow(self, flow_id: str) -> dict:
        path = self._flow_path(flow_id)
        shutil.rmtree(path)
        self.tuning.delete(flow_id)
        return {"ok": True, "id": flow_id}

    def save_file(self, flow_id: str, file_type: str, content: str) -> dict:
        if file_type not in self.FILES:
            raise ValueError(f"Unsupported file type: {file_type}")
        path = self._flow_path(flow_id)
        target = path / self.FILES[file_type]
        parsed_content = None
        if file_type in {"manifest", "root_flow"}:
            parsed_content = json.loads(content)
        if file_type == "manifest":
            self.validator.validate_package(path, parsed_content)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_suffix(target.suffix + ".tmp")
        temp_target.write_text(content, encoding="utf-8")
        temp_target.replace(target)
        if file_type == "root_flow" and isinstance(parsed_content, dict):
            protocol = parsed_content.get("protocol") if isinstance(parsed_content.get("protocol"), dict) else {}
            if self._has_feature(protocol, "recipe_versioning"):
                self.tuning.reconcile_node_heads(flow_id, parsed_content)
        return {"file_type": file_type, "saved": True}

    def save_files(self, flow_id: str, files: dict[str, str]) -> dict:
        """Validate related authoring files together and roll back a partial commit."""
        if not isinstance(files, dict) or not files:
            raise ValueError("files must contain at least one authoring file")
        unknown = sorted(set(files) - set(self.FILES))
        if unknown:
            raise ValueError("Unsupported file types: " + ", ".join(unknown))
        if any(not isinstance(content, str) for content in files.values()):
            raise ValueError("authoring file content must be a string")

        path = self._flow_path(flow_id)
        with tempfile.TemporaryDirectory(prefix="cartridgeflow-flow-save-", dir=path.parent) as temp_dir:
            staged = Path(temp_dir) / "package"
            shutil.copytree(path, staged)
            for file_type, content in files.items():
                target = staged / self.FILES[file_type]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            manifest = json.loads((staged / self.FILES["manifest"]).read_text(encoding="utf-8"))
            root_flow = json.loads((staged / self.FILES["root_flow"]).read_text(encoding="utf-8"))
            self.validator.validate_package(staged, manifest)
            errors: list[str] = []
            warnings: list[str] = []
            self._validate_root_flow(root_flow, errors, warnings)
            self._validate_presentation(staged, manifest, root_flow, errors)
            if errors:
                raise ValueError("; ".join(errors))

        originals: dict[Path, bytes | None] = {}
        try:
            for file_type, content in files.items():
                target = path / self.FILES[file_type]
                originals[target] = target.read_bytes() if target.exists() else None
                target.parent.mkdir(parents=True, exist_ok=True)
                temp_target = target.with_suffix(target.suffix + ".tmp")
                temp_target.write_text(content, encoding="utf-8")
                temp_target.replace(target)
            if "root_flow" in files:
                root_flow = json.loads(files["root_flow"])
                protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
                if self._has_feature(protocol, "recipe_versioning"):
                    self.tuning.reconcile_node_heads(flow_id, root_flow)
        except Exception:
            for target, original in originals.items():
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(original)
            raise
        return {"saved": True, "file_types": sorted(files)}

    def validate_files(self, flow_id: str, files: dict | None = None) -> dict:
        path = self._flow_path(flow_id)
        current = self.read_files(flow_id)
        current.update(files or {})
        with tempfile.TemporaryDirectory(prefix="cartridgeflow-flow-validate-", dir=path.parent) as temp_dir:
            staged = Path(temp_dir) / "package"
            shutil.copytree(path, staged)
            for file_type, content in current.items():
                if file_type not in self.FILES or not isinstance(content, str):
                    continue
                target = staged / self.FILES[file_type]
                if not content:
                    target.unlink(missing_ok=True)
                    continue
                if target.exists() and target.read_text(encoding="utf-8") == content:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            return self._validate_files_at(staged, current)

    def _validate_files_at(self, path: Path, current: dict) -> dict:
        errors = []
        warnings = []
        manifest = self._parse_json_file("manifest", current.get("manifest", ""), errors)
        root_flow = self._parse_json_file("root_flow", current.get("root_flow", ""), errors)
        if manifest:
            try:
                self.validator.validate_package(path, manifest)
            except ManifestValidationError as e:
                errors.extend(str(e).split("; "))
        if root_flow:
            self._validate_root_flow(root_flow, errors, warnings)
            protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
            if not self._has_feature(protocol, "execution_plan"):
                try:
                    from core.lab.flow_analyzer import analyze_flow_structure
                    structure = analyze_flow_structure(root_flow)
                    for finding in structure.get("findings") or []:
                        if finding.get("severity") == "warning":
                            warnings.append(f"isolated node: {finding.get('node')} - {finding.get('detail')}")
                except Exception as e:
                    warnings.append(f"flow structure analysis skipped: {e}")
        if manifest and root_flow:
            self._validate_presentation(path, manifest, root_flow, errors, files=current)
        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "summary": "校验通过" if not errors else f"发现 {len(errors)} 个错误",
        }

    def _validate_presentation(
        self,
        path: Path,
        manifest: dict,
        root_flow: dict,
        errors: list[str],
        *,
        files: dict[str, str] | None = None,
    ) -> None:
        presentation = manifest.get("presentation")
        supplied = files or {}
        has_documents = any(str(supplied.get(key) or "").strip() for key in ("settings_contract", "settings_bindings", "ui_contract"))
        if presentation is None and not has_documents:
            return
        try:
            settings = json.loads(supplied.get("settings_contract") or (path / self.FILES["settings_contract"]).read_text(encoding="utf-8"))
            bindings = json.loads(supplied.get("settings_bindings") or (path / self.FILES["settings_bindings"]).read_text(encoding="utf-8"))
            ui = json.loads(supplied.get("ui_contract") or (path / self.FILES["ui_contract"]).read_text(encoding="utf-8"))
            components_value = json.loads(supplied.get("interaction_components") or (path / self.FILES["interaction_components"]).read_text(encoding="utf-8"))
            component_by_id = {
                str(item.get("id")): item
                for item in components_value.get("components") or []
                if isinstance(item, dict) and item.get("id")
            }
            validate_cartridge_presentation_contracts(
                settings,
                bindings,
                ui,
                root_flow,
                component_by_id=component_by_id,
                root=self.root,
            )
        except (DataContractError, OSError, UnicodeError, json.JSONDecodeError, TypeError, AttributeError) as exc:
            code = getattr(exc, "code", "presentation_contract_invalid")
            errors.append(f"{code}: {exc}")

    def preview_graph(self, flow_id: str, files: dict | None = None) -> dict:
        current = self.read_files(flow_id)
        current.update(files or {})
        manifest = json.loads(current.get("manifest") or "{}")
        root_flow = json.loads(current.get("root_flow") or "{}")
        protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
        if self._has_feature(protocol, "recipe_versioning"):
            root_flow, tuning_context = self.tuning.materialize_draft(flow_id, root_flow)
            return {**manifest, "root_flow": root_flow, "tuning_context": tuning_context}
        return {**manifest, "root_flow": root_flow}

    def _flow_path(self, flow_id: str) -> Path:
        path = (self.dev_dir / flow_id).resolve()
        root = self.dev_dir.resolve()
        if path != root and root not in path.parents:
            raise ValueError("Invalid dev flow path")
        if not path.is_dir():
            raise FileNotFoundError(f"Dev flow not found: {flow_id}")
        return path

    def _normalize_id(self, flow_id: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9._-]+", ".", flow_id.strip()).strip(".").lower()
        if not value:
            raise ValueError("flow id is required")
        if not value.startswith("dev."):
            value = f"dev.{value}"
        return value

    def _parse_json_file(self, file_type: str, content: str, errors: list[str]) -> dict | None:
        try:
            return json.loads(content or "{}")
        except json.JSONDecodeError as e:
            errors.append(f"{file_type} JSON 解析失败: line {e.lineno}, column {e.colno}")
            return None

    def _validate_root_flow(self, root_flow: dict, errors: list[str], warnings: list[str]):
        states = root_flow.get("states")
        start = root_flow.get("start")
        if not isinstance(root_flow.get("id"), str) or not root_flow.get("id"):
            errors.append("root_flow.id is required")
        if not isinstance(states, dict) or not states:
            errors.append("root_flow.states must be a non-empty object")
            return
        if not start:
            errors.append("root_flow.start is required")
        elif start not in states:
            errors.append(f"root_flow.start state not found: {start}")
        terminal_count = 0
        for state_id, state in states.items():
            if not isinstance(state, dict):
                errors.append(f"root_flow.states.{state_id} must be an object")
                continue
            next_state = state.get("next")
            if next_state and next_state not in states:
                errors.append(f"root_flow.states.{state_id}.next points to missing state: {next_state}")
            if state.get("type") == "terminal":
                terminal_count += 1
        protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
        if self._has_feature(protocol, "execution_plan"):
            from core.protocol.flow_contract import validate_execution_plan_v1_flow_contract
            for finding in validate_execution_plan_v1_flow_contract(
                root_flow,
                protocol_id=str(protocol.get("id") or ""),
                protocol_version=str(protocol.get("version") or ""),
            ):
                if finding.get("severity") == "blocker":
                    errors.append(f"{finding.get('code')}: {finding.get('message')}")
            return
        is_typed_protocol = self._has_feature(protocol, "typed_control_edges")
        if is_typed_protocol and root_flow.get("edges"):
            errors.append(f"CF-FARP@{protocol.get('version')} root_flow.edges is legacy; use typed root_flow.control_edges")
        edge_field = "control_edges" if is_typed_protocol else "edges"
        edges = root_flow.get(edge_field) or []
        if edges and not isinstance(edges, list):
            errors.append(f"root_flow.{edge_field} must be an array")
        elif isinstance(edges, list):
            for index, edge in enumerate(edges):
                if not isinstance(edge, dict):
                    errors.append(f"root_flow.{edge_field}[{index}] must be an object")
                    continue
                if is_typed_protocol and edge.get("kind") not in {"control", "branch", "action_route", "failure_route"}:
                    errors.append(f"root_flow.control_edges[{index}].kind is invalid")
                source = edge.get("from") or edge.get("source")
                target = edge.get("to") or edge.get("target")
                if not source:
                    errors.append(f"root_flow.{edge_field}[{index}].from is required")
                elif source not in states:
                    errors.append(f"root_flow.{edge_field}[{index}].from points to missing state: {source}")
                if not target:
                    errors.append(f"root_flow.{edge_field}[{index}].to is required")
                elif target not in states:
                    errors.append(f"root_flow.{edge_field}[{index}].to points to missing state: {target}")
        if terminal_count == 0:
            warnings.append("root_flow has no terminal state")

    def _manifest_template(self, flow_id: str, name: str, description: str) -> dict:
        return {
            "schema_version": "1.0",
            "id": flow_id,
            "name": name or flow_id,
            "version": "0.0.1",
            "kind": "runtime_cartridge",
            "category": "dev_flow",
            "description": description or "Flow Developer Lab 创建的开发 Flow。",
            "publisher": {"id": "local", "name": "Local Developer", "type": "local", "verified": False},
            "branding": {"tags": ["dev", "flow", "lab"]},
            "welcome": {"type": "markdown", "entry": "assets/welcome.md"},
            "root_flow": {"entry": "root.flow.json", "mode": "lifecycle", "required": True},
            "asset_registry": "assets/registry.json",
            "interaction_components": "assets/components.json",
            "presentation": {
                "settings": {
                    "contract": "contracts/settings.contract.json",
                    "bindings": "settings/bindings.json",
                },
                "ui": {"contract": "contracts/ui.contract.json"},
            },
            "base_contract": dict(self.base_contract),
            "runtime_contract": {
                "protocol": self.default_protocol_id,
                "protocol_version": self.default_protocol_version,
                "target_runtimes": [{"id": "CF-DRP", "version": "1.0"}],
                "required_profiles": ["runtime_core", "flow_analysis", "tool_transparency", "execution_plan_runtime", "dynamic_decision_runtime", "interactive_decision_runtime", "interaction_runtime", "tuning_authoring", "recipe_release_runtime"],
                "recommended_profiles": ["testbench_core", "dev_authoring"],
                "required_capabilities": [
                    "manifest_load",
                    "manifest_validate",
                    "runtime_contract_parse",
                    "compatibility_report",
                    "root_flow_execution",
                    "structured_io_contract",
                    "explicit_input_binding",
                    "typed_control_edges",
                    "executable_topology_filter",
                    "flow_analysis_report_v1",
                    "analysis_report_freshness_guard",
                    "basic_node_execution",
                    "unified_process_node",
                    "process_node_kind_parse",
                    "process_executor_contract",
                    "process_effect_contract",
                    "decision_process",
                    "transfer_process",
                    "mcp_read_process",
                    "mcp_execute_process",
                    "process_mcp_readonly_binding",
                    "decision_envelope_v1",
                    "decision_envelope_validate",
                    "decision_consume_contract",
                    "decision_consume_projection",
                    "runtime_user_input_request",
                    "paused_waiting_user_status",
                    "pending_interaction_record_v2",
                    "runtime_resume_after_user_input",
                    "node_display_name",
                    "package_asset_registry",
                    "stable_asset_reference",
                    "interaction_component_registry",
                    "interaction_node",
                    "interaction_named_action_routes",
                    "passive_html_safety",
                    "builtin_tool_call",
                    "artifact_collect",
                    "data_chain_diagnostics",
                    "delivery_readiness_check",
                    "runtime_error_envelope_v1",
                    "runtime_state_machine",
                    "checkpoint_persistence",
                    "runtime_retry_policy",
                    "runtime_checkpoint_resume",
                    "runtime_rollback",
                    "runtime_restart",
                    "side_effect_replay_guard",
                    "model_recipe_binding",
                    "delivery_primary_output_guard",
                    "mcp_source_model_v1",
                    "tool_source_provenance",
                    "explicit_fallback_policy",
                    "opaque_tool_visibility_guard",
                    "mcp_source_digest_guard",
                    "portable_dlc_descriptor_v3",
                    "tool_resource_catalog_v2",
                    "execution_plan_v1_authoring",
                    "execution_plan_static_conformance",
                    "execution_plan_compile",
                    "execution_plan_sequence_contract",
                    "execution_plan_fork_contract",
                    "execution_plan_join_all_contract",
                    "execution_plan_join_any_contract",
                    "execution_plan_join_keyed_contract",
                    "execution_plan_loop_contract",
                    "execution_plan_batch_contract",
                    "execution_plan_wait_contract",
                    "execution_plan_failure_contract",
                    "execution_plan_token_ledger",
                    "execution_plan_join_runtime",
                    "execution_plan_wait_resume",
                    "execution_plan_cancellation",
                    "execution_plan_source_digest_guard",
                    "trusted_subprotocol_registry",
                    "tuning_repository_v1",
                    "tuning_revision_validate",
                    "tuning_node_head",
                    "recipe_release_snapshot_v1",
                    "recipe_release_activate",
                    "recipe_release_rollback",
                    "tuning_materialize",
                    "run_recipe_provenance",
                ],
                "optional_capabilities": [
                    "artifact_preview",
                    "testbench_run",
                    "probe_run",
                    "structure_analysis",
                    "optional_input",
                ],
                "required_tools": [],
                "optional_tools": [],
            },
            "tuning_contract": {
                "protocol": "CF-TUNING",
                "protocol_version": "1.0",
                "adapter": "cf-tuning.repository.v1",
                "release_entry": "tuning/release.json",
                "required_for": ["production", "package", "publish"],
            },
            "delivery_readiness": {"level": "dev", "certification_target": f"{self.default_protocol_id}@{self.default_protocol_version}", "notes": "Development flow generated by Flow Developer Lab."},
            "runtime": {"type": "capability_flow"},
            "workspace": {"type": "none", "required": False, "open_policy": "manual"},
            "environment": {"os": ["windows", "macos", "linux"], "requires": []},
            "permissions": [],
            "dependencies": [],
            "mcp_tools": [
                {
                    "id": "filesystem_write",
                    "name": "Filesystem 写入文件",
                    "type": "builtin",
                    "server": "filesystem",
                    "tool": "write_file",
                    "transparency": "contract_only",
                    "description": "把 AI 处理节点产出的内容写入工作区内的指定文件。",
                    "default_params": {"path": "test_output/result.txt", "content": "store:analysis_result"},
                    "contract": {"side_effect": "writes_files"},
                    "enabled": True,
                },
                {
                    "id": "filesystem_read",
                    "name": "Filesystem 读取文件",
                    "type": "builtin",
                    "server": "filesystem",
                    "tool": "read_file",
                    "transparency": "contract_only",
                    "description": "读取工作区内指定文件，并把内容写回 context.store。",
                    "default_params": {"path": "test_output/result.txt"},
                    "contract": {"side_effect": "none"},
                    "enabled": True,
                },
            ],
            "llm_recipe": {"schema": "cartridgeflow.llm_recipe.v1", "roles": []},
            "resource_requirements": [],
            "inputs": [],
            "outputs": [],
            "artifacts": {"store_policy": "run_scoped", "visibility_default": "user", "allowed_types": ["json", "text", "html"]},
            "delivery": {"type": "structured", "primary_output": "", "show_artifacts": True},
        }

    def _root_flow_template(self, flow_id: str, name: str) -> dict:
        if self.default_runtime_adapter in {"cf-farp.execution-plan.v1", "cf-farp.trusted-node-mapping.v1"}:
            return {
                "schema_version": "1.0",
                "id": f"{flow_id}.root",
                "name": f"{name or flow_id} 根流程",
                "mode": "lifecycle",
                "cartridge_id": flow_id,
                "protocol": {"id": self.default_protocol_id, "version": self.default_protocol_version},
                "start": "start",
                "states": {
                    "start": {"type": "control", "title": "开始", "display_name": "开始", "locked": True},
                    "complete": {"type": "terminal", "title": "完成", "display_name": "完成", "locked": True}
                },
                "execution_plan": {
                    "schema": "cartridgeflow.execution_plan.v1",
                    "entry": "start",
                    "edges": [{"id": "start_complete", "kind": "sequence", "from": "start", "to": "complete"}]
                }
            }
        return {
            "schema_version": "1.0",
            "id": f"{flow_id}.root",
            "name": f"{name or flow_id} Root Flow",
            "mode": "lifecycle",
            "cartridge_id": flow_id,
            "protocol": {"id": self.default_protocol_id, "version": self.default_protocol_version},
            "start": "start",
            "states": {
                "start": {"type": "system", "title": "开始", "display_name": "开始", "action": "start", "locked": True, "next": "welcome"},
                "welcome": {
                    "type": "process",
                    "kind": "interaction",
                    "executor": "deterministic",
                    "effect": "none",
                    "display": {"suffix": "交互", "label": "交互节点"},
                    "title": "欢迎界面",
                    "display_name": "欢迎界面",
                    "action": "render_interaction",
                    "interaction_mode": "display",
                    "component_ref": "welcome.panel",
                    "input_binding": {},
                    "inputs": {},
                    "outputs": {},
                    "params": {
                        "node_category": "interaction",
                        "preset": "display",
                        "description": "展示卡带欢迎页。",
                    },
                    "scope": "sub_flow",
                    "entry_kind": "sub_flow",
                    "template_id": "welcome",
                    "locked": False,
                    "next": "complete",
                },
                "complete": {"type": "terminal", "title": "完成", "display_name": "完成", "locked": True},
            },
            "control_edges": [
                {"kind": "control", "from": "start", "to": "welcome"},
                {"kind": "control", "from": "welcome", "to": "complete"},
            ],
        }

    def _has_feature(self, protocol: dict, feature: str) -> bool:
        return self.release_catalog.has_feature(
            str(protocol.get("id") or ""),
            str(protocol.get("version") or ""),
            feature,
        )

    def _asset_entry(self, asset_id: str, kind: str, path: str, media_type: str, content: bytes) -> dict:
        return {
            "id": asset_id,
            "kind": kind,
            "path": path,
            "media_type": media_type,
            "sha256": sha256_bytes(content),
            "size": len(content),
            "executable": False,
        }

    def _write_json(self, path: Path, data: dict):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
