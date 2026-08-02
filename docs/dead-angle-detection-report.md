# CartridgeFlow 死角复核与修复报告

> 复核日期：2026-08-02
>
> 范围：`src/`、`scripts/`、`config/`、`protocol/`、`docs/`
> 依据：当前工作树、协议治理规则、可执行测试与生产构建

## 结论

原报告是 11 轮扫描的累加草稿，不是稳定的问题台账。它的页首写 59 项，后续依次写
76、87、92、93、95、96、101、103 项，之后又增加 UX1-UX7；同一问题会在多轮中
重复计数，已修复项和误报也仍保留在总数中。因此“103 个问题（高 16 / 中 40 /
低 47）”不能作为当前缺陷数。

本次没有按累计数字机械修改，而是重新读取现有实现并按四种状态归档：

- **本次修复**：能以局部改动闭环，且有测试或构建证据。
- **此前已修复**：当前工作树在本次复核前已经不存在该问题。
- **误报/设计选择**：报告结论与代码、浏览器安全模型或项目边界不符。
- **后续工作**：问题成立，但需要协议发布决策、大模块拆分或专门的产品设计。

## 本次修复

### 安全与运行边界

| 原编号 | 处理结果 |
|---|---|
| H1 | `root_flow.entry` 与 `welcome.entry` 统一经过 package-relative resolve 和包边界校验；registry 再做防御性检查。 |
| H3 | 待审核 HTML 的内嵌预览改为无脚本 sandbox；新窗口只打开受 CSP 约束的静态外壳，原内容位于无权限内层 iframe。 |
| H8 | 缺失输入跟踪改用 `ContextVar`，同一 executor 的并发运行不再共享可变实例字段。 |
| N11 | 卡带启用 manifest 权限后，节点权限进入 fail-closed 执行门禁：未声明的权限 ID、pending 和 denied 均阻断节点；`always_allow` 自动授权，`deny` 自动拒绝，`ask_each_time` 每次执行后重新 pending。空权限表保留旧卡带兼容行为。 |
| N16/N27 | POSIX 本地配置、LLM 密钥、发布私钥和信任存储写入后限制为 owner-only `0600`。 |
| N25 | 内置 filesystem 的读、写、追加增加字节上限，追加同时限制目标文件总大小。 |
| N37 | resource catalog 与 external adapter 都拒绝非法 `auth_scheme`，封堵 CRLF header 注入。 |

### 数据一致性与运行语义

| 原编号 | 处理结果 |
|---|---|
| H6 | authoring `blocker` 现在产生真实 `severity: blocker`。 |
| H7 | 可编辑 ExecutionPlan v1 画布恢复节点、边的增删改能力；是否可写只由 cartridge editable 状态决定。 |
| H9-H11 | 边与注释保存串行化；保存失败回滚到最后成功快照；父组件不再吞异常；保存期间不由 props effect 覆盖乐观状态；切换卡带时按 `flowId` 重建工作台，旧请求不能回写新卡带状态。 |
| M2 | 长轮询加入代次令牌，切换卡带、卸载或开始新轮询后旧任务停止写回状态。 |
| M3 | 边比较改为按 ID、与数组顺序无关。 |
| M5 | React Flow 的 key 不再包含显示模式，切换投影不再强制重建实例。 |
| N14 | 任意正常 terminal 名称都归一为 run status `completed` 并立即收束，不再把节点 ID 泄漏为状态。 |
| N29 | active event loop 场景通过独立线程运行 coroutine，不再二次调用正在运行的 loop。 |
| N30 | conformance selector 只匹配完整 case ID 或 `.<selector>` 后缀。 |

### 前端、工具与维护链路

| 原编号 | 处理结果 |
|---|---|
| M6/M8/L4 | 开启 TypeScript `strict`；RunInputDialog 使用 `CartridgeInput[]`；API 默认泛型改为 `unknown`。 |
| M7 | InteractionAssetEditor 在 `componentRef` 变化时重新加载正确组件。 |
| N1 | CSS 红线扫描从 `src/styles` 扩大到整个前端 `src`，现覆盖 15 个 CSS 文件。 |
| N2/N3 | API 增加默认 60 秒超时和外部 AbortSignal 转接；Flow analyze 统一走 API wrapper 并展示失败状态。 |
| N4/M22 | 修复治理快照和 runtime developer toolkit 的失效路径。 |
| N5 | 环境命令改用跨平台 quoting 解析，带引号的可执行文件路径可正常探测。 |
| N6 | launch 只把命令行中包含当前 frontend 绝对路径的 5173 listener 视为可管理 Vite 进程。 |
| N7 | conformance 现在包含根级 `scripts/tests/test_*.py`，并对未登记的新测试目录 fail closed。 |
| N9/M23 | README 明确相对/绝对 data root 语义，以及产品、私有前端包、Base implementation 三种独立版本。 |
| N13 | 视频封面字体候选补充 macOS PingFang/STHeiti 与 Linux Noto/WenQuanYi。 |
| N18/N19 | sandbox renderer 对缺失 entry hash 返回稳定错误，并给路径边界条件补显式括号。 |
| N20 | Mentor 历史保留 system prompt 和至多最近 12 条消息，并丢弃截断后孤立的 assistant 开头，避免每轮累计完整 6000 字符快照。 |
| L10/L13/L18/L19 | 删除无效 eslint 注释；补全文档测试目录；launch 改用 `npm ci`；package 与 lockfile 声明 Node >=20.19。 |
| UX2/UX4 | 运行历史显示节点业务名称并保留内部 ID tooltip；时间显示完整日期和分钟。 |
| UX5 | 运行按钮接入统一创作就绪报告；输入、模型、工具和本机资源存在阻塞时 fail-closed，并提供可跳转的业务化修复入口。每次点击运行都会重新检查，检查请求失败也不再显示假绿色状态。 |

