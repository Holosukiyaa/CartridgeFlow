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
const workspace = source.get('pages/intent-studio/IntentStudio.tsx') || ''
const canvas = source.get('pages/intent-studio/IntentCanvas.tsx') || ''

check(source.has('pages/intent-studio/IntentStudio.tsx'), 'Intent Studio is the semantic product surface')
check(source.has('pages/intent-studio/IntentCanvas.tsx'), 'Intent Studio owns one focused canvas implementation')
check(app.includes('<IntentStudio projectId={projectId} />'), 'the application renders only IntentStudio')
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
check(!api.includes('/api/creator/starter-capabilities'), 'Creator does not inject a hardcoded capability after AI setup')
check(workspace.includes('ModelConnectionPanel') && workspace.includes('aiConnectedRef.current === false'), 'AI actions resolve an unbound model before sending generation requests')
check(workspace.includes('creator-clarification') && workspace.includes('suggested_answers'), 'AI discovery can clarify one decisive question before proposing directions')
check(api.includes("output_locale: 'zh-CN'") && workspace.includes('简体中文输出'), 'Creator requests and exposes the interface output language')
check(workspace.includes('composerError') && workspace.includes('role="alert"'), 'Creator keeps AI failures visible on the canvas for retry')
check((api.match(/timeoutMs: 135_000/g) || []).length >= 4, 'Creator waits for the configured AI response window')
check(api.includes('/reject-capability') && workspace.includes('不适合当前节点'), 'Creator can reject a proposed capability in place')
check(workspace.includes('NodeEditor') && workspace.includes('refineCreatorNodeWithAi'), 'a selected node has a scoped deepening flow')
check(canvas.includes('nodesDraggable={false}') && canvas.includes('nodesConnectable={false}'), 'the Creator canvas cannot place or wire engineering nodes')
check(canvas.includes('<Handle type="target"') && canvas.includes('<Handle type="source"'), 'semantic nodes retain both endpoints required to render relationships')
check(canvas.includes('animated: true') && canvas.includes('MarkerType.ArrowClosed'), 'semantic relationships render as animated directional arrows')
check(canvas.includes("relation.relation === 'uses' ? relation.to_node_id") && canvas.includes("relation.relation === 'uses' ? relation.from_node_id"), 'dependency relationships point from the provider to the consuming step')
check(canvas.includes('onInit={setFlow}') && canvas.includes('flow.fitView'), 'the canvas refits after an asynchronous semantic draft arrives')
check(workspace.includes('ProposalChanges') && workspace.includes('creator-review-changes'), 'node proposals expose their concrete Creator-safe field changes before acceptance')
check(workspace.includes('creator-package-error'), 'Creator packaging failures remain visible on the canvas')

const visibleForbidden = ['Developer', '工程语义', '运行测试', '调试', '调优', '版本切换', '执行映射', '配置模型', '配置工具', '权限设置']
for (const phrase of visibleForbidden) check(!workspace.includes(phrase), `Creator UI omits ${phrase}`)

const cssFiles = files.filter((file) => file.endsWith('.css'))
const importantCount = cssFiles.reduce((count, file) => count + (readFileSync(file, 'utf8').match(/!important/g) || []).length, 0)
check(cssFiles.length === 2, `Creator uses one local stylesheet plus the CSS entry (${cssFiles.length} found)`)
check(importantCount === 0, 'Creator CSS has no !important overrides')
check(existsSync(join(root, 'src/styles/intent-studio.css')), 'Intent Studio layout stylesheet exists')

console.log('=== Creator static contract ===')
for (const note of notes) console.log(note)
if (failures.length) {
  console.log(`\n${failures.length} failure(s):`)
  for (const failure of failures) console.log(failure)
}
process.exitCode = failures.length ? 1 : 0
