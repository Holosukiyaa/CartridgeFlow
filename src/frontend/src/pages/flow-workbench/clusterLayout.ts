import dagre from '@dagrejs/dagre'
import type { FlowEdge } from '../../api.ts'

export type ClusterLayoutNode = {
  id: string
  x: number
  y: number
  width: number
  height: number
}

export type ClusterLayoutSatellite = {
  editorId: string
  nodeId: string
  x: number
  y: number
  width: number
  height: number
}

export type ClusterLayoutResult = {
  nodeLayout: Record<string, { x: number; y: number }>
  satelliteLayout: Record<string, { x: number; y: number }>
  bounds: { x: number; y: number; width: number; height: number }
  wrapped: boolean
}

type NodeCluster = {
  id: string
  width: number
  height: number
  mainOffset: { x: number; y: number }
  satellites: Array<ClusterLayoutSatellite & { offsetX: number; offsetY: number }>
}

type PlacedCluster = NodeCluster & { x: number; y: number }

const CLUSTER_MARGIN_X = 80
const CLUSTER_MARGIN_Y = 100
const RANK_GAP = 150
const NODE_GAP = 96
const ROW_GAP = 180
const SATELLITE_GAP = 48
const SATELLITE_CLEARANCE = 18

function isStructuralEdge(edge: FlowEdge) {
  return String(edge.scope || 'root') !== 'branch'
}

type LocalSatellite = ClusterLayoutSatellite & { offsetX: number; offsetY: number }

function compactSatellites(node: ClusterLayoutNode, satellites: ClusterLayoutSatellite[]): LocalSatellite[] {
  if (satellites.length === 0) return []
  if (satellites.length === 1) {
    const satellite = satellites[0]
    return [{
      ...satellite,
      offsetX: node.width + SATELLITE_GAP,
      offsetY: node.height / 2 - satellite.height / 2,
    }]
  }
  if (satellites.length === 2) {
    const [left, right] = satellites
    return [
      { ...left, offsetX: -left.width - SATELLITE_GAP, offsetY: node.height / 2 - left.height / 2 },
      { ...right, offsetX: node.width + SATELLITE_GAP, offsetY: node.height / 2 - right.height / 2 },
    ]
  }

  const assignments = satellites.map((satellite, index) => {
    const slot = index % 4
    return {
      satellite,
      column: Math.floor(index / 4),
      side: slot % 2 === 0 ? 'left' as const : 'right' as const,
      row: slot < 2 ? 'top' as const : 'bottom' as const,
    }
  })
  const columnWidths = new Map<string, number>()
  assignments.forEach(({ satellite, side, column }) => {
    const key = `${side}:${column}`
    columnWidths.set(key, Math.max(columnWidths.get(key) || 0, satellite.width))
  })
  const precedingWidth = (side: 'left' | 'right', column: number) => Array.from({ length: column }, (_, index) => (
    columnWidths.get(`${side}:${index}`) || 0
  )).reduce((sum, width) => sum + width + SATELLITE_CLEARANCE, 0)

  return assignments.map(({ satellite, side, column, row }) => {
    const outward = precedingWidth(side, column)
    const offsetX = side === 'left'
      ? -SATELLITE_GAP - outward - satellite.width
      : node.width + SATELLITE_GAP + outward
    const offsetY = row === 'top'
      ? node.height / 2 - SATELLITE_CLEARANCE / 2 - satellite.height
      : node.height / 2 + SATELLITE_CLEARANCE / 2
    return { ...satellite, offsetX, offsetY }
  })
}

function buildNodeClusters(nodes: ClusterLayoutNode[], satellites: ClusterLayoutSatellite[]) {
  const satellitesByNode = new Map<string, ClusterLayoutSatellite[]>()
  satellites.forEach((satellite) => {
    satellitesByNode.set(satellite.nodeId, [...(satellitesByNode.get(satellite.nodeId) || []), satellite])
  })

  return nodes.map<NodeCluster>((node) => {
    const nodeSatellites = satellitesByNode.get(node.id) || []
    let minX = 0
    let minY = 0
    let maxX = node.width
    let maxY = node.height

    const relativeSatellites = compactSatellites(node, nodeSatellites)

    relativeSatellites.forEach((satellite) => {
      const { offsetX, offsetY } = satellite
      minX = Math.min(minX, offsetX)
      minY = Math.min(minY, offsetY)
      maxX = Math.max(maxX, offsetX + satellite.width)
      maxY = Math.max(maxY, offsetY + satellite.height)
    })

    return {
      id: node.id,
      width: maxX - minX,
      height: maxY - minY,
      mainOffset: { x: -minX, y: -minY },
      satellites: relativeSatellites.map((satellite) => ({
        ...satellite,
        offsetX: satellite.offsetX - minX,
        offsetY: satellite.offsetY - minY,
      })),
    }
  })
}

