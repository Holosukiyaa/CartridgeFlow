import { Badge, Box, Code, HStack, Heading, SimpleGrid, Text, VStack } from '../../ui.tsx'
import type { FlowGraph, FlowNode, ValidationResponse } from '../../api.ts'
import { getNodeCategory } from './nodeModel.ts'

export function CapabilityPill({ label, value }: { label: string; value: string }) {
  return (
    <Box className="cf-capability-pill">
      <small>{label}</small>
      <span>{value}</span>
    </Box>
  )
}

export function SelectedNodeBrief({ node, cartridgeName }: { node: FlowNode | null; cartridgeName: string }) {
  if (!node) {
    return (
      <Box p={4} className="cf-node-brief">
        <Text className="cf-kicker">当前 Flow</Text>
        <Heading size="sm" mb={2}>{cartridgeName}</Heading>
        <Text color="fg.muted">选择大图或左侧目录中的节点，查看它在链路中的职责。新版节点工作区会围绕“输入、处理、传递、存放、控制”五类展开。</Text>
      </Box>
    )
  }
  const category = getNodeCategory(node)
  const params = node.params || {}
  const items = [
    { label: '分类', value: category.shortLabel },
    { label: '动作', value: node.action || '未配置' },
    { label: '下一步', value: node.next || '由连线决定' },
    { label: 'AI', value: node.agent || '未接入' },
    { label: '工具', value: node.tools?.length ? `${node.tools.length} 项` : '未配置' },
    { label: '参数', value: Object.keys(params).length ? `${Object.keys(params).length} 项` : '未配置' },
  ]
  return (
    <Box p={4} className="cf-node-brief">
      <HStack justify="space-between" align="start" mb={2}>
        <Box>
          <Text className="cf-kicker">Node Brief</Text>
          <Heading size="sm">{node.title}</Heading>
        </Box>
        <Badge className="cf-badge" style={{ color: category.color } as any}>{category.label}</Badge>
      </HStack>
      <Text color="fg.muted" mb={3}>{node.locked ? '这是系统锁定节点，用来维持 Flow 生命周期。' : category.description}</Text>
      <SimpleGrid columns={3} gap={2} className="cf-capability-grid">
        {items.map((item) => <CapabilityPill key={item.label} label={item.label} value={item.value} />)}
      </SimpleGrid>
    </Box>
  )
}

export function ValidationCard({ validation }: { validation: ValidationResponse | null }) {
  if (!validation) return null
  return (
    <Box p={4} className="cf-panel">
      <Text className="cf-kicker">Validation</Text>
      <Text fontWeight="semibold" color={validation.valid ? 'fg.success' : 'fg.error'}>{validation.summary || (validation.valid ? '校验通过' : '校验失败')}</Text>
      {validation.errors.length > 0 && <VStack align="stretch" gap={1} mt={2}>{validation.errors.map((item, index) => <Text key={index} fontSize="sm" color="fg.error">{item}</Text>)}</VStack>}
      {validation.warnings.length > 0 && <VStack align="stretch" gap={1} mt={2}>{validation.warnings.map((item, index) => <Text key={index} fontSize="sm" color="fg.muted">{item}</Text>)}</VStack>}
    </Box>
  )
}

export function Inspector({ title, data }: { title: string; data: any }) {
  return (
    <Box p={4} className="cf-panel">
      <Text className="cf-kicker">Inspector</Text>
      <Heading size="sm" mb={3}>{title}</Heading>
      <Box maxH="360px" overflow="auto">
        <Code display="block" whiteSpace="pre-wrap" fontSize="xs" p={3} className="cf-terminal">{JSON.stringify(data, null, 2)}</Code>
      </Box>
    </Box>
  )
}

export function FlowMap({ graph, nodes, selectedNode, onFocusNode }: {
  graph: FlowGraph
  nodes: FlowNode[]
  selectedNode: FlowNode | null
  onFocusNode: (node: FlowNode) => void
}) {
  const order = new Map(graph.nodes.map((node, index) => [node.id, index + 1]))
  return (
    <Box p={4} className="cf-panel cf-flow-nav-panel">
      <Text className="cf-kicker">Flow Map</Text>
      <Heading size="sm" mb={1}>节点目录</Heading>
      <Text fontSize="sm" color="fg.muted" mb={3}>只展示可扩展节点。根节点仍保留在上方大图里。</Text>
      {nodes.length === 0 ? (
        <Text fontSize="sm" color="fg.muted">还没有可配置节点。可以在大图右键新增，或从下方五类节点开始。</Text>
      ) : (
        <VStack align="stretch" gap={2} className="cf-subflow-list">
          {nodes.map((node) => {
            const category = getNodeCategory(node)
            return (
              <button key={node.id} className={`cf-flow-nav-item ${selectedNode?.id === node.id ? 'active' : ''}`} onClick={() => onFocusNode(node)}>
                <b style={{ background: category.bg, color: category.color }}>{String(order.get(node.id) || 0).padStart(2, '0')}</b>
                <span>{node.title}</span>
                <small>{category.shortLabel} · {node.action || '未配置'}</small>
              </button>
            )
          })}
        </VStack>
      )}
    </Box>
  )
}
