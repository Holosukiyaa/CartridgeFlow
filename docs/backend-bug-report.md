# CartridgeFlow 后端代码 Bug 深度分析报告

> 生成日期：2026-08-01
> 分析范围：`src/backend/main.py`、`src/core/cartridge/runner.py`、`src/core/lab/node_executor.py`、`src/core/protocol/features.py`、`src/core/runtime/errors.py` 等
> 分析方法：逐行代码审查 + 执行路径分析 + 逻辑缺陷检测

---

## 目录

1. [P0 — 功能正确性](#p0--功能正确性)
2. [P1 — 安全与数据完整性](#p1--安全与数据完整性)
3. [P2 — 逻辑缺陷](#p2--逻辑缺陷)
4. [P3 — 代码质量](#p3--代码质量)
5. [附录：修复建议](#附录修复建议)

---

## P0 — 功能正确性

### Bug B1：`_sync_flow_edges_from_next` 静默丢弃指向不存在节点的边

**文件：** `main.py` 第 465-479 行

```python
def _sync_flow_edges_from_next(root_flow: dict, extra_edges: list[dict] | None = None) -> None:
    states = root_flow.get("states") if isinstance(root_flow.get("states"), dict) else {}
    edges = []
    for source_id, source_state in states.items():
        if not isinstance(source_state, dict):
            continue
        target_id = source_state.get("next")
        if target_id in states:  # ← 只检查 target_id 是否在 states 中
            edges.append({"from": source_id, "to": target_id, "scope": "root"})
    # ...extra_edges 同理，只追加 scope != "root" 的边
    _write_flow_edges(root_flow, edges)
```

**问题：** 当 `target_id` 不在 `states` 字典中时（例如指向不存在的节点 ID、拼写错误、或引用了已删除的节点），该边被**静默丢弃**。没有任何日志或错误提示告知用户某个节点引用了不存在的目标。

**影响：** 用户在编辑器中创建了节点 A 指向节点 B 的连线，但节点 B 被删除后，连线会静默消失。用户重新加载页面时，发现连线不见了，但没有任何错误提示。

**修复：** 记录警告日志，或至少返回报告中包含被丢弃的边。

---

### Bug B2：`_executable_edges` 与 `_is_execution_plan_root_flow` 判定条件不一致

**文件：**
- `main.py` 第 367-374 行（`_is_execution_plan_root_flow`）
- `runner.py` 第 38-52 行（`_executable_edges`）

```python
# main.py: 通过 protocol feature 判断
def _is_execution_plan_root_flow(root_flow: dict) -> bool:
    protocol = root_flow.get("protocol") if isinstance(root_flow.get("protocol"), dict) else {}
    return has_protocol_feature(..., "execution_plan", ROOT)

# runner.py: 通过 execution_plan.schema 字段判断
has_execution_plan = isinstance(root_flow.get("execution_plan"), dict) and \
    root_flow["execution_plan"].get("schema") == "cartridgeflow.execution_plan.v1"
```

**问题：** `main.py` 使用协议 feature 判断，而 `runner.py` 直接检查 `execution_plan.schema` 字段。如果某个 flow 有 `execution_plan` 字段但 schema 不匹配（或没有 schema 字段），`runner.py` 会认为不是 execution plan，而 `main.py` 也会认为不是。但如果某个 flow 声明的协议版本支持 `execution_plan` feature 但尚未设置 `execution_plan` 字段，`main.py` 会认为它是，而 `runner.py` 会认为不是。这可能导致运行时行为不一致。

---

### Bug B3：`_truncate_preview` 截断后超过长度限制

**文件：** `runner.py` 第 56-60 行

```python
def _truncate_preview(value, limit=2000):
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text[:limit] + "...(truncated)" if len(text) > limit else text
```

**问题：** 当 `text` 长度超过 `limit` 时，返回值是 `text[:limit] + "...(truncated)"`，总长度为 `limit + 14`。这超出了约定的 `limit` 限制。虽然这是一个小问题，但被截断的字符串可能被用于存储或显示，导致意外的长度超出。

---

### Bug B4：`_video_title` 正则表达式在标题包含 `*` 时截断

**文件：** `node_executor.py` 第 2155-2158 行

```python
def _video_title(self, brief: str) -> str:
    titled = re.search(r"视频标题[^\n]*\n+(?:\s*\*\*)?([^\n*]+)", brief)
    if titled:
        return titled.group(1).strip().strip("「」\"'")[:52]
```

**问题：** 正则表达式 `[^\n*]+` 匹配的字符集排除 `*`。如果标题中包含 `*` 字符（例如「3D 渲染 * 2」），标题会在 `*` 处被截断。正确的字符集应该是 `[^\n]+`（匹配任何非换行字符）。

**影响：** 视频标题中的 `*` 字符会导致标题被截断，生成的视频标题不完整。

---

## P1 — 安全与数据完整性

### Bug B5：`Content-Security-Policy` 的 `frame-src` 使用无效端口通配符

**文件：** `main.py` 第 287-294 行

```python
"frame-src 'self' http://127.0.0.1:* http://localhost:*; "
```

**问题：** CSP 规范不支持 `http://127.0.0.1:*` 这样的端口通配符语法。正确的做法是 `http://127.0.0.1:*` — 但实际上 CSP 不支持端口层面的通配符。`*` 在 CSP 中只作为 host 层面的通配符有效（如 `*.example.com`）。所以 `http://127.0.0.1:*` 会被浏览器忽略，导致 frame-src 只允许 `'self'`。

**影响：** 沙箱 iframe（DLC 和交互组件）使用 `http://127.0.0.1:8765` 或其他端口的服务时，可能被 CSP 阻止加载。`frame-src` 的端口通配符不生效，导致只有 `'self'` 源被允许。

**修复：** 使用精确端口或移除端口限制：`http://127.0.0.1 http://localhost`。

---

### Bug B6：Pydantic v2 使用已弃用的 `.dict()` 方法

**文件：** `main.py` 多处（共 9 处调用）

```python
# 在 Pydantic 2.13.4 中使用已弃用的 API
return {"ok": True, "resources": save_resources(payload.dict())}
```

**问题：** 项目使用 `pydantic==2.13.4`，但所有模型转字典操作都使用已弃用的 `.dict()` 方法。Pydantic v2 建议使用 `.model_dump()`。虽然 `.dict()` 短期内仍可用，但：
- 在 `model_config = ConfigDict(populate_by_name=True)` 的模型中，`.dict()` 不保证正确使用字段别名
- 未来版本可能移除 `.dict()` 方法

**影响：** 9 处调用在 Pydantic 未来版本升级时可能失效。当前版本中，`ConfigDict(extra="allow")` 与 `.dict()` 的行为可能不一致。

---

### Bug B7：`_registry_for_run` 缓存键使用 `json.dumps` 默认值可能导致非唯一键

**文件：** `node_executor.py` 第 82-94 行

```python
cache_key = json.dumps(
    {
        "extensions": extensions,
        "portable_dlc": portable_dlc,
        "package_path": package_path,
        ...
    },
    ensure_ascii=True,
    sort_keys=True,
    default=str,  # ← 非序列化对象转为字符串
)
```

**问题：** `default=str` 会将任何非 JSON 序列化的对象转换为其 Python 字符串表示（如 `<object object at 0x...>`）。两个不同的对象可能有不同的内存地址，但 JSON 序列化后 `default=str` 会生成不同的字符串，所以不会导致键碰撞。但更严重的问题是，`_scoped_mcp_registries` 字典**永远不会被清理**，每次运行都可能产生新的缓存条目，导致内存泄漏。

**影响：** 长时间运行后，`_scoped_mcp_registries` 字典可能无限增长，占用大量内存。

---

## P2 — 逻辑缺陷

### Bug B8：`_prepare_v02_mcp_node` 中 `allowed_tools=[]` 被错误地视为"未设置"

**文件：** `node_executor.py` 第 306-308 行

```python
allowed_tools = self._split_keys(params.get("allowed_tools")) or self._split_keys(mcp_binding.get("allowed_tools"))
```

**问题：** `self._split_keys([])` 返回 `[]`（空列表），而 `[]` 在 Python 中是 falsy 值。`or` 运算符会将其视为"未设置"，从而回退到 `mcp_binding.get("allowed_tools")`。这意味着用户显式设置 `allowed_tools=[]`（表示不允许任何工具）时，会被忽略，转而使用 MCP binding 中的工具列表。

**影响：** 用户无法通过 `allowed_tools=[]` 禁用所有工具。

---

### Bug B9：`_llm_prompt` 中空 prompt_template 被静默替换

**文件：** `node_executor.py` 第 1165-1172 行、第 1184-1189 行

```python
prompt_template = (
    params.get("prompt") or
    preset_config.get("target") or
    preset_config.get("format") or
    ...  # 回退到 ""
)
# ...
if not prompt_template:
    prompt_template = (
        run.get("inputs", {}).get("prompt") or
        run.get("inputs", {}).get("task_description") or
        "请根据上下文完成任务。"
    )
```

**问题：** 如果用户显式设置 `prompt=""`（空字符串），`not prompt_template` 为 `True`，导致 prompt 被替换为运行输入中的 prompt 或硬编码的默认值。用户无法通过设置空字符串来表示"没有 prompt"。

**影响：** 用户意图"使用上下文文本作为唯一输入，不需要额外 prompt"时，会被强制添加默认 prompt。

---

### Bug B10：`_tool_call` 中硬编码的 `server == "filesystem"` 检查

**文件：** `node_executor.py` 第 569-570 行

```python
if server == "filesystem" and isinstance(tool_params.get("path"), str):
    tool_params["path"] = self._resolve_package_relative_path(tool_params["path"], _run)
```

**问题：** `server == "filesystem"` 是硬编码的字符串比较。如果 filesystem 服务器的名称被配置为其他名称（如 `"fs"`、`"local_fs"`），路径解析逻辑不会触发。此外，其他需要路径解析的工具服务器也不会获得路径解析能力。

**影响：** 可配置的 MCP 服务器名称与硬编码检查不匹配时，路径解析失败。

---

## P3 — 代码质量

### Bug B11：`_public_data_path` 可能暴露不在 `.data/` 下的路径

**文件：** `main.py` 第 123-127 行

```python
def _public_data_path(path: str | Path) -> str:
    data_root = (ROOT / DATA_ROOT).resolve()
    relative = Path(path).resolve().relative_to(data_root)
    return (Path(".data") / relative).as_posix()
```

**问题：** 如果 `path` 不在 `DATA_ROOT` 下，`relative_to` 会抛出 `ValueError`。但调用者可能没有处理这个异常。虽然目前调用者 `upload_file` 使用的是 `UPLOADS_DIR` 下的路径，但未来如果传入其他路径，会直接 500 错误。

---

### Bug B12：`_redact_diagnostic_value` 正则表达式在 `bearer` 令牌中可能误匹配

**文件：** `main.py` 第 194 行

```python
text = re.sub(r"(?i)(bearer\s+)[a-z0-9._~+/-]+", r"\1[redacted]", text)
```

**问题：** 字符类 `[a-z0-9._~+/-]` 中的 `+/-` 被解释为从 `+`（0x2B）到 `/`（0x2F）的范围，包括 `,`（0x2C）和 `-`（0x2D）。虽然这恰好匹配了 URL-safe base64 字符集，但语义不清晰。更重要的是，这个正则匹配所有 `bearer` 后的文本直到遇到非 URL-safe 字符，这可能误匹配正常文本中的"bearer"一词。

---

## 附录：修复建议

### 修复优先级

| 优先级 | Bug | 影响 | 难度 | 建议修复方式 |
|--------|-----|------|------|-------------|
| **P0** | B1 | 功能正确性 | 低 | 添加日志警告 |
| **P0** | B2 | 功能正确性 | 低 | 统一判定条件 |
| **P0** | B3 | 功能正确性 | 低 | 改为 `text[:limit-14]` |
| **P0** | B4 | 功能正确性 | 低 | 正则改为 `[^\n]+` |
| **P1** | B5 | 安全性 | 低 | 移除端口通配符 |
| **P1** | B6 | 兼容性 | 中 | 迁移到 `.model_dump()` |
| **P1** | B7 | 内存泄漏 | 中 | 添加 LRU 缓存清理 |
| **P2** | B8 | 逻辑缺陷 | 低 | 添加 `is None` 检查 |
| **P2** | B9 | 逻辑缺陷 | 中 | 区分空字符串和未设置 |
| **P2** | B10 | 逻辑缺陷 | 低 | 使用配置或注册表 |
| **P3** | B11 | 代码质量 | 低 | 添加异常处理 |
| **P3** | B12 | 代码质量 | 低 | 明确字符类范围 |

---

*报告结束。共发现 12 个后端 bug，其中 P0 4 个、P1 3 个、P2 3 个、P3 2 个。*