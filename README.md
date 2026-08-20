# CartridgeFlow

CartridgeFlow 将开放式想法整理为经过人工审核的语义方案，并生成带签名、可移植的应用卡带。卡带也可以作为其他卡带中的可复用能力，因此少见需求可以先独立实现，再递归组合，而不需要写死到 Base 内核。

## 启动

需要在 `PATH` 中提供 Python 3、Node.js 20.19 或更高版本以及 npm。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
run.bat
```

一个 FastAPI 进程会在同源地址提供两个创作界面：

- 意图工作室：`http://127.0.0.1:8765/studio`
- 能力工作台：`http://127.0.0.1:8765/capabilities`

`run.bat` 只会清理占用 8765 端口的旧 CartridgeFlow 监听进程，然后构建两个前端并启动后端。草稿、能力发布物和生成的卡带默认写入已忽略的 `.data/`；可在启动前设置 `CARTRIDGEFLOW_DATA_ROOT`，将本地数据迁到源码仓之外。

## 产品流程

```text
用户想法 -> 语义画布 -> 可信能力绑定
         -> 递归打包 -> 独立运行交付
```

当语义节点没有匹配实现时，意图工作室会保留能力缺口。开发者可以在能力工作台中实现完整 Flow，验证后发布为工作区可信能力，再回到原节点进行自动解析与人工复核。意图层不暴露运行参数和实现拓扑，发布卡带是它进入可执行事实的唯一交接方式。

## 验证

```powershell
python scripts/run_conformance.py --quiet
python scripts/audit_protocol_registry.py
npm --prefix src/studio run build
npm --prefix src/studio run typecheck
npm --prefix src/studio run test:click
trufflehog filesystem . --results=verified --exclude-detectors=Lob --fail --fail-on-scan-errors --no-update --exclude-paths=config/trufflehog-filesystem-exclude.txt
trufflehog git file://. --results=verified --exclude-detectors=Lob --fail --fail-on-scan-errors --no-update
```

本项目没有集成 Lob。它的在线检测器会把普通 Python `test_*` 标识误判为 Lob 环境名，因此当前明确排除该检测器；引入 Lob 集成时必须取消排除。其余检测器保持启用。

## 仓库内容

- `src/backend/`：共享 HTTP 应用与 API 路由。
- `src/core/`：卡带、运行时、协议适配、实验室和工作室核心逻辑。
- `src/studio/`：唯一创作工作台（语义方案、能力补齐、试运行）。旧 Intent Studio、Capability Workshop、Delivery Workbench 源码已移出本仓库归档。
- `config/protocol/`：产品锁定的只读 `protocol-registry.sqlite` 和协议锁。
- `scripts/`：启动、构建、发布、审计和产品验收工具。

协议本体只存在于独立的 [cartridgeflow-protocols](https://github.com/Holosukiyaa/cartridgeflow-protocols) 仓库，产品仓不嵌入或挂载协议源。产品只消费经过锁定和验证的协议快照。
