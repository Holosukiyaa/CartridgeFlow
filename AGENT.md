# CartridgeFlow — Agent 快速开始

> 版本：v0.0.4-pre　｜　给接手开发/调试的 Agent 用的最小上手指南。

## 1. 这是什么

CartridgeFlow 是一个「卡带（Cartridge）+ 流程图（Flow）」式的 AI 工作流编排应用：

- **卡带（Cartridge）**：一个可运行的工作流单元，含 `manifest.json`（元信息、输入输出、权限、依赖、运行时）和 `root.flow.json`（流程图定义）。
- **Flow**：由若干 **节点（states）** 和 **连线（edges）** 组成的有向图，描述从 `start` 到 `complete` 的执行链路。
- **运行时（Runtime）**：节点实际干活的适配器，如 `html_generator`、`llm_prompt`、`agent_squad`。
- **LLM 层**：统一的多 Provider 配置与调用（OpenAI 兼容 / Anthropic）。
- **协议文件**：`docs/protocol/` 保存当前规范基座协议正文和后续 Agent 入口说明。改动协议、基座能力、兼容性认证、manifest / root flow / 节点语义前，必须先读 `docs/protocol/agent.md`。协议升级步骤参考 `skills/cartridgeflow-protocol-upgrader/SKILL.md`。
- **CF-FARP v0.4 active**：新流程优先使用 `CF-FARP@0.4`。协议层业务节点统一为 `type=process`，并用 `kind`、`executor`、`effect` 区分输入、传递、检索、AI 决策、MCP 执行、质检、展示、交付等行为。`executor=llm` 的 AI 决策节点必须输出 `decision_envelope.v1`；允许 `resolved` 时必须声明 `decision_contract.consume`，用显式 `path` 与 `as` 说明后续节点消费什么；`needs_user_input` 必须进入 `paused_waiting_user`，不得继续执行后续副作用节点。

## 2. 技术栈

| 层 | 技术 | 端口 / 入口 |
|---|---|---|
| 后端 | Python + FastAPI + uvicorn | `8765`，`server.main:app` |
| 前端 | React 19 + Vite + TypeScript | `5173` |
| 桌面壳 | pywebview（可选） | `desktop_app.py` |
| LLM | `openai` SDK（AsyncOpenAI） | `config/llm/*.json` |

## 3. 启动方式

### 一键启动（推荐）
```bash
python launch.py
```
`launch.py` 会：释放 8765/5173 端口 → 首次自动 `npm install` → 启动后端 → 启动前端 → 打开 http://localhost:5173

Windows 也可直接双击 `run.bat`。

### 分别启动（调试用）
```bash
# 后端
python -m uvicorn server.main:app --host 0.0.0.0 --port 8765 --reload

# 前端
cd frontend
npm install
npm run dev
```

### 桌面模式
```bash
python desktop_app.py   # 需要 pywebview，崩溃日志写到 ~/CartridgeFlow_crash.log
```

## 4. 依赖

