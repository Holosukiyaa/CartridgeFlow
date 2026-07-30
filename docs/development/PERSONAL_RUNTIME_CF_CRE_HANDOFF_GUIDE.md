# CF-CRE@1 个人运行台接入指南

本文给个人运行台团队提供一个可以重复执行的候选包闭环。当前 Base 对 `CF-CRE@1` 的支持状态为 `partial`：开发台可真实构建发行候选 ZIP，运行台可在不解压、不执行载荷代码的前提下读取并验证归档；它不是安装器，也不能运行卡带。

## 已交付边界

运行台可调用 `core.protocol.inspect_release_archive(path)`。输入是本地 `.zip` 文件路径，输出包含：

- `status`：仅可能是 `validated_pending_install` 或 `rejected`。
- `activation_allowed`：当前恒为 `false`。
- `report`：CF-CRE 验证报告、稳定错误码和摘要。
- `release`：仅验证成功后提供的发行清单。
- `public_contracts`：仅验证成功后提供的 `experience` 和 `delivery` 合同。

验证成功只说明归档路径、公开边界、文件清单和 SHA-256 摘要一致。签名文件当前仅验证元数据存在，尚未进行 Ed25519 验签，因此不得写入已安装目录、不得创建 Active 指针、不得启动 Runner。

## 演示闭环

开发台先通过工作台创建或选择一个可编辑的 v0.9 卡带，然后运行：

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
python scripts\demo_cf_cre_runtime_handoff.py `
  --source ".data\user\dev_cartridges\dev.cre-release-demo" `
  --output ".data\demo\dev.cre-release-demo-0.0.1.cf-release.zip" `
  --publisher "demo.publisher" `
  --product-name "每日摘要演示"
```

该命令实际写入 ZIP，再由 Archive Reader 从 ZIP 字节重新读取并验证。成功结果必须为：

```json
{"ok": true, "stage": "validated_pending_install", "activation_allowed": false}
```

运行台应只用 `public_contracts.experience` 渲染输入和公开阶段，只用 `public_contracts.delivery` 渲染交付承诺。不要向产品界面泄露 `payload/root.flow.json`、MCP、端点、凭据、提示词、节点、Store 或检查点。

## 运行台后续接口

未来安装器应在 Archive Reader 成功之后，以如下状态机继续，而不是跳过暂存：

```text
imported -> validated_pending_install -> signature_verified -> compatible
-> needs_binding -> ready -> active
```

`signature_verified` 必须验证 Ed25519 签名和信任/撤销状态；`compatible` 必须核对 Base、CF-FARP、运行器版本及必需能力；`needs_binding` 必须向用户收集本地资源授权和健康结果；只有全部通过后才允许原子写入版本目录和 Active 指针。

失败一律保持 `rejected` 或隔离暂存，不能改变当前 Active 版本。候选包不携带资源绑定、密钥、私有 URL、本机目录、用户输入、日志、检查点或用户产物。

## 责任划分

开发台负责：源包卫生检查、发行身份、公开合同、候选包构建和静态归档验证。

个人运行台负责：安全导入限额、验签与信任库、兼容性、用户授权、资源重绑定、版本并存、原子激活、回滚、卸载与运行记录。

市场未来负责：独立复验候选包、发布者身份、不可变 Release 记录与 Listing；不得信任开发台自报的验证结果。
