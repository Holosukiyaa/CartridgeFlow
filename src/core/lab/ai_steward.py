import json
import re


SYSTEM_PROMPT = """你是 CartridgeFlowLite 开发台的 AI 管家。你的职责是降低开发者理解和操作专业 Flow 的门槛。

你只有两种责任模式：
- guided（引导模式）：带着用户完成。默认只读，解释当前选区、指出下一步的位置、预期结果和完成标准。没有明确修改意图时不得生成变更。
- delegated（委托模式）：用户把目标和选区范围交给你。先复述目标、范围和完成标准，再给出可审计的结构化操作建议。不得扩大选区，不得直接写文件。

回答规则：
1. 优先使用业务大白话，只有确实需要时才解释工程字段。
2. 用户用指针选择一个对象时，说明它是什么、从哪里来、去哪里、当前状态和修改影响。
3. 用户框选一段流程时，说明整段链路、关键数据和明显缺口；委托模式下选区也是授权边界。
4. 删除、覆盖、公开契约、权限、网络、凭据、付费模型、外部服务和不可重放副作用必须要求确认。
5. 不要声称已经修改、校验或运行任何内容。本接口只生成说明与结构化建议。
6. 只输出 JSON，不要输出 Markdown 代码围栏或 JSON 之外的文字。

输出结构：
{
  "understanding": "对用户目标的简短复述",
  "answer": "对当前问题或选区的直接回答",
  "operations": [{"op": "建议动作", "target": "稳定工程引用", "description": "大白话说明"}],
  "validation": {"checks": ["建议验证项"]},
  "risk": "none|low|medium|high",
  "confirmation_required": false,
  "next_step": "唯一且明确的下一步"
}

guided 模式通常 operations 为空。delegated 模式可以给出建议，但仍由确定性代码和用户确认决定是否应用。"""


def build_messages(message: str, mode: str, view: str, revision: str, selection: dict, graph: dict) -> list[dict]:
    selected_ids = set(selection.get("node_ids") or [])
    compact_nodes = []
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        compact_nodes.append({
            "id": node.get("id"),
            "title": node.get("display_name") or node.get("title"),
            "type": node.get("type"),
            "kind": node.get("kind"),
            "action": node.get("action"),
            "executor": node.get("executor"),
            "effect": node.get("effect"),
            "input_binding": node.get("input_binding") if node.get("id") in selected_ids else None,
            "output": node.get("output") if node.get("id") in selected_ids else None,
            "selected": node.get("id") in selected_ids,
        })
    payload = {
        "mode": mode,
        "view": view,
        "revision": revision,
        "user_message": message,
        "selection": selection,
        "current_graph": {
            "nodes": compact_nodes,
            "edges": graph.get("edges") or [],
        },
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def parse_response(content: str, *, mode: str, revision: str, selection: dict) -> dict:
    text = str(content or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("AI 管家返回内容不是 JSON 对象")
    operations = []
    for item in data.get("operations") or []:
        if not isinstance(item, dict):
            continue
        operations.append({
            "op": str(item.get("op") or "建议调整")[:80],
            "target": str(item.get("target") or "")[:240],
            "description": str(item.get("description") or "")[:500],
        })
    risk = str(data.get("risk") or "none").lower()
    if risk not in {"none", "low", "medium", "high"}:
        risk = "medium"
    checks = (data.get("validation") or {}).get("checks") if isinstance(data.get("validation"), dict) else []
    return {
        "mode": mode,
        "understanding": str(data.get("understanding") or "")[:1000],
        "answer": str(data.get("answer") or "我已经读取当前工作台上下文。")[:6000],
        "selection_revision": revision,
        "scope": selection,
        "operations": operations,
        "validation": {"checks": [str(item)[:300] for item in (checks or []) if str(item).strip()][:12]},
        "risk": risk,
        "confirmation_required": bool(data.get("confirmation_required")) or risk in {"medium", "high"},
        "next_step": str(data.get("next_step") or "")[:1000],
    }
