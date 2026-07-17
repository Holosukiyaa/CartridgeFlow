import json
import re

SYSTEM_PROMPT = """你是 CartridgeFlow 的「管家」，一位帮助开发者把想法变成 Flow 链路图的产品级 AI 助手。

你的目标不是机械套模板，而是像有经验的流程架构师一样，直接、简洁地帮用户改图或设计图。用户表达明确时不要反复追问。

你拥有内置 Flow skills，但不要把 skill 名称生硬展示给用户：
1. 链路管理：新增/删除/插入/重命名节点，新增/删除/重命名分支，设计循环、汇聚、多输入、多分支和回流结构，整理布局。
2. 节点使用指导：解释六类节点的用途、边界、配置方式、上下游绑定方式。
3. 意图拆解：把自然语言目标拆成输入、处理、传递、存放、控制、自定义节点，并生成 Mermaid 草图和可应用 nodes/edges。

可用节点类型：
- input：输入节点，获取信息或外部上下文。
- ui：UI 节点，展示欢迎页、结果页、HTML/Markdown 预览或交互界面；不要把 UI 展示塞进 store 节点。
- process：处理节点，分析、总结、生成、修改、转换；这是 AI 节点，默认只能使用模型自身能力，不能直接挂外部工具。
- tool：工具节点，调用文件、网络、MCP 或外部系统；必须放在某个 process 节点之后，用来完成 process 节点提出的工具任务。
- transfer：传递节点，搬运、映射、合并、拆分、分发信息。
- store：存放节点，保存上下文、产物、缓存、草稿、记录。
- control：控制节点，人工确认、条件判断、风险检查、测试判定、回流控制。
- custom：自定义节点，标准节点表达不了时使用。

可用 preset：
- input：user_form, read_file, scan_project, import_log
- ui：welcome, html_view, markdown_view
- process：analyze, generate, modify, convert, summarize
- tool：filesystem_read, filesystem_write, filesystem_list, mcp_call
- transfer：pass, map, merge, split
- store：context, artifact, cache, draft
- control：confirm, condition, test_check, risk_check
- custom：blank

图结构能力：
- 可以生成单节点草稿。
- 可以生成线性流程。
- 可以生成单节点多分支。
- 可以生成多个节点汇聚到一个节点。
- 可以生成循环/回流边，例如测试失败回到分析节点。
- edges.from / edges.to 可以引用新建节点 id，也可以引用 current_graph 中已有节点 id。
- 不要为了满足线性结构而强行添加不必要节点。
- 需要外部工具能力时，不要把 tools 写入 process 节点；必须在 process 节点后面新增 tool 节点。
- tool 节点不能放在 process 节点前面；它只消费上游 process 节点给出的任务或数据。
- 需要欢迎界面、结果界面或 HTML/Markdown 展示时，使用 ui 节点；store 节点只保存数据，不负责展示。

生成前自检规则：
- flow_draft 必须是一个连通流程，不能生成多组互不相连的散链。
- 如果有多条并行分支，必须有共同入口或共同汇聚点。
- 如果有循环，循环必须从 control 节点或明确的检查节点回到上游处理节点。
- Mermaid 草图和 nodes/edges 必须表达同一张图。
- 输出前在 validation 字段说明自检是否通过，以及修复了什么。

删除/清空规则：
- 用户说“清空所有节点”“删掉全部”“删除全部”“把子节点全部删掉”时，返回 graph_ops，删除 current_graph 中 locked=false 的所有节点，只保留 locked=true 的开始/完成根节点。
- 用户说“删除子节点”时，如果上下文没有其它更具体限定，也按删除所有非锁定节点处理。
- 用户说“删除刚才应用的节点”时，如果前端已有撤销按钮，提示用户点撤销；否则返回 clarify。
- 删除操作不要生成 Mermaid，不要生成新节点。

回答风格：
- 简短、直接，不要废话。
- 能执行就给确认卡；不能确定才追问。
- 如果只是寒暄，最多一句话。
- 如果用户只说“创建一个新节点”，不要拒绝；给一个最小可确认草稿，默认 custom/blank，标题叫“新节点”。
- 如果用户目标不清楚，只问 1 个关键问题。
- 如果用户已经说清楚“生成/总结/整理某种内容，并写入某个文件路径”，不要追问 Flow 的输入、主步骤和最终结果；直接基于当前图追加 process 节点和后置 tool 节点。输入不明确时使用当前图中最近的上游输出 key。

输出必须是合法 JSON，不要输出 markdown，不要输出 JSON 之外的文字。

普通回复或追问：
{
  "type": "clarify",
  "message": "自然语言回复",
  "thinking_steps": ["我先判断用户意图", "我发现还缺少关键信息"]
}

节点说明：
{
  "type": "node_guidance",
  "message": "简洁说明",
  "thinking_steps": ["识别用户在询问节点用法", "用当前工具语境解释"]
}

图编辑操作：
{
  "type": "graph_ops",
  "summary": "清空业务节点",
  "understanding": "删除所有非锁定节点，仅保留开始和完成。",
  "thinking_steps": ["识别为删除操作", "选择所有非锁定节点"],
  "operations": [
    {"op": "delete_nodes", "target": "unlocked"}
  ]
}

可应用图方案：
{
  "type": "flow_draft",
  "summary": "简短方案名，不要叫通用任务 Flow",
  "understanding": "我理解你的目标是：...",
  "thinking_steps": ["识别输入来源", "拆解处理步骤", "设计分支/回流", "自检连通性"],
  "validation": {"ok": true, "issues": [], "repairs": []},
  "mermaid": "flowchart LR\n  a[节点] --> b[节点]",
  "nodes": [
    {
      "id": "稳定英文id",
      "title": "节点标题",
      "category": "input|ui|process|tool|transfer|store|control|custom",
      "preset": "上述可用 preset 之一",
      "description": "这个节点做什么",
      "input": "从上游 context.store 读取的 key，多个用英文逗号分隔，留空表示不需要上游数据",
      "output": "把结果写入 context.store 的 key，下游节点可用此 key 读取，留空表示本节点不产出数据",
      "preset_config": {"key": "value"}
    }
  ],
  "edges": [
    {"from": "节点id或已有节点id", "to": "节点id或已有节点id", "label": "可选分支标签"}
  ]
}

节点 IO 说明（必须遵守）：
- input/output 是运行时数据通道，不是给用户看的描述字段。
- output 必须是英文 key，例如 "user_request", "script_draft", "project_map"。
- 下游节点的 input 必须引用上游节点的 output key，才能读到真实数据。
- 不同节点的 output 不能重名，除非是有意覆盖。
- store 节点的 output 通常写为 "context.xxx"，表示持久化到运行上下文。
- transfer 节点负责搬运/合并/映射，input 是来源 key，output 是目标 key。
- process 节点如需外部能力，应输出一个 tool_request 或明确任务 key；后续 tool 节点读取该 key。
- tool 节点专门执行外部工具，input 通常引用上游 process 的 output，output 写入工具结果 key。
- 示例：
  输入节点 output: "user_request"
  处理节点 input: "user_request", output: "analysis_result"
  工具节点 input: "analysis_result", output: "file_write_result"
  传递节点 input: "file_write_result", output: "context.file_result"
  下一处理节点 input: "context.file_result", output: "final_plan"
"""

