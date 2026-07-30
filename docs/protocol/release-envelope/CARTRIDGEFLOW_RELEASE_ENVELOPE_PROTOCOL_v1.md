# CartridgeFlow 发行封装协议 v1

协议编号：`CF-CRE@1`

协议状态：草案（`draft`）

实现状态：部分支持（`partial`）：可构建发行候选包并进行归档静态验证；不可验签、安装、激活或执行。

发布日期：2026-07-30

依赖宿主契约：`CARTRIDGEFLOW-BASE@0.2`

## 1. 范围与状态

`CF-CRE@1` 规定开发台把卡带源工程发布为个人运行台发行包时，发行包必须携带的身份、公开体验、交付合同、完整性、签名元数据和兼容性事实。

本协议不定义流程节点或调度语义；这些仍由发行包中声明版本的 `CF-FARP` 负责。本协议也不定义支付、分账、市场审核、密钥托管、加密、数字版权保护、网络下载、运行台安装器或 Ed25519 实际验签的实现。

当前仓库已实现本协议的静态结构、公开合同泄露、路径和摘要验证器，以及确定性的发行候选 ZIP 构建和不解压的归档读取。Base 只声明这些已验证的部分能力；这不表示基础宿主、开发台、个人运行台或市场已经支持签名验签、安装、升级、回滚、资源重绑定、激活或执行 `CF-CRE@1` 发行包。

本文中的“必须”“不得”“应当”“可以”分别表示强制要求、禁止要求、推荐要求和可选行为。

## 2. 目标

1. 运行台只安装发行包，不读取开发工程或开发机状态。
2. 普通用户只看到产品输入、公开阶段、交付物和错误动作；不得看到根流程、提示词、节点、状态存储、工具参数或内部异常链。
3. 发布者、卡带、版本和内容摘要形成不可变身份；新版本不得覆盖历史发行包或其产物。
4. 凭据、私有连接、本机路径、资源绑定、运行状态和用户产物不得随包传播。
5. 业务卡带可以自由升级其流程、资产、输入、交付物和业务逻辑，而不必因每次业务升级修改发行协议。

## 3. 对象与版本

| 名称 | 含义 |
| --- | --- |
| 源工程 | 开发台中可编辑的卡带工程；不是发行物。 |
| 开发导出包 | 本地开发 ZIP；可用于受控测试，不得冒充市场发行包。 |
| 发行包 | 一个内容固定、已签名或待签名的 `CF-CRE@1` 包。 |
| 市场条目 | 市场中可变的封面、介绍、价格、评价和排序记录；只引用发行包身份。 |
| 安装记录 | 某台设备保存的发行包与本机重绑定状态。 |
| 激活版本 | 为新一次运行选定的已安装发行包。 |
| 运行 / 修订 | 一次生产与交付；固定引用实际发行包身份。 |

以下版本彼此独立：

- **卡带版本**：例如 `1.2.0`，表示业务产品版本。
- **发行协议版本**：`CF-CRE@1`，表示包如何被验证和安装。
- **流程协议版本**：例如 `CF-FARP@0.9`，表示执行载荷的流程语义。
- **运行器最低版本**：表示运行环境是否具备已声明的宿主能力。

业务功能变化通常只创建新卡带版本和新发行包。只有改变发行包的通用解释、完整性、权限、公开合同或安装语义时，才发布新的 `CF-CRE` 主版本；不得原地改写 v1。

## 4. 包布局

发行归档的根目录必须使用以下布局：

```text
release.manifest.json
hashes.json
signatures/
  publisher.ed25519
public/
  experience.json
  delivery.contract.json
payload/
  manifest.json
  root.flow.json
  assets/
  dlc/
proof/
  package.analysis.json
  portability.json
```

`release.manifest.json`、`hashes.json` 和 `signatures/` 是控制文件；其他每个分发文件必须出现在 `hashes.json` 中。归档不得包含重复路径、绝对路径、`..`、符号链接或未列出的文件。

