"""MCP Tool Slot Skeleton。

声明 MCP 工具槽的元数据结构，让 Root Flow node 的 tools 支持 type="mcp"。
当前只做声明和展示，不执行真实 MCP 工具调用。
"""

# 支持的 tool 类型
TOOL_TYPES = {
    "builtin": "内置工具（如 read_file, write_file）",
    "mcp": "MCP 工具槽（声明但不执行）",
    "agent": "Agent 能力调用（如 ask_mentor）",
}

# MCP 工具槽的标准字段
MCP_SLOT_FIELDS = {
    "id": "工具槽 ID（唯一标识）",
    "type": "必须是 'mcp'",
    "server": "MCP 服务器名称（声明性）",
    "tool": "MCP 工具名称（声明性）",
    "description": "工具描述",
    "params_schema": "参数 JSON Schema（声明性）",
    "enabled": "是否启用（默认 true）",
}


def normalize_tool(tool: dict) -> dict:
    """规范化一个 tool 声明，补全默认字段。"""
    if not isinstance(tool, dict):
        return {}
    normalized = {
        "id": tool.get("id", ""),
        "type": tool.get("type", "builtin"),
        "description": tool.get("description", ""),
        "enabled": tool.get("enabled", True),
    }
    if tool.get("type") == "mcp":
        normalized["server"] = tool.get("server", "")
        normalized["tool"] = tool.get("tool", "")
        normalized["params_schema"] = tool.get("params_schema") or {}
    elif tool.get("type") == "builtin":
        normalized["handler"] = tool.get("handler", tool.get("id", ""))
        normalized["server"] = tool.get("server", "")
        normalized["tool"] = tool.get("tool", "")
        normalized["params"] = tool.get("params") or {}
        normalized["output"] = tool.get("output", "")
        normalized["mcp_tool_id"] = tool.get("mcp_tool_id", "")
    elif tool.get("type") == "agent":
        normalized["agent"] = tool.get("agent", "")
        normalized["action"] = tool.get("action", "")
    return normalized


def normalize_tools(tools: list[dict] | None) -> list[dict]:
    """规范化工具列表。"""
    if not tools:
        return []
    return [normalize_tool(t) for t in tools if isinstance(t, dict)]


def get_mcp_slots(tools: list[dict] | None) -> list[dict]:
    """从工具列表中筛选 MCP 工具槽。"""
    return [t for t in (tools or []) if t.get("type") == "mcp"]


def get_tool_summary(tools: list[dict] | None) -> dict:
    """生成工具摘要，用于 graph 和 inspector 展示。"""
    normalized = normalize_tools(tools)
    return {
        "total": len(normalized),
        "builtin": sum(1 for t in normalized if t.get("type") == "builtin"),
        "mcp": sum(1 for t in normalized if t.get("type") == "mcp"),
        "agent": sum(1 for t in normalized if t.get("type") == "agent"),
        "mcp_slots": [f"{t.get('server', '?')}/{t.get('tool', '?')}" for t in normalized if t.get("type") == "mcp"],
        "builtin_slots": [f"{t.get('server', '?')}/{t.get('tool', '?')}" for t in normalized if t.get("type") == "builtin" and (t.get("server") or t.get("tool"))],
    }