SYSTEM_PROMPT += """

MCP 工具库规则：
- 当前卡带可能带有 available_mcp_tools；这些工具来自设计台的 MCP 管理库，并会随卡带一起打包。
- 需要 filesystem/MCP 能力时，优先选择 available_mcp_tools 里的工具，不要凭空编造 server/tool。
- 使用工具库时，mcp_tool_id 必须选择 available_mcp_tools 中真实存在的 id；如果没有匹配工具，再退回普通 filesystem preset。
- 生成 tool 节点时，必须放在 process 节点之后，并把 preset 设为 mcp_call 或对应 filesystem preset。
- 如果使用工具库里的工具，请在该 tool 节点 preset_config 写入 {"mcp_tool_id": "工具 id", "server": "...", "tool": "..."}。
- process 节点只负责 AI 判断和生成工具任务；真正的 filesystem/MCP 调用必须由后置 tool 节点完成。
- 用户说“生成 Markdown 总结，然后写入 xxx.md / xxx.txt / xxx.json”时，这是明确的可执行改图意图：必须返回 flow_draft，不要返回 clarify。
- 这种追加型请求默认不是重画整张 Flow，而是在当前选中节点或当前链路后方追加 “process -> tool” 小链路。
- 常见匹配：
  - 写文件：优先找 id 为 filesystem_write，或 server=filesystem 且 tool=write_file 的工具。
  - 读文件：优先找 id 为 filesystem_read，或 server=filesystem 且 tool=read_file 的工具。
  - 列目录：优先找 id 为 filesystem_list，或 server=filesystem 且 tool=list_dir 的工具。
- 写文件示例：如果用户要求“AI 生成内容并写入 test_output/result.md”，应生成 process 节点输出 "analysis_result"，再生成 tool 节点：
  {
    "id": "write_result_file",
    "title": "写入结果文件",
    "category": "tool",
    "preset": "mcp_call",
    "description": "调用 MCP filesystem 写入文件",
    "input": "analysis_result",
    "output": "file_write_result",
    "preset_config": {
      "mcp_tool_id": "filesystem_write",
      "server": "filesystem",
      "tool": "write_file",
      "path": "test_output/result.md",
      "source": "analysis_result",
      "output_name": "file_write_result"
    }
  }
"""

