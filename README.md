# CartridgeFlow

CartridgeFlow 是一个面向 AI 工作流的可视化卡带运行基座。它把流程定义、结构化 AI 决策、工具副作用、用户确认、运行恢复、产物收集和扩展卸载纳入同一套可验证协议。

当前正式版本：`v0.1.0`

## 版本特点

- `CF-FARP@0.5`：完整、独立、自包含的流程搭建与运行协议。
- 统一 Process Node：通过 `kind`、`executor`、`effect` 明确节点职责与副作用。
- 结构化 AI 决策：使用 `decision_envelope.v1`，并通过显式 consume 投影传递业务数据。
- 实时人机协作：流程可暂停为 `paused_waiting_user`，提交输入后从约定节点恢复。
- 测试台与探针：支持全流程、子图探针、mock 决策、真实 LLM 与工具 dry-run。
- Portable DLC：卡带可携带自己的后端工具、前端工作台、领域协议、工作流和测试。
- 隔离执行：DLC 后端运行在 JSON stdio worker 中，前端运行在 sandbox iframe 中。
- 可验证卸载：卡带卸载后，其工具、代码、协议 Overlay 和私有数据不再影响基座。
- LLM Provider：支持 OpenAI Chat Completions 与 Responses wire API，并提供文本/图片理解测试。

## 干净基座

`v0.1.0` 不预装任何业务卡带。首次启动时卡带架是空的，这是预期行为。

```text
cartridges/dev/                    # 本地开发卡带
.data/installed_cartridges/        # 导入安装的卡带
```

业务能力必须由卡带提供，不得硬编码到 `core/`、`server/` 或通用前端中。

## 快速开始

当前引导脚本支持 Windows x64。

1. 克隆仓库。
2. 双击 `run.bat`。
3. 首次运行会下载并校验项目本地 Python 3.13.14 与 Node.js 24.18.0，然后安装依赖。
4. 浏览器打开 `http://127.0.0.1:5173`。

手动启动：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
.\.tools\python\python.exe launch.py
```

运行测试：

```powershell
.\.tools\python\python.exe -m unittest discover -s tests/conformance -p "test_*.py"
$env:Path = (Resolve-Path .tools/node).Path + ";" + $env:Path
Set-Location frontend
npm.cmd run build
```

## 项目结构

```text
core/protocol/       协议解释、兼容性与认证
core/cartridge/      卡带发现、校验、运行、产物和依赖
core/extensions/     Portable DLC 描述符、作用域注册和隔离 worker
core/lab/            流程设计台、节点执行、探针和通用 MCP
core/llm/            LLM provider、wire API、重试和错误分类
server/              FastAPI 接口
frontend/            React 工作台
protocol/            机器可读协议 registry
docs/protocol/       只读协议正文
tests/conformance/   协议与基座一致性测试
devtools/AGENT.md    AI 开发者接手指南
```

## 协议入口

新卡带默认使用：

- `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.5.md`
- `protocol/CF-FARP-0.5.json`
- `BASE_IMPLEMENTATION.json`

已发布协议是不可变快照。协议语义需要改变时，必须建立新的完整版本。

## 开发卡带

一张最小卡带包含：

```text
cartridges/dev/<cartridge-id>/
  manifest.json
  root.flow.json
```

需要专属代码或 UI 时，使用 Portable DLC：

```text
  dlc/
    descriptor.json
    backend/
    frontend/
    protocols/
    workflows/
    tests/
```

详细约束、消息契约、测试与发布步骤见 `devtools/AGENT.md`。

## 发布状态

`v0.1.0` 是基座首个正式版本。`BASE_IMPLEMENTATION.json` 对协议支持状态的声明是权威信息；当前版本仍将各 CF-FARP 版本标记为 `partial`，不会把未通过的能力包装成完整实现。
