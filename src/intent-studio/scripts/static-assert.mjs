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
const styles = source.get('styles/intent-studio.css') || ''
const discoverStart = workspace.indexOf('const discover = async')
const composeStart = workspace.indexOf('const compose = async', discoverStart)
const discoverImplementation = discoverStart >= 0 && composeStart > discoverStart
  ? workspace.slice(discoverStart, composeStart)
  : ''

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
check(discoverImplementation.includes('discoverCreatorPossibilities') && !discoverImplementation.includes('composeCreatorRecipe'), 'AI discovery waits for an explicit direction choice before composing a recipe')
check(workspace.includes('DirectionExplorer') && workspace.includes('onChoose={chooseDirection}'), 'real AI directions have an explicit selection step')
check(workspace.includes("setWorkspacePane(discovery.possibilities.length ? 'outline' : 'collaboration')"), 'narrow screens reveal real directions as soon as discovery completes')
check(!workspace.includes('立刻摆出一版大纲') && !canvas.includes('大纲会立刻出现在这里'), 'empty-state copy matches the clarify, choose, then compose sequence')
check(api.includes("output_locale: 'zh-CN'") && workspace.includes('简体中文'), 'Creator requests and exposes the interface output language')
check(workspace.includes('composerError') && workspace.includes('role="alert"'), 'Creator keeps AI failures visible on the canvas for retry')
check((api.match(/timeoutMs: 135_000/g) || []).length >= 4, 'Creator waits for the configured AI response window')
check(api.includes('/reject-capability') && workspace.includes('不适合当前节点'), 'Creator can reject a proposed capability in place')
check(workspace.includes('NodeEditor') && workspace.includes('refineCreatorNodeWithAi'), 'a selected node has a scoped deepening flow')
check(canvas.includes("nodesDraggable={Boolean(creator) && tool === 'inspect'}") && canvas.includes('nodesConnectable={false}'), 'the Creator canvas can rearrange semantic nodes without wiring engineering nodes')
check(canvas.includes('CREATOR_LAYOUT_KEY') && canvas.includes('onNodeDragStop') && canvas.includes('savePositions'), 'node positions persist as local canvas preferences')
check(canvas.includes('<Handle type="target"') && canvas.includes('<Handle type="source"'), 'semantic nodes retain both endpoints required to render relationships')
check(canvas.includes('animated: false') && canvas.includes('MarkerType.ArrowClosed'), 'semantic relationships remain directional without distracting animation')
check(canvas.includes("relation.relation === 'uses' ? relation.to_node_id") && canvas.includes("relation.relation === 'uses' ? relation.from_node_id"), 'dependency relationships point from the provider to the consuming step')
check(canvas.includes('onInit={setFlow}') && canvas.includes('flow.fitView'), 'the canvas refits after an asynchronous semantic draft arrives')
check(canvas.includes('timer = window.setTimeout'), 'the canvas waits for viewport resizing to settle before refitting')
check(canvas.includes('new ResizeObserver') && canvas.includes('canvasHostRef'), 'the canvas reframes when a hidden narrow-screen pane becomes visible')
check(canvas.includes('flow.setCenter(firstNode.position.x + NODE_WIDTH / 2'), 'mobile starts from a readable first node instead of shrinking the whole outline')
check(workspace.includes('ProposalChanges') && workspace.includes('creator-review-changes'), 'node proposals expose their concrete Creator-safe field changes before acceptance')
check(workspace.includes('creator-package-error'), 'Creator packaging failures remain visible on the canvas')
check(workspace.includes('CREATOR_THEME_PRESETS') && workspace.includes('quiet-workbench') && workspace.includes('morning-mist') && workspace.includes('paper-ink') && workspace.includes('quiet-forest'), 'Creator ships the neutral workbench and alternate visual presets')
check(workspace.includes("localStorage.setItem(CREATOR_THEME_KEY") && workspace.includes("localStorage.getItem(CREATOR_THEME_KEY"), 'Creator persists the selected visual theme locally')
check(workspace.includes('控件颜色') && workspace.includes('焦点颜色') && workspace.includes('背景颜色'), 'Creator exposes the three user-adjustable theme colors')
check(styles.includes('--intent-accent') && styles.includes('--intent-focus') && styles.includes('--intent-page'), 'Creator routes controls, focus, and page background through theme variables')
check(!workspace.includes('creator-mode-switch') && workspace.includes('vip-workspace-body'), 'Creator keeps outlining and refinement on one continuous work surface')
check(workspace.includes('AI 共创记录') && workspace.includes('仍然不是终稿'), 'Creator never treats an accepted revision as final user intent')
check(canvas.includes("CreatorCanvasTool = 'inspect' | 'pointer' | 'lasso'") && canvas.includes('selectionOnDrag={tool === \'lasso\'}'), 'Creator supports pointer and lasso context selection')
check(canvas.includes('onSelectionEnd={() =>') && canvas.includes('flow.getNodes().filter((node) => node.selected)'), 'lasso updates the discussion range only after the gesture ends')
check(canvas.includes('nextNodeIds.length === currentNodeIds.length'), 'lasso selection ignores an unchanged node set')
check(workspace.includes('creator-draft-review') && canvas.includes('preview: CreatorRecipePreview | null'), 'AI outline revisions remain visible and reviewable on the canvas')
check(workspace.includes('if (creator) setGoal(creator.intent)') && workspace.includes('onClick={rejectRecipePreview}'), 'rejecting an outline revision restores the accepted intent')
check(workspace.includes('vip-ai-panel') && workspace.includes('vip-outline-panel') && workspace.includes('vip-canvas-panel'), 'Creator renders the approved collaboration, outline, and semantic canvas panes')
check(workspace.includes('creator?.history') && workspace.includes('syncLabel') && !workspace.includes('自动保存 10:'), 'history and save state come from real session activity')
check(workspace.includes('CREATOR_WORKSPACE_KEY') && workspace.includes('messages: stewardMessages.slice(-80)'), 'Creator restores bounded project conversation locally without adding it to authoring facts')
check(workspace.includes('creatorGuidance') && workspace.includes('runGuidanceAction') && workspace.includes('vip-next-action'), 'Creator derives one visible next action from the current project state')
check(workspace.includes('capabilityWorkshopUrl') && workspace.includes('开始补齐'), 'an unresolved step opens its scoped Capability Workshop directly')
check(workspace.includes('下载试运行包') && workspace.includes('http://127.0.0.1:18990/'), 'reviewed projects hand a real signed package to Desktop Runner')
check(workspace.includes('vip-pane-nav') && styles.includes('.vip-workspace-body.is-pane-collaboration') && !styles.includes('.vip-ai-panel, .vip-outline-panel { display: none; }'), 'narrow screens retain access to collaboration, outline, and canvas')
check(workspace.includes('data-view="outline"') && workspace.includes('data-view="detail"'), 'the middle pane switches in place between outline and node details')
check(!canvas.includes('<MiniMap') && canvas.includes('<Panel className="creator-zoom-controls"'), 'Creator canvas uses the approved compact zoom strip without an overview map')
check(canvas.includes('NODE_WIDTH = 204') && canvas.includes('NODE_HEIGHT = 174'), 'Creator nodes retain the approved reference dimensions')
check(workspace.includes('项目与大纲') && workspace.includes('vip-current-project'), 'project and outline navigation remains available in the middle pane')
check(styles.includes('font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI Variable Text", "Segoe UI", sans-serif;'), 'Creator uses the Windows-hinted Chinese UI font stack')
check(styles.includes('--vip-surface-ai: #f3f5f8') && styles.includes('--vip-surface-outline: #f6f7f9') && styles.includes('--vip-surface-canvas: #fafbfc'), 'Creator panes retain distinct neutral surface levels')
check(/\.vip-ai-panel\s*\{[^}]*grid-template-rows:\s*64px 76px minmax\(0, 1fr\) 104px;/.test(styles) && /\.vip-collaboration-composer > div\s*\{[^}]*padding:\s*4px 14px 6px;/.test(styles), 'Creator composer reserves internal and external bottom breathing room')
check(/\.vip-outline-row\s*\{[^}]*gap:\s*0;/.test(styles) && !styles.includes('min-height: 49.5px'), 'Creator outline columns align on an integer-pixel grid without inherited button gaps')

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