SYSTEM_PROMPT += """

CF-FARP@0.3 protocol rules:
- Every business node in a draft must be represented as type="process".
- Use kind to express the real processing role: input, ui, decision, retrieval, transfer, mcp_read, mcp_execute, remote_call, gate, human_gate, delivery.
- Do not describe tool as a separate protocol node type. A tool call is a process node with kind=mcp_read or kind=mcp_execute.
- decision nodes must not directly execute tools; LLM decision nodes must use output_contract="decision_envelope.v1" and include decision_contract.
- If a decision may need more user input, its decision_contract must include allowed_statuses with "needs_user_input" and interaction.store_key/input_schema/resume_policy.
- If a decision drives tools, place tool_plan.v1 inside decision_envelope.v1 payload and route it through a gate before mcp_execute.
- mcp_read must use executor="mcp", effect="read_only", mcp_binding.mode="read_only", and allowed_tools.
- mcp_execute must use executor="mcp", a side-effect effect, tool_binding, allowed_tools, failure_policy, permission, and audit_log=true.
- The user-facing label is the kind suffix plus "节点", for example AI决策节点, MCP读取节点, MCP执行节点, 传递节点. The protocol type remains type="process".
"""

ALLOWED_CATEGORIES = {"input", "ui", "process", "tool", "transfer", "store", "control", "custom"}
ALLOWED_PRESETS = {
    "input": {"user_form", "read_file", "scan_project", "import_log"},
    "ui": {"welcome", "html_view", "markdown_view"},
    "process": {"analyze", "generate", "modify", "convert", "summarize"},
    "tool": {"filesystem_read", "filesystem_write", "filesystem_list", "mcp_call"},
    "transfer": {"pass", "map", "merge", "split"},
    "store": {"context", "artifact", "cache", "draft"},
    "control": {"confirm", "condition", "test_check", "risk_check"},
    "custom": {"blank"},
}


def build_messages(message: str, graph: dict, files: dict) -> list[dict]:
    compact_graph = {
        "nodes": [
            {
                "id": node.get("id"),
                "title": node.get("title"),
                "type": node.get("type"),
                "action": node.get("action"),
                "kind": node.get("kind") or (node.get("data") or {}).get("kind"),
                "executor": node.get("executor") or (node.get("data") or {}).get("executor"),
                "effect": node.get("effect") or (node.get("data") or {}).get("effect"),
                "category": (node.get("params") or {}).get("node_category"),
                "preset": (node.get("params") or {}).get("preset"),
                "locked": bool(node.get("locked")),
            }
            for node in (graph.get("nodes") or [])
        ],
        "edges": graph.get("edges") or [],
    }
    user_prompt = {
        "user_message": message,
        "current_graph": compact_graph,
        "available_mcp_tools": _safe_json(files.get("manifest", "{}")).get("mcp_tools", []),
        "root_flow_preview": _safe_json(files.get("root_flow", "{}")),
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
    ]


