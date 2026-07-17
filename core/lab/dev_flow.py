import json
import re
import shutil
from pathlib import Path

from core.cartridge.validator import ManifestValidator
from core.cartridge.validator import ManifestValidationError


class DevFlowManager:
    FILES = {
        "manifest": "manifest.json",
        "root_flow": "root.flow.json",
        "welcome": "assets/welcome.md",
    }

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.dev_dir = self.root / "cartridges" / "dev"
        self.validator = ManifestValidator()
        self.dev_dir.mkdir(parents=True, exist_ok=True)

    def create_flow(self, flow_id: str, name: str, description: str = "") -> dict:
        flow_id = self._normalize_id(flow_id)
        path = self.dev_dir / flow_id
        if path.exists():
            raise FileExistsError(f"Dev flow already exists: {flow_id}")
        (path / "assets").mkdir(parents=True, exist_ok=True)
        manifest = self._manifest_template(flow_id, name, description)
        root_flow = self._root_flow_template(flow_id, name)
        self._write_json(path / "manifest.json", manifest)
        self._write_json(path / "root.flow.json", root_flow)
        (path / "assets" / "welcome.md").write_text(f"# {name}\n\n这是一个开发中的 Flow。", encoding="utf-8")
        (path / "assets" / "welcome.html").write_text(
            f"<!doctype html><meta charset=\"utf-8\"><title>{name}</title><main><h1>{name}</h1><p>{description or '这是一个开发中的 Flow。'}</p></main>",
            encoding="utf-8",
        )
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
        return {"ok": True, "id": flow_id}

    def save_file(self, flow_id: str, file_type: str, content: str) -> dict:
        if file_type not in self.FILES:
            raise ValueError(f"Unsupported file type: {file_type}")
        path = self._flow_path(flow_id)
        target = path / self.FILES[file_type]
        if file_type in {"manifest", "root_flow"}:
            json.loads(content)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_suffix(target.suffix + ".tmp")
        temp_target.write_text(content, encoding="utf-8")
        temp_target.replace(target)
        if file_type == "manifest":
            self.validator.validate_package(path, json.loads(content))
        return {"file_type": file_type, "saved": True}

    def validate_files(self, flow_id: str, files: dict | None = None) -> dict:
        path = self._flow_path(flow_id)
        current = self.read_files(flow_id)
        current.update(files or {})
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
            try:
                from core.lab.flow_analyzer import analyze_flow_structure
                structure = analyze_flow_structure(root_flow)
                for finding in structure.get("findings") or []:
                    if finding.get("severity") == "warning":
                        warnings.append(f"isolated node: {finding.get('node')} - {finding.get('detail')}")
            except Exception as e:
                warnings.append(f"flow structure analysis skipped: {e}")
        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "summary": "校验通过" if not errors else f"发现 {len(errors)} 个错误",
        }

    def preview_graph(self, flow_id: str, files: dict | None = None) -> dict:
        current = self.read_files(flow_id)
        current.update(files or {})
        manifest = json.loads(current.get("manifest") or "{}")
        root_flow = json.loads(current.get("root_flow") or "{}")
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
        edges = root_flow.get("edges") or []
        if edges and not isinstance(edges, list):
            errors.append("root_flow.edges must be an array")
        elif isinstance(edges, list):
            for index, edge in enumerate(edges):
                if not isinstance(edge, dict):
                    errors.append(f"root_flow.edges[{index}] must be an object")
                    continue
                source = edge.get("from") or edge.get("source")
                target = edge.get("to") or edge.get("target")
                if not source:
                    errors.append(f"root_flow.edges[{index}].from is required")
                elif source not in states:
                    errors.append(f"root_flow.edges[{index}].from points to missing state: {source}")
                if not target:
                    errors.append(f"root_flow.edges[{index}].to is required")
                elif target not in states:
                    errors.append(f"root_flow.edges[{index}].to points to missing state: {target}")
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
            "base_contract": {"id": "CF-FARP", "version": "0.4"},
            "runtime_contract": {
                "protocol": "CF-FARP",
                "protocol_version": "0.4",
                "required_profiles": ["runtime_core", "dynamic_decision_runtime", "interactive_decision_runtime"],
                "recommended_profiles": ["testbench_core", "dev_authoring"],
                "required_capabilities": [
                    "manifest_load",
                    "manifest_validate",
                    "runtime_contract_parse",
                    "compatibility_report",
                    "root_flow_execution",
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
                    "pending_interaction_record",
                    "runtime_resume_after_user_input",
                    "builtin_tool_call",
                    "artifact_collect",
                    "data_chain_diagnostics",
                    "delivery_readiness_check",
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
            "delivery_readiness": {"level": "dev", "certification_target": "CF-FARP@0.4", "notes": "Development flow generated by Flow Developer Lab."},
            "runtime": {"type": "html_generator", "adapter": "builtin:html_generator"},
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
                    "description": "读取工作区内指定文件，并把内容写回 context.store。",
                    "default_params": {"path": "test_output/result.txt"},
                    "contract": {"side_effect": "none"},
                    "enabled": True,
                },
            ],
            "inputs": [
                {"id": "title", "label": "标题", "type": "text", "required": True},
                {"id": "description", "label": "说明", "type": "textarea", "required": True},
            ],
            "outputs": [{"id": "html", "label": "HTML 产物", "type": "html", "required": True}],
            "artifacts": {"store_policy": "run_scoped", "visibility_default": "user", "allowed_types": ["html"]},
            "delivery": {"type": "summary_with_artifacts", "primary_output": "html", "show_artifacts": True},
        }

    def _root_flow_template(self, flow_id: str, name: str) -> dict:
        return {
            "schema_version": "1.0",
            "id": f"{flow_id}.root",
            "name": f"{name or flow_id} Root Flow",
            "mode": "lifecycle",
            "cartridge_id": flow_id,
            "protocol": {"id": "CF-FARP", "version": "0.4"},
            "start": "start",
            "states": {
                "start": {"type": "terminal", "title": "开始", "action": "start", "next": "welcome"},
                "welcome": {
                    "type": "process",
                    "kind": "ui",
                    "executor": "deterministic",
                    "effect": "writes_store",
                    "display": {"suffix": "展示", "label": "展示节点"},
                    "title": "展示节点",
                    "action": "show_ui",
                    "params": {
                        "node_category": "ui",
                        "preset": "welcome",
                        "preset_config": {"path": "assets/welcome.html", "format": "html", "output_name": "welcome_ui"},
                        "description": "展示卡带欢迎页。",
                        "output": "welcome_ui",
                    },
                    "scope": "sub_flow",
                    "entry_kind": "sub_flow",
                    "template_id": "welcome",
                    "locked": False,
                    "next": "complete",
                },
                "complete": {"type": "terminal", "title": "完成"},
            },
        }

    def _write_json(self, path: Path, data: dict):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
