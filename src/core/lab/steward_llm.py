"""FlowSteward LLM 模式的 prompt 构建与响应解析。

设计原则：
- LLM 只生成 summary/steps/patches，不直接写文件。
- patches 必须是受控操作：add_state / append_input / append_permission。
- 无效或不安全的 patch 会被 apply 阶段过滤。
- 如果 LLM 调用失败，自动 fallback 到规则模式。
"""

import json

SYSTEM_PROMPT = """你是 CartridgeFlow 的 Flow 管家助手。你的职责是理解开发者意图，并给出 Flow 修改建议。

CartridgeFlow 的卡带结构：
- manifest.json：卡带身份、runtime、inputs、outputs、permissions、environment、dependencies。
- root.flow.json：生命周期状态机，包含 states，每个 state 有 type/title/action/next。
- assets/welcome.md：卡带欢迎页说明。

你可以建议的受控操作（patch）：
1. add_state：在 root_flow.states 中新增节点，可选让选中节点的 next 指向新节点。
2. append_input：在 manifest.inputs 中追加输入参数声明。
3. append_permission：在 manifest.permissions 中追加权限声明。

你不能建议：
- 直接修改文件内容。
- 删除已有节点或参数。
- 执行 shell 或安装依赖。
- 任何不在受控操作列表里的操作。

输出格式：必须是合法 JSON，包含以下字段：
{
  "summary": "对开发者意图的简短理解和建议方向",
  "steps": ["步骤1", "步骤2", ...],
  "patches": [
    {
      "target": "root_flow.states 或 manifest.inputs 或 manifest.permissions",
      "operation": "add_state | append_input | append_permission",
      "state_template": {"type": "ui", "title": "...", "action": "...", "next": "run"},
      "input_template": {"id": "...", "label": "...", "type": "text", "required": false},
      "permission_template": {"id": "...", "level": "safe", "reason": "..."}
    }
  ]
}

注意：
- 只返回 JSON，不要包含任何其他文字。
- patches 可以为空数组，表示当前意图还不足以生成明确改动。
- 每个 patch 只需要包含对应 operation 的 template 字段，不需要全部包含。"""


def build_user_prompt(intent: str, files: dict, selected_node: dict | None) -> str:
    """构建发送给 LLM 的用户消息，包含 node capability 上下文。"""
    manifest = _safe_json(files.get("manifest", "{}"))
    root_flow = _safe_json(files.get("root_flow", "{}"))
    welcome = files.get("welcome", "")

    parts = [f"开发者意图：{intent or '(未提供)'}", ""]

    # 选中节点上下文（包含 capability）
    if selected_node:
        node_info = {
            "id": selected_node.get("id"),
            "title": selected_node.get("title"),
            "type": selected_node.get("type"),
            "action": selected_node.get("action"),
            "next": selected_node.get("next"),
            "agent": selected_node.get("agent"),
            "tools": selected_node.get("tools"),
            "params": selected_node.get("params"),
            "model_role": selected_node.get("model_role"),
        }
        parts.append(f"当前选中节点：{json.dumps(node_info, ensure_ascii=False)}")
    else:
        parts.append("当前未选中节点。")
    parts.append("")

    # 节点 capability 概览
    states = root_flow.get("states") or {}
    if states:
        capability_lines = []
        for sid, s in states.items():
            caps = []
            if s.get("agent"): caps.append(f"agent={s['agent']}")
            if s.get("tools"): caps.append(f"tools={len(s['tools'])}")
            if s.get("params"): caps.append(f"params={list(s['params'].keys())}")
            if s.get("model_role"): caps.append(f"model={s['model_role']}")
            if caps:
                capability_lines.append(f"  {sid}: {' · '.join(caps)}")
        if capability_lines:
            parts.append("节点能力概览：")
            parts.extend(capability_lines)
            parts.append("")

    parts.append(f"当前 manifest.json：\n{json.dumps(manifest, ensure_ascii=False, indent=2)}")
    parts.append("")
    parts.append(f"当前 root.flow.json：\n{json.dumps(root_flow, ensure_ascii=False, indent=2)}")
    parts.append("")

    if welcome:
        parts.append(f"当前 welcome.md（前 500 字）：\n{welcome[:500]}")
    else:
        parts.append("当前 welcome.md：(空)")
    parts.append("")

    parts.append("请根据开发者意图，给出 summary、steps 和 patches。只返回 JSON。")
    return "\n".join(parts)


def parse_llm_response(content: str) -> dict:
    """解析 LLM 返回的 JSON，容错处理。"""
    if not content:
        return _empty_response()

    text = content.strip()
    # 去掉可能的 markdown 代码块包裹
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines) - 1
        for i in range(1, len(lines)):
            if lines[i].strip().startswith("```"):
                end = i
                break
        text = "\n".join(lines[start:end])
    # 去掉前后非 JSON 文本
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _empty_response()

    if not isinstance(data, dict):
        return _empty_response()

    summary = str(data.get("summary", "")).strip()
    steps = data.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    patches = data.get("patches") or []
    if not isinstance(patches, list):
        patches = []

    # 只保留受控操作
    allowed_ops = {"add_state", "append_input", "append_permission"}
    clean_patches = []
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        operation = patch.get("operation")
        if operation not in allowed_ops:
            continue
        clean_patches.append(patch)

    return {
        "summary": summary,
        "steps": [str(step) for step in steps],
        "patches": clean_patches,
    }


def _empty_response() -> dict:
    return {"summary": "", "steps": [], "patches": []}


def _safe_json(content: str) -> dict:
    try:
        return json.loads(content or "{}")
    except json.JSONDecodeError:
        return {}
