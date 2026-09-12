import { useState } from 'react'
import { InventoryForm } from '../finish/InventoryForm'
import type { VenueInventory } from '../state/schema'
import { useStore } from '../state/store'

export function Finish() {
  const scan = useStore((s) => s.scan)
  const goto = useStore((s) => s.goto)
  const setInventory = useStore((s) => s.setInventory)
  const exportInteractions = useStore((s) => s.exportInteractions)
  const interactions = useStore((s) => s.interactions)
  const [doneInventory, setDoneInventory] = useState<VenueInventory | null>(null)
  const objects = scan?.objects ?? []

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      {doneInventory ? (
        <DoneCard
          inventory={doneInventory}
          interactions={interactions.length}
          onExport={exportInteractions}
          onStartOver={() => goto('landing')}
        />
      ) : (
        <InventoryForm
          key={scan?.roomId ?? 'no-scan'}
          objects={objects}
          scanned={scan !== null}
          onBack={() => goto('landing')}
          onSubmit={(inventory) => {
            setInventory(inventory)
            setDoneInventory(inventory)
          }}
        />
      )}
    </div>
  )
}

function DoneCard({
  inventory,
  interactions,
  onExport,
  onStartOver,
}: {
  inventory: VenueInventory
  interactions: number
  onExport: () => void
  onStartOver: () => void
}) {
  return (
    <div className="sk-panel" style={card}>
      <div style={eyebrow}>THANK YOU</div>
      <div style={title}>Journey complete</div>
      <div style={lines}>
        <div>
          {inventory.tables} tables · {inventory.chairs} seats · capacity {inventory.capacity}
        </div>
        <div>
          {inventory.areaSqm} m² · {inventory.zones} zones · {inventory.staffOnShift} staff on shift
        </div>
        <div>{interactions} interactions recorded</div>
      </div>
      <div style={actions}>
        <button onClick={onExport} style={summaryPrimary}>
          Export ground truth
        </button>
        <button onClick={onStartOver} style={summarySecondary}>
          Start over
        </button>
      </div>
    </div>
  )
}

const card = {
  width: 'min(520px, calc(100% - 40px))',
  maxHeight: 'calc(100% - 40px)',
  overflowY: 'auto' as const,
  padding: 20,
  zIndex: 4,
  animation: 'sk-rise 420ms var(--sk-ease) both',
}
const eyebrow = {
  color: 'var(--sk-cyan)',
  font: '11px var(--sk-font-mono)',
  letterSpacing: 2,
  marginBottom: 8,
}
const title = {
  color: 'var(--sk-text)',
  font: '22px var(--sk-font-display)',
}
const lines = {
  display: 'flex',
  flexDirection: 'column' as const,
  gap: 8,
  marginTop: 18,
  color: 'var(--sk-text-dim)',
  font: '11px var(--sk-font-mono)',
}
const actions = {
  display: 'flex',
  flexDirection: 'column' as const,
  gap: 8,
  marginTop: 20,
}
const summaryPrimary = {
  border: '1px solid var(--sk-cyan)',
  background: 'color-mix(in srgb, var(--sk-cyan) 12%, transparent)',
  color: 'var(--sk-cyan)',
  padding: '11px 14px',
  font: '14px var(--sk-font-display)',
  cursor: 'pointer',
  textAlign: 'left' as const,
}
const summarySecondary = {
  border: '1px solid var(--sk-edge)',
  background: 'transparent',
  color: 'var(--sk-text)',
  padding: '10px 14px',
  font: '13px var(--sk-font-display)',
  cursor: 'pointer',
  textAlign: 'left' as const,
}
