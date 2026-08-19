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
const modelDialog = source.get('pages/intent-studio/ModelConnectionDialog.tsx') || ''
const themeDialog = source.get('pages/intent-studio/ThemeDialog.tsx') || ''
const themeProvider = source.get('ui/AppThemeProvider.tsx') || ''
const workbench = source.get('ui/workbench.tsx') || ''
const uiEntry = source.get('ui/index.ts') || ''
const styles = source.get('styles/intent-studio.css') || ''
const discoverStart = workspace.indexOf('const discover = async')
const composeStart = workspace.indexOf('const compose = async', discoverStart)
const discoverImplementation = discoverStart >= 0 && composeStart > discoverStart
  ? workspace.slice(discoverStart, composeStart)
  : ''

check(source.has('pages/intent-studio/IntentStudio.tsx'), 'Intent Studio is the semantic product surface')
check(source.has('pages/intent-studio/IntentCanvas.tsx'), 'Intent Studio owns one focused canvas implementation')
check(source.has('ui/AppThemeProvider.tsx') && source.has('ui/controls.tsx') && source.has('ui/workbench.tsx'), 'Intent Studio owns one local UI boundary')
check(uiEntry.includes('SemanticWorkbench') && uiEntry.includes('Dialog') && uiEntry.includes('IconButton'), 'pages consume the bounded UI public entry')
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
check(workspace.includes('ModelConnectionDialog') && workspace.includes('aiConnectedRef.current === false'), 'AI actions resolve an unbound model before sending generation requests')
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
check(canvas.includes('flow.setCenter(firstNode.position.x + nodeWidth(firstNode) / 2'), 'mobile starts from a readable first node instead of shrinking the whole outline')
check(workspace.includes('ProposalChanges') && workspace.includes('creator-review-changes'), 'node proposals expose their concrete Creator-safe field changes before acceptance')
check(workspace.includes('creator-package-error'), 'Creator packaging failures remain visible on the canvas')
check(themeProvider.includes('APP_THEME_PRESETS') && themeProvider.includes('quiet-workbench') && themeProvider.includes('morning-mist') && themeProvider.includes('paper-ink') && themeProvider.includes('quiet-forest'), 'Creator ships the neutral workbench and alternate visual presets')
check(themeProvider.includes('localStorage.setItem(APP_THEME_KEY') && themeProvider.includes('localStorage.getItem(APP_THEME_KEY'), 'Creator persists the selected visual theme locally')
check(themeDialog.includes('控件颜色') && themeDialog.includes('焦点颜色') && themeDialog.includes('背景颜色'), 'Creator exposes the three user-adjustable theme colors')
check(styles.includes('--intent-accent') && styles.includes('--intent-focus') && styles.includes('--intent-page'), 'Creator routes controls, focus, and page background through theme variables')
check(!workspace.includes('creator-mode-switch') && workspace.includes('SemanticWorkbench'), 'Creator keeps authoring and refinement on one continuous semantic surface')
check(workspace.includes('AI 共创记录') && workspace.includes('仍然不是终稿'), 'Creator never treats an accepted revision as final user intent')
check(canvas.includes("CreatorCanvasTool = 'inspect' | 'pointer' | 'lasso'") && canvas.includes('selectionOnDrag={tool === \'lasso\'}'), 'Creator supports pointer and lasso context selection')
check(canvas.includes('onSelectionEnd={() =>') && canvas.includes('flow.getNodes().filter((node) => node.selected)'), 'lasso updates the discussion range only after the gesture ends')
check(canvas.includes('nextNodeIds.length === currentNodeIds.length'), 'lasso selection ignores an unchanged node set')
check(workspace.includes('creator-draft-review') && canvas.includes('preview: CreatorRecipePreview | null'), 'AI outline revisions remain visible and reviewable on the canvas')
check(workspace.includes('if (creator) setGoal(creator.intent)') && workspace.includes('onClick={rejectRecipePreview}'), 'rejecting an outline revision restores the accepted intent')
check(workspace.includes('vip-ai-panel') && workspace.includes('semantic-detail-stack') && workspace.includes('vip-canvas-panel') && !workspace.includes('vip-outline-panel'), 'Creator renders the approved semantic canvas with optional detail and AI panels')
check(workspace.includes('creator?.history') && workspace.includes('syncLabel') && !workspace.includes('自动保存 10:'), 'history and save state come from real session activity')
check(api.includes('/workspace') && workspace.includes('fetchCreatorWorkspace') && workspace.includes('saveCreatorWorkspace') && workspace.includes('workspaceRevisionRef'), 'Creator persists bounded project conversation in the server workspace without adding it to authoring facts')
check(workspace.includes('CREATOR_WORKSPACE_KEY') && workspace.includes('messages: stewardMessages.slice(-80)'), 'Creator retains a bounded local fallback when the server workspace cannot be recovered')
check(workspace.includes('creatorGuidance') && workspace.includes('runGuidanceAction') && workspace.includes('vip-next-action'), 'Creator derives one visible next action from the current project state')
check(workspace.includes("stage: 'connect-ai'") && workspace.includes("action: 'connect-ai'") && workspace.includes('creator-ai-button'), 'a new creator is guided through a tested AI connection before generation')
check(workspace.includes('capabilityWorkshopUrl') && workspace.includes('开始补齐'), 'an unresolved step opens its scoped Capability Workshop directly')
check(workspace.includes('下载试运行包') && workspace.includes('runnerUrl'), 'reviewed projects hand a real signed package to the discovered Desktop Runner')
check(api.includes('/desktop-runner') && workspace.includes('deliverCreatorProject') && workspace.includes("action: 'deliver-runner'") && workspace.includes("status === 'trust_required'"), 'reviewed projects can deliver a real signed package with explicit Runner publisher approval and download fallback')
check(workspace.includes('SemanticWorkbench') && workbench.includes('semantic-panel-tabs') && styles.includes('.semantic-panel-tabs'), 'narrow screens retain access to canvas, detail, and AI panels')
check(workbench.indexOf('semantic-canvas-region') < workbench.indexOf('semantic-detail-panel') && workbench.indexOf('semantic-detail-panel') < workbench.indexOf('semantic-ai-panel'), 'desktop panels keep canvas first, details next, and AI at the far right')
check(workbench.includes('getInitialValueInEffect: false'), 'compact workbench mode is selected before the first browser paint')
check(workbench.includes("visiblePanel === 'canvas'") && workbench.includes("visiblePanel === 'detail'") && workbench.includes("visiblePanel === 'ai'"), 'compact mode mounts only its active panel')
check(!workspace.includes('creator-overlay') && workspace.includes('ModelConnectionDialog') && workspace.includes('ThemeDialog'), 'page overlays use the shared dialog boundary')
check(workspace.includes('detailOpen={detailOpen}') && workspace.includes('aiOpen={aiPanelOpen}') && workspace.includes('setDetailOpen') && workspace.includes('setAiPanelOpen'), 'detail and AI panels open and collapse independently')
check(!canvas.includes('<MiniMap') && canvas.includes('<Panel className="creator-zoom-controls"'), 'Creator canvas uses the approved compact zoom strip without an overview map')
check(canvas.includes('NODE_WIDTH = 240') && canvas.includes('STEP_NODE_WIDTH = 260') && canvas.includes('NESTED_NODE_WIDTH = 280') && canvas.includes('NODE_HEIGHT = 220') && canvas.includes('contentNodeHeight'), 'Creator nodes size themselves from content while retaining readable boundary dimensions')
check(styles.includes('.semantic-workbench.has-detail.has-ai') && styles.includes('grid-template-columns:minmax('), 'Creator panel widths preserve a usable canvas when both side panels are open')
check(/\.creator-node\s*\{[^}]*\bwidth:\s*100%;[^}]*\bheight:\s*100%;/.test(styles) && !/\.creator-node\.is-selected\s*\{[^}]*\b(?:width|height)\s*:/.test(styles), 'Creator node visuals inherit the React Flow geometry without resizing selected nodes')
check(!styles.includes('is-co-create') && !styles.includes('--workbench-header') && !styles.includes('Final home prototype'), 'retired Creator layout generations stay removed from the active stylesheet')
check(workspace.includes('semantic-project-menu') && workspace.includes('semantic-node-route'), 'project and node navigation remain available without an outline pane')
check(styles.includes('Microsoft YaHei UI') && styles.includes('Segoe UI Variable Text'), 'Creator uses the Windows-hinted Chinese UI font stack')
check(styles.split('\n').length <= 300 && (styles.match(/@media\s/g) || []).length <= 2, 'Creator CSS stays within the skeleton-level size and breakpoint budget')
check(!styles.includes('box-shadow') && !styles.includes('transform:') && !styles.includes('.creator-node-order-'), 'Creator skeleton excludes decorative shadows, positional patches, and per-node layout exceptions')
check(!styles.includes('.creator-stage-rail') && !styles.includes('.vip-outline-row') && !workspace.includes('工程视图') && !workspace.includes('引导视图'), 'retired stage and outline layouts cannot return through active UI code')
check(canvas.includes("kind: 'start'") && canvas.includes("kind: 'end'") && canvas.includes("type: 'bezier'"), 'empty projects expose start and end placeholders and semantic links use curves')
check(workspace.includes("'control', 'data', 'dependency'") && workspace.includes('semantic-relation-filters'), 'the semantic canvas retains control, data, and dependency relation filters')
check(workspace.includes('semantic-command-main') && !workspace.includes('semantic-command-context'), 'the command bar keeps only dense relation navigation and panel actions')
check(canvas.includes('creator-node-${data.state}') && canvas.includes('AlertTriangle') && canvas.includes('CheckCircle2'), 'node trust is visible as warning or confirmed status')
check(workspace.includes('nested-cartridge-shell') && workspace.includes('capabilityWorkshopUrl') && !workspace.includes('/api/lab'), 'nested cartridges open through the public Capability Workshop owner')