def build_intent_fallback(message: str, graph: dict | None = None, files: dict | None = None) -> dict | None:
    """Deterministic safety net for common direct intents that should not be clarified."""
    text = (message or "").strip()
    if not text:
        return None
    lowered = text.lower()
    has_generate_intent = any(keyword in lowered for keyword in [
        "生成", "总结", "整理", "撰写", "写一段", "markdown", "md", "generate", "summarize", "summary",
    ])
    has_write_intent = any(keyword in lowered for keyword in [
        "写", "存", "保存", "输出", "导出", "write", "save", "output", "export",
    ])
    path_match = re.search(r"([\w./\\-]+\.(?:md|markdown|txt|json|csv|log|html?|xml|yaml|yml))", text, flags=re.IGNORECASE)
    if not (has_write_intent and path_match and (has_generate_intent or path_match.group(1).lower().endswith((".md", ".markdown", ".txt", ".json")))):
        return None

    output_path = path_match.group(1).replace("\\", "/")
    ext = output_path.rsplit(".", 1)[-1].lower()
    output_format = "Markdown" if ext in {"md", "markdown"} else ext.upper()
    input_key = _guess_latest_output_key(graph or {}, files or {})
    process_output = "markdown_summary" if ext in {"md", "markdown"} else "generated_content"
    tool_output = "file_write_result"
    mermaid = (
        "flowchart LR\n"
        f"  generate_content[生成{output_format}内容] --> write_file[写入文件]"
    )
    return {
        "type": "flow_draft",
        "summary": f"生成{output_format}内容并写入文件",
        "understanding": f"我会在当前链路后面追加一个 AI 处理节点生成{output_format}内容，再挂一个 MCP filesystem 写入节点，把结果写入 `{output_path}`。",
        "thinking_steps": ["识别到生成内容请求", "识别到明确文件写入路径", "按 AI 处理节点后置 MCP 工具节点的规则生成小链路"],
        "validation": {"ok": True, "issues": [], "repairs": ["输入未明确时自动使用当前图最近的上游输出。"]},
        "mermaid": mermaid,
        "nodes": [
            {
                "id": "generate_content_for_file",
                "title": f"生成{output_format}内容",
                "category": "process",
                "preset": "generate",
                "type": "process",
                "action": "llm_prompt",
                "kind": "decision",
                "executor": "llm",
                "effect": "none",
                "description": f"根据上游数据生成要写入 {output_path} 的{output_format}内容。",
                "input": input_key,
                "output": process_output,
                "preset_config": {
                    "target": f"生成一段{output_format}总结内容，用于写入 {output_path}",
                    "format": output_format,
                    "output_name": process_output,
                },
            },
            {
                "id": "write_generated_file",
                "title": "写入文件",
                "category": "tool",
                "preset": "mcp_call",
                "type": "process",
                "action": "tool_call",
                "kind": "mcp_execute",
                "executor": "mcp",
                "effect": "writes_files",
                "tool_binding": "static_params",
                "allowed_tools": ["filesystem_write"],
                "failure_policy": "fail_closed",
                "permission": "write_workspace_files",
                "audit_log": True,
                "description": f"调用 MCP filesystem 写入 {output_path}。",
                "input": process_output,
                "output": tool_output,
                "preset_config": {
                    "mcp_tool_id": "filesystem_write",
                    "server": "filesystem",
                    "tool": "write_file",
                    "path": output_path,
                    "source": process_output,
                    "output_name": tool_output,
                },
            },
        ],
        "edges": [{"from": "generate_content_for_file", "to": "write_generated_file"}],
    }


def _guess_latest_output_key(graph: dict, files: dict) -> str:
    root_flow = _safe_json((files or {}).get("root_flow", "{}"))
    states = root_flow.get("states") if isinstance(root_flow, dict) else {}
    candidates: list[tuple[float, str]] = []
    if isinstance(states, dict):
        for state in states.values():
            if not isinstance(state, dict):
                continue
            params = state.get("params") or {}
            preset_config = params.get("preset_config") or {}
            key = params.get("output") or preset_config.get("output_name") or preset_config.get("to") or preset_config.get("key")
            if not isinstance(key, str) or not key.strip():
                continue
            category = params.get("node_category")
            if category == "tool":
                continue
            layout = state.get("layout") or {}
            x = layout.get("x") if isinstance(layout, dict) else 0
            try:
                score = float(x or 0)
            except (TypeError, ValueError):
                score = 0
            candidates.append((score, key.strip()))
    if candidates:
        return sorted(candidates, key=lambda item: item[0])[-1][1]
    for node in (graph.get("nodes") or []):
        params = node.get("params") or {}
        key = params.get("output") or (params.get("preset_config") or {}).get("output_name")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return "上游结果"


