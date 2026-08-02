# 开发与维护

这里集中保存维护 CartridgeFlow 本身时需要阅读的说明和可选 AI Skill。可执行脚本与自动测试统一位于根目录 `scripts/`，不再和文档混放。

```text
docs/development/
├─ README.md               本入口
├─ DEVELOPMENT_CONSOLE_RELEASE_PROTOCOL_GUIDE.md
│                         开发台使用 CF-CRE@1 生成发行候选包的指南
├─ FILE_INVENTORY.md       项目自有文件清单和废弃审计
└─ skills/                 可选 AI Skill 包
```

## 脚本结构

```text
scripts/
├─ bootstrap.ps1         使用系统 Python 和 Node 安装项目依赖
├─ launch.py             启动前后端开发服务
├─ run_conformance.py    运行测试并生成一致性报告
└─ tests/
│  ├─ conformance/       当前协议、兼容性和认证
│  ├─ runtime/           节点执行、错误、恢复和 Worker
│  ├─ studio/            本机环境、资源和 TODO
│  ├─ llm/               模型配方和 Provider 接口
│  ├─ api/               HTTP API、边界和安全响应
│  ├─ lab/               Flow 创作、分析和编辑
│  ├─ orchestration/     执行计划编译与调度
│  ├─ hygiene/           仓库与发布包卫生
│  ├─ history/           旧协议识别、拒绝和规则快照
│  └─ fixtures/          跨测试复用的夹具，不单独执行
```

本目录中的 `skills/cartridgeflow-protocol-upgrader/` 是可选的协议升级 AI Skill 包。它包含机器指令和升级清单，因此随开发文档归档，不参与应用运行。

## 常用命令

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
python scripts/launch.py
python scripts/run_conformance.py
```

修改产品行为时先看 `src/`。修改验证规则、开发环境或维护流程时再进入 `scripts/`。当前能力证据只能引用当前或领域中立测试，不能由 `scripts/tests/history/` 中的旧协议测试代替。

根目录 `AGENT.md` 是 AI 接手仓库的唯一权威起点；架构与协议说明按当前任务从 `docs/` 对应分区查阅。

查找文件用途、审计历史遗留内容或新增文件时，使用并同步维护 [项目文件清单](FILE_INVENTORY.md)。

涉及卡带发布、发行候选包、签名、运行台导入或安装闭环时，阅读 [运行台开发者工具包](../../demos/runtime-developer-toolkit/README.md) 和其中的 [运行台团队 CF-CRE@1 与 CF-FARP@1.0 开发指南](../../demos/runtime-developer-toolkit/guide/RUNTIME_TEAM_CF_CRE_FARP_DEVELOPMENT_GUIDE.md)。
