import { INVENTORY } from '../state/schema'

export function InventoryTray() {
  return (
    <div className="sk-panel" style={{ padding: 14, width: 220 }}>
      <div style={{ font: '11px var(--sk-font-mono)', color: 'var(--sk-text-dim)', letterSpacing: 1 }}>
        INVENTORY
      </div>
      <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
        {INVENTORY.map((item) => (
          <div
            key={item.type}
            draggable
            onDragStart={(e) => e.dataTransfer.setData('text/sk-type', item.type)}
            style={{
              border: '1px solid var(--sk-edge)',
              borderRadius: 'var(--sk-radius-sm)',
              padding: '8px 10px',
              cursor: 'grab',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              background: 'rgba(70,227,255,0.05)',
            }}
          >
            <span style={{ fontSize: 13 }}>{item.label}</span>
            <span style={{ font: '10px var(--sk-font-mono)', color: 'var(--sk-text-dim)' }}>
              {item.w}×{item.h} {item.movable ? 'movable' : 'fixed'}
            </span>
          </div>
        ))}
      </div>
      <p style={{ font: '11px/1.5 var(--sk-font-mono)', color: 'var(--sk-text-dim)', marginTop: 14 }}>
        Drag onto the floor. Movable items can be dragged again at any time — including live.
      </p>
    </div>
  )
}