def parse_response(content: str) -> dict:
    data = _loads_json(content)
    result_type = data.get("type")
    thinking_steps = _clean_steps(data.get("thinking_steps"))
    if result_type in {"clarify", "node_guidance"}:
        return {
            "type": result_type,
            "message": str(data.get("message") or "我需要更多信息才能继续。"),
            "thinking_steps": thinking_steps,
        }
    if result_type == "graph_ops":
        operations = []
        for item in data.get("operations") or []:
            if not isinstance(item, dict):
                continue
            op = str(item.get("op") or "")
            if op != "delete_nodes":
                continue
            operation = {"op": op}
            if item.get("target") in {"unlocked", "all_unlocked"}:
                operation["target"] = "unlocked"
            node_ids = item.get("node_ids") or []
            if isinstance(node_ids, list):
                operation["node_ids"] = [_slug(str(node_id)) for node_id in node_ids if str(node_id).strip()]
            if operation.get("target") or operation.get("node_ids"):
                operations.append(operation)
        if operations:
            return {
                "type": "graph_ops",
                "summary": str(data.get("summary") or "编辑链路图"),
                "understanding": str(data.get("understanding") or "我会按你的要求修改当前链路图。"),
                "thinking_steps": thinking_steps,
                "operations": operations,
            }
        return {"type": "clarify", "message": "要删除哪些节点？", "thinking_steps": thinking_steps}
    if result_type != "flow_draft":
        return {
            "type": "clarify",
            "message": "我需要再确认一下：你希望这个 Flow 的输入、主要处理步骤和最终结果分别是什么？",
            "thinking_steps": thinking_steps or ["我没有拿到可靠的图方案", "需要补充关键信息"],
        }

    nodes = []
    seen = set()
    for item in data.get("nodes") or []:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        if category not in ALLOWED_CATEGORIES:
            category = "custom"
        preset = str(item.get("preset") or "").strip()
        if preset not in ALLOWED_PRESETS[category]:
            preset = "blank" if category == "custom" else next(iter(ALLOWED_PRESETS[category]))
        node_id = _slug(str(item.get("id") or item.get("title") or category))
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        preset_config = item.get("preset_config") or {}
        if not isinstance(preset_config, dict):
            preset_config = {}
        node_payload = {
            "id": node_id,
            "title": str(item.get("title") or node_id),
            "category": category,
            "preset": preset,
            "description": str(item.get("description") or ""),
            "input": str(item.get("input") or ""),
            "output": str(item.get("output") or ""),
            "preset_config": {str(k): str(v) for k, v in preset_config.items()},
        }
        for field in [
            "type",
            "action",
            "kind",
            "executor",
            "effect",
            "display",
            "output_contract",
            "tool_binding",
            "allowed_tools",
            "mcp_binding",
            "failure_policy",
            "permission",
            "audit_log",
            "input_kind",
            "source",
            "input_schema",
            "primary_output",
        ]:
            if field in item:
                node_payload[field] = item.get(field)
        nodes.append(node_payload)

    edges = []
    for item in data.get("edges") or []:
        if not isinstance(item, dict):
            continue
        source = _slug(str(item.get("from") or item.get("source") or ""))
        target = _slug(str(item.get("to") or item.get("target") or ""))
        if source and target and source != target:
            edge = {"from": source, "to": target}
            if item.get("label"):
                edge["label"] = str(item.get("label"))
            edges.append(edge)

    if not nodes and not edges:
        return {
            "type": "clarify",
            "message": "我还不能形成可靠的链路图。请补充你想新增或调整的节点、连接关系或最终目标。",
            "thinking_steps": thinking_steps or ["缺少可应用的节点或链路", "需要用户补充目标"],
        }

    validation = _validate_and_repair(nodes, edges)
    edges = validation.pop("edges")

    mermaid = str(data.get("mermaid") or "").strip()
    if not mermaid.startswith("flowchart LR") or validation.get("repairs"):
        mermaid = _make_mermaid(nodes, edges)

    summary = str(data.get("summary") or "Flow 方案").strip()
    if "通用任务" in summary:
        summary = "Flow 方案"

    return {
        "type": "flow_draft",
        "summary": summary,
        "understanding": str(data.get("understanding") or "我已经根据你的描述拆解出一个链路方案。"),
        "thinking_steps": thinking_steps,
        "validation": validation,
        "mermaid": mermaid,
        "nodes": nodes,
        "edges": edges,
    }


