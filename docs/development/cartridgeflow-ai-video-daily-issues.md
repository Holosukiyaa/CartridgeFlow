# AI 视频日报卡带：闭环过程中的问题清单

> 时间：2026-08-01（开发 → 测试 → 闭环）
> 卡带：`dev.ai-video-daily`（`.data/user/dev_cartridges/`）
> 状态：✅=已修复并验证 / ⏳=遗留 / 🟡=判定合理

## A. 运行 / 后端问题（5 个）

| # | 问题 | 根因 | 修复 | 状态 |
|---|---|---|---|---|
| A1 | LLM 节点空响应（`PROVIDER_EMPTY_RESPONSE`，finish_reason=length） | 推理模型 reasoning 吃满 `max_tokens`（8000 也偶发失败） | `max_tokens` → 20000（3 节点）；skill 模板同步 20k | ✅ |
| A2 | 视频渲染失败（`VIDEO_RENDER_FAILED`，TTS 超时） | 真实口播文本（~4000 字中英混排）TTS 超过 180s | `_run_media_command` 加 `timeout_seconds`，TTS 单独 300s | ✅ |
| A3 | 人工审核空内容（让用户确认空内容） | draft_script **未声明 `daily_brief` 输出契约** → human_review binding 无法解析 → `review_content` 空；且 `params.input` 为多端口 list，提取只认字符串 | ① 卡带补 outputs 契约；② binding 改绑 store 文本（`daily_brief_text`）；③ 后端支持 list aliases。实测审核 modal 显示 1221 字符完整脚本 | ✅ |
| A4 | 运行中当前节点显示空数据（"等待物料到达"，想看原料需往回翻） | runner input 提取不认 CF-FARP v1 顶层 `inputs` → 事件 input 空 | `_resolve_input_preview` helper（list aliases + 顶层 inputs 的 store 绑定值提取），两处 handler 统一走 helper | ✅ |
| A5 | 节点失败错误语义丢失（全变 `INTERNAL_UNEXPECTED`） | 执行器 18 处裸 `raise RuntimeError`；`VIDEO_RENDER_FAILED`/`ARTIFACT_READ_FAILED` 不在 ERROR_CATALOG 被兜底 | `NodeActionError(code)` 结构化异常 + catalog 补码（28 码）+ `classify_exception` 识别 | ✅ |

## B. 前端体验问题（14 个）

| # | 问题 | 修复 | 状态 |
|---|---|---|---|
| B1 | 白屏崩溃（运行中 ~45s `Maximum update depth exceeded`） | 移除自动选中运行节点的 setState 回环 effect | ✅ |
| B2 | 页面"卡住"假象（前端不跟随外部 run） | FlowWorkbench 全局轮询（2.5s） | ✅ |
| B3 | 画布动态载体半透明残留 bug | 整体移除（materialFlow.ts 删除），运行靠节点高亮 | ✅ |
| B4 | 节点尺寸不贴合数据（配方少留白 / 数据多溢出截断） | grid 4 行 auto + 配方高度估算 + wrapper 高度自适应 + saved layout 碰撞解析 | ✅ |
| B5 | 节点信息隐藏（sections 限 2 个、字段限 3 个、配方值 150 字符截断、4 行 clamp、运行时值 220 截断） | 全部显示 + 滚动容器（配方值 5000、运行时 12000） | ✅ |
| B6 | 配方条"上一步→xxx→xxx"无用 | 删除 | ✅ |
| B7 | 详情面板已有的信息重复显示在卡片 | 卡片精简：sections 只留 inputs/outputs（数据链端口） | ✅ |
| B8 | 信源 URL 撕裂（字符中间断行） | `insertUrlBreaks`：标点后 `<wbr>` 断点 | ✅ |
| B9 | 信源地址布局乱（URL 跑到 name 底下） | 矩形容器 + 列表，name/URL 同行 | ✅ |
| B10 | 长文本块背景太显眼 | 透明背景 + 1px 淡竖线（引文块风格） | ✅ |
| B11 | 物料流转容器太小内容截断（XML 只显示开头） | inspector grid 5 行 + 值 pre-wrap 滚动 + 区块 42vh 限高 | ✅ |
| B12 | 当前节点展开但数据全空 | 同 A4（input 预览修复） | ✅ |
| B13 | 完成横幅无"查看结果"入口（产物打不开） | 完成横幅加按钮（三层 props 传递链）+ 打开产物文件夹 | ✅ |
| B14 | 视图合并后残留"工程视图"过时文案（3 处） | 清理（卡片 footer / AI 管家提示 / 连线错误消息） | ✅ |

## C. 卡带 / 建模问题（4 个）

| # | 问题 | 修复 | 状态 |
|---|---|---|---|
| C1 | 失败终端 9 个冗余 | 合并为 1 个「流程失败」（协议强制 failure 边保留、终端可共享，精确原因在 run.error） | ✅ |
| C2 | 节点无职责描述（显示模板话术） | 9 个 process 节点写具体 `params.description` + skill 1.8.0 要求 + validate `NODE_DESCRIPTION_MISSING` 检查 | ✅ |
| C3 | 审核 prompt 默认"请确认是否继续执行" | 卡带 interaction 未配 prompt | ⏳ 遗留（可选优化） |
| C4 | fetch_trusted_rss「进入前」显示空 | 该节点无 inputs 声明（语义上不消费上游数据） | 🟡 判定合理 |

## D. 开发过程教训（环境类）

1. uvicorn 用 `(cmd &)` 子 shell 启动会随命令退出被杀——用受管后台 job（run_in_background）
2. 旧 python 进程占 8765 端口 → 新 uvicorn 启动失败（Errno 10048）但后端仍响应旧代码——"修复不生效"先查端口（netstat -ano | grep 8765）
3. httpx 默认走系统代理干扰 127.0.0.1——测试一律 `httpx.Client(trust_env=False)`
4. create run 请求慢（120s+）——测试放宽 timeout 并容忍
5. python heredoc 转义坑（`\n` 写入变真实换行导致 SyntaxError）
6. Playwright `networkidle` 30s 超时（前端慢）——加容错
7. 页面显示旧 run（残留 paused run 干扰验证）——测试前先清场（API 批准）

## E. 剩余遗留（非阻塞）

1. 审核 prompt 默认文案（C3）
2. `_truncate` 三份重复实现（可统一）
3. `review_content` 无截断上限（low，单用户 localhost 无风险）
4. create run 慢（未深挖耗时来源）
5. 前端构建 chunk >500KB 警告（可代码分割）

## 验证基线

- runtime/lab 测试 68 全绿（含恢复路径）+ conformance/api 113 全绿
- 前端生产构建通过（tsc -b && vite build）+ node --check 产物语法有效
- 端到端实测：审核 modal 1221 字符脚本、当前节点"进入前"真实原料、完成横幅 + 产物（md+mp4）
- review（edb602d 后）pass；security_review pass（无注入面）
