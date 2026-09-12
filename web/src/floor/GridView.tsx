import { useRef, useState } from 'react'
import { useStore } from '../state/store'
import type { ObjectType, VenueObject } from '../state/schema'

const TYPE_COLOR: Record<ObjectType, string> = {
  bar: 'var(--sk-amber)',
  table: 'var(--sk-cyan)',
  chair: 'var(--sk-text-dim)',
  plant: 'var(--sk-teal)',
  stage: 'var(--sk-magenta)',
  dock: 'var(--sk-teal)',
}

interface Props {
  cell: number
  editable?: boolean
  showRoute?: boolean
  showLabels?: boolean
}

/** Isometric-feeling holographic floor. Shared by the setup editor and the live minimap. */
export function GridView({ cell, editable = false, showRoute = true, showLabels = true }: Props) {
  const grid = useStore((s) => s.grid)
  const route = useStore((s) => s.route)
  const robot = useStore((s) => s.robot)
  const replanning = useStore((s) => s.replanning)
  const moveObject = useStore((s) => s.moveObject)
  const addObject = useStore((s) => s.addObject)
  const ref = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState<{ id: string; dx: number; dy: number } | null>(null)
  const [ghost, setGhost] = useState<{ x: number; y: number; o: VenueObject } | null>(null)

  const W = grid.width * cell
  const H = grid.height * cell

  const cellFromEvent = (e: { clientX: number; clientY: number }) => {
    const rect = ref.current!.getBoundingClientRect()
    return {
      x: Math.floor((e.clientX - rect.left) / cell),
      y: Math.floor((e.clientY - rect.top) / cell),
    }
  }

  const onPointerDown = (e: React.PointerEvent, o: VenueObject) => {
    if (!editable || !o.movable) return
    e.preventDefault()
    const c = cellFromEvent(e)
    setDragging({ id: o.id, dx: c.x - o.x, dy: c.y - o.y })
    setGhost({ x: o.x, y: o.y, o })
    ;(e.target as Element).setPointerCapture(e.pointerId)
  }

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging || !ghost) return
    const c = cellFromEvent(e)
    setGhost({ ...ghost, x: c.x - dragging.dx, y: c.y - dragging.dy })
  }

  const onPointerUp = () => {
    if (dragging && ghost) moveObject(dragging.id, ghost.x, ghost.y)
    setDragging(null)
    setGhost(null)
  }

  const onDrop = (e: React.DragEvent) => {
    if (!editable) return
    e.preventDefault()
    const type = e.dataTransfer.getData('text/sk-type') as ObjectType
    if (!type) return
    const c = cellFromEvent(e)
    addObject(type, Math.max(0, c.x), Math.max(0, c.y))
  }

  return (
    <div
      ref={ref}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onDragOver={(e) => editable && e.preventDefault()}
      onDrop={onDrop}
      style={{
        position: 'relative',
        width: W,
        height: H,
        borderRadius: 'var(--sk-radius-md)',
        border: '1px solid var(--sk-edge)',
        background:
          'radial-gradient(120% 90% at 50% 110%, rgba(70,227,255,0.10), rgba(5,7,15,0.86) 65%)',
        boxShadow: replanning ? '0 0 40px rgba(42,217,176,0.35)' : 'var(--sk-glow-cyan)',
        transition: 'box-shadow var(--sk-dur-med) var(--sk-ease)',
        touchAction: 'none',
        overflow: 'hidden',
      }}
    >
      <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
        <g stroke="rgba(70,227,255,0.14)" strokeWidth={1}>
          {Array.from({ length: grid.width + 1 }, (_, i) => (
            <line key={`v${i}`} x1={i * cell} y1={0} x2={i * cell} y2={H} />
          ))}
          {Array.from({ length: grid.height + 1 }, (_, i) => (
            <line key={`h${i}`} x1={0} y1={i * cell} x2={W} y2={i * cell} />
          ))}
        </g>

        {grid.zones.map((z) => (
          <g key={z.id}>
            <rect
              x={z.x * cell}
              y={z.y * cell}
              width={z.w * cell}
              height={z.h * cell}
              fill={z.kind === 'cleaning' ? 'rgba(42,217,176,0.09)' : 'rgba(255,181,71,0.09)'}
              stroke={z.kind === 'cleaning' ? 'var(--sk-teal)' : 'var(--sk-amber)'}
              strokeDasharray="4 4"
            />
            {showLabels && (
              <text
                x={z.x * cell + 6}
                y={z.y * cell + 14}
                fill={z.kind === 'cleaning' ? 'var(--sk-teal)' : 'var(--sk-amber)'}
                style={{ font: '10px var(--sk-font-mono)' }}
              >
                {z.label}
              </text>
            )}
          </g>
        ))}

        {showRoute && route.length > 1 && (
          <polyline
            points={route.map((c) => `${c.x * cell + cell / 2},${c.y * cell + cell / 2}`).join(' ')}
            fill="none"
            stroke="var(--sk-teal)"
            strokeWidth={Math.max(2, cell / 6)}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="10 10"
            style={{ animation: 'sk-dash 1.2s linear infinite', filter: 'drop-shadow(0 0 6px var(--sk-teal))' }}
          />
        )}

        <g>
          <circle
            cx={robot.x * cell + cell / 2}
            cy={robot.y * cell + cell / 2}
            r={Math.max(5, cell * 0.32)}
            fill="var(--sk-cyan)"
            style={{ filter: 'drop-shadow(0 0 10px var(--sk-cyan))' }}
          />
          <circle
            cx={robot.x * cell + cell / 2}
            cy={robot.y * cell + cell / 2}
            r={Math.max(5, cell * 0.32)}
            fill="none"
            stroke="var(--sk-cyan)"
            style={{ animation: 'sk-pulse-ring 2s var(--sk-ease) infinite', transformOrigin: `${robot.x * cell + cell / 2}px ${robot.y * cell + cell / 2}px` }}
          />
        </g>
      </svg>

      {grid.objects.map((o) => {
        const shown = ghost && ghost.o.id === o.id ? { ...o, x: ghost.x, y: ghost.y } : o
        return (
          <div
            key={o.id}
            onPointerDown={(e) => onPointerDown(e, o)}
            title={o.movable ? `${o.label} — drag to move` : `${o.label} — fixed`}
            style={{
              position: 'absolute',
              left: shown.x * cell + 2,
              top: shown.y * cell + 2,
              width: o.w * cell - 4,
              height: o.h * cell - 4,
              borderRadius: 'var(--sk-radius-sm)',
              border: `1px solid ${TYPE_COLOR[o.type]}`,
              background: `color-mix(in srgb, ${TYPE_COLOR[o.type]} 16%, transparent)`,
              boxShadow: `0 0 12px color-mix(in srgb, ${TYPE_COLOR[o.type]} 40%, transparent)`,
              cursor: editable && o.movable ? 'grab' : 'default',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              font: `${Math.max(8, cell * 0.28)}px var(--sk-font-mono)`,
              color: TYPE_COLOR[o.type],
              opacity: ghost && ghost.o.id === o.id ? 0.75 : 1,
              transition: dragging ? 'none' : 'left var(--sk-dur-med) var(--sk-ease), top var(--sk-dur-med) var(--sk-ease)',
              userSelect: 'none',
            }}
          >
            {showLabels && cell >= 22 ? o.label : null}
          </div>
        )
      })}
    </div>
  )
}