`payload/` 可以携带由 `CF-FARP` 和可移植 DLC 允许的流程、资产、DLC、模型配方和测试。它不得伪装成普通资产携带任意可执行内容；主动前端和 DLC 仍受描述文件、逐文件哈希、隔离工作进程和沙箱约束。

## 5. 发行清单

`release.manifest.json` 的 `schema` 必须为 `cartridgeflow.release_envelope.v1`。最小结构如下：

```json
{
  "schema": "cartridgeflow.release_envelope.v1",
  "release": {
    "publisher_id": "publisher.example",
    "cartridge_id": "ai.daily",
    "version": "1.2.0"
  },
  "release_id": "publisher.example:ai.daily@1.2.0+sha256:<hashes-json-hash>",
  "runtime": {
    "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
    "flow_contract": {"id": "CF-FARP", "version": "0.9"},
    "min_runner_version": "1.0.0"
  },
  "execution": {
    "placement": "either",
    "required_capabilities": ["media.ffmpeg"],
    "required_permissions": ["filesystem.output"]
  },
  "public_contracts": {
    "experience": {"path": "public/experience.json", "digest": "sha256:<hash>"},
    "delivery": {"path": "public/delivery.contract.json", "digest": "sha256:<hash>"}
  },
  "payload": {"path": "payload", "digest": "sha256:<payload-file-list-hash>"},
  "integrity": {"hashes_path": "hashes.json", "content_digest": "sha256:<hashes-json-hash>"},
  "signatures": [
    {"role": "publisher", "key_id": "publisher-key-2026", "algorithm": "ed25519", "path": "signatures/publisher.ed25519"}
  ]
}
```