function layoutWithDagre(clusters: NodeCluster[], edges: FlowEdge[]) {
  const layoutGraph = new dagre.graphlib.Graph()
  const clusterIds = new Set(clusters.map((cluster) => cluster.id))
  layoutGraph.setDefaultEdgeLabel(() => ({}))
  layoutGraph.setGraph({
    rankdir: 'LR',
    align: 'UL',
    acyclicer: 'greedy',
    ranker: 'network-simplex',
    nodesep: NODE_GAP,
    ranksep: RANK_GAP,
    edgesep: 42,
    marginx: CLUSTER_MARGIN_X,
    marginy: CLUSTER_MARGIN_Y,
  })

  clusters.forEach((cluster) => {
    layoutGraph.setNode(cluster.id, { width: cluster.width, height: cluster.height })
  })
  edges.forEach((edge) => {
    if (!edge.from || !edge.to || edge.from === edge.to) return
    if (!clusterIds.has(edge.from) || !clusterIds.has(edge.to)) return
    layoutGraph.setEdge(edge.from, edge.to, {
      minlen: 1,
      weight: isStructuralEdge(edge) ? 4 : 1,
    })
  })

  dagre.layout(layoutGraph)
  return clusters.map<PlacedCluster>((cluster) => {
    const point = layoutGraph.node(cluster.id)
    return {
      ...cluster,
      x: Math.round((point?.x || cluster.width / 2) - cluster.width / 2),
      y: Math.round((point?.y || cluster.height / 2) - cluster.height / 2),
    }
  })
}

function getBounds(clusters: PlacedCluster[]) {
  if (!clusters.length) return { x: 0, y: 0, width: 1, height: 1 }
  const minX = Math.min(...clusters.map((cluster) => cluster.x))
  const minY = Math.min(...clusters.map((cluster) => cluster.y))
  const maxX = Math.max(...clusters.map((cluster) => cluster.x + cluster.width))
  const maxY = Math.max(...clusters.map((cluster) => cluster.y + cluster.height))
  return { x: minX, y: minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) }
}

function groupRanks(clusters: PlacedCluster[]) {
  const ranks: PlacedCluster[][] = []
  clusters
    .slice()
    .sort((a, b) => a.x - b.x || a.y - b.y)
    .forEach((cluster) => {
      const centerX = cluster.x + cluster.width / 2
      const rank = ranks.find((items) => {
        const first = items[0]
        return Math.abs(centerX - (first.x + first.width / 2)) < 8
      })
      if (rank) rank.push(cluster)
      else ranks.push([cluster])
    })
  return ranks.sort((a, b) => {
    const centerA = a.reduce((sum, cluster) => sum + cluster.x + cluster.width / 2, 0) / a.length
    const centerB = b.reduce((sum, cluster) => sum + cluster.x + cluster.width / 2, 0) / b.length
    return centerA - centerB
  })
}

