# 个人运行台卡带发行、安装与市场桥接架构

> 状态：设计基线，尚未代表运行台或市场已实现。
>
> 范围：开发台源工程如何成为可分发卡带；个人运行台如何安装、预检、绑定、激活、升级、回滚和卸载；市场如何引用不可变发行物。
>
> 不在本文实现：支付与分账、卡带内容加密、企业组织治理、节点级跨 Runner 迁移和任意第三方代码执行。

## 1. 决策

个人运行台不是开发台的另一张皮。开发台管理源工程和完整 Flow；运行台消费经过验证的卡带发行物，只展示用户输入、公开阶段、必要交互和交付结果。

因此，开发台与运行台之间的唯一稳定桥梁是 **不可变 Release**，而不是共享目录、编辑器 API、Root Flow JSON 或开发机资源配置。

```text
开发台源工程
  -> package / publish 门禁
  -> Release Builder
  -> 已签名的不可变发行物
  -> 市场条目或手动导入
  -> 运行台安装器与本机资源重绑定
  -> 激活的卡带版本
  -> Run 与产品 revision
```

用户购买或安装的是“可生产某种结果的卡带产品”，不是 Flow、Prompt、节点或某台开发机的配置快照。

## 2. 不可破坏的边界

1. **运行台不读取开发工程。** 不能从 `dev_cartridges`、开发台 API 或工作台草稿加载卡带；它只能加载已验证的 Release。
2. **用户界面不接收内部执行细节。** UI 只消费公开体验合同和公开运行投影，不能取得 Root Flow、节点参数、Prompt、Store、工具参数、检查点或完整异常链。
3. **本机资源属于安装者。** 模型实例、MCP/API 地址、命令、文件路径、凭据和额度不随卡带传播，必须由运行台重新绑定和授权。
4. **发行物不可变。** 一个 Release 由 `publisher_id + cartridge_id + version + content_digest` 唯一确定；同一身份的内容不得被覆盖。
5. **Run 固定到实际 Release。** 创建 Run 时写入 Release digest、体验合同 digest、交付合同 digest 和资源绑定摘要；更新卡带不改变历史 Run 或产物。
6. **本地运行默认不依赖云端。** 市场、登录、下载和云端 Runner 可以增强体验，但不能成为用户已安装、本机可运行卡带的隐式前提。
7. **未验证即不可激活。** 下载成功、解压成功或 Manifest 可解析都不等于可运行；完整性、发布者信任、协议兼容、能力、权限和资源预检必须逐项成立。
8. **公开包不是 DRM 承诺。** 第一版可以隐藏内部 Flow 于运行台 UI，但本地可读取的公开包不构成代码或 Prompt 保护；受保护包须另行设计，不得以“隐藏画布”冒充加密。

## 3. 术语与对象

| 对象 | 定义 | 是否可变 |
| --- | --- | --- |
| Source Project | 开发台可编辑的卡带源工程。 | 可变 |
| Dev Export | 供开发、联调和离线测试使用的 ZIP。 | 可重建，不可当市场发行物 |
| Release Candidate | 通过打包检查但尚未发布的候选发行物。 | 可废弃，不可覆盖已发布版本 |
| Release | 已签名、内容固定、可由运行台安装的发行物。 | 不可变 |
| Listing | 市场中的产品展示、价格、截图、介绍、更新说明和可见性。 | 可变，必须引用 Release identity |
| Entitlement | 用户取得某 Release 或版本范围的安装/使用资格。 | 可更新，不进入卡带内容 |
| Installation | 某一设备保存的 Release 副本和本机绑定状态。 | 可升级、可停用 |
| Activation | 当前默认用于新 Run 的已安装版本指针。 | 可切换 |
| Run / Revision | 一次生产及其交付物；固定引用实际运行的 Release。 | 历史不可重写 |

`CF-FARP` 继续描述 Flow 的创作、分析和执行语义。本文提出的发行层应独立定义为 `Cartridge Release Envelope v1`（简称 `CF-CRE@1`），不得为了市场字段直接改写已发布的 CF-FARP 正文。

## 4. 发布、市场与运行的关系

```text
                    发布者私钥
                        |
Source Project -> Release Builder -> Release Blob + content digest + signature
                        |                         |
                        |                         +-> 手动导入文件
                        v
                 市场审核/索引
                        |
                   Listing + Release record + Entitlement
                        |
                        v
Runtime Package Manager -> 暂存验证 -> 资源绑定 -> 已安装版本 -> Active pointer
                                                            |
                                                            v
                                                     Runner 创建 Run
```

