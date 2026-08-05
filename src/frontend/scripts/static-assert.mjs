#!/usr/bin/env node
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const sourceRoot = join(root, 'src')
const failures = []
const notes = []

function check(ok, message) {
  ;(ok ? notes : failures).push(`  ${ok ? 'PASS' : 'FAIL'} ${message}`)
}

function filesUnder(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    return statSync(full).isDirectory() ? filesUnder(full) : [full]
  })
}

const files = filesUnder(sourceRoot)
const source = new Map(files.map((file) => [relative(sourceRoot, file).replaceAll('\\', '/'), readFileSync(file, 'utf8')]))
const app = source.get('App.tsx') || ''
const api = source.get('api.ts') || ''
const workspace = source.get('pages/flow-workbench/CreatorStudio.tsx') || ''
const canvas = source.get('pages/flow-workbench/CreatorCanvas.tsx') || ''

check(source.has('pages/flow-workbench/CreatorStudio.tsx'), 'Creator Studio is the product surface')
check(source.has('pages/flow-workbench/CreatorCanvas.tsx'), 'Creator owns one focused canvas implementation')
check(app.includes('<CreatorStudio projectId={projectId} />'), 'the application renders only CreatorStudio')
check(!app.includes('/api/lab') && !app.includes('FlowWorkbench'), 'startup is independent from Lab Flow and the old workbench')

const retiredFiles = [
  'pages/FlowWorkbench.tsx',
  'pages/flow-workbench/FlowGraphView.tsx',
  'pages/flow-workbench/TestBenchView.tsx',
  'pages/flow-workbench/TrustedNodePanel.tsx',
  'pages/flow-workbench/views.tsx',
  'pages/flow-workbench/nodeBuilder.ts',
  'pages/flow-workbench/ResourceManagementPanels.tsx',
]
for (const file of retiredFiles) check(!source.has(file), `${file} stays removed from Creator`)

for (const forbidden of ['/api/lab', '/api/developer', 'runtime-handoff', 'compile-candidate', '/tuning', '/runs']) {
  check(!api.includes(forbidden), `Creator API does not expose ${forbidden}`)
}
check(api.includes('/package') && workspace.includes('packageCreatorProject'), 'package is the sole Creator mapping action')
check(api.includes('/possibilities') && api.includes('/compose-recipe') && api.includes('/recompose'), 'both discovery and whole-draft collaboration are wired')
check(api.includes('/api/llm/detect') && api.includes('/api/llm/providers') && api.includes('/api/llm/test'), 'AI connection is completed from the Creator canvas')
check(api.includes('/api/creator/starter-capabilities'), 'Creator can request the simulated Base-owned starter capability')
check(workspace.includes('ModelConnectionPanel') && workspace.includes('aiConnectedRef.current === false'), 'AI actions resolve an unbound model before sending generation requests')
check(workspace.includes('NodeEditor') && workspace.includes('refineCreatorNodeWithAi'), 'a selected node has a scoped deepening flow')
check(canvas.includes('nodesDraggable={false}') && canvas.includes('nodesConnectable={false}'), 'the Creator canvas cannot place or wire engineering nodes')

const visibleForbidden = ['Developer', '工程语义', '运行测试', '调试', '调优', '版本切换', '执行映射', '配置模型', '配置工具', '权限设置']
for (const phrase of visibleForbidden) check(!workspace.includes(phrase), `Creator UI omits ${phrase}`)

const cssFiles = files.filter((file) => file.endsWith('.css'))
const importantCount = cssFiles.reduce((count, file) => count + (readFileSync(file, 'utf8').match(/!important/g) || []).length, 0)
check(cssFiles.length === 2, `Creator uses one local stylesheet plus the CSS entry (${cssFiles.length} found)`)
check(importantCount === 0, 'Creator CSS has no !important overrides')
check(existsSync(join(root, 'src/styles/creator.css')), 'Creator layout stylesheet exists')

console.log('=== Creator static contract ===')
for (const note of notes) console.log(note)
if (failures.length) {
  console.log(`\n${failures.length} failure(s):`)
  for (const failure of failures) console.log(failure)
}
process.exitCode = failures.length ? 1 : 0