function wrapRanks(clusters: PlacedCluster[], maxRowWidth: number) {
  const rankBlocks = groupRanks(clusters).map((rank) => {
    const ordered = rank.slice().sort((a, b) => a.y - b.y)
    const width = Math.max(...ordered.map((cluster) => cluster.width))
    const height = ordered.reduce((sum, cluster) => sum + cluster.height, 0) + Math.max(0, ordered.length - 1) * NODE_GAP
    let cursorY = 0
    const items = ordered.map((cluster) => {
      const item = { cluster, x: (width - cluster.width) / 2, y: cursorY }
      cursorY += cluster.height + NODE_GAP
      return item
    })
    return { width, height, items }
  })

  const rows: typeof rankBlocks[] = []
  rankBlocks.forEach((block) => {
    const current = rows.at(-1)
    const currentWidth = current?.reduce((sum, item) => sum + item.width, 0) || 0
    const gaps = current?.length || 0
    if (!current || currentWidth + gaps * RANK_GAP + block.width > maxRowWidth) rows.push([block])
    else current.push(block)
  })

  const placed: PlacedCluster[] = []
  let rowY = CLUSTER_MARGIN_Y
  rows.forEach((row, rowIndex) => {
    const rowWidth = row.reduce((sum, block) => sum + block.width, 0) + Math.max(0, row.length - 1) * RANK_GAP
    const rowHeight = Math.max(...row.map((block) => block.height))
    let cursorX = rowIndex % 2 === 0 ? CLUSTER_MARGIN_X : CLUSTER_MARGIN_X + rowWidth
    row.forEach((block) => {
      const blockX = rowIndex % 2 === 0 ? cursorX : cursorX - block.width
      const blockY = rowY + (rowHeight - block.height) / 2
      block.items.forEach((item) => {
        placed.push({ ...item.cluster, x: Math.round(blockX + item.x), y: Math.round(blockY + item.y) })
      })
      cursorX += rowIndex % 2 === 0 ? block.width + RANK_GAP : -(block.width + RANK_GAP)
    })
    rowY += rowHeight + ROW_GAP
  })
  return placed
}

function chooseAdaptiveLayout(dagreLayout: PlacedCluster[], targetAspect: number) {
  if (dagreLayout.length <= 4) return { placed: dagreLayout, wrapped: false }
  const dagreBounds = getBounds(dagreLayout)
  const widestCluster = Math.max(...dagreLayout.map((cluster) => cluster.width))
  const desiredAspect = Math.max(1.5, Math.min(2.8, targetAspect))
  const candidates = [{ placed: dagreLayout, wrapped: false }]
  const divisions = Math.min(8, dagreLayout.length)
  for (let divisor = 2; divisor <= divisions; divisor += 1) {
    const rowWidth = Math.max(widestCluster, dagreBounds.width / divisor)
    candidates.push({ placed: wrapRanks(dagreLayout, rowWidth), wrapped: true })
  }
  return candidates.reduce((best, candidate) => {
    const bounds = getBounds(candidate.placed)
    const aspect = bounds.width / Math.max(1, bounds.height)
    const score = Math.abs(Math.log(aspect / desiredAspect))
    const bestBounds = getBounds(best.placed)
    const bestAspect = bestBounds.width / Math.max(1, bestBounds.height)
    const bestScore = Math.abs(Math.log(bestAspect / desiredAspect))
    if (score < bestScore - 0.015) return candidate
    if (Math.abs(score - bestScore) <= 0.015 && bounds.width > bestBounds.width) return candidate
    return best
  })
}

export function buildClusterAwareLayout({
  nodes,
  satellites,
  edges,
  targetAspect,
}: {
  nodes: ClusterLayoutNode[]
  satellites: ClusterLayoutSatellite[]
  edges: FlowEdge[]
  targetAspect: number
}): ClusterLayoutResult {
  const clusters = buildNodeClusters(nodes, satellites)
  const dagreLayout = layoutWithDagre(clusters, edges)
  const adaptive = chooseAdaptiveLayout(dagreLayout, targetAspect)
  const placed = adaptive.placed
  const bounds = getBounds(placed)
  const nodeLayout: ClusterLayoutResult['nodeLayout'] = {}
  const satelliteLayout: ClusterLayoutResult['satelliteLayout'] = {}

  placed.forEach((cluster) => {
    nodeLayout[cluster.id] = {
      x: Math.round(cluster.x + cluster.mainOffset.x),
      y: Math.round(cluster.y + cluster.mainOffset.y),
    }
    cluster.satellites.forEach((satellite) => {
      satelliteLayout[satellite.editorId] = {
        x: Math.round(cluster.x + satellite.offsetX),
        y: Math.round(cluster.y + satellite.offsetY),
      }
    })
  })

  return { nodeLayout, satelliteLayout, bounds, wrapped: adaptive.wrapped }
}
