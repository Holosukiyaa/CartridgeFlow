#!/usr/bin/env node
/**
 * CartridgeFlow 前端静态断言（test:static）
 *
 * 不引入测试框架的轻量源码级检查，防住「UI 文案漂移」与「已知反模式回归」：
 *   1. 资源节点拒绝提示必须存在且与常量一致（防止实现文案与断言再次不同步）
 *   2. 历史旧文案不得残留（防止新旧文案并存造成断言混乱）
 *   3. 样式债务红线：!important 数量不得超过阈值（当前基线，只降不升）
 *
 * 用法：npm run test:static   （退出码 0=通过，1=失败）
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const flowGraphViewPath = join(root, 'src/pages/flow-workbench/FlowGraphView.tsx')
const cssGlobPath = join(root, 'src')

const failures = []
const notes = []

function check(ok, message) {
  if (ok) notes.push(`  ✓ ${message}`)
  else failures.push(`  ✗ ${message}`)
}

// --- 1. 资源节点拒绝提示：常量存在 + 声明与使用一致 ---
let src = ''
try {
  src = readFileSync(flowGraphViewPath, 'utf8')
} catch (error) {
  failures.push(`无法读取 FlowGraphView.tsx: ${error.message}`)
  process.exitCode = 1
  report(failures, notes)
  process.exit(1)
}

const decl = src.match(/export const RESOURCE_EDGE_REJECT_MESSAGE = '([^']+)'/)
check(Boolean(decl), 'RESOURCE_EDGE_REJECT_MESSAGE 常量已声明')
const message = decl ? decl[1] : ''
check(message.includes('资源'), '拒绝提示包含「资源」语义')
check(src.includes(`return RESOURCE_EDGE_REJECT_MESSAGE`), 'validateConnection 使用常量而非内联文案')

// --- 2. 历史旧文案不得残留（断言曾匹配旧文案导致失败） ---
const legacyPhrases = ['资源节点不能进入控制流', '资源节点不能进入 Root Flow', '不能将资源节点连入控制流']
for (const phrase of legacyPhrases) {
  check(!src.includes(phrase), `旧文案「${phrase}」未残留`)
}

// --- 3. CSS 样式债红线：!important 数量不得超过阈值（基线只降不升） ---
function collectCss(dir) {
  const out = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) out.push(...collectCss(full))
    else if (entry.endsWith('.css')) out.push(full)
  }
  return out
}
let importantCount = 0
let cssFiles = 0
let cssScanError = null
if (!existsSync(cssGlobPath)) {
  notes.push('  ⚠ 前端源码目录未找到，跳过 !important 红线检查')
} else {
  try {
    for (const file of collectCss(cssGlobPath)) {
      cssFiles += 1
      const text = readFileSync(file, 'utf8')
      importantCount += (text.match(/!important/g) || []).length
    }
  } catch (error) {
    cssScanError = error
  }
}
if (cssScanError) failures.push(`样式扫描失败（红线检查无法完成）: ${cssScanError.message}`)
// 基线 697（2026-08-01），红线 730 预留 33 条容差；只允许下降
const IMPORTANT_LIMIT = 730
check(importantCount <= IMPORTANT_LIMIT, `!important 计数 ${importantCount} ≤ 红线 ${IMPORTANT_LIMIT}（${cssFiles} 个 css 文件）`)

// --- 输出 ---
function report(failList, noteList) {
  console.log('=== 前端静态断言 (test:static) ===')
  for (const n of noteList) console.log(n)
  if (failList.length) {
    console.log(`\n失败 ${failList.length} 项:`)
    for (const f of failList) console.log(f)
  } else {
    console.log('\n全部通过')
  }
}

report(failures, notes)
process.exitCode = failures.length ? 1 : 0