市场不拥有用户本机凭据、输入文件、内部 Store 或本地产物。Runner 不信任市场展示文案；它只信任经过签名和校验的 Release 合同。开发台不应直接向用户运行台推送任意文件，市场或手动导入都必须经过同一个安装器。

## 5. `CF-CRE@1` 发行包

### 5.1 包布局

Release 使用新的根布局，避免与当前开发 ZIP 的“根目录就是源包”语义混淆：

```text
<id>-<version>.cartridge
  release.manifest.json        发行身份、兼容性、权限和内容根摘要
  hashes.json                  所有分发文件的路径、大小和 SHA-256
  signatures/
    publisher.ed25519          发布者对内容根的签名
    marketplace.ed25519        可选：市场审核/分发签名
  public/
    experience.json            用户输入、公开阶段、交互和结果展示合同
    delivery.contract.json     主产物、附件、质量门槛与 revision 规则
  payload/
    manifest.json              运行时 Manifest
    root.flow.json             运行时 Root Flow
    assets/                    随包静态资产与 registry
    dlc/                       经协议允许的声明及受限代码
  proof/
    package.analysis.json      package target 分析证据
    portability.json           可移植性报告
    certification.json         publish target 认证证据（需要时）
```

所有文件均由 `hashes.json` 覆盖。`release.manifest.json`、`hashes.json` 和签名文件以外，不允许未登记的可执行或主动内容。常规资产、Flow、模型配方和 Prompt 仍只能交给结构化解析器；Portable DLC 继续遵守其 descriptor、隔离 Worker 和 iframe sandbox 规则。

### 5.2 发行 Manifest 的最低字段

```json
{
  "schema": "cartridgeflow.release_envelope.v1",
  "release_id": "publisher.example:ai.daily@1.2.0+sha256:...",
  "publisher": {"id": "publisher.example", "key_id": "key-2026-01"},
  "cartridge": {"id": "ai.daily", "version": "1.2.0"},
  "content_digest": "sha256:...",
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
    "experience": {"path": "public/experience.json", "digest": "sha256:..."},
    "delivery": {"path": "public/delivery.contract.json", "digest": "sha256:..."}
  },
  "payload": {"path": "payload", "digest": "sha256:..."},
  "proof": {"package_analysis": "proof/package.analysis.json", "portability": "proof/portability.json"}
}
```

字段名称可在 `DIST-001` 中定稿，但以下原则固定：发行身份、协议版本、Runner 兼容性、能力要求、公开合同、内容摘要和发布者身份必须由同一签名覆盖。市场价格、排序、评价和促销不应写入 Release Manifest。

### 5.3 公开体验与交付合同

`experience.json` 是运行台展示卡带的唯一入口，至少声明：

- 产品名称、封面资产引用、短描述和类别。
- 用户可输入的字段、文件类型、默认值、校验与敏感性提示。
- 用户能理解的业务阶段、允许的交互、公开错误码和可执行动作。
- 是否支持本机、云端或任一 Runner，及各模式的用户可见数据去向。

`delivery.contract.json` 至少声明：

- 一个或多个主产物的格式、最小质量规则和预览能力。
- 附件、结果摘要、保留策略和下载规则。
- `produced`、`approved`、`delivered`、`failed` 等用户可见交付状态。
- “再次运行”创建新 revision 的规则，绝不覆盖旧交付物。

公开合同不能包含节点 ID、工具 URL、模型提供商、私有路径、密码、内部错误栈或可执行表达式。Flow 到阶段的映射仅保留于执行侧；无法可靠计算时只上报阶段状态，不能伪造百分比。

### 5.4 内容完整性与签名

Release Builder 必须以稳定路径排序、规范化 JSON 和逐文件 SHA-256 计算内容根。发布者使用 Ed25519 私钥签名内容根和规范化后的发行 Manifest；私钥只能保存在发布者安全存储或受控发布服务，不进入 Source Project、Release 或市场条目。

运行台的信任判断分为三层：

1. **完整性**：每个文件与 `hashes.json` 一致，不能有重复、未登记、越界或符号链接文件。
2. **来源**：签名可由本地信任库、市场发布者目录或用户明确导入的公钥验证。
3. **状态**：发行物未被撤销，或用户已明确接受离线情况下无法获得撤销信息的风险。

手动导入可以支持未知发布者，但必须以“外部来源”明确显示发布者指纹、权限、能力和无市场审核状态，不能用与官方市场相同的信任标记。市场服务器可以追加审核签名，但运行台仍需独立验证 Publisher 签名和内容摘要。

## 6. 不随包传播的内容

