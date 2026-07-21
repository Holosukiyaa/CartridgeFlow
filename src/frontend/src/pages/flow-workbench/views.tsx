import { Badge, Box, Button, HStack, Heading, Text } from '../../ui.tsx'
import type { FlowEdge, FlowEvent, FlowFiles, FlowGraph, FlowLabDetail, FlowNode, RunResult, TestProbeRange } from '../../api.ts'
import type { CreateNodeHandler, GraphResult, WorkbenchMode } from './types.ts'
import { FlowGraphView } from './FlowGraphView.tsx'
import { FlowAssistantPanel, type FlowAssistantApplyResult, type FlowAssistantDraft, type FlowAssistantGraphOps } from './FlowAssistantPanel.tsx'
import { NodeDrawer } from './NodeDrawer.tsx'
import { TestBenchView } from './TestBenchView.tsx'

export function WorkbenchHeader({ detail, tags, mode, onBack, onModeChange, onCloneToDev, cloningToDev = false }: {
  detail: FlowLabDetail
  tags: string[]
  mode: WorkbenchMode
  onBack: () => void
  onModeChange: (mode: WorkbenchMode) => void
  onCloneToDev?: () => void
  cloningToDev?: boolean
}) {
  const compatibility = detail.compatibility
  const status = compatibility?.status || 'unknown'
  const blocker = compatibility?.summary?.blocker || 0
  const warning = compatibility?.summary?.warning || 0
  const statusLabel = blocker > 0 ? '阻断' : warning > 0 ? '警告' : status === 'compatible' ? '兼容' : '未知'
  const baseLabel = compatibility?.base?.implementation_id
    ? `${compatibility.base.implementation_id}@${compatibility.base.implementation_version || '?'}`
    : 'base 未声明'
  const protocolLabel = compatibility?.protocol?.required || 'protocol 未声明'
  return (
    <HStack justify="space-between" className="cf-page-header cf-workbench-header">
      <HStack gap={3} className="cf-workbench-titlebar">
        <Text className="cf-kicker">Studio Workbench</Text>
        <Heading size="lg" className="cf-page-title">{detail.cartridge.name}</Heading>
        <Text className="cf-page-subtitle">
          {detail.cartridge.id} · v{detail.cartridge.version} · {detail.cartridge.source || 'project'} · {detail.cartridge.editable ? 'editable' : 'readonly'}
        </Text>
        <div className={`cf-contract-strip ${blocker > 0 ? 'blocked' : warning > 0 ? 'warning' : 'ok'}`}>
          <span>{statusLabel}</span>
          <code>{protocolLabel}</code>
          <code>{baseLabel}</code>
          {compatibility?.legacy && <b>legacy</b>}
        </div>
        {tags.length > 0 && (
          <HStack gap={1} className="cf-workbench-tags">
            {tags.map((tag, index) => <Badge key={`${tag}-${index}`} className="cf-badge">{tag}</Badge>)}
          </HStack>
        )}
      </HStack>
      <HStack gap={2}>
        <Button className="cf-outline-btn" onClick={onBack}>返回项目</Button>
        {!detail.cartridge.editable && onCloneToDev && (
          <Button className="cf-outline-btn" onClick={onCloneToDev} loading={cloningToDev} loadingText="复制中...">
            复制为可编辑版本
          </Button>
        )}
        <Button className={mode === 'design' ? 'cf-accent-btn' : 'cf-outline-btn'} onClick={() => onModeChange('design')}>设计</Button>
        <Button className={mode === 'run' ? 'cf-accent-btn' : 'cf-outline-btn'} onClick={() => onModeChange('run')}>测试</Button>
        <Button className={mode === 'models' ? 'cf-accent-btn' : 'cf-outline-btn'} onClick={() => onModeChange('models')}>模型配方</Button>
      </HStack>
    </HStack>
  )
}

export function DesignView({
  graph, editable, files, flowId, selectedNode, focusNodeId, drawerOpen,
  onSelectNode, onCloseDrawer, onLayoutSave, onEdgesSave, onCreateNode, onApplyAssistantDraft, onApplyAssistantGraphOps, onUndoAssistantDraft, onDeleteNode, onSaved,
}: {
  graph: FlowGraph
  editable: boolean
  files: FlowFiles
  flowId: string
  selectedNode: FlowNode | null
  focusNodeId: string | null
  drawerOpen: boolean
  onSelectNode: (node: FlowNode) => void
  onCloseDrawer: () => void
  onLayoutSave: (layout: Record<string, { x: number; y: number }>) => Promise<void>
  onEdgesSave: (edges: FlowEdge[]) => Promise<void>
  onCreateNode: CreateNodeHandler
  onApplyAssistantDraft: (draft: FlowAssistantDraft, sourceNode?: FlowNode | null) => Promise<FlowAssistantApplyResult>
  onApplyAssistantGraphOps: (ops: FlowAssistantGraphOps) => Promise<FlowAssistantApplyResult>
  onUndoAssistantDraft: (result: FlowAssistantApplyResult) => Promise<void>
  onDeleteNode: (node: FlowNode) => Promise<void>
  onSaved: (result: GraphResult) => void
}) {
  return (
    <div className={`cf-design-studio ${drawerOpen ? 'drawer-open' : ''}`}>
      <FlowAssistantPanel flowId={flowId} graph={graph} files={files} onApplyDraft={onApplyAssistantDraft} onApplyGraphOps={onApplyAssistantGraphOps} onUndoApply={onUndoAssistantDraft} />
      <Box className="cf-flow-panel cf-flow-overview cf-flow-overview-studio" overflow="hidden">
        <FlowGraphView
          graph={graph}
          selectedNode={selectedNode}
          focusNodeId={focusNodeId}
          onSelectNode={onSelectNode}
          onLayoutSave={editable ? onLayoutSave : undefined}
          onEdgesSave={editable ? onEdgesSave : undefined}
          onCreateNode={editable ? onCreateNode : undefined}
          onDeleteNode={editable ? onDeleteNode : undefined}
        />
      </Box>
      <NodeDrawer
        node={selectedNode}
        graphEdges={graph.edges || []}
        flowId={flowId}
        files={files}
        editable={editable}
        open={drawerOpen}
        onClose={onCloseDrawer}
        onSaved={onSaved}
      />
    </div>
  )
}

export function RunView({ detail, runs, events, onTestRun, onAnswerPendingInteraction, onRefresh, onManageMcp }: {
  detail: FlowLabDetail
  runs: RunResult[]
  events: FlowEvent[]
  onTestRun: (inputs: Record<string, string>, probeRange?: TestProbeRange, mode?: 'full' | 'probe', testMode?: Record<string, any>) => Promise<void> | void
  onAnswerPendingInteraction?: (runId: string, values: Record<string, any>) => Promise<void> | void
  onRefresh: () => void
  onManageMcp?: () => void
}) {
  return <TestBenchView detail={detail} runs={runs} events={events} onTestRun={onTestRun} onAnswerPendingInteraction={onAnswerPendingInteraction} onRefresh={onRefresh} onManageMcp={onManageMcp} />
}
