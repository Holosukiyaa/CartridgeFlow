# CF-FARP@1.2 - Migration material

## From v1.1

Migration creates a new v1.2 revision. Preserve the v1.1 Root Flow and recipe
release as evidence; create redacted source references, a v1.1 blueprint and
fixed instance, then require creator review of a proposed change set and an
explicit semantic freeze. The migration must create a separate immutable
acceptance result with selected change items; it must not alter the proposal or
silently interpret old v1.0 or early v1.1 proposal facts as accepted. Compile only accepted frozen facts into v1.2 CF-FARP
topology. Opening, saving, or running v1.1 MUST NOT migrate it.

## Historical v1.1 material

This file is non-normative CF-FARP@1.1 migration material. It does not add or change runtime semantics.

## 从 v1.0 迁移

v1.0 卡带迁移到 v1.1 必须生成新 revision 或副本：将 Base Contract 更新为 0.3，保留原显式执行计划，在 Manifest 增加精确的 `CF-TUNING@1.0` contract，建立包外开发调优仓库，并发布第一个 `tuning/release.json` 快照。不得把现有 Root Flow 参数静默解释成调优历史；迁移工具应把每个节点的当前效果参数作为显式初始修订，由开发者确认后发布。旧 v1.0 卡带继续按 v1.0 运行。

## 35. 从 v0.6 迁移

迁移到 v1.1 至少完成：

1. Runtime Contract、Root Flow 和 certification target 改为 v1.1；Base Contract 继续独立声明。
2. 建立 Asset Registry，为 Flow、模型配方、prompt、schema、动效、UI、媒体和 fixture 分配稳定 asset ID、media type、size 与 hash。
3. 将节点和组件中的裸包内路径迁移为 `asset:<id>`；悬空引用必须列为 blocker。
4. 将 `kind=ui` 迁移为 `kind=interaction`，明确 display/collect/review mode、component_ref、input binding、结构化 output、allowed_actions、wait_id 与 action schema。
5. 将节点标题迁移为可编辑 `display_name`，保持 states key/node id 不变。
6. 对现有 HTML 做主动内容分类：无脚本内容迁移为 passive template；含脚本、事件属性或其他主动内容的文件不得进入普通资产。
7. 把需要脚本的界面迁移到 Portable DLC descriptor v2 frontend component，拆出外部脚本并逐文件声明 role、media type 与 hash。
8. 建立 Interaction Component Registry，声明 component runtime、支持模式、输入 schema、具名 actions 和最小 Host capabilities。
9. Pending Interaction 升级为 v2，固化 component identity/hash、input revision、allowed actions 和 wait resume identity。
10. 把外部知识库、索引和数据接口统一迁移为 MCP/remote API 工具；随包静态内容迁移为 package asset。
11. 生成 portability report，区分随包携带、本机重新绑定、缺失阻断和禁止打包内容。
12. 重新计算所有 registry、descriptor 和 package hash，运行 v1.1 conformance 和认证，不沿用 v0.6 标签。
13. 把 legacy input/output 与 params 内数据引用迁移为结构化 inputs、outputs 和 bindings。
14. 将真实执行关系转换为带稳定 id 的 `execution_plan.edges`；删除派生 data/resource edges 并由 Analyzer 重建。
15. 生成匹配 source digest 与目标级别的 analysis report，修复 blockers 后才运行、打包或认证。

迁移 MUST 生成新卡带 revision 或副本，不得静默覆盖唯一原件。

迁移工具 MUST 在修改前生成报告，至少列出：旧 Base/Runtime Contract、节点字段变化、隐式 consume、嵌入连接信息、不完整 Tool Contract、不安全副作用、DLC hash 变化和无法自动判断项。

以下变化不得自动猜测：

- 哪个本机资源应绑定某个 role。
- 一个远程操作是否幂等。
- 旧 output 中哪个字段是真实业务消费值。
- 哪些 Artifact 在回滚后仍有效。
- 用户是否授权新的 permission 或 purge_all。
- 旧 HTML 中的脚本究竟只负责呈现还是隐藏了模型、工具、网络或流程控制。
- 旧 UI 按钮对应哪个稳定 action、payload schema 和 Flow route。
- sandboxed component 真正需要哪些 Host capabilities。

这些项必须由开发者明确确认，并写入迁移后的结构化声明。
## 39. v0.6 条款处置矩阵

| v0.6 内容 | v1.1 位置 | 处置 |
|---|---|---|
| 协议定位、关键词、独立 Base Contract | 1-3、6.3、32 | 完整保留；版本升级为独立 v1.1 快照 |
| Manifest、Root Flow 与静态拓扑 | 5-6、10 | 完整保留；Manifest 新增资产和交互组件入口 |
| Process Node、kind、executor、effect | 11-12 | 保留统一 `type=process`；作者模型明确分为能力节点和交互节点 |
| 节点用户层显示 | 11.5 | 扩展：新增可编辑 `display_name`，稳定 id 不随显示名变化 |
| `kind=ui` | 12.9、35 | 替代并废止：迁移为 `kind=interaction`，不保留别名 |
| UI 展示或收集输入 | flow-and-data | 扩展为 component、mode、input binding、structured output、allowed action 和 wait 契约 |
| 卡带静态 assets/prompts/schemas 目录 | 4.20、5、6.7 | 扩展为带稳定 ID、kind、media type、size 和 hash 的 Asset Registry |
| HTML 相对路径或内联内容 | 6.7-6.9、35 | 替代：保存 v1.1 前迁移为 asset/component 引用；主动内容不得作为普通资产 |
| Pending Interaction v1 | flow-and-data | 替代为 v2，增加 component/hash、input revision、allowed actions 和 wait identity |
| Decision Envelope 与 consume | 14-15 | 完整保留 |
| Tool Plan、MCP、Remote 与副作用 | 8、17-18、23 | 完整保留；外部知识和数据接口统一通过工具契约 |
| 模型配方与本机 assignment | 7 | 保留并允许通过 `model_recipe` 资产引用 |
| Store、错误、状态、Checkpoint 与恢复 | 13、19-23 | 完整保留；交互动作纳入相同状态与恢复语义 |
| Artifact、Delivery、fallback 与测试台 | 24-27 | 完整保留；测试台新增组件、action、revision 和脚本安全可见性 |
| Portable DLC descriptor v1 | 28 | 替代为 descriptor v2，frontend 从单 entry 改为具名 component entries |
| Frontend iframe sandbox 与 v2 消息 | 29 | 加强并替代：外部哈希脚本、严格 CSP、无同源 iframe、一次性 MessageChannel 和作用域消息 v1 |
| DLC Worker、Overlay、ownership 与卸载 | 28-31 | 完整保留；卸载残留检查增加 iframe、port 和组件资源 |
| 兼容性、认证和 capability 证据 | 32-34 | 扩展资产、组件、脚本安全、具名动作和 portability report |
| v0.6 认证标签 | 3、35 | 不沿用；v1.1 必须重新认证 |