以下内容属于安装者、Runner 或一次 Run，Release Builder 必须拒绝：

| 内容 | 正确位置 |
| --- | --- |
| API Key、Token、Cookie、私有 URL、MCP command/args | 本机或云端安全存储与资源绑定 |
| 开发者机器路径、已绑定资源 ID、模型实例 | 安装后重新绑定 |
| `.env`、日志、缓存、模型权重、`node_modules`、临时文件 | 不分发 |
| Store、检查点、运行事件、失败栈、上传输入 | Run 存储 |
| 用户生成的视频、文档、音频、下载记录 | 用户产物归档 |
| 市场价格、订单、用户评价、支付状态 | 市场服务 |

当前 `package.local-bindings.json` 可以保留为开发期审计证据，但不能被运行台解释为用户资源绑定。运行台应从 `resource_requirements` 和 Runner capability 重新生成绑定状态，并在创建 Run 时记录不含密钥的绑定摘要。

## 7. 开发台 Release Builder

### 7.1 构建步骤

```text
冻结 Source Project revision
  -> package target 全量分析
  -> package hygiene 检查
  -> portability 报告
  -> publish target 认证（市场提交时）
  -> 编译 public experience / delivery contracts
  -> 收集允许的 payload 文件与资产 registry
  -> 生成 hashes、内容根和 proof
  -> 签名
  -> 在干净 Runner 环境执行安装模拟
  -> 输出 Release 或拒绝构建
```

构建前后都要检测源摘要：分析报告、可移植性报告和认证报告必须对应同一 Source digest。报告过期、存在 blocker、存在禁止文件、缺少必需资产或资源声明不完整时，Builder 不能输出 Release。

### 7.2 当前 ZIP 的定位

现有开发台 `/api/cartridges/{id}/package` 会生成 `.cartridge.zip`，并附带兼容性、Flow 分析、本机绑定描述和 portability 报告。它适合作为 `dev_export` 的实现基础，但不应直接改名为市场包。

原因包括：它没有 Release identity、内容根签名、发行版本并存、公开体验合同、市场审核身份或授权记录；而且当前运行时语义和 CF-FARP 0.9 支持矩阵仍为 `partial`。在 `CF-CRE@1` 落地前，现有 ZIP 只服务开发、测试和受控手动导入。

### 7.3 可复现性

同一 Source digest、协议版本、Builder 版本和允许资产集合必须生成相同的内容根。ZIP 文件的时间戳不同不必阻止构建，但不得改变签名所覆盖的逻辑内容。Builder 需输出 Builder 版本、协议版本和构建时间用于诊断，不能把时间戳当作内容身份。

### 7.4 大媒体与外部依赖

用户生成的 1 GB 视频、运行日志和结果附件不属于包。首版发行包只带必要的静态资产；大模板或可选能力包应由独立、带摘要的分段下载提供。运行台不能因为下载封面或可选媒体失败而误报卡带已交付。

模型权重、FFmpeg、浏览器自动化、GPU 和 stdio MCP 属于 Runner 能力包或用户资源，不能嵌入卡带。卡带只能声明要求、版本范围、安装策略和预检规则。

## 8. 运行台安装器

### 8.1 安装状态机

```text
downloaded/imported
  -> staged
  -> integrity_verified
  -> trusted
  -> compatible
  -> needs_binding
  -> ready
  -> active

任一步失败 -> rejected / quarantined -> 清理暂存内容
```

`ready` 表示发行物已验证但尚未必然是默认版本；`active` 表示可为新 Run 选用。运行台不得在下载、解压或首次打开页面时自动授予敏感权限或启动外部程序。

### 8.2 安装步骤

1. 将网络下载或手动文件导入暂存目录；市场下载必须支持流式传输，不以 Base64 HTTP JSON 承载大包。
2. 检查归档成员数、压缩后/解压后大小、重复路径、路径穿越、符号链接和文件类型。
3. 读取并校验 `release.manifest.json`，验证所有文件摘要与签名，再解析 payload Manifest。
4. 比较 Base、Flow 协议、Runner 版本、目标平台和能力包兼容性。当前 Base 不支持的协议或 capability 必须拒绝激活，而非仅显示 warning。
5. 展示用户可理解的权限、执行位置、数据离开设备的条件、预计依赖安装和成本边界；用户逐项确认。
6. 执行资源重绑定与健康预检。缺少资源可保持 `needs_binding`，不能创建生产 Run。
7. 将验证后的包移动到版本目录，写入仅含摘要的安装记录，最后原子更新 Active pointer。

下载或导入失败不能损坏已激活版本。所有暂存目录必须在成功切换或失败清理后消失，不得成为 Registry 的可见卡带来源。

