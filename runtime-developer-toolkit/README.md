# CartridgeFlow 运行台开发者工具包

这是交给运行台团队的最小开发工具包，包含协议开发指南、无 Python Node.js demo，以及一个真实通过 Base 生产预检并签名的 `CF-CRE@1` 原始案例包。

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
   ├─ dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip
   └─ trusted_publishers.json
```

## 交接顺序

1. 阅读 `guide/RUNTIME_TEAM_CF_CRE_FARP_DEVELOPMENT_GUIDE.md`，先理解 CF-CRE@1 和 CF-FARP@1.0 的边界。
2. 运行 `npm --prefix demo run check`，确认 Node.js 环境满足要求。
3. 使用 `samples/trusted_publishers.json` 验证样例包。
4. 使用 `--mock` 跑通不联网的确定性执行链。
5. 启动 `demo/mock-model.mjs`，不加 `--mock` 跑通真实 OpenAI-compatible HTTP 链路。
6. 用运行台自己的信任库、资源绑定和安装目录替换样例配置。

## 快速命令

在仓库根目录执行：

```powershell
npm --prefix runtime-developer-toolkit/demo run check

node runtime-developer-toolkit/demo/run.mjs verify `
  runtime-developer-toolkit/samples/dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json

node runtime-developer-toolkit/demo/run.mjs run `
  runtime-developer-toolkit/samples/dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip `
  runtime-developer-toolkit/run-mock `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json `
  --mock
```

真实 HTTP 测试：

```powershell
node runtime-developer-toolkit/demo/mock-model.mjs
```

另开终端：

```powershell
$env:CF_RUNTIME_MODEL_BASE_URL = "http://127.0.0.1:11434/v1"
$env:CF_RUNTIME_MODEL_API_KEY = "cf-demo-key"
$env:CF_RUNTIME_MODEL = "cf-demo-model"

node runtime-developer-toolkit/demo/run.mjs run `
  runtime-developer-toolkit/samples/dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip `
  runtime-developer-toolkit/run-http `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json
```

## 原始案例说明

样例包 `dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip` 是通过 CartridgeFlow Base 生产打包链生成的真实归档，包含：

- CF-CRE@1 release envelope。
- CF-FARP@1.0 execution plan。
- 一个模型 API decision 节点。
- 一个 `filesystem_write` MCP 节点。
- 公共体验合同和交付合同。
- Ed25519 publisher signature。
- 与样例签名匹配的公开信任库。

`trusted_publishers.json` 只包含公钥，不包含签名私钥。它仅用于本地开发和协议交接验证，生产环境必须替换为运行台自己的受管信任库。

## 重要限制

这个工具包不是生产运行台，也不是完整开发台。demo 只实现最小的顺序执行、模型节点和文件写入 MCP。生产实现仍需补齐完整 execution plan、资源重绑定、权限 broker、MCP transport、checkpoint、升级回滚和审计策略。

## 规范来源

- `protocol/release-envelope/1/specification.md`
- `protocol/flow-authoring/1.0/`
- `config/base/BASE_IMPLEMENTATION.json`
- `src/core/protocol/release_builder.py`
- `src/core/protocol/release_signing.py`
