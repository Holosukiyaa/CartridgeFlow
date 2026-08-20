import { Handle, Position } from '@xyflow/react'
import {
  emptyPortCounts,
  getPortHandleId,
  portOffset,
  visiblePortCount,
  type PortCounts,
  type PortSide,
} from './graph.ts'

const SIDE_POSITION: Record<PortSide, Position> = {
  left: Position.Left,
  right: Position.Right,
  top: Position.Top,
  bottom: Position.Bottom,
}

function handles(type: 'target' | 'source', counts: PortCounts, fallback: PortSide) {
  const total = (['left', 'right', 'top', 'bottom'] as PortSide[]).reduce((sum, side) => sum + counts[side][type === 'target' ? 'incoming' : 'outgoing'], 0)
  return (['left', 'right', 'top', 'bottom'] as PortSide[]).flatMap((side) => {
    const raw = counts[side][type === 'target' ? 'incoming' : 'outgoing']
    const count = raw > 0 ? visiblePortCount(raw) : total === 0 && side === fallback ? 1 : 0
    return Array.from({ length: count }, (_, index) => {
      const offset = portOffset(type, index, count)
      const style = side === 'left' || side === 'right' ? { top: offset } : { left: offset }
      return <Handle
        key={getPortHandleId(type, side, index)}
        id={getPortHandleId(type, side, index)}
        className={`creator-port is-${type} is-${side}`}
        type={type}
        position={SIDE_POSITION[side]}
        style={style}
      />
    })
  })
}

export function StepPorts({ counts, vertical }: { counts?: PortCounts; vertical: boolean }) {
  const value = counts || emptyPortCounts()
  return <>
    {handles('target', value, vertical ? 'top' : 'left')}
    {handles('source', value, vertical ? 'bottom' : 'right')}
  </>
}