### 8.3 本机绑定与能力选择

卡带声明的是角色和能力，例如“需要只读 HTTP 检索”“偏好 GPU”或“需要输出目录写入权限”；用户选择的是实际本机模型、MCP、目录、云端账户或能力包。

```text
卡带要求 ∩ 已安装 Runner 能力 ∩ 用户已授权能力 ∩ 当前健康能力
```

四者缺一不可。资源绑定记录不保存密钥，而是保存角色、资源身份摘要、可用状态和最后验证时间。运行前重新检查；运行期间绑定变化时，按 Run 的资源快照拒绝或要求用户显式恢复，不能静默换到另一个资源。

本地 Runner 离线或缺少能力时不得静默转云端。只有 Release 声明允许、用户确认数据可离开设备、云端满足全部能力且用户显式选择时，才能创建新的云端 Run。

### 8.4 版本并存、升级与回滚

安装路径必须按版本和 digest 保存，而非仅按 `cartridge_id` 覆盖：

```text
installed/<publisher>/<cartridge_id>/<version>/<digest>/
active/<publisher>/<cartridge_id> -> release_id
```

- 新版本以暂存安装和预检完成后才可激活；默认不自动更新。
- 已运行或被历史产物引用的版本不得覆盖或删除。
- 回滚只是把 Active pointer 切回一个已安装、兼容且仍可信的 Release；它不修改历史 Run。
- Release 若改变权限、能力、输入 schema、交付合同或资源要求，必须要求重新确认和必要的重新绑定。
- 私有数据迁移必须是显式、可恢复、受版本约束的独立操作；Release 不能携带任意迁移脚本。

### 8.5 卸载与撤销

卸载前检查活动 Run、计划和其他依赖。默认卸载删除 package 与卡带私有数据，保留用户产物及其 Release identity；彻底删除用户产物需要独立高风险确认。

市场下架只阻止新安装，不应静默删除用户已安装版本。安全撤销必须展示原因、影响版本、可用修复版本和数据处理方式；高危撤销可以阻止新 Run，但应保留已生成产物和用户可理解的恢复路径。

## 9. 市场桥接

### 9.1 市场职责

市场是目录、分发和授权服务，不是 Runner，也不是开发工程仓库。它保存：

- 发布者资料、公钥、信任状态和撤销信息。
- 不可变 Release Blob、内容摘要、审核结果和兼容性索引。
- 可变 Listing：封面、演示产物、说明、分类、价格、版本说明和可见性。
- 用户 Entitlement、下载记录、安装来源和更新通知。

Listing 在安装前必须展示：实际主产物示例、用户输入、所需本机/云端资源、权限、数据位置、预计费用或额度、预计时长、失败限制和是否可离线运行。它不应以“AI 一键完成”掩盖关键资源和成本。

### 9.2 首版市场

市场首版只支持免费精选卡带与手动导入：

1. 作者由开发台生成候选 Release。
2. 市场在服务端重新执行结构、摘要、签名、协议、安全和审核检查，不能只信任作者上传的报告。
3. 审核通过后建立不可变 Release record，再将其挂到 Listing。
4. 用户从市场下载或安装；运行台记录 `market_release_id` 和安装来源。
5. 市场只提示可用更新，用户在查看变更、权限和兼容性后主动安装。

支付、分账和付费包不进入首版，但数据模型必须预留 `entitlement` 与 `license_policy`。免费 Release 可完全离线验证；付费 Release 的离线收据、设备约束和撤销策略必须在独立商业与隐私设计中决定，不能在没有明确政策时暗中要求用户长期联网。

### 9.3 受保护包的后续边界

受保护包可以在未来改变 payload 的存储和解密方式，但不能改变 `release.manifest.json`、公开体验合同、交付合同、能力/权限声明、版本身份或安装状态机。即使引入保护，所有用户数据边界、Runner 预检和公开交付证据仍保持一致。

## 10. 公开运行体验

个人运行台的产品页和任务页只使用 `experience.json`、`delivery.contract.json` 与 `PublicRunProjection`：

```json
{
  "run_id": "run_xxx",
  "release_id": "publisher.example:ai.daily@1.2.0+sha256:...",
  "status": "running",
  "runner_location": "local",
  "stage": {"id": "produce", "label": "正在生成成品"},
  "interaction": null,
  "result": null,
  "error": null
}
```

产品详情应显示主产物、附件、输入 revision、卡带版本、运行位置、可见外部调用摘要、交付状态和恢复入口；不显示节点图、Prompt、Store 或内部工具参数。`再次运行` 创建新的输入和产品 revision，不能复用或覆盖上一次的产物目录。