`publisher_id`、`cartridge_id`、能力标识、权限标识和密钥标识必须匹配 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`。`version` 和 `min_runner_version` 必须使用语义化版本格式 `主版本.次版本.修订版本`，可附加预发布或构建后缀。

`release_id` 必须严格等于：

```text
<publisher_id>:<cartridge_id>@<version>+<integrity.content_digest>
```

`placement` 只能是 `local`、`cloud` 或 `either`。该字段不授予云端回退权：本地运行只能在用户重新明确选择、发行包允许且云端能力与数据预检通过后，才创建新的云端运行。

## 6. 哈希、内容根与签名

### 6.1 `hashes.json`

`hashes.json` 必须是使用 `cartridgeflow.release_hashes.v1` 架构的 UTF-8 JSON：

```json
{
  "schema": "cartridgeflow.release_hashes.v1",
  "files": [
    {"path": "public/experience.json", "sha256": "sha256:<hash>", "size": 421},
    {"path": "payload/manifest.json", "sha256": "sha256:<hash>", "size": 1840}
  ]
}
```

每个路径必须相对、使用 `/`、无路径穿越且唯一。它不得列出 `release.manifest.json`、`hashes.json` 或 `signatures/*`。每个列出的文件必须存在，并精确匹配字节大小和 SHA-256；归档中每个非控制文件都必须被列出。

`integrity.content_digest` 等于精确 `hashes.json` 字节的 SHA-256，并以 `sha256:` 为前缀。`payload.digest` 等于以路径排序、仅保留 `path`、`sha256`、`size` 三个键的 `hashes.json.files` 中 `payload/` 条目的规范 UTF-8 JSON 的 SHA-256。规范 JSON 的对象键排序且使用紧凑分隔符。至少必须覆盖 `payload/manifest.json`。

静态验证器验证字节摘要和载荷文件清单摘要；它不会从文件名推断哈希，也不信任市场提供的摘要。

### 6.2 签名

至少必须有一个签名描述项，同时满足 `role=publisher`、`algorithm=ed25519`、安全的 `signatures/` 路径和稳定的 `key_id`。发布者签名必须覆盖：

1. `release.manifest.json` 的规范 UTF-8 JSON，不能排除任何字段。
2. `hashes.json` 的精确字节。

签名输入的规范 JSON 按 Unicode 码点排序对象键、使用 UTF-8、没有无意义空白，并且只允许本协议定义的 JSON 值。发行构建器在安装器声明支持验签前，必须公布其规范化实现和测试向量。

本协议现在定义了签名输入和元数据；在当前部分支持状态中，密码学签名验证尚未实现。因此，只有结构合法签名元数据的发行包，在验签器存在前仍不可信，也不能被未来生产运行台安装。

## 7. 公开体验合同

`public/experience.json` 必须使用 `cartridgeflow.cartridge_experience.v1` 架构：

```json
{
  "schema": "cartridgeflow.cartridge_experience.v1",
  "product": {"name": "AI 科技日报", "category": "content.video"},
  "inputs": [
    {"id": "topic", "label": "主题", "type": "string", "required": true, "sensitive": false}
  ],
  "stages": [
    {"id": "prepare", "label": "准备内容"},
    {"id": "deliver", "label": "完成交付"}
  ]
}
```

每个输入和阶段都需要稳定且唯一的 `id` 与用户可见的 `label`。输入 `type` 只能是 `string`、`number`、`boolean`、`enum`、`file`、`object` 或 `array`。运行台专属校验和界面装饰可随卡带版本演进，但不得添加未出现在公开合同中的执行语义。

公开合同任意层级不得包含 `root_flow`、`states`、`execution_plan`、`node_id`、`store`、`context`、`checkpoint`、`prompt`、`system_prompt`、`tool_parameters`、`endpoint`、`command`、`args`、`api_key`、`token`、`authorization`、`credential`、`credentials`、`secret` 或 `openapi_url` 字段。这一限制防止公开界面意外变成流程或连接调试器。

提供发行包字节时，验证器必须从包内这两个固定路径解析公开合同并据此校验；调用方传入的对象只能用于一致性比对，不能替代包内字节。包内合同缺失、不是 UTF-8 JSON 对象，或与调用方对象不一致时，验证必须失败。

## 8. 交付合同

`public/delivery.contract.json` 必须使用 `cartridgeflow.delivery_contract.v1` 架构：

```json
{
  "schema": "cartridgeflow.delivery_contract.v1",
  "primary_artifacts": [
    {"id": "main_video", "label": "主视频", "mime_types": ["video/mp4"]}
  ],
  "attachments": [],
  "revision": {"mode": "new_run"},
  "delivery_states": ["produced", "delivered", "failed"]
}
```

至少必须声明一个主产物。`revision.mode` 必须是 `new_run`：用户点击“再次运行”会创建新的运行和修订，绝不覆盖旧产物。交付状态必须包含 `produced`、`delivered` 和 `failed`；运行器可以增加其他已有文档说明的用户可见状态，但当主产物合同未满足时，不得报告 `delivered`。

交付合同是公开的产品事实。它独立于流程内部的交付节点，也独立于市场的价格、排序、评价或退款政策等主张。

## 9. 资源与数据边界

发行包可以声明角色、所需能力和所需权限，但不得包含具体模型提供者、接口地址、MCP 命令、本地目录、凭据值、凭据引用、用户文件、运行时状态存储、检查点、日志、输入或用户产物。

安装和创建运行时，只能从安装器所在的本机环境或用户明确选择的云端环境解析实际资源：

```text
发行包要求 ∩ 已安装运行器能力 ∩ 用户授权 ∩ 当前健康状态
```

这四项事实必须独立检查。资源名称匹配、旧安装记录、包内声明或云端可用性本身都不充分。缺少要求时，卡带处于不可运行的待绑定状态；不得通过把本地数据静默移至云端来满足要求。

## 10. 兼容性、未知字段与演进

`CF-CRE@1` 是精简的发行封装，不允许通用的可执行扩展机制。

- 新业务功能应进入新卡带版本、载荷、静态资产、已声明输入、阶段或交付产物。
- 新的通用发行语义需要新的 `CF-CRE` 版本和机器快照。
- 运行台必须拒绝未知的必需协议版本、不安全路径、缺失摘要、不支持的必需能力或泄露内部字段的公开合同。
- 仅当后续协议明确标为可选且无语义的描述字段时，运行台才可以忽略未来字段；不得猜测其效果。
- 卡带更新如改变所需权限、所需能力、公开输入结构、数据位置、交付合同或资源角色，必须要求用户明确复核，并在适用时重新绑定。
- 历史运行和产物记录必须保留精确的 `release_id`，不能只保留 `cartridge_id` 或当前激活版本。

这一分离允许业务频繁迭代，同时防止卡带把任意私有语义塞入发行封装。

## 11. 安装生命周期要求

未来的安装器必须按以下顺序执行：

```text
导入或下载 -> 暂存 -> 验证字节 -> 验证签名 -> 兼容性检查
                   -> 权限复核 -> 资源绑定 -> 就绪 -> 激活
```

任何步骤不得覆盖已激活发行包。版本和摘要必须并存，直至没有运行、计划、激活指针或保留产物引用它们。导入失败必须清理暂存目录，并保持当前激活卡带不变。

市场条目、授权记录和审核是独立记录。市场条目可以修改说明或价格，但不能修改发行包字节、`release_id`、公开合同或签名。市场下架会阻止后续获取，不得静默删除本地包或用户产物。

## 12. 稳定验证结果

当前发行构建与静态归档验证实现会产生以下阻断性结果：

| 情形 | 结果码 |
| --- | --- |
| 发行包架构、身份、版本或发行标识无效 | `cre_release_schema_invalid`、`cre_release_identity_invalid`、`cre_release_version_invalid`、`cre_release_id_mismatch` |
| 运行环境或执行声明无效 | `cre_runtime_contract_invalid`、`cre_min_runner_version_invalid`、`cre_execution_placement_invalid`、`cre_execution_requirements_invalid` |
| 公开合同或交付合同无效 | `cre_experience_*`、`cre_delivery_*`、`cre_public_contract_leaks_internal`、`cre_public_contract_file_*`、`cre_public_contract_object_mismatch` |
| 完整性或签名元数据缺失、格式错误 | `cre_digest_invalid`、`cre_hashes_path_invalid`、`cre_signature_*`、`cre_publisher_signature_missing` |
| 包文件路径不安全、缺失、未列出或被篡改 | `cre_bundle_path_invalid`、`cre_hash_entry_*`、`cre_hashed_file_*`、`cre_bundle_file_unlisted` |
| 内容摘要或载荷摘要不匹配 | `cre_content_digest_mismatch`、`cre_payload_digest_mismatch` |

验证器是纯校验：不执行 DLC、不导入卡带代码、不调用网络服务、不检查用户凭据，也不修改文件系统。

## 13. 晋级条件

`CF-CRE@1` 当前仅部分支持。只有在以下条件全部具备后，才能成为可安装和可激活的完整支持：

1. 发行构建器能生成本文要求的精确布局、规范输入、哈希和签名。
2. 密码学验证器能根据配置的信任库验证 Ed25519 签名，并如实处理吊销状态。
3. 运行台安装器具备暂存解压、版本共存、原子激活、资源重绑定、升级、回滚和卸载能力。
4. 公开运行台界面只消费公开合同和公开运行投影。
5. 市场接收端独立重复结构、完整性和策略检查，不信任作者自报结果。
6. 正反向一致性测试覆盖畸形归档、路径穿越、重复文件、签名失败、公开数据泄露、缺少绑定、升级、回滚和产物保留。

在完成晋级前，本协议只是冻结的实现目标，不代表个人用户今天已经可以安装或购买生产级卡带包。
