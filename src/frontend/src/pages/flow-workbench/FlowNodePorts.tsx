import { Handle, Position } from '@xyflow/react'
import type { FlowNode } from '../../api.ts'
import { isStartNode } from './nodeModel.ts'

export type PortSide = 'left' | 'right' | 'top' | 'bottom'
export type SidePortCounts = Record<PortSide, number>
export type PortCounts = { incoming: SidePortCounts; outgoing: SidePortCounts }
export type EdgePortAssignment = { sourceSide: PortSide; targetSide: PortSide; sourceIndex: number; targetIndex: number }

const PORT_LIMIT = 5
const TARGET_PORT_OFFSETS = [[44], [34, 50], [26, 42, 58], [18, 34, 50, 66], [14, 28, 42, 56, 70]]
const SOURCE_PORT_OFFSETS = [[56], [50, 66], [42, 58, 74], [34, 50, 66, 82], [30, 44, 58, 72, 86]]

export const PORT_SIDES: PortSide[] = ['left', 'right', 'top', 'bottom']

const PORT_SIDE_POSITION: Record<PortSide, Position> = {
  left: Position.Left,
  right: Position.Right,
  top: Position.Top,
  bottom: Position.Bottom,
}

function createSidePortCounts(): SidePortCounts {
  return { left: 0, right: 0, top: 0, bottom: 0 }
}

export function createPortCounts(): PortCounts {
  return { incoming: createSidePortCounts(), outgoing: createSidePortCounts() }
}

export function getPortHandleId(type: 'target' | 'source', side: PortSide, index: number) {
  return `${type}-${side}-${index}`
}

function getRenderedPortCount(count: number) {
  return Math.max(1, Math.min(PORT_LIMIT, count || 1))
}

function getPortStyle(type: 'target' | 'source', side: PortSide, index: number, count: number) {
  const groups = type === 'target' ? TARGET_PORT_OFFSETS : SOURCE_PORT_OFFSETS
  const offsets = groups[getRenderedPortCount(count) - 1]
  const value = `${offsets[index % offsets.length]}%`
  return side === 'left' || side === 'right' ? { top: value } : { left: value }
}

function renderHandles(type: 'target' | 'source', counts: SidePortCounts, fallbackSide: PortSide) {
  const total = PORT_SIDES.reduce((sum, side) => sum + counts[side], 0)
  return PORT_SIDES.flatMap((side) => {
    const count = counts[side] > 0 ? getRenderedPortCount(counts[side]) : total === 0 && side === fallbackSide ? 1 : 0
    return Array.from({ length: count }).map((_, index) => (
      <Handle
        key={`${type}-${side}-${index}`}
        id={getPortHandleId(type, side, index)}
        className={`cf-node-port cf-node-port-${type === 'target' ? 'in' : 'out'} cf-node-port-side-${side}`}
        type={type}
        position={PORT_SIDE_POSITION[side]}
        style={getPortStyle(type, side, index, count)}
      />
    ))
  })
}

export function FlowNodePorts({ node, counts }: { node: FlowNode; counts: PortCounts }) {
  return (
    <>
      {!isStartNode(node, node.id) && renderHandles('target', counts.incoming, 'left')}
      {(node.type !== 'terminal' || isStartNode(node, node.id)) && renderHandles('source', counts.outgoing, 'right')}
    </>
  )
}
