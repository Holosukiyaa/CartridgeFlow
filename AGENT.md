# CartridgeFlow AI 快速起点

这份文件是 AI 接手仓库的根入口。读完本文件即可开始定位和修改代码，不需要先跳转阅读另一份 Agent 指南。只有任务明确涉及协议正文、长期规划或某个专项边界时，才按文末索引继续查阅对应资料。

## 1. 项目是什么

CartridgeFlow 是面向专属 AI 服务开发者的本地工作流底座。

- **底座**提供 Flow 设计、运行、模型与工具连接、测试、恢复、产物和打包能力。
- **Flow / 卡带**描述某个具体服务的业务流程、配方、输入和交付结果。
- **本机配置**保存 URL、Key、凭据、工具实例和数据源连接，不随卡带迁移。
- **协议**定义卡带如何声明需求，以及底座如何校验和运行它。

正式基座不预装业务卡带。网站介绍视频、素材清洗、3D 生成等领域功能必须由独立卡带提供，不能写进通用底座源码。

## 2. 技术底座

- 后端：Python、FastAPI。
- 前端：React、TypeScript、Vite。
- 主开发环境：Windows x64。
- 本地运行数据：`.data/`。
- 项目本地 Python 和 Node：`.tools/`。
- 当前版本权威来源：根目录 `VERSION`。
- 当前能力声明：`config/base/BASE_IMPLEMENTATION.json`。

## 3. 仓库结构

```text
src/                         产品源码
  backend/main.py            FastAPI 应用和 HTTP 路由
  frontend/                  React 工作台、页面、组件和样式
  core/
    cartridge/               卡带发现、校验、运行、产物和依赖
    runtime/                 状态、错误、检查点和恢复基础能力
    lab/                     Flow 创建、编辑、分析、测试和通用 MCP
    studio/                  本机凭据、资源配置、发布和卫生检查
    llm/                     模型 Provider、调用适配和重试
    extensions/              Portable DLC 校验、隔离 Worker 和前端宿主
    protocol/                协议加载、兼容性和认证
    workspace/               卡带工作区宿主
    conformance/             自动一致性报告
    data_paths.py            `.data` 四区路径和旧布局迁移

config/                      可提交的基座配置
  base/                      能力声明和测试证据
  defaults/                  实际生效的出厂默认策略
  templates/                 本机配置的安全空白模板

protocol/                    机器可读协议 registry 和词表
docs/                        项目说明、开发指南、AI Skill、规划、架构和协议正文
scripts/                     启动脚本和自动测试
.data/                       本机数据，不是源码
  user/                      Flow、卡带、包、私有数据和用户产物
    config/                  真实模型、凭据、工具和数据来源配置
  runtime/                   运行记录、检查点和 Worker 状态
  reports/                   服务日志、错误报告和 conformance 报告
  temp/                      上传与导入缓存，可安全清理
.tools/                      自动生成的本地开发工具，不是源码
  runtimes/
    python/                  后端与工程脚本使用的 Python
    node/                    前端开发与构建使用的 Node.js
  downloads/                安装包下载缓存
```

## 4. 修改内容应该去哪里

| 需求 | 主要位置 |
|---|---|
| 页面、交互、布局、样式 | `src/frontend/src/` |
| HTTP 接口、请求校验、文件响应 | `src/backend/main.py` |
| 卡带发现、执行和交付 | `src/core/cartridge/` |
| 节点实际执行和测试探针 | `src/core/lab/node_executor.py`、`src/core/lab/` |
| 错误、检查点、重试、回滚和恢复 | `src/core/runtime/`、`src/core/cartridge/runner.py` |
| 模型配置和调用 | `src/core/llm/`、`.data/user/config/llm/`、`config/templates/llm/` |
| 凭据、工具和数据来源 | `src/core/studio/`、`.data/user/config/studio/`、`config/templates/studio/` |
| 卡带自带后端或专属 UI | 卡带自己的 `dlc/`、底座宿主 `src/core/extensions/` |
| 协议兼容性和认证 | `src/core/protocol/`、`protocol/` |
| 自动验证 | `scripts/tests/`（按 conformance、runtime、studio、llm、hygiene、history 分区） |
| 启动和开发脚本 | `scripts/` |

不要为了方便把业务逻辑塞进 `src/backend/main.py`、通用前端或 `src/core/`。先判断功能属于底座还是某张卡带，再选择所有者。

## 5. Flow 和卡带

开发中的 Flow 位于：

```text
.data/user/dev_cartridges/<cartridge-id>/
  manifest.json
  root.flow.json
```

导入的卡带位于 `.data/user/installed_cartridges/`。需要专属代码、UI、协议 Overlay 或供应商工作流时，卡带可以携带：

```text
dlc/
  descriptor.json
  backend/
  frontend/
  protocols/
  workflows/
  tests/
```

