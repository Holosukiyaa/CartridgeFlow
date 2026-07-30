# CartridgeFlowLite AI 快速起点

读完本文件即可开始定位和修改代码，不需要先跳转到其他 Agent 指南。

## 项目是什么

CartridgeFlowLite 是专注卡带开发闭环的本地工作台。开发者在一个界面内完成 Flow 设计、节点检查、模型与工具配置、真实运行、失败恢复和产物查看。

Lite 明确不包含：全局概览、跨卡带诊断、独立资源中心、发布后台、全局外观设置和 AI 助手。不要把这些完整版本能力重新接回 Lite。

## 运行入口

- 后端入口：`src/backend/lite_main.py`
- 完整路由实现：`src/backend/main.py`，由 Lite 中间件只开放白名单接口
- 前端入口：`src/frontend/src/App.tsx`
- 主工作台：`src/frontend/src/pages/FlowWorkbench.tsx`
- 启动器：`scripts/launch.py`
- 测试入口：`scripts/run_conformance.py`

## 结构速查

```text
src/
  backend/       FastAPI 入口与 Lite API 边界
  core/          卡带、协议、运行时、模型、工具、DLC 和本机配置
  frontend/      唯一的 React 工作台
config/          能力声明、默认策略和本机配置模板
protocol/        机器可读协议 registry
docs/            架构、开发、规划和协议正文
scripts/         依赖安装、启动、测试与 UI 断言
.data/           用户数据、运行数据、报告和临时文件，不是源码
```

工作台节点代码集中在 `src/frontend/src/pages/flow-workbench/`：

- `FlowGraphView.tsx`：画布、视口和连接交互。
- `FlowNodeCard.tsx`：主节点视觉与摘要信息。
- `NodeDetailCard.tsx`：可拖动、可钉住的详情卫星卡。
- `nodeDetails.ts`：不同节点的详情分区和字段语义。
- `flowNodeView.ts`：节点展示模型。
- `ResourceManagementPanels.tsx`：模型与工具工作台面板。
- `TestBenchView.tsx`：真实运行、历史、日志、恢复和产物。

## 数据与配置

开发卡带位于 `.data/user/dev_cartridges/<cartridge-id>/`，核心文件是 `manifest.json` 和 `root.flow.json`。模型、Key、凭据和工具实例位于 `.data/user/config/`，不得写入卡带或提交到 Git。

可提交的配置只有：

- `config/base/`：底座能力与证据声明。
- `config/defaults/`：实际生效的默认策略。
- `config/templates/`：创建本机配置时使用的无密钥模板。

## 运行链

```text
React 工作台
  -> Lite API 白名单
  -> 卡带 Registry 与协议检查
  -> CartridgeRunner
  -> 节点执行器
  -> LLM / MCP / Remote API / DLC
  -> Store / Artifact / Event / Checkpoint
  -> 运行历史、失败日志与恢复入口
```

失败不能伪装成成功。外部服务不可用、输出为空或协议不合法时必须保留真实错误身份。可能重复外部副作用的恢复动作必须先确认。

## 修改位置

| 需求 | 位置 |
|---|---|
| 工作台布局和交互 | `src/frontend/src/` |
| Lite 接口是否允许 | `src/backend/lite_main.py` |
| HTTP 实现 | `src/backend/main.py` |
| 卡带加载、执行和产物 | `src/core/cartridge/` |
| 节点执行与 Flow 编辑 | `src/core/lab/` |
| 错误、检查点和恢复 | `src/core/runtime/` |
| 模型配置与调用 | `src/core/llm/` |
| 本机工具与资源 | `src/core/studio/` |
| 协议兼容与认证 | `src/core/protocol/`、`protocol/` |
| 自动验证 | `scripts/tests/` |

## 开发规则

1. 每次行动前先把任务写入 `docs/planning/TODO.md`。
2. 底座只保留跨卡带通用能力，业务逻辑归卡带或 DLC。
3. 不提交 `.data/`、密钥、日志、依赖、缓存或构建产物。
4. Lite 使用开发者机器上的 Python、Node 和 npm，不创建 `.tools` 运行时。
5. 前端提交操作，后端和核心层负责真实状态与业务判定。
6. 新增、删除或移动文件时同步更新 `docs/development/FILE_INVENTORY.md`。
7. 修改公开语义时先更新协议版本；实现状态只以能力声明和测试证据为准。
8. 协议生命周期、默认新建版本、迁移目标和快照路径只从 `protocol/catalog/release_manifest.json` 读取；修改后必须运行 `python scripts/audit_protocol_governance.py`。
9. 保留用户已有改动，不顺手重构无关模块。

## 常用命令

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
python scripts/launch.py
python scripts/run_conformance.py
npm --prefix src/frontend run build
python -m compileall -q src/core src/backend scripts
```

完成修改前，按风险运行测试；前端改动必须通过生产构建。路径、启动或配置变化需要实际启动相关入口。协议和共享运行逻辑变化应运行完整 conformance。

需要深入时再查阅 `docs/overview/PROJECT_STRUCTURE.md` 和对应协议正文。