普通用户不需要理解 `MCP`、`Runner` 或 `Flow`。界面可使用“连接与资源”“在此设备处理”“云端处理”等产品语言；技术身份仍保留于高级详情和支持诊断中。

## 11. 当前基线与缺口

| 领域 | 当前可复用基础 | 发行架构仍需实现 |
| --- | --- | --- |
| 开发打包 | 现有 ZIP 导出、package/production 预检、分析和 portability 报告。 | `CF-CRE@1` 目录、内容根、签名、公开合同、安装模拟。 |
| 导入安全 | 已限制 ZIP 大小、成员数、解压总量、路径穿越和符号链接。 | 流式下载、Release 摘要/签名验证、信任库、隔离区和撤销状态。 |
| 卡带安装 | 已导入到 `installed_cartridges`，并可卸载、保留用户产物。 | 版本并存、原子激活、回滚、活动 Run 保护和安装记录。 |
| 资源可移植性 | 已区分随包内容、本机重绑定、禁止文件与缺失项。 | 面向运行台的绑定向导、授权记录、能力健康检查和绑定迁移。 |
| 执行协议 | CF-FARP 0.9 已是当前正式正文。 | 当前 Base 声明仍为 partial，市场只能发布真实已支持的 feature profile。 |
| 市场 | 无市场服务。 | 发布者身份、审核、Listing、Release blob、Entitlement 与更新索引。 |

当前 `/api/cartridges/import` 的 `replace` 模式会替换同 `cartridge_id` 的安装目录，因此只能作为开发期导入基础。个人运行台不得沿用该覆盖策略作为升级实现。

## 12. 实施顺序与验收

### DIST-001：`CF-CRE@1` 与产品合同

定义 Release Manifest、`experience.json`、`delivery.contract.json`、文件哈希、签名输入和安装状态记录 Schema；与 CF-FARP 分别版本化。

验收：同一 Source digest 构建出相同 content digest；任何公开合同都不能包含内部节点、凭据、私有 URL 或本机路径；协议变更不会原地修改 CF-FARP 历史版本。

### DIST-002：Release Builder 与验证器

将现有 package/publish、卫生、portability 和认证能力接入 Builder，输出 Release Candidate、proof 与签名；在干净临时 Runner 中安装模拟。

验收：密钥、日志、缓存、权重、Run 数据、绝对路径和用户产物都会阻断构建；篡改任意已登记文件会使验证失败；未通过当前 Base capability 的功能不能标记可发布。

### DIST-003：个人运行台安装器

实现文件与市场下载的统一暂存安装、签名校验、权限/资源绑定、版本并存、原子激活、回滚、计划关联和卸载。

验收：失败安装不影响当前 Active 版本；升级后的旧版本仍可解释历史 Run；本机资源不离开设备；缺少授权或能力时卡带只能停在 `needs_binding`，不能开始生产。

### DIST-004：免费精选市场闭环

实现发布者公钥、服务端复检、不可变 Release record、Listing、免费 Entitlement、下载、安装来源和更新提示。

验收：用户能安装两张独立卡带并得到产品交付；市场条目与实际 Release digest 一一对应；未知来源导入不会冒充市场审核；断网时已安装的免费本地卡带仍可运行。

## 13. 首批端到端验证

用两张范围受控、真实生产的卡带验证，而不是用空白示例：

1. **AI 科技日报**：验证文件输入、媒体能力、主视频与文档附件、定时任务、Local/Cloud 选择和 revision 交付。
2. **本地资料整理或接口适配卡带**：验证本地文件/MCP 能力、资源重绑定、敏感输入不出设备、fixture 和失败恢复。

每张卡带都必须走完“源工程 -> Release -> 安装 -> 预检/授权 -> Run -> 产物交付 -> 更新 -> 回滚 -> 卸载保留产物”链路。任何一步只能通过手工操作、拷贝开发目录或绕过安装器完成，都不算个人运行台发行能力已落地。

## 14. 明确不做

- 不把开发 ZIP、Flow JSON 或开发台资源快照直接当作市场商品。
- 不让浏览器直接控制本地 Agent、启动 stdio MCP 或访问用户文件。
- 不把签名、审核或市场条目当作凭据、权限和 Runner 预检的替代。
- 不自动把本地 Run 转到云端，不自动升级导致用户结果漂移。
- 不以“受保护包”承诺在用户机器上无法被读取；实际保护边界须单独证明。
- 不在首版同时完成支付、分账、订阅、DRM、企业私有市场和组织治理。