卡带只携带可迁移的配方和业务实现。Provider URL、API Key、本机命令、个人路径和全局资源实例不能进入卡带包。

## 6. 一次运行如何经过系统

```text
浏览器
  -> FastAPI 路由
  -> 卡带 Registry
  -> 协议与环境兼容性检查
  -> CartridgeRunner
  -> 节点执行器
  -> LLM / MCP / Remote API / Portable DLC
  -> Store、Artifact、事件和检查点
  -> 前端运行视图与交付入口
```

运行可能完成、暂停等待用户、失败或取消。失败不能伪装成普通成功；外部服务错误、空产物和 mock 结果都必须保留真实状态。

恢复分为四类：重试当前节点、从检查点继续、回滚到目标节点后重走、使用原始输入重新开始。可能重复外部副作用时，必须先获得明确确认。

## 7. 配置边界

`config/base/` 是随源码提交的基座声明：

- `BASE_IMPLEMENTATION.json` 声明底座承诺支持的协议和能力。
- `capability_evidence.json` 记录这些能力对应的实现和测试证据。

`config/defaults/` 保存底座实际采用的出厂默认策略，`config/templates/` 保存创建本机配置时使用的安全模板：

- `config/templates/` 可以提交，不得包含真实地址、Key 或个人路径。
- 本机的 `providers.json`、`assignments.json`、`credentials.json`、`resources.json` 位于 `.data/user/config/`。
- 卡带中的模型或工具配方通过稳定名称绑定到本机实例，不直接保存秘密。

任何 API 返回本机配置时都必须脱敏。不要在日志、错误、测试夹具或诊断包中输出完整密钥。

## 8. 协议基础

当前基座实现遵守 `CARTRIDGEFLOW-BASE@0.2`，当前 Flow 协议为 `CF-FARP@0.6`。真实支持范围以 `config/base/BASE_IMPLEMENTATION.json` 为准。

- 旧 CF-FARP 版本只保留身份识别和迁移信息，不代表当前基座仍可运行。
- 已发布协议正文是只读快照。修实现不改协议；改变公开语义必须发布新的完整协议版本。
- 新能力只有在实现、失败路径和 conformance 证据都存在后，才能加入能力声明。
- 缺少协议、能力、权限、配置或依赖时必须失败关闭，不能依靠隐藏默认值继续运行。

## 9. 开发硬规则

1. 底座只保留跨卡带通用能力，领域功能归卡带所有。
2. 不提交 `.data/`、`.tools/`、本机配置、密钥、日志、缓存和构建产物。
3. 不删除或覆盖用户已有改动；移动文件时同步更新所有引用。
4. 新增或移动项目文件时更新 `docs/development/FILE_INVENTORY.md`。
5. 前端只负责展示和提交操作，运行状态与业务判定由后端和核心层负责。
6. API、事件、运行快照和 UI 应使用同一错误身份，不在不同层改写错误含义。
7. mock、fallback 和外部未验证能力必须显式标记，不能冒充真实生产能力。
8. 用户 Artifact 默认保留；卸载卡带不能顺手删除用户交付物。
9. 路径使用仓库当前结构，不重新创建旧的 `server/`、`frontend/`、`tests/` 或 `tooling/` 根目录。
10. 保持改动聚焦，避免顺手重构无关模块。

## 10. 常用命令

首次安装并启动：

```powershell
.\run.bat
```

手动安装和启动：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
.\.tools\runtimes\python\python.exe scripts\launch.py
```

运行完整一致性测试：

```powershell
.\.tools\runtimes\python\python.exe scripts\run_conformance.py
```

构建前端：

```powershell
$env:Path = (Resolve-Path .tools/runtimes/node).Path + ";" + $env:Path
& .\.tools\runtimes\node\npm.cmd --prefix src/frontend run build
```

检查 Python 语法：

```powershell
.\.tools\runtimes\python\python.exe -m compileall -q src/core src/backend scripts
```

## 11. 完成改动前

- 运行与改动风险相匹配的测试；共享运行逻辑优先跑完整 conformance。
- 修改前端后执行生产构建，并检查常用缩放和窗口宽度。
- 修改启动、路径或配置后，实际启动服务并请求相关 API。
- 确认没有把本机数据、密钥、测试产物或业务卡带写进源码树。
- 新增、删除或移动文件后核对文件清单。
- 对外行为改变时更新对应说明；不要把过程记录堆进根目录。

## 12. 按需深入

本文件已经足够开始普通开发。只有任务直接涉及下列主题时，再打开对应资料：

- 项目分层：`docs/overview/PROJECT_STRUCTURE.md`
- 当前任务：`docs/planning/TODO.md`
- Base Contract：`docs/protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md`
- Flow 协议：`docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.6.md`
- DLC 所有权：`docs/architecture/PORTABLE_DLC_ARCHITECTURE.md`
- 全部文件用途：`docs/development/FILE_INVENTORY.md`
