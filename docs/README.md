# CartridgeFlow 文档入口

这里是项目文档的唯一总入口。第一次接手项目时，不需要把所有文档从头读一遍，先按下面的阅读路径找到与当前工作有关的内容。

## 先读什么

| 场景 | 阅读顺序 |
|---|---|
| 第一次了解项目 | 根目录 `README.md` -> [项目分层](overview/PROJECT_STRUCTURE.md) -> [路线图](planning/ROADMAP.md) |
| AI 接手或准备开发 | 根目录 `AGENT.md` -> [任务清单](planning/TODO.md) -> 与需求直接相关的源码；产品边界和里程碑再查 [路线图](planning/ROADMAP.md) |
| 修改 Base、Flow 或运行时 | [当前 Base 0.2 契约](protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md) -> [最新 CF-FARP 0.7 协议](protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.7.md) -> [机器 registry](../protocol/README.md) -> `src/core/protocol/` -> 对应 conformance 测试；修复现有运行时还要核对 v0.6 快照 |
| 修改 Portable DLC | [Portable DLC 架构](architecture/PORTABLE_DLC_ARCHITECTURE.md) -> [协议治理](protocol/GOVERNANCE.md) |
| 开发和运行自动测试 | [开发与维护](development/README.md) -> `scripts/` |
| 查找某个文件 | [逐文件清单](development/FILE_INVENTORY.md) |

## 文档分区

```text
docs/
├─ README.md             当前入口
├─ overview/             全局导览：项目是什么、系统怎么协作
├─ development/          维护入口、文件清单、深层 AI 参考和可选 Skill
├─ planning/             路线图、当前任务和任务模板
├─ architecture/         专项架构决策与不可破坏的设计约束
└─ protocol/             当前协议、已发布历史快照和治理规则
```

### 当前使用

- [项目分层](overview/PROJECT_STRUCTURE.md)：用大白话解释前端、后端、运行时、协议和本地数据如何协作。
- [逐文件清单](development/FILE_INVENTORY.md)：登记全部项目自有文件的用途，供维护时查阅。
- [路线图](planning/ROADMAP.md)：长期产品边界、阶段里程碑和生产验收门槛。
- [Base Contract 0.2](protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md)：当前基座宿主契约。
- [CF-FARP 0.7](protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.7.md)：最新 Flow 协议正文，定义卡带资产、交互节点和脚本安全边界。
- [CF-FARP 0.6](protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.6.md)：当前参考底座仍在运行的上一版协议快照。
- [Portable DLC 架构](architecture/PORTABLE_DLC_ARCHITECTURE.md)：基座与卡带私有能力的激活、隔离和所有权约束。
- [协议治理](protocol/GOVERNANCE.md)：修改协议、实现 Flow 和发布快照时必须遵守的规则。

当前基座支持矩阵以 `config/base/BASE_IMPLEMENTATION.json` 为准：

| 协议 | 基座声明 | 用途 |
|---|---|---|
| CARTRIDGEFLOW-BASE v0.2 | 当前实现契约 | 基座所有权、本机配置、恢复、扩展和卸载边界。 |
| CF-FARP v0.7 | 未声明支持 | 最新规范；实现与 conformance 完成前禁止运行。 |
| CF-FARP v0.6 | `partial` | 当前参考底座实际运行的协议。 |
| CF-FARP v0.1-v0.5 | `recognized` | 仅保留身份、迁移目标和历史测试；不可运行、不可认证。 |

### 历史快照

以下文件不是日常开发入口，但属于已经发布的语义证据，不能当作普通旧文档删除或改写：

- `protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.1.md`
- `protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.5.md`
- `protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.3.md`
- `protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.4.md`
- 根目录 `protocol/CF-FARP-0.1.json` 到 `protocol/CF-FARP-0.4.json`

历史协议保留原路径，是因为 registry、兼容性测试和外部卡带可能引用这些稳定地址。

`CF-FARP 0.2` 是一个已知历史缺口：机器 registry 仍用于迁移识别，但原始协议正文不在当前仓库。不能根据后续版本反向伪造这份已发布正文，也不为缺失文件保留永久跳过的测试。

## 根目录只保留什么

根目录文件只承担四类职责：

1. 仓库元数据：`.gitattributes`、`.gitignore`。
2. 启动和依赖：`run.bat`、`requirements.txt`；启动实现位于 `scripts/launch.py`。
3. 仓库入口：`README.md`、`AGENT.md`。
4. 版本声明：`VERSION`。

当前执行清单位于 `docs/planning/TODO.md`，基础模板与它放在同一目录。
项目不单独维护 Changelog；变更历史和正式发布说明由 GitHub 提交记录与 Release 承担。

新的背景说明、设计说明或过程记录默认放进 `docs/` 对应分区，不再继续堆到根目录。

## 不是正式文档或源码的内容

| 目录 | 含义 |
|---|---|
| `.data/user/` | 必须保留和备份的 Flow、已安装卡带、包、私有数据和用户产物。 |
| `.data/runtime/` | 运行记录、检查点和 Worker 生命周期状态。 |
| `.data/reports/` | 服务日志、错误报告和 conformance 报告。 |
| `.data/temp/` | 上传与导入缓存，可安全清理。 |
| `.tools/runtimes/` | Bootstrap 准备的项目本地 Python 和 Node 开发运行时。 |
| `.tools/downloads/` | 可重建的运行时安装包下载缓存。 |
| `src/frontend/node_modules/` | npm 第三方依赖。 |
| `src/frontend/dist/` | 前端生产构建产物，由 Vite 生成。 |
| `__pycache__/`、`.pytest_cache/` | 可清理的解释器和测试缓存。 |

这些内容可能出现在项目目录中，但不参与文档数量和源码结构统计。

## 工具和配置边界

这些分区直接承担开发、配置或协议职责；它们的边界必须保持单一：

| 目录 | 只负责什么 | 不应该放什么 |
|---|---|---|
| [`scripts/`](../scripts/) | 启动脚本和自动测试。 | 人类说明文档、AI Skill、运行时实现、卡带业务、用户数据。 |
| [`docs/development/`](development/README.md) | 开发入口、深层 AI 开发参考和可选 Skill。 | 可执行脚本、测试代码和本机数据。 |
| [`config/`](../config/README.md) | 基座默认配置和本机配置入口。 | 卡带业务配置；密钥只能存在被忽略的本机文件。 |
| [`protocol/`](../protocol/README.md) | 机器可读协议身份、词表和历史索引。 | 实现代码、运行数据和过程文档。 |

开发者需要执行或修改维护代码时进入 `scripts/`；需要阅读背景和规则时进入 `docs/development/`。两类内容不要重新混放。

## 维护规则

1. 每份文档只解决一个明确问题。
2. 当前入口必须能从本文件找到。
3. 过时但仍有兼容价值的内容标记为历史快照，不和当前说明混写。
4. 已发布协议保持原路径和内容不变；语义变化必须发布新版本。
5. 新增或移动项目文件时，同步更新 `development/FILE_INVENTORY.md`。