本矩阵是覆盖审计，不表示 v1.1 运行时可以直接解释 v0.6 卡带。迁移必须生成 v1.1 卡带 revision，完成主动内容审计、重新计算 hash 并重新认证。
## 48. 从 v0.7 迁移

v0.7 卡带迁移到 v1.1 MUST 生成新 revision 或副本，并至少完成：

1. Runtime Contract、Root Flow、Portable DLC protocol 和 certification target 更新为 v1.1，重新计算所有受影响 hash。
2. 把 `input`、`optional_input`、`output` 和隐藏在 params 中的 Store/Artifact 引用迁移为结构化 `inputs`、`outputs` 与 binding。
3. 为每个输入输出补齐 inline schema 或稳定 schema asset reference。
4. 将真实执行关系迁移为 `execution_plan.edges`，data/resource/dependency edge 删除并由 Analyzer 重建。
5. 为每条计划边补齐稳定 id、关系契约、失败、等待、汇合或循环信息，解决重复、冲突、悬空目标和未界定循环。
6. 检查每个 required input 在所有可达分支、失败继续、resume 和 rollback 路径上的可用性。
7. 把模型、工具、MCP、远程资源、组件、资产和 Artifact 依赖改为稳定角色或 identity。
8. 显式声明影响业务质量的 fallback；运行结果增加 actual executor、used_fallback 和 reason 证据。
9. 生成 `cartridgeflow.flow_analysis.v1` 报告，修复目标级别 blocker，并保存 source digest evidence。
10. 运行 v1.1 conformance，重新认证；不得沿用 `cf-farp-0-7-certified`。

以下项目不得自动猜测：

- 多个可能 producer 中哪个才是业务来源。
- 字符串 input 中逗号究竟是分隔符还是 key 内容。
- params 内某个字符串是数据绑定、普通文本还是秘密。
- 工程线是否曾被作者误当作控制线。
- 分支缺失数据应使用 default、optional、merge 还是改变业务路径。
- fallback 是否符合产品质量与对外交付承诺。
- 资源、权限、收费接口和外部副作用是否获得授权。

这些项目必须形成 confirm/manual finding，由开发者或负责人明确决定。

## 49. v0.7 条款处置矩阵

| v0.7 内容 | v1.1 位置 | 处置 |
|---|---|---|
| 协议身份、Manifest、资产与 Base Contract | 1-10 | 完整保留并升级为独立 v1.1 快照 |
| `next`、routes 与顶层 `edges` | execution-plan | 替代：迁移为唯一可执行事实 `execution_plan.edges` |
| Process Node、kind、executor、effect | 11-12 | 完整保留 |
| 字符串 `input`、`optional_input`、`output` | 11、42、48 | 替代：v1.1 作者事实使用结构化 inputs/outputs/binding |
| Store、数据链与 provenance | 13、42、44-45 | 加强：增加 schema 兼容、路径顺序与分支确定赋值 |
| Decision、Consume 与 Pending Interaction | 14-16 | 完整保留；输入输出必须映射结构化端口 |
| Tool Plan、工具、副作用与 replay | 17-23、46 | 完整保留；纳入资源与 policy 静态分析 |
| Artifact、Delivery 与 fallback | 24-27、42、46 | 加强：Artifact 端口结构化，业务 fallback 强制可见 |
| Portable DLC、sandbox、Overlay 与卸载 | 28-31 | 完整保留；descriptor protocol 升级并重新计算 hash |
| compatibility 与 certification | 32-33、44、46 | 加强：必须验证目标匹配且 source digest 新鲜的分析报告 |
| structure/data chain diagnostics | 34、44-46 | 替代并扩展为统一 Flow Analyzer 与 finding contract v1 |
| 前端自行推导工程关系 | 41、45、47 | 废止为权威来源；前端只能消费 Analyzer 投影或过渡兼容结果 |
| v0.7 认证标签 | 3、33、48 | 不沿用；v1.1 必须重新认证 |

本矩阵是覆盖审计，不表示 v1.1 Runner 可以直接解释 v0.7 卡带。迁移必须生成 v1.1 Authoring Facts、全量分析报告、新 hash 和新认证证据。
## 55. 与历史版本的迁移边界

从 0.8 或 0.9 迁移到 1.1 是显式创作操作：将旧控制事实转换为执行计划、补齐失败边、建立调优仓库与首个配方发布、重新编译、重新分析、重新做资源预检并重新认证。历史卡带继续按各自协议运行；运行器、前端和 AI 不得在保存、打开或运行时静默升级它们。