const visibleForbidden = ['Developer', '工程语义', '运行测试', '调试', '调优', '版本切换', '执行映射', '配置模型', '配置工具', '权限设置']
for (const phrase of visibleForbidden) check(!workspace.includes(phrase), `Creator UI omits ${phrase}`)

const cssFiles = files.filter((file) => file.endsWith('.css'))
const pageFiles = [...source.entries()].filter(([path]) => path.startsWith('pages/'))
const directLibraryImports = pageFiles.filter(([, content]) => content.includes("from '@mantine/") || content.includes("from 'allotment'"))
const importantCount = cssFiles.reduce((count, file) => count + (readFileSync(file, 'utf8').match(/!important/g) || []).length, 0)
check(cssFiles.length === 2, `Creator uses one local stylesheet plus the CSS entry (${cssFiles.length} found)`)
check(importantCount === 0, 'Creator CSS has no !important overrides')
check(directLibraryImports.length === 0, 'domain pages do not bypass the local UI boundary')
check(existsSync(join(root, 'src/styles/intent-studio.css')), 'Intent Studio layout stylesheet exists')

console.log('=== Creator static contract ===')
for (const note of notes) console.log(note)
if (failures.length) {
  console.log(`\n${failures.length} failure(s):`)
  for (const failure of failures) console.log(failure)
}
process.exitCode = failures.length ? 1 : 0