项目暂无 `requirements.txt`。后端至少需要：
```bash
pip install fastapi uvicorn pydantic openai
# 桌面模式额外：pip install pywebview
```
前端依赖见 [package.json](file:///c:/_Hololab/C0/CartridgeFlow-v0.0.4-pre/frontend/package.json)（`npm install` 自动装）。

## 5. 配置

- **`.env`**（参考 [.env.example](file:///c:/_Hololab/C0/CartridgeFlow-v0.0.4-pre/.env.example)）：`CARTRIDGEFLOW_HOST` / `CARTRIDGEFLOW_PORT`
- **LLM 配置** `config/llm/`：
  - `providers.json`：模型 Provider 列表（含 api_key、base_url、default_model）
  - `assignments.json`：角色→模型的分配（defaults / cartridges / nodes）
  - `retry.json`：重试策略
  - 启动时 `ensure_llm_config()` 会保证这些文件存在。

> ⚠️ [providers.json](file:///c:/_Hololab/C0/CartridgeFlow-v0.0.4-pre/config/llm/providers.json) 目前含明文 API Key，注意不要提交泄露。

## 6. 目录速览

```
server/main.py        # 全部 REST API（FastAPI），最重要的入口文件
core/
  cartridge/          # 卡带注册/运行/权限/依赖/环境/产物
    registry.py       # 扫描并加载卡带
    runner.py         # 创建 run、驱动状态机、发事件
  lab/                # Flow 实验室：图构建 / 编辑 / AI 管家
    graph.py          # FlowGraphBuilder：从卡带生成前端图
    dev_flow.py       # DevFlowManager：dev 卡带的增删改校验
    steward.py        # FlowSteward：AI 改图建议
  llm/                # LLM 配置与调用（config_manager, openai_provider, retry, importers）
  runtime/            # 运行时适配器（html_generator / llm_prompt / agent_squad）
  workspace/          # 工作区
cartridges/dev/       # 开发者可编辑的卡带（editable=true）
config/llm/           # LLM 配置
docs/protocol/        # 规范基座协议正文与后续 Agent 必读入口
skills/               # 项目内可复用 Agent 技能，包含协议升级步骤
frontend/src/         # React 前端
  App.tsx             # 侧边栏 + 三个页面
  pages/ShelfPage     # 卡带货架
  pages/LabPage       # Flow 实验室（含 flow-workbench 编辑器）
  pages/LlmPage       # LLM 设置
  api.ts              # 前端调用后端的 API 封装
web_static/           # 后端托管的已构建前端（生产/桌面模式用）
logs/                 # flow_layout_debug.jsonl 等调试日志
```

## 7. 前端三大页面（对应 App.tsx 导航）

1. **卡带货架 Shelf**：浏览/运行已有卡带。
2. **Flow 实验室 Lab**：可视化编辑 dev 卡带的流程图（拖拽节点、连线、AI 管家改图）。核心组件在 `frontend/src/pages/flow-workbench/`。
3. **LLM 设置**：管理 Provider、测试连通性、导入（opencode / claude-code / codex）。

## 8. 关键 API（server/main.py）

- 健康检查：`GET /api/health`
- 卡带：`GET /api/cartridges`、`GET /api/cartridges/{id}`
- 运行：`POST /api/cartridge-runs`、`GET /api/cartridge-runs/{run_id}`、`.../events`、`.../control`
- Lab 流程：`GET/POST /api/lab/flows`、`.../{id}/preview-graph`、`.../nodes`、`.../edges`、`.../layout`
- AI 管家：`POST /api/lab/flows/{id}/steward/suggest`、`.../assistant`
- LLM：`GET/POST /api/llm/providers`、`POST /api/llm/test`、`GET /api/llm/assignments`

## 9. 数据模型要点

节点（`root.flow.json` 里的 `states`）常见字段：
- `type`：`terminal` / `ui` / `runtime` / `user_gate`
- `action`：如 `collect_inputs`、`llm_prompt`、`confirm_checkpoint`、`pass_result`、`start`
- `next`：主链路下一节点（root 出边）
- `scope`：`root`（主链路）/ `branch`（分支）
- `layout`：`{x, y}` 画布坐标
- `model_role`：LLM 角色（映射到 assignments）
- `locked`：锁定节点不可删

只有 `manifest.category == dev_flow` 且 `editable=true` 的卡带（即 `cartridges/dev/` 下）才可编辑。

## 10. 常见排错

- **端口被占**：`launch.py` 会自动清理 8765/5173；手动可用 `Get-NetTCPConnection`。
- **LLM 调用失败**：先在「LLM 设置」页用 `POST /api/llm/test` 测通，检查 `providers.json` 的 key/base_url。
- **前端白屏**：确认后端 8765 已起（`/api/health`），且前端指向正确后端地址（见 `frontend/src/api.ts`）。
- **桌面模式崩溃**：看 `~/CartridgeFlow_crash.log`。
