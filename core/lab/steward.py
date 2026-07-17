import json

from .steward_llm import build_user_prompt, parse_llm_response, SYSTEM_PROMPT


class FlowSteward:
    def suggest(self, intent: str, files: dict, selected_node: dict | None = None) -> dict:
        """规则模拟模式：根据关键词生成受控 patch 建议。"""
        manifest = self._load_json(files.get("manifest", "{}"))
        root_flow = self._load_json(files.get("root_flow", "{}"))
        states = root_flow.get("states") or {}
        selected_id = selected_node.get("id") if selected_node else None
        steps = []
        patches = []
        lower_intent = (intent or "").lower()
        if selected_id and selected_id in states:
            steps.append(f"优先分析当前选中节点：{selected_id}")
            patches.append({"target": f"root_flow.states.{selected_id}", "operation": "inspect", "reason": "开发者当前正在查看这个节点"})
        if any(word in lower_intent for word in ["节点", "node", "阶段", "添加", "新增"]):
            steps.append("建议先新增一个 root_flow state，再把上游节点 next 指向它")
            patches.append({"target": "root_flow.states", "operation": "add_state", "state_template": self._state_template()})
        if any(word in lower_intent for word in ["参数", "input", "输入"]):
            steps.append("建议在 manifest.inputs 中添加参数声明，并在 input_collect 阶段展示")
            patches.append({"target": "manifest.inputs", "operation": "append_input", "input_template": {"id": "new_input", "label": "新参数", "type": "text", "required": False}})
        if any(word in lower_intent for word in ["权限", "permission"]):
            steps.append("建议在 manifest.permissions 中声明权限，并让 permission 阶段解释风险")
            patches.append({"target": "manifest.permissions", "operation": "append_permission", "permission_template": {"id": "create_artifact", "level": "safe", "reason": "生成 Flow 产物"}})
        if any(word in lower_intent for word in ["依赖", "dependency", "环境", "environment"]):
            steps.append("建议把可检测项放入 environment.requires，把可解释处理项放入 dependencies")
            patches.append({"target": "manifest.environment.dependencies", "operation": "review", "reason": "区分检测和处理"})
        if not steps:
            steps = ["先校验 manifest 和 root_flow", "确认要修改的节点或阶段", "生成小步变更后预览链路图", "开发者确认后再保存文件"]
            patches.append({"target": "lab", "operation": "clarify_intent", "reason": "当前意图还不足以生成明确 Flow 改动"})
        return {
            "status": "simulated",
            "intent": intent,
            "flow_id": manifest.get("id"),
            "selected_node_id": selected_id,
            "summary": "这是 Flow 管家骨架生成的模拟修改计划，未调用真实 LLM，也不会自动写文件。",
            "steps": steps,
            "patches": patches,
            "context": {
                "manifest_id": manifest.get("id"),
                "root_flow_id": root_flow.get("id"),
                "state_count": len(states),
                "selected_node": selected_id,
            },
        }

    async def suggest_with_llm(self, intent: str, files: dict, selected_node: dict | None = None) -> dict:
        """LLM 模式：调用 LLM 生成受控 patch 建议。失败时自动 fallback 到规则模式。"""
        manifest = self._load_json(files.get("manifest", "{}"))
        root_flow = self._load_json(files.get("root_flow", "{}"))
        states = root_flow.get("states") or {}
        selected_id = selected_node.get("id") if selected_node else None

        # 尝试调用 LLM
        llm_result = await self._call_llm(intent, files, selected_node)

        if llm_result is None:
            # LLM 不可用或调用失败，fallback 到规则模式
            fallback = self.suggest(intent, files, selected_node)
            fallback["status"] = "simulated_fallback"
            fallback["summary"] = f"[LLM 不可用，已降级为规则模式] {fallback['summary']}"
            return fallback

        return {
            "status": "llm",
            "intent": intent,
            "flow_id": manifest.get("id"),
            "selected_node_id": selected_id,
            "summary": llm_result.get("summary") or "LLM 生成的修改建议",
            "steps": llm_result.get("steps") or [],
            "patches": llm_result.get("patches") or [],
            "context": {
                "manifest_id": manifest.get("id"),
                "root_flow_id": root_flow.get("id"),
                "state_count": len(states),
                "selected_node": selected_id,
            },
        }

    async def _call_llm(self, intent: str, files: dict, selected_node: dict | None) -> dict | None:
        """调用 LLM，返回解析后的结果；不可用或失败时返回 None。"""
        try:
            from core.llm import ModelConfig, chat
            from core.llm.config_manager import resolve_model
        except Exception:
            return None

        try:
            cfg = resolve_model(role="steward")
        except Exception:
            return None

        if not cfg.api_key:
            return None

        user_prompt = build_user_prompt(intent, files, selected_node)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await chat(
                cfg,
                messages,
                agent_name="flow_steward",
                phase="suggest",
            )
        except Exception:
            return None

        content = response.get("content", "")
        parsed = parse_llm_response(content)

        if not parsed.get("summary") and not parsed.get("patches"):
            return None

        parsed["_meta"] = response.get("meta", {})
        return parsed

    def apply(self, files: dict, patches: list[dict], selected_node: dict | None = None) -> dict:
        manifest = self._load_json(files.get("manifest", "{}"))
        root_flow = self._load_json(files.get("root_flow", "{}"))
        applied = []
        skipped = []
        for patch in patches or []:
            operation = patch.get("operation")
            if operation == "append_input":
                self._append_unique(manifest, "inputs", patch.get("input_template") or {})
                applied.append(operation)
            elif operation == "append_permission":
                self._append_unique(manifest, "permissions", patch.get("permission_template") or {})
                applied.append(operation)
            elif operation == "add_state":
                state_id = self._add_state(root_flow, patch.get("state_template") or self._state_template(), selected_node)
                applied.append(f"add_state:{state_id}")
            else:
                skipped.append({"operation": operation, "reason": "unsupported or read-only operation"})
        return {
            "status": "applied_to_memory",
            "applied": applied,
            "skipped": skipped,
            "files": {
                "manifest": json.dumps(manifest, ensure_ascii=False, indent=2),
                "root_flow": json.dumps(root_flow, ensure_ascii=False, indent=2),
                "welcome": files.get("welcome", ""),
            },
            "summary": "受控 patch 已应用到编辑器内容，尚未保存到磁盘。",
        }

    def _load_json(self, content: str) -> dict:
        try:
            return json.loads(content or "{}")
        except json.JSONDecodeError:
            return {}

    def _state_template(self) -> dict:
        return {"type": "ui", "title": "新节点", "action": "custom_action", "next": "run"}

    def _append_unique(self, document: dict, key: str, item: dict):
        items = document.setdefault(key, [])
        item_id = item.get("id")
        if item_id and any(existing.get("id") == item_id for existing in items if isinstance(existing, dict)):
            item = {**item, "id": self._next_id(item_id, {existing.get("id") for existing in items if isinstance(existing, dict)})}
        items.append(item)

    def _add_state(self, root_flow: dict, state_template: dict, selected_node: dict | None = None) -> str:
        states = root_flow.setdefault("states", {})
        state_id = self._next_id("new_state", set(states.keys()))
        selected_id = selected_node.get("id") if selected_node else None
        previous_next = None
        if selected_id in states:
            previous_next = states[selected_id].get("next")
            states[selected_id]["next"] = state_id
        new_state = {**state_template}
        if previous_next:
            new_state["next"] = previous_next
        states[state_id] = new_state
        return state_id

    def _next_id(self, base: str, existing: set[str]) -> str:
        if base not in existing:
            return base
        index = 2
        while f"{base}_{index}" in existing:
            index += 1
        return f"{base}_{index}"