## 此前已修复

这些结论在本次开始前的工作树中已经不成立：

- **H4**：工程资源节点判定已统一。
- **H5**：批量删除已经遍历全部节点并汇总错误。
- **M1**：每条 toast 已有独立清理定时器。
- **M9**：颜色输入比较前已经 trim。
- **L15/N10**：旧 frontend/backend bug report 已从当前工作树移除，由本报告取代。

## 误报或应保持现状

| 原编号 | 复核结论 |
|---|---|
| H2 | `sandbox="allow-scripts"` 且无 `allow-same-origin` 的 iframe 是 opaque origin，向它初始化通信必须使用 `postMessage('*')`。接收侧同时校验 `event.source`、nonce、scope 和消息 schema，不能直接改成 host origin。 |
| H16/L11 | `output/` 和运行输出是被忽略的本地材料，不属于发布源码缺陷；本次不替用户删除本地文件。 |
| M13 | 全局 `letter-spacing: 0` 符合当前设计约束，不是功能 bug。 |
| M21 | 单独给 cryptography 设置上界没有可验证收益；依赖策略应整体制定。 |
| M24 | favicon 已存在于 `public/favicon.svg` 并由 index 引用，不是 404 缺陷。 |
| L3 | React root 非空断言是固定 HTML shell 下的标准入口约束。 |
| L5/L6 | parser 返回值被有意丢弃以执行校验；`getNodePreflightIssues` 存在跨文件调用，原“死导出”结论错误。 |
| L12/L16 | 测试文件长度不是行为缺陷；已发布的历史协议快照不可原地改写。 |
| N8/N12/N15/N17/N21/N24 | 分别属于已有 root 解析、显式兼容层、恢复状态机、loopback 端口竞争、同步线程调用链和 worker SDK 导入边界，当前证据不足以按漏洞修改。 |
| N32/N34/N35 | Base 能力不必与单一协议词表同构；历史快照 hash 相同和正文行数短本身不能证明协议错误。 |
| N36 | 前端通过 `/api/lab/flows` 聚合 dev/installed/builtin，并已有 workspace 浏览、克隆和导入入口；“installed 无法浏览或运行”与当前实现不符。 |
| UX6 | 事件数据已经放在折叠的 `details` 中并格式化输出，原结论已过期。 |

## 后续工作

以下项目成立或具有合理风险，但不适合在本次局部修复中强行完成：

| 范围 | 后续项 | 原因 |
|---|---|---|
| 模块边界 | H12-H14、M10、M18-M20 | 拆分 main/runner/node executor/FlowGraph/TestBench 会改变大量所有权边界，需要独立重构和回归计划。 |
| 前端测试 | H15 | 本次增加了严格类型、静态断言和后端回归，但尚未引入 Vitest/React Testing Library；应围绕边保存回滚和权限 UI 建立组件测试。 |
| 性能/CSS | M4、M11-M12、M14-M15、L1-L2/L7-L9 | 属性能测量、死代码清理和类型/CSS 债务，不与安全修复混做。 |
| Worker 隔离 | N22-N23/N26 | stdout 流式上限、POSIX RLIMIT 和 journal retention 需要修改 worker 协议与跨平台进程测试。 |
| 请求体 | N28 | upload/archive 已有专门上限；其余写端点仍需要统一 ASGI streaming body limiter，而不只是信任 Content-Length。 |
| 协议治理 | N31/N33 | FARP 1.0 capability/profile 与 Base 声明的对称性需要协议所有者决定。发布快照不可在普通 bugfix 中改写；治理审计应在决议后加入相应门禁。 |
| 产品体验 | UX1/UX3/UX7 | 节点生产数据、非 HTML 交付主视图和独立运行/结果模式仍属于后续产品设计工作。**UX1 修正**：复核确认运行时数据流完整——`runner.py:661-663` 在 `lab_node_executed` 事件 data 注入 `input_value`/`output_value`，`runState.ts:53-118` 消费后 compact 卡片与 NodeDetail runtime section 均可见；剩余差异仅是 **detailed 视图模式运行时未显示 in/out 值（与 compact 不对称）**，属可选的展示增强而非"数据不可见"。 |
| 依赖复现 | L17 | Python 顶层依赖已固定大部分版本，但完整传递依赖锁定需要确定支持平台和发布流程。 |

## 验证证据

- `python scripts/run_conformance.py --quiet`：**390 tests：389 passed，1 skipped**；128 capabilities verified，17 partial，0 failing；生成的 `latest.json` 已通过标准 JSON 解析校验。
- `npm run typecheck`：TypeScript strict 检查通过。
- `npm run build`：生产构建通过。
- `npm test`：静态断言通过；扫描 **15 个 CSS / 724 个 !important**，低于 730 红线。
- Playwright 实机浏览：设计画布、运行输入、历史切换和卡带双向切换均无页面异常或失败请求；注入布局保存 500 后，13 个节点坐标全部回滚，且无未处理 Promise。无 AI 搭建回归进一步验证了节点点击预配置、字段改名/换序后稳定键、模型一键绑定、统一就绪复检、工具读取、人工确认、点击新增自动布局和业务视图术语边界；20 个节点逐对检测 0 重叠，桌面 125% 缩放与 390px 窄视口无横向溢出或不可达操作，浏览器控制台错误为 0。
- 新增回归覆盖：路径逃逸、并发缺失输入、权限模式、terminal 状态、认证头注入、文件大小限制、active-loop async bridge、sandbox entry hash、带引号命令、selector 边界、Mentor 历史上限。

当前机器 Node.js 为 20.18.0，低于 Vite 要求的 20.19；构建仍成功，但本地环境应升级。
