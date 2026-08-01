# CartridgeFlow 运行台开发者工具包

**版本：2.0.0**（2026-08-01 交接基线更新）

这是交给运行台团队的最小开发工具包，包含协议开发指南、无 Python Node.js demo，以及 5 个经开发台「卡带打包」功能（CF-CRE@1 production 模式）生成并签名的真实案例包，覆盖当前平台已验证的四种代表性流程形态。

## 目录

```text
runtime-developer-toolkit/
├─ README.md
├─ guide/
│  └─ RUNTIME_TEAM_CF_CRE_FARP_DEVELOPMENT_GUIDE.md
├─ demo/
│  ├─ run.mjs
│  ├─ mock-model.mjs
│  ├─ package.json
│  └─ README.md
└─ samples/
   ├─ dev.ai-video-daily-0.1.0.cf-cre.zip       # 端到端视频日报（多 AI 决策 + 外部 RSS + 人工审核 + 产物交付）
   ├─ dev.blog-writer-0.1.0.cf-cre.zip          # 博客生成器（驳回重写循环：人工审核 → AI 按意见重写 → 再审核）
   ├─ dev.parallel-research-0.1.0.cf-cre.zip    # 并行资料调研（fork/join 三路并行抓源 → 汇合 → AI 提炼）
   ├─ dev.threejs-arena-0.1.0.cf-cre.zip        # three.js 场景工坊（综合：并行 + 4 个 AI 决策 + 外部工具 + 审核 + HTML 产物）
   ├─ dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip  # 原始验收包（纯 sequence 最小案例，保留兼容）
   └─ trusted_publishers.json
```

## 交接顺序

1. 阅读 `guide/RUNTIME_TEAM_CF_CRE_FARP_DEVELOPMENT_GUIDE.md`，先理解 CF-CRE@1 与 CF-FARP@1.0 的边界。
2. 运行 `npm --prefix demo run check`，确认 Node.js 环境满足要求。
3. 使用 `samples/trusted_publishers.json` 验证样例包（`verify` 全部 5 个包）。
4. 使用 `--mock` 跑通确定性执行链（`run` 支持 sequence / fork-join / loop / 人工审核 / 产物交付）。
5. 启动 `demo/mock-model.mjs`，不加 `--mock` 跑通真实 OpenAI-compatible HTTP 链路。
6. 用运行台自己的信任库、资源绑定和安装目录替换样例配置。

## 快速命令

在仓库根目录执行：

```powershell
npm --prefix runtime-developer-toolkit/demo run check

# 校验全部样例包（5 个）
node runtime-developer-toolkit/demo/run.mjs verify `
  runtime-developer-toolkit/samples/dev.blog-writer-0.1.0.cf-cre.zip `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json

# 驳回重写循环（loop + 人工审核 + 产物）
node runtime-developer-toolkit/demo/run.mjs run `
  runtime-developer-toolkit/samples/dev.blog-writer-0.1.0.cf-cre.zip `
  runtime-developer-toolkit/run-mock `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json `
  --mock

# 并行 fork/join
node runtime-developer-toolkit/demo/run.mjs run `
  runtime-developer-toolkit/samples/dev.parallel-research-0.1.0.cf-cre.zip `
  runtime-developer-toolkit/run-mock `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json `
  --mock
```

真实 HTTP 测试（demo 内 LLM 节点走真实模型 API）：

```powershell
node runtime-developer-toolkit/demo/mock-model.mjs
```

另开终端：

```powershell
$env:CF_RUNTIME_MODEL_BASE_URL = "http://127.0.0.1:11434/v1"
$env:CF_RUNTIME_MODEL_API_KEY = "cf-demo-key"
$env:CF_RUNTIME_MODEL = "cf-demo-model"

node runtime-developer-toolkit/demo/run.mjs run `
  runtime-developer-toolkit/samples/dev.blog-writer-0.1.0.cf-cre.zip `
  runtime-developer-toolkit/run-http `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json
```

## 案例包说明（v2.0.0）

四个新样例包均由设计台通过开发台自带「卡带打包」功能（`POST /api/cartridges/{id}/package`，`package_mode=production`）生成，全部通过生产预检（`production_ready`）、签名信任（Ed25519 `local.development`）与激活校验：

| 包 | 代表性形态 | 验证过的执行能力 |
|---|---|---|
| `dev.blog-writer` | 驳回重写循环 | `confirm_checkpoint` 人工审核 + `answer_routes` 路由 + `loop` 边（`continue_when`/`exit_to`） |
| `dev.parallel-research` | fork/join 并行 | `fork` 多分支 + `join`（all 等齐）+ `pass_result` 汇合 |
| `dev.threejs-arena` | 综合流程 | 并行 + 多 `llm_prompt` 决策 + 外部工具 + 审核循环 + `render_template` 组装 + HTML 产物交付 |
| `dev.ai-video-daily` | 端到端视频日报 | 多 AI 决策 + 外部 RSS + 人工审核 + 视频/文档产物交付 |

`trusted_publishers.json` 只包含公钥，不包含签名私钥。它仅用于本地开发和协议交接验证，生产环境必须替换为运行台自己的受管信任库。

## demo 支持范围（v2.0.0 更新）

`demo/run.mjs` 是最小参考实现，现支持：

- 完整 CF-CRE@1 校验链（哈希、摘要、Ed25519 签名、信任库）。
- `execution_plan` 边：`sequence`、`loop`（`continue_when` 求值 + `exit_to`）、`fork`/`join`（顺序模拟并行分支 + join 等齐校验）。
- 节点执行：`llm_prompt`（mock / OpenAI-compatible HTTP）、`confirm_checkpoint`（mock 自动批准；真实模式中止——交互审核需生产实现）、`pass_result`（artifact 落盘）、`filesystem_write` MCP。
- `failure` 边与交互式人工审核 UI **不在**最小 demo 范围内——生产运行台必须实现 fail-closed 路由与真实审核交互。

## 重要限制

这个工具包不是生产运行台，也不是完整开发台。demo 只实现最小执行语义；生产实现仍需补齐完整资源重绑定、权限 broker、MCP transport、checkpoint、升级回滚和审计策略。

## 规范来源

- `protocol/release-envelope/1/specification.md`
- `protocol/flow-authoring/1.0/`
- `config/base/BASE_IMPLEMENTATION.json`
- `src/core/protocol/release_builder.py`
- `src/core/protocol/release_signing.py`
- 卡带打包与预检：`src/backend/main.py`（`/api/studio/release/{id}/preflight`、`/api/cartridges/{id}/package`）