def _validate_and_repair(nodes: list[dict], edges: list[dict]) -> dict:
    if len(nodes) <= 1:
        return {"ok": True, "issues": [], "repairs": [], "edges": edges}

    node_ids = [node["id"] for node in nodes]
    node_set = set(node_ids)
    valid_edges = []
    seen_edges = set()
    issues = []
    repairs = []

    for edge in edges:
        source = edge.get("from")
        target = edge.get("to")
        if not source or not target or source == target:
            issues.append("移除了无效边")
            continue
        key = (source, target, edge.get("label") or "")
        if key in seen_edges:
            continue
        seen_edges.add(key)
        valid_edges.append(edge)

    internal_edges = [edge for edge in valid_edges if edge["from"] in node_set and edge["to"] in node_set]
    if not internal_edges:
        for source, target in zip(node_ids, node_ids[1:]):
            valid_edges.append({"from": source, "to": target})
        repairs.append("补齐节点之间的主流程连接")
        return {"ok": False, "issues": ["草稿没有形成内部流程"], "repairs": repairs, "edges": valid_edges}

    parent = {node_id: node_id for node_id in node_ids}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str):
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for edge in internal_edges:
        union(edge["from"], edge["to"])

    components: list[list[str]] = []
    component_map: dict[str, list[str]] = {}
    for node_id in node_ids:
        component_map.setdefault(find(node_id), []).append(node_id)
    components = list(component_map.values())

    if len(components) > 1:
        issues.append(f"草稿包含 {len(components)} 组未连通流程")
        for previous, current in zip(components, components[1:]):
            valid_edges.append({"from": previous[-1], "to": current[0], "label": "继续"})
        repairs.append("已把散链补成一个连通流程")

    pruned_edges = []
    for edge in valid_edges:
        if edge["from"] in node_set and edge["to"] in node_set and _has_alternative_path(edge["from"], edge["to"], valid_edges, edge):
            repairs.append(f"移除跨层捷径边：{edge['from']} -> {edge['to']}")
            continue
        pruned_edges.append(edge)
    valid_edges = pruned_edges

    metrics = _layout_metrics(node_ids, valid_edges)
    if metrics["max_edge_length"] > 560:
        issues.append(f"存在过长线段：{metrics['max_edge_length']}px")

    return {"ok": not issues, "issues": issues, "repairs": repairs, "metrics": metrics, "edges": valid_edges}


def _has_alternative_path(source: str, target: str, edges: list[dict], skipped: dict) -> bool:
    next_map: dict[str, list[str]] = {}
    for edge in edges:
        if edge is skipped:
            continue
        next_map.setdefault(edge["from"], []).append(edge["to"])
    queue = [source]
    visited = {source}
    while queue:
        current = queue.pop(0)
        for next_id in next_map.get(current, []):
            if next_id == target:
                return True
            if next_id not in visited:
                visited.add(next_id)
                queue.append(next_id)
    return False


def _layout_metrics(node_ids: list[str], edges: list[dict]) -> dict:
    rank = {node_ids[0]: 0} if node_ids else {}
    queue = [node_ids[0]] if node_ids else []
    outgoing: dict[str, list[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge["from"], []).append(edge["to"])
    while queue:
        source = queue.pop(0)
        for target in outgoing.get(source, []):
            if target in rank:
                continue
            rank[target] = min(rank[source] + 1, len(node_ids) - 1)
            queue.append(target)
    for node_id in node_ids:
        rank.setdefault(node_id, 0)
    lengths = []
    for edge in edges:
        if edge["from"] in rank and edge["to"] in rank:
            lengths.append(abs(rank[edge["to"]] - rank[edge["from"]]) * 280)
    return {"max_edge_length": max(lengths) if lengths else 0, "edge_count": len(edges), "node_count": len(node_ids)}


def _loads_json(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _make_mermaid(nodes: list[dict], edges: list[dict]) -> str:
    labels = {node["id"]: node["title"] for node in nodes}
    lines = ["flowchart LR"]
    for node in nodes:
        lines.append(f"  {node['id']}[{node['title']}]")
    for edge in edges:
        source = edge["from"]
        target = edge["to"]
        if source not in labels:
            lines.append(f"  {source}[{source}]")
            labels[source] = source
        if target not in labels:
            lines.append(f"  {target}[{target}]")
            labels[target] = target
        label = f"|{edge['label']}|" if edge.get("label") else ""
        lines.append(f"  {source} -->{label} {target}")
    return "\n".join(lines)


def _clean_steps(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()][:6]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_").lower()
    return slug[:64]


def _safe_json(content: str) -> dict:
    try:
        data = json.loads(content or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}
